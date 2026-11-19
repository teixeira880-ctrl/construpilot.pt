"""Modelo geométrico REAL de um edifício (qualquer forma), independente de como foi lido.

Unidades: metros. Eixos: x para a direita, y para cima (Norte do desenho), origem no canto
inferior-esquerdo do contorno. Nenhuma hipótese de retângulo: o contorno é um polígono
qualquer (com pátios/saguões como furos) e as paredes são segmentos com qualquer ângulo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import LineString, MultiPolygon, Polygon, mapping, shape


@dataclass
class Wall:
    a: tuple[float, float]
    b: tuple[float, float]
    t: float                         # espessura (m)
    material: str = "alvenaria"      # "alvenaria" | "betao"
    exterior: bool = False
    retained_height: float = 0.0     # altura de terras suportadas (m) — muro de suporte se > 0
    source: str = ""

    @property
    def line(self) -> LineString:
        return LineString([self.a, self.b])

    @property
    def length(self) -> float:
        return self.line.length


@dataclass
class Building:
    footprint: Polygon                       # área de construção (com furos = pátios)
    covered: list[Polygon] = field(default_factory=list)   # áreas exteriores cobertas (palas)
    walls: list[Wall] = field(default_factory=list)
    floor_level: float = 0.0                 # cota do pavimento (m)
    roof_level: float = 3.30                 # cota da face superior da laje de cobertura (m)
    storeys: int = 1
    country: str = "PT"
    hypotheses: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)   # confrontações de leitura (fonte A vs B)
    sources: list[str] = field(default_factory=list)

    @property
    def roof_slab(self) -> Polygon | MultiPolygon:
        from shapely.ops import unary_union
        return unary_union([self.footprint, *self.covered]).buffer(0)

    @property
    def storey_height(self) -> float:
        return round(self.roof_level - self.floor_level, 3)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "footprint": mapping(self.footprint),
            "covered": [mapping(p) for p in self.covered],
            "walls": [w.__dict__ for w in self.walls],
            "floor_level": self.floor_level, "roof_level": self.roof_level,
            "storeys": self.storeys, "country": self.country,
            "hypotheses": self.hypotheses, "checks": self.checks, "sources": self.sources,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Building":
        return cls(
            footprint=shape(raw["footprint"]),
            covered=[shape(p) for p in raw.get("covered") or []],
            walls=[Wall(**{**w, "a": tuple(w["a"]), "b": tuple(w["b"])}) for w in raw.get("walls") or []],
            floor_level=float(raw.get("floor_level", 0.0)),
            roof_level=float(raw.get("roof_level", 3.3)),
            storeys=int(raw.get("storeys", 1)),
            country=raw.get("country", "PT"),
            hypotheses=dict(raw.get("hypotheses") or {}),
            checks=list(raw.get("checks") or []),
            sources=list(raw.get("sources") or []),
        )
