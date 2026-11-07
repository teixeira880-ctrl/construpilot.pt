"""Revestimentos por face (paredes: lados A/B interior/exterior; lajes: pavimento/teto).

Cada face recebe uma pilha de camadas (de dentro para fora), cada uma com cor, textura,
zona em altura (ex.: azulejo de 0 a 1,20 m, pintura de 1,20 m ao teto), espessura opcional
e artigo da biblioteca opcional. As áreas de cada camada alimentam o orçamento como
qualquer outra medição, com origem explícita:
  * camada em toda a altura da face → mesma fiabilidade da área da face (calculada pela geometria);
  * camada numa zona parcial → "estimada" (proporção da altura; aberturas supostas uniformes).
"""
from __future__ import annotations

import re
import secrets

from pydantic import BaseModel, Field, field_validator

PATTERNS = ("liso", "azulejo", "madeira", "pedra", "tijolo", "reboco")

PRESETS = [
    {"preset": "pintura", "name": "Pintura", "color": "#F2EEE6", "pattern": "liso", "thickness_mm": 0, "faces": ["interior", "exterior", "teto"]},
    {"preset": "reboco", "name": "Reboco tradicional", "color": "#E7E1D6", "pattern": "reboco", "thickness_mm": 15, "faces": ["interior", "exterior", "teto"]},
    {"preset": "estuque", "name": "Estuque projetado", "color": "#F5F2EC", "pattern": "liso", "thickness_mm": 10, "faces": ["interior", "teto"]},
    {"preset": "azulejo", "name": "Azulejo cerâmico", "color": "#FFFFFF", "pattern": "azulejo", "pattern_size_m": 0.2, "thickness_mm": 10, "faces": ["interior"]},
    {"preset": "azulejo_pt", "name": "Azulejo português", "color": "#2F5DA8", "pattern": "azulejo", "pattern_size_m": 0.14, "thickness_mm": 10, "faces": ["interior", "exterior"]},
    {"preset": "capoto", "name": "Capoto (ETICS)", "color": "#EDE6D8", "pattern": "reboco", "thickness_mm": 60, "faces": ["exterior"]},
    {"preset": "granito", "name": "Pedra granito", "color": "#9C9A94", "pattern": "pedra", "pattern_size_m": 0.6, "thickness_mm": 30, "faces": ["exterior", "interior", "pavimento"]},
    {"preset": "xisto", "name": "Pedra xisto", "color": "#5F5B55", "pattern": "pedra", "pattern_size_m": 0.4, "thickness_mm": 30, "faces": ["exterior"]},
    {"preset": "madeira", "name": "Revestimento em madeira", "color": "#A8754A", "pattern": "madeira", "pattern_size_m": 0.15, "thickness_mm": 20, "faces": ["interior", "exterior", "pavimento", "teto"]},
    {"preset": "tijolo_face", "name": "Tijolo face à vista", "color": "#B4583A", "pattern": "tijolo", "pattern_size_m": 0.25, "thickness_mm": 100, "faces": ["exterior", "interior"]},
    {"preset": "pladur", "name": "Gesso cartonado + pintura", "color": "#F4F1EB", "pattern": "liso", "thickness_mm": 13, "faces": ["interior", "teto"]},
    {"preset": "microcimento", "name": "Microcimento", "color": "#B9B4AC", "pattern": "reboco", "thickness_mm": 3, "faces": ["interior", "pavimento"]},
    {"preset": "papel", "name": "Papel de parede", "color": "#D9C9B0", "pattern": "liso", "thickness_mm": 1, "faces": ["interior"]},
    {"preset": "ceramico_chao", "name": "Pavimento cerâmico", "color": "#D8D0C2", "pattern": "azulejo", "pattern_size_m": 0.6, "thickness_mm": 10, "faces": ["pavimento"]},
    {"preset": "flutuante", "name": "Pavimento flutuante", "color": "#B98D5E", "pattern": "madeira", "pattern_size_m": 0.2, "thickness_mm": 8, "faces": ["pavimento"]},
]

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class Layer(BaseModel):
    layer_id: str | None = Field(default=None, max_length=40)
    preset: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    color: str = "#F2EEE6"
    pattern: str = "liso"
    pattern_size_m: float = Field(default=0.3, ge=0.03, le=3.0)
    from_m: float = Field(default=0.0, ge=0.0, le=200.0)
    to_m: float | None = Field(default=None, ge=0.0, le=200.0)
    thickness_mm: float = Field(default=0.0, ge=0.0, le=500.0)
    item_id: str | None = Field(default=None, max_length=60)

    @field_validator("color")
    @classmethod
    def _c(cls, v: str) -> str:
        if not _HEX.match(v or ""):
            raise ValueError("cor inválida (use #RRGGBB)")
        return v.upper()

    @field_validator("pattern")
    @classmethod
    def _p(cls, v: str) -> str:
        if v not in PATTERNS:
            raise ValueError(f"textura inválida ({', '.join(PATTERNS)})")
        return v

    @field_validator("to_m")
    @classmethod
    def _z(cls, v, info):
        if v is not None and v <= info.data.get("from_m", 0.0):
            raise ValueError("a altura final tem de ser superior à inicial")
        return v


def normalise_layers(layers: list[Layer]) -> list[dict]:
    out = []
    for l in layers[:8]:
        d = l.model_dump()
        d["layer_id"] = d.get("layer_id") or "fl_" + secrets.token_hex(4)
        out.append(d)
    return out


def side_label(faces: dict, side: str, swap: bool = False) -> str:
    lab = ((faces or {}).get("sides") or {}).get(side, {}).get("label", side)
    if swap and lab in ("interior", "exterior") and faces.get("kind") == "wall":
        other = "B" if side == "A" else "A"
        olab = faces["sides"].get(other, {}).get("label")
        return olab or lab
    return lab


def resolve_sides(faces: dict, target: str, swap: bool = False) -> list[str]:
    """Traduz um alvo ("interior", "exterior", "A", "B", "ambos", "pavimento", "teto"…) em lados."""
    if not faces:
        return []
    sides = list((faces.get("sides") or {}).keys())
    if target in sides:
        return [target]
    if target == "ambos":
        return sides
    alias = {"pavimento": "top", "cobertura": "top", "teto": "bottom"}
    if target in alias and alias[target] in sides:
        return [alias[target]]
    return [s for s in sides if side_label(faces, s, swap) == target]


def layer_area(faces: dict, side: str, layer: dict, wall_area: dict | None = None) -> dict | None:
    """Área de uma camada com origem e fonte. ``wall_area`` = quantidade efetiva da área da parede."""
    sd = ((faces or {}).get("sides") or {}).get(side)
    if not sd:
        return None
    base = float(sd.get("area") or 0)
    origin, source = "calculated", f"geometria: área da face {side}"
    if base <= 0 and wall_area:
        base, origin, source = float(wall_area["value"]), wall_area["origin"], "área da parede (uma face)"
    if base <= 0:
        return None
    if faces.get("kind") == "wall":
        h = max(1e-6, float(faces["z1"]) - float(faces["z0"]))
        lo = max(0.0, float(layer.get("from_m") or 0))
        hi = min(h, float(layer["to_m"])) if layer.get("to_m") is not None else h
        frac = max(0.0, hi - lo) / h
        if frac <= 0:
            return {"value": 0.0, "origin": "estimated", "source": "zona fora da altura da parede"}
        if frac < 0.999:
            return {"value": round(base * frac, 4), "origin": "estimated",
                    "source": f"{source} × {frac:.0%} da altura ({lo:.2f}–{hi:.2f} m; aberturas supostas uniformes)"}
    return {"value": round(base, 4), "origin": origin, "source": source}


def pseudo_elements(elements: dict[str, dict], finishes: list[dict], wall_areas: dict[str, dict]) -> list[dict]:
    """Elementos virtuais "revestimento" para o agrupamento/orçamento (um por camada aplicada)."""
    out = []
    for fd in finishes:
        e = elements.get(fd["gid"])
        if not e or not e.get("faces") or not e.get("included", True):
            continue
        for side, layers in (fd.get("sides") or {}).items():
            label = side_label(e["faces"], side, fd.get("swap", False))
            for l in layers or []:
                q = layer_area(e["faces"], side, l, wall_areas.get(fd["gid"]))
                name = f"{l['name']} · {l['color']}"
                rec = {
                    "gid": f"{fd['gid']}|{side}|{l['layer_id']}", "ifc_class": "Revestimento",
                    "category": "revestimentos", "name": name, "type_name": name,
                    "materials": [l["name"]], "storey": e.get("storey"), "storey_gid": e.get("storey_gid"),
                    "counted": True, "included": True, "face": label, "host_gid": fd["gid"],
                    "item_id": l.get("item_id"), "quantities": {},
                }
                if q and q["value"] > 0:
                    rec["quantities"]["area"] = {"key": "area", "value": q["value"], "unit": "m²",
                                                 "origin": q["origin"], "source": q["source"]}
                out.append(rec)
    return out
