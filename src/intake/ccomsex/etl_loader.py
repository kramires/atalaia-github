"""ETLLoader — Trilha A CCOMSEx (SPEC-01 §8)."""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.errors.exceptions import PerfilNaoReconhecidoError
from src.intake.ccomsex.normalizers import (
    br_number,
    e_linha_rodape,
    make_hash,
    norm_sentiment,
    parse_date,
    split_assuntos,
)
from src.intake.ccomsex.perfis.registry import PerfilPlanilhaRegistry
from src.memory.database import Database, MigrationRunner
from src.memory.repositories.items_repo import ItemsRepo

log = logging.getLogger(__name__)

TEXT_COLS = [
    "titulo", "url_clip", "link_original", "tipo", "veiculo",
    "editoria", "mesorregiao", "uf", "municipio", "abrangencia", "pais",
    "midia", "espaco", "categoria", "maps", "tag_veiculo",
    "analise_qualitativa", "incluir_analise", "assunto",
]
NUM_COLS = ["cm", "seg", "valor", "publico"]


@dataclass
class EstatisticasArquivo:
    nome_arquivo: str
    inseridos: int = 0
    duplicados: int = 0
    erros: int = 0


@dataclass
class ResultadoETL:
    arquivos_processados: int = 0
    inseridos_total: int = 0
    duplicados_total: int = 0
    erros_total: int = 0
    total_no_banco: int = 0
    distribuicao_sentimento: dict[str, int] = field(default_factory=dict)
    top_veiculos: list[tuple[str, int]] = field(default_factory=list)
    por_arquivo: list[EstatisticasArquivo] = field(default_factory=list)


def _ler_planilha(path: Path) -> pd.DataFrame | None:
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    try:
        return pd.read_excel(path, engine=engine, dtype=str)
    except Exception as e:
        log.warning("etl.erro_leitura", extra={"dados": {"arquivo": path.name, "erro": str(e)}})
        return None


class ETLLoader:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = ItemsRepo(db)

    def processar(self, entrada: Path, glob: str = "*.xls*") -> ResultadoETL:
        if entrada.is_dir():
            arquivos = sorted(entrada.glob(glob))
        elif entrada.is_file():
            arquivos = [entrada]
        else:
            log.warning("etl.entrada_invalida", extra={"dados": {"caminho": str(entrada)}})
            return ResultadoETL()

        resultado = ResultadoETL()
        for arquivo in arquivos:
            stats = self._processar_arquivo(arquivo)
            resultado.por_arquivo.append(stats)
            resultado.inseridos_total += stats.inseridos
            resultado.duplicados_total += stats.duplicados
            resultado.erros_total += stats.erros
            resultado.arquivos_processados += 1

        resultado.total_no_banco = self._repo.contar(fonte_trilha="A")
        resultado.distribuicao_sentimento = self._distribuicao_sentimento()
        resultado.top_veiculos = self._top_veiculos()

        log.info(
            "etl.concluido",
            extra={
                "dados": {
                    "inseridos": resultado.inseridos_total,
                    "duplicados": resultado.duplicados_total,
                    "total_banco": resultado.total_no_banco,
                }
            },
        )
        return resultado

    def _processar_arquivo(self, path: Path) -> EstatisticasArquivo:
        stats = EstatisticasArquivo(nome_arquivo=path.name)
        log.info("etl.iniciando", extra={"dados": {"arquivo": path.name}})

        df = _ler_planilha(path)
        if df is None:
            stats.erros = 1
            return stats

        if df.empty:
            log.info("etl.planilha_vazia", extra={"dados": {"arquivo": path.name}})
            return stats

        try:
            perfil = PerfilPlanilhaRegistry.detectar_perfil(df)
        except PerfilNaoReconhecidoError as e:
            log.warning("etl.perfil_nao_reconhecido", extra={"dados": {"arquivo": path.name, "erro": str(e)}})
            stats.erros = 1
            return stats

        df = perfil.mapear(df)

        for _, raw in df.iterrows():
            row: dict = {}
            row["data_raw"] = str(raw.get("data", "")).strip() if "data" in raw else ""

            for tc in TEXT_COLS:
                row[tc] = str(raw.get(tc, "")).strip() if tc in raw else ""

            for nc in NUM_COLS:
                row[nc] = br_number(raw.get(nc)) if nc in raw else None

            row["data_pub"] = parse_date(raw.get("data"))
            row["sentimento"] = norm_sentiment(raw.get("analise_qualitativa"))
            row["content_hash"] = make_hash(row)
            row["fonte_trilha"] = "A"
            row["source_file"] = path.name
            row["ingested_at"] = datetime.now(timezone.utc).isoformat()

            if not row["titulo"]:
                continue

            if e_linha_rodape(row):
                log.debug(
                    "linha.rodape.descartada",
                    extra={"dados": {"titulo": row["titulo"][:60], "arquivo": path.name}},
                )
                continue

            resultado = self._repo.inserir_ccomsex(row)
            if resultado.duplicado:
                stats.duplicados += 1
            else:
                stats.inseridos += 1
                if resultado.item_id and row.get("assunto"):
                    assuntos = split_assuntos(raw.get("assunto"))
                    if assuntos:
                        self._repo.inserir_assuntos(resultado.item_id, assuntos)

        self._db.commit()
        log.info(
            "etl.arquivo_concluido",
            extra={"dados": {"arquivo": path.name, "inseridos": stats.inseridos, "duplicados": stats.duplicados}},
        )
        return stats

    def _distribuicao_sentimento(self) -> dict[str, int]:
        rows = self._db.executar(
            "SELECT sentimento, COUNT(*) AS n FROM items WHERE fonte_trilha='A' GROUP BY sentimento ORDER BY 2 DESC"
        ).fetchall()
        return {r["sentimento"]: r["n"] for r in rows}

    def _top_veiculos(self, limite: int = 5) -> list[tuple[str, int]]:
        rows = self._db.executar(
            "SELECT veiculo, COUNT(*) AS n FROM items WHERE fonte_trilha='A' AND veiculo != '' "
            "GROUP BY veiculo ORDER BY 2 DESC LIMIT ?",
            (limite,),
        ).fetchall()
        return [(r["veiculo"], r["n"]) for r in rows]


def _imprimir_resumo(resultado: ResultadoETL) -> None:
    print(f"\n--- RESUMO ---")
    print(f"Arquivos processados:  {resultado.arquivos_processados}")
    print(f"Inseridos:             {resultado.inseridos_total}")
    print(f"Duplicados ignorados:  {resultado.duplicados_total}")
    print(f"Total no banco:        {resultado.total_no_banco}")
    print("\nSentimento (baseline CCOMSEx):")
    for sent, n in resultado.distribuicao_sentimento.items():
        print(f"  {sent:10} {n}")
    print("\nTop 5 veículos:")
    for v, n in resultado.top_veiculos:
        print(f"  {n:4}  {v}")


def main() -> None:
    ap = argparse.ArgumentParser(description="ETL CCOMSEx → SQLite")
    ap.add_argument("entrada", help="arquivo .xls/.xlsx ou pasta com planilhas")
    ap.add_argument("--db", default="data/atalaia.db", help="caminho do SQLite")
    ap.add_argument("--glob", default="*.xls*")
    args = ap.parse_args()

    entrada = Path(args.entrada)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database.inicializar(db_path)
    MigrationRunner(db).aplicar_todas()

    resultado = ETLLoader(db).processar(entrada, args.glob)
    _imprimir_resumo(resultado)


if __name__ == "__main__":
    main()
