"""Piloto automático de licenciamento — testes sem rede (transporte HTTP simulado)."""
import asyncio
import json
import math

import pytest

from engines.urbanismo_pt import regras as R
from engines.urbanismo_pt import pdf as UP
from engines.urbanismo_pt.auto import coerencia as C
from engines.urbanismo_pt.auto import geo as G
from engines.urbanismo_pt.auto import pipeline as P

LAT, LON = 41.5402, -8.4786   # Padim da Graça (Braga) — coordenadas aproximadas para o teste
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50


def _png():
    from PIL import Image
    import io
    b = io.BytesIO()
    Image.new("RGB", (64, 64), (90, 120, 80)).save(b, "PNG")
    return b.getvalue()


def fake(solo="Solo Urbano", categoria="Espaços Habitacionais de Baixa Densidade", srup_titles=(), rede=True):
    calls = []

    async def t(method, url, params=None, headers=None, want="json"):
        calls.append(url)
        if not rede:
            return 0, None
        if "nominatim" in url:
            return 200, [{"lat": str(LAT), "lon": str(LON), "display_name": "Rua do Monte, Padim da Graça, Braga",
                          "address": {"road": "Rua do Monte", "house_number": "7", "village": "Padim da Graça",
                                      "municipality": "Braga", "postcode": "4705-000"}}]
        if url.endswith("/collections"):
            cols = [{"id": "crus", "title": "CRUS"}, {"id": "municipios", "title": "Municípios"}]
            cols += [{"id": f"srup_{i}", "title": tt} for i, tt in enumerate(srup_titles)]
            cols += [{"id": "srup_ren_outro", "title": "Reserva Ecológica Nacional"}]
            return 200, {"collections": cols}
        if "/collections/municipios/items" in url:
            return 200, {"features": [{"properties": {"municipio": "Braga", "distrito": "Braga"}}]}
        if "/collections/crus/items" in url:
            return 200, {"features": [{"properties": {"Classe": solo, "Categoria": categoria}}]}
        if "/collections/srup_" in url:
            i = url.split("srup_")[1].split("/")[0]
            return 200, {"features": [{"properties": {}}]} if i.isdigit() else {"features": []}
        if "/items" in url:
            return 200, {"features": []}
        if "overpass" in url:
            return 200, {"elements": [{"tags": {"name": "Rua do Monte", "highway": "residential"},
                                        "geometry": [{"lat": LAT - 0.00012, "lon": LON - 0.0006}, {"lat": LAT - 0.00012, "lon": LON + 0.0006}]}]}
        if "opentopodata" in url:
            locs = params["locations"].split("|")
            res = []
            for l in locs:
                la, lo = map(float, l.split(","))
                res.append({"elevation": 120 + (la - LAT) * 111320 * 0.06})   # 6 % a subir para norte
            return 200, {"status": "OK", "results": res}
        if "ortos-rgb" in url:
            return 200, _png()
        return 404, None
    t.calls = calls
    return t


def _loop_run(c):
    """Corre num ciclo próprio sem mexer no ciclo «atual» (outros testes usam asyncio.get_event_loop())."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def run(pedido, **kw):
    G.set_transport(fake(**kw))
    G._COLLECTIONS.update(t=0.0, list=[])
    try:
        return _loop_run(P.executar(pedido))
    finally:
        G.set_transport(None)


def test_interpretar_pedido_simples():
    d = P.interpretar_pedido("quero que me faças uma autorização de construção na rua do monte nº7 padim da graça municipio de braga")
    assert d["morada"].lower().startswith("rua do monte")
    d = P.interpretar_pedido("Moradia T4 térrea em granito sem garagem na Rua X 3, Braga")
    assert d["tipologia"] == "T4" and d["pisos"] == 1 and d["garagem"] is False and "granito" in d["fachada"]


def test_processo_completo_rua_do_monte():
    r = run({"texto": "quero que me faças uma autorização de construção na rua do monte nº7 padim da graça municipio de braga"})
    assert r["ok"], r
    proc, verif = r["processo"], r["verificacao"]
    # mesma verdade em todos os motores
    assert r["coerencia"]["ok"], r["coerencia"]["falhas"]
    assert verif["rjue"]["procedimento"] in ("licenciamento", "comunicacao_previa")
    q = verif["quadro"]
    assert q["indice_ocupacao_pct"] <= 30 + 1e-6 and q["indice_utilizacao"] <= 0.6 + 1e-6
    assert q["afastamentos_m"]["frontal"] >= 5 - 1e-6 and q["afastamentos_m"]["tardoz"] >= 6 - 1e-6
    assert proc["terreno"]["concelho"] == "Braga" and "Baixa Densidade" in proc["pdm"]["classe_espaco"]
    # nunca escreve valores municipais inventados no PDM
    assert all(proc["pdm"].get(k) is None for k in ("iu_max", "io_max_pct", "altura_fachada_max_m"))
    assert any("prudentes" in x for x in r["pressupostos"])
    # memória: todos os números vêm dos dados
    assert "Padim" in proc["memoria_texto"] and not any(f["codigo"] == "MEMORIA_NUMEROS" for f in r["coerencia"]["falhas"])
    # declive 6 % reconhecido
    assert 4 <= proc["auto"]["topografia"]["declive_pct"] <= 8
    # plantas: escada no mesmo sítio em todos os pisos
    pis = proc["auto"]["plantas"]["pisos"]
    esc = [[(c["x0"], c["x1"]) for c in p["compartimentos"] if c["tipo"] == "escada"] for p in pis]
    assert len(pis) == 2 and esc[0] == esc[1]
    json.dumps(proc, default=str)   # serializável para a base de dados


def test_desenhos_e_pdf_do_processo_auto():
    r = run({"morada": "Rua do Monte 7, Padim da Graça, Braga", "tipologia": "T3", "fachada": "granito"})
    proc, verif = r["processo"], r["verificacao"]
    ds = UP.desenhos(proc, verif)
    codes = [d["code"] for d in ds]
    for c in ("PLANTA_LOCALIZACAO", "LEVANTAMENTO_TOPOGRAFICO", "PLANTAS_PISOS", "PLANTA_IMPLANTACAO", "CORTES", "ALCADOS"):
        assert c in codes, codes
    pdf = UP.pecas_desenhadas_pdf(proc, ds)
    assert pdf[:4] == b"%PDF"
    assert proc["auto"]["materiais"]["fachada"] == "granito"


def test_solo_rustico_para_sem_inventar():
    r = run({"morada": "Rua do Monte 7, Braga"}, solo="Solo Rústico", categoria="Espaços Agrícolas")
    assert not r["ok"] and r["estado"] == "inviavel" and "RÚSTICO" in r["resposta"]


def test_ren_bloqueia():
    r = run({"morada": "Rua do Monte 7, Braga"}, srup_titles=("Reserva Ecológica Nacional (REN) — Braga",))
    assert not r["ok"] and r["estado"] == "inviavel"


def test_servicos_em_baixo_assume_e_avisa():
    r = run({"morada": "Rua do Monte 7, Braga"}, rede=False)
    assert not r["ok"] and r["estado"] == "servico_indisponivel"


def test_terreno_pequeno_ajusta_variantes():
    r = run({"morada": "Rua do Monte 7, Braga", "area_terreno_m2": 420, "pisos": 1})
    assert r["ok"], r
    assert r["processo"]["volume"]["levels"] == 2 and any("passou-se" in x for x in r["pressupostos"])
    assert r["coerencia"]["ok"]


def test_coerencia_deteta_numero_alterado():
    r = run({"morada": "Rua do Monte 7, Braga"})
    proc, verif = r["processo"], json.loads(json.dumps(r["verificacao"], default=str))
    verif["quadro"]["area_construcao_m2"] += 5   # um motor «diferente» devolve outro valor
    c = C.verificar(proc, verif)
    assert not c["ok"] and any(f["codigo"] == "AREA_CONSTRUCAO" for f in c["falhas"])
    assert C.numeros_sem_fonte("A casa tem 999,5 m² de área.", [100.0, 50.0]) == ["999,5 m²"]


# ------------------------------------------------------------------ geocodificação com repli (Lote 111b)
def _geo(transport, morada="Rua do Monte 7, Padim da Graça, Braga"):
    G.set_transport(transport)
    orig = G.asyncio.sleep

    async def nosleep(_s):
        return None
    G.asyncio.sleep = nosleep
    try:
        return _loop_run(G.geocode(morada))
    finally:
        G.asyncio.sleep = orig
        G.set_transport(None)


def test_geocode_repli_estruturado_e_photon():
    vistos = []

    async def t(method, url, params=None, headers=None, want="json"):
        vistos.append(("photon" if "photon" in url else "nom", dict(params or {})))
        if "nominatim" in url and "street" in (params or {}):
            return 200, []
        if "nominatim" in url:
            return 200, []
        if "photon" in url:
            return 200, {"features": [
                {"geometry": {"coordinates": [-8.0, 40.0]}, "properties": {"countrycode": "PT", "street": "Rua do Monte",
                 "city": "Lisboa", "postcode": "1000-001"}},
                {"geometry": {"coordinates": [-8.47, 41.52]}, "properties": {"countrycode": "PT", "street": "Rua do Monte",
                 "district": "Padim da Graça", "city": "Braga", "postcode": "4700-000"}}]}
        return 404, None
    r = _geo(t)
    assert r["ok"] and r["fonte"].endswith("(Photon)")
    assert r["data"]["concelho"] == "Braga" and r["data"]["precisao"] == "rua"        # a Rua do Monte de Lisboa é rejeitada
    assert any("street" in p for k, p in vistos if k == "nom")                          # tentou a pesquisa estruturada


def test_geocode_rejeita_concelho_errado_e_cai_na_localidade():
    async def t(method, url, params=None, headers=None, want="json"):
        q = (params or {}).get("q", "")
        if "nominatim" in url and q == "Padim da Graça, Braga":
            return 200, [{"lat": "41.52", "lon": "-8.47", "display_name": "Padim da Graça, Braga, Portugal",
                          "address": {"village": "Padim da Graça", "municipality": "Braga"}}]
        if "nominatim" in url:
            return 200, [{"lat": "38.7", "lon": "-9.1", "display_name": "Rua do Monte, Lisboa",
                          "address": {"road": "Rua do Monte", "city": "Lisboa"}}]
        if "photon" in url:
            return 200, {"features": []}
        return 404, None
    r = _geo(t)
    assert r["ok"] and r["data"]["precisao"] == "localidade" and abs(r["data"]["lat"] - 41.52) < 1e-6


def test_geocode_rede_indisponivel_e_diagnostico():
    async def t(method, url, params=None, headers=None, want="json"):
        return 403 if "nominatim" in url else 0, None
    r = _geo(t)
    assert not r["ok"] and "inacess" in r["nota"] and "nominatim" in r["nota"] and "photon" in r["nota"]


def test_geocode_rejeita_rua_de_outra_freguesia():
    """Caso real (smoke 07/11): «Rua do Monte, Braga» devolvia a rua de Santa Lucrécia de Algeriz, não a de Padim da Graça."""
    async def t(method, url, params=None, headers=None, want="json"):
        q = (params or {}).get("q", "")
        if "nominatim" in url and q == "Padim da Graça, Braga":
            return 200, [{"lat": "41.52", "lon": "-8.47", "display_name": "Padim da Graça, Braga, Portugal",
                          "address": {"village": "Padim da Graça", "municipality": "Braga"}}]
        if "nominatim" in url and (params or {}).get("street") or "nominatim" in url and q:
            return 200, [{"lat": "41.5833", "lon": "-8.3726",
                          "display_name": "Rua do Monte, Santa Lucrécia de Algeriz e Navarra, Braga, 4715-567, Portugal",
                          "address": {"road": "Rua do Monte", "municipality": "Braga"}}]
        if "photon" in url:
            return 200, {"features": []}
        return 404, None
    r = _geo(t)
    assert r["ok"] and r["data"]["precisao"] == "localidade" and "Padim" in r["data"]["morada_formatada"]


def _sem_esperas():
    orig = G.asyncio.sleep

    async def ns(_s):
        return None
    G.asyncio.sleep = ns
    return orig


def test_dgt_falha_transitoria_repete_e_deteta_solo_rustico():
    base = fake(solo="Solo Rústico", categoria="Espaço Agrícola")
    n = {"crus": 0}

    async def t(method, url, params=None, headers=None, want="json"):
        if "/collections/crus/items" in url:
            n["crus"] += 1
            if n["crus"] < 3:
                return 0, None          # duas falhas de rede seguidas
        return await base(method, url, params, headers, want)
    orig = _sem_esperas()
    G.set_transport(t)
    G._COLLECTIONS.update(t=0.0, list=[])
    try:
        r = _loop_run(P.executar({"morada": "Rua do Monte 7, Padim da Graça, Braga"}))
    finally:
        G.asyncio.sleep = orig
        G.set_transport(None)
    assert r["estado"] == "inviavel" and any("RÚSTICO" in b for b in r["bloqueios"])


def test_dados_criticos_por_confirmar_nunca_pronto_e_declive_rastreado():
    base = fake()

    async def t(method, url, params=None, headers=None, want="json"):
        if "/collections/crus/items" in url or "overpass" in url or "kumi" in url or "coffee" in url:
            return 0, None
        if "opentopodata" in url:
            res = []
            for l in params["locations"].split("|"):
                la, lo = map(float, l.split(","))
                res.append({"elevation": 265 + (la - LAT) * 111320 * 0.15})
            return 200, {"status": "OK", "results": res}
        return await base(method, url, params, headers, want)
    orig = _sem_esperas()
    G.set_transport(t)
    G._COLLECTIONS.update(t=0.0, list=[])
    try:
        r = _loop_run(P.executar({"morada": "Rua do Monte 7, Padim da Graça, Braga"}))
    finally:
        G.asyncio.sleep = orig
        G.set_transport(None)
    assert r["ok"] and r["estado"] == "revisao"                         # CRUS sem resposta → nunca «pronto»
    assert any("CRUS" in a for a in r["avisos"])
    assert r["processo"]["auto"]["por_confirmar"] == ["classe do PDM (CRUS)"]      # exportação bloqueada até confirmar
    assert any("DGT" in q for q in r["perguntas"])
    c = r["processo"]["auto"]["coerencia"]
    assert not any(f["codigo"] == "MEMORIA_NUMEROS" for f in c["falhas"]), c["falhas"]


def test_normalizacao_nao_come_o_no_de_nova():
    assert G._limpa_morada("Rua Nova de Santa Cruz nº 10, São Vicente, Braga") == "Rua Nova de Santa Cruz 10, São Vicente, Braga"
    assert G._limpa_morada("Rua do Monte n.º7, Padim da Graça, município de Braga").startswith("Rua do Monte 7")
    assert G._limpa_morada("Rua Norte no 5, Braga") == "Rua Norte 5, Braga"


def test_photon_rua_vizinha_rejeitada_e_via_pela_geometria():
    """Caso real: o Photon devolvia «Rua do Marco» para «Rua do Monte»; o Overpass estava inacessível."""
    async def t(method, url, params=None, headers=None, want="json"):
        q = (params or {}).get("q", "")
        if "photon" in url:
            return 200, {"features": [{"geometry": {"coordinates": [-8.5043, 41.5630]}, "properties": {
                "countrycode": "PT", "street": "Rua do Marco", "district": "Padim da Graça", "city": "Braga"}}]}
        if "nominatim" in url and q == "Rua do Monte, Padim da Graça, Braga":
            return 200, [{"lat": "41.5402", "lon": "-8.4786", "category": "highway",
                          "display_name": "Rua do Monte, Padim da Graça, Braga, Portugal",
                          "address": {"road": "Rua do Monte", "village": "Padim da Graça", "municipality": "Braga"},
                          "geojson": {"type": "LineString", "coordinates": [[-8.4795, 41.5401], [-8.4775, 41.5403]]}}]
        if "nominatim" in url:
            return 200, []
        return 404, None
    r = _geo(t)
    assert r["ok"] and r["data"]["rua"] == "Rua do Monte" and r["data"]["via_geom"]
    v = G.via_de_geometria(r["data"]["lat"], r["data"]["lon"], r["data"]["via_geom"], "Rua do Monte")
    assert v["ok"] and v["data"]["distancia_m"] < 5


def test_geocode_so_rua_vizinha_cai_na_localidade():
    async def t(method, url, params=None, headers=None, want="json"):
        q = (params or {}).get("q", "")
        if "photon" in url:
            return 200, {"features": [{"geometry": {"coordinates": [-8.5043, 41.5630]}, "properties": {
                "countrycode": "PT", "street": "Rua do Marco", "district": "Padim da Graça", "city": "Braga"}}]}
        if "nominatim" in url and q == "Padim da Graça, Braga":
            return 200, [{"lat": "41.54", "lon": "-8.48", "display_name": "Padim da Graça, Braga, Portugal",
                          "address": {"village": "Padim da Graça", "municipality": "Braga"}}]
        if "nominatim" in url:
            return 200, []
        return 404, None
    r = _geo(t)
    assert r["ok"] and r["data"]["precisao"] == "localidade"


def test_rua_com_freguesia_divergente_confirmada_pela_caop():
    """Caso real: «Rua Nova de Santa Cruz, São Vicente, Braga» — o OSM põe a rua noutra freguesia (união de freguesias)."""
    rua = {"lat": "41.5567", "lon": "-8.4060", "category": "highway",
           "display_name": "Rua Nova de Santa Cruz, São Victor, Braga, 4710-409, Portugal",
           "address": {"road": "Rua Nova de Santa Cruz", "suburb": "São Victor", "city": "Braga"},
           "geojson": {"type": "LineString", "coordinates": [[-8.4070, 41.5566], [-8.4050, 41.5568]]}}

    async def t(method, url, params=None, headers=None, want="json"):
        q = (params or {}).get("q", "")
        if "nominatim" in url and q == "Rua Nova de Santa Cruz, Braga":
            return 200, [rua, dict(rua, lat="41.5569", lon="-8.4045")]
        if "photon" in url:
            return 200, {"features": []}
        if "nominatim" in url:
            return 200, []
        if "/collections/freguesias/items" in url:
            return 200, {"features": [{"properties": {"freguesia": "União das freguesias de Braga (São Vicente)"}}]}
        return 404, None
    r = _geo(t, "Rua Nova de Santa Cruz 10, São Vicente, Braga")
    assert r["ok"] and r["data"]["rua"] == "Rua Nova de Santa Cruz" and r["data"]["freguesia_divergente"] == "São Vicente"
    assert "CAOP" in r["fonte"] and "São Vicente" in r["data"]["freguesia"]
    assert r["data"]["via_geom"]


def test_rua_repetida_no_concelho_nao_e_aceite():
    async def t(method, url, params=None, headers=None, want="json"):
        q = (params or {}).get("q", "")
        if "nominatim" in url and q == "Rua do Monte, Braga":
            return 200, [{"lat": "41.58", "lon": "-8.37", "display_name": "Rua do Monte, Santa Lucrécia, Braga",
                          "address": {"road": "Rua do Monte", "city": "Braga"}},
                         {"lat": "41.50", "lon": "-8.45", "display_name": "Rua do Monte, Ruilhe, Braga",
                          "address": {"road": "Rua do Monte", "city": "Braga"}}]
        if "nominatim" in url and q == "Padim da Graça, Braga":
            return 200, [{"lat": "41.565", "lon": "-8.486", "display_name": "Padim da Graça, Braga, Portugal",
                          "address": {"village": "Padim da Graça", "municipality": "Braga"}}]
        if "photon" in url:
            return 200, {"features": []}
        if "nominatim" in url:
            return 200, []
        return 404, None
    r = _geo(t)
    assert r["ok"] and r["data"]["precisao"] == "localidade"


def test_via_reversa_com_geometria():
    async def t(method, url, params=None, headers=None, want="json"):
        if "reverse" in url:
            return 200, {"category": "highway", "name": "Rua do Monte", "address": {"road": "Rua do Monte"},
                         "geojson": {"type": "LineString", "coordinates": [[-8.4795, 41.5401], [-8.4775, 41.5401]]}}
        return 404, None
    G.set_transport(t)
    try:
        v = _loop_run(G.via_reversa(41.5402, -8.4786))
    finally:
        G.set_transport(None)
    assert v["ok"] and 8 < v["data"]["distancia_m"] < 14 and v["data"]["nome"] == "Rua do Monte"
