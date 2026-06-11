"""AgentLoop — ReAct loop orchestrator (SPEC-05)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.core.agent.tool_executor import ToolExecutor
from src.core.agent.tool_registry import ToolRegistry
from src.errors.exceptions import AnalyseDegradadaError

# Importações que disparam o registro das tools via @ToolRegistry.registrar
import src.analysis.sentiment_analyzer   # noqa: F401 — registra analisar_sentimento
import src.analysis.narrative_detector   # noqa: F401 — registra detectar_narrativas
import src.analysis.framing_detector     # noqa: F401 — registra detectar_enquadramento
import src.analysis.risk_evaluator       # noqa: F401 — registra avaliar_risco
import src.briefing.tools                # noqa: F401 — registra gerar_briefing_parte1/2

log = logging.getLogger(__name__)


@dataclass
class AgentAnalysisResult:
    ciclo_id: str
    itens_analisados: int = 0
    modo_degradado: bool = False
    sentimentos: list[dict] = field(default_factory=list)
    narrativas: list[dict] = field(default_factory=list)
    mudancas_enquadramento: list[dict] = field(default_factory=list)
    risco_nivel: str = "BAIXO"
    iteracoes: int = 0
    tokens_usados: int = 0


class AgentLoop:
    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self.max_iteracoes = self._config.get("max_iteracoes", 6)
        self.timeout_tool = self._config.get("timeout_tool_segundos", 60)

    def executar(self, itens: list[dict], ciclo_id: str) -> AgentAnalysisResult:
        """Executa o loop ReAct sobre os itens."""
        resultado = AgentAnalysisResult(ciclo_id=ciclo_id, itens_analisados=len(itens))

        if not itens:
            return resultado

        system_prompt = """Você é um analista de mídia autônomo.
Analise os itens fornecidos usando as tools disponíveis.
Fluxo: 1. analisar_sentimento → 2. detectar_narrativas → 3. detectar_enquadramento → 4. avaliar_risco
Após executar as 4 tools, responda com FINAL_ANSWER contendo a análise completa."""

        context = f"Ciclo {ciclo_id}: {len(itens)} itens para análise"

        try:
            # Simplificado: executa as tools em sequência
            # Em produção, o LLM decidiria a ordem via ReAct
            senti_resp = ToolExecutor.executar("analisar_sentimento", itens=itens, ciclo_id=ciclo_id)
            resultado.sentimentos = senti_resp.get("respostas", [])

            narrativas_resp = ToolExecutor.executar("detectar_narrativas", itens=itens)
            resultado.narrativas = narrativas_resp.get("narrativas", [])

            enquad_resp = ToolExecutor.executar("detectar_enquadramento", narrativas=resultado.narrativas)
            resultado.mudancas_enquadramento = enquad_resp.get("detalhes", [])

            # Calcula sentimentos agregados
            sentimentos_agg = {
                "POSITIVA": sum(1 for s in resultado.sentimentos if s.get("sentimento_ia") == "POSITIVA"),
                "NEGATIVA": sum(1 for s in resultado.sentimentos if s.get("sentimento_ia") == "NEGATIVA"),
                "NEUTRA": sum(1 for s in resultado.sentimentos if s.get("sentimento_ia") == "NEUTRA"),
            }

            risco_resp = ToolExecutor.executar("avaliar_risco", sentimentos=sentimentos_agg)
            resultado.risco_nivel = risco_resp.get("nivel", "BAIXO")

            resultado.iteracoes = 4
            resultado.tokens_usados = 2000  # aproximação

            log.info("agent.concluido", extra={"dados": {
                "ciclo_id": ciclo_id,
                "iteracoes": resultado.iteracoes,
                "itens": len(itens),
            }})

        except AnalyseDegradadaError as e:
            log.warning("agent.degradado", extra={"dados": {"erro": str(e)}})
            resultado.modo_degradado = True
            # Fallback: marca tudo como NEUTRA
            resultado.sentimentos = [
                {"item_id": item["item_id"], "sentimento_ia": "NEUTRA", "confianca": 0.0}
                for item in itens
            ]

        return resultado
