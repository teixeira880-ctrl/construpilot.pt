"""Appareils sanitaires et électroménager : repris du plan quand la lecture les a détectés,
sinon implantés automatiquement selon le type de pièce (marqués `source="auto"`)."""
from __future__ import annotations

from . import geometry as G
from .placement import Wall

FOOTPRINT = {  # largeur × profondeur (m) pour le dessin et les volumes de salle de bains
    "evier": (1.0, 0.5), "lavabo": (0.6, 0.45), "lave_mains": (0.4, 0.3), "douche": (0.9, 0.9),
    "baignoire": (1.7, 0.75), "wc": (0.4, 0.65), "bidet": (0.4, 0.6), "lave_linge": (0.6, 0.6),
    "lave_vaisselle": (0.6, 0.6), "plaque": (0.6, 0.6), "four": (0.6, 0.6), "chauffe_eau": (0.6, 0.6),
    "seche_linge": (0.6, 0.6),
}
SANITARY = {"evier", "lavabo", "lave_mains", "douche", "baignoire", "wc", "bidet",
            "lave_linge", "lave_vaisselle"}


def _fx(kind, p, room, source, wall_s=None):
    return {"kind": kind, "x": round(p[0], 3), "y": round(p[1], 3), "room_id": room.id,
            "level_id": room.level_id, "source": source, "wall_s": wall_s}


def _fixtures_in(room, fixtures):
    """Appareils du plan situés dans la pièce (ou collés à sa paroi), non encore affectés."""
    out = []
    for f in fixtures:
        if f.get("_used") or f.get("level_id") != room.level_id:
            continue
        p = (f["x"], f["y"])
        if G.point_in_polygon(p, room.polygon) or G.min_dist_to_boundary(p, room.polygon) < 0.25:
            f["_used"] = True
            out.append(f)
    return out


def _longest_free_edge(wall: Wall) -> int:
    return max(range(len(wall.lengths)), key=wall.edge_free_length)


def _farthest_corner_from_doors(room):
    pts = room.polygon
    doors = [o.mid for o, *_ in room.doors] or [room.center]
    return max(pts, key=lambda p: min(G.dist(p, d) for d in doors))


def plan_equipment(levels, options) -> list[dict]:
    """Liste unique des appareils (sanitaires + électroménager + production d'ECS)."""
    out: list[dict] = []
    all_plan = [f for lv in levels for f in lv.fixtures]
    for lv in levels:
        for room in lv.rooms:
            given = _fixtures_in(room, all_plan)
            for f in given:
                f["room_id"] = room.id
            kinds = {f["kind"] for f in given}
            out.extend(given)
            wall = Wall(room, inset=0.30)
            if room.type == "cuisine":
                if "evier" not in kinds:
                    ei = _longest_free_edge(wall)
                    s = wall.place_at(wall.cum[ei] + wall.lengths[ei] / 2)
                    if s is not None:
                        out.append(_fx("evier", wall.point(s), room, "auto", s))
                        kinds.add("evier")
                ev = next(f for f in out if f["kind"] == "evier" and f["room_id"] == room.id)
                s_ev = wall.s_of((ev["x"], ev["y"]))
                wall.block(s_ev - 0.6, s_ev + 0.6)
                if "plaque" not in kinds:
                    s = wall.place_at(s_ev + 1.6)
                    if s is not None:
                        out.append(_fx("plaque", wall.point(s), room, "auto", s))
                pl = next((f for f in out if f["kind"] == "plaque" and f["room_id"] == room.id), None)
                if pl:
                    s_pl = wall.s_of((pl["x"], pl["y"]))
                    wall.block(s_pl - 0.4, s_pl + 0.4)
                if options.get("dishwasher") and "lave_vaisselle" not in kinds:
                    s = wall.place_at(s_ev + 0.85)
                    if s is not None:
                        out.append(_fx("lave_vaisselle", wall.point(s), room, "auto", s))
                if options.get("oven") and "four" not in kinds and pl:
                    s = wall.place_at(s_pl + 0.9)
                    if s is not None:
                        out.append(_fx("four", wall.point(s), room, "auto", s))
            elif room.type in ("salle_de_bain", "salle_d_eau"):
                if not kinds & {"douche", "baignoire"}:
                    kind = "baignoire" if room.type == "salle_de_bain" and room.area >= 5 else "douche"
                    c = _farthest_corner_from_doors(room)
                    cx = sum(p[0] for p in room.polygon) / len(room.polygon)
                    cy = sum(p[1] for p in room.polygon) / len(room.polygon)
                    w, d = FOOTPRINT[kind]
                    dx = (w / 2 + 0.05) * (1 if cx > c[0] else -1)
                    dy = (d / 2 + 0.05) * (1 if cy > c[1] else -1)
                    out.append(_fx(kind, (c[0] + dx, c[1] + dy), room, "auto"))
                if "lavabo" not in kinds:
                    wet = [f for f in out if f["room_id"] == room.id and f["kind"] in ("douche", "baignoire")]
                    fps = [G.rect_footprint((f["x"], f["y"]), *FOOTPRINT[f["kind"]]) for f in wet]
                    best = wall.best_far_from(fps, 0.3, 1)
                    if best:
                        out.append(_fx("lavabo", wall.point(best[0][0]), room, "auto", best[0][0]))
            elif room.type == "wc":
                if "wc" not in kinds:
                    door = room.doors[0][0].mid if room.doors else room.center
                    ei = max(range(len(wall.edges)),
                             key=lambda i: G.dist(G.lerp(*wall.edges[i], 0.5), door))
                    s = wall.place_at(wall.cum[ei] + wall.lengths[ei] / 2)
                    if s is not None:
                        out.append(_fx("wc", wall.point(s), room, "auto", s))
    # Lave-linge et production d'eau chaude : une seule pièce chacun
    rooms = [r for lv in levels for r in lv.rooms]
    if not any(f["kind"] == "lave_linge" for f in out):
        r = _pick_room(rooms, options.get("washing_machine_room"),
                       ("buanderie", "cellier", "garage", "salle_de_bain", "salle_d_eau"))
        if r:
            out.append(_auto_on_wall(r, "lave_linge", out))
    if options.get("dryer") and not any(f["kind"] == "seche_linge" for f in out):
        r = next((x for x in rooms if any(f["kind"] == "lave_linge" and f["room_id"] == x.id for f in out)), None)
        if r:
            out.append(_auto_on_wall(r, "seche_linge", out))
    if options.get("water_heater") not in (None, "aucun") and not any(f["kind"] == "chauffe_eau" for f in out):
        r = _pick_room(rooms, options.get("water_heater_room"),
                       ("cellier", "buanderie", "garage", "salle_de_bain", "salle_d_eau", "cuisine"))
        if r:
            out.append(_auto_on_wall(r, "chauffe_eau", out))
    for i, f in enumerate(out):
        f.pop("_used", None)
        f["id"] = f"eq{i + 1}"
    return out


def _pick_room(rooms, wanted_id, preference):
    if wanted_id:
        r = next((x for x in rooms if x.id == wanted_id), None)
        if r:
            return r
    ground = min((r.level_id for r in rooms), default=None)
    for kind in preference:
        cands = [r for r in rooms if r.type == kind]
        cands.sort(key=lambda r: (r.level_id != ground, -r.area))
        if cands:
            return cands[0]
    return None


def _auto_on_wall(room, kind, existing):
    wall = Wall(room, inset=0.35)
    for f in existing:
        if f["room_id"] == room.id:
            s = wall.s_of((f["x"], f["y"]))
            wall.block(s - 0.7, s + 0.7)
    ei = _longest_free_edge(wall)
    s = wall.place_at(wall.cum[ei] + 0.6) or 0.0
    return _fx(kind, wall.point(s), room, "auto", s)
