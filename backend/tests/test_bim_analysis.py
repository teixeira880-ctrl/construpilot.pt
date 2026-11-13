"""Pré-dimensionamento do pórtico BIM (PyNite): esforços conferidos com fórmulas clássicas, faixas de influência,
ligações, GUID iguais aos do IFC e rota /analysis com Mongo falso."""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_bim_analysis")
os.environ.setdefault("JWT_SECRET", "test")

pytest.importorskip("ifcopenshell")
pytest.importorskip("Pynite")

from engines import bim_core as B  # noqa: E402
from engines.bim_core import analysis as A  # noqa: E402

PPM = 50.0


def P(m):
    return m * PPM


def wall(i, x1, y1, x2, y2, t="porteur"):
    return {"wall_id": f"w{i}", "x1": P(x1), "y1": P(y1), "x2": P(x2), "y2": P(y2), "type": t}


def single_beam(reverse=False):
    """Viga 5 m entre duas paredes resistentes, sem laje: só peso próprio 25 × 0,20 × 0,40 = 2 kN/m."""
    b = {"beam_id": "b1", "x1": P(0), "y1": P(2), "x2": P(5), "y2": P(2)}
    if reverse:
        b = {**b, "x1": b["x2"], "x2": b["x1"]}
    return {"walls": [wall(1, 0, 0, 0, 4), wall(2, 5, 0, 5, 4)], "beams": [b]}


def house():
    """10 × 8 m, laje 20 cm, viga a meio (y = 4) contínua sobre um pilar 20×20 em x = 5."""
    return {
        "walls": [wall(1, 0, 8, 10, 8), wall(2, 10, 8, 10, 0), wall(3, 10, 0, 0, 0), wall(4, 0, 0, 0, 8)],
        "floors": [{"floor_id": "f1", "points": [[0, 0], [P(10), 0], [P(10), P(8)], [0, P(8)]], "thickness_cm": 20}],
        "columns": [{"column_id": "c1", "x1": P(4.9), "y1": P(3.9), "x2": P(5.1), "y2": P(4.1)}],
        "beams": [{"beam_id": "b1", "x1": P(0), "y1": P(4), "x2": P(10), "y2": P(4)}],
    }


def run_model(structure, **loads):
    m = B.from_takeoff(structure, PPM, plan_id="plan_1")
    return m, A.analyze(m, loads or None)


def test_simply_supported_beam_matches_wl2_over_8():
    _, r = run_model(single_beam())
    b = r["beams"][0]
    w_elu = 1.35 * 2.0
    assert b["spans_m"] == [5.0]
    assert b["m_span_knm"] == pytest.approx(w_elu * 25 / 8, rel=0.01)
    assert b["m_support_knm"] == pytest.approx(0.0, abs=0.05)
    assert b["v_kn"] == pytest.approx(w_elu * 5 / 2, rel=0.01)
    E = A._ecm(25.0) / 3.0                                   # E_ef = Ecm / (1 + φ), φ = 2
    inertia = 0.2 * 0.4 ** 3 / 12
    assert b["deflection_mm"] == pytest.approx(5 * 2.0 * 5 ** 4 / (384 * E * inertia) * 1000, rel=0.02)
    assert b["deflection_limit_mm"] == pytest.approx(20.0)
    assert r["status"] == "ok" and r["execution_ready"] is False


def test_beam_direction_does_not_change_results():
    _, r1 = run_model(single_beam())
    _, r2 = run_model(single_beam(reverse=True))
    for k in ("m_span_knm", "m_support_knm", "v_kn", "deflection_mm"):
        assert r1["beams"][0][k] == pytest.approx(r2["beams"][0][k], rel=1e-6)


def test_continuous_beam_over_column_matches_two_span_formulas():
    _, r = run_model(house())
    b = r["beams"][0]
    assert b["trib_width_m"] == pytest.approx(4.0)                 # 2 m de cada lado até às paredes paralelas
    assert b["w_g_kn_m"] == pytest.approx(25 * 0.2 * 0.2 + (25 * 0.2 + 1.5 + 1.0) * 4)   # retombée + laje
    assert b["w_q_kn_m"] == pytest.approx(2.0 * 4)
    w = 1.35 * b["w_g_kn_m"] + 1.5 * b["w_q_kn_m"]
    assert b["spans_m"] == [5.0, 5.0]
    assert b["m_support_knm"] == pytest.approx(w * 25 / 8, rel=0.03)         # wL²/8 no apoio central
    assert b["m_span_knm"] == pytest.approx(9 * w * 25 / 128, rel=0.03)      # 9wL²/128 no vão
    assert b["v_kn"] == pytest.approx(5 * w * 5 / 8, rel=0.03)
    c = r["columns"][0]
    assert c["n_ed_kn"] == pytest.approx(10 * w * 5 / 8 + 1.35 * 25 * 0.04 * 2.7, rel=0.03)
    assert c["warnings"]                                                    # esbelteza 2,7 / (0,2/√12) > 25
    assert b["as_support_cm2"] > b["as_span_cm2"] > 0
    assert b["utilization"] == max(b["utilization_parts"].values())
    assert b["status"] == "insuficiente"                                    # 20×40 é curta para 2 × 5 m com 4 m de laje


def test_heavier_section_or_lighter_loads_reduce_utilization():
    _, base = run_model(house())
    _, light = run_model(house(), imposed_kn_m2=1.0, partitions_kn_m2=0.0)
    assert light["beams"][0]["utilization"] < base["beams"][0]["utilization"]
    m = B.from_takeoff(house(), PPM, plan_id="plan_1", params={"poutre_h": 0.60, "poutre_l": 0.30})
    big = A.analyze(m)
    assert big["beams"][0]["utilization"] < base["beams"][0]["utilization"]


def test_unsupported_beam_is_excluded_and_reported():
    s = single_beam()
    s["beams"].append({"beam_id": "b_solta", "x1": P(1), "y1": P(3.5), "x2": P(3), "y2": P(3.5)})
    _, r = run_model(s)
    assert [b["source_id"] for b in r["beams"]] == ["b1"]
    assert any(w["code"] == "beam_unsupported" and w["source_id"] == "b_solta" for w in r["warnings"])


def test_secondary_beam_framing_into_main_beam_shares_a_node():
    s = single_beam()
    s["walls"].append(wall(3, 0, 4, 5, 4))
    s["beams"].append({"beam_id": "b2", "x1": P(2.5), "y1": P(2), "x2": P(2.5), "y2": P(4)})   # T sobre b1
    _, r = run_model(s)
    b1 = next(b for b in r["beams"] if b["source_id"] == "b1")
    assert b1["spans_m"] == [2.5, 2.5]                     # b1 dividida no apoio da viga secundária
    _, alone = run_model(single_beam())
    assert b1["m_span_knm"] > alone["beams"][0]["m_span_knm"]   # recebe a reação da secundária


def test_guids_match_the_ifc_elements():
    m, r = run_model(house())
    f = B.build_ifc(m)
    assert r["beams"][0]["guid"] == f.by_type("IfcBeam")[0].GlobalId
    assert r["columns"][0]["guid"] == f.by_type("IfcColumn")[0].GlobalId


def test_model_without_frame_elements_is_refused():
    m = B.from_takeoff({"walls": [wall(1, 0, 0, 5, 0)]}, PPM)
    with pytest.raises(A.AnalysisError):
        A.analyze(m)


# ---------------- rota ----------------

R = pytest.importorskip("routes.bim")
from fake_mongo_pt import FakeDB  # noqa: E402
from fastapi import HTTPException  # noqa: E402

USER = {"user_id": "u1"}
NONE = dict(wall_height=None, voile_ep=None, cloison_ep=None, dalle_ep=None, poutre_l=None, poutre_h=None,
            imposed_kn_m2=None, finishes_kn_m2=None, partitions_kn_m2=None, fck=None)


@pytest.fixture
def fdb(monkeypatch):
    db = FakeDB()
    db.plans_takeoff.docs.append({"plan_id": "plan_1", "user_id": "u1", "structure": {"0": house()},
                                  "calibrations": {"0": {"pixels_per_meter": PPM}}})
    db.plans_takeoff.docs.append({"plan_id": "walls_only", "user_id": "u1",
                                  "structure": {"0": {"walls": [wall(1, 0, 0, 5, 0)]}},
                                  "calibrations": {"0": {"pixels_per_meter": PPM}}})
    monkeypatch.setattr(R, "db", db)
    return db


def test_route_analysis_returns_results_by_guid(fdb):
    out = asyncio.run(R.bim_analysis("plan_1", 0, **NONE, user=USER))
    assert out["counts"]["beams"] == 1 and out["counts"]["columns"] == 1
    assert out["beams"][0]["guid"] and out["max_utilization"] > 0
    lighter = asyncio.run(R.bim_analysis("plan_1", 0, **{**NONE, "imposed_kn_m2": 1.0}, user=USER))
    assert lighter["params"]["imposed_kn_m2"] == 1.0
    assert lighter["beams"][0]["m_support_knm"] < out["beams"][0]["m_support_knm"]


def test_route_analysis_refuses_models_without_frame(fdb):
    with pytest.raises(HTTPException) as e:
        asyncio.run(R.bim_analysis("walls_only", 0, **NONE, user=USER))
    assert e.value.status_code == 422
