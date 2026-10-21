"""Lot 0 regression: /api/offer, /api/plans coherence, public routes, register+delete flow."""
import os
import re
import time
import random
import string
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pilot-build-demo.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


def test_offer_endpoint(s):
    r = s.get(f"{API}/offer", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("free_promo") is True
    assert d.get("trial_days") == 7
    assert "entry_price_eur" in d
    print("OFFER:", d)


def test_plans_endpoint_coherence(s):
    r = s.get(f"{API}/plans", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # plans is dict or list; find prices
    txt = str(data)
    # premium 19, pro 149, pro_business 249
    assert "19" in txt
    assert "149" in txt
    assert "249" in txt
    # offer field embedded
    assert "offer" in data if isinstance(data, dict) else True


PUBLIC_ROUTES = [
    "/", "/particuliers", "/metre", "/fonctionnalites", "/tarifs", "/estimation",
    "/calculateurs", "/prix", "/diy", "/coach", "/photo", "/aide", "/comparatif",
    "/blog", "/docs", "/marketplace", "/enterprise", "/mentions-legales",
    "/confidentialite", "/cgv", "/privacy", "/smart-project", "/radar", "/investisseurs",
]


@pytest.mark.parametrize("path", PUBLIC_ROUTES)
def test_public_route_200(s, path):
    r = s.get(f"{BASE_URL}{path}", timeout=30, allow_redirects=True)
    assert r.status_code == 200, f"{path} -> {r.status_code}"


def test_index_html_has_static_title_no_aggregate_rating(s):
    r = s.get(f"{BASE_URL}/", timeout=30)
    assert r.status_code == 200
    html = r.text
    assert re.search(r"<title>", html, re.IGNORECASE), "no <title>"
    assert "aggregateRating" not in html, "aggregateRating leak in index.html"


def test_register_and_delete_account(s):
    rnd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"lot0.qa.{rnd}@example.com"
    password = "Test12345!"
    # Register
    r = s.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "QA Lot0"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    # me
    r = s.get(f"{API}/auth/me", timeout=30)
    assert r.status_code == 200, r.text
    # login (fresh cookie)
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    # Delete
    r = s.delete(f"{API}/auth/account", json={"password": password, "confirm": "SUPPRIMER"}, timeout=30)
    assert r.status_code in (200, 204), r.text
    # verify gone
    r2 = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r2.status_code in (400, 401, 403, 404), f"account still exists: {r2.status_code}"
