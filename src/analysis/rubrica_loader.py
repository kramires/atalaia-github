"""RubricaLoader — carrega rubrica de sentimento do YAML + banco (SPEC-05 §6)."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


class RubricaLoader:
    def __init__(self, caminho_yaml: Path = Path("config/rubrica_sentimento.yaml")) -> None:
        self.caminho = caminho_yaml

    def carregar(self) -> dict:
        """Carrega rubrica YAML. Retorna dict com exemplos e critérios."""
        if not self.caminho.exists():
            log.warning("rubrica.nao_encontrada", extra={"dados": {"caminho": str(self.caminho)}})
            return self._rubrica_padrao()

        try:
            dados = yaml.safe_load(self.caminho.read_text(encoding="utf-8")) or {}
            return dados
        except Exception as e:
            log.error("rubrica.erro_carregamento", extra={"dados": {"erro": str(e)}})
            return self._rubrica_padrao()

    @staticmethod
    def _rubrica_padrao() -> dict:
        """Rubrica mínima quando arquivo não existe."""
        return {
            "positiva": {
                "criterios": [
                    "Uso de linguagem elogiosa ou favorável",
                    "Resultados positivos anunciados",
                    "Sucesso operacional relatado",
                ],
                "exemplos": [
                    "Exército alcança sucesso em operação",
                    "Tropa demonstra excelência",
                ],
            },
            "negativa": {
                "criterios": [
                    "Crítica explícita à instituição",
                    "Relato de fracasso ou problema",
                    "Linguagem desfavorável",
                ],
                "exemplos": [
                    "Soldado preso por crimes",
                    "Equipamento danificado em operação",
                ],
            },
            "neutra": {
                "criterios": [
                    "Relato factual sem juízo",
                    "Informação sem carga emocional",
                    "Notícia que afeta a instituição mas é neutra",
                ],
                "exemplos": [
                    "Exército abre inscrições para concurso",
                    "Quartel é aberto para visitação",
                ],
            },
        }
