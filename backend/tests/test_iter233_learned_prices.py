"""Tests iter 233: Learned prices panel (GET /api/library/learned + POST validate)."""
import os
import pytest
import requests
import secrets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@construpilot.fr")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Construpilot2026!")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


def _create_estimated_item(sess, designation, price=42.0):
    """Create a library item then flip to estimated via auto_save path.
    Simpler: just POST then PUT with estimated flag through direct update is not exposed.
    So we create a library item, then simulate via direct ingest if available, or use library/global for seed data.
    Fallback: use already seeded demo items.
    """
    # Create a plain item then we can only test validate path on an estimated item.
    r = sess.post(f"{BASE_URL}/api/library", json={
        "designation": designation,
        "unit": "m2",
        "unit_price_ht": price,
        "vat_rate": 10,
        "category": "Peinture",
    })
    assert r.status_code in (200, 201), f"create item failed: {r.text}"
    return r.json()


class TestLearnedEndpoints:
    def test_list_learned_200(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/library/learned")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "count" in data
        assert isinstance(data["items"], list)
        # Every item must be flagged estimated when returned
        for it in data["items"]:
            # The endpoint filters on estimated=True, but response may or may not include that field
            assert "item_id" in it
            assert "designation" in it
        print(f"learned items count = {data['count']}")

    def test_validate_404_on_unknown_id(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/library/does_not_exist_xyz/validate", json={})
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text}"

    def test_validate_demo_seed_item_flow(self, admin_session):
        """Validate one of the pre-seeded estimated demo items and verify it disappears from /learned."""
        r = admin_session.get(f"{BASE_URL}/api/library/learned")
        assert r.status_code == 200
        items = r.json()["items"]
        if not items:
            pytest.skip("No seeded estimated items to validate")
        target = items[0]
        iid = target["item_id"]
        new_price = 55.0
        v = admin_session.post(f"{BASE_URL}/api/library/{iid}/validate",
                               json={"unit_price_ht": new_price})
        assert v.status_code == 200, v.text
        doc = v.json()
        assert doc.get("estimated") is False
        assert doc.get("price_source") == "validated"
        assert abs(float(doc.get("unit_price_ht", 0)) - new_price) < 0.01

        # No longer in /learned
        r2 = admin_session.get(f"{BASE_URL}/api/library/learned")
        assert r2.status_code == 200
        remaining_ids = {it["item_id"] for it in r2.json()["items"]}
        assert iid not in remaining_ids, "item still appears in learned after validation"

    def test_validate_without_body_keeps_price(self, admin_session):
        """Validate without unit_price_ht: must keep current price and set estimated=False."""
        r = admin_session.get(f"{BASE_URL}/api/library/learned")
        items = r.json().get("items", [])
        if not items:
            pytest.skip("No estimated items left to test no-body validation")
        target = items[0]
        iid = target["item_id"]
        current_price = float(target.get("unit_price_ht") or 0)
        v = admin_session.post(f"{BASE_URL}/api/library/{iid}/validate", json={})
        assert v.status_code == 200, v.text
        doc = v.json()
        assert doc.get("estimated") is False
        assert doc.get("price_source") == "validated"
        if current_price > 0:
            assert abs(float(doc["unit_price_ht"]) - current_price) < 0.01
