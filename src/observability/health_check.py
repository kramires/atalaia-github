"""HealthCheck (SPEC-14)."""
from __future__ import annotations

import logging
import shutil

from src.memory.database import Database
from src.providers.factory import ProviderFactory

log = logging.getLogger(__name__)


class HealthCheck:
    def __init__(self, db: Database, coletores: list | None = None, provider_factory: ProviderFactory | None = None) -> None:
        self._db = db
        self._coletores = coletores or []
        self._factory = provider_factory

    def verificar(self) -> dict:
        return {
            "banco": self._check_banco(),
            "llm": self._check_llm(),
            "disco": self._check_disco(),
        }

    def _check_banco(self) -> dict:
        try:
            resultado = self._db.executar("PRAGMA integrity_check").fetchone()[0]
            n = self._db.executar("SELECT COUNT(*) FROM items").fetchone()[0]
            return {"ok": resultado == "ok", "total_itens": n, "detalhe": resultado}
        except Exception as e:
            return {"ok": False, "detalhe": str(e)}

    def _check_llm(self) -> dict:
        if not self._factory:
            return {"ok": False, "detalhe": "Factory não disponível"}
        try:
            provider = self._factory.provider_para("analise")
            return {"ok": provider.esta_disponivel(), "provider": provider.nome}
        except Exception as e:
            return {"ok": False, "detalhe": str(e)}

    def _check_disco(self) -> dict:
        livre = shutil.disk_usage(".").free
        return {"ok": livre > 500 * 1024 * 1024, "livre_mb": livre // (1024 * 1024)}
