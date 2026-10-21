"""Iteration 160: production-safe postal regression checks (read-only + non-billable quote status)."""

from __future__ import annotations

import os
import re

import pytest
import requests


def _origin() -> str:
    origin = (os.environ.get("POSTAL_DIAGNOSTIC_ORIGIN") or os.environ.get("TEST_TARGET_URL") or "").strip()
    if not origin:
        raise RuntimeError("Set POSTAL_DIAGNOSTIC_ORIGIN or TEST_TARGET_URL explicitly.")
    return origin.rstrip("/")


def _api(path: str) -> str:
    return f"{_origin()}/api{path}"


def _cred_from_env_or_doc() -> tuple[str, str]:
    email = (os.environ.get("TEST_ADMIN_EMAIL") or "").strip()
    password = (os.environ.get("TEST_ADMIN_PASSWORD") or "").strip()
    if email and password:
        return email, password

    content = open("/app/memory/test_credentials.md", "r", encoding="utf-8").read()
    m = re.search(
        r"##\s*Administrateur \(back-office `/admin`\).*?Email\*\*\s*:\s*`([^`]+)`.*?Password\*\*\s*:\s*`([^`]+)`",
        content,
        flags=re.S,
    )
    if not m:
        raise RuntimeError("Admin test credentials missing in env and /app/memory/test_credentials.md")
    return m.group(1).strip(), m.group(2).strip()


@pytest.fixture(scope="session")
def admin_session() -> requests.Session:
    email, password = _cred_from_env_or_doc()
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    login = s.post(_api("/auth/login"), json={"email": email, "password": password}, timeout=30)
    assert login.status_code == 200, f"Login failed: {login.status_code} {login.text[:300]}"
    body = login.json()
    token = body.get("token")
    assert isinstance(token, str) and token, f"Missing token in login response: {body}"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# Admin diagnostics should deny public/noauth and succeed for authenticated admin.
def test_admin_postal_diagnostics_auth_matrix(admin_session: requests.Session):
    unauth = requests.get(_api("/admin/postal/diagnostics"), timeout=20)
    assert unauth.status_code in (401, 403), unauth.text[:300]

    auth = admin_session.get(_api("/admin/postal/diagnostics"), timeout=30)
    assert auth.status_code == 200, auth.text[:400]
    data = auth.json()
    assert data.get("configured") is True
    assert isinstance(data.get("configured_ips"), list)
    assert len(data.get("configured_ips")) >= 10
    assert data.get("provider_ok") is True
    assert isinstance(data.get("observed_ip"), str) and data["observed_ip"]
    assert data["observed_ip"] in data["configured_ips"]


# Postal quote tariffs must be reachable in production for all user-facing modes.
@pytest.mark.parametrize("mode", ["normal", "suivi", "lrar"])
def test_postal_prices_all_modes_200_with_real_values(admin_session: requests.Session, mode: str):
    response = admin_session.get(_api(f"/radar/postal/price?mode={mode}"), timeout=35)
    assert response.status_code == 200, f"mode={mode} -> {response.status_code} {response.text[:300]}"
    payload = response.json()
    assert payload["mode"] == mode
    assert payload["pages"] == 1
    assert payload["currency"] == "EUR"
    assert isinstance(payload.get("total_ttc"), (int, float)) and payload["total_ttc"] > 0
    assert isinstance(payload.get("postage"), (int, float)) and payload["postage"] > 0


# Offer contract for demo phase must stay zero-charge customer-side.
def test_postal_status_contract_remains_demo_zero_charge(admin_session: requests.Session):
    response = admin_session.get(_api("/radar/postal/status"), timeout=20)
    assert response.status_code == 200, response.text[:300]
    payload = response.json()
    assert payload.get("configured") is True
    assert set(payload.get("modes", [])) == {"normal", "suivi", "lrar"}

    offer = payload.get("offer") or {}
    assert offer.get("phase") == "demo"
    assert offer.get("customer_amount_cents") == 0
    assert offer.get("operator_pays_postage") is True
    assert offer.get("paid_enabled") is False
    assert offer.get("demo_limit") == 1


# Repeat diagnostics once later in run; no send path involved, only read checks.
def test_repeat_diagnostics_stays_healthy(admin_session: requests.Session):
    response = admin_session.get(_api("/admin/postal/diagnostics"), timeout=30)
    assert response.status_code == 200, response.text[:300]
    payload = response.json()
    assert payload.get("provider_ok") is True
    assert isinstance(payload.get("configured_ips"), list) and len(payload["configured_ips"]) >= 10


# Radar quote endpoint should return a real quote (non-billable) for a valid admin campaign.
def test_postal_quote_returns_200_for_generated_campaign(admin_session: requests.Session):
    opportunities = admin_session.get(_api("/radar/opportunities?page=1&page_size=1"), timeout=40)
    assert opportunities.status_code == 200, opportunities.text[:300]
    rows = opportunities.json().get("opportunities") or []
    assert rows, "No opportunities available"
    opp_id = rows[0]["id"]

    detail_resp = admin_session.get(_api(f"/radar/opportunities/{opp_id}"), timeout=35)
    assert detail_resp.status_code == 200, detail_resp.text[:300]
    detail = detail_resp.json()

    campaign_resp = admin_session.post(_api(f"/radar/opportunities/{opp_id}/prospection"), json={"message": ""}, timeout=45)
    assert campaign_resp.status_code == 200, campaign_resp.text[:500]
    campaign = campaign_resp.json()
    token = campaign.get("token")
    assert isinstance(token, str) and token

    promoteur = detail.get("promoteur") or {}
    has_contact = all(str(promoteur.get(k) or "").strip() for k in ("nom", "adresse1", "cp", "ville"))
    recipient = {
        "nom": str(promoteur.get("nom") or "À l'attention du maître d'ouvrage").strip()[:160],
        "societe": str(promoteur.get("societe") or "").strip()[:160],
        "adresse1": (str(promoteur.get("adresse1") or "").strip() if has_contact else str(detail.get("adresse") or "").strip())[:200],
        "adresse2": "",
        "cp": (str(promoteur.get("cp") or "").strip() if has_contact else str(detail.get("cp") or "").strip())[:12],
        "ville": (str(promoteur.get("ville") or "").strip() if has_contact else str(detail.get("commune") or "").strip())[:100],
        "pays": "france",
    }
    assert all(recipient[k] for k in ("nom", "adresse1", "cp", "ville")), f"Recipient incomplete: {recipient}"

    branding_resp = admin_session.get(_api("/users/me/branding"), timeout=30)
    assert branding_resp.status_code == 200
    branding = branding_resp.json()
    sender_ready = all(str(branding.get(field) or "").strip() for field in ("address", "postal_code", "city"))

    quote_resp = admin_session.post(
        _api(f"/radar/prospection/{token}/postal/quote"),
        json={
            "recipient": recipient,
            "mode": "normal",
            "address_source": "contact" if has_contact else "terrain",
        },
        timeout=60,
    )
    if not sender_ready:
        assert quote_resp.status_code == 400, f"Missing sender must return actionable 400, got {quote_resp.status_code}"
        detail = quote_resp.json()["detail"]
        assert detail["code"] == "sender_address_required"
        assert detail["fields"]
        assert detail["action_url"] == "/entreprise"
        return

    retry_debug = ""
    if quote_resp.status_code != 200:
        recipient_retry = {
            **recipient,
            "adresse1": " ".join(str(recipient["adresse1"]).replace("/", " ").split()),
            "ville": " ".join(str(recipient["ville"]).split()),
        }
        quote_retry = admin_session.post(
            _api(f"/radar/prospection/{token}/postal/quote"),
            json={
                "recipient": recipient_retry,
                "mode": "normal",
                "address_source": "manual",
            },
            timeout=60,
        )
        retry_debug = (
            f" retry_status={quote_retry.status_code} retry_body={quote_retry.text[:300]} "
            f"retry_recipient={recipient_retry}"
        )
    assert quote_resp.status_code == 200, (
        "quote failed: "
        f"status={quote_resp.status_code} body={quote_resp.text[:500]} "
        f"opp_id={opp_id} token={token} recipient={recipient} has_contact={has_contact}{retry_debug}"
    )
    quote = quote_resp.json()
    assert quote.get("currency") == "EUR"
    assert isinstance(quote.get("total_ttc"), (int, float)) and quote["total_ttc"] > 0
    assert isinstance(quote.get("quote_id"), str) and quote["quote_id"]
