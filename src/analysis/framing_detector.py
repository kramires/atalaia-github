"""FramingDetector (SPEC-07)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.core.agent.tool_registry import ToolRegistry
from src.memory.database import Database

log = logging.getLogger(__name__)


@dataclass
class MudancaEnquadramento:
    narrativa: str
    enquadramento_anterior: str
    enquadramento_atual: str
    tipo_inferencia: str = "HIPOTESE"
    confianca: float = 0.5


class FramingDetector:
    def __init__(self, db: Database) -> None:
        self._db = db

    def detectar(self, narrativas: list[dict], janela_dias: int = 30) -> list[MudancaEnquadramento]:
        """Detecta mudanças de enquadramento nas narrativas."""
        # MVP: simplificado — sem histórico real
        mudancas: list[MudancaEnquadramento] = []
        # Em produção, compararia com histórico do banco
        return mudancas


@ToolRegistry.registrar("detectar_enquadramento", "Detecta mudanças de enquadramento", timeout=60)
def detectar_enquadramento(narrativas: list[dict]) -> dict:
    db = Database.instancia()
    detector = FramingDetector(db)
    mudancas = detector.detectar(narrativas)
    return {
        "mudancas": len(mudancas),
        "detalhes": [
            {
                "narrativa": m.narrativa,
                "anterior": m.enquadramento_anterior,
                "atual": m.enquadramento_atual,
            }
            for m in mudancas
        ],
    }
