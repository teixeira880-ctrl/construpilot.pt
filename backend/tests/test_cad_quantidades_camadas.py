"""14/11 Valpaços: o mapa de quantidades não calculava materiais — o DWG tinha camadas de pavimento/lancil/verdes que
ninguém media. Medição por camadas + perfis-tipo declarados como hipótese."""
import ezdxf

from engines.cad_quantidades_camadas import medir
from engines.mapa_materiais import decompor, mapa


def _doc():
    d = ezdxf.new()
    d.header["$INSUNITS"] = 4                      # declarado mm, desenhado em metros (como Valpaços)
    m = d.modelspace()
    h = m.add_hatch(dxfattribs={"layer": "SMC_PAV BETUMINOSO"})
    h.paths.add_polyline_path([(0, 0), (20, 0), (20, 10), (0, 10)], is_closed=True)        # 200 m²
    h2 = m.add_hatch(dxfattribs={"layer": "SMC_PAVE PERMEAVEL"})
    h2.paths.add_polyline_path([(0, 20), (10, 20), (10, 30), (0, 30)], is_closed=True)     # 100 m²
    m.add_lwpolyline([(0, -1), (50, -1)], dxfattribs={"layer": "LANCIL"})                   # face
    m.add_lwpolyline([(0, -1.15), (50, -1.15)], dxfattribs={"layer": "LANCIL"})             # tardoz (15 cm)
    m.add_lwpolyline([(0, -5), (30, -5)], dxfattribs={"layer": "LANCIL"})                   # lancil simples
    m.add_lwpolyline([(0, 50), (40, 50)], dxfattribs={"layer": "muro"})                     # levantamento (existente)
    m.add_lwpolyline([(0, 60), (5, 60)], dxfattribs={"layer": "SMC_LIMITE LOTE"})
    m.add_text("PAVIMENTO 200.00 m²", dxfattribs={"layer": "SMC_TEXTO"})
    return d


def test_mede_camadas_com_unidades_confirmadas_pelas_areas_escritas():
    r = medir(_doc())
    q = {l["classe"]: l for l in r["linhas"]}
    assert "em m" in r["unidades"] and abs(r["fator_m"] - 1.0) < 1e-9
    assert abs(q["betuminoso"]["qty"] - 200) < 0.01 and q["betuminoso"]["unit"] == "m2"
    assert abs(q["pave_drenante"]["qty"] - 100) < 0.01
    assert abs(q["lancil"]["qty"] - 80) < 0.01, "face+tardoz contam uma vez: 50 + 30"
    assert "SMC_PAV BETUMINOSO" in q["betuminoso"]["description"]
    assert any(x["camada"] == "muro" for x in r["excluidas"]), "camada de levantamento não é orçamentada"


def test_materiais_saem_com_perfil_tipo_declarado():
    m = mapa(medir(_doc())["linhas"])
    tot = {t["material"]: t for t in m["totais"]}
    assert abs(tot["Mistura betuminosa AC 14 surf (e = 5 cm, 2,40 t/m³)"]["quantidade_liquida"] - 24.0) < 1e-6
    assert tot["Blocos de pavê drenante 20×10×8 cm"]["quantidade_encomenda"] == 5150
    assert tot["Lancil de betão 100×25×15 cm (peças de 1 m)"]["quantidade_encomenda"] == 82
    assert all(a["estado"] == "hipotese" and a["perfil_tipo"] for a in m["artigos"])


def test_espessura_escrita_ganha_ao_perfil_tipo():
    a = decompor({"designation": "Pavimento betuminoso AC 14 e=6 cm", "unit": "m2", "qty": 100})
    assert a["estado"] != "hipotese" and any("6 cm" in x["material"] for x in a["materiais"])


def test_ferramenta_registada():
    import os
    for k in ("MONGO_URL", "DB_NAME", "JWT_SECRET"):
        os.environ.setdefault(k, "x" if k != "MONGO_URL" else "mongodb://localhost:27017")
    from routes import assistant
    assert any(t.get("name") == "medir_camadas_cad" for t in assistant.TOOLS)
    assert "medir_camadas_cad" in assistant.INDIVIDUAL_TOOL_NAMES
