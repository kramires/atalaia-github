"""ItemsRepo — acesso a dados da tabela items (SPEC-04 §6.2)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from src.memory.database import Database


@dataclass
class ItemInserido:
    item_id: int | None
    content_hash: str
    duplicado: bool


class ItemsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Trilha A ──────────────────────────────────────────────────────────────

    def inserir_ccomsex(self, row: dict) -> ItemInserido:
        """INSERT OR IGNORE para itens da Trilha A. Commit feito pelo ETLLoader."""
        cols = ", ".join(row.keys())
        ph = ", ".join("?" * len(row))
        try:
            cur = self._db.executar(
                f"INSERT INTO items ({cols}) VALUES ({ph})", tuple(row.values())
            )
            return ItemInserido(item_id=cur.lastrowid, content_hash=row["content_hash"], duplicado=False)
        except sqlite3.IntegrityError:
            return ItemInserido(item_id=None, content_hash=row["content_hash"], duplicado=True)

    def inserir_assuntos(self, item_id: int, assuntos: list[str]) -> None:
        """Insere assuntos na tabela item_assuntos. Commit feito pelo chamador."""
        self._db.executar_many(
            "INSERT INTO item_assuntos (item_id, assunto) VALUES (?, ?)",
            [(item_id, a) for a in assuntos],
        )

    # ── Trilha B ──────────────────────────────────────────────────────────────

    def inserir_ou_ignorar_b(self, row: dict, ciclo_id: str | None = None) -> ItemInserido:
        """INSERT OR IGNORE para item da Trilha B. Faz commit individual."""
        row = {**row, "ciclo_id": ciclo_id}
        cols = ", ".join(row.keys())
        ph = ", ".join("?" * len(row))
        try:
            cur = self._db.executar(
                f"INSERT INTO items ({cols}) VALUES ({ph})", tuple(row.values())
            )
            self._db.commit()
            return ItemInserido(item_id=cur.lastrowid, content_hash=row["content_hash"], duplicado=False)
        except sqlite3.IntegrityError:
            return ItemInserido(item_id=None, content_hash=row["content_hash"], duplicado=True)

    def atualizar_relevance_score(self, item_id: int, score: float) -> None:
        self._db.executar("UPDATE items SET relevance_score = ? WHERE id = ?", (score, item_id))

    def marcar_pendente(self, item_id: int) -> None:
        self._db.executar("UPDATE items SET pendente_analise = 1 WHERE id = ?", (item_id,))

    def desmarcar_pendente(self, item_id: int) -> None:
        self._db.executar("UPDATE items SET pendente_analise = 0 WHERE id = ?", (item_id,))

    def buscar_pendentes(self, limite: int = 100, desde: date | None = None) -> list[dict]:
        filtro = "AND data_pub >= ?" if desde else ""
        params: tuple = (desde.isoformat(), limite) if desde else (limite,)
        rows = self._db.executar(
            f"""SELECT id, content_hash, titulo, conteudo_texto, link_original,
                       fonte_id, veiculo, data_pub, relevance_score
                FROM items
                WHERE pendente_analise = 1 AND fonte_trilha = 'B'
                {filtro}
                ORDER BY ingested_at ASC LIMIT ?""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def buscar_recentes(self, janela_dias: int) -> list[dict]:
        """Itens dos últimos janela_dias dias com sentimento fusionado (análise mais recente)."""
        desde = (date.today() - timedelta(days=janela_dias)).isoformat()
        rows = self._db.executar(
            """SELECT i.id, i.data_pub, i.titulo, i.link_original, i.veiculo,
                      i.uf, i.midia, i.valor, i.publico, i.assunto,
                      COALESCE(a.sentimento_ia, i.sentimento, 'NA') AS sentimento_exibido,
                      a.narrativa, a.risco
               FROM items i
               LEFT JOIN analise_ia a
                   ON a.item_id = i.id
                   AND a.created_at = (
                       SELECT MAX(created_at) FROM analise_ia WHERE item_id = i.id
                   )
               WHERE i.data_pub >= ?
               ORDER BY i.data_pub DESC, i.id DESC""",
            (desde,),
        ).fetchall()
        return [dict(r) for r in rows]

    def contar(self, fonte_trilha: str | None = None) -> int:
        if fonte_trilha:
            return self._db.executar(
                "SELECT COUNT(*) FROM items WHERE fonte_trilha = ?", (fonte_trilha,)
            ).fetchone()[0]
        return self._db.executar("SELECT COUNT(*) FROM items").fetchone()[0]

    def existe(self, content_hash: str) -> bool:
        row = self._db.executar(
            "SELECT 1 FROM items WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return row is not None
