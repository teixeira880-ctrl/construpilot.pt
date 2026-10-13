"""Iter155 — Admin expenses API guards, CRUD/reconciliation and metering/context contracts."""

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import requests

from engines.expenses import context as expense_context
from engines.expenses import metering


def _base_url() -> str:
    env = os.environ.get("REACT_APP_BACKEND_URL")
    if env:
        return env.rstrip("/")
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _base_url()
ADMIN_CREDS = (os.environ["TEST_ADMIN_EMAIL"], os.environ["TEST_ADMIN_PASSWORD"])
NONADMIN_CREDS = (os.environ["TEST_PRO_EMAIL"], os.environ["TEST_PRO_PASSWORD"])
MONTH = "2025-02"


def _login(email: str, password: str) -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("token") or response.json().get("access_token")
    assert isinstance(token, str) and token
    return token


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    return {"Authorization": f"Bearer {_login(*ADMIN_CREDS)}"}


@pytest.fixture(scope="module")
def nonadmin_headers() -> dict:
    return {"Authorization": f"Bearer {_login(*NONADMIN_CREDS)}"}


def _create_manual(headers: dict, *, provider: str = "other", amount: str = "12.34", currency: str = "EUR",
                   scope: str = "single", source_ref: str | None = None, is_test: bool = True,
                   feature: str = "iter155", settled_eur: str | None = None, settlement_ref: str | None = None):
    ref = source_ref or f"ITER155-{uuid4().hex[:12]}"
    payload = {
        "provider": provider,
        "source_ref": ref,
        "amount": amount,
        "currency": currency,
        "occurred_on": f"{MONTH}-10",
        "feature": feature,
        "scope": scope,
        "confirmed_charge": True,
        "is_test": is_test,
    }
    if settled_eur is not None:
        payload["settled_eur"] = settled_eur
    if settlement_ref is not None:
        payload["settlement_ref"] = settlement_ref
    response = requests.post(f"{BASE_URL}/api/admin/expenses/entries", json=payload, headers=headers, timeout=30)
    return response, payload


@pytest.mark.parametrize(
    "method,path,body,params",
    [
        ("GET", "/api/admin/expenses/overview", None, {"month": MONTH}),
        ("GET", "/api/admin/expenses/ledger", None, {"month": MONTH}),
        ("GET", "/api/admin/expenses/selectors", None, None),
        ("GET", "/api/admin/expenses/trend", None, {"month": MONTH}),
        ("GET", "/api/admin/expenses/export.csv", None, {"month": MONTH}),
        ("POST", "/api/admin/expenses/sync-local", None, None),
        ("GET", "/api/admin/expenses/budgets", None, {"month": MONTH}),
        ("PUT", "/api/admin/expenses/budgets", {"provider": "other", "month": MONTH, "amount_eur": "100.00", "warning_percent": 80}, None),
        ("GET", "/api/admin/expenses/rates", None, None),
        ("PUT", "/api/admin/expenses/rates", {"provider": "other", "model": "iter155-guard", "currency": "EUR", "mode": "unit", "unit": "calls", "per_units": "1", "price": "1.000000", "input_price": "0", "output_price": "0", "effective_from": f"{MONTH}-01", "source_ref": "ITER155-GUARD-RATE"}, None),
    ],
)
def test_admin_expenses_endpoints_require_auth(method, path, body, params, nonadmin_headers):
    unauth = requests.request(method, f"{BASE_URL}{path}", json=body, params=params, timeout=40)
    assert unauth.status_code == 401, f"{path} unauth expected 401, got {unauth.status_code}"

    nonadmin = requests.request(method, f"{BASE_URL}{path}", json=body, params=params, headers=nonadmin_headers, timeout=40)
    assert nonadmin.status_code == 403, f"{path} nonadmin expected 403, got {nonadmin.status_code}"


def test_month_validation_and_selectors_serialization(admin_headers):
    invalid = requests.get(f"{BASE_URL}/api/admin/expenses/overview", params={"month": "2025-13"}, headers=admin_headers, timeout=30)
    assert invalid.status_code == 422

    selectors = requests.get(f"{BASE_URL}/api/admin/expenses/selectors", headers=admin_headers, timeout=30)
    assert selectors.status_code == 200
    data = selectors.json()
    assert isinstance(data.get("users"), list)
    assert isinstance(data.get("companies"), list)
    assert isinstance(data.get("features"), list)
    if data["users"]:
        assert "_id" not in data["users"][0]
    if data["companies"]:
        assert "_id" not in data["companies"][0]


def test_entries_crud_conflict_dedupe_and_no_implicit_fx(admin_headers):
    # invalid non-EUR settlement evidence must be rejected
    invalid_fx, _ = _create_manual(
        admin_headers,
        provider="other",
        amount="10.00",
        currency="USD",
        settled_eur="9.50",
        settlement_ref=None,
        source_ref=f"ITER155-FX-{uuid4().hex[:8]}",
    )
    assert invalid_fx.status_code == 422

    create, payload = _create_manual(
        admin_headers,
        provider="other",
        amount="-10.500000",
        currency="USD",
        settled_eur="-9.500000",
        settlement_ref="BANK-ITER155",
        source_ref=f"ITER155-DUPE-{uuid4().hex[:8]}",
    )
    assert create.status_code == 200, create.text
    row = create.json()
    assert row["source_ref"] == payload["source_ref"]
    assert row["amount"] == "-10.5"
    assert row["currency"] == "USD"
    assert row["amount_eur"] == "-9.5"
    assert row["is_test"] is True

    duplicate, _ = _create_manual(
        admin_headers,
        provider="other",
        amount="1",
        currency="EUR",
        source_ref=payload["source_ref"],
    )
    assert duplicate.status_code == 409

    entry_id = row["entry_id"]
    wrong_confirm = requests.put(
        f"{BASE_URL}/api/admin/expenses/entries/{entry_id}/confirmation",
        headers=admin_headers,
        json={
            "source_ref": payload["source_ref"],
            "amount": "-10.500000",
            "currency": "USD",
            "settled_eur": "-9.500000",
            "settlement_ref": "BANK-ITER155",
            "confirmed_charge": True,
            "version": 4,
        },
        timeout=30,
    )
    assert wrong_confirm.status_code == 409

    ok_confirm = requests.put(
        f"{BASE_URL}/api/admin/expenses/entries/{entry_id}/confirmation",
        headers=admin_headers,
        json={
            "source_ref": payload["source_ref"],
            "amount": "-10.500000",
            "currency": "USD",
            "settled_eur": "-9.500000",
            "settlement_ref": "BANK-ITER155",
            "confirmed_charge": True,
            "version": 0,
        },
        timeout=30,
    )
    assert ok_confirm.status_code == 200
    assert ok_confirm.json().get("ok") is True

    wrong_void = requests.delete(
        f"{BASE_URL}/api/admin/expenses/entries/{entry_id}",
        headers=admin_headers,
        params={"version": 0},
        timeout=30,
    )
    assert wrong_void.status_code == 409

    ok_void = requests.delete(
        f"{BASE_URL}/api/admin/expenses/entries/{entry_id}",
        headers=admin_headers,
        params={"version": 1},
        timeout=30,
    )
    assert ok_void.status_code == 200
    assert ok_void.json().get("ok") is True


def test_monthly_total_reconciliation_and_no_double_count(admin_headers):
    op_ref = f"ITER155-OP-{uuid4().hex[:8]}"
    total_ref = f"ITER155-TOTAL-{uuid4().hex[:8]}"
    created_total = False

    op_resp, _ = _create_manual(admin_headers, provider="other", amount="20.00", currency="EUR", scope="single", source_ref=op_ref)
    assert op_resp.status_code == 200, op_resp.text
    op_id = op_resp.json()["entry_id"]

    total_resp, _ = _create_manual(admin_headers, provider="other", amount="100.00", currency="EUR", scope="monthly_total", source_ref=total_ref)
    assert total_resp.status_code in {200, 409}, total_resp.text
    total_id = total_resp.json().get("entry_id") if total_resp.status_code == 200 else None
    created_total = total_resp.status_code == 200

    overview = requests.get(
        f"{BASE_URL}/api/admin/expenses/overview",
        headers=admin_headers,
        params={"month": MONTH, "provider": "other", "include_test": "true"},
        timeout=30,
    )
    assert overview.status_code == 200, overview.text
    summary = overview.json()["summary"]
    assert summary["operations"] >= 1
    assert Decimal(summary["confirmed_eur"]) >= Decimal("100")

    ledger = requests.get(
        f"{BASE_URL}/api/admin/expenses/ledger",
        headers=admin_headers,
        params={"month": MONTH, "provider": "other", "include_test": "true", "page_size": 100},
        timeout=30,
    )
    assert ledger.status_code == 200
    rows = ledger.json()["items"]
    op_row = next((r for r in rows if r.get("entry_id") == op_id), None)
    assert op_row is not None
    assert op_row.get("evidence") == "reconciled"
    assert op_row.get("amount") is None
    assert op_row.get("amount_eur") is None

    # cleanup (best-effort)
    requests.delete(f"{BASE_URL}/api/admin/expenses/entries/{op_id}", headers=admin_headers, params={"version": op_row.get("version", 0)}, timeout=30)
    if created_total and total_id:
        requests.delete(f"{BASE_URL}/api/admin/expenses/entries/{total_id}", headers=admin_headers, params={"version": 0}, timeout=30)


def test_budget_and_rates_roundtrip_restore(admin_headers):
    budget_id = hashlib.sha256(f"other|{MONTH}".encode()).hexdigest()
    rates_before = requests.get(f"{BASE_URL}/api/admin/expenses/rates", headers=admin_headers, timeout=30)
    assert rates_before.status_code == 200

    prev_budget_resp = requests.get(f"{BASE_URL}/api/admin/expenses/budgets", headers=admin_headers, params={"month": MONTH}, timeout=30)
    assert prev_budget_resp.status_code == 200
    previous_budget = next((b for b in prev_budget_resp.json()["items"] if b.get("budget_id") == budget_id), None)

    set_budget = requests.put(
        f"{BASE_URL}/api/admin/expenses/budgets",
        headers=admin_headers,
        json={"provider": "other", "month": MONTH, "amount_eur": "99.99", "warning_percent": 70},
        timeout=30,
    )
    assert set_budget.status_code == 200
    assert set_budget.json().get("ok") is True

    overview = requests.get(
        f"{BASE_URL}/api/admin/expenses/overview",
        headers=admin_headers,
        params={"month": MONTH, "provider": "other", "include_test": "true"},
        timeout=30,
    )
    assert overview.status_code == 200
    budget_row = next((b for b in overview.json().get("budgets", []) if b.get("budget_id") == budget_id), None)
    assert budget_row is not None
    assert budget_row["automatic_blocking"] is False
    assert budget_row.get("percent") is None or isinstance(budget_row.get("percent"), float)
    assert budget_row.get("estimated_percent") is None or isinstance(budget_row.get("estimated_percent"), float)

    rate_model = f"iter155-{uuid4().hex[:8]}"
    effective_from = f"{MONTH}-01"
    rate_id = hashlib.sha256(f"other|{rate_model}|{effective_from}".encode()).hexdigest()
    put_rate = requests.put(
        f"{BASE_URL}/api/admin/expenses/rates",
        headers=admin_headers,
        json={
            "provider": "other",
            "model": rate_model,
            "currency": "EUR",
            "mode": "unit",
            "unit": "calls",
            "per_units": "1",
            "price": "2.500000",
            "input_price": "0",
            "output_price": "0",
            "effective_from": effective_from,
            "source_ref": f"ITER155-RATE-{uuid4().hex[:8]}",
        },
        timeout=30,
    )
    assert put_rate.status_code == 200
    assert put_rate.json().get("ok") is True

    rates_after = requests.get(f"{BASE_URL}/api/admin/expenses/rates", headers=admin_headers, timeout=30)
    assert rates_after.status_code == 200
    target_rate = next((r for r in rates_after.json()["items"] if r.get("rate_id") == rate_id), None)
    assert target_rate is not None
    assert "_id" not in target_rate

    del_rate = requests.delete(f"{BASE_URL}/api/admin/expenses/rates/{rate_id}", headers=admin_headers, timeout=30)
    assert del_rate.status_code == 200
    assert del_rate.json().get("ok") is True

    # restore budget to previous state
    if previous_budget:
        restore = requests.put(
            f"{BASE_URL}/api/admin/expenses/budgets",
            headers=admin_headers,
            json={
                "provider": previous_budget["provider"],
                "month": previous_budget["month"],
                "amount_eur": previous_budget["amount_eur"],
                "warning_percent": previous_budget["warning_percent"],
            },
            timeout=30,
        )
        assert restore.status_code == 200
    else:
        requests.delete(f"{BASE_URL}/api/admin/expenses/budgets/{budget_id}", headers=admin_headers, timeout=30)


def test_export_csv_and_sync_local(admin_headers):
    export = requests.get(
        f"{BASE_URL}/api/admin/expenses/export.csv",
        headers=admin_headers,
        params={"month": MONTH, "include_test": "true"},
        timeout=60,
    )
    assert export.status_code == 200
    assert export.headers.get("Content-Disposition", "").startswith("attachment; filename=")
    assert "date_utc;provider;feature" in export.text

    sync = requests.post(f"{BASE_URL}/api/admin/expenses/sync-local", headers=admin_headers, timeout=120)
    assert sync.status_code in {200, 409}
    if sync.status_code == 200:
        payload = sync.json()
        assert payload.get("status") in {"ok", "partial"}


def test_meteredchat_passthrough_and_usage_capture(monkeypatch):
    calls = []

    class FakeDone:
        def __init__(self, usage):
            self.usage = usage

    class FakeLlmChat:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def with_model(self, provider, model):
            self.provider = provider
            self.model = model
            return self

        async def send_message(self, payload):
            return {"payload": payload, "usage": {"input_tokens": 10, "output_tokens": 5}}

        async def send_message_multimodal_response(self, payload):
            return ({"payload": payload, "usage": {"prompt_tokens": 8, "completion_tokens": 4}}, ["img1", "img2"])

        async def stream_message(self, _payload):
            yield "chunk-1"
            yield FakeDone({"input_tokens": 3, "output_tokens": 2})

    async def fake_observe(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(metering, "LlmChat", FakeLlmChat)
    monkeypatch.setattr(metering, "StreamDone", FakeDone)
    monkeypatch.setattr(metering, "observe", fake_observe)

    async def _run():
        wrapped = metering.MeteredChat(api_key="x", session_id="s", system_message="sys", expense_feature="coach").with_model("openai", "gpt-test")
        one = await wrapped.send_message({"x": 1})
        two = await wrapped.send_message_multimodal_response({"m": 1})
        stream = []
        async for ev in wrapped.stream_message({"s": 1}):
            stream.append(ev)
        return one, two, stream

    one, two, stream = asyncio.run(_run())
    assert one["payload"] == {"x": 1}
    assert two[0]["payload"] == {"m": 1}
    assert two[1] == ["img1", "img2"]
    assert stream[0] == "chunk-1"
    assert len(calls) == 3
    assert all(c["feature"] == "coach" for c in calls)


def test_expense_context_isolation_and_middleware_reset():
    async def _task(uid: str):
        expense_context.bind({"user_id": uid, "organization_id": f"org-{uid}"})
        await asyncio.sleep(0)
        return expense_context.actor()

    async def _run_parallel():
        a, b = await asyncio.gather(_task("u1"), _task("u2"))
        return a, b

    a, b = asyncio.run(_run_parallel())
    assert a["user_id"] == "u1"
    assert b["user_id"] == "u2"

    async def app(scope, receive, send):
        assert expense_context.actor() == {}
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def _call_middleware():
        expense_context.bind({"user_id": "before", "organization_id": "org-before"})
        wrapped = expense_context.ExpenseContextMiddleware(app)
        sent = []

        async def _send(message):
            sent.append(message)

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        await wrapped({"type": "http", "method": "GET", "path": "/"}, _receive, _send)
        return sent, expense_context.actor()

    sent, actor_after = asyncio.run(_call_middleware())
    assert sent[0]["type"] == "http.response.start"
    assert actor_after.get("user_id") == "before"