"""Iter 146 — Postal non-billable workflow regression + isolated send-path guards."""

from __future__ import annotations

import os
import sys
import asyncio
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from pypdf import PdfWriter

sys.path.append("/app/backend")
from engines import mercifacteur as mf
from engines import postal_delivery as pd


def _base_url() -> str:
    env_url = os.environ.get("REACT_APP_BACKEND_URL")
    if env_url:
        return env_url.rstrip("/")
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    pytest.skip("Missing REACT_APP_BACKEND_URL")


BASE_URL = _base_url()


def _login(email: str, password: str) -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("token")
    assert isinstance(token, str) and token
    return token


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_campaign(token: str) -> tuple[str, dict]:
    auth = _headers(token)
    opp_resp = requests.get(
        f"{BASE_URL}/api/radar/opportunities?page=1&page_size=50",
        headers=auth,
        timeout=60,
    )
    assert opp_resp.status_code == 200, opp_resp.text
    items = opp_resp.json().get("opportunities") or []
    assert items, "No opportunities available"
    opp = items[0]

    create = requests.post(
        f"{BASE_URL}/api/radar/opportunities/{opp['id']}/prospection",
        headers=auth,
        json={"message": ""},
        timeout=60,
    )
    assert create.status_code == 200, create.text
    payload = create.json()
    assert payload.get("token", "").startswith("rop_")
    return payload["token"], opp


def _recipient_from_opp(opp: dict) -> dict:
    return {
        "nom": (opp.get("promoteur") or {}).get("nom") or "Destinataire Test",
        "societe": (opp.get("promoteur") or {}).get("societe") or "",
        "adresse1": (opp.get("adresse") or "10 rue de Rivoli")[:200],
        "adresse2": "",
        "cp": (opp.get("cp") or "75001")[:12],
        "ville": (opp.get("commune") or "Paris")[:100],
        "pays": "france",
    }


# ---------- live non-billable API checks ----------
def test_postal_price_real_modes_expected_totals():
    """Real provider GET price must return 200 and expected totals for one page."""
    token = _login("pro@construpilot.fr", "Pro2026!")
    expected = {"normal": 2.26, "suivi": 2.76, "lrar": 7.73}
    for mode, total in expected.items():
        response = requests.get(
            f"{BASE_URL}/api/radar/postal/price?mode={mode}",
            headers=_headers(token),
            timeout=45,
        )
        assert response.status_code == 200, f"mode={mode}: {response.text}"
        data = response.json()
        assert data["mode"] == mode
        assert data["pages"] == 1
        assert data["currency"] == "EUR"
        assert pytest.approx(data["total_ttc"], abs=0.01) == total


def test_postal_quote_blocks_missing_branding_for_pro_account():
    """Sender branding guard must fail in French before any billable send path."""
    token = _login("pro@construpilot.fr", "Pro2026!")
    campaign_token, opp = _create_campaign(token)
    recipient = _recipient_from_opp(opp)
    response = requests.post(
        f"{BASE_URL}/api/radar/prospection/{campaign_token}/postal/quote",
        headers=_headers(token),
        json={"recipient": recipient, "mode": "normal", "address_source": "terrain"},
        timeout=60,
    )
    assert response.status_code == 400, response.text
    detail = response.json().get("detail")
    assert isinstance(detail, str)
    assert "Renseignez l'adresse de votre entreprise" in detail


def test_postal_quote_success_admin_non_billable():
    """Quote endpoint should succeed for branded admin account and return immutable quote metadata."""
    token = _login("admin@construpilot.fr", "Construpilot2026!")
    campaign_token, opp = _create_campaign(token)
    recipient = _recipient_from_opp(opp)

    response = requests.post(
        f"{BASE_URL}/api/radar/prospection/{campaign_token}/postal/quote",
        headers=_headers(token),
        json={"recipient": recipient, "mode": "normal", "address_source": "terrain"},
        timeout=60,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data.get("quote_id"), str) and len(data["quote_id"]) >= 16
    assert data["mode"] == "normal"
    assert data["pages"] >= 1
    assert data["total_ttc"] > 0
    assert data["currency"] == "EUR"
    expiry = datetime.fromisoformat(data["expires_at"])
    now = datetime.now(timezone.utc)
    assert now < expiry <= now + timedelta(minutes=16)


def test_postal_quote_invalid_recipient_returns_422():
    """Quote endpoint must reject incomplete recipient payload."""
    token = _login("admin@construpilot.fr", "Construpilot2026!")
    campaign_token, _ = _create_campaign(token)
    invalid = {
        "recipient": {"nom": "", "adresse1": "", "cp": "", "ville": "", "pays": "france"},
        "mode": "normal",
        "address_source": "manual",
    }
    response = requests.post(
        f"{BASE_URL}/api/radar/prospection/{campaign_token}/postal/quote",
        headers=_headers(token),
        json=invalid,
        timeout=60,
    )
    assert response.status_code == 422, response.text


def test_postal_send_validation_fails_without_quote_and_confirmed_true():
    """Validation must fail with 422 before any provider call when quote/confirmed are invalid."""
    token = _login("admin@construpilot.fr", "Construpilot2026!")
    campaign_token, opp = _create_campaign(token)
    recipient = _recipient_from_opp(opp)
    response = requests.post(
        f"{BASE_URL}/api/radar/prospection/{campaign_token}/postal",
        headers=_headers(token),
        json={
            "recipient": recipient,
            "mode": "normal",
            "address_source": "terrain",
            "quote_id": "short",
            "confirmed": False,
        },
        timeout=60,
    )
    assert response.status_code == 422, response.text


def test_postal_history_contains_no_objectid_fields():
    """History response must not leak Mongo ObjectId fields."""
    token = _login("admin@construpilot.fr", "Construpilot2026!")
    campaign_token, _ = _create_campaign(token)
    response = requests.get(
        f"{BASE_URL}/api/radar/prospection/{campaign_token}/postal",
        headers=_headers(token),
        timeout=60,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    for row in data.get("sends", []):
        assert "_id" not in row


def test_provider_history_keeps_known_receipt_4122403():
    """Real non-billable provider history must still include known authentic receipt 4122403."""
    if not mf.configured():
        pytest.skip("Postal provider not configured")
    payload = asyncio.run(mf.list_sends())
    dumped = json.dumps(payload, ensure_ascii=False)
    assert dumped.count("4122403") >= 1


# ---------- isolated unit tests (no real sendCourrier) ----------
def test_create_quote_counts_pdf_pages(monkeypatch):
    """create_quote must use pypdf page count for provider pricing."""
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)
    raw = BytesIO()
    writer.write(raw)
    pdf = raw.getvalue()

    calls = {"pages": None}

    async def fake_price(mode="normal", pages=1, pays="france"):
        calls["pages"] = pages
        return {
            "mode": mode,
            "pages": pages,
            "postage": 1.0,
            "content_ttc": 1.0,
            "total_ttc": 2.0,
            "currency": "EUR",
        }

    class FakeQuotes:
        async def create_index(self, *_args, **_kwargs):
            return None

        async def insert_one(self, _doc):
            return None

    class FakePostal:
        async def find_one(self, *_args, **_kwargs):
            return None

    fake_db = SimpleNamespace(radar_postal=FakePostal(), radar_postal_quotes=FakeQuotes())
    monkeypatch.setattr(pd, "db", fake_db)
    monkeypatch.setattr(pd.mf, "postage_price", fake_price)

    class FakeOffer:
        def model_dump(self):
            return {"phase": "demo", "customer_amount_cents": 0, "eligible": True}

    async def fake_require_available(_user):
        return FakeOffer()

    monkeypatch.setattr(pd.postal_offer, "require_available", fake_require_available)
    monkeypatch.setattr(pd.postal_offer, "company_key", lambda _user: "org:test")
    user = {"user_id": "u1", "organization_id": "test"}

    out = asyncio.run(pd.create_quote(
        user=user,
        user_id="u1",
        token="rop_x",
        opp_id="opp_1",
        recipient={"nom": "A", "societe": "", "adresse1": "10 rue", "adresse2": "", "cp": "75001", "ville": "Paris", "pays": "france"},
        mode="normal",
        address_source="terrain",
        sender={"nom": "Sender", "adresse1": "10", "cp": "75001", "ville": "Paris", "pays": "france"},
        pdf=pdf,
        context_hash="ctx",
    ))
    assert calls["pages"] == 2
    assert out["pages"] == 2
    assert out["total_ttc"] == 2.0


def test_price_missing_amount_raises_invalid_price(monkeypatch):
    """Provider price missing amount must raise error; never fallback to 0 EUR."""

    async def fake_request(_method, _op, **_kw):
        return {"affranchissement": {"FRANCE": {}}, "content": {"totalContentTtc": 0.0}}

    monkeypatch.setattr(mf, "request", fake_request)
    async def _runner():
        with pytest.raises(mf.PostalProviderError) as exc:
            await mf.postage_price(mode="normal", pages=1)
        return exc.value

    err = asyncio.run(_runner())
    assert err.code == "invalid_price"


def test_deliver_uses_single_send_call_and_submitted_only_with_valid_envoi_id(monkeypatch):
    """deliver() should call mocked provider once and persist submitted state when envoi_id is valid."""

    now = datetime.now(timezone.utc)
    quote_doc = {
        "quote_id": "q_1234567890123456",
        "user_id": "u1",
        "token": "rop_1",
        "opp_id": "opp_1",
        "recipient": {"nom": "Dest", "societe": "", "adresse1": "10 rue", "adresse2": "", "cp": "75001", "ville": "Paris", "pays": "france"},
        "sender": {"nom": "Send", "societe": "", "adresse1": "11 rue", "adresse2": "", "cp": "75001", "ville": "Paris", "pays": "france"},
        "mode": "normal",
        "address_source": "terrain",
        "pdf": b"%PDF-1.4\n%mock",
        "context_hash": "ctx",
        "price": {"total_ttc": 2.26},
        "expires_at": now + timedelta(minutes=10),
        "lock_id": "lock_hash",
        "company_key": "org:test",
        "offer": {"phase": "demo", "customer_amount_cents": 0},
    }

    class FakeQuotes:
        async def find_one(self, *_args, **_kwargs):
            return quote_doc

    class FakePostal:
        def __init__(self):
            self.saved = {}

        async def insert_one(self, doc):
            self.saved = doc

        async def update_one(self, _flt, payload):
            self.saved.update(payload.get("$set", {}))

        async def find_one(self, *_args, **_kwargs):
            return dict(self.saved)

    class FakeProspections:
        async def update_one(self, *_args, **_kwargs):
            return None

    fake_postal = FakePostal()
    fake_db = SimpleNamespace(
        radar_postal_quotes=FakeQuotes(),
        radar_postal=fake_postal,
        radar_prospections=FakeProspections(),
    )

    calls = {"send": 0}

    async def fake_get_token(force=False):
        return "tok"

    async def fake_send_letter(*_args, **_kwargs):
        calls["send"] += 1
        return {"envoi_id": "4122404", "price": 2.26}

    monkeypatch.setattr(pd, "db", fake_db)
    monkeypatch.setattr(pd.mf, "get_token", fake_get_token)
    monkeypatch.setattr(pd.mf, "send_letter", fake_send_letter)
    monkeypatch.setattr(pd.postal_offer, "company_key", lambda _user: "org:test")

    async def reserve(*_args, **_kwargs):
        return None

    async def settle(*_args, **_kwargs):
        return None

    monkeypatch.setattr(pd.postal_offer, "reserve", reserve)
    monkeypatch.setattr(pd.postal_offer, "settle", settle)
    user = {"user_id": "u1", "organization_id": "test"}

    result = asyncio.run(pd.deliver(
        user=user,
        user_id="u1",
        token="rop_1",
        quote_id="q_1234567890123456",
        recipient=quote_doc["recipient"],
        mode="normal",
        context_hash="ctx",
    ))

    assert calls["send"] == 1
    assert result["status"] == "submitted"
    assert result["envoi_id"] == "4122404"
