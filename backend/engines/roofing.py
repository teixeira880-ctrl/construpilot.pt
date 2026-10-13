"""Métré toiture (couverture en pente) → surfaces rampantes + quantités commandables.
Module « Analyse technique & Approvisionnement IA » — Phase 2 (Toiture)."""
import math

# Couvertures : nombre d'unités/m² de rampant + conditionnement + pertes indicatives
MATERIALS = {
    "tuiles_terre_cuite": {"label": "Telhas cerâmicas", "per_m2": 10.5, "pack": "tuile",
                           "pack_label": "tuile", "loss": 8.0},
    "tuiles_beton": {"label": "Telhas de betão", "per_m2": 10.0, "pack": "tuile",
                     "pack_label": "tuile", "loss": 8.0},
    "ardoises": {"label": "Ardósias", "per_m2": 23.0, "pack": "ardoise",
                 "pack_label": "ardoise", "loss": 10.0},
    "bac_acier": {"label": "Painel sandwich / cobertura seca", "per_m2": 1.0, "pack": "m²",
                  "pack_label": "m²", "loss": 10.0, "is_area": True},
}

DEFAULTS = {
    "pente_pct": 35.0,           # pente par défaut (%) si non détectée
    "ecran_recouvrement_pct": 10.0,
    "ecran_roll_m2": 75.0,       # rouleau écran sous-toiture 1,5 × 50 m
    "liteau_entraxe_m": 0.32,    # pureau / entraxe liteaux
    "liteau_length_m": 3.0,      # longueur liteau commercial
    "faitiere_per_ml": 2.5,      # tuiles faîtières / arêtiers par ml
    "bac_sheet_m2": 5.0,         # surface moyenne d'un bac acier
    "loss_pct": 8.0,
}


def _dev_area(surface_projetee_m2: float, pente_pct: float) -> float:
    """Surface rampante (développée) = surface projetée / cos(angle de pente)."""
    angle = math.atan(max(0.0, pente_pct) / 100.0)
    c = math.cos(angle)
    return surface_projetee_m2 / c if c > 0 else surface_projetee_m2


def compute(surface_projetee_m2: float, pente_pct: float, material: str,
            lengths: dict, conf: float = 0.8, params: dict | None = None,
            regions: list | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    reg = {r.get("key"): r.get("bbox") for r in (regions or []) if r.get("bbox")}
    s_proj = max(0.0, float(surface_projetee_m2 or 0))
    pente = float(pente_pct if pente_pct not in (None, 0) else p["pente_pct"])
    mat = MATERIALS.get(material, MATERIALS["tuiles_terre_cuite"])
    lg = lengths or {}
    faitage = max(0.0, float(lg.get("faitage_ml") or 0))
    aretiers = max(0.0, float(lg.get("aretiers_ml") or 0))
    noues = max(0.0, float(lg.get("noues_ml") or 0))
    rives = max(0.0, float(lg.get("rives_ml") or 0))
    egout = max(0.0, float(lg.get("egout_ml") or 0))
    loss = 1 + float(p["loss_pct"]) / 100.0
    c = float(conf or 0.8)

    s_ramp = round(_dev_area(s_proj, pente), 1)
    angle_deg = round(math.degrees(math.atan(pente / 100.0)), 1)
    items = []

    def add(name, unit, qty, commandable_unit=None, commandable_qty=None, region=None):
        items.append({"designation": name, "unit": unit, "qty": round(qty, 2),
                      "commandable_unit": commandable_unit,
                      "commandable_qty": commandable_qty, "confidence": c,
                      "bbox": reg.get(region) or reg.get("couverture")})

    # 1. Couverture (tuiles / ardoises / bac)
    mat_loss = 1 + float(mat.get("loss", p["loss_pct"])) / 100.0
    if mat.get("is_area"):
        area_cmd = round(s_ramp * mat_loss, 1)
        add(mat["label"], "m²", area_cmd, "bac",
            math.ceil(area_cmd / p["bac_sheet_m2"]) if area_cmd else 0, "couverture")
    else:
        units = s_ramp * mat["per_m2"] * mat_loss
        add(f"{mat['label']} ({mat['per_m2']:g} u/m²)", "u", units,
            mat["pack_label"], math.ceil(units) if units else 0, "couverture")

    # 2. Écran sous-toiture HPV
    ecran = round(s_ramp * (1 + p["ecran_recouvrement_pct"] / 100.0), 1)
    add("Subtelha respirável", "m²", ecran, "rouleau",
        math.ceil(ecran / p["ecran_roll_m2"]) if ecran else 0, "couverture")

    # 3. Liteaux / voliges
    liteau_ml = round(s_ramp / p["liteau_entraxe_m"], 1) if p["liteau_entraxe_m"] else 0
    add(f"Ripas (afastamento {p['liteau_entraxe_m'] * 100:g} cm)", "ml", liteau_ml, "liteau",
        math.ceil(liteau_ml * loss / p["liteau_length_m"]) if liteau_ml else 0, "couverture")

    # 4. Faîtage + arêtiers (tuiles faîtières)
    faite_ml = faitage + aretiers
    if faite_ml:
        add("Cumeeira + rincões — telhas de cumeeira", "ml", faite_ml, "faîtière",
            math.ceil(faite_ml * p["faitiere_per_ml"]), "faitage")
        add("Remate ventilado de cumeeira/rincão", "ml", faite_ml, "ml",
            math.ceil(faite_ml * loss), "faitage")

    # 5. Noues (zinguerie)
    if noues:
        add("Noue zinc", "ml", noues, "ml", math.ceil(noues * loss), "noues")

    # 6. Rives
    if rives:
        add("Empenas (telhas/remates de empena)", "ml", rives, "ml", math.ceil(rives * loss), "rives")

    # 7. Égout — gouttières + closoir peigne
    if egout:
        add("Caleira (beirado)", "ml", egout, "ml", math.ceil(egout * loss), "egout")
        add("Pente / grelha anti-aves de beirado", "ml", egout, "ml", math.ceil(egout * loss), "egout")

    return {"material": material, "material_label": mat["label"],
            "surface_projetee_m2": round(s_proj, 1), "surface_rampante_m2": s_ramp,
            "pente_pct": round(pente, 1), "angle_deg": angle_deg,
            "lengths": {"faitage_ml": faitage, "aretiers_ml": aretiers, "noues_ml": noues,
                        "rives_ml": rives, "egout_ml": egout},
            "items": items, "loss_pct": p["loss_pct"]}


def to_csv(items: list) -> str:
    rows = ["Designation;Quantite;Unite;Commandable_qty;Commandable_unite;Confiance"]
    for it in items:
        rows.append(";".join(str(x) for x in [
            it.get("designation", ""), it.get("qty", ""), it.get("unit", ""),
            it.get("commandable_qty", ""), it.get("commandable_unit", ""),
            it.get("confidence", ""),
        ]))
    return "\n".join(rows)
