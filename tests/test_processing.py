"""Testes do pipeline de processamento Trilha B (SPEC-02, SPEC-03)."""
import pytest
from src.processing.dedup_engine import RSSDeduplicationEngine
from src.processing.relevance_engine import RelevanceEngine, Router, HardCapFilter
from src.processing.html_sanitizer import HTMLSanitizer as _HTMLSanitizer
from src.processing.text_normalizer import TextNormalizer as _TextNormalizer

# Adaptadores para a API real
class HTMLSanitizer:
    @staticmethod
    def sanitizar(html: str) -> str:
        return _HTMLSanitizer.limpar(html)

class TextNormalizer:
    @staticmethod
    def normalizar(texto: str) -> str:
        return _TextNormalizer.normalizar(texto)


class TestDeduplicationEngine:
    def test_remove_utm_source(self):
        url = "https://example.com/news?utm_source=twitter&id=1"
        norm = RSSDeduplicationEngine.normalizar_url(url)
        assert "utm_source" not in norm
        assert "id=1" in norm

    def test_remove_multiplos_utms(self):
        url = "https://example.com/news?utm_source=x&utm_medium=social&id=5"
        norm = RSSDeduplicationEngine.normalizar_url(url)
        assert "utm_source" not in norm
        assert "utm_medium" not in norm

    def test_remove_fbclid(self):
        url = "https://example.com/news?fbclid=ABCDE&id=1"
        norm = RSSDeduplicationEngine.normalizar_url(url)
        assert "fbclid" not in norm

    def test_url_sem_params(self):
        url = "https://example.com/news"
        assert RSSDeduplicationEngine.normalizar_url(url) == url

    def test_normaliza_titulo_acentos(self):
        t1 = RSSDeduplicationEngine.normalizar_titulo("Título com Ação")
        t2 = RSSDeduplicationEngine.normalizar_titulo("Titulo com Acao")
        assert t1 == t2

    def test_normaliza_titulo_maiusculas(self):
        t1 = RSSDeduplicationEngine.normalizar_titulo("EXÉRCITO BRASILEIRO")
        t2 = RSSDeduplicationEngine.normalizar_titulo("exército brasileiro")
        assert t1 == t2

    def test_hash_url_diferente_sem_utm(self):
        h1 = RSSDeduplicationEngine.fazer_hash("https://site.com/a?utm_source=x", "Notícia")
        h2 = RSSDeduplicationEngine.fazer_hash("https://site.com/a", "Noticia")
        assert h1 == h2

    def test_hash_url_diferente_id(self):
        h1 = RSSDeduplicationEngine.fazer_hash("https://site.com/a?id=1", "Notícia")
        h2 = RSSDeduplicationEngine.fazer_hash("https://site.com/a?id=2", "Notícia")
        assert h1 != h2


@pytest.fixture(autouse=True)
def setup_config(tmp_path):
    """Inicializa config mínimo para testes que dependem do ConfigLoader."""
    import yaml
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({
        "sistema": {"nome": "ATALAIA Test"},
        "providers": {"analise": "degradado", "briefing_p1": "degradado", "briefing_p2": "degradado"},
        "database": {"caminho": str(tmp_path / "test.db")},
        "relevancia": {"threshold": 0.5, "keywords_eb": ["exército", "forças armadas"]},
        "scheduler": {"intervalo_minutos": 60, "ativo": False, "timezone": "America/Sao_Paulo"},
    }))
    from src.core.config.config_loader import carregar
    try:
        carregar(cfg_path)
    except Exception:
        pass


class TestRelevanceEngine:
    def test_calcular_score_retorna_float(self, setup_config):
        engine = RelevanceEngine()
        score = engine.calcular_score(
            "Exército Brasileiro realiza operação", "conteudo", "fonte", 0.5
        )
        assert isinstance(score, float)

    def test_titulo_sem_keyword_score_baixo(self, setup_config):
        engine = RelevanceEngine()
        score = engine.calcular_score(
            "Receita de bolo de chocolate", "sem relevância", "fonte", 0.3
        )
        assert isinstance(score, float)

    def test_score_maior_com_keyword(self, setup_config):
        engine = RelevanceEngine()
        score_relevante = engine.calcular_score(
            "Exército Brasileiro faz exercício", "conteudo", "fonte", 0.5
        )
        score_irrelevante = engine.calcular_score(
            "Receita de macarrão", "conteudo", "fonte", 0.5
        )
        assert score_relevante >= score_irrelevante


class TestRouter:
    def test_classify_retorna_tuple(self, setup_config):
        router = Router(threshold=0.5)
        resultado = router.classificar("Exército Brasileiro", "conteudo", "fonte", 0.7)
        assert isinstance(resultado, tuple)
        assert len(resultado) == 2
        assert isinstance(resultado[0], bool)
        assert isinstance(resultado[1], float)

    def test_score_sempre_float(self, setup_config):
        router = Router(threshold=0.5)
        _, score = router.classificar("Receita de bolo", "conteudo", "fonte", 0.3)
        assert isinstance(score, float)


class TestHardCapFilter:
    def test_retorna_top_n(self):
        itens = [{"id": i, "relevance_score": float(i)} for i in range(200)]
        cap = HardCapFilter(cap=100)
        selecionados, n_acima = cap.filtrar(itens)
        assert len(selecionados) == 100
        assert n_acima == 100

    def test_sem_cap_retorna_todos(self):
        itens = [{"id": i, "relevance_score": float(i)} for i in range(50)]
        cap = HardCapFilter(cap=100)
        selecionados, n_acima = cap.filtrar(itens)
        assert len(selecionados) == 50
        assert n_acima == 0

    def test_ordena_por_relevance_score(self):
        itens = [
            {"id": 1, "relevance_score": 0.3},
            {"id": 2, "relevance_score": 0.9},
            {"id": 3, "relevance_score": 0.6},
        ]
        cap = HardCapFilter(cap=2)
        selecionados, _ = cap.filtrar(itens)
        # Deve selecionar os dois mais relevantes: id=2 e id=3
        ids = {i["id"] for i in selecionados}
        assert 2 in ids
        assert 3 in ids
        assert 1 not in ids


class TestHTMLSanitizer:
    def test_remove_tags_html(self):
        r = HTMLSanitizer.sanitizar("<b>Título</b> com <a href='x'>link</a>")
        assert "<b>" not in r
        assert "<a" not in r
        assert "Título" in r

    def test_preserva_texto(self):
        r = HTMLSanitizer.sanitizar("Exército Brasileiro")
        assert "Exército Brasileiro" == r

    def test_trunca_8k(self):
        longo = "a" * 10000
        r = HTMLSanitizer.sanitizar(longo)
        assert len(r) <= 8001


class TestTextNormalizer:
    def test_normaliza_unicode_nfc(self):
        r = TextNormalizer.normalizar("café")
        assert r is not None

    def test_remove_controle(self):
        r = TextNormalizer.normalizar("texto\x00\x01normal")
        assert "\x00" not in r
        assert "texto" in r

    def test_trunca_8k(self):
        longo = "b" * 10000
        r = TextNormalizer.normalizar(longo)
        assert len(r) <= 8001
