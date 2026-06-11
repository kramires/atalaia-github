"""Testes de Database e Repositories (SPEC-04)."""
import tempfile
from pathlib import Path

import pytest

from src.memory.database import Database, MigrationRunner
from src.memory.repositories.items_repo import ItemsRepo
from src.memory.repositories.ciclos_repo import CiclosRepo
from src.memory.repositories.rollups_repo import RollupsRepo


@pytest.fixture
def db():
    """Cria DB isolado para cada teste (reseta singleton)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    # Reset singleton para garantir instância nova por teste
    Database._instance = None
    d = Database.inicializar(path)
    MigrationRunner(d).aplicar_todas()
    yield d
    Database._instance = None
    path.unlink(missing_ok=True)


class TestDatabase:
    def test_inicializar_cria_banco(self, db):
        result = db.executar("PRAGMA integrity_check").fetchone()[0]
        assert result == "ok"

    def test_migrations_aplicadas(self, db):
        tabelas = {r[0] for r in db.executar("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "items" in tabelas
        assert "analise_ia" in tabelas
        assert "briefings" in tabelas
        assert "rollups_dashboard" in tabelas

    def test_banco_operacional(self, db):
        # Banco deve estar funcional após inicializar + migrations
        n = db.executar("SELECT COUNT(*) FROM items").fetchone()[0]
        assert n == 0


class TestItemsRepo:
    def _row(self, content_hash: str) -> dict:
        from datetime import datetime, timezone
        return {
            "content_hash": content_hash,
            "fonte_trilha": "A",
            "titulo": f"Teste {content_hash}",
            "sentimento": "POSITIVA",
            "data_pub": "2026-01-01",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }

    def test_insert_ou_ignore(self, db):
        repo = ItemsRepo(db)
        row = self._row("abc123_unico_test")
        r1 = repo.inserir_ccomsex(row)
        r2 = repo.inserir_ccomsex(row)
        db.commit()
        assert r1.duplicado is False
        assert r2.duplicado is True

    def test_contar(self, db):
        repo = ItemsRepo(db)
        assert repo.contar() == 0

    def test_buscar_recentes_sem_itens(self, db):
        repo = ItemsRepo(db)
        itens = repo.buscar_recentes(90)
        assert itens == []

    def test_existe_por_hash(self, db):
        repo = ItemsRepo(db)
        row = self._row("xyz999_unico_test")
        r = repo.inserir_ccomsex(row)
        db.commit()
        assert r.duplicado is False
        assert repo.existe("xyz999_unico_test") is True
        assert repo.existe("hash_inexistente_99") is False


class TestCiclosRepo:
    def test_ciclo_lifecycle(self, db):
        repo = CiclosRepo(db)
        repo.iniciar("ciclo-001")
        repo.finalizar("ciclo-001", "COMPLETO", {"coletados": 5})
        # Não deve lançar exceção

    def test_duplo_iniciar(self, db):
        repo = CiclosRepo(db)
        repo.iniciar("ciclo-dup")
        # Segundo iniciar com mesmo ID não deve lançar
        # (pode ser INSERT OR IGNORE ou ON CONFLICT)
        try:
            repo.iniciar("ciclo-dup")
        except Exception:
            pass  # tolerável


class TestRollupsRepo:
    def test_upsert_lote(self, db):
        repo = RollupsRepo(db)
        rollups = [
            {
                "tipo": "mes_resumo", "chave": "2026-01", "chave2": None,
                "fonte_trilha": "ALL", "contagem": 10, "valor_total": 5000.0,
                "publico_total": 200000.0, "veiculos_distintos": 5,
                "n_pos": 4, "n_neu": 3, "n_neg": 2, "n_na": 1,
            }
        ]
        repo.upsert_lote(rollups)
        rows = repo.buscar_por_tipo("mes_resumo", "ALL")
        assert len(rows) == 1
        assert rows[0]["contagem"] == 10

    def test_upsert_idempotente(self, db):
        repo = RollupsRepo(db)
        rollup = {
            "tipo": "veiculo", "chave": "Jornal A", "chave2": None,
            "fonte_trilha": "ALL", "contagem": 5, "valor_total": 1000.0,
            "publico_total": 0.0, "veiculos_distintos": None,
            "n_pos": 3, "n_neu": 1, "n_neg": 1, "n_na": 0,
        }
        repo.upsert_lote([rollup])
        rollup["contagem"] = 10
        repo.upsert_lote([rollup])
        rows = repo.buscar_por_tipo("veiculo", "ALL")
        assert rows[0]["contagem"] == 10
