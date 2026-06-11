"""CicloManager — orquestra ciclos de coleta e análise (ARCHITECTURE §9)."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.core.agent.agent_loop import AgentLoop
from src.dashboard.rollup_calculator import RollupCalculator
from src.errors.exceptions import ColetorIndisponivelError
from src.intake.rss.google_news import GoogleNewsRSSCollector
from src.memory.database import Database
from src.memory.repositories.ciclos_repo import CiclosRepo
from src.memory.repositories.items_repo import ItemsRepo
from src.memory.repositories.metricas_repo import MetricasRepo
from src.memory.repositories.rollups_repo import RollupsRepo
from src.processing.dedup_engine import RSSDeduplicationEngine
from src.processing.relevance_engine import Router, HardCapFilter, RelevanceEngine
from src.processing.text_normalizer import TextNormalizer

log = logging.getLogger(__name__)


class CicloManager:
    def __init__(self, db: Database, config: dict | None = None) -> None:
        self._db = db
        self._config = config or {}
        self._items_repo = ItemsRepo(db)
        self._ciclos_repo = CiclosRepo(db)
        self._metricas_repo = MetricasRepo(db)
        self._rollups_repo = RollupsRepo(db)

    def executar_ciclo(self) -> dict:
        """Executa um ciclo completo: coleta → dedup → relevância → análise → briefing → rollups."""
        ciclo_id = str(uuid.uuid4())[:12]
        inicio = time.monotonic()

        log.info("ciclo.iniciando", extra={"dados": {"ciclo_id": ciclo_id}})
        self._ciclos_repo.iniciar(ciclo_id)

        stats = {
            "coletados": 0,
            "processados": 0,
            "relevantes": 0,
            "acima_cap": 0,
            "analisados": 0,
        }

        try:
            # 1. COLETA
            itens_coletados = self._coletar()
            stats["coletados"] = len(itens_coletados)
            log.info("ciclo.coletado", extra={"dados": {"n": len(itens_coletados)}})

            # 2. PROCESSAMENTO (dedup + normalização + relevância)
            itens_processados = self._processar(itens_coletados, ciclo_id)
            stats["processados"] = len(itens_processados)

            # 3. FILTRO DE RELEVÂNCIA
            itens_relevantes, n_acima_cap = self._filtrar_relevancia(itens_processados)
            stats["relevantes"] = len(itens_relevantes)
            stats["acima_cap"] = n_acima_cap

            # 4. ANÁLISE IA
            if itens_relevantes:
                agent_loop = AgentLoop(self._config)
                result_analise = agent_loop.executar(itens_relevantes, ciclo_id)
                stats["analisados"] = result_analise.itens_analisados
                log.info("ciclo.analisado", extra={"dados": {"modo_degradado": result_analise.modo_degradado}})

            # 5. RECALCULAR ROLLUPS
            RollupCalculator(self._db, self._rollups_repo).recalcular_todos()

            # 6. FINALIZAR
            duracao_ms = int((time.monotonic() - inicio) * 1000)
            self._ciclos_repo.finalizar(
                ciclo_id=ciclo_id,
                status="COMPLETO",
                stats=stats,
                duracao_ms=duracao_ms,
            )

            log.info("ciclo.concluido", extra={"dados": {
                "ciclo_id": ciclo_id,
                "stats": stats,
                "duracao_ms": duracao_ms,
            }})

            return {"ciclo_id": ciclo_id, "status": "COMPLETO", **stats}

        except Exception as e:
            log.error("ciclo.erro", extra={"dados": {"ciclo_id": ciclo_id, "erro": str(e)}})
            self._ciclos_repo.finalizar(
                ciclo_id=ciclo_id,
                status="FALHA",
                stats=stats,
                erro_msg=str(e),
            )
            return {"ciclo_id": ciclo_id, "status": "FALHA", "erro": str(e)}

    def _coletar(self) -> list[dict]:
        """Coleta de todas as fontes ativas."""
        itens = []
        # Lê queries do config.sistema.queries_google_news
        from src.core.config.config_loader import instancia as get_cfg
        try:
            cfg = get_cfg()
            queries_config = cfg.sistema.queries_google_news
        except Exception:
            queries_config = ["Exército Brasileiro", "Forças Armadas"]
        fonte = GoogleNewsRSSCollector(
            fonte_id="google_news_eb",
            nome="Google News — EB",
            queries=queries_config,
            ativo=True,
        )
        try:
            coletados = fonte.coletar()
            itens.extend([{
                "item_id": i,
                "titulo": c.titulo,
                "url": c.link,
                "conteudo_texto": c.conteudo_texto,
                "data_pub": c.pub_date,
                "fonte_id": c.fonte_id,
                "veiculo": c.veiculo,
            } for i, c in enumerate(coletados, 1)])
        except ColetorIndisponivelError:
            log.warning("ciclo.fonte_indisponivel", extra={"dados": {"fonte": fonte.fonte_id}})
        return itens

    def _processar(self, itens: list[dict], ciclo_id: str) -> list[dict]:
        """Dedup, normalização, relevância e persistência no banco."""
        from datetime import datetime, timezone

        processados = []
        vistas_hashes = set()
        router = Router(threshold=0.5)

        for item in itens:
            # Dedup
            hash_item = RSSDeduplicationEngine.fazer_hash(item["url"], item["titulo"])
            if hash_item in vistas_hashes or self._items_repo.existe(hash_item):
                continue
            vistas_hashes.add(hash_item)

            # Normaliza
            conteudo_norm = TextNormalizer.normalizar(item["conteudo_texto"])

            # Relevância
            eh_relevante, score = router.classificar(
                titulo=item["titulo"],
                conteudo=conteudo_norm,
                fonte_id=item["fonte_id"],
                trust_score=0.7,
            )

            if not eh_relevante:
                continue

            # Persiste no banco (Trilha B)
            row = {
                "content_hash": hash_item,
                "fonte_trilha": "B",
                "titulo": item["titulo"],
                "link_original": item["url"],
                "conteudo_texto": conteudo_norm,
                "veiculo": item.get("veiculo", ""),
                "data_pub": item.get("data_pub", ""),
                "fonte_id": item.get("fonte_id", ""),
                "relevance_score": score,
                "pendente_analise": 1,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            resultado = self._items_repo.inserir_ou_ignorar_b(row, ciclo_id)
            if resultado.duplicado:
                continue

            item["item_id"] = resultado.item_id
            item["relevance_score"] = score
            item["content_hash"] = hash_item
            item["conteudo_texto"] = conteudo_norm
            item["ciclo_id"] = ciclo_id
            processados.append(item)

        return processados

    def _filtrar_relevancia(self, itens: list[dict]) -> tuple[list[dict], int]:
        """Aplica hard cap de itens por ciclo."""
        cap_filter = HardCapFilter(cap=100)
        selecionados, n_acima = cap_filter.filtrar(itens)
        return selecionados, n_acima
