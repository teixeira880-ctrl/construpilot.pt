"""Iter70 — Étude PC extras : planning de chantier + envoi client + comparateur.

- Planning présent dans l'étude stockée (phases, durées, séchages, totaux cohérents)
- POST /pc-study/send : validation email (422), plan sans étude (400)
- Arithmétique planning : total_days = somme (work_days + cure_days)
"""
import os

import pytest
import requests


def _get_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.strip().split("=", 1)[1]
    return url.rstrip("/")


BASE_URL = _get_base_url()
PLAN_ID = "plan_619e41f98d6b"


@pytest.fixture(scope="module")
def pro_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "pro@construpilot.fr", "password": "Pro2026!"}, timeout=30)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


class TestPcPlanning:
    def test_planning_in_stored_study(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study",
                         headers=pro_headers, timeout=30)
        assert r.status_code == 200
        study = r.json()["pc_study"]
        pl = study.get("planning")
        assert pl and pl["phases"], "planning manquant dans l'étude stockée"
        assert pl["crew_size"] >= 1
        for ph in pl["phases"]:
            assert ph["work_days"] >= 1
            assert ph["end_day"] >= ph["start_day"]
        assert pl["total_work_days"] == sum(p["work_days"] for p in pl["phases"])
        assert pl["total_days"] == sum(p["work_days"] + p["cure_days"]
                                       for p in pl["phases"])

    def test_planning_engine_unit(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from engines.pc_study import compute_gros_oeuvre, compute_planning
        i = {"perimeter_m": 34.0, "refends_m": 8.0, "levels": 2, "wall_height_m": 2.5,
             "ground_floor_area_m2": 70.0, "upper_floors_area_m2": 50.0,
             "openings_count": 14, "avg_opening_width_m": 1.2,
             "openings_area_m2": 24.0, "stairs_count": 1}
        pl = compute_planning(compute_gros_oeuvre(i)["lots"])
        assert len(pl["phases"]) == 5  # avec escalier
        names = " ".join(p["name"] for p in pl["phases"])
        assert "fouilles" in names.lower() and "escalier" in names.lower()
        starts = [p["start_day"] for p in pl["phases"]]
        assert starts == sorted(starts), "phases non séquentielles"

    def test_pdf_includes_planning(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/pdf",
                         headers=pro_headers, timeout=60)
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert len(r.content) > 5000


class TestPcSend:
    def test_send_invalid_email_422(self, pro_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/send",
                          json={"to_email": "pas-un-email", "message": "x"},
                          headers=pro_headers, timeout=30)
        assert r.status_code == 422

    def test_send_unknown_plan_404(self, pro_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/plan_inexistant/pc-study/send",
                          json={"to_email": "client@exemple.fr", "message": ""},
                          headers=pro_headers, timeout=30)
        assert r.status_code == 404

    def test_send_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/send",
                          json={"to_email": "client@exemple.fr"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_send_history_recorded(self, pro_headers):
        # L'envoi réel a été fait manuellement vers delivered@resend.dev (sink Resend)
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}",
                         headers=pro_headers, timeout=30)
        assert r.status_code == 200
        reports = r.json().get("sent_reports") or []
        assert any(s.get("kind") == "pc_study" for s in reports), \
            "l'envoi pc_study doit apparaître dans sent_reports"
