"""Núcleo BIM: planta lida (píxeis) → modelo métrico → IFC 4.3 válido, com geometria, quantidades e GlobalId estáveis.
Rotas /bim testadas com Mongo falso (sem servidor)."""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_bim_core")
os.environ.setdefault("JWT_SECRET", "test")

ifcopenshell = pytest.importorskip("ifcopenshell")
import ifcopenshell.geom  # noqa: E402
import ifcopenshell.util.element as E  # noqa: E402
import ifcopenshell.util.shape as S  # noqa: E402
import numpy as np  # noqa: E402

from engines import bim_core as B  # noqa: E402

PPM = 50.0  # 50 píxeis por metro


def P(m):
    return m * PPM


def house():
    """Moradia 10 × 8 m: 4 paredes resistentes, 1 divisória, 1 porta, 1 janela, laje, pilar, viga, sapata."""
    return {
        "walls": [
            {"wall_id": "w1", "x1": P(0), "y1": P(8), "x2": P(10), "y2": P(8), "type": "porteur"},
            {"wall_id": "w2", "x1": P(10), "y1": P(8), "x2": P(10), "y2": P(0), "type": "porteur"},
            {"wall_id": "w3", "x1": P(10), "y1": P(0), "x2": P(0), "y2": P(0), "type": "porteur"},
            {"wall_id": "w4", "x1": P(0), "y1": P(0), "x2": P(0), "y2": P(8), "type": "porteur"},
            {"wall_id": "w5", "x1": P(5), "y1": P(0), "x2": P(5), "y2": P(8), "type": "cloison"},
        ],
        "openings": [
            {"opening_id": "o1", "kind": "porte", "x1": P(2), "y1": P(8), "x2": P(2.9), "y2": P(8)},
            {"opening_id": "o2", "kind": "fenetre", "x1": P(10), "y1": P(3), "x2": P(10), "y2": P(4.2)},
            {"opening_id": "o3", "kind": "fenetre", "x1": P(20), "y1": P(20), "x2": P(21), "y2": P(20)},
        ],
        "floors": [{"floor_id": "f1", "name": "Laje piso 0",
                    "points": [[0, 0], [P(10), 0], [P(10), P(8)], [0, P(8)]], "thickness_cm": 20}],
        "columns": [{"column_id": "c1", "x1": P(4.9), "y1": P(3.9), "x2": P(5.1), "y2": P(4.1)}],
        "beams": [{"beam_id": "b1", "x1": P(0), "y1": P(4), "x2": P(10), "y2": P(4)}],
        "footings": [{"footing_id": "s1", "x1": P(4.6), "y1": P(3.6), "x2": P(5.4), "y2": P(4.4)}],
    }


ROOMS = [{"room_id": "r1", "name": "Sala", "page_index": 0,
          "points": [[0, 0], [P(5), 0], [P(5), P(8)], [0, P(8)]]}]


def build(structure=None, **kw):
    m = B.from_takeoff(structure or house(), PPM, rooms=ROOMS, plan_id="plan_1", **kw)
    return m, B.build_ifc(m)


def bbox(el):
    sh = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), el)
    v = S.get_shape_vertices(sh, sh.geometry)
    return np.round(v.min(0), 3), np.round(v.max(0), 3)


# ---------------- modelo métrico ----------------

def test_model_converts_pixels_to_metres_with_y_up_and_origin_at_bottom_left():
    m, _ = build()
    assert m.counts() == {"walls": 5, "openings": 2, "slabs": 1, "columns": 1, "beams": 1, "footings": 1, "spaces": 1}
    w1 = next(w for w in m.walls if w.source_id == "w1")      # parede no fundo da imagem → y = 0
    assert (w1.x1, w1.y1, w1.x2, w1.y2) == (0.0, 0.0, 10.0, 0.0)
    assert w1.load_bearing and w1.thickness == 0.20
    assert next(w for w in m.walls if w.source_id == "w5").thickness == 0.10
    assert m.slabs[0].area == pytest.approx(80.0)


def test_openings_are_hosted_by_the_nearest_parallel_wall_and_orphans_are_reported():
    m, _ = build()
    o1 = next(o for o in m.openings if o.source_id == "o1")
    assert o1.wall_id == "w1" and o1.offset == pytest.approx(2.0) and o1.width == pytest.approx(0.9)
    assert o1.sill == 0.0 and o1.height == pytest.approx(2.10)
    o2 = next(o for o in m.openings if o.source_id == "o2")
    assert o2.wall_id == "w2" and o2.sill == pytest.approx(0.90)
    assert {"code": "opening_without_wall", "source_id": "o3"} in m.warnings


def test_missing_calibration_or_geometry_is_refused_instead_of_invented():
    with pytest.raises(B.ModelError, match="calibrada"):
        B.from_takeoff(house(), None)
    with pytest.raises(B.ModelError):
        B.from_takeoff({"walls": []}, PPM)


def test_user_parameters_override_defaults_and_bad_values_fall_back():
    m = B.from_takeoff(house(), PPM, params={"wall_height": 3.0, "voile_ep": 0.25, "poutre_h": "abc"})
    assert all(w.height == 3.0 for w in m.walls)
    assert next(w for w in m.walls if w.load_bearing).thickness == 0.25
    assert m.beams[0].depth == B.DEFAULTS["poutre_h"]


# ---------------- IFC ----------------

def test_ifc_is_ifc4x3_in_metres_and_passes_schema_validation():
    _, f = build()
    assert f.schema.upper().startswith("IFC4X3")
    assert B.validate(f) == []
    lengths = [u for u in f.by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT"]
    assert lengths and lengths[0].Prefix is None          # metros, não milímetros
    assert len(f.by_type("IfcProject")) == 1 and len(f.by_type("IfcBuildingStorey")) == 1


def test_every_element_has_real_geometry_where_expected():
    _, f = build()
    lo, hi = bbox(next(w for w in f.by_type("IfcWall") if w.Name.startswith("Parede resistente 1")))
    assert lo.tolist() == [0.0, -0.1, 0.0] and hi.tolist() == [10.0, 0.1, 2.7]
    lo, hi = bbox(f.by_type("IfcSlab")[0])
    assert lo.tolist() == [0.0, 0.0, -0.2] and hi.tolist() == [10.0, 8.0, 0.0]      # laje sob a cota 0
    lo, hi = bbox(f.by_type("IfcColumn")[0])
    assert lo.tolist() == [4.9, 3.9, 0.0] and hi.tolist() == [5.1, 4.1, 2.7]
    lo, hi = bbox(f.by_type("IfcBeam")[0])
    assert lo[2] == pytest.approx(2.3) and hi[2] == pytest.approx(2.7)               # viga pendurada no topo
    lo, hi = bbox(f.by_type("IfcFooting")[0])
    assert lo[2] == pytest.approx(-0.6) and hi[2] == pytest.approx(-0.2)             # sapata sob a laje
    for el in f.by_type("IfcProduct"):
        if el.Representation is not None:
            bbox(el)                                                                  # tudo é triangulável


def test_openings_void_their_wall_and_carry_a_door_or_window():
    _, f = build()
    voids = f.by_type("IfcRelVoidsElement")
    fills = f.by_type("IfcRelFillsElement")
    assert len(voids) == 2 and len(fills) == 2
    assert {r.RelatedBuildingElement.is_a() for r in fills} == {"IfcDoor", "IfcWindow"}
    door = f.by_type("IfcDoor")[0]
    assert door.OverallWidth == pytest.approx(0.9) and door.OverallHeight == pytest.approx(2.1)


def test_quantities_and_psets_are_written_in_the_ifc():
    _, f = build()
    w1 = next(w for w in f.by_type("IfcWall") if E.get_psets(w)["CP_Origem"]["IdOrigem"] == "w1")
    ps = E.get_psets(w1)
    assert ps["Pset_WallCommon"]["LoadBearing"] is True
    q = ps["Qto_WallBaseQuantities"]
    assert q["GrossVolume"] == pytest.approx(10 * 2.7 * 0.2)
    assert q["NetVolume"] == pytest.approx(10 * 2.7 * 0.2 - 0.9 * 2.1 * 0.2)       # porta deduzida
    assert ps["CP_Origem"]["PlanoId"] == "plan_1"
    slab = f.by_type("IfcSlab")[0]
    assert E.get_psets(slab)["Qto_SlabBaseQuantities"]["GrossArea"] == pytest.approx(80.0)
    assert E.get_material(slab).Name.startswith("Betão")
    space = f.by_type("IfcSpace")[0]
    assert E.get_psets(space)["Qto_SpaceBaseQuantities"]["NetFloorArea"] == pytest.approx(40.0)


def test_global_ids_are_unique_and_stable_across_regenerations():
    _, f1 = build()
    _, f2 = build()
    g1 = sorted(el.GlobalId for el in f1.by_type("IfcRoot"))
    g2 = sorted(el.GlobalId for el in f2.by_type("IfcRoot"))
    products = [el.GlobalId for el in f1.by_type("IfcProduct")]
    assert len(products) == len(set(products))

    def key(el):
        return E.get_psets(el).get("CP_Origem", {}).get("IdOrigem", el.Name) + el.is_a()

    stable1 = {key(el): el.GlobalId for el in f1.by_type("IfcElement")}
    stable2 = {key(el): el.GlobalId for el in f2.by_type("IfcElement")}
    assert stable1 == stable2 and len(g1) == len(g2)
    m3 = B.from_takeoff(house(), PPM, plan_id="plan_2")
    f3 = B.build_ifc(m3)
    assert not set(stable1.values()) & {el.GlobalId for el in f3.by_type("IfcElement")}


def test_summary_reads_quantities_back_from_the_ifc():
    _, f = build()
    s = B.summarize(f)
    assert s["totals"]["IfcWall"]["count"] == 5 and s["totals"]["IfcWall"]["length_m"] == pytest.approx(44.0)
    assert s["totals"]["IfcSlab"]["area_m2"] == pytest.approx(80.0)
    # betão = paredes resistentes (líquido) + laje + pilar + viga + sapata
    walls_lb = (10 + 8 + 10 + 8) * 2.7 * 0.2 - 0.9 * 2.1 * 0.2 - 1.2 * 1.2 * 0.2
    expected = walls_lb + 16.0 + 0.2 * 0.2 * 2.7 + 10 * 0.2 * 0.4 + 0.8 * 0.8 * 0.4
    assert s["concrete_volume_m3"] == pytest.approx(expected, abs=0.01)
    assert all(e["guid"] and e["ifc_class"] for e in s["elements"])


def test_ifc_roundtrip_through_text_reopens_identically():
    _, f = build()
    g = ifcopenshell.file.from_string(f.to_string())
    assert len(g.by_type("IfcProduct")) == len(f.by_type("IfcProduct"))


# ---------------- rotas ----------------

R = pytest.importorskip("routes.bim")
from fake_mongo_pt import FakeDB  # noqa: E402
from fastapi import HTTPException  # noqa: E402

USER = {"user_id": "u1", "account_type": "pro"}
NONE = dict(wall_height=None, voile_ep=None, cloison_ep=None, dalle_ep=None, poutre_l=None, poutre_h=None)


@pytest.fixture
def fdb(monkeypatch):
    db = FakeDB()
    db.plans_takeoff.docs.append({"plan_id": "plan_1", "user_id": "u1", "filename": "Moradia Silva.pdf",
                                  "structure": {"0": house()}, "rooms": ROOMS,
                                  "calibrations": {"0": {"pixels_per_meter": PPM}}})
    db.plans_takeoff.docs.append({"plan_id": "plan_nocal", "user_id": "u1", "structure": {"0": house()}})
    monkeypatch.setattr(R, "db", db)
    return db


def run(c):
    return asyncio.run(c)


def test_route_summary_returns_valid_model_with_warnings(fdb):
    out = run(R.bim_summary("plan_1", 0, **NONE, user=USER))
    assert out["valid"] is True and out["schema"].startswith("IFC4X3")
    assert out["counts"]["walls"] == 5 and out["warnings"][0]["code"] == "opening_without_wall"
    assert out["totals"]["IfcDoor"]["count"] == 1


def test_route_ifc_download_is_a_reopenable_ifc_file(fdb):
    resp = run(R.bim_ifc("plan_1", 0, **NONE, inline=False, user=USER))
    assert resp.media_type == "application/x-step"
    assert ".ifc" in resp.headers["content-disposition"] and "Moradia" in resp.headers["content-disposition"]
    body = resp.body.decode()
    assert body.startswith("ISO-10303-21;") and "IFC4X3" in body
    assert len(ifcopenshell.file.from_string(body).by_type("IfcWall")) == 5


def test_route_respects_parameters(fdb):
    out = run(R.bim_summary("plan_1", 0, **{**NONE, "wall_height": 3.0}, user=USER))
    assert out["params"]["wall_height"] == 3.0


def test_route_refuses_other_users_and_uncalibrated_plans(fdb):
    with pytest.raises(HTTPException) as e:
        run(R.bim_summary("plan_1", 0, **NONE, user={"user_id": "intruso"}))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        run(R.bim_ifc("plan_nocal", 0, **NONE, inline=False, user=USER))
    assert e.value.status_code == 422 and "calibrada" in e.value.detail
