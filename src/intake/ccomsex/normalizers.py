"""Normalizers da Trilha A (SPEC-01 §3.2–3.7 + §6.9)."""
from __future__ import annotations

import hashlib
import re

import pandas as pd


def norm_header(h: str) -> str:
    """Normaliza cabeçalho: minúsculo, sem acento, espaços colapsados."""
    h = str(h).strip().lower()
    acentos = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçº°",
        "aaaaaeeeeiiiiooooouuuuc  ",
    )
    h = h.translate(acentos)
    return re.sub(r"\s+", " ", h).strip()


def br_number(v) -> float | None:
    """
    Converte número BR para float (SPEC-01 §3.3 — heurística corrigida).

    Regras:
    1. Há vírgula → vírgula é decimal, pontos são milhares.
    2. Só ponto(s) → se grupo após último ponto tem 3 dígitos exatos: milhar.
       Senão: ponto é decimal.
    3. Sem ponto nem vírgula → converte direto.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # remove prefixos monetários e caracteres não numéricos (exceto ponto e vírgula)
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    try:
        if "," in s:
            # vírgula presente → decimal BR
            s = s.replace(".", "").replace(",", ".")
        elif "." in s:
            # só ponto → verificar se é separador de milhar
            partes = s.split(".")
            if len(partes[-1]) == 3:
                # último grupo tem 3 dígitos → ponto é milhar
                s = s.replace(".", "")
            # senão: ponto já é decimal → não alterar
        return float(s)
    except ValueError:
        return None


def parse_date(v) -> str | None:
    """
    Converte data para ISO 8601 (SPEC-01 §3.4).

    Trata os dois formatos das fontes CCOMSEx:
    - clipping diário: string BR "DD/MM/YYYY[ HH:MM]" -> dayfirst=True
    - consolidada: datetime / string ISO "YYYY-MM-DD..." -> sem dayfirst
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        s = str(v).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):       # ISO -> não forçar dayfirst
            ts = pd.to_datetime(v, errors="coerce")
        else:                                         # BR -> dia primeiro
            ts = pd.to_datetime(v, dayfirst=True, errors="coerce")
        if pd.isna(ts):
            return None
        if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def norm_sentiment(v) -> str:
    """Padroniza sentimento CCOMSEx (SPEC-01 §3.5)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "NA"
    s = norm_header(str(v)).upper()
    # Verificar NEGATIVA antes de POSITIVA: "DESFAVORAV" contém "FAVORAV"
    if s.startswith("NEG") or "DESFAVORAV" in s:
        return "NEGATIVA"
    if s.startswith("POS") or "FAVORAV" in s:
        return "POSITIVA"
    if s.startswith("NEU"):
        return "NEUTRA"
    return "NA"


def split_assuntos(v) -> list[str]:
    """Quebra campo multivalorado Assunto (SPEC-01 §3.6)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    parts = re.split(r"[\n;,/]+", str(v))
    return [p.strip().upper() for p in parts if p.strip()]


def make_hash(row: dict) -> str:
    """
    SHA-256 de titulo+veiculo+data(dia)+link_original (SPEC-01 §3.7).

    Usa a data PARSEADA (só o dia, data_pub[:10]) em vez da string crua, para
    que a MESMA matéria deduplique entre a planilha consolidada (data só com o
    dia: "2024-01-01 00:00:00") e o clipping diário (data com hora:
    "26/05/2026 09:00"). Fallback para data_raw quando a data não parseou.
    """
    data_dia = (row.get("data_pub") or row.get("data_raw") or "")[:10]
    base = "|".join([
        str(row.get("titulo", "")).strip().lower(),
        str(row.get("veiculo", "")).strip().lower(),
        str(data_dia).strip().lower(),
        str(row.get("link_original", "")).strip().lower(),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def e_linha_rodape(row: dict) -> bool:
    """
    Filtro ESTRUTURAL de linhas de rodapé/totalização (SPEC-01 §6.9).

    Descarta se:
    - titulo normalizado == "total geral" (exato), OU
    - veiculo vazio E data_raw vazia E (valor > 0 OU publico > 0).

    NÃO descarta só por conter "total" no título — evita falsos positivos.
    """
    titulo_norm = norm_header(str(row.get("titulo", "")))
    if titulo_norm == "total geral":
        return True

    veiculo_vazio = not str(row.get("veiculo", "")).strip()
    data_vazia = not str(row.get("data_raw", "")).strip()
    tem_valor = bool(row.get("valor") or row.get("publico"))

    return veiculo_vazio and data_vazia and tem_valor
