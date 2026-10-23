"""Désignations des ouvrages (matériaux) — valeurs par défaut quand le client ne précise rien.

Défauts France (demande du fondateur, 19/10/2026) quand un PC est joint sans autre précision :
  - dallage du sous-sol (s'il existe) : béton armé C25/30 20 cm ;
  - semelles : béton armé C25/30, classe d'exposition XC2 ;
  - murs porteurs du sous-sol : blocs à bancher 20 cm remplis de béton armé ;
  - murs à partir du RDC : brique terre cuite Isobric 20 cm (joint mince) ;
  - planchers : poutrelles-hourdis ;
  - charpente : traditionnelle.
Toute précision du client (user_hypotheses) l'emporte. Les propriétés mécaniques de la brique (f_k, f_b) restent les
valeurs prudentes communes aux briques de 20 cm à perforations verticales, à confirmer par la DoP du fabricant.
"""
from __future__ import annotations

BRICKS = {
    "brique_isobric_20": {"short": "Isobric 20", "name": "Brique terre cuite Isobric 20 (joint mince)"},
    "brique_porotherme_20": {"short": "Porotherme 20", "name": "Brique terre cuite Porotherme 20 (R20 / Th+), joint mince"},
    "brique_20": {"short": "brique 20", "name": "Brique terre cuite 20 cm à perforations verticales, joint mince"},
}
BASEMENT_WALLS = {
    "bloc_a_bancher_20": {"short": "blocs à bancher 20", "core": 0.15, "buried": "Murs en blocs à bancher 20 enterrés",
                          "name": "Murs en blocs à bancher 20 cm remplis de béton C25/30 armé hydrofugé"},
    "voile_ba_20": {"short": "voile BA 20", "core": 0.20, "buried": "Voiles BA 20 enterrés",
                    "name": "Voiles périphériques BA 20 C25/30 hydrofugé"},
}
DEFAULTS = {
    "FR": {"masonry": "brique_isobric_20", "basement_wall": "bloc_a_bancher_20", "floor_system": "poutrelles_hourdis",
           "roof_structure": "charpente_traditionnelle", "foundation_exposure": "XC2", "basement_slab_cm": 20},
    "PT": {"masonry": "brique_20", "basement_wall": "voile_ba_20", "floor_system": "poutrelles_hourdis",
           "roof_structure": "charpente_traditionnelle", "foundation_exposure": "XC2", "basement_slab_cm": 20},
}


def apply_defaults(raw: dict) -> dict:
    """Complète user_hypotheses avec les défauts du pays, sans écraser ce que le client a précisé."""
    country = ((raw.get("project") or {}).get("country") or "FR").upper()
    uh = raw.setdefault("user_hypotheses", {})
    for k, v in DEFAULTS.get(country, DEFAULTS["FR"]).items():
        uh.setdefault(k, v)
    if uh.get("masonry") not in BRICKS:
        uh["masonry"] = DEFAULTS.get(country, DEFAULTS["FR"])["masonry"]
    if uh.get("basement_wall") not in BASEMENT_WALLS:
        uh["basement_wall"] = DEFAULTS.get(country, DEFAULTS["FR"])["basement_wall"]
    return raw


def of(m) -> dict:
    uh = m.raw.get("user_hypotheses") or {}
    brick = BRICKS.get(uh.get("masonry"), BRICKS["brique_isobric_20"])
    bw = BASEMENT_WALLS.get(uh.get("basement_wall"), BASEMENT_WALLS["bloc_a_bancher_20"])
    exp = uh.get("foundation_exposure") or "XC2"
    return {"masonry": uh.get("masonry", "brique_isobric_20"), "brick": brick["short"], "brick_name": brick["name"],
            "basement_wall": uh.get("basement_wall", "bloc_a_bancher_20"), "bw": bw["short"], "bw_name": bw["name"],
            "bw_buried": bw["buried"],
            "bw_core": bw["core"], "bw_blocks": uh.get("basement_wall", "bloc_a_bancher_20") == "bloc_a_bancher_20",
            "exposure": exp, "slab_cm": int(uh.get("basement_slab_cm") or 20)}


# ---------------------------------------------------------------- géotechnique incomplète
# Une G2 ne donne pas toujours tout (ou l'IA ne recopie pas tout) : sans ces champs les calculs plantaient (CALC-00,
# ex. « geotech.retaining.layers[0].base_m ») et l'Assistant relançait en boucle. On complète avec des valeurs prudentes,
# chacune tracée comme hypothèse « à confirmer par la G2 » dans le dossier — jamais en silence.
GEO_TXT = {
    "FR": {"bearing": "couche porteuse à confirmer par l'étude G2", "layer": "Sol (hypothèse prudente)"},
    "PT": {"bearing": "camada resistente a confirmar pelo estudo geotécnico", "layer": "Solo (hipótese prudente)"},
}


def _num(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def complete_geotech(raw: dict) -> list[str]:
    """Complète raw["geotech"] (s'il existe) et retourne la liste lisible des valeurs ajoutées par défaut."""
    geo = raw.get("geotech")
    if not isinstance(geo, dict) or not geo:
        return []
    country = ((raw.get("project") or {}).get("country") or "FR").upper()
    txt = GEO_TXT.get(country, GEO_TXT["FR"])
    added: list[tuple[str, object, str]] = []

    def put(d, key, value, label):
        if _num(d.get(key)) is None if isinstance(value, (int, float)) else not d.get(key):
            d[key] = value
            added.append((key, value, label))

    tops = [_num(lv.get("floor_top")) for lv in raw.get("levels") or [] if isinstance(lv, dict)]
    tops = [t for t in tops if t is not None]
    depth = -min(tops) if tops and min(tops) < -1.0 else 0.0          # même règle que structure.has_basement

    put(geo, "bearing_layer", txt["bearing"], "couche d'assise")
    put(geo, "foundation_base_depth_m", round(max(0.8, depth + 0.5) if depth else 0.8, 2), "profondeur d'assise (m/TN)")
    put(geo, "anchorage_m", 0.2, "ancrage dans la couche porteuse (m)")
    vw = geo.get("verified_widths_m")
    if not isinstance(vw, dict):
        vw = geo["verified_widths_m"] = {}
    put(vw, "filante", 0.5, "largeur mini des semelles filantes (m)")
    put(vw, "isolee", 0.8, "largeur mini des semelles isolées (m)")

    if depth:
        ret = geo.get("retaining")
        if not isinstance(ret, dict):
            ret = geo["retaining"] = {}
        put(ret, "neighbour_surcharge_kpa", 15.0, "surcharge des fondations voisines (kPa)")
        layers = [L for L in ret.get("layers") or [] if isinstance(L, dict)]
        if not layers:
            layers = [{"name": txt["layer"]}]
            added.append(("retaining.layers", txt["layer"], "couches de sol pour la poussée des terres"))
        prev = 0.0
        for i, L in enumerate(layers):
            L.setdefault("name", f"{txt['layer']} {i + 1}")
            if _num(L.get("base_m")) is None:
                L["base_m"] = round(depth + 2.0, 2) if i == len(layers) - 1 else round(prev + 1.0, 2)
                added.append((f"retaining.layers[{i}].base_m", L["base_m"], f"base de la couche « {L['name']} » (m)"))
            L["base_m"] = _num(L["base_m"])
            prev = L["base_m"]
            if _num(L.get("gamma")) is None:
                L["gamma"] = 20.0
                added.append((f"retaining.layers[{i}].gamma", 20.0, f"poids volumique « {L['name']} » (kN/m³)"))
            if _num(L.get("k0")) is None:
                phi = _num(L.get("phi"))
                import math
                L["k0"] = round(1 - math.sin(math.radians(phi)), 3) if phi else 0.5
                added.append((f"retaining.layers[{i}].k0", L["k0"], f"coefficient de poussée au repos K0 « {L['name']} »"
                                                          + (" (1 − sin φ)" if phi else "")))
            L["gamma"], L["k0"] = _num(L["gamma"]), _num(L["k0"])
        ret["layers"] = layers

    if added:
        hyps = raw.setdefault("hypotheses", [])
        if isinstance(hyps, list):
            for key, value, label in added:
                hyps.append({"field": f"geotech.{key}", "value": value, "source": "hypothese",
                             "_comment": f"{label} — valeur prudente par défaut, à confirmer par la G2"})
    return [f"{label} = {value}" for _, value, label in added]


# ---------------------------------------------------------------- identification du projet incomplète
# Les cartouches des plans et la note citent ces champs : une valeur nulle faisait planter le rendu
# (« TypeError: 'NoneType' object is not subscriptable » sur project['g2_ref']).
PROJECT_TXT = {
    "FR": {"name": "Projet", "address": "Adresse non précisée", "pc_ref": "non précisé", "architect": "non précisé",
           "g2_ref": "étude de sol non fournie — hypothèses prudentes"},
    "PT": {"name": "Projeto", "address": "Morada não indicada", "pc_ref": "não indicado", "architect": "não indicado",
           "g2_ref": "estudo geotécnico não fornecido — hipóteses prudentes"},
}


def complete_project(raw: dict) -> list[str]:
    """Remplit les champs texte du projet manquants ou nuls ; la région de neige FR est déduite du code postal si absente."""
    pr = raw.get("project")
    if not isinstance(pr, dict):
        pr = raw["project"] = {}
    country = (pr.get("country") or "FR").upper()
    txt = PROJECT_TXT.get(country, PROJECT_TXT["FR"])
    added = []
    for k, v in txt.items():
        if not isinstance(pr.get(k), str) or not pr.get(k).strip():
            if pr.get(k) not in (None, "") and not isinstance(pr.get(k), str):
                pr[k] = str(pr[k])
                continue
            pr[k] = v
            if k == "g2_ref":
                added.append(f"référence de l'étude de sol = {v}")
    if country != "PT" and not pr.get("snow_region"):
        import re
        cp = re.search(r"\b(\d{5})\b", " ".join(str(pr.get(k) or "") for k in ("address", "postal_code", "code_postal", "city")))
        region = None
        if cp:
            try:
                from engines.calc_lots.climat_dept import NEIGE_DEPT
                d = cp.group(1)[:2]
                region = NEIGE_DEPT.get("2A" if d == "20" else d)
            except Exception:  # noqa: BLE001
                region = None
        pr["snow_region"] = region or "A1"
        added.append(f"région de neige = {pr['snow_region']}" + (" (d'après le code postal)" if region else " (par défaut)"))
    return added
