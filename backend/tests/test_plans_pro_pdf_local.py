"""Análise de planta Pro: PDF lido no servidor (sem Autodesk)."""
import asyncio
import base64
import types

import pymupdf
import pytest
from fastapi import HTTPException

from plans_pro import routes as R


def _pdf(pages=1, w=842, h=595):
    doc = pymupdf.open()
    for i in range(pages):
        p = doc.new_page(width=w, height=h)
        p.draw_rect(pymupdf.Rect(50, 50, w - 50, h - 50), width=3)
        p.insert_text((80, 90), f"RES-DO-CHAO {i + 1}", fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


class _Coll:
    def __init__(self, docs=None):
        self.docs = {d["job_id"]: d for d in (docs or [])}

    async def update_one(self, flt, upd):
        self.docs.setdefault(flt["job_id"], {"job_id": flt["job_id"]}).update(upd["$set"])

    async def find_one(self, flt, proj=None):
        d = self.docs.get(flt["job_id"])
        if d is None or (flt.get("user_id") and d.get("user_id") != flt["user_id"]):
            return None
        d = dict(d)
        for k, v in (proj or {}).items():
            if v == 0:
                d.pop(k, None)
        return d


def test_pdf_ne_demande_plus_autodesk():
    assert R._ACCEPT_MIME[".pdf"] == ("application/pdf", False)
    assert R._ACCEPT_MIME[".dwg"][1] is True


def test_rasterisation_premiere_page():
    png, pages = R.pdf_primeira_pagina_png(_pdf(pages=3))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and pages == 3
    pix = pymupdf.Pixmap(png)
    assert max(pix.width, pix.height) <= R.PDF_MAX_PX and max(pix.width, pix.height) >= 2000


def test_rasterisation_petit_pdf_plafonnee_a_300_dpi():
    png, _ = R.pdf_primeira_pagina_png(_pdf(w=200, h=100))
    pix = pymupdf.Pixmap(png)
    assert abs(pix.width - 200 * 300 / 72) <= 1   # 300 dpi, pas plus


def test_pdf_illisible_refuse():
    with pytest.raises(Exception):
        R.pdf_primeira_pagina_png(b"%PDF-1.4 pas un pdf")


def _run_pipeline(monkeypatch, data, vision_out):
    coll = _Coll([{"job_id": "j1", "user_id": "u"}])
    monkeypatch.setattr(R, "db", types.SimpleNamespace(plans_pro_jobs=coll))
    vus = {}

    async def fake_vision(*, image_bytes, image_mime, **_):
        vus["png"], vus["mime"] = image_bytes, image_mime
        return dict(vision_out)

    async def no_autodesk(*a, **k):
        raise AssertionError("O Autodesk não deve ser chamado para um PDF")

    monkeypatch.setattr(R.vision_cascade, "analyze_plan_image", fake_vision)
    monkeypatch.setattr(R.autodesk_pipeline, "extract_full", no_autodesk)
    asyncio.run(R._pipeline("j1", data, "plan.pdf", ".pdf", False, "u"))
    return coll, vus


def test_pipeline_pdf_sans_autodesk(monkeypatch):
    coll, vus = _run_pipeline(monkeypatch, _pdf(pages=2), {"ok": True, "status": "ok", "elements": [], "warnings": []})
    doc = coll.docs["j1"]
    assert vus["mime"] == "image/png" and vus["png"][:4] == b"\x89PNG"
    assert doc["status"] == "done" and doc["pdf_pages"] == 2
    assert doc["vision"]["source"] == "pdf_page_1"
    assert any("2 páginas" in w for w in doc["vision"]["warnings"])
    assert doc["checks"][0].startswith("Leitura do PDF")
    assert doc["preview"].startswith("data:image/png;base64,")
    # l'aperçu n'est pas renvoyé à chaque interrogation, seulement dans le résultat
    st = asyncio.run(R.job_status("j1", user={"user_id": "u"}))
    assert "preview" not in st
    res = asyncio.run(R.job_result("j1", user={"user_id": "u"}))
    assert res["pdf"]["pages"] == 2 and res["pdf"]["preview"] == doc["preview"] and res["autodesk"] is None


def test_pipeline_pdf_endommage(monkeypatch):
    coll, vus = _run_pipeline(monkeypatch, b"%PDF-1.4 casse", {"ok": True})
    doc = coll.docs["j1"]
    assert doc["status"] == "failed" and "PDF ilegível" in doc["error"] and not vus

