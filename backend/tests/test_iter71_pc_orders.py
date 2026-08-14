"""Iter71 — Étude PC : bon de commande fournisseur + notification ouverture + historique."""
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


class TestPurchaseOrder:
    def test_order_items_engine(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from engines.pc_study import (build_purchase_order_items,
                                      compute_levels_breakdown)
        i = {"perimeter_m": 34.0, "refends_m": 8.0, "levels": 2, "wall_height_m": 2.5,
             "ground_floor_area_m2": 70.0, "upper_floors_area_m2": 50.0,
             "openings_count": 14, "avg_opening_width_m": 1.2,
             "openings_area_m2": 24.0, "stairs_count": 1}
        lb = compute_levels_breakdown(i)
        items = build_purchase_order_items(lb[1])  # RDC
        names = [it["designation"] for it in items]
        assert any("Briques isobrique" in n for n in names)
        assert any("Colle" in n for n in names)
        assert any("Treillis" in n for n in names)
        # +5 % de chutes : la qty commandée > qty brute
        beton = [it for it in items if "dalle" in it["designation"].lower()][0]
        assert beton["qty"] >= lb[1]["lines"][0]["qty"]
        # fouilles jamais commandées (pas un matériau)
        assert not any("Fouilles" in n for n in names)

    def test_order_pdf_download(self, pro_headers):
        r = requests.get(
            f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/purchase-order?level=1&supplier=Test",
            headers=pro_headers, timeout=60)
        assert r.status_code == 200 and r.content[:4] == b"%PDF"

    def test_order_bad_level_400(self, pro_headers):
        r = requests.get(
            f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/purchase-order?level=9",
            headers=pro_headers, timeout=30)
        assert r.status_code == 400

    def test_order_send_validation(self, pro_headers):
        r = requests.post(
            f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/purchase-order/send",
            json={"level_index": 1, "supplier_email": "pas-un-email"},
            headers=pro_headers, timeout=30)
        assert r.status_code == 422

    def test_order_send_recorded_in_history(self, pro_headers):
        # Un envoi réel a déjà été fait vers delivered@resend.dev (sink)
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}",
                         headers=pro_headers, timeout=30)
        reports = r.json().get("sent_reports") or []
        po = [s for s in reports if s.get("kind") == "purchase_order"]
        assert po and po[-1].get("ref", "").startswith("BC-")


class TestPcHistory:
    def test_history_versions_after_recompute(self, pro_headers):
        r0 = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/history",
                          headers=pro_headers, timeout=30)
        n0 = len(r0.json()["history"])
        r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/recompute",
                          headers=pro_headers, timeout=30)
        assert r.status_code == 200
        r1 = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/history",
                          headers=pro_headers, timeout=30)
        h = r1.json()["history"]
        assert len(h) == min(n0 + 1, 20)  # l'endpoint plafonne à 20 versions
        assert h[0]["source"] in ("analyse", "recalcul")
        assert h[0]["ttc"] and h[0]["beton_m3"]

    def test_history_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/history",
                         timeout=30)
        assert r.status_code in (401, 403)


class TestOpenNotification:
    def test_notify_settings_roundtrip(self, pro_headers):
        r = requests.put(f"{BASE_URL}/api/pc/settings",
                         json={"notify_on_open": "both",
                               "notify_phone": "+33612345678"},
                         headers=pro_headers, timeout=30)
        assert r.status_code == 200
        r = requests.get(f"{BASE_URL}/api/pc/settings", headers=pro_headers, timeout=30)
        s = r.json()["settings"]
        assert s["notify_on_open"] == "both"
        assert s["notify_phone"] == "+33612345678"
        assert r.json()["defaults"]["notify_on_open"] == "email"
        requests.delete(f"{BASE_URL}/api/pc/settings", headers=pro_headers, timeout=30)

    def test_notify_mode_validation(self, pro_headers):
        r = requests.put(f"{BASE_URL}/api/pc/settings",
                         json={"notify_on_open": "pigeon"},
                         headers=pro_headers, timeout=30)
        assert r.status_code == 422

    def test_pixel_still_200_with_notification(self, pro_headers):
        # le pixel ne doit jamais échouer même si la notif plante
        px = requests.get(f"{BASE_URL}/api/pc/track/pct_inconnu_notif", timeout=30)
        assert px.status_code == 200
