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
                if o.a < m.t_str - 1e-6 or o.b > length - m.t_str + 1e-6:      # la baie ne peut pas entamer le mur en retour (le doublage s'arrête au tableau)
                    out.append(_a("GEO-01", BLOCK, f"{o.id} déborde du mur {side} ({o.a:.2f}–{o.b:.2f} m)", "Relire la cote de la baie"))
                if o.width <= 0.3:
                    out.append(_a("GEO-02", BLOCK, f"{o.id} : largeur {o.width:.2f} m invraisemblable", "Relire la baie"))
                st = m.raw.get("stair") or {}
                stair_win = (m.side(side)["axis"] == "y" and st and o.a < st.get("x1", -1) and o.b > st.get("x0", 1e9)
                             and (abs(m.side(side)["pos"] - st.get("y0", -9)) < 0.6 or abs(m.side(side)["pos"] - st.get("y1", -9)) < 0.6)) or \
                            (m.side(side)["axis"] == "x" and st and o.a < st.get("y1", -1) and o.b > st.get("y0", 1e9)
                             and (abs(m.side(side)["pos"] - st.get("x0", -9)) < 0.6 or abs(m.side(side)["pos"] - st.get("x1", -9)) < 0.6))
                if o.sill + o.height > m.storey_height(lv.id) - 0.10 and lv.id != m.levels[-1].id and not stair_win:
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


def check_spans(m: Model) -> list[dict]:
    """Portée des planchers entre murs porteurs : plage couverte par les poutrelles-hourdis (L/h ≤ 27, h ≤ 30 cm)."""
    out = []
    try:
        L = m.span_y_calc
    except Exception:  # noqa: BLE001
        return [_a("GEO-40", BLOCK, "Largeur ou épaisseur des murs porteurs illisible : portée des planchers incalculable.",
                   "Relever envelope.width_y et wall_structural_thickness sur les plans.")]
    from .structure import HOURDIS, SLENDER_MAX
    lmax = round(SLENDER_MAX * max(h for _, h, _, _ in HOURDIS), 2)
    if L > lmax:
        out.append(_a("GEO-40", BLOCK, f"Portée de plancher {L:.2f} m entre murs porteurs > {lmax:.2f} m (limite poutrelles-hourdis)."
                      .replace(".", ","),
                      "Vérifier le sens porteur et les refends sur les plans (mur ou poutre intermédiaire) ; sinon prévoir une dalle BA ou un plancher porté par poutres."))
    if L < 1.5:
        out.append(_a("GEO-41", BLOCK, f"Portée de plancher {L:.2f} m invraisemblable pour une maison : relevé à vérifier.".replace(".", ","),
                      "Vérifier length_x / width_y et l'orientation (Y = côté court, entre murs porteurs)."))
    if len(m.levels) < 2:
        out.append(_a("GEO-42", BLOCK, "Un seul niveau relevé : aucun plancher à dimensionner — le document ne semble pas être un PC de maison.",
                      "Joindre les plans de niveaux (PCMI 02), coupes (PCMI 03) et façades (PCMI 05)."))
    return out


REQUIRED = {"envelope": "l'enveloppe (longueur × largeur hors tout et épaisseur des murs)",
            "levels": "les niveaux (cotes de plancher et hauteurs sous plafond, sur la coupe)",
            "roof": "la toiture (type, niveaux d'égout et de faîtage, sur la coupe)",
            "openings": "les baies (portes et fenêtres, sur les plans et façades)",
            "stair": "l'escalier (position sur le plan et type, ex. quart tournant)",
            "rooms": "les pièces de chaque niveau",
            "interior_walls": "les murs intérieurs porteurs",
            "geotech": "l'étude de sol G2 (couche porteuse, contrainte admissible, profondeur d'assise)"}


def check_references(m: Model) -> list[dict]:
    """Complétude et cohérence des renvois (une lecture IA peut oublier une section ou citer un niveau inexistant) :
    sans ce contrôle, les calculs plantent au lieu de poser une question claire."""
    out, raw = [], m.raw
    for key, what in REQUIRED.items():
        if not raw.get(key):
            fix = ("Joignez l'étude de sol G2 en PDF, ou indiquez dans votre demande la contrainte admissible (ex. 0,20 MPa) et "
                   "la profondeur d'assise des fondations." if key == "geotech" else f"Vérifiez que le PC joint montre {what}.")
            out.append(_a(f"REF-{key.upper()}", BLOCK, f"Élément manquant dans le relevé : {what}.", fix))
    ids = {lv.id for lv in m.levels}
    refs = []
    for f in (raw.get("stair") or {}).get("flights") or []:
        refs += [("escalier", f.get("from")), ("escalier", f.get("to"))]
    refs += [("baie " + str(o.get("id")), o.get("level")) for o in raw.get("openings") or []]
    refs += [("pièces", k) for k in (raw.get("rooms") or {})] + [("murs intérieurs", k) for k in (raw.get("interior_walls") or {})]
    for where, lid in refs:
        if lid not in ids:
            out.append(_a("REF-LEVEL", BLOCK, f"{where} : niveau « {lid} » introuvable (niveaux relevés : {', '.join(sorted(ids))}).",
                          "Relire la coupe : liste des niveaux et cotes de plancher."))
    return out


def check_coherence(m: Model) -> list[dict]:
    """Contrôles de cohérence géométrique du relevé (en plus des contrôles métier ci-dessus) :
    cotes croissantes, enveloppe fermée, murs dans l'enveloppe, baies sur un côté existant, HSP plausible,
    somme des surfaces ≈ surface de plancher déclarée. Sans eux, une lecture IA fausse passerait au calcul."""
    out, raw = [], m.raw
    for a, b in zip(m.levels, m.levels[1:]):
        if b.floor_top <= a.floor_top:
            out.append(_a("COH-01", BLOCK, f"Cotes de plancher non croissantes : {a.name} ({a.floor_top:+.2f}) ≥ {b.name} ({b.floor_top:+.2f}).",
                          "Relire les cotes de niveau sur la coupe (du plus bas au plus haut)."))
    try:
        L, W = m.L, m.W
    except Exception:  # noqa: BLE001
        L = W = 0.0
    if not (L > 0 and W > 0):
        out.append(_a("COH-02", BLOCK, "Enveloppe non fermée : longueur ou largeur hors tout manquante ou nulle.",
                      "Relever length_x et width_y (dimensions hors tout)."))
    sides = raw.get("sides") or {}
    axes = [s.get("axis") for s in sides.values() if isinstance(s, dict)]
    if len(sides) != 4 or axes.count("x") != 2 or axes.count("y") != 2:
        out.append(_a("COH-03", WARN, f"{len(sides)} côté(s) relevé(s) au lieu de 4 (2 d'axe x, 2 d'axe y).",
                      "Décrire les 4 côtés de l'enveloppe."))
    if L > 0 and W > 0:
        tol = 0.05
        for lid, walls in (raw.get("interior_walls") or {}).items():
            for w in walls or []:
                xs, ys = [w.get("x0", 0.0), w.get("x1", 0.0)], [w.get("y0", 0.0), w.get("y1", 0.0)]
                if min(xs) < -tol or max(xs) > L + tol or min(ys) < -tol or max(ys) > W + tol:
                    out.append(_a("COH-04", BLOCK, f"Mur intérieur hors enveloppe au niveau {lid} "
                                  f"({w.get('x0')},{w.get('y0')}–{w.get('x1')},{w.get('y1')}).",
                                  "Relire les coordonnées (origine au coin extérieur brut, en mètres)."))
    for o in m.openings:
        if o.side not in sides:
            out.append(_a("COH-05", BLOCK, f"Baie {o.id} posée sur un côté inconnu « {o.side} ».",
                          "Poser la baie sur un côté existant (sides)."))
    for lv in m.levels:
        if lv.use.startswith("habitation") and not (2.20 <= lv.hsp <= 3.50):
            out.append(_a("COH-06", WARN, f"{lv.name} : HSP {lv.hsp:.2f} m hors plage courante 2,20–3,50 m.",
                          "Vérifier la hauteur sous plafond sur la coupe."))
    sp = (raw.get("project") or {}).get("surface_plancher")
    if isinstance(sp, (int, float)) and sp > 0:
        tot = 0.0
        for rms in (raw.get("rooms") or {}).values():
            for r in rms or []:
                for part in [r] + (r.get("parts") or []):
                    tot += max(part.get("x1", 0) - part.get("x0", 0), 0) * max(part.get("y1", 0) - part.get("y0", 0), 0)
        if tot and abs(tot - sp) / sp > 0.05:
            out.append(_a("COH-07", WARN, f"Somme des surfaces de pièces {tot:.1f} m² ≠ surface de plancher déclarée {sp:.1f} m² (écart > 5 %).",
                          "Contrôler les cotes des pièces ou la surface de plancher."))
    return out


EC8_Z1 = {"1.1", "1.2", "1.3", "1.4", "1.5", "1.6"}      # zones sismiques action type 1 (NP EN 1998-1 AN PT)
EC8_Z2 = {"2.1", "2.2", "2.3", "2.4", "2.5"}             # action type 2
EC8_SOIL = {"A", "B", "C", "D", "E"}                     # types de terrain EC8
EC8_CLASS = {"I", "II", "III", "IV"}                     # classes d'importance EC8
PT_WIND = {"A", "B"}                                     # zones de vent NP EN 1991-1-4 AN PT
PT_SNOW = {"Z1", "Z2", "Z3"}                             # zones de neige NP EN 1991-1-3 AN PT


def _missing(v) -> bool:
    return v in (None, "") or (isinstance(v, str) and "confirm" in v.lower())


def check_seismic_pt(m: Model) -> list[dict]:
    """Cohérence des données sismiques Eurocode 8 (NP EN 1998-1 AN PT) pour les projets portugais :
    présence et validité des zones (type 1 / type 2), du terrain, de la classe d'importance et du coefficient q.
    Sans cela, un relevé PT incomplet calculerait avec des défauts prudents silencieux."""
    pr = m.raw.get("project") or {}
    if pr.get("country") != "PT":
        return []
    out = []
    for field, label in (("seismic_zone_type1", "zone sismique action type 1"),
                         ("seismic_zone_type2", "zone sismique action type 2"),
                         ("ground_type", "type de terrain"),
                         ("importance_class", "classe d'importance")):
        if _missing(pr.get(field)):
            out.append(_a("SEIS-00", BLOCK, f"Donnée sismique manquante (projet portugais) : {label}.",
                          "Relever la zone (NA NP EN 1998-1), le type de terrain et la classe d'importance, ou les préciser dans la demande."))
    z1 = str(pr.get("seismic_zone_type1", "")).strip()
    if z1 and not _missing(z1) and z1 not in EC8_Z1:
        out.append(_a("SEIS-01", BLOCK, f"Zone sismique type 1 « {z1} » invalide (NP EN 1998-1 : 1.1 à 1.6).", "Corriger la zone type 1."))
    z2 = str(pr.get("seismic_zone_type2", "")).strip()
    if z2 and not _missing(z2) and z2 not in EC8_Z2:
        out.append(_a("SEIS-02", BLOCK, f"Zone sismique type 2 « {z2} » invalide (NP EN 1998-1 : 2.1 à 2.5).", "Corriger la zone type 2."))
    soil = str(pr.get("ground_type", "")).strip().upper()
    if soil and not _missing(soil) and soil not in EC8_SOIL:
        out.append(_a("SEIS-03", BLOCK, f"Type de terrain « {soil} » invalide (EC8 : A à E).", "Corriger le type de terrain."))
    cls = str(pr.get("importance_class", "")).strip().upper()
    if cls and not _missing(cls) and cls not in EC8_CLASS:
        out.append(_a("SEIS-04", BLOCK, f"Classe d'importance « {cls} » invalide (EC8 : I à IV).", "Corriger la classe d'importance (II par défaut)."))
    q = pr.get("behaviour_factor_q")
    if q is not None and not _missing(q):
        try:
            qf = float(q)
            if not (1.0 <= qf <= 5.0):
                out.append(_a("SEIS-05", WARN, f"Coefficient de comportement q = {qf} hors plage courante (1,5–3,0 maçonnerie, ≤ 5,0).",
                              "Vérifier q selon le système structurel (EC8 §5/§9)."))
        except (TypeError, ValueError):
            out.append(_a("SEIS-05", WARN, f"Coefficient de comportement q « {q} » non numérique.", "Renseigner q (ex. 1,5 pour la maçonnerie)."))
    wind = str(pr.get("wind_zone", "")).strip().upper()
    if wind and not _missing(wind) and wind not in PT_WIND:
        out.append(_a("SEIS-06", WARN, f"Zone de vent « {wind} » inhabituelle (NP EN 1991-1-4 AN PT : A ou B).", "Vérifier la zone de vent."))
    snow = str(pr.get("snow_zone", "")).strip().upper()
    if snow and not _missing(snow) and snow not in PT_SNOW:
        out.append(_a("SEIS-07", WARN, f"Zone de neige « {snow} » inhabituelle (NP EN 1991-1-3 AN PT : Z1 à Z3).", "Vérifier la zone de neige."))
    return out


def run_all(m: Model) -> list[dict]:
    ref = check_references(m)
    if any(a["level"] == BLOCK for a in ref):
        return ref                       # inutile (et dangereux) de lancer les autres contrôles sur un relevé incomplet
    out = list(ref)
    for chk in (check_openings, check_levels, check_rooms, check_stair, check_spans, check_coherence, check_seismic_pt):
        try:
            out += chk(m)
        except Exception as exc:  # noqa: BLE001 — un contrôle qui plante devient une question, pas une erreur muette
            out.append(_a("CHK-" + chk.__name__.replace("check_", "").upper(), BLOCK,
                          f"Contrôle « {chk.__name__.replace('check_', '')} » impossible sur ce relevé ({type(exc).__name__}: {exc}).",
                          "Relire la planche concernée et compléter le relevé."))
    return out
