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


def test_cost_estimate_by_floor_with_company_values():
    from decimal import Decimal
    from bim_studio.clt_economics import EstimateInput, estimate, merged

    params = merged({"fabrication_h_m3": {"value": "2", "origin": "empresa"},
                     "truck_m3": {"value": "10", "origin": "empresa"}})
    assert params["fabrication_h_m3"]["origin"] == "empresa"
    assert params["timber_eur_m3"]["origin"] == "mercado" and params["timber_eur_m3"]["source"]
    body = EstimateInput(floors=[
        {"name": "RDC", "height_m": "3", "walls": [{"thickness_mm": "100", "layers": 5, "length_m": "10"}],
         "board_layers_m2": "20", "paint_m2": "10"},
        {"name": "+1", "height_m": "2.5", "walls": [{"thickness_mm": "160", "layers": 3, "length_m": "4"}]},
    ])
    result = estimate(body, params)
    rdc, first = result["pisos"]
    assert rdc["montagem_m2"] == 30 and rdc["fabrico_m3"] == 3
    assert first["fabrico_m3"] == 1.6
    assert rdc["horas_fabrico"] == 6
    p = {k: Decimal(v["value"]) for k, v in params.items()}
    compra = 3 * p["timber_input_m3_per_m3"] * p["timber_eur_m3"] + 30 * 4 * p["adhesive_kg_m2"] * p["adhesive_eur_kg"]
    assert rdc["custos_eur"]["compra"] == float(compra.quantize(Decimal("0.01")))
    assert result["total"]["viagens"] == 1
    transport = float(p["transport_km"] * p["transport_eur_km"])
    assert abs(rdc["custos_eur"]["transporte"] + first["custos_eur"]["transporte"] - transport) < .02
    assert result["prazo"]["fabrico_dias"] == 1
    assert abs(result["total"]["margem_eur"] - (result["total"]["receita_eur"] - result["total"]["custo_total_eur"])) <= .011
    assert result["status"] == "estimativa" and "Tempo de fabrico por m³ de CLT" not in result["hipoteses_por_confirmar"]


def test_home_a_basement_sheet_is_out_of_scope():
    import fitz
    from bim_studio.home_a_takeoff import review_page

    doc = fitz.open()
    page = doc.new_page()
    review = review_page(page, [{"kind": "declared_area", "values": [40.45], "id": "x", "rect": [0, 0, 1, 1]}])
    assert review["in_scope"] is False
    assert review["interior_base_m2"] is None and not review["markers"]


def test_http_company_parameters_and_estimate(monkeypatch):
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
        assert items["adhesive_eur_kg"]["origin"] == "hipotese"
        saved = client.put(prefix + "/parameters", json={"adhesive_eur_kg": {"value": "6.2"}})
        assert saved.status_code == 200, saved.text
        assert saved.json()["items"]["adhesive_eur_kg"] == {**items["adhesive_eur_kg"], "value": "6.2",
                                                           "origin": "empresa", "source": "Valor da empresa"}
        assert client.put(prefix + "/parameters", json={"nao_existe": {"value": 1}}).status_code == 422
        actor["user_id"] = "bia"
        assert client.get(prefix + "/parameters").json()["items"]["adhesive_eur_kg"]["value"] == "6.2"
        estimate = client.post(prefix + "/estimate", json={"floors": [
            {"name": "RDC", "height_m": 3, "walls": [{"thickness_mm": 100, "layers": 5, "length_m": 10}]}]})
        assert estimate.status_code == 200, estimate.text
        assert "Adesivo PUR, preço de compra" not in estimate.json()["hipoteses_por_confirmar"]
