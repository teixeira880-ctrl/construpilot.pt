"""Iteration 181 — BTP Solver + Plans Pro API tests.

- Read-only endpoints exhaustively tested
- ONE solve request (probably 429 since IP quota exhausted)
- ONE plans-pro upload (PNG)
- ONE plans-pro analyze-image (PNG)
Uses HttpOnly session cookies via requests.Session.
"""
import base64
import io
import os
import time

import pytest
import requests
from PIL import Image, ImageDraw

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

PRO = ("pro@construpilot.fr", "Pro2026!")
CLIENT = ("client@construpilot.fr", "Client2026!")

KNOWN_DONE_PROBLEM = "prob_69d962d5f6"
KNOWN_DONE_PLAN = "pplan_0de14e2fddb346"


def _login(email: str, pwd: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    assert s.cookies.get("session_token"), "no session_token cookie set"
    return s


@pytest.fixture(scope="module")
def pro_session():
    return _login(*PRO)


@pytest.fixture(scope="module")
def client_session():
    return _login(*CLIENT)


# ---------- BTP Solver ----------

class TestBtpSolverReadOnly:
    def test_history_pro(self, pro_session):
        r = pro_session.get(f"{API}/btp-solver/history?limit=5", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert len(data["items"]) <= 5
        # Sort desc by generated_at_iso
        isos = [it.get("generated_at_iso") for it in data["items"] if it.get("generated_at_iso")]
        assert isos == sorted(isos, reverse=True)
        for it in data["items"]:
            assert "problem_id" in it
            assert "status" in it
            assert it["status"] in ("running", "done", "error")
            assert "_id" not in it
            assert "user_id" not in it

    def test_detail_known_done(self, pro_session):
        r = pro_session.get(f"{API}/btp-solver/{KNOWN_DONE_PROBLEM}", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "done"
        assert d.get("domain") == "humidite"
        assert d.get("urgency") in {"informative", "planned", "urgent", "immediate"}
        assert len(d.get("causes") or []) >= 2
        sols = d.get("solutions") or []
        assert len(sols) >= 2
        for s in sols:
            for k in ("cost_min_eur", "cost_max_eur", "duration_days_min", "risk", "warranty_years"):
                assert k in s, f"missing {k} in solution {s}"
        charts = d.get("charts") or []
        chart_ids = {c.get("id") for c in charts} if isinstance(charts, list) else set(charts.keys())
        for cid in ("cost_comparison", "duration_comparison", "risk_radar", "causes_confidence"):
            assert cid in chart_ids, f"missing chart {cid}"
        refs = d.get("references") or []
        assert refs, "expected references"
        for ref in refs:
            for k in ("kind", "code", "url"):
                assert k in ref, f"missing {k} in ref"

    def test_detail_cross_user_404(self, client_session):
        r = client_session.get(f"{API}/btp-solver/{KNOWN_DONE_PROBLEM}", timeout=30)
        assert r.status_code == 404, f"expected 404 got {r.status_code}"

    def test_detail_unauth_401(self):
        r = requests.get(f"{API}/btp-solver/{KNOWN_DONE_PROBLEM}", timeout=30)
        assert r.status_code == 401


class TestBtpSolverSolveOnce:
    """Send ONE solve request. Expect 429 (quota exhausted) OR 202."""

    def test_solve_once(self, pro_session):
        body = {
            "description": "Fissure horizontale de 3 mm au 1er étage d'une maison en parpaings de 1985.",
            "region": "Île-de-France",
        }
        r = pro_session.post(f"{API}/btp-solver/solve", json=body, timeout=30)
        assert r.status_code in (202, 429), f"unexpected {r.status_code}: {r.text[:200]}"
        if r.status_code == 429:
            print("solve => 429 (rate limit exhausted, expected)")
            return
        data = r.json()
        assert "problem_id" in data
        assert data.get("status") == "running"
        pid = data["problem_id"]
        # Poll up to 180s
        deadline = time.time() + 180
        final = None
        while time.time() < deadline:
            time.sleep(5)
            g = pro_session.get(f"{API}/btp-solver/{pid}", timeout=30)
            assert g.status_code == 200
            gd = g.json()
            if gd.get("status") in ("done", "error"):
                final = gd
                break
        assert final is not None, "solve did not finish in 180s"
        assert final.get("status") == "done", f"got status={final.get('status')} err={final.get('error')}"


# ---------- Plans Pro ----------

def _png_bytes(w=900, h=600) -> bytes:
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    # outer walls
    d.rectangle([50, 50, w - 50, h - 50], outline="black", width=6)
    # inner walls
    d.line([(w // 2, 50), (w // 2, h - 50)], fill="black", width=4)
    d.line([(50, h // 2), (w - 50, h // 2)], fill="black", width=4)
    # a door (gap + arc)
    d.rectangle([w // 2 - 40, h - 55, w // 2 + 40, h - 45], fill="white", outline="white")
    d.arc([w // 2 - 40, h - 90, w // 2 + 40, h - 10], 0, 90, fill="black", width=2)
    # a window
    d.rectangle([200, 50 - 4, 300, 50 + 4], fill="white", outline="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestPlansProReadOnly:
    def test_history_pro(self, pro_session):
        r = pro_session.get(f"{API}/plans-pro/history?limit=5", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        for it in d["items"]:
            assert "_id" not in it
            assert "user_id" not in it
            assert "job_id" in it

    def test_job_result_known_done(self, pro_session):
        r = pro_session.get(f"{API}/plans-pro/job/{KNOWN_DONE_PLAN}/result", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        vision = d.get("vision") or {}
        assert vision.get("ok") is True
        elems = vision.get("elements") or []
        assert len(elems) > 0
        assert d.get("autodesk") is None

    def test_cross_user_404(self, client_session):
        r = client_session.get(f"{API}/plans-pro/job/{KNOWN_DONE_PLAN}", timeout=30)
        assert r.status_code == 404


class TestPlansProAnalyzeImageOnce:
    def test_invalid_b64(self, pro_session):
        r = pro_session.post(
            f"{API}/plans-pro/analyze-image",
            json={"image_b64": "!!!not-base64!!!", "mime": "image/png"},
            timeout=30,
        )
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"

    def test_analyze_image_once(self, pro_session):
        png = _png_bytes()
        b64 = base64.b64encode(png).decode()
        r = pro_session.post(
            f"{API}/plans-pro/analyze-image",
            json={"image_b64": b64, "mime": "image/png"},
            timeout=90,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        assert d.get("ok") is True
        assert "plan_type" in d
        assert isinstance(d.get("elements"), list)
        providers = d.get("providers_used") or []
        assert 2 <= len(providers) <= 3, f"providers_used={providers}"


class TestPlansProUploadOnce:
    def test_bad_ext(self, pro_session):
        files = {"file": ("plan.txt", b"hello", "text/plain")}
        r = pro_session.post(f"{API}/plans-pro/upload", files=files, timeout=30)
        assert r.status_code == 400

    def test_empty_file(self, pro_session):
        files = {"file": ("plan.png", b"", "image/png")}
        r = pro_session.post(f"{API}/plans-pro/upload", files=files, timeout=30)
        assert r.status_code == 400

    def test_upload_once_and_poll(self, pro_session):
        png = _png_bytes()
        files = {"file": ("floorplan.png", png, "image/png")}
        r = pro_session.post(f"{API}/plans-pro/upload", files=files, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        d = r.json()
        assert d.get("job_id", "").startswith("pplan_")
        assert d.get("status") == "queued"
        assert d.get("needs_autodesk") is False
        job_id = d["job_id"]

        # Before done → 409 on /result
        r_early = pro_session.get(f"{API}/plans-pro/job/{job_id}/result", timeout=30)
        # Accept 409 or 200 if pipeline already very quick
        assert r_early.status_code in (409, 200), r_early.status_code

        deadline = time.time() + 90
        final = None
        while time.time() < deadline:
            time.sleep(3)
            g = pro_session.get(f"{API}/plans-pro/job/{job_id}", timeout=30)
            assert g.status_code == 200
            gd = g.json()
            if gd.get("status") in ("done", "error", "autodesk_error"):
                final = gd
                break
        assert final is not None, "job did not finish in 90s"
        assert final.get("status") == "done", f"status={final.get('status')} err={final.get('error')}"

        rr = pro_session.get(f"{API}/plans-pro/job/{job_id}/result", timeout=30)
        assert rr.status_code == 200
        rd = rr.json()
        vision = rd.get("vision") or {}
        assert vision.get("ok") is True
        assert len(vision.get("elements") or []) > 0
        assert rd.get("autodesk") is None

        # Should appear in history
        h = pro_session.get(f"{API}/plans-pro/history?limit=5", timeout=30)
        assert h.status_code == 200
        ids = [it.get("job_id") for it in h.json().get("items", [])]
        assert job_id in ids

        # Other user must not see it
        cs = _login(*CLIENT)
        r_other = cs.get(f"{API}/plans-pro/job/{job_id}", timeout=30)
        assert r_other.status_code == 404
