"""Estudo estrutural de moradia — cálculo e PDF (sem IA)."""
from engines import structuro_house as H
from engines.structuro_house_pdf import build_pdf

GEO = {"name": "Teste", "outer_L_m": 11.14, "outer_W_m": 7.35, "interior_walls_x": [5.6],
       "basement": {"present": True, "height_m": 2.04},
       "levels": [{"name": "R/C", "storey_height_m": 3.0, "use": "garagem"},
                  {"name": "1.º piso", "storey_height_m": 2.75, "use": "habitacao"}],
       "openings": [{"level": "R/C", "facade": "frente", "width_m": 2.5}],
       "stair": {"present": True, "cage_length_m": 2.3, "cage_width_m": 1.8},
       "soil": {"q_els_kpa": 200, "confirmed": True}}


def test_compute_full():
    r = H.compute(GEO)
    assert len(r["slabs"]) == 3 and all(s["h"] >= 0.18 for s in r["slabs"])
    assert all(d["ld"]["ok"] for s in r["slabs"] for d in s["panels"])
    assert set(r["footings"]) == {"frente", "tras", "esquerda", "direita", "PX1"}
    assert r["footings"]["PX1"]["b_m"] >= r["footings"]["frente"]["b_m"]
    assert r["lintels"][0]["ok"] and r["lintels"][0]["h"] >= 0.25
    assert 25 <= r["quantities"]["ratio_kg_m3"] <= 80
    assert any("sísmica" in w for w in r["warnings"])


def test_no_soil_no_footings():
    r = H.compute({**GEO, "soil": {"q_els_kpa": None}})
    assert r["footings"] == {} and len(r["footing_table"]) == 4


def test_labels_pt():
    assert H.pt_bars(3.85)["label"] == "Ø10//0,20"
    assert H.fmt_s(0.175) == "0,175"


def test_pdf_pages():
    pdf = build_pdf(H.compute(GEO), "Teste")
    assert pdf[:4] == b"%PDF" and len(pdf) > 15000
