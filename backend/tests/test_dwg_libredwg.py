"""Conversão DWG → DXF com LibreDWG: reconstrução do DXF a partir do JSON do LibreDWG, ordem dos conversores e,
se houver um DWG real indicado em CP_SAMPLE_DWG, o circuito completo."""
import asyncio
import math
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("CLOUDCONVERT_API_BASE", "https://api.cloudconvert.invalid/v2")
os.environ.setdefault("CLOUDCONVERT_SYNC_BASE", "https://sync.cloudconvert.invalid/v2")

ezdxf = pytest.importorskip("ezdxf")

from engines import dwg_convert
from engines import dwg_libredwg as D


def P(x, y, z=None):
    return {"x": x, "y": y} if z is None else {"x": x, "y": y, "z": z}


def sample():
    return {
        "header": {"INSUNITS": 4, "EXTMIN": P(1000, 2000, 0), "EXTMAX": P(1100, 2080, 0)},
        "layers": [{"name": "PAREDES", "colorIndex": 1, "off": False, "frozen": False},
                   {"name": "OCULTA", "colorIndex": 3, "off": True, "frozen": False}],
        "entities": [
            {"type": "LINE", "layer": "PAREDES", "colorIndex": 256, "startPoint": P(1000, 2000, 0), "endPoint": P(1010, 2000, 0)},
            {"type": "LWPOLYLINE", "layer": "PAREDES", "flag": 1, "elevation": 0,
             "vertices": [{"x": 1000, "y": 2010, "bulge": 0}, {"x": 1004, "y": 2010, "bulge": 1}, {"x": 1004, "y": 2014, "bulge": 0}]},
            {"type": "ARC", "layer": "0", "center": P(1050, 2050, 0), "radius": 2, "startAngle": 0, "endAngle": math.pi / 2,
             "extrusionDirection": P(0, 0, 1)},
            # Círculo espelhado: centro em OCS com Z para baixo → x do mundo = −x OCS.
            {"type": "CIRCLE", "layer": "0", "center": P(-1060, 2060, 0), "radius": 1, "extrusionDirection": P(0, 0, -1)},
            {"type": "TEXT", "layer": "0", "text": "SALA", "startPoint": P(1002, 2005), "endPoint": P(0, 0), "textHeight": 0.5,
             "rotation": math.pi / 2, "halign": 0, "valign": 0},
            {"type": "MTEXT", "layer": "0", "text": "ZONA\\P10 m2", "insertionPoint": P(1020, 2020, 0), "textHeight": 1,
             "attachmentPoint": 1, "direction": P(1, 0, 0)},
            {"type": "INSERT", "layer": "0", "name": "*U7", "insertionPoint": P(1080, 2030, 0), "xScale": 2, "yScale": 2,
             "zScale": 1, "rotation": math.pi},
            {"type": "HATCH", "layer": "PAREDES", "solidFill": 1, "patternName": "SOLID", "extrusionDirection": P(0, 0, 1),
             "boundaryPaths": [{"boundaryPathTypeFlag": 1, "edges": [
                 {"type": 1, "start": P(1030 + 10 * math.cos(math.radians(30)), 2030 - 10 * math.sin(math.radians(30))),
                  "end": P(1030, 2030)},
                 {"type": 1, "start": P(1030, 2030), "end": P(1040, 2030)},
                 # arco horário de 0° a −30°, guardado como no DWG (ângulos simétricos)
                 {"type": 2, "center": P(1030, 2030), "radius": 10, "startAngle": 0.0, "endAngle": math.radians(30), "isCCW": 0},
             ]}]},
            {"type": "MULTILEADER", "layer": "0"},
        ],
        "blocks": {"*U7": {"basePoint": P(0, 0, 0), "entities": [
            {"type": "LINE", "layer": "0", "startPoint": P(0, 0, 0), "endPoint": P(1, 0, 0)},
            {"type": "ATTDEF", "layer": "0"}]}},
    }


def test_json_to_dxf_rebuilds_geometry():
    data, stats = D.json_to_dxf(sample())
    assert stats["skipped"] == {"MULTILEADER": 1} and not stats["failed"]
    assert stats["units_hint"] == "m"                          # textos de 0,5 a 1 unidade "em mm": é um desenho em metros
    doc = ezdxf.read(__import__("io").StringIO(data.decode()))
    msp = doc.modelspace()
    assert doc.header["$INSUNITS"] == 4 and doc.layers.get("OCULTA").is_off()
    arc = msp.query("ARC")[0]
    assert (arc.dxf.start_angle, arc.dxf.end_angle) == (pytest.approx(0), pytest.approx(90))
    pl = msp.query("LWPOLYLINE")[0]
    assert pl.closed and pl.has_arc
    assert msp.query("TEXT")[0].dxf.rotation == pytest.approx(90)
    ins = msp.query("INSERT")[0]
    assert ins.dxf.name == "ANON_U7" and ins.dxf.xscale == 2 and ins.dxf.rotation == pytest.approx(180)
    assert len(doc.blocks.get("ANON_U7")) == 1                 # ATTDEF não é desenhado


def test_mirrored_entities_land_in_world_coordinates():
    from ezdxf import bbox

    from engines.plan_dxf import _compute_bounds

    data, _ = D.json_to_dxf(sample())
    doc = ezdxf.read(__import__("io").StringIO(data.decode()))
    circle = doc.modelspace().query("CIRCLE")[0]
    b = bbox.extents([circle])
    assert b.center.x == pytest.approx(1060) and b.center.y == pytest.approx(2060)
    assert _compute_bounds([circle])[0] == pytest.approx(1059)        # e não −1061 (coordenada OCS)


def test_clockwise_hatch_arc_follows_the_boundary():
    from ezdxf.path import from_hatch

    data, _ = D.json_to_dxf(sample())
    doc = ezdxf.read(__import__("io").StringIO(data.decode()))
    pts = [p for path in from_hatch(doc.modelspace().query("HATCH")[0]) for p in path.flattening(0.01)]
    assert min(p.y for p in pts) == pytest.approx(2030 - 10 * math.sin(math.radians(30)), abs=0.05)
    assert max(p.y for p in pts) == pytest.approx(2030, abs=1e-6)     # nada acima da corda: o arco desce


def test_units_hint_only_for_implausible_millimetres():
    s = sample()
    s["header"]["INSUNITS"] = 6
    assert "units_hint" not in D.json_to_dxf(s)[1]
    s = sample()
    for e in s["entities"]:
        if e["type"] in ("TEXT", "MTEXT"):
            e["textHeight"] = 250.0
    assert "units_hint" not in D.json_to_dxf(s)[1]


def test_converter_order_libredwg_then_cloud():
    with patch.dict(os.environ, {"ODA_FILE_CONVERTER": "", "APS_DWG_ENABLED": "false", "CLOUDCONVERT_API_KEY": ""}), \
            patch.object(D, "available", return_value=True), \
            patch.object(D, "dwg_to_dxf", return_value=(b"0\nSECTION\n", {"provider": "libredwg"})):
        prov = {}
        assert asyncio.run(dwg_convert.dwg_to_dxf(b"AC1018xxxx", provenance=prov)) == b"0\nSECTION\n"
        assert prov["provider"] == "libredwg"
    with patch.dict(os.environ, {"ODA_FILE_CONVERTER": "", "APS_DWG_ENABLED": "false", "CLOUDCONVERT_API_KEY": ""}), \
            patch.object(D, "available", return_value=True), \
            patch.object(D, "dwg_to_dxf", side_effect=RuntimeError("versão não suportada")):
        prov = {}
        with pytest.raises(RuntimeError, match="DXF"):              # sem conversor externo: mensagem para exportar em DXF
            asyncio.run(dwg_convert.dwg_to_dxf(b"AC1018xxxx", provenance=prov))
        assert "versão" in prov["libredwg_error"]
    with patch.dict(os.environ, {"ODA_FILE_CONVERTER": "/opt/oda"}), patch.object(dwg_convert, "_local_dwg_to_dxf",
                                                                                   return_value=b"oda") as oda, \
            patch.object(D, "dwg_to_dxf") as lib:
        assert asyncio.run(dwg_convert.dwg_to_dxf(b"AC1018xxxx")) == b"oda"
        oda.assert_called_once()
        lib.assert_not_called()


SAMPLE = os.environ.get("CP_SAMPLE_DWG")


@pytest.mark.skipif(not (SAMPLE and D.available()), reason="defina CP_SAMPLE_DWG e instale tools/dwg2json")
def test_real_dwg_end_to_end():
    from engines.plan_dxf import process_dxf

    data = open(SAMPLE, "rb").read()  # noqa: SIM115
    dxf, stats = D.dwg_to_dxf(data)
    assert stats["written"] > 0 and not stats["failed"]
    page = process_dxf(dxf, "sample.dxf", stats.get("units_hint"))["pages"][0]
    assert page["text_blocks"] and page["vectors_total"] > 0
