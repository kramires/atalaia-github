"""BriefingGenerator — orquestra Parte 1 + Parte 2 (SPEC-11 §8)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.briefing import BriefingParte1, BriefingParte2
from src.briefing.parte1_renderer import Parte1Renderer
from src.briefing.parte2_renderer import Parte2Renderer
from src.core.agent.agent_loop import AgentAnalysisResult
from src.analysis.risk_evaluator import AvaliacaoRisco
from src.memory.repositories.briefings_repo import (
    BriefingRecord,
    BriefingsRepo,
)

log = logging.getLogger(__name__)


class BriefingGenerator:
    """Orquestra geração de Parte 1 + Parte 2 e persistência."""

    def __init__(
        self,
        parte1: Parte1Renderer,
        parte2: Parte2Renderer,
        briefings_repo: BriefingsRepo,
        output_dir: Path,
    ) -> None:
        self._p1 = parte1
        self._p2 = parte2
        self._repo = briefings_repo
        self._output_dir = output_dir

    def gerar(
        self,
        result: AgentAnalysisResult,
        avaliacao: AvaliacaoRisco | None,
        ciclo_id: str,
    ) -> BriefingRecord:
        p1 = self._p1.renderizar(result, avaliacao)
        p2 = (
            self._p2.renderizar(avaliacao, ciclo_id)
            if avaliacao
            else self._p2_vazio()
        )

        briefing = BriefingRecord(
            id=str(uuid.uuid4()),
            ciclo_id=ciclo_id,
            gerado_em=datetime.now(timezone.utc),
            periodo_inicio=p1.periodo_inicio,
            periodo_fim=p1.periodo_fim,
            total_itens=p1.total_itens,
            itens_relevantes=result.itens_analisados,
            nivel_risco=avaliacao.nivel_risco if avaliacao else None,
            parte1_md=p1.markdown,
            parte2_md=p2.markdown,
            parte1_html=p1.html,
            parte2_html=p2.html,
            status=(
                "DEGRADADO"
                if (result.modo_degradado or p2.modo_degradado)
                else "COMPLETO"
            ),
            provider_parte1=(
                "rule-based" if result.modo_degradado else "llm"
            ),
            provider_parte2=p2.provider,
        )

        self._repo.inserir(briefing)
        self._salvar_arquivos(briefing)
        log.info(
            "briefing.gerado",
            extra={
                "dados": {
                    "id": briefing.id,
                    "status": briefing.status,
                    "nivel_risco": briefing.nivel_risco,
                }
            },
        )
        return briefing

    def _salvar_arquivos(self, b: BriefingRecord) -> None:
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        try:
            (self._output_dir / f"{ts}-parte1.md").write_text(
                b.parte1_md, encoding="utf-8"
            )
            (self._output_dir / f"{ts}-parte2.md").write_text(
                b.parte2_md, encoding="utf-8"
            )
            (self._output_dir / f"{ts}-parte1.html").write_text(
                b.parte1_html, encoding="utf-8"
            )
            (self._output_dir / f"{ts}-parte2.html").write_text(
                b.parte2_html, encoding="utf-8"
            )
        except IOError as e:
            log.error(
                "briefing.erro_salvar_arquivos",
                extra={"dados": {"erro": str(e)}},
            )

    def _p2_vazio(self) -> BriefingParte2:
        """Parte 2 mínima quando não há AvaliacaoRisco."""
        return BriefingParte2(
            nivel_risco="BAIXO",
            justificativa="Nenhum item relevante no ciclo.",
            fatores_risco=[],
            oportunidades=[],
            acoes_sugeridas=[],
            prospeccao=[
                "Nenhuma prospecção disponível — ciclo sem itens relevantes."
            ],
            confianca_geral=0.0,
            provider="none",
            modo_degradado=True,
            markdown="# Parte 2\n\nNenhum item relevante neste ciclo.",
            html="<p>Nenhum item relevante neste ciclo.</p>",
        )
