"""Recompute persisted quantities from their source geometry, without I/O."""
from engines import geometry as G


def recompute_room(room: dict, ppm: float) -> dict:
    """Recalcule surface / périmètre / murs / volume d'une pièce avec un nouveau ppm.

    Iter68 : les déductions (trémie, escalier…) sont soustraites de la surface,
    du plafond et du volume — le périmètre et les murs restent inchangés.
    """
    pts = room.get("points") or []
    if len(pts) < 3 or not ppm or ppm <= 0:
        return room
    height = float(room.get("ceiling_height_m") or 2.5)
    m = G.room_measurements(pts, ppm, height)
    net = G.subtract_openings(m["wall_area_gross_m2"], room.get("openings") or [])
    for deduction in room.get("deductions") or []:
        if len(deduction.get("points") or []) >= 3:
            deduction["area_m2"] = round(G.polygon_area_m2(deduction["points"], ppm), 3)
    room["openings"] = net["openings"]
    ded = round(sum(float(d.get("area_m2") or 0)
                    for d in (room.get("deductions") or [])), 3)
    surface = max(0.0, round(m["surface_m2"] - ded, 3))
    room.update({
        "surface_m2": surface,
        "surface_gross_m2": m["surface_m2"],
        "deductions_area_m2": ded,
        "perimeter_m": m["perimeter_m"],
        "ceiling_area_m2": surface,
        "wall_area_gross_m2": m["wall_area_gross_m2"],
        "wall_area_net_m2": net["wall_area_net_m2"],
        "openings_area_m2": net["openings_area_m2"],
        "volume_m3": round(surface * height, 3),
    })
    written = room.get("surface_written_m2")
    if written and surface > 0:
        room["surface_delta_pct"] = round((float(written) / surface - 1) * 100, 1)
    return room


def _measure_gross_m(m: dict) -> float:
    """Longueur brute d'une cote linéaire (avant déduction des ouvertures)."""
    if m.get("gross_m") is not None:
        return float(m["gross_m"])
    return float(m.get("value_m") or m.get("length_m") or 0)


def recompute_linear_sets(m: dict) -> dict:
    """Recalcule le net (ml) et, si une hauteur de mur est saisie, les surfaces (m²)
    mur brut / ouvertures / mur net — de façon déterministe.

    - net (ml)              = brut − Σ(largeur × nombre)
    - mur brut (m²)         = brut × hauteur mur
    - ouvertures (m²)       = Σ(largeur × hauteur × nombre) — seules les ouvertures
                              dont la hauteur est renseignée sont déduites en surface
    - mur net (m²)          = mur brut − ouvertures
    Renvoie le dict des champs à persister (clés sans préfixe positionnel)."""
    gross = round(_measure_gross_m(m), 3)
    openings = m.get("openings") or []
    deducted = sum(float(o["width_m"]) * int(o.get("count", 1)) for o in openings)
    net = round(max(0.0, gross - deducted), 3)
    wh = float(m.get("wall_height_m") or 0)
    sets = {"gross_m": gross, "openings": openings,
            "value_m": net, "length_m": net, "wall_height_m": (wh or None)}
    if wh > 0:
        gross_area = round(gross * wh, 3)
        op_area = round(sum(float(o["width_m"]) * int(o.get("count", 1))
                            * float(o.get("height_m") or 0) for o in openings), 3)
        net_area = round(max(0.0, gross_area - op_area), 3)
        sets.update({"wall_area_gross_m2": gross_area,
                     "openings_area_m2": op_area, "wall_area_net_m2": net_area})
    else:
        sets.update({"wall_area_gross_m2": None,
                     "openings_area_m2": None, "wall_area_net_m2": None})
    return sets


def recalibrate_measurement(measurement: dict, ppm: float) -> dict:
    """Pixel geometry follows the scale; manually entered metres stay unchanged."""
    m = measurement
    kind = m.get("kind")
    points = m.get("points") or []
    if kind in ("distance", "polyline", "cumulative"):
        segments = m.get("segments") if kind == "cumulative" else [points]
        segments = [s for s in (segments or []) if len(s) >= 2]
        if segments:
            m["gross_m"] = round(sum(G.polyline_length_m(s, ppm) for s in segments), 3)
            for opening in m.get("openings") or []:
                drawn = opening.get("points") or []
                if len(drawn) == 2:
                    opening["width_m"] = round(G.distance_m(drawn[0], drawn[1], ppm), 3)
            m.update(recompute_linear_sets(m))
    elif kind in ("polygon", "cumulative_area"):
        polygons = m.get("polygons") if kind == "cumulative_area" else [points]
        polygons = [p for p in (polygons or []) if len(p) >= 3]
        if polygons:
            m["area_m2"] = round(sum(G.polygon_area_m2(p, ppm) for p in polygons), 3)
            m["perimeter_m"] = round(sum(G.polygon_perimeter_m(p, ppm) for p in polygons), 3)
    return m
