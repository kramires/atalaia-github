"""AnthropicProvider (SPEC-16 §3.1)."""
from __future__ import annotations

import json
import logging
import os

from anthropic import Anthropic
from pydantic import BaseModel, ValidationError

from src.errors.exceptions import AnalyseDegradadaError
from src.providers.protocol import RespostaLLM

log = logging.getLogger(__name__)


class AnthropicProvider:
    nome = "anthropic"

    def __init__(self, modelo: str = "claude-sonnet-4-6", temperature: float = 0.3) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise AnalyseDegradadaError("ANTHROPIC_API_KEY não está configurada", provider=self.nome)
        self.cliente = Anthropic(api_key=api_key)
        self.modelo = modelo
        self.temperature = temperature

    def completar(self, system: str, user: str, max_tokens: int = 4096) -> RespostaLLM:
        resp = self.cliente.messages.create(
            model=self.modelo,
            max_tokens=max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        first = resp.content[0]
        texto = first.text if hasattr(first, "text") else ""  # type: ignore[union-attr]
        return RespostaLLM(
            conteudo=texto,
            tokens_entrada=resp.usage.input_tokens,
            tokens_saida=resp.usage.output_tokens,
            provider=self.nome,
            modelo=self.modelo,
        )

    def completar_estruturado(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        """Usa tool use para forçar output estruturado."""
        json_schema = schema.model_json_schema()
        tool_def = {
            "name": "resposta_estruturada",
            "description": f"Retorna {schema.__name__} conforme solicitado.",
            "input_schema": json_schema,
        }

        for tentativa in range(2):
            resp = self.cliente.messages.create(  # type: ignore[call-overload]
                model=self.modelo,
                max_tokens=4096,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[tool_def],  # type: ignore[list-item]
                tool_choice={"type": "any"},
            )

            tool_use_block = next((b for b in resp.content if b.type == "tool_use"), None)
            if tool_use_block:
                try:
                    return schema.model_validate(tool_use_block.input)
                except ValidationError as e:
                    log.warning(
                        "anthropic.validacao_falhou",
                        extra={"dados": {"tentativa": tentativa + 1, "erro": str(e)}},
                    )
                    user = f"{user}\n\nErro de validação na tentativa anterior: {e}. Tente novamente."
            else:
                log.warning("anthropic.tool_nao_chamada", extra={"dados": {"tentativa": tentativa + 1}})

        raise AnalyseDegradadaError(
            "Anthropic não chamou a tool após 2 tentativas.", provider=self.nome
        )

    def esta_disponivel(self) -> bool:
        try:
            self.cliente.messages.create(
                model=self.modelo,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
