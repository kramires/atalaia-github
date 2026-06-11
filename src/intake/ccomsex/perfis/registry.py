"""PerfilPlanilhaRegistry (SPEC-01 §4.4)."""
from __future__ import annotations

import pandas as pd

from src.errors.exceptions import PerfilNaoReconhecidoError
from src.intake.ccomsex.perfis.base import PerfilPlanilha
from src.intake.ccomsex.perfis.perfil_clipping_24col import PerfilClipping24Col


class PerfilPlanilhaRegistry:
    _perfis: list[PerfilPlanilha] = []

    @classmethod
    def registrar(cls, perfil: PerfilPlanilha) -> None:
        cls._perfis.append(perfil)

    @classmethod
    def detectar_perfil(cls, df: pd.DataFrame) -> PerfilPlanilha:
        for perfil in cls._perfis:
            try:
                if perfil.detectar(df):
                    return perfil
            except NotImplementedError:
                continue
        raise PerfilNaoReconhecidoError(
            f"Nenhum perfil reconheceu o layout. "
            f"Cabeçalhos encontrados: {list(df.columns)[:8]}"
        )


# Registro automático na importação do módulo
PerfilPlanilhaRegistry.registrar(PerfilClipping24Col())
