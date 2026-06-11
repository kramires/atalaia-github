"""CiclosRepo (SPEC-04 §6.5)."""
from __future__ import annotations

from datetime import datetime, timezone

from src.memory.database import Database


class CiclosRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def iniciar(self, ciclo_id: str) -> None:
        self._db.executar(
            "INSERT INTO ciclos_execucao (id, iniciado_em, status) VALUES (?, ?, 'EXECUTANDO')",
            (ciclo_id, datetime.now(timezone.utc).isoformat()),
        )
        self._db.commit()

    def finalizar(
        self,
        ciclo_id: str,
        status: str,
        stats: dict,
        briefing_id: str | None = None,
        erro_msg: str | None = None,
        duracao_ms: int = 0,
    ) -> None:
        self._db.executar(
            """UPDATE ciclos_execucao SET
                   finalizado_em=?, status=?,
                   itens_coletados=?, itens_processados=?,
                   itens_relevantes=?, itens_acima_cap=?,
                   briefing_id=?, erro_msg=?, duracao_ms=?
               WHERE id=?""",
            (
                datetime.now(timezone.utc).isoformat(), status,
                stats.get("coletados", 0), stats.get("processados", 0),
                stats.get("relevantes", 0), stats.get("acima_cap", 0),
                briefing_id, erro_msg, duracao_ms, ciclo_id,
            ),
        )
        self._db.commit()

    def ultimo_completo(self) -> dict | None:
        row = self._db.executar(
            """SELECT * FROM ciclos_execucao
               WHERE status IN ('COMPLETO','DEGRADADO')
               ORDER BY finalizado_em DESC LIMIT 1"""
        ).fetchone()
        return dict(row) if row else None
