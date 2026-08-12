"""Iter16 — Tests bugs quantités (Shopping optimizer + Estimation lots).

Vérifie :
- Calculateurs (insulation/paint/drywall) retournent des matériaux packagés (pas m² brut).
- /api/estimation/compute avec liste de lots produit des quantités réalistes via DEFAULT_LOT_FACTORS.
- /api/estimation/analyse renvoie des lots cohérents.
- /api/prices/optimize renvoie un total shopping réaliste.
- DEFAULT_LOT_FACTORS exposé dans catalog.py contient bien les valeurs cibles.
"""
import os
import sys
import requests

def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")
API = f"{BASE_URL}/api"

sys.path.insert(0, "/app/backend")


# ---------------------------- DEFAULT_LOT_FACTORS ----------------------------

EXPECTED_FACTORS = {
    "demolition": 0.90, "fondations": 0.30, "maconnerie": 0.20, "toiture": 1.10,
    "facade": 0.90, "menuiseries": 0.08, "electricite": 1.00, "plomberie": 1.00,
    "chauffage": 1.00, "isolation": 1.40, "placo": 1.80, "carrelage": 0.35,
    "parquet": 0.50, "peinture": 2.90, "cuisine": 0.03, "salle_de_bain": 0.06,
    "terrasse": 0.20, "dechets": 1.00,
}


def test_default_lot_factors_dict_exposed():
    from engines.catalog import DEFAULT_LOT_FACTORS
    for k, v in EXPECTED_FACTORS.items():
        assert k in DEFAULT_LOT_FACTORS, f"missing key {k}"
        assert abs(DEFAULT_LOT_FACTORS[k] - v) < 1e-6, (
            f"factor {k}: got {DEFAULT_LOT_FACTORS[k]} expected {v}"
        )


# ---------------------------- BUG #1 CALCULATORS ----------------------------

def _call_calc(key, params):
    r = requests.post(f"{API}/calculators/{key}", json={"params": params}, timeout=30)
    assert r.status_code == 200, f"{key} -> {r.status_code} : {r.text[:200]}"
    return r.json()


def _find_material(mats, name_substr):
    for m in mats:
        if name_substr.lower() in m["name"].lower():
            return m
    return None


def test_calc_insulation_vapor_membrane_packaged():
    data = _call_calc("insulation", {"area": 64, "material": "laine_de_verre"})
    mats = data["materials"]
    membrane = _find_material(mats, "membrane pare-vapeur")
    assert membrane is not None, f"membrane not found in {[m['name'] for m in mats]}"
    assert membrane["unit"] == "rouleau", f"unit={membrane['unit']}"
    assert membrane["quantity"] == 1, f"qty={membrane['quantity']} (expected 1 for 64 m²)"

    adhesif = _find_material(mats, "adhésif pare-vapeur")
    assert adhesif is not None
    assert adhesif["unit"] == "rouleau"
    # ceil(64*1.06 / 40) = ceil(67.84/40) = 2
    assert adhesif["quantity"] == 2, f"adhesif qty={adhesif['quantity']}"


def test_calc_paint_packaged_pot_10L():
    data = _call_calc("paint", {"length": 4, "width": 4, "height": 2.5})
    mats = data["materials"]
    peinture = _find_material(mats, "peinture murale")
    assert peinture is not None
    assert peinture["unit"] == "pot 10L"
    # Rough sanity: 2 pots suffit largement pour ~15L
    assert peinture["quantity"] == 2, f"paint qty={peinture['quantity']}"


def test_calc_drywall_plafond_barres():
    data = _call_calc("drywall", {"area": 50, "structure": "plafond"})
    mats = data["materials"]
    rail = _find_material(mats, "rail r48")
    montant = _find_material(mats, "montant m48")
    fourrure = _find_material(mats, "fourrure")
    suspente = _find_material(mats, "suspente")

    assert rail and rail["unit"] == "barre", f"rail={rail}"
    # rails = ceil(50*0.9)=45 ml / 3 = 15
    assert rail["quantity"] == 15, f"rail qty={rail['quantity']}"

    assert montant and montant["unit"] == "barre"
    # studs = ceil(50*1.7)=85 ml / 3 = 29
    assert montant["quantity"] == 29, f"montant qty={montant['quantity']}"

    assert fourrure and fourrure["unit"] == "barre"
    assert fourrure["quantity"] >= 1

    assert suspente and suspente["unit"] == "lot"
    assert suspente["quantity"] == 1


# ---------------------------- BUG #1 SHOPPING E2E ----------------------------

def test_prices_optimize_membrane_quantity_preserved():
    payload = {"items": [
        {"query": "membrane pare vapeur 75m2 rouleau", "quantity": 1,
         "name": "Membrane pare-vapeur (rouleau 75 m²)"},
        {"query": "laine de verre 200 mm", "quantity": 68, "name": "Laine 200mm"},
        {"query": "adhesif pare vapeur", "quantity": 2, "name": "Adhésif"},
    ]}
    r = requests.post(f"{API}/prices/optimize", json=payload, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    multi = data.get("multi_supplier") or {}
    lines = multi.get("lines") or data.get("lines") or []
    # Find membrane line
    membrane_line = next((l for l in lines if "membrane" in (l.get("name") or l.get("query") or "").lower()), None)
    assert membrane_line, f"membrane line not found. lines={lines[:2]}"
    assert membrane_line.get("quantity") == 1, f"qty={membrane_line.get('quantity')}"
    total = multi.get("total") or data.get("total") or 0
    print(f"optimize total={total}")
    assert total < 2000, f"total too high: {total}"


# ---------------------------- BUG #2 ESTIMATION COMPUTE ----------------------------

EXPECTED_QUANTITIES = {
    "fondations": (45, "m³"),
    "maconnerie": (22.5, "m²"),
    "toiture": (165, "m²"),
    "menuiseries": (12, "u"),
    "electricite": (150, "m²"),
    "plomberie": (150, "m²"),
    "chauffage": (150, "m²"),
    "isolation": (210, "m²"),
    "placo": (270, "m²"),
    "carrelage": (52.5, "m²"),
    "parquet": (75, "m²"),
    "peinture": (435, "m²"),
    "cuisine": (4.5, "ml"),
    "salle_de_bain": (9, "m²"),
    "facade": (135, "m²"),
    "terrasse": (30, "m²"),
    "dechets": (150, "m²"),
}


def test_estimation_compute_realistic_quantities():
    body = {
        "project_type": "renovation_complete", "country": "FR",
        "region": "Île-de-France", "city": "Paris", "surface": 150,
        "building_type": "maison", "construction_year": 1990, "condition": "bon",
        "finish_level": "standard",
        "lots": ["fondations", "maconnerie", "toiture", "menuiseries", "electricite",
                 "plomberie", "chauffage", "isolation", "placo", "carrelage",
                 "parquet", "peinture", "cuisine", "salle_de_bain", "facade",
                 "terrasse", "dechets"],
    }
    r = requests.post(f"{API}/estimation/compute", json=body, timeout=30)
    assert r.status_code == 200, r.text[:300]
    est = r.json()
    lots = {l["key"]: l for l in est["lots"]}
    errors = []
    for key, (exp_qty, exp_unit) in EXPECTED_QUANTITIES.items():
        if key not in lots:
            errors.append(f"MISSING {key}")
            continue
        got = lots[key]["quantity"]
        unit = lots[key]["unit"]
        if abs(got - exp_qty) > 0.5:
            errors.append(f"{key}: qty={got} unit={unit} (expected {exp_qty} {exp_unit})")
        if unit != exp_unit:
            errors.append(f"{key}: unit={unit} expected {exp_unit}")

    # Bug guard : aucune quantité pour menuiseries/cuisine/salle_de_bain doit être 150
    for k in ("menuiseries", "cuisine", "salle_de_bain"):
        assert lots[k]["quantity"] != 150, f"BUG: {k} quantity is still 150"
    assert not errors, "Estimation errors:\n" + "\n".join(errors)


# ---------------------------- BUG #2 ANALYSE (Smart Project) ----------------------------

def test_estimation_analyse_realistic_lots():
    body = {"description": (
        "Je veux rénover totalement ma maison de 150 m² à Paris avec 12 fenêtres, "
        "refaire la toiture, la façade, la cuisine et la salle de bain. Standard."
    )}
    r = requests.post(f"{API}/estimation/analyse", json=body, timeout=90)
    assert r.status_code == 200, r.text[:300]
    payload = r.json()
    est = payload["estimation"]
    lots = {l["key"]: l for l in est["lots"]}
    # Check no absurd defaults (150 for u/ml/m² pieces humides)
    if "menuiseries" in lots:
        assert lots["menuiseries"]["quantity"] < 20, (
            f"menuiseries qty={lots['menuiseries']['quantity']} unit={lots['menuiseries']['unit']}"
        )
    if "cuisine" in lots:
        assert lots["cuisine"]["quantity"] < 20, f"cuisine qty={lots['cuisine']['quantity']}"
    if "salle_de_bain" in lots:
        assert lots["salle_de_bain"]["quantity"] < 20, f"sdb qty={lots['salle_de_bain']['quantity']}"
    # Total dans fourchette réno complète 150 m² IDF
    total = est.get("total_avg", 0)
    print(f"analyse total_avg={total}")
    assert 80_000 <= total <= 300_000, f"total_avg={total} hors fourchette"


# ---------------------------- NON-REGRESSION ----------------------------

def test_estimation_compute_no_lot_keys_backward_compat():
    """Le comportement du template renovation_complete SANS lot_keys explicites doit rester inchangé."""
    body = {
        "project_type": "renovation_complete", "surface": 100, "country": "FR",
        "region": "Île-de-France", "building_type": "maison", "condition": "bon",
        "finish_level": "standard",
    }
    r = requests.post(f"{API}/estimation/compute", json=body, timeout=30)
    assert r.status_code == 200, r.text[:300]
    est = r.json()
    lot_keys = {l["key"] for l in est["lots"]}
    # Template renovation_complete keys
    expected_keys = {"demolition", "maconnerie", "placo", "isolation", "electricite",
                     "plomberie", "chauffage", "carrelage", "parquet", "peinture",
                     "menuiseries", "cuisine", "salle_de_bain", "dechets"}
    assert expected_keys.issubset(lot_keys), f"missing: {expected_keys - lot_keys}"
    # menuiseries qty for 100 m² → 100 * 0.08 = 8
    men = next(l for l in est["lots"] if l["key"] == "menuiseries")
    assert men["quantity"] == 8, f"menuiseries={men['quantity']}"


def test_login_demo():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "demo@construpilot.fr", "password": "Demo2026!"},
                      timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert "access_token" in r.json() or "token" in r.json()


def test_share_sms_config():
    r = requests.get(f"{API}/share/sms/config", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data.get("twilio_enabled") is True, f"twilio_enabled={data.get('twilio_enabled')}"


def test_push_public_key():
    r = requests.get(f"{API}/push/public-key", timeout=20)
    assert r.status_code == 200
    key = r.json().get("public_key") or r.json().get("publicKey")
    assert key, "no push public key"


def test_admin_revenue_kpis():
    # Login admin
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@construpilot.fr", "password": "Construpilot2026!"},
                      timeout=30)
    assert r.status_code == 200
    tok = r.json().get("access_token") or r.json().get("token")
    r2 = requests.get(f"{API}/admin/revenue/kpis",
                      headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r2.status_code == 200, r2.text[:200]
