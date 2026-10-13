"""Lot 5 — tests déterministes de la vérification bois EN 1995-1-1."""
from engines import structuro_ec5 as ec5


def test_catalog_and_kmod():
    c = ec5.catalog()
    assert "C24" in [x["key"] for x in c["classes"]]
    assert c["gamma_m"]["solid"] == 1.3
    assert ec5.kmod_value("1", "medium") == 0.80
    assert ec5.kmod_value("3", "permanent") == 0.50


def test_bending_shear_c24():
    cls = ec5.CLASSES["C24"]
    r = ec5.verify(10, 15, b_m=0.10, h_m=0.22, fm_k=cls["fm_k"], fv_k=cls["fv_k"],
                   E0_05=cls["E0_05"], kmod=0.8, gamma_m=1.3, kind="solid")
    assert abs(r["bending"]["sigma_m_d_mpa"] - 12.40) < 0.3   # W=b·h²/6
    assert abs(r["bending"]["fm_d_mpa"] - 14.77) < 0.1        # 0.8·24/1.3
    assert r["bending"]["utilisation"]["status"] in ("ok", "proche")
    assert r["shear"]["utilisation"]["ratio"] > 0
    assert r["execution_ready"] is False


def test_stability_requires_lef():
    cls = ec5.CLASSES["C24"]
    r = ec5.verify(10, 0, b_m=0.10, h_m=0.22, fm_k=cls["fm_k"], fv_k=cls["fv_k"],
                   E0_05=cls["E0_05"], kmod=0.8, gamma_m=1.3)
    assert r["lateral_torsional"]["utilisation"]["status"] == "non_calcule"


def test_stability_with_lef():
    cls = ec5.CLASSES["C24"]
    r = ec5.verify(10, 0, b_m=0.10, h_m=0.22, fm_k=cls["fm_k"], fv_k=cls["fv_k"],
                   E0_05=cls["E0_05"], kmod=0.8, gamma_m=1.3, lef_m=4.0)
    assert r["lateral_torsional"]["kcrit"] <= 1.0
    assert r["lateral_torsional"]["utilisation"]["status"] in ("ok", "proche", "a_revoir")


def test_design_study_from_envelope():
    model = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.10, "height_m": 0.22}]}
    result = {"cases": [{"id": "ELU1", "label": "ELU", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 10.0, "shear_max_kn": 12.0}]}]}
    out = ec5.design_study(model, result, {"strength_class": "C24", "service_class": "1", "load_duration": "medium"})
    assert out["elements"][0]["status"] == "ok"
    assert "kmod=0.8" in out["note"]
