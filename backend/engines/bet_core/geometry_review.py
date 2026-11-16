"""Preserve source geometry when the rectangular BET engine cannot represent the footprint."""
from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient

from . import reader

SHAPE = re.compile(
    r"\b(?:moradia|casa|planta|implantaç[aã]o|maison|emprise|footprint|house)\b"
    r"[^\n.!?]{0,38}?\b(?:em L\b|en L\b|L[- ]shaped\b)"
    r"|\bL[- ]shaped\s+(?:house|footprint|plan)\b", re.I,
)
SCALE = re.compile(r"\b1\s*:\s*(20|25|50|75|100|150|200)\b")
AREA = re.compile(r"\b(\d{2,4}(?:[.,]\d+)?)\s*m[²2]\s*(?:por piso|par niveau|per floor)\b", re.I)
BRIEF_AREA = re.compile(r"\b(?:em L|en L)\b\s*(?:com|de|avec|[·,])?\s*(\d{2,4}(?:[.,]\d+)?)\s*m[²2]", re.I)
DIMENSION = re.compile(r"(?:^|\n)\s*(\d{1,3}[.,]\d{2})\s*m\s*(?=\n|$)")
LEVEL = re.compile(r"(?:^|\n)\s*([+±−-]\d{1,2}[.,]\d{2})\s*(?:m)?\s*(?=\n|$)")


@dataclass
class Floor:
    file_index: int
    page_index: int
    outline: Polygon
    marks: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    interior: tuple[tuple[tuple[float, float], tuple[float, float]], ...]


@dataclass
class Source:
    sheets: list[tuple[int, int, str]]
    floors: list[Floor]
    levels: list[float]
    flat: bool
    source_text: str

    @property
    def floor_matches_3d(self):
        return bool(self.floors and self.levels and self.flat)


def _ring(drawing, factor):
    """Only closed, explicitly filled straight-line paths. Avoid guessing from wall fragments."""
    lines = drawing["items"]
    if drawing.get("fill") is None or not 4 <= len(lines) <= 80 or any(item[0] != "l" for item in lines):
        return None
    for previous, following in zip(lines, lines[1:]):
        if abs(previous[2] - following[1]) > 0.1:
            return None
    if not drawing.get("closePath") and abs(lines[-1][2] - lines[0][1]) > 0.1:
        return None
    points = [item[1] for item in lines] + [lines[-1][2]]
    x0, y0 = min(p.x for p in points), max(p.y for p in points)
    outline = Polygon([(round((p.x - x0) * factor, 3), round((y0 - p.y) * factor, 3)) for p in points])
    if not outline.is_valid or outline.area <= 0:
        return None
    return orient(outline), x0, y0


def _floor(page, text, file_index, page_index):
    scales = set(SCALE.findall(text))
    areas = {float(a.replace(",", ".")) for a in AREA.findall(text)}
    if len(scales) != 1 or len(areas) != 1:
        return None
    factor = 25.4 * int(scales.pop()) / 72000
    area = areas.pop()
    drawing = page.get_drawings()
    matches = []
    for shape in drawing:
        result = _ring(shape, factor)
        if result is None:
            continue
        polygon, x0, y0 = result
        if math.isclose(polygon.area, area, rel_tol=0.015, abs_tol=0.15):
            matches.append((polygon, x0, y0))
    if len(matches) != 1:
        return None
    outline, x0, y0 = matches[0]
    dimensions = [float(d.replace(",", ".")) for d in DIMENSION.findall(text)]
    vertices = list(outline.exterior.coords)
    if not all(any(math.isclose(math.dist(a, b), dim, abs_tol=0.025) for dim in dimensions)
               for a, b in zip(vertices, vertices[1:])):
        return None
    # Colour-coded linear openings on the perimeter. Only reproduce their position
    # in plan. In the massing image their vertical dimensions are schematic.
    opening_lines, interior_lines = [], []
    edge_buffer = outline.boundary.buffer(0.015)
    covered = outline.buffer(0.015)
    for shape in drawing:
        colour = shape.get("color")
        if not colour or shape.get("fill") is not None:
            continue
        is_opening = colour[1] > colour[0] + 0.18 and colour[2] > colour[0] + 0.18
        is_dark_stroke = max(colour) < 0.35 and (shape.get("width") or 0) > 0.6
        if not (is_opening or is_dark_stroke):
            continue
        for item in shape["items"]:
            if item[0] != "l":
                continue
            endpoints = tuple((round((p.x - x0) * factor, 3), round((y0 - p.y) * factor, 3)) for p in item[1:3])
            segment = LineString(endpoints)
            if segment.length <= 0.35:
                continue
            on_edge = edge_buffer.covers(segment)
            if is_opening and on_edge:
                opening_lines.append(endpoints)
            if is_dark_stroke and not on_edge and covered.covers(segment):
                interior_lines.append(endpoints)
    return Floor(file_index, page_index, outline, tuple(dict.fromkeys(opening_lines)),
                 tuple(dict.fromkeys(interior_lines)))


def inspect(docs, hypotheses: str, *, force=False) -> Source | None:
    import pymupdf

    from_brief = SHAPE.search(hypotheses or "")
    mentioned = bool(from_brief)
    irregular = False
    sheets, all_pages, floors, section_text, texts = [], [], [], [], []
    floor_count = 0
    for fi, (_, data) in enumerate(docs):
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            for pi, page in enumerate(pdf):
                all_pages.append((fi, pi, "autre"))
                text = page.get_text()
                kind = reader.classify("\n".join(text.splitlines()[:6]))
                if kind == "autre":
                    kind = reader.classify(text)
                if kind not in {"plan", "coupe", "facade", "masse"}:
                    continue
                sheets.append((fi, pi, kind))
                texts.append(text)
                mentioned |= bool(SHAPE.search(text[:2000]))
                if kind in {"coupe", "facade"}:
                    section_text.append(text)
                if kind == "plan":
                    floor_count += 1
                    exact = _floor(page, text, fi, pi)
                    if exact is not None:
                        floors.append(exact)
                        irregular |= not exact.outline.equals(exact.outline.envelope)
    if not (irregular or mentioned or force):
        return None
    if not sheets:
        sheets = all_pages
    # Align floors only when the same reference outline is demonstrated. Keep the
    # original vector sheets if a change of footprint or its origin is ambiguous.
    aligned = bool(floors) and len(floors) == floor_count and all(
        floor.outline.equals(floors[0].outline) for floor in floors
    )
    # An explicit L-shaped brief and a rectangular extraction are contradictory.
    # Keep the original evidence, without certifying or recreating that outline.
    floors = floors if irregular else []
    if from_brief and floors:
        for floor in floors:
            outline = floor.outline
            recess = outline.envelope.difference(outline)
            x0, y0, x1, y1 = outline.bounds
            a, b, c, d = recess.bounds
            if not (recess.equals(recess.envelope) and (a == x0 or c == x1) and (b == y0 or d == y1)):
                floors = []
                break
        brief_area = BRIEF_AREA.search(hypotheses)
        if floors and aligned and brief_area and not math.isclose(sum(f.outline.area for f in floors),
                                                                 float(brief_area[1].replace(",", ".")), abs_tol=0.15):
            floors = []
    levels = sorted({float(x.replace("±", "").replace("−", "-").replace(",", "."))
                     for text in section_text for x in LEVEL.findall(text)})
    if not aligned or not floors or len(levels) != len(floors) + 1 or not math.isclose(levels[0], 0.0, abs_tol=0.03):
        levels = []
    text = "\n".join(texts)
    flat = bool(re.search(r"\b(?:cobertura plana|toiture[- ]terrasse|flat roof)\b", text, re.I))
    return Source(sheets, floors, levels, flat, text)


def write_originals(source, docs, path):
    writer = PdfWriter()
    readers = {index: PdfReader(io.BytesIO(data)) for index, (_, data) in enumerate(docs)}
    for fi, pi, _ in source.sheets:
        writer.add_page(readers[fi].pages[pi])
    writer.write(path)


def write_dxf(source, path):
    import ezdxf
    from ezdxf import units

    cad = ezdxf.new("R2010", units=units.M)
    model = cad.modelspace()
    for i, floor in enumerate(source.floors, 1):
        outline_layer = f"PISO_{i}_CONTORNO"
        openings_layer = f"PISO_{i}_VAOS"
        interior_layer = f"PISO_{i}_INTERIOR"
        cad.layers.new(outline_layer, dxfattribs={"color": 7})
        cad.layers.new(openings_layer, dxfattribs={"color": 4})
        cad.layers.new(interior_layer, dxfattribs={"color": 8})
        model.add_lwpolyline(list(floor.outline.exterior.coords)[:-1], close=True, dxfattribs={"layer": outline_layer})
        for a, b in floor.marks:
            model.add_line(a, b, dxfattribs={"layer": openings_layer})
        for a, b in floor.interior:
            model.add_line(a, b, dxfattribs={"layer": interior_layer})
    data = io.StringIO()
    cad.write(data)
    checked = ezdxf.read(io.StringIO(data.getvalue()))
    outlines = list(checked.modelspace().query("LWPOLYLINE"))
    if len(outlines) != len(source.floors) or any(
        not entity.closed or not Polygon(entity.get_points("xy")).equals(floor.outline)
        for entity, floor in zip(outlines, source.floors)
    ):
        raise ValueError("DXF does not reproduce the verified contours")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Contornos_e_vaos.dxf", data.getvalue().encode("utf-8"))

def model(source):
    """Match each floor to the source coordinates. No geometry from the text brief."""
    if not source.floor_matches_3d:
        return None
    outline = source.floors[0].outline
    _, _, length, width = outline.bounds
    text = source.source_text.lower()
    return {
        "envelope": {"length_x": length, "width_y": width},
        "levels": [{"id": f"P{i}", "floor_top": z, "ceiling_height": source.levels[i + 1] - z}
                   for i, z in enumerate(source.levels[:-1])],
        "roof": {"type": "plana", "eaves_level": source.levels[-1], "ridge_level": source.levels[-1]},
        "verified_footprint": {
            "vertices": list(outline.exterior.coords)[:-1],
            "openings": [f.marks for f in source.floors],
            "granite": "granito" in text,
            "timber": "madeira" in text,
        },
    }


def horizontal_sections(outline):
    """One section per band defined by the vertices. Keep individual intervals."""
    x0, _, x1, _ = outline.bounds
    ordinates = sorted({y for _, y in outline.exterior.coords})
    for y0, y1 in zip(ordinates, ordinates[1:]):
        y = (y0 + y1) / 2
        intersection = outline.intersection(LineString([(x0 - 1, y), (x1 + 1, y)]))
        parts = list(intersection.geoms) if hasattr(intersection, "geoms") else [intersection]
        yield y, [(line.bounds[0], line.bounds[2]) for line in parts if line.geom_type == "LineString" and line.length > 0]


def write_presentation(source, path, lang, photos=()):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader

    pt = lang == "pt"
    w, h = landscape(A3)
    c = Canvas(str(path), pagesize=(w, h))
    ink, muted, accent = map(HexColor, ("#172923", "#435D54", "#226351"))
    tint = HexColor("#F2F6F2")

    def text(x, y, value, size=12, bold=False, color=ink):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.setFillColor(color)
        c.drawString(x, y, value)

    def header(title, subtitle, number):
        c.setFillColor(tint)
        c.rect(0, h - 129, w, 129, stroke=0, fill=1)
        text(45, h - 36, "CONSTRUPILOT   /   " + ("GEOMETRIA DO PROJETO" if pt else "GÉOMÉTRIE DU PROJET"), 11, True, accent)
        text(45, h - 83, title, 32, True)
        text(45, h - 109, subtitle, 12, color=muted)
        c.setStrokeColor(HexColor("#BED2C8"))
        c.line(45, 52, w - 45, 52)
        text(45, 31, "Verificação geométrica · consulte as plantas de origem para o detalhe construtivo."
             if pt else "Vérification géométrique · consulter les plans sources pour les détails constructifs.", 9, color=muted)
        text(w - 71, 31, f"{number:02d}", 9, True, accent)

    def number(value):
        return f"{value:.2f}".replace(".", ",")

    total = sum(floor.outline.area for floor in source.floors)
    plates = [(f"Piso {i}  /  Contorno cotado" if pt else f"Niveau {i}  /  Emprise cotée", floor, False)
              for i, floor in enumerate(source.floors)]
    if source.levels:
        plates.append(("Fundações  /  Contorno de referência" if pt else "Fondations  /  Contour de référence", source.floors[0], True))
        for i, floor in enumerate(source.floors[:-1], 1):
            title = f"Laje entre pisos {i - 1} e {i}  /  Contorno" if pt else f"Plancher entre niveaux {i - 1} et {i}  /  Contour"
            plates.append((title, floor, True))
    for index, (title, floor, structure_reference) in enumerate(plates, 1):
        subtitle = (f"{number(total)} m² nos pisos verificados" if pt else f"{number(total)} m² sur les niveaux vérifiés")
        if structure_reference:
            subtitle = ("Perímetro de referência. Disposição dos elementos resistentes e armaduras por calcular."
                        if pt else "Contour de référence. Implantation des éléments porteurs et armatures à calculer.")
        header(title, f"{number(floor.outline.area)} m²   ·   {subtitle}", index)
        _, _, length, depth = floor.outline.bounds
        paper_scale = next((s for s in (50, 75, 100, 150, 200, 250, 500)
                            if length * 1000 / s <= 214 and depth * 1000 / s <= 184), 1000)
        factor = 1000 * mm / paper_scale
        ox = 90 + (630 - length * factor) / 2
        oy = 122 + (545 - depth * factor) / 2
        polygon = c.beginPath()
        coordinates = list(floor.outline.exterior.coords)
        for i, (x, y) in enumerate(coordinates):
            (polygon.lineTo if i else polygon.moveTo)(ox + x * factor, oy + y * factor)
        polygon.close()
        c.setStrokeColor(ink)
        c.setFillColor(tint)
        c.setLineWidth(2.2)
        c.drawPath(polygon, stroke=1, fill=1)
        c.setStrokeColor(muted)
        c.setLineWidth(1.1)
        for a, b in (() if structure_reference else floor.interior):
            c.line(ox + a[0] * factor, oy + a[1] * factor, ox + b[0] * factor, oy + b[1] * factor)
        for a, b in zip(coordinates, coordinates[1:]):
            x, y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            edge = math.dist(a, b)
            dx, dy = (b[1] - a[1]) / edge, (a[0] - b[0]) / edge
            c.saveState()
            c.translate(ox + x * factor + dx * 16, oy + y * factor + dy * 16)
            if abs(dx) > 0.5:
                c.rotate(90)
            c.setFont("Helvetica", 10)
            c.setFillColor(muted)
            c.drawCentredString(0, -3, f"{number(edge)} m")
            c.restoreState()
        for a, b in (() if structure_reference else floor.marks):
            c.setStrokeColor(HexColor("#378F8C"))
            c.setLineWidth(3.2)
            c.line(ox + a[0] * factor, oy + a[1] * factor, ox + b[0] * factor, oy + b[1] * factor)
        c.setStrokeColor(HexColor("#BED2C8"))
        c.line(770, 157, 770, h - 183)
        x = 817
        text(x, h - 213, "ÁREA BRUTA" if pt else "SURFACE BRUTE", 11, True, accent)
        text(x, h - 256, f"{number(floor.outline.area)} m²", 31, True)
        text(x, h - 298, f"{number(length)} × {number(depth)} m", 17, True)
        text(x, h - 325, f"1:{paper_scale} · A3", 12, color=muted)
        text(x, h - 384, "VÉRTICES DO CONTORNO (m)" if pt else "SOMMETS DU CONTOUR (m)", 10, True, accent)
        for n, (xv, yv) in enumerate(coordinates[:-1]):
            row, column = divmod(n, 9)
            if row >= 3:
                break
            text(x + row * 111, h - 411 - column * 18, f"{n + 1:02d}   {number(xv)} / {number(yv)}", 9, color=muted)
        c.showPage()
    sections = list(horizontal_sections(source.floors[0].outline)) if source.levels else []
    if sections:
        header("Cortes  /  Larguras verificadas" if pt else "Coupes  /  Largeurs vérifiées",
               "Interseções com o contorno de origem. Cotas verticais da planta de corte."
               if pt else "Intersections du contour source. Altimétrie issue de la coupe d'origine.", len(plates) + 1)
        _, _, length, _ = source.floors[0].outline.bounds
        top = source.levels[-1]
        factor = min(1000 * mm / 100, 400 / length, 164 / top)
        for i, (y, spans) in enumerate(sections[:4]):
            row, col = divmod(i, 2)
            x, z = 85 + col * 550, h - 436 - row * 268
            text(x, z + factor * top + 25, f"{'Corte' if pt else 'Coupe'} {chr(65 + i)}–{chr(65 + i)}   ·   Y = {number(y)} m", 15, True)
            for a, b in spans:
                c.setStrokeColor(ink)
                for j, (low, high) in enumerate(zip(source.levels, source.levels[1:])):
                    c.setFillColor(HexColor("#EBE3D7") if j else tint)
                    c.rect(x + a * factor, z + low * factor, (b - a) * factor, (high - low) * factor, stroke=1, fill=1)
                text(x + a * factor + 7, z - 22, f"{number(b-a)} m", 12, True)
            for level in source.levels:
                text(x + length * factor + 13, z + level * factor - 4, f"+{number(level)}", 10, color=muted)
        c.showPage()
    for index, (label, photo) in enumerate(photos, len(plates) + 1 + bool(sections)):
        header(label, ("Volumetria a partir do contorno e das cotas de nível da planta. Altura dos vãos ilustrativa."
                       if pt else "Volume issu du contour et des niveaux du plan. Hauteurs des baies illustratives."), index)
        image = ImageReader(str(photo))
        iw, ih = image.getSize()
        k = min((w - 90) / iw, (h - 213) / ih)
        c.drawImage(image, (w - iw * k) / 2, 67 + (h - 226 - ih * k) / 2, iw * k, ih * k)
        c.showPage()
    c.save()
