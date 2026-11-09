"""Medições efetivas, agrupamento, sugestões de artigos e orçamento a partir do BIM.

Cadeia: Modelo BIM → Elementos → Quantidades → Artigos (biblioteca) → Orçamento.

Princípios:
* Preços vêm SEMPRE da biblioteca da empresa (``library_items``) — nunca inventados.
* Quantidades vêm do motor (declarada/calculada/estimada) ou de correção manual.
  Só a validação humana marca uma quantidade como "verificada".
* Sugestões de associação são heurísticas explicáveis (palavras-chave + unidade)
  e ficam em estado "sugerida" até o utilizador confirmar.
* Elementos agregadores e excluídos nunca entram nas somas (sem contagem dupla).
"""
from __future__ import annotations

import re
import unicodedata

from bim_studio.constants import CATEGORIES, PRIMARY, QTY_LABELS

ORIGIN_LABELS = {
    "declared": "Declarada no modelo IFC", "calculated": "Calculada pela geometria",
    "estimated": "Estimada (aproximação)", "manual": "Corrigida manualmente",
}

# Unidade da biblioteca → chave de quantidade BIM
UNIT_TO_KEY = {"m²": "area", "m2": "area", "m³": "volume", "m3": "volume", "ml": "length", "m": "length",
               "u": "count", "un": "count", "ud": "count", "unid": "count", "kg": "weight"}

CATEGORY_WORDS = {
    "paredes": ["parede", "alvenaria", "divisoria", "bloco", "tijolo", "pladur", "gesso", "fachada"],
    "lajes": ["laje", "betao", "betonilha", "pavimento"],
    "pavimentos": ["pavimento", "ceramico", "flutuante", "parquet", "mosaico", "soalho", "betonilha"],
    "coberturas": ["cobertura", "telha", "telhado", "impermeabilizacao"],
    "portas": ["porta"], "janelas": ["janela", "caixilharia", "vidro", "porta-janela"],
    "pilares": ["pilar", "betao", "armado"], "vigas": ["viga", "betao", "armado", "perfil"],
    "escadas": ["escada", "degrau"], "revestimentos": ["revestimento", "azulejo", "reboco", "pintura", "teto"],
    "espacos": ["pintura", "pavimento", "teto"], "estrutura": ["sapata", "fundacao", "betao", "armado"],
    "fachadas": ["fachada", "caixilharia", "vidro"], "guardas": ["guarda", "corrimao"],
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def tokens(s: str) -> set[str]:
    return {t for t in norm(s).split() if len(t) > 2}


def unit_key(unit: str) -> str | None:
    return UNIT_TO_KEY.get((unit or "").strip().lower())


# ── Quantidades efetivas ─────────────────────────────────────────────────────
def effective(element: dict, key: str, overrides: dict) -> dict | None:
    """Quantidade efetiva de um elemento (correção manual > motor). ``overrides`` por (gid, key)."""
    ov = overrides.get((element["gid"], key))
    base = (element.get("quantities") or {}).get(key)
    if ov and ov.get("value") is not None:
        return {"key": key, "value": float(ov["value"]), "unit": ov.get("unit") or (base or {}).get("unit", ""),
                "origin": "manual" if ov.get("corrected") else (base or {}).get("origin", "manual"),
                "source": ov.get("note") or "correção do utilizador", "verified": bool(ov.get("validated")),
                "by": ov.get("by"), "at": ov.get("at")}
    if not base:
        return None
    out = dict(base)
    out["verified"] = bool(ov and ov.get("validated"))
    return out


def element_view(element: dict, overrides: dict) -> dict:
    keys = set((element.get("quantities") or {}).keys()) | {k for (g, k) in overrides if g == element["gid"]}
    qs = {}
    for k in sorted(keys):
        q = effective(element, k, overrides)
        if q:
            q["label"] = QTY_LABELS.get(k, k)
            q["origin_label"] = ORIGIN_LABELS.get(q["origin"], q["origin"])
            qs[k] = q
    e = {k: v for k, v in element.items() if k not in ("_id", "quantities")}
    e["quantities"] = qs
    e["category_label"] = CATEGORIES.get(element.get("category"), element.get("category"))
    return e


# ── Agrupamento ──────────────────────────────────────────────────────────────
_TRAILING_ID = re.compile(r"[\s_\-:#]+[\(\[]?[0-9]+[\)\]]?$")


def group_key(e: dict) -> str:
    label = e.get("type_name") or _TRAILING_ID.sub("", (e.get("name") or "").strip()) or e.get("ifc_class")
    mat = (e.get("materials") or [""])[0]
    return f"{e.get('category')}|{norm(label)[:60]}|{norm(mat)[:40]}"


def build_groups(elements: list[dict], overrides: dict) -> list[dict]:
    groups: dict[str, dict] = {}
    for e in elements:
        if not e.get("counted", True):
            continue
        gk = group_key(e)
        g = groups.get(gk)
        if g is None:
            g = groups[gk] = {
                "group_key": gk, "category": e["category"],
                "category_label": CATEGORIES.get(e["category"], e["category"]),
                "label": e.get("type_name") or _TRAILING_ID.sub("", (e.get("name") or "").strip()) or e["ifc_class"],
                "material": (e.get("materials") or [None])[0], "ifc_class": e["ifc_class"],
                "primary_key": PRIMARY.get(e["category"], "count"),
                "elements": 0, "included": 0, "gids": [], "totals": {}, "origins": {},
                "missing": {}, "by_storey": {}, "verified": 0,
            }
        g["elements"] += 1
        g["gids"].append(e.get("host_gid") or e["gid"])
        if not e.get("included", True):
            continue
        g["included"] += 1
        for key in ("area", "volume", "length", "count", "weight"):
            q = effective(e, key, overrides)
            if q is None:
                g["missing"][key] = g["missing"].get(key, 0) + 1
                continue
            g["totals"][key] = g["totals"].get(key, 0.0) + q["value"]
            g["origins"].setdefault(key, {})
            g["origins"][key][q["origin"]] = g["origins"][key].get(q["origin"], 0) + 1
            if key == g["primary_key"] and q.get("verified"):
                g["verified"] += 1
            st = e.get("storey") or "Sem piso"
            g["by_storey"].setdefault(st, {})
            g["by_storey"][st][key] = g["by_storey"][st].get(key, 0.0) + q["value"]
    out = list(groups.values())
    for g in out:
        g["totals"] = {k: round(v, 4) for k, v in g["totals"].items()}
        g["confidence"] = _confidence(g)
    out.sort(key=lambda g: (list(CATEGORIES).index(g["category"]) if g["category"] in CATEGORIES else 99, g["label"]))
    return out


def _confidence(g: dict) -> str:
    """Resumo da fiabilidade da quantidade principal de um grupo."""
    o = g["origins"].get(g["primary_key"], {})
    n = sum(o.values())
    if not n or g["missing"].get(g["primary_key"]):
        return "incompleta"
    if g["verified"] == g["included"] and g["included"]:
        return "verificada"
    if o.get("estimated"):
        return "estimada"
    if o.get("calculated"):
        return "calculada"
    return "declarada"


# ── Sugestões de artigos ─────────────────────────────────────────────────────
_STOP = {"com", "para", "sobre", "dos", "das", "tipo", "interior", "exterior", "piso", "nivel"}


def suggest(group: dict, items: list[dict], top: int = 3) -> list[dict]:
    """Pontuação explicável: nome/tipo/material do grupo pesam mais do que as palavras genéricas
    da categoria; palavras típicas de OUTRA categoria (ex.: "janela" num grupo de portas) penalizam."""
    cat = group["category"]
    cat_words = set(CATEGORY_WORDS.get(cat, []))
    specific = (tokens(group["label"]) | tokens(group.get("material") or "")) - _STOP
    other = set().union(*(set(w) for c, w in CATEGORY_WORDS.items() if c != cat)) - cat_words - specific
    available = {k for k, v in group["totals"].items() if v > 0}
    scored = []
    for it in items:
        itoks = tokens(it.get("designation", "")) | tokens(it.get("category", ""))
        sp, cw, ot = specific & itoks, (cat_words & itoks) - specific, other & tokens(it.get("designation", ""))
        if not sp and not cw:
            continue
        score = 2.0 * len(sp) + 0.5 * len(cw) - 0.75 * len(ot)
        reasons = [f"palavras em comum: {', '.join(sorted(sp | cw))}"]
        if ot:
            reasons.append(f"refere outro tipo de elemento ({', '.join(sorted(ot))})")
        uk = unit_key(it.get("unit", ""))
        if uk and uk in available:
            score += 1.5 + (0.5 if uk == group["primary_key"] else 0)
            reasons.append(f"unidade compatível ({it.get('unit')})")
        else:
            score -= 2
            reasons.append(f"unidade {it.get('unit')!r} sem quantidade BIM correspondente")
        if it.get("type") == "materiau":
            score -= 0.5
        scored.append({"item_id": it["item_id"], "designation": it.get("designation"), "unit": it.get("unit"),
                       "unit_price_ht": it.get("unit_price_ht"), "score": round(score, 2),
                       "reason": "; ".join(reasons)})
    scored.sort(key=lambda s: -s["score"])
    return [s for s in scored if s["score"] > 0][:top]


# ── Orçamento ────────────────────────────────────────────────────────────────
def budget(groups: list[dict], mappings: dict, items: dict) -> dict:
    """Constrói linhas de orçamento a partir dos grupos com associação CONFIRMADA."""
    lines, unmapped, warnings = [], [], []
    by_cat: dict[str, float] = {}
    by_storey: dict[str, float] = {}
    for g in groups:
        m = mappings.get(g["group_key"])
        if not m or m.get("status") != "confirmed" or m.get("excluded"):
            if not (m and m.get("excluded")) and g["included"]:
                unmapped.append({"group_key": g["group_key"], "label": g["label"], "category": g["category_label"],
                                 "elements": g["included"], "status": (m or {}).get("status", "sem associação")})
            continue
        item = items.get(m["item_id"])
        if not item:
            warnings.append(f"Artigo removido da biblioteca: {m.get('item_snapshot', {}).get('designation', m['item_id'])}")
            continue
        qkey = m.get("quantity_key") or unit_key(item.get("unit", "")) or g["primary_key"]
        qty = g["totals"].get(qkey)
        quantity_missing = bool(g["missing"].get(qkey)) or qty is None
        price = float(item.get("unit_price_ht") or 0)
        price_missing = price <= 0
        qty_v = round(float(qty or 0), 2)
        total = round(qty_v * price, 2)
        storeys = {st: round(v.get(qkey, 0.0), 2) for st, v in g["by_storey"].items() if v.get(qkey)}
        line = {
            "group_key": g["group_key"], "mapping_id": m["mapping_id"], "item_id": item["item_id"],
            "category": g["category_label"], "designation": item.get("designation"),
            "bim_label": g["label"], "unit": item.get("unit"), "quantity_key": qkey, "qty": qty_v,
            "unit_price_ht": price, "total_ht": total, "vat_rate": item.get("vat_rate"),
            "cost_price_ht": float(item.get("cost_price_ht") or 0),
            "price_missing": price_missing, "quantity_missing": quantity_missing,
            "missing_elements": g["missing"].get(qkey, 0), "elements": g["included"],
            "confidence": g["confidence"], "origins": g["origins"].get(qkey, {}), "by_storey": storeys,
            "gids": g["gids"][:500],
        }
        lines.append(line)
        by_cat[g["category_label"]] = round(by_cat.get(g["category_label"], 0) + total, 2)
        for st, q in storeys.items():
            by_storey[st] = round(by_storey.get(st, 0) + q * price, 2)
        if quantity_missing:
            warnings.append(f"{g['label']}: {g['missing'].get(qkey, 0)} elemento(s) sem {QTY_LABELS.get(qkey, qkey).lower()}.")
        if price_missing:
            warnings.append(f"{item.get('designation')}: artigo sem preço na biblioteca.")
    total = round(sum(l["total_ht"] for l in lines), 2)
    return {"lines": lines, "unmapped": unmapped, "subtotals_by_category": by_cat,
            "subtotals_by_storey": by_storey, "total_ht": total, "warnings": warnings,
            "verified_lines": sum(1 for l in lines if l["confidence"] == "verificada")}


def compare(old: list[dict], new: list[dict], tol: float = 1e-3) -> dict:
    """Comparação de versões por GlobalId (adicionados, removidos, alterados)."""
    o = {e["gid"]: e for e in old}
    n = {e["gid"]: e for e in new}
    added = [_brief(n[g]) for g in n.keys() - o.keys()]
    removed = [_brief(o[g]) for g in o.keys() - n.keys()]
    changed = []
    for g in n.keys() & o.keys():
        diffs = {}
        for k in ("area", "volume", "length", "count"):
            a = ((o[g].get("quantities") or {}).get(k) or {}).get("value")
            b = ((n[g].get("quantities") or {}).get(k) or {}).get("value")
            if a is None and b is None:
                continue
            if a is None or b is None or abs(a - b) > tol * max(1.0, abs(a)):
                diffs[k] = {"before": a, "after": b}
        if o[g].get("ifc_class") != n[g].get("ifc_class"):
            diffs["ifc_class"] = {"before": o[g].get("ifc_class"), "after": n[g].get("ifc_class")}
        if diffs:
            changed.append({**_brief(n[g]), "changes": diffs})
    return {"added": added, "removed": removed, "changed": changed,
            "summary": {"added": len(added), "removed": len(removed), "changed": len(changed),
                        "unchanged": len(n.keys() & o.keys()) - len(changed)}}


def _brief(e: dict) -> dict:
    return {"gid": e["gid"], "name": e.get("name"), "category": e.get("category"), "storey": e.get("storey")}
