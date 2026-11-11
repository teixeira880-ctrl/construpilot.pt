"""CLT engines: junctions, cutting plan, IFC 3D check, drawings and PDF reader."""
import fitz
import pytest

from bim_studio.clt_nesting import NestingInput, Piece, pieces_from_walls, plan
from bim_studio.clt_walls import Floor, Opening, WallAxis, analyse, rectangles_to_axes


def wall(id, x1, y1, x2, y2, thickness_mm=100, height_m=2.9, **kw):
    return WallAxis(id=id, x1=x1, y1=y1, x2=x2, y2=y2, thickness_mm=thickness_mm, height_m=height_m, **kw)


def house():
    """10 × 6 m on the axes, 100 mm, one window, one door and an interior T wall."""
    return Floor(name="RDC", walls=[
        wall("A", 0, 0, 10, 0, openings=[Opening(offset_m=2, width_m=1.2, sill_m=0.9, height_m=1.2)]),
        wall("B", 10, 0, 10, 6), wall("C", 10, 6, 0, 6, openings=[Opening(offset_m=4, width_m=0.9, height_m=2.1, kind="porta")]),
        wall("D", 0, 6, 0, 0), wall("E", 5, 0, 5, 6)])


def test_axis_corners_are_closed_and_counted_once():
    r = analyse(house())
    # Outer ring 10.1 × 6.1 minus 9.9 × 5.9 = 3.20 m², interior wall 5.9 × 0.1 = 0.59 m², all × 2.9 m.
    assert r["totais"]["volume_bruto_m3"] == pytest.approx(3.79 * 2.9, abs=1e-6)
    assert r["metodos"]["uniao_area_sobre_espessura_m"] == pytest.approx(37.9, abs=1e-6)
    assert r["metodos"]["pecas_producao_m"] == pytest.approx(37.9, abs=1e-6)
    assert r["contagem_dupla_evitada_m3"] == pytest.approx(4 * 0.1 * 0.1 * 2.9 + 2 * 0.05 * 0.1 * 2.9, abs=1e-6)
    assert r["verificacao_volume"]["passed"]
    assert r["totais"]["area_vaos_m2"] == pytest.approx(1.2 * 1.2 + 0.9 * 2.1)
    kinds = sorted(j["tipo"] for j in r["juntas"])
    assert kinds == ["L", "L", "L", "L", "T", "T"]
    assert r["totais"]["juntas_parede_m"] == pytest.approx(6 * 2.9)
    # Longer walls run through; short ones are trimmed between faces.
    assert {p["id"]: p["comprimento_m"] for p in r["pecas"]} == {"A": 10.1, "C": 10.1, "B": 5.9, "D": 5.9, "E": 5.9}


def test_crossing_wall_and_press_format_split():
    floor = Floor(name="X", walls=[wall("L", 0, 0, 25, 0), wall("S", 5, -2, 5, 2)])
    r = analyse(floor)
    ids = {p["id"]: p["comprimento_m"] for p in r["pecas"]}
    assert ids["L/1"] == ids["L/2"] == pytest.approx(12.5)
    assert ids["S.1"] == pytest.approx(1.95) and ids["S.2"] == pytest.approx(1.95)
    assert r["juntas"][0]["tipo"] == "X"
    assert r["divisoes_formato"][0]["paineis"] == 2
    assert r["verificacao_volume"]["passed"]


def test_opening_on_a_panel_joint_and_tall_walls_are_rejected():
    with pytest.raises(ValueError, match="junta"):
        analyse(Floor(name="J", walls=[wall("L", 0, 0, 20, 0, openings=[Opening(offset_m=9.5, width_m=1, height_m=2)])]))
    with pytest.raises(ValueError, match="painel vertical"):
        analyse(Floor(name="T", walls=[wall("H", 0, 0, 5, 0, height_m=4.0)]))
    with pytest.raises(ValueError, match="sai da parede"):
        wall("O", 0, 0, 2, 0, openings=[Opening(offset_m=1.5, width_m=1, height_m=2)])
    with pytest.raises(ValueError, match="duplicadas"):
        analyse(Floor(name="D", walls=[wall("A", 0, 0, 5, 0), wall("B", 0, 0, 5, 0)]))


def test_rectangles_to_axes_matches_nominal_thickness():
    walls, rejected = rectangles_to_axes([
        [(0, 0), (4, 0), (4, 0.101), (0, 0.101)], [(0, 1), (3, 1), (3, 1.13), (0, 1.13)]], height_m=2.8)
    assert len(walls) == 1 and walls[0].thickness_mm == 100 and walls[0].length == pytest.approx(4)
    assert rejected[0]["largura_mm"] == pytest.approx(130)


def test_cutting_plan_is_feasible_and_never_worse_than_heuristic():
    r = analyse(house())
    out = plan(NestingInput(pieces=pieces_from_walls(r), time_limit_s=3))
    g = out["grupos"][0]
    placed = [p for b in g["layout"] for p in b["pecas"]]
    assert sorted(p["id"] for p in placed) == ["A", "B", "C", "D", "E"]
    assert g["paineis"] <= g["heuristica_paineis"] and g["paineis"] >= g["limite_inferior_paineis"]
    for b in g["layout"]:
        assert b["comprimento_usado_m"] <= 18.0 + 1e-9
        rects = [(p["x_m"], p["y_m"], p["x_m"] + p["comprimento_m"], p["y_m"] + p["largura_m"]) for p in b["pecas"]]
        for i, a in enumerate(rects):
            assert a[3] <= 3.5 + 0.01
            for c in rects[i + 1:]:
                assert min(a[2], c[2]) <= max(a[0], c[0]) + 1e-9 or min(a[3], c[3]) <= max(a[1], c[1]) + 1e-9
    t = out["total"]
    assert t["volume_liquido_m3"] == pytest.approx(r["totais"]["volume_liquido_m3"], abs=1e-3)
    assert t["volume_paineis_m3"] >= t["volume_pecas_m3"]
    assert t["volume_desperdicio_m3"] == pytest.approx(t["volume_paineis_m3"] - t["volume_liquido_m3"], abs=1e-3)


def test_cutting_plan_rejects_oversize_and_groups_build_ups():
    with pytest.raises(ValueError, match="formato"):
        plan(NestingInput(pieces=[Piece(id="big", length_m=19, width_m=3, thickness_mm=100)], time_limit_s=1))
    out = plan(NestingInput(pieces=[Piece(id="a", length_m=4, width_m=2.9, thickness_mm=100),
                                    Piece(id="b", length_m=4, width_m=2.9, thickness_mm=160, layers=5)],
                            time_limit_s=1, variable_width=True))
    assert [g["espessura_mm"] for g in out["grupos"]] == [100, 160]
    assert all(g["paineis"] == 1 for g in out["grupos"])
    assert out["grupos"][0]["layout"][0]["aproveitamento_percent"] == pytest.approx(100, abs=0.5)


def test_ifc_model_volumes_match_opencascade():
    from bim_studio.clt_ifc import build

    floor = house()
    floor.walls.append(wall("G", 1, 1, 4, 5, thickness_mm=160))
    r = analyse(floor)
    data, check = build([("RDC", 0.0, floor.walls, r["pecas"])],
                        slabs=[{"name": "Laje", "storey": "RDC", "polygon": [(0, 0), (10, 0), (10, 6), (0, 6)],
                                "thickness_mm": 200, "elevation_m": 2.9, "source": "teste"}])
    assert data.startswith(b"ISO-10303-21")
    assert check["passed"] and len(check["pecas"]) == len(r["pecas"])
    assert check["volume_ifc_m3"] == pytest.approx(r["totais"]["volume_liquido_m3"], rel=1e-4)
    assert b"Qto_WallBaseQuantities" in data and b"ConstruPilot_CLT" in data and b"IFCOPENINGELEMENT" in data


def test_fabrication_drawings_dxf_and_pdf():
    import io

    import ezdxf

    from bim_studio.clt_drawings import build

    floor = house()
    r = analyse(floor)
    nesting = plan(NestingInput(pieces=pieces_from_walls(r), time_limit_s=1))
    out = build([("RDC", floor.walls, r["pecas"])], nesting)
    doc = ezdxf.read(io.StringIO(out["dxf"].decode()))
    layers = {e.dxf.layer for e in doc.modelspace()}
    assert {"CLT_EIXO", "CLT_PECA", "CLT_VAO", "CLT_COTA", "CLT_PAINEL"} <= layers
    assert len(doc.modelspace().query("DIMENSION")) >= 10
    with fitz.open(stream=out["pdf"], filetype="pdf") as pdf:
        assert len(pdf) == 3
    assert out["folhas"][1]["vaos"] == 2


def synthetic_plan(scale_text="Escala 1:50"):
    k = 72 / 25.4 / 50 * 1000
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)

    def rect(x0, y0, x1, y1, fill=(1, 0, 1)):
        page.draw_rect(fitz.Rect(100 + x0 * k, 450 - y1 * k, 100 + x1 * k, 450 - y0 * k), color=(0, 0, 0), fill=fill)
    for r in ((0, 0, 10, .1), (0, 5.9, 10, 6), (0, .1, .1, 5.9), (9.9, .1, 10, 5.9), (4.95, .1, 5.05, 5.9)):
        rect(*r)
    rect(6, 2, 8, 2.3, fill=(0, 0, 1))  # 300 mm band in another colour: not the CLT legend colour
    page.draw_rect(fitz.Rect(600, 500, 700, 520), color=(0, 0, 0))
    if scale_text:
        page.insert_text((600, 560), scale_text)
    return doc.tobytes()


def test_pdf_reader_finds_walls_scale_and_junctions():
    from bim_studio.clt_pdf_walls import detect

    r = detect(synthetic_plan(), 1, height_m=2.9)
    assert r["escala"] == 50 and "lida na folha" in r["origem_escala"]
    assert r["cor_usada"] == "#ff00ff" and len(r["paredes"]) == 5
    assert r["estado"] == "detetado, por confirmar"
    assert r["analise"]["totais"]["volume_bruto_m3"] == pytest.approx((2 * 10 * .1 + 3 * 5.8 * .1) * 2.9, rel=1e-4)
    assert sorted(j["tipo"] for j in r["analise"]["juntas"]) == ["L", "L", "L", "L", "T", "T"]
    assert len(r["marcadores"]) == 5 and all(0 <= v <= 1 for m in r["marcadores"] for v in m["rect"])
    with pytest.raises(ValueError, match="escala"):
        detect(synthetic_plan(None), 1, height_m=2.9)
    assert detect(synthetic_plan(None), 1, height_m=2.9, scale=50)["escala"] == 50


def test_http_engines(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "clt_test")
    monkeypatch.setenv("CLT_PILOT_USER_ID", "ana")
    monkeypatch.setenv("CLT_PILOT_TENANT_ID", "org_a")
    monkeypatch.setenv("JWT_SECRET", "local-test-only")
    from routes import clt_engines as route
    from routes import clt_industrial

    actor = {"user_id": "ana", "organization_id": "a", "org_role": "owner"}
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[clt_industrial.pro_required] = lambda: actor
    body = {"floors": [{"name": "RDC", "walls": [w.model_dump() for w in house().walls]}],
            "cutting": {"time_limit_s": 1}}
    with TestClient(app) as client:
        r = client.post("/clt-industrial/motores/analise", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["estado"] == "medido" and data["verificacoes"] == {"pecas_vs_planta": True, "ifc_opencascade": True}
        assert data["total"]["volume_liquido_m3"] == pytest.approx(3.79 * 2.9 - (1.44 + 1.89) * .1, abs=1e-4)
        ifc = client.post("/clt-industrial/motores/ifc", json=body)
        assert ifc.status_code == 200 and ifc.content.startswith(b"ISO-10303-21")
        pdf = client.post("/clt-industrial/motores/desenhos?formato=pdf", json=body)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        dxf = client.post("/clt-industrial/motores/desenhos?formato=dxf", json=body)
        assert dxf.status_code == 200 and b"CLT_PECA" in dxf.content
        found = client.post("/clt-industrial/motores/pdf-paredes", data={"page": "1", "height_m": "2.9"},
                            files={"file": ("plan.pdf", synthetic_plan(), "application/pdf")})
        assert found.status_code == 200, found.text
        assert len(found.json()["paredes"]) == 5
        bad = client.post("/clt-industrial/motores/analise", json={"floors": [{"name": "X", "walls": [
            {**house().walls[0].model_dump(), "height_m": 4.2}]}]})
        assert bad.status_code == 422
        other = {"user_id": "zé", "organization_id": "b", "org_role": "owner"}
        app.dependency_overrides[clt_industrial.pro_required] = lambda: other
        assert client.post("/clt-industrial/motores/analise", json=body).status_code == 200  # every account
        app.dependency_overrides[clt_industrial.pro_required] = lambda: {**other, "active": False}
        assert client.post("/clt-industrial/motores/analise", json=body).status_code == 404


def test_raster_reader_is_an_estimate_with_pixel_uncertainty():
    import cv2
    import numpy as np

    from bim_studio.clt_raster_walls import detect

    ppm = 20  # 5 cm per pixel
    im = np.full((400, 400, 3), 255, np.uint8)
    grey = (94, 94, 94)
    # 10 × 6 m outline, 20 cm walls (4 px), plus an L-shaped thin wall ending in a 1 m pier.
    cv2.rectangle(im, (50, 50), (249, 53), grey, -1)
    cv2.rectangle(im, (50, 166), (249, 169), grey, -1)
    cv2.rectangle(im, (50, 54), (53, 165), grey, -1)
    cv2.rectangle(im, (246, 54), (249, 165), grey, -1)
    cv2.rectangle(im, (60, 300), (199, 303), grey, -1)
    cv2.rectangle(im, (200, 290), (219, 313), grey, -1)  # pier wider than 50 cm: excluded
    ok, png = cv2.imencode(".png", im)
    r = detect(png.tobytes(), pixels_per_metre=ppm, height_m=3.0, min_thickness_m=0.1)
    assert r["estado"] == "estimativa de imagem" and r["pixel_m"] == 0.05
    lengths = sorted(round(w["thickness_mm"]) for w in r["paredes"])
    assert lengths == [200] * 5
    a = r["analise"]
    # Outline 10 × 6 m outer edge: (10 × 6 − 9.6 × 5.6) m² of plan, plus the 7 m free wall × 0.2 m.
    assert a["totais"]["volume_bruto_m3"] == pytest.approx(((10 * 6 - 9.6 * 5.6) + 7 * 0.2) * 3.0, rel=0.03)
    assert a["verificacao_volume"]["passed"]
    with pytest.raises(ValueError, match="ilegível"):
        detect(b"not an image", pixels_per_metre=ppm, height_m=3.0)


def test_network_healing_joins_runs_over_lintels_and_resolves_t_stems():
    from bim_studio.clt_walls import connect

    # outlines as a plan reader returns them: each run stops at the other wall's face, the door gap has a lintel
    runs = [wall("A1", 0, 0.05, 4, 0.05), wall("A2", 5, 0.05, 10, 0.05),        # front wall, door 4–5 m
            wall("B", 0.05, 0.1, 0.05, 6), wall("C", 9.95, 0.1, 9.95, 6),        # side walls butt on the front wall
            wall("T", 3, 0.1, 3, 4)]                                             # interior stem, shorter than nothing
    lintel = {"ref": "L1", "rect_m": [3.95, 0, 5.05, 0.1], "head_m": 2.1, "thickness_mm": 100}
    walls, net = connect(runs, lintels=[lintel])
    assert net["membros"] == {"A1": "A1+A2", "A2": "A1+A2", "B": "B", "C": "C", "T": "T"} and not net["notas"]
    front = next(w for w in walls if w.id == "A1+A2")
    assert front.length == pytest.approx(9.9) and len(front.openings) == 1  # axis to axis of the side walls
    assert front.openings[0].width_m == pytest.approx(1.0) and front.openings[0].height_m == 2.1
    r = analyse(Floor(name="RDC", walls=walls))
    kinds = sorted(j["tipo"] for j in r["juntas"])
    assert kinds == ["L", "L", "T"] and r["verificacao_volume"]["passed"]
    assert r["metodos"]["volume_pecas_m3"] == pytest.approx(r["metodos"]["volume_uniao_planta_m3"], abs=1e-6)
    piece = next(p for p in r["pecas"] if p["parede"] == "A1+A2")
    # one 10 m piece (closing both corners) with the 1.0 × 2.1 m door cut out; the CLT over the door is inside it
    assert piece["comprimento_m"] == pytest.approx(10.0) and piece["area_vaos_m2"] == pytest.approx(2.1)
    assert piece["volume_liquido_m3"] == pytest.approx((10 * 2.9 - 2.1) * 0.1)
    # a lintel of another thickness, or with no run on its line, stays a separate panel and is reported
    _w, other = connect(runs, lintels=[{**lintel, "thickness_mm": 160}, {"ref": "L2", "rect_m": [20, 0, 21, .1], "head_m": 2.1}])
    assert len(other["notas"]) == 2 and not other["linteis"]


def test_t_stem_is_cut_even_when_longer():
    """The through wall runs on at a T: a long stem must not notch a short through wall."""
    floor = Floor(name="RDC", walls=[wall("short", 0, 0, 1, 0), wall("stem", 0.5, 0, 0.5, 6)])
    r = analyse(floor)
    by = {p["parede"]: p for p in r["pecas"]}
    assert by["short"]["comprimento_m"] == pytest.approx(1.0) and by["stem"]["comprimento_m"] == pytest.approx(5.95)
    assert r["metodos"]["volume_pecas_m3"] == pytest.approx(r["metodos"]["volume_uniao_planta_m3"], abs=1e-9)


def lintel_plan():
    k = 72 / 25.4 / 50 * 1000
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    X = lambda x: 100 + x * k
    Y = lambda y: 450 - y * k
    for x0, y0, x1, y1 in ((0, 0, 4, .1), (5, 0, 10, .1), (0, .1, .1, 5.9), (9.9, .1, 10, 5.9), (0, 5.9, 2, 6), (4, 5.9, 10, 6)):
        page.draw_rect(fitz.Rect(X(x0), Y(y1), X(x1), Y(y0)), color=(0, 0, 0), fill=(1, 0, 1))
    for y in (0, .1):  # red dashed lintel over the 1 m door
        page.draw_line((X(3.95), Y(y)), (X(5.05), Y(y)), color=(1, 0, 0), dashes="[3 2] 0", width=.6)
    for y in (5.9, 6):  # orange dashed band over the 2 m window: another symbol
        page.draw_line((X(1.95), Y(y)), (X(4.05), Y(y)), color=(.867, .435, 0), dashes="[3 2] 0", width=.6)
    page.insert_text((600, 560), "Escala 1:50")
    page.insert_text((300, 300), "P1 900x2300H")
    return doc.tobytes()


def test_pdf_reader_reads_lintels_and_only_uses_a_confirmed_colour():
    from bim_studio.clt_pdf_walls import detect

    r = detect(lintel_plan(), 1, height_m=2.9)
    assert {c["cor"] for c in r["cores_linteis"]} == {"#ff0000", "#dd6f00"} and not r["linteis"]  # two symbols: ask
    r = detect(lintel_plan(), 1, height_m=2.9, lintel_colour="#FF0000")
    assert len(r["linteis"]) == 1 and r["linteis"][0]["thickness_mm"] == 100 and r["linteis"][0]["head_m"] == 2.3
    assert "lida" in r["linteis"][0]["origem_altura"] and r["estado"] == "detetado, por confirmar"
    assert len(r["rede"]["linteis"]) == 1 and r["analise"]["verificacao_volume"]["passed"]
    assert any(len(p["vaos"]) == 1 and p["vaos"][0]["height_m"] == 2.3 for p in r["analise"]["pecas"])
