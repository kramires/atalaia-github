#!/bin/sh
# Inicializa o banco (migrations idempotentes) e sobe o servidor web.
set -e

echo "→ Inicializando banco de dados (migrations)…"
python - <<'PY'
from pathlib import Path
from src.memory.database import Database, MigrationRunner
db = Database.inicializar(Path("data/atalaia.db"))
MigrationRunner(db).aplicar_todas()
print("✓ Banco pronto")
PY

PORT="${PORT:-9001}"
echo "→ Iniciando ATALAIA ComSoc em 0.0.0.0:${PORT}…"
exec python app.py --host 0.0.0.0 --port "${PORT}"
