"""DXF/DWG Import — parseur natif ezdxf pour ConstruPilot PLAN.

- **DXF** (natif) : ezdxf lit lignes, LWPOLYLINE, TEXT, MTEXT, CIRCLE, DIMENSION.
- **DWG** : nécessite ODA File Converter (binaire externe). Non installé → on
  renvoie une ValueError explicite pour que le frontend guide l'utilisateur.

Pour un DXF, on rend une preview raster PNG (matplotlib est trop lourd — on
utilise PIL en dessinant les segments à la main) et on renvoie la même structure
normalisée que `plan_processor.process_pdf` : page unique avec `vectors` +
`text_blocks` + `image_png_b64`.
"""
from __future__ import annotations

import base64
import io
import logging

from PIL import Image, ImageDraw

import ezdxf
from ezdxf.recover import readfile as recover_readfile

logger = logging.getLogger(__name__)

# Taille max de la preview raster (côté le plus grand)
PREVIEW_MAX_SIDE = 2000
PREVIEW_MARGIN = 40


def _iter_dxf_entities(msp) -> None:
    """Génère les entités graphiques utiles depuis un modelspace ezdxf."""
    for e in msp:
        yield e


def _points_from_polyline(entity) -> list[tuple[float, float]]:
    """Extrait les points d'une LWPOLYLINE ou POLYLINE en 2D."""
    dxftype = entity.dxftype()
    pts: list[tuple[float, float]] = []
    if dxftype == "LWPOLYLINE":
        for p in entity.vertices():
            pts.append((float(p[0]), float(p[1])))
    elif dxftype == "POLYLINE":
        for v in entity.vertices:
            loc = v.dxf.location
            pts.append((float(loc[0]), float(loc[1])))
    return pts


def _bounds_from_entity(e, upd) -> None:
    """Feed the per-type extents of entity `e` into `upd(x, y)`.
    Silent no-op if the entity has an unsupported type or bad geometry."""
    t = e.dxftype()
    if t == "LINE":
        upd(e.dxf.start.x, e.dxf.start.y)
        upd(e.dxf.end.x, e.dxf.end.y)
    elif t in ("LWPOLYLINE", "POLYLINE"):
        for p in _points_from_polyline(e):
            upd(p[0], p[1])
    elif t == "CIRCLE":
        c, r = e.dxf.center, e.dxf.radius
        upd(c.x - r, c.y - r)
        upd(c.x + r, c.y + r)
    elif t in ("TEXT", "MTEXT"):
        pos = e.dxf.insert if hasattr(e.dxf, "insert") else None
        if pos:
            upd(pos.x, pos.y)


def _compute_bounds(entities) -> tuple[float, float, float, float]:
    """Renvoie (min_x, min_y, max_x, max_y) sur toutes les entités."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    def upd(x, y) -> None:
        nonlocal min_x, min_y, max_x, max_y
        if x < min_x: min_x = x
        if y < min_y: min_y = y
        if x > max_x: max_x = x
        if y > max_y: max_y = y

    for e in entities:
        try:
            _bounds_from_entity(e, upd)
        except Exception:
            continue

    if min_x == float("inf"):
        return (0.0, 0.0, 100.0, 100.0)
    return (min_x, min_y, max_x, max_y)


def _render_preview(entities, bounds: tuple[float, float, float, float]) -> tuple[bytes, dict]:
    """Rend une preview PNG en dessinant les segments DXF avec PIL.

    Renvoie (png_bytes, mapping{scale_px_per_dxf_unit, offset_x, offset_y, width, height})
    """
    min_x, min_y, max_x, max_y = bounds
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)

    # Fit dans PREVIEW_MAX_SIDE avec marge
    ratio = min((PREVIEW_MAX_SIDE - 2 * PREVIEW_MARGIN) / span_x,
                (PREVIEW_MAX_SIDE - 2 * PREVIEW_MARGIN) / span_y)
    w = int(span_x * ratio + 2 * PREVIEW_MARGIN)
    h = int(span_y * ratio + 2 * PREVIEW_MARGIN)

    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)

    def to_px(x, y):
        # DXF Y monte, image Y descend → flip
        px = PREVIEW_MARGIN + (x - min_x) * ratio
        py = h - PREVIEW_MARGIN - (y - min_y) * ratio
        return (px, py)

    for e in entities:
        t = e.dxftype()
        try:
            if t == "LINE":
                p1 = to_px(e.dxf.start.x, e.dxf.start.y)
                p2 = to_px(e.dxf.end.x, e.dxf.end.y)
                draw.line([p1, p2], fill="black", width=2)
            elif t in ("LWPOLYLINE", "POLYLINE"):
                pts = [to_px(*p) for p in _points_from_polyline(e)]
                if len(pts) >= 2:
                    closed = getattr(e, "closed", False) or (hasattr(e.dxf, "flags")
                                                             and e.dxf.flags & 1)
                    if closed and pts:
                        pts = pts + [pts[0]]
                    draw.line(pts, fill="black", width=2)
            elif t == "CIRCLE":
                c = e.dxf.center; r = e.dxf.radius
                x1, y1 = to_px(c.x - r, c.y - r)
                x2, y2 = to_px(c.x + r, c.y + r)
                # bounding box PIL veut coords ordonnées
                draw.ellipse([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                             outline="black", width=2)
            elif t == "TEXT":
                pos = to_px(e.dxf.insert.x, e.dxf.insert.y)
                draw.text(pos, str(e.dxf.text or ""), fill="black")
            elif t == "MTEXT":
                pos = to_px(e.dxf.insert.x, e.dxf.insert.y)
                draw.text(pos, str(e.text or ""), fill="black")
        except Exception:
            continue

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), {
        "scale_px_per_dxf_unit": ratio,
        "offset_x": min_x, "offset_y": min_y,
        "width": w, "height": h,
    }


def process_dxf(data: bytes, filename: str = "plan.dxf") -> dict:
    """Point d'entrée : parse un DXF et renvoie la structure normalisée."""
    # ezdxf a besoin d'un stream mode texte ou d'un fichier temporaire
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        f.write(data)
        path = f.name

    try:
        try:
            doc = ezdxf.readfile(path)
        except Exception:
            # Fichier abîmé → tenter la récupération
            doc, _ = recover_readfile(path)
    except Exception as e:
        raise ValueError(f"DXF invalide : {e}")
    finally:
        try:
            import os
            os.unlink(path)
        except Exception:
            pass

    msp = doc.modelspace()
    entities = list(_iter_dxf_entities(msp))
    bounds = _compute_bounds(entities)
    png, mapping = _render_preview(entities, bounds)

    # Extract vectors en coord IMAGE PX (pour le canvas) — LINE + LWPOLYLINE seulement
    vectors = []
    ratio = mapping["scale_px_per_dxf_unit"]
    min_x = mapping["offset_x"]; min_y = mapping["offset_y"]
    h = mapping["height"]

    def to_px(x, y):
        return (PREVIEW_MARGIN + (x - min_x) * ratio,
                h - PREVIEW_MARGIN - (y - min_y) * ratio)

    for e in entities:
        t = e.dxftype()
        try:
            if t == "LINE":
                p1 = to_px(e.dxf.start.x, e.dxf.start.y)
                p2 = to_px(e.dxf.end.x, e.dxf.end.y)
                vectors.append({"type": "line",
                                "p1": [round(p1[0], 2), round(p1[1], 2)],
                                "p2": [round(p2[0], 2), round(p2[1], 2)]})
            elif t in ("LWPOLYLINE", "POLYLINE"):
                pts_dxf = _points_from_polyline(e)
                for i in range(len(pts_dxf) - 1):
                    p1 = to_px(*pts_dxf[i])
                    p2 = to_px(*pts_dxf[i + 1])
                    vectors.append({"type": "line",
                                    "p1": [round(p1[0], 2), round(p1[1], 2)],
                                    "p2": [round(p2[0], 2), round(p2[1], 2)]})
        except Exception:
            continue

    # Text blocks en coord image
    text_blocks = []
    for e in entities:
        t = e.dxftype()
        try:
            if t == "TEXT":
                pos = to_px(e.dxf.insert.x, e.dxf.insert.y)
                text_blocks.append({"text": str(e.dxf.text or ""),
                                    "x": pos[0], "y": pos[1], "w": 0, "h": 0})
            elif t == "MTEXT":
                pos = to_px(e.dxf.insert.x, e.dxf.insert.y)
                text_blocks.append({"text": str(e.text or ""),
                                    "x": pos[0], "y": pos[1], "w": 0, "h": 0})
        except Exception:
            continue

    return {
        "kind": "dxf",
        "page_count": 1,
        "pages": [{
            "index": 0,
            "width_px": mapping["width"],
            "height_px": mapping["height"],
            "dpi": 96,
            "image_png_b64": base64.b64encode(png).decode("ascii"),
            "vectors": vectors[:8000],
            "text_blocks": text_blocks[:3000],
            "dimensions_count": sum(1 for e in entities if e.dxftype() == "DIMENSION"),
            "raw_text_length": sum(len(t.get("text", "")) for t in text_blocks),
            "dxf_bounds": {"min_x": bounds[0], "min_y": bounds[1],
                           "max_x": bounds[2], "max_y": bounds[3]},
            "dxf_ratio": mapping["scale_px_per_dxf_unit"],
        }],
        # DXF ratio = pixels/unit_dxf. Si le DXF est en mètres, ratio = pixels/m
        # (calibration auto ! très pratique)
        "dxf_units": _guess_units(doc),
        "detected_scale_denominator": None,
    }


def _guess_units(doc) -> str:
    """Devine l'unité DXF (mètres/cm/mm/pouces)."""
    try:
        insunits = doc.header.get("$INSUNITS", 0)
        return {
            0: "unspecified", 1: "inches", 2: "feet", 4: "mm",
            5: "cm", 6: "m", 8: "microinches", 9: "mils",
            13: "microns", 14: "decimeters", 15: "dekameters",
        }.get(insunits, f"code_{insunits}")
    except Exception:
        return "unknown"


def process_dwg(data: bytes, filename: str = "plan.dwg") -> dict:
    """DWG nécessite ODA File Converter externe — non installé.
    Retourne une erreur explicite avec instructions utilisateur.
    """
    raise ValueError(
        "Format DWG non supporté nativement — convertissez d'abord en DXF "
        "avec AutoCAD (Enregistrer sous → DXF), LibreCAD, ou un convertisseur en ligne "
        "(ex: https://cloudconvert.com/dwg-to-dxf), puis réimportez le fichier."
    )
