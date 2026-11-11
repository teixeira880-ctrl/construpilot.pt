"""Faturas ligadas à ficha do cliente + ferramentas CRM do Assistente (base de dados em memória)."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

import core.security as security
from engines import assistant_crm_tools as crm
from routes import chantiers, clients, documents as D

USER = {"user_id": "u_test", "role": "admin", "account_type": "pro"}


@pytest.fixture()
def mem_db(monkeypatch):
    db = AsyncMongoMockClient()["crm_test"]
    for mod in (D, clients, chantiers):
        monkeypatch.setattr(mod, "db", db)
    monkeypatch.setattr(chantiers, "ATTACH_KINDS", {
        "document": (db.pro_documents, "doc_id"), "plan": (db.plans_takeoff, "plan_id")})

    async def _pro(user=None):
        return user
    monkeypatch.setattr(security, "pro_required", _pro)
    return db


def run(coro):
    return asyncio.run(coro)


def test_invoice_from_assistant_quote_is_linked_to_existing_client(mem_db):
    async def scenario():
        c = await clients.create_client(clients.ClientIn(company="Cunha Jardins"), user=USER)
        # Brouillon de l'assistant : seulement un nom libre, sans client_id.
        await mem_db.pro_documents.insert_one({
            "doc_id": "doc_q1", "user_id": USER["user_id"], "doc_type": "quote", "status": "signed",
            "client_id": None, "client": {"last_name": "cunha jardins"}, "client_name": "cunha jardins",
            "lines": [{"designation": "Manutenção", "qty": 1, "unit_price_ht": 100, "vat_rate": 23}],
            "number": "ORC-1", "title": "Jardim Braga"})
        inv = await D.quote_to_invoice("doc_q1", D.ToInvoiceIn(mode="total", pct=100), user=USER)
        assert inv["client_id"] == c["client_id"]
        q = await mem_db.pro_documents.find_one({"doc_id": "doc_q1"})
        assert q["client_id"] == c["client_id"]
        summary = await D.client_summary(c["client_id"], user=USER)
        assert [i["doc_id"] for i in summary["invoices"]] == [inv["doc_id"]]
        assert len(summary["quotes"]) == 1
    run(scenario())


def test_invoice_without_any_crm_client_creates_the_file(mem_db):
    async def scenario():
        doc = {"doc_id": "doc_i", "client_id": None, "client": {"last_name": "Novo Cliente"}}
        await D.ensure_client_link(USER, doc)
        assert doc["client_id"]
        assert await mem_db.clients.count_documents({"user_id": USER["user_id"]}) == 1
        # Idempotente: um segundo documento reutiliza a mesma ficha.
        doc2 = {"doc_id": "doc_j", "client_id": None, "client": {"last_name": "novo cliente"}}
        await D.ensure_client_link(USER, doc2)
        assert doc2["client_id"] == doc["client_id"]
        assert await mem_db.clients.count_documents({"user_id": USER["user_id"]}) == 1
    run(scenario())


def test_client_summary_backfills_existing_orphan_invoices(mem_db):
    async def scenario():
        c = await clients.create_client(clients.ClientIn(first_name="Ana", last_name="Silva", email="ana@ex.pt"), user=USER)
        await mem_db.pro_documents.insert_many([
            {"doc_id": "i1", "user_id": USER["user_id"], "doc_type": "invoice", "client_id": None,
             "client": {"email": "ANA@ex.pt"}, "created_at": "1"},
            {"doc_id": "i2", "user_id": USER["user_id"], "doc_type": "invoice",
             "client": {"first_name": "ana", "last_name": "silva"}, "created_at": "2"},
            {"doc_id": "i3", "user_id": USER["user_id"], "doc_type": "invoice", "client_id": None,
             "client": {"last_name": "Outra Pessoa"}, "created_at": "3"},
            {"doc_id": "i4", "user_id": "other_user", "doc_type": "invoice", "client_id": None,
             "client": {"email": "ana@ex.pt"}, "created_at": "4"},
        ])
        s = await D.client_summary(c["client_id"], user=USER)
        assert sorted(i["doc_id"] for i in s["invoices"]) == ["i1", "i2"]
        assert (await mem_db.pro_documents.find_one({"doc_id": "i4"}))["client_id"] is None
    run(scenario())


def test_assistant_creates_client_and_project(mem_db):
    async def scenario():
        conv = {"conversation_id": "c1", "user_id": USER["user_id"]}
        r = await crm.execute_crm_tool("create_client", {"company": "Cunha Jardins", "first_name": "", "last_name": "",
                                       "email": "", "phone": "", "address": "", "postal_code": "", "city": "Braga",
                                       "nif": "", "notes": ""}, USER, conv, mem_db)
        assert r["ok"] and not r["duplicate"]
        cid = r["client"]["client_id"]
        again = await crm.execute_crm_tool("create_client", {"company": "cunha jardins", "first_name": "", "last_name": "",
                                           "email": "", "phone": "", "address": "", "postal_code": "", "city": "",
                                           "nif": "", "notes": ""}, USER, conv, mem_db)
        assert again["duplicate"] and again["client"]["client_id"] == cid
        p = await crm.execute_crm_tool("create_project", {"name": "Jardim Braga", "client_id": cid, "address": "",
                                       "postal_code": "", "city": "", "status": "en_cours", "notes": ""}, USER, conv, mem_db)
        assert p["ok"] and p["project"]["client_id"] == cid and p["project"]["client_name"] == "Cunha Jardins"
        found = await crm.execute_crm_tool("find_projects", {"query": "braga"}, USER, conv, mem_db)
        assert found["projects"][0]["chantier_id"] == p["project"]["chantier_id"]
        await mem_db.pro_documents.insert_one({"doc_id": "d1", "user_id": USER["user_id"], "doc_type": "quote", "client_id": None})
        link = await crm.execute_crm_tool("link_to_client", {"doc_id": "d1", "client_id": cid}, USER, conv, mem_db)
        assert link["ok"]
        att = await crm.execute_crm_tool("attach_to_project", {"chantier_id": p["project"]["chantier_id"], "kind": "document",
                                         "ref_id": "d1"}, USER, conv, mem_db)
        assert att["ok"]
    run(scenario())


def test_crm_tools_exposed_to_professionals_only():
    from routes import assistant as A
    pro = {t.get("name") for t in A.tools_for({"user_id": "u", "account_type": "pro", "role": "admin"})}
    assert crm.CRM_TOOL_NAMES <= pro
    part = {t.get("name") for t in A.tools_for({"user_id": "u", "account_type": "particulier"})}
    assert not (crm.CRM_TOOL_NAMES & part)
