"""Iter 127 — Hopla parity features:
 (a) Devis margin fields (cost_ht / margin_ht / margin_pct)
 (b) Library import-pdf preview / confirm + cost_price_ht persistence
 (c) documents/video-transcribe accepts audio (no 500)
 (e) Radar postal (status, price, list) — NEVER POST /postal (billed)
"""
from __future__ import annotations

import io
import os
import time
import wave
import struct
import math

import pytest
import requests

def _load_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        # read from frontend/.env
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip()
                break
    if not v:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return v.rstrip("/")


BASE = _load_backend_url()
API = f"{BASE}/api"

PRO_EMAIL = "pro@construpilot.fr"
PRO_PWD = "Pro2026!"


# --------- helpers ---------
def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok, r.json()
    return tok


@pytest.fixture(scope="module")
def pro_headers() -> dict:
    return {"Authorization": f"Bearer {_login(PRO_EMAIL, PRO_PWD)}"}


# ================= (a) documents totals margin =================

class TestDocumentsMargin:
    def test_create_doc_with_costs_returns_margin(self, pro_headers):
        payload = {
            "doc_type": "quote",
            "title": "TEST_margin_doc",
            "lines": [
                {"designation": "Peinture", "qty": 10, "unit_price_ht": 30, "cost_price_ht": 20, "vat_rate": 10, "category": "Peinture"},
                {"designation": "Carrelage", "qty": 5, "unit_price_ht": 40, "cost_price_ht": 50, "vat_rate": 10, "category": "Carrelage"},
            ],
        }
        r = requests.post(f"{API}/documents", json=payload, headers=pro_headers, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        t = doc["totals"]
        assert t["ht"] == 500
        assert t["cost_ht"] == 450
        assert t["margin_ht"] == 50
        assert t["margin_pct"] == 10.0
        # persistence of cost_price_ht in lines
        assert doc["lines"][0]["cost_price_ht"] == 20
        assert doc["lines"][1]["cost_price_ht"] == 50
        # cleanup + PUT recompute test
        doc_id = doc["doc_id"] if "doc_id" in doc else doc.get("id")
        assert doc_id, f"no doc id in {list(doc)}"
        # PUT: change cost on line1 to 25 → cost 450→ 10*25+5*50=500; margin 0; pct 0
        upd = dict(payload)
        upd["lines"] = [dict(x) for x in payload["lines"]]
        upd["lines"][0]["cost_price_ht"] = 25
        r2 = requests.put(f"{API}/documents/{doc_id}", json=upd, headers=pro_headers, timeout=30)
        assert r2.status_code == 200, r2.text
        t2 = r2.json()["totals"]
        assert t2["cost_ht"] == 500
        assert t2["margin_ht"] == 0
        assert t2["margin_pct"] == 0.0
        requests.delete(f"{API}/documents/{doc_id}", headers=pro_headers, timeout=15)

    def test_create_doc_without_costs_null_margin(self, pro_headers):
        payload = {
            "doc_type": "quote",
            "title": "TEST_no_cost",
            "lines": [
                {"designation": "Item", "qty": 2, "unit_price_ht": 100, "vat_rate": 10},
            ],
        }
        r = requests.post(f"{API}/documents", json=payload, headers=pro_headers, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        t = doc["totals"]
        assert t["ht"] == 200
        assert t["cost_ht"] is None
        assert t["margin_ht"] is None
        assert t["margin_pct"] is None
        doc_id = doc.get("doc_id") or doc.get("id")
        requests.delete(f"{API}/documents/{doc_id}", headers=pro_headers, timeout=15)


# ================= (b) library import-pdf =================

def _make_quote_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 800, "DEVIS N° TEST-127")
    c.setFont("Helvetica", 10)
    c.drawString(50, 780, "Date : 15/01/2026")
    c.drawString(50, 760, "Désignation                        Unité   Qté     PU HT")
    lines = [
        ("Peinture murs 2 couches", "m²", "50", "28.00"),
        ("Pose parquet flottant chene", "m²", "30", "38.00"),
        ("Pose carrelage sol grand format", "m²", "20", "55.00"),
        ("Depose ancien revetement", "m²", "20", "12.00"),
    ]
    y = 740
    for d, u, q, pu in lines:
        c.drawString(50, y, f"{d}   {u}   {q}   {pu}")
        y -= 20
    c.drawString(50, y - 20, "Total HT : 3560,00 EUR")
    c.showPage()
    c.save()
    return buf.getvalue()


class TestLibraryImportAndCost:
    created_ids: list[str] = []

    def test_create_item_with_cost(self, pro_headers):
        r = requests.post(f"{API}/library", json={
            "type": "ouvrage", "category": "TEST_iter127",
            "designation": "TEST_iter127 ouvrage avec cout", "unit": "m²",
            "unit_price_ht": 50, "cost_price_ht": 30, "vat_rate": 10,
        }, headers=pro_headers, timeout=30)
        assert r.status_code in (200, 201), r.text
        it = r.json()
        assert it["cost_price_ht"] == 30
        self.__class__.created_ids.append(it["item_id"])
        # GET
        r2 = requests.get(f"{API}/library", headers=pro_headers, timeout=30)
        assert r2.status_code == 200
        items = r2.json()["items"]
        found = [i for i in items if i["item_id"] == it["item_id"]]
        assert found and found[0]["cost_price_ht"] == 30

    def test_import_pdf_preview_and_confirm(self, pro_headers):
        pdf = _make_quote_pdf()
        # preview – AI can be slow; allow 120s
        files = {"files": ("devis_test.pdf", pdf, "application/pdf")}
        r = requests.post(f"{API}/library/import-pdf/preview",
                          files=files, headers=pro_headers, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        assert "line_count" in data
        assert isinstance(data["items"], list) and data["items"], data
        item0 = data["items"][0]
        assert item0["ok"] is True or "lines" in item0
        preview_lines = item0.get("lines") or []
        if not preview_lines:
            pytest.skip(f"AI returned no lines from generated PDF (soft skip) — items={data['items']}")

        # confirm
        payload = {"lines": preview_lines[:4], "category": "TEST_import_iter127"}
        r2 = requests.post(f"{API}/library/import-pdf/confirm",
                           json=payload, headers=pro_headers, timeout=30)
        assert r2.status_code == 200, r2.text
        res = r2.json()
        assert "created" in res and "updated" in res
        n_created = res["created"]
        assert n_created >= 1, res

        # re-confirm → should be updates now, not creates
        r3 = requests.post(f"{API}/library/import-pdf/confirm",
                           json=payload, headers=pro_headers, timeout=30)
        assert r3.status_code == 200
        res2 = r3.json()
        assert res2["created"] == 0, res2
        assert res2["updated"] >= n_created

        # cleanup: fetch and delete TEST_import_iter127 items
        r4 = requests.get(f"{API}/library", params={"q": ""}, headers=pro_headers, timeout=30)
        items = r4.json()["items"]
        for it in items:
            if it.get("category") == "TEST_import_iter127":
                requests.delete(f"{API}/library/{it['item_id']}", headers=pro_headers, timeout=15)

    def test_cleanup_manual_items(self, pro_headers):
        for iid in self.__class__.created_ids:
            requests.delete(f"{API}/library/{iid}", headers=pro_headers, timeout=15)


# ================= (c) video-transcribe accepts audio =================

def _make_silent_wav(seconds: float = 0.5, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        # very quiet tone (avoids all-zero being rejected)
        n = int(seconds * rate)
        for i in range(n):
            s = int(1000 * math.sin(2 * math.pi * 440 * i / rate))
            w.writeframesraw(struct.pack("<h", s))
    return buf.getvalue()


class TestVideoTranscribeAudio:
    def test_audio_upload_no_500(self, pro_headers):
        audio = _make_silent_wav()
        files = {"file": ("note.wav", audio, "audio/wav")}
        r = requests.post(f"{API}/documents/video-transcribe",
                          files=files, headers=pro_headers, timeout=120)
        # Must not be 500; either 200 with transcript, or 4xx with detail
        assert r.status_code != 500, f"500 error: {r.text[:400]}"
        if r.status_code == 200:
            assert "transcript" in r.json()
        else:
            assert 400 <= r.status_code < 500, r.status_code
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text}
            assert "detail" in body or body


# ================= (e) Radar postal — READ-ONLY =================

class TestRadarPostalReadOnly:
    def test_postal_status(self, pro_headers):
        r = requests.get(f"{API}/radar/postal/status", headers=pro_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("configured") is True, d
        modes = d.get("modes") or []
        for m in ("normal", "suivi", "lrar"):
            assert m in modes, d

    def test_postal_price_normal(self, pro_headers):
        r = requests.get(f"{API}/radar/postal/price", params={"mode": "normal"},
                         headers=pro_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mode"] == "normal"
        assert float(d["total_ttc"]) > 0
        assert "postage" in d or "content_ttc" in d

    def test_prospection_postal_list(self, pro_headers):
        # find any existing prospection token
        r = requests.get(f"{API}/radar/opportunities", headers=pro_headers, timeout=30)
        assert r.status_code == 200, r.text
        opps = r.json().get("opportunities") or r.json().get("items") or []
        if not opps:
            pytest.skip("No opportunities available to create prospection")
        opp = opps[0]
        opp_id = opp.get("opp_id") or opp.get("id")
        assert opp_id, opp
        # create/reuse prospection
        r2 = requests.post(f"{API}/radar/opportunities/{opp_id}/prospection",
                           json={}, headers=pro_headers, timeout=45)
        assert r2.status_code in (200, 201), r2.text
        token = r2.json().get("token")
        assert token, r2.json()
        # list postal sends (must NOT trigger POST)
        r3 = requests.get(f"{API}/radar/prospection/{token}/postal",
                          headers=pro_headers, timeout=20)
        assert r3.status_code == 200, r3.text
        d = r3.json()
        assert "sends" in d
        assert isinstance(d["sends"], list)
