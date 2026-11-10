"""Acompanhamento do cálculo ao vivo (conta CLT Rezult): rastreio do licenciamento, do motor Ucrânia, acesso e no-op."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from engines import calc_live as CL
from engines.urbanismo_pt.auto import dgt_cache as CACHE
from engines.urbanismo_pt.auto import geo as G
from engines.urbanismo_pt.auto import pipeline as P
from tests.test_urbanismo_auto import fake

CLT = {"user_id": "u_clt", "email": "clt-rezult.demo@construpilot.pt"}
OUTRO = {"user_id": "u_x", "email": "alguem@exemplo.pt"}


@pytest.fixture(autouse=True)
def _copia_isolada(tmp_path):
    CACHE.usar_pasta(str(tmp_path / "dgt_cache"))
    yield
    G._CACHE_EM_TESTE["on"] = False


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_acesso_so_clt(monkeypatch):
    assert CL.is_clt(CLT) and CL.is_clt({"email": "Office@CLT-Rezult.com"})
    assert not CL.is_clt(OUTRO) and not CL.is_clt(None)
    monkeypatch.setenv("CALC_LIVE_EMAILS", "alguem@exemplo.pt")
    assert CL.is_clt(OUTRO)


def test_sem_tracer_nada_e_gravado():
    async def go():
        assert not CL.ativo()
        await CL.ev("calculo", "x")          # no-op
        CL.ev_sync("calculo", "y")
    _run(go())


def test_licenciamento_rastreado_de_ponta_a_ponta():
    db = AsyncMongoMockClient()["t"]
    conv = {"conversation_id": "c1", "_quote_request_id": "req1",
            "_user_request_text": "autorização de construção na rua do monte nº7 padim da graça municipio de braga"}

    async def go():
        G.set_transport(fake())
        G._COLLECTIONS.update(t=0.0, list=[])
        try:
            async with CL.ferramenta(db, CLT, conv, "licenciamento_automatico", {"texto": conv["_user_request_text"]}):
                r = await P.executar({"texto": conv["_user_request_text"], "area_terreno_m2": 1500})
                await CL.resultado_ferramenta("licenciamento_automatico", {"ok": True})
        finally:
            G.set_transport(None)
        assert not CL.ativo()                      # o contextvar é reposto
        return r, await db.calc_live_runs.find_one({"run_id": "live_req1"})
    r, run = _run(go())
    assert r["ok"]
    ev = sorted(run["eventos"], key=lambda e: e["seq"])
    tipos = {e["tipo"] for e in ev}
    assert {"ferramenta", "etapa", "dado", "calculo", "decisao", "verificacao", "pressuposto", "resultado"} <= tipos
    etapas = [e["titulo"] for e in ev if e["tipo"] == "etapa"]
    for k in ("0.", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."):
        assert any(t.startswith(k) for t in etapas), (k, etapas)
    assert etapas.index(next(t for t in etapas if t.startswith("1."))) < etapas.index(next(t for t in etapas if t.startswith("8.")))
    # cada verificação tem resultado e as do PDM trazem a norma
    verifs = [e for e in ev if e["tipo"] == "verificacao"]
    assert len(verifs) >= 10 and all("ok" in e or e.get("valores") for e in verifs)
    io = next(e for e in ev if e["titulo"].startswith("Índice de ocupação"))
    assert "Io =" in io["formula"] and io["resultado"].endswith("%")
    assert run["pedido"].startswith("autorização") and run["em_curso"] == 0
    assert CL.estado(run) in ("a_calcular", "terminado")
    assert run["n_verificacao"] == len(verifs)


def test_motor_ucrania_rastreado_num_thread():
    """calcul_ucrania corre em asyncio.to_thread: os eventos chegam pelo loop do pedido, pela ordem do cálculo."""
    from engines.calc_lots import rastreio_ua as RTU
    from engines.calc_lots import ucrania
    db = AsyncMongoMockClient()["t"]
    conv = {"conversation_id": "c2", "_quote_request_id": "req2", "_user_request_text": "Run the complete Ukrainian study"}
    p = ucrania.exemplo_clt()

    def calc():
        o = {"r": ucrania.calcular(p), "go": None, "orcamento": None}
        RTU.inicio(p, None)
        RTU.dossier(o, p)
        return o

    async def go():
        async with CL.ferramenta(db, CLT, conv, "calcul_ucrania", {"exemplo": True}):
            o = await asyncio.to_thread(calc)
        await asyncio.sleep(0)
        return o, await db.calc_live_runs.find_one({"run_id": "live_req2"})
    o, run = _run(go())
    ev = sorted(run["eventos"], key=lambda e: e["seq"])
    titulos = [e["titulo"] for e in ev]
    assert titulos[0].startswith("Motor Ucrânia")              # 1.º: a ferramenta escolhida
    assert any(t.startswith("Design heat load") for t in titulos)
    phi = next(e for e in ev if e["titulo"].startswith("Design heat load"))
    assert phi["formula"] == "Φ = (H_T + H_V) · (θi − θe)"
    assert phi["resultado"] == CL.num(o["r"]["phi_w"] / 1000, 2, "kW")
    assert sum(1 for e in ev if e["tipo"] == "verificacao") == sum(len(e["controles"]) for e in o["r"]["elementos"])


def test_outra_conta_nao_e_seguida():
    """O envoltório do Assistente só cria execuções para a conta CLT."""
    assert not CL.is_clt(OUTRO)
    db = AsyncMongoMockClient()["t"]

    async def go():
        await CL.ev("etapa", "nada")
        return await db.calc_live_runs.count_documents({})
    assert _run(go()) == 0
