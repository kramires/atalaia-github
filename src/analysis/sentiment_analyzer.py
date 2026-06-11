"""SentimentAnalyzer — análise de sentimento (SPEC-06)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from src.core.agent.tool_registry import ToolRegistry
from src.errors.exceptions import AnalyseDegradadaError
from src.memory.database import Database
from src.memory.repositories.analise_ia_repo import AnaliseIARecord, AnaliseIARepo
from src.providers.factory import ProviderFactory

log = logging.getLogger(__name__)


class RespostaSentimentoLLM(BaseModel):
    item_id: int
    sentimento_ia: str = Field(..., pattern="^(POSITIVA|NEGATIVA|NEUTRA)$")
    confianca: float = Field(..., ge=0.0, le=1.0)
    tipo_inferencia: str = Field(..., pattern="^(FATO|INTERPRETACAO|HIPOTESE)$")
    evidencia: str = ""


class RespostaSentimentoBatch(BaseModel):
    """Wrapper para completar_estruturado receber array de análises."""
    respostas: list[RespostaSentimentoLLM]


class SentimentAnalyzer:
    def __init__(self, db: Database, provider_factory: ProviderFactory) -> None:
        self._db = db
        self._provider_factory = provider_factory
        self._repo = AnaliseIARepo(db)

    def analisar(self, itens: list[dict], ciclo_id: str) -> list[RespostaSentimentoLLM]:
        """Analisa sentimento de itens em batches."""
        provider = self._provider_factory.provider_para("analise")
        respostas: list[RespostaSentimentoLLM] = []

        system = """Você é um analista de sentimento especializado em mídia.
Classifique o sentimento de cada item em relação ao Exército Brasileiro.
Retorne APENAS o JSON com array de análises, sem texto adicional."""

        # Batches de 20 itens
        for i in range(0, len(itens), 20):
            batch = itens[i : i + 20]
            user_text = "\n".join(
                f"ID={item['item_id']}: {item.get('titulo', '')} | {item.get('conteudo_texto', '')[:200]}"
                for item in batch
            )

            try:
                resp = provider.completar_estruturado(
                    system=system,
                    user=user_text,
                    schema=RespostaSentimentoBatch,
                )
                if isinstance(resp, RespostaSentimentoBatch):
                    respostas.extend(resp.respostas)
            except AnalyseDegradadaError:
                log.warning("sentimento.degradado", extra={"dados": {"batch_size": len(batch)}})
                # Fallback rule-based
                for item in batch:
                    respostas.append(
                        RespostaSentimentoLLM(
                            item_id=item["item_id"],
                            sentimento_ia="NEUTRA",
                            confianca=0.0,
                            tipo_inferencia="HIPOTESE",
                            evidencia="Modo degradado",
                        )
                    )

        # Persiste análises
        records = [
            AnaliseIARecord(
                item_id=r.item_id,
                sentimento_ia=r.sentimento_ia,
                confianca=r.confianca,
                tipo_inferencia=r.tipo_inferencia,
                evidencia=r.evidencia,
                provider=provider.nome,
                modelo=provider.modelo,
                ciclo_id=ciclo_id,
            )
            for r in respostas
        ]
        self._repo.inserir_lote(records)
        return respostas


@ToolRegistry.registrar("analisar_sentimento", "Analisa sentimento de itens", timeout=120)
def analisar_sentimento(itens: list[dict], ciclo_id: str) -> dict:
    """Tool wrapper para sentimento."""
    # Injeção via singleton — ver AgentLoop
    db = Database.instancia()
    from src.core.config.config_loader import instancia as get_config
    factory = ProviderFactory(get_config())
    analyzer = SentimentAnalyzer(db, factory)
    respostas = analyzer.analisar(itens, ciclo_id)
    return {
        "analisados": len(respostas),
        "respostas": [r.model_dump() for r in respostas],
    }
