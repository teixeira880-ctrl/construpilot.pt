"""Iter 188 — Growth : correction automatique des erreurs d'audit (autofix)."""
import asyncio
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = (os.environ.get("TEST_ADMIN_EMAIL", "admin@construpilot.fr"), os.environ.get("TEST_ADMIN_PASSWORD", "Construpilot2026!"))
PID = "growth_fr"


def _db():
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient
    load_dotenv("/app/backend/.env")
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def synthetic_issues():
    """Insère dans le dernier audit un canonical_mismatch et une 404 fictifs, nettoyés à la fin."""
    async def setup():
        db = _db()
        audit = await db.growth_audits.find_one({"project_id": PID, "status": "completed"}, {"_id": 0, "audit_id": 1}, sort=[("finished_at", -1)])
        tag = uuid.uuid4().hex[:6]
        broken = f"https://construpilot.fr/estimatio-{tag}"
        canon_url = f"https://construpilot.fr/test-autofix-{tag}"
        issues = [
            {"issue_id": f"iss_t{tag}a", "audit_id": audit["audit_id"], "project_id": PID, "url": canon_url, "kind": "canonical_mismatch", "severity": "moyenne",
             "evidence": "test", "status": "open", "is_fact": True},
            {"issue_id": f"iss_t{tag}b", "audit_id": audit["audit_id"], "project_id": PID, "url": broken, "kind": "http_error", "severity": "haute",
             "evidence": "HTTP 404", "status": "open", "is_fact": True},
            {"issue_id": f"iss_t{tag}c", "audit_id": audit["audit_id"], "project_id": PID, "url": f"https://construpilot.fr/zzz-{tag}-qqq-nothing", "kind": "http_error", "severity": "haute",
             "evidence": "HTTP 404", "status": "open", "is_fact": True},
        ]
        await db.growth_issues.insert_many([dict(i) for i in issues])
        return {"audit_id": audit["audit_id"], "tag": tag, "broken": broken, "canon_url": canon_url, "ids": [i["issue_id"] for i in issues]}

    data = _run(setup())
    yield data

    async def teardown():
        db = _db()
        await db.growth_issues.delete_many({"issue_id": {"$in": data["ids"]}})
        await db.growth_seo_overrides.delete_many({"path": f"/test-autofix-{data['tag']}"})
        await db.growth_redirects.delete_many({"from_path": f"/estimatio-{data['tag']}"})
    _run(teardown())


class TestAutofix:
    def test_status_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/growth/projects/{PID}/autofix")
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d) >= {"enabled", "runs", "last_run", "fixing", "open", "reappeared", "redirects", "running"}
        assert d["enabled"] is True

    def test_run_fixes_canonical_and_redirect_lists_manual(self, admin, synthetic_issues):
        r = admin.post(f"{BASE_URL}/api/growth/projects/{PID}/autofix/run")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "completed"
        tag = synthetic_issues["tag"]
        fixed_urls = {f["url"] for f in d["fixed"]}
        assert synthetic_issues["canon_url"] in fixed_urls
        assert synthetic_issues["broken"] in fixed_urls
        redirect = next(f for f in d["fixed"] if f["url"] == synthetic_issues["broken"])
        assert "→ /estimation" in redirect["how"]
        manual = {m["url"]: m for m in d["manual"]}
        assert any(f"zzz-{tag}" in u for u in manual), "404 sans page proche doit rester manuelle"
        assert all(m["reason"] for m in d["manual"])
        assert not any(m["kind"] in ("canonical_mismatch",) for m in d["manual"])

    def test_issues_marked_fixing_not_fixed(self, admin, synthetic_issues):
        d = admin.get(f"{BASE_URL}/api/growth/projects/{PID}/autofix").json()
        ids = {f["issue_id"] for f in d["fixing"]}
        assert synthetic_issues["ids"][0] in ids and synthetic_issues["ids"][1] in ids
        assert synthetic_issues["ids"][2] not in ids

    def test_public_overrides_and_redirects(self, synthetic_issues):
        ov = requests.get(f"{BASE_URL}/api/growth/seo-overrides", timeout=30).json()["overrides"]
        path = f"/test-autofix-{synthetic_issues['tag']}"
        assert ov[path]["canonical"] == path
        assert ov["/"]["title"]  # surcharge title existante conservée dans le même payload
        rd = requests.get(f"{BASE_URL}/api/growth/redirects", timeout=30).json()["redirects"]
        assert rd[f"/estimatio-{synthetic_issues['tag']}"] == "/estimation"

    def test_toggle_requires_admin_and_persists(self, admin):
        r = admin.put(f"{BASE_URL}/api/growth/projects/{PID}/autofix", json={"enabled": False})
        assert r.status_code == 200 and r.json()["enabled"] is False
        st = admin.get(f"{BASE_URL}/api/growth/projects/{PID}/autopilot").json()["settings"]
        assert st["auto_fix_enabled"] is False and st["seo_override_mode"] == "review"
        r = admin.put(f"{BASE_URL}/api/growth/projects/{PID}/autofix", json={"enabled": True})
        assert r.json()["enabled"] is True
        assert admin.get(f"{BASE_URL}/api/growth/projects/{PID}/autopilot").json()["settings"]["seo_override_mode"] == "auto"

    def test_assistant_grounded_on_autofix(self, admin):
        r = admin.post(f"{BASE_URL}/api/growth/assistant", json={"project_id": PID, "question": "Qu'est-ce qui a été corrigé automatiquement et que reste-t-il à faire ?"}, timeout=180)
        assert r.status_code == 200, r.text
        assert len(r.json()["answer"]) > 50

    def test_unauthenticated_blocked(self):
        assert requests.get(f"{BASE_URL}/api/growth/projects/{PID}/autofix", timeout=30).status_code in (401, 403)
        assert requests.post(f"{BASE_URL}/api/growth/projects/{PID}/autofix/run", timeout=30).status_code in (401, 403)
