"""Radar V2: suggested_message, honeypot, campaigns, open tracking, SITADEL admin."""
import io
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASS = "Pro2026!"
ADMIN_EMAIL = "teixeira8880@gmail.com"
ADMIN_PASS = "CP-D5615C-Prov!"


def _login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


def test_suggested_message_present():
    tok = _login(PRO_EMAIL, PRO_PASS)
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{BASE}/api/radar/opportunities/CP-2026-95119", headers=h, timeout=15)
    assert r.status_code == 200
    o = r.json()
    assert o.get("suggested_message", "").startswith("Bonjour,")


def test_generate_letter_and_campaign_and_open_tracking():
    tok = _login(PRO_EMAIL, PRO_PASS)
    h = {"Authorization": f"Bearer {tok}"}
    # Create campaign
    r = requests.post(f"{BASE}/api/radar/opportunities/CP-2026-95119/prospection",
                      headers=h, json={"message": "TEST_msg V2"}, timeout=30)
    assert r.status_code == 200
    j = r.json()
    token = j["token"]

    # Campaigns list must include it
    r = requests.get(f"{BASE}/api/radar/campaigns", headers=h, timeout=15)
    assert r.status_code == 200
    cj = r.json()
    assert any(c["token"] == token for c in cj["campaigns"])

    # Hit public landing without auth -> increments open_count
    r = requests.get(f"{BASE}/api/radar/public/prospection/{token}", timeout=15)
    assert r.status_code == 200

    # Verify open_count >= 1
    r = requests.get(f"{BASE}/api/radar/campaigns", headers=h, timeout=15)
    row = next((c for c in r.json()["campaigns"] if c["token"] == token), None)
    assert row is not None
    assert row["open_count"] >= 1


def test_honeypot_silently_accepts_no_lead():
    tok = _login(PRO_EMAIL, PRO_PASS)
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{BASE}/api/radar/opportunities/CP-2026-95588/prospection",
                      headers=h, json={}, timeout=30)
    token = r.json()["token"]
    # Bot submits with website filled
    r = requests.post(f"{BASE}/api/radar/public/prospection/{token}/lead",
                      json={"name": "BOT", "email": "TEST_bot_honey@example.com",
                            "website": "http://spam.example"}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("ok") is True
    # No lead should be visible for that email
    r = requests.get(f"{BASE}/api/leads/assigned", headers=h, timeout=15)
    leads = r.json() if isinstance(r.json(), list) else r.json().get("leads", [])
    assert not any(l.get("email") == "test_bot_honey@example.com" for l in leads), \
        "Honeypot leaked a lead"


def test_sitadel_import_count_and_cleanup():
    tok = _login(ADMIN_EMAIL, ADMIN_PASS)
    h = {"Authorization": f"Bearer {tok}"}

    # Baseline: ensure empty (mock)
    r = requests.get(f"{BASE}/api/radar/admin/permits/count", headers=h, timeout=15)
    assert r.status_code == 200, r.text[:200]

    csv_content = (
        "commune;cp;lat;lon;num;type;nature;batiment;surf_created;logements;date_auth;mo\n"
        "TEST_Ville1;95000;49.05;2.10;PC-TEST-001;Permis de construire;neuf;Maison test;120;1;2026-06-01;particulier\n"
        "TEST_Ville2;95000;49.06;2.11;PC-TEST-002;Permis de construire;renovation;Extension test;40;1;2026-06-02;particulier\n"
        "TEST_Ville3;95000;49.07;2.12;PC-TEST-003;Permis de construire;neuf;Immeuble test;800;12;2026-06-03;promoteur\n"
    )
    files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    r = requests.post(f"{BASE}/api/radar/admin/import-sitadel",
                      headers=h, files=files, timeout=60)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["inserted"] >= 1, f"expected inserted>=1, got {j}"

    r = requests.get(f"{BASE}/api/radar/admin/permits/count", headers=h, timeout=15)
    assert r.status_code == 200
    j2 = r.json()
    assert j2["count"] >= 1
    assert j2["using"] == "db.radar_permits"

    # Cleanup: delete all so mock is restored
    r = requests.delete(f"{BASE}/api/radar/admin/permits", headers=h, timeout=15)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = requests.get(f"{BASE}/api/radar/admin/permits/count", headers=h, timeout=15)
    j3 = r.json()
    assert j3["count"] == 0
    assert "mock" in j3["using"]
