"""Scheduler com APScheduler para ciclos automáticos (ARCHITECTURE §3.1)."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from src.core.lifecycle.cycle_manager import CicloManager
from src.memory.database import Database

log = logging.getLogger(__name__)


class Scheduler:
    """Dispara ciclos periódicos usando APScheduler."""

    def __init__(
        self,
        db: Database,
        intervalo_minutos: int = 60,
        timezone_str: str = "America/Sao_Paulo",
    ) -> None:
        self._db = db
        self._intervalo_minutos = intervalo_minutos
        self._timezone_str = timezone_str
        self._scheduler = BackgroundScheduler(
            {
                "apscheduler.timezone": timezone_str,
            }
        )
        self._manager = CicloManager(db)
        self._lock = threading.Lock()
        self._ciclo_ativo = False

    def iniciar(self) -> None:
        """Inicia o scheduler com job periódico."""
        self._scheduler.add_job(
            self._job_executar_ciclo,
            "interval",
            minutes=self._intervalo_minutos,
            id="ciclo_periodico",
            name="Ciclo Trilha B Periódico",
            next_run_time=datetime.now(tz=timezone.utc),
        )
        self._scheduler.start()
        log.info(
            "scheduler.iniciado",
            extra={
                "dados": {
                    "intervalo_minutos": self._intervalo_minutos,
                    "timezone": self._timezone_str,
                }
            },
        )

    def parar(self) -> None:
        """Para o scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown()
            log.info("scheduler.parado")

    def _job_executar_ciclo(self) -> None:
        """Job executado periodicamente."""
        with self._lock:
            if self._ciclo_ativo:
                log.warning(
                    "scheduler.ciclo_ja_em_execucao",
                    extra={"dados": {"timestamp": datetime.now().isoformat()}},
                )
                return

            self._ciclo_ativo = True

        try:
            resultado = self._manager.executar_ciclo()
            log.info(
                "scheduler.ciclo_concluido",
                extra={"dados": {"resultado": resultado["status"]}},
            )
        except Exception as e:
            log.error(
                "scheduler.ciclo_erro",
                extra={"dados": {"erro": str(e)}},
            )
        finally:
            self._ciclo_ativo = False

    def esta_rodando(self) -> bool:
        """True se scheduler está ativo."""
        return self._scheduler.running

    def proxima_execucao(self) -> datetime | None:
        """Data/hora da próxima execução."""
        job = self._scheduler.get_job("ciclo_periodico")
        return job.next_run_time if job else None
