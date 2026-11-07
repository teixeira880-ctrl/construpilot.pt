"""Leitura de um pedido em linguagem corrente (pessoa sem conhecimentos técnicos).

Ex.: «quero uma casa térrea em L com 200 m2 habitáveis, piscina e garagem exterior, terreno de 1500 m2,
fachadas em granito e madeira, estilo contemporâneo, na Rua do Monte 7, Braga».

Só extrai o que está escrito; o que falta é decidido mais tarde pelos motores e registado como hipótese.
Cada área é classificada pelo contexto (terreno vs. casa) para nunca confundir as duas.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional

from engines.urbanismo_pt.auto import estilos as E

_NUM = r"(\d{1,3}(?:[ .]\d{3})+|\d+(?:[.,]\d+)?)"
_M2 = r"\s*(?:m\s?²|m2|m\^2|metros quadrados|metros2)"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _num(s: str) -> Optional[float]:
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+", s):
        s = re.sub(r"[ .]", "", s)
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def areas(texto: str) -> Dict[str, float]:
    """Classifica cada «N m²» pelo contexto próximo: terreno, área habitável (útil) ou área de construção."""
    t = texto or ""
    tn = _norm(t)
    out: Dict[str, float] = {}
    sem_rotulo = []
    classes = (("area_terreno_m2", r"terreno|lote|parcela|propriedade|quintal"),
               ("area_util_alvo_m2", r"habit|uteis|util\b|\bcasa\b|moradia|habitacao|vivenda"),
               ("area_construcao_alvo_m2", r"constru|bruta"))
    for m in re.finditer(_NUM + _M2, t, re.I):
        v = _num(m.group(1))
        if not v:
            continue
        depois = re.split(r",|;|\be\b|\bcom\b", tn[m.end():m.end() + 30])[0]
        antes = tn[max(0, m.start() - 45):m.start()]
        alvo = next((k for k, rx in classes if k != "area_util_alvo_m2" and re.search(rx, depois)), None) \
            or ("area_util_alvo_m2" if re.search(r"habit|uteis|util\b", depois) else None)
        if not alvo:   # palavra-chave mais próxima à esquerda
            melhor = -1
            for k, rx in classes:
                for mm in re.finditer(rx, antes):
                    if mm.start() > melhor:
                        melhor, alvo = mm.start(), k
        if alvo:
            out.setdefault(alvo, v)
        else:
            sem_rotulo.append(v)
    if sem_rotulo:   # compatibilidade: uma área sem contexto é a do terreno (comportamento anterior)
        if "area_terreno_m2" not in out:
            out["area_terreno_m2"] = sem_rotulo[0]
        elif "area_util_alvo_m2" not in out:
            out["area_util_alvo_m2"] = sem_rotulo[0]
    return out


def tipologia_por_area(area_util: float) -> str:
    """Tipologia corrente para uma área útil pedida (hipótese registada pelo pipeline)."""
    for lim, t in ((70, "T1"), (100, "T2"), (150, "T3"), (210, "T4"), (280, "T5")):
        if area_util < lim:
            return t
    return "T6"


def interpretar(texto: str) -> Dict[str, Any]:
    t = texto or ""
    n = _norm(t)
    out: Dict[str, Any] = {}
    m = re.search(r"\b[Tt]\s?([0-6])\b", t)
    if m:
        out["tipologia"] = f"T{m.group(1)}"
    else:
        m = re.search(r"\b(\d)\s*quartos?\b", n) or re.search(r"\b(um|dois|tres|quatro|cinco|seis)\s+quartos?\b", n)
        if m:
            w = {"um": 1, "dois": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6}
            k = int(m.group(1)) if m.group(1).isdigit() else w[m.group(1)]
            out["tipologia"] = f"T{max(0, min(6, k))}"
    if re.search(r"terrea|um so piso|1 piso|plain-pied|so rés-do-chao|so res-do-chao", n):
        out["pisos"] = 1
    elif re.search(r"\b(2|dois) pisos\b|\bandar\b|dois andares|r/c ?\+ ?1", n):
        out["pisos"] = 2
    # forma
    m = re.search(r"\b(?:em|forma(?: de)?|formato(?: de)?)\s+(?:de\s+)?([lut])\b", n)
    if m:
        out["forma"] = m.group(1)
    elif re.search(r"retangular|rectangular", n):
        out["forma"] = "retangulo"
    # garagem
    if re.search(r"sem garagem", n):
        out["garagem"] = False
    elif re.search(r"garagem", n):
        out["garagem"] = True
        if re.search(r"garagem\s+(?:\w+\s+){0,2}(exterior|independente|separada|isolada|a parte|destacada)", n):
            out["garagem_tipo"] = "exterior"
        elif re.search(r"garagem\s+(?:\w+\s+){0,2}(integrada|interior|incorporada|na casa)", n):
            out["garagem_tipo"] = "integrada"
        m = re.search(r"garagem\s+(?:para|de)\s+(\d|um|uma|dois|duas|tres)\s+(?:carro|viatura|lugar)", n)
        if m:
            w = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3}
            out["lugares"] = int(m.group(1)) if m.group(1).isdigit() else w[m.group(1)]
    # piscina
    if re.search(r"sem piscina", n):
        out["piscina"] = False
    elif re.search(r"piscina", n):
        out["piscina"] = True
        m = re.search(r"piscina\s+(?:de\s+)?(\d+(?:[.,]\d+)?)\s*(?:m\s*)?[x×]\s*(\d+(?:[.,]\d+)?)", n)
        if m:
            out["piscina_l_m"], out["piscina_w_m"] = _num(m.group(1)), _num(m.group(2))
    # fachada, cobertura, estilo
    mats = re.findall(r"(granito|madeira|xisto|tijolo|betao|reboco|branc[ao]|pedra|ripado)", n)
    if mats:
        out["fachada"] = " ".join(dict.fromkeys(mats))
    if re.search(r"cobertura plana|telhado plano|terraco na cobertura|acoteia", n):
        out["cobertura_tipo"] = "plana"
    elif re.search(r"telhado|telha|duas aguas|4 aguas|quatro aguas", n):
        out["cobertura_tipo"] = "duas_aguas"
    if re.search(r"telha preta|telha escura|ardosia", n):
        out["cobertura"] = "telha_preta"
    elif re.search(r"zinco|chapa", n):
        out["cobertura"] = "zinco"
    sem_morada = re.split(r"\b(?:na|no|em|sito em|situad[oa] em)\s+(?:rua|avenida|av\.|travessa|largo|estrada|caminho|lugar|"
                          r"praca|praça|urbaniza|quinta|bairro)\b", t, maxsplit=1, flags=re.I)[0]
    est = E.detectar(sem_morada)
    if est:
        out["estilo"] = est
    # obra
    if re.search(r"renova|reabilita|remodela|recupera", n):
        out["tipo_obra"] = "renovacao"
    elif re.search(r"amplia", n):
        out["tipo_obra"] = "ampliacao"
    out.update(areas(t))
    return out
