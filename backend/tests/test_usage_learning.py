"""Aprendizagem automática com o uso — memória privada por cliente + biblioteca geral anónima (k-anonimato)."""
import asyncio
import os
import sys
import types

import pytest

mm = pytest.importorskip("mongomock_motor")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_db = mm.AsyncMongoMockClient()["test_usage_learning"]
_core_db = types.ModuleType("core.db")
_core_db.db = _db
sys.modules["core.db"] = _core_db

from engines import usage_learning as ul  # noqa: E402


def _quote(doc_id, status, lines, dtype="quote", parent=None):
    return {"doc_id": doc_id, "doc_type": dtype, "status": status, "parent_doc_id": parent, "lines": lines}


def _line(lid, desig, price, unit="m²", **kw):
    return {"line_id": lid, "kind": "line", "designation": desig, "unit": unit, "qty": 10, "unit_price_ht": price, **kw}


async def _users(*ids, share=True):
    for i in ids:
        await _db.users.update_one({"user_id": i}, {"$set": {"user_id": i, "share_anonymous_prices": share}}, upsert=True)
        await _db.library_items.update_one({"user_id": i, "designation": "Pintura de paredes 2 demãos"},
                                           {"$set": {"user_id": i, "designation": "Pintura de paredes 2 demãos",
                                                     "unit": "m²", "unit_price_ht": 9}}, upsert=True)


def run(coro):
    return asyncio.run(coro)


def test_private_memory_stats_and_stage_never_regresses():
    async def go():
        await _db.client.drop_database("test_usage_learning")
        await _users("u1")
        u = {"user_id": "u1"}
        await ul.record_document(u, _quote("d1", "draft", [_line("l1", "Pintura de paredes 2 demãos", 9),
                                                          _line("l2", "Estimado", 50, price_estimated=True)]))
        await ul.record_document(u, _quote("d1", "signed", [_line("l1", "Pintura de paredes 2 demãos", 10)]))
        # fatura rascunho criada a partir do orçamento assinado : não faz regredir a etapa
        await ul.record_document(u, _quote("f1", "draft", [_line("l1", "Pintura de paredes 2 demãos", 10)],
                                           dtype="invoice", parent="d1"))
        obs = await _db.price_observations.find({"org_id": "u1"}).to_list(10)
        assert len(obs) == 1 and obs[0]["stage"] == "signed"          # estimativa IA ignorada
        item = await _db.library_items.find_one({"user_id": "u1"})
        assert item["price_stats"]["n_real"] == 1 and item["price_stats"]["median_real"] == 10
        # recusado → sai das estatísticas
        await ul.record_document(u, _quote("d2", "refused", [_line("l9", "Pintura de paredes 2 demãos", 99)]))
        item = await _db.library_items.find_one({"user_id": "u1"})
        assert item["price_stats"]["max"] == 10
        block = await ul._build_block("u1")
        assert "Pintura de paredes 2 demãos" in block and "PRIVADOS" in block
    run(go())


def test_global_pool_k_anonymity_and_opt_out():
    async def go():
        await _db.client.drop_database("test_usage_learning")
        await _users("a", "b")
        await _users("c", share=False)
        for uid, p in (("a", 8), ("b", 10), ("c", 12)):
            await ul.record_document({"user_id": uid}, _quote("q" + uid, "sent", [_line("l", "Pintura de paredes 2 demãos", p)]))
        g = await _db.library_global_auto.find_one({})
        assert g["n_orgs"] == 2 and not g["published"] and g.get("designation") is None
        # rascunho de outra empresa não conta para a biblioteca geral
        await _users("d")
        await ul.record_document({"user_id": "d"}, _quote("qd", "draft", [_line("l", "Pintura de paredes 2 demãos", 50)]))
        g = await _db.library_global_auto.find_one({})
        assert g["n_orgs"] == 2
        await _users("e")
        await ul.record_document({"user_id": "e"}, _quote("qe", "signed", [_line("l", "Pintura paredes 2 demãos ", 9)]))
        await ul.record_document({"user_id": "e"}, _quote("qe2", "signed", [_line("l", "Pintura de paredes 2 demãos", 9)]))
        g = await _db.library_global_auto.find_one({"published": True})
        assert g and g["n_orgs"] == 3 and g["unit_price_ht"] == 9
        assert "user_id" not in g and all(k not in str(g["orgs"]) for k in ("'a'", "'b'", "'e'"))
        pub = await ul.global_published()
        assert pub and "orgs" not in pub[0]
    run(go())


def test_purchase_and_requests_scrubbed():
    async def go():
        await _db.client.drop_database("test_usage_learning")
        await _users("p")
        u = {"user_id": "p"}
        await ul.record_purchase(u, {"order_id": "o1", "items": [{"designation": "Saco de cimento 25 kg", "unit": "u",
                                                                   "qty": 40, "unit_price": 4.2}]})
        await ul.record_request(u, "Orçamento pintura moradia, liguem 912345678 ou joao@x.pt", dedupe_id="r1")
        await ul.record_request(u, "Orçamento pintura moradia, liguem 912345678 ou joao@x.pt", dedupe_id="r1")
        reqs = await _db.client_requests.find({}).to_list(5)
        assert len(reqs) == 1 and "912345678" not in reqs[0]["text"] and "joao@x.pt" not in reqs[0]["text"]
        block = await ul._build_block("p")
        assert "Saco de cimento 25 kg" in block and "4,20 €" in block
        assert await ul._build_block("nobody") == ""
    run(go())


def test_demo_users_ignored():
    async def go():
        await _db.client.drop_database("test_usage_learning")
        n = await ul.record_document({"user_id": "demo", "is_demo": True},
                                     _quote("x", "signed", [_line("l", "Pintura de paredes 2 demãos", 9)]))
        assert n == 0 and await _db.price_observations.count_documents({}) == 0
    run(go())
