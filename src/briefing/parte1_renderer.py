"""Parte1Renderer — renderiza panorama do ciclo sem LLM (SPEC-11 §6)."""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

import jinja2

from src.briefing import (
    BriefingParte1,
    DestaqueItem,
    ItemResumo,
    MudancaEnquadramento,
    Narrativa,
)
from src.core.agent.agent_loop import AgentAnalysisResult
from src.analysis.risk_evaluator import AvaliacaoRisco

log = logging.getLogger(__name__)


class Parte1Renderer:
    """Monta a Parte 1 do briefing a partir do AgentAnalysisResult. Não chama LLM."""

    MAX_DESTAQUES = 3

    def __init__(
        self, jinja_env: jinja2.Environment, itens_ciclo: dict[int, dict]
    ) -> None:
        self._env = jinja_env
        self._itens = itens_ciclo

    def renderizar(
        self, result: AgentAnalysisResult, avaliacao: AvaliacaoRisco | None
    ) -> BriefingParte1:
        sent_map = {s["item_id"]: s for s in result.sentimentos if isinstance(s, dict)}
        destaques_pos = self._selecionar_destaques("POSITIVA", sent_map)
        destaques_neg = self._selecionar_destaques("NEGATIVA", sent_map)
        todos = self._montar_lista_itens(sent_map)

        periodo_inicio, periodo_fim = self._calcular_periodo(todos)
        n_pos = sum(
            1
            for s in result.sentimentos
            if s.get("sentimento_ia") == "POSITIVA"
        )
        n_neu = sum(
            1
            for s in result.sentimentos
            if s.get("sentimento_ia") == "NEUTRA"
        )
        n_neg = sum(
            1
            for s in result.sentimentos
            if s.get("sentimento_ia") == "NEGATIVA"
        )
        total = len(result.sentimentos) or 1

        narrativas_obj = [
            Narrativa(**n) if isinstance(n, dict) else n
            for n in result.narrativas
        ]
        mudancas_obj = [
            MudancaEnquadramento(**m) if isinstance(m, dict) else m
            for m in result.mudancas_enquadramento
        ]

        ctx = {
            "periodo_inicio": periodo_inicio.strftime("%d/%m/%Y"),
            "periodo_fim": periodo_fim.strftime("%d/%m/%Y"),
            "total_itens": result.itens_analisados,
            "n_positivos": n_pos,
            "n_neutros": n_neu,
            "n_negativos": n_neg,
            "pct_positiva": round(n_pos / total * 100),
            "nivel_risco": avaliacao.nivel_risco if avaliacao else "N/A",
            "destaques_positivos": destaques_pos,
            "destaques_negativos": destaques_neg,
            "narrativas": narrativas_obj,
            "mudancas_enquadramento": mudancas_obj,
            "todos_os_itens": todos,
            "modo_degradado": result.modo_degradado,
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "ciclo_id": result.ciclo_id,
        }

        md = self._env.get_template("parte1.md.jinja2").render(**ctx)
        html = self._env.get_template("parte1.html.jinja2").render(**ctx)

        return BriefingParte1(
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            total_itens=result.itens_analisados,
            n_positivos=n_pos,
            n_neutros=n_neu,
            n_negativos=n_neg,
            pct_positiva=round(n_pos / total * 100),
            nivel_risco=avaliacao.nivel_risco if avaliacao else "N/A",
            destaques_positivos=destaques_pos,
            destaques_negativos=destaques_neg,
            narrativas=narrativas_obj,
            mudancas_enquadramento=mudancas_obj,
            todos_os_itens=todos,
            modo_degradado=result.modo_degradado,
            markdown=md,
            html=html,
        )

    def _selecionar_destaques(
        self, sentimento: str, sent_map: dict[int, dict]
    ) -> list[DestaqueItem]:
        candidatos = [
            (iid, s)
            for iid, s in sent_map.items()
            if s.get("sentimento_ia") == sentimento and iid in self._itens
        ]
        candidatos.sort(
            key=lambda t: t[1].get("confianca", 0.0), reverse=True
        )
        destaques = []
        for iid, s in candidatos[: self.MAX_DESTAQUES]:
            item = self._itens[iid]
            destaques.append(
                DestaqueItem(
                    item_id=iid,
                    veiculo=item.get("fonte_nome", "—"),
                    titulo=item.get("titulo", "—"),
                    link=item.get("url", "#"),
                    resumo=item.get("conteudo_texto", "")[: 120] + "...",
                    sentimento=s.get("sentimento_ia", "—"),
                    tipo_inferencia=s.get("tipo_inferencia", "FATO"),
                    confianca=s.get("confianca", 0.0),
                )
            )
        return destaques

    def _montar_lista_itens(
        self, sent_map: dict[int, dict]
    ) -> list[ItemResumo]:
        def parse_date(item: dict) -> date:
            pub = item.get("pub_date")
            if isinstance(pub, date):
                return pub
            if isinstance(pub, str):
                try:
                    return datetime.fromisoformat(pub).date()
                except ValueError:
                    return date.min
            return date.min

        itens_ordenados = sorted(
            self._itens.values(),
            key=lambda i: parse_date(i),
            reverse=True,
        )
        return [
            ItemResumo(
                data=(
                    parse_date(item).strftime("%d/%m/%Y")
                    if parse_date(item) != date.min
                    else "—"
                ),
                veiculo=item.get("fonte_nome", "—"),
                sentimento=(
                    sent_map[item["item_id"]].get("sentimento_ia", "—")
                    if item["item_id"] in sent_map
                    else "—"
                ),
                titulo=item.get("titulo", "—"),
                link=item.get("url", "#"),
            )
            for item in itens_ordenados
        ]

    def _calcular_periodo(self, itens: list[ItemResumo]) -> tuple[date, date]:
        datas = []
        for i in itens:
            if i.data != "—":
                try:
                    d = datetime.strptime(i.data, "%d/%m/%Y").date()
                    datas.append(d)
                except ValueError:
                    pass
        if not datas:
            hoje = date.today()
            return hoje, hoje
        return min(datas), max(datas)
