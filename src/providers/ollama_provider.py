"""OllamaProvider (SPEC-16 §3.2)."""
from __future__ import annotations

import json
import logging

import httpx
from pydantic import BaseModel, ValidationError

from src.errors.exceptions import AnalyseDegradadaError
from src.providers.protocol import RespostaLLM

log = logging.getLogger(__name__)


class OllamaProvider:
    nome = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", modelo: str = "llama3.1") -> None:
        self.base_url = base_url
        self.modelo = modelo

    def completar(self, system: str, user: str, max_tokens: int = 4096) -> RespostaLLM:
        payload = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        conteudo = data["message"]["content"]
        return RespostaLLM(
            conteudo=conteudo,
            tokens_entrada=data.get("prompt_eval_count", 0),
            tokens_saida=data.get("eval_count", 0),
            provider=self.nome,
            modelo=self.modelo,
        )

    def completar_estruturado(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        """JSON mode + 1 retry em ValidationError."""
        schema_str = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)
        system_com_schema = (
            f"{system}\n\nRETORNE EXCLUSIVAMENTE JSON válido que siga este schema:\n"
            f"```json\n{schema_str}\n```\n"
            "Não inclua texto fora do JSON."
        )

        for tentativa in range(2):
            payload = {
                "model": self.modelo,
                "messages": [
                    {"role": "system", "content": system_com_schema},
                    {"role": "user", "content": user},
                ],
                "format": "json",
                "stream": False,
                "options": {"num_predict": 4096},
            }
            resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
            resp.raise_for_status()
            conteudo = resp.json()["message"]["content"]

            try:
                dados = json.loads(conteudo)
                return schema.model_validate(dados)
            except (json.JSONDecodeError, ValidationError) as e:
                log.warning(
                    "ollama.json_invalido",
                    extra={"dados": {"tentativa": tentativa + 1, "erro": str(e)}},
                )
                if tentativa == 0:
                    user = (
                        f"{user}\n\nSua resposta anterior continha JSON inválido: {e}\n"
                        f"Corrija e retorne APENAS o JSON válido conforme o schema."
                    )

        raise AnalyseDegradadaError(
            "Ollama retornou JSON inválido após 2 tentativas.", provider=self.nome
        )

    def esta_disponivel(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
