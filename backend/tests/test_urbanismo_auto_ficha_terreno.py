"""Ficha oficial do terreno: CAOP/DICOFRE, PDM, REN e RAN cruzados com o POLÍGONO do terreno (serviços simulados)."""
import asyncio

import pytest

from engines.urbanismo_pt.auto import ficha_terreno as FT, geo as G

LAT, LON = 41.5651, -8.4861


def quad(lat0, lon0, dlat, dlon):
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon0 + dlon, lat0], [lon0 + dlon, lat0 + dlat],
                                                [lon0, lat0 + dlat], [lon0, lat0]]]}


def transporte(ren=None, ran=None, solo="Solo Urbano", rede=True):
    grande = quad(LAT - 0.01, LON - 0.01, 0.02, 0.02)

    async def t(method, url, params=None, headers=None, want="json"):
        if not rede:
            return 0, None
        if url.endswith("/collections"):
            return 200, {"collections": [{"id": c, "title": c} for c in ("crus", "municipios", "freguesias", "srup_ren_areal",
                                                                           "srup_ran", "srup_rede_eletrica", "cadastro", "linhas_agua",
                                                                           "altimetria_curvas_nivel")]}
        if "nominatim" in url and "reverse" in url:
            return 200, {"address": {"hamlet": "Monte da Preguiça", "village": "Padim da Graça"}}
        if "/municipios/items" in url:
            return 200, {"features": [{"properties": {"municipio": "Braga", "distrito_ilha": "Braga", "dtmn": "0303"}, "geometry": grande}]}
        if "/freguesias/items" in url:
            return 200, {"features": [{"properties": {"freguesia": "Padim da Graça", "dtmnfr": "030341"}, "geometry": grande}]}
        if "/crus/items" in url:
            return 200, {"features": [{"properties": {"classe_2021": solo, "categoria_2021": "Espaço Urbano de Baixa Densidade",
                                                      "registo_ou_deposito": "01.03.03/PDM/03/2026/53", "situacao_pdm": "Vigente"},
                                       "geometry": grande}]}
        if "/srup_ren_areal/items" in url:
            return 200, {"features": [{"properties": {"tipologia": "Áreas de máxima infiltração"}, "geometry": ren}] if ren else []}
        if "/srup_ran/items" in url:
            return 200, {"features": [{"properties": {}, "geometry": ran}] if ran else []}
        if "/srup_rede_eletrica/items" in url:
            return 200, {"features": [{"properties": {"tipologia": "Linha MT"},
                                       "geometry": {"type": "LineString", "coordinates": [[LON - 0.001, LAT + 0.00035], [LON + 0.001, LAT + 0.00035]]}}]}
        if "/linhas_agua/items" in url:
            return 200, {"features": [{"properties": {"nome": "Ribeiro"}, "geometry": {"type": "LineString",
                                       "coordinates": [[LON - 0.002, LAT - 0.0006], [LON + 0.002, LAT - 0.0006]]}}]}
        if "/altimetria_curvas_nivel/items" in url:
            return 200, {"features": [{"properties": {"cota": 100 + k * 5}, "geometry": {"type": "LineString",
                                       "coordinates": [[LON - 0.002, LAT - 0.0005 + k * 0.0002], [LON + 0.002, LAT - 0.0005 + k * 0.0002]]}}
                                      for k in range(5)]}
        if "/items" in url:
            return 200, {"features": []}
        if "opentopodata" in url:
            locs = params["locations"].split("|")
            return 200, {"status": "OK", "results": [{"elevation": 100 + (float(l.split(",")[0]) - LAT) * 110574 * 0.12}
                                                     for l in locs]}
        if "ortos-rgb/map" in url:
            return 0, None
        return 0, None
    return t


@pytest.fixture(autouse=True)
def _rede():
    G._COLLECTIONS.update(t=0.0, list=[])
    yield
    G.set_transport(None)
    G._COLLECTIONS.update(t=0.0, list=[])


def run(c):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(c)


TERRENO = FT.terreno_aproximado(LAT, LON, 1500)


def test_terreno_limpo_compativel_com_dicofre_e_lugar():
    G.set_transport(transporte())
    f = run(FT.ficha(LAT, LON, TERRENO))
    a = f["administrativo"]
    assert (a["municipio"], a["dico"], a["freguesia"], a["dicofre"], a["lugar"]) == ("Braga", "0303", "Padim da Graça", "030341",
                                                                                      "Monte da Preguiça")
    assert f["pdm"][0]["solo"] == "urbano" and f["pdm"][0]["pct_terreno"] == pytest.approx(100, abs=0.5)
    assert f["ren"]["pct"] == 0 and f["ran"]["pct"] == 0
    assert f["parecer"]["estado"] == "compativel"
    eletr = next(o for o in f["outras_servidoes"] if o["id"] == "srup_rede_eletrica")
    assert eletr["distancia_m"] == pytest.approx(19, abs=3)      # a linha passa ~19 m a norte do limite do terreno


def test_ren_em_metade_do_terreno_condiciona_e_toda_inviabiliza():
    lado = (1500 ** 0.5) / 2
    dlat, dlon = lado / 110574, lado / (111320 * 0.7487)
    metade_sul = quad(LAT - dlat - 0.001, LON - 0.001, 0.001 + dlat * 0.6, 0.002)   # cobre ~30 % do terreno
    G.set_transport(transporte(ren=metade_sul))
    f = run(FT.ficha(LAT, LON, TERRENO))
    assert 20 < f["ren"]["pct"] < 40 and f["parecer"]["estado"] == "condicionado"
    G._COLLECTIONS.update(t=0.0, list=[])
    G.set_transport(transporte(ren=quad(LAT - 0.01, LON - 0.01, 0.02, 0.02)))
    f = run(FT.ficha(LAT, LON, TERRENO))
    assert f["ren"]["pct"] == pytest.approx(100, abs=0.5) and f["parecer"]["estado"] == "inviavel"
    assert any("REN" in m for m in f["parecer"]["fundamentos"])


def test_solo_rustico_inviavel_e_servico_em_baixo_fica_por_confirmar():
    G.set_transport(transporte(solo="Solo Rústico"))
    assert run(FT.ficha(LAT, LON, TERRENO))["parecer"]["estado"] == "inviavel"
    G._COLLECTIONS.update(t=0.0, list=[])
    G.set_transport(transporte(rede=False))
    f = run(FT.ficha(LAT, LON, TERRENO))
    assert f["parecer"]["estado"] == "por_confirmar" and "REN" in f["por_confirmar"] and "RAN" in f["por_confirmar"]


def test_planta_de_condicionantes_desenha_sem_ortofoto():
    G.set_transport(transporte(ren=quad(LAT - 0.0005, LON - 0.0005, 0.0004, 0.001)))
    f = run(FT.ficha(LAT, LON, TERRENO))
    png = run(FT.planta_condicionantes(f, FT.terreno_aproximado(LAT, LON, 200)))
    assert png[:4] == b"\x89PNG" and len(png) > 20000


def test_carta_de_declives_e_ficha_pdf_com_linhas_de_agua():
    G.set_transport(transporte())
    f = run(FT.ficha(LAT, LON, TERRENO))
    d = run(FT.declives(f))
    assert d["ok"] and d["declive_medio_pct"] == pytest.approx(12, abs=1.5) and d["escoamento_para"] == "sul"
    assert FT.tem_desnivel(d) and d["desnivel_m"] > 3
    carta = run(FT.carta_declives(f, d, FT.terreno_aproximado(LAT, LON, 200)))
    assert carta[:4] == b"\x89PNG"
    linha_agua = next(o for o in f["outras_servidoes"] if o["id"] == "linhas_agua")
    assert linha_agua["distancia_m"] == pytest.approx(47, abs=4)       # o ribeiro passa ~47 m a sul do limite
    pdf = FT.ficha_pdf(f, run(FT.planta_condicionantes(f)), carta, d, "Teste")
    from pypdf import PdfReader
    import io as _io
    r = PdfReader(_io.BytesIO(pdf))
    assert len(r.pages) == 2
    t = r.pages[0].extract_text()
    assert "030341" in t and "Padim da Graça" in t and "REN" in t and "RAN" in t and "Espaço Urbano" in t
