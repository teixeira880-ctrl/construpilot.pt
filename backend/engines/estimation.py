"""Moteur d'estimation déterministe : aucun prix ne vient du LLM."""
import math
from dataclasses import dataclass, asdict, field
from engines.catalog import (LOTS_BY_KEY, PROJECT_TYPES_BY_KEY, FINISH_BY_KEY, REGIONS,
                            CONDITION_COEF, BUILDING_COEF, DIFFICULTY, EXECUTION_ORDER,
                            HIGH_RISK_LOTS, RISK_KEYWORDS, DEFAULT_LOT_FACTORS)


# Hauteur de référence utilisée pour calibrer les facteurs de `catalog.py`
# (murs, façade, isolation, plaques de plâtre, peinture).
# Si l'utilisateur (ou l'IA) indique une hauteur différente (ex 2.70 m),
# les lots MURAUX sont scalés par le ratio `ceiling_height / REFERENCE_CEILING_HEIGHT`.
REFERENCE_CEILING_HEIGHT_M = 2.5
DEFAULT_CEILING_HEIGHT_M = 2.5

# Lots dont la quantité dépend linéairement de la hauteur sous plafond
# (murs intérieurs, façade, isolation périmétrale, plâtrerie, peinture).
WALL_HEIGHT_SENSITIVE_LOTS = {"peinture", "placo", "isolation", "facade", "maconnerie"}


def _weighted_avg_height(levels: list[dict] | None,
                          default_height: float) -> float:
    """Retourne la hauteur moyenne PONDÉRÉE PAR SURFACE quand plusieurs étages
    ont des HSP différents (ex : maison ancienne RDC 2.60m + R+1 2.20m + combles 1.80m).

    Chaque item : {"label": str, "surface_m2": float, "ceiling_height_m": float}
    - Si liste vide ou None → renvoie `default_height`.
    - Si un item n'a pas surface_m2 → il est ignoré.
    - Si somme des surfaces = 0 → renvoie `default_height`.
    """
    if not levels:
        return default_height
    total_area = sum(float(l.get("surface_m2") or 0) for l in levels)
    if total_area <= 0:
        return default_height
    weighted = sum(
        float(l.get("surface_m2") or 0) * float(l.get("ceiling_height_m") or default_height)
        for l in levels
    )
    return round(weighted / total_area, 3)


@dataclass
class PricingRequest:
    """Groupe les 10 paramètres de `estimate()` en un objet unique — plus lisible
    à l'appel, plus facile à tester et à sérialiser.

    Usage recommandé pour le nouveau code :

        estimate_from_request(PricingRequest(
            project_type='renovation_complete', surface=80.0, finish='standard',
            ceiling_height_m=2.70))
    """
    project_type: str
    surface: float
    finish: str = "standard"
    country: str = "FR"
    region: str | None = None
    building_type: str = "maison"
    condition: str = "bon"
    construction_year: int | None = None
    lot_keys: list[str] | None = field(default=None)
    ceiling_height_m: float = DEFAULT_CEILING_HEIGHT_M


def estimate_from_request(req: PricingRequest) -> dict:
    """Wrapper autour de `estimate()` acceptant un `PricingRequest`."""
    return estimate(**asdict(req))


def region_coef(country: str, region: str | None) -> float:
    for r in REGIONS:
        if r["country"] == (country or "FR").upper() and r["region"] == region:
            return r["coef"]
    return 1.0 if (country or "FR").upper() == "FR" else 0.68


def _mat_price(lot: dict, finish: str) -> float:
    if finish == "eco":
        return lot["mat_eco"]
    if finish in ("premium", "luxe"):
        base = lot["mat_premium"]
        return base * 1.25 if finish == "luxe" else base
    return lot["mat_std"]


def year_coef(year: int | None) -> float:
    if not year:
        return 1.0
    if year < 1949:
        return 1.12
    if year < 1975:
        return 1.08
    if year < 2000:
        return 1.0
    return 0.96


def _resolve_lots(tpl: dict, lot_keys: list[str] | None) -> dict:
    """Résout les lots à estimer (template + fallbacks pour lots additionnels)."""
    if not lot_keys:
        return tpl["lots"]
    selected = {k: v for k, v in tpl["lots"].items() if k in lot_keys}
    for k in lot_keys:
        if k not in selected and k in LOTS_BY_KEY:
            selected[k] = DEFAULT_LOT_FACTORS.get(k, 1.0)
    return selected


def _compute_lot(key: str, factor: float, surface: float,
                 finish_cfg: dict, global_coef: float, rc: float,
                 ceiling_height_m: float = DEFAULT_CEILING_HEIGHT_M) -> dict | None:
    """Calcule le détail d'un lot (qty, prix unitaire, total).

    Si le lot est sensible à la hauteur sous plafond (peinture, placo, isolation,
    façade, maçonnerie), la quantité est scalée par
    `ceiling_height / REFERENCE_CEILING_HEIGHT_M` pour refléter fidèlement la
    demande sur les murs (utile quand le client renseigne 2.70 m au lieu de 2.50 m).
    """
    lot = LOTS_BY_KEY.get(key)
    if not lot:
        return None
    height_ratio = 1.0
    if key in WALL_HEIGHT_SENSITIVE_LOTS and ceiling_height_m and ceiling_height_m > 0:
        height_ratio = ceiling_height_m / REFERENCE_CEILING_HEIGHT_M
    qty = round(surface * factor * height_ratio, 2)
    if lot["unit"] == "u":
        qty = max(1, round(qty))
    mp = _mat_price(lot, finish_cfg["key"])
    mat_unit = round(mp * rc * 0.6 + mp * 0.4, 2)
    labour_unit = round(lot["labour"] * global_coef * finish_cfg["coef"] ** 0.4, 2)
    materials = round(qty * mat_unit, 2)
    labour = round(qty * labour_unit, 2)
    hours = round(qty * lot["hours"], 1)
    return {
        "key": key, "name": lot["name"], "unit": lot["unit"], "quantity": qty,
        "material_unit_price": mat_unit, "labour_unit_price": labour_unit,
        "material_cost": materials, "labour_cost": labour,
        "price_per_unit": round(mat_unit + labour_unit, 2),
        "total": round(materials + labour, 2),
        "hours": hours, "days": round(hours / 7, 1),
        "difficulty": lot["difficulty"],
        "difficulty_label": DIFFICULTY[lot["difficulty"]]["label"],
        "diy_possible": lot["diy_possible"], "tools": lot["tools"],
        "pro_recommended": key in HIGH_RISK_LOTS,
    }


def estimate(project_type: str, surface: float, finish: str = "standard", country: str = "FR",
             region: str | None = None, building_type: str = "maison", condition: str = "bon",
             construction_year: int | None = None, lot_keys: list[str] | None = None,
             ceiling_height_m: float = DEFAULT_CEILING_HEIGHT_M,
             levels: list[dict] | None = None) -> dict:
    """Moteur d'estimation. Si `levels` est fourni ([{label, surface_m2, ceiling_height_m}]),
    la hauteur retenue pour les lots muraux est la moyenne pondérée par surface,
    permettant de bien chiffrer les bâtiments à HSP mixtes (RDC 2.60 + R+1 2.20 + combles 1.80).
    """
    tpl = PROJECT_TYPES_BY_KEY.get(project_type) or PROJECT_TYPES_BY_KEY["renovation_complete"]
    finish_cfg = FINISH_BY_KEY.get(finish) or FINISH_BY_KEY["standard"]
    rc = region_coef(country, region)
    cc = CONDITION_COEF.get(condition, 1.0)
    bc = BUILDING_COEF.get(building_type, 1.0)
    yc = year_coef(construction_year)
    global_coef = rc * cc * bc * yc

    effective_height = _weighted_avg_height(levels, ceiling_height_m)

    selected = _resolve_lots(tpl, lot_keys)
    lots = [lot for key, factor in selected.items()
            if (lot := _compute_lot(key, factor, surface, finish_cfg, global_coef, rc,
                                     effective_height))]
    lots.sort(key=lambda l: EXECUTION_ORDER.index(l["key"]) if l["key"] in EXECUTION_ORDER else 99)

    materials_total = round(sum(l["material_cost"] for l in lots), 2)
    labour_total = round(sum(l["labour_cost"] for l in lots), 2)
    hours_total = round(sum(l["hours"] for l in lots), 1)
    equipment = round((materials_total + labour_total) * 0.035, 2)
    waste = round(surface * 9 * rc, 2)
    subtotal = round(materials_total + labour_total + equipment + waste, 2)
    contingency = round(subtotal * 0.10, 2)
    total_avg = round(subtotal + contingency, 2)

    return {
        "project_type": tpl["key"], "project_type_name": tpl["name"], "surface": surface,
        "ceiling_height_m": effective_height,
        "levels": levels or [],
        "finish_level": finish_cfg["key"], "finish_level_name": finish_cfg["name"],
        "country": country, "region": region, "building_type": building_type,
        "condition": condition, "construction_year": construction_year,
        "coefficients": {"region": rc, "condition": cc, "building": bc, "year": yc,
                         "finish": finish_cfg["coef"]},
        "lots": lots,
        "breakdown": {
            "materials": materials_total, "labour": labour_total,
            "equipment_rental": equipment, "waste_disposal": waste,
            "contingency_rate": 0.10, "contingency": contingency,
        },
        "total_min": round(total_avg * 0.88, 2),
        "total_avg": total_avg,
        "total_max": round(total_avg * 1.16, 2),
        "price_per_sqm": round(total_avg / surface, 2) if surface else 0,
        "total_hours": hours_total,
        "duration_weeks": max(1, math.ceil(hours_total / 70)),
        "price_model": _price_model(project_type, surface, country, region, building_type,
                                    condition, construction_year, lot_keys),
    }


def _price_model(project_type, surface, country, region, building_type, condition, year, lot_keys):
    out = {}
    for lvl in ("eco", "standard", "premium"):
        tpl = PROJECT_TYPES_BY_KEY.get(project_type) or PROJECT_TYPES_BY_KEY["renovation_complete"]
        finish_cfg = FINISH_BY_KEY[lvl]
        rc = region_coef(country, region)
        coef = rc * CONDITION_COEF.get(condition, 1.0) * BUILDING_COEF.get(building_type, 1.0) * year_coef(year)
        sel = tpl["lots"] if not lot_keys else {k: v for k, v in tpl["lots"].items() if k in lot_keys}
        tot = 0.0
        for key, factor in sel.items():
            lot = LOTS_BY_KEY.get(key)
            if not lot:
                continue
            qty = surface * factor
            tot += qty * (_mat_price(lot, lvl) * rc + lot["labour"] * coef * finish_cfg["coef"] ** 0.4)
        tot *= 1.145
        out[lvl] = {"total": round(tot, 2), "per_sqm": round(tot / surface, 2) if surface else 0}
    return out


def planning(lots: list[dict]) -> list[dict]:
    weeks = []
    week = 1
    prev = None
    for lot in sorted(lots, key=lambda l: EXECUTION_ORDER.index(l["key"]) if l["key"] in EXECUTION_ORDER else 99):
        dur = max(1, round(lot["hours"] / 35))
        weeks.append({
            "lot": lot["key"], "name": lot["name"], "start_week": week,
            "duration_weeks": dur, "end_week": week + dur - 1,
            "depends_on": prev, "hours": lot["hours"],
        })
        prev = lot["key"]
        week += dur
    return weeks


def diy_vs_pro(est: dict) -> dict:
    diy_material = 0.0
    diy_labour_saved = 0.0
    pro_only = []
    diy_ok = []
    diy_hours = 0.0
    for lot in est["lots"]:
        if lot["diy_possible"] and lot["difficulty"] != "pro":
            diy_material += lot["material_cost"] * 1.06
            diy_labour_saved += lot["labour_cost"]
            diy_hours += lot["hours"] * 1.8
            diy_ok.append(lot["name"])
        else:
            diy_material += lot["total"]
            pro_only.append(lot["name"])
    pro_total = est["total_avg"]
    diy_total = round(diy_material * 1.10, 2)
    risk = "élevé" if pro_only else ("moyen" if diy_hours > 80 else "faible")
    return {
        "pro_total": pro_total,
        "diy_total": diy_total,
        "savings": round(pro_total - diy_total, 2),
        "savings_pct": round((pro_total - diy_total) / pro_total * 100, 1) if pro_total else 0,
        "diy_hours": round(diy_hours),
        "diy_tasks": diy_ok,
        "pro_tasks": pro_only,
        "risk": risk,
        "conclusion": (
            f"Vous pouvez réaliser vous-même : {', '.join(diy_ok) if diy_ok else 'aucun lot'}. "
            + (f"Nous recommandons de confier à un professionnel : {', '.join(pro_only)}."
               if pro_only else "Aucun lot ne nécessite obligatoirement un professionnel.")
        ),
    }


def safety_check(text: str, lot_keys: list[str] | None = None) -> list[dict]:
    alerts = []
    low = (text or "").lower()
    for kw, msg in RISK_KEYWORDS.items():
        if kw in low:
            alerts.append({"trigger": kw, "message": msg, "level": "pro_required"})
    for key in (lot_keys or []):
        if key in HIGH_RISK_LOTS:
            lot = LOTS_BY_KEY.get(key)
            if lot:
                alerts.append({"trigger": lot["name"],
                               "message": f"{lot['name']} : intervention d'un professionnel fortement recommandée.",
                               "level": "pro_recommended"})
    return alerts
