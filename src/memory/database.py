"""Singleton de conexão SQLite + MigrationRunner (SPEC-04 §3 e §4)."""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class Database:
    """
    Singleton de conexão SQLite.
    Uma conexão por thread (threading.local), WAL mode, FK habilitadas.
    """

    _instance: Database | None = None
    _lock = threading.Lock()

    def __init__(self, caminho: Path) -> None:
        self._caminho = caminho
        self._local = threading.local()

    @classmethod
    def inicializar(cls, caminho: Path) -> Database:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(caminho)
                cls._instance._configurar()
        return cls._instance

    @classmethod
    def instancia(cls) -> Database:
        if cls._instance is None:
            raise RuntimeError("Database não inicializado. Chame Database.inicializar() primeiro.")
        return cls._instance

    def _configurar(self) -> None:
        conn = self._conexao()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-32000")
        conn.commit()

    def _conexao(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self._caminho,
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
            # habilita FK por conexão (necessário em cada nova conexão)
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def executar(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conexao().execute(sql, params)

    def executar_many(self, sql: str, params: list[tuple]) -> sqlite3.Cursor:
        return self._conexao().executemany(sql, params)

    def commit(self) -> None:
        self._conexao().commit()

    def fechar(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


class MigrationRunner:
    """
    Aplica migrations SQL numeradas em ordem crescente.
    Idempotente: migrations já aplicadas são ignoradas.
    """

    MIGRATIONS_DIR = Path("src/memory/migrations")

    def __init__(self, db: Database) -> None:
        self._db = db

    def aplicar_todas(self) -> list[str]:
        """Retorna lista de versões aplicadas nesta execução."""
        self._garantir_tabela_migrations()
        aplicadas_agora: list[str] = []

        for arquivo in sorted(self.MIGRATIONS_DIR.glob("*.sql")):
            versao = arquivo.stem
            if not self._ja_aplicada(versao):
                log.info("migration.aplicando", extra={"dados": {"versao": versao}})
                sql = arquivo.read_text(encoding="utf-8")
                self._db._conexao().executescript(sql)
                self._registrar(versao, arquivo.name)
                aplicadas_agora.append(versao)
                log.info("migration.aplicada", extra={"dados": {"versao": versao}})

        return aplicadas_agora

    def _garantir_tabela_migrations(self) -> None:
        self._db.executar("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                versao      TEXT PRIMARY KEY,
                aplicado_em TEXT NOT NULL,
                descricao   TEXT
            )
        """)
        self._db.commit()

    def _ja_aplicada(self, versao: str) -> bool:
        row = self._db.executar(
            "SELECT 1 FROM schema_migrations WHERE versao = ?", (versao,)
        ).fetchone()
        return row is not None

    def _registrar(self, versao: str, descricao: str) -> None:
        self._db.executar(
            "INSERT INTO schema_migrations (versao, aplicado_em, descricao) VALUES (?, ?, ?)",
            (versao, datetime.now(timezone.utc).isoformat(), descricao),
        )
        self._db.commit()
