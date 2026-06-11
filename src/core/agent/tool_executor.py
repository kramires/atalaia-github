"""ToolExecutor — executa tools com timeout (SPEC-05 §5)."""
from __future__ import annotations

import logging
import threading
from functools import wraps
from typing import Any

from src.core.agent.tool_registry import ToolRegistry
from src.errors.exceptions import ToolNaoEncontradaError, ToolTimeoutError

log = logging.getLogger(__name__)


class ToolExecutor:
    @staticmethod
    def executar(nome: str, **kwargs) -> Any:
        """Executa uma tool pelo nome com seus kwargs."""
        if not ToolRegistry.existe(nome):
            raise ToolNaoEncontradaError(f"Tool '{nome}' não registrada")

        fn = ToolRegistry.obter(nome)
        timeout = ToolRegistry.timeout(nome)

        resultado: dict[str, Any] = {"valor": None, "erro": None}

        def worker() -> None:
            try:
                resultado["valor"] = fn(**kwargs)
            except Exception as e:
                resultado["erro"] = e

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            log.warning("tool.timeout", extra={"dados": {"nome": nome, "timeout": timeout}})
            raise ToolTimeoutError(f"Tool '{nome}' excedeu timeout de {timeout}s")

        if resultado["erro"]:
            raise resultado["erro"]

        return resultado["valor"]
