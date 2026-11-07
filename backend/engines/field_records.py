"""Registos de terreno: visita à obra, registo diário e alteração pedida pelo cliente.

Funciona sem IA: o registo diário é interpretado por regras determinísticas e devolvido como
PROPOSTA. Nada é inventado (horas, quantidades); o que é ambíguo é sinalizado e só é guardado
depois de o utilizador confirmar.
"""
from __future__ import annotations

import re
import unicodedata

# ----------------------------------------------------------------------------- visita à obra

VISIT_SECTIONS = {
    "access": "Acessos (estacionamento, elevador, chaves, horários)",
    "demolitions": "Demolições e remoções",
    "protections": "Proteção de espaços (móveis, pavimentos, zonas habitadas)",
    "notes": "Notas gerais",
}
MEASURE_SOURCES = {"medido": "Medido no local", "planta": "Retirado da planta", "estimado": "Estimado (por confirmar)"}


def _txt(v, n=2000) -> str:
    return str(v or "").strip()[:n]


def clean_visit(body: dict) -> dict:
    measures = []
    for m in (body.get("measures") or [])[:200]:
        label = _txt(m.get("label"), 120)
        if not label:
            continue
        value = m.get("value")
        try:
            value = None if value in (None, "", "nao_sei") else float(value)
        except (TypeError, ValueError):
            value = None
        if value is not None and (value < 0 or value > 1e6):
            raise ValueError(f"Medida «{label}» fora dos limites.")
        src = m.get("source") if m.get("source") in MEASURE_SOURCES else "medido"
        measures.append({"label": label, "value": value, "unit": _txt(m.get("unit"), 12) or "m", "source": src})
    questions = []
    for q in (body.get("questions") or [])[:100]:
        text = _txt(q.get("text") if isinstance(q, dict) else q, 300)
        if text:
            questions.append({"text": text, "answered": bool(q.get("answered")) if isinstance(q, dict) else False,
                              "answer": _txt(q.get("answer"), 500) if isinstance(q, dict) else ""})
    return {
        "title": _txt(body.get("title"), 160) or "Visita à obra",
        "address": _txt(body.get("address"), 300),
        "client_name": _txt(body.get("client_name"), 160),
        "visit_date": _txt(body.get("visit_date"), 20),
        **{k: _txt(body.get(k)) for k in VISIT_SECTIONS},
        "measures": measures, "questions": questions,
    }


def visit_summary(v: dict) -> dict:
    """Resumo editável + lista do que falta confirmar (determinístico)."""
    lines = [f"Visita: {v.get('title')}" + (f" — {v['visit_date']}" if v.get("visit_date") else "")]
    if v.get("client_name") or v.get("address"):
        lines.append(" · ".join(x for x in (v.get("client_name"), v.get("address")) if x))
    for k, label in VISIT_SECTIONS.items():
        if v.get(k):
            lines.append(f"{label.split(' (')[0]}: {v[k]}")
    if v.get("measures"):
        lines.append("Medidas:")
        for m in v["measures"]:
            val = "por medir" if m["value"] is None else f"{m['value']:g} {m['unit']}"
            lines.append(f"- {m['label']}: {val} ({MEASURE_SOURCES[m['source']].lower()})")
    if v.get("photos"):
        lines.append(f"Fotografias: {len(v['photos'])}")

    missing = []
    if not v.get("address"):
        missing.append("Morada da obra")
    for m in v.get("measures") or []:
        if m["value"] is None:
            missing.append(f"Medida em falta: {m['label']}")
        elif m["source"] == "estimado":
            missing.append(f"Medida estimada a confirmar: {m['label']}")
    for q in v.get("questions") or []:
        if not q["answered"]:
            missing.append(f"Pergunta pendente: {q['text']}")
    for k in ("access", "protections"):
        if not v.get(k):
            missing.append(f"Não registado: {VISIT_SECTIONS[k].split(' (')[0].lower()}")
    return {"summary": "\n".join(lines), "to_confirm": missing}


# ----------------------------------------------------------------------------- registo diário

_NUM_WORDS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
              "sete": 7, "oito": 8, "nove": 9, "dez": 10}
_DONE_VERBS = ("coloc", "pint", "assent", "acab", "termin", "fiz", "fizemos", "mont", "instal", "reboc", "demol",
               "limp", "betum", "lix", "aplic", "lig", "pass", "abri", "fech", "subst", "repar", "comec")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _count(token: str) -> int | None:
    token = _norm(token)
    if token.isdigit():
        return int(token)
    return _NUM_WORDS.get(token)


def parse_daily(text: str) -> dict:
    """Proposta de registo diário a partir de uma frase. Nunca inventa horas nem quantidades."""
    raw = _txt(text, 3000)
    if not raw:
        raise ValueError("Escreva ou dite o que se passou hoje.")
    t = _norm(raw)
    ambiguous: list[str] = []

    workers = None
    m = re.search(r"\b(?:fomos|eramos|estivemos|estavamos|somos)\s+(\w+)", t) or re.search(r"\b(\w+)\s+(?:trabalhadores|pessoas|operarios|homens)\b", t)
    if m:
        workers = _count(m.group(1))
    if workers is None and re.search(r"\beu e (?:o|a)\s+\w+", t):
        workers = 2
    if workers is None and re.search(r"\b(?:fomos|eramos|estivemos)\b", t):
        ambiguous.append("Número de pessoas na equipa")
    elif workers is None:
        ambiguous.append("Número de pessoas na equipa (não indicado)")

    hours = None
    h = re.search(r"(\d{1,2})\s*(?:h|horas)\b(?!\s*(?:as|da|de))", t)
    span = re.search(r"das\s+(\d{1,2})(?:h|:\d{2})?\s*(?:h)?\s*(?:as|ate)\s+(\d{1,2})", t)
    if span:
        a, b = int(span.group(1)), int(span.group(2))
        if 0 <= a < b <= 24:
            hours = b - a
            ambiguous.append("Horas: calculadas pelo intervalo indicado — confirme se houve pausa")
    elif h:
        hours = int(h.group(1)) if 0 < int(h.group(1)) <= 24 else None

    missing = []
    for mm in re.finditer(r"\b(?:faltou|faltaram|falta|faltam|acabou|acabaram|ficamos sem|precisamos de)\s+(?:o |a |os |as |de |mais )?([^,.;]+)", t):
        item = mm.group(1).strip()
        item = re.split(r"\s+(?:e|mas|porque|para)\s+", item)[0].strip()
        if item and len(item) < 80:
            missing.append({"item": _restore(raw, item), "quantity": None})
    if missing:
        ambiguous.append("Quantidade dos materiais em falta (não indicada)")

    done = []
    for clause in _clauses(raw):
        n = _norm(clause).strip()
        if not n or any(n.startswith(p) for p in ("hoje fomos", "fomos", "eramos", "estivemos")):
            continue
        if re.search(r"\b(?:faltou|faltaram|falta|faltam|acabou|ficamos sem)\b", n):
            continue
        if any(re.search(rf"\b{v}\w*", n) for v in _DONE_VERBS):
            done.append(clause.strip()[:200])

    return {"workers": workers, "hours": hours, "work_done": done, "missing_materials": missing,
            "blockers": [], "ambiguous": ambiguous, "source_text": raw,
            "requires_confirmation": True}


def _clauses(raw: str) -> list[str]:
    """Divide por pontuação e por « e » apenas quando o que segue começa por um verbo
    (« pintámos a sala e o quarto » fica inteiro; « colocámos o chão e faltou cola » divide-se)."""
    out = []
    for part in re.split(r"[,.;\n]", raw):
        pieces = re.split(r"\s+e\s+", part)
        cur = pieces[0]
        for nxt in pieces[1:]:
            first = _norm(nxt).split(" ")[0] if nxt.strip() else ""
            if any(first.startswith(v) for v in _DONE_VERBS) or first.startswith(("falt", "acab", "ficam")):
                out.append(cur)
                cur = nxt
            else:
                cur = f"{cur} e {nxt}"
        out.append(cur)
    return out


def _restore(original: str, normalized_piece: str) -> str:
    """Devolve o excerto com acentos tal como foi escrito, quando encontrado."""
    o = original
    i = _norm(o).find(normalized_piece)
    return o[i:i + len(normalized_piece)] if i >= 0 else normalized_piece


def clean_daily(body: dict) -> dict:
    def opt_int(v, name, hi):
        if v in (None, ""):
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"«{name}»: indique um número.")
        if v < 0 or v > hi:
            raise ValueError(f"«{name}»: valor fora dos limites.")
        return v
    mats = []
    for m in (body.get("missing_materials") or [])[:50]:
        item = _txt(m.get("item") if isinstance(m, dict) else m, 120)
        if item:
            mats.append({"item": item, "quantity": _txt(m.get("quantity"), 40) if isinstance(m, dict) else ""})
    return {
        "date": _txt(body.get("date"), 20),
        "workers": opt_int(body.get("workers"), "Pessoas na equipa", 500),
        "hours": opt_int(body.get("hours"), "Horas", 24),
        "work_done": [_txt(x, 200) for x in (body.get("work_done") or [])[:50] if _txt(x, 200)],
        "missing_materials": mats,
        "blockers": [_txt(x, 200) for x in (body.get("blockers") or [])[:20] if _txt(x, 200)],
        "notes": _txt(body.get("notes"), 2000),
        "source_text": _txt(body.get("source_text"), 3000),
    }


# ----------------------------------------------------------------------------- alteração pedida pelo cliente

def change_impact(original_totals: dict, extra_lines_ht: float, delay_days) -> dict:
    """Impacto da alteração. O prazo só é indicado se o profissional o der (nunca estimado)."""
    base = float((original_totals or {}).get("ht") or 0)
    try:
        delay = None if delay_days in (None, "") else int(delay_days)
    except (TypeError, ValueError):
        delay = None
    return {"original_ht": round(base, 2), "extra_ht": round(extra_lines_ht, 2),
            "new_total_ht": round(base + extra_lines_ht, 2), "delay_days": delay,
            "delay_known": delay is not None}
