"""Pipeline Autodesk pour la lecture de plans.

Réutilise directement l'API publique de ``engines.autodesk_md`` (déjà en prod) :

  - ``extract(data, filename, user_id=)`` fait upload OSS + traduction MD +
    récupération des vues + extraction properties (avec cache par hash).

Le rôle de ce module est de :
  1. exposer une interface stable pour ``plans_pro/routes.py``
  2. enrichir la sortie brute Autodesk avec des quantités agrégées
     par catégorie (murs / dalles / portes / fenêtres / poutres…)
  3. offrir un fallback souple si Autodesk n'est pas configuré
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """Renvoie True si les variables APS_* sont présentes."""
    import os
    required = ("APS_CLIENT_ID", "APS_CLIENT_SECRET", "APS_BUCKET_KEY", "APS_OSS_BASE_URL")
    return all(bool(os.environ.get(k, "").strip()) for k in required)


async def extract_full(file_bytes: bytes, filename: str, *, user_id: str) -> dict:
    """Wrapper autour de ``autodesk_md.extract`` : renvoie un dict enrichi.

    Structure de sortie :
        {
          "urn": str,
          "status": "success"|...,
          "views": [ { name, role, guid, objects, layers[], categories[], property_keys[] } ],
          "sample_objects": [ { objectid, name, properties } ],
          "quantities": { <Catégorie>: { count, total_area_m2, ... } },
          "cached": bool,
        }
    """
    from engines import autodesk_md
    raw = await autodesk_md.extract(file_bytes, filename, user_id=user_id)

    # Convertit les summaries en un dict de quantités agrégées
    quantities = _aggregate_quantities(raw)
    return {
        **raw,
        "quantities": quantities,
    }


_LAYER_RULES: list[tuple[tuple[str, ...], str]] = [
    (("wall", "mur", "voile", "cloison", "partition"), "Paredes"),
    (("beam", "poutre", "linteau"), "Vigas"),
    (("cols", "col", "column", "poteau", "pilier"), "Pilares"),
    (("flor", "floor", "slab", "dalle", "plancher", "sol"), "Pavimentos"),
    (("door", "porte"), "Portas"),
    (("glaz", "wind", "fenetre", "fenêtre", "vitrage", "chassis", "châssis"), "Janelas"),
    (("strs", "stair", "escalier"), "Escadas"),
    (("roof", "toit", "couverture"), "Coberturas"),
    (("fndn", "found", "fondation", "semelle", "longrine"), "Fondations"),
    (("grid", "trame", "axe", "file"), "Trames / axes"),
    (("detl", "detail", "détail"), "Détails"),
    (("site", "topo", "terrain"), "Site"),
    (("plmb", "plomb", "sanit", "evac"), "Canalização"),
    (("elec", "lght", "light"), "Eletricidade"),
    (("hvac", "cvc", "vent"), "CVC"),
    (("anno", "dims", "text", "symb", "iden", "revc", "titl", "nplt", "cote", "texte"), "Annotations"),
]


def _layer_category(layer: str) -> str:
    tokens = [t for t in re.split(r"[-_ .]+", layer.lower()) if t]
    for words, cat in _LAYER_RULES:
        if any(tok in words or any(tok.startswith(w) for w in words if len(w) >= 4) for tok in tokens):
            return cat
    return "Autres"


async def thumbnail(urn: str, size: int = 400) -> bytes | None:
    """Aperçu PNG Model Derivative (max 400 px) ; None si indisponible."""
    from engines.autodesk_client import request
    try:
        resp = await request("GET", f"https://developer.api.autodesk.com/modelderivative/v2/designdata/{urn}/thumbnail",
                             params={"width": size, "height": size})
    except Exception as exc:  # noqa: BLE001 — l'aperçu est optionnel
        logger.warning("Autodesk thumbnail unavailable: %s", exc)
        return None
    data = resp.content or b""
    return data if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8" else None


def _aggregate_quantities(raw: dict) -> dict[str, dict[str, Any]]:
    """Comptage par catégorie Revit/IFC (``categories``) ou, pour les DWG, par calque (``layers``).

    Les sample_objects (propriétés Revit ``Dimensions``) enrichissent surface / volume / longueur.
    """
    result: dict[str, dict[str, Any]] = {}

    def _bucket(cat: str) -> dict[str, Any]:
        return result.setdefault(cat, {
            "count": 0, "total_area_m2": None,
            "total_volume_m3": None, "total_length_m": None, "layers": [],
        })

    # 1) Comptage par catégorie (Revit/IFC) — max entre les vues (une vue = un même modèle)
    for view in raw.get("views", []) or []:
        for cat, count in view.get("categories", []) or []:
            cur = _bucket(cat)
            cur["count"] = max(cur["count"], int(count))

    # 2) DWG : pas de catégories (ou toutes à zéro) → calques AIA / français regroupés par ouvrage
    if not any(v["count"] for v in result.values()):
        result.clear()
        best: dict[str, dict[str, int]] = {}
        for view in raw.get("views", []) or []:
            per_view: dict[str, dict[str, int]] = {}
            for layer, count in view.get("layers", []) or []:
                cat = _layer_category(str(layer))
                per_view.setdefault(cat, {})[str(layer)] = int(count)
            for cat, layers in per_view.items():
                if sum(layers.values()) > sum(best.get(cat, {}).values()):
                    best[cat] = layers
        for cat, layers in best.items():
            cur = _bucket(cat)
            cur["count"] = sum(layers.values())
            cur["layers"] = [{"layer": k, "count": v} for k, v in sorted(layers.items(), key=lambda kv: -kv[1])[:12]]
            cur["source"] = "layers"

    # 3) Enrichissement via les sample_objects (properties Revit/IFC « Dimensions »)
    for obj in raw.get("sample_objects", []) or []:
        props = obj.get("properties") or {}
        dims = props.get("Dimensions") if isinstance(props.get("Dimensions"), dict) else {}
        if not dims:
            continue
        cur = _bucket(_detect_category(obj))
        area = _parse_num(dims.get("Area"))
        volume = _parse_num(dims.get("Volume"))
        length = _parse_num(dims.get("Length"))
        if area:
            cur["total_area_m2"] = round((cur.get("total_area_m2") or 0) + area, 2)
        if volume:
            cur["total_volume_m3"] = round((cur.get("total_volume_m3") or 0) + volume, 2)
        if length:
            cur["total_length_m"] = round((cur.get("total_length_m") or 0) + length, 2)

    for cur in result.values():
        if not cur["layers"]:
            cur.pop("layers")
    order = ["Paredes", "Pavimentos", "Vigas", "Pilares", "Fondations", "Portas", "Janelas", "Escadas", "Coberturas"]
    return dict(sorted(result.items(), key=lambda kv: (order.index(kv[0]) if kv[0] in order else 50 + (kv[0] in ("Annotations", "Autres", "Détails", "Trames / axes")), -kv[1]["count"])))


def _detect_category(obj: dict) -> str:
    props = obj.get("properties", {}) or {}
    if isinstance(props.get("Category"), str):
        return props["Category"]
    if isinstance(props.get("Type"), str):
        return props["Type"]
    for k in ("IFC Type", "IfcType", "IfcExportAs"):
        if isinstance(props.get(k), str):
            return props[k]
    name = (obj.get("name") or "").lower()
    for word, cat in [
        ("wall", "Paredes"), ("floor", "Pavimentos"), ("ceiling", "Tetos"),
        ("door", "Portas"), ("window", "Janelas"), ("column", "Pilares"),
        ("beam", "Vigas"), ("stair", "Escadas"), ("roof", "Coberturas"),
        ("mur", "Paredes"), ("dalle", "Pavimentos"), ("porte", "Portas"),
        ("fenêtre", "Janelas"), ("poteau", "Pilares"), ("poutre", "Vigas"),
    ]:
        if word in name:
            return cat
    return "Autres"


def _parse_num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return 0.0
    m = re.search(r"[-+]?\d*[.,]?\d+", value.replace(",", "."))
    return float(m.group(0)) if m else 0.0
