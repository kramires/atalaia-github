"""Tools de Briefing registradas no ToolRegistry (SPEC-11 §9)."""
from __future__ import annotations

import logging
from typing import Any

from src.core.agent.tool_registry import ToolRegistry

log = logging.getLogger(__name__)

# Variáveis globais para armazenar contexto (setter em CicloManager)
_parte1_renderer: Any = None
_parte2_renderer: Any = None
_agent_result_atual: Any = None
_avaliacao_atual: Any = None


def set_briefing_context(
    parte1_renderer: Any,
    parte2_renderer: Any,
    agent_result: Any,
    avaliacao: Any,
) -> None:
    """Define contexto para as tools de briefing."""
    global _parte1_renderer, _parte2_renderer, _agent_result_atual, _avaliacao_atual
    _parte1_renderer = parte1_renderer
    _parte2_renderer = parte2_renderer
    _agent_result_atual = agent_result
    _avaliacao_atual = avaliacao


@ToolRegistry.registrar(
    "gerar_briefing_parte1",
    "Gera a Parte 1 do briefing: panorama do ciclo, destaques positivos/negativos, "
    "narrativas e lista completa de matérias com links.",
    timeout=120,
)
def gerar_briefing_parte1(ciclo_id: str) -> dict:
    """Gera Parte 1 do briefing (sem LLM)."""
    if _parte1_renderer is None or _agent_result_atual is None:
        return {
            "status": "erro",
            "mensagem": "Contexto não definido para briefing",
        }

    try:
        parte1 = _parte1_renderer.renderizar(
            _agent_result_atual, _avaliacao_atual
        )
        return parte1.model_dump(exclude={"markdown", "html"})
    except Exception as e:
        log.error(
            "briefing.parte1.erro",
            extra={"dados": {"erro": str(e)}},
        )
        return {"status": "erro", "mensagem": str(e)}


@ToolRegistry.registrar(
    "gerar_briefing_parte2",
    "Gera a Parte 2 do briefing: prospecção de curto prazo e plano de ação ComSoc. "
    "Usa provider LLM isolado (pode ser Ollama local para SegInfo).",
    timeout=180,
)
def gerar_briefing_parte2(ciclo_id: str) -> dict:
    """Gera Parte 2 do briefing (com LLM isolado)."""
    if _parte2_renderer is None or _avaliacao_atual is None:
        return {
            "status": "erro",
            "mensagem": "Contexto não definido para briefing ou avaliação nula",
        }

    try:
        parte2 = _parte2_renderer.renderizar(_avaliacao_atual, ciclo_id)
        return parte2.model_dump(exclude={"markdown", "html"})
    except Exception as e:
        log.error(
            "briefing.parte2.erro",
            extra={"dados": {"erro": str(e)}},
        )
        return {"status": "erro", "mensagem": str(e)}
