"""Hierarquia de exceções do ATALAIA ComSoc (SPEC-15 §2)."""


class AtalaiaError(Exception):
    """Base de todas as exceções do ATALAIA."""


class ConfigValidationError(AtalaiaError):
    """Configuração inválida — impede startup."""


class DatabaseError(AtalaiaError):
    """Erro de banco — impede operação."""


class IngestaoError(AtalaiaError):
    """Erro de ingestão — não fatal; o ciclo continua."""


class PerfilNaoReconhecidoError(IngestaoError):
    """Nenhum perfil de planilha reconheceu o layout."""


class ColetorIndisponivelError(IngestaoError):
    """Coletor RSS ou API inacessível."""


class AnalyseDegradadaError(AtalaiaError):
    """LLM não produziu resposta estruturada válida após retentativas."""

    def __init__(self, motivo: str, provider: str = "desconhecido"):
        self.motivo = motivo
        self.provider = provider
        super().__init__(f"[{provider}] {motivo}")


class ToolNaoEncontradaError(AtalaiaError):
    """Tool solicitada pelo AgentLoop não está registrada."""


class ToolTimeoutError(AtalaiaError):
    """Execução de tool excedeu o timeout configurado."""


class DashboardRenderError(AtalaiaError):
    """Falha ao renderizar ou salvar o dashboard HTML."""


class BriefingRenderError(AtalaiaError):
    """Falha ao renderizar o briefing."""


class ExportError(AtalaiaError):
    """Falha ao exportar dados."""
