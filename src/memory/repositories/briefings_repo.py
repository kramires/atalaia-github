"""BriefingsRepo (SPEC-04 §6.4)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.memory.database import Database


@dataclass
class BriefingRecord:
    id: str
    ciclo_id: str
    gerado_em: datetime
    parte1_md: str
    parte2_md: str
    parte1_html: str
    parte2_html: str
    status: str
    provider_parte1: str = ""
    provider_parte2: str = ""
    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    total_itens: int = 0
    itens_relevantes: int = 0
    nivel_risco: str | None = None


class BriefingsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def inserir(self, b: BriefingRecord) -> None:
        self._db.executar(
            """INSERT INTO briefings
               (id, ciclo_id, gerado_em, periodo_inicio, periodo_fim,
                total_itens, itens_relevantes, nivel_risco,
                parte1_md, parte2_md, parte1_html, parte2_html,
                status, provider_parte1, provider_parte2)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                b.id, b.ciclo_id, b.gerado_em.isoformat(),
                b.periodo_inicio.isoformat() if b.periodo_inicio else None,
                b.periodo_fim.isoformat() if b.periodo_fim else None,
                b.total_itens, b.itens_relevantes, b.nivel_risco,
                b.parte1_md, b.parte2_md, b.parte1_html, b.parte2_html,
                b.status, b.provider_parte1, b.provider_parte2,
            ),
        )
        self._db.commit()

    def buscar_recentes(self, limite: int = 10) -> list[dict]:
        rows = self._db.executar(
            """SELECT id, gerado_em, nivel_risco, status, itens_relevantes, total_itens
               FROM briefings ORDER BY gerado_em DESC LIMIT ?""",
            (limite,),
        ).fetchall()
        return [dict(r) for r in rows]
