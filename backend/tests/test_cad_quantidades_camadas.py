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


def _quadrado(a=40.0, b=30.0):
    return [(0, 0), (a, 0), (a, b), (0, b)]


def test_estrutura_metalica_calculada_e_decomposta_ate_aos_parafusos():
    from engines import estrutura_metalica as EM
    r = EM.calcular(_quadrado(60.0, 40.0), nome="teste", altitude=416.7)     # 40 m > 30 m → 2 vãos
    assert all(v["util"] <= 1.0 for v in r["perfis"].values() if v)
    assert r["geometria"]["vaos"] == 2 and r["geometria"]["afastamento"] <= 6.0
    m = mapa(r["linhas"])
    assert m["contagem"]["completo"] == len(r["linhas"])
    mats = {t["material"] for t in m["totais"]}
    assert any(x.startswith("Aço S275 — IPE") for x in mats) and any(x.startswith("Aço S275 — HEA") for x in mats)
    assert any("Chumbadouros M24" in x for x in mats) and any("autoperfurante" in x for x in mats)
    assert "Aço A500 em varão" in mats, "o varão das fundações não pode ser lido como perfil (descrição fala em S275)"
    assert all("VENTO e SISMO não verificados" in l["description"] for l in r["linhas"])


def test_estrutura_betao_armado_sobre_contorno_em_l():
    from engines import estrutura_implantacao as EI
    pts = [(0, 0), (30, 0), (30, 15), (15, 15), (15, 30), (0, 30)]
    r = EI.calcular(pts, nome="teste")
    assert r["celulas_sem_laje"] > 0, "o L respeita o contorno, não o retângulo"
    assert mapa(r["linhas"])["contagem"]["completo"] == len(r["linhas"])


def test_contorno_e_cota_soleira_lidos_do_desenho():
    d = _doc()
    m = d.modelspace()
    h = m.add_hatch(dxfattribs={"layer": "SMC_LIMITE CONSTR P0"})
    h.paths.add_polyline_path([(100, 0), (140, 0), (140, 30), (100, 30)], is_closed=True)
    m.add_text("EDIFÍCIO área implantação: 1200.00m² cota soleira 416.70", dxfattribs={"layer": "SMC_TEXTO"})
    r = medir(d)
    assert r["edificio"]["area_m2"] == 1200.0 and "área de implantação escrita" in r["edificio"]["origem"]
    assert r["altitude_m"] == 416.7


def test_ferramenta_estrutura_registada():
    import os
    for k in ("MONGO_URL", "DB_NAME", "JWT_SECRET"):
        os.environ.setdefault(k, "x" if k != "MONGO_URL" else "mongodb://localhost:27017")
    from routes import assistant
    t = next(t for t in assistant.TOOLS if t.get("name") == "calcular_estrutura_cad")
    assert t["parameters"]["properties"]["sistema"]["enum"] == ["metalica", "betao_armado"]
