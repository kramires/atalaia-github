"""Circuit Breaker thread-safe (SPEC-15 §4)."""
import logging
import threading
import time
from enum import Enum

log = logging.getLogger(__name__)


class EstadoCircuit(str, Enum):
    FECHADO = "FECHADO"
    ABERTO = "ABERTO"
    SEMI_ABERTO = "SEMI_ABERTO"


class CircuitBreaker:
    def __init__(self, nome: str, falhas_para_abrir: int = 3, timeout_reset_segundos: int = 120):
        self.nome = nome
        self._limite = falhas_para_abrir
        self._timeout = timeout_reset_segundos
        self._falhas = 0
        self._estado = EstadoCircuit.FECHADO
        self._aberto_em: float | None = None
        self._lock = threading.Lock()

    @property
    def estado(self) -> EstadoCircuit:
        with self._lock:
            if (
                self._estado == EstadoCircuit.ABERTO
                and self._aberto_em is not None
                and time.monotonic() - self._aberto_em >= self._timeout
            ):
                self._estado = EstadoCircuit.SEMI_ABERTO
                log.info("circuit_breaker.semi_aberto", extra={"dados": {"nome": self.nome}})
        return self._estado

    def registrar_sucesso(self) -> None:
        with self._lock:
            self._falhas = 0
            if self._estado != EstadoCircuit.FECHADO:
                self._estado = EstadoCircuit.FECHADO
                log.info("circuit_breaker.fechado", extra={"dados": {"nome": self.nome}})

    def registrar_falha(self) -> None:
        with self._lock:
            self._falhas += 1
            if self._falhas >= self._limite:
                self._estado = EstadoCircuit.ABERTO
                self._aberto_em = time.monotonic()
                log.warning(
                    "circuit_breaker.aberto",
                    extra={"dados": {"nome": self.nome, "falhas": self._falhas}},
                )

    def esta_disponivel(self) -> bool:
        return self.estado != EstadoCircuit.ABERTO
