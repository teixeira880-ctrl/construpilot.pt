"""Lote 74 PT — preços de referência da estrutura com o coeficiente regional de Portugal."""
from engines import dxf_takeoff as D
from engines.estimation import region_coef


def test_reference_prices_use_pt_coefficient():
    c = region_coef("PT", None)
    assert c < 1
    assert D.PRICES["beton_escalier"] == round(320.0 * c, 2)
    assert D.PRICES["coffrage_poteau"] == round(60.0 * c, 2)
    assert D.PRICES["installation_chantier"] == round(8000.0 * c, 2)


def test_user_prices_keep_priority():
    metre = {"walls_ml": 10.0, "columns_count": 0, "slab_area_m2": 0.0, "beams_ml": 0.0, "detected": {}}
    est = D.cost_structural(metre, {"prices": {"beton_voile": 111.0}})
    blob = str(est)
    assert "111.0" in blob or "111" in blob
