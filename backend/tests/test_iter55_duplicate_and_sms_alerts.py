"""Iter 55 — Plan Duplication + Price Alerts SMS regression tests."""
import pytest
from fastapi.testclient import TestClient

from server import app
from routes.plans_crud import _duplicate_filename


client = TestClient(app)


# ============ UNIT — filename helper ============

def test_duplicate_filename_basic_extension():
    assert _duplicate_filename("plan.pdf") == "plan (copie).pdf"


def test_duplicate_filename_no_extension():
    assert _duplicate_filename("plan") == "plan (copie)"


def test_duplicate_filename_already_a_copy():
    assert _duplicate_filename("plan (copie).pdf") == "plan (copie 2).pdf"


def test_duplicate_filename_empty_fallback():
    assert _duplicate_filename("") == "plan (copie)"


# ============ Endpoint registration ============

def test_duplicate_route_registered():
    routes = {r.path for r in app.routes}
    assert "/api/takeoffs/{plan_id}/duplicate" in routes


def test_alerts_route_registered():
    routes = {r.path for r in app.routes}
    assert "/api/prices/alerts" in routes


# ============ AlertIn schema — SMS validation ============

def test_alert_in_defaults_to_email_only():
    """AlertIn defaults to email-only when channels is not provided."""
    from routes.prices import AlertIn
    a = AlertIn(query="ba13", target_price=5.0)
    assert a.channels == ["email"]
    assert a.phone is None


def test_alert_in_accepts_sms_channel_with_phone():
    from routes.prices import AlertIn
    a = AlertIn(query="ba13", target_price=5.0, channels=["email", "sms"], phone="+33612345678")
    assert "sms" in a.channels
    assert a.phone == "+33612345678"


# ============ Alerting SMS helper ============

def test_send_sms_returns_false_without_twilio_env(monkeypatch):
    """Ensure the SMS helper degrades gracefully when Twilio env vars are missing."""
    from engines import alerting
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "")
    assert alerting._send_sms("+33612345678", "hello") is False


def test_send_sms_returns_false_when_to_missing():
    from engines import alerting
    assert alerting._send_sms("", "hello") is False


# ============ Alerting notify_channels dispatch ============

def test_notify_channels_email_only(monkeypatch):
    """When channels=[email], only _notify_user is called."""
    import asyncio
    from engines import alerting
    calls = {"email": 0, "sms": 0}

    async def fake_notify_user(user, alert, best):
        calls["email"] += 1
        return True

    def fake_send_sms(to, body):
        calls["sms"] += 1
        return True

    monkeypatch.setattr(alerting, "_notify_user", fake_notify_user)
    monkeypatch.setattr(alerting, "_send_sms", fake_send_sms)

    ok = asyncio.run(alerting._notify_channels(
        {"user_id": "u1", "email": "x@y.z"},
        {"alert_id": "a1", "channels": ["email"], "target_price": 5.0,
         "product": "BA13", "query": "ba13"},
        {"price": 4.0, "supplier": "Castorama", "url": "https://x"}
    ))
    assert ok is True
    assert calls == {"email": 1, "sms": 0}


def test_notify_channels_sms_and_email(monkeypatch):
    import asyncio
    from engines import alerting
    calls = {"email": 0, "sms": 0}

    async def fake_notify_user(user, alert, best):
        calls["email"] += 1
        return True

    def fake_send_sms(to, body):
        calls["sms"] += 1
        assert to == "+33612345678"
        assert "BA13" in body
        assert "Castorama" in body
        return True

    monkeypatch.setattr(alerting, "_notify_user", fake_notify_user)
    monkeypatch.setattr(alerting, "_send_sms", fake_send_sms)

    # Mock the db update so we don't hit real Mongo
    async def fake_update_one(*args, **kwargs):
        return None
    monkeypatch.setattr(alerting.db.price_alerts, "update_one", fake_update_one)

    ok = asyncio.run(alerting._notify_channels(
        {"user_id": "u1", "email": "x@y.z"},
        {"alert_id": "a1", "channels": ["email", "sms"], "phone": "+33612345678",
         "target_price": 5.0, "product": "BA13", "query": "ba13"},
        {"price": 4.0, "supplier": "Castorama", "url": "https://x"}
    ))
    assert ok is True
    assert calls == {"email": 1, "sms": 1}
