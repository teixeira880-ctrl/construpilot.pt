"""Orçamentação sempre completa: preços que faltam na biblioteca → preço de mercado online (estimado, a verificar)."""
import asyncio
from types import SimpleNamespace as NS

from engines import assistant_quote_pricing as aqp
from engines import market_prices as mp


def test_lookup_uses_web_once_and_caches(monkeypatch):
    monkeypatch.setenv("MARKET_PRICES_IN_TESTS", "1")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "x")
    monkeypatch.setattr(mp, "_CACHE", {})
    calls = []

    async def web(system, prompt):
        calls.append(prompt)
        return {"prices": {"0": {"price": 24.5, "source": "leroymerlin.pt"}, "1": {"price": None}}}
    monkeypatch.setattr(mp, "_ask_web", web)
    items = [{"designation": "Pintura de paredes interiores", "unit": "m2"}, {"designation": "Item raro", "unit": "u"}]
    a = asyncio.run(mp.lookup(items, "PT"))
    b = asyncio.run(mp.lookup(items, "PT"))
    assert a == b == {0: {"price": 24.5, "source": "leroymerlin.pt"}} and len(calls) == 1


def test_no_network_in_tests_by_default(monkeypatch):
    monkeypatch.delenv("MARKET_PRICES_IN_TESTS", raising=False)
    assert asyncio.run(mp.lookup([{"designation": "x", "unit": "u"}], "PT")) == {}


def test_build_lines_fills_missing_prices_from_market(monkeypatch):
    async def branding(uid):
        return {"country": "PT", "city": "Lisboa"}

    async def sources(user):
        return []

    async def lookup(items, country, region, db):
        assert country == "PT" and [i["designation"] for i in items] == ["Pintura", "Sem preço"]
        return {0: {"price": 12.0, "source": "web"}}
    import routes.plans_common as pc
    monkeypatch.setattr(pc, "_resolve_branding", branding)
    monkeypatch.setattr(aqp, "price_sources", sources)
    monkeypatch.setattr(mp, "lookup", lookup)
    L = lambda d, o, p=None: NS(line_id=None, designation=d, description="", quantity=10, unit="m2", unit_price=p, price_origin=o, lot="", vat_rate=None)
    body = NS(lines=[L("Pintura", "library"), L("Dado", "user", 5.0), L("Sem preço", "unpriced")], vat_rate=None)
    rows = asyncio.run(aqp.build_lines(body, {"user_id": "u1"}))
    assert rows[0]["unit_price_ht"] == 12.0 and rows[0]["price_source"] == "market_web" and rows[0]["price_estimated"]
    assert "mercado online" in rows[0]["price_reference_label"]
    assert rows[1]["unit_price_ht"] == 5.0 and rows[1]["price_source"] == "user_input"
    assert rows[2]["price_missing"] is True                         # sem preço encontrado: fica por preencher, nunca inventado
