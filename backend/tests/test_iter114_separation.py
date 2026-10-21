"""Iter114 — Confirm separation particulier/pro on API + reminders settings."""
import os
import requests

BASE = os.environ.get('REACT_APP_BACKEND_URL', 'https://pilot-build-demo.preview.emergentagent.com').rstrip('/')

def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("token") or j.get("access_token")

def test_particulier_blocked_documents():
    tok = _login("client@construpilot.fr", "Client2026!")
    r = requests.get(f"{BASE}/api/documents", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"

def test_particulier_blocked_clients():
    tok = _login("client@construpilot.fr", "Client2026!")
    r = requests.get(f"{BASE}/api/clients", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    assert r.status_code == 403

def test_particulier_projects_ok():
    tok = _login("client@construpilot.fr", "Client2026!")
    r = requests.get(f"{BASE}/api/projects", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    assert r.status_code == 200

def test_pro_documents_ok():
    tok = _login("pro@construpilot.fr", "Pro2026!")
    r = requests.get(f"{BASE}/api/documents", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    assert r.status_code == 200

def test_pro_reminders_settings_get():
    tok = _login("pro@construpilot.fr", "Pro2026!")
    r = requests.get(f"{BASE}/api/quotes/reminders/settings", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "enabled" in data
    assert "delay_days" in data
    assert "max_reminders" in data

def test_pro_reminders_settings_post_toggle():
    tok = _login("pro@construpilot.fr", "Pro2026!")
    h = {"Authorization": f"Bearer {tok}"}
    # get current
    cur = requests.get(f"{BASE}/api/quotes/reminders/settings", headers=h, timeout=20).json()
    original = cur.get("enabled", True)
    # toggle off
    r = requests.post(f"{BASE}/api/quotes/reminders/settings", headers=h, json={"enabled": False}, timeout=20)
    assert r.status_code == 200, r.text
    # verify persistence
    after = requests.get(f"{BASE}/api/quotes/reminders/settings", headers=h, timeout=20).json()
    assert after["enabled"] is False
    # restore
    requests.post(f"{BASE}/api/quotes/reminders/settings", headers=h, json={"enabled": original}, timeout=20)
