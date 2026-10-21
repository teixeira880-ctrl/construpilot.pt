"""Radar Chantiers + Prospection end-to-end tests."""
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASS = "Pro2026!"


def _login():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": PRO_EMAIL, "password": PRO_PASS}, timeout=15)
    assert r.status_code == 200, f"login {r.status_code}: {r.text[:200]}"
    return r.json()["token"]


def test_login_pro():
    token = _login()
    assert isinstance(token, str) and len(token) > 10


def test_radar_profile_get_put_persist():
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/api/radar/profile", headers=h, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert "metier_options" in j and "metiers" in j
    new_metiers = ["gros_oeuvre", "maconnerie", "couverture"]
    r = requests.put(f"{BASE}/api/radar/profile", headers=h, json={"metiers": new_metiers, "km": 30}, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert set(j["metiers"]) == set(new_metiers)
    assert j["km"] == 30
    # persistence
    r = requests.get(f"{BASE}/api/radar/profile", headers=h, timeout=15)
    assert set(r.json()["metiers"]) == set(new_metiers)


def test_radar_opportunities_and_kpis():
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    for km in [10, 30, 100]:
        r = requests.get(f"{BASE}/api/radar/opportunities?km={km}", headers=h, timeout=15)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j["radius_km"] == km
        assert "opportunities" in j
    r = requests.get(f"{BASE}/api/radar/stats", headers=h, timeout=15)
    assert r.status_code == 200
    assert "detected" in r.json()


def test_favorite_toggle():
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    opp_id = "CP-2026-95731"
    r = requests.post(f"{BASE}/api/radar/opportunities/{opp_id}/favorite", headers=h, timeout=15)
    assert r.status_code == 200
    s1 = r.json()["is_favorite"]
    r = requests.post(f"{BASE}/api/radar/opportunities/{opp_id}/favorite", headers=h, timeout=15)
    assert r.json()["is_favorite"] != s1


def test_prospection_letter_and_landing_and_lead():
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    opp_id = "CP-2026-95731"
    r = requests.post(f"{BASE}/api/radar/opportunities/{opp_id}/prospection",
                      headers=h, json={"message": "Test T1 automation"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["token"].startswith("rop_")
    assert j["qr_b64"].startswith("data:image/png;base64,")
    assert j["letter_b64"].startswith("data:application/pdf;base64,")
    tok = j["token"]
    public_url = j["public_url"]
    assert f"/prospection/{tok}" in public_url

    # Public landing (no auth)
    r = requests.get(f"{BASE}/api/radar/public/prospection/{tok}", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "company" in data and "opportunity" in data
    assert data["company"]["name"]

    # Submit lead (no auth)
    r = requests.post(f"{BASE}/api/radar/public/prospection/{tok}/lead",
                      json={"name": "TEST_Prospect", "email": "TEST_prospect_radar@example.com",
                            "phone": "0102030405", "message": "Intéressé par votre proposition"}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    assert r.json().get("ok") is True

    # Verify lead is visible to pro via /leads/assigned
    r = requests.get(f"{BASE}/api/leads/assigned", headers=h, timeout=15)
    assert r.status_code == 200
    leads = r.json()
    if isinstance(leads, dict):
        leads = leads.get("leads") or leads.get("items") or []
    matches = [l for l in leads if l.get("radar_token") == tok and l.get("source") == "radar_prospection"]
    assert matches, f"No radar_prospection lead found for token {tok}"
    assert matches[0]["email"] == "TEST_prospect_radar@example.com"


def test_prospection_letter_pdf_download():
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    opp_id = "CP-2026-95402"
    r = requests.post(f"{BASE}/api/radar/opportunities/{opp_id}/prospection",
                      headers=h, json={}, timeout=30)
    tok = r.json()["token"]
    r = requests.get(f"{BASE}/api/radar/prospection/{tok}/letter.pdf", headers=h, timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
