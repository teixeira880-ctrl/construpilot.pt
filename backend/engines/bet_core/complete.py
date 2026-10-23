"""Complétion déterministe du relevé AVANT la validation de schéma.

Une lecture IA (surtout de repli : OpenAI / Gemini sans sortie structurée) laisse souvent des champs numériques vides
(« null »), écrits en texte (« 2,50 m », « 20 cm ») ou invente un niveau de comble sans cote. Plutôt que de bloquer
l'étude (« Relevé non conforme au schéma »), on applique les règles qu'un projeteur BET appliquerait, chacune
TRACÉE dans _decisions et dans les hypothèses du dossier — jamais en silence :
  - nombres écrits en texte → nombres (virgule décimale, unités cm / mm) ;
  - épaisseur de plancher absente → 0,20 (poutrelles 16+4) ; dallage du sous-sol → 0,20 ;
  - hauteur sous plafond absente → différence des cotes de niveau moins le plancher, sinon 2,50 ;
  - niveau de comble sans cote ni pièce → retiré des niveaux (le comble est porté par la toiture) ;
  - épaisseur des murs absente → brique 0,20 + doublage provisoire, recalculée ensuite par l'étude thermique ;
  - égout / faîtage absents → déduits des niveaux et d'une pente de 40° ;
  - baies sans position → retirées (et signalées), allège / hauteur absentes → valeurs courantes selon le type ;
  - pays « PT » sur un dossier français (adresse, code postal à 5 chiffres, « rue ») → FR.
"""
from __future__ import annotations

import math
import re

_NUM_RX = re.compile(r"^\s*([-+]?\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\s*$", re.I)


def num(v, field: str = ""):
    """'2,50' → 2.5 ; '20 cm' → 0.20 ; '200 mm' → 0.20 ; nombre → nombre ; sinon None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else None
    if not isinstance(v, str):
        return None
    mt = _NUM_RX.match(v.replace("\u00a0", " "))
    if not mt:
        return None
    x = float(mt.group(1).replace(",", "."))
    unit = (mt.group(2) or "").lower()
    if unit == "cm":
        x /= 100
    elif unit == "mm":
        x /= 1000
    return x


def _thick(v):
    """Épaisseur écrite en cm sans unité (« 20 ») → 0,20 m."""
    if v is None:
        return None
    return v / 100 if v > 1.5 else v


def complete(raw: dict) -> list[str]:
    dec: list[str] = []
    if not isinstance(raw, dict):
        return dec
    hyps = raw.setdefault("hypotheses", []) if isinstance(raw.get("hypotheses", []), list) else []

    def note(msg, field=None, value=None):
        dec.append(msg)
        if field is not None:
            hyps.append({"field": field, "value": value, "source": "hypothese"})

    pr = raw.setdefault("project", {}) if isinstance(raw.get("project"), dict) else {}
    # ---- pays : un PC traduit en portugais reste un projet français
    addr = " ".join(str(pr.get(k, "")) for k in ("address", "name", "pc_ref"))
    if str(pr.get("country", "")).upper() == "PT":
        pt = re.search(r"\b\d{4}-\d{3}\b|c[âa]mara municipal|freguesia|concelho", addr, re.I)
        fr = re.search(r"\b\d{5}\b|\brue\b|\bavenue\b|\ball[ée]e\b|\bfrance\b|\(\d{2}\)|\bPCMI\b", addr, re.I)
        if fr and not pt:
            pr["country"] = "FR"
            note("Pays : dossier rédigé en portugais mais terrain en France (adresse française) → règles françaises (Eurocodes AN FR, RE2020, NF C 15-100).")
    # ---- enveloppe
    env = raw.get("envelope") if isinstance(raw.get("envelope"), dict) else None
    if env is not None:
        for k in ("length_x", "width_y", "wall_total_thickness", "wall_structural_thickness", "lining_thickness"):
            if k in env and not isinstance(env[k], (int, float)):
                v = num(env[k])
                env[k] = _thick(v) if (v is not None and "thickness" in k) else v
        if env.get("wall_structural_thickness") in (None, 0):
            env["wall_structural_thickness"] = 0.20
            note("Épaisseur structurelle des murs non lue : 0,20 m (brique / blocs de 20).", "envelope.wall_structural_thickness", 0.20)
        if env.get("wall_total_thickness") in (None, 0) or env["wall_total_thickness"] < env["wall_structural_thickness"]:
            env["wall_total_thickness"] = round(env["wall_structural_thickness"] + 0.15, 2)
            env["lining_thickness"] = 0.15
            note("Épaisseur totale des murs non lue : provisoirement 0,35 m, recalculée par l'étude thermique RE2020.", "envelope.wall_total_thickness", 0.35)
        rooms = [r for lst in (raw.get("rooms") or {}).values() if isinstance(lst, list) for r in lst if isinstance(r, dict)]
        for k, c1 in (("length_x", "x1"), ("width_y", "y1")):
            if env.get(k) in (None, 0) and rooms:
                ext = max((num(r.get(c1)) or 0) for r in rooms) + env["wall_total_thickness"]
                if ext > 3:
                    env[k] = round(ext, 2)
                    note(f"Dimension hors tout {k} non lue : {ext:.2f} m déduite des pièces.".replace(".", ","), f"envelope.{k}", round(ext, 2))
    # ---- niveaux
    levels = raw.get("levels") if isinstance(raw.get("levels"), list) else None
    roof = raw.get("roof") if isinstance(raw.get("roof"), dict) else {}
    if roof:
        for k in ("eaves_level", "ridge_level", "ceiling_level", "ridge_x", "ridge_y"):
            if k in roof and roof[k] is not None and not isinstance(roof[k], (int, float)):
                roof[k] = num(roof[k])
    txt = " ".join(str((raw.get("user_hypotheses") or {}).get(k, "")) for k in ("_text", "_source")).lower()
    if levels:
        for lv in levels:
            for k in ("floor_top", "slab_thickness", "ceiling_height"):
                if k in lv and lv[k] is not None and not isinstance(lv[k], (int, float)):
                    v = num(lv[k])
                    lv[k] = _thick(v) if (k == "slab_thickness" and v is not None) else v
        rooms_by = raw.get("rooms") or {}
        attic_rx = re.compile(r"combl|s[oó]t[aã]o|grenier|attic|sotao", re.I)
        keep = []
        for lv in levels:
            no_rooms = not (rooms_by.get(lv.get("id")) or [])
            eav = roof.get("eaves_level")
            is_attic = bool(attic_rx.search(f"{lv.get('id', '')} {lv.get('name', '')} {lv.get('use', '')}"))
            if no_rooms and (lv.get("floor_top") is None or (eav is not None and lv["floor_top"] >= eav - 0.30) or (is_attic and not lv.get("use"))) \
                    and len(levels) > 2 and lv is levels[-1]:
                note(f"Niveau « {lv.get('name') or lv.get('id')} » sans cote ni pièce : comble, retiré des niveaux (porté par la toiture).")
                if re.search(r"am[ée]nag", txt) or re.search(r"am[ée]nag", str(lv.get("name", "")) + str(lv.get("use", ""))):
                    roof["attic_floor"] = True
                continue
            keep.append(lv)
        levels[:] = keep
        known = [lv for lv in levels if isinstance(lv.get("floor_top"), (int, float))]
        if known:
            levels.sort(key=lambda lv: lv["floor_top"] if isinstance(lv.get("floor_top"), (int, float)) else 1e9)
        for i, lv in enumerate(levels):
            if not isinstance(lv.get("floor_top"), (int, float)):
                prev = levels[i - 1] if i else None
                if prev and isinstance(prev.get("floor_top"), (int, float)):
                    lv["floor_top"] = round(prev["floor_top"] + (prev.get("ceiling_height") or 2.50) + 0.20, 2)
                else:
                    lv["floor_top"] = 0.0
                note(f"Cote du niveau {lv.get('id')} non lue : {lv['floor_top']:+.2f}.".replace(".", ","), f"levels.{lv.get('id')}.floor_top", lv["floor_top"])
        uh = raw.get("user_hypotheses") or {}
        for i, lv in enumerate(levels):
            if not lv.get("use"):
                lv["use"] = "annexe" if lv["floor_top"] < -1.0 else "habitation"
            if not isinstance(lv.get("slab_thickness"), (int, float)) or lv["slab_thickness"] <= 0:
                lv["slab_thickness"] = round((uh.get("basement_slab_cm") or 20) / 100, 2) if i == 0 else 0.20
                note(f"Épaisseur du plancher sous {lv.get('id')} non cotée : {lv['slab_thickness']:.2f} m "
                     f"({'dallage' if i == 0 else 'poutrelles-hourdis 16+4'}).".replace(".", ",", 1), f"levels.{lv.get('id')}.slab_thickness", lv["slab_thickness"])
        for i, lv in enumerate(levels):
            if not isinstance(lv.get("ceiling_height"), (int, float)) or lv["ceiling_height"] <= 0:
                nxt = levels[i + 1] if i + 1 < len(levels) else None
                if nxt:
                    h = nxt["floor_top"] - lv["floor_top"] - nxt["slab_thickness"]
                elif isinstance(roof.get("eaves_level"), (int, float)):
                    h = roof["eaves_level"] - lv["floor_top"] - 0.20
                else:
                    h = 2.50
                h = round(h if 2.0 <= h <= 3.6 else 2.50, 2)
                lv["ceiling_height"] = h
                note(f"Hauteur sous plafond {lv.get('id')} non cotée : {h:.2f} m (différence des cotes de niveau).".replace(".", ",", 1),
                     f"levels.{lv.get('id')}.ceiling_height", h)
        # ---- toiture
        if roof is not None and levels:
            top = levels[-1]
            if not isinstance(roof.get("eaves_level"), (int, float)):
                roof["eaves_level"] = round(top["floor_top"] + top["ceiling_height"] + 0.20, 2)
                note(f"Cote d'égout non lue : {roof['eaves_level']:.2f} (dessus du dernier plancher).".replace(".", ","), "roof.eaves_level", roof["eaves_level"])
            if not isinstance(roof.get("ridge_level"), (int, float)) and env:
                run = (env.get("length_x") or 10) / 2 if str(roof.get("ridge_axis", "y")) != "x" else (env.get("width_y") or 8) / 2
                roof["ridge_level"] = round(roof["eaves_level"] + run * math.tan(math.radians(40)), 2)
                note(f"Cote de faîtage non lue : {roof['ridge_level']:.2f} (pente 40°).".replace(".", ","), "roof.ridge_level", roof["ridge_level"])
            if not isinstance(roof.get("ceiling_level"), (int, float)):
                roof["ceiling_level"] = round(top["floor_top"] + top["ceiling_height"], 2)
            roof.setdefault("type", "deux_pans")
            if roof.get("dormers") is None:
                roof["dormers"] = []
    # ---- baies
    ops = raw.get("openings") if isinstance(raw.get("openings"), list) else None
    if ops is not None:
        keep = []
        for o in ops:
            if not isinstance(o, dict):
                continue
            for k in ("from", "to", "sill", "height"):
                if k in o and o[k] is not None and not isinstance(o[k], (int, float)):
                    o[k] = num(o[k])
            if not isinstance(o.get("from"), (int, float)) or not isinstance(o.get("to"), (int, float)) or o["to"] <= o["from"]:
                note(f"Baie {o.get('id', '?')} sans position lisible : non reprise (à vérifier sur les façades).")
                continue
            kind = str(o.get("kind") or "fenêtre").lower()
            o["kind"] = o.get("kind") or "fenêtre"
            door = "porte" in kind or "baie" in kind or "coulissant" in kind
            if not isinstance(o.get("sill"), (int, float)):
                o["sill"] = 0.0 if door else 0.90
            if not isinstance(o.get("height"), (int, float)) or o["height"] <= 0:
                o["height"] = 2.15 if door else 1.25
                note(f"Baie {o.get('id')} : hauteur non cotée, {o['height']:.2f} m retenue.".replace(".", ","))
            keep.append(o)
        ops[:] = keep
    # ---- sol
    geo = raw.get("geotech") if isinstance(raw.get("geotech"), dict) else None
    if geo is not None:
        for k, dflt in (("q_els_kpa", 150.0), ("q_elu_kpa", 225.0)):
            v = num(geo.get(k)) if geo.get(k) is not None else None
            if v is None:
                geo[k] = dflt
                note(f"Contrainte {k[2:5].upper()} absente de l'étude de sol : {dflt:.0f} kPa (valeur prudente à confirmer par la G2).", f"geotech.{k}", dflt)
            else:
                geo[k] = v * 1000 if v < 5 else v              # 0,25 MPa écrit sans unité → 250 kPa
    if dec:
        raw.setdefault("_decisions", [])
        raw["_decisions"] += [d for d in dec if d not in raw["_decisions"]]
    return dec
