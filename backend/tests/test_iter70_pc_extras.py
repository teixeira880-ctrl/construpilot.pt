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
        assert len(pl["phases"]) == 10  # tous corps d'état, avec escalier
        names = " ".join(p["name"] for p in pl["phases"])
        assert "terrassement" in names.lower() and "escalier" in names.lower()
        assert "charpente" in names.lower() and "menuiseries" in names.lower()
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


class TestPcSettings:
    def test_get_settings_with_defaults(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/pc/settings", headers=pro_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert len(d["defaults"]["unit_prices"]) == 21
        assert d["defaults"]["crew_size"] >= 1

    def test_put_recompute_and_reset(self, pro_headers):
        r0 = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study",
                          headers=pro_headers, timeout=30)
        base_ttc = r0.json()["pc_study"]["totals"]["ttc"]
        r = requests.put(f"{BASE_URL}/api/pc/settings", json={
            "unit_prices": {"mur_isobrique": {"mat": 60, "mo": 70}},
            "crew_size": 5, "hourly_rate_eur": 50}, headers=pro_headers, timeout=30)
        assert r.status_code == 200
        r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/recompute",
                          headers=pro_headers, timeout=30)
        assert r.status_code == 200
        study = r.json()
        assert study["custom_pricing"] == True
        assert study["planning"]["crew_size"] == 5
        assert study["totals"]["ttc"] > base_ttc
        # reset → retour au TTC de base
        assert requests.delete(f"{BASE_URL}/api/pc/settings",
                               headers=pro_headers, timeout=30).status_code == 200
        r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/recompute",
                          headers=pro_headers, timeout=30)
        assert r.json()["totals"]["ttc"] == pytest.approx(base_ttc, abs=0.02)
        assert r.json()["custom_pricing"] == False

    def test_put_rejects_bad_crew(self, pro_headers):
        r = requests.put(f"{BASE_URL}/api/pc/settings", json={"crew_size": 99},
                         headers=pro_headers, timeout=30)
        assert r.status_code == 422

    def test_settings_require_auth(self):
        assert requests.get(f"{BASE_URL}/api/pc/settings",
                            timeout=30).status_code in (401, 403)


class TestPcTracking:
    def test_pixel_public_and_idempotent(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}", headers=pro_headers,
                         timeout=30)
        tracked = [s for s in r.json().get("sent_reports") or []
                   if s.get("track_id")]
        assert tracked, "au moins un envoi pc_study doit avoir un track_id"
        tid = tracked[-1]["track_id"]
        # pixel public (sans auth), gif, 2 hits = idempotent
        for _ in range(2):
            px = requests.get(f"{BASE_URL}/api/pc/track/{tid}", timeout=30)
            assert px.status_code == 200
            assert px.headers["content-type"].startswith("image/gif")
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}", headers=pro_headers,
                         timeout=30)
        s = [x for x in r.json()["sent_reports"] if x.get("track_id") == tid][0]
        assert s["opened"] == True and s.get("opened_at")

    def test_pixel_unknown_track_id_still_200(self):
        px = requests.get(f"{BASE_URL}/api/pc/track/pct_inconnu", timeout=30)
        assert px.status_code == 200


class TestPcLevelsAndGantt:
    def test_levels_breakdown_in_study(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study",
                         headers=pro_headers, timeout=30)
        study = r.json()["pc_study"]
        lb = study.get("levels_breakdown")
        assert lb and "fondations" in lb[0]["name"].lower()
        assert len(lb) >= 2  # Fondations + RDC au minimum
        # cohérence : somme des HT niveaux ≈ HT global (arrondis qty par niveau)
        assert sum(l["ht"] for l in lb) == pytest.approx(study["totals"]["ht"], abs=10.0)

    def test_levels_engine_sums_match_global(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from engines.pc_study import compute_gros_oeuvre, compute_levels_breakdown
        i = {"perimeter_m": 34.0, "refends_m": 8.0, "levels": 2, "wall_height_m": 2.5,
             "ground_floor_area_m2": 70.0, "upper_floors_area_m2": 50.0,
             "openings_count": 14, "avg_opening_width_m": 1.2,
             "openings_area_m2": 24.0, "stairs_count": 1}
        lb = compute_levels_breakdown(i)
        g = compute_gros_oeuvre(i)["totals"]
        assert [l["name"] for l in lb] == ["Chantier, terrassement & fondations",
                                           "RDC", "R+1",
                                           "Charpente, couverture & menuiseries"]
        assert sum(l["ht"] for l in lb) == pytest.approx(g["ht"], abs=10.0)
        assert sum(l["acier_kg"] for l in lb) == pytest.approx(g["acier_kg"], abs=0.5)

    def test_schedule_with_dates_skips_weekends(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from engines.pc_study import (compute_gros_oeuvre, compute_planning,
                                      schedule_with_dates)
        i = {"perimeter_m": 34.0, "refends_m": 8.0, "levels": 2, "wall_height_m": 2.5,
             "ground_floor_area_m2": 70.0, "upper_floors_area_m2": 50.0,
             "openings_count": 14, "avg_opening_width_m": 1.2,
             "openings_area_m2": 24.0, "stairs_count": 1}
        pl = compute_planning(compute_gros_oeuvre(i)["lots"])
        # samedi 2026-09-05 → démarrage lundi 07/09
        rows = schedule_with_dates(pl, "2026-09-05")
        assert rows[0]["work_start"] == "2026-09-07"
        from datetime import date
        for r in rows:
            assert date.fromisoformat(r["work_start"]).weekday() < 5

    def test_pdf_with_start_param(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/pdf?start=2026-09-07",
                         headers=pro_headers, timeout=60)
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        r2 = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/pdf?start=pas-une-date",
                          headers=pro_headers, timeout=60)
        assert r2.status_code == 200  # date invalide ignorée proprement


class TestPcReminders:
    def test_reminder_settings_roundtrip(self, pro_headers):
        r = requests.put(f"{BASE_URL}/api/pc/settings", json={"reminder_days": 5},
                         headers=pro_headers, timeout=30)
        assert r.status_code == 200
        r = requests.get(f"{BASE_URL}/api/pc/settings", headers=pro_headers, timeout=30)
        assert r.json()["settings"]["reminder_days"] == 5
        assert r.json()["defaults"]["reminder_days"] == 3
        requests.delete(f"{BASE_URL}/api/pc/settings", headers=pro_headers, timeout=30)

    def test_reminder_days_bounds(self, pro_headers):
        r = requests.put(f"{BASE_URL}/api/pc/settings", json={"reminder_days": 99},
                         headers=pro_headers, timeout=30)
        assert r.status_code == 422

    def test_reminders_run_requires_admin(self, pro_headers):
        r = requests.post(f"{BASE_URL}/api/pc/reminders/run",
                          headers=pro_headers, timeout=30)
        assert r.status_code in (401, 403)

    def test_reminders_run_idempotent(self):
        # Un envoi déjà relancé (reminder_sent=True) ne doit pas être relancé 2×
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@construpilot.fr", "password": "Construpilot2026!"},
            timeout=30)
        admin = {"Authorization": f"Bearer {r.json()['token']}"}
        out = requests.post(f"{BASE_URL}/api/pc/reminders/run",
                            headers=admin, timeout=60).json()
        assert out["sent"] == 0, "les envois déjà relancés/ouverts ne doivent pas repartir"

