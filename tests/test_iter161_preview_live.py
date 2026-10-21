"""Preview live API checks for Radar filters/profile/qualification without postal sends."""
import os
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = os.environ["TEST_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["TEST_ADMIN_PASSWORD"]
PRO_EMAIL = os.environ["TEST_PRO_EMAIL"]
PRO_PASSWORD = os.environ["TEST_PRO_PASSWORD"]


def _login(email: str, password: str) -> dict:
    response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("token")
    return data


@pytest.fixture(scope="session")
def admin_session() -> requests.Session:
    token = _login(ADMIN_EMAIL, ADMIN_PASSWORD)["token"]
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def pro_session() -> requests.Session:
    token = _login(PRO_EMAIL, PRO_PASSWORD)["token"]
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


# Radar profile/filter persistence and reset semantics
def test_profile_filters_persist_and_reset_only_filters(admin_session: requests.Session):
    profile_before = admin_session.get(f"{BASE_URL}/api/radar/profile", timeout=30)
    assert profile_before.status_code == 200
    before = profile_before.json()
    original_filters = before.get("filters") or {"work_types": [], "building_types": [], "client_types": []}
    original_departments = before.get("departments") or []

    target_filters = {
        "work_types": ["neuf", "extension"],
        "building_types": ["maison"],
        "client_types": ["entreprise"],
    }
    try:
        put_selected = admin_session.put(f"{BASE_URL}/api/radar/profile", json={"filters": target_filters}, timeout=30)
        assert put_selected.status_code == 200, put_selected.text
        selected = put_selected.json()
        assert selected["filters"]["work_types"] == ["extension", "neuf"]
        assert selected["filters"]["building_types"] == ["maison"]
        assert selected["filters"]["client_types"] == ["entreprise"]

        put_reset = admin_session.put(
            f"{BASE_URL}/api/radar/profile",
            json={"filters": {"work_types": [], "building_types": [], "client_types": []}},
            timeout=30,
        )
        assert put_reset.status_code == 200, put_reset.text
        after_reset = put_reset.json()
        assert after_reset["filters"] == {"work_types": [], "building_types": [], "client_types": []}
        assert after_reset.get("departments") == original_departments
    finally:
        restore = admin_session.put(f"{BASE_URL}/api/radar/profile", json={"filters": original_filters}, timeout=30)
        assert restore.status_code == 200, restore.text


# Radar opportunities contract: filters/facets/unfiltered_count and classification
def test_opportunities_contract_and_filter_dedup(admin_session: requests.Session):
    response = admin_session.get(
        f"{BASE_URL}/api/radar/opportunities",
        params={
            "work_types": "neuf,neuf,extension",
            "building_types": "maison",
            "client_types": "entreprise",
            "page": 1,
            "page_size": 10,
        },
        timeout=45,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "filters" in data and "facets" in data and "unfiltered_count" in data
    assert data["filters"]["work_types"] == ["extension", "neuf"]
    assert data["filters"]["building_types"] == ["maison"]
    assert data["filters"]["client_types"] == ["entreprise"]
    assert isinstance(data["unfiltered_count"], int)
    for item in data.get("opportunities", []):
        assert "classification" in item
        assert "work_types" in item["classification"]
        assert "building_types" in item["classification"]
        assert "client_type" in item["classification"]


# Radar invalid filter categories must be rejected with 422
def test_invalid_filter_value_rejected_422(admin_session: requests.Session):
    response = admin_session.get(
        f"{BASE_URL}/api/radar/opportunities",
        params={"client_types": "guessed_bank"},
        timeout=30,
    )
    assert response.status_code == 422


# Official sync status should not end in error and maison filters should return data
def test_sync_status_and_maison_results(admin_session: requests.Session):
    last = None
    for _ in range(8):
        response = admin_session.get(
            f"{BASE_URL}/api/radar/opportunities",
            params={"building_types": "maison", "page": 1, "page_size": 20},
            timeout=45,
        )
        assert response.status_code == 200, response.text
        last = response.json()
        statuses = [d.get("status") for d in (last.get("sync") or {}).get("departments", [])]
        assert "error" not in statuses
        if statuses and all(status != "running" for status in statuses):
            break
        time.sleep(3)
    assert last is not None
    assert isinstance(last.get("count"), int)
    assert last.get("count", 0) > 0


# Qualification private override is user-scoped and restorable
def test_qualification_user_scoped_and_validation(admin_session: requests.Session, pro_session: requests.Session):
    listed = admin_session.get(f"{BASE_URL}/api/radar/opportunities", params={"page": 1, "page_size": 20}, timeout=45)
    assert listed.status_code == 200, listed.text
    opportunities = listed.json().get("opportunities", [])
    assert opportunities
    target = next((item for item in opportunities if not item.get("is_demo")), opportunities[0])
    opp_id = target["id"]

    admin_before = admin_session.get(f"{BASE_URL}/api/radar/opportunities/{opp_id}", timeout=30)
    assert admin_before.status_code == 200, admin_before.text
    before = admin_before.json()
    existing = before.get("qualification")

    try:
        put_ok = admin_session.put(
            f"{BASE_URL}/api/radar/opportunities/{opp_id}/qualification",
            json={"category": "banque", "source_note": "TEST_ITER161 qualification check", "confirmed": True},
            timeout=30,
        )
        assert put_ok.status_code == 200, put_ok.text
        data_ok = put_ok.json()
        assert data_ok["qualification"]["category"] == "banque"
        assert data_ok["classification"]["client_type"] == "banque"
        assert data_ok["classification"]["client_source"] == "user_confirmed"

        pro_view = pro_session.get(f"{BASE_URL}/api/radar/opportunities/{opp_id}", timeout=30)
        assert pro_view.status_code == 200, pro_view.text
        pro_data = pro_view.json()
        assert not pro_data.get("qualification")

        invalid_note = admin_session.put(
            f"{BASE_URL}/api/radar/opportunities/{opp_id}/qualification",
            json={"category": "architecte", "source_note": "", "confirmed": True},
            timeout=30,
        )
        assert invalid_note.status_code == 422

        invalid_confirmed = admin_session.put(
            f"{BASE_URL}/api/radar/opportunities/{opp_id}/qualification",
            json={"category": "architecte", "source_note": "note ok", "confirmed": False},
            timeout=30,
        )
        assert invalid_confirmed.status_code == 422

        invalid_category = admin_session.put(
            f"{BASE_URL}/api/radar/opportunities/{opp_id}/qualification",
            json={"category": "invalid_category", "source_note": "note ok", "confirmed": True},
            timeout=30,
        )
        assert invalid_category.status_code == 422
    finally:
        if existing:
            restore = admin_session.put(
                f"{BASE_URL}/api/radar/opportunities/{opp_id}/qualification",
                json={
                    "category": existing["category"],
                    "source_note": existing["source_note"],
                    "confirmed": True,
                },
                timeout=30,
            )
            assert restore.status_code == 200, restore.text
        else:
            remove = admin_session.delete(f"{BASE_URL}/api/radar/opportunities/{opp_id}/qualification", timeout=30)
            assert remove.status_code == 200, remove.text
            after_remove = remove.json()
            assert not after_remove.get("qualification")
            assert after_remove["classification"].get("client_source") != "user_confirmed"
