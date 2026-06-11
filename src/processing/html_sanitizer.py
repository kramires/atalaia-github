"""HTMLSanitizer — limpa HTML de feeds RSS (SPEC-02 §6)."""
from __future__ import annotations

import bleach

MAX_CHARS_ITEM = 8_000


class HTMLSanitizer:
    ALLOWED_TAGS: list[str] = []  # zero tags — só texto
    ALLOWED_ATTRIBUTES: dict[str, list[str]] = {}

    @staticmethod
    def limpar(html: str) -> str:
        """Remove HTML/scripts; trunca a 8k chars."""
        if not html:
            return ""
        texto = bleach.clean(
            html,
            tags=HTMLSanitizer.ALLOWED_TAGS,
            attributes=HTMLSanitizer.ALLOWED_ATTRIBUTES,
            strip=True,
        )
        # Collapse espaços múltiplos
        import re
        texto = re.sub(r"\s+", " ", texto).strip()
        # Trunca
        return texto[:MAX_CHARS_ITEM]
