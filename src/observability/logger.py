"""Logger estruturado JSON Lines (SPEC-14 §2)."""
import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path


class JSONLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        dados = getattr(record, "dados", {})
        entrada: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "componente": record.name,
            "evento": record.getMessage(),
            "dados": dados,
            "duracao_ms": getattr(record, "duracao_ms", None),
            "ciclo_id": getattr(record, "ciclo_id", None),
            "erro": None,
        }
        if record.exc_info:
            entrada["erro"] = self.formatException(record.exc_info)
        return json.dumps(entrada, ensure_ascii=False)


def configurar_logger(nivel: str, dir_logs: Path) -> None:
    """Chamado uma vez na startup — configura o root logger."""
    dir_logs.mkdir(parents=True, exist_ok=True)

    handler_arquivo = logging.handlers.TimedRotatingFileHandler(
        filename=str(dir_logs / "atalaia.jsonl"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    handler_arquivo.setFormatter(JSONLinesFormatter())

    handler_console = logging.StreamHandler(sys.stderr)
    handler_console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    )

    nivel_int = getattr(logging, nivel.upper(), logging.INFO)
    logging.basicConfig(level=nivel_int, handlers=[handler_arquivo, handler_console])
