"""Medição por faces entre camadas: laje fechada pelas paredes (Revit/BEGT) e leitura das etiquetas AI/AS impressas."""
import io

import ezdxf

from engines.metre.coffrage_dxf import coffrage_takeoff


def _dxf() -> bytes:
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6                     # metros
    msp = doc.modelspace()
    W, S = "BEGT - Coffrage - Murs coupé", "BEGT - Coffrage - Dalle"
    # caixa 10 × 6 m com paredes de 20 cm: só as paredes fecham os contornos; a camada laje tem um único traço solto
    for x0, y0, x1, y1 in ((0, 0, 10, 0), (0, 0.2, 10, 0.2), (0, 6, 10, 6), (0, 5.8, 10, 5.8),
                           (0, 0, 0, 6), (0.2, 0.2, 0.2, 5.8), (10, 0, 10, 6), (9.8, 0.2, 9.8, 5.8)):
        msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": W})
    msp.add_line((0.2, 3), (9.8, 3), dxfattribs={"layer": S})
    msp.add_text("20", dxfattribs={"layer": "A-FLOR-IDEN", "insert": (5, 1)})
    msp.add_text("96,14 NGF", dxfattribs={"layer": "A-FLOR-IDEN", "insert": (5, 1.3)})
    msp.add_text("Ai: 95,94 NGF", dxfattribs={"layer": "TEXT", "insert": (5, 4)})
    buf = io.StringIO(); doc.write(buf)
    return buf.getvalue().encode()


def test_slab_closed_by_walls_is_measured_and_labels_read():
    r = coffrage_takeoff(_dxf())
    slab, walls = r["elements"]["slab"], r["elements"]["walls"]
    assert abs(slab["net_area_m2"] - 60.0) < 0.05                       # 10 × 6 m (laje cobre os topos das paredes)
    assert abs(walls["plan_area_m2"] - (60.0 - 9.6 * 5.6)) < 0.05       # coroa de 20 cm
    lp = r["levels_printed"]
    assert lp["dominant"] == {"as_plancher_haut_m": 96.14, "epaisseur_dalle_m": 0.2}
    assert lp["slab_tags"][0]["ai_ngf"] == 95.94 and lp["ai_texts"][0]["ngf"] == 95.94
    assert any("faces entre camadas" in f["subject"].lower() for f in r["findings"])
