"""BuildingModel : chargement et accès au modèle bâtiment.

Le modèle est un JSON produit par la lecture du PC (agent Claude vision) puis validé
par les contrôles déterministes de `checks.py`. Aucun calcul ici : uniquement de la
géométrie et des accesseurs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Opening:
    id: str
    level: str
    side: str
    a: float          # début le long du mur (m)
    b: float          # fin le long du mur (m)
    sill: float       # allège au-dessus du plancher fini (m)
    height: float
    kind: str

    @property
    def width(self) -> float:
        return round(self.b - self.a, 3)


@dataclass
class Level:
    id: str
    name: str
    floor_top: float
    slab: float
    hsp: float
    use: str


@dataclass
class Model:
    raw: dict
    levels: list[Level] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)

    # ---------- géométrie générale ----------
    @property
    def L(self) -> float:
        return self.raw["envelope"]["length_x"]

    @property
    def W(self) -> float:
        return self.raw["envelope"]["width_y"]

    @property
    def t_tot(self) -> float:
        return self.raw["envelope"]["wall_total_thickness"]

    @property
    def t_str(self) -> float:
        return self.raw["envelope"]["wall_structural_thickness"]

    @property
    def inner(self) -> tuple[float, float, float, float]:
        t = self.t_tot
        return (t, t, self.L - t, self.W - t)

    @property
    def clear_span_y(self) -> float:
        """Portée libre entre nus intérieurs des murs mitoyens (structure)."""
        return round(self.W - 2 * self.t_str, 3)

    @property
    def span_y_calc(self) -> float:
        """Portée de calcul des planchers entre mitoyens : nu à nu + 2 × appui/2 (appui 0,10)."""
        return round(self.clear_span_y + 0.10, 3)

    def level(self, lid: str) -> Level:
        return next(l for l in self.levels if l.id == lid)

    def level_above(self, lid: str) -> Level | None:
        ids = [l.id for l in self.levels]
        i = ids.index(lid)
        return self.levels[i + 1] if i + 1 < len(self.levels) else None

    def storey_height(self, lid: str) -> float:
        """Hauteur d'étage (dessus de plancher à dessus de plancher, ou à l'égout pour le dernier)."""
        up = self.level_above(lid)
        top = up.floor_top if up else self.raw["roof"]["eaves_level"]
        return round(top - self.level(lid).floor_top, 3)

    def openings_on(self, side: str, level: str | None = None) -> list[Opening]:
        return [o for o in self.openings if o.side == side and (level is None or o.level == level)]

    @property
    def stair(self) -> dict:
        return self.raw["stair"]

    @property
    def roof(self) -> dict:
        return self.raw["roof"]

    @property
    def geo(self) -> dict:
        return self.raw["geotech"]

    def rooms(self, lid: str) -> list[dict]:
        return self.raw["rooms"].get(lid, [])

    def side(self, sid: str) -> dict:
        return self.raw["sides"][sid]

    def side_length(self, sid: str) -> float:
        return self.L if self.side(sid)["axis"] == "y" else self.W


def load(path: str | Path) -> Model:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def from_dict(raw: dict) -> Model:
    m = Model(raw=raw)
    for l in raw["levels"]:
        m.levels.append(Level(l["id"], l["name"], l["floor_top"], l["slab_thickness"], l["ceiling_height"], l["use"]))
    for o in raw["openings"]:
        m.openings.append(Opening(o["id"], o["level"], o["side"], o["from"], o["to"], o["sill"], o["height"], o["kind"]))
    return m
