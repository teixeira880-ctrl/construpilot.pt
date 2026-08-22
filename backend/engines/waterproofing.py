"""Métré étanchéité toiture terrasse → bordereau par couche + quantités commandables."""
import math

DEFAULTS = {
    "recouvrement_pct": 10.0,   # majoration lés (10/15 cm)
    "loss_pct": 5.0,
    "pente_ep_m": 0.05,         # épaisseur moyenne forme de pente
    "roll_m2": 10.0,            # rouleau membrane
    "pv_roll_m2": 10.0,         # rouleau pare-vapeur
    "eif_g_m2": 300.0,          # primaire
    "eif_bidon_kg": 25.0,
    "isolant_panel_m2": 1.44,   # panneau XPS 0.6x1.2 (indicatif)
}
_LAYER_KEYS = ("forme de pente", "chape", "eif", "primaire", "pare-vapeur",
               "isolant", "membrane 1", "membrane 2", "protection")


def _has(layers, *keys):
    names = " ".join((l.get("name", "") if isinstance(l, dict) else str(l)) for l in (layers or [])).lower()
    return any(k in names for k in keys)


def compute(surface_m2: float, perimeter_m: float, releve_h_m: float,
            system_type: str, layers: list, conf: dict, params: dict | None = None,
            regions: list | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    reg = {r.get("key"): r.get("bbox") for r in (regions or []) if r.get("bbox")}
    s = max(0.0, float(surface_m2 or 0))
    per = max(0.0, float(perimeter_m or 0))
    rh = max(0.0, float(releve_h_m or 0))
    recouv = 1 + p["recouvrement_pct"] / 100.0
    loss = 1 + p["loss_pct"] / 100.0
    area_releve = per * rh
    membrane_area = round((s + area_releve) * recouv * loss, 1)
    c = float(conf or 0.8)
    bicouche = (system_type or "bicouche").lower().startswith("bi")
    items = []

    def add(name, unit, qty, commandable_unit=None, commandable_qty=None, region="surface"):
        items.append({"designation": name, "unit": unit, "qty": round(qty, 2),
                      "commandable_unit": commandable_unit, "commandable_qty": commandable_qty,
                      "confidence": c, "bbox": reg.get(region) or reg.get("surface")})

    if _has(layers, "forme de pente", "pente"):
        add("Forme de pente béton (350 kg/m³)", "m³", s * p["pente_ep_m"])
    if _has(layers, "chape", "lissage"):
        add("Chape de lissage 2 cm", "m²", s)
    if _has(layers, "eif", "primaire"):
        kg = s * p["eif_g_m2"] / 1000.0
        add("EIF / primaire", "kg", kg, "bidon", math.ceil(kg / p["eif_bidon_kg"]) if kg else 0)
    if _has(layers, "pare-vapeur", "vapeur"):
        a = round(s * recouv, 1)
        add("Pare-vapeur", "m²", a, "rouleau", math.ceil(a / p["pv_roll_m2"]) if a else 0)
    if _has(layers, "isolant", "polystyrène", "laine", "liège", "xps"):
        add("Isolant thermique", "m²", s, "panneau", math.ceil(s / p["isolant_panel_m2"]) if s else 0)
    add("Membrane étanchéité — couche 1", "m²", membrane_area, "rouleau",
        math.ceil(membrane_area / p["roll_m2"]) if membrane_area else 0)
    if bicouche:
        add("Membrane étanchéité — couche 2", "m²", membrane_area, "rouleau",
            math.ceil(membrane_area / p["roll_m2"]) if membrane_area else 0)
    if _has(layers, "protection"):
        add("Protection (gravillon/dalles)", "m²", s)

    return {"system_type": "bicouche" if bicouche else "monocouche",
            "surface_m2": round(s, 1), "releve_area_m2": round(area_releve, 1),
            "membrane_area_m2": membrane_area, "items": items,
            "recouvrement_pct": p["recouvrement_pct"], "loss_pct": p["loss_pct"]}


def to_csv(items: list) -> str:
    rows = ["Designation;Quantite;Unite;Commandable_qty;Commandable_unite;Confiance"]
    for it in items:
        rows.append(";".join(str(x) for x in [
            it.get("designation", ""), it.get("qty", ""), it.get("unit", ""),
            it.get("commandable_qty", ""), it.get("commandable_unit", ""),
            it.get("confidence", ""),
        ]))
    return "\n".join(rows)
