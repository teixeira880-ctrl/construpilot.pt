"""Lot 1 — Combinaisons EN 1990 (ELU/ELS) déterministes, sourcées et éditables.

Applique la MÉTHODOLOGIE PUBLIQUE de l'EN 1990 (format des combinaisons d'actions) ;
ne reproduit aucun texte normatif protégé. Les coefficients pré-remplis sont les
VALEURS USUELLES de l'Annexe Nationale française (γG=1.35, γQ=1.5, ψ0/ψ1/ψ2 par
catégorie), toutes éditables et marquées « à vérifier par l'ingénieur ».

Zéro hallucination : aucune résistance n'est vérifiée, aucune section dimensionnée.
Chaque combinaison générée porte ses facteurs explicites et une source traçable.
"""
from __future__ import annotations

from engines.structuro_calc import Action, Combination, Source

VERSION = "eurocode-en1990-0.1.0"

# EN 1990 Tableau A1.2(B), approche STR, valeurs usuelles NA FR — à vérifier.
GAMMA = {"G_sup": 1.35, "G_inf": 1.00, "Q": 1.50}

# ψ0 (combinaison), ψ1 (fréquente), ψ2 (quasi-permanente).
# Valeurs usuelles NF EN 1990/NA tableau A1.1 — à vérifier par l'ingénieur.
PSI: dict[str, dict] = {
    "A":          {"label": "A — Habitation, résidentiel",            "psi0": 0.7, "psi1": 0.5, "psi2": 0.3},
    "B":          {"label": "B — Bureaux",                            "psi0": 0.7, "psi1": 0.5, "psi2": 0.3},
    "C":          {"label": "C — Lieux de réunion",                   "psi0": 0.7, "psi1": 0.7, "psi2": 0.6},
    "D":          {"label": "D — Commerces",                          "psi0": 0.7, "psi1": 0.7, "psi2": 0.6},
    "E":          {"label": "E — Stockage",                           "psi0": 1.0, "psi1": 0.9, "psi2": 0.8},
    "F":          {"label": "F — Trafic, véhicules ≤ 30 kN",          "psi0": 0.7, "psi1": 0.7, "psi2": 0.6},
    "G":          {"label": "G — Trafic, 30 à 160 kN",               "psi0": 0.7, "psi1": 0.5, "psi2": 0.3},
    "H":          {"label": "H — Toitures (entretien)",              "psi0": 0.0, "psi1": 0.0, "psi2": 0.0},
    "neige_bas":  {"label": "Neige, altitude ≤ 1000 m",              "psi0": 0.5, "psi1": 0.2, "psi2": 0.0},
    "neige_haut": {"label": "Neige, altitude > 1000 m",              "psi0": 0.7, "psi1": 0.5, "psi2": 0.2},
    "vent":       {"label": "Vent",                                  "psi0": 0.6, "psi1": 0.2, "psi2": 0.0},
    "temperature": {"label": "Température (hors incendie)",           "psi0": 0.6, "psi1": 0.5, "psi2": 0.0},
}
_DEFAULT_CAT = "A"
SOURCE_DOC = "EN 1990 — valeurs usuelles NA FR — à vérifier"

DEFAULT_OPTIONS = {"uls": True, "sls_char": True, "sls_freq": False, "sls_qp": True}


def catalog() -> dict:
    return {"version": VERSION, "gamma": GAMMA,
            "categories": [{"key": k, **v} for k, v in PSI.items()]}


def _src(note: str) -> Source:
    return Source(document=SOURCE_DOC, note=note)


def _psi(cat: str, overrides: dict | None) -> dict:
    if overrides and all(k in overrides for k in ("psi0", "psi1", "psi2")):
        return overrides
    return PSI.get(cat or _DEFAULT_CAT, PSI[_DEFAULT_CAT])


def generate(actions: list[Action], categories: dict[str, str] | None = None,
             options: dict[str, bool] | None = None,
             psi_overrides: dict[str, dict] | None = None) -> list[Combination]:
    """Combinaisons EN 1990 pour les actions du modèle. Une ELU/ELS par Q dominante."""
    opt = {**DEFAULT_OPTIONS, **(options or {})}
    categories = categories or {}
    psi_overrides = psi_overrides or {}
    gids = [a.id for a in actions if a.kind == "G"]
    qs = [a for a in actions if a.kind == "Q"]

    def psi_of(q: Action) -> dict:
        return _psi(categories.get(q.id, _DEFAULT_CAT), psi_overrides.get(q.id))

    combos: list[Combination] = []

    if not qs:
        if opt["uls"]:
            combos.append(Combination(id="ELU", label="ELU STR — 1.35·G",
                factors={g: GAMMA["G_sup"] for g in gids},
                source=_src("EN 1990 §6.4.3.2 éq. 6.10 ; γG=1.35 (défavorable), aucune action variable. "
                            "Valeurs usuelles NA FR — à vérifier.")))
        if opt["sls_char"]:
            combos.append(Combination(id="ELScar", label="ELS caractéristique — G",
                factors={g: 1.0 for g in gids},
                source=_src("EN 1990 §6.5.3 éq. 6.14b ; G seul. Valeurs usuelles NA FR — à vérifier.")))
        return combos

    for i, lead in enumerate(qs, start=1):
        if opt["uls"]:
            factors = {g: GAMMA["G_sup"] for g in gids}
            for q in qs:
                factors[q.id] = round(GAMMA["Q"] * (1.0 if q.id == lead.id else psi_of(q)["psi0"]), 4)
            combos.append(Combination(id=f"ELU{i}", label=f"ELU STR — {lead.label} dominante",
                factors=factors,
                source=_src(f"EN 1990 §6.4.3.2 éq. 6.10 ; γG=1.35, γQ=1.5, ψ0 sur accompagnantes. "
                            f"Action dominante : {lead.label}. Valeurs usuelles NA FR — à vérifier.")))
        if opt["sls_char"]:
            factors = {g: 1.0 for g in gids}
            for q in qs:
                factors[q.id] = round(1.0 if q.id == lead.id else psi_of(q)["psi0"], 4)
            combos.append(Combination(id=f"ELScar{i}", label=f"ELS caractéristique — {lead.label} dominante",
                factors=factors,
                source=_src(f"EN 1990 §6.5.3 éq. 6.14b ; Qk,1 + ψ0·Qk,i. Dominante : {lead.label}. "
                            "Valeurs usuelles NA FR — à vérifier.")))
        if opt["sls_freq"]:
            factors = {g: 1.0 for g in gids}
            for q in qs:
                factors[q.id] = round(psi_of(lead)["psi1"] if q.id == lead.id else psi_of(q)["psi2"], 4)
            combos.append(Combination(id=f"ELSfreq{i}", label=f"ELS fréquente — {lead.label} dominante",
                factors=factors,
                source=_src(f"EN 1990 §6.5.3 éq. 6.15b ; ψ1·Qk,1 + ψ2·Qk,i. Dominante : {lead.label}. "
                            "Valeurs usuelles NA FR — à vérifier.")))

    if opt["sls_qp"]:
        factors = {g: 1.0 for g in gids}
        for q in qs:
            factors[q.id] = round(psi_of(q)["psi2"], 4)
        combos.append(Combination(id="ELSqp", label="ELS quasi-permanente",
            factors=factors,
            source=_src("EN 1990 §6.5.3 éq. 6.16b ; ψ2·Qk,i. Valeurs usuelles NA FR — à vérifier.")))
    return combos


def is_uls(case_id: str) -> bool:
    return case_id.startswith("ELU")


def is_sls(case_id: str) -> bool:
    return case_id.startswith("ELS")


def design_envelope(result: dict) -> dict:
    """Combinaison dimensionnante (enveloppe) par élément, sur les combinaisons EN 1990.

    Efforts uniquement : aucune résistance de section n'est vérifiée ici.
    """
    cases = result.get("cases") or []
    uls = [c for c in cases if is_uls(c.get("id", ""))]
    sls = [c for c in cases if is_sls(c.get("id", ""))]
    env: dict[str, dict] = {}
    for c in cases:
        for row in c.get("elements", []):
            env.setdefault(row["id"], {"id": row["id"], "kind": row.get("kind"), "uls": {}, "sls": {}})

    def pick_max(subset, elem_id, key, absval=True):
        best = None
        for c in subset:
            row = next((r for r in c.get("elements", []) if r["id"] == elem_id), None)
            if not row or row.get(key) is None:
                continue
            v = abs(row[key]) if absval else row[key]
            if best is None or v > best["value"]:
                best = {"case": c["id"], "label": c.get("label", c["id"]), "value": round(v, 3)}
        return best

    for eid, e in env.items():
        k = e["kind"]
        if k == "beam":
            for metric, key in (("moment_knm", "moment_max_knm"), ("shear_kn", "shear_max_kn")):
                b = pick_max(uls, eid, key)
                if b:
                    e["uls"][metric] = b
            d = pick_max(sls, eid, "deflection_sampled_mm")
            if d:
                e["sls"]["deflection_mm"] = d
        elif k in ("wall", "column"):
            n = pick_max(uls, eid, "total_kn", absval=False)
            if n:
                e["uls"]["axial_kn"] = n
            st = pick_max(uls, eid, "axial_stress_mpa", absval=False)
            if st:
                e["uls"]["stress_mpa"] = st
        elif k == "footing":
            p = pick_max(uls, eid, "mean_pressure_kpa", absval=False)
            if p:
                e["uls"]["pressure_kpa"] = p

    return {"version": VERSION, "uls_count": len(uls), "sls_count": len(sls),
            "elements": list(env.values()),
            "note": "Enveloppe des combinaisons EN 1990 générées. Efforts seulement ; "
                    "aucune résistance, section ni ferraillage vérifié. À valider par l'ingénieur."}
