"""GoogleAlertsRSSCollector — RSS do Google Alerts (SPEC-02 §8.2)."""
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


class GoogleAlertsRSSCollector:
    """Coleta via URL RSS privada do Google Alerts."""

    def __init__(self, fonte_id: str, nome: str, url: str, ativo: bool = True) -> None:
        self.fonte_id = fonte_id
        self.nome = nome
        self.url = url
        self.ativo_config = ativo
        self.circuit_breaker = CircuitBreaker(
            nome=f"google_alerts_{fonte_id}", falhas_para_abrir=3, timeout_reset_segundos=120
        )

    def coletar(self) -> list[ItemColetado]:
        """Busca via Google Alerts RSS."""
        if not self.esta_ativo():
            raise ColetorIndisponivelError(f"{self.nome} não está ativo ou circuit breaker aberto")

        try:
            resp = httpx.get(self.url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log.warning(
                "coletor.falha",
                extra={"dados": {"coletor": self.fonte_id, "erro": str(e)}},
            )
            self.circuit_breaker.registrar_falha()
            raise ColetorIndisponivelError(f"Erro HTTP: {e}") from e

        feed = feedparser.parse(resp.content)
        if feed.bozo:
            log.debug("feedparser.bozo", extra={"dados": {"coletor": self.fonte_id}})

        itens: list[ItemColetado] = []
        for entry in feed.entries:
            titulo = entry.get("title", "")
            link = entry.get("link", "")
            descricao = entry.get("summary", "")

            if not titulo or not link:
                continue

            # Sanitizar + normalizar
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
                veiculo="Google Alerts",
                conteudo_texto=conteudo,
            )
            itens.append(item)

        self.circuit_breaker.registrar_sucesso()
        log.info(
            "coletor.concluido",
            extra={"dados": {"coletor": self.fonte_id, "itens": len(itens)}},
        )
        return itens

    def esta_ativo(self) -> bool:
        return self.ativo_config and self.circuit_breaker.esta_disponivel()
