"""Traceable construction estimates. No inferred structural design and no eval.

Vision proposes a source-linked specification; this module owns every quantity,
unit, price multiplication and total. Missing/conflicting evidence stays missing.
The same specification is used by the editor, exports and later recomputations.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

VERSION = "construction-dossier-1"
CATALOG_VERSION = "budget-FR-2026-10-11"
# Indicative SELLING prices, supply + install, not supplier quotes/cost prices.
# No default margin is applied on top. Overrides belong to one account only.
CATALOG = {
    "installation": ("ft", 7000), "execution_studies": ("ft", 5000),
    "fence_removal": ("ft", 1800), "excavation": ("m³", 35),
    "soil_disposal": ("m³", 34), "backfill": ("m³", 42),
    "temporary_shoring": ("ft", 15000), "foundation_allowance": ("ft", 18000),
    "subbase": ("m²", 38), "basement_slab": ("m²", 110),
    "basement_concrete_wall": ("m²", 290), "waterproofing": ("m²", 42),
    "waterproofing_protection": ("m²", 26), "drainage": ("ml", 65),
    "floor_over_basement": ("m²", 175), "upper_floor": ("m²", 180),
    "attic_floor_allowance": ("m²", 170), "trimmers": ("ft", 2800),
    "masonry_block": ("m²", 110), "masonry_brick": ("m²", 110),
    "masonry_gable": ("m²", 120), "interior_structure": ("ft", 12000),
    "concrete_stairs": ("ens.", 6200), "garage_ramp": ("m²", 220),
    "ramp_retaining_wall": ("m²", 300), "ramp_channel": ("ml", 190),
    "sump_pump": ("ft", 2000), "entrance_steps": ("ens.", 1800),
    "boundary_masonry": ("ft", 3200), "sills": ("ft", 2500),
    "facade_render": ("m²", 52), "underfloor_drainage": ("ft", 4500),
    "handover": ("ft", 900), "filled_crawlspace_block": ("m²", 125),
    "solid_crawlspace_block": ("m²", 95),
}
GROUPS = {"A": "Preparação e estudos", "B": "Movimentos de terras e estabilidade das escavações",
          "C": "Fundações e infraestrutura", "D": "Pavimentos e chaminés de laje",
          "E": "Elevações, estrutura e escadas", "F": "Acessos e vedações",
          "G": "Fachadas e interfaces", "H": "Redes e receção"}
UNITS = {"m": (1, 0), "ml": (1, 0), "m²": (2, 0), "m2": (2, 0),
         "m³": (3, 0), "m3": (3, 0), "kg": (0, 1),
         "u": (0, 0), "ens.": (0, 0), "ft": (0, 0), "1": (0, 0)}
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
MAX_PARAMETERS, MAX_ITEMS = 1500, 600


class StudyError(ValueError):
    pass


def number(value, *, maximum=1e12):
    if isinstance(value, bool) or value is None:
        raise StudyError("Número em falta ou inválido")
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise StudyError("Número inválido") from None
    if not math.isfinite(n) or abs(n) > maximum:
        raise StudyError("Número fora dos limites")
    return n


def money(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def quote_lines_hash(lines):
    """Ignore editor metadata, never ignore a commercial value or description."""
    fields = ("kind", "designation", "description", "qty", "unit", "unit_price_ht", "vat_rate", "discount_pct")
    return fingerprint([{k: (float(r.get(k) or 0) if k in ("qty", "unit_price_ht", "vat_rate", "discount_pct")
                             else r.get(k) or ("line" if k == "kind" else "")) for k in fields} for r in lines])


def _unit(unit):
    if unit not in UNITS:
        raise StudyError(f'Unidade desconhecida: {str(unit)[:25]}')
    return UNITS[unit]


def _text(value, limit=2000):
    return str(value or "")[:limit]


class QuantityEvaluator:
    """Small dimensional arithmetic language; dependencies cannot execute code."""
    def __init__(self, parameters, page_count):
        self.parameters, self.cache, self.stack = {}, {}, set()
        self.page_count = page_count
        for raw in parameters:
            if not isinstance(raw, dict):
                raise StudyError("Medição inválida")
            key = raw.get("id", "")
            if not isinstance(key, str) or not IDENT.fullmatch(key):
                raise StudyError("Identificador de medição inválido")
            if key in self.parameters:
                raise StudyError(f'Medição duplicada: {key}')
            self.parameters[key] = raw

    def parameter(self, key):
        if key in self.cache:
            return self.cache[key]
        if key in self.stack or len(self.stack) > 50:
            raise StudyError("Ciclo ou profundidade excessiva nos cálculos")
        p = self.parameters.get(key)
        if p is None:
            raise StudyError(f'Medição ausente: {key}')
        if p.get("conflict"):
            raise StudyError(f"Cotes contradictoires : {key}")
        self.stack.add(key)
        try:
            if p.get("expression"):
                val, dim, refs = self.expression(p["expression"])
                if dim != _unit(p.get("unit")):
                    raise StudyError(f'Unidade incoerente para {key}')
            else:
                val, dim, refs = number(p.get("value")), _unit(p.get("unit")), {key}
                if val < 0 and not p.get("signed_level"):
                    raise StudyError(f'Medição negativa: {key}')
            result = (val, dim, refs | {key})
            self.cache[key] = result
            return result
        finally:
            self.stack.remove(key)

    def expression(self, expression):
        if not isinstance(expression, str) or len(expression) > 1200:
            raise StudyError("Fórmula em falta ou demasiado longa")
        try:
            root = ast.parse(expression, mode="eval")
        except (SyntaxError, RecursionError):
            raise StudyError("Fórmula inválida") from None
        if len(list(ast.walk(root))) > 160:
            raise StudyError("Fórmula demasiado complexa")

        def run(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return number(node.value), (0, 0), set()
            if isinstance(node, ast.Name):
                return self.parameter(node.id)
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
                v, d, r = run(node.operand)
                return (-v if isinstance(node.op, ast.USub) else v), d, r
            if isinstance(node, ast.BinOp):
                a, da, ra = run(node.left)
                b, db, rb = run(node.right)
                if isinstance(node.op, (ast.Add, ast.Sub)):
                    if da != db:
                        raise StudyError("Adição de dimensões incompatíveis")
                    val, dim = (a+b if isinstance(node.op, ast.Add) else a-b), da
                elif isinstance(node.op, ast.Mult):
                    val, dim = a*b, tuple(x+y for x, y in zip(da, db))
                elif isinstance(node.op, ast.Div):
                    if b == 0:
                        raise StudyError("Divisão por zero")
                    val, dim = a/b, tuple(x-y for x, y in zip(da, db))
                elif isinstance(node.op, ast.Pow) and not rb and db == (0, 0) and b in (2, 3):
                    val, dim = a**b, tuple(x*int(b) for x in da)
                else:
                    raise StudyError("Operador não autorizado")
                return number(val), dim, ra | rb
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "sqrt" and len(node.args) == 1 and not node.keywords):
                v, d, r = run(node.args[0])
                if v < 0 or any(x % 2 for x in d):
                    raise StudyError("Raiz incompatível com as dimensões")
                return math.sqrt(v), tuple(x//2 for x in d), r
            raise StudyError("Expressão não autorizada")
        try:
            return run(root.body)
        except (OverflowError, RecursionError):
            raise StudyError("Cálculo fora dos limites") from None

    def trace(self, refs):
        rows = []
        for key in sorted(refs):
            p = self.parameters[key]
            sources = []
            for s in (p.get("sources") or [])[:12]:
                if not isinstance(s, dict):
                    continue
                page = s.get("page")
                if isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= self.page_count:
                    sources.append({"page": page, "text": _text(s.get("text"), 300)})
            rows.append({"id": key, "label": _text(p.get("label") or key, 180),
                         "value": self.parameter(key)[0], "unit": p.get("unit"),
                         "expression": p.get("expression"), "sources": sources,
                         "status": p.get("status", "hypothesis"), "reviewed": p.get("reviewed") is True,
                         "note": _text(p.get("note"))})
        return rows


def normalize_ai_spec(raw, page_count):
    """Do not let a model certify itself or introduce invented selling prices."""
    if not isinstance(raw, dict):
        raise StudyError("Síntese IA inválida")
    spec = copy.deepcopy(raw)
    if any(not isinstance(spec.get(key), list) or any(not isinstance(x, dict) for x in spec[key]) for key in ("parameters", "items")):
        raise StudyError("Medições ou trabalhos IA inválidos")
    for p in spec.get("parameters") or []:
        p["reviewed"] = False
        p["status"] = p.get("status") if p.get("status") in ("observed", "hypothesis", "provision", "missing") else "hypothesis"
        valid = [s for s in (p.get("sources") or []) if isinstance(s, dict)
                 and type(s.get("page")) is int and 1 <= s["page"] <= page_count]
        p["sources"] = valid
        if p["status"] == "observed" and not valid:
            p["status"] = "hypothesis"
            p["note"] = "Origem do valor não encontrada. " + _text(p.get("note"))
    for item in spec.get("items") or []:
        item.pop("unit_price", None)
        item.pop("price_source", None)
        item["reviewed"] = False
    spec.pop("vat_rate", None)
    return spec


def build_dossier(spec, *, page_count, source=None, settings=None, coverage=None):
    settings, coverage = settings or {}, coverage or {}
    if not isinstance(spec, dict):
        raise StudyError("Estudo inválido")
    params, items = spec.get("parameters") or [], spec.get("items") or []
    if not isinstance(params, list) or not isinstance(items, list) or len(params) > MAX_PARAMETERS or len(items) > MAX_ITEMS:
        raise StudyError("Estudo demasiado volumoso; reparta os trabalhos por processo")
    if not items:
        raise StudyError("Nenhum trabalho utilizável nas peças analisadas")
    if any(not isinstance(x, dict) for x in params + items):
        raise StudyError("Medição ou trabalho inválido")
    ev = QuantityEvaluator(params, page_count)
    warnings = [_text(x) for x in spec.get("warnings", [])][:100]
    controls, calculations, rows = [], [], []
    seen = {}
    for item in items:
        ident = item.get("id")
        physical = item.get("physical_key") or ident
        if not isinstance(ident, str) or not isinstance(physical, str) or not ident or not physical:
            raise StudyError("Cada trabalho deve ter um identificador e uma referência física")
        if str(ident) in seen:
            raise StudyError(f'Identificador de trabalho duplicado: {str(ident)[:80]}')
        seen[str(ident)] = physical
    duplicate_keys = {k for k in seen.values() if list(seen.values()).count(k) > 1}
    country = str(settings.get("country") or spec.get("country") or "").upper()
    prices = settings.get("dossier_unit_prices") or {}
    for n, item in enumerate(items):
        ident = str(item["id"])
        unit = item.get("unit", "u")
        trace, qty, error = [], None, None
        expression = item.get("expression", "")
        try:
            if seen[ident] in duplicate_keys:
                raise StudyError("Trabalho físico duplicado: fundir ou distinguir o seu âmbito")
            value, dim, refs = ev.expression(expression)
            if dim != _unit(unit):
                raise StudyError("A fórmula não produz a unidade do trabalho")
            if value < 0:
                raise StudyError("Quantidade negativa: verificar as deduções")
            if not refs and unit in ("m", "ml", "m²", "m2", "m³", "m3", "kg"):
                raise StudyError("Quantidade sem medição de origem: acrescentar uma medição ou uma provisão")
            trace = ev.trace(refs)
            qty = money(value)
        except StudyError as exc:
            error = str(exc)
            controls.append({"severity": "error", "item_id": ident, "message": error})
        status = "M" if trace and all(p["reviewed"] for p in trace) else "H"
        if item.get("quantity_status") == "P" or any(p["status"] == "provision" for p in trace):
            status = "P"
        if qty is None:
            status = "N/C"
        key = item.get("price_key")
        pu, price_source = None, "non_chiffre"
        chosen = prices.get(key) if key else None
        manual_price = "unit_price" in item
        if manual_price:  # only from authenticated manual revisions
            chosen = item["unit_price"]
        if chosen is not None:
            pu = number(chosen)
            if pu < 0:
                raise StudyError("Preço negativo: utilizar uma variante explícita")
            price_source = "prix_utilisateur"
        elif not manual_price and country == "FR" and key in CATALOG:
            catalog_unit, pu = CATALOG[key]
            canonical = lambda u: {"m2": "m²", "m3": "m³", "m": "ml"}.get(u, u)
            if canonical(catalog_unit) != canonical(unit):
                controls.append({"severity": "error", "item_id": ident, "message": "Unidade do preço incompatível"})
                pu = None
            else:
                price_source = "estimation_budgetaire"
        if pu is not None:
            # Account-wide price overrides still refer to the catalogue unit.
            # A per-line manual price explicitly belongs to that line's unit.
            canonical = lambda u: {"m2": "m²", "m3": "m³", "m": "ml"}.get(u, u)
            if not manual_price and key in CATALOG and canonical(CATALOG[key][0]) != canonical(unit):
                controls.append({"severity": "error", "item_id": ident, "message": "Unidade do preço incompatível"})
                pu, price_source = None, "non_chiffre"
        if pu is not None:
            pu = money(pu)
        total = money(Decimal(str(qty))*Decimal(str(pu))) if qty is not None and pu is not None else None
        included = item.get("included", True) is not False
        row = {"id": ident, "key": key or ident, "group": str(item.get("group") or "E")[:80],
               "designation": _text(item.get("designation") or ident, 240), "detail": _text(item.get("note")),
               "unit": unit, "qty": qty, "unit_price": pu, "total": total,
               "quantity_status": status, "price_source": price_source, "included": included,
               "expression": expression, "sources": trace, "physical_key": seen[ident],
               "level": _text(item.get("level"), 100), "error": error}
        rows.append(row)
        calculations.append({"id": ident, "label": row["designation"], "formula": expression,
                             "result": qty, "unit": unit, "status": status, "sources": trace})
    active = [r for r in rows if r["included"]]
    if not active:
        raise StudyError("Nenhum artigo incluído no orçamento")
    ht = money(sum((Decimal(str(r["total"])) for r in active if r["total"] is not None), Decimal(0)))
    vat = settings.get("vat_rate")
    if vat is not None:
        vat = number(vat, maximum=100)
        if vat < 0:
            raise StudyError("IVA inválido")
    tax = money(Decimal(str(ht))*Decimal(str(vat))/100) if vat is not None else None
    ttc = money(ht+tax) if tax is not None else None
    missing = [r["id"] for r in active if r["total"] is None]
    if missing:
        warnings.append(f'{len(missing)} artigo(s) sem preço: o total é parcial.')
    if vat is None:
        warnings.append("IVA não determinado: confirmar o país e a taxa antes de um total c/ IVA.")
    if coverage.get("failed_pages") or coverage.get("omitted_pages"):
        warnings.append("Algumas páginas não foram analisadas: verificar a cobertura do processo.")
    for gap in spec.get("missing_information", []):
        warnings.append(_text(gap))
    # No claim of exhaustive scope based on the model's own confidence value.
    warnings.append("Âmbito e interpretação das plantas a controlar; o cálculo aritmético não certifica a leitura completa do projeto.")
    lots = []
    for key in dict.fromkeys(r["group"] for r in active):
        lines = [r for r in active if r["group"] == key]
        subtotal = money(sum(Decimal(str(r["total"])) for r in lines if r["total"] is not None))
        lots.append({"key": key, "lot": (spec.get("group_names") or {}).get(key) or GROUPS.get(key, key),
                     "lines": lines, "total_ht": subtotal, "partial": any(r["total"] is None for r in lines)})
    variants = []
    for v in (spec.get("variants") or [])[:30]:
        ids = set(v.get("omit_item_ids") or [])
        selected = [r for r in active if r["id"] in ids]
        if ids and len(selected) == len(ids) and all(r["total"] is not None for r in selected):
            reduction = money(sum(Decimal(str(r["total"])) for r in selected))
            variants.append({"label": _text(v.get("label"), 200), "deduction_ht": reduction,
                             "total_ht": money(ht-reduction), "note": _text(v.get("note")),
                             "omit_item_ids": sorted(ids)})
    return {"schema_version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
            "revision": fingerprint({"spec": spec, "settings": settings, "coverage": coverage}),
            "spec": copy.deepcopy(spec), "settings_snapshot": copy.deepcopy(settings),
            "project": spec.get("project") or {}, "scope": spec.get("scope") or "Obra grossa",
            "source": source or {}, "page_count": page_count, "coverage": coverage,
            "pages_analyzed": [p-1 for p in coverage.get("analyzed_pages", [])],
            "demandes": spec.get("demandes") or [], "items": rows, "lots": lots,
            "totals": {"ht": ht, "tva": tax, "ttc": ttc, "tva_rate": vat/100 if vat is not None else None,
                       "partial": bool(missing), "missing_item_ids": missing,
                       "cout_ht": None, "marge_eur": None, "marge_pct": None},
            "calculations": calculations, "controls": controls, "variants": variants,
            "warnings": list(dict.fromkeys(warnings)), "assumptions": spec.get("assumptions") or [],
            "exclusions": spec.get("exclusions") or [], "planning": None, "levels_breakdown": [],
            "catalog_version": CATALOG_VERSION, "automatic_plan_validation_complete": False,
            "review_required": True, "quantity_status_counts": {s: sum(r["quantity_status"] == s for r in active) for s in ("M", "H", "P", "N/C")}}
