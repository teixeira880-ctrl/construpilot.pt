"""Demonstrações públicas calculadas pelos motores reais do produto, sobre um projeto de exemplo.

* Medições  → engines/geometry.py (compute_calibration, room_measurements, subtract_openings,
               calibration_check, paint_liters, placo_quantity, floor_quantity, skirting_length_m)
* Orçamento → total de linha = quantidade × preço unitário × (1 − desconto/100), como em
               engines/chantier_costs.py
* Margem    → margem = (venda − custo) / venda ; markup = (venda − custo) / custo
               (fórmulas de engines/chantier_costs.py; paridade verificada em teste)

Sem acesso à base de dados, sem uploads, sem IA, sem dados de clientes. O visitante só pode
alterar parâmetros numéricos limitados do projeto de exemplo.
"""
from __future__ import annotations

import math

from engines import geometry as G

SAMPLE = {
    "name": {"pt": "Sala de exemplo — Moradia T3", "en": "Sample living room — 3-bed house", "fr": "Séjour d'exemple — maison T3"},
    # Planta de exemplo em píxeis (desenho 1:50 a 100 px/m quando calibrado com 5,00 m).
    "calibration_line": [(100, 520), (600, 520)],
    "calibration_real_m": 5.00,
    "check_line": [(80, 100), (80, 480)],
    "check_expected_m": 3.80,
    "room": [(100, 100), (520, 100), (520, 480), (100, 480)],
    "ceiling_height_m": 2.60,
    "openings": [
        {"kind": "door", "width_m": 0.90, "height_m": 2.10, "count": 1},
        {"kind": "window", "width_m": 1.20, "height_m": 1.20, "count": 2},
    ],
}

# Preços de exemplo, explicitamente fictícios (não são tabela ConstruPilot nem preços de mercado).
SAMPLE_LINES = [
    {"key": "paint_walls", "lot": "pintura", "unit": "m2", "unit_price_ht": 9.50, "cost_price_ht": 6.20, "qty_from": "wall_net"},
    {"key": "paint_ceiling", "lot": "pintura", "unit": "m2", "unit_price_ht": 11.00, "cost_price_ht": 7.10, "qty_from": "ceiling"},
    {"key": "parquet", "lot": "pavimentos", "unit": "m2", "unit_price_ht": 38.00, "cost_price_ht": 27.50, "qty_from": "floor_order"},
    {"key": "skirting", "lot": "pavimentos", "unit": "m", "unit_price_ht": 8.50, "cost_price_ht": 5.40, "qty_from": "skirting_order"},
]

LINE_LABELS = {
    "paint_walls": {"pt": "Pintura de paredes (2 demãos)", "en": "Wall painting (2 coats)", "fr": "Peinture murs (2 couches)"},
    "paint_ceiling": {"pt": "Pintura de teto (2 demãos)", "en": "Ceiling painting (2 coats)", "fr": "Peinture plafond (2 couches)"},
    "parquet": {"pt": "Pavimento flutuante", "en": "Floating floor", "fr": "Parquet flottant"},
    "skirting": {"pt": "Rodapé", "en": "Skirting", "fr": "Plinthe"},
}
LOT_LABELS = {"pintura": {"pt": "Pintura", "en": "Painting", "fr": "Peinture"},
              "pavimentos": {"pt": "Pavimentos", "en": "Flooring", "fr": "Sols"}}

LIMITS = {"calibration_real_m": (0.5, 50.0), "unit_price_ht": (0.0, 10000.0), "cost_price_ht": (0.0, 10000.0),
          "discount_pct": (0.0, 100.0), "coats": (1, 4)}


class DemoInputError(ValueError):
    pass


def _bounded(name: str, value, default):
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise DemoInputError(f"{name} inválido")
    lo, hi = LIMITS[name]
    if not math.isfinite(v) or v < lo or v > hi:
        raise DemoInputError(f"{name} fora do intervalo [{lo}, {hi}]")
    return v


def takeoff(calibration_real_m: float | None = None, coats: int | None = None) -> dict:
    real = _bounded("calibration_real_m", calibration_real_m, SAMPLE["calibration_real_m"])
    n_coats = int(_bounded("coats", coats, 2))
    cal = G.compute_calibration(*SAMPLE["calibration_line"], real)
    ppm = cal["pixels_per_meter"]
    check_measured = G.distance_m(*SAMPLE["check_line"], ppm)
    check = G.calibration_check(check_measured, SAMPLE["check_expected_m"])
    room = G.room_measurements(SAMPLE["room"], ppm, SAMPLE["ceiling_height_m"])
    walls = G.subtract_openings(room["wall_area_gross_m2"], SAMPLE["openings"])
    door_width = sum(o["width_m"] * o["count"] for o in SAMPLE["openings"] if o["kind"] == "door")
    paint = G.paint_liters(walls["wall_area_net_m2"] + room["ceiling_area_m2"], coats=n_coats)
    floor = G.floor_quantity(room["surface_m2"], "parquet")
    skirting = G.skirting_length_m(room["perimeter_m"], door_openings_m=door_width)
    return {
        "engine": "engines/geometry.py",
        "sample": {"name": SAMPLE["name"], "room_px": SAMPLE["room"], "calibration_line_px": SAMPLE["calibration_line"],
                   "check_line_px": SAMPLE["check_line"], "ceiling_height_m": SAMPLE["ceiling_height_m"],
                   "openings": SAMPLE["openings"], "check_expected_m": SAMPLE["check_expected_m"]},
        "calibration": cal,
        "calibration_check": check,
        "room": room,
        "walls": walls,
        "quantities": {"paint": paint, "floor": floor, "skirting": skirting},
    }


def _line_total(qty: float, pu: float, discount: float) -> float:
    return round(qty * pu * (1 - discount / 100), 2)


def margin_figures(sale: float, cost: float, complete: bool = True) -> dict:
    """Mesmas fórmulas que engines/chantier_costs.py (função interna `margin`)."""
    m = round(sale - cost, 2) if complete else None
    return {"margin_ht": m,
            "margin_pct": round(m / sale * 100, 1) if m is not None and sale > 0 else None,
            "markup_pct": round(m / cost * 100, 1) if m is not None and cost > 0 else None}


def quote(overrides: dict | None = None, calibration_real_m: float | None = None) -> dict:
    """Orçamento de exemplo a partir das quantidades medidas. `overrides`: {line_key: {unit_price_ht, cost_price_ht, discount_pct}}."""
    overrides = overrides or {}
    unknown = set(overrides) - {l["key"] for l in SAMPLE_LINES}
    if unknown:
        raise DemoInputError("linha desconhecida")
    t = takeoff(calibration_real_m)
    qty_map = {
        "wall_net": t["walls"]["wall_area_net_m2"],
        "ceiling": t["room"]["ceiling_area_m2"],
        "floor_order": t["quantities"]["floor"]["quantity_m2"],
        "skirting_order": t["quantities"]["skirting"]["quantity_m"],
    }
    lines, lots = [], {}
    for base in SAMPLE_LINES:
        ov = overrides.get(base["key"]) or {}
        pu = _bounded("unit_price_ht", ov.get("unit_price_ht"), base["unit_price_ht"])
        cost = _bounded("cost_price_ht", ov.get("cost_price_ht"), base["cost_price_ht"])
        disc = _bounded("discount_pct", ov.get("discount_pct"), 0.0)
        qty = round(qty_map[base["qty_from"]], 2)
        sale = _line_total(qty, pu, disc)
        cost_total = round(qty * cost, 2)
        lines.append({"key": base["key"], "label": LINE_LABELS[base["key"]], "lot": base["lot"], "unit": base["unit"],
                      "qty": qty, "unit_price_ht": pu, "cost_price_ht": cost, "discount_pct": disc,
                      "total_ht": sale, "cost_total_ht": cost_total, **margin_figures(sale, cost_total)})
        g = lots.setdefault(base["lot"], {"lot": base["lot"], "label": LOT_LABELS[base["lot"]], "vente_ht": 0.0, "cost_prev_ht": 0.0})
        g["vente_ht"] += sale
        g["cost_prev_ht"] += cost_total
    lot_rows = []
    for g in lots.values():
        g["vente_ht"], g["cost_prev_ht"] = round(g["vente_ht"], 2), round(g["cost_prev_ht"], 2)
        lot_rows.append({**g, **margin_figures(g["vente_ht"], g["cost_prev_ht"])})
    sale = round(sum(l["total_ht"] for l in lines), 2)
    cost = round(sum(l["cost_total_ht"] for l in lines), 2)
    return {
        "engine": "engines/geometry.py + fórmulas de engines/chantier_costs.py",
        "prices_are_examples": True,
        "lines": lines,
        "lots": lot_rows,
        "totals": {"vente_ht": sale, "cost_prev_ht": cost, **margin_figures(sale, cost),
                   "coefficient": round(sale / cost, 3) if cost > 0 else None},
        "takeoff": {"surface_m2": t["room"]["surface_m2"], "calibration_ok": t["calibration_check"]["ok"]},
    }


def compute(demo_id: str, params: dict | None = None) -> dict:
    params = params or {}
    if demo_id in ("demo_takeoff", "demo_painting"):
        return {"demo": demo_id, "takeoff": takeoff(params.get("calibration_real_m"), params.get("coats"))}
    if demo_id in ("demo_quote", "demo_margin"):
        q = quote(params.get("lines"), params.get("calibration_real_m"))
        return {"demo": demo_id, "quote": q}
    raise DemoInputError("demonstração sem cálculo")
