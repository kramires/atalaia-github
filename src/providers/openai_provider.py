"""OpenAIProvider — suporte a OpenAI e qualquer API OpenAI-compatível (ex: DeepSeek)."""
from __future__ import annotations

import logging
import os
from typing import Any

from openai import OpenAI, APIError, APIConnectionError, RateLimitError, AuthenticationError
from pydantic import BaseModel, ValidationError

from src.errors.exceptions import AnalyseDegradadaError
from src.providers.protocol import RespostaLLM

log = logging.getLogger(__name__)

# Modelos padrão por provider
_MODELOS_PADRAO = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
}

_BASE_URLS = {
    "openai": None,                          # usa o padrão da lib
    "deepseek": "https://api.deepseek.com",
}

_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


class OpenAICompatProvider:
    """Provider OpenAI-compatível. Funciona para OpenAI e DeepSeek."""

    def __init__(
        self,
        perfil: str = "openai",
        modelo: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> None:
        self.perfil = perfil
        env_key = _ENV_KEYS.get(perfil, "OPENAI_API_KEY")
        api_key = os.environ.get(env_key)
        if not api_key:
            raise AnalyseDegradadaError(
                f"{env_key} não está configurada.", provider=perfil
            )
        base_url = _BASE_URLS.get(perfil)
        self.cliente = OpenAI(api_key=api_key, base_url=base_url)
        self.nome = perfil
        self.modelo = modelo or _MODELOS_PADRAO.get(perfil, "gpt-4o-mini")
        self.temperature = temperature
        self._max_tokens = max_tokens

    def completar(self, system: str, user: str, max_tokens: int = 4096) -> RespostaLLM:
        try:
            resp = self.cliente.chat.completions.create(
                model=self.modelo,
                temperature=self.temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            conteudo = resp.choices[0].message.content or ""
            return RespostaLLM(
                conteudo=conteudo,
                tokens_entrada=resp.usage.prompt_tokens if resp.usage else 0,
                tokens_saida=resp.usage.completion_tokens if resp.usage else 0,
                provider=self.nome,
                modelo=self.modelo,
            )
        except (AuthenticationError, RateLimitError, APIConnectionError, APIError) as e:
            raise AnalyseDegradadaError(str(e), provider=self.nome) from e

    def completar_estruturado(
        self, system: str, user: str, schema: type[BaseModel]
    ) -> BaseModel:
        """Usa response_format JSON para saída estruturada."""
        schema_json = schema.model_json_schema()
        system_com_schema = (
            f"{system}\n\nResponda EXCLUSIVAMENTE em JSON válido seguindo este schema:\n"
            f"{schema_json}"
        )

        for tentativa in range(2):
            try:
                resp = self.cliente.chat.completions.create(
                    model=self.modelo,
                    temperature=self.temperature,
                    max_tokens=self._max_tokens,
                    messages=[
                        {"role": "system", "content": system_com_schema},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                conteudo = resp.choices[0].message.content or "{}"
                try:
                    return schema.model_validate_json(conteudo)
                except ValidationError as e:
                    log.warning(
                        f"{self.nome}.validacao_falhou",
                        extra={"dados": {"tentativa": tentativa + 1, "erro": str(e)}},
                    )
                    user = f"{user}\n\nErro de validação: {e}. Corrija e tente novamente."
            except (AuthenticationError, RateLimitError, APIConnectionError, APIError) as e:
                raise AnalyseDegradadaError(str(e), provider=self.nome) from e

        raise AnalyseDegradadaError(
            f"{self.nome}: falhou em estruturar resposta após 2 tentativas.",
            provider=self.nome,
        )

    def esta_disponivel(self) -> bool:
        try:
            self.cliente.chat.completions.create(
                model=self.modelo,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
