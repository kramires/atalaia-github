"""ProviderFactory — cria providers configuráveis por pipeline (SPEC-16 §2)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from src.core.config.config_schema import ConfigSchema
from src.errors.exceptions import AnalyseDegradadaError, ConfigValidationError
from src.providers.protocol import ProvedorLLM

log = logging.getLogger(__name__)

# Providers válidos
_PROVIDERS_VALIDOS = "claude, openai, deepseek, balanceado, ollama, degradado"


def _carregar_dotenv() -> None:
    """Carrega variáveis do .env se existir."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, _, valor = linha.partition("=")
                os.environ.setdefault(chave.strip(), valor.strip())


class ProviderFactory:
    def __init__(self, config: ConfigSchema) -> None:
        _carregar_dotenv()
        self._config = config
        self._cache: dict[str, ProvedorLLM] = {}

    def provider_para(self, pipeline: str) -> ProvedorLLM:
        """
        Retorna o provider configurado para o pipeline.

        Se o provider não puder ser criado (SDK ausente, ex.: `openai` não
        instalado; ou chave de API faltando/ inválida na criação), cai em
        DegradadoProvider com log claro — o briefing nunca derruba o app com
        500 (RF-24, modo degradado funcional).
        """
        nome = getattr(self._config.providers, pipeline, "balanceado")
        if nome not in self._cache:
            try:
                self._cache[nome] = self._criar(nome)
            except ImportError as e:
                log.error("provider.sdk_ausente", extra={"dados": {
                    "pipeline": pipeline, "provider": nome, "erro": str(e),
                    "acao": "pip install -r requirements.txt no venv"}})
                self._cache[nome] = self._degradado()
            except Exception as e:  # noqa: BLE001 — falha de config/chave não pode derrubar o app
                log.error("provider.falha_criacao", extra={"dados": {
                    "pipeline": pipeline, "provider": nome, "erro": str(e),
                    "acao": "verifique a chave de API no .env"}})
                self._cache[nome] = self._degradado()
        return self._cache[nome]

    def _degradado(self) -> ProvedorLLM:
        from src.providers.degradado_provider import DegradadoProvider
        return DegradadoProvider()

    def _criar(self, nome: str) -> ProvedorLLM:
        if nome == "claude":
            from src.providers.anthropic_provider import AnthropicProvider
            return AnthropicProvider(
                self._config.anthropic.modelo,
                self._config.anthropic.temperature,
            )

        if nome == "openai":
            from src.providers.openai_provider import OpenAICompatProvider
            return OpenAICompatProvider(
                perfil="openai",
                modelo=self._config.openai.modelo,
                temperature=self._config.openai.temperature,
                max_tokens=self._config.openai.max_tokens,
            )

        if nome == "deepseek":
            from src.providers.openai_provider import OpenAICompatProvider
            return OpenAICompatProvider(
                perfil="deepseek",
                modelo=self._config.deepseek.modelo,
                temperature=self._config.deepseek.temperature,
                max_tokens=self._config.deepseek.max_tokens,
            )

        if nome == "balanceado":
            return self._criar_balanceado()

        if nome == "ollama":
            from src.providers.ollama_provider import OllamaProvider
            return OllamaProvider(
                self._config.ollama.base_url,
                self._config.ollama.modelo,
            )

        if nome == "degradado":
            from src.providers.degradado_provider import DegradadoProvider
            return DegradadoProvider()

        raise ConfigValidationError(
            f"Provider desconhecido: '{nome}'. Válidos: {_PROVIDERS_VALIDOS}"
        )

    def _criar_balanceado(self) -> ProvedorLLM:
        """Cria BalanceadoProvider: OpenAI (primário) → DeepSeek (secundário).
        Se uma das chaves faltar, tenta o provider disponível como único."""
        from src.providers.balanceado_provider import BalanceadoProvider
        from src.providers.degradado_provider import DegradadoProvider
        from src.providers.openai_provider import OpenAICompatProvider

        primario: ProvedorLLM | None = None
        secundario: ProvedorLLM | None = None

        try:
            primario = OpenAICompatProvider(
                perfil="openai",
                modelo=self._config.openai.modelo,
                temperature=self._config.openai.temperature,
                max_tokens=self._config.openai.max_tokens,
            )
        except AnalyseDegradadaError as e:
            log.warning("factory.openai_indisponivel", extra={"dados": {"erro": str(e)}})

        try:
            secundario = OpenAICompatProvider(
                perfil="deepseek",
                modelo=self._config.deepseek.modelo,
                temperature=self._config.deepseek.temperature,
                max_tokens=self._config.deepseek.max_tokens,
            )
        except AnalyseDegradadaError as e:
            log.warning("factory.deepseek_indisponivel", extra={"dados": {"erro": str(e)}})

        if primario and secundario:
            return BalanceadoProvider(primario, secundario)
        if primario:
            log.info("factory.usando_apenas_openai")
            return primario
        if secundario:
            log.info("factory.usando_apenas_deepseek")
            return secundario

        log.error("factory.nenhum_provider_disponivel")
        return DegradadoProvider()
