"""Orçamento de moradia: perspetivas 3D com a geometria real + paredes calculadas pelo motor de paredes da conta CLT."""
import asyncio
import json
from pathlib import Path

import pymupdf
import pytest

from engines import house3d
from engines import quote_building as QB
from engines.pdf_docs import build_document_pdf

CASES = Path(__file__).parents[1] / "engines/bet_core/cases"


def _raw(name="moradia_pt_demo.json"):
    return json.loads((CASES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", ["moradia_pt_demo.json", "la_courneuve.json", "saint_denis.json"])
def test_takeoff_crosschecks_and_renders(case):
    raw = _raw(case)
    floors = [f for f in house3d.takeoff(raw) if not f.get("error")]
    assert floors
    for f in floors:
        assert f["check"]["passed"] and f["net_m2"] > 0 and abs(f["union_m"] - f["pieces_m"]) / f["pieces_m"] < 0.02
    for v in house3d.VIEWS:
        assert house3d.render_png(raw, 320, 200, v)[:4] == b"\x89PNG"
    assert house3d.plan_png(raw, floors[0], 400)[:4] == b"\x89PNG"
    assert house3d.cutaway_png(raw, floors[0], 400, 260)[:4] == b"\x89PNG"


def test_quote_pdf_has_3d_cover_perspectives_and_walls():
    raw = _raw()
    doc = {"doc_type": "quote", "title": "Moradia", "lines": [{"designation": "Alvenaria", "unit": "m2", "qty": 10, "unit_price_ht": 40, "vat_rate": 23}],
           "totals": {"ht": 400, "tva_breakdown": {"23": 92}, "ttc": 492}, "_building_model": raw, "_house_views": QB.computed_views(raw)}
    d = pymupdf.open(stream=build_document_pdf(doc, branding={"company_name": "X", "country": "PT"}, lang="pt"), filetype="pdf")
    txt = "".join(p.get_text() for p in d)
    assert "Perspetivas do projeto" in txt and "Paredes calculadas" in txt and "Verificação" in txt and "conforme" in txt
    assert d[0].get_images()                                           # capa com a imagem da moradia
    plain = pymupdf.open(stream=build_document_pdf({k: v for k, v in doc.items() if not k.startswith("_")}, branding={"company_name": "X"}, lang="pt"),
                         filetype="pdf")
    assert "Paredes calculadas" not in "".join(p.get_text() for p in plain)


def test_model_found_from_conversation_and_views_cached(monkeypatch):
    mm = pytest.importorskip("mongomock_motor")
    db = mm.AsyncMongoMockClient()["t"]
    raw = _raw()
    monkeypatch.setattr(QB, "_photoreal_all", lambda *a, **k: asyncio.sleep(0))

    async def run():
        await db.bet_study_jobs.insert_one({"user_id": "u1", "conversation_id": "c1", "model": raw, "created_at": "2026-11-11"})
        doc = {"doc_type": "quote", "assistant_conversation_id": "c1", "lines": []}
        out = await QB.enrich(db, doc, "u1")
        none = await QB.enrich(db, {"doc_type": "quote", "assistant_conversation_id": "zz", "lines": []}, "u1")
        return out, none
    out, none = asyncio.run(run())
    assert out["_building_model"]["envelope"] == raw["envelope"] and "main" in out["_house_views"] and "cut_0" in out["_house_views"]
    assert "_building_model" not in none
