"""Planta com LEADER (cotas de nível com chamada): a leitura não pode falhar por «Invalid DXF attribute "extrusion"»."""
import io

import ezdxf

from engines.plan_dxf import process_dxf


def test_dxf_with_leader_is_read():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for a, b in (((0, 0), (10, 0)), ((10, 0), (10, 6)), ((10, 6), (0, 6)), ((0, 6), (0, 0))):
        msp.add_line(a, b, dxfattribs={"layer": "MURS"})
    msp.add_leader([(2, 2), (4, 4), (5, 4)], dxfattribs={"layer": "COTES"})
    msp.add_text("Ai: 95,94 NGF", dxfattribs={"layer": "TEXT", "insert": (5, 4)})
    buf = io.StringIO(); doc.write(buf)
    out = process_dxf(buf.getvalue().encode(), "piso.dxf")
    assert out["pages"]
