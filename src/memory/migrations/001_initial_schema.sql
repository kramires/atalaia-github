-- 001_initial_schema.sql
-- Schema inicial ATALAIA ComSoc — Fase 1
-- Gerado conforme SPEC-04 §5 e ARCHITECTURE.md §5

-- ─────────────────────────────────────────────────────────────────────────────
-- ITENS (tabela unificada Trilha A + Trilha B)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash     TEXT    UNIQUE NOT NULL,
    fonte_trilha     TEXT    NOT NULL CHECK (fonte_trilha IN ('A','B')),
    fonte_id         TEXT,
    ciclo_id         TEXT,
    data_raw         TEXT,
    data_pub         TEXT,
    titulo           TEXT    NOT NULL DEFAULT '',
    url_clip         TEXT,
    link_original    TEXT,
    veiculo          TEXT,
    uf               TEXT,
    pais             TEXT,
    midia            TEXT,
    conteudo_texto   TEXT,
    tipo             TEXT,
    editoria         TEXT,
    mesorregiao      TEXT,
    municipio        TEXT,
    abrangencia      TEXT,
    espaco           TEXT,
    cm               REAL,
    seg              REAL,
    valor            REAL,
    publico          REAL,
    categoria        TEXT,
    maps             TEXT,
    tag_veiculo      TEXT,
    analise_qualitativa TEXT,
    sentimento       TEXT    CHECK (sentimento IN ('POSITIVA','NEGATIVA','NEUTRA','NA')),
    incluir_analise  TEXT,
    assunto          TEXT,
    relevance_score  REAL,
    pendente_analise INTEGER NOT NULL DEFAULT 0,
    source_file      TEXT,
    ingested_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_data_pub    ON items(data_pub);
CREATE INDEX IF NOT EXISTS idx_items_veiculo     ON items(veiculo);
CREATE INDEX IF NOT EXISTS idx_items_sentimento  ON items(sentimento);
CREATE INDEX IF NOT EXISTS idx_items_trilha      ON items(fonte_trilha);
CREATE INDEX IF NOT EXISTS idx_items_ciclo       ON items(ciclo_id);
CREATE INDEX IF NOT EXISTS idx_items_uf          ON items(uf);
CREATE INDEX IF NOT EXISTS idx_items_pendente    ON items(pendente_analise) WHERE pendente_analise = 1;

-- ─────────────────────────────────────────────────────────────────────────────
-- ASSUNTOS (1 linha por assunto por item)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS item_assuntos (
    item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    assunto  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assunto_item  ON item_assuntos(item_id);
CREATE INDEX IF NOT EXISTS idx_assunto_texto ON item_assuntos(assunto);

-- ─────────────────────────────────────────────────────────────────────────────
-- ANÁLISE IA (aditivo — nunca sobrescreve sentimento da Trilha A)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analise_ia (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id          INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    sentimento_ia    TEXT    NOT NULL CHECK (sentimento_ia IN ('POSITIVA','NEGATIVA','NEUTRA')),
    narrativa        TEXT,
    enquadramento    TEXT,
    risco            TEXT    CHECK (risco IN ('BAIXO','MEDIO','ALTO','CRITICO')),
    oportunidade     TEXT,
    confianca        REAL    NOT NULL CHECK (confianca BETWEEN 0.0 AND 1.0),
    tipo_inferencia  TEXT    NOT NULL CHECK (tipo_inferencia IN ('FATO','INTERPRETACAO','HIPOTESE')),
    evidencia        TEXT,
    provider         TEXT    NOT NULL,
    modelo           TEXT,
    ciclo_id         TEXT,
    created_at       TEXT    NOT NULL
);

-- impede duplicata por ciclo; JOIN usa MAX(created_at) para análise mais recente
CREATE UNIQUE INDEX IF NOT EXISTS idx_analise_item_ciclo
    ON analise_ia(item_id, COALESCE(ciclo_id, ''));
CREATE INDEX IF NOT EXISTS idx_analise_item  ON analise_ia(item_id);
CREATE INDEX IF NOT EXISTS idx_analise_ciclo ON analise_ia(ciclo_id);
CREATE INDEX IF NOT EXISTS idx_analise_risco ON analise_ia(risco);

-- ─────────────────────────────────────────────────────────────────────────────
-- FONTES (coletores registrados)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fontes (
    id              TEXT    PRIMARY KEY,
    nome            TEXT    NOT NULL,
    tipo            TEXT    NOT NULL CHECK (tipo IN
                      ('google_news_rss','google_alerts_rss','manual','search_api')),
    url             TEXT,
    ativo           INTEGER NOT NULL DEFAULT 1,
    trust_score     REAL    NOT NULL DEFAULT 0.7 CHECK (trust_score BETWEEN 0.0 AND 1.0),
    ultima_coleta   TEXT,
    ultimo_erro     TEXT,
    criado_em       TEXT    NOT NULL
);

-- ─────────────────────────────────────────────────────────────────────────────
-- CICLOS DE EXECUÇÃO
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ciclos_execucao (
    id                TEXT    PRIMARY KEY,
    iniciado_em       TEXT    NOT NULL,
    finalizado_em     TEXT,
    status            TEXT    NOT NULL CHECK (status IN
                        ('EXECUTANDO','COMPLETO','FALHA','DEGRADADO')),
    itens_coletados   INTEGER DEFAULT 0,
    itens_processados INTEGER DEFAULT 0,
    itens_relevantes  INTEGER DEFAULT 0,
    itens_acima_cap   INTEGER DEFAULT 0,
    briefing_id       TEXT,
    erro_msg          TEXT,
    duracao_ms        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_ciclos_status      ON ciclos_execucao(status);
CREATE INDEX IF NOT EXISTS idx_ciclos_iniciado_em ON ciclos_execucao(iniciado_em);

-- ─────────────────────────────────────────────────────────────────────────────
-- BRIEFINGS
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS briefings (
    id               TEXT    PRIMARY KEY,
    ciclo_id         TEXT    NOT NULL REFERENCES ciclos_execucao(id),
    gerado_em        TEXT    NOT NULL,
    periodo_inicio   TEXT,
    periodo_fim      TEXT,
    total_itens      INTEGER,
    itens_relevantes INTEGER,
    nivel_risco      TEXT    CHECK (nivel_risco IN ('BAIXO','MEDIO','ALTO','CRITICO')),
    parte1_md        TEXT,
    parte2_md        TEXT,
    parte1_html      TEXT,
    parte2_html      TEXT,
    status           TEXT    NOT NULL CHECK (status IN ('COMPLETO','DEGRADADO','FALHA')),
    provider_parte1  TEXT,
    provider_parte2  TEXT
);

CREATE INDEX IF NOT EXISTS idx_briefings_ciclo     ON briefings(ciclo_id);
CREATE INDEX IF NOT EXISTS idx_briefings_gerado_em ON briefings(gerado_em);

-- ─────────────────────────────────────────────────────────────────────────────
-- MÉTRICAS DE OBSERVABILIDADE
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metricas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ciclo_id      TEXT,
    componente    TEXT    NOT NULL,
    metrica       TEXT    NOT NULL,
    valor         REAL    NOT NULL,
    unidade       TEXT,
    registrado_em TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metricas_ciclo      ON metricas(ciclo_id);
CREATE INDEX IF NOT EXISTS idx_metricas_componente ON metricas(componente);

-- ─────────────────────────────────────────────────────────────────────────────
-- TRAÇOS DO AGENTE (audit trail simplificado — 1 linha por iteração)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tracos_agente (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ciclo_id      TEXT    NOT NULL,
    iteracao      INTEGER NOT NULL,
    pensamento    TEXT,
    acao          TEXT,
    acao_input    TEXT,
    observacao    TEXT,
    tokens_usados INTEGER,
    duracao_ms    INTEGER,
    created_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tracos_ciclo ON tracos_agente(ciclo_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- ROLLUPS DO DASHBOARD
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rollups_dashboard (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo               TEXT    NOT NULL CHECK (tipo IN
                         ('mes_resumo','mes_sentimento','veiculo','assunto','uf','midia')),
    chave              TEXT    NOT NULL,
    chave2             TEXT,
    fonte_trilha       TEXT    NOT NULL,
    contagem           INTEGER NOT NULL DEFAULT 0,
    valor_total        REAL    DEFAULT 0,
    publico_total      REAL    DEFAULT 0,
    veiculos_distintos INTEGER DEFAULT NULL,
    n_pos              INTEGER DEFAULT 0,
    n_neu              INTEGER DEFAULT 0,
    n_neg              INTEGER DEFAULT 0,
    n_na               INTEGER DEFAULT 0,
    atualizado_em      TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rollup_pk
    ON rollups_dashboard(tipo, chave, COALESCE(chave2,''), fonte_trilha);
CREATE INDEX IF NOT EXISTS idx_rollup_tipo ON rollups_dashboard(tipo);

-- ─────────────────────────────────────────────────────────────────────────────
-- CONTROLE DE MIGRATIONS
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_migrations (
    versao      TEXT PRIMARY KEY,
    aplicado_em TEXT NOT NULL,
    descricao   TEXT
);
