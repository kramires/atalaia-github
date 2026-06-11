"""Parte2Renderer — prospecção com LLM isolado (SPEC-11 §7)."""
from __future__ import annotations

import logging
from datetime import datetime

import jinja2

from src.briefing import BriefingParte2, RespostaProspeccaoLLM
from src.analysis.risk_evaluator import AvaliacaoRisco
from src.errors.exceptions import AnalyseDegradadaError
from src.providers.protocol import ProvedorLLM

log = logging.getLogger(__name__)


class Parte2Renderer:
    """Gera a Parte 2 usando provider isolado (pode ser Ollama local para SegInfo)."""

    SYSTEM_PARTE2 = """
Você é um analista sênior de comunicação social do Exército Brasileiro.
Gere a seção de prospecção e plano de ação de um briefing de mídia.

REGRAS:
- Foque em ações realizáveis pela ComSoc (notas, press releases, destaques).
- NUNCA sugira contrapropaganda, desinformação ou rebate agressivo.
- Toda inferência deve ser classificada: FATO | INTERPRETAÇÃO | HIPÓTESE.
- Prospecção de curto prazo (3-5 dias) baseada em tendências observadas.
- Linguagem objetiva, militarmente adequada.
""".strip()

    USER_PARTE2_TEMPLATE = """
AVALIAÇÃO DE RISCO DO CICLO:
Nível: {nivel_risco} | Confiança: {confianca:.0%}
Justificativa: {justificativa}

Fatores de risco: {fatores}
Oportunidades identificadas: {oportunidades}
Ações sugeridas pela análise: {acoes}

Com base neste cenário, gere:
1. Prospecção para os próximos 3-5 dias (bullets)
2. Refinamento das ações sugeridas (mais específicas e acionáveis)
""".strip()

    def __init__(
        self, provider: ProvedorLLM, jinja_env: jinja2.Environment
    ) -> None:
        self._provider = provider
        self._env = jinja_env

    def renderizar(
        self, avaliacao: AvaliacaoRisco, ciclo_id: str
    ) -> BriefingParte2:
        user = self.USER_PARTE2_TEMPLATE.format(
            nivel_risco=avaliacao.nivel_risco,
            confianca=avaliacao.confianca,
            justificativa=avaliacao.justificativa,
            fatores="; ".join(avaliacao.fatores_risco) or "(nenhum)",
            oportunidades="; ".join(avaliacao.oportunidades) or "(nenhuma)",
            acoes="; ".join(avaliacao.acoes_sugeridas) or "(nenhuma)",
        )

        modo_degradado = False
        prospeccao = []
        acoes_refinadas = []
        confianca = avaliacao.confianca

        try:
            resp_raw = self._provider.completar_estruturado(
                system=self.SYSTEM_PARTE2,
                user=user,
                schema=RespostaProspeccaoLLM,
            )
            resp = resp_raw if isinstance(resp_raw, RespostaProspeccaoLLM) else RespostaProspeccaoLLM.model_validate(resp_raw.model_dump())  # type: ignore[union-attr]
            prospeccao = resp.prospeccao
            acoes_refinadas = resp.acoes_refinadas
            confianca = resp.confianca
        except AnalyseDegradadaError as e:
            log.warning("parte2.degradado", extra={"dados": {"erro": str(e)}})
            prospeccao = [
                "Prospecção indisponível — LLM offline ou inacessível."
            ]
            acoes_refinadas = avaliacao.acoes_sugeridas
            modo_degradado = True

        acoes_refinadas = self._filtrar_contrapropaganda(acoes_refinadas)

        ctx = {
            "nivel_risco": avaliacao.nivel_risco,
            "justificativa": avaliacao.justificativa,
            "tipo_inferencia": avaliacao.tipo_inferencia,
            "confianca": confianca,
            "fatores_risco": avaliacao.fatores_risco,
            "oportunidades": avaliacao.oportunidades,
            "acoes_sugeridas": acoes_refinadas,
            "prospeccao": prospeccao,
            "modo_degradado": modo_degradado,
            "provider": self._provider.nome,
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }

        md = self._env.get_template("parte2.md.jinja2").render(**ctx)
        html = self._env.get_template("parte2.html.jinja2").render(**ctx)

        return BriefingParte2(
            nivel_risco=avaliacao.nivel_risco,
            justificativa=avaliacao.justificativa,
            fatores_risco=avaliacao.fatores_risco,
            oportunidades=avaliacao.oportunidades,
            acoes_sugeridas=acoes_refinadas,
            prospeccao=prospeccao,
            confianca_geral=confianca,
            provider=self._provider.nome,
            modo_degradado=modo_degradado,
            markdown=md,
            html=html,
        )

    _KEYWORDS_CONTRAPROPAGANDA = [
        "desmentir",
        "rebater",
        "fake news atacar",
        "contra-atacar",
        "refutar agressivamente",
        "desinformação produzir",
    ]

    def _filtrar_contrapropaganda(self, acoes: list[str]) -> list[str]:
        filtradas = []
        for acao in acoes:
            acao_low = acao.lower()
            if any(
                kw in acao_low for kw in self._KEYWORDS_CONTRAPROPAGANDA
            ):
                log.warning(
                    "parte2.contrapropaganda_detectada",
                    extra={"dados": {"acao": acao[: 100]}},
                )
                continue
            filtradas.append(acao)
        return filtradas
