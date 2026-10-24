"""Moteur « Plans d'exécution Électricité & Plomberie » (MEP) — ConstruPilot.

Moteur DÉTERMINISTE : l'IA (lecture de plans) ne fournit que la géométrie (pièces,
ouvertures, appareils repérés) ; l'implantation, le dimensionnement et les contrôles
sont calculés ici par des règles testables (NF C 15-100 / NF DTU 60.11 en France,
RTIEBT / DR 23/95 au Portugal).

    from engines.mep import generate, recompute
    study = generate(data)                       # proposition complète
    study = recompute(study_input, edits)        # après modification par le professionnel
"""
from __future__ import annotations

import copy

from . import checks, electrical, equipment as equipment_mod, plumbing, quantities
from .i18n import tr
from .model import build
from .rules import rules_for

ENGINE_VERSION = "mep-1.0.0"


def generate(data: dict, edits: dict | None = None) -> dict:
    """Calcule l'étude complète.

    `edits` (facultatif) remplace la proposition automatique :
      {"points": [...], "equipment": [...]}  — positions validées / déplacées par l'utilisateur.
    """
    data = copy.deepcopy(data)
    country = (data.get("country") or "fr").lower()
    lang = data.get("lang") or ("pt" if country == "pt" else "fr")
    rules = rules_for(country)
    levels, options = build(data)
    if not levels or not any(lv.rooms for lv in levels):
        raise ValueError("Nenhuma divisão utilizável: verifique a leitura da planta (divisões fechadas)." if lang == "pt" else
                         "Nenhuma divisão utilizável: verifique a leitura da planta (divisões fechadas).")
    edits = edits or {}
    equipment = edits.get("equipment") or equipment_mod.plan_equipment(levels, options)
    points = edits.get("points") or electrical.layout(levels, equipment, options, rules)
    for p in points:
        p.pop("circuit_id", None)
    elec = electrical.network(points, levels, options, rules)
    plumb = plumbing.network(equipment, levels, options, rules)
    controls = checks.run(levels, points, equipment, elec, plumb, options, rules, lang)
    bom = quantities.build(points, elec, plumb, equipment, options, rules, lang)
    summary = {
        "status": "error" if any(c["status"] == "error" for c in controls)
        else "warning" if any(c["status"] == "warning" for c in controls) else "ok",
        "errors": sum(1 for c in controls if c["status"] == "error"),
        "warnings": sum(1 for c in controls if c["status"] == "warning"),
        "circuits": len(elec["circuits"]), "rcds": len(elec["rcds"]),
        "points": len(points), "fixtures": sum(1 for f in equipment if f["kind"] in rules["plumbing"]["fixtures"]),
        "habitable_m2": round(sum(r.area for lv in levels for r in lv.rooms
                                  if r.type not in ("garage", "exterieur", "escalier")), 1),
    }
    return {
        "engine": ENGINE_VERSION, "country": country, "lang": lang, "norms": rules["label"],
        "disclaimer": tr(lang, "disclaimer"),
        "input": data, "options": options,
        "levels": [{"id": lv.id, "name": lv.name, "elevation_m": lv.elevation, "height_m": lv.height,
                    "rooms": [{"id": r.id, "name": r.name, "type": r.type, "area_m2": round(r.area, 2),
                               "polygon": [[round(x, 3), round(y, 3)] for x, y in r.polygon]} for r in lv.rooms],
                    "openings": [{"kind": o.kind, "a": list(o.a), "b": list(o.b), "exterior": o.exterior}
                                 for o in lv.openings]} for lv in levels],
        "equipment": equipment, "points": points,
        "electrical": elec, "plumbing": plumb, "checks": controls, "quantities": bom, "summary": summary,
    }


def recompute(study: dict, edits: dict) -> dict:
    """Recalcule une étude après modification de l'implantation par le professionnel."""
    return generate(study["input"], {
        "points": edits.get("points") or study.get("points"),
        "equipment": edits.get("equipment") or study.get("equipment"),
    })
