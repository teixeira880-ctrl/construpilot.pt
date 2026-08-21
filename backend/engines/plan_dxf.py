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

from PIL import Image, ImageDraw, ImageFont

import ezdxf
from ezdxf.recover import readfile as recover_readfile

logger = logging.getLogger(__name__)

_FONT_CACHE: dict[int, "ImageFont.FreeTypeFont"] = {}


def _font(size: int):
    """Police TrueType (DejaVuSans, fournie avec Pillow) mise en cache par taille."""
    size = int(max(8, min(200, size)))
    f = _FONT_CACHE.get(size)
    if f is None:
        try:
            f = ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            f = ImageFont.load_default()
        _FONT_CACHE[size] = f
    return f

# Taille max de la preview raster (côté le plus grand)
PREVIEW_MAX_SIDE = 3200
PREVIEW_MARGIN = 40


_EXPLODE_TYPES = {"INSERT", "DIMENSION"}
_GRAPHIC_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT"}


def _iter_dxf_entities(msp, _depth: int = 0):
    """Génère les entités graphiques utiles depuis un modelspace ezdxf.

    Les INSERT (blocs) et DIMENSION (cotes) sont explosés en primitives via
    `virtual_entities()` afin de préserver la géométrie des blocs, les lignes de
    cote et le texte des cotes/descriptions. Récursion bornée pour les blocs
    imbriqués.
    """
    for e in msp:
        t = e.dxftype()
        if t in _EXPLODE_TYPES and _depth < 4:
            try:
                for sub in e.virtual_entities():
                    yield from _iter_dxf_entities([sub], _depth + 1)
                continue
            except Exception:
                pass
        if t in _GRAPHIC_TYPES:
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
    elif t == "ARC":
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
            elif t == "ARC":
                c = e.dxf.center; r = e.dxf.radius
                x1, y1 = to_px(c.x - r, c.y + r)
                x2, y2 = to_px(c.x + r, c.y - r)
                # DXF: angles CCW, Y haut. Image: Y bas → négation + inversion start/end.
                start = -float(e.dxf.end_angle)
                end = -float(e.dxf.start_angle)
                draw.arc([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                         start, end, fill="black", width=2)
            elif t in ("TEXT", "MTEXT"):
                txt = str(e.dxf.text if t == "TEXT" else (e.text or "")).replace("\n", " ")
                if not txt.strip():
                    continue
                th = float(getattr(e.dxf, "height", 0) or getattr(e.dxf, "char_height", 0) or 0)
                # Taille RÉELLE à l'échelle. On n'inflate PLUS le texte minuscule :
                # forcer une taille mini transformait les milliers de cotes/notes en pâtés
                # noirs illisibles. Sous ~6 px, le texte est illisible → on ne l'affiche pas.
                fsize = int(round(th * ratio)) if th else 0
                if fsize < 6:
                    continue
                fsize = min(fsize, 140)
                pos = to_px(e.dxf.insert.x, e.dxf.insert.y)
                # PIL place le texte par son coin haut-gauche → remonte d'une hauteur de police
                draw.text((pos[0], pos[1] - fsize), txt, fill="#333333", font=_font(fsize))
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
    dim_count = sum(1 for e in msp if e.dxftype() == "DIMENSION")
    entities = list(_iter_dxf_entities(msp))
    bounds = _compute_bounds(entities)
    png, mapping = _render_preview(entities, bounds)

    # Métré structure par calques (quantités réelles depuis la géométrie)
    structural_metre = None
    try:
        from engines.dxf_takeoff import extract_structural_metre
        unit_to_m = _unit_to_m(doc, bounds)
        structural_metre = extract_structural_metre(doc, unit_to_m)
    except Exception:
        logger.exception("structural metre extraction failed")

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
            "dimensions_count": dim_count,
            "raw_text_length": sum(len(t.get("text", "")) for t in text_blocks),
            "dxf_bounds": {"min_x": bounds[0], "min_y": bounds[1],
                           "max_x": bounds[2], "max_y": bounds[3]},
            "dxf_ratio": mapping["scale_px_per_dxf_unit"],
        }],
        # DXF ratio = pixels/unit_dxf. Si le DXF est en mètres, ratio = pixels/m
        # (calibration auto ! très pratique)
        "dxf_units": _guess_units(doc),
        "structural_metre": structural_metre,
        "detected_scale_denominator": None,
    }


_UNIT_TO_M = {"mm": 0.001, "cm": 0.01, "m": 1.0, "decimeters": 0.1,
              "dekameters": 10.0, "inches": 0.0254, "feet": 0.3048}


def _unit_to_m(doc, bounds) -> float:
    """Facteur unité DXF → mètres, avec contrôle de plausibilité (plan 0,5–1000 m)."""
    u = _UNIT_TO_M.get(_guess_units(doc))
    span = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
    if u and 0.5 <= span * u <= 1000:
        return u
    if span > 3000:
        return 0.001   # mm
    if span > 300:
        return 0.01    # cm
    return 1.0         # m


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
