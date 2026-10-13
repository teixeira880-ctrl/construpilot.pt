"""Systèmes de calcul par corps d'état — même principe que le gros œuvre.

Pour un poste (placo, isolation, peinture, parquet, carrelage, faïence, chape,
cloison, plinthes, escalier…) et une quantité mesurée sur le plan (m², ml ou u),
on décompose l'ouvrage en fournitures + main d'œuvre via des RATIOS déterministes
et documentés (méthode métreur). Aucune quantité inventée par IA.

Les PRIX unitaires sont des DÉFAUTS éditables par l'artisan (comme le gros œuvre) :
ils servent d'estimation de départ, pas d'affirmation de prix de marché.

Sortie alignée sur `cost_structural` : lines[] + totals{} + params{}.
"""
from __future__ import annotations

# Catalogue des postes : unité de base mesurée + libellé + couleur + famille
POSTES: dict[str, dict] = {
    "cloison":    {"label": "Cloison (placo distributive)", "unit": "m2", "color": "#a855f7", "family": "area"},
    "placo":      {"label": "Doublage / placo (1 face)",    "unit": "m2", "color": "#8b5cf6", "family": "area"},
    "plafond":    {"label": "Plafond placo / faux-plafond", "unit": "m2", "color": "#6366f1", "family": "area"},
    "isolation":  {"label": "Isolation",                    "unit": "m2", "color": "#f59e0b", "family": "area"},
    "peinture":   {"label": "Peinture",                     "unit": "m2", "color": "#22c55e", "family": "area"},
    "parquet":    {"label": "Parquet",                      "unit": "m2", "color": "#b45309", "family": "area"},
    "carrelage":  {"label": "Carrelage (sol)",              "unit": "m2", "color": "#0d9488", "family": "area"},
    "faience":    {"label": "Faïence (mur)",                "unit": "m2", "color": "#14b8a6", "family": "area"},
    "chape":      {"label": "Chape",                        "unit": "m2", "color": "#64748b", "family": "area"},
    "enduit":     {"label": "Enduit / ratissage",          "unit": "m2", "color": "#94a3b8", "family": "area"},
    "chauffage_sol": {"label": "Plancher chauffant (hydraulique)", "unit": "m2", "color": "#ef4444", "family": "area"},
    "ragreage":   {"label": "Ragréage sol",                 "unit": "m2", "color": "#78716c", "family": "area"},
    "etancheite": {"label": "Étanchéité sous carrelage (SEL)", "unit": "m2", "color": "#0ea5e9", "family": "area"},
    "demolition": {"label": "Dépose / démolition",          "unit": "m2", "color": "#525252", "family": "area"},
    "plinthes":   {"label": "Plinthes",                     "unit": "ml", "color": "#7c3aed", "family": "length"},
    "escalier":   {"label": "Escalier",                     "unit": "u",  "color": "#e11d48", "family": "count"},
}

# Prix unitaires par défaut (€ HT) — fourniture + pose. À AJUSTER par l'artisan.
PRICES: dict[str, float] = {
    "plaque_ba13": 7.0, "plaque_hydro": 12.0, "ossature_ml": 3.5, "vis_u": 0.03,
    "bande_enduit_m2": 2.5, "laine_m2": 9.0, "isolant_pse_m2": 12.0,
    "souscouche_l": 6.0, "peinture_l": 9.0, "mo_peinture_m2": 9.0,
    "parquet_m2": 35.0, "souscouche_acou_m2": 4.0, "plinthe_ml": 6.0,
    "carreau_sol_m2": 30.0, "carreau_mur_m2": 28.0, "colle_kg": 1.2, "joint_kg": 2.0,
    "mortier_chape_m3": 160.0, "enduit_m2": 6.0,
    "per_tube_m2": 9.0, "dalle_liquide_m2": 22.0, "mo_pose_pcbt_m2": 28.0,
    "ragreage_m2": 8.0, "mo_ragreage_m2": 6.0, "sel_m2": 7.0, "mo_sel_m2": 6.0,
    "mo_demolition_m2": 18.0, "evacuation_m2": 6.0,
    "mo_pose_placo_m2": 18.0, "mo_pose_cloison_m2": 25.0, "mo_pose_isolation_m2": 8.0,
    "mo_pose_carrelage_m2": 35.0, "mo_pose_faience_m2": 40.0, "mo_pose_parquet_m2": 25.0,
    "mo_pose_chape_m2": 15.0, "mo_pose_plafond_m2": 22.0, "mo_pose_plinthe_ml": 5.0,
    "escalier_forfait": 1800.0, "escalier_marche": 120.0,
}


# Ratios de composition par défaut (méthode métreur) — AJUSTABLES par l'artisan.
RATIOS: dict[str, float] = {
    "chutes_plaque": 1.05, "cloison_faces": 2.0, "cloison_ossature_ml_m2": 3.0,
    "cloison_isolant_chutes": 1.05, "placo_ossature_ml_m2": 2.2,
    "isolant_chutes": 1.05, "souscouche_l_m2": 0.12, "peinture_l_m2_couche": 0.12,
    "parquet_souscouche_chutes": 1.02, "parquet_chutes": 1.08, "plinthe_ratio": 0.35,
    "carrelage_chutes": 1.10, "faience_chutes": 1.12, "colle_kg_m2": 5.0,
    "faience_colle_kg_m2": 4.0, "joint_kg_m2": 0.7, "faience_joint_kg_m2": 0.5,
    "chape_ep_m": 0.05, "plinthes_chutes": 1.05,
}

# Libellés lisibles pour l'éditeur (prix)
PRICE_LABELS: dict[str, str] = {
    "plaque_ba13": "Plaque BA13 (m²)", "plaque_hydro": "Plaque hydrofuge (m²)",
    "ossature_ml": "Ossature métal (ml)", "vis_u": "Vis (u)",
    "bande_enduit_m2": "Bande + enduit joints (m²)", "laine_m2": "Laine minérale (m²)",
    "isolant_pse_m2": "Isolant PSE (m²)", "souscouche_l": "Sous-couche (l)",
    "peinture_l": "Peinture (l)", "mo_peinture_m2": "MO peinture (m²)",
    "parquet_m2": "Parquet lames (m²)", "souscouche_acou_m2": "Sous-couche acoustique (m²)",
    "plinthe_ml": "Plinthe (ml)", "carreau_sol_m2": "Carreau sol (m²)",
    "carreau_mur_m2": "Carreau mural (m²)", "colle_kg": "Colle carrelage (kg)",
    "joint_kg": "Joint (kg)", "mortier_chape_m3": "Mortier chape (m³)", "enduit_m2": "Enduit (m²)",
    "mo_pose_placo_m2": "MO pose placo (m²)", "mo_pose_cloison_m2": "MO pose cloison (m²)",
    "mo_pose_isolation_m2": "MO pose isolation (m²)", "mo_pose_carrelage_m2": "MO pose carrelage (m²)",
    "mo_pose_faience_m2": "MO pose faïence (m²)", "mo_pose_parquet_m2": "MO pose parquet (m²)",
    "mo_pose_chape_m2": "MO pose chape (m²)", "mo_pose_plafond_m2": "MO pose plafond (m²)",
    "mo_pose_plinthe_ml": "MO pose plinthe (ml)", "escalier_forfait": "Escalier forfait (u)",
    "escalier_marche": "Marche / habillage (u)",
    "per_tube_m2": "Tube PER + isolant (m²)", "dalle_liquide_m2": "Dalle liquide d'enrobage (m²)",
    "mo_pose_pcbt_m2": "MO plancher chauffant (m²)", "ragreage_m2": "Ragréage autolissant (m²)",
    "mo_ragreage_m2": "MO ragréage (m²)", "sel_m2": "Étanchéité SEL (m²)", "mo_sel_m2": "MO étanchéité (m²)",
    "mo_demolition_m2": "MO dépose/démolition (m²)", "evacuation_m2": "Évacuation gravats (m²)",
}
RATIO_LABELS: dict[str, str] = {
    "chutes_plaque": "Chutes plaques (×)", "cloison_faces": "Faces cloison (×)",
    "cloison_ossature_ml_m2": "Ossature cloison (ml/m²)", "cloison_isolant_chutes": "Chutes isolant cloison (×)",
    "placo_ossature_ml_m2": "Ossature doublage (ml/m²)", "isolant_chutes": "Chutes isolant (×)",
    "souscouche_l_m2": "Sous-couche (l/m²)", "peinture_l_m2_couche": "Peinture (l/m²/couche)",
    "parquet_souscouche_chutes": "Chutes sous-couche parquet (×)", "parquet_chutes": "Chutes parquet (×)",
    "plinthe_ratio": "Plinthes (ml/m²)", "carrelage_chutes": "Chutes carrelage (×)",
    "faience_chutes": "Chutes faïence (×)", "colle_kg_m2": "Colle (kg/m²)",
    "faience_colle_kg_m2": "Colle faïence (kg/m²)", "joint_kg_m2": "Joint (kg/m²)",
    "faience_joint_kg_m2": "Joint faïence (kg/m²)", "chape_ep_m": "Épaisseur chape (m)",
    "plinthes_chutes": "Chutes plinthes (×)",
}


def _line(designation: str, detail: str, unit: str, qty: float, pu: float) -> dict:
    qty = round(float(qty), 3)
    pu = round(float(pu), 2)
    return {"designation": designation, "detail": detail, "unit": unit,
            "qty": qty, "pu": pu, "total": round(qty * pu, 2)}


def _price(P: dict, key: str) -> float:
    return float(P.get(key, PRICES.get(key, 0)))


def _r(R: dict, key: str) -> float:
    return float(R.get(key, RATIOS.get(key, 0)))


def _compose(poste: str, q: float, params: dict, P: dict, R: dict) -> list[dict]:
    """Renvoie les lignes de composition d'un poste pour une quantité q (unité de base)."""
    L: list[dict] = []
    if poste == "cloison":
        faces = _r(R, "cloison_faces")
        L += [
            _line("Plaques BA13 (2 faces)", f"surface × {faces} faces × {_r(R,'chutes_plaque')} (chutes)", "m²", q * faces * _r(R, "chutes_plaque"), _price(P, "plaque_ba13")),
            _line("Ossature métallique (rails + montants)", f"≈ {_r(R,'cloison_ossature_ml_m2')} ml/m²", "ml", q * _r(R, "cloison_ossature_ml_m2"), _price(P, "ossature_ml")),
            _line("Isolant laine minérale", f"surface × {_r(R,'cloison_isolant_chutes')}", "m²", q * _r(R, "cloison_isolant_chutes"), _price(P, "laine_m2")),
            _line("Visserie + bande à joint + enduit", "traitement des joints (2 faces)", "m²", q * faces, _price(P, "bande_enduit_m2")),
            _line("Main d'œuvre pose cloison", "montage + finition", "m²", q, _price(P, "mo_pose_cloison_m2")),
        ]
    elif poste in ("placo", "plafond"):
        mo = "mo_pose_plafond_m2" if poste == "plafond" else "mo_pose_placo_m2"
        L += [
            _line("Plaques BA13", f"surface × {_r(R,'chutes_plaque')} (chutes)", "m²", q * _r(R, "chutes_plaque"), _price(P, "plaque_ba13")),
            _line("Ossature (fourrures / suspentes)", f"≈ {_r(R,'placo_ossature_ml_m2')} ml/m²", "ml", q * _r(R, "placo_ossature_ml_m2"), _price(P, "ossature_ml")),
            _line("Visserie + bande à joint + enduit", "traitement des joints", "m²", q, _price(P, "bande_enduit_m2")),
            _line("Main d'œuvre pose", "fixation + finition", "m²", q, _price(P, mo)),
        ]
        if params.get("with_isolation"):
            L.insert(1, _line("Isolant laine minérale", f"surface × {_r(R,'isolant_chutes')}", "m²", q * _r(R, "isolant_chutes"), _price(P, "laine_m2")))
    elif poste == "isolation":
        key = "isolant_pse_m2" if params.get("isolant") == "pse" else "laine_m2"
        L += [
            _line("Isolant", f"surface × {_r(R,'isolant_chutes')}", "m²", q * _r(R, "isolant_chutes"), _price(P, key)),
            _line("Main d'œuvre pose isolation", "", "m²", q, _price(P, "mo_pose_isolation_m2")),
        ]
    elif poste == "peinture":
        couches = int(params.get("couches", 2))
        L += [
            _line("Sous-couche d'impression", f"≈ {_r(R,'souscouche_l_m2')} l/m²", "l", q * _r(R, "souscouche_l_m2"), _price(P, "souscouche_l")),
            _line(f"Peinture ({couches} couches)", f"≈ {round(_r(R,'peinture_l_m2_couche') * couches, 2)} l/m²", "l", q * _r(R, "peinture_l_m2_couche") * couches, _price(P, "peinture_l")),
            _line("Main d'œuvre application", "prépa + application", "m²", q, _price(P, "mo_peinture_m2")),
        ]
    elif poste == "parquet":
        perim_ratio = float(params.get("plinthe_ratio", _r(R, "plinthe_ratio")))
        L += [
            _line("Sous-couche acoustique", f"surface × {_r(R,'parquet_souscouche_chutes')}", "m²", q * _r(R, "parquet_souscouche_chutes"), _price(P, "souscouche_acou_m2")),
            _line("Parquet (lames)", f"surface × {_r(R,'parquet_chutes')} (coupes)", "m²", q * _r(R, "parquet_chutes"), _price(P, "parquet_m2")),
            _line("Plinthes", f"≈ {perim_ratio} ml/m²", "ml", q * perim_ratio, _price(P, "plinthe_ml")),
            _line("Main d'œuvre pose", "", "m²", q, _price(P, "mo_pose_parquet_m2")),
        ]
    elif poste in ("carrelage", "faience"):
        carreau = "carreau_sol_m2" if poste == "carrelage" else "carreau_mur_m2"
        mo = "mo_pose_carrelage_m2" if poste == "carrelage" else "mo_pose_faience_m2"
        chutes = _r(R, "carrelage_chutes") if poste == "carrelage" else _r(R, "faience_chutes")
        colle = _r(R, "colle_kg_m2") if poste == "carrelage" else _r(R, "faience_colle_kg_m2")
        joint = _r(R, "joint_kg_m2") if poste == "carrelage" else _r(R, "faience_joint_kg_m2")
        L += [
            _line("Carreaux", f"surface × {chutes} (coupes)", "m²", q * chutes, _price(P, carreau)),
            _line("Colle à carrelage", f"≈ {colle} kg/m²", "kg", q * colle, _price(P, "colle_kg")),
            _line("Mortier de joint", f"≈ {joint} kg/m²", "kg", q * joint, _price(P, "joint_kg")),
            _line("Main d'œuvre pose", "", "m²", q, _price(P, mo)),
        ]
    elif poste == "chape":
        ep = float(params.get("ep_m", _r(R, "chape_ep_m")))
        L += [
            _line("Mortier de chape", f"surface × ép. {ep} m", "m³", q * ep, _price(P, "mortier_chape_m3")),
            _line("Main d'œuvre pose chape", "tirée + talochée", "m²", q, _price(P, "mo_pose_chape_m2")),
        ]
    elif poste == "enduit":
        L += [_line("Enduit / ratissage", "prépa + finition", "m²", q, _price(P, "enduit_m2"))]
    elif poste == "chauffage_sol":
        L += [
            _line("Tube PER + plots isolants", "circuit plancher chauffant", "m²", q, _price(P, "per_tube_m2")),
            _line("Dalle / chape liquide d'enrobage", "enrobage des circuits", "m²", q, _price(P, "dalle_liquide_m2")),
            _line("Main d'œuvre plancher chauffant", "pose circuits + essais pression", "m²", q, _price(P, "mo_pose_pcbt_m2")),
        ]
    elif poste == "ragreage":
        L += [
            _line("Ragréage autolissant", "fourniture", "m²", q, _price(P, "ragreage_m2")),
            _line("Main d'œuvre ragréage", "primaire + application", "m²", q, _price(P, "mo_ragreage_m2")),
        ]
    elif poste == "etancheite":
        L += [
            _line("Système d'étanchéité sous carrelage (SEL)", "natte / résine pièces humides", "m²", q, _price(P, "sel_m2")),
            _line("Main d'œuvre étanchéité", "application + bandes", "m²", q, _price(P, "mo_sel_m2")),
        ]
    elif poste == "demolition":
        L += [
            _line("Dépose / démolition", "découpe + dépose", "m²", q, _price(P, "mo_demolition_m2")),
            _line("Évacuation des gravats", "tri + benne", "m²", q, _price(P, "evacuation_m2")),
        ]
    elif poste == "plinthes":
        L += [
            _line("Plinthes", f"longueur × {_r(R,'plinthes_chutes')} (coupes)", "ml", q * _r(R, "plinthes_chutes"), _price(P, "plinthe_ml")),
            _line("Main d'œuvre pose plinthes", "", "ml", q, _price(P, "mo_pose_plinthe_ml")),
        ]
    elif poste == "escalier":
        n = max(0, int(params.get("nb_marches", 0)))
        L += [_line("Escalier (forfait)", "fourniture + pose", "u", q, _price(P, "escalier_forfait"))]
        if n:
            L += [_line("Habillage / marches", f"{n} marches", "u", q * n, _price(P, "escalier_marche"))]
    return L


def estimate(poste: str, quantity: float, params: dict | None = None) -> dict:
    """Chiffrage d'un poste : composition déterministe + totaux (marge + TVA)."""
    params = params or {}
    if poste not in POSTES:
        raise ValueError(f"Poste inconnu: {poste}")
    q = round(float(quantity or 0), 3)
    if q <= 0:
        raise ValueError("Quantité invalide")
    P = {**PRICES, **((params.get("prices") or {}))}
    R = {**RATIOS, **((params.get("ratios") or {}))}
    lines = _compose(poste, q, params, P, R)
    ht = round(sum(l["total"] for l in lines), 2)
    margin_pct = float(params.get("margin_pct", 0) or 0)
    ht_marge = round(ht * (1 + margin_pct / 100.0), 2)
    tva_rate = float(params.get("tva_rate", 0.20) or 0.20)
    tva = round(ht_marge * tva_rate, 2)
    meta = POSTES[poste]
    return {
        "poste": poste, "label": meta["label"], "unit": meta["unit"],
        "family": meta["family"], "color": meta["color"], "quantity": q,
        "lines": lines,
        "totals": {"ht": ht, "margin_pct": margin_pct, "ht_with_margin": ht_marge,
                   "tva_rate": tva_rate, "tva": tva, "ttc": round(ht_marge + tva, 2)},
        "params": {k: v for k, v in params.items() if k not in ("prices", "ratios")},
    }


def catalog() -> list[dict]:
    return [{"key": k, **v} for k, v in POSTES.items()]


def price_schema(overrides: dict | None = None) -> list[dict]:
    ov = overrides or {}
    return [{"key": k, "label": PRICE_LABELS.get(k, k), "default": v,
             "value": ov.get(k, v)} for k, v in PRICES.items()]


def ratio_schema(overrides: dict | None = None) -> list[dict]:
    ov = overrides or {}
    return [{"key": k, "label": RATIO_LABELS.get(k, k), "default": v,
             "value": ov.get(k, v)} for k, v in RATIOS.items()]
