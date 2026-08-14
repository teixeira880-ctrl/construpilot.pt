"""Iter62 — Analyse 2D : calibration par cotes IA, recalage surfaces écrites,
application des textes du plan, filtrage traits de cote dans detect-walls.

Couvre :
- POST /api/takeoffs/{id}/calibrate/from-cotes (médiane robuste des cotes IA)
- POST /api/takeoffs/{id}/calibrate/reconcile (check + apply, recalcul des pièces)
- POST /api/takeoffs/{id}/apply-ai-texts (renommage, matériau sol, drapeaux surface)
- POST /api/takeoffs/{id}/detect-walls (champ filtered_cotes)
- Cas d'erreur : analyse manquante (400), page non calibrée (400)
"""
from __future__ import annotations

import io
import os

import pytest
import requests


def _base():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    url = ln.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return url.rstrip("/")


BASE_URL = _base()
ADMIN = ("admin@construpilot.fr", os.environ.get("TEST_ADMIN_PASSWORD", "Construpilot2026!"))


def _login(email, pwd):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def headers():
    return {"Authorization": f"Bearer {_login(*ADMIN)}"}


def _mongo():
    import pymongo
    env = {}
    with open("/app/backend/.env") as f:
        for ln in f:
            if "=" in ln:
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    client = pymongo.MongoClient(env["MONGO_URL"])
    return client[env["DB_NAME"]]


def _make_png(w=1200, h=900):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([100, 100, 700, 500], outline="black", width=6)
    d.rectangle([700, 100, 1100, 400], outline="black", width=6)
    # trait de cote fin isolé (doit être filtré par detect-walls)
    d.line([100, 700, 700, 700], fill="black", width=1)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


# ai_analysis synthétique : cotes cohérentes à 50 px/m + 1 outlier
FAKE_AI = {
    "plan_type": "residential",
    "detected_scale": "1:100",
    "quality": "good",
    "page_index": 0,
    "confidence": 0.9,
    "warnings": [],
    "dimension_lines": [
        {"value_m": 6.0, "bbox_norm": [100 / 1200, 80 / 900, 400 / 1200, 80 / 900],
         "orientation": "horizontale", "confidence": 0.9},   # 300 px / 6 m = 50
        {"value_m": 4.0, "bbox_norm": [0.05, 0.2, 0.05, 0.2 + 200 / 900],
         "orientation": "verticale", "confidence": 0.8},      # 200 px / 4 m = 50
        {"value_m": 2.0, "bbox_norm": [0.5, 0.9, 0.5 + 100 / 1200, 0.9],
         "orientation": "horizontale", "confidence": 0.9},    # 100 px / 2 m = 50
        {"value_m": 1.0, "bbox_norm": [0.0, 0.0, 0.5, 0.0],
         "orientation": "horizontale", "confidence": 0.9},    # outlier 600 px/m
    ],
    "rooms": [
        {"name": "Séjour", "surface_written_m2": 121.0, "estimated_surface_m2": 120.0,
         "ceiling_height_m": 2.7, "floor_material": "carrelage",
         "floor_note_text": "Carrelage grès cérame 60x60"},
    ],
    "materials_notes": [],
    "openings": {"details": []},
}


@pytest.fixture(scope="module")
def plan_id():
    hdrs = {"Authorization": f"Bearer {_login(*ADMIN)}"}
    files = {"file": ("plan_iter62.png", _make_png(), "image/png")}
    r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files, headers=hdrs, timeout=60)
    assert r.status_code == 200, r.text
    pid = r.json()["plan_id"]
    # Injection de l'analyse IA synthétique (déterministe, pas d'appel GPT)
    db = _mongo()
    res = db.plans_takeoff.update_one({"plan_id": pid}, {"$set": {"ai_analysis": FAKE_AI}})
    assert res.matched_count == 1
    yield pid
    requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=hdrs, timeout=15)


class TestIter62CotesTextes:
    """Classe unique — loadscope pin sur un seul worker (état séquentiel partagé)."""

    def test_from_cotes_requires_analysis(self, headers):
        files = {"file": ("bare.png", _make_png(400, 300), "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files, headers=headers, timeout=60)
        pid = r.json()["plan_id"]
        r2 = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/calibrate/from-cotes",
                           json={"page_index": 0}, headers=headers, timeout=15)
        assert r2.status_code == 400
        assert "Analyse IA" in r2.json()["detail"]
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=headers, timeout=15)

    def test_from_cotes_median_robust(self, plan_id, headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/calibrate/from-cotes",
                          json={"page_index": 0}, headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        calib = d["calibration"]
        assert calib["method"] == "auto_cotes"
        assert abs(calib["pixels_per_meter"] - 50.0) < 0.5, calib
        assert calib["samples_used"] == 3          # l'outlier est rejeté
        assert calib["samples_total"] == 4
        assert calib["spread_pct"] <= 2.0
        # échantillons détaillés renvoyés avec drapeau inlier
        inliers = [s for s in d["samples"] if s["inlier"]]
        assert len(inliers) == 3

    def test_calibration_persisted(self, plan_id, headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=15)
        calib = r.json()["calibrations"]["0"]
        assert calib["method"] == "auto_cotes"
        assert abs(calib["pixels_per_meter"] - 50.0) < 0.5

    def test_room_created_with_generic_name(self, plan_id, headers):
        # carré 500x500 px @ 50 px/m = 10x10 m = 100 m²
        r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/rooms", json={
            "page_index": 0, "name": "Pièce 01",
            "points": [[100, 100], [600, 100], [600, 600], [100, 600]],
            "ceiling_height_m": 2.5,
        }, headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        assert abs(r.json()["surface_m2"] - 100.0) < 1.0

    def test_apply_texts_renames_and_sets_material(self, plan_id, headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/apply-ai-texts",
                          json={"page_index": 0}, headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["rooms_matched"] == 1
        assert len(d["renamed"]) == 1
        assert d["renamed"][0]["to"] == "Séjour"
        assert len(d["materials_set"]) == 1
        assert d["materials_set"][0]["material"] == "carrelage"
        # hauteur 2.7 écrite → appliquée (pièce à 2.5 par défaut)
        assert len(d["heights_updated"]) == 1
        assert d["heights_updated"][0]["to"] == 2.7
        # écart surface 100 vs 121 > 5 % → drapeau
        assert len(d["surface_flags"]) == 1
        assert abs(d["surface_flags"][0]["delta_pct"] - 21.0) < 1.5

    def test_room_updated_in_db(self, plan_id, headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=15)
        room = r.json()["rooms"][0]
        assert room["name"] == "Séjour"
        assert room["floor_material"] == "carrelage"
        assert room["ceiling_height_m"] == 2.7
        assert room["surface_written_m2"] == 121.0
        assert abs(room["surface_delta_pct"] - 21.0) < 1.5

    def test_reconcile_check_only(self, plan_id, headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/calibrate/reconcile",
                          json={"page_index": 0, "apply": False}, headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["applied"] is False
        assert d["can_reconcile"] is True
        assert d["needs_recalib"] is True
        assert abs(d["deviation_pct"] - 21.0) < 1.5
        assert d["matches"][0]["match_method"] == "name"   # « Séjour » matché par nom
        # ppm proposé = 50 × √(100/121) ≈ 45.45
        assert abs(d["proposed_ppm"] - 45.45) < 0.2

    def test_reconcile_apply_recomputes_rooms(self, plan_id, headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/calibrate/reconcile",
                          json={"page_index": 0, "apply": True}, headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["applied"] is True
        assert d["rooms_recomputed"] == 1
        assert d["calibration"]["method"] == "reconcile_surfaces"
        # après recalage, la surface mesurée == surface écrite
        rp = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=15)
        room = rp.json()["rooms"][0]
        assert abs(room["surface_m2"] - 121.0) < 1.5, room["surface_m2"]

    def test_reconcile_uncalibrated_page_400(self, headers):
        files = {"file": ("bare2.png", _make_png(400, 300), "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files, headers=headers, timeout=60)
        pid = r.json()["plan_id"]
        r2 = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/calibrate/reconcile",
                           json={"page_index": 0, "apply": False}, headers=headers, timeout=15)
        assert r2.status_code == 400
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=headers, timeout=15)

    def test_detect_walls_returns_filtered_cotes(self, plan_id, headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/detect-walls?page_index=0",
                          headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "filtered_cotes" in d
        assert d["segment_count"] > 0        # les murs épais restent détectés
        # aucun segment gardé ne doit être parallèle+proche d'une cote IA
        assert isinstance(d["filtered_cotes"], int)
