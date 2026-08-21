"""Métré structure béton par calques (DWG/DXF de coffrage).

Extrait des quantités RÉELLES depuis la géométrie du plan (calques nommés type
BEGT : Murs, Poutre, Poteaux, Dalle, Linteaux, réservations…) puis les chiffre.

Deux étapes séparées :
- `extract_structural_metre(doc, unit_to_m)` : quantités géométriques brutes
  (indépendantes des hypothèses de hauteur/épaisseur) — calculées à l'import.
- `cost_structural(metre, params)` : applique hauteurs/épaisseurs/prix pour
  produire volumes béton, m² coffrage, aciers, comptages et lots chiffrés
  (recalculable quand l'utilisateur change les paramètres).
"""
from __future__ import annotations

import math
import re
from collections import Counter

try:
    from ezdxf import bbox as _ezbbox
except Exception:  # pragma: no cover
    _ezbbox = None

# Mots-clés de calques → catégories (FR + norme US/NCS AIA). Recherche sous-chaîne.
_WALL = ("mur", "wall", "voile")
# Distinction porteur béton vs cloison/architecture (pour ne chiffrer que le béton)
_WALL_ARCH = ("a-wall", "i-wall", "cloison", "partition", "doublage", "-part")
_WALL_STRUCT = ("voile", "s-wall", "s-cwal", "s-conc", "porteur", "beton", "béton",
                "coffrage", "mur ba", "mur-ba", "s-wal")
_BEAM = ("poutre", "beam")
_COL = ("poteau", "cols", "colon", "column")
_LINTEL = ("linteau", "lintel")
_SLAB = ("dalle", "flor", "floor", "slab", "plancher")
_RESA = ("servation", "resa", "opening", "penetr", "trémie", "tremie")
_DOOR = ("porte", "door", "-dr-", "a-door")
_WIN = ("fenetre", "fenêtre", "window", "glaz", "baie")


def _layer(e) -> str:
    return (getattr(e.dxf, "layer", "") or "").lower()


def _line_len(e) -> float:
    if e.dxftype() == "LINE":
        return math.dist((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
    return 0.0


def _lwpoly_len_area(e):
    """Longueur et aire (si fermée) d'une LWPOLYLINE."""
    try:
        pts = [(p[0], p[1]) for p in e.vertices()]
    except Exception:
        return 0.0, 0.0
    if len(pts) < 2:
        return 0.0, 0.0
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    closed = bool(getattr(e, "closed", False) or (hasattr(e.dxf, "flags") and e.dxf.flags & 1))
    area = 0.0
    if closed and len(pts) >= 3:
        s = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts)))
        area = abs(s) / 2.0
        length += math.dist(pts[-1], pts[0])
    return length, area


def _match(layer: str, keys) -> bool:
    return any(k in layer for k in keys)


def _seg(e):
    """(a, b, angle_deg[0..180), length, ux, uy) pour une LINE, sinon None."""
    a = (e.dxf.start.x, e.dxf.start.y)
    b = (e.dxf.end.x, e.dxf.end.y)
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy)
    if ln < 1e-6:
        return None
    ang = math.degrees(math.atan2(dy, dx)) % 180
    return (a, b, ang, ln, dx / ln, dy / ln)


def _detect_thickness(segs, unit_to_m, gmin_m=0.08, gmax_m=0.70, tol_ang=3.0):
    """Mesure l'épaisseur dominante entre traits parallèles proches (trait double).
    Retourne (mode_m, distribution{cm:count}) ou (None, {})."""
    import collections as _c
    gmin, gmax = gmin_m / unit_to_m, gmax_m / unit_to_m
    buckets = _c.defaultdict(list)
    for s in segs:
        if s and s[3] * unit_to_m > 0.2:  # ignore < 20 cm
            buckets[round(s[2] / tol_ang)].append(s)
    gaps = _c.Counter()
    for arr in buckets.values():
        n = len(arr)
        if n > 600:  # borne perf
            arr = arr[:600]; n = 600
        for i in range(n):
            a1, _b1, ang1, l1, ux, uy = arr[i]
            nx, ny = -uy, ux
            for j in range(i + 1, n):
                a2, _b2, ang2, l2, _, _ = arr[j]
                if abs(((ang1 - ang2 + 90) % 180) - 90) > tol_ang:
                    continue
                d = abs((a2[0] - a1[0]) * nx + (a2[1] - a1[1]) * ny)
                if not (gmin <= d <= gmax):
                    continue
                t1a, t1b = a1[0] * ux + a1[1] * uy, _b1[0] * ux + _b1[1] * uy
                t2a, t2b = a2[0] * ux + a2[1] * uy, _b2[0] * ux + _b2[1] * uy
                lo1, hi1 = sorted((t1a, t1b)); lo2, hi2 = sorted((t2a, t2b))
                if min(hi1, hi2) - max(lo1, lo2) < min(l1, l2) * 0.3:
                    continue
                gaps[round(d * unit_to_m * 100)] += 1  # en cm
    if not gaps:
        return None, {}
    mode_cm = gaps.most_common(1)[0][0]
    return round(mode_cm / 100.0, 3), {str(k): v for k, v in gaps.most_common(10)}


def extract_structural_metre(doc, unit_to_m: float) -> dict:
    """Parcourt le modelspace et agrège les quantités par catégorie de calque."""
    msp = doc.modelspace()
    U = unit_to_m

    wall_len = beam_len = col_len = lintel_len = 0.0
    partition_len = 0.0
    slab_area_units = 0.0
    col_inserts = 0
    openings = Counter()
    opening_details: list[dict] = []
    resa_ngf: list[str] = []
    resa_dims: list[str] = []
    resa_types: Counter = Counter()
    layer_line_len: Counter = Counter()
    wall_segs: list = []
    beam_segs: list = []
    col_segs: list = []
    col_sections_units: list = []  # (w, h) en unités dessin, par poteau

    def _entity_wh(ent):
        """Largeur/hauteur (unités dessin) de la bbox d'une entité (bloc INSERT inclus)."""
        if _ezbbox is None:
            return None
        try:
            bb = _ezbbox.extents([ent], fast=True)
        except Exception:
            return None
        if not bb.has_data:
            return None
        w = float(bb.size.x)
        h = float(bb.size.y)
        return (w, h) if (w > 0 and h > 0) else None

    for e in msp:
        t = e.dxftype()
        L = _layer(e)
        if t == "LINE":
            ln = _line_len(e)
            if _match(L, _WALL):
                if _match(L, _WALL_ARCH) and not _match(L, _WALL_STRUCT):
                    partition_len += ln          # cloison / architecture → non béton
                else:
                    wall_len += ln; wall_segs.append(_seg(e))  # voile porteur béton
            elif _match(L, _BEAM): beam_len += ln; beam_segs.append(_seg(e))
            elif _match(L, _COL): col_len += ln; col_segs.append(_seg(e))
            elif _match(L, _LINTEL): lintel_len += ln
            if ln:
                layer_line_len[getattr(e.dxf, "layer", "?")] += ln
        elif t in ("LWPOLYLINE", "POLYLINE"):
            ln, ar = _lwpoly_len_area(e)
            if _match(L, _SLAB):
                slab_area_units += ar
            if _match(L, _COL):
                col_inserts += 1
                wh = _entity_wh(e)
                if wh:
                    col_sections_units.append(wh)
            elif _match(L, _WALL):
                if _match(L, _WALL_ARCH) and not _match(L, _WALL_STRUCT):
                    partition_len += ln
                else:
                    wall_len += ln
            elif _match(L, _BEAM): beam_len += ln
        elif t == "INSERT":
            nm = (e.dxf.name or "")
            low = nm.lower()
            if _match(L, _COL) or "poteau" in low:
                col_inserts += 1
                wh = _entity_wh(e)
                if wh:
                    col_sections_units.append(wh)
            is_door = _match(low, _DOOR) or _match(L, _DOOR)
            is_win = _match(low, _WIN) or _match(L, _WIN)
            if is_door or is_win:
                openings["portes" if is_door else "fenetres"] += 1
                m = re.search(r"(\d{2,3})[xX](\d{2,3})", nm)
                label = (nm.split("-")[0].strip() or nm)[:60]
                opening_details.append({
                    "kind": "porte" if is_door else "fenetre",
                    "label": label,
                    "w_cm": int(m.group(1)) if m else None,
                    "h_cm": int(m.group(2)) if m else None,
                })
        elif t == "MTEXT" and _match(L, _RESA):
            txt = (e.text or "").replace("\n", " ").strip()
            if txt.lower().startswith("ai"):
                resa_ngf.append(txt)
            elif re.match(r"^(ø|Ø|\d+\s*x\s*\d+)", txt):
                resa_dims.append(txt)
            elif txt in ("Elec", "VB", "PLB", "CH", "EU", "EV", "EP", "Gaine"):
                resa_types[txt] += 1

    def m(v):  # unités dessin → mètres
        return round(v * U, 2)

    # Trait double → longueur d'axe ≈ longueur totale / 2
    walls_ml = round(m(wall_len) / 2, 1)
    partitions_ml = round(m(partition_len) / 2, 1)
    # Repli : plan de coffrage sans calque « voile » dédié → les murs (A-WALL) SONT le béton
    wall_source = "structure"
    if walls_ml == 0 and partitions_ml > 0:
        walls_ml, partitions_ml, wall_source = partitions_ml, 0.0, "archi_fallback"
    beams_ml = round(m(beam_len) / 2, 1)
    columns_count = col_inserts
    linteaux_ml = round(m(lintel_len) / 2, 1)
    slab_area_m2 = round(slab_area_units * U * U, 1)

    ngf_vals = []
    for s in resa_ngf:
        mm = re.search(r"(\d+[.,]\d+)", s)
        if mm:
            ngf_vals.append(float(mm.group(1).replace(",", ".")))
    resa_count = max(len(resa_ngf), len(resa_dims))

    # Détection automatique des sections depuis la géométrie (trait double)
    wall_th, wall_dist = _detect_thickness(wall_segs, U)
    beam_w, beam_dist = _detect_thickness(beam_segs, U)
    col_sz, _cd = _detect_thickness(col_segs, U, gmin_m=0.12, gmax_m=0.90)

    # Sections de poteaux lues par plan (bbox de chaque bloc/rectangle poteau)
    col_sections = []
    col_area_units = 0.0
    for (w, h) in col_sections_units:
        wm, hm = round(w * U, 3), round(h * U, 3)
        if 0.10 <= wm <= 2.0 and 0.10 <= hm <= 2.0:   # section béton plausible
            col_sections.append({"w_cm": round(wm * 100), "h_cm": round(hm * 100)})
            col_area_units += w * h
    col_area_m2 = round(col_area_units * U * U, 3)

    detected = {
        "wall_thickness_m": wall_th,
        "wall_thickness_dist_cm": wall_dist,
        "beam_w_m": beam_w,
        "beam_w_dist_cm": beam_dist,
        "col_size_m": col_sz,
        "col_sections": col_sections[:400],
        "col_area_m2": col_area_m2,
    }

    return {
        "source": "dxf_layers",
        "unit_to_m": U,
        "walls_ml": walls_ml,
        "partitions_ml": partitions_ml,
        "wall_source": wall_source,
        "beams_ml": beams_ml,
        "columns_count": columns_count,
        "col_area_m2": col_area_m2,
        "linteaux_ml": linteaux_ml,
        "slab_area_m2": slab_area_m2,
        "detected": detected,
        "openings": {
            "portes": openings.get("portes", 0),
            "fenetres": openings.get("fenetres", 0),
            "details": opening_details[:400],
        },
        "reservations": {
            "count": resa_count,
            "by_type": dict(resa_types),
            "ngf": sorted(set(round(v, 3) for v in ngf_vals)),
            "dims": resa_dims[:200],
        },
        "ngf_levels": sorted(set(round(v, 3) for v in ngf_vals)),
        "layers_line_ml": {k: round(v * U, 1) for k, v in layer_line_len.most_common(25)},
    }


# ---- Chiffrage --------------------------------------------------------------
DEFAULTS = {
    "storey_height_m": 2.70,
    "n_levels": 1,
    "wall_thickness_m": 0.20,
    "beam_w_m": 0.20, "beam_h_m": 0.50,
    "col_w_m": 0.20, "col_h_m": 0.20,
    "slab_thickness_m": 0.20,
    "margin_pct": 12.0,
    "tva_rate": 0.20,
    "include_second_oeuvre": True,
    # Gros œuvre immeuble : aucune cloison, tous les murs sont des voiles béton
    "partitions_as_concrete": True,
    # Arases NGF (m) : si fournies, hauteur des voiles/poteaux = AS - AI
    "arase_inf_m": None,
    "arase_sup_m": None,
    # Utiliser les sections de poteaux lues sur le plan (bbox) plutôt qu'uniforme
    "use_detected_col_sections": True,
}
# Prix unitaires structure (€ HT) — fourniture + pose
PRICES = {
    "beton_voile":   190.0,  # m³ C25/30 murs/voiles coulés
    "coffrage_voile": 45.0,  # m² coffrage 2 faces (par m² de paroi)
    "acier_voile":     1.5,  # kg
    "beton_poutre":  260.0,  # m³
    "coffrage_poutre": 55.0,  # m²
    "acier_poutre":    1.6,
    "beton_poteau":  300.0,  # m³
    "acier_poteau":    1.6,
    "beton_dalle":   170.0,  # m³
    "coffrage_dalle": 40.0,  # m² (sous-face + étaiement)
    "acier_dalle":     1.45,
    "linteau_ml":     35.0,  # ml linteau BA
    "reservation_u":  45.0,  # u — traçage + coffrage réservation
    "huisserie_u":    90.0,  # u — pré-cadre / réservation baie
    "installation_chantier": 8000.0,
    "echafaudage":         12000.0,
    "protection_securite":  6000.0,
}
# Ratios aciers kg/m³
REBAR = {"voile": 60.0, "poutre": 120.0, "poteau": 130.0, "dalle": 85.0}


def _line(desig, detail, unit, qty, pu):
    qty = round(qty, 2)
    return {"designation": desig, "detail": detail, "unit": unit,
            "qty": qty, "pu": pu, "total": round(qty * pu, 2)}


def cost_structural(metre: dict, params: dict | None = None) -> dict:
    det = metre.get("detected") or {}
    # Valeurs détectées sur le plan → défauts (surchargées par l'utilisateur si fournies)
    auto = {k: det[k] for k in ("wall_thickness_m", "beam_w_m") if det.get(k)}
    if det.get("col_size_m"):
        auto["col_w_m"] = det["col_size_m"]
        auto["col_h_m"] = det["col_size_m"]
    p = {**DEFAULTS, **auto, **{k: v for k, v in (params or {}).items() if v is not None}}
    P = {**PRICES, **((params or {}).get("prices") or {})}
    h = float(p["storey_height_m"])
    nlv = max(1, int(p["n_levels"]))
    tw = float(p["wall_thickness_m"])
    bw, bh = float(p["beam_w_m"]), float(p["beam_h_m"])
    cw, ch = float(p["col_w_m"]), float(p["col_h_m"])
    ts = float(p["slab_thickness_m"])

    # Hauteur des éléments verticaux (voiles/poteaux) : si les arases NGF sont
    # fournies, hauteur = arase supérieure (AS) - arase inférieure (AI), sinon
    # la hauteur d'étage. C'est la méthode métreur pour un plan de coffrage.
    ai_v, as_v = p.get("arase_inf_m"), p.get("arase_sup_m")
    h_vert = h
    h_label = f"H {h} m"
    if ai_v not in (None, "", 0, "0") and as_v not in (None, "", 0, "0"):
        ai_v, as_v = float(ai_v), float(as_v)
        if as_v > ai_v:
            h_vert = round(as_v - ai_v, 3)
            h_label = f"H {h_vert} m (AS {as_v} − AI {ai_v})"

    walls_ml = float(metre.get("walls_ml", 0)) * nlv
    # Gros œuvre : sur les plans coffrage immeuble il n'existe pas de cloison,
    # tous les murs relevés sont des voiles béton → on additionne les cloisons.
    partitions_ml = float(metre.get("partitions_ml", 0))
    if p.get("partitions_as_concrete", True) and partitions_ml:
        walls_ml += partitions_ml * nlv
    beams_ml = float(metre.get("beams_ml", 0)) * nlv
    cols = int(metre.get("columns_count", 0)) * nlv
    lint_ml = float(metre.get("linteaux_ml", 0)) * nlv
    # Aire dalle : override utilisateur prioritaire (souvent non fermée sur le plan)
    slab_base = p.get("slab_area_m2")
    slab_base = float(slab_base) if slab_base not in (None, "", 0, "0") else float(metre.get("slab_area_m2", 0))
    slab_m2 = slab_base * nlv
    resa = int((metre.get("reservations") or {}).get("count", 0))
    op = metre.get("openings") or {}
    huiss = int(op.get("portes", 0)) + int(op.get("fenetres", 0))

    # Volumes / surfaces
    wall_face = round(walls_ml * h_vert, 1)         # m² de paroi (une face)
    wall_m3 = round(walls_ml * h_vert * tw, 2)
    wall_cof = round(wall_face * 2, 1)              # 2 faces
    wall_ac = round(wall_m3 * REBAR["voile"], 0)

    beam_m3 = round(beams_ml * bw * bh, 2)
    beam_cof = round(beams_ml * (bw + 2 * bh), 1)
    beam_ac = round(beam_m3 * REBAR["poutre"], 0)

    # Poteaux : volume à partir des sections lues par plan si disponibles,
    # sinon section uniforme (largeur × épaisseur).
    col_area = float(metre.get("col_area_m2", 0) or 0) * nlv
    use_plan_cols = p.get("use_detected_col_sections", True) and col_area > 0
    if use_plan_cols:
        col_m3 = round(col_area * h_vert, 2)
        col_detail = f"{cols} poteaux (sections lues sur plan) × {h_label}"
    else:
        col_m3 = round(cols * cw * ch * h_vert, 2)
        col_detail = f"{cols} × {cw}×{ch} m × {h_label}"
    col_ac = round(col_m3 * REBAR["poteau"], 0)

    slab_m3 = round(slab_m2 * ts, 2)
    slab_ac = round(slab_m3 * REBAR["dalle"], 0)

    lots = []

    struct_lines = []
    if walls_ml:
        struct_lines += [
            _line("Voiles / murs béton — béton C25/30",
                  f"{walls_ml} ml × {h_label} × ép. {tw} m", "m³", wall_m3, P["beton_voile"]),
            _line("Coffrage voiles (2 faces)", f"{wall_face} m² × 2 faces", "m²", wall_cof, P["coffrage_voile"]),
            _line("Aciers voiles", f"{REBAR['voile']} kg/m³", "kg", wall_ac, P["acier_voile"]),
        ]
    if beams_ml:
        struct_lines += [
            _line("Poutres béton — béton C25/30", f"{beams_ml} ml × {bw}×{bh} m", "m³", beam_m3, P["beton_poutre"]),
            _line("Coffrage poutres", f"{beams_ml} ml", "m²", beam_cof, P["coffrage_poutre"]),
            _line("Aciers poutres", f"{REBAR['poutre']} kg/m³", "kg", beam_ac, P["acier_poutre"]),
        ]
    if cols:
        struct_lines += [
            _line("Poteaux béton — béton C25/30", col_detail, "m³", col_m3, P["beton_poteau"]),
            _line("Aciers poteaux", f"{REBAR['poteau']} kg/m³", "kg", col_ac, P["acier_poteau"]),
        ]
    if slab_m2:
        struct_lines += [
            _line("Dalle / plancher béton", f"{slab_m2} m² × ép. {ts} m", "m³", slab_m3, P["beton_dalle"]),
            _line("Coffrage + étaiement dalle", f"{slab_m2} m²", "m²", slab_m2, P["coffrage_dalle"]),
            _line("Aciers dalle", f"{REBAR['dalle']} kg/m³", "kg", slab_ac, P["acier_dalle"]),
        ]
    if lint_ml:
        struct_lines.append(_line("Linteaux béton armé", f"{lint_ml} ml", "ml", lint_ml, P["linteau_ml"]))
    if struct_lines:
        lots.append({"lot": "Structure béton (métré plan)", "lines": struct_lines})

    div = []
    if resa:
        div.append(_line("Réservations (traçage + coffrage)",
                         f"{resa} réservations relevées sur plan", "u", resa, P["reservation_u"]))
    if huiss:
        div.append(_line("Huisseries — pré-cadres / réservations de baies",
                         f"{op.get('portes',0)} portes + {op.get('fenetres',0)} fenêtres", "u", huiss, P["huisserie_u"]))
    if div:
        lots.append({"lot": "Réservations & huisseries", "lines": div})

    lots.append({"lot": "Installation & sécurité", "lines": [
        _line("Installation de chantier — base vie, clôture, benne", "forfait", "forfait", 1, P["installation_chantier"]),
        _line("Échafaudage périphérique — location, montage & démontage", "forfait", "forfait", 1, P["echafaudage"]),
        _line("Protection collective & sécurité — garde-corps, filets, PPSPS", "forfait", "forfait", 1, P["protection_securite"]),
    ]})

    all_lines = [ln for l in lots for ln in l["lines"]]
    ht_brut = round(sum(ln["total"] for ln in all_lines), 2)
    margin = float(p["margin_pct"]) / 100.0
    ht = round(ht_brut * (1 + margin), 2)
    tva = round(ht * float(p["tva_rate"]), 2)

    totals = {
        "beton_m3": round(wall_m3 + beam_m3 + col_m3 + slab_m3, 2),
        "acier_kg": round(wall_ac + beam_ac + col_ac + slab_ac, 0),
        "coffrage_m2": round(wall_cof + beam_cof + slab_m2, 1),
        "walls_ml": round(walls_ml, 1), "beams_ml": round(beams_ml, 1),
        "columns": cols, "slab_m2": round(slab_m2, 1),
        "height_m": h_vert, "height_source": "arases" if h_label != f"H {h} m" else "etage",
        "reservations": resa, "huisseries": huiss,
        "ht_brut": ht_brut, "margin_pct": p["margin_pct"], "ht": ht,
        "tva_rate": p["tva_rate"], "tva": tva, "ttc": round(ht + tva, 2),
    }
    return {"lots": lots, "totals": totals, "params": p}
