"""14/11 Valpaços: o Assistente devia fazer num só passo o orçamento completo de um DWG (medição + estrutura + preços com
origem + totais). Preços de referência CYPE PT entre a biblioteca e o mercado online; nunca preço sem origem."""
import asyncio
from types import SimpleNamespace as NS

from engines import assistant_quote_pricing as aqp
from engines import precos_referencia as PR


def test_referencia_cype_por_designacao_e_unidade():
    assert PR.procurar("Aço S275 em perfis IPE330 — vigas de pórtico", "kg")[0] == "EAV010"
    assert PR.procurar("Aço S275 em perfis IPE120 — madres de cobertura", "kg")[0] == "EAT030"
    assert PR.procurar("Betão C25/30 em sapatas (1.00×1.00×0.50 m)", "m3")[0] == "CSZ010"
    assert PR.procurar("Lancil — camada LANCIL", "m")[0] == "UXB020"
    assert PR.procurar("Lancil — camada LANCIL", "m2") is None              # unidade errada → nunca
    assert PR.procurar("Pintura de paredes interiores", "m2") is None         # fora da tabela → mercado online


def test_preco_de_venda_com_encargos_e_margem_e_custo_guardado():
    rows = [{"designation": "Betão C25/30 em sapatas", "unit": "m3", "price_missing": True},
            {"designation": "Aço A500 NR em varão — sapatas (armadura mínima)", "unit": "kg", "price_missing": True},
            {"designation": "Parafusos M12 classe 8.8 — ligação madres/pórticos", "unit": "un", "price_missing": True},
            {"designation": "Vedação — camada VEDAÇÃO", "unit": "m", "price_missing": True}]
    assert PR.preencher(rows, {"overhead_pct": 12, "target_margin_pct": 20}) == 2
    k = 1.03 * 1.12 / 0.8
    assert rows[0]["cost_price_ht"] == 198.01 and rows[0]["unit_price_ht"] == round(198.01 * k, 2)
    assert "CYPE" in rows[0]["price_reference_label"] and rows[0]["price_estimated"]
    assert rows[1]["unit_price_ht"] == 0 and "Incluído" in rows[1]["price_reference_label"]   # armadura dentro de CSZ010
    assert rows[2]["price_missing"] is True                                                   # sem madres no orçamento → não incluído
    assert rows[3]["price_missing"] is True                                                   # vai à pesquisa de mercado


def test_build_lines_referencia_antes_do_mercado(monkeypatch):
    async def branding(uid):
        return {"country": "PT"}

    async def sources(user):
        return []

    seen = []

    async def market(lines, branding, db_):
        seen.extend(r["designation"] for r in lines if r.get("price_missing"))

    class _Col:
        async def find_one(self, *a, **k):
            return None
    import routes.plans_common as pc
    monkeypatch.setattr(pc, "_resolve_branding", branding)
    monkeypatch.setattr(aqp, "price_sources", sources)
    monkeypatch.setattr(aqp, "_fill_market_prices", market)
    monkeypatch.setattr(aqp, "db", NS(company_cost_resources=_Col()))
    L = lambda d, u: NS(line_id=None, designation=d, description="", quantity=10, unit=u, unit_price=None, price_origin="library", lot="", vat_rate=None)
    body = NS(lines=[L("Laje térrea R/C e=0,15", "m2"), L("Caleira em chapa lacada", "m")], vat_rate=None)
    rows = asyncio.run(aqp.build_lines(body, {"user_id": "u1"}))
    assert rows[0]["price_source"] == "reference_cype" and rows[0]["cost_price_ht"] == 17.78
    assert seen == ["Caleira em chapa lacada"]


def test_build_lines_fora_de_portugal_sem_referencia(monkeypatch):
    async def branding(uid):
        return {"country": "FR"}

    async def sources(user):
        return []

    async def market(lines, branding, db_):
        return None
    import routes.plans_common as pc
    monkeypatch.setattr(pc, "_resolve_branding", branding)
    monkeypatch.setattr(aqp, "price_sources", sources)
    monkeypatch.setattr(aqp, "_fill_market_prices", market)
    body = NS(lines=[NS(line_id=None, designation="Laje térrea", description="", quantity=1, unit="m2", unit_price=None,
                        price_origin="library", lot="", vat_rate=None)], vat_rate=None)
    rows = asyncio.run(aqp.build_lines(body, {"user_id": "u1"}))
    assert rows[0]["price_missing"] is True


def test_ferramenta_orcamento_cad_registada_e_reservada_a_orcamentos():
    from routes import assistant
    t = next(t for t in assistant.TOOLS if t.get("name") == "orcamento_cad_completo")
    assert set(t["parameters"]["required"]) == set(t["parameters"]["properties"])
    assert "orcamento_cad_completo" not in assistant.INDIVIDUAL_TOOL_NAMES
    assert "orcamento_cad_completo" in assistant.TOOL_STATUS_PT


def test_ferramenta_orcamento_cad_junta_medicao_estrutura_bases_e_transporte(monkeypatch):
    from routes import assistant
    import engines.assistant_quote_service as qs
    import engines.assistant_quote_exports as qe
    calls = {}

    async def inner(name, args, user, conv):
        calls[name] = args
        if name == "medir_camadas_cad":
            return {"ok": True, "excluidas": [], "edificio": {"area_m2": 100.0}, "linhas": [
                {"category": "Pavimentos", "designation": "Pavimento betuminoso — camada X", "unit": "m2", "qty": 100.0, "description": "d"},
                {"category": "Pavimentos", "designation": "Pavimento em pavê drenante — camada Y", "unit": "m2", "qty": 40.0, "description": "d"}]}
        return {"ok": True, "hipoteses": ["pé-direito 7 m"], "linhas": [
            {"category": "Fundações", "designation": "Escavação para sapatas", "unit": "m3", "qty": 12.5, "description": "d"}]}

    saved = {}

    async def save(args, user, conv):
        saved["args"] = args
        lines = [{"designation": l["designation"], "price_source": "reference_cype", "price_missing": False} for l in args["lines"]]
        return {"ok": True, "doc_id": "doc1", "draft": {"lines": lines, "total_ht": 1.0, "total_tva": 0.23, "total_ttc": 1.23}}

    async def exports(res, user, conv):
        return {**res, "artifacts": ["x"]}

    from mongomock_motor import AsyncMongoMockClient
    mdb = AsyncMongoMockClient()["t"]
    asyncio.run(mdb.plans_takeoff.insert_one({"plan_id": "p1", "user_id": "u1", "filename": "Valpacos.dwg"}))
    monkeypatch.setattr(assistant, "_exec_tool_inner", inner)
    monkeypatch.setattr(qs, "save_quote", save)
    monkeypatch.setattr(qe, "with_exports", exports)
    monkeypatch.setattr(assistant, "db", mdb)
    out = asyncio.run(assistant._orcamento_cad_completo(
        {"plan_id": "p1", "sistema": "metalica", "pe_direito_m": None, "pisos": None, "titulo": None, "cliente": None,
         "incluir_bases_pavimento": True}, {"user_id": "u1"}, {}))
    des = [l["designation"] for l in saved["args"]["lines"]]
    assert calls["calcular_estrutura_cad"]["sistema"] == "metalica"
    assert any(d.startswith("HIPÓTESE — Base") and "betuminoso" in d for d in des)
    base_bet = next(l for l in saved["args"]["lines"] if "betuminoso" in l["designation"] and l["unit"] == "m3")
    assert base_bet["quantity"] == 20.0                                    # 100 m² × 0,20 m
    transp = next(l for l in saved["args"]["lines"] if l["designation"].startswith("Carga, transporte"))
    assert transp["quantity"] == 12.5
    assert all(l["price_origin"] == "library" and l["unit_price"] is None for l in saved["args"]["lines"])
    assert out["resumo"]["total_com_iva"] == 1.23 and out["resumo"]["sem_preco"] == [] and out["artifacts"] == ["x"]
    assert saved["args"]["title"].endswith("Valpacos.dwg")
    assert isinstance(out["resumo"]["verificacao_cruzada"], list) and out["resumo"]["referencia"]["precos"]
