"""Contrôles déterministes du BuildingModel (avant tout calcul).

Chaque contrôle renvoie des anomalies {code, level, message, fix}. Un seul niveau
« bloquant » interdit de déclarer le dossier « prêt » : c'est la règle qui manquait
dans l'ancien moteur (pastilles vertes malgré des erreurs de lecture).
"""
from __future__ import annotations

import math

from .model import Model

BLOCK, WARN, INFO = "bloquant", "attention", "info"


def _a(code, level, msg, fix=""):
    return {"code": code, "level": level, "message": msg, "fix": fix}


def check_openings(m: Model) -> list[dict]:
    out = []
    for side in m.raw["sides"]:
        length = m.side_length(side)
        for lv in m.levels:
            ops = sorted(m.openings_on(side, lv.id), key=lambda o: o.a)
            for o in ops:
                if o.a < m.t_tot - 1e-6 or o.b > length - m.t_tot + 1e-6:
                    out.append(_a("GEO-01", BLOCK, f"{o.id} déborde du mur {side} ({o.a:.2f}–{o.b:.2f} m)", "Relire la cote de la baie"))
                if o.width <= 0.3:
                    out.append(_a("GEO-02", BLOCK, f"{o.id} : largeur {o.width:.2f} m invraisemblable", "Relire la baie"))
                if o.sill + o.height > m.storey_height(lv.id) - 0.10 and lv.id != m.levels[-1].id:
                    out.append(_a("GEO-03", BLOCK, f"{o.id} : baie plus haute que l'étage", "Relire la hauteur"))
            for p, q in zip(ops, ops[1:]):
                pier = round(q.a - p.b, 3)
                if pier <= 0:
                    out.append(_a("GEO-04", BLOCK, f"{p.id} et {q.id} se chevauchent (trumeau {pier:.2f} m) — baie comptée deux fois ?", "Supprimer le doublon ou corriger les positions"))
                elif pier < 0.20:
                    out.append(_a("GEO-05", WARN, f"Trumeau de {pier:.2f} m entre {p.id} et {q.id} : poteau BA obligatoire", "Prévoir un poteau BA"))
    return out


def check_levels(m: Model) -> list[dict]:
    out = []
    for lv in m.levels:
        h = m.storey_height(lv.id)
        if lv.id != m.levels[-1].id and not (2.0 <= h <= 4.0):
            out.append(_a("GEO-10", BLOCK, f"Hauteur d'étage {lv.name} = {h:.2f} m invraisemblable", "Relire la coupe"))
        if lv.hsp < 1.80 and lv.use != "annexe":
            out.append(_a("GEO-11", BLOCK, f"{lv.name} : HSP {lv.hsp:.2f} m < 1,80 m pour un niveau habité", "Vérifier l'usage du niveau"))
    top = m.levels[-1]
    hab = [r for r in m.rooms(top.id) if r["type"] in ("chambre", "salle_eau")]
    if hab and not top.use.startswith("habitation"):
        out.append(_a("GEO-12", BLOCK, "Le comble contient des chambres mais n'est pas classé habitation", "Classer le comble en catégorie A"))
    return out


def check_rooms(m: Model) -> list[dict]:
    out = []
    for lv in m.levels:
        for r in m.rooms(lv.id):
            area = sum((p["x1"] - p["x0"]) * (p["y1"] - p["y0"]) for p in [r] + r.get("parts", []))
            pc = r.get("area_pc")
            if pc and lv.id != m.levels[-1].id and abs(area - pc) / pc > 0.15 and r["type"] not in ("circulation", "entree"):
                out.append(_a("GEO-20", WARN, f"{lv.name} / {r['name']} : surface relevée {area:.2f} m² ≠ PC {pc:.2f} m²", "Contrôler les cotes de la pièce"))
    return out


def check_stair(m: Model) -> list[dict]:
    out = []
    s = m.stair
    B, Lc = s["x1"] - s["x0"], s["y1"] - s["y0"]
    for w in [w for lv in m.levels[1:] for w in m.raw["interior_walls"].get(lv.id, [])]:
        cx, cy = (w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2
        if s["x0"] + 0.05 < cx < s["x1"] - 0.05 and s["y0"] + 0.05 < cy < s["y1"] - 0.05:
            out.append(_a("GEO-30", BLOCK, f"Un mur ({w['kind']}) passe dans la trémie d'escalier", "Relire le plan"))
    walk = stair_walking_line(B, Lc)
    for f in s["flights"]:
        H = m.level(f["to"]).floor_top - m.level(f["from"]).floor_top
        n = math.ceil(H / 0.18)
        h = H / n
        g = min(walk / (n - 1), 0.29)
        if g < 0.21:
            out.append(_a("GEO-31", BLOCK, f"Escalier {f['from']}→{f['to']} : giron {g*100:.0f} cm, ne tient pas dans la cage {B:.2f}×{Lc:.2f}", "Revoir la cage ou le type d'escalier"))
        elif 2 * h + g < 0.59:
            out.append(_a("GEO-32", WARN, f"Escalier {f['from']}→{f['to']} : Blondel 2h+g = {(2*h+g)*100:.0f} cm (raide)", "À valider avec l'escaliéteur"))
    return out


def stair_walking_line(B: float, Lc: float, flight=0.85, core=0.10) -> float:
    """Ligne de foulée d'un escalier à deux quarts tournants dans une cage B × Lc
    (deux volées parallèles séparées par un noyau). Foulée au milieu de la volée."""
    r = core / 2 + flight / 2
    straight = max(Lc - B / 2, 0)
    return 2 * straight + math.pi * r


def check_hypotheses(m: Model, results: dict | None = None) -> list[dict]:
    out = []
    hyp = m.raw.get("user_hypotheses", {})
    if results:
        if hyp.get("floor_system") and results["floors"]["system"] != hyp["floor_system"]:
            out.append(_a("HYP-01", BLOCK, "Le système de plancher calculé ne respecte pas l'hypothèse du client", "Recalculer"))
        if hyp.get("masonry") and results["masonry"]["material"] != hyp["masonry"]:
            out.append(_a("HYP-02", BLOCK, "La maçonnerie calculée ne respecte pas l'hypothèse du client", "Recalculer"))
    return out


def run_all(m: Model) -> list[dict]:
    return check_openings(m) + check_levels(m) + check_rooms(m) + check_stair(m)
