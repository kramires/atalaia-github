"""ManualIntakeCollector — ingestão manual via CLI (SPEC-02 §8.3)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.intake.rss.base import ItemColetado
from src.processing.html_sanitizer import HTMLSanitizer
from src.processing.text_normalizer import TextNormalizer

log = logging.getLogger(__name__)


class ManualIntakeCollector:
    """Ingestão manual de um item — sem collection, direto de CLI."""

    def __init__(self, fonte_id: str = "manual") -> None:
        self.fonte_id = fonte_id
        self.nome = "Manual (WhatsApp/etc.)"

    def criar_item(
        self,
        titulo: str,
        texto: str,
        data: str | None = None,
        veiculo: str = "",
    ) -> ItemColetado:
        """Cria um ItemColetado a partir de entrada manual."""
        # Sanitizar + normalizar
        conteudo = HTMLSanitizer.limpar(texto)
        conteudo = TextNormalizer.normalizar(conteudo)

        pub_date = data or datetime.now(timezone.utc).isoformat()

        return ItemColetado(
            titulo=titulo,
            link="",  # Manual não tem link
            descricao=texto,
            pub_date=pub_date,
            fonte_id=self.fonte_id,
            veiculo=veiculo or "Manual",
            conteudo_texto=conteudo,
        )
