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
    assert not r["ok"] and r["estado"] == "morada_nao_encontrada"


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
