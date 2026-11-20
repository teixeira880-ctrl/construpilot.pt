"""20/11: o estudo é entregue SEM esperar por imagens; as imagens HD entram depois e o orçamento é refeito com elas."""
import asyncio
import base64

import pytest

from engines.bet_geo import run


def test_imagens_hd_depois_da_entrega(monkeypatch):
    mm = pytest.importorskip("mongomock_motor")
    from engines import quote_building as QB
    db = mm.AsyncMongoMockClient()["t"]
    stored = []

    async def store(db_, uid, cid, rid, kind, path, title):
        stored.append((kind, title))
        return {"kind": kind, "title": title}

    async def fake_views(db_, raw, wait=0):
        await db_.house_renders.insert_one({"key": QB.geometry_key(raw), "quality": "pbr", "views": {"main": base64.b64encode(b"x").decode()}})
        return {"main": b"\xff\xd8jpg", "side": b"\xff\xd8jpg"}
    monkeypatch.setattr(QB, "views", fake_views)
    exports = []

    async def fake_exports(doc_id, user, conv):
        exports.append(doc_id)
        return [{"kind": "quote_pdf", "title": "Orçamento (PDF)"}]
    import engines.assistant_quote_exports as AQ
    monkeypatch.setattr(AQ, "attach_quote_exports", fake_exports)

    async def go():
        await db.bet_study_jobs.insert_one({"job_id": "j", "artifacts": []})
        await db.pro_documents.insert_one({"doc_id": "q1", "user_id": "u", "doc_type": "quote", "source": "bet_study"})
        geo = {"footprint": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 8], [0, 8], [0, 0]]]}, "walls": [],
               "floor_level": 0, "roof_level": 3.2, "slab_h": 0.22}
        await run._late_images(db, "j", "u", "c", "r", geo, store, [{"kind": "pdf"}], "q1")
        return await db.bet_study_jobs.find_one({"job_id": "j"}), await db.pro_documents.find_one({"doc_id": "q1"})
    job, doc = asyncio.run(go())
    assert [k for k, _ in stored] == ["render_png", "render_png"] and exports == ["q1"]
    assert job["renders_status"] == "done" and len(job["artifacts"]) == 4 and doc["study_images_ready"] is True


def test_orcamento_do_estudo_nao_espera_pelas_imagens(monkeypatch):
    from engines import quote_building as QB
    monkeypatch.setenv("QUOTE_PHOTO_WAIT", "90")
    seen = {}

    async def fake_model(db, doc, uid):
        return {"_geo": {}}

    async def fake_views(db, raw, wait=0):
        seen["wait"] = wait
        return {}
    monkeypatch.setattr(QB, "model_for_quote", fake_model)
    monkeypatch.setattr(QB, "views", fake_views)

    async def fake_plans(db, doc, uid):
        return []
    monkeypatch.setattr(QB, "plan_images", fake_plans)
    monkeypatch.setenv("CP_3D_IMAGES", "1")
    asyncio.run(QB.enrich(None, {"doc_type": "quote", "source": "bet_study"}, "u", wait=40))
    assert seen["wait"] == 0
