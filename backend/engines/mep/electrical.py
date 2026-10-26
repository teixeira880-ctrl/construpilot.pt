"""Électricité : implantation des points, circuits, protections, tableau et contrôles.

Deux étapes séparées pour permettre l'édition par le professionnel :
  1. `layout()`  propose les points (prises, éclairage, commandes, sorties spécialisées) ;
  2. `network()` calcule circuits / DDR / tableau / longueurs à partir des points,
     qu'ils viennent de la proposition ou d'une implantation modifiée à la main.
"""
from __future__ import annotations

import math

from . import geometry as G
from .equipment import FOOTPRINT
from .model import room_index
from .placement import Wall, door_switch_s
from .rules import HABITABLE

LIGHT_KINDS = {"point_lumineux", "point_lumineux_ext"}
SOCKET_KINDS = {"prise", "prise_plan_travail"}
SWITCH_KINDS = {"interrupteur", "va_et_vient"}
MULTI_ACCESS = {"sejour", "entree", "circulation", "garage"}
APPLIANCE_TO_CIRCUIT = {"plaque": "plaque", "four": "four", "lave_vaisselle": "lave_vaisselle",
                        "lave_linge": "lave_linge", "seche_linge": "seche_linge",
                        "chauffe_eau": "chauffe_eau"}


class _Ids:
    def __init__(self, prefix):
        self.prefix, self.n = prefix, 0

    def __call__(self):
        self.n += 1
        return f"{self.prefix}{self.n}"


def _pt(kind, p, room, h, nid, **kw):
    return {"id": nid(), "kind": kind, "x": round(p[0], 3), "y": round(p[1], 3), "h": h,
            "room_id": room.id, "level_id": room.level_id, "source": "auto", **kw}


# ======================================================================================
# 1. Implantation
# ======================================================================================
def layout(levels, equipment, options, rules) -> list[dict]:
    er = rules["elec"]
    H = er["heights"]
    nid = _Ids("e")
    pts: list[dict] = []
    entrance_room, entrance_door = _main_entrance(levels)
    rooms_by_id = room_index(levels)

    for lv in levels:
        for room in lv.rooms:
            if room.type in ("escalier", "exterieur"):
                continue
            wall = Wall(room)
            s = room.area
            eq = [f for f in equipment if f["room_id"] == room.id]
            # --- éclairage ---------------------------------------------------------
            lights = []
            for c in _light_positions(room, er):
                lights.append(_pt("point_lumineux", c, room, lv.height, nid))
            # --- commandes : une par accès (va-et-vient pour les pièces à plusieurs accès)
            inner_doors = [d for d in room.doors if d[0].kind != "porte_garage"]
            if not inner_doors:
                inner_doors = room.doors[:1]
            cap = 3 if s >= 8 else 2
            n_cmd = min(cap, len(inner_doors)) if room.type in MULTI_ACCESS else min(1, len(inner_doors))
            kind_cmd = "va_et_vient" if n_cmd >= 2 else "interrupteur"
            # portes avant passages ouverts, puis la plus large
            ext_first = room.type == "entree"
            secondary = {"salle_de_bain", "salle_d_eau", "wc", "dressing", "cellier"}

            def _other_is_secondary(d):
                others = [rid for rid, *_ in d[0].rooms if rid != room.id]
                return room.type not in secondary and any(rooms_by_id[o].type in secondary for o in others)
            ranked = sorted(inner_doors, key=lambda d: (d[0].kind == "passage", d[0].exterior != ext_first,
                                                        _other_is_secondary(d), -d[0].width))
            for d in ranked[:max(1, n_cmd)]:
                sp = wall.place_at(door_switch_s(wall, d))
                if sp is not None:
                    pts.append(_pt(kind_cmd, wall.point(sp, 0.08), room, H["interrupteur"], nid,
                                   controls=[x["id"] for x in lights]))
            if not inner_doors and lights:
                sp = wall.place_at(0.5)
                if sp is not None:
                    pts.append(_pt("interrupteur", wall.point(sp, 0.08), room, H["interrupteur"], nid,
                                   controls=[x["id"] for x in lights]))
            pts.extend(lights)
            # --- réservations : appareils déjà implantés --------------------------------
            for f in eq:
                sf = wall.s_of((f["x"], f["y"]))
                wall.block(sf - 0.45, sf + 0.45)
            # --- cuisine : plan de travail + circuits spécialisés -------------------------
            n_work = er["worktop"](room.type, s)
            if n_work:
                pts.extend(_worktop_sockets(room, wall, eq, n_work, H, nid))
            # --- salle de bains : socle hors volumes -----------------------------------
            n_sock = er["sockets"](room.type, s)
            if room.type in ("salle_de_bain", "salle_d_eau"):
                fps = [G.rect_footprint((f["x"], f["y"]), *FOOTPRINT[f["kind"]])
                       for f in eq if f["kind"] in ("douche", "baignoire")]
                for sp, d in wall.best_far_from(fps, er["bathroom_clearance_m"], n_sock):
                    p = wall.point(sp)
                    pts.append(_pt("prise", p, room, H["prise"], nid,
                                   clearance_m=round(min((G.dist_point_to_rect(p, fp) for fp in fps), default=9.0), 2)))
                wet = [f for f in eq if f["kind"] in ("douche", "baignoire")]
                les_p = (wet[0]["x"], wet[0]["y"] - 0.6) if wet else (room.center[0] + 0.45, room.center[1] + 0.45)
                if not G.point_in_polygon(les_p, room.polygon):
                    les_p = G.interior_point_near(les_p, room.polygon)
                pts.append(_pt("les", les_p, room, 0.2, nid, label="LES"))
            else:
                for sp in wall.place_even(n_sock, s_start=0.3 * wall.P / max(1, n_sock)):
                    pts.append(_pt("prise", wall.point(sp), room, H["prise"], nid))
            # --- communication ---------------------------------------------------------
            for sp in wall.place_even(er["rj45"](room.type, s)):
                pts.append(_pt("rj45", wall.point(sp), room, H["rj45"], nid))
            # --- sorties spécialisées ----------------------------------------------------
            for f in eq:
                use = APPLIANCE_TO_CIRCUIT.get(f["kind"])
                if not use:
                    continue
                if f["kind"] == "chauffe_eau" and options.get("water_heater") not in ("ballon_electrique", "thermodynamique"):
                    continue
                kind = "sortie_cable" if use in ("plaque", "chauffe_eau") else "prise_specialisee"
                pts.append(_pt(kind, (f["x"], f["y"]), room,
                               H["sortie_cable"] if kind == "sortie_cable" else H["prise"], nid,
                               use=use, equipment_id=f["id"]))
    # Tableau + coffret de communication (GTL) près de l'entrée principale
    if entrance_room:
        w = Wall(entrance_room)
        s_door = door_switch_s(w, entrance_door) if entrance_door else 0.5
        sp = w.snap(s_door + 0.6) or 0.5
        p = w.point(sp, 0.15)
        pts.append(_pt("tableau", p, entrance_room, H["tableau"], nid, label="GTL"))
        pts.append(_pt("coffret_com", (p[0], p[1]), entrance_room, 1.9, nid, label="Coffret com."))
        if entrance_door:
            o = entrance_door[0]
            n = G.inward_normal(*w.edges[entrance_door[1]], entrance_room.polygon)
            m = o.mid
            ext = (m[0] - n[0] * 0.45, m[1] - n[1] * 0.45)
            pts.append(_pt("point_lumineux_ext", ext, entrance_room, 2.0, nid, label="Applique ext."))
    # Détecteurs de fumée : un par niveau (circulation / entrée / séjour)
    n_daaf = rules["elec"]["smoke_detector_per_level"]
    for lv in levels:
        if not n_daaf or not lv.rooms:
            continue
        pref = sorted(lv.rooms, key=lambda r: (r.type not in ("circulation", "entree"),
                                               r.type != "sejour", -r.area))
        r = pref[0]
        c = G.centroid(r.polygon)
        pts.append(_pt("daaf", (c[0] + 0.3, c[1] + 0.3), r, lv.height, nid))
    # VMC : groupe en combles / local technique, bouches en pièces humides
    if options.get("vmc"):
        wet = [r for lv in levels for r in lv.rooms if r.type in ("cuisine", "wc", "salle_de_bain", "salle_d_eau", "buanderie")]
        if wet:
            top = max(levels, key=lambda lv: lv.elevation)
            host = next((r for r in top.rooms if r.type in ("circulation", "salle_de_bain", "salle_d_eau")), top.rooms[0])
            c = G.centroid(host.polygon)
            pts.append(_pt("sortie_cable", (c[0] - 0.3, c[1] - 0.3), host, top.height, nid, use="vmc", label="VMC"))
    if options.get("ev_charger"):
        g = next((r for lv in levels for r in lv.rooms if r.type == "garage"), None)
        if g:
            w = Wall(g, inset=0.15)
            sp = w.snap(w.P * 0.6) or 0.0
            pts.append(_pt("sortie_cable", w.point(sp), g, 1.2, nid, use="irve", label="IRVE"))
    return pts


def _light_positions(room, er):
    s = room.area
    x0, y0, x1, y1 = G.bbox(room.polygon)
    w, h = x1 - x0, y1 - y0
    if s > er["light_large_room_m2"] or max(w, h) / max(0.1, min(w, h)) > 2.2 and s > 12:
        if w >= h:
            halves = [(x0, y0, (x0 + x1) / 2, y1), ((x0 + x1) / 2, y0, x1, y1)]
        else:
            halves = [(x0, y0, x1, (y0 + y1) / 2), (x0, (y0 + y1) / 2, x1, y1)]
        out = []
        for a, b, c, d in halves:
            target = ((a + c) / 2, (b + d) / 2)
            out.append(target if G.point_in_polygon(target, room.polygon)
                       else G.interior_point_near(target, room.polygon))
        return out
    return [room.center]


def _worktop_sockets(room, wall, eq, n, H, nid):
    """Socles au-dessus du plan de travail : le long de l'évier et de la plaque, jamais
    au-dessus d'eux (dégagement 0,30 m de part et d'autre)."""
    out = []
    anchors = [f for f in eq if f["kind"] in ("evier", "plaque")]
    if not anchors:
        for sp in wall.place_even(n):
            out.append(_pt("prise_plan_travail", wall.point(sp), room, H["prise_plan_travail"], nid))
        return out
    # plus petit arc du périmètre contenant l'évier et la plaque (le périmètre est circulaire)
    ss = sorted(wall.s_of((f["x"], f["y"])) for f in anchors)
    gaps = [((ss[(i + 1) % len(ss)] - ss[i]) % wall.P or wall.P, i) for i in range(len(ss))]
    _, gi = max(gaps)
    start, end = ss[(gi + 1) % len(ss)], ss[gi]
    if end < start:
        end += wall.P
    lo, hi = start - 1.0, end + 1.0
    if hi - lo > wall.P:
        lo, hi = 0, wall.P
    for sp in wall.place_even(n, lo, hi):
        out.append(_pt("prise_plan_travail", wall.point(sp), room, H["prise_plan_travail"], nid))
    missing = n - len(out)
    for sp in wall.place_even(missing):
        out.append(_pt("prise_plan_travail", wall.point(sp), room, H["prise_plan_travail"], nid))
    return out


def _main_entrance(levels):
    if not levels:
        return None, None
    ground = levels[0]
    for kinds in (("entree",), ("circulation", "sejour"), ("garage", "cellier")):
        for r in ground.rooms:
            if r.type in kinds:
                ext = [d for d in r.doors if d[0].exterior and d[0].kind in ("porte", "porte_fenetre")]
                if ext:
                    return r, max(ext, key=lambda d: d[0].width)
    r = next((x for x in ground.rooms if x.type == "entree"), ground.rooms[0] if ground.rooms else None)
    return r, (r.doors[0] if r and r.doors else None)


# ======================================================================================
# 2. Réseau : circuits, protections, longueurs
# ======================================================================================
def network(points, levels, options, rules) -> dict:
    er = rules["elec"]
    rooms = room_index(levels)
    lv_by_id = {lv.id: lv for lv in levels}
    board = next((p for p in points if p["kind"] == "tableau"), None)
    if board is None:
        r0 = levels[0].rooms[0]
        board = {"id": "e0", "kind": "tableau", "x": r0.center[0], "y": r0.center[1], "h": 1.4,
                 "room_id": r0.id, "level_id": r0.level_id, "source": "auto"}
    cid = _Ids("C")
    circuits = []

    def add(kind, pts_, section, breaker, label, rcd_type=None, use=None):
        c = {"id": cid(), "kind": kind, "use": use, "label": label, "section_mm2": section,
             "breaker_a": breaker, "rcd_type": rcd_type or er["rcd_default_type"],
             "points": [p["id"] for p in pts_]}
        for p in pts_:
            p["circuit_id"] = c["id"]
        c["length_m"] = _circuit_length(board, pts_, points, lv_by_id, options)
        circuits.append(c)

    lights = [p for p in points if p["kind"] in LIGHT_KINDS]
    for grp in _chunks_by_proximity(lights, board, er["lighting_circuit"]["max_points"], lv_by_id):
        lc = er["lighting_circuit"]
        add("eclairage", grp, lc["section"], lc["breaker"], _label_rooms("Éclairage", grp, rooms))
    socks = [p for p in points if p["kind"] == "prise"]
    for grp in _chunks_by_proximity(socks, board, er["socket_circuit"]["max_points"], lv_by_id):
        sc = er["socket_circuit"]
        add("prises", grp, sc["section"], sc["breaker"], _label_rooms("Prises", grp, rooms))
    work = [p for p in points if p["kind"] == "prise_plan_travail"]
    for grp in _chunks_by_proximity(work, board, er["worktop_circuit"]["max_points"], lv_by_id):
        wc = er["worktop_circuit"]
        add("prises_cuisine", grp, wc["section"], wc["breaker"], _label_rooms("Prises plan de travail", grp, rooms))
    spec = er["specialised"]
    for p in points:
        use = p.get("use")
        if p["kind"] in ("prise_specialisee", "sortie_cable") and use in spec:
            sp = spec[use]
            add("specialise", [p], sp["section"], sp["breaker"], sp["label"], sp.get("rcd_type"), use)
    if options.get("freezer"):
        pass  # congélateur : à positionner par l'utilisateur (prise spécialisée `congelateur`)

    rcds = _assign_rcds(circuits, levels, er)
    board_info = _board(circuits, rcds, er, options)
    cables = _cable_totals(circuits, points, board, lv_by_id, options)
    return {"board": board, "circuits": circuits, "rcds": rcds, "panel": board_info, "cables": cables}


def _label_rooms(prefix, grp, rooms):
    names = []
    for p in grp:
        r = rooms.get(p["room_id"])
        n = r.name if r else "?"
        if n not in names:
            names.append(n)
    return f"{prefix} — {', '.join(names[:4])}{'…' if len(names) > 4 else ''}"


def _chunks_by_proximity(pts, board, max_n, lv_by_id):
    """Regroupe les points par niveau puis par chaînage du plus proche voisin."""
    out = []
    by_level = {}
    for p in pts:
        by_level.setdefault(p["level_id"], []).append(p)
    for lid in sorted(by_level, key=lambda k: lv_by_id[k].elevation if k in lv_by_id else 0):
        rest = list(by_level[lid])
        cur = (board["x"], board["y"])
        chain = []
        while rest:
            nxt = min(rest, key=lambda p: G.manhattan(cur, (p["x"], p["y"])))
            rest.remove(nxt)
            chain.append(nxt)
            cur = (nxt["x"], nxt["y"])
        n_groups = math.ceil(len(chain) / max_n) if chain else 0
        if n_groups:
            size = math.ceil(len(chain) / n_groups)
            out.extend(chain[i:i + size] for i in range(0, len(chain), size))
    return out


def _route_h(lv, options):
    return lv.height if options.get("route", "plafond") == "plafond" else 0.0


def _circuit_length(board, pts, all_points, lv_by_id, options):
    """Longueur de câble : tableau → points chaînés (Manhattan + descentes), + commandes."""
    if not pts:
        return 0.0
    blv = lv_by_id.get(board["level_id"])
    total = abs(_route_h(blv, options) - board["h"]) if blv else 1.0
    cur = (board["x"], board["y"])
    cur_lv = board["level_id"]
    for i, p in enumerate(pts):
        lv = lv_by_id.get(p["level_id"])
        if p["level_id"] != cur_lv:
            # changement de niveau par la GTL / gaine palière (à l'aplomb du tableau)
            total += G.manhattan(cur, (board["x"], board["y"]))
            total += abs((lv.elevation if lv else 0) - (lv_by_id[cur_lv].elevation if cur_lv in lv_by_id else 0))
            cur = (board["x"], board["y"])
            cur_lv = p["level_id"]
        total += G.manhattan(cur, (p["x"], p["y"]))
        drop = abs(_route_h(lv, options) - p["h"]) if lv else 0.0
        total += drop * (1 if i == len(pts) - 1 else 2)
        cur = (p["x"], p["y"])
    by_id = {q["id"]: q for q in all_points}
    for sw in all_points:
        if sw["kind"] in SWITCH_KINDS and set(sw.get("controls") or []) & {p["id"] for p in pts}:
            lv = lv_by_id.get(sw["level_id"])
            for lid in sw["controls"]:
                light = by_id.get(lid)
                if light:
                    total += G.manhattan((sw["x"], sw["y"]), (light["x"], light["y"]))
                    total += abs(_route_h(lv, options) - sw["h"]) if lv else 1.4
    return round(total * (1 + options.get("cable_slack", 0.10)), 1)


def _assign_rcds(circuits, levels, er):
    surface = sum(r.area for lv in levels for r in lv.rooms if r.type in HABITABLE)
    ratings = next(v for lim, v in er["rcd_by_surface"] if surface <= lim)
    rcds = [{"id": f"DDR{i + 1}", "rating_a": a, "type": er["rcd_default_type"], "sensitivity_ma": 30,
             "circuits": []} for i, a in enumerate(ratings)]
    special_f = [c for c in circuits if c["rcd_type"] == "F"]
    others = [c for c in circuits if c["rcd_type"] != "F"]
    # Les éclairages et les prises sont répartis sur plusieurs DDR (continuité de service).
    order = {"eclairage": 0, "prises": 1, "prises_cuisine": 2, "specialise": 3}
    others.sort(key=lambda c: (order.get(c["kind"], 9), c["id"]))
    for c in others:
        target = min(rcds, key=lambda r: (len(r["circuits"]) >= er["rcd_max_circuits"],
                                          sum(1 for x in r["circuits"] if x["kind"] == c["kind"]),
                                          len(r["circuits"])))
        if len(target["circuits"]) >= er["rcd_max_circuits"]:
            target = {"id": f"DDR{len(rcds) + 1}", "rating_a": 40, "type": er["rcd_default_type"],
                      "sensitivity_ma": 30, "circuits": []}
            rcds.append(target)
        target["circuits"].append(c)
    if special_f:
        rcds.append({"id": f"DDR{len(rcds) + 1}", "rating_a": 40, "type": "F", "sensitivity_ma": 30,
                     "circuits": special_f})
    for r in rcds:
        for c in r["circuits"]:
            c["rcd_id"] = r["id"]
        r["circuits"] = [c["id"] for c in r["circuits"]]
    rcds = [r for r in rcds if r["circuits"]]
    return rcds


def _board(circuits, rcds, er, options):
    modules = 2 * len(rcds) + len(circuits)
    if any(c.get("use") == "chauffe_eau" for c in circuits):
        modules += 1                      # contacteur heures creuses
    if options.get("surge_protector"):
        modules += 2
    reserve = math.ceil(modules * er["reserve_ratio"])
    total = modules + reserve
    rows = max(1, math.ceil(total / 13))
    return {"modules_used": modules, "modules_reserve": reserve, "rows_13": rows,
            "capacity_modules": rows * 13,
            "contactor_hc": any(c.get("use") == "chauffe_eau" for c in circuits)}


def _cable_totals(circuits, points, board, lv_by_id, options):
    by_section: dict[float, float] = {}
    for c in circuits:
        by_section[c["section_mm2"]] = by_section.get(c["section_mm2"], 0.0) + c["length_m"]
    rj = [p for p in points if p["kind"] == "rj45"]
    cat6 = 0.0
    for p in rj:
        lv = lv_by_id.get(p["level_id"])
        blv = lv_by_id.get(board["level_id"])
        d = G.manhattan((board["x"], board["y"]), (p["x"], p["y"]))
        d += abs((lv.elevation if lv else 0) - (blv.elevation if blv else 0))
        d += abs(_route_h(lv, options) - p["h"]) + 1.0 if lv else 2.0
        cat6 += d
    return {"by_section_m": {str(k): round(v, 1) for k, v in sorted(by_section.items())},
            "rj45_cat6_m": round(cat6 * (1 + options.get("cable_slack", 0.10)), 1)}
