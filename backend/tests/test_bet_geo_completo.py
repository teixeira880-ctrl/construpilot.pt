"""Estudo completo sobre geometria real: divisões, mapa de vãos, REH + custo-benefício, especialidades, desenhos, orçamento."""
import asyncio

import pytest
from shapely.geometry import Polygon

from engines.bet_geo import costs, covers, drawings, especialidades as E, rooms, structure
from engines.bet_geo.model import Building, Wall

L_SHAPE = Polygon([(0, 0), (14, 0), (14, 6), (6, 6), (6, 12), (0, 12)])
SCHEDULE = """1.Hall de entrada - 8,00m²
2.Sala Comum - 34,00m²
3.Cozinha - 12,50m²
4.Quarto - 14,00m²
5.Inst. San. - 5,20m²
6.Garagem - 18,00m²
PV3- Flutuante carvalho - 142.80 M2
Tinta plástica RAL 1013 36,5m²"""
WINDOW = "DESIGNAÇÃO\nVe 1\nQUANTIDADES\n02\nDIMENSÃO\n290x 180 cm\nLOCALIZAÇÃO\n2. Sala Comum\nVÃOS EXTERIORES - Ve 1"
WINDOW2 = "DESIGNAÇÃO\nVe 2\nQUANTIDADES\n01\nDIMENSÃO\n290x 120 cm\nLOCALIZAÇÃO\n4. Quarto\nVÃOS EXTERIORES - Ve 2"


def _walls(poly, t=0.2):
    cs = list(poly.exterior.coords)
    return [Wall(a, b, t, exterior=True) for a, b in zip(cs, cs[1:])]


def _building():
    w = _walls(L_SHAPE)
    # janelas: troços sem parede na fachada sul e nascente
    w = [x for x in w if not (x.a == (0, 0) and x.b == (14, 0))] + [Wall((0, 0), (5, 0), 0.2, exterior=True), Wall((8, 0), (14, 0), 0.2, exterior=True)]
    w += [Wall((6, 0), (6, 6), 0.15), Wall((0, 6), (6, 6), 0.15)]
    return Building(footprint=L_SHAPE, walls=w, roof_level=3.2)


def _pdf(texts):
    import io
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for t in texts:
        y = 800
        for ln in t.split("\n"):
            c.drawString(40, y, ln)
            y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()


def _layout(b, placed=True):
    docs = [("areas.pdf", _pdf([SCHEDULE, WINDOW, WINDOW2]))]
    pos = {"Hall de entrada": (8, 3), "Sala Comum": (3, 3), "Cozinha": (11, 3), "Quarto": (3, 9), "Inst. San.": (4.5, 7), "Garagem": (12.5, 4.5)}

    async def llm(system, prompt, images=None, max_tokens=0):
        png, _ = rooms.plan_png(b)
        x0, y0, x1, y1 = b.footprint.bounds
        pad = 0.06 * max(x1 - x0, y1 - y0)
        X0, Y0, X1, Y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        import json
        return json.dumps({"rooms": [{"name": n, "area_m2": None, "x": (x - X0) / (X1 - X0) * 1000, "y": (Y1 - y) / (Y1 - Y0) * 1000}
                                     for n, (x, y) in pos.items()]})
    return asyncio.run(rooms.read_layout(b, docs, llm if placed else None)), docs


def test_quadro_de_areas_e_mapa_de_vaos():
    rs = rooms.schedule_from_text([SCHEDULE])
    assert [r.name for r in rs] == ["Hall de entrada", "Sala Comum", "Cozinha", "Quarto", "Inst. San", "Garagem"]   # sem «Tinta…» nem «PV3»
    assert [r.type for r in rs] == ["corredor", "sala", "cozinha", "quarto", "casa_de_banho", "garagem"]
    ws = rooms.windows_from_text([WINDOW, WINDOW2])
    assert ws[0].w == pytest.approx(1.8) and ws[0].h == pytest.approx(2.9) and ws[0].qty == 2 and ws[0].area == pytest.approx(10.44)


def test_divisoes_localizadas_e_garagem_nao_aquecida():
    b = _building()
    lay, _ = _layout(b)
    assert all(r.placed for r in lay.rooms)
    assert lay.useful_area == pytest.approx(8 + 34 + 12.5 + 14 + 5.2)
    sala = next(r for r in lay.rooms if r.name == "Sala Comum")
    assert sala.zone is not None and sala.zone.within(b.footprint.buffer(0.01))
    assert next(w for w in lay.windows if w.name == "Ve 1").orient == "S"     # a sala está a sul, vão na fachada sul


def test_posicao_fora_do_edificio_passa_a_exterior():
    b = _building()
    known = rooms.schedule_from_text([SCHEDULE])
    notes = []
    placed = [rooms.Room("Garagem", 0, "garagem", x=30.0, y=30.0, source="ia")]
    out = rooms._merge(known, placed, b.footprint, notes)
    assert next(r for r in out if r.name == "Garagem").type == "exterior" and notes


def test_reh_custo_beneficio_escolhe_solucao_que_cumpre():
    b = _building()
    lay, docs = _layout(b)
    esp = E.run_all(b, lay, docs, "moradia em Bragança", {"obra": "teste"}, 0.22)
    assert esp["concelho"] == "Bragança"
    best = esp["best"]
    assert best["ok"] and best["lcc"] == min(o["lcc"] for o in esp["options"] if o["ok"])
    assert esp["reh_pdf"][:4] == b"%PDF" and esp["cb_pdf"][:4] == b"%PDF" and esp["mep_pdf"][:4] == b"%PDF"
    assert esp["env"].glazing_total == pytest.approx(10.44 + 3.48, rel=0.01)   # mapa de vãos (aquecidas)
    lines = costs.quote_lines(b, structure.design(b), lay, esp)
    lots = {l["lot"] for l in lines}
    for lot in ("Estrutura", "Alvenarias", "Isolamento térmico", "Caixilharias", "Eletricidade (RTIEBT)", "Águas e esgotos (DR 23/95)"):
        assert lot in lots, lot
    assert all(l["qty"] > 0 and l["pu"] >= 0 for l in lines)


def test_concelho_sem_indicacao_usa_clima_por_defeito_assinalado():
    b = _building()
    lay, docs = _layout(b, placed=False)
    esp = E.run_all(b, lay, docs, "", {"obra": "teste"}, 0.22)
    assert esp["concelho"] is None
    assert any("Grande Lisboa" in h for h in esp["reh"]["hipoteses"])


def test_desenhos_completos_e_capa_com_imagem(tmp_path):
    b = _building()
    lay, docs = _layout(b)
    esp = E.run_all(b, lay, docs, "Évora", {"obra": "teste"}, 0.22)
    R = structure.design(b)
    p, done = drawings.write_drawings(b, R, lay, esp, tmp_path / "d.pdf", {"obra": "teste"}, R.slab["h"])
    assert not any("falhou" in s for s in done) and len(done) == 12
    import pymupdf
    n = pymupdf.open(str(p)).page_count
    assert n >= 14                                                              # + plantas parciais 1:50
    imgs = covers.local_views(b, R.slab["h"])
    assert imgs.get("main")
    covers.prepend(p, covers.cover_pdf(imgs, "Desenhos", "x", {"obra": "t"}, [], landscape_a3=True))
    doc = pymupdf.open(str(p))
    assert doc.page_count == n + 1 and doc[0].get_images()                  # capa com a imagem real


def test_cotas_escritas_confirmadas_pelas_faces_desenhadas():
    """Cota real do projeto: «3,06» escrita ao centro entre duas faces a 3,06 m → confirmada com as extremidades;
    «2,00» sem faces a essa distância → não confirmada (fica visível como valor escrito a verificar)."""
    import numpy as np
    from engines.bet_geo.pdf_vector import _drop_patterns, _match_span
    vt = np.array([(0.0, 5.0, 1.00), (0.0, 5.0, 4.06), (0.0, 5.0, 4.30)])         # faces verticais x = 1,00 / 4,06 / 4,30
    hz = np.array([(0.0, 6.0, 0.0), (0.0, 6.0, 5.0)])
    m = _match_span(3.06, 2.55, 2.5, hz, vt)
    assert m and m[0] == "x" and m[1][0] == pytest.approx(1.0) and m[2][0] == pytest.approx(4.06)
    assert _match_span(2.00, 2.55, 2.5, hz, vt) is None
    floor = [[0.0, y / 100, 3.0, y / 100] for y in range(0, 200, 19)]               # tábuas de soalho a 19 cm
    walls = [[0.0, 5.0, 3.0, 5.0], [0.0, 5.2, 3.0, 5.2]]                            # duas faces de uma parede
    kept = _drop_patterns(floor + walls)
    assert all(q in kept for q in walls) and sum(q in kept for q in floor) <= 2
