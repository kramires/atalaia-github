"""Carrega config.yaml + .env e valida com Pydantic (ARCHITECTURE §7.1)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from src.core.config.config_schema import ConfigSchema
from src.errors.exceptions import ConfigValidationError

log = logging.getLogger(__name__)

_instancia: ConfigSchema | None = None


def carregar(config_path: Path = Path("config/config.yaml")) -> ConfigSchema:
    """Singleton: carrega e valida config.yaml + .env. Levanta ConfigValidationError se inválido."""
    global _instancia
    if _instancia is not None:
        return _instancia

    load_dotenv(override=False)

    if not config_path.exists():
        raise ConfigValidationError(f"config.yaml não encontrado em: {config_path}")

    try:
        dados = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigValidationError(f"config.yaml inválido: {e}") from e

    try:
        _instancia = ConfigSchema.model_validate(dados)
    except ValidationError as e:
        raise ConfigValidationError(f"Configuração inválida:\n{e}") from e

    log.info("config.carregado", extra={"dados": {"caminho": str(config_path)}})
    return _instancia


def instancia() -> ConfigSchema:
    if _instancia is None:
        raise RuntimeError("ConfigLoader não inicializado. Chame carregar() primeiro.")
    return _instancia
