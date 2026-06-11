#!/usr/bin/env python3
"""ATALAIA ComSoc — CLI principal (IMPLEMENTACAO_PROMPT.md)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.core.config.config_loader import carregar
from src.core.lifecycle.cycle_manager import CicloManager
from src.memory.database import Database, MigrationRunner
from src.observability.logger import configurar_logger


def setup_logging(config) -> None:
    """Configura logger estruturado JSON."""
    nivel = config.observabilidade.nivel_log
    dir_logs = Path(config.observabilidade.dir_logs)
    configurar_logger(nivel, dir_logs)


def cmd_etl(args) -> None:
    """Executa ETL CCOMSEx."""
    from src.intake.ccomsex.etl_loader import ETLLoader

    db = Database.inicializar(Path(args.db))
    MigrationRunner(db).aplicar_todas()

    entrada = Path(args.entrada)
    resultado = ETLLoader(db).processar(entrada, args.glob)

    print(f"\nInseridos: {resultado.inseridos_total}")
    print(f"Duplicados: {resultado.duplicados_total}")
    print(f"Total no banco: {resultado.total_no_banco}")


def cmd_run(args) -> None:
    """Executa um ciclo da Trilha B."""
    import src.core.config.config_loader as _cfg_mod
    _cfg_mod._instancia = None          # garante reload do config
    Database._instance = None           # garante DB do config, não de testes

    config = carregar(Path("config/config.yaml"))
    setup_logging(config)

    db = Database.inicializar(Path(config.database.caminho))
    MigrationRunner(db).aplicar_todas()

    manager = CicloManager(db, config.react_loop.model_dump())
    resultado = manager.executar_ciclo()

    print(f"\nCiclo: {resultado['ciclo_id']}")
    print(f"Status: {resultado['status']}")
    if resultado["status"] == "COMPLETO":
        print(f"Coletados: {resultado['coletados']}")
        print(f"Relevantes: {resultado['relevantes']}")
        print(f"Analisados: {resultado['analisados']}")


def cmd_health(args) -> None:
    """Verifica saúde do sistema."""
    config = carregar(Path("config/config.yaml"))
    db = Database.inicializar(Path(config.database.caminho))

    from src.observability.health_check import HealthCheck
    from src.providers.factory import ProviderFactory

    factory = ProviderFactory(config)
    health = HealthCheck(db, [], factory)
    status = health.verificar()

    print("\n=== HEALTH CHECK ===")
    print(f"Banco: {'OK' if status['banco']['ok'] else 'ERRO'}")
    print(f"LLM:   {'OK' if status['llm']['ok'] else 'ERRO'}")
    print(f"Disco: {'OK' if status['disco']['ok'] else 'ERRO'}")


def cmd_dashboard(args) -> None:
    """Gera dashboard HTML autocontido."""
    from src.dashboard.generator import DashboardHTMLGenerator
    from src.memory.repositories.items_repo import ItemsRepo
    from src.memory.repositories.rollups_repo import RollupsRepo

    db = Database.inicializar(Path(args.db))
    MigrationRunner(db).aplicar_todas()

    janela = getattr(args, "janela", 90)
    gen = DashboardHTMLGenerator(
        db=db,
        rollups_repo=RollupsRepo(db),
        items_repo=ItemsRepo(db),
        janela_dias=janela,
    )
    destino = gen.gerar(Path(args.out))
    n = ItemsRepo(db).contar()
    print(f"Dashboard gerado: {destino}  ({n} itens no banco)")


def cmd_export(args) -> None:
    """Exporta dados em xlsx/csv/json."""
    from src.export.manager import ExportManager

    db = Database.inicializar(Path(args.db))
    MigrationRunner(db).aplicar_todas()

    manager = ExportManager(db)
    n = manager.exportar(
        formato=args.formato,
        destino=Path(args.out),
        trilha=args.trilha,
        desde=getattr(args, "desde", None),
        ate=getattr(args, "ate", None),
        sentimento=getattr(args, "sentimento", None),
    )
    print(f"Exportados: {n} itens → {args.out}")


def cmd_stats(args) -> None:
    """Exibe estatísticas de uso dos providers LLM."""
    config = carregar(Path("config/config.yaml"))

    from src.providers.factory import ProviderFactory
    factory = ProviderFactory(config)
    provider = factory.provider_para("analise")

    print("\n=== ESTATÍSTICAS DE USO LLM ===")
    print(f"Provider configurado: {provider.nome}")
    if hasattr(provider, "estatisticas"):
        for nome, stats in provider.estatisticas().items():
            print(f"\n  [{nome}]")
            print(f"    Requisições OK:    {stats['ok']}")
            print(f"    Requisições erro:  {stats['erro']}")
            print(f"    Taxa de sucesso:   {stats['taxa_sucesso']}")
            print(f"    Tokens entrada:    {stats['tokens_entrada']}")
            print(f"    Tokens saída:      {stats['tokens_saida']}")
            print(f"    Último uso:        {stats['ultimo_uso'] or '—'}")
    else:
        print("  Provider sem rastreamento de estatísticas.")


def cmd_briefing(args) -> None:
    """Gera briefing do último ciclo."""
    config = carregar(Path("config/config.yaml"))
    from src.memory.database import Database as DB
    from src.memory.repositories.briefings_repo import BriefingsRepo

    db = DB.inicializar(Path(config.database.caminho))
    repo = BriefingsRepo(db)
    recentes = repo.buscar_recentes(limite=1)
    if recentes:
        b = recentes[0]
        print(f"Último briefing: {b['id']} | {b['gerado_em']} | {b['status']}")
    else:
        print("Nenhum briefing encontrado. Execute: python main.py run")


def main() -> None:
    ap = argparse.ArgumentParser(description="ATALAIA ComSoc")
    subparsers = ap.add_subparsers(dest="comando", required=True)

    # ETL
    etl_parser = subparsers.add_parser("etl", help="Executa ETL CCOMSEx")
    etl_parser.add_argument("entrada", help="Arquivo .xls/.xlsx ou pasta")
    etl_parser.add_argument("--db", default="data/atalaia.db")
    etl_parser.add_argument("--glob", default="*.xls*")
    etl_parser.set_defaults(func=cmd_etl)

    # Run ciclo
    run_parser = subparsers.add_parser("run", help="Executa ciclo Trilha B")
    run_parser.set_defaults(func=cmd_run)

    # Health
    health_parser = subparsers.add_parser("health", help="Verifica saúde do sistema")
    health_parser.set_defaults(func=cmd_health)

    # Dashboard
    dash_parser = subparsers.add_parser("dashboard", help="Gera dashboard HTML")
    dash_parser.add_argument("--db", default="data/atalaia.db")
    dash_parser.add_argument("--out", default="output/dashboard.html")
    dash_parser.add_argument("--janela", type=int, default=90)
    dash_parser.set_defaults(func=cmd_dashboard)

    # Export
    exp_parser = subparsers.add_parser("export", help="Exporta dados (xlsx/csv/json)")
    exp_parser.add_argument("--formato", choices=["xlsx", "csv", "json"], default="xlsx")
    exp_parser.add_argument("--out", default="output/export.xlsx")
    exp_parser.add_argument("--db", default="data/atalaia.db")
    exp_parser.add_argument("--trilha", choices=["A", "B", "ALL"], default="ALL")
    exp_parser.add_argument("--desde", default=None, help="YYYY-MM-DD")
    exp_parser.add_argument("--ate", default=None, help="YYYY-MM-DD")
    exp_parser.add_argument("--sentimento", choices=["POSITIVA", "NEUTRA", "NEGATIVA"], default=None)
    exp_parser.set_defaults(func=cmd_export)

    # Briefing
    brief_parser = subparsers.add_parser("briefing", help="Mostra último briefing")
    brief_parser.set_defaults(func=cmd_briefing)

    # Stats LLM
    stats_parser = subparsers.add_parser("stats", help="Estatísticas de uso dos providers LLM")
    stats_parser.set_defaults(func=cmd_stats)

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupção pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"Erro: {e}")
        sys.exit(1)
