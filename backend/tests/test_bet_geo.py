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

    res = asyncio.run(run.study([("planta.pdf", l_pdf)], "", "PT", tmp_path / "out", llm=fake_llm))
    assert res["ok"] and res["checks_ok"] in (True, False)
    kinds = [k for k, _, _ in res["files"]]
    assert kinds == ["pdf", "plans_pdf", "xlsx", "zip"]
    assert all(p.stat().st_size > 1000 for _, p, _ in res["files"])
    assert res["summary"]["pilares"] >= 6 and res["summary"]["aco_kg"] > 0


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
    """geo_first: estudo entregue com 4 ficheiros e passo final 'done'; BET_GEO_ENGINE=0 desliga."""
    steps, stored = [], []

    async def step(label, **extra):
        steps.append((label, extra))

    async def store(db, uid, cid, rid, kind, path, title):
        stored.append((kind, path.stat().st_size, title))
        return {"kind": kind, "title": title}

    async def fake_llm(system, text, images=None, max_tokens=0, **k):
        return "{}"                       # IA sem resposta útil: estudo segue com hipóteses por defeito

    ok = asyncio.run(run.geo_first(None, "job1", "u", "c", "r", [("p.pdf", l_pdf)], "", "PT", step, store, fake_llm))
    assert ok and [k for k, _, _ in stored] == ["pdf", "plans_pdf", "xlsx", "zip"]
    final = steps[-1][1]
    assert final["status"] == "done" and final["geometry_verified"] is True and final["execution_verified"] is False
    assert any("por defeito" in p for p in final["points"])               # aviso: cotas por defeito

    monkeypatch.setenv("BET_GEO_ENGINE", "0")
    assert asyncio.run(run.geo_first(None, "j", "u", "c", "r", [("p.pdf", l_pdf)], "", "PT", step, store, fake_llm)) is False
