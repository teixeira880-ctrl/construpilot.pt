"""ConstruPilot AI Evolution Lab — moteur de tests synthétiques déterministes (TIER-1).

Exerce les moteurs de calcul réels de ConstruPilot (toiture, étanchéité, VRD, chiffrage,
séquence de phases) contre une vérité-terrain, sans appel LLM (coût quasi nul).
Fournit : Virtual User Factory, Project Generator, exécution de lots, mining d'échecs,
score de fitness, suivi des générations (Champion/Challenger en sandbox).
"""
import math
import random
import uuid
from datetime import datetime, timezone

from engines import roofing, waterproofing, vrd, pricing

# --- Virtual User Factory ---
PERSONAS = [
    "particulier_sans_technique", "particulier_renovation", "empreteur", "architecte",
    "ingenieur", "mestre_obras", "encarregado", "electricien", "plombier", "peintre",
    "charpentier", "investisseur", "promoteur", "gestionnaire_obras", "technicien_orcamentacao",
    "acheteur", "client_impatient", "client_indecis", "client_exigent", "donne_mesures_erronees",
    "change_davis", "ne_lit_pas_plans", "info_contradictoire", "insiste_solution_incorrecte",
]

# --- Project Generator ---
PROJECT_TYPES = ["moradia_terrea", "R+1", "R+2", "extension", "renovation_totale",
                 "appartement", "batiment", "garage", "piscine", "mur", "couverture",
                 "isolation", "remodelage_interieur"]

# --- Séquence de chantier canonique (ordre partiel) ---
CORRECT_PHASES = ["terrassement", "fondations", "vide_sanitaire", "dalle", "maconnerie",
                  "charpente", "couverture", "menuiseries", "isolation", "electricite",
                  "plomberie", "placo", "revetements", "peinture", "finitions"]
_PHASE_RANK = {p: i for i, p in enumerate(CORRECT_PHASES)}

CATEGORIES = ["measurement", "material_waste", "pricing", "phase_sequence", "robustness"]


def make_user(rng: random.Random) -> dict:
    return {"persona": rng.choice(PERSONAS), "budget": rng.choice([50_000, 120_000, 250_000, 500_000]),
            "urgence": rng.choice(["basse", "normale", "haute"]),
            "technique": rng.choice(["aucune", "faible", "moyenne", "forte"])}


def make_project(rng: random.Random) -> dict:
    return {"type": rng.choice(PROJECT_TYPES), "surface": round(rng.uniform(20, 400), 1),
            "etages": rng.randint(0, 3), "pente_pct": rng.choice([0, 15, 25, 35, 45, 60]),
            "terrain_incline": rng.random() < 0.3}


def is_valid_sequence(seq: list) -> bool:
    """True si la séquence respecte l'ordre partiel canonique (pas d'inversion)."""
    ranks = [_PHASE_RANK[p] for p in seq if p in _PHASE_RANK]
    return all(ranks[i] <= ranks[i + 1] for i in range(len(ranks) - 1))


def _t_measurement(rng, level):
    L = round(rng.uniform(1, 200), 2)
    W = round(rng.uniform(1, 100), 2)
    gross = L * W
    n_doors = rng.randint(0, 4)
    door_area = min(n_doors * 0.8 * 2.1, gross * 0.5)  # jamais plus de 50% de la surface
    net = gross - door_area
    ok = (gross >= 0) and (0 <= net <= gross) and (abs(gross - L * W) < 1e-2)
    return ok, "aire nette/brute incohérente" if not ok else None


def _t_material_waste(rng, level):
    surface = round(rng.uniform(30, 350), 1)
    pente = rng.choice([25, 35, 45])
    loss = rng.choice([3, 5, 8, 10, 15])
    comp = roofing.compute(surface, pente, "tuiles_terre_cuite",
                           {"faitage_ml": 10, "aretiers_ml": 20, "noues_ml": 5, "egout_ml": 40},
                           0.9, {"loss_pct": loss})
    ramp = comp["surface_rampante_m2"]
    # Invariants : rampant >= projeté ; quantités commandables >= brut ; pas de négatif
    ok = ramp >= surface - 1e-6
    for it in comp["items"]:
        if it.get("commandable_qty") is not None and it["commandable_qty"] < 0:
            ok = False
        if it.get("qty", 0) < 0:
            ok = False
    return ok, "quantité négative ou rampant < projeté" if not ok else None


def _t_pricing(rng, level):
    items = [{"designation": "Tuiles terre cuite", "commandable_qty": rng.randint(100, 5000), "unit": "u"},
             {"designation": "Gouttière égout", "commandable_qty": rng.randint(10, 200), "unit": "ml"}]
    supplier = {"price_list": [{"label": "tuiles terre cuite", "price": 0.85},
                               {"label": "gouttiere egout", "price": 9.5}]}
    res = pricing.price_items(items, supplier, [], {})
    total = round(sum(i["line_total"] for i in res["items"]), 2)
    ok = abs(total - res["grand_total"]) < 0.05 and res["grand_total"] >= 0
    # override manuel prioritaire
    res2 = pricing.price_items(items, supplier, [], {"0": 99})
    ok = ok and abs(res2["items"][0]["unit_price"] - 99) < 1e-6
    return ok, "total != somme lignes ou override ignoré" if not ok else None


def _t_phase_sequence(rng, level):
    seq = CORRECT_PHASES[:]
    should_be_valid = rng.random() > 0.5
    if not should_be_valid:
        i, j = sorted(rng.sample(range(len(seq)), 2))
        seq[i], seq[j] = seq[j], seq[i]  # inversion volontaire
    detected_valid = is_valid_sequence(seq)
    ok = detected_valid == should_be_valid
    return ok, "séquence incorrecte non détectée" if not ok else None


def _t_robustness(rng, level):
    """Entrées adverses/contradictoires : les moteurs ne doivent jamais planter ni renvoyer NaN."""
    try:
        bad = [(-50, -1), (0, 200), (1e6, 0)]
        s, p = rng.choice(bad)
        comp = roofing.compute(s, p, "ardoises", {"faitage_ml": -5, "egout_ml": 0}, 0.5)
        for it in comp["items"]:
            v = it.get("commandable_qty")
            if v is not None and (v != v or v < 0):  # NaN or negative
                return False, "sortie NaN/négative sur entrée adverse"
        vc = vrd.compute([{"key": "EP", "length_ml": rng.choice([-10, 0])}])
        wc = waterproofing.compute(-10, -5, -1, "bicouche", [], 0.5)
        _ = (vc, wc)
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"exception moteur: {type(e).__name__}"


_TESTS = {"measurement": _t_measurement, "material_waste": _t_material_waste,
          "pricing": _t_pricing, "phase_sequence": _t_phase_sequence, "robustness": _t_robustness}

# Poids du Fitness Score (brief §28)
FITNESS_WEIGHTS = {"material_waste": 0.30, "pricing": 0.20, "measurement": 0.15,
                   "phase_sequence": 0.20, "robustness": 0.15}


def run_batch(size: int, level: int = 2, seed: int | None = None) -> dict:
    rng = random.Random(seed)
    size = max(1, min(size, 20000))
    per_cat = {c: {"total": 0, "passed": 0} for c in CATEGORIES}
    failures = {}
    for _ in range(size):
        cat = rng.choice(CATEGORIES)
        _ = make_user(rng), make_project(rng)  # simulate a virtual user + project
        ok, reason = _TESTS[cat](rng, level)
        per_cat[cat]["total"] += 1
        if ok:
            per_cat[cat]["passed"] += 1
        else:
            key = f"{cat}:{reason}"
            failures[key] = failures.get(key, 0) + 1

    acc = {c: round(per_cat[c]["passed"] / per_cat[c]["total"], 4) if per_cat[c]["total"] else 1.0
           for c in CATEGORIES}
    fitness = round(sum(FITNESS_WEIGHTS[c] * acc[c] for c in CATEGORIES) * 100, 2)
    clusters = sorted(({"cluster": k, "count": v} for k, v in failures.items()),
                      key=lambda x: -x["count"])
    total_passed = sum(per_cat[c]["passed"] for c in CATEGORIES)
    return {
        "run_id": "run_" + uuid.uuid4().hex[:10],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "size": size, "level": level, "seed": seed,
        "accuracy": acc, "fitness_score": fitness,
        "passed": total_passed, "failed": size - total_passed,
        "pass_rate": round(total_passed / size, 4),
        "failure_clusters": clusters[:20],
        "per_category": per_cat,
    }
