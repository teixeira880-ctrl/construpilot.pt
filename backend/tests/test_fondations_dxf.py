"""Fundações pelo DWG (23/11/2026, plantas AES/TZ): rótulos fragmentados reagrupados, S = A×B×ht do rótulo, SF = área × ht,
rótulo ilegível fica explícito — nada estimado."""
import io

import ezdxf

from engines.metre.fondations_dxf import fondations_takeoff


def _doc():
    doc = ezdxf.new(); doc.header["$INSUNITS"] = 6
    return doc, doc.modelspace()


def _rect(msp, layer, x, y, a, b):
    for p1, p2 in (((x, y), (x + a, y)), ((x + a, y), (x + a, y + b)), ((x + a, y + b), (x, y + b)), ((x, y + b), (x, y))):
        msp.add_line(p1, p2, dxfattribs={"layer": layer})


def _label(msp, x, y, lines):
    for i, t in enumerate(lines):
        msp.add_text(t, dxfattribs={"layer": "Etiquettes de fondations", "insert": (x, y - 0.4 * i)})


def test_isolated_footing_volume_from_label_fragments():
    doc, msp = _doc()
    _rect(msp, "Fondations", 0, 0, 2.0, 3.5)
    _label(msp, 0.6, 2.4, ["S 4", "200 x 350 x 50 ht", "(As: 50.92 )"])
    r = fondations_takeoff(_bytes(doc))
    row = r["rows"][0]
    assert row["ref"] == "S04" and row["volume_m3"] == 3.5 and row["state"] == "confirmed"
    assert row["as_ngf"] == 50.92 and row["fond_ngf"] == 50.42
    assert r["totals"]["betao_total_m3"] == 3.5


def test_strip_footing_area_times_height():
    doc, msp = _doc()
    _rect(msp, "Fondations", 0, 0, 10.0, 0.5)          # SF de 10 m × 50 cm
    _label(msp, 4.8, 1.0, ["SF 06", "50 x 40 ht", "(As: 50.92 )"])
    r = fondations_takeoff(_bytes(doc))
    row = r["rows"][0]
    assert row["kind"] == "SF" and abs(row["volume_m3"] - 2.0) < 0.01 and abs(row["length_m"] - 10.0) < 0.1


def test_unreadable_label_is_flagged_not_estimated():
    doc, msp = _doc()
    _rect(msp, "Fondations", 0, 0, 2.0, 2.0)
    _label(msp, 0.8, 1.2, ["S 9", "(As: 50.92 )"])     # sem dimensões
    r = fondations_takeoff(_bytes(doc))
    assert r["totals"]["betao_total_m3"] == 0 and r["totals"]["rotulos_ilegiveis"] == 1
    assert any("ilegível" in f["subject"] for f in r["findings"])


def _bytes(doc):
    buf = io.StringIO(); doc.write(buf)
    return buf.getvalue().encode()
