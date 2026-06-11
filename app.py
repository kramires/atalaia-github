#!/usr/bin/env python3
"""ATALAIA ComSoc — Servidor Web Central (Fase 1)."""
from __future__ import annotations

import json
import re
import socket
import sqlite3
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from threading import Thread
from typing import Literal

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(title="ATALAIA ComSoc")

# ── Estado global ─────────────────────────────────────────────────────────────
_ciclo: dict = {"rodando": False, "log": [], "concluido_em": None}
_briefing_cache: dict = {"html": None, "gerado_em": None, "rodando": False, "log": []}
DB = "data/atalaia.db"


def _ip_local() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Modelos Pydantic para o briefing IA ────────────────────────────────────────

class ItemIndicador(BaseModel):
    descricao: str
    tipo: Literal["FATO", "INTERPRETACAO", "HIPOTESE"] = "INTERPRETACAO"


class AtorIdentificado(BaseModel):
    nome: str
    papel: str
    posicao: Literal["FAVORAVEL", "ADVERSO", "NEUTRO"] = "NEUTRO"


class BriefingIA(BaseModel):
    sintese_executiva: str
    cenarios: list[str] = Field(max_length=6)
    diagnostico: str
    indicadores_positivos: list[ItemIndicador] = Field(max_length=8)
    indicadores_negativos: list[ItemIndicador] = Field(max_length=8)
    indicadores_neutros: list[ItemIndicador] = Field(max_length=6)
    atores: list[AtorIdentificado] = Field(max_length=10)
    analise_prospectiva: list[str] = Field(max_length=6)
    recomendacoes_manter: list[str] = Field(max_length=6)
    recomendacoes_reverter: list[str] = Field(max_length=6)
    recomendacoes_oportunidade: list[str] = Field(max_length=5)


# ── Funções de dados ──────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def _status_banco() -> dict:
    try:
        conn = _conn()
        total    = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        trilha_a = conn.execute("SELECT COUNT(*) FROM items WHERE fonte_trilha='A'").fetchone()[0]
        trilha_b = conn.execute("SELECT COUNT(*) FROM items WHERE fonte_trilha='B'").fetchone()[0]
        analises = conn.execute("SELECT COUNT(*) FROM analise_ia").fetchone()[0]
        sents    = dict(conn.execute("SELECT sentimento_ia, COUNT(*) FROM analise_ia GROUP BY sentimento_ia").fetchall())
        ontem    = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        b_24h    = conn.execute("SELECT COUNT(*) FROM items WHERE fonte_trilha='B' AND ingested_at >= ?", (ontem,)).fetchone()[0]
        ciclo    = conn.execute("SELECT iniciado_em, status, itens_coletados, itens_relevantes FROM ciclos_execucao ORDER BY rowid DESC LIMIT 1").fetchone()
        conn.close()
        pos = sents.get("POSITIVA", 0)
        neg = sents.get("NEGATIVA", 0)
        return {
            "total": total, "trilha_a": trilha_a, "trilha_b": trilha_b,
            "analises": analises, "b_24h": b_24h, "pos": pos, "neg": neg,
            "pct_pos": round(pos / analises * 100) if analises else 0,
            "pct_neg": round(neg / analises * 100) if analises else 0,
            "ciclo_em": ciclo["iniciado_em"][:19].replace("T", " ") if ciclo else "—",
            "ciclo_status": ciclo["status"] if ciclo else "—",
            "ciclo_coletados": ciclo["itens_coletados"] if ciclo else 0,
            "ciclo_relevantes": ciclo["itens_relevantes"] if ciclo else 0,
        }
    except Exception as e:
        return {"erro": str(e)}


def _itens_24h(horas: int = 24) -> list[dict]:
    """Retorna itens Trilha B das últimas N horas filtrados por data de PUBLICAÇÃO,
    deduplicados por título similar."""
    try:
        # Filtra pela data de publicação (data_pub), não pela data de ingestão.
        # Isso garante que somente notícias realmente recentes aparecem no briefing.
        desde_pub = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
        # Fallback: inclui também por ingested_at para itens sem data_pub
        desde_ing = (datetime.now(timezone.utc) - timedelta(hours=horas * 2)).isoformat()
        conn = _conn()
        rows = conn.execute(
            """SELECT i.id, i.titulo, COALESCE(i.link_original,'') AS link,
                      COALESCE(i.veiculo,'') AS veiculo,
                      COALESCE(a.sentimento_ia,'NA') AS sent,
                      COALESCE(a.confianca, 0) AS conf,
                      COALESCE(a.narrativa,'') AS narrativa,
                      COALESCE(a.evidencia,'') AS evidencia,
                      COALESCE(i.data_pub,'') AS data_pub,
                      COALESCE(a.risco,'') AS risco
               FROM items i
               LEFT JOIN analise_ia a ON a.item_id = i.id
               WHERE i.fonte_trilha='B'
                 AND (
                   (i.data_pub IS NOT NULL AND i.data_pub != '' AND i.data_pub >= ?)
                   OR
                   (i.data_pub IS NULL OR i.data_pub = '') AND i.ingested_at >= ?
                 )
               ORDER BY i.data_pub DESC, a.confianca DESC""",
            (desde_pub, desde_ing)
        ).fetchall()
        conn.close()

        # Deduplicação: normaliza título (primeiras 7 palavras significativas)
        def chave_titulo(t: str) -> str:
            palavras = re.sub(r"[^\w\s]", "", t.lower()).split()
            stop = {"o", "a", "os", "as", "de", "da", "do", "que", "e", "em", "no", "na",
                    "para", "com", "por", "um", "uma", "se", "é", "são"}
            sig = [p for p in palavras if p not in stop]
            return " ".join(sig[:7])

        vistos: set[str] = set()
        itens = []
        for r in rows:
            chave = chave_titulo(r["titulo"] or "")
            if chave and chave not in vistos:
                vistos.add(chave)
                itens.append(dict(r))
        return itens
    except Exception:
        return []


def _formatar_noticias_para_llm(itens: list[dict]) -> str:
    linhas = []
    for i, item in enumerate(itens, 1):
        linhas.append(
            f"{i}. [{item['sent']} {item['conf']:.0%}] {item['titulo']}\n"
            f"   Veículo: {item['veiculo']} | {item['data_pub'][:10]}\n"
            f"   Narrativa: {item['narrativa'] or '—'}"
        )
    return "\n\n".join(linhas)


# ── Geração do Briefing IA ─────────────────────────────────────────────────────

_SYSTEM_BRIEFING = """Você é um analista sênior de comunicação social institucional.
Elabore um briefing completo de inteligência de mídia no formato JSON especificado.

REGRAS INEGOCIÁVEIS:
- Toda inferência deve ser marcada: FATO, INTERPRETACAO ou HIPOTESE.
- Nunca sugira contrapropaganda, fake news ou ações ilegais.
- Linguagem objetiva, clara e militarmente adequada.
- Recomendações devem ser acionáveis pela área de Comunicação Social.
- Máximo de 3 frases por item de lista.
"""


def _gerar_briefing_html_ia(itens: list[dict]) -> str:
    """Gera HTML completo do briefing usando IA."""
    from src.core.config.config_loader import carregar, _instancia
    import src.core.config.config_loader as _cfg_mod
    from src.providers.factory import ProviderFactory

    # Garante config carregada
    try:
        cfg = _cfg_mod._instancia or carregar(Path("config/config.yaml"))
    except Exception:
        cfg = carregar(Path("config/config.yaml"))

    provider = ProviderFactory(cfg).provider_para("briefing_p2")

    noticias_txt = _formatar_noticias_para_llm(itens[:50])  # cap 50 para controlar tokens

    n_neg = sum(1 for i in itens if i["sent"] == "NEGATIVA")
    n_pos = sum(1 for i in itens if i["sent"] == "POSITIVA")
    n_neu = sum(1 for i in itens if i["sent"] == "NEUTRA")
    total = len(itens) or 1

    user_prompt = f"""PERÍODO: últimas 24 horas
TOTAL DE NOTÍCIAS ANALISADAS: {len(itens)} (POSITIVA: {n_pos}, NEUTRA: {n_neu}, NEGATIVA: {n_neg})

NOTÍCIAS COLETADAS:
{noticias_txt}

Elabore o briefing completo seguindo rigorosamente o schema JSON fornecido.
Seja específico: cite veículos, temas e eventos concretos das notícias acima."""

    _briefing_cache["log"].append(f"Enviando {len(itens)} notícias para análise…")
    resultado: BriefingIA = provider.completar_estruturado(  # type: ignore
        system=_SYSTEM_BRIEFING,
        user=user_prompt,
        schema=BriefingIA,
    )
    _briefing_cache["log"].append("✓ Análise IA concluída. Gerando HTML…")
    return _html_briefing_completo(resultado, itens)


def _executar_briefing_bg() -> None:
    _briefing_cache["rodando"] = True
    _briefing_cache["log"] = ["Buscando notícias das últimas 24h…"]
    try:
        itens = _itens_24h(24)
        _briefing_cache["log"].append(f"{len(itens)} notícias únicas encontradas.")
        if not itens:
            _briefing_cache["html"] = "<p style='padding:40px;font-family:sans-serif'>Sem notícias nas últimas 24h. Execute uma busca primeiro.</p>"
            return
        html = _gerar_briefing_html_ia(itens)
        _briefing_cache["html"] = html
        _briefing_cache["gerado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        _briefing_cache["log"].append("✓ Briefing completo gerado.")
    except Exception as e:
        _briefing_cache["log"].append(f"✗ Erro: {e}")
        import traceback
        _briefing_cache["log"].append(traceback.format_exc()[:300])
    finally:
        _briefing_cache["rodando"] = False


# ── Ciclo coleta ──────────────────────────────────────────────────────────────

def _executar_ciclo() -> None:
    _ciclo["rodando"] = True
    _ciclo["log"] = ["Iniciando coleta e análise…"]
    try:
        proc = subprocess.Popen(
            ["python3", "main.py", "run"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=Path(__file__).parent,
        )
        for line in proc.stdout:
            txt = line.strip()
            if txt and not txt.startswith("20") and "httpx" not in txt:
                _ciclo["log"].append(txt)
        proc.wait()
        subprocess.run(
            ["python3", "main.py", "dashboard", "--db", DB, "--out", "dashboard.html"],
            cwd=Path(__file__).parent, capture_output=True,
        )
        _ciclo["log"].append("✓ Dashboard atualizado automaticamente.")
        _ciclo["concluido_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    except Exception as e:
        _ciclo["log"].append(f"✗ Erro: {e}")
    finally:
        _ciclo["rodando"] = False


# ── Endpoints API ─────────────────────────────────────────────────────────────

@app.post("/api/coletar")
def api_coletar():
    if _ciclo["rodando"]:
        return {"ok": False, "msg": "Ciclo já em execução."}
    Thread(target=_executar_ciclo, daemon=True).start()
    return {"ok": True}


@app.get("/api/log")
def api_log():
    return {"rodando": _ciclo["rodando"], "linhas": _ciclo["log"], "concluido_em": _ciclo["concluido_em"]}


@app.post("/api/dashboard")
def api_dashboard():
    r = subprocess.run(
        ["python3", "main.py", "dashboard", "--db", DB, "--out", "dashboard.html"],
        capture_output=True, text=True, cwd=Path(__file__).parent,
    )
    return {"ok": r.returncode == 0, "msg": r.stdout.strip() or r.stderr.strip()}


@app.post("/api/upload-clipping")
async def api_upload_clipping(file: UploadFile = File(...)):
    """Recebe a planilha diária de clipping, roda o ETL (Trilha A) e atualiza o dashboard."""
    nome = file.filename or "planilha.xls"
    if not nome.lower().endswith((".xls", ".xlsx")):
        return JSONResponse({"ok": False, "erro": "Envie um arquivo .xls ou .xlsx."}, status_code=400)

    updir = Path("data/uploads")
    updir.mkdir(parents=True, exist_ok=True)
    destino = updir / f"{datetime.now():%Y%m%d-%H%M%S}-{Path(nome).name}"
    destino.write_bytes(await file.read())

    # ETL via main.py (mesmo padrão dos demais comandos do app)
    etl = subprocess.run(
        ["python3", "main.py", "etl", str(destino), "--db", DB],
        capture_output=True, text=True, cwd=Path(__file__).parent,
    )
    if etl.returncode != 0:
        return JSONResponse(
            {"ok": False, "erro": (etl.stderr or etl.stdout or "Falha no ETL")[-400:]},
            status_code=500,
        )

    def _num(pat: str) -> int:
        m = re.search(pat, etl.stdout)
        return int(m.group(1)) if m else 0

    inseridos = _num(r"Inseridos:\s*(\d+)")
    duplicados = _num(r"Duplicados:\s*(\d+)")
    total = _num(r"Total no banco:\s*(\d+)")

    # regenera o dashboard com os novos dados
    subprocess.run(
        ["python3", "main.py", "dashboard", "--db", DB, "--out", "dashboard.html"],
        capture_output=True, cwd=Path(__file__).parent,
    )
    return {"ok": True, "arquivo": nome, "inseridos": inseridos, "duplicados": duplicados, "total": total}


@app.get("/api/status")
def api_status():
    return _status_banco()


@app.post("/api/gerar-briefing")
def api_gerar_briefing():
    if _briefing_cache["rodando"]:
        return {"ok": False, "msg": "Briefing já em geração."}
    Thread(target=_executar_briefing_bg, daemon=True).start()
    return {"ok": True}


@app.get("/api/briefing-status")
def api_briefing_status():
    return {
        "rodando": _briefing_cache["rodando"],
        "gerado_em": _briefing_cache["gerado_em"],
        "pronto": _briefing_cache["html"] is not None,
        "linhas": _briefing_cache["log"],
    }


# ── Endpoints de visualização ─────────────────────────────────────────────────

@app.get("/dashboard")
def ver_dashboard():
    p = Path("dashboard.html")
    if not p.exists():
        return HTMLResponse("<p style='padding:40px;font-family:sans-serif'>Dashboard não gerado. Clique em <b>Atualizar Dashboard</b>.</p>")
    return FileResponse(p, media_type="text/html")


@app.get("/briefing/simples")
def briefing_simples():
    """Briefing rápido sem IA — só lista as notícias agrupadas."""
    return HTMLResponse(_html_briefing_simples())


@app.get("/briefing")
def ver_briefing():
    """Briefing completo gerado por IA."""
    if _briefing_cache["html"]:
        return HTMLResponse(_briefing_cache["html"])
    # Se não gerado, mostra página de espera
    return HTMLResponse(_html_briefing_aguardando())


@app.get("/")
def home():
    return HTMLResponse(_pagina_central())


# ── Exportação ────────────────────────────────────────────────────────────────

@app.get("/export/dashboard")
def export_dashboard():
    p = Path("dashboard.html")
    if not p.exists():
        return JSONResponse({"erro": "Dashboard não gerado."}, 404)
    return FileResponse(
        p, media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="atalaia_dashboard_{datetime.now().strftime("%Y%m%d_%H%M")}.html"'}
    )


@app.get("/export/briefing")
def export_briefing():
    if not _briefing_cache["html"]:
        return JSONResponse({"erro": "Briefing não gerado ainda."}, 404)
    html_bytes = _briefing_cache["html"].encode("utf-8")
    return StreamingResponse(
        iter([html_bytes]),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="atalaia_briefing_{datetime.now().strftime("%Y%m%d_%H%M")}.html"'}
    )


@app.get("/export/pacote")
def export_pacote():
    """ZIP com dashboard + briefing para compartilhar."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        p = Path("dashboard.html")
        if p.exists():
            zf.writestr(f"dashboard_{datetime.now().strftime('%Y%m%d')}.html", p.read_text(encoding="utf-8"))
        if _briefing_cache["html"]:
            zf.writestr(f"briefing_{datetime.now().strftime('%Y%m%d_%H%M')}.html", _briefing_cache["html"])
        # README simples
        zf.writestr("LEIAME.txt",
            "ATALAIA ComSoc — Pacote de relatórios\n"
            f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            "Abra os arquivos .html em qualquer navegador (Chrome, Safari, Firefox).\n"
            "Não necessita de internet para abrir — tudo está embutido nos arquivos.\n"
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="atalaia_' + datetime.now().strftime('%Y%m%d') + '.zip"'}
    )


# ── HTML: Briefing aguardando ─────────────────────────────────────────────────

def _html_briefing_aguardando() -> str:
    return """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATALAIA — Briefing</title>
<style>body{margin:0;background:#050908;color:#e8fff4;font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{text-align:center;padding:40px;max-width:480px}
.icon{font-size:56px;margin-bottom:20px}
h2{color:#2eff8a;margin:0 0 12px;font-size:18px;letter-spacing:1px}
p{color:#9bb6aa;line-height:1.6;margin-bottom:24px}
.btn{display:inline-block;background:rgba(46,255,138,.1);border:1px solid rgba(46,255,138,.4);color:#2eff8a;
  padding:12px 28px;border-radius:8px;text-decoration:none;font-size:14px;cursor:pointer;font-family:inherit}
.btn:hover{background:rgba(46,255,138,.2)}
a.back{display:block;margin-top:16px;color:#9bb6aa;font-size:15px;text-decoration:none}
a.back:hover{color:#4bdcff}
</style></head><body>
<div class="box">
  <div class="icon">📋</div>
  <h2>Briefing de Inteligência</h2>
  <p>O briefing completo ainda não foi gerado.<br>
  Clique em <b>Gerar Briefing</b> na página central para produzir a análise de inteligência com IA.</p>
  <a href="/" class="btn">← Voltar à Central</a>
  <a href="/briefing/simples" class="back">Ver lista simples de notícias →</a>
</div>
</body></html>"""


# ── HTML: Briefing simples (sem IA) ──────────────────────────────────────────

def _html_briefing_simples() -> str:
    itens = _itens_24h(24)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    n_neg = sum(1 for i in itens if i["sent"] == "NEGATIVA")
    n_pos = sum(1 for i in itens if i["sent"] == "POSITIVA")
    n_neu = sum(1 for i in itens if i["sent"] == "NEUTRA")
    total = len(itens) or 1
    risco = "CRÍTICO" if n_neg/total >= .5 else "ALTO" if n_neg/total >= .3 else "MÉDIO" if n_neg/total >= .15 else "BAIXO"
    cr = {"CRÍTICO":"#ff3b3b","ALTO":"#ff8a2a","MÉDIO":"#ffd84a","BAIXO":"#2eff8a"}[risco]

    def badge(s: str, c: float) -> str:
        cls = {"POSITIVA":"pos","NEGATIVA":"neg","NEUTRA":"neu"}.get(s, "na")
        return f'<span class="badge {cls}">{s} {c:.0%}</span>'

    grupos = ""
    for s, label, ico in [("NEGATIVA","Alertas","🔴"),("NEUTRA","Neutras","🟡"),("POSITIVA","Positivas","🟢")]:
        g = [i for i in itens if i["sent"] == s]
        if not g: continue
        grupos += f'<div class="grupo"><h2>{ico} {label} <span class="cnt">({len(g)})</span></h2>'
        for i in g:
            lnk = f'<a href="{i["link"]}" target="_blank" rel="noopener">{i["titulo"]}</a>' if i["link"] else i["titulo"]
            narr = f'<div class="narr">📌 {i["narrativa"]}</div>' if i["narrativa"] else ""
            grupos += f'<div class="item"><div class="item-top">{badge(i["sent"],i["conf"])} <span class="vei">{i["veiculo"]}</span><span class="dt">{i["data_pub"][:10]}</span></div><div class="tit">{lnk}</div>{narr}</div>'
        grupos += "</div>"

    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATALAIA — Notícias 24h</title>
<style>
:root{{--bg:#050908;--panel:rgba(12,24,21,.82);--line:rgba(116,255,190,.20);
  --text:#e8fff4;--muted:#9bb6aa;--green:#2eff8a;--yellow:#ffd84a;--red:#ff3b3b;--cyan:#4bdcff}}
*{{box-sizing:border-box}}html,body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",sans-serif;font-size:17px}}
.wrap{{max-width:1400px;margin:0 auto;padding:24px 20px}}
header{{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px}}
h1{{margin:0;font-size:18px;letter-spacing:2px;text-transform:uppercase;text-shadow:0 0 16px rgba(46,255,138,.35)}}
h1 span{{color:var(--green)}}.meta{{color:var(--muted);font-size:12px;text-align:right}}
.kpis{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
.kpi{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 16px;text-align:center}}
.kpi .v{{font-size:22px;font-weight:700}}.kpi .l{{color:var(--muted);font-size:10px;text-transform:uppercase;margin-top:3px}}
.grupos-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:900px){{.grupos-grid{{grid-template-columns:1fr}}}}
.grupo{{margin-bottom:0}}.grupo h2{{font-size:17px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;margin:0 0 10px;display:flex;align-items:center;gap:6px}}
.cnt{{color:var(--muted);font-weight:400}}
.item{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin-bottom:8px}}
.item-top{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:7px}}
.badge{{padding:2px 9px;border-radius:10px;font-size:11px;font-weight:700;display:inline-block}}
.badge.pos{{background:rgba(46,255,138,.14);color:var(--green);border:1px solid rgba(46,255,138,.4)}}
.badge.neg{{background:rgba(255,59,59,.14);color:#ff7676;border:1px solid rgba(255,59,59,.4)}}
.badge.neu{{background:rgba(255,216,74,.14);color:var(--yellow);border:1px solid rgba(255,216,74,.4)}}
.badge.na{{background:rgba(100,100,100,.2);color:var(--muted);border:1px solid var(--line)}}
.vei{{color:var(--cyan);font-size:14px;font-weight:600;text-transform:uppercase}}
.dt{{color:var(--muted);font-size:11px;margin-left:auto}}
.tit{{font-size:13px;line-height:1.5}}.tit a{{color:var(--text);text-decoration:none}}.tit a:hover{{color:var(--green);text-decoration:underline}}
.narr{{color:var(--muted);font-size:11px;margin-top:5px;font-style:italic}}
.back{{display:inline-block;margin-bottom:16px;color:var(--muted);font-size:15px;text-decoration:none}}.back:hover{{color:var(--green)}}
footer{{margin-top:24px;border-top:1px solid var(--line);padding-top:12px;color:var(--muted);font-size:11px;text-align:center}}
</style></head><body><div class="wrap">
<button onclick="toggleFullscreen()" style="position:fixed;top:16px;right:16px;z-index:1000;background:rgba(46,255,138,.1);border:1px solid rgba(46,255,138,.4);color:#2eff8a;padding:10px 16px;border-radius:8px;font-size:14px;cursor:pointer;font-family:inherit">⛶ Fullscreen (F)</button>
<a href="/" class="back">← Voltar à Central</a>
<header>
  <div><h1><span>Atalaia</span> — Notícias Monitoradas</h1><div style="color:var(--muted);font-size:11px;margin-top:3px">Últimas 24 horas · Trilha B · {len(itens)} notícias únicas</div></div>
  <div class="meta">Gerado: {now}<br>Risco: <b style="color:{cr}">{risco}</b></div>
</header>
<div class="kpis">
  <div class="kpi"><div class="v">{len(itens)}</div><div class="l">Total</div></div>
  <div class="kpi"><div class="v" style="color:var(--green)">{n_pos}</div><div class="l">Positivas</div></div>
  <div class="kpi"><div class="v" style="color:var(--yellow)">{n_neu}</div><div class="l">Neutras</div></div>
  <div class="kpi"><div class="v" style="color:var(--red)">{n_neg}</div><div class="l">Negativas</div></div>
  <div class="kpi"><div class="v" style="color:{cr}">{risco}</div><div class="l">Risco</div></div>
</div>
<div class="grupos-grid">
{grupos if grupos else '<p style="color:var(--muted);text-align:center;padding:32px;grid-column:1/-1">Sem notícias nas últimas 24h.</p>'}
</div>
<footer>ATALAIA ComSoc · Validação humana obrigatória antes de qualquer ação institucional</footer>
</div>

<script>
function toggleFullscreen() {{
  if (!document.fullscreenElement) {{
    document.documentElement.requestFullscreen().catch(err => {{
      console.log('Fullscreen não suportado:', err);
    }});
  }} else {{
    document.exitFullscreen();
  }}
}}
document.addEventListener('keydown', e => {{
  if (e.key === 'F' || e.key === 'f') {{
    e.preventDefault();
    toggleFullscreen();
  }}
}});
</script>

</body></html>"""


# ── HTML: Briefing completo com IA ────────────────────────────────────────────

def _html_briefing_completo(b: BriefingIA, itens: list[dict]) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    n_neg = sum(1 for i in itens if i["sent"] == "NEGATIVA")
    n_pos = sum(1 for i in itens if i["sent"] == "POSITIVA")
    n_neu = sum(1 for i in itens if i["sent"] == "NEUTRA")
    total = len(itens) or 1
    risco = "CRÍTICO" if n_neg/total >= .5 else "ALTO" if n_neg/total >= .3 else "MÉDIO" if n_neg/total >= .15 else "BAIXO"
    cr = {"CRÍTICO":"#ff3b3b","ALTO":"#ff8a2a","MÉDIO":"#ffd84a","BAIXO":"#2eff8a"}[risco]

    def ul(items_list: list, cls: str = "") -> str:
        if not items_list:
            return '<li style="color:#9bb6aa">Nenhum identificado</li>'
        linhas = []
        for item in items_list:
            if hasattr(item, "descricao"):
                tipo_cls = {"FATO":"tag-fato","INTERPRETACAO":"tag-int","HIPOTESE":"tag-hip"}.get(item.tipo, "tag-int")
                linhas.append(f'<li>{item.descricao} <span class="tag {tipo_cls}">{item.tipo}</span></li>')
            elif hasattr(item, "nome"):
                pos_cls = {"FAVORAVEL":"pos","ADVERSO":"neg","NEUTRO":"neu"}.get(item.posicao, "neu")
                linhas.append(f'<li><b>{item.nome}</b> — {item.papel} <span class="badge {pos_cls}">{item.posicao}</span></li>')
            else:
                linhas.append(f'<li>{item}</li>')
        return "\n".join(linhas)

    # Lista de notícias agrupadas
    def noticias_grupo(sent: str, ico: str) -> str:
        g = [i for i in itens if i["sent"] == sent]
        if not g: return ""
        linhas = []
        for i in g[:20]:
            lnk = f'<a href="{i["link"]}" target="_blank">{i["titulo"]}</a>' if i["link"] else i["titulo"]
            linhas.append(f'<li>{lnk} <span style="color:#9bb6aa;font-size:11px">— {i["veiculo"]} ({i["conf"]:.0%})</span></li>')
        return f'<div class="noticia-grupo"><h3>{ico} {sent.title()} ({len(g)})</h3><ul>{"".join(linhas)}</ul></div>'

    noticias_html = noticias_grupo("NEGATIVA","🔴") + noticias_grupo("NEUTRA","🟡") + noticias_grupo("POSITIVA","🟢")

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATALAIA — Briefing de Inteligência</title>
<style>
:root{{--bg:#050908;--panel:rgba(12,24,21,.82);--panel2:rgba(20,38,34,.94);
  --line:rgba(116,255,190,.18);--line-s:rgba(116,255,190,.44);
  --text:#e8fff4;--muted:#9bb6aa;--green:#2eff8a;--yellow:#ffd84a;--red:#ff3b3b;--cyan:#4bdcff;--blue:#5b8cff;--orange:#ff8a2a}}
*{{box-sizing:border-box}}
html,body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",sans-serif;font-size:18px;line-height:1.8}}
.wrap{{max-width:1400px;margin:0 auto;padding:28px 20px}}
header{{background:var(--panel2);border:1px solid var(--line-s);border-radius:14px;padding:24px 28px;margin-bottom:24px}}
.header-top{{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:16px}}
header h1{{margin:0 0 4px;font-size:36px;letter-spacing:2.5px;text-transform:uppercase;text-shadow:0 0 20px rgba(46,255,138,.4)}}
header h1 span{{color:var(--green)}}
.header-meta{{color:var(--muted);font-size:12px;text-align:right}}
.aviso{{background:rgba(255,216,74,.08);border:1px solid rgba(255,216,74,.3);border-radius:8px;padding:10px 16px;color:var(--yellow);font-size:12px}}
.kpis{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px}}
.kpi{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 18px;text-align:center;min-width:90px}}
.kpi .v{{font-size:40px;font-weight:700}}.kpi .l{{color:var(--muted);font-size:10px;text-transform:uppercase;margin-top:4px}}
.secao{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:18px}}
.secao-header{{display:flex;align-items:center;gap:10px;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--line)}}
.secao-icon{{font-size:22px}}.secao-titulo{{font-size:20px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--cyan)}}
.secao-num{{background:rgba(75,220,255,.12);border:1px solid rgba(75,220,255,.3);color:var(--cyan);border-radius:4px;padding:1px 8px;font-size:14px;font-weight:600}}
p{{margin:0 0 10px;color:var(--text)}}
ul{{margin:0;padding-left:20px}}li{{margin-bottom:8px}}
.ind-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.ind-card{{border-radius:8px;padding:14px 16px}}
.ind-pos{{background:rgba(46,255,138,.07);border:1px solid rgba(46,255,138,.25)}}
.ind-neg{{background:rgba(255,59,59,.07);border:1px solid rgba(255,59,59,.25)}}
.ind-neu{{background:rgba(255,216,74,.07);border:1px solid rgba(255,216,74,.25)}}
.ind-card h4{{margin:0 0 10px;font-size:20px;text-transform:uppercase;letter-spacing:.8px}}
.ind-pos h4{{color:var(--green)}}.ind-neg h4{{color:#ff7676}}.ind-neu h4{{color:var(--yellow)}}
.ind-card li{{font-size:20px}}
.tag{{display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600;margin-left:6px;vertical-align:middle}}
.tag-fato{{background:rgba(75,220,255,.15);color:var(--cyan);border:1px solid rgba(75,220,255,.4)}}
.tag-int{{background:rgba(255,216,74,.12);color:var(--yellow);border:1px solid rgba(255,216,74,.35)}}
.tag-hip{{background:rgba(155,182,170,.12);color:var(--muted);border:1px solid var(--line)}}
.badge{{display:inline-block;padding:1px 8px;border-radius:8px;font-size:14px;font-weight:600}}
.badge.pos{{background:rgba(46,255,138,.14);color:var(--green)}}.badge.neg{{background:rgba(255,59,59,.14);color:#ff7676}}.badge.neu{{background:rgba(255,216,74,.14);color:var(--yellow)}}
.atores{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}}
.ator{{background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:8px;padding:16px 20px}}
.ator b{{color:var(--text);font-size:19px}}.ator .papel{{color:var(--muted);font-size:16px}}
.prosp{{border-left:3px solid var(--cyan);padding-left:14px;margin-bottom:10px}}
.prosp-txt{{color:var(--text);font-size:20px}}
.rec-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
.rec-card{{border-radius:8px;padding:14px 16px}}
.rec-card.verde{{background:rgba(46,255,138,.07);border:1px solid rgba(46,255,138,.25)}}
.rec-card.vermelho{{background:rgba(255,59,59,.07);border:1px solid rgba(255,59,59,.25)}}
.rec-card.amarelo{{background:rgba(255,216,74,.07);border:1px solid rgba(255,216,74,.25)}}
.rec-card h4{{margin:0 0 10px;font-size:15px;text-transform:uppercase;letter-spacing:.7px}}
.rec-card.verde h4{{color:var(--green)}}.rec-card.vermelho h4{{color:#ff7676}}.rec-card.amarelo h4{{color:var(--yellow)}}
.rec-card ol{{margin:0;padding-left:18px}}.rec-card li{{font-size:19px;margin-bottom:7px}}
.noticias-detalhe{{margin-top:8px}}
.noticia-grupo h3{{font-size:15px;text-transform:uppercase;letter-spacing:.7px;margin:10px 0 6px}}
.noticia-grupo ul{{margin:0;padding-left:16px}}.noticia-grupo li{{font-size:18px;margin-bottom:5px;line-height:1.4}}
.noticia-grupo a{{color:var(--text);text-decoration:none}}.noticia-grupo a:hover{{color:var(--green)}}
.back{{display:inline-block;margin-bottom:18px;color:var(--muted);font-size:15px;text-decoration:none}}.back:hover{{color:var(--green)}}
.export-bar{{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.export-bar span{{color:var(--muted);font-size:15px;margin-right:6px}}
.btn-exp{{background:rgba(46,255,138,.08);border:1px solid rgba(46,255,138,.35);color:var(--green);padding:6px 14px;border-radius:6px;font-size:15px;text-decoration:none;white-space:nowrap}}
.btn-exp:hover{{background:rgba(46,255,138,.18)}}
footer{{margin-top:28px;border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:11px;text-align:center}}
@media(max-width:700px){{.ind-grid,.rec-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="wrap">
  <button onclick="toggleFullscreen()" style="position:fixed;top:16px;right:16px;z-index:1000;background:rgba(46,255,138,.1);border:1px solid rgba(46,255,138,.4);color:#2eff8a;padding:10px 16px;border-radius:8px;font-size:14px;cursor:pointer;font-family:inherit">⛶ Fullscreen (F)</button>
  <a href="/" class="back">← Voltar à Central</a>

  <div class="export-bar">
    <span>Exportar:</span>
    <a href="/export/briefing" class="btn-exp">⬇ Baixar Briefing (.html)</a>
    <a href="/export/dashboard" class="btn-exp">⬇ Baixar Dashboard (.html)</a>
    <a href="/export/pacote" class="btn-exp">📦 Pacote completo (.zip)</a>
  </div>

  <header>
    <div class="header-top">
      <div>
        <h1><span>Atalaia</span> ComSoc — Briefing de Inteligência</h1>
        <div style="color:var(--muted);font-size:15px;margin-top:4px">Análise das últimas 24 horas · Trilha B (Tempo Real) · {len(itens)} notícias únicas</div>
      </div>
      <div class="header-meta">
        Gerado em {now}<br>
        Risco identificado: <b style="color:{cr}">{risco}</b>
      </div>
    </div>
    <div class="aviso">⚠️ Documento de análise prospectiva gerado por IA. Toda inferência está classificada como FATO / INTERPRETAÇÃO / HIPÓTESE. Validação humana obrigatória antes de qualquer ação institucional.</div>
  </header>

  <div class="kpis">
    <div class="kpi"><div class="v">{len(itens)}</div><div class="l">Notícias</div></div>
    <div class="kpi"><div class="v" style="color:var(--green)">{n_pos}</div><div class="l">Positivas</div></div>
    <div class="kpi"><div class="v" style="color:var(--yellow)">{n_neu}</div><div class="l">Neutras</div></div>
    <div class="kpi"><div class="v" style="color:var(--red)">{n_neg}</div><div class="l">Negativas</div></div>
    <div class="kpi"><div class="v" style="color:{cr}">{risco}</div><div class="l">Risco</div></div>
  </div>

  <!-- 1. SÍNTESE EXECUTIVA -->
  <div class="secao">
    <div class="secao-header"><span class="secao-icon">📋</span><span class="secao-titulo">Síntese Executiva</span><span class="secao-num">1</span></div>
    <p>{b.sintese_executiva.replace(chr(10), '</p><p>')}</p>
  </div>

  <!-- 2. CENÁRIOS -->
  <div class="secao">
    <div class="secao-header"><span class="secao-icon">🗺</span><span class="secao-titulo">Cenários Identificados</span><span class="secao-num">2</span></div>
    <ul>{"".join(f"<li>{c}</li>" for c in b.cenarios)}</ul>
  </div>

  <!-- 3. DIAGNÓSTICO -->
  <div class="secao">
    <div class="secao-header"><span class="secao-icon">🔬</span><span class="secao-titulo">Diagnóstico da Situação</span><span class="secao-num">3</span></div>
    <p>{b.diagnostico.replace(chr(10), '</p><p>')}</p>
  </div>

  <!-- 4. INDICADORES -->
  <div class="secao">
    <div class="secao-header"><span class="secao-icon">📊</span><span class="secao-titulo">Indicadores</span><span class="secao-num">4</span></div>
    <div class="ind-grid">
      <div class="ind-card ind-pos"><h4>✅ Positivos ({len(b.indicadores_positivos)})</h4><ul>{ul(b.indicadores_positivos)}</ul></div>
      <div class="ind-card ind-neg"><h4>⚠️ Negativos ({len(b.indicadores_negativos)})</h4><ul>{ul(b.indicadores_negativos)}</ul></div>
    </div>
    <div style="margin-top:12px"><div class="ind-card ind-neu"><h4>🔄 Neutros / Ambíguos ({len(b.indicadores_neutros)})</h4><ul>{ul(b.indicadores_neutros)}</ul></div></div>
  </div>

  <!-- 5. ATORES -->
  <div class="secao">
    <div class="secao-header"><span class="secao-icon">👥</span><span class="secao-titulo">Atores Identificados</span><span class="secao-num">5</span></div>
    <div class="atores">
      {"".join(f'<div class="ator"><b>{a.nome}</b> <span class="badge {"pos" if a.posicao=="FAVORAVEL" else "neg" if a.posicao=="ADVERSO" else "neu"}">{a.posicao}</span><div class="papel">{a.papel}</div></div>' for a in b.atores)}
    </div>
  </div>

  <!-- 6. ANÁLISE PROSPECTIVA -->
  <div class="secao">
    <div class="secao-header"><span class="secao-icon">🔮</span><span class="secao-titulo">Análise Prospectiva (3-5 dias)</span><span class="secao-num">6</span></div>
    {"".join(f'<div class="prosp"><div class="prosp-txt">{p_}</div></div>' for p_ in b.analise_prospectiva)}
  </div>

  <!-- 7. PRESCRIÇÃO -->
  <div class="secao">
    <div class="secao-header"><span class="secao-icon">💡</span><span class="secao-titulo">Prescrição e Recomendações</span><span class="secao-num">7</span></div>
    <div class="rec-grid">
      <div class="rec-card verde"><h4>🟢 Manter positivas</h4><ol>{"".join(f"<li>{r}</li>" for r in b.recomendacoes_manter) or "<li>Nenhuma</li>"}</ol></div>
      <div class="rec-card vermelho"><h4>🔴 Reverter negativas</h4><ol>{"".join(f"<li>{r}</li>" for r in b.recomendacoes_reverter) or "<li>Nenhuma</li>"}</ol></div>
      <div class="rec-card amarelo"><h4>🟡 Neutras → Positivas</h4><ol>{"".join(f"<li>{r}</li>" for r in b.recomendacoes_oportunidade) or "<li>Nenhuma</li>"}</ol></div>
    </div>
  </div>

  <!-- 8. NOTÍCIAS DETALHADAS -->
  <div class="secao">
    <div class="secao-header"><span class="secao-icon">📰</span><span class="secao-titulo">Notícias Analisadas ({len(itens)})</span><span class="secao-num">8</span></div>
    <div class="noticias-detalhe">{noticias_html}</div>
  </div>

  <footer>ATALAIA ComSoc · Fase 1 · Gerado por IA ({datetime.now().strftime("%d/%m/%Y %H:%M")}) · Análise prospectiva — validação humana obrigatória</footer>
</div>

<script>
function toggleFullscreen() {{
  if (!document.fullscreenElement) {{
    document.documentElement.requestFullscreen().catch(err => {{
      console.log('Fullscreen não suportado:', err);
    }});
  }} else {{
    document.exitFullscreen();
  }}
}}
document.addEventListener('keydown', e => {{
  if (e.key === 'F' || e.key === 'f') {{
    e.preventDefault();
    toggleFullscreen();
  }}
}});
</script>

</body>
</html>"""


# ── Página Central ─────────────────────────────────────────────────────────────

def _pagina_central() -> str:
    ip = _ip_local()
    st = _status_banco()
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATALAIA ComSoc — Central</title>
<style>
:root{{--bg:#050908;--panel:rgba(12,24,21,.78);--panel2:rgba(20,38,34,.92);
  --line:rgba(116,255,190,.18);--line-s:rgba(116,255,190,.44);
  --text:#e8fff4;--muted:#9bb6aa;--green:#2eff8a;--yellow:#ffd84a;--red:#ff3b3b;--cyan:#4bdcff;--blue:#5b8cff}}
*{{box-sizing:border-box}}
html,body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",Roboto,Arial,sans-serif;font-size:17px}}
body::before{{content:"";position:fixed;inset:0;z-index:-4;background:
  radial-gradient(circle at 8% 12%,rgba(46,255,138,.12),transparent 35%),
  radial-gradient(circle at 90% 6%,rgba(75,220,255,.10),transparent 30%),
  linear-gradient(rgba(46,255,138,.020) 1px,transparent 1px),
  linear-gradient(90deg,rgba(46,255,138,.020) 1px,transparent 1px);
  background-size:auto,auto,44px 44px,44px 44px}}
.wrap{{max-width:1400px;margin:0 auto;padding:28px 20px}}
header{{text-align:center;margin-bottom:28px}}
h1{{margin:0 0 6px;font-size:42px;letter-spacing:4px;text-transform:uppercase;text-shadow:0 0 28px rgba(46,255,138,.45)}}
h1 span{{color:var(--green)}}.sub{{color:var(--muted);font-size:16px;letter-spacing:.5px}}
.rede{{display:inline-block;margin-top:8px;background:rgba(75,220,255,.08);border:1px solid rgba(75,220,255,.3);
  color:var(--cyan);border-radius:6px;padding:4px 12px;font-size:11px;font-family:monospace}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;text-align:center;transition:border-color .2s}}
.stat:hover{{border-color:var(--line-s)}}
.stat .v{{font-size:26px;font-weight:700;text-shadow:0 0 12px rgba(46,255,138,.2)}}
.stat .l{{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.8px;margin-top:4px}}
.acoes{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}}
.btn{{background:var(--panel);border:1px solid var(--line-s);border-radius:12px;padding:20px 16px;cursor:pointer;text-align:center;
  transition:all .2s;outline:none;display:flex;flex-direction:column;align-items:center;gap:8px;
  color:var(--text);font-family:inherit;font-size:13px;width:100%}}
.btn:hover{{background:rgba(46,255,138,.08);border-color:var(--green);transform:translateY(-2px)}}
.btn.disabled{{opacity:.45;cursor:not-allowed;pointer-events:none}}
.btn .ico{{font-size:30px}}.btn .t{{font-size:18px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--green)}}
.btn .d{{color:var(--muted);font-size:15px;line-height:1.5}}
.nav{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:20px}}
.nav-card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;
  text-decoration:none;color:var(--text);transition:all .2s;display:flex;align-items:center;gap:14px}}
.nav-card:hover{{background:rgba(75,220,255,.07);border-color:var(--cyan);transform:translateY(-1px)}}
.nav-card .ico{{font-size:28px;flex-shrink:0}}
.nav-card .t{{font-size:18px;font-weight:600;color:var(--cyan);margin-bottom:3px}}
.nav-card .d{{color:var(--muted);font-size:14px;line-height:1.5}}
.export-bar{{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.export-bar span{{color:var(--muted);font-size:12px}}
.btn-exp{{background:rgba(46,255,138,.07);border:1px solid rgba(46,255,138,.3);color:var(--green);
  padding:6px 14px;border-radius:6px;font-size:15px;text-decoration:none;white-space:nowrap}}
.btn-exp:hover{{background:rgba(46,255,138,.16)}}
.log-box{{background:var(--panel2);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.log-top{{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--muted);transition:background .3s;flex-shrink:0}}
.dot.ativo{{background:var(--green);box-shadow:0 0 8px rgba(46,255,138,.6);animation:pulse 1.2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.log-body{{padding:12px 16px;max-height:200px;overflow-y:auto;font-family:"SF Mono","Courier New",monospace;font-size:15px;line-height:1.65;color:var(--muted)}}
.log-body .ok{{color:var(--green)}}.log-body .err{{color:var(--red)}}.log-body .inf{{color:var(--cyan)}}
footer{{margin-top:22px;text-align:center;color:var(--muted);font-size:11px;letter-spacing:.3px}}
@media(max-width:800px){{.stats,.acoes,.nav{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:500px){{.stats,.acoes,.nav{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="wrap">
  <button onclick="toggleFullscreen()" style="position:fixed;top:16px;right:16px;z-index:1000;background:rgba(46,255,138,.1);border:1px solid rgba(46,255,138,.4);color:#2eff8a;padding:10px 16px;border-radius:8px;font-size:14px;cursor:pointer;font-family:inherit">⛶ Fullscreen (F)</button>
  <header>
    <h1><span>ATALAIA</span> ComSoc</h1>
    <div class="sub">Central de Monitoramento e Análise de Mídia · Comunicação Social</div>
    <div class="rede">📱 Rede local: http://{ip}:9001</div>
  </header>

  <div class="stats">
    <div class="stat"><div class="v" id="sTrilhaA">—</div><div class="l">Histórico (Trilha A)</div></div>
    <div class="stat"><div class="v" id="sTrilhaB">—</div><div class="l">Tempo Real (Trilha B)</div></div>
    <div class="stat"><div class="v" id="sB24h">—</div><div class="l">Últimas 24h</div></div>
    <div class="stat"><div class="v" id="sPctPos" style="color:var(--green)">—</div><div class="l">% Positivo (IA)</div></div>
  </div>

  <div class="acoes">
    <button class="btn" id="btnColetar" onclick="iniciarColeta()">
      <div class="ico">🔍</div><div class="t">Buscar Notícias</div>
      <div class="d">Varre Google News agora<br>Analisa com IA (OpenAI → DeepSeek)</div>
    </button>
    <button class="btn" id="btnDash" onclick="atualizarDashboard()">
      <div class="ico">📊</div><div class="t">Atualizar Dashboard</div>
      <div class="d">Regenera o painel completo<br>Histórico + Tempo Real</div>
    </button>
    <button class="btn" id="btnBriefing" onclick="gerarBriefing()">
      <div class="ico">🧠</div><div class="t">Gerar Briefing IA</div>
      <div class="d">Análise completa das 24h<br>Diagnóstico · Prospectiva · Prescrição</div>
    </button>
  </div>

  <div style="display:flex;align-items:center;gap:14px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:18px;flex-wrap:wrap">
    <label style="background:rgba(46,255,138,.1);border:1px solid rgba(46,255,138,.4);color:#2eff8a;padding:10px 18px;border-radius:8px;font-size:14px;cursor:pointer;white-space:nowrap">
      📥 Adicionar planilha do dia
      <input type="file" id="fileClipping" accept=".xls,.xlsx" style="display:none" onchange="enviarClipping()">
    </label>
    <span id="uploadMsg" style="color:var(--muted);font-size:13px">Envie a planilha de clipping (.xls/.xlsx) — o sistema lê e popula o histórico automaticamente.</span>
  </div>

  <div class="nav">
    <a href="/dashboard" target="_blank" class="nav-card">
      <div class="ico">📋</div>
      <div><div class="t">Dashboard</div><div class="d">Painel interativo com gráficos<br>Filtros por sentimento e período</div></div>
    </a>
    <a href="/briefing" target="_blank" class="nav-card">
      <div class="ico">📰</div>
      <div><div class="t">Briefing Completo</div><div class="d">Análise de inteligência IA<br>Diagnóstico, atores e prescrição</div></div>
    </a>
    <a href="/briefing/simples" target="_blank" class="nav-card">
      <div class="ico">📄</div>
      <div><div class="t">Lista 24h</div><div class="d">Notícias agrupadas por sentimento<br>Rápido, sem IA</div></div>
    </a>
  </div>

  <div class="export-bar">
    <span>⬇ Exportar:</span>
    <a href="/export/dashboard" class="btn-exp">Dashboard (.html)</a>
    <a href="/export/briefing" class="btn-exp">Briefing (.html)</a>
    <a href="/export/pacote" class="btn-exp">📦 Pacote completo (.zip)</a>
    <span style="margin-left:auto;color:var(--muted);font-size:11px">Os arquivos abrem em qualquer navegador (PC ou celular)</span>
  </div>

  <div class="log-box">
    <div class="log-top"><div class="dot" id="logDot"></div><span id="logStatus">Sistema pronto</span><span style="margin-left:auto" id="logHora"></span></div>
    <div class="log-body" id="logBody"><span class="inf">Clique em Buscar Notícias para iniciar o monitoramento.</span></div>
  </div>

  <footer>ATALAIA ComSoc · Acesso na rede: <b>http://{ip}:9001</b> · Validação humana obrigatória antes de ações institucionais</footer>
</div>

<script>
let _polling = null, _briefingPolling = null, _linhasVistas = 0, _bLinhas = 0;

async function carregarStatus() {{
  try {{
    const d = await (await fetch('/api/status')).json();
    if(d.erro) return;
    document.getElementById('sTrilhaA').textContent = (d.trilha_a||0).toLocaleString('pt-BR');
    document.getElementById('sTrilhaB').textContent = (d.trilha_b||0).toLocaleString('pt-BR');
    document.getElementById('sB24h').textContent = (d.b_24h||0).toLocaleString('pt-BR');
    document.getElementById('sPctPos').textContent = (d.pct_pos||0) + '%';
  }} catch(e) {{}}
}}

async function enviarClipping() {{
  const inp = document.getElementById('fileClipping');
  if(!inp.files.length) return;
  const f = inp.files[0];
  const msg = document.getElementById('uploadMsg');
  msg.textContent = '⏳ Enviando e processando ' + f.name + '…';
  log('Upload: ' + f.name, 'inf');
  const fd = new FormData(); fd.append('file', f);
  try {{
    const resp = await fetch('/api/upload-clipping', {{method:'POST', body:fd}});
    const r = await resp.json();
    if(r.ok) {{
      msg.textContent = '✓ ' + r.inseridos + ' inseridas · ' + r.duplicados + ' duplicadas · total no banco: ' + r.total;
      log('✓ ETL: +' + r.inseridos + ' inseridas, ' + r.duplicados + ' duplicadas (total ' + r.total + ')', 'ok');
      carregarStatus();
    }} else {{
      msg.textContent = '✗ ' + (r.erro || 'Falha no processamento');
      log('✗ ' + (r.erro || 'falha no upload'), 'err');
    }}
  }} catch(e) {{
    msg.textContent = '✗ Erro de rede ao enviar a planilha';
    log('✗ ' + e, 'err');
  }}
  inp.value = '';
}}

function log(txt, cls='') {{
  const b = document.getElementById('logBody');
  const el = document.createElement('div');
  if(cls) el.className = cls;
  el.textContent = txt;
  if(b.children[0]?.classList.contains('inf')) b.innerHTML='';
  b.appendChild(el);
  b.scrollTop = b.scrollHeight;
}}

async function iniciarColeta() {{
  const btn = document.getElementById('btnColetar');
  btn.classList.add('disabled');
  const d = await (await fetch('/api/coletar',{{method:'POST'}})).json();
  if(!d.ok) {{ alert(d.msg); btn.classList.remove('disabled'); return; }}
  _linhasVistas = 0;
  document.getElementById('logDot').classList.add('ativo');
  document.getElementById('logStatus').textContent = 'Coletando e analisando…';
  document.getElementById('logHora').textContent = new Date().toLocaleTimeString('pt-BR');
  document.getElementById('logBody').innerHTML = '';
  if(_polling) clearInterval(_polling);
  _polling = setInterval(async () => {{
    const d = await (await fetch('/api/log')).json();
    d.linhas.slice(_linhasVistas).forEach(l => {{
      log(l, l.startsWith('✓')||l.includes('COMPLETO')?'ok': l.startsWith('✗')||l.includes('FALHA')?'err':'');
    }});
    _linhasVistas = d.linhas.length;
    if(!d.rodando) {{
      clearInterval(_polling); _polling = null;
      document.getElementById('logDot').classList.remove('ativo');
      document.getElementById('logStatus').textContent = 'Concluído ' + (d.concluido_em||'');
      document.getElementById('btnColetar').classList.remove('disabled');
      carregarStatus();
    }}
  }}, 1200);
}}

async function atualizarDashboard() {{
  document.getElementById('btnDash').classList.add('disabled');
  log('Gerando dashboard…','inf');
  const d = await (await fetch('/api/dashboard',{{method:'POST'}})).json();
  log(d.ok ? '✓ '+d.msg : '✗ '+d.msg, d.ok?'ok':'err');
  document.getElementById('btnDash').classList.remove('disabled');
  if(d.ok) carregarStatus();
}}

async function gerarBriefing() {{
  document.getElementById('btnBriefing').classList.add('disabled');
  const d = await (await fetch('/api/gerar-briefing',{{method:'POST'}})).json();
  if(!d.ok) {{ alert(d.msg); document.getElementById('btnBriefing').classList.remove('disabled'); return; }}
  _bLinhas = 0;
  document.getElementById('logDot').classList.add('ativo');
  document.getElementById('logStatus').textContent = 'Gerando briefing com IA…';
  document.getElementById('logBody').innerHTML = '';
  if(_briefingPolling) clearInterval(_briefingPolling);
  _briefingPolling = setInterval(async () => {{
    const d = await (await fetch('/api/briefing-status')).json();
    d.linhas.slice(_bLinhas).forEach(l => log(l, l.startsWith('✓')?'ok':l.startsWith('✗')?'err':'inf'));
    _bLinhas = d.linhas.length;
    if(!d.rodando) {{
      clearInterval(_briefingPolling); _briefingPolling = null;
      document.getElementById('logDot').classList.remove('ativo');
      document.getElementById('btnBriefing').classList.remove('disabled');
      if(d.pronto) {{
        document.getElementById('logStatus').textContent = 'Briefing gerado! Abrindo…';
        setTimeout(() => window.open('/briefing','_blank'), 600);
      }} else {{
        document.getElementById('logStatus').textContent = 'Erro ao gerar briefing';
      }}
    }}
  }}, 1500);
}}

carregarStatus();
setInterval(carregarStatus, 15000);
(async () => {{
  const d = await (await fetch('/api/log')).json();
  if(d.rodando) {{ _linhasVistas=0; iniciarPolling?.(); }}
}})();
</script>

<script>
function toggleFullscreen() {{
  if (!document.fullscreenElement) {{
    document.documentElement.requestFullscreen().catch(err => {{
      console.log('Fullscreen não suportado:', err);
    }});
  }} else {{
    document.exitFullscreen();
  }}
}}
document.addEventListener('keydown', e => {{
  if (e.key === 'F' || e.key === 'f') {{
    e.preventDefault();
    toggleFullscreen();
  }}
}});
</script>

</body>
</html>"""


# ── Início ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ATALAIA ComSoc — Interface Web")
    parser.add_argument("--port", type=int, default=9001, help="Porta (padrão: 9001)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (padrão: 0.0.0.0)")
    args = parser.parse_args()

    ip = _ip_local()
    print("\n" + "═"*56)
    print("  ATALAIA ComSoc — Interface Web Central")
    print(f"  Local:  http://127.0.0.1:{args.port}")
    print(f"  Rede:   http://{ip}:{args.port}  ← abra no celular")
    print("═"*56 + "\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
