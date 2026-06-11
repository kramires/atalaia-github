#!/usr/bin/env python3
"""
ATALAIA ComSoc — Starter Inteligente
Inicia todo o sistema com um clique
Porta: 9001 (menos usada, evita conflitos)
"""

import os
import sys
import subprocess
import socket
import time
from pathlib import Path

# ── Configurações ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
VENV_PATH = PROJECT_ROOT / "venv"
PORT = 9001
HOST = "0.0.0.0"

# ── Cores para output ──────────────────────────────────
class C:
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header():
    """Banner de início"""
    print("\n" + "═" * 60)
    print(f"{C.BOLD}{C.CYAN}  ATALAIA ComSoc — Sistema de Monitoramento de Mídia{C.RESET}")
    print("═" * 60 + "\n")


def check_python():
    """Verifica Python 3.11+"""
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 11):
        print(f"{C.RED}✗ Python 3.11+ necessário (você tem {v.major}.{v.minor}){C.RESET}")
        sys.exit(1)
    print(f"{C.GREEN}✓ Python {v.major}.{v.minor}.{v.micro}{C.RESET}")


def check_venv():
    """Verifica se venv existe, senão cria"""
    if not VENV_PATH.exists():
        print(f"{C.YELLOW}⚙ Criando virtual environment...{C.RESET}")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_PATH)], check=True)
        print(f"{C.GREEN}✓ venv criado{C.RESET}")
    else:
        print(f"{C.GREEN}✓ venv encontrado{C.RESET}")


def check_requirements():
    """
    Garante que TODAS as dependências do requirements.txt estão no venv.

    NÃO usa 'pip check' para decidir (ele só valida compatibilidade entre o que JÁ
    está instalado — não detecta pacote ausente). Em vez disso, roda sempre
    'pip install -r requirements.txt' (idempotente; rápido quando já satisfeito) e,
    ao final, verifica os imports críticos, abortando com mensagem clara se faltar.
    """
    req_file = PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        print(f"{C.RED}✗ requirements.txt não encontrado{C.RESET}")
        sys.exit(1)

    if sys.platform == "win32":
        pip_exe = VENV_PATH / "Scripts" / "pip"
        python_exe = VENV_PATH / "Scripts" / "python"
    else:
        pip_exe = VENV_PATH / "bin" / "pip"
        python_exe = VENV_PATH / "bin" / "python"

    # Instala/atualiza tudo (idempotente). Sem timeout curto — a 1ª vez pode demorar.
    print(f"{C.YELLOW}⚙ Verificando/instalando dependências (a 1ª vez pode levar alguns minutos)...{C.RESET}")
    try:
        subprocess.run(
            [str(pip_exe), "install", "-r", str(req_file)],
            check=True,
        )
    except subprocess.CalledProcessError:
        print(f"{C.RED}✗ Falha ao instalar dependências. Rode manualmente:{C.RESET}")
        print(f"    {pip_exe} install -r {req_file}")
        sys.exit(1)

    # Verificação final dos imports críticos (módulo -> pacote pip)
    criticos = {
        "yaml": "pyyaml", "pydantic": "pydantic", "fastapi": "fastapi",
        "uvicorn": "uvicorn", "pandas": "pandas", "jinja2": "Jinja2",
        "openai": "openai", "httpx": "httpx", "feedparser": "feedparser",
        "bleach": "bleach", "openpyxl": "openpyxl", "apscheduler": "APScheduler",
    }
    faltando = []
    for modulo, pacote in criticos.items():
        r = subprocess.run(
            [str(python_exe), "-c", f"import {modulo}"],
            capture_output=True,
        )
        if r.returncode != 0:
            faltando.append(pacote)

    if faltando:
        print(f"{C.RED}✗ Dependências ainda ausentes no venv: {', '.join(faltando)}{C.RESET}")
        print(f"    {pip_exe} install {' '.join(faltando)}")
        sys.exit(1)

    print(f"{C.GREEN}✓ Dependências OK{C.RESET}")


def check_env():
    """Verifica .env"""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        print(f"{C.RED}✗ .env não encontrado!{C.RESET}")
        print(f"   Crie com: cat > .env << 'EOF'")
        print(f"   OPENAI_API_KEY=sk-proj-sua-chave")
        print(f"   DEEPSEEK_API_KEY=sk-sua-chave")
        print(f"   EOF")
        sys.exit(1)

    # Carregar .env
    with open(env_file) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val

    # Verificar chaves
    if not os.environ.get("OPENAI_API_KEY"):
        print(f"{C.RED}✗ OPENAI_API_KEY não configurada em .env{C.RESET}")
        sys.exit(1)

    print(f"{C.GREEN}✓ .env carregado{C.RESET}")


def check_db():
    """Verifica/cria banco de dados"""
    db_file = PROJECT_ROOT / "data" / "atalaia.db"
    if not db_file.exists():
        print(f"{C.YELLOW}⚙ Inicializando banco de dados...{C.RESET}")
        db_file.parent.mkdir(exist_ok=True)

        import sqlite3
        conn = sqlite3.connect(db_file)
        c = conn.cursor()

        # Minimal schema
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
        print(f"{C.GREEN}✓ Banco de dados criado{C.RESET}")
    else:
        print(f"{C.GREEN}✓ Banco de dados encontrado{C.RESET}")


def check_port():
    """Verifica se porta 9001 está livre"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", PORT))
    sock.close()

    if result == 0:
        print(f"{C.RED}✗ Porta {PORT} já está em uso!{C.RESET}")
        print(f"   Mate o processo: lsof -ti:{PORT} | xargs kill -9")
        sys.exit(1)

    print(f"{C.GREEN}✓ Porta {PORT} disponível{C.RESET}")


def get_local_ip():
    """Encontra IP local da máquina"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_server():
    """Inicia servidor FastAPI"""
    print(f"\n{C.BOLD}Iniciando servidor...{C.RESET}\n")

    # Python executable dentro do venv
    if sys.platform == "win32":
        python_exe = VENV_PATH / "Scripts" / "python"
    else:
        python_exe = VENV_PATH / "bin" / "python"

    # Comando: python app.py --port 9001
    cmd = [str(python_exe), str(PROJECT_ROOT / "app.py"), "--port", str(PORT)]

    # Mostrar IPs antes de iniciar
    local_ip = get_local_ip()
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print(f"║  {C.GREEN}✓ Sistema iniciado com sucesso!{C.RESET}" + " " * 28 + "║")
    print("║" + " " * 58 + "║")
    print(f"║  {C.BOLD}Localhost:{C.RESET}  http://127.0.0.1:{PORT}" + " " * 19 + "║")
    print(f"║  {C.BOLD}Rede Local:{C.RESET} http://{local_ip}:{PORT}" + " " * (23 - len(str(local_ip))) + "║")
    print("║" + " " * 58 + "║")
    print("║  Tecle Ctrl+C para parar o servidor" + " " * 22 + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "═" * 58 + "╝\n")

    # Executar app.py
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT)
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}⏹ Servidor parado{C.RESET}\n")
    except Exception as e:
        print(f"{C.RED}✗ Erro ao iniciar servidor: {e}{C.RESET}")
        sys.exit(1)


def main():
    """Fluxo principal"""
    print_header()

    print(f"{C.BOLD}Verificando pré-requisitos...{C.RESET}\n")

    try:
        check_python()
        check_venv()
        check_requirements()
        check_env()
        check_db()
        check_port()
    except Exception as e:
        print(f"\n{C.RED}✗ Erro durante setup: {e}{C.RESET}")
        sys.exit(1)

    start_server()


if __name__ == "__main__":
    main()
