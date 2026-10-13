"""LOT 1 « Fiabilité » — iter 185 regression suite.

Coverage:
  * A06 cost coverage (POST/PUT /api/documents + margin gating)
  * A05 fiscal policy (GET /api/documents/fiscal-profile + no silent 10 %)
  * A04 frozen signed/issued documents + auto revision
  * A02 vision_cascade unit (validate_provider_result / merge_observations)
  * A01 plans_pro _finalize unit + /result & /retry HTTP contract

The single « paid » end-to-end PNG upload is behind env var
``RUN_ITER185_PAID_PNG=1`` — it is NOT executed in the default run.
"""
from __future__ import annotations

import os
import sys
import re

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.creds import PRO  # noqa: E402

_frontend_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", ".env")
if "REACT_APP_BACKEND_URL" not in os.environ and os.path.exists(_frontend_env):
    for _ln in open(_frontend_env, encoding="utf-8"):
        if _ln.startswith("REACT_APP_BACKEND_URL="):
            os.environ["REACT_APP_BACKEND_URL"] = _ln.split("=", 1)[1].strip().strip('"')
            break
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pro_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": PRO[0], "password": PRO[1]}, timeout=30)
    assert r.status_code == 200, f"login pro failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def anon_client() -> requests.Session:
    return requests.Session()


# ---------------------------------------------------------------------------
# A05 — fiscal policy
# ---------------------------------------------------------------------------
class TestA05FiscalProfile:
    def test_fiscal_profile_shape(self, pro_client):
        r = pro_client.get(f"{BASE_URL}/api/documents/fiscal-profile", timeout=15)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["country"] == "FR"
        assert p["rates"] == [0, 5.5, 10, 20] or set(p["rates"]) == {0, 5.5, 10, 20}
        assert p["default_rate"] == 20
        assert p["known"] is True
        assert isinstance(p.get("version"), str) and p["version"]

    def test_fiscal_profile_requires_auth(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/documents/fiscal-profile", timeout=15)
        assert r.status_code == 401

    def test_line_without_vat_rate_no_silent_fallback(self, pro_client):
        # Line WITHOUT vat_rate → stored as None, ttc == ht, vat_unset_lines == 1
        payload = {
            "doc_type": "quote",
            "title": "TEST_iter185 vat unset",
            "lines": [{"designation": "SansTVA", "qty": 1, "unit_price_ht": 100}],
        }
        r = pro_client.post(f"{BASE_URL}/api/documents", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        doc = r.json()
        line = doc["lines"][0]
        assert line.get("vat_rate") is None, f"expected None, got {line.get('vat_rate')}"
        t = doc["totals"]
        assert t["vat_unset_lines"] == 1
        assert t["ht"] == 100.0
        assert t["ttc"] == t["ht"], f"ttc must equal ht when vat unset (no silent 10%), got {t}"
        # cleanup
        pro_client.delete(f"{BASE_URL}/api/documents/{doc['doc_id']}", timeout=15)


# ---------------------------------------------------------------------------
# A06 — cost coverage
# ---------------------------------------------------------------------------
class TestA06CostCoverage:
    def test_partial_coverage_then_confirm_zero(self, pro_client):
        payload = {
            "doc_type": "quote",
            "title": "TEST_iter185 A06",
            "lines": [
                {"designation": "A", "qty": 1, "unit_price_ht": 100, "cost_price_ht": 40, "vat_rate": 20},
                {"designation": "B", "qty": 1, "unit_price_ht": 100, "cost_price_ht": 0, "vat_rate": 20},
            ],
        }
        r = pro_client.post(f"{BASE_URL}/api/documents", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        doc = r.json()
        t = doc["totals"]
        # Partial coverage: margin_ht None until all costs known
        assert t["margin_ht"] is None
        assert t["margin_pct"] is None
        cov = t["cost_coverage"]
        assert cov["known_lines"] == 1
        assert cov["total_lines"] == 2
        assert cov["complete"] is False
        assert cov["missing_lines"] == 1
        assert cov["covered_ht"] == 100
        assert t["partial_margin_ht"] == 60
        assert t["cost_ht"] == 40
        assert t["ht"] == 200 and t["tva"] == 40 and t["ttc"] == 240

        # PUT with line B cost_confirmed_zero: True → complete coverage
        put_payload = {
            "doc_type": "quote",
            "title": doc["title"],
            "lines": [
                {"designation": "A", "qty": 1, "unit_price_ht": 100, "cost_price_ht": 40, "vat_rate": 20},
                {"designation": "B", "qty": 1, "unit_price_ht": 100, "cost_price_ht": 0,
                 "cost_confirmed_zero": True, "vat_rate": 20},
            ],
        }
        r2 = pro_client.put(f"{BASE_URL}/api/documents/{doc['doc_id']}", json=put_payload, timeout=20)
        assert r2.status_code == 200, r2.text
        t2 = r2.json()["totals"]
        assert t2["margin_ht"] == 160
        assert t2["margin_pct"] == 80.0
        assert t2["cost_coverage"]["complete"] is True
        assert t2["ht"] == 200 and t2["tva"] == 40 and t2["ttc"] == 240

        # cleanup
        pro_client.delete(f"{BASE_URL}/api/documents/{doc['doc_id']}", timeout=15)


# ---------------------------------------------------------------------------
# A04 — frozen signed docs + auto revision
# ---------------------------------------------------------------------------
def _make_draft_quote(client: requests.Session, title: str) -> dict:
    r = client.post(f"{BASE_URL}/api/documents", json={
        "doc_type": "quote",
        "title": title,
        "lines": [
            {"designation": "L1", "qty": 1, "unit_price_ht": 100, "cost_price_ht": 40, "vat_rate": 20},
            {"designation": "L2", "qty": 2, "unit_price_ht": 50, "cost_price_ht": 20, "vat_rate": 20},
        ],
    }, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


class TestA04FrozenQuote:
    def test_sign_quote_freezes_and_edit_creates_revision(self, pro_client):
        q = _make_draft_quote(pro_client, "TEST_iter185 A04 signed")
        doc_id = q["doc_id"]

        # PATCH → signed
        r = pro_client.patch(f"{BASE_URL}/api/documents/{doc_id}/status",
                             json={"status": "signed"}, timeout=20)
        assert r.status_code == 200, r.text
        signed = r.json()
        assert signed["status"] == "signed"
        assert signed["signed"] is True
        fhash = signed.get("frozen_hash")
        assert isinstance(fhash, str) and re.fullmatch(r"[0-9a-f]{64}", fhash)
        assert signed.get("frozen_at")
        assert isinstance(signed.get("frozen_pdf_b64"), str) and len(signed["frozen_pdf_b64"]) > 100
        assert len(signed["frozen_snapshot"]["lines"]) == 2

        # PUT with changed price → revision
        put_body = {
            "doc_type": "quote",
            "title": signed["title"],
            "lines": [
                {"designation": "L1", "qty": 1, "unit_price_ht": 150, "cost_price_ht": 40, "vat_rate": 20},
                {"designation": "L2", "qty": 2, "unit_price_ht": 50, "cost_price_ht": 20, "vat_rate": 20},
            ],
        }
        r2 = pro_client.put(f"{BASE_URL}/api/documents/{doc_id}", json=put_body, timeout=20)
        assert r2.status_code == 200, r2.text
        rev = r2.json()
        assert rev.get("revision_created") is True
        assert rev["doc_id"] != doc_id
        assert rev["status"] == "draft"
        assert rev["signed"] is False
        assert rev["revision"] == 2
        assert rev["revision_of"] == doc_id

        # Original untouched
        r3 = pro_client.get(f"{BASE_URL}/api/documents/{doc_id}", timeout=15)
        assert r3.status_code == 200
        orig = r3.json()
        assert orig["status"] == "signed"
        assert orig["lines"][0]["unit_price_ht"] == 100
        assert orig.get("superseded_by") == rev["doc_id"]

        # PUT signed with identical content but status draft → 409
        identical_body = {
            "doc_type": "quote",
            "title": orig["title"],
            "status": "draft",
            "lines": [
                {"designation": ln["designation"], "qty": ln["qty"], "unit_price_ht": ln["unit_price_ht"],
                 "cost_price_ht": ln.get("cost_price_ht"), "vat_rate": ln.get("vat_rate")}
                for ln in orig["lines"]
            ],
            "notes": orig.get("notes", ""),
            "payment_terms": orig.get("payment_terms", ""),
            "deposit_pct": orig.get("deposit_pct", 0),
        }
        r4 = pro_client.put(f"{BASE_URL}/api/documents/{doc_id}", json=identical_body, timeout=20)
        assert r4.status_code == 409, f"expected 409, got {r4.status_code} {r4.text[:200]}"

        # PATCH signed → draft blocked
        r5 = pro_client.patch(f"{BASE_URL}/api/documents/{doc_id}/status",
                              json={"status": "draft"}, timeout=15)
        assert r5.status_code == 409

        # PATCH signed → sent blocked
        r6 = pro_client.patch(f"{BASE_URL}/api/documents/{doc_id}/status",
                              json={"status": "sent"}, timeout=15)
        assert r6.status_code == 409

    def test_quote_transitions_draft_sent_and_paid_blocked(self, pro_client):
        q = _make_draft_quote(pro_client, "TEST_iter185 A04 transitions")
        doc_id = q["doc_id"]
        r = pro_client.patch(f"{BASE_URL}/api/documents/{doc_id}/status",
                             json={"status": "sent"}, timeout=15)
        assert r.status_code == 200
        r = pro_client.patch(f"{BASE_URL}/api/documents/{doc_id}/status",
                             json={"status": "draft"}, timeout=15)
        assert r.status_code == 200
        r = pro_client.patch(f"{BASE_URL}/api/documents/{doc_id}/status",
                             json={"status": "paid"}, timeout=15)
        assert r.status_code == 409  # paid not allowed for quote
        pro_client.delete(f"{BASE_URL}/api/documents/{doc_id}", timeout=15)

    def test_invoice_from_quote_frozen_avoir_message(self, pro_client):
        # signed quote required to build invoice
        q = _make_draft_quote(pro_client, "TEST_iter185 A04 invoice")
        doc_id = q["doc_id"]
        r = pro_client.patch(f"{BASE_URL}/api/documents/{doc_id}/status",
                             json={"status": "signed"}, timeout=20)
        assert r.status_code == 200
        r2 = pro_client.post(f"{BASE_URL}/api/documents/{doc_id}/to-invoice",
                             json={"mode": "total", "pct": 100}, timeout=20)
        assert r2.status_code == 200, r2.text
        inv = r2.json()
        inv_id = inv["doc_id"]
        # Invoice created with status sent → non-draft → frozen. Editing must be blocked.
        put_changed = {
            "doc_type": "invoice",
            "title": inv["title"],
            "lines": [{**dict(ln), "unit_price_ht": (ln.get("unit_price_ht") or 0) + 10}
                      for ln in inv["lines"]],
        }
        r3 = pro_client.put(f"{BASE_URL}/api/documents/{inv_id}", json=put_changed, timeout=20)
        assert r3.status_code == 409
        body = r3.text.lower()
        assert "avoir" in body, f"expected 'avoir' in error, got {r3.text[:300]}"

        # sent → paid allowed
        r4 = pro_client.patch(f"{BASE_URL}/api/documents/{inv_id}/status",
                              json={"status": "paid"}, timeout=15)
        assert r4.status_code == 200
        # paid → draft blocked
        r5 = pro_client.patch(f"{BASE_URL}/api/documents/{inv_id}/status",
                              json={"status": "draft"}, timeout=15)
        assert r5.status_code == 409


# ---------------------------------------------------------------------------
# A02 — vision_cascade unit
# ---------------------------------------------------------------------------
class TestA02VisionCascadeUnit:
    def test_validate_and_merge(self):
        from plans_pro.vision_cascade import validate_provider_result, merge_observations
        a = validate_provider_result(
            {"plan_type": "niveau", "elements": [
                {"kind": "portes", "count": 2, "confidence": 0.95},
                {"kind": "murs", "count": 8, "confidence": 0.8},
            ]}, "claude")
        b = validate_provider_result(
            {"plan_type": "niveau", "elements": [
                {"kind": "door", "count": 10, "confidence": 0.95},
                {"kind": "murs", "count": 8, "confidence": 0.7},
                {"kind": "wc", "count": "x"},
            ]}, "gpt-5.5")
        assert a is not None and b is not None
        # 'wc' count invalid → warning + entry ignored
        assert any("wc" in w.lower() for w in b["warnings"]), b["warnings"]

        els, nr = merge_observations([a, b])
        assert nr is True
        by_kind = {e["kind"]: e for e in els}
        assert "portes" in by_kind and "murs" in by_kind
        p = by_kind["portes"]
        assert p["count"] is None
        assert p["count_range"] == [2, 10]
        assert p["disagreement"] is True
        assert p["needs_review"] is True
        assert p["contributions"] == 2
        assert len(p["observations"]) == 2
        for obs in p["observations"]:
            assert "provider" in obs and "count" in obs
        m = by_kind["murs"]
        assert m["count"] == 8
        assert m["agreed"] is True

    def test_validate_edge_cases(self):
        from plans_pro.vision_cascade import validate_provider_result
        assert validate_provider_result(None, "x") is None
        assert validate_provider_result({"elements": []}, "x") is None


# ---------------------------------------------------------------------------
# A01 — plans_pro unit + HTTP
# ---------------------------------------------------------------------------
class TestA01Finalize:
    def test_finalize_matrix(self):
        from plans_pro.routes import _finalize
        s, _ = _finalize(needs_autodesk=True, autodesk_ok=False, vision=None)
        assert s == "failed"
        s, _ = _finalize(needs_autodesk=False, autodesk_ok=False, vision={"status": "failed"})
        assert s == "failed"
        s, _ = _finalize(needs_autodesk=True, autodesk_ok=True, vision={"status": "failed"})
        assert s == "partial"
        s, _ = _finalize(needs_autodesk=False, autodesk_ok=False, vision={"status": "needs_review"})
        assert s == "needs_review"
        s, _ = _finalize(needs_autodesk=False, autodesk_ok=False, vision={"status": "ok"})
        assert s == "done"


class TestA01PlansProHTTP:
    def test_result_legacy_job(self, pro_client):
        r = pro_client.get(f"{BASE_URL}/api/plans-pro/job/pplan_0de14e2fddb346/result", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("status", "checks", "help", "can_retry"):
            assert k in body, f"missing {k}"
        assert isinstance(body["checks"], list)
        assert isinstance(body["can_retry"], bool)

    def test_result_dwg_legacy_job(self, pro_client):
        r = pro_client.get(f"{BASE_URL}/api/plans-pro/job/pplan_4e216317b5b949/result", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "status" in body and "checks" in body and "help" in body and "can_retry" in body

    def test_retry_source_not_stored(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/plans-pro/job/pplan_0de14e2fddb346/retry", timeout=20)
        assert r.status_code == 409
        assert "importez" in r.text.lower()

    def test_retry_unknown(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/plans-pro/job/unknown_iter185/retry", timeout=20)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# A01/A02 end-to-end paid PNG — gated
# ---------------------------------------------------------------------------
@pytest.mark.skipif(os.environ.get("RUN_ITER185_PAID_PNG") != "1",
                    reason="Paid vision run — set RUN_ITER185_PAID_PNG=1 to enable")
class TestA01PaidPngOnce:
    def test_png_upload_and_poll(self, pro_client):
        import io
        import time

        from PIL import Image, ImageDraw

        img = Image.new("RGB", (900, 600), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([50, 50, 850, 550], outline="black", width=4)
        d.line([300, 50, 300, 550], fill="black", width=3)
        d.line([50, 320, 850, 320], fill="black", width=3)
        d.arc([120, 250, 180, 320], 0, 90, fill="black", width=2)
        d.arc([400, 250, 460, 320], 0, 90, fill="black", width=2)
        d.rectangle([600, 46, 720, 54], fill="white", outline="black")
        d.text((150, 150), "Chambre", fill="black")
        d.text((500, 150), "Salon", fill="black")
        d.text((150, 400), "Cuisine", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        files = {"file": ("plan.png", buf.getvalue(), "image/png")}
        headers = {k: v for k, v in pro_client.headers.items() if k != "Content-Type"}
        r = requests.post(f"{BASE_URL}/api/plans-pro/upload", files=files, headers=headers,
                          cookies=pro_client.cookies, timeout=60)
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        deadline = time.time() + 90
        final = None
        while time.time() < deadline:
            j = pro_client.get(f"{BASE_URL}/api/plans-pro/job/{job_id}", timeout=20).json()
            if j.get("status") in {"done", "needs_review", "partial", "failed"}:
                final = j
                break
            time.sleep(4)
        assert final is not None, "job did not reach final status in 90 s"
        assert final["status"] in {"done", "needs_review"}, final
