"""BalanceadoProvider — primário + secundário com fallback e rastreamento de uso."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel

from src.errors.exceptions import AnalyseDegradadaError
from src.providers.protocol import ProvedorLLM, RespostaLLM

log = logging.getLogger(__name__)


@dataclass
class EstatisticasProvider:
    nome: str
    requisicoes_ok: int = 0
    requisicoes_erro: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    ultimo_uso: str = ""
    ultimo_erro: str = ""

    @property
    def total(self) -> int:
        return self.requisicoes_ok + self.requisicoes_erro

    @property
    def taxa_sucesso(self) -> float:
        return self.requisicoes_ok / self.total if self.total else 1.0


class BalanceadoProvider:
    """
    Tenta o primário; se falhar (AnalyseDegradadaError), usa o secundário.
    Mantém estatísticas de uso por provider e loga qual foi usado.
    """

    def __init__(self, primario: ProvedorLLM, secundario: ProvedorLLM) -> None:
        self._primario = primario
        self._secundario = secundario
        self.nome = f"balanceado({primario.nome}→{secundario.nome})"
        self.modelo = primario.modelo
        self._lock = threading.Lock()
        self._stats: dict[str, EstatisticasProvider] = {
            primario.nome: EstatisticasProvider(primario.nome),
            secundario.nome: EstatisticasProvider(secundario.nome),
        }

    # ── Interface ProvedorLLM ─────────────────────────────────────────────────

    def completar(self, system: str, user: str, max_tokens: int = 4096) -> RespostaLLM:
        return self._executar(
            lambda p: p.completar(system, user, max_tokens)
        )

    def completar_estruturado(
        self, system: str, user: str, schema: type[BaseModel]
    ) -> BaseModel:
        return self._executar(
            lambda p: p.completar_estruturado(system, user, schema)
        )

    def esta_disponivel(self) -> bool:
        return self._primario.esta_disponivel() or self._secundario.esta_disponivel()

    # ── Estatísticas ──────────────────────────────────────────────────────────

    def estatisticas(self) -> dict[str, dict]:
        with self._lock:
            return {
                nome: {
                    "ok": s.requisicoes_ok,
                    "erro": s.requisicoes_erro,
                    "taxa_sucesso": f"{s.taxa_sucesso:.0%}",
                    "tokens_entrada": s.tokens_entrada,
                    "tokens_saida": s.tokens_saida,
                    "ultimo_uso": s.ultimo_uso,
                }
                for nome, s in self._stats.items()
            }

    # ── Lógica interna ────────────────────────────────────────────────────────

    def _executar(self, fn):
        """Tenta primário; fallback para secundário se falhar."""
        try:
            resultado = fn(self._primario)
            self._registrar_ok(self._primario, resultado)
            return resultado
        except AnalyseDegradadaError as e_prim:
            log.warning(
                "balanceado.primario_falhou",
                extra={"dados": {"provider": self._primario.nome, "erro": str(e_prim)}},
            )
            self._registrar_erro(self._primario, str(e_prim))

        try:
            resultado = fn(self._secundario)
            self._registrar_ok(self._secundario, resultado)
            log.info(
                "balanceado.usando_secundario",
                extra={"dados": {"provider": self._secundario.nome}},
            )
            return resultado
        except AnalyseDegradadaError as e_sec:
            self._registrar_erro(self._secundario, str(e_sec))
            raise AnalyseDegradadaError(
                f"Ambos os providers falharam — "
                f"{self._primario.nome}: anterior; "
                f"{self._secundario.nome}: {e_sec}",
                provider=self.nome,
            ) from e_sec

    def _registrar_ok(self, provider: ProvedorLLM, resultado) -> None:
        with self._lock:
            s = self._stats[provider.nome]
            s.requisicoes_ok += 1
            s.ultimo_uso = datetime.now(timezone.utc).isoformat()
            if isinstance(resultado, RespostaLLM):
                s.tokens_entrada += resultado.tokens_entrada
                s.tokens_saida += resultado.tokens_saida

    def _registrar_erro(self, provider: ProvedorLLM, erro: str) -> None:
        with self._lock:
            s = self._stats[provider.nome]
            s.requisicoes_erro += 1
            s.ultimo_erro = erro[:200]
