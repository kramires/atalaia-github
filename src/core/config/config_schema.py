"""Schemas Pydantic v2 para config.yaml + .env (ARCHITECTURE §7.1)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SchedulerConfig(BaseModel):
    intervalo_minutos: int = 60
    ativo: bool = True
    timezone: str = "America/Sao_Paulo"


class JanelaConfig(BaseModel):
    dias: int = 90
    hard_cap_ciclo: int = 100


class RelevanciaConfig(BaseModel):
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    keywords_criticas: list[str] = Field(default_factory=list)
    keywords_primarias: list[str] = Field(default_factory=list)
    keywords_secundarias: list[str] = Field(default_factory=list)


class ProvidersConfig(BaseModel):
    analise: str = "balanceado"          # openai (primário) + deepseek (secundário)
    briefing_p1: str = "balanceado"
    briefing_p2: str = "balanceado"


class AnthropicConfig(BaseModel):
    modelo: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    temperature: float = 0.3


class OpenAIConfig(BaseModel):
    modelo: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.3


class DeepSeekConfig(BaseModel):
    modelo: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.3
    base_url: str = "https://api.deepseek.com"


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    modelo: str = "llama3.1"
    max_tokens: int = 4096


class ReactLoopConfig(BaseModel):
    max_iteracoes: int = 6
    timeout_tool_segundos: int = 60
    max_tokens_contexto: int = 40_000


class DatabaseConfig(BaseModel):
    caminho: str = "data/atalaia.db"


class DashboardConfig(BaseModel):
    saida_padrao: str = "output/dashboards"
    max_arquivos_retidos: int = 30


class BriefingsConfig(BaseModel):
    saida_padrao: str = "output/briefings"


class ColetaConfig(BaseModel):
    timeout_http_segundos: int = 30
    max_chars_item: int = 8_000
    google_news_rate_limit_min: int = 15
    user_agent: str = "ATALAIA-ComSoc/1.0"


class CircuitBreakerConfig(BaseModel):
    falhas_para_abrir: int = 3
    timeout_reset_segundos: int = 120


class ObservabilidadeConfig(BaseModel):
    nivel_log: str = "INFO"
    dir_logs: str = "logs"
    retencao_dias: int = 30


class FonteConfig(BaseModel):
    id: str
    nome: str
    tipo: str
    url: str | None = None
    queries: list[str] = Field(default_factory=list)
    ativo: bool = True
    trust_score: float = Field(default=0.7, ge=0.0, le=1.0)
    intervalo_minutos: int | None = None


class SistemaConfig(BaseModel):
    nome: str = "ATALAIA ComSoc"
    queries_google_news: list[str] = Field(default_factory=lambda: [
        "Exército Brasileiro",
        "Forças Armadas",
        "Comando do Exército",
        "Ministério da Defesa",
    ])


class ConfigSchema(BaseModel):
    sistema: SistemaConfig = Field(default_factory=SistemaConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    janela: JanelaConfig = Field(default_factory=JanelaConfig)
    relevancia: RelevanciaConfig = Field(default_factory=RelevanciaConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    deepseek: DeepSeekConfig = Field(default_factory=DeepSeekConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    react_loop: ReactLoopConfig = Field(default_factory=ReactLoopConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    briefings: BriefingsConfig = Field(default_factory=BriefingsConfig)
    coleta: ColetaConfig = Field(default_factory=ColetaConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    observabilidade: ObservabilidadeConfig = Field(default_factory=ObservabilidadeConfig)
    fontes: list[FonteConfig] = Field(default_factory=list)
