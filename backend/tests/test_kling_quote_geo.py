"""Kling AI no orçamento: imagem real a partir da GEOMETRIA REAL (bet_geo), só aceite se respeitar a geometria."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from shapely.geometry import Polygon  # noqa: E402

from engines import kling_client as K  # noqa: E402
from engines.bet_geo import structure, views as GV  # noqa: E402
from engines.bet_geo.model import Building, Wall  # noqa: E402

L_SHAPE = Polygon([(0, 0), (14, 0), (14, 6), (6, 6), (6, 12), (0, 12)])


def _house() -> Building:
    cs = list(L_SHAPE.exterior.coords)
    walls = []
    for (a, b) in zip(cs, cs[1:]):                      # fachadas com um vão de 3 m a meio de cada uma > 6 m
        seg = __import__("shapely.geometry", fromlist=["LineString"]).LineString([a, b])
        if seg.length > 6:
            p1, p2 = seg.interpolate(seg.length / 2 - 1.5), seg.interpolate(seg.length / 2 + 1.5)
            walls += [Wall(a, (p1.x, p1.y), 0.25, exterior=True), Wall((p2.x, p2.y), b, 0.25, exterior=True)]
        else:
            walls.append(Wall(a, b, 0.25, exterior=True))
    b = Building(footprint=L_SHAPE, walls=walls, covered=[Polygon([(0, -1), (14, -1), (14, 0), (0, 0)])])
    b.floor_level, b.roof_level = 0.0, 3.3
    return b


def _png(w=640, h=360, color=(120, 130, 140)) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


# ----------------------------------------------------------------------------- cliente Kling
def test_sem_chaves_nao_configurado(monkeypatch):
    for v in ("KLING_API_KEY", "KLING_ACCESS_KEY", "KLING_SECRET_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert not K.configured()
    assert asyncio.run(K.render("x", _png())) is None


def test_autenticacao_api_key_e_jwt(monkeypatch):
    import jwt
    monkeypatch.setenv("KLING_API_KEY", "kk-123")
    assert K._auth() == "Bearer kk-123"
    monkeypatch.delenv("KLING_API_KEY")
    monkeypatch.setenv("KLING_ACCESS_KEY", "AK")
    monkeypatch.setenv("KLING_SECRET_KEY", "SK")
    tok = K._auth().split(" ", 1)[1]
    claims = jwt.decode(tok, "SK", algorithms=["HS256"])
    assert claims["iss"] == "AK" and claims["exp"] - claims["nbf"] == 1805


@pytest.mark.parametrize("model,path,key", [("kling-v3-omni", "/v1/images/omni-image", "image_list"),
                                            ("kling-4.0", "/image-generation/kling-4.0", "contents"),
                                            ("kling-v2-1", "/v1/images/generations", "image")])
def test_pedido_por_modelo(model, path, key):
    p, body, q = K._request(model, "prompt", _png(1600, 900), None)
    assert p == path and key in body and "{id}" in q
    raw = json.dumps(body)
    assert "data:image" not in raw                      # Kling exige base64 sem prefixo
    if model == "kling-v2-1":
        assert body["image_fidelity"] == 1.0
    assert ("16:9" in raw)


def _mock(states, fmt="old"):
    seen = {"auth": [], "create": None}
    img = _png(1600, 900, (200, 190, 180))

    def handler(req: httpx.Request):
        seen["auth"].append(req.headers.get("authorization"))
        if req.method == "POST":
            seen["create"] = json.loads(req.content)
            return httpx.Response(200, json={"code": 0, "data": {"task_id": "t1", "task_status": "submitted"}})
        if req.url.path.endswith(".png"):
            return httpx.Response(200, content=img)
        st = states.pop(0) if states else "succeed"
        if fmt == "new":
            return httpx.Response(200, json={"code": 0, "data": [{"id": "t1", "status": "succeeded" if st == "succeed" else st,
                                                                     "outputs": [{"type": "image", "url": "https://cdn.x/r.png"}]}]})
        return httpx.Response(200, json={"code": 0, "data": {"task_id": "t1", "task_status": st,
                                                             "task_result": {"images": [{"index": 0, "url": "https://cdn.x/r.png"}]}}})
    return httpx.MockTransport(handler), seen, img


@pytest.mark.parametrize("model,fmt", [("kling-v3-omni", "old"), ("kling-4.0", "new")])
def test_tarefa_ate_imagem(monkeypatch, model, fmt):
    monkeypatch.setenv("KLING_API_KEY", "kk-123")
    tr, seen, img = _mock(["processing"], fmt)
    monkeypatch.setattr(K, "_TRANSPORT", tr)
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    out = asyncio.run(K.render("photo", _png(1600, 900), model=model, timeout=60))
    assert out == img and all(a == "Bearer kk-123" for a in seen["auth"][:2])


async def _fast_sleep(*_a, **_k):
    return None


def test_falha_devolve_none_sem_segredos_no_log(monkeypatch, caplog):
    monkeypatch.setenv("KLING_API_KEY", "segredo-xyz")

    def handler(req):
        return httpx.Response(401, json={"code": 1000, "message": "auth failed"})
    monkeypatch.setattr(K, "_TRANSPORT", httpx.MockTransport(handler))
    assert asyncio.run(K.render("x", _png())) is None
    assert "segredo-xyz" not in caplog.text


# ----------------------------------------------------------------------------- geometria real → vistas → controlo
def test_vistas_e_mascaras_da_geometria_real():
    b = _house()
    fs = GV.faces(b)
    kinds = {k for _, k, _ in fs}
    assert {"wall", "glass", "roof", "parapet"} <= kinds           # vãos lidos nos troços sem parede
    for v in GV.VIEWS:
        img, mask = GV.computed_and_mask(b, v, 800, 450)
        import cv2
        import numpy as np
        m = cv2.imdecode(np.frombuffer(mask, np.uint8), 0)
        assert (m == GV.GLASS_TONE).any() or v == "aerial"
        assert (m > 0).mean() > 0.02


def test_fachada_sem_paredes_lidas_fica_cega():
    b = Building(footprint=L_SHAPE, walls=[])
    assert not any(k == "glass" for _, k, _ in GV.faces(b))        # nunca inventar janelas


def test_kling_so_entra_se_respeitar_a_geometria(monkeypatch):
    from engines import geometry_lock as G
    from engines import image_hd
    from engines import photoreal as PR
    b = _house()
    base, mask = GV.computed_and_mask(b, "main", 800, 450)
    wrong, _ = GV.computed_and_mask(b, "rear", 800, 450)
    monkeypatch.setenv("KLING_API_KEY", "k")
    monkeypatch.setattr(image_hd, "sharpen", lambda d, m, long_side=0: (d, m))

    async def good(prompt, b_, style=None, timeout=0, model=None):
        return base
    async def bad(prompt, b_, style=None, timeout=0, model=None):
        return wrong
    monkeypatch.setattr(K, "render", good)
    r = asyncio.run(PR.render(base, "x", engines=["kling"], verify=lambda img: G.check(img, base, mask)))
    assert r and r[1] == "kling"
    calls = []

    async def bad_then_good(prompt, b_, style=None, timeout=0, model=None):
        calls.append(1)
        return wrong if len(calls) == 1 else base
    monkeypatch.setattr(K, "render", bad)
    assert asyncio.run(PR.render(base, "x", engines=["kling"], verify=lambda img: G.check(img, base, mask))) is None
    monkeypatch.setattr(K, "render", bad_then_good)                  # 1.ª foto falha o controlo → 2.ª tentativa aceite
    r = asyncio.run(PR.render(base, "x", engines=["kling"], verify=lambda img: G.check(img, base, mask)))
    assert r and len(calls) == 2


# ----------------------------------------------------------------------------- orçamento
def test_orcamento_com_geometria_real_e_foto_kling(monkeypatch):
    mm = pytest.importorskip("mongomock_motor")
    from engines import house_pbr, photoreal as PR
    from engines import quote_building as QB
    monkeypatch.setenv("QUOTE_HOUSE_PHOTO", "1")
    monkeypatch.setenv("QUOTE_PHOTO_AI", "1")
    monkeypatch.setenv("CP_3D_IMAGES", "1")
    monkeypatch.setenv("QUOTE_PHOTO_FAST", "kling")
    monkeypatch.setattr(house_pbr, "available", lambda: False)
    db = mm.AsyncMongoMockClient()["t"]
    b = _house()

    async def fake_render(base, prompt, *, engines=None, verify=None, timeout=0, style_ref=None, **kw):
        assert engines == ["kling"]
        aligned, sc = verify(base)
        return (aligned, "kling") if sc >= 0.62 else None
    monkeypatch.setattr(PR, "render", fake_render)

    async def run():
        QB._PENDING.clear()
        await db.bet_study_jobs.insert_one({"user_id": "u", "conversation_id": "c1", "created_at": "2026-11-19",
                                            "geo_building": {**b.to_dict(), "slab_h": 0.22}})
        doc = {"doc_type": "quote", "assistant_conversation_id": "c1", "lines": [], "title": "Moradia"}
        return await QB.enrich(db, doc, "u", wait=5)
    out = asyncio.run(run())
    assert out["_building_model"].get("_geo")
    assert set(out["_house_views"]) >= {"main", "side", "rear", "aerial"}
    assert out["_house_views_meta"].get("engine") == "kling" and out["_house_views_meta"].get("geometry_checked")
    # página do PDF com as imagens e a origem
    fl = GV.quote_flowables(out["_building_model"]["_geo"], out["_house_views"], out["_house_views_meta"], "#15803D", "pt")
    from reportlab.platypus import Paragraph
    txt = " ".join(p.text for p in fl if isinstance(p, Paragraph))
    assert "Kling" in txt and "verificada" in txt and "geometria real" in txt


def test_estudo_guarda_a_geometria_para_o_orcamento(tmp_path):
    from engines.bet_geo import run
    steps = []

    async def step(label, **extra):
        steps.append(extra)

    async def store(db, uid, cid, rid, kind, path, title):
        return {"kind": kind}

    async def fake_study(docs, hyp, country, out_dir, *, llm=None, meta=None, on_step=None, images_fn=None):
        from engines.bet_geo.rooms import Layout
        b = _house()
        R = structure.design(b)
        return {"ok": True, "building": b, "result": R, "checks_ok": True, "files": [], "layout": Layout(), "esp": {},
                "lines": [], "sheets": [],
                "summary": {"area": b.footprint.area, "area_util": 100.0, "slab_h": R.slab["h"], "pilares": 1, "vigas": 1,
                            "sapatas": 1, "muros": 0, "aco_kg": 1, "betao_m3": 1.0, "classe": None, "total_ht": 0.0,
                            "divisoes": 0, "vaos": 0}}
    orig = run.study
    run.study = fake_study
    try:
        assert asyncio.run(run.handle(None, "j", "u", "c", "r", [], "", "PT", step=step, store=store, llm=None))
    finally:
        run.study = orig
    geo = next(s for s in steps if "geo_building" in s)["geo_building"]
    assert Building.from_dict(geo).footprint.area == pytest.approx(L_SHAPE.area) and geo["slab_h"] > 0


def test_orcamento_sem_ia_usa_motores_internos_em_alta_definicao(monkeypatch):
    """Escolha do Martinho (19/11): sem Kling/IA — as 4 vistas do orçamento são a renderização física da geometria real."""
    mm = pytest.importorskip("mongomock_motor")
    from engines import house_pbr
    from engines import quote_building as QB
    monkeypatch.setenv("QUOTE_HOUSE_PHOTO", "1")
    monkeypatch.setenv("CP_3D_IMAGES", "1")
    monkeypatch.delenv("QUOTE_PHOTO_AI", raising=False)
    monkeypatch.setattr(house_pbr, "available", lambda: True)
    sizes = {}

    def fake_pbr(b, view, w, h, spp):
        sizes[view] = (w, h, spp)
        return GV.computed_and_mask(b, view, w // 4, h // 4)[0]
    monkeypatch.setattr(GV, "render_pbr", fake_pbr)
    db = mm.AsyncMongoMockClient()["t"]
    b = _house()

    async def run():
        QB._PENDING.clear()
        await db.bet_study_jobs.insert_one({"user_id": "u", "conversation_id": "c2", "created_at": "2026-11-19",
                                            "geo_building": {**b.to_dict(), "slab_h": 0.22}})
        return await QB.enrich(db, {"doc_type": "quote", "assistant_conversation_id": "c2", "lines": []}, "u", wait=10)
    out = asyncio.run(run())
    assert out["_house_views_meta"]["quality"] == "pbr" and set(out["_house_views"]) >= {"main", "side", "rear", "aerial"}
    assert sizes["main"][:2] == (2560, 1440) and sizes["side"][:2] == (1920, 1080)      # alta definição
    fl = GV.quote_flowables(out["_building_model"]["_geo"], out["_house_views"], out["_house_views_meta"])
    from reportlab.platypus import Paragraph
    assert "Renderização física (sem IA)" in " ".join(p.text for p in fl if isinstance(p, Paragraph))
