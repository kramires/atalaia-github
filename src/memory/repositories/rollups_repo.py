"""RollupsRepo (SPEC-04 §6.8)."""
from __future__ import annotations

from datetime import datetime, timezone

from src.memory.database import Database


class RollupsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert_lote(self, rollups: list[dict]) -> None:
        agora = datetime.now(timezone.utc).isoformat()
        self._db.executar_many(
            """INSERT INTO rollups_dashboard
               (tipo, chave, chave2, fonte_trilha, contagem, valor_total, publico_total,
                veiculos_distintos, n_pos, n_neu, n_neg, n_na, atualizado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tipo, chave, COALESCE(chave2,''), fonte_trilha)
               DO UPDATE SET
                   contagem=excluded.contagem,
                   valor_total=excluded.valor_total,
                   publico_total=excluded.publico_total,
                   veiculos_distintos=excluded.veiculos_distintos,
                   n_pos=excluded.n_pos, n_neu=excluded.n_neu,
                   n_neg=excluded.n_neg, n_na=excluded.n_na,
                   atualizado_em=excluded.atualizado_em""",
            [
                (
                    r["tipo"], r["chave"], r.get("chave2"), r["fonte_trilha"],
                    r["contagem"], r.get("valor_total", 0), r.get("publico_total", 0),
                    r.get("veiculos_distintos"), r.get("n_pos", 0), r.get("n_neu", 0),
                    r.get("n_neg", 0), r.get("n_na", 0), agora,
                )
                for r in rollups
            ],
        )
        self._db.commit()

    def buscar_por_tipo(self, tipo: str, fonte_trilha: str = "ALL") -> list[dict]:
        rows = self._db.executar(
            """SELECT chave, chave2, contagem, valor_total, publico_total,
                      veiculos_distintos, n_pos, n_neu, n_neg, n_na
               FROM rollups_dashboard WHERE tipo = ? AND fonte_trilha = ?
               ORDER BY contagem DESC""",
            (tipo, fonte_trilha),
        ).fetchall()
        return [dict(r) for r in rows]
