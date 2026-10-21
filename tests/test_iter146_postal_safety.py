"""Simulated storage and provider only. Never invokes real sendCourrier."""
import asyncio
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

sys.path.append("/app/backend")

from engines import mercifacteur as mf
from engines import postal_delivery as pd


class FakeStore:
    def __init__(self):
        self.rows = {}

    async def find_one(self, query, *args):
        return next((deepcopy(doc) for doc in self.rows.values() if all(
            doc.get(key) > value["$gt"] if isinstance(value, dict) and "$gt" in value else doc.get(key) == value
            for key, value in query.items())), None)

    async def insert_one(self, doc):
        if doc["_id"] in self.rows:
            raise DuplicateKeyError("simulated duplicate")
        self.rows[doc["_id"]] = deepcopy(doc)

    async def update_one(self, query, update):
        if query.get("_id") in self.rows:
            self.rows[query["_id"]].update(update.get("$set", {}))


def isolated(monkeypatch, outcome):
    user = {"user_id": "unit_user", "organization_id": "org_unit"}
    recipient = {"nom": "TEST", "adresse1": "TEST", "cp": "75001", "ville": "TEST", "pays": "france"}
    quote = {"quote_id": "unit_quote", "user_id": "unit_user", "token": "unit_campaign",
        "opp_id": "unit_opp", "recipient": recipient, "mode": "normal", "context_hash": "ctx",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10), "lock_id": "unit_lock",
        "price": {"total_ttc": 2.26}, "pdf": b"simulated PDF", "sender": {}, "address_source": "terrain",
        "company_key": "org:org_unit",
        "offer": {"phase": "demo", "next_kind": "demo", "customer_amount_cents": 0}}
    quotes, postal = FakeStore(), FakeStore()
    quotes.rows["quote"] = quote
    monkeypatch.setattr(pd, "db", SimpleNamespace(radar_postal_quotes=quotes, radar_postal=postal, radar_prospections=FakeStore()))
    monkeypatch.setattr(pd.postal_offer, "company_key", lambda _user: "org:org_unit")

    async def reserve(*_args, **_kwargs):
        return None

    async def offer_for(_user):
        return pd.postal_offer._offer({"count": 0, "credits": 0, "sends": []})

    monkeypatch.setattr(pd.postal_offer, "offer_for", offer_for)

    async def settle(*_args, **_kwargs):
        return None

    monkeypatch.setattr(pd.postal_offer, "reserve", reserve)
    monkeypatch.setattr(pd.postal_offer, "settle", settle)
    calls = []

    async def token(*args, **kwargs):
        return "simulated-token"

    async def send(*args, **kwargs):
        calls.append(kwargs)
        await asyncio.sleep(0.01)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(mf, "get_token", token)
    monkeypatch.setattr(mf, "send_letter", send)
    args = {"user": user, "user_id": "unit_user", "token": "unit_campaign", "quote_id": "unit_quote", "recipient": recipient,
            "mode": "normal", "context_hash": "ctx"}
    return args, calls, quotes, postal


def test_concurrent_duplicate_only_one_provider_call(monkeypatch):
    args, calls, _, postal = isolated(monkeypatch, {"envoi_id": ["99999"]})

    async def run():
        return await asyncio.gather(pd.deliver(**args), pd.deliver(**args), return_exceptions=True)

    results = asyncio.run(run())
    assert len(calls) == 1
    assert calls[0]["reference"] == "unit_lock"
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1
    assert postal.rows["unit_lock"]["status"] == "submitted"


@pytest.mark.parametrize("outcome", [mf.PostalProviderError("timeout", "simulated timeout", uncertain=True), {"envoi_id": []}])
def test_ambiguous_send_persisted_and_never_retried(monkeypatch, outcome):
    args, calls, _, postal = isolated(monkeypatch, outcome)
    first = asyncio.run(pd.deliver(**args))
    assert first["status"] == "unknown"
    assert postal.rows["unit_lock"]["status"] == "unknown"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pd.deliver(**args))
    assert exc.value.status_code == 409
    assert len(calls) == 1


@pytest.mark.parametrize("change", [{"user_id": "other"}, {"token": "other"}, {"context_hash": "changed"}, {"mode": "lrar"}, {"recipient": {"nom": "different"}}])
def test_tampered_quote_never_calls_provider(monkeypatch, change):
    args, calls, _, _ = isolated(monkeypatch, {"envoi_id": "99999"})
    with pytest.raises(HTTPException):
        asyncio.run(pd.deliver(**{**args, **change}))
    assert calls == []


def test_expired_quote_never_calls_provider(monkeypatch):
    args, calls, quotes, _ = isolated(monkeypatch, {"envoi_id": "99999"})
    quotes.rows["quote"]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(HTTPException):
        asyncio.run(pd.deliver(**args))
    assert calls == []


@pytest.mark.parametrize("response,uncertain", [
    (httpx.Response(401, json={"success": False, "error": {"code": "INVALID_TOKEN_FOR_IP"}}), False),
    (httpx.Response(502, text="<html>Cloudflare provider secret detail</html>"), True),
    (httpx.Response(200, json={"unexpected": "shape"}), True),
])
def test_provider_failure_single_call_no_html_leak(monkeypatch, response, uncertain):
    calls = []

    class Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def request(self, *args, **kwargs):
            calls.append(args)
            return response

    monkeypatch.setattr(mf.httpx, "AsyncClient", Client)
    with pytest.raises(mf.PostalProviderError) as exc:
        asyncio.run(mf._call("POST", "sendCourrier", {}))
    assert len(calls) == 1
    assert exc.value.uncertain is uncertain
    assert "<html>" not in str(exc.value) and "secret detail" not in str(exc.value)