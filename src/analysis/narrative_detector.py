"""NarrativeDetector (SPEC-07)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.core.agent.tool_registry import ToolRegistry

log = logging.getLogger(__name__)


@dataclass
class Narrativa:
    tema: str
    n_itens: int
    temas: list[str]


class NarrativeDetector:
    def detectar(self, itens: list[dict]) -> list[Narrativa]:
        """Agrupa itens por narrativa/tema."""
        # MVP: agrupa por palavras-chave comuns nos títulos
        narrativas: dict[str, list] = {}

        for item in itens:
            titulo = item.get("titulo", "").lower()
            # Agrupa por primeira palavra significativa
            palavras = [p for p in titulo.split() if len(p) > 3]
            chave = palavras[0] if palavras else "outros"

            if chave not in narrativas:
                narrativas[chave] = []
            narrativas[chave].append(item)

        result = [
            Narrativa(
                tema=tema,
                n_itens=len(itens_tema),
                temas=[tema],
            )
            for tema, itens_tema in narrativas.items()
            if len(itens_tema) >= 2
        ]
        return sorted(result, key=lambda x: x.n_itens, reverse=True)


@ToolRegistry.registrar("detectar_narrativas", "Detecta narrativas nos itens", timeout=60)
def detectar_narrativas(itens: list[dict]) -> dict:
    detector = NarrativeDetector()
    narrativas = detector.detectar(itens)
    return {
        "detectadas": len(narrativas),
        "narrativas": [
            {"tema": n.tema, "n_itens": n.n_itens, "temas": n.temas} for n in narrativas
        ],
    }
