"""Leitura de IFC externos para cálculo: ida e volta com o nosso IFC, ficheiro "tipo Revit" (milímetros,
dois pisos, edifício rodado, laje contida no piso de cima, divisória não resistente) e rota de envio."""
import asyncio
import math
import os

import numpy as np
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_bim_ifc_reader")
os.environ.setdefault("JWT_SECRET", "test")

pytest.importorskip("ifcopenshell")
pytest.importorskip("Pynite")
pytest.importorskip("shapely")

import ifcopenshell.api
from test_bim_analysis import house

from engines import bim_core as B
from engines.bim_core import analysis as A
from engines.bim_core import ifc_reader as IR

PPM = 50.0


def _api(_usecase, *a, **k):
    return ifcopenshell.api.run(_usecase, *a, **k)


def third_party_ifc(angle_deg=30.0, origin=(120.0, 45.0), mm=True):
    """Moradia de dois pisos 8 × 6 m, modelada como num programa de arquitetura.

    Paredes 25 cm sob a laje (2,80 m), pilar 30 × 30 a meio, viga 25 × 50 de parede a parede com o topo à face da
    laje, laje 20 cm contida no piso de cima, divisória de 10 cm com LoadBearing = False.
    """
    f = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", f, ifc_class="IfcProject", name="Moradia tipo Revit")
    length = _api("unit.add_si_unit", f, unit_type="LENGTHUNIT", prefix="MILLI" if mm else None)
    _api("unit.assign_unit", f, units=[length])
    model = _api("context.add_context", f, context_type="Model")
    body = _api("context.add_context", f, context_type="Model", context_identifier="Body",
                target_view="MODEL_VIEW", parent=model)
    site = _api("root.create_entity", f, ifc_class="IfcSite", name="Site")
    bld = _api("root.create_entity", f, ifc_class="IfcBuilding", name="Building")
    _api("aggregate.assign_object", f, products=[site], relating_object=project)
    _api("aggregate.assign_object", f, products=[bld], relating_object=site)
    scale = 1000.0 if mm else 1.0
    levels = []
    for name, z in (("Level 0", 0.0), ("Level 1", 3.0), ("Roof", 6.0)):
        st = _api("root.create_entity", f, ifc_class="IfcBuildingStorey", name=name)
        _api("aggregate.assign_object", f, products=[st], relating_object=bld)
        _api("geometry.edit_object_placement", f, product=st, matrix=_m(0, 0, z))
        st.Elevation = z * scale
        levels.append(st)
    a = math.radians(angle_deg)
    ox, oy = origin

    def W(x, y):  # coordenadas locais → mundo (rodado e afastado da origem, como num projeto georreferenciado)
        return ox + x * math.cos(a) - y * math.sin(a), oy + x * math.sin(a) + y * math.cos(a)

    def place(el, x, y, z, ang=0.0):
        X, Y = W(x, y)
        _api("geometry.edit_object_placement", f, product=el, matrix=_m(X, Y, z, a + ang))

    els = {}
    for k in (0, 1):
        e, st = 3.0 * k, levels[k]
        contained = []
        for i, (x1, y1, x2, y2) in enumerate(((0, 0, 8, 0), (8, 0, 8, 6), (8, 6, 0, 6), (0, 6, 0, 0))):
            w = _api("root.create_entity", f, ifc_class="IfcWall", name=f"Parede {k}.{i}")
            rep = _api("geometry.add_wall_representation", f, context=body, length=math.hypot(x2 - x1, y2 - y1),
                       height=2.8, thickness=0.25, offset=-0.125)
            _api("geometry.assign_representation", f, product=w, representation=rep)
            place(w, x1, y1, e, math.atan2(y2 - y1, x2 - x1))
            contained.append(w)
        part = _api("root.create_entity", f, ifc_class="IfcWall", name=f"Divisória {k}")
        rep = _api("geometry.add_wall_representation", f, context=body, length=3.0, height=2.8, thickness=0.10, offset=-0.05)
        _api("geometry.assign_representation", f, product=part, representation=rep)
        place(part, 6, 0, e, math.pi / 2)
        ps = _api("pset.add_pset", f, product=part, name="Pset_WallCommon")
        _api("pset.edit_pset", f, pset=ps, properties={"LoadBearing": False})
        contained.append(part)
        col = _api("root.create_entity", f, ifc_class="IfcColumn", name=f"Pilar {k}")
        prof = _api("profile.add_parameterized_profile", f, ifc_class="IfcRectangleProfileDef")
        prof.XDim = prof.YDim = 0.30 * scale
        rep = _api("geometry.add_profile_representation", f, context=body, profile=prof, depth=2.8)
        _api("geometry.assign_representation", f, product=col, representation=rep)
        place(col, 4, 3, e)
        contained.append(col)
        beam = _api("root.create_entity", f, ifc_class="IfcBeam", name=f"Viga {k}")
        rep = _api("geometry.add_wall_representation", f, context=body, length=8.0, height=0.5, thickness=0.25, offset=-0.125)
        _api("geometry.assign_representation", f, product=beam, representation=rep)
        place(beam, 0, 3, e + 2.5)
        contained.append(beam)
        slab = _api("root.create_entity", f, ifc_class="IfcSlab", name=f"Laje {k + 1}", predefined_type="FLOOR")
        rep = _api("geometry.add_slab_representation", f, context=body, depth=0.2,
                   polyline=[(-0.125, -0.125), (8.125, -0.125), (8.125, 6.125), (-0.125, 6.125)])
        _api("geometry.assign_representation", f, product=slab, representation=rep)
        place(slab, 0, 0, e + 2.8)
        _api("spatial.assign_container", f, products=contained, relating_structure=st)
        _api("spatial.assign_container", f, products=[slab], relating_structure=levels[k + 1])
        els[k] = {"beam": beam.GlobalId, "column": col.GlobalId, "partition": part.GlobalId}
    return f, els


def _m(x, y, z, ang=0.0):
    m = np.eye(4)
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = math.cos(ang), -math.sin(ang), math.sin(ang), math.cos(ang)
    m[:3, 3] = (x, y, z)
    return m


def roundtrip(f):
    return IR.open_ifc(f.to_string().encode())


def test_our_own_ifc_reads_back_to_the_same_analysis():
    m = B.from_takeoff(house(), PPM, plan_id="plan_1")
    f = B.build_ifc(m)
    m2, st = IR.read(roundtrip(f))
    assert len(st) == 1 and st[0]["columns"] == 1 and st[0]["beams"] == 1
    assert m2.counts()["walls"] == 4 and m2.params["wall_height"] == pytest.approx(2.7)
    assert any(w["code"] == "slab_from_floor" for w in m2.warnings)
    r0, r = A.analyze(m), A.analyze(m2)
    for k in ("m_span_knm", "m_support_knm", "v_kn", "deflection_mm"):
        assert r["beams"][0][k] == pytest.approx(r0["beams"][0][k], rel=0.01)
    assert r["columns"][0]["n_ed_kn"] == pytest.approx(r0["columns"][0]["n_ed_kn"], rel=0.01)
    assert r["beams"][0]["guid"] == f.by_type("IfcBeam")[0].GlobalId
    assert r["columns"][0]["guid"] == f.by_type("IfcColumn")[0].GlobalId


def test_third_party_storeys_units_and_load_bearing():
    f, els = third_party_ifc()
    m, st = IR.read(roundtrip(f))
    assert [s["name"] for s in st] == ["Level 0", "Level 1", "Roof"]
    assert [s["elevation"] for s in st] == [0.0, 3.0, 6.0]
    assert st[0]["columns"] == st[1]["columns"] == 1 and st[2]["columns"] == st[2]["beams"] == 0
    assert m.storey_name == "Level 0" and m.params["wall_height"] == pytest.approx(3.0)
    assert not m.warnings                                       # laje do teto encontrada no piso de cima
    walls = {w.source_id: w for w in m.walls}
    assert walls[els[0]["partition"]].load_bearing is False
    assert sum(w.load_bearing for w in m.walls) == 4
    assert all(w.thickness == pytest.approx(0.25, abs=1e-3) for w in m.walls if w.load_bearing)
    c = m.columns[0]
    assert (c.dx, c.dy) == (pytest.approx(0.3, abs=1e-3), pytest.approx(0.3, abs=1e-3))
    b = m.beams[0]
    assert b.length == pytest.approx(8.0, abs=0.01) and b.depth == pytest.approx(0.5, abs=1e-3)
    assert m.slabs[0].area == pytest.approx(8.25 * 6.25, rel=0.01)


def test_rotation_and_units_do_not_change_results():
    fa, _ = third_party_ifc(angle_deg=0.0, origin=(0.0, 0.0), mm=False)
    fb, eb = third_party_ifc(angle_deg=30.0, origin=(120.0, 45.0), mm=True)
    ra = A.analyze(IR.read(roundtrip(fa), 1)[0])
    rb = A.analyze(IR.read(roundtrip(fb), 1)[0])
    for k in ("m_span_knm", "m_support_knm", "v_kn", "deflection_mm"):
        assert rb["beams"][0][k] == pytest.approx(ra["beams"][0][k], rel=0.01)
    assert rb["beams"][0]["guid"] == eb[1]["beam"] and rb["columns"][0]["guid"] == eb[1]["column"]
    assert ra["beams"][0]["spans_m"] == [pytest.approx(4.0, abs=0.01)] * 2


def test_column_loads_from_upper_storeys_are_carried_down():
    f, els = third_party_ifc()
    _, _, top = IR.analyze_storey(roundtrip(f), 1)
    _, _, low = IR.analyze_storey(roundtrip(f), 0)
    c_top, c_low = top["columns"][0], low["columns"][0]
    assert "n_ed_above_kn" not in c_top and low["storeys_above_carried"] == ["Level 1"]
    assert c_low["n_ed_above_kn"] == pytest.approx(c_top["n_ed_kn"])
    assert c_low["n_ed_kn"] == pytest.approx(c_low["n_ed_own_kn"] + c_top["n_ed_kn"], rel=1e-3)
    assert c_low["utilization"] > c_top["utilization"] and c_low["guid"] == els[0]["column"]


def test_georeferenced_coordinates_are_moved_near_origin():
    f, _ = third_party_ifc(origin=(487250.0, 4290120.0))
    m, _ = IR.read(roundtrip(f))
    assert m.origin[0] > 487000 and all(0 <= c.cx < 20 and 0 <= c.cy < 20 for c in m.columns)
    assert A.analyze(m)["beams"][0]["spans_m"] == [pytest.approx(4.0, abs=0.01)] * 2


def test_bad_input_is_refused():
    with pytest.raises(B.ModelError):
        IR.open_ifc(b"not an ifc")
    f, _ = third_party_ifc()
    with pytest.raises(B.ModelError):
        IR.read(roundtrip(f), 7)


# ---------------- rota ----------------

R = pytest.importorskip("routes.bim")
from fastapi import HTTPException


class _Upload:
    def __init__(self, data, name="modelo.ifc"):
        self.data, self.filename = data, name

    async def read(self, n=-1):
        return self.data if n < 0 else self.data[:n]


LOADS = {"imposed_kn_m2": None, "finishes_kn_m2": None, "partitions_kn_m2": None, "fck": None}


def test_route_ifc_analysis():
    f, els = third_party_ifc()
    out = asyncio.run(R.bim_ifc_analysis(_Upload(f.to_string().encode()), storey=None, **LOADS, user={"user_id": "u1"}))
    assert out["origin"] == "ifc" and out["storey"]["name"] == "Level 0" and len(out["storeys"]) == 3
    assert out["beams"][0]["guid"] == els[0]["beam"] and out["columns"][0]["n_ed_above_kn"] > 0
    upper = asyncio.run(R.bim_ifc_analysis(_Upload(f.to_string().encode()), storey=1, **LOADS, user={"user_id": "u1"}))
    assert upper["beams"][0]["guid"] == els[1]["beam"]
    with pytest.raises(HTTPException) as e:
        asyncio.run(R.bim_ifc_analysis(_Upload(b"xx"), storey=None, **LOADS, user={"user_id": "u1"}))
    assert e.value.status_code == 422
