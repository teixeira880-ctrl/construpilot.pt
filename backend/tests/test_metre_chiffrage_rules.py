"""Règles de métreur et cohérence du chiffrage (déterministe, sans serveur)."""
import pytest

from engines import estimation as est

PPM = 100.0   # 100 px = 1 m


def _descr(**kw):
    from routes.plans_analysis import _compute_descriptif
    return _compute_descriptif(**kw)


def _base_structure(beam_h=None, beam_type=None):
    beam = {"x1": 0, "y1": 0, "x2": 500, "y2": 0}        # 5 m
    if beam_h:
        beam["height_m"] = beam_h
    if beam_type:
        beam["type"] = beam_type
    return {
        "walls": [{"x1": 0, "y1": 100, "x2": 1000, "y2": 100, "type": "porteur"},   # 10 m porteur
                  {"x1": 0, "y1": 600, "x2": 400, "y2": 600, "type": "cloison"}],
        "openings": [{"x1": 200, "y1": 100, "x2": 290, "y2": 100, "kind": "porte"},          # 0,90 m dans le porteur
                     {"x1": 100, "y1": 600, "x2": 220, "y2": 600, "kind": "fenetre"}],      # dans la cloison
        "beams": [beam],
        "floors": [{"points": [[0, 0], [1000, 0], [1000, 800], [0, 800]]}],                # 80 m²
        "columns": [], "footings": [],
    }


def test_beam_under_slab_counts_only_drop():
    d = _descr(structure=_base_structure(), ppm=PPM, rooms=[], wall_height=2.5, dalle_ep=0.20,
               poutre_l=0.20, poutre_h=0.50)
    assert d["beton_poutres_m3"] == pytest.approx(5 * 0.20 * 0.30, abs=1e-3)   # retombée 0,30
    assert d["beton_dalles_m3"] == pytest.approx(80 * 0.20, abs=1e-3)
    assert d["bandes_noyees_ml"] == 0.0


def test_embedded_band_is_not_also_a_beam():
    d = _descr(structure=_base_structure(beam_type="bande_noyee"), ppm=PPM, rooms=[], dalle_ep=0.20,
               poutre_h=0.50)
    assert d["bandes_noyees_ml"] == pytest.approx(5.0)
    assert d["poutres_ml"] == 0.0 and d["beton_poutres_m3"] == 0.0


def test_voile_deducts_only_openings_of_bearing_walls():
    d = _descr(structure=_base_structure(), ppm=PPM, rooms=[], wall_height=2.5, voile_ep=0.20)
    assert d["voiles_vides_deduits_m2"] == pytest.approx(0.90 * 2.15, abs=0.01)
    assert d["beton_voiles_m3"] == pytest.approx((10 * 2.5 - 0.90 * 2.15) * 0.20, abs=0.01)


def test_weighted_steel_ratio():
    d = _descr(structure=_base_structure(), ppm=PPM, rooms=[], dalle_ep=0.20, poutre_h=0.50)
    assert d["acier_ratio_moyen_kg_m3"] == pytest.approx(d["acier_total_kg"] / d["beton_total_m3"], abs=0.1)


def test_descriptif_lines_do_not_double_count():
    from routes.plans_analysis import _descriptif_line_items
    d = _descr(structure=_base_structure(), ppm=PPM, rooms=[], dalle_ep=0.20, poutre_h=0.50)
    lines = _descriptif_line_items(d)
    names = [l["designation"] for l in lines]
    assert not any(n.startswith("Béton coulé") for n in names)
    assert not any(n in ("Poteaux béton", "Semelles / fondations", "Poutres / linteaux") for n in names)
    beton = sum(l["qty"] for l in lines if l["unit"] == "m³")
    assert beton == pytest.approx(d["beton_total_m3"] - d["beton_voiles_m3"], abs=0.02)


@pytest.mark.parametrize("kw", [dict(project_type="renovation_complete", surface=80.0),
                                dict(project_type="renovation_complete", surface=65.0, ceiling_height_m=2.8,
                                     region=None, condition="mauvais")])
def test_price_model_standard_equals_displayed_total(kw):
    r = est.estimate(**kw)
    assert r["price_model"]["standard"]["total"] == pytest.approx(r["total_avg"], abs=0.01)
    assert r["price_model"]["eco"]["total"] <= r["price_model"]["standard"]["total"] <= r["price_model"]["premium"]["total"]
