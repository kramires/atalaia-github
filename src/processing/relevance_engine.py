"""RelevanceEngine — scoring multicamadas de relevância (SPEC-03 §6)."""
from __future__ import annotations

import re

from src.core.config.config_loader import instancia as config_instancia


class RelevanceEngine:
    BÔNUS_KEYWORDS_CRITICAS = 0.40
    BÔNUS_KEYWORDS_PRIMARIAS = 0.20
    BÔNUS_KEYWORDS_SECUNDARIAS = 0.10

    def __init__(self) -> None:
        cfg = config_instancia()
        self.keywords_criticas = set(k.lower() for k in cfg.relevancia.keywords_criticas)
        self.keywords_primarias = set(k.lower() for k in cfg.relevancia.keywords_primarias)
        self.keywords_secundarias = set(k.lower() for k in cfg.relevancia.keywords_secundarias)

    def calcular_score(self, titulo: str, conteudo: str, fonte_id: str, trust_score: float) -> float:
        """Retorna score entre 0.0 e 1.0."""
        texto = f"{titulo} {conteudo}".lower()
        score = 0.0
        # Keywords
        for kw in self.keywords_criticas:
            if self._buscar_palavra(kw, texto):
                score = min(score + self.BÔNUS_KEYWORDS_CRITICAS, 1.0)
                break
        if score < 1.0:
            for kw in self.keywords_primarias:
                if self._buscar_palavra(kw, texto):
                    score += self.BÔNUS_KEYWORDS_PRIMARIAS
                    if score >= 1.0:
                        score = 1.0
                        break
        if score < 1.0:
            for kw in self.keywords_secundarias:
                if self._buscar_palavra(kw, texto):
                    score += self.BÔNUS_KEYWORDS_SECUNDARIAS
                    if score >= 1.0:
                        score = 1.0
                        break
        # Bônus de fonte
        bonus_fonte = (trust_score - 0.5) * 0.10
        score += bonus_fonte
        return max(0.0, min(1.0, score))

    @staticmethod
    def _buscar_palavra(palavra: str, texto: str) -> bool:
        """Busca palavra com word boundary."""
        pattern = r"\b" + re.escape(palavra) + r"\b"
        return bool(re.search(pattern, texto))


class Router:
    def __init__(self, threshold: float = 0.5) -> None:
        self.engine = RelevanceEngine()
        self.threshold = threshold

    def classificar(self, titulo: str, conteudo: str, fonte_id: str, trust_score: float) -> tuple[bool, float]:
        """Retorna (é_relevante, score)."""
        score = self.engine.calcular_score(titulo, conteudo, fonte_id, trust_score)
        return score >= self.threshold, score


class HardCapFilter:
    def __init__(self, cap: int = 100) -> None:
        self.cap = cap

    def filtrar(self, itens: list[dict]) -> tuple[list[dict], int]:
        """Retorna (itens_selecionados, n_descartados_acima_cap)."""
        # Ordena por relevance_score descendente
        itens_sorted = sorted(itens, key=lambda x: x.get("relevance_score", 0), reverse=True)
        selecionados = itens_sorted[: self.cap]
        n_acima_cap = max(0, len(itens) - self.cap)
        return selecionados, n_acima_cap
