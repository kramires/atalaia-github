"""RiskEvaluator (SPEC-08)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.agent.tool_registry import ToolRegistry

log = logging.getLogger(__name__)


@dataclass
class AvaliacaoRisco:
    nivel_risco: str
    justificativa: str
    confianca: float
    tipo_inferencia: str
    fatores_risco: list[str] = field(default_factory=list)
    oportunidades: list[str] = field(default_factory=list)
    acoes_sugeridas: list[str] = field(default_factory=list)


class RiskEvaluator:
    def _nivel_rule_based(self, sentimentos: dict[str, int]) -> str:
        """Classifica risco por percentual de sentimentos negativos."""
        total = sum(sentimentos.values())
        if total == 0:
            return "BAIXO"
        pct_neg = sentimentos.get("NEGATIVA", 0) / total
        if pct_neg >= 0.6:
            return "CRITICO"
        if pct_neg >= 0.4:
            return "ALTO"
        if pct_neg >= 0.2:
            return "MEDIO"
        return "BAIXO"

    def avaliar(self, sentimentos: dict[str, int]) -> AvaliacaoRisco:
        """Avalia risco com base em sentimentos."""
        nivel = self._nivel_rule_based(sentimentos)
        return AvaliacaoRisco(
            nivel_risco=nivel,
            justificativa=f"Análise rule-based. Negativos: {sentimentos.get('NEGATIVA', 0)}",
            confianca=0.5,
            tipo_inferencia="HIPOTESE",
            fatores_risco=[f"Sentimento negativo detectado"],
            oportunidades=[f"Oportunidade de posicionamento"],
            acoes_sugeridas=[f"Monitorar evolução"],
        )


@ToolRegistry.registrar("avaliar_risco", "Avalia nível de risco", timeout=60)
def avaliar_risco(sentimentos: dict[str, int]) -> dict:
    evaluator = RiskEvaluator()
    avaliacao = evaluator.avaliar(sentimentos)
    return {
        "nivel": avaliacao.nivel_risco,
        "confianca": avaliacao.confianca,
        "justificativa": avaliacao.justificativa,
    }
