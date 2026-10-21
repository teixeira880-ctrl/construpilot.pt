"""Module 6 — Planning de chantier : tests end-to-end (CPM, replanif, suggestions, OR-Tools, PDF, RBAC)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PRO_EMAIL = "pro@construpilot.fr"
PRO_PWD = "Pro2026!"
CLIENT_EMAIL = "client@construpilot.fr"
CLIENT_PWD = "Client2026!"
EXISTING_CID = "cht_865024ac1183"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def pro():
    return _login(PRO_EMAIL, PRO_PWD)


@pytest.fixture(scope="module")
def client_sess():
    return _login(CLIENT_EMAIL, CLIENT_PWD)


# ---------- Section 1 — list + existing planning ----------

def test_01_get_existing_planning(pro):
    r = pro.get(f"{API}/planning/chantiers/{EXISTING_CID}", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["exists"] is True
    assert "schedule" in data
    assert "suggestions" in data
    assert len(data["tasks"]) >= 1
    assert data["schedule"]["project"]["end_date"]


def test_02_list_chantiers(pro):
    r = pro.get(f"{API}/chantiers", timeout=20)
    assert r.status_code == 200
    ids = [c.get("chantier_id") for c in r.json()]
    assert EXISTING_CID in ids


# ---------- Section 2 — fresh chantier init/delete ----------

@pytest.fixture(scope="module")
def fresh_cid(pro):
    r = pro.post(f"{API}/chantiers", json={"name": "TEST planning"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    cid = r.json().get("chantier_id") or r.json().get("id")
    assert cid
    yield cid
    pro.delete(f"{API}/planning/chantiers/{cid}", timeout=20)
    pro.delete(f"{API}/chantiers/{cid}", timeout=20)


def test_03_get_plan_before_init(pro, fresh_cid):
    r = pro.get(f"{API}/planning/chantiers/{fresh_cid}", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is False
    assert "lots_available" in data
    assert "trades" in data
    assert isinstance(data["trades"], list) and len(data["trades"]) > 0


def test_04_init_plan(pro, fresh_cid):
    r = pro.post(f"{API}/planning/chantiers/{fresh_cid}/init",
                 json={"start_date": "2026-10-12", "from_quotes": True}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["exists"] is True
    assert "schedule" in data and data["schedule"]["project"]["start_date"]


# ---------- Section 3 — PUT with calendar + resources ----------

def test_05_put_plan_calendar_and_resources(pro, fresh_cid):
    payload = {
        "start_date": "2026-10-12",
        "deadline": "2026-11-13",
        "holidays": ["2026-11-11"],
        "workdays": [0, 1, 2, 3, 4],
        "capacities": {},
        "tasks": [
            {"id": "a", "name": "Démolition", "resource": "Démolition", "duration": 3, "predecessors": []},
            {"id": "b", "name": "Gros oeuvre", "resource": "Gros œuvre", "duration": 5, "predecessors": [{"id": "a"}]},
            {"id": "c", "name": "Électricité", "resource": "Électricité", "duration": 4, "predecessors": [{"id": "b"}]},
            {"id": "d", "name": "Plomberie", "resource": "Plomberie", "duration": 4, "predecessors": [{"id": "b"}]},
            {"id": "e", "name": "Plâtrerie 1", "resource": "Plâtrerie", "duration": 5, "predecessors": [{"id": "c"}, {"id": "d"}]},
            {"id": "f", "name": "Plâtrerie 2", "resource": "Plâtrerie", "duration": 5, "predecessors": [{"id": "c"}, {"id": "d"}]},
            {"id": "g", "name": "Peinture", "resource": "Peinture", "duration": 4, "predecessors": [{"id": "e"}, {"id": "f"}]},
        ],
    }
    r = pro.put(f"{API}/planning/chantiers/{fresh_cid}", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    sched = data["schedule"]
    tasks = {t["id"]: t for t in sched["tasks"]}
    # Weekends never used
    import datetime
    for t in sched["tasks"]:
        sd = datetime.date.fromisoformat(t["start_date"])
        ed = datetime.date.fromisoformat(t["end_date"])
        assert sd.weekday() < 5, f"Task {t['id']} starts on weekend {sd}"
        assert ed.weekday() < 5, f"Task {t['id']} ends on weekend {ed}"
        assert t["start_date"] != "2026-11-11", f"Task {t['id']} starts on holiday"
        assert t["end_date"] != "2026-11-11", f"Task {t['id']} ends on holiday"
    # No overlap between e and f (same resource Plâtrerie, cap 1)
    e, f = tasks["e"], tasks["f"]
    assert e["end_idx"] <= f["start_idx"] or f["end_idx"] <= e["start_idx"], \
        f"Plâtrerie tasks overlap: e={e['start_idx']}-{e['end_idx']}, f={f['start_idx']}-{f['end_idx']}"
    # critical path non-empty
    assert len(sched["project"]["critical_path"]) > 0
    # deadline_gap_days negative (plan likely exceeds nov 13)
    gap = sched["project"]["deadline_gap_days"]
    assert gap is not None
    # suggestions contain deadline and add_crew
    kinds = {s["kind"] for s in data["suggestions"]}
    assert "deadline" in kinds, f"kinds={kinds}"
    assert "add_crew" in kinds, f"kinds={kinds}"
    # add_crew suggestion carries action.capacity (value) or capacity field
    ac = next(s for s in data["suggestions"] if s["kind"] == "add_crew")
    assert "action" in ac and ac["action"].get("type") == "capacity"
    assert ac["action"].get("value", 0) >= 2


# ---------- Section 4 — validations ----------

def test_06_cycle_rejected(pro, fresh_cid):
    payload = {
        "start_date": "2026-10-12",
        "tasks": [
            {"id": "a", "name": "A", "duration": 2, "predecessors": [{"id": "b"}]},
            {"id": "b", "name": "B", "duration": 2, "predecessors": [{"id": "a"}]},
        ],
    }
    r = pro.put(f"{API}/planning/chantiers/{fresh_cid}", json=payload, timeout=20)
    assert r.status_code == 422, r.text
    # French message
    body = r.json()
    msg = str(body.get("detail") or body)
    assert any(w in msg.lower() for w in ["boucle", "dépend", "depend"])


def test_07_duplicate_ids(pro, fresh_cid):
    payload = {
        "start_date": "2026-10-12",
        "tasks": [
            {"id": "a", "name": "A", "duration": 2, "predecessors": []},
            {"id": "a", "name": "A2", "duration": 2, "predecessors": []},
        ],
    }
    r = pro.put(f"{API}/planning/chantiers/{fresh_cid}", json=payload, timeout=20)
    assert r.status_code == 422


def test_08_duration_zero(pro, fresh_cid):
    payload = {
        "start_date": "2026-10-12",
        "tasks": [{"id": "a", "name": "A", "duration": 0, "predecessors": []}],
    }
    r = pro.put(f"{API}/planning/chantiers/{fresh_cid}", json=payload, timeout=20)
    assert r.status_code == 422


# ---------- Section 5 — progress PATCH ----------

def test_09_patch_progress_100(pro, fresh_cid):
    # First recreate valid plan
    payload = {
        "start_date": "2026-10-12", "deadline": "2026-12-15",
        "holidays": [], "workdays": [0, 1, 2, 3, 4], "capacities": {},
        "tasks": [
            {"id": "a", "name": "A", "resource": "R1", "duration": 3, "predecessors": []},
            {"id": "b", "name": "B", "resource": "R2", "duration": 3, "predecessors": [{"id": "a"}]},
        ],
    }
    pro.put(f"{API}/planning/chantiers/{fresh_cid}", json=payload, timeout=20)
    r = pro.patch(f"{API}/planning/chantiers/{fresh_cid}/tasks/a",
                  json={"progress": 100, "actual_start": "2026-10-12", "actual_end": "2026-10-14"}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    task_a = next(t for t in data["schedule"]["tasks"] if t["id"] == "a")
    assert task_a["fixed"] is True
    assert task_a["actual_start"] == "2026-10-12"
    assert task_a["actual_end"] == "2026-10-14"
    assert task_a["progress"] == 100


def test_10_patch_progress_50_auto_actual_start(pro, fresh_cid):
    r = pro.patch(f"{API}/planning/chantiers/{fresh_cid}/tasks/b",
                  json={"progress": 50}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    task_b = next(t for t in data["schedule"]["tasks"] if t["id"] == "b")
    assert task_b["actual_start"]  # auto-filled


# ---------- Section 6 — baseline + drift ----------

def test_11_baseline(pro, fresh_cid):
    r = pro.post(f"{API}/planning/chantiers/{fresh_cid}/baseline", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["baseline"]["end_date"]
    assert data["baseline"].get("frozen_at")


def test_12_drift_after_slip(pro, fresh_cid):
    # inflate durations to force slip
    payload = {
        "start_date": "2026-10-12", "deadline": "2026-12-15",
        "holidays": [], "workdays": [0, 1, 2, 3, 4], "capacities": {},
        "tasks": [
            {"id": "a", "name": "A", "resource": "R1", "duration": 3, "predecessors": [],
             "progress": 100, "actual_start": "2026-10-12", "actual_end": "2026-10-14"},
            {"id": "b", "name": "B", "resource": "R2", "duration": 20, "predecessors": [{"id": "a"}]},
        ],
    }
    r = pro.put(f"{API}/planning/chantiers/{fresh_cid}", json=payload, timeout=20)
    assert r.status_code == 200
    kinds = {s["kind"] for s in r.json()["suggestions"]}
    assert "drift" in kinds, f"kinds={kinds}"


# ---------- Section 7 — optimize ----------

def test_13_optimize(pro, fresh_cid):
    # Build a plan with real resource conflict
    payload = {
        "start_date": "2026-10-12", "deadline": "2026-12-31",
        "holidays": [], "workdays": [0, 1, 2, 3, 4], "capacities": {},
        "tasks": [
            {"id": "a", "name": "A", "resource": "R1", "duration": 3, "predecessors": []},
            {"id": "b", "name": "B", "resource": "R1", "duration": 3, "predecessors": []},
            {"id": "c", "name": "C", "resource": "R2", "duration": 2, "predecessors": [{"id": "a"}]},
        ],
    }
    pro.put(f"{API}/planning/chantiers/{fresh_cid}", json=payload, timeout=20)
    r = pro.post(f"{API}/planning/chantiers/{fresh_cid}/optimize", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["optimization"]["ok"] is True
    assert data["optimization"]["makespan_days"] <= data["optimization"]["baseline_days"]


def test_14_optimize_apply(pro, fresh_cid):
    r = pro.post(f"{API}/planning/chantiers/{fresh_cid}/optimize?apply=true", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "optimization" in data
    # applied is True only when gain_days > 0 ; either way should not error
    assert "applied" in data


# ---------- Section 8 — PDF ----------

def test_15_pdf_existing(pro):
    r = pro.get(f"{API}/planning/chantiers/{EXISTING_CID}/pdf", timeout=30)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


# ---------- Section 9 — RBAC ----------

def test_16_client_forbidden(client_sess):
    r = client_sess.get(f"{API}/planning/chantiers/{EXISTING_CID}", timeout=20)
    assert r.status_code == 403, r.text


def test_17_unknown_chantier(pro):
    r = pro.get(f"{API}/planning/chantiers/cht_doesnotexist", timeout=20)
    assert r.status_code == 404
