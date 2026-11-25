"""Viabilidade construtiva de terrenos: sol, relevo, riscos, ordenamento, conforto, implantação, IFC, PDF e orquestração
(MDT sintético e serviços externos simulados — sem rede)."""
import asyncio
import math
import os
import re

import numpy as np
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")

from engines.mdt_pt import grelha as GR, pttm06 as TM
from engines.mdt_pt.geotiff import Raster
from engines.viabilidade_pt import bim as BM, conforto as CF, ordenamento as OR, relatorio as RL, riscos as RK
from engines.viabilidade_pt import servico as SV, solar as SO

LAT, LON = 38.7876, -9.3906          # Sintra
XC, YC = TM.ponto_tm(LAT, LON)


def _raster(fz, lado=400.0, res=1.0):
    n = int(lado / res)
    x0, y1 = XC - lado / 2, YC + lado / 2
    X, Y = np.meshgrid(x0 + (np.arange(n) + .5) * res, y1 - (np.arange(n) + .5) * res)
    return Raster(fz(X - XC, Y - YC).astype(np.float32), x0, y1, res, res)


def _encosta_sul(x, y):
    """Encosta a 12 % virada a sul + vale (talvegue) a x = 30 m."""
    return 150 + 0.12 * y + 3 * (1 - np.exp(-((x - 30) / 15) ** 2))


def _plano(x, y):
    return 100 + 0 * x


def _anel(meio_x=30.0, meio_y=25.0, dx=0.0, dy=0.0):
    q = [(-meio_x, -meio_y), (meio_x, -meio_y), (meio_x, meio_y), (-meio_x, meio_y)]
    return [TM.ponto_ll(XC + dx + a, YC + dy + b) for a, b in q]


VIA_SUL = {"ok": True, "fonte": "OpenStreetMap (Overpass)",
           "data": {"a": TM.ponto_ll(XC - 80, YC - 27), "b": TM.ponto_ll(XC + 80, YC - 27), "nome": "Rua de Teste",
                    "tipo": "residential", "distancia_m": 25}}
SRUP_VAZIO = {"ok": True, "data": {"afeta": [], "proximas_60m": [], "por_confirmar": [], "hidricos": []}}
PDM_URBANO = {"ok": True, "data": {"classes": [{"solo": "urbano", "classe": "Solo urbano", "categoria": "Espaço habitacional",
                                                "habitacional": True, "fracao": 1.0}]}}


def _terr(pdm=PDM_URBANO, srup=SRUP_VAZIO):
    return {"geometria": {}, "pdm": pdm, "servidoes": srup, "caop": None, "cadastro": None, "bupi": None, "estado": {}, "alertas": []}


# ------------------------------------------------------------------ sol
def test_posicao_solar_meio_dia_equinocio_e_solsticios():
    # meio-dia solar em Sintra ≈ 12:38 UTC (longitude −9,39° → +37,6 min)
    hs = np.arange(11.0, 14.5, 1 / 60)
    for dia, esperado in ((80, 90 - LAT), (172, 90 - LAT + 23.44), (355, 90 - LAT - 23.44)):
        az, alt = SO.posicao(LAT, LON, dia, hs)
        k = int(np.argmax(alt))
        assert abs(alt[k] - esperado) < 0.8
        assert abs(az[k] - 180) < 2


def test_horizonte_de_um_vale_reduz_o_sol_de_inverno():
    vale = _raster(lambda x, y: 100 + 0.004 * y ** 2 * (np.abs(y) > 30), lado=600, res=4)   # paredes a norte e sul
    m = np.zeros(vale.z.shape, bool)
    m[73:77, 73:77] = True
    H = SO.horizonte(vale, m)
    assert H[18].mean() > 15                    # sul tapado
    plano = _raster(_plano, lado=600, res=4)
    assert SO.horizonte(plano, m).max() < 0.5


def test_irradiacao_encosta_sul_maior_que_encosta_norte():
    from engines.mdt_pt import analise as AN
    out = {}
    for nome, f in (("sul", lambda x, y: 150 + 0.25 * y), ("norte", lambda x, y: 150 - 0.25 * y)):
        r = _raster(f, lado=200, res=2)
        m = AN.mascara_poligono(r, _anel(20, 20))
        d, e = AN.declive_exposicao(r)
        out[nome] = SO.analisar(r, m, d, e, LAT, LON)
    assert out["sul"]["irradiacao_anual_kwh_m2"]["media"] > 1.2 * out["norte"]["irradiacao_anual_kwh_m2"]["media"]
    ref = out["sul"]["referencia_horizontal_livre_kwh_m2"]
    assert 1500 < ref < 2000                    # ordem de grandeza da irradiação global em Lisboa


# ------------------------------------------------------------------ avaliação completa (sem rede)
def test_calcular_encosta_sul_urbana_viavel_com_implantacao():
    r = _raster(_encosta_sul)
    res = SV.calcular(r, {"fonte": "teste", "oficial": False}, _anel(), _terr(), VIA_SUL, {"ok": False},
                      {"iu_max": 0.5, "io_max_pct": 30, "n_pisos_max": 2}, None)
    rel = res["relevo"]
    assert rel["exposicao"] == "S" and 10 < rel["declive_medio_pct"] < 16
    assert res["acessibilidade"]["estado"] == "confinante"
    im = res["implantacao"]
    assert im["ok"] and im["azimute_fachada_principal"] in (165.0, 180.0, 195.0)
    # dentro do terreno e fora dos afastamentos (frontal 5 m a sul)
    xy = np.asarray(im["poligono_tm"])
    assert (xy[:, 1] - YC).min() >= -25 + 5 - 1.5
    assert (np.abs(xy[:, 0] - XC)).max() <= 30 - 3 + 1.5
    assert im["movimento_terras"]["ok"]
    pot = res["ordenamento"]["potencial"]
    assert pot["area_construcao_max_m2"] == 1500.0 and pot["area_implantacao_max_m2"] == 900.0
    assert all(v["resultado"] == "conforme" for v in res["verificacao_edificio"])
    assert res["viabilidade"]["classificacao"] in ("viavel", "viavel_com_condicionantes")
    assert res["camadas"]["aptidao"]["png"].startswith("data:image/png;base64,")
    # o talvegue sintético é detetado e não fica sob o edifício
    assert rel["linhas_agua"]
    pub = SV.publico(res)
    assert "_interno" not in pub and not any(k.startswith("_") for k in pub["relevo"])


def test_pdm_em_falta_nao_inventa_indices_e_marca_pressupostos():
    r = _raster(_plano, lado=200, res=1)
    res = SV.calcular(r, {"fonte": "teste"}, _anel(15, 15), _terr(), {"ok": False, "nota": "sem OSM"}, {"ok": False}, {}, None)
    pot = res["ordenamento"]["potencial"]
    assert pot["estado"] == "sem_dados" and pot["area_construcao_max_m2"] is None
    assert set(res["ordenamento"]["afastamentos"]["pressupostos"]) == {"frontal", "lateral", "tardoz"}
    assert res["acessibilidade"]["estado"] == "por_confirmar"
    # sem via, o maior afastamento (6 m) aplica-se a todo o perímetro: 30×30 → ≈ 18×18
    assert 250 < res["zona_livre"]["area_m2"] < 400


def test_solo_rustico_e_ren_tornam_inviavel():
    r = _raster(_plano, lado=200, res=1)
    anel = _anel(20, 20)
    srup = {"ok": True, "data": {"afeta": [
        {"id": "ren", "titulo": "REN - Áreas de instabilidade de vertentes", "tipo": "REN", "fracao": 0.95,
         "area_afetada_m2": 1520, "distancia_m": 0, "aneis_latlon": [[list(p) for p in anel]]}],
        "proximas_60m": [], "por_confirmar": [], "hidricos": []}}
    pdm = {"ok": True, "data": {"classes": [{"solo": "rustico", "classe": "Solo rústico", "categoria": "Espaço agrícola",
                                             "habitacional": False, "fracao": 1.0}]}}
    res = SV.calcular(r, {"fonte": "teste"}, anel, _terr(pdm, srup), VIA_SUL, {"ok": False}, {}, None)
    assert res["viabilidade"]["classificacao"] == "inviavel_provavel"
    assert not res["implantacao"]["ok"]                      # a REN cobre o terreno: nenhuma zona livre
    v = next(e for e in res["riscos"]["riscos"] if e["risco"] == "movimentos_vertente")
    assert v["nivel"] == "muito_elevado" and v["cartografia_oficial"]


def test_riscos_sem_cartografia_ficam_por_confirmar_nunca_baixo():
    r = _raster(_plano, lado=200, res=1)
    res = SV.calcular(r, {"fonte": "teste"}, _anel(15, 15), _terr(srup={"ok": False}), VIA_SUL, {"ok": False}, {}, None)
    niveis = {e["risco"]: e["nivel"] for e in res["riscos"]["riscos"]}
    assert niveis["cheias_inundacoes"] == "por_confirmar" and niveis["movimentos_vertente"] == "por_confirmar"
    assert res["riscos"]["nivel_global"] == "por_confirmar"


def test_incendio_cartografia_oficial_prevalece():
    rel = {"_decl": np.zeros((10, 10)), "_expo": np.zeros((10, 10)), "forma_dominante": "plano"}
    m = np.ones((10, 10), bool)
    srup = {"ok": True, "data": {"afeta": [{"id": "p", "titulo": "Perigosidade de incêndio rural - classe muito alta",
                                            "tipo": "servidao"}], "proximas_60m": [], "por_confirmar": []}}
    e = RK.incendio(rel, m, srup, "urbano")
    assert e["nivel"] == "muito_elevado" and e["suscetibilidade_mdt"]["nivel"] == "baixo"


def test_conforto_fachada_sul_no_hemisferio_norte():
    f = CF.irradiacao_fachadas(LAT, LON, [0.0] * 36)
    assert f["S"]["inverno_kwh_m2"] > 2 * f["N"]["inverno_kwh_m2"]
    assert f["O"]["verao_kwh_m2"] > f["S"]["verao_kwh_m2"]       # poente de verão aquece mais do que o sul
    assert CF._orientacao_otima(f, None, 0)["fachada"] in ("S", "SE", "SO")


def test_afastamentos_respeitam_minimo_do_codigo_civil():
    a = OR.afastamentos({"afastamento_lateral_min_m": 1.0, "afastamento_frontal_min_m": 3, "afastamento_tardoz_min_m": 4})
    assert a["valores_m"]["lateral"] == 1.5 and a["pressupostos"] == []


# ------------------------------------------------------------------ BIM e PDF
def _resultado():
    r = _raster(_encosta_sul)
    return SV.calcular(r, {"fonte": "teste", "oficial": False}, _anel(), _terr(), VIA_SUL, {"ok": False},
                       {"iu_max": 0.5, "io_max_pct": 30, "n_pisos_max": 2}, None)


def test_ifc_terreno_georreferenciado_e_bem_formado():
    res = _resultado()
    it = res["_interno"]
    b = BM.ifc_terreno(it["r"], it["mascara"], it["anel_tm"], SV.publico(res), "Terreno de teste — Sintra", it["impl"],
                       it["zona_livre_tm"])
    t = b.decode("ascii")
    assert t.startswith("ISO-10303-21;") and t.rstrip().endswith("END-ISO-10303-21;")
    assert "FILE_SCHEMA(('IFC4'))" in t
    for ent in ("IFCPROJECT(", "IFCSITE(", "IFCMAPCONVERSION(", "IFCPROJECTEDCRS('EPSG:3763'", "IFCTRIANGULATEDFACESET(",
                ".TERRAIN.)", "IFCBUILDING(", "IFCEXTRUDEDAREASOLID(", "CP_ViabilidadeTerreno"):
        assert ent in t, ent
    linhas = re.findall(r"^#(\d+)=", t, re.M)
    assert [int(x) for x in linhas] == list(range(1, len(linhas) + 1))
    refs = {int(x) for x in re.findall(r"#(\d+)", t)}
    assert max(refs) <= len(linhas)                          # nenhuma referência pendurada
    guids = re.findall(r"IFC[A-Z]+\('([0-9A-Za-z_$]{22})'", t)
    assert len(guids) == len(set(guids)) and len(guids) >= 8
    # a origem da MapConversion fica no centro do terreno (coordenadas locais pequenas)
    mc = re.search(r"IFCMAPCONVERSION\(#\d+,#\d+,([-\d.]+),([-\d.]+),", t)
    assert abs(float(mc.group(1)) - XC) < 2 and abs(float(mc.group(2)) - YC) < 2
    # determinístico
    b2 = BM.ifc_terreno(it["r"], it["mascara"], it["anel_tm"], SV.publico(res), "Terreno de teste — Sintra", it["impl"],
                        it["zona_livre_tm"])
    assert re.findall(r"'([0-9A-Za-z_$]{22})'", b2.decode()) == re.findall(r"'([0-9A-Za-z_$]{22})'", t)


def test_cadeias_step_acentos_e_apostrofos():
    assert BM._s("Pré'dio") == "'Pr\\X2\\00E9\\X0\\''dio'"
    assert len(BM.guid("a")) == 22 and BM.guid("a") != BM.guid("b")


def test_relatorio_pdf():
    pdf = RL.pdf(_resultado(), "Terreno de teste", {"nome": "Empresa X", "cor": "#123456"})
    assert pdf[:4] == b"%PDF" and len(pdf) > 30_000


# ------------------------------------------------------------------ orquestração assíncrona
def test_avaliar_com_fontes_simuladas(monkeypatch):
    r = _raster(_encosta_sul)

    async def obter(pts, resolucao=None, margem_m=15.0, so_dgt=False):
        return r, {"fonte": "MDT simulado", "oficial": True, "resolucao_m": 1.0}

    async def territorio(pts, prazo):
        return _terr()

    async def via(lat, lon):
        return VIA_SUL

    async def edif(lat, lon):
        # prédio alto a sul do terreno: tapa sol de inverno a parte do terreno
        anel = [list(TM.ponto_ll(XC + a, YC + b)) for a, b in ((-40, -60), (40, -60), (40, -45), (-40, -45))]
        return {"ok": True, "data": {"edificios": [{"latlon": anel, "altura_m": 30.0}]}}

    monkeypatch.setattr(GR, "obter", obter)
    monkeypatch.setattr(SV, "_territorio", territorio)
    monkeypatch.setattr(SV, "_via", via)
    monkeypatch.setattr(SV, "_edificios", edif)
    res = asyncio.run(SV.avaliar(_anel(), {"n_pisos_max": 2}, {"largura_m": 10, "profundidade_m": 14, "n_pisos": 2}))
    assert res["ok"] and res["implantacao"]["ok"]
    assert res["implantacao"]["largura_m"] == 14 and res["implantacao"]["profundidade_m"] == 10
    assert res["solar"]["horizonte_sul_graus"] > 5 or res["solar"]["fracao_sombra_inverno"] > 0
    with pytest.raises(SV.ViabilidadeErro):
        asyncio.run(SV.avaliar([[48.85, 2.35], [48.851, 2.35], [48.851, 2.351]]))   # Paris


def test_ferramenta_do_assistente(monkeypatch):
    from engines.viabilidade_pt import assistente as AS

    async def avaliar(anel, pdm=None, ed=None, modelo=None, prazo_s=80.0):
        return _resultado()

    monkeypatch.setattr(SV, "avaliar", avaliar)
    out = asyncio.run(AS.executar({"anel_latlon": [list(p) for p in _anel()], "iu_max": 0.5}, {"user_id": "u"}))
    assert out["ok"] and out["classificacao"] and len(out["riscos"]) == 4
    assert AS.TOOL["name"] == "terreno_viabilidade"
    assert set(AS.TOOL["parameters"]["required"]) == set(AS.TOOL["parameters"]["properties"])
    assert asyncio.run(AS.executar({}, {"user_id": "u"}))["ok"] is False


def test_rotas_registadas():
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from routes import viabilidade as RV
    caminhos = {r.path for r in RV.router.routes}
    assert {"/viabilidade/avaliar", "/viabilidade/relatorio.pdf", "/viabilidade/terreno.ifc", "/viabilidade/modelo",
            "/viabilidade/modelo-implantado.ifc"} <= caminhos


# ------------------------------------------------------------------ melhorias: relevo longínquo, PVGIS, vento ERA5, REH, BIM
def test_horizonte_distante_serra_a_sul_tapa_o_sol_de_inverno():
    """Serra de 600 m a 1 km para sul (fora da envolvente de 120 m) → horizonte sul ≈ atan(598,5 / 1000) ≈ 30,9°,
    acima do sol do meio-dia de 21 de dezembro em Sintra (≈ 27,8°)."""
    al = _raster(lambda x, y: np.where(y < -1000, 700.0, 100.0), lado=2800, res=8)
    h = SO.horizonte_distante(al, XC, YC, 100.0)
    assert h[18] == pytest.approx(math.degrees(math.atan2(598.5, 1000)), abs=1.2)
    assert h[0] < 0.5                               # norte livre
    r = _raster(_plano, lado=300, res=2)
    m = np.zeros(r.z.shape, bool)
    m[70:80, 70:80] = True
    from engines.mdt_pt import analise as AN
    decl, expo = AN.declive_exposicao(r)
    sem = SO.analisar(r, m, decl, expo, LAT, LON)
    com = SO.analisar(r, m, decl, expo, LAT, LON, h_distante=h)
    # a 21 de dezembro o sol em Sintra sobe a ~27,8°: com 16,6° a sul perde-se o início e o fim do dia
    assert com["horas_sol_21dez"]["media"] < sem["horas_sol_21dez"]["media"] - 1.5
    assert com["horas_sol_21jun"]["media"] == pytest.approx(sem["horas_sol_21jun"]["media"], abs=0.5)
    assert com["horizonte_distante"]["incluido"] and com["horizonte_distante"]["sul_graus"] > 10


def test_rosa_dos_ventos_era5():
    from engines.viabilidade_pt import externos as EX
    t = [f"2024-{m:02d}-15T{h:02d}:00" for m in range(1, 13) for h in range(24)]
    temp = [30.0 if m in (7, 8) and 13 <= h <= 18 else 12.0 for m in range(1, 13) for h in range(24)]
    vel = [4.0] * len(t)
    # verão quente: vento de NO (315°); inverno: SO (225°); resto: N
    dirs = [315.0 if temp[i] >= 24 else 225.0 if t[i][5:7] in ("12", "01", "02") else 0.0 for i in range(len(t))]
    ro = EX.rosa(t, temp, vel, dirs)
    assert ro["dominante_verao"] == "NO" and ro["dominante_inverno"] == "SO"
    assert sum(s["freq_pct"] for s in ro["anual"]) == pytest.approx(100, abs=0.5)


def test_conforto_com_vento_medido_e_zona_climatica():
    from engines.viabilidade_pt import externos as EX
    rosa = {"ok": True, "dominante_anual": "N", "dominante_verao": "NO", "dominante_inverno": "SO",
            "verao_quente": [{"rumo": "NO", "freq_pct": 41.0, "vel_media_ms": 5.1}], "anual": [], "inverno": [],
            "fonte": "Copernicus ERA5 (ECMWF), via Open-Meteo", "periodo": "2024–2025"}
    clima = EX.clima_reh("Braga", 190.0)
    assert clima["ok"] and clima["zona_inverno"] in ("I1", "I2", "I3") and clima["zona_verao"] in ("V1", "V2", "V3")
    sol = {"horizonte_centro": [{"azimute": k * 10.0, "angulo": 0.0} for k in range(36)], "horas_sol_21dez": {"media": 9.0, "duracao_dia": 9.4},
           "horizonte_sul_graus": 0.0, "fracao_sombra_inverno": 0.0, "indice_solar_pct": 100, "horas_sol_21jun": {"media": 14.5},
           "irradiacao_anual_kwh_m2": {"media": 1600}}
    rel = {"cota_media": 190.0, "declive_medio_pct": 3.0, "exposicao": "S", "exposicao_graus": 180.0, "forma_dominante": "plano"}
    cf = CF.avaliar(41.55, -8.42, sol, rel, rosa, clima)
    v = cf["ventilacao"]
    assert v["medido"] and v["vento_dominante_verao"] == "NO" and "SE" in v["recomendacao"] and "SO" in v["recomendacao"]
    assert cf["clima_reh"]["ok"] and any("Zona climática" in x for x in cf["recomendacoes"])
    # sem dados do local: continua a funcionar e diz que a direção é a típica
    cf2 = CF.avaliar(41.55, -8.42, sol, rel, {"ok": False}, {"ok": False, "nota": "x"})
    assert cf2["ventilacao"]["medido"] is False and cf2["clima_reh"]["ok"] is False


def test_avaliar_usa_relevo_envolvente_pvgis_e_era5(monkeypatch):
    from engines.viabilidade_pt import externos as EX
    r = _raster(_encosta_sul)
    serra = _raster(lambda x, y: np.where(y < -900, 450.0, 150.0 + 0.12 * y), lado=2800, res=8)

    async def obter(pts, resolucao=None, margem_m=15.0, so_dgt=False):
        if resolucao == 8.0:
            return serra, {"fonte": "MDT alargado simulado", "oficial": True, "resolucao_m": 8.0}
        return r, {"fonte": "MDT simulado", "oficial": True, "resolucao_m": 1.0}

    async def territorio(pts, prazo):
        t = _terr()
        t["geometria"] = {"area_m2": 3000.0}
        t["caop"] = {"ok": True, "data": {"principal": {"concelho": "Sintra", "freguesia": "x", "distrito": "Lisboa"}}}
        return t

    async def via(lat, lon):
        return VIA_SUL

    async def nada(lat, lon):
        return {"ok": False}

    async def pv(lat, lon):
        return {"ok": True, "mensal_kwh_m2": [60, 80, 130, 160, 200, 215, 225, 200, 150, 105, 70, 55], "anual_kwh_m2": 1650,
                "periodo": "2016–2023", "fonte": "PVGIS 5.3 — Comissão Europeia (JRC), com horizonte"}

    async def vt(lat, lon):
        return {"ok": True, "dominante_anual": "N", "dominante_verao": "N", "dominante_inverno": "SO",
                "verao_quente": [{"rumo": "N", "freq_pct": 55.0, "vel_media_ms": 6.0}], "anual": [], "inverno": [],
                "fonte": "Copernicus ERA5 (ECMWF), via Open-Meteo", "periodo": "2024–2025"}

    monkeypatch.setattr(GR, "obter", obter)
    monkeypatch.setattr(SV, "_territorio", territorio)
    monkeypatch.setattr(SV, "_via", via)
    monkeypatch.setattr(SV, "_edificios", nada)
    monkeypatch.setattr(EX, "pvgis", pv)
    monkeypatch.setattr(EX, "ventos", vt)
    res = asyncio.run(SV.avaliar(_anel()))
    s, c = res["solar"], res["conforto"]
    assert s["horizonte_distante"]["incluido"] and s["horizonte_distante"]["sul_graus"] > 8
    assert s["pvgis"]["anual_kwh_m2"] == 1650
    assert c["ventilacao"]["medido"] and c["ventilacao"]["vento_dominante_verao"] == "N"
    assert c["clima_reh"]["ok"] and c["clima_reh"]["nuts3"]
    pdf = RL.pdf(res, "Encosta com serra a sul")
    assert pdf[:4] == b"%PDF"
    open("/tmp/viab_melhorias.pdf", "wb").write(pdf) if os.environ.get("CP_GRAVAR_PDF") else None


def test_ifc_do_utilizador_em_milimetros_fica_no_sitio_e_com_terreno():
    import tempfile
    import ifcopenshell
    import ifcopenshell.api
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    p = api("root.create_entity", f, ifc_class="IfcProject", name="Casa mm")
    api("unit.assign_unit", f, units=[api("unit.add_si_unit", f, unit_type="LENGTHUNIT", prefix="MILLI")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api("root.create_entity", f, ifc_class="IfcSite", name="S")
    bld = api("root.create_entity", f, ifc_class="IfcBuilding", name="B")
    st = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="R/C")
    api("aggregate.assign_object", f, products=[site], relating_object=p)
    api("aggregate.assign_object", f, products=[bld], relating_object=site)
    api("aggregate.assign_object", f, products=[st], relating_object=bld)
    for e in (site, bld, st):
        api("geometry.edit_object_placement", f, product=e, matrix=np.eye(4))
    laje = api("root.create_entity", f, ifc_class="IfcSlab", name="Laje")
    rep = api("geometry.add_slab_representation", f, context=body, depth=300.0,
              polyline=[(0.0, 0.0), (12000.0, 0.0), (12000.0, 8000.0), (0.0, 8000.0)])
    api("geometry.assign_representation", f, product=laje, representation=rep)
    api("geometry.edit_object_placement", f, product=laje, matrix=np.eye(4))
    api("spatial.assign_container", f, products=[laje], relating_structure=st)
    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as fh:
        pass
    f.write(fh.name)
    dados = open(fh.name, "rb").read()
    mod = BM.ler_modelo_ifc(dados)
    assert mod["largura_m"] == pytest.approx(12, abs=0.05) and mod["profundidade_m"] == pytest.approx(8, abs=0.05)
    impl = {"centro_tm": [XC, YC], "azimute_fachada_principal": 180.0, "cota_soleira_sugerida": 151.2}
    r = _raster(_encosta_sul, lado=200, res=2)
    out = BM.georreferenciar_ifc(dados, impl, mod, r)
    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as fh2:
        fh2.write(out)
    g = ifcopenshell.open(fh2.name)
    mc = g.by_type("IfcMapConversion")[0]
    assert mc.Scale == pytest.approx(0.001)
    # o centro da laje (6000, 4000 mm) cai no centro da implantação
    E = mc.Eastings + mc.Scale * (6000 * mc.XAxisAbscissa - 4000 * mc.XAxisOrdinate)
    N = mc.Northings + mc.Scale * (6000 * mc.XAxisOrdinate + 4000 * mc.XAxisAbscissa)
    assert abs(E - XC) < 0.05 and abs(N - YC) < 0.05
    ter = g.by_type("IfcGeographicElement")
    assert ter and ter[0].PredefinedType == "TERRAIN"
    # a superfície, convertida para o mapa, reproduz as cotas do MDT
    pl = ter[0].Representation.Representations[0].Items[0].Coordinates.CoordList
    x, y, z = pl[len(pl) // 2]
    Em = mc.Eastings + mc.Scale * (x * mc.XAxisAbscissa - y * mc.XAxisOrdinate)
    Nm = mc.Northings + mc.Scale * (x * mc.XAxisOrdinate + y * mc.XAxisAbscissa)
    Hm = mc.OrthogonalHeight + mc.Scale * z
    from engines.mdt_pt.analise import amostrar
    assert abs(Hm - float(amostrar(r, np.array([Em]), np.array([Nm]))[0])) < 0.3
