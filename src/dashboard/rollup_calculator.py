"""RollupCalculator — agrega rollups pré-computados para o dashboard (SPEC-10)."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from src.memory.database import Database
from src.memory.repositories.rollups_repo import RollupsRepo

log = logging.getLogger(__name__)

TRILHAS = ("A", "B", "ALL")


class RollupCalculator:
    def __init__(self, db: Database, rollups_repo: RollupsRepo) -> None:
        self._db = db
        self._repo = rollups_repo

    def recalcular_todos(self) -> dict:
        inicio = time.monotonic()
        stats: dict = {}
        agora = datetime.now(timezone.utc).isoformat()

        for trilha in TRILHAS:
            stats[f"mes_resumo_{trilha}"] = self._rollup_mes_resumo(trilha, agora)
            stats[f"mes_sentimento_{trilha}"] = self._rollup_mes_sentimento(trilha, agora)
            stats[f"veiculo_{trilha}"] = self._rollup_categoria(
                trilha, agora, "veiculo", "COALESCE(i.veiculo,'(sem veículo)')"
            )
            stats[f"assunto_{trilha}"] = self._rollup_assunto(trilha, agora)
            stats[f"uf_{trilha}"] = self._rollup_categoria(
                trilha, agora, "uf", "COALESCE(i.uf,'(sem UF)')", apenas_contagem=True
            )
            stats[f"midia_{trilha}"] = self._rollup_categoria(
                trilha, agora, "midia", "COALESCE(i.midia,'(sem mídia)')", apenas_contagem=True
            )

        stats["duracao_ms"] = int((time.monotonic() - inicio) * 1000)
        log.info("rollups.recalculados", extra={"dados": stats})
        return stats

    def _rollup_mes_resumo(self, trilha: str, agora: str) -> int:
        """Uma linha por (ano_mes, trilha) com todos os KPIs incluindo veiculos_distintos."""
        rows = self._db.executar(
            """
            SELECT
                SUBSTR(i.data_pub, 1, 7) AS ano_mes,
                COUNT(*) AS n,
                COALESCE(SUM(i.valor), 0) AS val,
                COALESCE(SUM(i.publico), 0) AS pub,
                COUNT(DISTINCT i.veiculo) AS veic_dist,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'POSITIVA' THEN 1 ELSE 0 END) AS n_pos,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NEUTRA'   THEN 1 ELSE 0 END) AS n_neu,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NEGATIVA' THEN 1 ELSE 0 END) AS n_neg,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NA'       THEN 1 ELSE 0 END) AS n_na
            FROM items i
            LEFT JOIN analise_ia a
                ON a.item_id = i.id
                AND a.created_at = (SELECT MAX(created_at) FROM analise_ia WHERE item_id = i.id)
            WHERE i.data_pub IS NOT NULL
              AND (? = 'ALL' OR i.fonte_trilha = ?)
            GROUP BY ano_mes
            """,
            (trilha, trilha),
        ).fetchall()

        rollups = [
            {
                "tipo": "mes_resumo",
                "chave": r["ano_mes"],
                "chave2": None,
                "fonte_trilha": trilha,
                "contagem": r["n"],
                "valor_total": r["val"],
                "publico_total": r["pub"],
                "veiculos_distintos": r["veic_dist"],
                "n_pos": r["n_pos"],
                "n_neu": r["n_neu"],
                "n_neg": r["n_neg"],
                "n_na": r["n_na"],
            }
            for r in rows
            if r["ano_mes"]
        ]
        if rollups:
            self._repo.upsert_lote(rollups)
        return len(rollups)

    def _rollup_mes_sentimento(self, trilha: str, agora: str) -> int:
        """Breakdown por mês × sentimento — alimenta gráfico série empilhada."""
        rows = self._db.executar(
            """
            SELECT
                SUBSTR(i.data_pub, 1, 7) AS ano_mes,
                COALESCE(a.sentimento_ia, i.sentimento, 'NA') AS sentimento_exibido,
                COUNT(*) AS n,
                COALESCE(SUM(i.valor), 0) AS val,
                COALESCE(SUM(i.publico), 0) AS pub
            FROM items i
            LEFT JOIN analise_ia a
                ON a.item_id = i.id
                AND a.created_at = (SELECT MAX(created_at) FROM analise_ia WHERE item_id = i.id)
            WHERE i.data_pub IS NOT NULL
              AND (? = 'ALL' OR i.fonte_trilha = ?)
            GROUP BY ano_mes, sentimento_exibido
            """,
            (trilha, trilha),
        ).fetchall()

        rollups = [
            {
                "tipo": "mes_sentimento",
                "chave": r["ano_mes"],
                "chave2": r["sentimento_exibido"],
                "fonte_trilha": trilha,
                "contagem": r["n"],
                "valor_total": r["val"],
                "publico_total": r["pub"],
            }
            for r in rows
            if r["ano_mes"]
        ]
        if rollups:
            self._repo.upsert_lote(rollups)
        return len(rollups)

    def _rollup_categoria(
        self,
        trilha: str,
        agora: str,
        tipo: str,
        expr_chave: str,
        apenas_contagem: bool = False,
    ) -> int:
        """Rollup genérico para veiculo, uf, midia com breakdown de sentimento."""
        sent_cols = (
            "" if apenas_contagem
            else """,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'POSITIVA' THEN 1 ELSE 0 END) AS n_pos,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NEUTRA'   THEN 1 ELSE 0 END) AS n_neu,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NEGATIVA' THEN 1 ELSE 0 END) AS n_neg,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NA'       THEN 1 ELSE 0 END) AS n_na"""
        )

        rows = self._db.executar(
            f"""
            SELECT
                {expr_chave} AS chave,
                COUNT(*) AS n,
                COALESCE(SUM(i.valor), 0) AS val,
                COALESCE(SUM(i.publico), 0) AS pub
                {sent_cols}
            FROM items i
            LEFT JOIN analise_ia a
                ON a.item_id = i.id
                AND a.created_at = (SELECT MAX(created_at) FROM analise_ia WHERE item_id = i.id)
            WHERE (? = 'ALL' OR i.fonte_trilha = ?)
            GROUP BY {expr_chave}
            ORDER BY n DESC
            LIMIT 50
            """,
            (trilha, trilha),
        ).fetchall()

        rollups = [
            {
                "tipo": tipo,
                "chave": r["chave"],
                "chave2": None,
                "fonte_trilha": trilha,
                "contagem": r["n"],
                "valor_total": r["val"],
                "publico_total": r["pub"],
                "n_pos": dict(r).get("n_pos", 0),
                "n_neu": dict(r).get("n_neu", 0),
                "n_neg": dict(r).get("n_neg", 0),
                "n_na": dict(r).get("n_na", 0),
            }
            for r in rows
        ]
        if rollups:
            self._repo.upsert_lote(rollups)
        return len(rollups)

    def _rollup_assunto(self, trilha: str, agora: str) -> int:
        """Rollup de assuntos via JOIN com item_assuntos."""
        rows = self._db.executar(
            """
            SELECT
                ia.assunto AS chave,
                COUNT(*) AS n,
                COALESCE(SUM(i.valor), 0) AS val,
                COALESCE(SUM(i.publico), 0) AS pub,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'POSITIVA' THEN 1 ELSE 0 END) AS n_pos,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NEUTRA'   THEN 1 ELSE 0 END) AS n_neu,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NEGATIVA' THEN 1 ELSE 0 END) AS n_neg,
                SUM(CASE WHEN COALESCE(a.sentimento_ia, i.sentimento, 'NA') = 'NA'       THEN 1 ELSE 0 END) AS n_na
            FROM item_assuntos ia
            JOIN items i ON i.id = ia.item_id
            LEFT JOIN analise_ia a
                ON a.item_id = i.id
                AND a.created_at = (SELECT MAX(created_at) FROM analise_ia WHERE item_id = i.id)
            WHERE (? = 'ALL' OR i.fonte_trilha = ?)
              AND ia.assunto != ''
            GROUP BY ia.assunto
            ORDER BY n DESC
            LIMIT 50
            """,
            (trilha, trilha),
        ).fetchall()

        rollups = [
            {
                "tipo": "assunto",
                "chave": r["chave"],
                "chave2": None,
                "fonte_trilha": trilha,
                "contagem": r["n"],
                "valor_total": r["val"],
                "publico_total": r["pub"],
                "n_pos": r["n_pos"],
                "n_neu": r["n_neu"],
                "n_neg": r["n_neg"],
                "n_na": r["n_na"],
            }
            for r in rows
        ]
        if rollups:
            self._repo.upsert_lote(rollups)
        return len(rollups)
