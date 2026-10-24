"""Construit l'entrée du moteur MEP à partir d'un plan déjà lu par ConstruPilot
(collection `plans_takeoff` : pièces en pixels par page, échelle `calibrations`,
structure IA `structure[page]` avec les ouvertures)."""
from __future__ import annotations

OPENING_KIND = {"porte": "porte", "fenetre": "fenetre", "baie": "baie", "porte_fenetre": "porte_fenetre",
                "door": "porte", "window": "fenetre"}


class AdapterError(ValueError):
    pass


def from_takeoff(plan: dict, levels: list[dict] | None = None, country: str = "fr",
                 options: dict | None = None) -> dict:
    """`levels` : [{"page_index": 0, "name": "RDC", "elevation_m": 0, "height_m": 2.5,
    "origin": [dx, dy]}] ; par défaut une page = un niveau, empilés de 2,8 m."""
    pages = sorted({int(r.get("page_index", 0)) for r in plan.get("rooms") or []})
    if not pages:
        raise AdapterError("Nenhuma divisão relevada nesta planta: faça primeiro a leitura / medição da planta." if country == "pt" else
                           "Aucune pièce relevée sur ce plan : lancez d'abord la lecture / le métré du plan.")
    if not levels:
        levels = [{"page_index": p, "name": (f"Piso {i}" if i else "Rés-do-chão") if country == "pt" else (f"Niveau {i}" if i else "RDC"),
                   "elevation_m": 2.8 * i} for i, p in enumerate(pages)]
    out_levels = []
    missing_scale = []
    for i, lv in enumerate(levels):
        page = int(lv.get("page_index", 0))
        cal = (plan.get("calibrations") or {}).get(str(page)) or {}
        ppm = cal.get("pixels_per_meter")
        if not ppm or ppm <= 0:
            missing_scale.append(page + 1)
            continue
        rooms = []
        for r in plan.get("rooms") or []:
            if int(r.get("page_index", 0)) != page or len(r.get("points") or []) < 3:
                continue
            rooms.append({"id": r.get("room_id") or f"p{page}-r{len(rooms) + 1}", "name": r.get("name") or ("Divisão" if country == "pt" else "Pièce"),
                          "polygon": [[float(x) / ppm, float(y) / ppm] for x, y in r["points"]]})
        structure = (plan.get("structure") or {}).get(str(page)) or {}
        openings = []
        for o in structure.get("openings") or []:
            try:
                a = [float(o["x1"]) / ppm, float(o["y1"]) / ppm]
                b = [float(o["x2"]) / ppm, float(o["y2"]) / ppm]
            except (KeyError, TypeError, ValueError):
                continue
            openings.append({"kind": OPENING_KIND.get(o.get("kind"), "porte"), "a": a, "b": b})
        fixtures = []
        for f in (plan.get("mep_fixtures") or {}).get(str(page)) or []:
            fixtures.append({"kind": f["kind"], "x": float(f["x"]) / ppm, "y": float(f["y"]) / ppm, "source": "plan"})
        out_levels.append({"id": lv.get("id") or f"N{i}", "name": lv.get("name") or f"Niveau {i}",
                           "elevation_m": float(lv.get("elevation_m", 2.8 * i)),
                           "height_m": float(lv.get("height_m", 2.5)),
                           "origin": lv.get("origin") or [0, 0],
                           "rooms": rooms, "openings": openings, "fixtures": fixtures})
    if missing_scale:
        pages = ", ".join(map(str, missing_scale))
        raise AdapterError(f"Escala em falta na(s) página(s) {pages}: calibre a planta antes de gerar os planos de execução." if country == "pt" else
                           f"Échelle manquante sur la/les page(s) {pages} : calibrez le plan avant de générer les plans d'exécution.")
    return {"country": country, "project": {"name": plan.get("filename") or ("Projeto" if country == "pt" else "Projet"), "plan_id": plan.get("plan_id")},
            "levels": out_levels, "options": options or {}}


# Façades du modèle « boîte » structure (structuro_maison) → axes de l'emprise rectangulaire.
_FACADE_EDGE = {
    # frente : y=0 (le long de L, axe X) ; tras : y=W ; esquerda : x=0 (axe Y) ; direita : x=L
    "frente": ("x", 0.0), "tras": ("x", 1.0), "esquerda": ("y", 0.0), "direita": ("y", 1.0),
}


def from_structuro_geometry(geo: dict, country: str = "fr", options: dict | None = None) -> dict:
    """Construit l'entrée du moteur MEP à partir de la géométrie structurelle lue par
    read_building_geometry (modèle « boîte » : emprise L×W en mètres, niveaux, baies par façade).
    Chaque niveau devient une pièce rectangulaire = l'emprise, avec les ouvertures reportées
    sur les arêtes correspondantes. Déterministe, sans IA."""
    L = float(geo.get("outer_L_m") or 0) or 8.0
    W = float(geo.get("outer_W_m") or 0) or 7.0
    levels_in = [lv for lv in (geo.get("levels") or []) if isinstance(lv, dict)] or [{"name": "RDC", "storey_height_m": 2.5}]
    openings = geo.get("openings") or []
    out_levels = []
    elev = 0.0
    for i, lv in enumerate(levels_in[:6]):
        name = lv.get("name") or (f"R+{i}" if i else "RDC")
        h = float(lv.get("storey_height_m") or 2.5)
        poly = [[0.0, 0.0], [L, 0.0], [L, W], [0.0, W]]
        ops = []
        for op in openings:
            if (op.get("level") or levels_in[0].get("name")) != name:
                continue
            edge = _FACADE_EDGE.get(op.get("facade"))
            if not edge:
                continue
            axis, frac = edge
            x0 = float(op.get("x0_m") or 0.0)
            wd = float(op.get("width_m") or 0.9)
            if axis == "x":
                y = frac * W
                a, b = [x0, y], [min(x0 + wd, L), y]
            else:
                x = frac * L
                a, b = [x, x0], [x, min(x0 + wd, W)]
            sill = float(op.get("sill_m") or 0.0)
            kind = "porte_fenetre" if sill <= 0.05 and wd >= 1.6 else ("porte" if sill <= 0.05 else "fenetre")
            ops.append({"kind": kind, "a": a, "b": b})
        out_levels.append({"id": f"N{i}", "name": name, "elevation_m": round(elev, 2),
                           "height_m": h, "origin": [0, 0],
                           "rooms": [{"id": f"N{i}-r1", "name": f"{name} — emprise", "polygon": poly}],
                           "openings": ops, "fixtures": []})
        elev += h
    return {"country": country,
            "project": {"name": geo.get("name") or "Maison", "plan_id": geo.get("plan_id")},
            "levels": out_levels, "options": options or {}}
