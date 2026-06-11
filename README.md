# ATALAIA ComSoc — Robô de Monitoramento e Análise de Mídia

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-app-009688)
![SQLite](https://img.shields.io/badge/db-SQLite-003B57)
![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)
![Status](https://img.shields.io/badge/status-MVP%20Fase%201-success)

Sistema automatizado de **monitoramento, consolidação e análise de mídia** com
classificação de sentimento, detecção de narrativas, dashboard HTML interativo e
geração de briefings — em duas trilhas (histórico de clipping + tempo real).

**Versão:** 1.0 (MVP — Fase 1) · **Stack:** Python · FastAPI · SQLite · LLM (OpenAI/DeepSeek)

---

## O que é

ATALAIA é um sistema automatizado de monitoramento, consolidação e análise de mídia para a **comunicação social e análise de mídia institucional**.

Funciona em **duas trilhas paralelas:**

| Trilha | Fonte | O que faz | IA? |
|--------|-------|----------|-----|
| **A — Histórico** | Planilha de clipping (.xlsx) | ETL → normaliza → deduplica → SQLite | ❌ Não |
| **B — Tempo Real** | Google News RSS (6 queries) | Coleta → deduplica → **análise IA** (sentimento, narrativa, risco) | ✅ Sim |

**Saídas:**
- 📊 **Dashboard HTML** interativo (histórico + filtros)
- 📋 **Briefing IA** em 8 seções (síntese, cenários, diagnóstico, indicadores, atores, prospectiva, prescrição, notícias)
- 📱 **Export ZIP** para compartilhar em celular sem internet

---

## Começar em 5 Minutos

### 1. Clonar & Instalar

```bash
cd ~/Desktop
git clone <repo-url> projeto_comsoc_cmtEB
cd projeto_comsoc_cmtEB

# Criar ambiente Python
python3.11 -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate (Windows)

# Instalar dependências
pip install -r requirements.txt
```

### 2. Configurar Chaves API

```bash
cat > .env << 'EOF'
OPENAI_API_KEY=sk-proj-sua-chave-aqui
DEEPSEEK_API_KEY=sk-sua-chave-deepseek-aqui
EOF
```

Obter chaves:
- **OpenAI:** https://platform.openai.com/api-keys
- **DeepSeek:** https://platform.deepseek.com/api_keys

### 3. Inicializar Banco

```bash
python main.py run --help  # Verificar se tudo está ok

# Ou inicializar manualmente (SETUP.md seção 4.1)
```

### 4. Rodar Servidor

```bash
python app.py

# Acesse: http://localhost:9001
```

---

## Documentação Completa

| Documento | Para quem | Conteúdo |
|-----------|-----------|----------|
| **[PRD.md](docs/desenvolvimento/PRD.md)** | Stakeholders, Product Manager | Requisitos, casos de uso, métricas de sucesso |
| **[ARQUITETURA.md](docs/desenvolvimento/ARQUITETURA.md)** | Engenheiros, Arquitetos | Design técnico, banco de dados, fluxos de dados, stack |
| **[SETUP.md](docs/usuario/SETUP.md)** | DevOps, Desenvolvedores | Passo a passo para replicar sistema do zero |
| **[CLAUDE.md](CLAUDE.md)** | Colabs (desenvolvimento) | Regras de projeto, stack obrigatória, decisões fechadas |

---

## Funcionalidades

### ✅ Implemented (MVP)

- [x] Ingestão clipping (ETL → histórico)
- [x] Coleta Google News RSS (tempo real)
- [x] Análise IA com fallback (OpenAI → DeepSeek)
- [x] Deduplicação inteligente (content_hash + título normalizado)
- [x] Dashboard HTML interativo com filtros
- [x] Briefing IA em 8 seções (Pydantic estruturado)
- [x] Exportação HTML + ZIP (self-contained)
- [x] Interface web central (FastAPI)
- [x] Fullscreen + fontes grandes (para projeção)
- [x] Log estruturado + rastreamento de ciclos

### 🚀 Roadmap (Fase 2+)

- [ ] Hospedagem remota (EBNet/nuvem)
- [ ] Autenticação (OAuth2/SAML)
- [ ] Ollama local (análise sensível)
- [ ] Tavily/SerpAPI (cobertura expandida)
- [ ] WhatsApp semiautomático
- [ ] Busca semântica (sqlite-vec)
- [ ] Detecção de movimentos coordenados

---

## Arquitetura (Visão 30 segundos)

```
┌─────────────────────────────────────────┐
│     FastAPI Web Interface               │
│  (localhost:9001)                       │
│  ├─ Home (central com botões)          │
│  ├─ Dashboard (histórico + filtros)    │
│  ├─ Briefing (IA 8 seções)             │
│  └─ Export (HTML + ZIP)                │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼─────────────────┐  ┌─▼──────────────────┐
│  SQLite Database    │  │  IA Analysis       │
│  ├─ items (Trilha   │  │  (ReAct Loop)      │
│  │   A+B)           │  │  - Sentimento      │
│  ├─ analise_ia      │  │  - Narrativa       │
│  ├─ item_assuntos   │  │  - Risco           │
│  └─ ciclos_exec     │  │  - Prospectiva     │
└───┬─────────────────┘  └────────────────────┘
    │
┌───▼──────────────────────────────────────┐
│  Coleta & Processamento                  │
│  ├─ Google News RSS (6 queries)          │
│  ├─ Normaliza + Dedup + Relevância      │
│  └─ Persiste antes de analisar          │
└────────────────────────────────────────────┘
```

**Stack:** Python 3.11+, FastAPI, SQLite, Pydantic, feedparser, httpx, anthropic

---

## Fluxo de Uso Diário

### Cenário 1: Receber Planilha de clipping

```bash
# 1. Recebeu arquivo novo_clipping.xlsx
python main.py etl --planilha novo_clipping.xlsx --db data/atalaia.db

# 2. Atualizar dashboard
python main.py dashboard --db data/atalaia.db

# 3. Acessar: http://localhost:9001/dashboard
```

### Cenário 2: Gerar Briefing Diário

```bash
# 1. Abrir interface: http://localhost:9001
# 2. Clicar "Buscar Notícias" (coleta Trilha B)
# 3. Aguardar log "✓ Concluído"
# 4. Clicar "Gerar Briefing IA"
# 5. Aguardar "✓ Análise concluída"
# 6. Acessar: http://localhost:9001/briefing
# 7. Exportar: "⬇ Pacote completo (.zip)"
# 8. Compartilhar via email/WhatsApp/Dropbox
```

### Cenário 3: Apresentação em Reunião

```bash
# 1. Abrir: http://localhost:9001/dashboard
# 2. Selecionar filtros (ano/mês/sentimento)
# 3. Clicar "⛶ Fullscreen" (ou pressionar F)
# 4. Projetar em tela
# Fontes 18-20px → legível a 5 metros
```

---

## Requisitos do Sistema

### Obrigatório

- **Python:** 3.11 ou superior
- **OS:** macOS 13+, Linux (Ubuntu 22.04+), Windows 11 (WSL2)
- **Chaves API:** OpenAI e/ou DeepSeek
- **Internet:** Para coleta RSS e chamadas LLM
- **Porta:** 9001 (FastAPI)

### Opcional

- **Ollama:** Para análise local sem internet (Fase 2)
- **Tavily/SerpAPI:** Para cobertura expandida (Fase 2)
- **Servidor web:** Apache/Nginx (para hospedagem Fase 2)

---

## CLI Commands

```bash
# ETL: Ingerir planilha clipping
python main.py etl --planilha dados.xlsx --db data/atalaia.db

# Coleta + Análise (uma vez)
python main.py run --db data/atalaia.db

# Gerar Dashboard
python main.py dashboard --db data/atalaia.db --out dashboard.html

# Iniciar Servidor Web
python app.py
# Acessível em http://localhost:9001
```

---

## Testes

```bash
# Rodar todos
pytest -v

# Testar deduplicação
pytest tests/test_dedup.py -v

# Testar ETL
pytest tests/test_etl.py -v

# Com cobertura
pytest --cov=src tests/
```

---

## Segurança

✅ **Implementado:**
- Chaves API em `.env` (gitignored)
- SQL prepared statements (sem injection)
- HTML sanitizado (bleach)
- Fallback provider (OpenAI → DeepSeek)
- Logs estruturados (sem PII)

⚠️ **Fase 2:**
- Hospedagem com autenticação
- Suporte a Ollama (análise local para sensível)
- HTTPS/TLS

---

## Troubleshooting Rápido

| Erro | Solução |
|------|---------|
| `OPENAI_API_KEY not set` | Preencher `.env` com chaves |
| `Port 9001 already in use` | `lsof -ti:9001 \| xargs kill -9` |
| `Database is locked` | `rm data/atalaia.db-wal` + reiniciar |
| `LLM timeout` | Verificar internet / trocar provider |
| `Google News 302 redirect` | Já corrigido (`hl=pt-BR&gl=BR`) |

Mais: ver [SETUP.md § 13 — Troubleshooting](SETUP.md#13-troubleshooting)

---

## Estrutura do Projeto

```
projeto_comsoc_cmtEB/
├── app.py                  # FastAPI central
├── main.py                 # CLI entry point
├── config/
│   └── config.yaml         # Configurações
├── src/
│   ├── core/               # Database, config, lifecycle
│   ├── intake/             # ETL, RSS, coleta
│   ├── analysis/           # IA, sentiment, narrativa, risco
│   ├── providers/          # LLM (OpenAI, DeepSeek, Ollama)
│   ├── briefing/           # Gerador HTML briefing
│   ├── dashboard/          # Gerador HTML dashboard
│   └── utils/              # Dedup, datas, logging
├── tests/                  # Testes unitários
├── data/
│   └── atalaia.db          # SQLite (gitignored)
├── logs/                   # Logs estruturados
├── .env                    # Chaves API (gitignored)
├── README.md               # Este arquivo
├── PRD.md                  # Product Requirements
├── ARQUITETURA.md          # Design técnico
├── SETUP.md                # Guia de instalação
└── CLAUDE.md               # Regras de projeto
```

---

## Métricas de Sucesso

| Métrica | Meta | Status |
|---------|------|--------|
| Importação clipping | 100% de cobertura | ✅ |
| Deduplicação | ≥85% redução | ✅ |
| Latência coleta | < 5 min | ✅ |
| Latência briefing | < 90 seg | ✅ |
| Uptime | 99% | ✅ |
| Satisfação (feedback) | Briefing lido antes de ação | ⏳ Em validação |

---

## Próximas Ações

1. **Você está aqui:** MVP rodando em localhost
2. **Próximo:** Ler [SETUP.md](docs/usuario/SETUP.md) para replicar em outro ambiente
3. **Depois:** Ler [ARQUITETURA.md](docs/desenvolvimento/ARQUITETURA.md) para customizações
4. **Produção:** Fase 2 com hospedagem + auth

---

## Suporte & Contribuições

**Dúvidas técnicas:** Ver [SETUP.md § 13 — Troubleshooting](SETUP.md#13-troubleshooting)  
**Feedback PRD:** Cap/Você (EsIMEx)  
**Issues:** Abrir em GitHub / Jira  

---

## Licença & Confidencialidade

**Data de Criação:** 2026-06-07  
**Versão:** 1.0

---

**⚡ Rápido & Preciso: Este é ATALAIA.**

Comece em 5 min → [SETUP.md](docs/usuario/SETUP.md)
