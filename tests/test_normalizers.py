"""Testes dos normalizadores do ETL CCOMSEx (SPEC-01)."""
import pytest
from src.intake.ccomsex.normalizers import br_number, norm_sentiment, make_hash, e_linha_rodape


class TestBrNumber:
    def test_virgula_como_decimal(self):
        assert br_number("1.234,56") == pytest.approx(1234.56)

    def test_apenas_virgula(self):
        assert br_number("32058,00") == pytest.approx(32058.0)

    def test_ponto_milhar_3_digitos(self):
        assert br_number("12.000") == pytest.approx(12000.0)
        assert br_number("1.200") == pytest.approx(1200.0)

    def test_ponto_decimal_nao_3_digitos(self):
        assert br_number("1.5") == pytest.approx(1.5)
        assert br_number("32058.0") == pytest.approx(32058.0)

    def test_inteiro_python(self):
        assert br_number(100) == pytest.approx(100.0)

    def test_float_python(self):
        assert br_number(3.14) == pytest.approx(3.14)

    def test_none(self):
        assert br_number(None) is None

    def test_string_vazia(self):
        assert br_number("") is None

    def test_valor_simples_sem_separador(self):
        assert br_number("500") == pytest.approx(500.0)


class TestNormSentiment:
    def test_positiva(self):
        assert norm_sentiment("POSITIVA") == "POSITIVA"
        assert norm_sentiment("positiva") == "POSITIVA"
        assert norm_sentiment("Favorável") == "POSITIVA"

    def test_negativa_antes_de_positiva(self):
        # "Desfavorável" contém "FAVORAV" → deve retornar NEGATIVA, não POSITIVA
        assert norm_sentiment("Desfavorável") == "NEGATIVA"
        assert norm_sentiment("NEGATIVA") == "NEGATIVA"

    def test_neutra(self):
        assert norm_sentiment("NEUTRA") == "NEUTRA"
        assert norm_sentiment("neutra") == "NEUTRA"

    def test_na_quando_desconhecido(self):
        assert norm_sentiment("") == "NA"
        assert norm_sentiment(None) == "NA"
        assert norm_sentiment("OUTRO") == "NA"


class TestMakeHash:
    def test_hash_consistente(self):
        row = {"titulo": "Teste", "veiculo": "Jornal", "data_raw": "01/01/2026", "link_original": ""}
        assert make_hash(row) == make_hash(row)

    def test_hash_diferente_para_titulos_diferentes(self):
        row1 = {"titulo": "A", "veiculo": "", "data_raw": "", "link_original": ""}
        row2 = {"titulo": "B", "veiculo": "", "data_raw": "", "link_original": ""}
        assert make_hash(row1) != make_hash(row2)

    def test_hash_case_insensitive(self):
        row1 = {"titulo": "TESTE", "veiculo": "JORNAL", "data_raw": "", "link_original": ""}
        row2 = {"titulo": "teste", "veiculo": "jornal", "data_raw": "", "link_original": ""}
        assert make_hash(row1) == make_hash(row2)


class TestELinhaRodape:
    def test_total_geral(self):
        # A função usa norm_header(titulo) internamente para comparar com "total geral"
        assert e_linha_rodape({"titulo": "Total Geral", "veiculo": "", "data_raw": ""})

    def test_linha_normal_nao_rodape(self):
        assert not e_linha_rodape({"titulo": "Materia sobre total geral", "veiculo": "Jornal", "data_raw": "01/01/2026"})

    def test_linha_vazia_com_valores(self):
        assert e_linha_rodape({"titulo": "", "veiculo": "", "data_raw": "", "valor": 100.0})
