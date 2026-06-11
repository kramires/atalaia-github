"""AnaliseIARepo (SPEC-04 §6.3)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from src.memory.database import Database


@dataclass
class AnaliseIARecord:
    item_id: int
    sentimento_ia: str
    confianca: float
    tipo_inferencia: str
    evidencia: str
    provider: str
    modelo: str = ""
    ciclo_id: str | None = None
    narrativa: str | None = None
    enquadramento: str | None = None
    risco: str | None = None
    oportunidade: str | None = None


class AnaliseIARepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def inserir(self, a: AnaliseIARecord) -> int | None:
        agora = datetime.now(timezone.utc).isoformat()
        try:
            cur = self._db.executar(
                """INSERT INTO analise_ia
                   (item_id, sentimento_ia, narrativa, enquadramento, risco, oportunidade,
                    confianca, tipo_inferencia, evidencia, provider, modelo, ciclo_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    a.item_id, a.sentimento_ia, a.narrativa, a.enquadramento,
                    a.risco, a.oportunidade, a.confianca, a.tipo_inferencia,
                    a.evidencia, a.provider, a.modelo, a.ciclo_id, agora,
                ),
            )
            self._db.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # UNIQUE(item_id, ciclo_id) violado — item já analisado neste ciclo
            return None

    def inserir_lote(self, analises: list[AnaliseIARecord]) -> None:
        agora = datetime.now(timezone.utc).isoformat()
        for a in analises:
            try:
                self._db.executar(
                    """INSERT INTO analise_ia
                       (item_id, sentimento_ia, narrativa, enquadramento, risco, oportunidade,
                        confianca, tipo_inferencia, evidencia, provider, modelo, ciclo_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        a.item_id, a.sentimento_ia, a.narrativa, a.enquadramento,
                        a.risco, a.oportunidade, a.confianca, a.tipo_inferencia,
                        a.evidencia, a.provider, a.modelo, a.ciclo_id, agora,
                    ),
                )
            except sqlite3.IntegrityError:
                pass  # duplicata por ciclo — ignorar
        self._db.commit()

    def buscar_por_ciclo(self, ciclo_id: str) -> list[dict]:
        rows = self._db.executar(
            "SELECT * FROM analise_ia WHERE ciclo_id = ?", (ciclo_id,)
        ).fetchall()
        return [dict(r) for r in rows]
