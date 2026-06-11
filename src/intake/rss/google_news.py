"""GoogleNewsRSSCollector — RSS do Google News (SPEC-02 §8.1)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from src.errors.circuit_breaker import CircuitBreaker
from src.errors.exceptions import ColetorIndisponivelError
from src.intake.rss.base import ColetorPlugavel, ItemColetado
from src.processing.html_sanitizer import HTMLSanitizer
from src.processing.text_normalizer import TextNormalizer

log = logging.getLogger(__name__)


class GoogleNewsRSSCollector:
    BASE_URL = "https://news.google.com/rss/search"

    def __init__(self, fonte_id: str, nome: str, queries: list[str], ativo: bool = True) -> None:
        self.fonte_id = fonte_id
        self.nome = nome
        self.queries = queries
        self.ativo_config = ativo
        self.circuit_breaker = CircuitBreaker(
            nome=f"google_news_{fonte_id}", falhas_para_abrir=3, timeout_reset_segundos=120
        )

    def coletar(self) -> list[ItemColetado]:
        """Busca via Google News RSS."""
        if not self.esta_ativo():
            raise ColetorIndisponivelError(f"{self.nome} não está ativo ou circuit breaker aberto")

        itens: list[ItemColetado] = []
        for query in self.queries:
            try:
                itens_query = self._coletar_query(query)
                itens.extend(itens_query)
                self.circuit_breaker.registrar_sucesso()
            except Exception as e:
                log.warning(
                    "coletor.falha",
                    extra={"dados": {"coletor": self.fonte_id, "query": query, "erro": str(e)}},
                )
                self.circuit_breaker.registrar_falha()

        return itens

    def _coletar_query(self, query: str) -> list[ItemColetado]:
        # hl/gl/ceid obrigatórios — sem eles o Google News retorna 302
        params = {"q": query, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
        try:
            resp = httpx.get(self.BASE_URL, params=params, timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            raise ColetorIndisponivelError(f"Erro HTTP: {e}") from e

        feed = feedparser.parse(resp.content)
        if feed.bozo:
            log.debug("feedparser.bozo", extra={"dados": {"query": query}})

        itens = []
        for entry in feed.entries:
            titulo_raw = entry.get("title", "")
            link = entry.get("link", "")
            descricao = entry.get("summary", "")

            if not titulo_raw or not link:
                continue

            # Extrai veículo real: Google News coloca "Título — Veículo" no título
            veiculo, titulo = self._extrair_veiculo(titulo_raw, entry)

            # Sanitizar + normalizar conteúdo
            conteudo = HTMLSanitizer.limpar(descricao)
            conteudo = TextNormalizer.normalizar(conteudo)

            pub_date = None
            if hasattr(entry, "published"):
                try:
                    pub_date = entry.published_parsed
                    if pub_date:
                        pub_date = datetime(*pub_date[:6]).replace(tzinfo=timezone.utc).isoformat()
                except Exception:
                    pass

            item = ItemColetado(
                titulo=titulo,
                link=link,
                descricao=descricao,
                pub_date=pub_date,
                fonte_id=self.fonte_id,
                veiculo=veiculo,
                conteudo_texto=conteudo,
            )
            itens.append(item)

        log.info(
            "coletor.concluido",
            extra={"dados": {"coletor": self.fonte_id, "query": query, "itens": len(itens)}},
        )
        return itens

    @staticmethod
    def _extrair_veiculo(titulo_raw: str, entry) -> tuple[str, str]:
        """Extrai o veículo real e o título limpo do Google News RSS.

        Google News formata como: 'Título da notícia - Nome do Veículo'
        O feedparser às vezes expõe o source separado; caso contrário usamos o sufixo.
        """
        veiculo = ""

        # 1. Tenta feedparser source element (mais confiável)
        source = getattr(entry, "source", None)
        if isinstance(source, dict):
            veiculo = source.get("title") or source.get("value") or ""

        # 2. Fallback: extrai sufixo " - Veículo" do título
        # O Google News usa: "Título da Notícia - Nome do Veículo"
        # Alguns veículos têm localização: "Gazeta Digital - Cuiabá - MT"
        # Nesse caso pegamos os dois últimos segmentos como nome do veículo
        titulo = titulo_raw
        if not veiculo and " - " in titulo_raw:
            partes = [p.strip() for p in titulo_raw.split(" - ")]
            if len(partes) >= 3:
                # "Título - Veículo - Cidade" → junta os 2 últimos se o último parecer UF/cidade
                ultimo = partes[-1]
                penultimo = partes[-2]
                if len(ultimo) <= 30 and len(penultimo) <= 50:
                    veiculo = f"{penultimo} - {ultimo}"
                    titulo = " - ".join(partes[:-2])
                else:
                    veiculo = ultimo
                    titulo = " - ".join(partes[:-1])
            elif len(partes) == 2:
                candidato = partes[-1]
                if candidato and len(candidato) < 80:
                    veiculo = candidato
                    titulo = partes[0]

        return veiculo or "Google News", titulo or titulo_raw

    def esta_ativo(self) -> bool:
        return self.ativo_config and self.circuit_breaker.esta_disponivel()
