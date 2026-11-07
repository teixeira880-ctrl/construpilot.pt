"""Auditoria V2 (07/11/2026) — assinatura, pagamentos e envio, com base simulada.

Corre sem MongoDB real (mongomock_motor). Requer as variáveis do backend
(MONGO_URL, DB_NAME, JWT_SECRET…) como o resto da suite.
"""
import asyncio
import hashlib

import pytest

mm = pytest.importorskip("mongomock_motor")


@pytest.fixture()
def mdb(monkeypatch):
    from routes import plans_export, documents
    from engines import monetization
    db = mm.AsyncMongoMockClient()["audit_v2"]
    for mod in (plans_export, documents, monetization):
        monkeypatch.setattr(mod, "db", db)
    # nada de e-mails / push reais
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(plans_export, "_notify_pro_on_signature", _noop)
    monkeypatch.setattr(plans_export, "_auto_deposit_after_signature", _noop)
    return db


def _req():
    from starlette.requests import Request
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest"), (b"x-forwarded-for", b"203.0.113.9")],
                    "client": ("127.0.0.1", 1), "method": "POST", "path": "/"})


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


async def _seed(db, *, expires="2999-01-01T00:00:00+00:00"):
    from routes.documents import _content_hash
    doc = {"doc_id": "doc_1", "user_id": "u1", "doc_type": "quote", "title": "Pintura",
           "lines": [{"designation": "Pintura", "qty": 10, "unit_price_ht": 25}], "status": "sent"}
    await db.pro_documents.insert_one(dict(doc))
    await db.quote_sends.insert_one({"log_id": "qs_1", "doc_id": "doc_1", "user_id": "u1",
                                     "signature_token": "tok", "signed": False, "client_email": "c@x.pt",
                                     "sent_content_hash": _content_hash(doc),
                                     "signature_expires_at": expires})


def _sig():
    from routes.plans_export import SignatureIn
    return SignatureIn(signature_b64="data:image/png;base64," + "A" * 200, signer_name="Cliente Teste")


def test_signature_ok_then_not_twice(mdb, monkeypatch):
    from routes import plans_export, documents

    async def _freeze(*a, **k):
        return {}
    monkeypatch.setattr(documents, "_freeze_document", _freeze)

    async def go():
        await _seed(mdb)
        res = await plans_export.submit_signature("tok", _sig(), _req())
        assert res["ok"]
        log = await mdb.quote_sends.find_one({"log_id": "qs_1"})
        assert log["signature_evidence"]["ip"] == "203.0.113.9"
        assert len(log["signature_evidence"]["content_sha256"]) == 64
        with pytest.raises(Exception) as e:
            await plans_export.submit_signature("tok", _sig(), _req())
        assert getattr(e.value, "status_code", None) == 400
    _run(go())


def test_signature_refused_if_quote_changed(mdb):
    from routes import plans_export

    async def go():
        await _seed(mdb)
        await mdb.pro_documents.update_one({"doc_id": "doc_1"}, {"$set": {"lines.0.unit_price_ht": 30}})
        with pytest.raises(Exception) as e:
            await plans_export.submit_signature("tok", _sig(), _req())
        assert getattr(e.value, "status_code", None) == 409
    _run(go())


def test_signature_refused_if_expired(mdb):
    from routes import plans_export

    async def go():
        await _seed(mdb, expires="2020-01-01T00:00:00+00:00")
        with pytest.raises(Exception) as e:
            await plans_export.submit_signature("tok", _sig(), _req())
        assert getattr(e.value, "status_code", None) == 410
    _run(go())


def test_signature_expiry_from_validity():
    from routes.documents import _signature_expiry
    assert _signature_expiry({"validity_days": 30, "issue_date": "2026-11-01T10:00:00+00:00"}).startswith("2026-12-01")
    assert _signature_expiry({"valid_until": "2026-12-01"}) == "2026-12-01T23:59:59+00:00"
    assert _signature_expiry({"validity_days": 0}) is None


def test_webhook_refused_without_secret(monkeypatch):
    from engines import monetization
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(monetization, "STRIPE_WEBHOOK_SECRET", "")
    with pytest.raises(RuntimeError):
        _run(monetization.handle_webhook(b"{}", "t=1,v1=abc"))


def test_subscription_recovers_and_addon_revoked(mdb):
    from engines import monetization

    async def go():
        await mdb.entitlements.insert_one({"user_id": "u1", "plan_id": "pro_monthly", "status": "active",
                                           "stripe_subscription_id": "sub_1", "granted_at": "2026-11-01"})
        await mdb.users.insert_one({"user_id": "u1", "invoicing_addon": True, "invoicing_addon_sub": "sub_2"})
        await monetization._webhook_invoice_failed({"subscription": "sub_1"})
        assert (await mdb.entitlements.find_one({"stripe_subscription_id": "sub_1"}))["status"] == "past_due"
        await monetization._webhook_invoice_paid({"subscription": "sub_1"})
        assert (await mdb.entitlements.find_one({"stripe_subscription_id": "sub_1"}))["status"] == "active"
        await monetization.revoke_entitlement("sub_2", "cancelled")
        assert (await mdb.users.find_one({"user_id": "u1"}))["invoicing_addon"] is False
    _run(go())


def test_send_blocked_when_prices_missing(mdb):
    from fastapi import BackgroundTasks
    from routes import documents

    async def go():
        await mdb.pro_documents.insert_one({"doc_id": "doc_2", "user_id": "u1", "doc_type": "quote",
                                            "lines": [{"designation": "Telha", "qty": 10, "unit_price_ht": 0,
                                                       "price_missing": True}]})
        body = documents.DocSendIn(client_email="c@x.pt")
        with pytest.raises(Exception) as e:
            await documents.send_document("doc_2", body, BackgroundTasks(), {"user_id": "u1", "email_verified": True})
        assert getattr(e.value, "status_code", None) == 409
        assert (await mdb.pro_documents.find_one({"doc_id": "doc_2"})).get("number") is None
    _run(go())
