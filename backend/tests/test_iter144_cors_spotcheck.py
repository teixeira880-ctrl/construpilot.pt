"""Iteration 144: focused CORS + auth smoke checks for public frontend origin."""
import os

import pytest
import requests
from dotenv import load_dotenv


load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


@pytest.fixture(scope="session")
def base_url() -> str:
    """API base URL from environment only (no hardcoded fallback)."""
    if not BASE_URL:
        pytest.fail("Missing REACT_APP_BACKEND_URL in environment")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def api_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# Module: auth login and CORS preflight checks
def test_login_existing_pro_account_success(api_session: requests.Session, base_url: str):
    response = api_session.post(
        f"{base_url}/api/auth/login",
        json={"email": "pro@construpilot.fr", "password": "Pro2026!"},
        timeout=30,
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("token") and isinstance(data.get("token"), str)
    assert data.get("user", {}).get("email") == "pro@construpilot.fr"


def test_cors_preflight_public_origin_allowed(base_url: str):
    origin = base_url
    response = requests.options(
        f"{base_url}/api/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
        timeout=20,
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_evil_origin_rejected(base_url: str):
    evil = "https://evil.example"
    response = requests.options(
        f"{base_url}/api/auth/login",
        headers={
            "Origin": evil,
            "Access-Control-Request-Method": "POST",
        },
        timeout=20,
    )
    assert response.status_code in (400, 403)
    assert response.headers.get("access-control-allow-origin") != evil


@pytest.mark.parametrize("origin", ["https://www.construpilot.fr", "https://construpilot.fr"])
def test_cors_preflight_prod_www_and_bare_allowed(base_url: str, origin: str):
    response = requests.options(
        f"{base_url}/api/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
        timeout=20,
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"
