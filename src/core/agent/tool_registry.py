"""ToolRegistry — registro de tools para o ReAct loop (SPEC-05 §4)."""
from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Callable

log = logging.getLogger(__name__)


class ToolRegistry:
    _tools: dict[str, dict[str, Any]] = {}

    @classmethod
    def registrar(cls, nome: str, descricao: str, timeout: int = 60) -> Callable:
        """Decorator para registrar uma tool."""
        def decorator(fn: Callable) -> Callable:
            # Extrai tipos de parâmetro e retorno
            sig = inspect.signature(fn)
            params = {}
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                tipo = str(param.annotation).replace("typing.", "")
                params[param_name] = {"type": tipo}

            schema = {
                "name": nome,
                "description": descricao,
                "input_schema": {
                    "type": "object",
                    "properties": params,
                    "required": list(params.keys()),
                },
            }

            cls._tools[nome] = {
                "funcao": fn,
                "schema": schema,
                "timeout": timeout,
            }
            log.debug("tool.registrada", extra={"dados": {"nome": nome}})
            return fn

        return decorator

    @classmethod
    def obter(cls, nome: str) -> Callable | None:
        """Retorna a função da tool pelo nome."""
        return cls._tools.get(nome, {}).get("funcao")

    @classmethod
    def schema(cls, nome: str) -> dict | None:
        """Retorna o schema JSON da tool."""
        return cls._tools.get(nome, {}).get("schema")

    @classmethod
    def listar(cls) -> list[dict]:
        """Retorna lista de schemas de todas as tools."""
        return [tool["schema"] for tool in cls._tools.values()]

    @classmethod
    def existe(cls, nome: str) -> bool:
        """Verifica se a tool está registrada."""
        return nome in cls._tools

    @classmethod
    def timeout(cls, nome: str) -> int:
        """Retorna timeout da tool."""
        return cls._tools.get(nome, {}).get("timeout", 60)
