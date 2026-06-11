#!/bin/bash
# ATALAIA ComSoc — Starter Shell
# Uso: ./start.sh

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$PROJECT_DIR/venv"
PORT=9001

echo ""
echo "════════════════════════════════════════════════════"
echo "  ATALAIA ComSoc — Sistema de Monitoramento de Mídia"
echo "════════════════════════════════════════════════════"
echo ""

# Verificar Python
echo "Verificando Python..."
if ! python3 --version | grep -qE "Python 3\.(11|12|13|14)"; then
    echo "✗ Python 3.11+ necessário"
    exit 1
fi
echo "✓ Python OK"

# Criar/verificar venv
if [ ! -d "$VENV_DIR" ]; then
    echo "⚙ Criando virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
echo "✓ venv OK"

# Ativar venv
echo "⚙ Ativando venv..."
source "$VENV_DIR/bin/activate"
echo "✓ venv ativado"

# Instalar deps
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "⚙ Verificando dependências..."
    pip install -q -r "$PROJECT_DIR/requirements.txt"
    echo "✓ Dependências OK"
fi

# Verificar .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "✗ .env não encontrado!"
    echo "  Crie com: cat > .env << 'EOF'"
    echo "  OPENAI_API_KEY=sk-proj-sua-chave"
    echo "  DEEPSEEK_API_KEY=sk-sua-chave"
    echo "  EOF"
    exit 1
fi
echo "✓ .env carregado"

# Criar banco se não existir
if [ ! -f "$PROJECT_DIR/data/atalaia.db" ]; then
    echo "⚙ Inicializando banco de dados..."
    mkdir -p "$PROJECT_DIR/data"
    python3 << 'SQLEOF'
import sqlite3
from pathlib import Path

db = Path("data/atalaia.db")
conn = sqlite3.connect(db)
c = conn.cursor()

c.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        conteudo TEXT,
        link_original TEXT,
        veiculo TEXT,
        data_pub TEXT,
        fonte_trilha TEXT NOT NULL,
        content_hash TEXT UNIQUE,
        ingested_at TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
""")
c.execute("""
    CREATE TABLE IF NOT EXISTS analise_ia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL UNIQUE,
        sentimento_ia TEXT,
        confianca REAL DEFAULT 0.0,
        narrativa TEXT,
        enquadramento TEXT,
        risco TEXT,
        evidencia TEXT,
        analise_raw TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
    )
""")
c.execute("""
    CREATE TABLE IF NOT EXISTS item_assuntos (
        item_id INTEGER NOT NULL,
        assunto TEXT NOT NULL,
        fonte_original TEXT,
        PRIMARY KEY(item_id, assunto),
        FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
    )
""")
c.execute("""
    CREATE TABLE IF NOT EXISTS ciclos_execucao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        iniciado_em TEXT NOT NULL,
        finalizado_em TEXT,
        status TEXT,
        itens_coletados INTEGER DEFAULT 0,
        itens_relevantes INTEGER DEFAULT 0,
        erro_msg TEXT,
        log_output TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
""")

conn.commit()
conn.close()
SQLEOF
    echo "✓ Banco criado"
fi

# Verificar porta
if lsof -ti:$PORT > /dev/null 2>&1; then
    echo "✗ Porta $PORT já está em uso!"
    echo "  Mate: lsof -ti:$PORT | xargs kill -9"
    exit 1
fi
echo "✓ Porta $PORT disponível"

# Encontrar IP local
LOCAL_IP=$(python3 -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "127.0.0.1")

# Iniciar servidor
echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║                                                    ║"
echo "║  ✓ Sistema iniciado com sucesso!                  ║"
echo "║                                                    ║"
echo "║  Localhost:  http://127.0.0.1:$PORT               ║"
echo "║  Rede Local: http://$LOCAL_IP:$PORT               ║"
echo "║                                                    ║"
echo "║  Tecle Ctrl+C para parar o servidor               ║"
echo "║                                                    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

cd "$PROJECT_DIR"
python3 app.py --port $PORT
