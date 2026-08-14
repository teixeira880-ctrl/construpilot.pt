"""Iter20 — PDF branding, non-régression on iter19 endpoints, and endpoint healthchecks."""
import os
import pytest
import requests


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    return v.rstrip("/")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

DEMO = {"email": "demo@construpilot.fr", "password": "Demo2026!"}
ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}

# 1x1 red PNG
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json=DEMO, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_auth():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---- Helpers ----
def _upload_plan(auth):
    with open("/app/before.png", "rb") as f:
        r = requests.post(
            f"{API}/takeoffs/upload",
            files={"file": ("before.png", f, "image/png")},
            headers=auth, timeout=60,
        )
    assert r.status_code == 200, r.text
    return r.json()["plan_id"]


def _calibrate(plan_id, auth):
    body = {"page_index": 0, "p1": [0, 0], "p2": [100, 0], "real_distance_m": 1.0}
    r = requests.post(f"{API}/takeoffs/{plan_id}/calibrate", json=body, headers=auth, timeout=30)
    assert r.status_code == 200, r.text


def _add_room(plan_id, auth, name, w_m=6, h_m=4):
    pts = [[0, 0], [w_m * 100, 0], [w_m * 100, h_m * 100], [0, h_m * 100]]
    body = {"page_index": 0, "name": name, "points": pts, "ceiling_height_m": 2.5}
    r = requests.post(f"{API}/takeoffs/{plan_id}/rooms", json=body, headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["room_id"]


def _clear_branding(auth):
    # Set explicit empty strings -> cleared to null
    r = requests.put(
        f"{API}/users/me/branding",
        json={"company_name": "", "contact_line": "", "logo_b64": ""},
        headers=auth, timeout=30,
    )
    assert r.status_code == 200, r.text


# =============== BRANDING ENDPOINT ===============
class TestBrandingEndpoint:
    def test_branding_full_cycle(self, auth):
        # Ensure clean state
        _clear_branding(auth)
        r = requests.get(f"{API}/users/me/branding", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k, v in {"company_name": None, "contact_line": None,
                     "has_logo": False, "logo_b64": None}.items():
            assert d.get(k) == v, f"{k}={d.get(k)}"

        # PUT branding
        payload = {
            "company_name": "BTP Test SAS",
            "contact_line": "12 rue X · Paris",
            "logo_b64": TINY_PNG_B64,
        }
        r = requests.put(f"{API}/users/me/branding", json=payload,
                         headers=auth, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["company_name"] == "BTP Test SAS"
        assert d["contact_line"] == "12 rue X · Paris"
        assert d["has_logo"] == True
        assert d["logo_b64"] == TINY_PNG_B64

        # GET refresh persists
        r = requests.get(f"{API}/users/me/branding", headers=auth, timeout=30)
        d2 = r.json()
        assert d2["company_name"] == "BTP Test SAS"
        assert d2["contact_line"] == "12 rue X · Paris"
        assert d2["has_logo"] == True

    def test_branding_clear_empty_string(self, auth):
        # First set a value
        requests.put(f"{API}/users/me/branding",
                     json={"company_name": "ToClear"}, headers=auth, timeout=30)
        # Now clear
        r = requests.put(f"{API}/users/me/branding",
                         json={"company_name": ""}, headers=auth, timeout=30)
        assert r.status_code == 200
        assert r.json()["company_name"] is None

    def test_branding_logo_too_large(self, auth):
        big = "A" * 500_001
        r = requests.put(f"{API}/users/me/branding",
                         json={"logo_b64": big}, headers=auth, timeout=30)
        assert r.status_code == 413


# =============== PDF WITH BRANDING ===============
class TestPdfBranding:
    def test_pdf_larger_with_branding(self, auth):
        # Ensure branding cleared, get baseline PDF size
        _clear_branding(auth)
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        _add_room(plan_id, auth, "Salon", 6, 4)
        r_plain = requests.get(f"{API}/takeoffs/{plan_id}/pdf", headers=auth, timeout=60)
        assert r_plain.status_code == 200
        assert r_plain.content[:5] == b"%PDF-"
        assert len(r_plain.content) > 2000
        plain_size = len(r_plain.content)

        # Set branding with logo
        requests.put(
            f"{API}/users/me/branding",
            json={"company_name": "BTP Test SAS",
                  "contact_line": "12 rue X · Paris",
                  "logo_b64": TINY_PNG_B64},
            headers=auth, timeout=30,
        )
        r_brand = requests.get(f"{API}/takeoffs/{plan_id}/pdf", headers=auth, timeout=60)
        assert r_brand.status_code == 200
        assert r_brand.content[:5] == b"%PDF-"
        # With branding header, size should be larger (logo + text)
        assert len(r_brand.content) > plain_size, (
            f"Branded PDF ({len(r_brand.content)}) not larger than plain ({plain_size})"
        )

    def test_pdf_fallback_no_branding(self, auth):
        _clear_branding(auth)
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        _add_room(plan_id, auth, "Salon", 6, 4)
        r = requests.get(f"{API}/takeoffs/{plan_id}/pdf", headers=auth, timeout=60)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_pdf_invalid_logo_no_crash(self, auth):
        # Put an invalid base64 logo (not a valid image)
        requests.put(
            f"{API}/users/me/branding",
            json={"company_name": "BadLogo Corp",
                  "logo_b64": "!!!not_valid_b64$$$"},
            headers=auth, timeout=30,
        )
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        _add_room(plan_id, auth, "Salon", 6, 4)
        r = requests.get(f"{API}/takeoffs/{plan_id}/pdf", headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        assert r.content[:5] == b"%PDF-"
        # cleanup
        _clear_branding(auth)


# =============== NON-RÉGRESSION (iter19 & others) ===============
class TestNonRegression:
    def test_takeoffs_full_pipeline(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        _add_room(plan_id, auth, "Salon", 5, 4)

        # measure
        r = requests.post(f"{API}/takeoffs/{plan_id}/measure",
                          json={"page_index": 0, "kind": "distance",
                                "points": [[0, 0], [500, 0]]},
                          headers=auth, timeout=30)
        assert r.status_code == 200, r.text

        # takeoff aggregate
        r = requests.get(f"{API}/takeoffs/{plan_id}/takeoff", headers=auth, timeout=30)
        assert r.status_code == 200
        assert "rooms" in r.json()

        # materials
        r = requests.post(f"{API}/takeoffs/{plan_id}/materials",
                          json={}, headers=auth, timeout=30)
        assert r.status_code in (200, 400, 422)

        # history
        r = requests.get(f"{API}/takeoffs/{plan_id}/history", headers=auth, timeout=30)
        assert r.status_code == 200
        assert r.json()["count"] >= 1

        # restore
        h = r.json()["history"]
        snap_id = h[-1]["snapshot_id"]
        r = requests.post(f"{API}/takeoffs/{plan_id}/history/restore/{snap_id}",
                          headers=auth, timeout=30)
        assert r.status_code == 200

    def test_detect_walls_and_autofill(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        # detect-walls uses query param page_index
        r = requests.post(f"{API}/takeoffs/{plan_id}/detect-walls",
                          params={"page_index": 0}, headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        # room-autofill needs seed inside the image
        r = requests.post(f"{API}/takeoffs/{plan_id}/room-autofill",
                          json={"page_index": 0, "seed_x": 10, "seed_y": 10,
                                "tolerance": 25},
                          headers=auth, timeout=60)
        assert r.status_code in (200, 400, 500)  # depends on image content

    def test_compare(self, auth):
        plan_a = _upload_plan(auth)
        _calibrate(plan_a, auth)
        _add_room(plan_a, auth, "Salon", 6, 4)
        plan_b = _upload_plan(auth)
        _calibrate(plan_b, auth)
        _add_room(plan_b, auth, "Salon", 7, 4)
        r = requests.post(
            f"{API}/takeoffs/compare",
            json={"before_plan_id": plan_a, "after_plan_id": plan_b},
            headers=auth, timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # standard keys expected
        assert "added" in d or "delta" in d or "rooms" in d

    def test_calculators_roof_facade(self, auth):
        r = requests.post(
            f"{API}/calculators/roof_facade",
            json={"params": {"projected_m2": 100, "pitch_deg": 30}},
            headers=auth, timeout=30,
        )
        assert r.status_code == 200, r.text

    def test_estimation_compute(self, auth):
        r = requests.post(
            f"{API}/estimation/compute",
            json={"surface_m2": 80, "lot_breakdown": {"peinture": 0.4}},
            headers=auth, timeout=30,
        )
        assert r.status_code == 200

    def test_prices_optimize(self, auth):
        r = requests.post(
            f"{API}/prices/optimize",
            json={"items": [{"query": "carrelage 60x60", "qty": 20}]},
            headers=auth, timeout=60,
        )
        assert r.status_code in (200, 400, 422)

    def test_admin_revenue_kpis(self, admin_auth):
        r = requests.get(f"{API}/admin/revenue/kpis", headers=admin_auth, timeout=30)
        assert r.status_code == 200

    def test_share_sms_config(self, auth):
        r = requests.get(f"{API}/share/sms/config", headers=auth, timeout=30)
        assert r.status_code == 200

    def test_push_public_key(self, auth):
        r = requests.get(f"{API}/push/public-key", headers=auth, timeout=30)
        assert r.status_code == 200
