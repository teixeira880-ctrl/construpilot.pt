"""Import DXF natif : unités déclarées, blocs transformés, courbes et rendu PDF noir/blanc.
Le DWG est converti par la route d’import (ODA local ou CloudConvert configuré).
Le rendu et les primitives partagent la même transformation ; les omissions sont signalées.
"""
from __future__ import annotations

import base64
import io
import logging
import re

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
# Rendu CAO fidèle (ezdxf + pymupdf) : taille cible du plus grand côté, en px.
HQ_TARGET_PX = 4200
HQ_MIN_DPI = 40
HQ_MAX_DPI = 300


def _inline_svg_styles(xml):
    """MuPDF ignore les classes CSS du SVG ezdxf : on recopie chaque style en attributs de présentation."""
    import re
    styles = {}
    for st in list(xml.iter("style")) + list(xml.iter("{http://www.w3.org/2000/svg}style")):
        m = re.match(r"\s*\.(\S+)\s*\{(.*)\}", st.text or "", re.S)
        if m:
            styles[m.group(1)] = {k.strip(): v.strip() for k, v in (kv.split(":", 1) for kv in m.group(2).split(";") if ":" in kv)
                                  if not (k.strip() == "stroke-width" and v.strip() == "none")}
    for el in xml.iter():
        cls = el.get("class")
        if cls and cls in styles:
            for k, v in styles[cls].items():
                el.set(k, v)
            del el.attrib["class"]
    return xml


def _render_preview_hq(doc, bounds):
    """Rendu vectoriel (SVG → PDF MuPDF) puis aperçu : transformation commune pour toutes les mesures.

    Le backend SVG d'ezdxf est ~10× plus rapide que le backend PyMuPDF sur les gros plans
    (des dizaines de milliers de tracés) ; la matrice DXF→page est celle réellement appliquée.
    """
    import math
    import xml.etree.ElementTree as ET
    import pymupdf
    from ezdxf.addons.drawing import RenderContext, Frontend, layout
    from ezdxf.addons.drawing.svg import SVGBackend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy, HatchPolicy

    backend = SVGBackend()
    config = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                           hatch_policy=HatchPolicy.SHOW_OUTLINE)
    Frontend(RenderContext(doc), backend, config=config).draw_layout(doc.modelspace())
    render_box = backend.player().bbox()
    if not render_box.has_data:
        raise ValueError("Le DXF ne contient aucun objet visible exploitable")
    if bounds and render_box.has_data:
        from ezdxf.math import BoundingBox2d
        focus = BoundingBox2d([(bounds[0], bounds[1]), (bounds[2], bounds[3])])
        if focus.size.x * focus.size.y < 0.9 * render_box.size.x * render_box.size.y:
            render_box = focus
    landscape = render_box.size.x >= render_box.size.y
    page = layout.Page(420 if landscape else 297, 297 if landscape else 420, layout.Units.mm,
                       margins=layout.Margins.all(10))
    settings = layout.Settings(fit_page=True)
    xml = _inline_svg_styles(backend.get_xml_root_element(page, settings=settings, render_box=render_box))
    matrix = backend.transformation_matrix  # DXF → unités viewBox, origine en haut à gauche
    vb_w, vb_h = (float(v) for v in xml.get("viewBox").split()[2:4])
    svg = ET.tostring(xml, encoding="utf-8", xml_declaration=True)
    with pymupdf.open(stream=svg, filetype="svg") as drawing:
        pdf = drawing.convert_to_pdf()
    with pymupdf.open(stream=pdf, filetype="pdf") as rendered:
        dpi = min(HQ_MAX_DPI, max(HQ_MIN_DPI, round(HQ_TARGET_PX * 72 / max(rendered[0].rect.width, rendered[0].rect.height))))
        pix = rendered[0].get_pixmap(matrix=pymupdf.Matrix(dpi/72,dpi/72), alpha=False)
        png = pix.tobytes("png")
        width, height = pix.width, pix.height
    kx, ky = width / vb_w, height / vb_h  # viewBox → pixels (la page PDF conserve les mm du SVG)
    origin, along = matrix.transform((0,0,0)), matrix.transform((1,0,0))
    ratio = math.hypot((along.x-origin.x)*kx,(along.y-origin.y)*ky)
    tx, ty = origin.x*kx, origin.y*ky
    return png, {"scale_px_per_dxf_unit": ratio, "offset_x": -tx/ratio, "offset_y": (ty-height)/ratio,
                 "width": width, "height": height, "margin": 0, "dpi": dpi, "pdf_bytes": pdf}


_EXPLODE_TYPES = {"INSERT", "DIMENSION"}
_GRAPHIC_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT"}


def _iter_dxf_entities(msp, _depth=0):
    from engines.cad_geometry import walk_entities
    yield from walk_entities(msp.doc, msp)


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
        "width": w, "height": h, "margin": PREVIEW_MARGIN,
    }


_DIM_UNIT_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\b", re.IGNORECASE)


def _extract_dimensions(msp, to_px, unit_to_m, diagnostics=None):
    """Cotes natives linéaires, blocs compris : projection et DIMLFAC respectés."""
    import math
    from engines.cad_geometry import walk_entities
    issues = diagnostics if diagnostics is not None else []
    out = []
    for e in walk_entities(msp.doc, msp, explode_dimensions=False, diagnostics=issues):
        if e.dxftype() != "DIMENSION":
            continue
        try:
            if e.dimtype not in (0,1):
                issues.append({"code":"NON_LINEAR_DIMENSION","type":e.dimtype})
                continue
            p2, p3 = e.dxf.defpoint2, e.dxf.defpoint3
            angle = math.radians(e.dxf.get("angle",0)) if e.dimtype == 0 else math.atan2(p3.y-p2.y,p3.x-p2.x)
            ux,uy = math.cos(angle),math.sin(angle)
            measured = abs((p3.x-p2.x)*ux+(p3.y-p2.y)*uy)
            base = e.dxf.defpoint
            def on_dimension(p):
                shift = (base.x-p.x)*(-uy)+(base.y-p.y)*ux
                return to_px(p.x-shift*uy,p.y+shift*ux)
            a,b = on_dimension(p2),on_dimension(p3)
            raw = str(e.dxf.get("text", "") or "")
            if raw == " ":
                issues.append({"code":"DIMENSION_TEXT_HIDDEN"}); continue
            txt=raw.strip()
            override = bool(txt and "<>" not in txt)
            indicated = measured*unit_to_m
            style = e.override()
            factor = float(style.get("dimlfac",1) or 1)
            if override:
                match = _DIM_UNIT_RE.fullmatch(txt)
                if not match:
                    issues.append({"code":"DIMENSION_OVERRIDE_UNREADABLE","text":txt[:100]}); continue
                number=float(match.group(1).replace(",","."))
                explicit=match.group(2)
                post=str(style.get("dimpost", "") or "").replace("<>", "").strip().lower()
                suffix = explicit.lower() if explicit else post
                unit = {"mm":.001,"cm":.01,"m":1.}.get(suffix)
                indicated = number*unit if unit is not None else number/abs(factor)*unit_to_m
            if measured<=0 or indicated<=0 or not math.isfinite(indicated):continue
            out.append({"x1":round(a[0],4),"y1":round(a[1],4),"x2":round(b[0],4),"y2":round(b[1],4),
                        "measured_m":round(measured*unit_to_m,6),"value_m":round(indicated,6),
                        "raw_text":txt or None,"override":override,"dimlfac":factor,"location":f"calque {e.dxf.layer}"})
        except Exception as exc:
            issues.append({"code":"DIMENSION_UNREADABLE","reason":type(exc).__name__})
    return out


def _focus_bounds(doc, bounds, diagnostics=None):
    """Stray far-away entities must not squeeze the drawing: when the dimensions occupy a small part of the full
    extents, the render focuses on the dimensioned drawing (+15 %). Recorded in diagnostics, never silent."""
    pts = []
    for e in doc.modelspace().query("DIMENSION"):
        for attr in ("defpoint", "defpoint2", "defpoint3"):
            p = e.dxf.get(attr)
            if p is not None:
                pts.append((p.x, p.y))
    if len(pts) < 8:
        return bounds
    xs, ys = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
    lo, hi = int(len(xs) * 0.01), max(int(len(xs) * 0.99), int(len(xs) * 0.01) + 1)
    min_x, max_x, min_y, max_y = xs[lo], xs[hi - 1], ys[lo], ys[hi - 1]
    span_x, span_y = max(max_x - min_x, 1e-9), max(max_y - min_y, 1e-9)
    full_x, full_y = max(bounds[2] - bounds[0], 1e-9), max(bounds[3] - bounds[1], 1e-9)
    if span_x * span_y >= 0.25 * full_x * full_y:
        return bounds
    if diagnostics is not None:
        diagnostics.append({"code": "EXTENTS_FOCUSED_ON_DIMENSIONS", "full_extents": [round(v, 3) for v in bounds],
                            "focus": [round(v, 3) for v in (min_x, min_y, max_x, max_y)]})
    return (min_x - 0.15 * span_x, min_y - 0.15 * span_y, max_x + 0.15 * span_x, max_y + 0.15 * span_y)


def process_dxf(data: bytes, filename: str = "plan.dxf", unit_override: str | None = None) -> dict:
    import tempfile
    import os
    from engines.cad_geometry import resolve_units, walk_entities, inventory, entity_vectors
    from engines.plan_walls import analyze_walls
    diagnostics=[]
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        f.write(data); path=f.name
    try:
        try: doc=ezdxf.readfile(path)
        except (ezdxf.DXFError,UnicodeError):
            doc,auditor=recover_readfile(path)
            diagnostics.append({"code":"DXF_RECOVERED","fixes":len(auditor.fixes),"errors":len(auditor.errors)})
    except Exception as exc:
        raise ValueError(f"DXF invalide ({type(exc).__name__})") from None
    finally: os.unlink(path)
    units=resolve_units(doc,unit_override)
    unit_to_m=units["unit_to_m"]
    entities=list(walk_entities(doc,diagnostics=diagnostics))
    bounds=_focus_bounds(doc,_compute_bounds(entities),diagnostics)
    # Un échec du rendu fidèle est explicite : pas de recalage approximatif silencieux.
    png,mapping=_render_preview_hq(doc,bounds)
    ratio=mapping["scale_px_per_dxf_unit"]
    def to_px(x,y):
        return ((x-mapping["offset_x"])*ratio, mapping["height"]-(y-mapping["offset_y"])*ratio)
    vectors=[]; text_blocks=[]
    for entity in entities:
        vectors.extend(entity_vectors(entity,to_px,max(.0005/unit_to_m,1e-8)))
        kind=entity.dxftype()
        if kind in ("TEXT","MTEXT","ATTRIB","ATTDEF"):
            pos=entity.dxf.insert
            text=entity.plain_text() if kind=="MTEXT" else str(entity.dxf.get("text", ""))
            x,y=to_px(pos.x,pos.y)
            text_blocks.append({"text":text,"x":x,"y":y,"w":0,"h":0,"layer":entity.dxf.layer})
    if len(vectors)>1500000:raise ValueError("Trop de primitives CAO : isoler une zone du plan")
    dims=_extract_dimensions(doc.modelspace(),to_px,unit_to_m,diagnostics)
    if len(vectors)>150000:
        # Plan dense (BET) : cotes natives et inventaire conservés, analyse automatique des murs non tentée (pas de classification hasardeuse).
        from engines.plan_walls import INCOMPLETE_MSG
        walls={"walls":[],"validation":{"complete":False,"failed_checks":[f"plan dense ({len(vectors)} primitives) : analyse des murs non tentée"],"message":INCOMPLETE_MSG}}
    else:
        walls=analyze_walls(vectors,[{**d,"index":i+1} for i,d in enumerate(dims)],text_blocks,ratio/unit_to_m,1,
                            page_size_px=(mapping["width"],mapping["height"]))
    cad=inventory(doc,entities,diagnostics)
    cad["units"]=units
    if diagnostics:
        walls["validation"]["complete"]=False
        walls["validation"]["failed_checks"].append("import CAO avec réserves : consulter les diagnostics")
        from engines.plan_walls import INCOMPLETE_MSG
        walls["validation"]["message"]=INCOMPLETE_MSG
    from engines.dxf_takeoff import extract_structural_metre
    metre=extract_structural_metre(doc,unit_to_m)
    return {"kind":"dxf","page_count":1,"dxf_units":units["name"],"cad_import":cad,"structural_metre":metre,
            "analysis_pdf_b64":base64.b64encode(mapping["pdf_bytes"]).decode("ascii"),"detected_scale_denominator":None,
            "pages":[{"index":0,"width_px":mapping["width"],"height_px":mapping["height"],"dpi":mapping["dpi"],
                      "image_png_b64":base64.b64encode(png).decode("ascii"),"img_mime":"image/png",
                      "vectors":vectors[:8000],"vectors_total":len(vectors),"vectors_truncated":len(vectors)>8000,
                      "geometry_coordinate_space":"image_px","geometry_version":2,"cad_import":cad,
                      "walls_analysis":walls,"text_blocks":text_blocks[:3000],"dimensions_count":len(dims),
                      "dxf_dimensions":dims,"unit_to_m":unit_to_m,"raw_text_length":sum(len(t["text"]) for t in text_blocks),
                      "dxf_bounds":dict(zip(("min_x","min_y","max_x","max_y"),bounds)),"dxf_ratio":ratio}]}


_UNIT_TO_M = {"mm": 0.001, "cm": 0.01, "m": 1.0, "decimeters": 0.1,
              "dekameters": 10.0, "inches": 0.0254, "feet": 0.3048}


def _unit_to_m(doc, bounds=None):
    from engines.cad_geometry import resolve_units
    return resolve_units(doc)["unit_to_m"]


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
