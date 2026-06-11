"""ColetorPlugavel Protocol (SPEC-02 §5)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ItemColetado:
    titulo: str
    link: str
    descricao: str
    pub_date: str | None
    fonte_id: str
    veiculo: str = ""
    conteudo_texto: str = ""


@runtime_checkable
class ColetorPlugavel(Protocol):
    """Protocolo para coletores de Trilha B."""

    fonte_id: str
    nome: str

    def coletar(self) -> list[ItemColetado]:
        """Retorna lista de itens coletados ou levanta ColetorIndisponivelError."""
        ...

    def esta_ativo(self) -> bool:
        """True se o coletor pode operar."""
        ...
