from datetime import date
from io import StringIO

import numpy as np
import pytest

from bim_studio.clt_access import allowed
from bim_studio.clt_costs import CostLot, summary
from bim_studio.clt_geometry import panel_quantities, reconciliation
from bim_studio.finishes import layer_area


def ring(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def test_panel_cutouts_and_two_percent_gate():
    gross = ring(0, 0, 5, 3)
    opening = ring(1, 0, 2, 2)
    result = panel_quantities(gross, [opening], 140)
    assert result["net_area_m2"] == 13
    assert result["gross_volume_m3"] == 2.1
    assert result["net_volume_m3"] == 1.82
    assert reconciliation(1.02, 1)["passed"]
    assert not reconciliation(1.021, 1)["passed"]
    assert not reconciliation(0.0001, 0)["passed"]
    with pytest.raises(ValueError, match="sobrepostos"):
        panel_quantities(gross, [opening, ring(1.5, 0, 2.5, 2)], 140)


def test_cut_band_excludes_only_the_part_of_window_inside_it():
    from bim_studio.clt_geometry import face_profile

    def triangles(x0, z0, x1, z1):
        a, b, c, d = [(x, 7, z) for x, z in ring(x0, z0, x1, z1)[:4]]
        return [(a, b, c), (a, c, d)]

    mesh = np.asarray(triangles(0, 0, 5, 1) + triangles(0, 1, 1, 2)
                      + triangles(2, 1, 5, 2) + triangles(0, 2, 5, 3))
    profile = face_profile(mesh, np.array([0., 1.]))
    faces = {"kind": "wall", "z0": 0, "z1": 3, "sides": {"A": {"area": 14, "profile": profile}}}
    exact = layer_area(faces, "A", {"from_m": 0, "to_m": 1.2})
    assert exact["origin"] == "calculated"
    assert exact["value"] == 5.8
    faces["sides"]["A"].pop("profile")
    assert layer_area(faces, "A", {"from_m": 0, "to_m": 1.2})["origin"] == "estimated"


def test_dxf_units_and_source_handles(monkeypatch, tmp_path):
    import ezdxf
    from bim_studio.clt_cad import measure_dxf

    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    doc = ezdxf.new(units=ezdxf.units.MM)
    panel = doc.modelspace().add_lwpolyline(ring(0, 0, 5000, 3000)[:-1], close=True, dxfattribs={"layer": "CLT"})
    opening = doc.modelspace().add_lwpolyline(ring(1000, 0, 2000, 2000)[:-1], close=True, dxfattribs={"layer": "VAOS"})
    stream = StringIO()
    doc.write(stream)
    (result,) = measure_dxf(stream.getvalue().encode(), "CLT", "VAOS", 140)
    assert result["net_volume_m3"] == 1.82
    assert result["handle"] == panel.dxf.handle
    assert result["opening_handles"] == [opening.dxf.handle]


def test_rotated_pdf_annotations_and_unconfirmed_units():
    import fitz
    from bim_studio.clt_pdf import inspect_pdf

    with fitz.open() as doc:
        page = doc.new_page(width=600, height=400)
        page.insert_text((50, 100), "Opening 900x2100H")
        page.insert_text((50, 140), "Ceiling height 2350 mm")
        page.set_rotation(270)
        report = inspect_pdf(doc.tobytes())
    records = report["pages"][0]["evidence"]
    assert [x["values"] for x in records] == [[900, 2100], [2350]]
    assert all(0 <= v <= 1 for x in records for v in x["rect"])
    assert not report["fabrication_ready"]


def test_progress_and_forecast_separate_missing_costs():
    lot = CostLot.model_validate({
        "name": "Painéis A", "revenue_eur": "2000", "planned_delivery": date(2027, 1, 15),
        "forecast_delivery": date(2027, 1, 18),
        "lines": [{"code": "CLT", "stage": "producao", "name": "Corte", "unit": "m3",
                   "rate_eur": "100", "baseline_qty": 10, "planned_to_date_qty": 6, "accepted_qty": 5,
                   "actual_eur": 600, "actual_reference": "FT-1", "source_reference": "IFC rev B / painel A",
                   "open_commitment_eur": 300}],
    })
    assert summary(lot)["forecast_cost_eur"] is None
    lot.lines[0].uncommitted_remaining_eur = 200
    result = summary(lot)
    assert result["planned_percent"] == "60.00"
    assert result["accepted_percent"] == "50.00"
    assert result["cost_overrun_to_date_eur"] == "100.00"
    assert result["forecast_margin_eur"] == "900.00"
    assert result["delay_days"] == 3


def test_pilot_is_closed_to_other_accounts_and_organisations(monkeypatch):
    monkeypatch.setenv("CLT_PILOT_USER_ID", "ana")
    monkeypatch.setenv("CLT_PILOT_TENANT_ID", "org_a")
    monkeypatch.delenv("CLT_PILOT_ACCOUNTS", raising=False)
    assert allowed({"user_id": "ana", "organization_id": "a"})
    assert not allowed({"user_id": "ana", "organization_id": "b"})
    assert not allowed({"user_id": "bia", "organization_id": "a"})


def test_http_access_rate_and_lot_revision(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mongomock_motor import AsyncMongoMockClient

    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "clt_test")
    monkeypatch.setenv("JWT_SECRET", "local-test-only")
    monkeypatch.setenv("CLT_PILOT_USER_ID", "ana")
    monkeypatch.setenv("CLT_PILOT_TENANT_ID", "org_a")
    monkeypatch.setenv("CLT_PILOT_ACCOUNTS", '{"bia":"org_a"}')
    from bim_studio import store
    from routes import clt_industrial as route

    monkeypatch.setattr(store, "_DB", AsyncMongoMockClient().clt_test)
    actor = {"user_id": "ana", "organization_id": "a", "org_role": "owner"}
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.pro_required] = lambda: actor
    prefix = "/clt-industrial"
    with TestClient(app) as client:
        rate_body = {"code": "CLT", "name": "Madeira", "kind": "compra", "unit": "m3",
                     "rate_eur": 100, "effective_from": "2026-11-11"}
        rate = client.post(prefix + "/rates", json=rate_body)
        assert rate.status_code == 201, rate.text
        assert client.post(prefix + "/rates", json=rate_body).status_code == 409
        body = {"name": "Lote A", "revenue_eur": 2000, "planned_delivery": "2026-12-01", "lines": [
            {"code": "CLT", "name": "Compra", "stage": "compra", "unit": "m3", "rate_id": rate.json()["rate_id"],
             "rate_eur": 100, "baseline_qty": 10, "source_reference": "Plano 1, rev A"}]}
        result = client.post(prefix + "/lots", json=body)
        assert result.status_code == 201, result.text
        lot_id = result.json()["lot_id"]
        body["expected_revision"] = 1
        path = prefix + f"/lots/{lot_id}"
        assert client.put(path, json=body).json()["revision"] == 2
        assert client.put(path, json=body).status_code == 409
        actor["user_id"] = "bia"
        assert client.get(prefix + "/rates").json() == {"items": []}
        assert client.get(prefix + "/lots").json() == {"items": []}
        body["expected_revision"] = 0
        assert client.post(prefix + "/lots", json=body).status_code == 422
        actor["user_id"] = "unlisted"
        assert client.get(prefix + "/config").status_code == 404


def test_dwg_uses_autodesk_and_measures_the_result(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock

    import ezdxf
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "clt_test")
    monkeypatch.setenv("JWT_SECRET", "local-test-only")
    monkeypatch.setenv("CLT_PILOT_USER_ID", "ana")
    monkeypatch.setenv("CLT_PILOT_TENANT_ID", "usr_ana")
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    from engines import autodesk_dwg
    from routes import clt_industrial as route

    doc = ezdxf.new(units=ezdxf.units.MM)
    doc.modelspace().add_lwpolyline(ring(0, 0, 5000, 3000)[:-1], close=True, dxfattribs={"layer": "CLT"})
    stream = StringIO()
    doc.write(stream)
    conversion = AsyncMock(return_value=(stream.getvalue().encode(), {}))
    monkeypatch.setattr(autodesk_dwg, "convert", conversion)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.pro_required] = lambda: {"user_id": "ana"}
    dwg = b"AC1032synthetic"
    with TestClient(app) as client:
        monkeypatch.setenv("APS_DWG_ENABLED", "false")
        payload = {"files": {"file": ("plan.dwg", dwg)}, "data": {"panel_layer": "CLT", "thickness_mm": "140"}}
        assert client.post("/clt-industrial/cad", **payload).status_code == 503
        conversion.assert_not_awaited()
        monkeypatch.setenv("APS_DWG_ENABLED", "true")
        result = client.post("/clt-industrial/cad", **payload)
        assert result.status_code == 200, result.text
        conversion.assert_awaited_once_with(dwg, user_id="ana")
        assert result.json()["provider"] == "autodesk-aps"
        assert result.json()["panels"][0]["net_volume_m3"] == 2.1
    assert not allowed({"user_id": "ana", "organization_id": "a", "active": False})
    monkeypatch.setenv("CLT_PILOT_ACCOUNTS", '{"bia":"org_b"}')
    assert allowed({"user_id": "bia", "organization_id": "b"})
    assert not allowed({"user_id": "bia", "organization_id": "a"})


def test_hatched_wall_without_outline_is_measured():
    import fitz
    from shapely.geometry import Polygon
    from bim_studio.home_a_takeoff import _hatched_runs

    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    tan = (0.82, 0.733, 0.463)

    def hatch(x0, y0, x1, y1):
        x = x0
        while x < x1:
            page.draw_line((x, y1), (min(x + 4, x1), y0), color=tan, width=.36)
            x += 2

    hatch(50, 100, 250, 110)    # outlined wall, 10 points = 100 mm at 0.01 m/point
    hatch(300, 200, 450, 210)   # same hatch, no outline: 1.50 m
    hatch(300, 300, 450, 315)   # 150 mm wide: does not match the 100 mm hatch
    outlined = [Polygon([(50, 100), (250, 100), (250, 110), (50, 110)])]
    markers = [{"id": "clt-1", "drawing_width_mm": 100.0}]
    runs = _hatched_runs(page, .01, outlined, markers)
    measured = [r for r in runs if r["status"] == "measured"]
    assert len(measured) == 1
    assert abs(measured[0]["length_m"] - 1.5) < .01
    assert abs(measured[0]["drawing_width_mm"] - 100) < 1
    assert [r["status"] for r in runs].count("pending") == 1


def test_section_offsets_from_printed_panel_thickness():
    import fitz
    from bim_studio.home_a_takeoff import section_heights

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    cyan, red, black = (0, 1, 1), (0.722, 0, 0), (0, 0, 0)
    k = 5.0  # mm per point

    def stack(top, layers, thickness_mm, label):
        for i in range(layers + 1):
            y = top + i * thickness_mm / k / layers
            page.draw_line((100, y), (400, y), color=cyan)
        page.insert_text((20, top + thickness_mm / k / 2 + 2), label, fontsize=5)
        return top + thickness_mm / k

    roof_under = stack(100, 5, 140, "Panel140-5s")
    for y in (roof_under + 100 / k, roof_under + 115 / k):
        page.draw_line((100, y), (400, y), color=red)
    page.draw_line((100, 380), (400, 380), color=black)          # +1 finished floor
    slab_under = stack(380 + 100 / k, 7, 240, "Panel240-7s")
    for y in (slab_under + 100 / k, slab_under + 115 / k):
        page.draw_line((100, y), (400, y), color=red)
    page.draw_line((100, 700), (400, 700), color=black)          # RDC finished floor
    page.draw_line((250, slab_under), (250, 700 + 60 / k), color=cyan)  # RDC wall to its base
    result = section_heights(page)
    assert abs(result["scale_mm_per_point"] - k) < .01
    assert abs(result["+1"]["floor_buildup_m"] - .100) < .001
    assert abs(result["+1"]["ceiling_zone_m"] - .115) < .001
    assert abs(result["RDC"]["floor_buildup_m"] - .060) < .001
    assert abs(result["RDC"]["ceiling_zone_m"] - .115) < .001


def test_cost_estimate_by_floor_from_libraries():
    from datetime import date
    from decimal import Decimal
    from bim_studio.clt_economics import EstimateInput, estimate, library_merged, lot_from_estimate, merged
    from bim_studio.clt_costs import CostLot

    params = merged({"fabrication_h_m3": {"value": "2", "origin": "empresa"},
                     "truck_m3": {"value": "10", "origin": "empresa"}})
    library = library_merged({
        "MAQ-GRUA": {"deleted": True},
        "COL-AJUDANTE": {"code": "COL-AJUDANTE", "category": "colaboradores", "name": "Ajudante", "unit": "h",
                         "cost_eur": "15", "sale_eur": None, "basis": "h_fabrico", "per_basis": "0.5", "origin": "empresa"},
    })
    assert "MAQ-GRUA" not in library and library["COL-AJUDANTE"]["standard"] is False
    body = EstimateInput(floors=[
        {"name": "RDC", "height_m": "3", "walls": [{"thickness_mm": "100", "layers": 5, "length_m": "10"}],
         "board_layers_m2": "20", "paint_m2": "10"},
        {"name": "+1", "height_m": "2.5", "walls": [{"thickness_mm": "160", "layers": 3, "length_m": "4"}]},
    ], start=date(2027, 1, 4))
    result = estimate(body, params, library)
    rdc, first = result["pisos"]
    assert rdc["montagem_m2"] == 30 and rdc["fabrico_m3"] == 3 and first["fabrico_m3"] == 1.6
    assert rdc["horas_fabrico"] == 6
    lines = {line["codigo"]: line for line in result["linhas"]}
    assert lines["COL-AJUDANTE"]["quantidade"] == 4.6     # 0.5 × 9.2 h
    assert lines["MP-COLA-PUR"]["quantidade"] == float(Decimal("0.16") * (30 * 4 + 10 * 2))
    timber = Decimal(3) * Decimal("1.18") * 315 + Decimal("0.16") * 120 * 5
    assert rdc["custos_eur"]["compra"] == float(timber.quantize(Decimal("0.01")))
    assert result["total"]["viagens"] == 1
    assert lines["TR-OBRA"]["quantidade"] == 300          # one trip × 300 km
    assert abs(rdc["receita_eur"] - (3 * 500 + 30 * 61.69 + 20 * 1.05 * 4.03 + 20 * 1.73 + 20 * 28.75 + 10 * (1.73 + 8.05)
                                 + rdc["custo_total_eur"] / 1.11 * .11)) < .05   # engineering, site and contingency billed at cost
    plan = result["plano"]
    assert [s["fase"] for s in plan["fases"]] == ["compra", "fabrico", "transporte", "montagem"]
    assert plan["inicio"] == "2027-01-04" and plan["fases"][1]["inicio"] == "2027-01-25"
    assert abs(result["total"]["margem_eur"] - (result["total"]["receita_eur"] - result["total"]["custo_total_eur"])) <= .011
    assert any("Adesivo PUR" in h for h in result["hipoteses_por_confirmar"])
    lot = CostLot.model_validate(lot_from_estimate("Home A", result))
    assert lot.planned_delivery.isoformat() == plan["fim"]
    assert {line.code for line in lot.lines} >= {"MP-LAMELA", "EN-ELETRICIDADE", "TR-OBRA", "COL-AJUDANTE"}


def test_price_table_from_excel_paste_and_files(tmp_path):
    from io import BytesIO
    from openpyxl import Workbook
    from bim_studio.clt_economics import read_table_file, rows_to_items, parse_eurostat

    rows = [["Categoria", "Código", "Designação", "Unidade", "Custo", "Venda", "Base", "Consumo por base"],
            ["Matéria-prima", "mp-lamela", "Lamela C24", "m³", "1.234,50 €", "", "m³ de madeira comprada", "1"],
            ["Gruas e máquinas", "GRUA-50", "Grua 50 t", "dia", "650", "", "dia_montagem", "1"],
            ["Revestimentos", "", "Sem código", "m²", "3", "", "m2_placa", "1"]]
    items, errors = rows_to_items(rows)
    assert items[0]["code"] == "MP-LAMELA" and items[0]["cost_eur"] == "1234.50" and items[0]["basis"] == "m3_madeira"
    assert items[1]["category"] == "maquinas" and items[1]["basis"] == "dia_montagem"
    assert errors and errors[0]["row"] == 4
    book = Workbook()
    for row in rows[:2]:
        book.active.append(row)
    buffer = BytesIO()
    book.save(buffer)
    assert read_table_file(buffer.getvalue(), "precos.xlsx")[1][1] == "mp-lamela"
    assert read_table_file("Código;Designação;Custo\nX;Y;2,5\n".encode(), "p.csv")[1] == ["X", "Y", "2,5"]
    payload = {"value": {"0": 0.1133, "1": 0.1086},
               "dimension": {"time": {"category": {"index": {"2025-S2": 0, "2026-S1": 1}}}}}
    assert parse_eurostat(payload) == ("2026-S1", __import__("decimal").Decimal("0.1086"))


def test_home_a_basement_sheet_is_out_of_scope():
    import fitz
    from bim_studio.home_a_takeoff import review_page

    doc = fitz.open()
    page = doc.new_page()
    review = review_page(page, [{"kind": "declared_area", "values": [40.45], "id": "x", "rect": [0, 0, 1, 1]}])
    assert review["in_scope"] is False
    assert review["interior_base_m2"] is None and not review["markers"]


def test_http_company_libraries_estimate_and_lot(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mongomock_motor import AsyncMongoMockClient

    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "clt_test")
    monkeypatch.setenv("JWT_SECRET", "local-test-only")
    monkeypatch.setenv("CLT_PILOT_USER_ID", "ana")
    monkeypatch.setenv("CLT_PILOT_TENANT_ID", "org_a")
    monkeypatch.setenv("CLT_PILOT_ACCOUNTS", '{"bia":"org_a"}')
    from bim_studio import store
    from routes import clt_industrial as route

    monkeypatch.setattr(store, "_DB", AsyncMongoMockClient().clt_test)
    actor = {"user_id": "ana", "organization_id": "a", "org_role": "owner"}
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.pro_required] = lambda: actor
    prefix = "/clt-industrial"
    with TestClient(app) as client:
        items = client.get(prefix + "/parameters").json()["items"]
        assert items["fabrication_h_m3"]["origin"] == "hipotese"
        assert client.put(prefix + "/parameters", json={"fabrication_h_m3": {"value": "2.4"}}).status_code == 200
        assert client.put(prefix + "/parameters", json={"nao_existe": {"value": 1}}).status_code == 422
        library = client.get(prefix + "/library").json()
        glue = {**library["items"]["MP-COLA-PUR"], "cost_eur": "6.2", "origin": "empresa"}
        glue.pop("standard")
        assert client.put(prefix + "/library/MP-COLA-PUR", json=glue).status_code == 200
        preview = client.post(prefix + "/library/table", json={"rows": [["Código", "Designação", "Custo", "Base", "Categoria"],
                                                                      ["GRUA-50", "Grua 50 t", "650", "dia_montagem", "maquinas"]]}).json()
        assert preview["saved"] is False and preview["items"][0]["code"] == "GRUA-50"
        assert client.post(prefix + "/library/table", json={"rows": [["Código", "Designação", "Custo", "Base", "Categoria"],
                                                                   ["GRUA-50", "Grua 50 t", "650", "dia_montagem", "maquinas"]],
                                                          "save": True}).json()["saved"]
        assert client.delete(prefix + "/library/MAQ-GRUA").status_code == 200
        actor["user_id"] = "bia"
        shared = client.get(prefix + "/library").json()["items"]
        assert shared["MP-COLA-PUR"]["cost_eur"] == "6.2" and "GRUA-50" in shared and "MAQ-GRUA" not in shared
        body = {"floors": [{"name": "RDC", "height_m": 3, "walls": [{"thickness_mm": 100, "layers": 5, "length_m": 10}]}],
                "start": "2027-01-04", "start_mode": "fabrico"}
        estimate = client.post(prefix + "/estimate", json=body).json()
        assert estimate["plano"]["fases"][0]["fase"] == "fabrico"
        assert any(line["codigo"] == "GRUA-50" and line["custo_eur"] == 650 * estimate["plano"]["fases"][-1]["dias"]
                   for line in estimate["linhas"])
        lot = client.post(prefix + "/estimate/lot", json={**body, "lot_name": "Home A"})
        assert lot.status_code == 201, lot.text
        forecast = float(lot.json()["lot"]["summary"]["forecast_cost_eur"])
        assert abs(forecast - estimate["total"]["custo_total_eur"]) < .01 * len(estimate["linhas"])


def test_lintel_band_clear_span_and_door_in_clt_wall():
    import fitz
    from shapely.geometry import box
    from bim_studio.home_a_takeoff import DOOR, LINTEL, _openings

    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    for y in (100, 110):                         # dashed red band, 100 mm wide, 3.00 m long
        x = 50
        while x < 350:
            page.draw_line((x, y), (min(x + 3, 350), y), color=LINTEL, width=.6)
            x += 5
    walls = [box(50, 100, 100, 110), box(300, 100, 350, 110), box(400, 200, 500, 210)]
    page.draw_line((410, 210), (410, 300), color=DOOR, width=.72)   # leaf
    page.draw_bezier((410, 300), (450, 300), (500, 260), (500, 210), color=DOOR, width=.72)
    page.draw_line((410, 210), (500, 210), color=DOOR, width=.72)   # opening, on the wall line
    evidence = [{"kind": "opening_dimensions", "values": [900.0, 2300.0], "rect": [440 / 600, 250 / 400, 460 / 600, 255 / 400]}]
    lintels, beams, doors = _openings(page, .01, walls, evidence)
    assert len(lintels) == 1 and not beams
    assert abs(lintels[0]["length_m"] - 3.0) < .05 and abs(lintels[0]["clear_span_m"] - 2.0) < .05
    assert lintels[0]["thickness_mm"] == 100
    assert doors == [{"width_m": .9, "height_m": 2.3, "source": "cotado", "under_lintel": False}]


def test_full_estimate_counts_slab_roof_lintels_indirects_and_vat():
    from decimal import Decimal
    from bim_studio.clt_economics import EstimateInput, estimate, library_merged, merged

    body = EstimateInput(floors=[{
        "name": "+1", "height_m": "3", "walls": [{"thickness_mm": "100", "layers": 5, "length_m": "10"}],
        "panels": [{"kind": "laje", "thickness_mm": "240", "layers": 7, "area_m2": "50"},
                   {"kind": "lintel", "thickness_mm": "100", "layers": 5, "area_m2": "2"}],
        "ceiling_m2": "45", "slab_buildup_m2": "50", "roof_buildup_m2": "50", "facade_m2": "30", "steel_beam_m": "4"}])
    result = estimate(body, merged({}), library_merged({}))
    floor, lines = result["pisos"][0], {l["codigo"]: l for l in result["linhas"]}
    assert floor["fabrico_m3"] == 3 + 12 + .2 and floor["montagem_m2"] == 82
    assert lines["MP-COLA-PUR"]["quantidade"] == float(Decimal("0.16") * (30 * 4 + 50 * 6 + 2 * 4))
    assert lines["REV-TETO-SUB"]["custo_eur"] == 45 * 25 and lines["EST-VIGA-ACO"]["quantidade"] == 4
    assert lines["ISO-COBERTURA"]["quantidade"] == 50 and lines["ISO-FACHADA"]["quantidade"] == 30
    direct = sum(l["custo_eur"] for l in result["linhas"] if l["fase"] not in ("venda", "indiretos"))
    assert abs(lines["IND-IMPREVISTOS"]["custo_eur"] - direct * .05) < .02
    assert abs(result["total"]["custo_total_eur"] - direct * 1.11) < .05
    assert result["total"]["iva_percent"] == 23
    assert abs(result["total"]["receita_com_iva_eur"] - result["total"]["receita_eur"] * 1.23) < .02


def test_fitout_rooms_fixtures_and_windows_reach_the_estimate():
    from bim_studio.clt_economics import EstimateInput, estimate, library_merged, lot_from_estimate, merged
    from bim_studio.clt_costs import CostLot

    body = EstimateInput(floors=[{
        "name": "RDC", "height_m": "3", "walls": [{"thickness_mm": "100", "layers": 5, "length_m": "10"}],
        "rooms": [{"nome": "Sala", "tipo": "sala", "area_m2": "30", "perimetro_m": "22", "rect_m": [0, 0, 6, 5]},
                  {"nome": "WC", "tipo": "casa_de_banho", "area_m2": "4", "perimetro_m": "8", "rect_m": [6, 0, 8, 2],
                   "aparelhos": ["autoclismo", "lavatorio", "chuveiro"]}],
        "windows": [{"largura_m": "2", "sobre": "lintel", "tipo": "janela"}], "interior_doors": 2, "riser_m": [8, 0]}])
    result = estimate(body, merged({}), library_merged({}))
    lines = {l["codigo"]: l for l in result["linhas"]}
    assert lines["CN-SANITA"]["quantidade"] == 1 and lines["CN-DUCHE"]["quantidade"] == 1
    assert lines["CN-PONTO-AGUA"]["quantidade"] == 5          # cold to 3 fixtures, hot to lavatory and shower
    assert lines["CN-PONTO-ESGOTO"]["quantidade"] == 3
    assert abs(lines["CX-CAIXILHARIA"]["quantidade"] - 4.6) < .01   # 2 m × 2.30 m under a lintel
    assert lines["CX-PORTA-INTERIOR"]["quantidade"] == 2 and lines["CX-PORTA-ENTRADA"]["quantidade"] == 1
    assert lines["AC-PAVIMENTO"]["quantidade"] == 30 and lines["AC-PAV-CERAMICO"]["quantidade"] == 4
    assert abs(lines["AC-CERAMICA-PAREDE"]["quantidade"] - 16.8) < .01
    assert lines["EL-TOMADA"]["quantidade"] > 0 and lines["EL-QUADRO"]["quantidade"] == 1
    assert result["plano"]["fases"][-1]["fase"] == "acabamentos"
    assert any("RTIEBT" in n for n in result["notas_quantidades"])
    CostLot.model_validate(lot_from_estimate("Casa", result))


def test_ifc_model_from_measured_polygons():
    import ifcopenshell
    from shapely.geometry import box
    from bim_studio.clt_model3d import _Model

    b = _Model(units="m")
    st = b.storey("RDC", 0.0)
    wall = b.solid(st, "IfcWall", "Parede CLT 100 mm · clt-1", box(0, 0, 5, .1), 0.0, 3.0, "CLT 100 mm 5 camadas",
                   {"Folha": 2, "Referencia": "clt-1", "Fonte": "medido"}, "SOLIDWALL")
    assert wall.is_a("IfcWall") and wall.ContainedInStructure[0].RelatingStructure == st
    props = {p.Name: p.NominalValue.wrappedValue for r in wall.IsDefinedBy for p in r.RelatingPropertyDefinition.HasProperties}
    assert props["Referencia"] == "clt-1"
    import ifcopenshell.geom, ifcopenshell.util.shape as us
    shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), wall)
    v = us.get_vertices(shape.geometry)
    assert abs(v[:, 2].max() - 3.0) < 1e-6 and abs(v[:, 0].max() - 5.0) < 1e-6


def test_assistant_complete_clt_study_note(monkeypatch):
    import asyncio
    from mongomock_motor import AsyncMongoMockClient
    from bim_studio import store
    from bim_studio.clt_economics import EstimateInput, estimate, library_merged, merged
    from engines.calc_lots import assistant_bridge, outils

    floors = {"floors": [{
        "name": "RDC", "height_m": "3", "walls": [{"thickness_mm": "100", "layers": 5, "length_m": "10"}],
        "rooms": [{"nome": "WC", "tipo": "casa_de_banho", "area_m2": "4", "perimetro_m": "8", "rect_m": [0, 0, 2, 2],
                   "aparelhos": ["autoclismo"]}], "windows": [{"largura_m": "2", "sobre": "lintel", "tipo": "janela"}]}]}
    assert "estudo_clt_completo" in outils.CALC_TOOL_NAMES
    out = outils.run("estudo_clt_completo", {"titulo": "Casa teste", "_entrada": floors,
                                             "_parametros": merged({}), "_biblioteca": library_merged({})})
    ref = estimate(EstimateInput.model_validate(floors), merged({}), library_merged({}))["total"]
    assert out["pdf"].startswith(b"%PDF") and out["png"]
    assert out["data"]["custo_total_eur"] == ref["custo_total_eur"] and out["data"]["estado"] == "estimativa"
    assert "HIPÓTESE" not in out["resume"] and "Hipóteses por confirmar" in out["resume"]
    with pytest.raises(ValueError):
        outils.run("estudo_clt_completo", {"_parametros": {}, "_biblioteca": {}})
    import pymupdf
    branded = outils.run("estudo_clt_completo", {"empresa": "clt-rezult", "_entrada": {**floors, "floors": [{
        **floors["floors"][0], "segments": [{"ref": "clt-1", "thickness_mm": "100", "length_m": "10"}]}]},
        "_parametros": merged({}), "_biblioteca": library_merged({})})
    doc = pymupdf.open(stream=branded["pdf"], filetype="pdf")
    assert "CLT Rezult" in doc.metadata["author"] and doc.get_toc()[0][1] == "Capa"
    text = "".join(pg.get_text() for pg in doc)
    assert "clt-1" in text and "Plano de seguimento" in text and "Sensibilidade" in text and "23" in text
    ua = estimate(EstimateInput.model_validate({**floors, "vat_regime": "ua"}), merged({}), library_merged({}))["total"]
    assert ua["iva_percent"] == 20 and abs(ua["iva_eur"] - ua["receita_eur"] * .2) < .01 and "193.1" in ua["iva_fonte"]
    exp = estimate(EstimateInput.model_validate({**floors, "vat_regime": "ua_export"}), merged({}), library_merged({}))["total"]
    assert exp["iva_eur"] == 0 and "195.1.1" in exp["iva_fonte"] and exp["custo_total_eur"] == ua["custo_total_eur"]
    for lingua, words in (("en", ("Tracking plan", "Detailed budget", "bathroom")), ("uk", ("План контролю", "Детальний кошторис", "санвузол"))):
        o = outils.run("estudo_clt_completo", {"empresa": "clt-rezult", "lingua": lingua, "regime_iva": "ua", "_entrada": floors,
                                                 "_parametros": merged({}), "_biblioteca": library_merged({})})
        text = "".join(pg.get_text() for pg in pymupdf.open(stream=o["pdf"], filetype="pdf"))
        assert o["data"]["custo_total_eur"] == ref["custo_total_eur"] and all(w in text for w in words), lingua
        assert "Preencher" not in text and "Custo total" not in text and "193.1" in text

    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(store, "get_db", lambda: db)
    monkeypatch.setattr("bim_studio.clt_access.allowed", lambda user: user["user_id"] == "u1")
    user, conv = {"user_id": "u1", "tenant_id": "t1"}, {"conversation_id": "c1"}
    asyncio.run(db.clt_estimate_inputs.insert_one({"_id": store.tenant_of(user), "body": floors}))
    r = asyncio.run(assistant_bridge.execute_calc_tool("estudo_clt_completo", {"titulo": None, "pisos_json": None}, user, conv, db))
    assert r["ok"] and r["data"]["custo_total_eur"] == ref["custo_total_eur"]
    denied = asyncio.run(assistant_bridge.execute_calc_tool("estudo_clt_completo", {}, {"user_id": "u2", "tenant_id": "t1"}, conv, db))
    assert not denied["ok"] and "piloto CLT" in denied["error"]


def test_dossier_fabrication_annex_and_standard_heights():
    """Runs with plan rectangles bring the dimensioned fabrication drawings as Annex A (same references);
    floors without a height take the company standard: RDC 3,00 m, other floors 2,50 m (editable)."""
    import pymupdf
    from bim_studio.clt_economics import EstimateInput, estimate, library_merged, merged
    from bim_studio.clt_study import note

    def floor(name, height):
        return {"name": name, "height_m": height, "walls": [{"thickness_mm": "100", "layers": 5, "length_m": "14"}],
                "segments": [{"ref": f"{name}-A", "thickness_mm": "100", "length_m": "6", "rect_m": [0, 0, 6, 0.1]},
                             {"ref": f"{name}-B", "thickness_mm": "100", "length_m": "8", "rect_m": [0, 0.1, 0.1, 8.1]}]}

    entrada = {"floors": [floor("RDC", ""), floor("+1", None)]}
    r = estimate(EstimateInput.model_validate(entrada), merged({}), library_merged({}))
    assert [f["altura_m"] for f in r["pisos"]] == [3.0, 2.5]
    assert any("altura standard de 3.00 m" in n for n in r["notas_quantidades"])
    edited = merged({"standard_height_upper_m": {"value": "2.7"}})
    assert estimate(EstimateInput.model_validate(entrada), edited, library_merged({}))["pisos"][1]["altura_m"] == 2.7
    for lingua, words in (("pt", ("Anexo A", "RDC-A", "altura standard da empresa", "Cotas em mm")),
                          ("en", ("Annex A", "RDC-A", "company standard height", "Dimensions in mm")),
                          ("uk", ("Додаток A", "RDC-A", "стандартна висота", "Розміри в мм"))):
        doc = pymupdf.open(stream=note(entrada, merged({}), library_merged({}), "Casa teste", lingua=lingua)["pdf"], filetype="pdf")
        text = "".join(pg.get_text() for pg in doc)
        assert all(w in text for w in words), (lingua, [w for w in words if w not in text])
        assert doc[-1].rect.width > doc[-1].rect.height  # annex sheets in A3 landscape


def test_fabrication_dimensions_are_millimetres():
    import ezdxf, io
    from bim_studio import clt_drawings, clt_walls

    walls, _ = clt_walls.rectangles_to_axes([[(0, 0), (6, 0), (6, 0.1), (0, 0.1)]], height_m=3.0, nominal_mm=(100.0,))
    a = clt_walls.analyse(clt_walls.Floor(name="RDC", walls=walls))
    out = clt_drawings.build([("RDC", walls, a["pecas"])])
    doc = ezdxf.read(io.StringIO(out["dxf"].decode()))
    values = {round(d.get_measurement()) for d in doc.modelspace().query("DIMENSION")}
    texts = " ".join(t.dxf.text for b in doc.blocks if b.name.startswith("*D") for t in b.query("MTEXT TEXT"))
    assert 6000 in values and "6000" in texts and "600000" not in texts
