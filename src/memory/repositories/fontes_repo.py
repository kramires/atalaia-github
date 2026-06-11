"""FontesRepo — acesso a dados da tabela fontes (SPEC-04 §6.7)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.core.config.config_schema import FonteConfig
from src.memory.database import Database

log = logging.getLogger(__name__)


class FontesRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(self, fonte: FonteConfig) -> None:
        self._db.executar(
            """INSERT INTO fontes (id, nome, tipo, url, ativo, trust_score, criado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   nome=excluded.nome, url=excluded.url,
                   ativo=excluded.ativo, trust_score=excluded.trust_score""",
            (
                fonte.id, fonte.nome, fonte.tipo, fonte.url,
                int(fonte.ativo), fonte.trust_score,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._db.commit()

    def atualizar_ultima_coleta(self, fonte_id: str, erro: str | None = None) -> None:
        agora = datetime.now(timezone.utc).isoformat()
        self._db.executar(
            "UPDATE fontes SET ultima_coleta = ?, ultimo_erro = ? WHERE id = ?",
            (agora, erro, fonte_id),
        )
        self._db.commit()

    def trust_score(self, fonte_id: str) -> float:
        row = self._db.executar(
            "SELECT trust_score FROM fontes WHERE id = ?", (fonte_id,)
        ).fetchone()
        return float(row["trust_score"]) if row else 0.5

    def sincronizar_config(self, fontes: list[FonteConfig]) -> None:
        """Upsert de todas as fontes do config.yaml na tabela fontes."""
        for f in fontes:
            self.upsert(f)
        log.info("fontes.sincronizadas", extra={"dados": {"n": len(fontes)}})
