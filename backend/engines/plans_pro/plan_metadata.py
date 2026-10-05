"""Agregação de quantidades a partir das views Autodesk Model Derivative.

Mapeia categorias Revit/IFC + layers DWG para ouvrages PT (Paredes, Lajes, Pilares…).
"""
from __future__ import annotations

import re
from typing import Any


_LAYER_RULES: list[tuple[tuple[str, ...], str]] = [
    (("wall", "mur", "parede", "paredes", "voile", "cloison", "partition"), "Paredes"),
    (("beam", "poutre", "viga", "vigas", "linteau", "lintel"), "Vigas"),
    (("cols", "col", "column", "pilar", "pilares", "poteau", "colonne"), "Pilares"),
    (("flor", "floor", "slab", "laje", "lajes", "dalle", "plancher", "piso"), "Lajes"),
    (("door", "porte", "porta", "portas"), "Portas"),
    (("glaz", "wind", "window", "janela", "janelas", "fenetre", "vitrage"), "Janelas"),
    (("strs", "stair", "stairs", "escada", "escadas", "escalier"), "Escadas"),
    (("roof", "cobertura", "coberturas", "toit", "toiture"), "Coberturas"),
    (("fndn", "found", "fundacao", "fundações", "fondation", "sapata"), "Fundações"),
    (("grid", "trame", "eixo", "eixos", "axe"), "Eixos / malha"),
    (("detl", "detail", "detalhe", "détail"), "Detalhes"),
    (("site", "topo", "terreno", "terrain"), "Terreno"),
    (("plmb", "plomb", "canaliz", "esgoto", "aguas"), "Canalização"),
    (("elec", "eletric", "lght", "light", "iluminacao"), "Eletricidade"),
    (("hvac", "avac", "cvc", "ventil"), "AVAC"),
    (("anno", "dims", "text", "symb", "iden", "titl", "cota", "cotas", "texto"), "Anotações"),
]

ORDER = ["Paredes", "Lajes", "Vigas", "Pilares", "Fundações", "Portas",
         "Janelas", "Escadas", "Coberturas", "Canalização", "Eletricidade", "AVAC"]


def _layer_category(layer: str) -> str:
    tokens = [t for t in re.split(r"[-_ .]+", layer.lower()) if t]
    for words, cat in _LAYER_RULES:
        for tok in tokens:
            if tok in words:
                return cat
            for w in words:
                if len(w) >= 4 and tok.startswith(w):
                    return cat
    return "Outros"


def aggregate_quantities(views: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Agrega categorias por view. Para DWG (sem categories), usa layers."""
    result: dict[str, dict[str, Any]] = {}

    def bucket(cat: str) -> dict[str, Any]:
        return result.setdefault(cat, {
            "count": 0, "layers": [], "source": None,
        })

    # 1) Revit/IFC: categories presentes
    for view in views or []:
        for item in view.get("categories") or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                cat, count = str(item[0]), int(item[1])
            elif isinstance(item, dict):
                cat, count = str(item.get("name") or item.get("category") or ""), int(item.get("count") or 0)
            else:
                continue
            if not cat:
                continue
            b = bucket(cat)
            b["count"] = max(b["count"], count)
            b["source"] = "categories"

    # 2) DWG: só layers → agrupar
    if not any(v["count"] for v in result.values()):
        result.clear()
        best: dict[str, dict[str, int]] = {}
        for view in views or []:
            per_view: dict[str, dict[str, int]] = {}
            for item in view.get("layers") or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    layer, count = str(item[0]), int(item[1])
                elif isinstance(item, dict):
                    layer, count = str(item.get("name") or ""), int(item.get("count") or 0)
                else:
                    continue
                if not layer:
                    continue
                cat = _layer_category(layer)
                per_view.setdefault(cat, {})[layer] = count
            for cat, layers in per_view.items():
                if sum(layers.values()) > sum(best.get(cat, {}).values()):
                    best[cat] = layers
        for cat, layers in best.items():
            b = bucket(cat)
            b["count"] = sum(layers.values())
            b["layers"] = [
                {"layer": k, "count": v}
                for k, v in sorted(layers.items(), key=lambda kv: -kv[1])[:12]
            ]
            b["source"] = "layers"

    # 3) Ordenação PT
    def sort_key(kv: tuple[str, dict[str, Any]]) -> tuple[int, int]:
        cat, data = kv
        order_idx = ORDER.index(cat) if cat in ORDER else 50
        return (order_idx, -data["count"])

    return dict(sorted(result.items(), key=sort_key))
