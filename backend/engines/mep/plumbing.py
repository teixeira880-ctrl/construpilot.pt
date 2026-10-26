"""Plomberie : alimentation EF/ECS en pieuvre depuis une nourrice par niveau, colonne
montante, évacuations (branchements → chute → collecteur → sortie), dimensionnement."""
from __future__ import annotations

from engines import dtu_plomberie as D

from . import geometry as G
from .model import level_of, room_at
from .placement import Wall
from .rules import pipe_for, pipe_for_flow, simultaneity, velocity

SUPPLY_DROP = 1.0      # remontée / descente moyenne entre nourrice (sol) et robinetterie


def network(equipment, levels, options, rules) -> dict:
    pr = rules["plumbing"]
    fx_rules = pr["fixtures"]
    sanit = [f for f in equipment if f["kind"] in fx_rules]
    heater = next((f for f in equipment if f["kind"] == "chauffe_eau"), None)
    ground = levels[0]
    out = {"manifolds": [], "supplies": [], "risers": [], "drains": [], "stacks": [],
           "collector": None, "exit": None, "main": None, "heater": heater}
    if not sanit:
        return out

    # ---------------- nourrices -------------------------------------------------------------
    by_level: dict[str, list] = {}
    for f in sanit:
        by_level.setdefault(f["level_id"], []).append(f)
    manifolds = {}
    ground_anchor = heater or _nearest_wall_point(ground, sanit)
    for lv in levels:
        fx = by_level.get(lv.id)
        if not fx:
            continue
        if lv.id == ground.id or lv is ground:
            p = (ground_anchor["x"], ground_anchor["y"])
            room = room_at(levels, lv.id, p)
            mp = _beside(room, p, 0.7) if room else p
        else:
            # nourrice d'étage dans la pièce d'eau la plus chargée
            counts: dict[str, int] = {}
            for f in fx:
                counts[f["room_id"]] = counts.get(f["room_id"], 0) + 1
            rid = max(counts, key=counts.get)
            room = next(r for r in lv.rooms if r.id == rid)
            target = (ground_anchor["x"], ground_anchor["y"])
            w = Wall(room, inset=0.15)
            mp = w.point(w.snap(w.s_of(target)) or 0.0)
        manifolds[lv.id] = {"id": f"N-{lv.id}", "level_id": lv.id, "x": round(mp[0], 3),
                            "y": round(mp[1], 3), "room_id": room.id if room else None,
                            "outlets_ef": 0, "outlets_ecs": 0}

    # ---------------- alimentations en pieuvre ------------------------------------------------
    sid = 0
    for f in sanit:
        fr = fx_rules[f["kind"]]
        m = manifolds[f["level_id"]]
        for net in ("EF", "ECS") if fr["hot"] else ("EF",):
            # Ø intérieur ≥ minimum du référentiel ET vitesse ≤ vmax au débit de base
            ext, inner = max(pipe_for(fr["d_supply"], pr["pipes"], pr["pipe_tolerance_mm"]),
                             pipe_for_flow(fr["q"], pr["max_velocity"], pr["pipes"]))
            off = 0.06 if net == "ECS" else -0.06
            a = (m["x"] + off, m["y"] + off)
            b = (f["x"] + off, f["y"] + off)
            path = G.manhattan_path(a, b, horizontal_first=abs(a[0] - b[0]) >= abs(a[1] - b[1]))
            L = (G.path_length(path) + SUPPLY_DROP) * (1 + options.get("pipe_slack", 0.10))
            sid += 1
            out["supplies"].append({
                "id": f"A{sid}", "net": net, "level_id": f["level_id"], "fixture_id": f["id"],
                "fixture": f["kind"], "from": m["id"], "path": [list(map(lambda v: round(v, 3), q)) for q in path],
                "length_m": round(L, 1), "pipe_ext_mm": ext, "pipe_int_mm": inner,
                "q_ls": fr["q"], "velocity_ms": round(velocity(fr["q"], inner), 2)})
            m["outlets_ef" if net == "EF" else "outlets_ecs"] += 1

    # ---------------- colonnes montantes (nourrice RDC → nourrices d'étage) ---------------------
    gm = manifolds.get(ground.id)
    for lv in levels[1:]:
        m = manifolds.get(lv.id)
        if not m or not gm:
            continue
        upper = by_level[lv.id]
        for net in ("EF", "ECS"):
            fx = [f for f in upper if net == "EF" or fx_rules[f["kind"]]["hot"]]
            if not fx:
                continue
            (ext, inner), dim = _group_pipe([f["kind"] for f in fx], net, pr, options, 13, colonne=True)
            q = dim["q_probable_ls"]
            horiz = G.manhattan((gm["x"], gm["y"]), (m["x"], m["y"]))
            L = (horiz + (lv.elevation - ground.elevation) + 0.5) * (1 + options.get("pipe_slack", 0.10))
            out["risers"].append({"id": f"CM-{net}-{lv.id}", "net": net, "from": gm["id"], "to": m["id"],
                                  "x": m["x"], "y": m["y"], "length_m": round(L, 1),
                                  "pipe_ext_mm": ext, "pipe_int_mm": inner, "q_probable_ls": round(q, 3),
                                  "velocity_ms": round(velocity(q, inner), 2), **dim})
            gm["outlets_ef" if net == "EF" else "outlets_ecs"] += 1

    # ---------------- alimentation générale (arrivée → nourrice RDC) ---------------------------
    (ext, inner), dim_main = _group_pipe([f["kind"] for f in sanit], "EF", pr, options, 16)
    q_all = dim_main["q_probable_ls"]
    entry = _exterior_point(ground, (gm["x"], gm["y"])) if gm else None
    out["main"] = {"from": "Compteur / regard de branchement", "to": gm["id"] if gm else None,
                   "entry": [round(entry[0], 3), round(entry[1], 3)] if entry else None,
                   "length_in_building_m": round(G.manhattan(entry, (gm["x"], gm["y"])) + 0.5, 1) if entry and gm else None,
                   "pipe_ext_mm": ext, "pipe_int_mm": inner, "q_probable_ls": round(q_all, 3),
                   "velocity_ms": round(velocity(q_all, inner), 2), "fixtures_count": len(sanit), **dim_main}
    hot = [f for f in sanit if fx_rules[f["kind"]]["hot"]]
    if heater and gm:
        (e2, i2), dim_h = _group_pipe([f["kind"] for f in hot], "ECS", pr, options, 13)
        out["heater_link"] = {"length_m": round(G.dist((heater["x"], heater["y"]), (gm["x"], gm["y"])) + 1.5, 1),
                              "pipe_ext_mm": e2, "pipe_int_mm": i2, **dim_h}
    out["manifolds"] = list(manifolds.values())

    # ---------------- évacuations ----------------------------------------------------------------
    _drains(out, sanit, levels, options, pr)
    return out


def _group_pipe(kinds, net, pr, options, floor_int, colonne=False):
    """Tube d'une conduite desservant plusieurs appareils.

    FR : NF DTU 60.11 — méthode des coefficients (graphique) jusqu'à 15, sinon débit probable et vitesse de calcul
    (1,5 m/s en colonne montante, 2 m/s ailleurs) ; une seule machine à laver dans le débit.
    Autres pays : somme des débits × simultanéité, vitesse maximale du référentiel."""
    fx_rules = pr["fixtures"]
    if not pr.get("dtu"):
        q = sum(fx_rules[k]["q"] for k in kinds) * simultaneity(len(kinds)) if kinds else 0
        pipe = max(pipe_for_flow(q, pr["max_velocity"], pr["pipes"]), pipe_for(floor_int, pr["pipes"]))
        return pipe, {"q_probable_ls": round(q, 3)}
    g = D.groupe_alimentation(kinds, "q" if net == "EF" else "q_ecs", colonne=colonne,
                              baignoire_l=options.get("bath_capacity_l"))
    vmax = pr["max_velocity"] if g["methode"] == "individuelle" else g["v_calcul"]
    pipe = max(pipe_for_flow(g["q_probable"], vmax, pr["pipes"]), pipe_for(floor_int, pr["pipes"]))
    if g["d_int_min"]:
        pipe = max(pipe, pipe_for(g["d_int_min"], pr["pipes"], pr["pipe_tolerance_mm"]))
    return pipe, {"q_probable_ls": round(g["q_probable"], 3), "v_max": vmax, "method": g["methode"],
                  "coef_total": g["coef_total"], "d_int_min_mm": g["d_int_min"], "y": round(g["y"], 3)}


def _branch_diameter(kind, length_m, pr):
    """Ø PVC du branchement : Ø courant du référentiel, relevé si le Ø intérieur DTU n'est pas couvert."""
    d = pr["fixtures"][kind]["drain"]
    if not pr.get("dtu"):
        return d, None
    need = D.vidange_int_min(kind, length_m)
    return (D.pvc_pour(need, plancher=d), need) if need else (d, None)


def _beside(room, p, d):
    w = Wall(room, inset=0.15)
    s = w.s_of(p)
    sp = w.snap(s + d) or s
    return w.point(sp)


def _nearest_wall_point(level, fixtures):
    fx = [f for f in fixtures if f["level_id"] == level.id] or fixtures
    cx = sum(f["x"] for f in fx) / len(fx)
    cy = sum(f["y"] for f in fx) / len(fx)
    return {"x": cx, "y": cy}


def _outside_mask(level, cell=0.1, close=0.5):
    """Grille « extérieur » : pièces dilatées de `close` (murs, placards non relevés),
    puis remplissage depuis le bord. Un vide intérieur n'est donc jamais pris pour la façade."""
    pts = [p for r in level.rooms for p in r.polygon]
    x0, y0, x1, y1 = G.bbox(pts)
    x0, y0, x1, y1 = x0 - 2, y0 - 2, x1 + 2, y1 + 2
    nx, ny = int((x1 - x0) / cell) + 1, int((y1 - y0) / cell) + 1
    occ = [[False] * ny for _ in range(nx)]
    for i in range(nx):
        x = x0 + (i + 0.5) * cell
        for j in range(ny):
            y = y0 + (j + 0.5) * cell
            occ[i][j] = any(G.point_in_polygon((x, y), r.polygon) for r in level.rooms)
    k = int(round(close / cell))
    dil = [[False] * ny for _ in range(nx)]
    for i in range(nx):
        for j in range(ny):
            if occ[i][j]:
                for di in range(-k, k + 1):
                    ii = i + di
                    if 0 <= ii < nx:
                        row = dil[ii]
                        for dj in range(-k, k + 1):
                            jj = j + dj
                            if 0 <= jj < ny:
                                row[jj] = True
    outside = [[False] * ny for _ in range(nx)]
    stack = [(0, 0)]
    while stack:
        i, j = stack.pop()
        if not (0 <= i < nx and 0 <= j < ny) or outside[i][j] or dil[i][j]:
            continue
        outside[i][j] = True
        stack.extend(((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)))

    def is_out(p):
        i, j = int((p[0] - x0) / cell), int((p[1] - y0) / cell)
        return 0 <= i < nx and 0 <= j < ny and outside[i][j]
    return is_out


def _exterior_edges(level):
    """Parois de façade : segments de pièces donnant sur l'extérieur du bâtiment."""
    is_out = getattr(level, "_is_out", None)
    if is_out is None:
        is_out = _outside_mask(level)
        level._is_out = is_out
    out = []
    for r in level.rooms:
        for a, b in G.edges(r.polygon):
            mid = G.lerp(a, b, 0.5)
            n = G.inward_normal(a, b, r.polygon)
            if any(is_out((mid[0] - n[0] * d, mid[1] - n[1] * d)) for d in (0.9, 1.3)):
                out.append((a, b, r))
    return out


def _exterior_point(level, target):
    best = None
    for a, b, r in _exterior_edges(level):
        t, d = G.project_on_segment(target, a, b)
        t = max(0.05, min(0.95, t))
        p = G.lerp(a, b, t)
        dd = G.dist(p, target)
        if best is None or dd < best[0]:
            best = (dd, p)
    return best[1] if best else None


def _drains(out, sanit, levels, options, pr):
    dtu = pr.get("dtu")
    ground = levels[0]
    slope = pr["slope_min"]
    did = 0

    def branch(f, path, to, level_id, available, apparent):
        nonlocal did
        did += 1
        L = G.path_length(path) + 0.3
        d, need = _branch_diameter(f["kind"], L, pr)
        row = {"id": f"E{did}", "net": "EV" if f["kind"] == "wc" else "EU", "level_id": level_id,
               "fixture_id": f["id"], "fixture": f["kind"], "to": to, "path": _r(path), "length_m": round(L, 1),
               "diameter_mm": d, "slope": slope, "drop_m": round(L * slope + d / 1000, 3), "available_m": available}
        if dtu:
            row["d_int_min_mm"] = need
            if apparent:          # en plancher / faux plafond d'étage ; au RDC le branchement est enterré
                row["supports"] = D.colliers(d, L)
        out["drains"].append(row)
        return row

    # Chutes : une par niveau supérieur ayant des appareils, placée près du WC / de la douche.
    stacks = []
    for lv in levels[1:]:
        fx = [f for f in sanit if f["level_id"] == lv.id]
        if not fx:
            continue
        anchor = next((f for f in fx if f["kind"] == "wc"), None) \
            or next((f for f in fx if f["kind"] in ("douche", "baignoire")), fx[0])
        room = next(r for r in lv.rooms if r.id == anchor["room_id"])
        w = Wall(room, inset=0.10)
        p = w.point(w.s_of((anchor["x"], anchor["y"])))
        below = room_at(levels, ground.id, p)
        st = {"id": f"CH-{lv.id}", "level_id": lv.id, "x": round(p[0], 3), "y": round(p[1], 3),
              "height_m": round(lv.elevation - ground.elevation + 1.0, 2),
              "lands_in_room": below.name if below else None, "fixtures": [f["id"] for f in fx]}
        rows = [branch(f, G.manhattan_path((f["x"], f["y"]), p), st["id"], lv.id,
                       options.get("floor_drain_depth_m", 0.20), True) for f in fx]
        diam = max(r["diameter_mm"] for r in rows)
        if dtu:
            # NF DTU 60.11 Tableau 4 : Ø intérieur mini selon les appareils desservis, constant sur toute la hauteur
            need = D.chute_int_min([f["kind"] for f in fx])
            diam = max(diam, D.pvc_pour(need))
            st.update({"d_int_min_mm": need, "supports": D.colliers(diam, st["height_m"], vertical=True)})
        elif len(fx) > 1:
            diam = max(diam, 75)          # chute commune à plusieurs appareils
        st["diameter_mm"] = diam
        st["ventilation"] = f"primaire Ø{diam} prolongée hors toiture"
        stacks.append(st)
    out["stacks"] = stacks

    # RDC : collecteur sous dallage vers la sortie en façade
    gfx = [f for f in sanit if f["level_id"] == ground.id]
    sources = [((f["x"], f["y"]), f) for f in gfx] + [((s["x"], s["y"]), s) for s in stacks]
    if not sources:
        return
    # sortie au plus près des gros débits (WC, pied de chute) : pondération 3
    wts = [3 if ("kind" not in s or s.get("kind") == "wc") else 1 for _, s in sources]
    cx = sum(p[0] * w for (p, _), w in zip(sources, wts)) / sum(wts)
    cy = sum(p[1] * w for (p, _), w in zip(sources, wts)) / sum(wts)
    exit_p = _exterior_point(ground, (cx, cy)) or (cx, cy)
    far = max(sources, key=lambda s: G.manhattan(s[0], exit_p))
    coll_path = G.manhattan_path(far[0], exit_p, horizontal_first=False)
    slab = options.get("slab_drain_depth_m", 0.50)
    for p, src in sources:
        if src is far[1]:
            continue
        path = G.manhattan_path(p, _nearest_on_path(p, coll_path))
        if "kind" in src:
            branch(src, path, "COL", ground.id, slab, False)
        else:
            did += 1
            L = G.path_length(path) + 0.3
            d = src["diameter_mm"]
            out["drains"].append({"id": f"E{did}", "net": "EU/EV", "level_id": ground.id, "fixture_id": src["id"],
                                  "fixture": "chute", "to": "COL", "path": _r(path), "length_m": round(L, 1),
                                  "diameter_mm": d, "slope": slope, "drop_m": round(L * slope + d / 1000, 3),
                                  "available_m": slab})
    # le point le plus éloigné se raccorde à l'origine du collecteur
    if "kind" in far[1]:
        branch(far[1], [far[0], far[0]], "COL", ground.id, slab, False)

    coll_len = G.path_length(coll_path)
    diams = [d["diameter_mm"] for d in out["drains"]] + [s["diameter_mm"] for s in stacks]
    coll_d = max(max(diams), 100)         # collecteur enterré : Ø100 minimum (règle de l'art)
    coll = {}
    if dtu:
        # NF DTU 60.11 §3.3 : débit probable des appareils desservis, Bazin à demi-plein, jamais sous la chute
        c = D.collecteur([f["kind"] for f in sanit], slope, d_chute_ext=max([s["diameter_mm"] for s in stacks] or [0]),
                         plancher=coll_d)
        coll_d = c["diametre"]
        coll = {"q_probable_ls": c["q_probable"], "capacity_ls": c["capacite"], "y": c["y"]}
    out["collector"] = {"id": "COL", "path": _r(coll_path), "length_m": round(coll_len + 0.5, 1),
                        "diameter_mm": coll_d, "slope": slope,
                        "drop_m": round(coll_len * slope + coll_d / 1000, 3), "available_m": slab, **coll}
    out["exit"] = {"x": round(exit_p[0], 3), "y": round(exit_p[1], 3),
                   "label": "Sortie EU/EV → regard de visite"}


def _nearest_on_path(p, path):
    best = None
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        t, d = G.project_on_segment(p, a, b)
        q = G.lerp(a, b, max(0.0, min(1.0, t)))
        if best is None or d < best[0]:
            best = (d, q)
    return best[1]


def _r(path):
    return [[round(x, 3), round(y, 3)] for x, y in path]
