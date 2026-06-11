"""RSSDeduplicationEngine — dedup por URL normalizada + título (SPEC-02 §7)."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlparse


class RSSDeduplicationEngine:
    @staticmethod
    def normalizar_url(url: str) -> str:
        """Remove UTMs, fbclid, gclid."""
        if not url:
            return ""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=False)
        # Remove tracking params
        params_bloqueados = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
                            "fbclid", "gclid", "msclkid"}
        qs = {k: v for k, v in qs.items() if k not in params_bloqueados}
        nova_qs = urlencode(qs, doseq=True)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{nova_qs}" if nova_qs else f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    @staticmethod
    def normalizar_titulo(titulo: str) -> str:
        """Remove acentos, símbolos dinâmicos, collapse espaços."""
        import unicodedata
        # Remove acentos
        titulo = unicodedata.normalize("NFD", titulo)
        titulo = "".join(c for c in titulo if unicodedata.category(c) != "Mn")
        # Remove símbolos
        titulo = re.sub(r"[\s\-_•·→\|]+", " ", titulo).strip()
        return titulo.lower()

    @staticmethod
    def fazer_hash(url: str, titulo: str) -> str:
        """SHA-256 de URL normalizada + título."""
        url_norm = RSSDeduplicationEngine.normalizar_url(url)
        tit_norm = RSSDeduplicationEngine.normalizar_titulo(titulo)
        base = f"{url_norm}|{tit_norm}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()
