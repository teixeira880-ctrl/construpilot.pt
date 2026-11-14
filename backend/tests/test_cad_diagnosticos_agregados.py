"""14/11 Valpaços: 263 212 diagnósticos NON_PLANAR_GEOMETRY iguais (16 MB) impediam guardar a planta. Agora: entidades em
espelho (extrusão 0,0,-1) não contam, e as inclinadas dão um só diagnóstico por tipo, com contador."""
import ezdxf
from engines.cad_geometry import walk_entities


def test_espelho_nao_conta_e_inclinadas_agregadas():
    doc = ezdxf.new()
    msp = doc.modelspace()
    for i in range(500):
        msp.add_lwpolyline([(i, 0), (i, 1)], dxfattribs={"extrusion": (0, 0, -1)})
    for i in range(300):
        msp.add_circle((i, 5), 0.5, dxfattribs={"extrusion": (0, 0.6, 0.8)})
    diag = []
    list(walk_entities(doc, diagnostics=diag))
    np_ = [d for d in diag if d.get("code") == "NON_PLANAR_GEOMETRY"]
    assert len(np_) == 1 and np_[0]["entity"] == "CIRCLE" and np_[0]["count"] == 300
