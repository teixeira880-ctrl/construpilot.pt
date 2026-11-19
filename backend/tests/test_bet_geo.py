"""Motor de geometria real (bet_geo): formas quaisquer, leitura vetorial, cotas, estudo completo.

Sem rede nem IA real: plantas PDF sintéticas geradas no teste e IA simulada.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from pathlib import Path

import pytest
from shapely.affinity import rotate
from shapely.geometry import LineString, Point, Polygon, box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.bet_geo import levels_ai, pdf_vector, run, structure  # noqa: E402
from engines.bet_geo.model import Building, Wall  # noqa: E402

L_SHAPE = Polygon([(0, 0), (14, 0), (14, 6), (6, 6), (6, 12), (0, 12)])


def _walls_of(poly, t=0.23):
    cs = list(poly.exterior.coords)
    ws = [Wall(cs[i], cs[i + 1], t, exterior=True) for i in range(len(cs) - 1)]
    return ws


def _invariants(b: Building, R):
    # 1) nada da laje fica por calcular: soma dos painéis = área da laje
    assert sum(p["area"] for p in R.panels) == pytest.approx(b.roof_slab.area, rel=0.01)
    # 2) equilíbrio: cada extremo de viga apoia num pilar (≤ 0,9 m) ou a meio de outra viga
    for v in R.beams:
        for end in (Point(v["geom"].coords[0]), Point(v["geom"].coords[-1])):
            near_col = any(math.hypot(c["x"] - end.x, c["y"] - end.y) <= 0.9 for c in R.columns)
            on_beam = any(o is not v and o["geom"].distance(end) < 0.03 for o in R.beams)
            assert near_col or on_beam, f"{v['id']} sem apoio em {end}"
    # 3) uma sapata por pilar, tensão de serviço ≤ admissível
    assert len(R.footings) == len(R.columns)
    assert all(f["sigma_sls"] <= structure.DEFAULTS["sigma_adm_kPa"] * 1.11 for f in R.footings)
    # 4) quantidades positivas e confrontações calculadas
    assert all(q["qtd"] >= 0 for q in R.quantities) and len(R.checks) == 4


def test_casa_em_L():
    b = Building(footprint=L_SHAPE, walls=_walls_of(L_SHAPE) + [Wall((6, 0), (6, 6), 0.20)])
    R = structure.design(b)
    _invariants(b, R)
    assert 0.18 <= R.slab["h"] <= 0.26
    # o canto reentrante (6;6) tem pilar
    assert any(math.hypot(c["x"] - 6, c["y"] - 6) < 0.9 for c in R.columns)


def test_casa_em_U_rodada_com_patio_e_pala():
    u = Polygon([(0, 0), (18, 0), (18, 12), (12, 12), (12, 5), (6, 5), (6, 12), (0, 12)])
    patio = box(13.5, 1.5, 16.5, 3.5)
    fp = rotate(Polygon(u.exterior, [patio.exterior]), 30, origin=(0, 0))
    pala = rotate(box(0, -1.0, 18, 0), 30, origin=(0, 0))
    b = Building(footprint=fp, covered=[pala], walls=_walls_of(fp))
    R = structure.design(b)
    _invariants(b, R)
    assert any(p["tipo"] == "consola" for p in R.panels)          # pala de 1 m = consola, sem pilares
    # vigas seguem as direções rodadas (30° / 120°), nenhuma em diagonal arbitrária
    for v in R.beams:
        (x0, y0), (x1, y1) = v["geom"].coords[0], v["geom"].coords[-1]
        a = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 90
        assert abs(a - 30) < 2, f"{v['id']} a {a:.1f}°"


def test_pilares_nunca_a_meio_de_envidracado():
    rect = box(0, 0, 16, 5)
    walls = [Wall((0, 0), (0, 5), 0.25, exterior=True), Wall((16, 0), (16, 5), 0.25, exterior=True),
             Wall((0, 5), (16, 5), 0.25, exterior=True), Wall((0, 0), (3, 0), 0.25, exterior=True),
             Wall((13, 0), (16, 0), 0.25, exterior=True)]                 # fachada sul envidraçada de 3 a 13 m
    R = structure.design(Building(footprint=rect, walls=walls))
    on_glass = [c for c in R.columns if abs(c["y"]) < 0.05 and 3.3 < c["x"] < 12.7]
    assert not on_glass
    assert any("platibanda" in w or "sem parede" in w for w in R.warnings)


def test_muro_de_suporte():
    b = Building(footprint=L_SHAPE, walls=_walls_of(L_SHAPE))
    b.walls.append(Wall((0, 12), (6, 12), 0.30, "betao", True, 2.5))
    R = structure.design(b)
    assert R.retaining and R.retaining[0]["t"] >= 0.25 and R.retaining[0]["H_terras"] == 2.5


def test_levels_apply_valida_resposta_da_ia():
    b = Building(footprint=L_SHAPE)
    warns = levels_ai.apply(b, {"floor_level": 100.0, "roof_slab_top_level": 103.2, "storeys": 1,
                                "declared_construction_area_m2": 120.0,
                                "retaining": [{"edge": "E1", "retained_height_m": 1.5},
                                              {"edge": "E99", "retained_height_m": 2},
                                              {"edge": "E2", "retained_height_m": 40}]})
    assert b.storey_height == pytest.approx(3.2)
    assert len([w for w in b.walls if w.retained_height > 0]) == 1       # E99 e 40 m rejeitados
    assert len(warns) == 2
    assert any(c.get("ok") is True for c in b.checks)                    # 120 m² declarados = 120 m² lidos
    b2 = Building(footprint=L_SHAPE)
    assert levels_ai.apply(b2, {"floor_level": 1, "roof_slab_top_level": 50})    # pé-direito absurdo → aviso
    assert b2.storey_height == pytest.approx(3.3)


# ----------------------------------------------------------------------------- PDF sintético
def _synthetic_plan_pdf(path: Path, poly: Polygon, walls: list[tuple], scale=100):
    """Planta vetorial à moda CAD: linha de área tracejada a azul + paredes com tracejado a 45°."""
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.pdfgen import canvas

    k = 72 / 0.0254 / scale
    W, H = landscape(A3)
    ox, oy = 100, 100
    c = canvas.Canvas(str(path), pagesize=(W, H))
    c.setFont("Helvetica", 14)
    c.drawString(W - 300, 60, "PLANTA DE PISO 1")
    c.drawString(W - 300, 40, "ESCALA 1:100")
    c.setFillColorRGB(0.0, 0.32, 0.65)
    ring = poly.exterior
    L = ring.length
    s = 0.0
    while s < L:
        a = ring.interpolate(s)
        b = ring.interpolate(min(s + 0.20, L))
        x0, x1 = sorted((a.x, b.x))
        y0, y1 = sorted((a.y, b.y))
        c.rect(ox + x0 * k - 0.4, oy + y0 * k - 0.4, (x1 - x0) * k + 0.8, (y1 - y0) * k + 0.8, stroke=0, fill=1)
        s += 0.32
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.2)
    for (a, b, t) in walls:
        band = LineString([a, b]).buffer(t / 2, cap_style=2)
        x0, y0, x1, y1 = band.bounds
        d = 0.0
        while d < (x1 - x0) + (y1 - y0):
            ln = LineString([(x0 + d, y0), (x0 + d - (y1 - y0) - 1, y1 + 1)]).intersection(band)
            if not ln.is_empty and ln.geom_type == "LineString":
                (p, q) = ln.coords[0], ln.coords[-1]
                c.line(ox + p[0] * k, oy + p[1] * k, ox + q[0] * k, oy + q[1] * k)
            d += 0.06
    c.showPage()
    c.save()
    return path


@pytest.fixture()
def l_pdf(tmp_path):
    walls = [((0.1, 0.1), (13.9, 0.1), 0.2), ((13.9, 0.1), (13.9, 5.9), 0.2), ((13.9, 5.9), (6.1, 5.9), 0.2),
             ((6.1, 5.9), (6.1, 11.9), 0.2), ((6.1, 11.9), (0.1, 11.9), 0.2), ((0.1, 11.9), (0.1, 0.1), 0.2),
             ((6.1, 0.1), (6.1, 5.9), 0.15)]
    return _synthetic_plan_pdf(tmp_path / "planta.pdf", L_SHAPE, walls).read_bytes()


def test_leitura_vetorial_de_planta_em_L(l_pdf):
    b = pdf_vector.read([("planta.pdf", l_pdf)])
    assert b is not None
    assert b.footprint.area == pytest.approx(L_SHAPE.area, rel=0.02)
    assert not b.footprint.equals(b.footprint.envelope)                  # forma real, não o retângulo envolvente
    assert sum(w.length for w in b.walls) > 30


def test_estudo_completo_com_ia_simulada(l_pdf, tmp_path):
    async def fake_llm(system, text, images=None, max_tokens=0, **k):
        return json.dumps({"floor_level": 0.0, "roof_slab_top_level": 3.2, "storeys": 1,
                           "declared_construction_area_m2": 120, "retaining": []})

    res = asyncio.run(run.study([("planta.pdf", l_pdf)], "Moradia em Évora", "PT", tmp_path / "out", llm=fake_llm))
    assert res["ok"] and res["checks_ok"] in (True, False)
    kinds = [k for k, _, _ in res["files"]]
    for k in ("pdf", "plans_pdf", "re2020_pdf", "xlsx", "zip", "render_png"):
        assert k in kinds, k
    names = [p.name for _, p, _ in res["files"]]
    for n in ("Processo_de_estudo.pdf", "Desenhos_de_execucao.pdf", "Estudo_termico_REH.pdf", "Analise_custo_beneficio.pdf",
              "Especialidades_nota_de_calculo.pdf", "Medicoes_e_orcamento.xlsx"):
        assert n in names, n
    assert all(p.stat().st_size > 1000 for _, p, _ in res["files"])
    assert res["summary"]["pilares"] >= 6 and res["summary"]["aco_kg"] > 0
    assert res["summary"]["classe"] and res["summary"]["total_ht"] > 50000
    assert not any("falhou" in s for s in res["sheets"])
    import pymupdf
    assert pymupdf.open(str(tmp_path / "out" / "Desenhos_de_execucao.pdf")).page_count >= 14     # capa + 13 folhas


def test_sem_planta_vetorial_devolve_none():
    from reportlab.pdfgen import canvas
    import io

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 100, "Memória descritiva")
    c.showPage()
    c.save()
    assert pdf_vector.read([("mem.pdf", buf.getvalue())]) is None


def test_gancho_do_estudo_bet_entrega_artefactos(l_pdf, monkeypatch):
    """geo_first: estudo completo entregue e passo final 'done'; BET_GEO_ENGINE=0 desliga."""
    steps, stored = [], []

    async def step(label, **extra):
        steps.append((label, extra))

    async def store(db, uid, cid, rid, kind, path, title):
        stored.append((kind, path.stat().st_size, title))
        return {"kind": kind, "title": title}

    async def fake_llm(system, text, images=None, max_tokens=0, **k):
        return "{}"                       # IA sem resposta útil: estudo segue com hipóteses por defeito

    ok = asyncio.run(run.geo_first(None, "job1", "u", "c", "r", [("p.pdf", l_pdf)], "", "PT", step, store, fake_llm))
    kinds = [k for k, _, _ in stored]
    assert ok and {"pdf", "plans_pdf", "re2020_pdf", "xlsx", "zip"} <= set(kinds)
    final = steps[-1][1]
    assert final["status"] == "done" and final["geometry_verified"] is True and final["execution_verified"] is False
    assert any("por defeito" in p for p in final["points"])               # aviso: cotas por defeito

    monkeypatch.setenv("BET_GEO_ENGINE", "0")
    assert asyncio.run(run.geo_first(None, "j", "u", "c", "r", [("p.pdf", l_pdf)], "", "PT", step, store, fake_llm)) is False


# ============================================================================= todos os formatos
def _scan_of(pdf_bytes: bytes, dpi=150) -> bytes:
    """Digitalização simulada: só imagem, sem texto nem vetores, mesmo formato de papel."""
    import pymupdf
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")[0]
    pix = src.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    out = pymupdf.open()
    pg = out.new_page(width=src.rect.width, height=src.rect.height)
    pg.insert_image(pg.rect, stream=pix.tobytes("png"))
    return out.tobytes()


def _l_layout(page_w_pt, page_h_pt, noise=4.0, transform=None):
    """Resposta simulada da IA de visão (coordenadas 0–1000, com erro de leitura)."""
    import random
    random.seed(3)
    k = 72 / 0.0254 / 100
    ox, oy = 100, 100
    def n(x, y):
        X, Y = ox + x * k, page_h_pt - (oy + y * k)
        if transform:
            X, Y = transform(X, Y)
        return [X / page_w_pt * 1000 + random.uniform(-noise, noise), Y / page_h_pt * 1000 + random.uniform(-noise, noise)]
    outer = [(0, 0), (14, 0), (14, 6), (6, 6), (6, 12), (0, 12)]
    return {"is_floor_plan": True, "scale": "1:100", "outline": [n(x, y) for x, y in outer], "courtyards": [],
            "covered_outside": [], "declared_area_m2": 120,
            "overall_dims": [{"value_m": 14.0, "from": n(0, -1), "to": n(14, -1)},
                             {"value_m": 12.0, "from": n(-1, 0), "to": n(-1, 12)}]}


def test_planta_digitalizada(l_pdf):
    from reportlab.lib.pagesizes import A3, landscape
    from engines.bet_geo import raster
    W, H = landscape(A3)
    scan = _scan_of(l_pdf)
    b = asyncio.run(raster.read(scan, layout=_l_layout(W, H)))
    assert b is not None
    assert b.footprint.area == pytest.approx(120, rel=0.04)
    assert all(c.get("ok") is not False for c in b.checks), b.checks
    R = structure.design(b)
    _invariants(b, R)


def test_fotografia_torta_com_sombra(l_pdf):
    """Fotografia: sem tamanho de papel (escala pelas cotas), rodada 1,5°, reduzida, JPEG, sombra."""
    import cv2
    import numpy as np
    from reportlab.lib.pagesizes import A3, landscape
    from engines.bet_geo import raster
    W, H = landscape(A3)
    img, _ = raster.load_gray(_scan_of(l_pdf, dpi=150))
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 1.5, 0.85)
    ph = cv2.warpAffine(img, M, (w, h), borderValue=255)
    ph = np.clip(ph.astype(np.float32) - np.tile(np.linspace(0, 50, w), (h, 1)), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", ph, [cv2.IMWRITE_JPEG_QUALITY, 85])

    def tr(X, Y):
        px, py = X / W * w, Y / H * h
        return ((M[0, 0] * px + M[0, 1] * py + M[0, 2]) / w * W, (M[1, 0] * px + M[1, 1] * py + M[1, 2]) / h * H)
    lay = _l_layout(W, H, transform=tr)
    lay["scale"] = None
    b = asyncio.run(raster.read(buf.tobytes(), layout=lay))
    assert b is not None and any("cota" in c["metodo"] for c in b.checks if c["item"] == "escala")
    assert b.footprint.area == pytest.approx(120, rel=0.05)


def _l_dxf() -> bytes:
    import ezdxf, io
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    pts = [(0, 0), (14, 0), (14, 6), (6, 6), (6, 12), (0, 12)]
    walls = [(pts[i], pts[(i + 1) % 6], 0.25) for i in range(6)] + [((6, 0), (6, 6), 0.15)]
    for a, b_, t in walls:
        band = LineString([a, b_]).buffer(t / 2, cap_style=3 if t > 0.2 else 2)
        ring = [(x * 1000, y * 1000) for x, y in band.exterior.coords]
        msp.add_lwpolyline(ring, close=True)
        h = msp.add_hatch()
        h.set_pattern_fill("ANSI31", scale=12)
        h.paths.add_polyline_path(ring, is_closed=True)
    msp.add_text("SALA 44,80 m2", dxfattribs={"height": 250, "insert": (2000, 3000)})
    s = io.StringIO()
    doc.write(s)
    return s.getvalue().encode()


def test_dxf_escala_exata_sem_ia():
    from engines.bet_geo import cad
    b = asyncio.run(cad.read_dxf(_l_dxf(), llm=None, name="casa.dxf"))
    assert b is not None
    exp = Polygon([(-.125, -.125), (14.125, -.125), (14.125, 6.125), (6.125, 6.125), (6.125, 12.125), (-.125, 12.125)]).area
    assert b.footprint.area == pytest.approx(exp, rel=0.01)
    assert any(not w.exterior for w in b.walls)                          # parede interior reconhecida
    R = structure.design(b)
    _invariants(b, R)
    assert all(c["ok"] for c in R.checks)


def _l_ifc() -> bytes | None:
    try:
        import ifcopenshell
        import numpy as np
        from ifcopenshell.api import aggregate, context, geometry, material, pset, root, spatial, unit
    except Exception:  # noqa: BLE001
        return None
    f = ifcopenshell.file(schema="IFC4")
    proj = root.create_entity(f, ifc_class="IfcProject", name="Casa L")
    unit.assign_unit(f)
    ctx = context.add_context(f, context_type="Model")
    body = context.add_context(f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site, bld = root.create_entity(f, ifc_class="IfcSite"), root.create_entity(f, ifc_class="IfcBuilding")
    st = root.create_entity(f, ifc_class="IfcBuildingStorey")
    aggregate.assign_object(f, relating_object=proj, products=[site])
    aggregate.assign_object(f, relating_object=site, products=[bld])
    aggregate.assign_object(f, relating_object=bld, products=[st])
    conc = material.add_material(f, name="Betão C30/37")

    def wall(x0, y0, x1, y1, t, ext=True):
        w = root.create_entity(f, ifc_class="IfcWall")
        L, ang = float(np.hypot(x1 - x0, y1 - y0)), np.arctan2(y1 - y0, x1 - x0)
        M = np.eye(4)
        M[:2, :2] = [[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]]
        M[0, 3], M[1, 3] = x0 + np.sin(ang) * t / 2, y0 - np.cos(ang) * t / 2
        geometry.assign_representation(f, product=w, representation=geometry.add_wall_representation(
            f, context=body, length=L, height=3.3, thickness=t))
        geometry.edit_object_placement(f, product=w, matrix=M)
        spatial.assign_container(f, relating_structure=st, products=[w])
        material.assign_material(f, products=[w], material=conc)
        ps = pset.add_pset(f, product=w, name="Pset_WallCommon")
        pset.edit_pset(f, pset=ps, properties={"IsExternal": ext})
    pts = [(0, 0), (14, 0), (14, 6), (6, 6), (6, 12), (0, 12)]
    for i in range(6):
        wall(*pts[i], *pts[(i + 1) % 6], 0.25)
    wall(6, 0, 6, 6, 0.15, ext=False)
    s = root.create_entity(f, ifc_class="IfcSlab")
    geometry.assign_representation(f, product=s, representation=geometry.add_slab_representation(
        f, context=body, depth=0.22, polyline=[(-.125, -1.125), (14.125, -1.125), (14.125, 6.125), (6.125, 6.125),
                                                 (6.125, 12.125), (-.125, 12.125)]))
    M = np.eye(4)
    M[2, 3] = 3.3
    geometry.edit_object_placement(f, product=s, matrix=M)
    spatial.assign_container(f, relating_structure=st, products=[s])
    return f.to_string().encode()


def test_ifc_exato():
    from engines.bet_geo import cad
    data = _l_ifc()
    if data is None:
        pytest.skip("ifcopenshell.api indisponível")
    b = cad.read_ifc(data, name="casa.ifc")
    assert b is not None
    assert b.footprint.area == pytest.approx(126.56, rel=0.005)
    assert b.covered and sum(c.area for c in b.covered) == pytest.approx(14.25, rel=0.05)    # pala de 1 m
    assert b.roof_level == pytest.approx(3.52, abs=0.02)
    assert all(w.material == "betao" for w in b.walls)
    assert any(not w.exterior for w in b.walls)
    R = structure.design(b)
    _invariants(b, R)


def test_entrada_do_estudo_aceita_imagem_e_ifc(l_pdf):
    """read_any: o original agarrado ao documento é lido pelo leitor certo."""
    from engines.bet_geo import sources
    data = _l_ifc()
    if data is None:
        pytest.skip("ifcopenshell.api indisponível")
    doc = sources.make("casa.ifc", sources.ifc_preview_pdf(data), data, "ifc")
    name, pdf = doc                                                     # compatível com (nome, pdf)
    assert pdf.startswith(b"%PDF") and doc.kind == "ifc"
    b = asyncio.run(run.read_any([doc], "", "PT", None))
    assert b is not None and b.hypotheses.get("_reader") == "ifc"
    # imagem: convertida em PDF para o resto do estudo, original guardado
    import cv2
    from engines.bet_geo import raster
    img, _ = raster.load_gray(_scan_of(l_pdf))
    ok, png = cv2.imencode(".png", img)
    assert sources.kind_of("planta.png", png.tobytes()) == "image"
    assert sources.image_to_pdf(png.tobytes()).startswith(b"%PDF")
    assert len(sources.dedupe([doc, doc])) == 1 and sources.dedupe([doc, doc])[0].kind == "ifc"
