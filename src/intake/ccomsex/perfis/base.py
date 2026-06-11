"""Protocol PerfilPlanilha (SPEC-01 §4.1)."""
from __future__ import annotations

from typing import Protocol

import pandas as pd


class PerfilPlanilha(Protocol):
    nome: str

    def detectar(self, df: pd.DataFrame) -> bool:
        """True se este perfil reconhece o layout do DataFrame."""
        ...

    def mapear(self, df: pd.DataFrame) -> pd.DataFrame:
        """Renomeia colunas para os nomes canônicos. Colunas ausentes ficam ausentes."""
        ...
