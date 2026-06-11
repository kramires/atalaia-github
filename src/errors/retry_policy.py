"""Decorator @com_retry com backoff fixo (SPEC-15 §3)."""
import functools
import logging
import time
from collections.abc import Callable
from typing import TypeVar

from src.errors.exceptions import AtalaiaError

log = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable)


def com_retry(tentativas: int = 3, backoff: tuple[float, ...] = (2.0, 4.0, 8.0)) -> Callable:
    """
    Faz retry com backoff fixo em exceções de IO/rede.
    Não faz retry em AtalaiaError (são erros de domínio, não de rede).
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            esperas = list(backoff)[: tentativas - 1] + [0.0]
            ultimo_erro: Exception | None = None
            for i, espera in enumerate(esperas, 1):
                try:
                    return fn(*args, **kwargs)
                except AtalaiaError:
                    raise
                except Exception as e:
                    ultimo_erro = e
                    log.warning(
                        "retry.tentativa",
                        extra={"dados": {"tentativa": i, "max": tentativas, "erro": str(e)}},
                    )
                    if espera > 0:
                        time.sleep(espera)
            raise ultimo_erro  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
