"""DegradadoProvider (SPEC-16 §3.3)."""
from __future__ import annotations

from pydantic import BaseModel

from src.errors.exceptions import AnalyseDegradadaError
from src.providers.protocol import RespostaLLM


class DegradadoProvider:
    nome = "degradado"
    modelo = "none"

    def completar(self, system: str, user: str, max_tokens: int = 4096) -> RespostaLLM:
        raise AnalyseDegradadaError("Modo degradado ativo.", provider=self.nome)

    def completar_estruturado(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        raise AnalyseDegradadaError("Modo degradado ativo.", provider=self.nome)

    def esta_disponivel(self) -> bool:
        return False
