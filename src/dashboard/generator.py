"""
DashboardHTMLGenerator (SPEC-12 — ADR-02).

Gera HTML autocontido e LEVE: os gráficos históricos (2024→) são montados a partir
de AGREGADOS MENSAIS compactos (não dos itens brutos); apenas os itens da janela
recente (padrão 90 dias) são embutidos, para a tabela de checagem, a nuvem e a busca.
Isso mantém o HTML < 2 MB mesmo com dezenas de milhares de matérias no histórico.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from src.dashboard.rollup_calculator import RollupCalculator
from src.memory.database import Database, MigrationRunner
from src.memory.repositories.items_repo import ItemsRepo
from src.memory.repositories.rollups_repo import RollupsRepo

log = logging.getLogger(__name__)

# Expressão de sentimento exibido (baseline CCOMSEx ou IA quando houver) + JOIN
_SENT = "COALESCE(a.sentimento_ia, i.sentimento, 'NA')"
_JOIN = (
    "FROM items i "
    "LEFT JOIN analise_ia a ON a.item_id = i.id "
    "AND a.created_at = (SELECT MAX(created_at) FROM analise_ia WHERE item_id = i.id)"
)
TOP_VEIC = 15
TOP_ASSU = 15
MAX_ITENS_RECENTES = 8000


class DadosDashboard(BaseModel):
    gerado: str
    total: int
    janela: int
    mes_data: list[dict]    # por mês: n, val, pub, veic, pos, neu, neg, na
    mes_sent: list[dict]    # por (mês, sentimento): n, val, pub
    veic_mes: list[dict]    # por (mês, veículo top-N): pos, neu, neg, na
    assu_mes: list[dict]    # por (mês, assunto top-N): pos, neu, neg, na
    uf_mes: list[dict]      # por (mês, uf): n
    midia_mes: list[dict]   # por (mês, mídia): n
    itens: list[dict]       # janela recente — tabela/nuvem/busca
    anos: list[str]


class DashboardHTMLGenerator:
    def __init__(
        self,
        db: Database,
        rollups_repo: RollupsRepo,
        items_repo: ItemsRepo,
        janela_dias: int = 90,
    ) -> None:
        self._db = db
        self._rollups = rollups_repo
        self._items = items_repo
        self._janela = janela_dias

    def gerar(self, destino: Path) -> Path:
        # mantém os rollups persistidos atualizados (consumidos por outros canais)
        RollupCalculator(self._db, self._rollups).recalcular_todos()
        dados = self._montar_dados()
        html = self._renderizar(dados)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(html, encoding="utf-8")
        log.info(
            "dashboard.gerado",
            extra={"dados": {
                "path": str(destino),
                "total": dados.total,
                "itens_recentes": len(dados.itens),
                "bytes": len(html),
            }},
        )
        return destino

    # ── montagem de dados (agregados mensais + janela recente) ────────────────

    def _q(self, sql: str, params: tuple = ()) -> list:
        return self._db.executar(sql, params).fetchall()

    def _montar_dados(self) -> DadosDashboard:
        total = self._q("SELECT COUNT(*) n FROM items")[0]["n"]

        mes_data = [dict(r) for r in self._q(
            f"""SELECT substr(i.data_pub,1,7) ym, COALESCE(i.fonte_trilha,'A') trilha, COUNT(*) n,
                   COALESCE(SUM(i.valor),0) val, COALESCE(SUM(i.publico),0) pub,
                   COUNT(DISTINCT i.veiculo) veic,
                   SUM(CASE WHEN {_SENT}='POSITIVA' THEN 1 ELSE 0 END) pos,
                   SUM(CASE WHEN {_SENT}='NEUTRA'   THEN 1 ELSE 0 END) neu,
                   SUM(CASE WHEN {_SENT}='NEGATIVA' THEN 1 ELSE 0 END) neg,
                   SUM(CASE WHEN {_SENT}='NA'       THEN 1 ELSE 0 END) na
                {_JOIN}
                WHERE i.data_pub IS NOT NULL
                GROUP BY ym, trilha ORDER BY ym""")]

        mes_sent = [dict(r) for r in self._q(
            f"""SELECT substr(i.data_pub,1,7) ym, COALESCE(i.fonte_trilha,'A') trilha,
                   {_SENT} sent, COUNT(*) n,
                   COALESCE(SUM(i.valor),0) val, COALESCE(SUM(i.publico),0) pub
                {_JOIN}
                WHERE i.data_pub IS NOT NULL
                GROUP BY ym, trilha, sent""")]

        veic_mes = self._cat_mes("i.veiculo", TOP_VEIC, filtro="i.veiculo <> ''")
        assu_mes = self._assu_mes(TOP_ASSU)
        uf_mes = [dict(r) for r in self._q(
            """SELECT substr(data_pub,1,7) ym, COALESCE(fonte_trilha,'A') trilha,
                   COALESCE(NULLIF(uf,''),'(s/ UF)') chave, COUNT(*) n
               FROM items WHERE data_pub IS NOT NULL GROUP BY ym, trilha, chave""")]
        midia_mes = [dict(r) for r in self._q(
            """SELECT substr(data_pub,1,7) ym, COALESCE(fonte_trilha,'A') trilha,
                   COALESCE(NULLIF(midia,''),'(s/ mídia)') chave, COUNT(*) n
               FROM items WHERE data_pub IS NOT NULL GROUP BY ym, trilha, chave""")]

        corte = (date.today() - timedelta(days=self._janela)).isoformat()
        itens = [dict(r) for r in self._q(
            f"""SELECT substr(i.data_pub,1,10) data, COALESCE(i.titulo,'') titulo,
                   COALESCE(i.link_original,i.url_clip,'') link, COALESCE(i.veiculo,'') veiculo,
                   COALESCE(i.uf,'') uf, COALESCE(i.midia,'') midia, {_SENT} sent,
                   COALESCE(i.valor,0) valor, COALESCE(i.publico,0) publico,
                   COALESCE(i.assunto,'') assunto, i.fonte_trilha trilha
                {_JOIN}
                WHERE i.data_pub >= ? AND i.titulo <> ''
                ORDER BY i.data_pub DESC, i.id DESC LIMIT ?""",
            (corte, MAX_ITENS_RECENTES))]

        anos = sorted({r["ym"][:4] for r in mes_data if r["ym"]})

        return DadosDashboard(
            gerado=datetime.now().strftime("%d/%m/%Y %H:%M"),
            total=total, janela=self._janela,
            mes_data=mes_data, mes_sent=mes_sent,
            veic_mes=veic_mes, assu_mes=assu_mes, uf_mes=uf_mes, midia_mes=midia_mes,
            itens=itens, anos=anos,
        )

    def _cat_mes(self, expr: str, top: int, filtro: str) -> list[dict]:
        """Top-N categorias (por total) com breakdown de sentimento por mês."""
        tops = [r["chave"] for r in self._q(
            f"SELECT {expr} chave, COUNT(*) n {_JOIN} WHERE {filtro} "
            f"GROUP BY {expr} ORDER BY n DESC LIMIT ?", (top,))]
        if not tops:
            return []
        ph = ",".join("?" * len(tops))
        return [dict(r) for r in self._q(
            f"""SELECT substr(i.data_pub,1,7) ym, COALESCE(i.fonte_trilha,'A') trilha, {expr} chave,
                   SUM(CASE WHEN {_SENT}='POSITIVA' THEN 1 ELSE 0 END) pos,
                   SUM(CASE WHEN {_SENT}='NEUTRA'   THEN 1 ELSE 0 END) neu,
                   SUM(CASE WHEN {_SENT}='NEGATIVA' THEN 1 ELSE 0 END) neg,
                   SUM(CASE WHEN {_SENT}='NA'       THEN 1 ELSE 0 END) na
                {_JOIN}
                WHERE i.data_pub IS NOT NULL AND {expr} IN ({ph})
                GROUP BY ym, trilha, chave""", tuple(tops))]

    def _assu_mes(self, top: int) -> list[dict]:
        """Top-N assuntos (via item_assuntos) com breakdown por mês."""
        tops = [r["chave"] for r in self._q(
            f"""SELECT ia.assunto chave, COUNT(*) n
                FROM item_assuntos ia JOIN items i ON i.id=ia.item_id
                WHERE ia.assunto <> '' GROUP BY ia.assunto ORDER BY n DESC LIMIT ?""", (top,))]
        if not tops:
            return []
        ph = ",".join("?" * len(tops))
        return [dict(r) for r in self._q(
            f"""SELECT substr(i.data_pub,1,7) ym, COALESCE(i.fonte_trilha,'A') trilha,
                   ia.assunto chave,
                   SUM(CASE WHEN {_SENT}='POSITIVA' THEN 1 ELSE 0 END) pos,
                   SUM(CASE WHEN {_SENT}='NEUTRA'   THEN 1 ELSE 0 END) neu,
                   SUM(CASE WHEN {_SENT}='NEGATIVA' THEN 1 ELSE 0 END) neg,
                   SUM(CASE WHEN {_SENT}='NA'       THEN 1 ELSE 0 END) na
                FROM item_assuntos ia
                JOIN items i ON i.id=ia.item_id
                LEFT JOIN analise_ia a ON a.item_id=i.id
                    AND a.created_at=(SELECT MAX(created_at) FROM analise_ia WHERE item_id=i.id)
                WHERE i.data_pub IS NOT NULL AND ia.assunto IN ({ph})
                GROUP BY ym, trilha, ia.assunto""", tuple(tops))]

    # ── renderização ──────────────────────────────────────────────────────────

    def _renderizar(self, dados: DadosDashboard) -> str:
        dados_json = json.dumps(dados.model_dump(), ensure_ascii=False, default=str)
        dados_json = dados_json.replace("<", "\\u003c")  # impede </script> em títulos
        anos_opts = "".join(f'<option value="{a}">{a}</option>' for a in dados.anos)

        chartjs_path = Path(__file__).parent / "assets" / "chartjs.min.js"
        if chartjs_path.exists():
            chartjs_tag = f"<script>{chartjs_path.read_text(encoding='utf-8')}</script>"
        else:
            chartjs_tag = '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>'

        return (_HTML_TEMPLATE
                .replace("__CHARTJS__", chartjs_tag)
                .replace("__ANOS_OPTS__", anos_opts)
                .replace("__DADOS_JSON__", dados_json))


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ATALAIA ComSoc — Síntese de Notícias</title>
__CHARTJS__
<style>
:root{
  --bg:#050908;--panel:rgba(12,24,21,.72);--panel2:rgba(20,38,34,.88);
  --line:rgba(116,255,190,.18);--line-strong:rgba(116,255,190,.42);
  --text:#e8fff4;--muted:#9bb6aa;
  --green:#2eff8a;--yellow:#ffd84a;--red:#ff3b3b;--cyan:#4bdcff;--blue:#5b8cff;--orange:#ff8a2a;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",Roboto,Arial,sans-serif;font-size:14px}
body::before{content:"";position:fixed;inset:0;z-index:-4;background:
  radial-gradient(circle at 12% 16%,rgba(46,255,138,.10),transparent 30%),
  radial-gradient(circle at 84% 8%,rgba(75,220,255,.09),transparent 30%),
  linear-gradient(rgba(46,255,138,.025) 1px,transparent 1px),
  linear-gradient(90deg,rgba(46,255,138,.025) 1px,transparent 1px);
  background-size:auto,auto,42px 42px,42px 42px}
.wrap{max-width:1380px;margin:0 auto;padding:22px}
header{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:1px solid var(--line-strong);padding-bottom:14px;margin-bottom:18px;flex-wrap:wrap;gap:10px}
header h1{margin:0;font-size:22px;letter-spacing:3px;text-transform:uppercase;text-shadow:0 0 18px rgba(46,255,138,.35)}
header h1 span{color:var(--green)}
.sub{color:var(--muted);font-size:12px;margin-top:4px;letter-spacing:.4px}
.meta{text-align:right;color:var(--muted);font-size:12px;line-height:1.8}
.meta b{color:var(--text)}
.filters{display:flex;gap:14px;align-items:center;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:18px}
.filters .fg{display:flex;flex-direction:column;gap:3px}
.filters label{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}
.filters select{background:#0a1512;border:1px solid var(--line-strong);color:var(--text);border-radius:7px;padding:7px 12px;font-size:13px;min-width:120px}
.clearbtn{margin-left:auto;background:rgba(46,255,138,.08);border:1px solid var(--line-strong);color:var(--green);border-radius:7px;padding:7px 16px;font-size:12px;cursor:pointer;text-transform:uppercase;letter-spacing:1px}
.clearbtn:hover{background:rgba(46,255,138,.18)}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:16px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpi .v{font-size:22px;font-weight:700;text-shadow:0 0 12px rgba(46,255,138,.2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .l{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.8px;margin-top:4px}
.kpi.green .v{color:var(--green)}.kpi.cyan .v{color:var(--cyan)}.kpi.yellow .v{color:var(--yellow)}.kpi.red .v{color:var(--red)}
.grid{display:grid;gap:16px;margin-bottom:16px}
.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:1fr 1fr 1fr}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.card h2{margin:0 0 12px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted)}
.card h2 em{color:var(--text);font-style:normal}
.chart-box{position:relative;height:280px}
.chart-box.tall{height:360px}
.cloud{display:flex;flex-wrap:wrap;gap:5px 12px;align-items:center;justify-content:center;padding:12px 6px;line-height:1.5;min-height:120px}
.cloud span{color:var(--muted);cursor:default;transition:color .12s}
.cloud span:hover{color:var(--green)}
.toolbar{display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.toolbar input{flex:1;min-width:200px;background:#0a1512;border:1px solid var(--line);color:var(--text);border-radius:7px;padding:7px 10px;font-size:13px}
.cnt{color:var(--muted);font-size:12px}
.tscroll{max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
thead th{position:sticky;top:0;background:var(--panel2);text-align:left;padding:9px 10px;border-bottom:1px solid var(--line-strong);color:var(--muted);text-transform:uppercase;font-size:11px;letter-spacing:.4px;cursor:pointer;white-space:nowrap;user-select:none}
thead th:hover{color:var(--text)}
tbody td{padding:8px 10px;border-bottom:1px solid rgba(116,255,190,.08);vertical-align:top}
tbody tr:hover{background:rgba(46,255,138,.04)}
.tit{min-width:260px;max-width:400px}
.tit a{color:var(--text);text-decoration:none}.tit a:hover{color:var(--green);text-decoration:underline}
.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:2px 8px;border-radius:16px;font-size:11px;font-weight:600;white-space:nowrap}
.b-POSITIVA{background:rgba(46,255,138,.14);color:var(--green);border:1px solid rgba(46,255,138,.4)}
.b-NEGATIVA{background:rgba(255,59,59,.14);color:#ff7676;border:1px solid rgba(255,59,59,.4)}
.b-NEUTRA{background:rgba(255,216,74,.14);color:var(--yellow);border:1px solid rgba(255,216,74,.4)}
.b-NA{background:rgba(155,182,170,.10);color:var(--muted);border:1px solid var(--line)}
.tnote{color:var(--muted);font-size:11px;margin-top:8px}
footer{color:var(--muted);font-size:11px;text-align:center;margin:24px 0 8px;letter-spacing:.4px}
@media(max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)}.g3{grid-template-columns:1fr 1fr}}
@media(max-width:740px){.kpis{grid-template-columns:repeat(2,1fr)}.g2,.g3{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1><span>Atalaia</span> ComSoc &mdash; Síntese de Notícias</h1>
      <div class="sub">Monitoramento e análise do cenário informacional &middot; Comunicação Social do Exército</div>
    </div>
    <div class="meta">Gerado em <b id="mGerado"></b><br>Histórico no banco: <b id="mTotal"></b> matérias</div>
  </header>

  <div class="filters">
    <div class="fg"><label>Ano</label>
      <select id="fAno"><option value="">Todos</option>__ANOS_OPTS__</select></div>
    <div class="fg"><label>Mês</label>
      <select id="fMes">
        <option value="">Todos</option>
        <option value="01">Jan</option><option value="02">Fev</option><option value="03">Mar</option>
        <option value="04">Abr</option><option value="05">Mai</option><option value="06">Jun</option>
        <option value="07">Jul</option><option value="08">Ago</option><option value="09">Set</option>
        <option value="10">Out</option><option value="11">Nov</option><option value="12">Dez</option>
      </select></div>
    <div class="fg"><label>Sentimento</label>
      <select id="fSent">
        <option value="">Todos</option>
        <option value="POSITIVA">Positiva</option>
        <option value="NEUTRA">Neutra</option>
        <option value="NEGATIVA">Negativa</option>
        <option value="NA">Sem classif.</option>
      </select></div>
    <div class="fg"><label>Tipo de Notícia</label>
      <select id="fTipo">
        <option value="">Todos</option>
        <option value="A">CCOMSEx (Trilha A)</option>
        <option value="B">Tempo Real (Trilha B)</option>
      </select></div>
    <button class="clearbtn" id="fClear">&#x2715; Limpar</button>
  </div>

  <div class="kpis" id="kpis"></div>

  <div class="grid g2">
    <div class="card"><h2><em>Análise qualitativa</em> (sentimento)</h2><div class="chart-box"><canvas id="cDonut"></canvas></div></div>
    <div class="card"><h2><em>Histórico mensal</em> (matérias por sentimento)</h2><div class="chart-box"><canvas id="cSerie"></canvas></div></div>
  </div>

  <div class="grid g2">
    <div class="card"><h2>Top <em>veículos</em> por sentimento</h2><div class="chart-box tall"><canvas id="cVeic"></canvas></div></div>
    <div class="card"><h2>Top <em>assuntos</em> por sentimento</h2><div class="chart-box tall"><canvas id="cAssu"></canvas></div></div>
  </div>

  <div class="grid g2">
    <div class="card"><h2>Por <em>UF</em></h2><div class="chart-box"><canvas id="cUF"></canvas></div></div>
    <div class="card"><h2>Por <em>tipo de mídia</em></h2><div class="chart-box"><canvas id="cMidia"></canvas></div></div>
  </div>

  <div class="grid">
    <div class="card"><h2>Nuvem de palavras <em>(janela recente)</em></h2><div class="cloud" id="cloud"></div></div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Lista de checagem <em>(janela recente)</em></h2>
      <div class="toolbar">
        <input id="q" placeholder="Filtrar por título, veículo, assunto, UF...">
        <span class="cnt" id="cnt"></span>
      </div>
      <div class="tscroll"><table id="tbl">
        <thead><tr>
          <th data-k="data">Data</th><th data-k="titulo">Título</th><th data-k="veiculo">Veículo</th>
          <th data-k="uf">UF</th><th data-k="midia">Mídia</th><th data-k="sent">Sentimento</th>
          <th data-k="valor">Valor (R$)</th><th data-k="publico">Público</th><th data-k="assunto">Assunto</th>
        </tr></thead><tbody></tbody>
      </table></div>
      <div class="tnote" id="tnote"></div>
    </div>
  </div>

  <footer>ATALAIA ComSoc &middot; gráficos históricos por agregados mensais &middot; tabela e nuvem na janela recente &middot; sem dependência de internet</footer>
</div>

<script>
const D = __DADOS_JSON__;
const C={pos:'#2eff8a',neu:'#ffd84a',neg:'#ff3b3b',na:'#3a4b46',cyan:'#4bdcff',blue:'#5b8cff',grid:'rgba(116,255,190,.10)',muted:'#9bb6aa'};
const MESES=['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
const STOP=new Set("a o e de da do das dos no na nos nas em um uma para por com sem sob sobre ao aos os as ou mas como mais menos ja nao sim entre ate seu sua que se foi sao tem apos contra desde pela pelo num numa the of to and in for on is at by an be it cmt ex eb".split(' '));
Chart.defaults.color=C.muted;Chart.defaults.font.family="Inter,'Segoe UI',Roboto,Arial,sans-serif";Chart.defaults.borderColor=C.grid;
const fmtInt=n=>(Math.round(n)||0).toLocaleString('pt-BR');
const fmtBRL=n=>(n||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0});
const fmtC=n=>{n=n||0;if(n>=1e9)return(n/1e9).toFixed(1)+'B';if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(1)+'k';return''+n;};

document.getElementById('mGerado').textContent=D.gerado;
document.getElementById('mTotal').textContent=fmtInt(D.total);

const F={ano:'',mes:'',sent:'',tipo:''};
const ymOK=ym=>(!F.ano||ym.slice(0,4)===F.ano)&&(!F.mes||ym.slice(5,7)===F.mes);
const rowOK=r=>ymOK(r.ym)&&(!F.tipo||r.trilha===F.tipo);
const CH={};
function chart(id,cfg){if(CH[id])CH[id].destroy();CH[id]=new Chart(document.getElementById(id),cfg);}

// agrega [{chave,pos,neu,neg,na}] por chave dentro do escopo de mês, devolve top N
function aggCat(rows,n){
  const m=new Map();
  rows.filter(r=>rowOK(r)).forEach(r=>{
    const o=m.get(r.chave)||{pos:0,neu:0,neg:0,na:0};
    o.pos+=r.pos;o.neu+=r.neu;o.neg+=r.neg;o.na+=r.na;m.set(r.chave,o);
  });
  return [...m.entries()].map(([k,o])=>({k,...o,t:o.pos+o.neu+o.neg+o.na}))
         .sort((a,b)=>b.t-a.t).slice(0,n);
}
function aggKey(rows,n){
  const m=new Map();
  rows.filter(r=>rowOK(r)).forEach(r=>m.set(r.chave,(m.get(r.chave)||0)+r.n));
  return [...m.entries()].map(([k,v])=>({k,v})).sort((a,b)=>b.v-a.v).slice(0,n);
}

function update(){
  // ── KPIs ──
  let total=0,valor=0,pub=0,pos=0,neu=0,neg=0,na=0,veic=0,meses=0;
  if(F.sent){
    D.mes_sent.filter(r=>rowOK(r)&&r.sent===F.sent).forEach(r=>{total+=r.n;valor+=r.val;pub+=r.pub;});
  }else{
    D.mes_data.filter(r=>rowOK(r)).forEach(r=>{total+=r.n;valor+=r.val;pub+=r.pub;pos+=r.pos;neu+=r.neu;neg+=r.neg;na+=r.na;veic+=r.veic;meses++;});
  }
  const pct=total?Math.round((F.sent==='POSITIVA'?total:pos)/total*100):0;
  const veicTxt=F.sent?'—':(meses>1?'~'+fmtInt(veic):fmtInt(veic));
  document.getElementById('kpis').innerHTML=[
    {l:'Matérias',v:fmtInt(total)},
    {l:F.sent?('% '+F.sent.toLowerCase()):'% Positivas',v:(F.sent&&F.sent!=='POSITIVA'?'100%':pct+'%'),c:'green'},
    {l:'Valor de mídia',v:fmtBRL(valor),c:'green'},
    {l:'Público',v:fmtC(pub),c:'cyan'},
    {l:'Veículos distintos',v:veicTxt},
    {l:'Meses no recorte',v:fmtInt(F.sent?D.mes_sent.filter(r=>rowOK(r)&&r.sent===F.sent).length:meses)},
  ].map(k=>`<div class="kpi ${k.c||''}"><div class="v">${k.v}</div><div class="l">${k.l}</div></div>`).join('');

  // ── Donut (composição de sentimento; ignora filtro de sentimento) ──
  let dp=0,dn=0,dg=0,da=0;
  D.mes_data.filter(r=>rowOK(r)).forEach(r=>{dp+=r.pos;dn+=r.neu;dg+=r.neg;da+=r.na;});
  chart('cDonut',{type:'doughnut',
    data:{labels:['Positiva','Neutra','Negativa','Sem classif.'],datasets:[{data:[dp,dn,dg,da],backgroundColor:[C.pos,C.neu,C.neg,C.na],borderColor:'#050908',borderWidth:3}]},
    options:{cutout:'62%',plugins:{legend:{position:'bottom',labels:{padding:12,usePointStyle:true}},
      tooltip:{callbacks:{label:c=>{const t=c.dataset.data.reduce((a,b)=>a+b,0)||1;return ` ${c.label}: ${fmtInt(c.parsed)} (${Math.round(c.parsed/t*100)}%)`;}}}}}});

  // ── Série mensal empilhada ──
  const yms=[...new Set(D.mes_sent.filter(r=>rowOK(r)).map(r=>r.ym))].sort();
  const byYm=s=>yms.map(ym=>{const r=D.mes_sent.find(x=>x.ym===ym&&x.sent===s);return r?r.n:0;});
  chart('cSerie',{type:'bar',
    data:{labels:yms.map(ym=>{const[y,m]=ym.split('-');return MESES[+m]+'/'+y.slice(2);}),datasets:[
      {label:'Positiva',data:byYm('POSITIVA'),backgroundColor:C.pos,stack:'s'},
      {label:'Neutra',data:byYm('NEUTRA'),backgroundColor:C.neu,stack:'s'},
      {label:'Negativa',data:byYm('NEGATIVA'),backgroundColor:C.neg,stack:'s'}]},
    options:{plugins:{legend:{position:'bottom',labels:{usePointStyle:true,padding:10}}},
      scales:{x:{stacked:true,grid:{display:false},ticks:{maxRotation:0,autoSkip:true}},y:{stacked:true,beginAtZero:true,grid:{color:C.grid}}}}});

  // ── Top veículos / assuntos (empilhado; respeita filtro de sentimento) ──
  function stacked(id,rows){
    const top=aggCat(rows,15);
    const ds=F.sent
      ?[{label:F.sent[0]+F.sent.slice(1).toLowerCase(),data:top.map(r=>r[F.sent.toLowerCase()==='positiva'?'pos':F.sent.toLowerCase()==='neutra'?'neu':F.sent.toLowerCase()==='negativa'?'neg':'na']),backgroundColor:F.sent==='POSITIVA'?C.pos:F.sent==='NEUTRA'?C.neu:F.sent==='NEGATIVA'?C.neg:C.na,stack:'s'}]
      :[{label:'Positiva',data:top.map(r=>r.pos),backgroundColor:C.pos,stack:'s'},
        {label:'Neutra',data:top.map(r=>r.neu),backgroundColor:C.neu,stack:'s'},
        {label:'Negativa',data:top.map(r=>r.neg),backgroundColor:C.neg,stack:'s'}];
    chart(id,{type:'bar',data:{labels:top.map(r=>r.k),datasets:ds},
      options:{indexAxis:'y',plugins:{legend:{position:'bottom',labels:{usePointStyle:true,padding:10}}},
        scales:{x:{stacked:true,beginAtZero:true,grid:{color:C.grid}},y:{stacked:true,grid:{display:false},ticks:{autoSkip:false,font:{size:11}}}}}});
  }
  stacked('cVeic',D.veic_mes);
  stacked('cAssu',D.assu_mes);

  // ── UF / Mídia ──
  const uf=aggKey(D.uf_mes,12);
  chart('cUF',{type:'bar',data:{labels:uf.map(x=>x.k),datasets:[{data:uf.map(x=>x.v),backgroundColor:C.cyan,borderRadius:3}]},
    options:{plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:C.grid}}}}});
  const md=aggKey(D.midia_mes,10);
  chart('cMidia',{type:'bar',data:{labels:md.map(x=>x.k),datasets:[{data:md.map(x=>x.v),backgroundColor:C.blue,borderRadius:3}]},
    options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:C.grid}},y:{grid:{display:false}}}}});

  // ── Nuvem + tabela (itens da janela recente) ──
  const itensF=D.itens.filter(i=>
    (!F.ano||(i.data||'').slice(0,4)===F.ano)&&
    (!F.mes||(i.data||'').slice(5,7)===F.mes)&&
    (!F.sent||i.sent===F.sent)&&
    (!F.tipo||i.trilha===F.tipo));
  const foraJanela=(F.ano||F.mes)&&itensF.length===0;
  const wc=new Map();
  itensF.forEach(i=>(i.titulo.toLowerCase().match(/[a-zà-ÿ]{3,}/g)||[]).forEach(w=>{if(!STOP.has(w))wc.set(w,(wc.get(w)||0)+1);}));
  const cloud=[...wc.entries()].sort((a,b)=>b[1]-a[1]).slice(0,60);const mx=Math.max(1,...cloud.map(c=>c[1]));
  document.getElementById('cloud').innerHTML=cloud.length
    ?cloud.map(([w,n])=>`<span style="font-size:${(12+n/mx*28).toFixed(0)}px;opacity:${(.55+n/mx*.45).toFixed(2)}" title="${n}">${w}</span>`).join('')
    :'<span>(sem itens na janela recente para este recorte)</span>';
  renderTabela(itensF,foraJanela);
}

let sortK=null,sortDir=1;
function renderTabela(rows,fora){
  const q=document.getElementById('q').value.toLowerCase();
  let r=q?rows.filter(x=>(x.titulo+' '+x.veiculo+' '+x.assunto+' '+x.uf).toLowerCase().includes(q)):rows.slice();
  if(sortK)r.sort((a,b)=>{let va=a[sortK],vb=b[sortK];if(typeof va==='number')return(va-vb)*sortDir;return String(va).localeCompare(String(vb),'pt-BR')*sortDir;});
  document.getElementById('cnt').textContent=`${r.length} matérias na janela`;
  document.querySelector('#tbl tbody').innerHTML=r.slice(0,1500).map(x=>{
    const link=x.link?`<a href="${x.link}" target="_blank" rel="noopener">${x.titulo||'(sem título)'}</a>`:(x.titulo||'');
    const ass=(x.assunto||'').replace(/\s*\n\s*/g,' · ').slice(0,80);
    return `<tr><td>${x.data||''}</td><td class="tit">${link}</td><td>${x.veiculo}</td><td>${x.uf}</td><td>${x.midia}</td><td><span class="badge b-${x.sent}">${x.sent}</span></td><td class="num">${x.valor?fmtInt(x.valor):''}</td><td class="num">${x.publico?fmtInt(x.publico):''}</td><td>${ass}</td></tr>`;
  }).join('');
  document.getElementById('tnote').textContent=fora
    ?'O recorte selecionado está fora da janela recente — os gráficos acima cobrem todo o histórico; para o detalhe das matérias deste período, use o export.'
    :(r.length>1500?`Exibindo 1.500 de ${r.length} (refine com a busca).`:'');
}

document.getElementById('fAno').onchange=e=>{F.ano=e.target.value;update();};
document.getElementById('fMes').onchange=e=>{F.mes=e.target.value;update();};
document.getElementById('fSent').onchange=e=>{F.sent=e.target.value;update();};
document.getElementById('fTipo').onchange=e=>{F.tipo=e.target.value;update();};
document.getElementById('fClear').onclick=()=>{F.ano=F.mes=F.sent=F.tipo='';fAno.value=fMes.value=fSent.value=fTipo.value='';update();};
document.getElementById('q').addEventListener('input',()=>update());
document.querySelectorAll('#tbl thead th').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.k;if(sortK===k)sortDir*=-1;else{sortK=k;sortDir=1;}update();}));
update();
</script>
</body>
</html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="ATALAIA ComSoc — Gerar Dashboard")
    ap.add_argument("--db", default="data/atalaia.db")
    ap.add_argument("--out", default="output/dashboard.html")
    ap.add_argument("--janela", type=int, default=90)
    args = ap.parse_args()

    Database._instance = None
    db = Database.inicializar(Path(args.db))
    MigrationRunner(db).aplicar_todas()

    gen = DashboardHTMLGenerator(
        db=db,
        rollups_repo=RollupsRepo(db),
        items_repo=ItemsRepo(db),
        janela_dias=args.janela,
    )
    destino = gen.gerar(Path(args.out))
    n = db.executar("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"Dashboard gerado: {destino}  ({n} itens no banco)")


if __name__ == "__main__":
    main()
