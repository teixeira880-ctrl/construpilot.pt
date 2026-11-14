"""14/11 (Martinho): em todas as contas, o mesmo DWG dá SEMPRE o mesmo resultado, mesmo com o pedido reescrito ou repetido;
dados novos só acrescentam. Verificação cruzada entre motores em cada resultado."""
import asyncio
from types import SimpleNamespace as NS

from mongomock_motor import AsyncMongoMockClient

from engines import cad_baseline as CB
from engines import cad_quantidades_camadas as CQ
from engines import estrutura_metalica as EM
from engines import verificacao_cruzada as VC

RET = [[0.0, 0.0], [50.5, 0.0], [50.5, 34.5], [0.0, 34.5]]


def _med(qty):
    return {"versao": CQ.VERSAO, "unidades": "unidades do desenho: m (confirmadas por 3 área(s) escrita(s))", "excluidas": [],
            "edificio": {"camada": "IMPLANT", "area_m2": 1742.25, "origem": "polilinha", "pontos": RET},
            "linhas": [{"category": "Pavimentos", "designation": "Pavimento betuminoso — camada X", "unit": "m2", "qty": qty, "description": "d"}]}


def _setup(monkeypatch):
    from routes import assistant
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(assistant, "db", db)

    async def go():
        for pid, qty in (("p1", 100.0), ("p2", 999.0)):      # p2 = o MESMO ficheiro reimportado; motor mais recente daria outro valor
            await db.plans_takeoff.insert_one({"plan_id": pid, "user_id": "u1", "kind": "dxf", "filename": "V.dwg", "cad_quantidades": _med(qty)})
            await db.plan_cad_sources.insert_one({"plan_id": pid, "user_id": "u1", "source_kind": "original", "index": 0, "sha256": "abc123"})
    asyncio.run(go())
    return assistant, db


USER = {"user_id": "u1", "role": "particulier", "account_type": "individual"}


def _call(assistant, name, **args):
    return asyncio.run(assistant._exec_tool_inner(name, {"recalcular": False, **args}, USER, {"user_id": "u1"}))


def test_mesmo_desenho_mesma_medicao_mesmo_reimportado(monkeypatch):
    assistant, db = _setup(monkeypatch)
    a = _call(assistant, "medir_camadas_cad", plan_id="p1")
    b = _call(assistant, "medir_camadas_cad", plan_id="p2")
    c = _call(assistant, "medir_camadas_cad", plan_id="p1")
    assert a["linhas"] == b["linhas"] == c["linhas"] and a["linhas"][0]["qty"] == 100.0
    assert "congelada" in b["referencia"]["medicao"]
    assert any(v["estado"] == "ok" and "Unidades" in v["verificacao"] for v in a["verificacao_cruzada"])


def test_estrutura_identica_e_dados_novos_so_acrescentam(monkeypatch):
    assistant, db = _setup(monkeypatch)
    e1 = _call(assistant, "calcular_estrutura_cad", plan_id="p1", sistema="metalica", pe_direito_m=None, pisos=None)
    e2 = _call(assistant, "calcular_estrutura_cad", plan_id="p2", sistema="metalica", pe_direito_m=None, pisos=None)
    assert e1["linhas"] == e2["linhas"] and "congelada" in e2["referencia"]["estrutura"]
    e3 = _call(assistant, "calcular_estrutura_cad", plan_id="p1", sistema="metalica", pe_direito_m=9.0, pisos=None)
    assert "dados novos" in e3["referencia"]["estrutura"] and e3["referencia"]["parametros"]["pe_direito_m"] == 9.0
    assert e3["referencia"]["diferencas"]                                      # o que mudou fica escrito
    e4 = _call(assistant, "calcular_estrutura_cad", plan_id="p2", sistema="metalica", pe_direito_m=None, pisos=None)
    assert e4["linhas"] == e3["linhas"]                                        # null mantém o dado novo, não volta atrás
    rec = asyncio.run(db.cad_baselines.find_one({"user_id": "u1", "sha256": "abc123"}))
    assert len(rec["estrutura"]["metalica"]["revisoes"]) == 1


def test_contas_isoladas(monkeypatch):
    assistant, db = _setup(monkeypatch)
    _call(assistant, "medir_camadas_cad", plan_id="p1")
    assert asyncio.run(CB.ler(db, "outra", "abc123")) is None


def test_verificacao_cruzada_estrutura_metalica_coerente():
    r = EM.calcular([tuple(p) for p in RET], nome="T", pe_direito=7.0, altitude=400.0)
    v = VC.verificar(_med(100.0), {"linhas": r["linhas"], "contorno": {"area_m2": 1742.25}})
    nomes = {x["verificacao"]: x for x in v}
    assert nomes["Aço da estrutura por m² ↔ gama corrente"]["estado"] == "ok"
    assert nomes["Escavação ↔ betão enterrado"]["estado"] == "ok"
    assert nomes["Perímetro ↔ fachada (altura implícita)"]["estado"] == "ok"
    assert all(x["estado"] in ("ok", "aviso") and x["detalhe"] for x in v)


def test_verificacao_orcamento_soma_e_aviso():
    rows = [{"designation": "Aço S275 em perfis IPE330 — vigas", "unit": "kg", "qty": 1000, "unit_price_ht": 3.0, "price_source": "reference_cype"}]
    v = VC.verificar_orcamento(rows, 3000.0, 100.0, 1.442)
    assert v[0]["estado"] == "ok"
    assert VC.verificar_orcamento(rows, 2000.0, None, 1.442)[0]["estado"] == "aviso"


def test_precos_fixos_do_desenho_ganham_a_tudo(monkeypatch):
    from engines import assistant_quote_pricing as aqp

    async def branding(uid):
        return {"country": "PT"}

    async def sources(user):
        return []

    async def market(lines, branding, db_):
        return None
    import routes.plans_common as pc
    monkeypatch.setattr(pc, "_resolve_branding", branding)
    monkeypatch.setattr(aqp, "price_sources", sources)
    monkeypatch.setattr(aqp, "_fill_market_prices", market)
    monkeypatch.setattr(aqp, "db", NS(company_cost_resources=NS(find_one=lambda *a, **k: asyncio.sleep(0, None))))
    fixo = {"unit_price_ht": 99.0, "cost_price_ht": 50.0, "price_source": "reference_cype", "price_estimated": True,
            "price_reference": "cype_pt:ANS010", "price_reference_label": "fixado"}
    tok = CB.PRECOS_FIXOS.set({CB.chave_fixa("Laje térrea R/C", "m2"): fixo})
    try:
        L = NS(line_id=None, designation="Laje térrea R/C", description="", quantity=10, unit="m2", unit_price=None,
               price_origin="library", lot="", vat_rate=None)
        rows = asyncio.run(aqp.build_lines(NS(lines=[L], vat_rate=None), {"user_id": "u1"}))
    finally:
        CB.PRECOS_FIXOS.reset(tok)
    assert rows[0]["unit_price_ht"] == 99.0 and rows[0]["price_reference_label"] == "fixado" and not rows[0]["price_missing"]


def test_juntar_parametros_null_nunca_apaga():
    p, m = CB.juntar_parametros({"pe_direito_m": 8.0}, {"pe_direito_m": None, "pisos": 2})
    assert p == {"pe_direito_m": 8.0, "pisos": 2} and m == ["pisos = 2 (dado novo)"]
