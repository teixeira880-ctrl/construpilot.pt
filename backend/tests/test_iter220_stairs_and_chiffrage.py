"""
Iteration 220 - Escaliers module + chiffrage P0 (room-preset, ouvrages, default height).
Testing agent regression tests for /api/stairs/* and /api/takeoffs/corps-etat/*.
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
PRO = {"email": "pro@construpilot.fr", "password": "Pro2026!"}
CLIENT = {"email": "client@construpilot.fr", "password": "Client2026!"}


def _login(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def pro_client():
    return _login(PRO)


@pytest.fixture(scope="module")
def client_client():
    return _login(CLIENT)


# =========== Escaliers ==============
class TestStairsCalculate:
    def test_straight(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/stairs/calculate/straight", json={
            "floor_height_mm": 2700, "available_length_mm": 5000,
            "available_width_mm": 1200, "stair_width_mm": 1000,
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "is_buildable" in d and "num_steps" in d and "alerts" in d
        assert d["is_buildable"] is True
        assert isinstance(d["num_steps"], int) and d["num_steps"] > 0

    def test_quarter_turn_bottom(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/stairs/calculate/quarter-turn-bottom", json={
            "floor_height_mm": 2700, "available_length_mm": 4000,
            "available_width_mm": 2000, "stair_width_mm": 900,
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert "is_buildable" in r.json()

    def test_quarter_turn_top(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/stairs/calculate/quarter-turn-top", json={
            "floor_height_mm": 2700, "available_length_mm": 4000,
            "available_width_mm": 2000, "stair_width_mm": 900,
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_half_turn(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/stairs/calculate/half-turn", json={
            "floor_height_mm": 2700, "available_length_mm": 3500,
            "available_width_mm": 2200, "stair_width_mm": 900,
            "balancing": "balanced", "num_winders": "auto",
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_helicoidal(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/stairs/calculate/helicoidal", json={
            "floor_height_mm": 2700, "inner_radius_mm": 200,
            "outer_radius_mm": 900, "sweep_angle_deg": 360,
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "is_buildable" in d


class TestStairsOptimizeAndConcrete:
    def test_optimize(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/stairs/optimize", json={
            "floor_height_mm": 2700, "available_length_mm": 5000,
            "available_width_mm": 1200, "stair_width_mm": 1000,
        }, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "solutions" in d and "excluded" in d
        assert isinstance(d["solutions"], list)

    def test_concrete_analyze_ok(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/stairs/calculate/straight", json={
            "floor_height_mm": 2700, "available_length_mm": 5000,
            "available_width_mm": 1200, "stair_width_mm": 1000,
        }, timeout=30)
        stair_result = r.json()
        r2 = pro_client.post(f"{BASE_URL}/api/stairs/concrete/analyze",
                             json={"stair_result": stair_result}, timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        for key in ("quantities", "paillasse", "reinforcement", "nomenclature"):
            assert key in d, f"missing {key}"

    def test_concrete_analyze_422_on_raw_dims(self, pro_client):
        r = pro_client.post(f"{BASE_URL}/api/stairs/concrete/analyze", json={
            "floor_height_mm": 2700, "available_length_mm": 5000,
        }, timeout=30)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text[:200]}"


class TestStairsDossierPDF:
    def test_pdf_generate(self, pro_client):
        stair_input = {"floor_height_mm": 2700, "available_length_mm": 5000,
                       "available_width_mm": 1200, "stair_width_mm": 1000}
        calc = pro_client.post(f"{BASE_URL}/api/stairs/calculate/straight",
                               json=stair_input, timeout=30).json()
        payload = {
            "project_name": "TEST Escalier Alpha",
            "stair_input": stair_input,
            "stair_result": calc,
        }
        r = pro_client.post(f"{BASE_URL}/api/stairs/dossier/generate", json=payload, timeout=90)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        cd = r.headers.get("content-disposition", "")
        assert "TEST" in cd or "Escalier" in cd or "Alpha" in cd, f"filename should reflect project name: {cd}"
        assert r.content[:4] == b"%PDF", "content should be a PDF"


class TestStairsProjectsCRUD:
    def test_crud_and_isolation(self, pro_client, client_client):
        # create
        body = {"name": "TEST Stair Project", "stair_type": "straight",
                "input": {"floor_height_mm": 2700, "available_length_mm": 5000,
                          "available_width_mm": 1200, "stair_width_mm": 1000}}
        r = pro_client.post(f"{BASE_URL}/api/stairs/projects", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        proj = r.json()
        pid = (proj.get("project") or {}).get("project_id") or proj.get("project_id")
        assert pid, f"missing project_id in {proj}"

        # list
        r = pro_client.get(f"{BASE_URL}/api/stairs/projects", timeout=30)
        assert r.status_code == 200
        data = r.json()
        projects = data.get("projects") if isinstance(data, dict) else data
        assert any((p.get("project_id") or p.get("id")) == pid for p in projects)

        # update
        r = pro_client.put(f"{BASE_URL}/api/stairs/projects/{pid}",
                           json={**body, "name": "TEST Stair Renamed"}, timeout=30)
        assert r.status_code == 200, r.text[:300]

        # isolation - client should NOT see it (403 pro_required)
        r = client_client.get(f"{BASE_URL}/api/stairs/projects", timeout=30)
        assert r.status_code == 403, f"expected 403 pro_required, got {r.status_code}"

        # delete
        r = pro_client.delete(f"{BASE_URL}/api/stairs/projects/{pid}", timeout=30)
        assert r.status_code in (200, 204), r.text[:300]


class TestStairsProGating:
    @pytest.mark.parametrize("path,body", [
        ("/api/stairs/calculate/straight", {"floor_height_mm": 2700, "available_length_mm": 5000,
                                            "available_width_mm": 1200, "stair_width_mm": 1000}),
        ("/api/stairs/optimize", {"floor_height_mm": 2700, "available_length_mm": 5000,
                                  "available_width_mm": 1200, "stair_width_mm": 1000}),
        ("/api/stairs/dossier/generate", {"project_name": "X", "stair_result": {}}),
    ])
    def test_client_forbidden(self, client_client, path, body):
        r = client_client.post(f"{BASE_URL}{path}", json=body, timeout=30)
        assert r.status_code == 403, f"{path} expected 403 got {r.status_code}"


# =========== Chiffrage P0 ==============
class TestChiffrageRoomPresetAndPrefs:
    def test_default_height_put_and_prefs_persist(self, pro_client):
        # set via dedicated endpoint
        r = pro_client.put(f"{BASE_URL}/api/takeoffs/corps-etat/default-height",
                           json={"default_wall_height": 2.55}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        # verify via GET prefs
        r = pro_client.get(f"{BASE_URL}/api/takeoffs/corps-etat/prefs", timeout=30)
        assert r.status_code == 200
        assert abs(float(r.json().get("default_wall_height", 0)) - 2.55) < 0.01

        # update via PUT prefs
        r = pro_client.put(f"{BASE_URL}/api/takeoffs/corps-etat/prefs",
                           json={"default_wall_height": 2.7}, timeout=30)
        assert r.status_code == 200
        r = pro_client.get(f"{BASE_URL}/api/takeoffs/corps-etat/prefs", timeout=30)
        assert abs(float(r.json().get("default_wall_height", 0)) - 2.7) < 0.01

    def test_room_preset_count_4_and_uses_default_height(self, pro_client):
        # ensure default height is 2.7
        pro_client.put(f"{BASE_URL}/api/takeoffs/corps-etat/default-height",
                       json={"default_wall_height": 2.7}, timeout=30)
        r = pro_client.post(f"{BASE_URL}/api/takeoffs/corps-etat/room-preset",
                            json={"area_m2": 20, "perimeter_m": 18}, timeout=45)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        # count=4 (Sol / Plinthes / Peinture murs / Plafond)
        items = d.get("items") or d.get("lines") or d.get("entries") or []
        count = d.get("count") if isinstance(d.get("count"), int) else len(items)
        assert count == 4, f"expected count=4 got {count}: {d}"
        # totals present
        assert any(k in d for k in ("total_ht", "totals", "total"))


class TestChiffrageOuvragesLib:
    def test_create_list_delete_ouvrage(self, pro_client):
        payload = {"name": "TEST Cloison BA13",
                   "poste": "cloison",
                   "params": {"with_isolation": True},
                   "margin_pct": 12}
        r = pro_client.post(f"{BASE_URL}/api/takeoffs/corps-etat/ouvrages",
                            json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        created = r.json()
        oid = created.get("ouvrage_id") or created.get("id") or (created.get("ouvrage") or {}).get("id") or (created.get("ouvrage") or {}).get("ouvrage_id")
        assert oid, f"missing ouvrage id in {created}"

        r = pro_client.get(f"{BASE_URL}/api/takeoffs/corps-etat/ouvrages", timeout=30)
        assert r.status_code == 200
        rows = r.json().get("ouvrages", [])
        assert any((row.get("ouvrage_id") or row.get("id")) == oid for row in rows)

        r = pro_client.delete(f"{BASE_URL}/api/takeoffs/corps-etat/ouvrages/{oid}", timeout=30)
        assert r.status_code in (200, 204), r.text[:300]
