"""EN 1992-1-1 §8.4/§8.7 : ancrages et recouvrements à partir du ferraillage proposé."""
from engines import structuro_anchorage as anc


def test_anchorage_basic_c25_b500():
    r = anc.anchorage(16, fck=25, fyk=500, as_req_cm2=4.0, as_prov_cm2=4.02, cover_mm=30)
    # fctm(25)=2.565, fctk05=1.796, fctd=1.197, fbd=2.25·1·1·1.197=2.69 MPa
    assert abs(r["fbd_mpa"] - 2.69) < 0.1
    # lb,rqd = (16/4)·(435/2.69) ≈ 647 mm
    assert abs(r["lb_rqd_mm"] - 647) < 20
    assert r["lbd_mm"] >= r["lb_min_mm"] > 0
    assert r["l0_mm"] >= r["lbd_mm"]        # recouvrement ≥ ancrage (α6 ≥ 1)
    assert r["execution_ready"] is False


def test_poor_bond_increases_length():
    good = anc.anchorage(20, fck=30, bond="good")
    poor = anc.anchorage(20, fck=30, bond="poor")
    assert poor["lbd_mm"] > good["lbd_mm"]   # η1=0.7 → fbd plus faible → lbd plus long


def test_lap_alpha6_from_rho1():
    low = anc.anchorage(16, rho1_pct=25)     # α6 = 1.0
    high = anc.anchorage(16, rho1_pct=100)   # α6 = min(√4, 1.5) = 1.5
    assert abs(low["alpha6"] - 1.0) < 1e-6
    assert abs(high["alpha6"] - 1.5) < 1e-6
    assert high["l0_mm"] > low["l0_mm"]


def test_anchorage_study_from_envelope():
    model = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.25, "height_m": 0.45}]}
    result = {"cases": [{"id": "ELU1", "label": "ELU", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 120.0, "shear_max_kn": 80.0}]}]}
    out = anc.anchorage_study(model, result, {"fck": 25, "bar_mm": 16, "cover_m": 0.04})
    row = out["elements"][0]
    assert row["status"] == "ok"
    assert row["result"]["lbd_m"] > 0 and row["result"]["l0_m"] > 0


def test_fck_cap():
    import pytest
    with pytest.raises(ValueError):
        anc.anchorage(16, fck=60)


def test_anchorage_study_reinjects_automation_bars():
    model = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.30, "height_m": 0.50}]}
    result = {"input_hash": "h1", "cases": [{"id": "ELU1", "label": "ELU STR",
        "elements": [{"id": "B1", "kind": "beam", "moment_max_knm": 100.0, "shear_max_kn": 40.0}]}]}
    auto = {"output_input_hash": "h1", "designs": [{"element_id": "B1", "kind": "beam",
        "diameter_mm": 20, "count": 3, "as_provided_mm2": 942.5, "stirrup_diameter_mm": 8,
        "asw_provided_mm2_m": 670.0, "stirrup_spacing_mm": 150.0}]}
    out = anc.anchorage_study(model, result, {"fck": 25, "fyk": 500, "cover_m": 0.05, "bar_mm": 12,
        "cot_theta": 2.5, "gamma_c": 1.5, "gamma_s": 1.15, "alpha_cc": 1.0}, auto)
    assert out["reinjected_from_automation"] is True
    row = next(r for r in out["elements"] if r["id"] == "B1")
    assert row["status"] == "ok"
    assert row["reinforcement_source"] == "automation"
    assert row["result"]["bar_mm"] == 20  # Ø choisi réinjecté dans §8
    assert row["bar_label"] == "3Ø20"
