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
    "cloison":    {"label": "Divisória (pladur)", "unit": "m2", "color": "#a855f7", "family": "area"},
    "placo":      {"label": "Forro / pladur (1 face)",    "unit": "m2", "color": "#8b5cf6", "family": "area"},
    "plafond":    {"label": "Teto em pladur / teto falso", "unit": "m2", "color": "#6366f1", "family": "area"},
    "isolation":  {"label": "Isolamento",                    "unit": "m2", "color": "#f59e0b", "family": "area"},
    "peinture":   {"label": "Pintura",                     "unit": "m2", "color": "#22c55e", "family": "area"},
    "parquet":    {"label": "Soalho",                      "unit": "m2", "color": "#b45309", "family": "area"},
    "carrelage":  {"label": "Revestimento cerâmico (pavimento)",              "unit": "m2", "color": "#0d9488", "family": "area"},
    "faience":    {"label": "Azulejo (parede)",                "unit": "m2", "color": "#14b8a6", "family": "area"},
    "chape":      {"label": "Betonilha",                        "unit": "m2", "color": "#64748b", "family": "area"},
    "enduit":     {"label": "Estuque / barramento",          "unit": "m2", "color": "#94a3b8", "family": "area"},
    "chauffage_sol": {"label": "Piso radiante (hidráulico)", "unit": "m2", "color": "#ef4444", "family": "area"},
    "ragreage":   {"label": "Autonivelante",                 "unit": "m2", "color": "#78716c", "family": "area"},
    "etancheite": {"label": "Impermeabilização sob cerâmica", "unit": "m2", "color": "#0ea5e9", "family": "area"},
    "demolition": {"label": "Desmontagem / demolição",          "unit": "m2", "color": "#525252", "family": "area"},
    "plinthes":   {"label": "Rodapés",                     "unit": "ml", "color": "#7c3aed", "family": "length"},
    "escalier":   {"label": "Escada",                     "unit": "u",  "color": "#e11d48", "family": "count"},
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
    "plaque_ba13": "Plaque BA13 (m²)", "plaque_hydro": "Placa hidrófuga (m²)",
    "ossature_ml": "Estrutura metálica (ml)", "vis_u": "Parafusos (u)",
    "bande_enduit_m2": "Fita + massa de juntas (m²)", "laine_m2": "Lã mineral (m²)",
    "isolant_pse_m2": "Isolante EPS (m²)", "souscouche_l": "Primário (l)",
    "peinture_l": "Tinta (l)", "mo_peinture_m2": "MO pintura (m²)",
    "parquet_m2": "Parquet lames (m²)", "souscouche_acou_m2": "Subcamada acústica (m²)",
    "plinthe_ml": "Plinthe (ml)", "carreau_sol_m2": "Mosaico de pavimento (m²)",
    "carreau_mur_m2": "Azulejo de parede (m²)", "colle_kg": "Cimento-cola (kg)",
    "joint_kg": "Joint (kg)", "mortier_chape_m3": "Argamassa de betonilha (m³)", "enduit_m2": "Estuque (m²)",
    "mo_pose_placo_m2": "MO aplicação pladur (m²)", "mo_pose_cloison_m2": "MO pose cloison (m²)",
    "mo_pose_isolation_m2": "MO pose isolation (m²)", "mo_pose_carrelage_m2": "MO assentamento de pavimento cerâmico (m²)",
    "mo_pose_faience_m2": "MO assentamento de azulejo (m²)", "mo_pose_parquet_m2": "MO pose parquet (m²)",
    "mo_pose_chape_m2": "MO pose chape (m²)", "mo_pose_plafond_m2": "MO pose plafond (m²)",
    "mo_pose_plinthe_ml": "MO pose plinthe (ml)", "escalier_forfait": "Escada valor global (u)",
    "escalier_marche": "Marche / habillage (u)",
    "per_tube_m2": "Tubo PEX + isolante (m²)", "dalle_liquide_m2": "Betonilha fluida de envolvimento (m²)",
    "mo_pose_pcbt_m2": "MO piso radiante (m²)", "ragreage_m2": "Autonivelante (m²)",
    "mo_ragreage_m2": "MO autonivelante (m²)", "sel_m2": "Impermeabilização sob cerâmica (m²)", "mo_sel_m2": "MO impermeabilização (m²)",
    "mo_demolition_m2": "MO desmontagem/demolição (m²)", "evacuation_m2": "Remoção de entulho (m²)",
}
RATIO_LABELS: dict[str, str] = {
    "chutes_plaque": "Desperdício de placas (×)", "cloison_faces": "Faces cloison (×)",
    "cloison_ossature_ml_m2": "Estrutura de divisória (ml/m²)", "cloison_isolant_chutes": "Desperdício de isolante de divisória (×)",
    "placo_ossature_ml_m2": "Estrutura de forro (ml/m²)", "isolant_chutes": "Desperdício de isolante (×)",
    "souscouche_l_m2": "Primário (l/m²)", "peinture_l_m2_couche": "Tinta (l/m²/demão)",
    "parquet_souscouche_chutes": "Desperdício de subcamada de soalho (×)", "parquet_chutes": "Desperdício de soalho (×)",
    "plinthe_ratio": "Rodapés (ml/m²)", "carrelage_chutes": "Desperdício de mosaico (×)",
    "faience_chutes": "Desperdício de azulejo (×)", "colle_kg_m2": "Cimento-cola (kg/m²)",
    "faience_colle_kg_m2": "Cola de azulejo (kg/m²)", "joint_kg_m2": "Joint (kg/m²)",
    "faience_joint_kg_m2": "Betume de juntas de azulejo (kg/m²)", "chape_ep_m": "Espessura da betonilha (m)",
    "plinthes_chutes": "Desperdício de rodapés (×)",
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
            _line("Placas de gesso cartonado 13 mm (2 faces)", f"área × {faces} faces × {_r(R, 'chutes_plaque')} (chutes)", "m²", q * faces * _r(R, "chutes_plaque"), _price(P, "plaque_ba13")),
            _line("Estrutura metálica (calhas + montantes)", f"≈ {_r(R,'cloison_ossature_ml_m2')} ml/m²", "ml", q * _r(R, "cloison_ossature_ml_m2"), _price(P, "ossature_ml")),
            _line("Isolante de lã mineral", f"área × {_r(R, 'cloison_isolant_chutes')}", "m²", q * _r(R, "cloison_isolant_chutes"), _price(P, "laine_m2")),
            _line("Parafusos + fita de juntas + massa", "tratamento das juntas (2 faces)", "m²", q * faces, _price(P, "bande_enduit_m2")),
            _line("Mão de obra de montagem de divisória", "montagem + acabamento", "m²", q, _price(P, "mo_pose_cloison_m2")),
        ]
    elif poste in ("placo", "plafond"):
        mo = "mo_pose_plafond_m2" if poste == "plafond" else "mo_pose_placo_m2"
        L += [
            _line("Placas de gesso cartonado 13 mm", f"área × {_r(R, 'chutes_plaque')} (chutes)", "m²", q * _r(R, "chutes_plaque"), _price(P, "plaque_ba13")),
            _line("Estrutura (perfis / tirantes)", f"≈ {_r(R,'placo_ossature_ml_m2')} ml/m²", "ml", q * _r(R, "placo_ossature_ml_m2"), _price(P, "ossature_ml")),
            _line("Parafusos + fita de juntas + massa", "tratamento das juntas", "m²", q, _price(P, "bande_enduit_m2")),
            _line("Mão de obra de aplicação", "fixação + acabamento", "m²", q, _price(P, mo)),
        ]
        if params.get("with_isolation"):
            L.insert(1, _line("Isolante de lã mineral", f"área × {_r(R, 'isolant_chutes')}", "m²", q * _r(R, "isolant_chutes"), _price(P, "laine_m2")))
    elif poste == "isolation":
        key = "isolant_pse_m2" if params.get("isolant") == "pse" else "laine_m2"
        L += [
            _line("Isolante", f"área × {_r(R, 'isolant_chutes')}", "m²", q * _r(R, "isolant_chutes"), _price(P, key)),
            _line("Mão de obra de aplicação do isolamento", "", "m²", q, _price(P, "mo_pose_isolation_m2")),
        ]
    elif poste == "peinture":
        couches = int(params.get("couches", 2))
        L += [
            _line("Primário de impressão", f"≈ {_r(R,'souscouche_l_m2')} l/m²", "l", q * _r(R, "souscouche_l_m2"), _price(P, "souscouche_l")),
            _line(f'Tinta ({couches} couches)', f"≈ {round(_r(R,'peinture_l_m2_couche') * couches, 2)} l/m²", "l", q * _r(R, "peinture_l_m2_couche") * couches, _price(P, "peinture_l")),
            _line("Mão de obra de aplicação", "preparação + aplicação", "m²", q, _price(P, "mo_peinture_m2")),
        ]
    elif poste == "parquet":
        perim_ratio = float(params.get("plinthe_ratio", _r(R, "plinthe_ratio")))
        L += [
            _line("Subcamada acústica", f"área × {_r(R, 'parquet_souscouche_chutes')}", "m²", q * _r(R, "parquet_souscouche_chutes"), _price(P, "souscouche_acou_m2")),
            _line("Parquet (lames)", f"área × {_r(R, 'parquet_chutes')} (coupes)", "m²", q * _r(R, "parquet_chutes"), _price(P, "parquet_m2")),
            _line("Rodapés", f"≈ {perim_ratio} ml/m²", "ml", q * perim_ratio, _price(P, "plinthe_ml")),
            _line("Mão de obra de aplicação", "", "m²", q, _price(P, "mo_pose_parquet_m2")),
        ]
    elif poste in ("carrelage", "faience"):
        carreau = "carreau_sol_m2" if poste == "carrelage" else "carreau_mur_m2"
        mo = "mo_pose_carrelage_m2" if poste == "carrelage" else "mo_pose_faience_m2"
        chutes = _r(R, "carrelage_chutes") if poste == "carrelage" else _r(R, "faience_chutes")
        colle = _r(R, "colle_kg_m2") if poste == "carrelage" else _r(R, "faience_colle_kg_m2")
        joint = _r(R, "joint_kg_m2") if poste == "carrelage" else _r(R, "faience_joint_kg_m2")
        L += [
            _line("Azulejos", f'área × {chutes} (coupes)', "m²", q * chutes, _price(P, carreau)),
            _line("Cola para azulejo", f"≈ {colle} kg/m²", "kg", q * colle, _price(P, "colle_kg")),
            _line("Betume de juntas", f"≈ {joint} kg/m²", "kg", q * joint, _price(P, "joint_kg")),
            _line("Mão de obra de aplicação", "", "m²", q, _price(P, mo)),
        ]
    elif poste == "chape":
        ep = float(params.get("ep_m", _r(R, "chape_ep_m")))
        L += [
            _line("Argamassa de betonilha", f'área × esp. {ep} m', "m³", q * ep, _price(P, "mortier_chape_m3")),
            _line("Mão de obra de betonilha", "sarrafada + talochada", "m²", q, _price(P, "mo_pose_chape_m2")),
        ]
    elif poste == "enduit":
        L += [_line("Estuque / barramento", "preparação + acabamento", "m²", q, _price(P, "enduit_m2"))]
    elif poste == "chauffage_sol":
        L += [
            _line("Tubo PEX + placas isolantes", "circuito de piso radiante", "m²", q, _price(P, "per_tube_m2")),
            _line("Betonilha fluida de envolvimento", "envolvimento dos circuitos", "m²", q, _price(P, "dalle_liquide_m2")),
            _line("Mão de obra de piso radiante", "pose circuits + essais pression", "m²", q, _price(P, "mo_pose_pcbt_m2")),
        ]
    elif poste == "ragreage":
        L += [
            _line("Autonivelante", "fourniture", "m²", q, _price(P, "ragreage_m2")),
            _line("Mão de obra de autonivelante", "primário + aplicação", "m²", q, _price(P, "mo_ragreage_m2")),
        ]
    elif poste == "etancheite":
        L += [
            _line("Sistema de impermeabilização sob cerâmica", "membrana / resina em zonas húmidas", "m²", q, _price(P, "sel_m2")),
            _line("Mão de obra de impermeabilização", "application + bandes", "m²", q, _price(P, "mo_sel_m2")),
        ]
    elif poste == "demolition":
        L += [
            _line("Desmontagem / demolição", "corte + desmontagem", "m²", q, _price(P, "mo_demolition_m2")),
            _line("Remoção do entulho", "tri + benne", "m²", q, _price(P, "evacuation_m2")),
        ]
    elif poste == "plinthes":
        L += [
            _line("Rodapés", f"comprimento × {_r(R, 'plinthes_chutes')} (coupes)", "ml", q * _r(R, "plinthes_chutes"), _price(P, "plinthe_ml")),
            _line("Mão de obra de aplicação de rodapés", "", "ml", q, _price(P, "mo_pose_plinthe_ml")),
        ]
    elif poste == "escalier":
        n = max(0, int(params.get("nb_marches", 0)))
        L += [_line("Escada (valor global)", "fornecimento + aplicação", "u", q, _price(P, "escalier_forfait"))]
        if n:
            L += [_line("Revestimento / degraus", f"{n} marches", "u", q * n, _price(P, "escalier_marche"))]
    return L


def estimate(poste: str, quantity: float, params: dict | None = None) -> dict:
    """Chiffrage d'un poste : composition déterministe + totaux (marge + TVA)."""
    params = params or {}
    if poste not in POSTES:
        raise ValueError(f'Artigo desconhecido: {poste}')
    q = round(float(quantity or 0), 3)
    if q <= 0:
        raise ValueError("Quantidade inválida")
    P = {**PRICES, **((params.get("prices") or {}))}
    R = {**RATIOS, **((params.get("ratios") or {}))}
    lines = _compose(poste, q, params, P, R)
    ht = round(sum(l["total"] for l in lines), 2)
    margin_pct = float(params.get("margin_pct", 0) or 0)
    ht_marge = round(ht * (1 + margin_pct / 100.0), 2)
    tva_rate = float(params.get("tva_rate", 0.23) or 0.23)
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
