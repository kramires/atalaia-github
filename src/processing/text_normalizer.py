"""TextNormalizer — normaliza e trunca conteúdo textual (SPEC-03 §5)."""
from __future__ import annotations

import re
import unicodedata

MAX_CHARS_CONTEUDO = 8_000


class TextNormalizer:
    @staticmethod
    def normalizar(texto: str) -> str:
        """NFC + remove control chars + collapse espaços + trunca."""
        if not texto:
            return ""
        # NFC normalization
        texto = unicodedata.normalize("NFC", texto)
        # Remove caracteres de controle (exceto espaços/tabs/newlines)
        texto = "".join(c for c in texto if unicodedata.category(c)[0] != "C" or c in "\n\t ")
        # Collapse espaços múltiplos
        texto = re.sub(r"\s+", " ", texto).strip()
        # Trunca
        return texto[:MAX_CHARS_CONTEUDO]
