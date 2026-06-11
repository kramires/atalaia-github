"""Perfil das 24 colunas do clipping diário CCOMSEx (SPEC-01 §4.2)."""
from __future__ import annotations

import pandas as pd

from src.intake.ccomsex.normalizers import norm_header

COLUMN_MAP: dict[str, str] = {
    "data": "data",
    "titulo": "titulo",
    "url": "url_clip",
    "link": "link_original",
    "tipo": "tipo",
    "veiculo": "veiculo",
    "editoria / pag.": "editoria",
    "editoria/pag.": "editoria",
    "editoria": "editoria",
    "mesorregiao": "mesorregiao",
    "uf": "uf",
    "municipio": "municipio",
    "abrangencia": "abrangencia",
    "pais": "pais",
    "midia": "midia",
    "espaco": "espaco",
    "cm": "cm",
    "seg": "seg",
    "valor": "valor",
    "publico": "publico",
    "categoria": "categoria",
    "maps": "maps",
    "tag veiculo": "tag_veiculo",
    "analise qualitativa das materias": "analise_qualitativa",
    "analise qualitativa": "analise_qualitativa",
    "incluir na analise": "incluir_analise",
    "assunto": "assunto",
}

_COLUNAS_CHAVE = {
    "titulo", "veiculo", "analise qualitativa das materias", "valor", "publico", "cm"
}


class PerfilClipping24Col:
    nome = "clipping_24col"

    def detectar(self, df: pd.DataFrame) -> bool:
        headers_norm = {norm_header(c) for c in df.columns}
        chaves_norm = {norm_header(c) for c in _COLUNAS_CHAVE}
        return len(chaves_norm & headers_norm) >= 3

    def mapear(self, df: pd.DataFrame) -> pd.DataFrame:
        rename: dict[str, str] = {}
        for col in df.columns:
            key = norm_header(col)
            if key in COLUMN_MAP:
                rename[col] = COLUMN_MAP[key]
        return df.rename(columns=rename)
