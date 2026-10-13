"""Auto-pilote BET — pont IA→déterministe.

L'IA (Gemini vision) EXTRAIT des faits d'un plan/PC/G2 (probabiliste). Le modèle
structurel, la descente de charges et le dimensionnement restent 100 % DÉTERMINISTES
(aucune valeur inventée par l'IA n'est calculée sans passer par l'écran de validation).

Phase 1 : trame régulière poteaux/poutres/dalles 1 sens + semelles isolées, descente
de charges (moteur gravitaire), combinaisons EN 1990 et pré-dimensionnement des semelles
à partir de la contrainte admissible de la G2. NON EXÉCUTOIRE — à viser par l'ingénieur.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import re

from engines.structuro_calc import (Action, Combination, Element, Load, Model, Source, Support, calculate)
from engines import structuro_eurocode as eurocode

VERSION = "autopilot-0.1.0"

CONCRETE_DENSITY = 25.0            # kN/m³
E_CONCRETE_KPA = 32_000_000.0     # kPa (C25/30, indicatif)

# Charges d'exploitation EN 1991-1-1 (valeurs usuelles NA FR, kN/m²) + catégorie EN 1990
IMPOSED = {
    "habitation": {"q": 1.5, "cat": "A"},
    "bureau": {"q": 2.5, "cat": "B"},
    "commerce": {"q": 5.0, "cat": "D"},
    "parking": {"q": 2.5, "cat": "F"},
    "industriel": {"q": 7.5, "cat": "E"},
    "erp": {"q": 4.0, "cat": "C"},
}
DEFAULT_DEST = "habitation"
DEFAULT_FLOOR_PERM_EXTRA = 1.5    # revêtements + cloisons légères (hors poids propre dalle)
DEFAULT_ROOF_PERM_EXTRA = 1.5     # étanchéité + isolation + protection
DEFAULT_ROOF_VAR = 1.0            # toiture accessible entretien
DEFAULT_SECTIONS = {"col_side_m": 0.30, "beam_width_m": 0.20, "beam_height_m": 0.40, "slab_thickness_m": 0.20}
# Aucune contrainte de sol par défaut : une valeur inventée dimensionnerait des fondations
# fictives. q_ELS/q_ELU viennent du rapport G2 (lecture vérifiée) ou d'une saisie confirmée.
DEFAULT_SOIL = {"q_els_kpa": None, "q_elu_kpa": None, "q_confirmed": False, "foundation_type": "isolee",
                "anchorage_depth_m": 0.8, "water_table": False, "soil_class": "", "mode": "drained",
                "phi_deg": 0.0, "c_kpa": 0.0, "cu_kpa": 0.0, "gamma_soil_kn_m3": 18.0}

MAX_ELEMENTS = 200


# ----------------------------------------------------------------- défauts / normalisation ----

def default_inputs() -> dict:
    return {
        "building": {"destination": DEFAULT_DEST, "levels": 1, "storey_height_m": 2.8, "ground_height_m": 3.0},
        "system": {"structure": "portique", "wall_thickness_m": 0.20, "two_way_slab": False},
        "grid": {"bays_x_m": [4.0, 4.0], "bays_y_m": [4.0]},
        "loads": {"floor_perm_extra_kn_m2": DEFAULT_FLOOR_PERM_EXTRA, "floor_var_kn_m2": IMPOSED[DEFAULT_DEST]["q"],
                  "roof_perm_extra_kn_m2": DEFAULT_ROOF_PERM_EXTRA, "roof_var_kn_m2": DEFAULT_ROOF_VAR},
        "sections": dict(DEFAULT_SECTIONS),
        "soil": dict(DEFAULT_SOIL),
        "prices": {"concrete_eur_m3": 150.0, "steel_eur_kg": 2.0, "formwork_eur_m2": 45.0},
        "incertitudes": [],
    }


def _flist(v, fallback):
    if not isinstance(v, list):
        return list(fallback)
    out = []
    for x in v:
        try:
            f = float(x)
            if math.isfinite(f) and 0.5 <= f <= 30:
                out.append(round(f, 3))
        except (TypeError, ValueError):
            continue
    return out or list(fallback)


def _f(v, fallback, lo=0.0, hi=1e6):
    try:
        f = float(v)
        return f if math.isfinite(f) and lo <= f <= hi else float(fallback)
    except (TypeError, ValueError):
        return float(fallback)


def _opt_f(v, lo: float, hi: float) -> float | None:
    """Valeur numérique optionnelle bornée ; absente/invalide → None (jamais de valeur inventée)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or x <= 0:
        return None
    return max(lo, min(hi, x))


def normalize_inputs(raw: dict | None) -> dict:
    d = default_inputs()
    raw = raw or {}
    b = raw.get("building") or {}
    dest = (b.get("destination") or DEFAULT_DEST).strip().lower()
    if dest not in IMPOSED:
        dest = DEFAULT_DEST
    d["building"]["destination"] = dest
    d["building"]["levels"] = int(max(1, min(12, _f(b.get("levels"), 1, 1, 12))))
    d["building"]["storey_height_m"] = _f(b.get("storey_height_m"), 2.8, 2.0, 6.0)
    d["building"]["ground_height_m"] = _f(b.get("ground_height_m"), 3.0, 2.0, 8.0)

    g = raw.get("grid") or {}
    d["grid"]["bays_x_m"] = _flist(g.get("bays_x_m"), d["grid"]["bays_x_m"])
    d["grid"]["bays_y_m"] = _flist(g.get("bays_y_m"), d["grid"]["bays_y_m"])

    sy = raw.get("system") or {}
    struct = (sy.get("structure") or "portique").strip().lower()
    d["system"]["structure"] = struct if struct in ("portique", "voiles") else "portique"
    d["system"]["wall_thickness_m"] = _f(sy.get("wall_thickness_m"), 0.20, 0.10, 0.60)
    d["system"]["two_way_slab"] = bool(sy.get("two_way_slab"))

    pr = raw.get("prices") or {}
    d["prices"] = {"concrete_eur_m3": _f(pr.get("concrete_eur_m3"), 150.0, 0, 1e4),
                   "steel_eur_kg": _f(pr.get("steel_eur_kg"), 2.0, 0, 100),
                   "formwork_eur_m2": _f(pr.get("formwork_eur_m2"), 45.0, 0, 1e4)}

    ld = raw.get("loads") or {}
    d["loads"]["floor_var_kn_m2"] = _f(ld.get("floor_var_kn_m2"), IMPOSED[dest]["q"], 0, 100)
    d["loads"]["floor_perm_extra_kn_m2"] = _f(ld.get("floor_perm_extra_kn_m2"), DEFAULT_FLOOR_PERM_EXTRA, 0, 100)
    d["loads"]["roof_var_kn_m2"] = _f(ld.get("roof_var_kn_m2"), DEFAULT_ROOF_VAR, 0, 100)
    d["loads"]["roof_perm_extra_kn_m2"] = _f(ld.get("roof_perm_extra_kn_m2"), DEFAULT_ROOF_PERM_EXTRA, 0, 100)

    sc = raw.get("sections") or {}
    d["sections"]["col_side_m"] = _f(sc.get("col_side_m"), 0.30, 0.15, 1.2)
    d["sections"]["beam_width_m"] = _f(sc.get("beam_width_m"), 0.20, 0.12, 1.0)
    d["sections"]["beam_height_m"] = _f(sc.get("beam_height_m"), 0.40, 0.20, 1.5)
    d["sections"]["slab_thickness_m"] = _f(sc.get("slab_thickness_m"), 0.20, 0.10, 0.50)

    so = raw.get("soil") or {}
    q_els = _opt_f(so.get("q_els_kpa"), 20, 5000)
    q_elu = _opt_f(so.get("q_elu_kpa"), 20, 8000)
    if q_elu is None and q_els is not None:
        # q_ELU absent : 1,5·q_ELS (rapport des facteurs partiels NF P94-261 ≈ 2,3/1,4 = 1,64 → 1,5 sécuritaire).
        q_elu = round(q_els * 1.5, 1)
    d["soil"]["q_els_kpa"] = q_els
    d["soil"]["q_elu_kpa"] = q_elu
    # Confirmation explicite (lecture G2 ou case cochée par l'utilisateur) requise pour dimensionner.
    d["soil"]["q_confirmed"] = bool(so.get("q_confirmed")) and q_els is not None
    ft = (so.get("foundation_type") or "isolee").strip().lower()
    d["soil"]["foundation_type"] = ft if ft in ("isolee", "filante", "radier") else "isolee"
    d["soil"]["anchorage_depth_m"] = _f(so.get("anchorage_depth_m"), 0.8, 0, 20)
    d["soil"]["water_table"] = bool(so.get("water_table"))
    d["soil"]["soil_class"] = (so.get("soil_class") or "").strip()[:40]
    d["soil"]["mode"] = "undrained" if (so.get("mode") == "undrained") else "drained"
    d["soil"]["phi_deg"] = _f(so.get("phi_deg"), 0.0, 0, 60)
    d["soil"]["c_kpa"] = _f(so.get("c_kpa"), 0.0, 0, 1e5)
    d["soil"]["cu_kpa"] = _f(so.get("cu_kpa"), 0.0, 0, 1e5)
    d["soil"]["gamma_soil_kn_m3"] = _f(so.get("gamma_soil_kn_m3"), 18.0, 0, 40)

    inc = raw.get("incertitudes")
    d["incertitudes"] = [str(x)[:300] for x in inc][:20] if isinstance(inc, list) else []
    return d


# ----------------------------------------------------------------- construction déterministe du modèle ----

def _cum(bays: list[float]) -> list[float]:
    coords, acc = [0.0], 0.0
    for b in bays:
        acc += b
        coords.append(round(acc, 4))
    return coords


def estimate_counts(inputs: dict) -> int:
    nx = len(inputs["grid"]["bays_x_m"])
    ny = len(inputs["grid"]["bays_y_m"])
    L = inputs["building"]["levels"]
    nodes = (nx + 1) * (ny + 1)
    if inputs.get("system", {}).get("structure") == "voiles":
        walls_x = nx * (ny + 1) * L
        walls_y = (nx + 1) * ny * L
        footings = nx * (ny + 1) + (nx + 1) * ny
        slabs = nx * ny * L
        return walls_x + walls_y + footings + slabs
    cols = nodes * L
    beams = nx * (ny + 1) * L
    if inputs.get("system", {}).get("two_way_slab"):
        beams += (nx + 1) * ny * L
    slabs = nx * ny * L
    return cols + beams + slabs + nodes


def _lvl_name(s: int, L: int) -> str:
    if s == 0:
        return "Toiture" if L > 1 else "Plancher haut"
    return "RDC" if s == L - 1 else f"R+{L - 1 - s}"


def _build_frame(cfg: dict, xs, ys, nx, ny, L, src) -> list[Element]:
    sec = cfg["sections"]
    bx, by = cfg["grid"]["bays_x_m"], cfg["grid"]["bays_y_m"]
    two_way = bool(cfg["system"].get("two_way_slab"))
    col_b = sec["col_side_m"]
    bw, bh, th = sec["beam_width_m"], sec["beam_height_m"], sec["slab_thickness_m"]
    ei = round(E_CONCRETE_KPA * bw * bh ** 3 / 12.0, 3)
    els: list[Element] = []
    # Semelles isolées (une par noeud)
    for ix in range(nx + 1):
        for iy in range(ny + 1):
            els.append(Element(id=f"F_{ix}_{iy}", kind="footing", level="Fondations",
                material="Béton C25/30", length_m=1.0, width_m=1.0, height_m=0.4,
                x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY,
                source=src, mechanics_source=src, reviewed=True))
    # Poteaux empilés
    for s in range(L):
        h = cfg["building"]["ground_height_m"] if s == L - 1 else cfg["building"]["storey_height_m"]
        for ix in range(nx + 1):
            for iy in range(ny + 1):
                below = f"C_{s + 1}_{ix}_{iy}" if s < L - 1 else f"F_{ix}_{iy}"
                els.append(Element(id=f"C_{s}_{ix}_{iy}", kind="column", level=_lvl_name(s, L),
                    material="Béton C25/30", length_m=col_b, width_m=col_b, height_m=round(h, 3),
                    x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY,
                    source=src, mechanics_source=src, reviewed=True,
                    supports=[Support(target=below, fraction=1.0, receiving="axial")]))
    # Poutres sens X (toujours) et sens Y (si plancher 2 sens)
    for s in range(L):
        for iy in range(ny + 1):
            for ix in range(nx):
                els.append(Element(id=f"B_{s}_{ix}_{iy}", kind="beam", level=_lvl_name(s, L),
                    material="Béton C25/30", length_m=bx[ix], width_m=bw, height_m=bh,
                    x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY, ei_kn_m2=ei,
                    source=src, mechanics_source=src, reviewed=True,
                    supports=[Support(target=f"C_{s}_{ix}_{iy}", receiving="axial"),
                              Support(target=f"C_{s}_{ix + 1}_{iy}", receiving="axial")]))
        if two_way:
            for ix in range(nx + 1):
                for iy in range(ny):
                    els.append(Element(id=f"BY_{s}_{ix}_{iy}", kind="beam", level=_lvl_name(s, L),
                        material="Béton C25/30", length_m=by[iy], width_m=bw, height_m=bh,
                        x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY, ei_kn_m2=ei,
                        source=src, mechanics_source=src, reviewed=True,
                        supports=[Support(target=f"C_{s}_{ix}_{iy}", receiving="axial"),
                                  Support(target=f"C_{s}_{ix}_{iy + 1}", receiving="axial")]))
    # Dalles
    for s in range(L):
        perm, var = _slab_actions(cfg, s == 0)
        for ix in range(nx):
            for iy in range(ny):
                if two_way:
                    lx, ly = bx[ix], by[iy]
                    # Lignes de rupture à 45° : le bord court reçoit un triangle, le bord long un
                    # trapèze de rampe (côté court)/2. Charger en uniforme sous-estimait le moment
                    # des poutres de rive courte de 25 % (WL/8 au lieu de WL/6).
                    if lx <= ly:
                        fx, fy = lx / (4 * ly), 0.5 - lx / (4 * ly)   # X=court (triangle), Y=long (trapèze)
                        shape_x, ramp_x = "triangle", None
                        shape_y, ramp_y = ("trapezoid", round(lx / 2, 6)) if ly > lx else ("triangle", None)
                    else:
                        fy, fx = ly / (4 * lx), 0.5 - ly / (4 * lx)
                        shape_y, ramp_y = "triangle", None
                        shape_x, ramp_x = "trapezoid", round(ly / 2, 6)
                    sup = [Support(target=f"B_{s}_{ix}_{iy}", fraction=round(fx, 6), receiving="uniform",
                                   shape=shape_x, ramp_m=ramp_x),
                           Support(target=f"B_{s}_{ix}_{iy + 1}", fraction=round(fx, 6), receiving="uniform",
                                   shape=shape_x, ramp_m=ramp_x),
                           Support(target=f"BY_{s}_{ix}_{iy}", fraction=round(fy, 6), receiving="uniform",
                                   shape=shape_y, ramp_m=ramp_y),
                           Support(target=f"BY_{s}_{ix + 1}_{iy}", fraction=round(fy, 6), receiving="uniform",
                                   shape=shape_y, ramp_m=ramp_y)]
                    # correction d'arrondi sur la dernière fraction pour sommer exactement à 1
                    sup[-1].fraction = round(1.0 - (sup[0].fraction + sup[1].fraction + sup[2].fraction), 6)
                else:
                    sup = [Support(target=f"B_{s}_{ix}_{iy}", fraction=0.5, receiving="uniform"),
                           Support(target=f"B_{s}_{ix}_{iy + 1}", fraction=0.5, receiving="uniform")]
                els.append(Element(id=f"D_{s}_{ix}_{iy}", kind="slab", level=_lvl_name(s, L),
                    material="Béton C25/30", length_m=bx[ix], width_m=by[iy], height_m=th,
                    x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY,
                    source=src, mechanics_source=src, reviewed=True,
                    loads=_slab_loads(perm, var, src), supports=sup))
    return els


def _slab_actions(cfg, roof):
    perm = cfg["loads"]["roof_perm_extra_kn_m2"] if roof else cfg["loads"]["floor_perm_extra_kn_m2"]
    var = cfg["loads"]["roof_var_kn_m2"] if roof else cfg["loads"]["floor_var_kn_m2"]
    return perm, var


def _slab_loads(perm, var, src):
    loads = []
    if perm > 0:
        loads.append(Load(action="G", value=round(perm, 3), mode="surface", source=src))
    if var > 0:
        loads.append(Load(action="Q", value=round(var, 3), mode="surface", source=src))
    return loads


def _build_walls(cfg: dict, xs, ys, nx, ny, L, src) -> list[Element]:
    bx = cfg["grid"]["bays_x_m"]
    by = cfg["grid"]["bays_y_m"]
    th = cfg["sections"]["slab_thickness_m"]
    wt = cfg["system"]["wall_thickness_m"]
    els: list[Element] = []
    # Semelles filantes sous les files de murs porteurs sens X
    for iy in range(ny + 1):
        for ix in range(nx):
            els.append(Element(id=f"SF_{ix}_{iy}", kind="footing", level="Fondations",
                material="Béton C25/30", length_m=bx[ix], width_m=0.6, height_m=0.4,
                x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY,
                source=src, mechanics_source=src, reviewed=True))
    # Semelles filantes sous les pignons/refends sens Y (périmètre fermé)
    for ix in range(nx + 1):
        for iy in range(ny):
            els.append(Element(id=f"SFY_{ix}_{iy}", kind="footing", level="Fondations",
                material="Béton C25/30", length_m=by[iy], width_m=0.6, height_m=0.4,
                x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY,
                source=src, mechanics_source=src, reviewed=True))
    # Murs porteurs empilés — sens X (portent les planchers) sur chaque ligne Y
    for s in range(L):
        h = cfg["building"]["ground_height_m"] if s == L - 1 else cfg["building"]["storey_height_m"]
        for iy in range(ny + 1):
            for ix in range(nx):
                below = f"W_{s + 1}_{ix}_{iy}" if s < L - 1 else f"SF_{ix}_{iy}"
                els.append(Element(id=f"W_{s}_{ix}_{iy}", kind="wall", level=_lvl_name(s, L),
                    material="Béton/maçonnerie", length_m=bx[ix], width_m=wt, height_m=round(h, 3),
                    x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY,
                    source=src, mechanics_source=src, reviewed=True,
                    supports=[Support(target=below, fraction=1.0, receiving="axial")]))
        # Pignons/refends sens Y (ferment le volume ; reprennent leur poids propre)
        for ix in range(nx + 1):
            for iy in range(ny):
                belowy = f"WY_{s + 1}_{ix}_{iy}" if s < L - 1 else f"SFY_{ix}_{iy}"
                els.append(Element(id=f"WY_{s}_{ix}_{iy}", kind="wall", level=_lvl_name(s, L),
                    material="Béton/maçonnerie", length_m=by[iy], width_m=wt, height_m=round(h, 3),
                    x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY,
                    source=src, mechanics_source=src, reviewed=True,
                    supports=[Support(target=belowy, fraction=1.0, receiving="axial")]))
    # Dalles 1 sens portant sur les murs sens X (transfert axial centré)
    _add_slabs(els, cfg, xs, ys, nx, ny, L, th, src, support_prefix="W", receiving="axial")
    return els


def _add_slabs(els, cfg, xs, ys, nx, ny, L, th, src, support_prefix, receiving):
    bx, by = cfg["grid"]["bays_x_m"], cfg["grid"]["bays_y_m"]
    for s in range(L):
        roof = (s == 0)
        perm = cfg["loads"]["roof_perm_extra_kn_m2"] if roof else cfg["loads"]["floor_perm_extra_kn_m2"]
        var = cfg["loads"]["roof_var_kn_m2"] if roof else cfg["loads"]["floor_var_kn_m2"]
        for ix in range(nx):
            for iy in range(ny):
                loads = []
                if perm > 0:
                    loads.append(Load(action="G", value=round(perm, 3), mode="surface", source=src))
                if var > 0:
                    loads.append(Load(action="Q", value=round(var, 3), mode="surface", source=src))
                els.append(Element(id=f"D_{s}_{ix}_{iy}", kind="slab", level=_lvl_name(s, L),
                    material="Béton C25/30", length_m=bx[ix], width_m=by[iy], height_m=th,
                    x_m=xs[ix], y_m=ys[iy], density_kn_m3=CONCRETE_DENSITY,
                    source=src, mechanics_source=src, reviewed=True, loads=loads,
                    supports=[Support(target=f"{support_prefix}_{s}_{ix}_{iy}", fraction=0.5, receiving=receiving),
                              Support(target=f"{support_prefix}_{s}_{ix}_{iy + 1}", fraction=0.5, receiving=receiving)]))


def build_model(inputs: dict) -> Model:
    """Treillis régulier déterministe — portique (poteaux/poutres) ou voiles (murs porteurs)."""
    cfg = normalize_inputs(inputs)
    if estimate_counts(cfg) > MAX_ELEMENTS:
        raise ValueError("Trame trop grande pour la Phase 1 (max 200 éléments). "
                         "Réduisez le nombre de travées ou de niveaux.")
    bx, by = cfg["grid"]["bays_x_m"], cfg["grid"]["bays_y_m"]
    xs, ys = _cum(bx), _cum(by)
    nx, ny = len(bx), len(by)
    L = cfg["building"]["levels"]
    dest = cfg["building"]["destination"]
    system = cfg["system"]["structure"]
    src = Source(document="Auto-pilote BET", note="Pré-modèle généré automatiquement — À VÉRIFIER avant calcul")
    elements = _build_walls(cfg, xs, ys, nx, ny, L, src) if system == "voiles" \
        else _build_frame(cfg, xs, ys, nx, ny, L, src)
    sys_label = "voiles / murs porteurs" if system == "voiles" else "portique poteaux-poutres"
    actions = [Action(id="G", kind="G", label="Permanentes (poids propre + G complémentaires)"),
               Action(id="Q", kind="Q", label=f"Exploitation ({dest})")]
    model = Model(title=f"Auto-pilote BET — {dest} {L} niveau(x) — {sys_label}",
                  actions=actions, self_weight_action="G", gravity_model_reviewed=True, elements=elements,
                  assumptions=[
                      f"Pré-modèle AUTOMATIQUE ({sys_label}) : trame régulière, transferts centrés"
                      + (" ; dalles 2 sens : charges triangulaires/trapézoïdales sur les poutres." if cfg["system"]["two_way_slab"]
                         else " ; planchers 1 sens."),
                      f"Charges d'exploitation {IMPOSED[dest]['q']} kN/m² (EN 1991-1-1, cat. {IMPOSED[dest]['cat']}) — à vérifier.",
                      "Aucune action horizontale (vent/séisme) ni second ordre. Portique : poutres traitées en "
                      "files continues (trois moments, Q alternées) au dimensionnement ; descente de charges "
                      "majorée de l'effet de continuité.",
                      "NON EXÉCUTOIRE — modèle à valider et compléter par l'ingénieur.",
                  ])
    combos = eurocode.generate(model.actions, categories={"Q": IMPOSED[dest]["cat"]},
                               options={"uls": True, "sls_char": True, "sls_freq": False, "sls_qp": True})
    model.combinations = combos
    return Model.model_validate(model.model_dump())


# ----------------------------------------------------------------- pré-dimensionnement semelles (G2) ----

def _case_rows(result: dict, prefix: str) -> dict:
    for case in result.get("cases", []):
        if str(case.get("id", "")).startswith(prefix):
            return {r["id"]: r for r in case.get("elements", [])}
    return {}

SOIL_MISSING_MSG = ("Contrainte de sol non confirmée : fondations NON dimensionnées. "
                    "Importez la G2 ou saisissez q_ELS/q_ELU du rapport et cochez « valeurs confirmées ».")


def size_footings(model: dict, result: dict, q_els_kpa: float | None, q_elu_kpa: float | None,
                  confirmed: bool = True) -> dict:
    """Semelle isolée (carré b×b) ou filante (largeur b) depuis la contrainte admissible G2.

    Sans contrainte de sol confirmée, aucune dimension n'est proposée (statut `sol_a_confirmer`) :
    les efforts restent fournis, la géométrie de semelle reste celle du pré-modèle."""
    els = _case_rows(result, "ELScar")
    uls = _case_rows(result, "ELU")
    soil_ok = bool(confirmed) and bool(q_els_kpa) and bool(q_elu_kpa)
    out = {}
    for e in model.get("elements", []):
        if e.get("kind") != "footing":
            continue
        fid = e["id"]
        n_els = float((els.get(fid) or {}).get("total_kn") or 0.0)
        n_elu = float((uls.get(fid) or {}).get("total_kn") or 0.0)
        if not soil_ok:
            out[fid] = {"type": "filante" if fid.startswith("SF") else "isolee", "status": "sol_a_confirmer",
                        "n_els_kn": round(n_els, 2), "n_elu_kn": round(n_elu, 2),
                        "side_m": None, "width_m": None, "dim_m": None, "message": SOIL_MISSING_MSG}
            continue
        if fid.startswith("SF"):  # semelle filante
            lf = float(e.get("length_m") or 1.0)
            q_els_line, q_elu_line = n_els / lf, n_elu / lf
            w_req = max(q_els_line / q_els_kpa if q_els_kpa > 0 else 0.0,
                        q_elu_line / q_elu_kpa if q_elu_kpa > 0 else 0.0)
            width = max(0.4, math.ceil(max(w_req, 1e-6) * 20.0) / 20.0)
            out[fid] = {"type": "filante", "status": "ok", "n_els_kn": round(n_els, 2), "n_elu_kn": round(n_elu, 2),
                        "length_m": round(lf, 2), "line_load_elu_kn_m": round(q_elu_line, 2),
                        "width_req_m": round(w_req, 3), "width_m": round(width, 2), "dim_m": round(width, 2)}
        else:  # semelle isolée
            a_req = max(n_els / q_els_kpa if q_els_kpa > 0 else 0.0,
                        n_elu / q_elu_kpa if q_elu_kpa > 0 else 0.0)
            side = max(0.6, math.ceil(math.sqrt(max(a_req, 1e-6)) * 20.0) / 20.0)
            out[fid] = {"type": "isolee", "status": "ok", "n_els_kn": round(n_els, 2), "n_elu_kn": round(n_elu, 2),
                        "area_req_m2": round(a_req, 3), "side_m": round(side, 2), "dim_m": round(side, 2)}
    return out


def apply_footing_sizes(model: dict, sizes: dict) -> dict:
    for e in model.get("elements", []):
        if e.get("kind") != "footing" or e["id"] not in sizes or sizes[e["id"]].get("status") != "ok":
            continue
        s = sizes[e["id"]]
        if s["type"] == "filante":
            e["width_m"] = s["width_m"]           # longueur = longueur de mur conservée
        else:
            e["length_m"] = s["side_m"]
            e["width_m"] = s["side_m"]
    return model


def summarize(model: dict, result: dict, sizes: dict, superstructure: dict | None = None) -> dict:
    ground = 0.0
    for case in result.get("cases", []):
        if str(case.get("id", "")).startswith("ELU"):
            ground = round(float(case.get("ground_kn") or 0.0), 1)
            break
    footings = [{"id": fid, **s} for fid, s in sizes.items()]
    footings.sort(key=lambda x: -(x.get("dim_m") or 0))
    counts = {}
    for e in model.get("elements", []):
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return {"elements_count": counts, "total_elements": len(model.get("elements", [])),
            "ground_reaction_elu_kn": ground, "footings": footings,
            "n_footings": len(footings), "max_footing_dim_m": footings[0]["dim_m"] if footings else None,
            "footing_type": footings[0]["type"] if footings else None,
            "superstructure": superstructure}


# ----------------------------------------------------------------- ferraillage superstructure (EC2) ----

BAR_AREA_CM2 = {8: 0.503, 10: 0.785, 12: 1.131, 14: 1.539, 16: 2.011, 20: 3.142, 25: 4.909, 32: 8.042}


def _choose_bars(as_req_cm2: float, as_max_cm2: float, min_bars: int = 4) -> dict:
    best = None
    for dia, area in sorted(BAR_AREA_CM2.items()):
        if dia < 12:
            continue
        n = max(min_bars, math.ceil(as_req_cm2 / area))
        if n % 2:
            n += 1
        prov = round(n * area, 2)
        cand = {"bar_mm": dia, "count": n, "as_prov_cm2": prov, "within_max": prov <= as_max_cm2 + 1e-6}
        if best is None or (cand["within_max"] and not best["within_max"]) or \
           (cand["within_max"] == best["within_max"] and prov < best["as_prov_cm2"]):
            best = cand
    return best or {"bar_mm": 20, "count": min_bars, "as_prov_cm2": round(min_bars * BAR_AREA_CM2[20], 2), "within_max": False}


def column_rebar(n_ed_kn: float, b_m: float, h_m: float, *, fck=25, fyk=500,
                 gamma_c=1.5, gamma_s=1.15) -> dict:
    """Armatures de poteau comprimé (EN 1992-1-1 §9.5) — compression centrée, flambement non vérifié."""
    ac_mm2 = b_m * h_m * 1e6
    fyd = fyk / gamma_s
    fcd = fck / gamma_c
    n_ed_n = max(n_ed_kn, 0.0) * 1000.0
    as_min = max(0.10 * n_ed_n / fyd, 0.002 * ac_mm2)      # mm²
    as_max = 0.04 * ac_mm2
    bars = _choose_bars(as_min / 100.0, as_max / 100.0, min_bars=4)
    tie = max(6, int(math.ceil(bars["bar_mm"] / 4.0 / 2.0) * 2))
    s_tie = min(20 * bars["bar_mm"], int(min(b_m, h_m) * 1000), 400)
    n_rd_kn = (ac_mm2 * fcd + bars["as_prov_cm2"] * 100.0 * fyd) / 1000.0
    status = "ok" if (bars["within_max"] and n_ed_n <= n_rd_kn * 1000.0) else "section_a_revoir"
    return {"kind": "column", "b_m": round(b_m, 3), "h_m": round(h_m, 3), "n_ed_kn": round(n_ed_kn, 1),
            "as_min_cm2": round(as_min / 100.0, 2), "as_max_cm2": round(as_max / 100.0, 2),
            "long_bars": f"{bars['count']}Ø{bars['bar_mm']}", "as_prov_cm2": bars["as_prov_cm2"],
            "ties": f"Ø{tie} e={s_tie} mm", "nrd_kn": round(n_rd_kn, 0), "status": status,
            "note": "Compression centrée (As,min=max(0,10·N/fyd ; 0,002·Ac)). Flambement/moments non vérifiés."}


def wall_rebar(n_ed_kn: float, thickness_m: float, length_m: float, *, fck=25, fyk=500) -> dict:
    """Armatures minimales de voile (EN 1992-1-1 §9.6) — verticales + horizontales."""
    ac_mm2 = thickness_m * length_m * 1e6
    as_v = 0.002 * ac_mm2                       # mm² (verticales, 2 faces)
    as_h = max(0.25 * as_v, 0.001 * ac_mm2)     # mm² (horizontales)
    per_m_v = as_v / (length_m) / 100.0 if length_m else 0.0   # cm²/m
    return {"kind": "wall", "thickness_m": round(thickness_m, 3), "length_m": round(length_m, 2),
            "n_ed_kn": round(n_ed_kn, 1), "as_vert_cm2": round(as_v / 100.0, 2),
            "as_horiz_cm2": round(as_h / 100.0, 2), "as_vert_cm2_per_m": round(per_m_v, 2),
            "note": "Aciers minimaux de voile §9.6 ; répartis deux faces. Compression centrée, flambement non vérifié."}


# ----------------------------------------------------------------- continuité des poutres ----

def _beam_line_key(beam_id: str):
    """B_s_ix_iy → file X (s, iy), rang ix ; BY_s_ix_iy → file Y (s, ix), rang iy."""
    parts = beam_id.split("_")
    if len(parts) != 4 or parts[0] not in ("B", "BY"):
        return None
    s, ix, iy = int(parts[1]), int(parts[2]), int(parts[3])
    return ((parts[0], s, iy), ix) if parts[0] == "B" else ((parts[0], s, ix), iy)


def continuity_study(model: dict, result: dict) -> dict:
    """Poutres du portique traitées en FILES CONTINUES (béton monolithique) :
    moments sur appuis (chapeaux), moments en travée et réactions par alternance de Q.

    Renvoie par poutre l'enveloppe ELU et, par combinaison, la majoration d'effort normal
    (continuité) à reporter sur chaque nœud poteau (s, ix, iy)."""
    from engines import structuro_continuous as cont
    els = {e["id"]: e for e in model.get("elements", [])}
    kinds = {a["id"]: a["kind"] for a in model.get("actions", [])}
    lines: dict[tuple, list] = {}
    for e in model.get("elements", []):
        if e.get("kind") != "beam":
            continue
        k = _beam_line_key(e["id"])
        if k:
            lines.setdefault(k[0], []).append((k[1], e["id"]))
    combos = [c for c in model.get("combinations", [])
              if str(c["id"]).startswith(("ELU", "ELScar", "ELSqp"))]
    beams: dict[str, dict] = {}
    node_delta: dict[str, dict] = {}
    out_lines = []
    for key, items in sorted(lines.items()):
        items.sort()
        ids = [bid for _, bid in items]
        spans = [{"id": bid, "L": float(els[bid]["length_m"]), "EI": els[bid].get("ei_kn_m2"),
                  "actions": cont.beam_actions(model, result, bid)} for bid in ids]
        prefix, s, fixed = key
        uls_env = None
        for c in combos:
            env = cont.envelope(spans, [c], kinds)
            for k, sup in enumerate(env["supports"]):
                node = (s, k, fixed) if prefix == "B" else (s, fixed, k)
                cd = node_delta.setdefault(c["id"], {})
                cd[node] = cd.get(node, 0.0) + sup["continuity_delta_kn"]
            if str(c["id"]).startswith("ELU"):
                if uls_env is None:
                    uls_env = env
                else:   # plusieurs ELU : enveloppe des enveloppes
                    for a, b in zip(uls_env["spans"], env["spans"]):
                        if b["m_pos_knm"] > a["m_pos_knm"]:
                            a["m_pos_knm"], a["m_pos_case"] = b["m_pos_knm"], b["m_pos_case"]
                        if b["v_max_kn"] > a["v_max_kn"]:
                            a["v_max_kn"], a["v_case"] = b["v_max_kn"], b["v_case"]
                    for a, b in zip(uls_env["supports"], env["supports"]):
                        if b["m_neg_knm"] < a["m_neg_knm"]:
                            a["m_neg_knm"], a["m_neg_case"] = b["m_neg_knm"], b["m_neg_case"]
        if uls_env is None:
            continue
        qp = next((c for c in combos if str(c["id"]).startswith("ELSqp")), None)
        qp_res = None
        if qp:   # quasi-permanente, toutes travées chargées : moments d'appui pour la flèche continue
            qp_res = cont.solve([{"L": sp["L"], "EI": sp["EI"], "loads": cont.combined_loads(sp, qp["factors"])}
                                 for sp in spans])
        for i, bid in enumerate(ids):
            sp = uls_env["spans"][i]
            beams[bid] = {"m_pos_knm": round(sp["m_pos_knm"], 3), "m_pos_case": sp["m_pos_case"],
                          "v_max_kn": round(sp["v_max_kn"], 3), "v_case": sp["v_case"],
                          "m_left_knm": round(uls_env["supports"][i]["m_neg_knm"], 3),
                          "m_right_knm": round(uls_env["supports"][i + 1]["m_neg_knm"], 3),
                          "end_left": i == 0, "end_right": i == len(ids) - 1, "n_spans": len(ids)}
            if qp_res:
                beams[bid]["qp_m_left_knm"] = qp_res["support_moments_knm"][i]
                beams[bid]["qp_m_right_knm"] = qp_res["support_moments_knm"][i + 1]
                beams[bid]["qp_m_span_knm"] = qp_res["spans"][i]["m_span_max_knm"]
        out_lines.append({"line": f"{prefix}{s}-{fixed}", "beams": ids,
                          "support_moments_knm": [round(x["m_neg_knm"], 2) for x in uls_env["supports"]]})
    return {"version": cont.VERSION, "beams": beams, "node_delta": node_delta, "lines": out_lines,
            "method": "Files de poutres continues — équation des trois moments, Q alternées ; "
                      "appuis de rive articulés + chapeaux minimaux 0,15·As (EN 1992-1-1 §9.2.1.2)."}


def apply_continuity(model: dict, result: dict, continuity: dict) -> dict:
    """Reporte la majoration d'effort normal due à la continuité sur poteaux et semelles.

    Jamais de minoration (appuis de rive conservés isostatiques). Cumul des niveaux supérieurs."""
    by_id = {e["id"]: e for e in model.get("elements", [])}
    for case in result.get("cases", []):
        nd = (continuity.get("node_delta") or {}).get(case["id"])
        if not nd:
            continue
        for row in case.get("elements", []):
            parts = row["id"].split("_")
            if row.get("kind") == "column" and len(parts) == 4 and parts[0] == "C":
                t, ix, iy = int(parts[1]), int(parts[2]), int(parts[3])
                delta = sum(v for (s, a, b), v in nd.items() if a == ix and b == iy and s <= t)
            elif row.get("kind") == "footing" and len(parts) == 3 and parts[0] == "F":
                ix, iy = int(parts[1]), int(parts[2])
                delta = sum(v for (s, a, b), v in nd.items() if a == ix and b == iy)
            else:
                continue
            if delta <= 1e-9:
                continue
            el = by_id.get(row["id"]) or {}
            row["total_kn"] += delta
            row["received_kn"] = row.get("received_kn", 0.0) + delta
            row["continuity_delta_kn"] = round(delta, 3)
            area = (el.get("length_m") or 0) * (el.get("width_m") or 0)
            if area and "axial_stress_mpa" in row:
                row["axial_stress_mpa"] = row["total_kn"] / area / 1000
            if area and "mean_pressure_kpa" in row:
                row["mean_pressure_kpa"] = row["total_kn"] / area
        case["continuity_note"] = ("Efforts normaux poteaux/semelles majorés de l'effet de continuité des poutres "
                                   "(réaction continue enveloppe − réaction isostatique).")
    return result


def _top_steel_design(m_sup_knm: float, as_bottom_cm2: float, b: float, h: float, d: float,
                      fck: float, fyk: float) -> dict:
    """Aciers supérieurs sur appui : max(calcul sous M négatif ; 0,15·As travée §9.2.1.2 ; As,min)."""
    from engines import structuro_ec2 as ec2
    as_calc = 0.0
    if m_sup_knm > 1e-6:
        as_calc = ec2.design_section(m_sup_knm, 0.0, b_m=b, h_m=h, d_m=d, fck=fck, fyk=fyk)["flexure"]["as_req_cm2"]
    fctm = 0.30 * fck ** (2.0 / 3.0)
    as_min = max(0.26 * fctm / fyk, 0.0013) * b * d * 1e4
    as_constr = 0.15 * as_bottom_cm2
    req = max(as_calc, as_constr, as_min if m_sup_knm > 1e-6 else 0.0)
    return {"m_sup_knm": round(max(m_sup_knm, 0.0), 3), "as_calc_cm2": round(as_calc, 2),
            "as_constructive_cm2": round(as_constr, 2), "as_top_req_cm2": round(req, 2),
            "rule": "As,sup = max(M⁻/(z·fyd) ; 0,15·As,travée [EN 1992-1-1 §9.2.1.2(1)] ; As,min)"}


def _continuous_beams(model: dict, result: dict, continuity: dict, fck: float, fyk: float) -> dict:
    """Ferraillage EC2 des poutres depuis l'enveloppe CONTINUE (travée + appuis) + flèche fissurée."""
    from engines import structuro_ec2 as ec2
    from engines.structuro_sls import cracked_long_term
    by_id = {e["id"]: e for e in model.get("elements", [])}
    qp = next((c for c in result.get("cases", []) if str(c.get("id", "")).startswith("ELSqp")), None)
    qp_rows = {r["id"]: r for r in (qp or {}).get("elements", [])}
    out = {}
    for bid, env in (continuity.get("beams") or {}).items():
        el = by_id.get(bid) or {}
        b, h = el.get("width_m"), el.get("height_m")
        if not b or not h:
            continue
        cover = 0.05
        d = round(h - cover, 4)
        des = ec2.design_section(max(env["m_pos_knm"], 0.0), env["v_max_kn"], b_m=b, h_m=h, d_m=d,
                                 d_prime_m=cover, fck=fck, fyk=fyk)
        as_bot = des["flexure"]["as_req_cm2"]
        top_l = _top_steel_design(-env["m_left_knm"], as_bot, b, h, d, fck, fyk)
        top_r = _top_steel_design(-env["m_right_knm"], as_bot, b, h, d, fck, fyk)
        top = top_l if top_l["as_top_req_cm2"] >= top_r["as_top_req_cm2"] else top_r
        bars = _choose_bars(as_bot, des["flexure"]["as_max_cm2"], min_bars=2)
        defl = None
        row = qp_rows.get(bid) or {}
        L = el.get("length_m")
        if row.get("deflection_sampled_mm") is not None and el.get("ei_kn_m2") and L:
            w_el = row["deflection_sampled_mm"]
            m_qp = row.get("moment_max_knm") or 0
            basis = "Flèche isostatique fissurée + fluage."
            if "qp_m_left_knm" in env:
                # Travée continue : les moments d'appui (quasi-permanents) relèvent la mi-travée de
                # (|Mg|+|Md|)·L²/(16·EI) ; moment de travée continu pour ζ.
                relief = (abs(env["qp_m_left_knm"]) + abs(env["qp_m_right_knm"])) * L ** 2 / (16 * el["ei_kn_m2"]) * 1000
                w_el = max(w_el - relief, 0.0)
                m_qp = env["qp_m_span_knm"]
                basis = ("Travée continue : flèche élastique isostatique diminuée de l'effet des moments "
                         "d'appui quasi-permanents, puis fissuration + fluage (§7.4.3).")
            cr = cracked_long_term(w_el, el["ei_kn_m2"], b_m=b, h_m=h, d_m=d,
                                   as_mm2=bars["as_prov_cm2"] * 100, m_qp_knm=m_qp, fck=fck)
            lim = L * 1000 / 250
            cr.update({"limit_mm": round(lim, 2), "ratio_label": "L/250 (quasi-permanente, §7.4.1(4))",
                       "limit_partitions_mm": round(L * 1000 / 500, 2),
                       "utilisation": round(cr["w_long_term_mm"] / lim, 3),
                       "status": "ok" if cr["w_long_term_mm"] <= lim else "a_revoir",
                       "basis": basis})
            defl = cr
        out[bid] = {"design": des, "as_bottom_req_cm2": as_bot, "top": top,
                    "top_left": top_l, "top_right": top_r, "bars_bottom": bars, "deflection": defl, "env": env}
    return out


def superstructure_rebar(model: dict, result: dict, opts: dict | None = None,
                         continuity: dict | None = None) -> dict:
    """Ferraillage EC2 des poutres (enveloppe M/V) et poteaux/voiles (effort normal ELU).

    Avec `continuity` (portique), les poutres sont dimensionnées sur l'enveloppe des FILES
    CONTINUES : aciers inférieurs (travée), supérieurs (chapeaux sur appuis) et flèche fissurée."""
    from engines import structuro_ec2 as ec2
    from engines import structuro_eurocode as eurocode
    opts = opts or {}
    fck = float(opts.get("fck", 25)); fyk = float(opts.get("fyk", 500))
    by_id = {e["id"]: e for e in model.get("elements", [])}
    beams_by_level: dict[str, dict] = {}
    if continuity and continuity.get("beams"):
        for bid, r in _continuous_beams(model, result, continuity, fck, fyk).items():
            el = by_id.get(bid) or {}
            lvl = el.get("level", "?")
            family = "Y" if bid.startswith("BY_") else "X"
            key = f"{lvl}|{family}"     # gouvernant par niveau ET par sens (files X et Y distinctes)
            prev = beams_by_level.get(key)
            gov = max(r["as_bottom_req_cm2"], r["top"]["as_top_req_cm2"])
            if prev is None or gov > max(prev["as_req_cm2"], prev["as_top_req_cm2"]):
                beams_by_level[key] = {
                    "level": lvl, "id": bid, "family": family, "b_m": round(el.get("width_m"), 3), "h_m": round(el.get("height_m"), 3),
                    "med_knm": r["env"]["m_pos_knm"], "med_case": r["env"]["m_pos_case"],
                    "m_support_knm": r["top"]["m_sup_knm"],
                    "ved_kn": r["env"]["v_max_kn"], "as_req_cm2": r["as_bottom_req_cm2"],
                    "as_top_req_cm2": r["top"]["as_top_req_cm2"], "top_steel": r["top"],
                    "asw_s_req_cm2_m": r["design"]["shear"]["asw_s_req_cm2_m"],
                    "bottom_bars": f"{r['bars_bottom']['count']}Ø{r['bars_bottom']['bar_mm']}",
                    "deflection": r["deflection"], "analysis": "continue",
                    "scheme": None}
        return _finish_superstructure(model, result, beams_by_level, by_id, fck, fyk, continuity)
    # Poutres : réutilise le dimensionnement EN 1992 par poutre, gouvernant par niveau
    beam_out = ec2.design_study(model, result, {"fck": fck, "fyk": fyk, "cover_m": 0.05,
                                                "bar_mm": int(opts.get("bar_mm", 16)), "stirrup_mm": 8, "legs": 2})
    for row in beam_out.get("elements", []):
        if row.get("status") != "ok":
            continue
        el = by_id.get(row["id"]) or {}
        lvl = el.get("level", "?")
        asr = (row.get("design") or {}).get("flexure", {}).get("as_req_cm2", 0)
        prev = beams_by_level.get(lvl)
        if prev is None or asr > prev["as_req_cm2"]:
            beams_by_level[lvl] = {"level": lvl, "id": row["id"], "b_m": row.get("b_m"), "h_m": row.get("h_m"),
                "med_knm": row.get("med_knm"), "ved_kn": row.get("ved_kn"), "as_req_cm2": asr,
                "asw_s_req_cm2_m": (row.get("design") or {}).get("shear", {}).get("asw_s_req_cm2_m"),
                "scheme": row.get("scheme")}
    return _finish_superstructure(model, result, beams_by_level, by_id, fck, fyk, None)


def _finish_superstructure(model, result, beams_by_level, by_id, fck, fyk, continuity) -> dict:
    from engines import structuro_eurocode as eurocode
    # Poteaux / voiles : effort normal ELU gouvernant par niveau
    env = eurocode.design_envelope(result)
    cols_by_level: dict[str, dict] = {}
    walls_by_level: dict[str, dict] = {}
    for e in env.get("elements", []):
        if e.get("kind") not in ("column", "wall"):
            continue
        n = (e.get("uls") or {}).get("axial_kn")
        if not n:
            continue
        el = by_id.get(e["id"]) or {}
        lvl = el.get("level", "?")
        if e["kind"] == "column":
            r = column_rebar(n["value"], el.get("width_m", 0.3), el.get("length_m", 0.3), fck=fck, fyk=fyk)
            r.update({"level": lvl, "id": e["id"]})
            prev = cols_by_level.get(lvl)
            if prev is None or r["n_ed_kn"] > prev["n_ed_kn"]:
                cols_by_level[lvl] = r
        else:
            r = wall_rebar(n["value"], el.get("width_m", 0.2), el.get("length_m", 1.0), fck=fck, fyk=fyk)
            r.update({"level": lvl, "id": e["id"]})
            prev = walls_by_level.get(lvl)
            if prev is None or r["n_ed_kn"] > prev["n_ed_kn"]:
                walls_by_level[lvl] = r
    note = ("Ferraillage gouvernant par niveau (élément le plus sollicité). Efforts seulement ; "
            "dispositions constructives, ancrages, flèche et flambement à valider par l'ingénieur.")
    if continuity:
        note = ("Poutres en FILES CONTINUES (trois moments, Q alternées) : aciers inférieurs en travée, "
                "chapeaux sur appuis, flèche fissurée long terme (§7.4.3). Poteaux majorés de l'effet de "
                "continuité. " + note)
    return {"version": VERSION, "beams": list(beams_by_level.values()),
            "columns": list(cols_by_level.values()), "walls": list(walls_by_level.values()),
            "continuity": {"method": continuity.get("method"), "lines": continuity.get("lines")} if continuity else None,
            "note": note}


# ----------------------------------------------------------------- repères & métré (aciers/béton/coût) ----

_MARK_PREFIX = {"beam": "PTR", "column": "POT", "wall": "VOI", "slab": "DAL", "footing": "SEM"}


def _mark(kind: str, level: str) -> str:
    code = {"Toiture": "TOIT", "Fondations": "FOND", "RDC": "RDC", "Plancher haut": "PH"}.get(level, level.replace("+", "").replace(" ", ""))
    return f"{_MARK_PREFIX.get(kind, 'EL')}-{code}"


def element_marks(model: dict) -> dict:
    """Repère d'armature par élément (groupé par niveau + type, pratique courante de plan de coffrage)."""
    return {e["id"]: _mark(e.get("kind"), e.get("level", "?")) for e in model.get("elements", [])}


def _kg_per_m(dia_mm: float) -> float:
    return 0.006165 * dia_mm * dia_mm           # acier Ø en mm → kg/m


def _count_by(model, kind, level):
    return sum(1 for e in model.get("elements", []) if e.get("kind") == kind and e.get("level") == level)


def _bars_count(label: str) -> tuple[int, int]:
    import re as _re
    m = _re.match(r"(\d+)\D+(\d+)", label or "")
    return (int(m.group(1)), int(m.group(2))) if m else (4, 12)


def metre(model: dict, result: dict, superstructure: dict, prices: dict) -> dict:
    """Métré déterministe : volume béton (exact) + nomenclature/tonnage acier (barres gouvernantes par niveau) + coût."""
    by_id = {e["id"]: e for e in model.get("elements", [])}
    # --- béton (exact par type) ---
    vol = {}
    for e in model.get("elements", []):
        v = (e.get("length_m") or 0) * (e.get("width_m") or 0) * (e.get("height_m") or 0)
        vol[e["kind"]] = round(vol.get(e["kind"], 0.0) + v, 4)
    total_concrete = round(sum(vol.values()), 3)
    # --- acier : nomenclature par repère (barres gouvernantes × nombre d'éléments identiques) ---
    schedule, steel_kg = [], 0.0
    for b in superstructure.get("beams", []):
        el = by_id.get(b["id"]) or {}
        span = el.get("length_m") or 4.0
        bh = el.get("height_m") or 0.4
        bwi = el.get("width_m") or 0.2
        dia, _ = _bars_count("0Ø0")
        bars = _choose_bars(b.get("as_req_cm2", 0) or 0.5, (b.get("as_req_cm2", 1) or 1) * 6, min_bars=2)
        dia = bars["bar_mm"]; n_bot = bars["count"]
        # Chapeaux sur appuis (poutres continues) : nombre de barres du même Ø couvrant As,sup.
        as_top = float(b.get("as_top_req_cm2") or 0.0)
        n_top = max(2, math.ceil(as_top / BAR_AREA_CM2[dia])) if as_top else 2
        n_el = _count_by(model, "beam", b["level"])
        if b.get("family"):
            pref = "BY_" if b["family"] == "Y" else "B_"
            n_el = sum(1 for e in model.get("elements", []) if e.get("kind") == "beam"
                       and e.get("level") == b["level"] and e["id"].startswith(pref))
        lap = 40 * dia / 1000.0
        long_len = (n_bot + n_top) * (span + 2 * lap)
        nstir = int(span / 0.20) + 1
        stir_len = max(2 * ((bwi - 0.05) + (bh - 0.05)), 0.4)
        w = (long_len * _kg_per_m(dia) + nstir * stir_len * _kg_per_m(8)) * n_el
        steel_kg += w
        schedule.append({"mark": _mark("beam", b["level"]) + (f"-{b['family']}" if b.get("family") else ""),
                         "type": "Poutre", "level": b["level"],
                         "section": f"{bwi}×{bh} m", "bars": f"{n_bot}+{n_top}Ø{dia} + cadres Ø8",
                         "count": n_el, "unit_length_m": round(span + 2 * lap, 2), "weight_kg": round(w, 1)})
    for c in superstructure.get("columns", []):
        el = by_id.get(c["id"]) or {}
        h = el.get("height_m") or 3.0
        n_bar, dia = _bars_count(c.get("long_bars", "4Ø12"))
        n_el = _count_by(model, "column", c["level"])
        lap = 0.6
        long_len = n_bar * (h + lap)
        nstir = int(h / 0.20) + 1
        stir_len = max(2 * ((el.get("width_m", 0.3) - 0.05) + (el.get("length_m", 0.3) - 0.05)), 0.4)
        w = (long_len * _kg_per_m(dia) + nstir * stir_len * _kg_per_m(8)) * n_el
        steel_kg += w
        schedule.append({"mark": _mark("column", c["level"]), "type": "Poteau", "level": c["level"],
                         "section": f"{el.get('width_m')}×{el.get('length_m')} m", "bars": f"{c.get('long_bars')} + {c.get('ties')}",
                         "count": n_el, "unit_length_m": round(h + lap, 2), "weight_kg": round(w, 1)})
    for wl in superstructure.get("walls", []):
        el = by_id.get(wl["id"]) or {}
        h = el.get("height_m") or 3.0
        n_el = _count_by(model, "wall", wl["level"])
        as_tot_cm2 = (wl.get("as_vert_cm2", 0) + wl.get("as_horiz_cm2", 0))
        w = as_tot_cm2 * 1e-4 * h * 2.0 * 7850.0 * n_el / 1.0      # 2 faces, acier 7850 kg/m³
        steel_kg += w
        schedule.append({"mark": _mark("wall", wl["level"]), "type": "Voile", "level": wl["level"],
                         "section": f"{el.get('width_m')}×{el.get('length_m')} m",
                         "bars": f"vert. {wl.get('as_vert_cm2')} cm² + horiz. {wl.get('as_horiz_cm2')} cm²",
                         "count": n_el, "unit_length_m": round(h, 2), "weight_kg": round(w, 1)})
    # Fondations : ratio forfaitaire (indicatif)
    foot_ratio = 45.0
    foot_steel = round(vol.get("footing", 0.0) * foot_ratio, 1)
    steel_kg += foot_steel
    schedule.append({"mark": "SEM-FOND", "type": "Semelles", "level": "Fondations", "section": "—",
                     "bars": f"forfait {int(foot_ratio)} kg/m³", "count": _count_by_kind(model, "footing"),
                     "unit_length_m": None, "weight_kg": foot_steel})
    steel_kg = round(steel_kg, 0)
    pc = float(prices.get("concrete_eur_m3", 150)); ps = float(prices.get("steel_eur_kg", 2))
    cost_c = round(total_concrete * pc, 0); cost_s = round(steel_kg * ps, 0)
    return {"concrete": {"by_type_m3": vol, "total_m3": total_concrete},
            "steel": {"schedule": schedule, "total_kg": steel_kg,
                      "ratio_kg_m3": round(steel_kg / total_concrete, 1) if total_concrete else 0},
            "cost": {"concrete_eur": cost_c, "steel_eur": cost_s, "total_eur": round(cost_c + cost_s, 0),
                     "concrete_eur_m3": pc, "steel_eur_kg": ps},
            "note": "Métré INDICATIF : béton exact, acier estimé d'après le ferraillage gouvernant par niveau "
                    "(+ forfait semelles). Hors coffrage, chutes, aciers de peau et recouvrements détaillés."}


def _count_by_kind(model, kind):
    return sum(1 for e in model.get("elements", []) if e.get("kind") == kind)



_SYSTEM = (
    "Tu es un assistant de bureau d'études structure (BTP, France). Tu LIS des plans cotés, "
    "des pièces de permis de construire et des rapports géotechniques G2, et tu en extrais "
    "UNIQUEMENT ce qui est écrit/lisible. N'INVENTE JAMAIS une cote, une charge ou une valeur de sol : "
    "mets-la dans 'incertitudes' si absente. Réponds STRICTEMENT en JSON valide, sans texte autour."
)

_GEOM_PROMPT = (
    "Tu analyses des PLANS COTÉS et des pièces de PERMIS DE CONSTRUIRE (plans de masse, "
    "coupes, façades, plans de niveau). Renvoie CE JSON exact :\n"
    '{"building":{"destination":"habitation|bureau|commerce|parking|industriel|erp","levels":<nombre de niveaux porteurs entier>,'
    '"storey_height_m":<hauteur d\'étage courant>,"ground_height_m":<hauteur RDC>},'
    '"system":{"structure":"portique|voiles","wall_thickness_m":<épaisseur mur porteur en m si lisible sinon null>},'
    '"grid":{"bays_x_m":[<portées successives entre files de poteaux/murs selon X, en m>],"bays_y_m":[<idem selon Y, en m>]},'
    '"loads":{"floor_var_kn_m2":<charge exploitation plancher si lisible sinon null>,"roof_var_kn_m2":<null si inconnu>},'
    '"sections":{"col_side_m":<section poteau si cotée sinon null>,"beam_width_m":<null>,"beam_height_m":<null>,"slab_thickness_m":<épaisseur dalle/plancher si cotée sinon null>},'
    '"incertitudes":[""]}\n'
    "RÈGLES :\n"
    "- Déduis le nombre de niveaux du type (R+1 = 2 niveaux porteurs, R+2 = 3, etc.), des coupes/façades ou des altitudes (±0.00, +3.10, +5.90…). Compte aussi un sous-sol s'il est porteur.\n"
    "- SYSTÈME : maison/immeuble en MAÇONNERIE de blocs ou VOILES béton armé porteurs → structure='voiles' ; ossature POTEAUX-POUTRES (BA ou acier) → structure='portique'. Une maison individuelle courante est presque toujours en 'voiles' (murs porteurs).\n"
    "- Lis les HAUTEURS sur la COUPE : storey_height_m = différence d'altitude entre deux planchers courants successifs.\n"
    "- Utilise l'ÉCHELLE indiquée (ex 1/50, 1/100) ET les cotes écrites pour mesurer les portées. Chaque portée = distance d'axe à axe entre deux files consécutives.\n"
    "- Si la trame est régulière de N files espacées de d, renvoie [d, d, …] (N-1 valeurs).\n"
    "- Si la trame intérieure des murs/files porteurs n'est PAS cotée (fréquent en permis de construire), déduis l'EMPRISE hors-tout Lx x Ly depuis le plan de masse/toiture et renvoie bays_x_m=[Lx], bays_y_m=[Ly], puis signale-le dans 'incertitudes'.\n"
    "- Ne renvoie QUE des nombres en MÈTRES. Mets null (jamais 0 inventé) quand une valeur n'est pas lisible, "
    "et explique le doute dans 'incertitudes'. N'invente aucune cote."
)

_SOIL_PROMPT = (
    "Tu analyses un RAPPORT GÉOTECHNIQUE (mission G2 AVP/PRO, NF P94-500) — PLUSIEURS PAGES te sont fournies. Renvoie CE JSON exact :\n"
    '{"soil":{"q_els_kpa":<contrainte admissible ELS en kPa ou null>,"q_elu_kpa":<ELU en kPa ou null>,'
    '"foundation_type":"isolee|filante|radier","anchorage_depth_m":<profondeur d\'ancrage/encastrement D en m>,'
    '"water_table":<true/false nappe/eau rencontrée>,"soil_class":"<nature/classe du sol d\'assise lue>",'
    '"phi_deg":<angle de frottement phi\' ou null>,"c_kpa":<cohésion c\' ou null>,"cu_kpa":<cohésion non drainée cu ou null>,'
    '"gamma_soil_kn_m3":<poids volumique du sol ou null>},"incertitudes":[""]}\n'
    "RÈGLES :\n"
    "- Cherche la 'contrainte admissible', 'qadm', 'contrainte de calcul ELS/ELU', 'qELS/qELU', ou une formule du type 'Vd ≤ q × A'' (alors q EST la contrainte admissible). "
    "Convertis TOUT en kPa : 1 MPa = 1000 kPa, 1 bar = 100 kPa, 1 t/m2 = 10 kPa, 1 daN/cm2 = 100 kPa. Ex : 0,300 MPa → 300 kPa ; 0,492 MPa → 492 kPa.\n"
    "- Prends la contrainte de la STRATE D'ASSISE des fondations superficielles (pas celle des butons/parois provisoires).\n"
    "- Déduis 'foundation_type' de la recommandation (semelles isolées / filantes / radier / pieux->radier). Pour une maison en murs porteurs, retiens 'filante' si des semelles filantes sont citées.\n"
    "- Mets null (jamais une valeur inventée) quand ce n'est pas écrit sur les pages fournies ; liste les doutes dans 'incertitudes'. "
    "Ne tranche pas entre deux valeurs contradictoires : signale-les."
)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _chat():
    from emergentintegrations.llm.chat import LlmChat
    import uuid
    model = os.environ.get("BET_GEMINI_MODEL") or os.environ.get("GEMINI_FALLBACK_MODEL") or "gemini-3.5-flash"
    return (LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"],
                    session_id=f"autopilot-{uuid.uuid4().hex}", system_message=_SYSTEM)
            .with_model("gemini", model).with_params(max_tokens=3000))


async def _ask(prompt: str, images: list[bytes]) -> dict | None:
    if not images or not os.environ.get("EMERGENT_LLM_KEY"):
        return None
    from emergentintegrations.llm.chat import UserMessage, ImageContent
    contents = [ImageContent(image_base64=base64.b64encode(im).decode("ascii")) for im in images[:9]]
    resp = await _chat().send_message(UserMessage(text=prompt, file_contents=contents))
    return _extract_json(resp if isinstance(resp, str) else str(resp))


_SOIL_SCALARS = ("q_els_kpa", "q_elu_kpa", "anchorage_depth_m", "phi_deg", "c_kpa", "cu_kpa", "gamma_soil_kn_m3")
_SOIL_BATCH = 9
_SOIL_CONCURRENCY = 4


async def _extract_soil_batched(images: list[bytes]) -> tuple[dict | None, list[str]]:
    """Scanne un rapport G2 page par page par LOTS (la synthèse qELS/qELU est souvent loin
    dans le document) et fusionne : premier non-null gagne, incertitudes agrégées."""
    if not images or not os.environ.get("EMERGENT_LLM_KEY"):
        return None, []
    batches = [images[i:i + _SOIL_BATCH] for i in range(0, len(images), _SOIL_BATCH)]
    sem = asyncio.Semaphore(_SOIL_CONCURRENCY)

    async def _one(chunk: list[bytes]) -> dict | None:
        async with sem:
            try:
                return await _ask(_SOIL_PROMPT, chunk)
            except Exception:  # noqa: BLE001
                return None

    parts = await asyncio.gather(*[_one(c) for c in batches])
    merged: dict = {}
    inc: list[str] = []
    water, soil_class, found = False, "", False
    for p in parts:
        if not p:
            continue
        found = True
        s = p.get("soil") or {}
        for k in _SOIL_SCALARS:
            if merged.get(k) is not None:
                continue
            v = s.get(k)
            if v in (None, ""):
                continue
            if k in ("q_els_kpa", "q_elu_kpa") and (not isinstance(v, (int, float)) or v <= 0):
                continue
            merged[k] = v
        if not merged.get("foundation_type") and s.get("foundation_type"):
            merged["foundation_type"] = s.get("foundation_type")
        if s.get("water_table"):
            water = True
        if not soil_class and s.get("soil_class"):
            soil_class = str(s.get("soil_class"))
        inc += [str(x) for x in (p.get("incertitudes") or [])]
    if not found:
        return None, []
    merged["water_table"] = water
    if soil_class:
        merged["soil_class"] = soil_class
    # Chaque lot ne voit que ses ~9 pages : il se plaint que « les autres pages sont absentes ».
    # Ces reproches de couverture sont FAUX au niveau du document complet → on les écarte.
    got_core = merged.get("q_els_kpa") is not None or bool(merged.get("foundation_type"))
    _cover = ("absent", "non fourni", "non fournies", "fournies", "extrait",
              "ne contiennent pas", "non figur", "non mentionn", "pages ")
    seen, inc_clean = set(), []
    for x in inc:
        xl = x.lower()
        if got_core and any(c in xl for c in _cover):
            continue
        if x and x not in seen:
            seen.add(x)
            inc_clean.append(x)
    return {"soil": merged}, inc_clean[:6]


async def extract_inputs(geom_images: list[bytes], soil_images: list[bytes]) -> dict:
    """Fusionne lecture géométrie (plan/PC) + sol (G2) en inputs normalisés. Jamais d'invention."""
    merged = {"building": {}, "system": {}, "grid": {}, "loads": {}, "sections": {}, "soil": {}, "incertitudes": []}
    read_flags = {"geometry": False, "soil": False}
    try:
        g = await _ask(_GEOM_PROMPT, geom_images)
        if g:
            read_flags["geometry"] = True
            for k in ("building", "system", "grid", "loads", "sections"):
                if isinstance(g.get(k), dict):
                    merged[k] = g[k]
            merged["incertitudes"] += [str(x) for x in (g.get("incertitudes") or [])]
    except Exception as e:  # noqa: BLE001
        merged["incertitudes"].append(f"Lecture plan/PC indisponible : {str(e)[:120]}")
    try:
        s, s_inc = await _extract_soil_batched(soil_images)
        if s:
            read_flags["soil"] = True
            if isinstance(s.get("soil"), dict):
                merged["soil"] = s["soil"]
                if merged["soil"].get("q_els_kpa") is not None:
                    merged["soil"]["q_confirmed"] = True   # lu dans la G2 (à relire par l'utilisateur)
            merged["incertitudes"] += s_inc
    except Exception as e:  # noqa: BLE001
        merged["incertitudes"].append(f"Lecture G2 indisponible : {str(e)[:120]}")

    inputs = normalize_inputs(merged)
    if not read_flags["geometry"]:
        inputs["incertitudes"].insert(0, "Aucun plan/PC lisible : trame par défaut (à saisir).")
    if not read_flags["soil"]:
        inputs["incertitudes"].insert(0, "Aucune G2 lisible : contrainte de sol à saisir — fondations non dimensionnées sans elle.")
    inputs["read_flags"] = read_flags
    return inputs


def build_and_compute(inputs: dict) -> dict:
    """Pipeline déterministe complet : modèle → descente → semelles G2 → ferraillage → recalcul."""
    cfg = normalize_inputs(inputs)
    soil = cfg["soil"]
    q_args = (soil["q_els_kpa"], soil["q_elu_kpa"])
    frame = cfg["system"]["structure"] == "portique"
    model = build_model(cfg)
    result = calculate(model)
    mdict = model.model_dump()
    if frame and result.get("status") != "blocked":
        apply_continuity(mdict, result, continuity_study(mdict, result))
    sizes = size_footings(mdict, result, *q_args, confirmed=soil["q_confirmed"])
    mdict = apply_footing_sizes(mdict, sizes)
    model2 = Model.model_validate(mdict)
    result2 = calculate(model2)
    m2 = model2.model_dump()
    continuity = None
    if frame and result2.get("status") != "blocked":
        continuity = continuity_study(m2, result2)
        apply_continuity(m2, result2, continuity)
    sizes = size_footings(m2, result2, *q_args, confirmed=soil["q_confirmed"])
    rebar = superstructure_rebar(m2, result2, {"fck": 25, "fyk": 500}, continuity=continuity)
    quant = metre(m2, result2, rebar, cfg["prices"])
    summary = summarize(m2, result2, sizes, rebar)
    summary["metre"] = quant
    warnings = []
    if not soil["q_confirmed"]:
        warnings.append(SOIL_MISSING_MSG)
    for bm in rebar.get("beams", []):
        dfl = bm.get("deflection") or {}
        if dfl.get("status") == "a_revoir":
            warnings.append(f"Poutre {bm['id']} ({bm['level']}) : flèche long terme {dfl['w_long_term_mm']} mm "
                            f"> L/250 = {dfl['limit_mm']} mm — augmenter la hauteur.")
    summary["warnings"] = warnings
    summary["soil_confirmed"] = soil["q_confirmed"]
    return {"model": m2, "result": result2, "footing_sizes": sizes,
            "superstructure": rebar, "metre": quant, "marks": element_marks(m2),
            "summary": summary, "soil": cfg["soil"], "system": cfg["system"], "version": VERSION}
