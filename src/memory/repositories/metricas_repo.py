"""MetricasRepo (SPEC-04 §6.6)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from src.memory.database import Database


class MetricasRepo:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._buffer: list[tuple] = []
        self._lock = threading.Lock()

    def registrar(
        self,
        componente: str,
        metrica: str,
        valor: float,
        unidade: str = "",
        ciclo_id: str | None = None,
    ) -> None:
        agora = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._buffer.append((ciclo_id, componente, metrica, valor, unidade, agora))

    def flush(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            self._db.executar_many(
                """INSERT INTO metricas
                   (ciclo_id, componente, metrica, valor, unidade, registrado_em)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                self._buffer,
            )
            self._db.commit()
            self._buffer.clear()

    def resumo_ciclo(self, ciclo_id: str) -> list[dict]:
        rows = self._db.executar(
            "SELECT componente, metrica, valor, unidade FROM metricas WHERE ciclo_id = ?",
            (ciclo_id,),
        ).fetchall()
        return [dict(r) for r in rows]
