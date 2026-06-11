"""Protocol ProvedorLLM (SPEC-16 §3)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass
class RespostaLLM:
    conteudo: str
    tokens_entrada: int
    tokens_saida: int
    provider: str
    modelo: str


class ProvedorLLM(Protocol):
    nome: str
    modelo: str

    def completar(self, system: str, user: str, max_tokens: int = 4096) -> RespostaLLM:
        """Completamento de texto simples."""
        ...

    def completar_estruturado(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        """Completamento forçado a um schema Pydantic."""
        ...

    def esta_disponivel(self) -> bool:
        """True se o provider consegue operar agora."""
        ...
