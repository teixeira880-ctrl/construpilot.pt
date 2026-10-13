"""Iteration 129 tests:
(A) User preferences price_library_mode
(B) Documents from-text with library pricing
(C) Estimation catalog + pool_items for piscine_* project types
(D) Profitability report full CRUD flow
"""
import os
import pytest
import requests


def _read_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _read_backend_url()
ADMIN = {"email": "deboradsmelo@gmail.com", "password": "Miguel1156."}


def _login(creds):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:300]}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- (A) User preferences price_library_mode ----------
class TestPreferences:
    def test_pref_set_company_first_and_get_me(self, h):
        r = requests.put(f"{BASE}/api/users/me/preferences",
                         json={"price_library_mode": "company_first"}, headers=h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # find price_library_mode in response somewhere
        got = data.get("price_library_mode") or (data.get("preferences") or {}).get("price_library_mode") \
              or (data.get("user") or {}).get("price_library_mode")
        assert got == "company_first", f"expected company_first, got {data}"

        me = requests.get(f"{BASE}/api/auth/me", headers=h, timeout=15).json()
        assert me.get("price_library_mode") == "company_first", me

    def test_pref_invalid_value_422(self, h):
        r = requests.put(f"{BASE}/api/users/me/preferences",
                         json={"price_library_mode": "banana"}, headers=h, timeout=15)
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text[:200]}"

    def test_pref_reset_to_shared_first(self, h):
        r = requests.put(f"{BASE}/api/users/me/preferences",
                         json={"price_library_mode": "shared_first"}, headers=h, timeout=15)
        assert r.status_code == 200
        me = requests.get(f"{BASE}/api/auth/me", headers=h, timeout=15).json()
        assert me.get("price_library_mode") == "shared_first"


# ---------- (B) Documents from-text with library pricing ----------
class TestFromText:
    def test_from_text_priced_lines(self, h):
        payload = {
            "text": "Rénovation salle de bain 12 m² : dépose carrelage, faïence 25 m², "
                    "douche italienne, meuble vasque, peinture plafond"
        }
        r = requests.post(f"{BASE}/api/documents/from-text", json=payload,
                          headers=h, timeout=120)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        data = r.json()
        doc_id = data.get("doc_id") or (data.get("doc") or {}).get("doc_id")
        assert doc_id, f"no doc_id in {data}"

        lines = data.get("lines") or (data.get("doc") or {}).get("lines") or []
        if not lines:
            # fetch doc
            d = requests.get(f"{BASE}/api/documents/{doc_id}", headers=h, timeout=15).json()
            lines = d.get("lines") or []
        assert len(lines) >= 3, f"expected >=3 lines got {len(lines)}"

        priced = [l for l in lines if float(l.get("unit_price_ht") or 0) > 0]
        pct = len(priced) / len(lines)
        assert pct >= 0.6, f"priced coverage {pct:.0%} < 60%; lines={lines}"

        # at least one line with a library price_source
        sources = [(l.get("price_source") or "") for l in lines]
        has_lib = any("bibliotheque" in s for s in sources)
        assert has_lib, f"no library price_source in {sources}"

        # cleanup
        try:
            requests.delete(f"{BASE}/api/documents/{doc_id}", headers=h, timeout=10)
        except Exception:
            pass


# ---------- (C) Estimation catalog + piscine pool_items ----------
class TestEstimationPool:
    def test_catalog_contains_piscine_types(self):
        r = requests.get(f"{BASE}/api/estimation/catalog", timeout=15)
        assert r.status_code == 200, r.text
        cat = r.json()
        types = cat.get("project_types") or []
        keys = {(t.get("key") or t.get("id") or t.get("value") or t) if isinstance(t, dict) else t for t in types}
        for k in ("piscine_beton", "piscine_coque", "piscine_renovation"):
            assert k in keys, f"missing {k} in {keys}"

    def test_compute_piscine_beton_anonymous(self):
        payload = {"project_type": "piscine_beton", "surface": 32, "finish_level": "standard", "country": "FR"}
        r = requests.post(f"{BASE}/api/estimation/compute", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        est = r.json()
        pool = est.get("pool_items")
        assert pool, f"no pool_items in {est.keys()}"
        assert len(pool.get("lines") or []) >= 15, f"only {len(pool.get('lines') or [])} pool lines"
        geom = pool.get("geometry") or {}
        assert abs(float(geom.get("length") or 0) - 8) < 0.5, geom
        assert abs(float(geom.get("width") or 0) - 4) < 0.5, geom
        assert float(pool.get("total_ht") or 0) > 0
        for l in pool["lines"]:
            assert float(l.get("qty") or 0) > 0, l
            assert float(l.get("unit_price_ht") or 0) > 0, l
        return float(pool["total_ht"])

    def test_compute_piscine_coque_has_forfait(self):
        r = requests.post(f"{BASE}/api/estimation/compute",
                          json={"project_type": "piscine_coque", "surface": 32, "finish_level": "standard", "country": "FR"},
                          timeout=30)
        assert r.status_code == 200
        pool = r.json().get("pool_items") or {}
        designations = " | ".join((l.get("designation") or "").lower() for l in pool.get("lines") or [])
        assert "piscine coque" in designations or "coque polyester" in designations, designations

    def test_compute_non_pool_type_has_no_pool_items(self):
        r = requests.post(f"{BASE}/api/estimation/compute",
                          json={"project_type": "renovation_complete", "surface": 80, "finish_level": "standard", "country": "FR"},
                          timeout=30)
        assert r.status_code == 200
        assert "pool_items" not in r.json() or r.json().get("pool_items") in (None, {}, [])

    def test_pro_prices_lower_than_anonymous(self, h):
        payload = {"project_type": "piscine_beton", "surface": 32, "finish_level": "standard", "country": "FR"}
        anon = requests.post(f"{BASE}/api/estimation/compute", json=payload, timeout=30).json()
        pro = requests.post(f"{BASE}/api/estimation/compute", json=payload, headers=h, timeout=30).json()
        a = float((anon.get("pool_items") or {}).get("total_ht") or 0)
        p = float((pro.get("pool_items") or {}).get("total_ht") or 0)
        assert a > 0 and p > 0
        assert p < a, f"pro total {p} should be lower than anon {a} (no +30% markup)"


# ---------- (D) Profitability flow ----------
class TestProfitability:
    @pytest.fixture(scope="class")
    def created_doc_id(self, h):
        payload = {
            "doc_type": "quote",
            "title": "TEST_iter129 rentabilité",
            "lines": [{"designation": "Test", "unit": "u", "qty": 2, "unit_price_ht": 100,
                       "cost_price_ht": 60, "vat_rate": 20}],
        }
        r = requests.post(f"{BASE}/api/documents", json=payload, headers=h, timeout=15)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        doc_id = doc.get("doc_id") or doc.get("id")
        assert doc_id
        yield doc_id
        try:
            requests.delete(f"{BASE}/api/documents/{doc_id}", headers=h, timeout=10)
        except Exception:
            pass

    def test_01_report_include_open(self, h):
        r = requests.get(f"{BASE}/api/pro/profitability?include_open=true", headers=h, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("summary", "monthly", "jobs"):
            assert k in data, f"missing {k}"

    def test_02_finish_true(self, h, created_doc_id):
        r = requests.patch(f"{BASE}/api/pro/profitability/{created_doc_id}/finish",
                           json={"finished": True}, headers=h, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["job"]["finished"] is True

    def test_03_add_cost(self, h, created_doc_id):
        r = requests.post(f"{BASE}/api/pro/profitability/{created_doc_id}/costs",
                          json={"label": "TEST_Achat test", "amount_ht": 50, "kind": "achat"},
                          headers=h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["costs"]) == 1
        job = data["job"]
        assert job["real_cost_ht"] == 50.0
        assert job["cost_basis"] == "reel"
        assert job["margin_ht"] == round(job["revenue_ht"] - 50, 2)

    def test_04_report_lists_job(self, h, created_doc_id):
        r = requests.get(f"{BASE}/api/pro/profitability", headers=h, timeout=20)
        assert r.status_code == 200
        data = r.json()
        job_ids = [j["doc_id"] for j in data["jobs"]]
        assert created_doc_id in job_ids, f"created doc {created_doc_id} not in jobs {job_ids[:5]}"

    def test_05_delete_cost_and_verify_basis(self, h, created_doc_id):
        # find cost_id
        r = requests.get(f"{BASE}/api/pro/profitability/{created_doc_id}/costs", headers=h, timeout=15).json()
        costs = r["costs"]
        assert len(costs) == 1
        cost_id = costs[0]["cost_id"]
        d = requests.delete(f"{BASE}/api/pro/profitability/costs/{cost_id}", headers=h, timeout=15)
        assert d.status_code == 200
        assert d.json().get("ok") is True

        r2 = requests.get(f"{BASE}/api/pro/profitability/{created_doc_id}/costs", headers=h, timeout=15).json()
        assert len(r2["costs"]) == 0
        assert r2["job"]["cost_basis"] == "devis"

    def test_06_unfinish(self, h, created_doc_id):
        r = requests.patch(f"{BASE}/api/pro/profitability/{created_doc_id}/finish",
                           json={"finished": False}, headers=h, timeout=15)
        assert r.status_code == 200
        assert r.json()["job"]["finished"] is False

    def test_07_invalid_doc_404(self, h):
        r = requests.patch(f"{BASE}/api/pro/profitability/doc_deadbeef/finish",
                           json={"finished": True}, headers=h, timeout=15)
        assert r.status_code == 404
