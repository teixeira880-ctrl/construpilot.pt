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

    # ---------- refends porteurs (murs intérieurs parallèles à X qui recoupent la portée des planchers) ----------
    @property
    def refends(self) -> list[dict]:
        """envelope.refends = [{id, y0, y1, x0?, x1?, label?, gaps: [{level, x0, x1}]}] : murs intérieurs porteurs continus
        des fondations au dernier plancher ; un « gap » (garage, grande baie) est franchi par une poutre BA."""
        out = []
        for i, r in enumerate(self.raw["envelope"].get("refends") or []):
            y0, y1 = float(r["y0"]), float(r["y1"])
            out.append({"id": r.get("id") or f"RF{i + 1}", "y0": y0, "y1": y1, "t": round(y1 - y0, 3),
                        "x0": float(r.get("x0", self.t_str)), "x1": float(r.get("x1", self.L - self.t_str)),
                        "label": r.get("label") or f"Refend porteur y = {(y0 + y1) / 2:.2f}".replace(".", ","),
                        "gaps": list(r.get("gaps") or [])})
        return sorted(out, key=lambda r: r["y0"])

    def refend(self, rid: str) -> dict | None:
        return next((r for r in self.refends if r["id"] == rid), None)

    @property
    def bays(self) -> list[tuple[float, float]]:
        """Travées libres des planchers (sens Y) entre nus des murs porteurs : façades/mitoyens et refends."""
        faces = [self.t_str] + [v for r in self.refends for v in (r["y0"], r["y1"])] + [self.W - self.t_str]
        return [(round(a, 3), round(b, 3)) for a, b in zip(faces[0::2], faces[1::2])]

    @property
    def clear_span_y(self) -> float:
        """Portée libre la plus grande entre nus intérieurs des murs porteurs (structure)."""
        return round(max(b - a for a, b in self.bays), 3)

    # ---------- toiture : faîtage parallèle à Y (pignons = murs le long de X) ou parallèle à X ----------
    @property
    def ridge_along_x(self) -> bool:
        return str(self.raw["roof"].get("ridge_axis", "y")).lower() == "x"

    @property
    def roof_run(self) -> float:
        """Projection horizontale d'un versant (égout → faîtage)."""
        r = self.raw["roof"]
        if self.ridge_along_x:
            return float(r.get("ridge_y", self.W / 2))
        return float(r.get("ridge_x", self.L / 2))

    @property
    def ridge_length(self) -> float:
        return self.L if self.ridge_along_x else self.W

    @property
    def gable_length(self) -> float:
        """Longueur à la base d'un pignon (= portée de la toiture)."""
        return self.W if self.ridge_along_x else self.L

    @property
    def trusses(self) -> list[float]:
        """Fermes intermédiaires (abscisses le long du faîtage) quand la distance entre pignons dépasse 7,50 m :
        les pannes portent de pignon à ferme, portée ≤ 5 m environ. Positions imposées par roof.trusses si fournies."""
        r = self.raw["roof"]
        if r.get("trusses") is not None:
            return [float(v) for v in r["trusses"]]
        span = self.ridge_length
        if span <= 7.5:
            return []
        import math
        n = math.ceil(span / 5.0) - 1
        return [round(span * k / (n + 1), 3) for k in range(1, n + 1)]

    def roof_z(self, x: float, y: float) -> float:
        """Cote du dessus de la couverture (sans débord) au droit du point (x, y)."""
        r = self.raw["roof"]
        tan_a = (r["ridge_level"] - r["eaves_level"]) / max(self.roof_run, 0.1)
        d = abs(y - self.roof_run) if self.ridge_along_x else abs(x - self.roof_run)
        return r["ridge_level"] - d * tan_a

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
