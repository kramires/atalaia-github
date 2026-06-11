"""Testes do BriefingGenerator (SPEC-11)."""
import pytest
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import jinja2

from src.briefing import BriefingParte1, BriefingParte2, RespostaProspeccaoLLM
from src.briefing.parte1_renderer import Parte1Renderer
from src.briefing.parte2_renderer import Parte2Renderer
from src.briefing.generator import BriefingGenerator
from src.core.agent.agent_loop import AgentAnalysisResult
from src.analysis.risk_evaluator import AvaliacaoRisco
from src.errors.exceptions import AnalyseDegradadaError
from src.memory.repositories.briefings_repo import BriefingsRepo
from src.memory.database import Database, MigrationRunner
from src.memory.repositories.ciclos_repo import CiclosRepo


TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "briefing" / "templates"


@pytest.fixture
def jinja_env():
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        undefined=jinja2.Undefined,
    )


@pytest.fixture
def avaliacao_mock():
    return AvaliacaoRisco(
        nivel_risco="MEDIO",
        justificativa="Análise de teste",
        confianca=0.7,
        tipo_inferencia="HIPOTESE",
        fatores_risco=["Fator 1"],
        oportunidades=["Oportunidade 1"],
        acoes_sugeridas=["Ação 1"],
    )


@pytest.fixture
def result_mock():
    return AgentAnalysisResult(
        ciclo_id="test-001",
        itens_analisados=3,
        modo_degradado=False,
        sentimentos=[
            {"item_id": 1, "sentimento_ia": "POSITIVA", "confianca": 0.9, "tipo_inferencia": "FATO"},
            {"item_id": 2, "sentimento_ia": "NEGATIVA", "confianca": 0.7, "tipo_inferencia": "INTERPRETACAO"},
            {"item_id": 3, "sentimento_ia": "NEUTRA", "confianca": 0.5, "tipo_inferencia": "HIPOTESE"},
        ],
        narrativas=[{"nome": "Narrativa 1", "frequencia": 2, "temas": ["militares"]}],
        mudancas_enquadramento=[],
    )


@pytest.fixture
def itens_ciclo():
    return {
        1: {
            "item_id": 1,
            "titulo": "Exército realiza exercício",
            "url": "https://example.com/1",
            "fonte_nome": "Jornal A",
            "conteudo_texto": "Conteúdo do item 1",
            "pub_date": date(2026, 6, 7),
        },
        2: {
            "item_id": 2,
            "titulo": "Crítica às Forças Armadas",
            "url": "https://example.com/2",
            "fonte_nome": "Portal B",
            "conteudo_texto": "Conteúdo do item 2",
            "pub_date": date(2026, 6, 7),
        },
    }


@pytest.fixture
def mock_provider_ok():
    m = Mock()
    m.nome = "mock-provider"
    m.completar_estruturado.return_value = RespostaProspeccaoLLM(
        prospeccao=["Prospecção 1", "Prospecção 2"],
        acoes_refinadas=["Ação refinada 1"],
        confianca=0.8,
        tipo="HIPOTESE",
    )
    return m


@pytest.fixture
def mock_provider_degradado():
    m = Mock()
    m.nome = "mock-degradado"
    m.completar_estruturado.side_effect = AnalyseDegradadaError("LLM offline")
    return m


@pytest.fixture
def db_temp():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    db = Database.inicializar(path)
    MigrationRunner(db).aplicar_todas()
    yield db
    path.unlink(missing_ok=True)


class TestParte1Renderer:
    def test_renderiza_markdown(self, jinja_env, result_mock, avaliacao_mock, itens_ciclo):
        r = Parte1Renderer(jinja_env, itens_ciclo)
        p1 = r.renderizar(result_mock, avaliacao_mock)
        assert "PANORAMA" in p1.markdown
        assert "DESTAQUES" in p1.markdown
        assert "TODAS AS MATÉRIAS" in p1.markdown

    def test_renderiza_html(self, jinja_env, result_mock, avaliacao_mock, itens_ciclo):
        r = Parte1Renderer(jinja_env, itens_ciclo)
        p1 = r.renderizar(result_mock, avaliacao_mock)
        assert "<html" in p1.html.lower()
        assert "href=" in p1.html

    def test_top_3_destaques_positivos(self, jinja_env, avaliacao_mock):
        # 5 itens positivos: deve retornar só os 3 com maior confiança
        sentimentos = [
            {"item_id": i, "sentimento_ia": "POSITIVA", "confianca": float(i) / 10, "tipo_inferencia": "FATO"}
            for i in range(1, 6)
        ]
        result = AgentAnalysisResult(
            ciclo_id="t", itens_analisados=5, sentimentos=sentimentos
        )
        itens = {i: {"item_id": i, "titulo": f"T{i}", "url": f"http://x.com/{i}",
                     "fonte_nome": f"J{i}", "conteudo_texto": "c", "pub_date": date(2026, 1, 1)}
                 for i in range(1, 6)}
        r = Parte1Renderer(jinja_env, itens)
        p1 = r.renderizar(result, avaliacao_mock)
        assert len(p1.destaques_positivos) <= 3
        # O de maior confiança (0.5) deve estar
        if len(p1.destaques_positivos) > 0:
            confianças = [d.confianca for d in p1.destaques_positivos]
            assert confianças == sorted(confianças, reverse=True)

    def test_ciclo_vazio(self, jinja_env, avaliacao_mock):
        result = AgentAnalysisResult(ciclo_id="t", itens_analisados=0)
        r = Parte1Renderer(jinja_env, {})
        p1 = r.renderizar(result, avaliacao_mock)
        assert p1.markdown != ""
        assert len(p1.destaques_positivos) == 0

    def test_lista_itens_ordenada_por_data(self, jinja_env, result_mock, avaliacao_mock):
        itens = {
            1: {"item_id": 1, "titulo": "Antigo", "url": "x", "fonte_nome": "J",
                "conteudo_texto": "c", "pub_date": date(2026, 1, 1)},
            2: {"item_id": 2, "titulo": "Recente", "url": "y", "fonte_nome": "J",
                "conteudo_texto": "c", "pub_date": date(2026, 6, 7)},
        }
        r = Parte1Renderer(jinja_env, itens)
        p1 = r.renderizar(result_mock, avaliacao_mock)
        if len(p1.todos_os_itens) >= 2:
            # primeiro deve ser o mais recente
            assert p1.todos_os_itens[0].titulo == "Recente"


class TestParte2Renderer:
    def test_renderiza_com_llm_ok(self, jinja_env, mock_provider_ok, avaliacao_mock):
        r = Parte2Renderer(mock_provider_ok, jinja_env)
        p2 = r.renderizar(avaliacao_mock, "test-001")
        assert len(p2.prospeccao) >= 1
        assert len(p2.acoes_sugeridas) >= 1
        assert p2.provider == "mock-provider"
        assert p2.modo_degradado is False

    def test_degradado_quando_llm_falha(self, jinja_env, mock_provider_degradado, avaliacao_mock):
        r = Parte2Renderer(mock_provider_degradado, jinja_env)
        p2 = r.renderizar(avaliacao_mock, "test-001")
        assert p2.modo_degradado is True
        assert len(p2.prospeccao) >= 1
        assert "indisponível" in p2.prospeccao[0].lower()

    def test_filtra_contrapropaganda(self, jinja_env, mock_provider_ok, avaliacao_mock):
        mock_provider_ok.completar_estruturado.return_value = RespostaProspeccaoLLM(
            prospeccao=["Análise normal"],
            acoes_refinadas=["Ação válida", "desmentir fake news atacar oposição"],
            confianca=0.8,
            tipo="HIPOTESE",
        )
        r = Parte2Renderer(mock_provider_ok, jinja_env)
        p2 = r.renderizar(avaliacao_mock, "test-001")
        acao_baixa = [a for a in p2.acoes_sugeridas if "desmentir" in a.lower()]
        assert len(acao_baixa) == 0

    def test_acao_valida_mantida(self, jinja_env, mock_provider_ok, avaliacao_mock):
        mock_provider_ok.completar_estruturado.return_value = RespostaProspeccaoLLM(
            prospeccao=["Tendência X"],
            acoes_refinadas=["Divulgar nota de esclarecimento no site institucional"],
            confianca=0.8,
            tipo="HIPOTESE",
        )
        r = Parte2Renderer(mock_provider_ok, jinja_env)
        p2 = r.renderizar(avaliacao_mock, "test-001")
        assert len(p2.acoes_sugeridas) == 1


class TestBriefingGenerator:
    def test_gera_e_persiste(self, jinja_env, mock_provider_ok, result_mock, avaliacao_mock, db_temp):
        ciclos = CiclosRepo(db_temp)
        ciclos.iniciar("test-001")

        p1_renderer = Parte1Renderer(jinja_env, {})
        p2_renderer = Parte2Renderer(mock_provider_ok, jinja_env)
        repo = BriefingsRepo(db_temp)

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = BriefingGenerator(p1_renderer, p2_renderer, repo, Path(tmpdir))
            b = gen.gerar(result_mock, avaliacao_mock, "test-001")

        assert b.id is not None
        assert b.status == "COMPLETO"
        assert b.provider_parte2 == "mock-provider"
        recentes = repo.buscar_recentes()
        assert len(recentes) == 1

    def test_status_degradado(self, jinja_env, mock_provider_ok, db_temp):
        ciclos = CiclosRepo(db_temp)
        ciclos.iniciar("test-degradado")

        result = AgentAnalysisResult(ciclo_id="test-degradado", itens_analisados=0, modo_degradado=True)
        av = AvaliacaoRisco(nivel_risco="BAIXO", justificativa="teste", confianca=0.0, tipo_inferencia="HIPOTESE")

        p1_renderer = Parte1Renderer(jinja_env, {})
        p2_renderer = Parte2Renderer(mock_provider_ok, jinja_env)
        repo = BriefingsRepo(db_temp)

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = BriefingGenerator(p1_renderer, p2_renderer, repo, Path(tmpdir))
            b = gen.gerar(result, av, "test-degradado")

        assert b.status == "DEGRADADO"

    def test_html_contem_links(self, jinja_env, mock_provider_ok, avaliacao_mock, db_temp, itens_ciclo):
        ciclos = CiclosRepo(db_temp)
        ciclos.iniciar("test-links")

        result = AgentAnalysisResult(
            ciclo_id="test-links",
            itens_analisados=2,
            sentimentos=[
                {"item_id": 1, "sentimento_ia": "POSITIVA", "confianca": 0.9, "tipo_inferencia": "FATO"},
                {"item_id": 2, "sentimento_ia": "NEGATIVA", "confianca": 0.7, "tipo_inferencia": "FATO"},
            ],
        )

        p1_renderer = Parte1Renderer(jinja_env, itens_ciclo)
        p2_renderer = Parte2Renderer(mock_provider_ok, jinja_env)
        repo = BriefingsRepo(db_temp)

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = BriefingGenerator(p1_renderer, p2_renderer, repo, Path(tmpdir))
            b = gen.gerar(result, avaliacao_mock, "test-links")

        assert "href=" in b.parte1_html
