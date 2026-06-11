"""Módulo de Briefing — SPEC-11."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DestaqueItem(BaseModel):
    item_id: int
    veiculo: str
    titulo: str
    link: str
    resumo: str
    sentimento: str
    tipo_inferencia: str
    confianca: float


class ItemResumo(BaseModel):
    data: str
    veiculo: str
    sentimento: str
    titulo: str
    link: str


class Narrativa(BaseModel):
    nome: str
    frequencia: int
    temas: list[str]


class MudancaEnquadramento(BaseModel):
    narrativa: str
    enquadramento_anterior: str
    enquadramento_novo: str
    tipo_inferencia: str
    confianca: float


class BriefingParte1(BaseModel):
    periodo_inicio: date
    periodo_fim: date
    total_itens: int
    n_positivos: int
    n_neutros: int
    n_negativos: int
    pct_positiva: int
    nivel_risco: str
    destaques_positivos: list[DestaqueItem]
    destaques_negativos: list[DestaqueItem]
    narrativas: list[Narrativa]
    mudancas_enquadramento: list[MudancaEnquadramento]
    todos_os_itens: list[ItemResumo]
    modo_degradado: bool
    markdown: str
    html: str


class RespostaProspeccaoLLM(BaseModel):
    prospeccao: list[str] = Field(max_length=5)
    acoes_refinadas: list[str] = Field(max_length=5)
    confianca: float = Field(ge=0.0, le=1.0)
    tipo: Literal['FATO', 'INTERPRETACAO', 'HIPOTESE']


class BriefingParte2(BaseModel):
    nivel_risco: str
    justificativa: str
    fatores_risco: list[str]
    oportunidades: list[str]
    acoes_sugeridas: list[str]
    prospeccao: list[str]
    confianca_geral: float
    provider: str
    modo_degradado: bool
    markdown: str
    html: str


__all__ = [
    'DestaqueItem',
    'ItemResumo',
    'Narrativa',
    'MudancaEnquadramento',
    'BriefingParte1',
    'BriefingParte2',
    'RespostaProspeccaoLLM',
]
