"""Regra AI/AS (Martinho, 22/11/2026): sem etiqueta de laje, a AI vem dos textos «Ai:» impressos; a base das paredes vem da AS
da laje do piso inferior, lida na planta desse piso (base_plan_id)."""
import io

import ezdxf

from engines.metre.volumes_run import _base_from_lower_floor
from engines.metre.volumes_tool import compute_volumes


def _floor(texts, slab_tags=()):
    doc = ezdxf.new(); doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    W = "BEGT - Coffrage - Murs coupé"
    for x0, y0, x1, y1 in ((0, 0, 10, 0), (0, 0.2, 10, 0.2), (0, 6, 10, 6), (0, 5.8, 10, 5.8),
                           (0, 0, 0, 6), (0.2, 0.2, 0.2, 5.8), (10, 0, 10, 6), (9.8, 0.2, 9.8, 5.8)):
        msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": W})
    for i, t in enumerate(texts):
        msp.add_text(t, dxfattribs={"layer": "TEXT", "insert": (2 + i, 3)})
    for i, (cm, ngf) in enumerate(slab_tags):
        msp.add_text(str(cm), dxfattribs={"layer": "A-FLOR-IDEN", "insert": (5 + 3 * i, 1)})
        msp.add_text(f"{ngf} NGF".replace(".", ","), dxfattribs={"layer": "A-FLOR-IDEN", "insert": (5 + 3 * i, 1.3)})
    buf = io.StringIO(); doc.write(buf)
    return buf.getvalue().encode()


def test_base_from_lower_floor_reads_dominant_as():
    b = _base_from_lower_floor(_floor([], [(23, 89.26), (23, 89.26), (20, 89.16)]))
    assert b["m"] == 89.26 and "piso inferior" in b["source"]


def test_wall_height_from_ai_texts_and_lower_floor_as():
    rdc = _floor(["Ai: 92,77 NGF", "Ai: 92,77 NGF", "Ai: 92,65 NGF"])
    r = compute_volumes(rdc, None, None, None, None, {"m": 89.26, "source": "AS do PH-1"})
    assert r["heights"]["ai_plancher_haut_m"] == 92.77
    assert r["heights"]["h_murs_m"] == 3.51
    walls = next(line for line in r["lines"] if line["element"].startswith("Paredes"))
    assert walls["net"] and walls["net"] > 0


def test_without_base_wall_height_stays_indeterminate():
    r = compute_volumes(_floor(["Ai: 92,77 NGF"]), None, None, None, None, None)
    assert r["heights"]["h_murs_m"] is None and "nível de base das paredes" in r["heights"]["missing"]
