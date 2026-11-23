"""Regra AI/AS (Martinho, 22-23/11/2026): sem etiqueta de laje, a AI vem dos textos «Ai:» de laje impressos; a base das
paredes vem da AS dominante da laje do piso inferior. O teste adapta-se às duas arquiteturas (lower_dxf_bytes no pod,
base_level/base_plan_id no GitHub)."""
import inspect
import io

import ezdxf

from engines.metre.volumes_tool import compute_volumes

_POD = "lower_dxf_bytes" in inspect.signature(compute_volumes).parameters


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


def _volumes(cur, lower):
    if _POD:
        return compute_volumes(cur, None, None, None, None, lower)
    from engines.metre.volumes_run import _base_from_lower_floor
    return compute_volumes(cur, None, None, None, None, _base_from_lower_floor(lower) if lower else None)


def test_wall_height_from_ai_texts_and_lower_floor_as():
    rdc = _floor(["Ai: 92,77 NGF", "Ai: 92,77 NGF", "Ai: 92,65 NGF"])
    ph1 = _floor([], [(23, 89.26), (23, 89.26), (23, 89.26), (20, 89.16)])
    r = _volumes(rdc, ph1)
    assert r["heights"]["ai_plancher_haut_m"] == 92.77
    assert r["heights"]["h_murs_m"] == 3.51
    walls = next(line for line in r["lines"] if line["element"].startswith("Paredes"))
    assert walls["net"] and walls["net"] > 0


def test_lintel_ai_is_not_used_as_slab_ai():
    rdc = _floor(["LT(Ai:56.82)", "LT(Ai:56.82)", "LT(Ai:56.82)", "Ai: 92,77 NGF", "Ai: 92,77 NGF"])
    r = _volumes(rdc, _floor([], [(23, 89.26), (23, 89.26), (23, 89.26)]))
    assert r["heights"]["ai_plancher_haut_m"] == 92.77


def test_without_base_wall_height_stays_indeterminate():
    r = _volumes(_floor(["Ai: 92,77 NGF"]), None)
    assert r["heights"]["h_murs_m"] is None and "nível de base das paredes" in r["heights"]["missing"]
