from __future__ import annotations

import io
import math
import zipfile

import ezdxf
import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from engines.bet_core import geometry_review as geometry
from engines import house_pbr


EXPECTED = [(0, 0), (6, 0), (6, 5), (12, 5), (12, 10), (0, 10)]


def make_pdf(vertices=EXPECTED, bad_dimension=False):
    buf = io.BytesIO()
    pdf = Canvas(buf, pagesize=landscape(A3))
    scale = 10 * mm
    area = Polygon(vertices).area
    for title in ("Planta do piso térreo", "Planta do primeiro piso"):
        pdf.drawString(40, 780, title)
        pdf.drawString(40, 754, f"{area:.0f} m² por piso")
        path = pdf.beginPath()
        for i, (x, y) in enumerate(vertices):
            (path.lineTo if i else path.moveTo)(80 + x * scale, 120 + y * scale)
        path.close()
        pdf.setFillColorRGB(.91, .94, .92)
        pdf.drawPath(path, stroke=1, fill=1)
        pdf.setStrokeColorRGB(.31, .65, .65)
        pdf.line(80 + scale, 120, 80 + 3 * scale, 120)
        pdf.setFillColorRGB(0, 0, 0)
        for i, label in enumerate(("1:100", "12,00 m", "10,00 m", "6,00 m",
                                   "4,00 m" if bad_dimension else "5,00 m")):
            pdf.drawString(42, 550 - i * 18, label)
        pdf.showPage()
    pdf.drawString(40, 780, "Corte A-A e alçado sul")
    pdf.drawString(40, 754, "Cobertura plana, granito e madeira")
    for i, label in enumerate(("±0,00", "+3,00", "+6,40")):
        pdf.drawString(42, 550 - i * 18, label)
    pdf.showPage()
    pdf.save()
    return [("plantas.pdf", buf.getvalue())]


def test_source_pdf_cad_and_mesh_share_every_vertex(tmp_path):
    docs = make_pdf()
    raw_source = geometry.inspect(docs, "Moradia contemporânea em L, 180 m²")
    reference = Polygon(EXPECTED)
    assert raw_source is not None
    assert len(raw_source.floors) == 2
    assert sum(f.outline.area for f in raw_source.floors) == 180
    assert all(f.outline.equals(reference) for f in raw_source.floors)
    assert raw_source.levels == [0, 3, 6.40]

    originals = tmp_path / "originals.pdf"
    geometry.write_originals(raw_source, docs, originals)
    copied = PdfReader(originals)
    supplied = PdfReader(io.BytesIO(docs[0][1]))
    assert len(copied.pages) == 3
    assert [p.get_contents().get_data() for p in copied.pages] == [p.get_contents().get_data() for p in supplied.pages]
    sheets = tmp_path / "geometria.pdf"
    geometry.write_presentation(raw_source, sheets, "pt")
    plates = PdfReader(sheets).pages
    assert len(plates) == 5
    foundation = plates[2].extract_text()
    assert "Fundações" in foundation and "90,00 m²" in foundation and "por calcular" in foundation
    slab = plates[3].extract_text()
    assert "Laje entre pisos 0 e 1" in slab and "90,00 m²" in slab and "por calcular" in slab
    assert list(geometry.horizontal_sections(reference)) == [(2.5, [(0, 6)]), (7.5, [(0, 12)])]
    assert "6,00 m" in plates[4].extract_text() and "12,00 m" in plates[4].extract_text()

    cad = tmp_path / "cad.zip"
    geometry.write_dxf(raw_source, cad)
    with zipfile.ZipFile(cad) as archive:
        drawing = ezdxf.read(io.StringIO(archive.read("Contornos_e_vaos.dxf").decode()))
    outline_entities = list(drawing.modelspace().query("LWPOLYLINE"))
    assert len(outline_entities) == 2
    for e in outline_entities:
        points = list(e.get_points("xy"))
        assert e.closed and len(points) == 6
        assert Polygon(points).equals(reference)

    model = geometry.model(raw_source)
    parts = house_pbr._parts(model)
    canopy = unary_union([Polygon([(x, y) for x, y, _ in face]) for face in parts["flat"]])
    assert canopy.equals(reference)
    assert not canopy.covers(Point(9, 2))
    assert all(Polygon([(x, y) for x, y, _ in face]).exterior.is_ccw for face in parts["flat"])
    assert math.isclose(max(z for f in parts["parapet"] for _, _, z in f), 6.4)
    assert parts["granite"] and parts["timber"] and parts["glass"]


def test_wrong_recess_dimension_keeps_all_original_sheets_and_yields_no_derived_geometry():
    source = geometry.inspect(make_pdf(bad_dimension=True), "Cria uma moradia em L")
    assert len(source.sheets) == 3
    assert not source.floors
    assert geometry.model(source) is None


def test_rectangular_study_keeps_existing_workflow():
    rectangle = [(0, 0), (12, 0), (12, 10), (0, 10)]
    assert geometry.inspect(make_pdf(rectangle), "Moradia de dois pisos") is None
    contradictory = geometry.inspect(make_pdf(rectangle), "Moradia em L")
    assert not contradictory.floors


def test_stated_total_must_match_the_sum_of_storeys():
    source = geometry.inspect(make_pdf(), "Moradia em L de 200 m²")
    assert len(source.sheets) == 3
    assert not source.floors
