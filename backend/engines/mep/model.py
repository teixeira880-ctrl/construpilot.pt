"""Normalisation de l'entrée du moteur MEP.

Entrée (mètres, repère du plan, y vers le bas) :

    {
      "country": "fr" | "pt",
      "project": {"name": "...", "client": "..."},
      "levels": [{
          "id": "RDC", "name": "RDC", "elevation_m": 0, "height_m": 2.7,
          "origin": [dx, dy],                 # position du niveau dans le repère bâtiment
          "rooms": [{"id": "r1", "name": "Cuisine", "type": null, "polygon": [[x, y], ...]}],
          "openings": [{"kind": "porte|fenetre|baie|porte_fenetre|porte_garage|passage",
                        "a": [x, y], "b": [x, y]}],
          "fixtures": [{"kind": "evier|plaque|wc|lavabo|douche|...", "x": .., "y": ..}]
      }],
      "options": {...}
    }

Les coordonnées des pièces / ouvertures / équipements sont exprimées dans le repère
du niveau ; `origin` les place dans le repère commun du bâtiment (superposition des
niveaux pour les colonnes montantes et les chutes).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import geometry as G
from .rules import classify_room

DOOR_KINDS = {"porte", "porte_fenetre", "porte_garage", "passage"}
WINDOW_KINDS = {"fenetre", "baie", "porte_fenetre"}
EDGE_TOL = 0.40      # distance max ouverture ↔ paroi d'une pièce (épaisseur de mur + doublage)

DEFAULT_OPTIONS = {
    "water_heater": "ballon_electrique",   # ballon_electrique | thermodynamique | chaudiere | pac | aucun
    "water_heater_room": None,             # id de pièce ; sinon choix automatique
    "washing_machine_room": None,
    "dishwasher": True,
    "oven": True,
    "dryer": False,
    "freezer": False,
    "vmc": None,                            # None = oui en France, non au Portugal
    "ev_charger": False,
    "route": "plafond",                     # plafond | sol : cheminement des câbles
    "floor_drain_depth_m": 0.20,            # épaisseur disponible pour les évacuations à l'étage
    "slab_drain_depth_m": 0.50,             # profondeur disponible sous dallage au RDC
    "cable_slack": 0.10,                    # 10 % de surlongueur
    "pipe_slack": 0.10,
}


@dataclass
class Opening:
    kind: str
    a: tuple
    b: tuple
    rooms: list = field(default_factory=list)   # [(room_id, edge_index, t0, t1)]

    @property
    def width(self) -> float:
        return G.dist(self.a, self.b)

    @property
    def mid(self):
        return G.lerp(self.a, self.b, 0.5)

    @property
    def exterior(self) -> bool:
        return len(self.rooms) == 1


@dataclass
class Room:
    id: str
    name: str
    type: str
    polygon: list
    level_id: str
    doors: list = field(default_factory=list)      # [(Opening, edge_index, t0, t1)]
    windows: list = field(default_factory=list)

    @property
    def area(self) -> float:
        return G.area(self.polygon)

    @property
    def center(self):
        return G.centroid(self.polygon)


@dataclass
class Level:
    id: str
    name: str
    elevation: float
    height: float
    index: int
    rooms: list
    openings: list
    fixtures: list


def _pt(v) -> tuple:
    return (float(v[0]), float(v[1]))


def build(data: dict) -> tuple[list[Level], dict]:
    options = {**DEFAULT_OPTIONS, **(data.get("options") or {})}
    country = (data.get("country") or "fr").lower()
    if options.get("vmc") is None:
        options["vmc"] = country == "fr"
    levels: list[Level] = []
    for li, ld in enumerate(data.get("levels") or []):
        ox, oy = _pt(ld.get("origin") or (0, 0))
        lid = str(ld.get("id") or f"N{li}")
        rooms = []
        for ri, rd in enumerate(ld.get("rooms") or []):
            poly = [(_pt(p)[0] + ox, _pt(p)[1] + oy) for p in rd.get("polygon") or []]
            if len(poly) < 3:
                continue
            name = rd.get("name") or f"Pièce {ri + 1}"
            rooms.append(Room(id=str(rd.get("id") or f"{lid}-r{ri + 1}"), name=name,
                              type=rd.get("type") or classify_room(name),
                              polygon=poly, level_id=lid))
        openings = []
        for od in ld.get("openings") or []:
            a = _pt(od["a"])
            b = _pt(od["b"])
            o = Opening(kind=od.get("kind") or "porte", a=(a[0] + ox, a[1] + oy), b=(b[0] + ox, b[1] + oy))
            _attach(o, rooms)
            openings.append(o)
        fixtures = []
        for fd in ld.get("fixtures") or []:
            fixtures.append({**fd, "x": float(fd["x"]) + ox, "y": float(fd["y"]) + oy,
                             "level_id": lid, "source": fd.get("source") or "plan"})
        levels.append(Level(id=lid, name=ld.get("name") or lid,
                            elevation=float(ld.get("elevation_m", li * 2.8)),
                            height=float(ld.get("height_m", 2.7)), index=li,
                            rooms=rooms, openings=openings, fixtures=fixtures))
    levels.sort(key=lambda lv: lv.elevation)
    for i, lv in enumerate(levels):
        lv.index = i
    return levels, options


def _attach(o: Opening, rooms: list[Room]) -> None:
    """Rattache une ouverture aux parois des pièces voisines (une pièce = extérieure)."""
    for r in rooms:
        best = None
        for ei, (a, b) in enumerate(G.edges(r.polygon)):
            ta, da = G.project_on_segment(o.a, a, b)
            tb, db = G.project_on_segment(o.b, a, b)
            if max(da, db) > EDGE_TOL:
                continue
            t0, t1 = sorted((max(0.0, min(1.0, ta)), max(0.0, min(1.0, tb))))
            L = G.dist(a, b)
            if (t1 - t0) * L < 0.3:          # ouverture qui ne touche que l'angle
                continue
            d = da + db
            if best is None or d < best[0]:
                best = (d, ei, t0, t1)
        if best:
            _, ei, t0, t1 = best
            o.rooms.append((r.id, ei, t0, t1))
            if o.kind in DOOR_KINDS:
                r.doors.append((o, ei, t0, t1))
            if o.kind in WINDOW_KINDS:
                r.windows.append((o, ei, t0, t1))


def room_index(levels: list[Level]) -> dict:
    return {r.id: r for lv in levels for r in lv.rooms}


def level_of(levels: list[Level], level_id: str) -> Level:
    return next(lv for lv in levels if lv.id == level_id)


def room_at(levels: list[Level], level_id: str, p) -> Room | None:
    lv = level_of(levels, level_id)
    for r in lv.rooms:
        if G.point_in_polygon(p, r.polygon):
            return r
    best = min(lv.rooms, key=lambda r: G.min_dist_to_boundary(p, r.polygon), default=None)
    return best
