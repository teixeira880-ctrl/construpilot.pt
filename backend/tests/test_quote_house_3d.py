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


# ---- geometria das fotos: só aceites se respeitarem 100 % a geometria calculada
def _case(name="moradia_pt_demo"):
    import json
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[1] / "engines/bet_core/cases" / f"{name}.json").read_text())


def test_geometry_lock_accepts_same_rejects_moved_windows():
    import copy
    from engines import geometry_lock as G
    from engines import house3d
    raw = _case()
    base, mask = house3d.render_png(raw, 1600, 900, "side"), house3d.render_png(raw, 1600, 900, "side", mask=True)
    assert G.check(base, base, mask)[1] >= G.threshold()
    moved = copy.deepcopy(raw)
    for o in moved["openings"]:
        w = o["to"] - o["from"]
        o["from"] += 1.2
        o["to"] = o["from"] + w
    assert G.check(house3d.render_png(moved, 1600, 900, "side"), base, mask)[1] < G.threshold()
    none = {**raw, "openings": []}
    assert G.check(house3d.render_png(none, 1600, 900, "side"), base, mask)[1] < G.threshold()


def test_pad_crop_roundtrip_keeps_box():
    from PIL import Image
    import io
    from engines import geometry_lock as G
    from engines import house3d
    base = house3d.render_png(_case(), 1600, 900, "main")
    p, box = G.pad(base, 1.5)
    W, H = Image.open(io.BytesIO(p)).size
    assert abs(W / H - 1.5) < 0.01 and box[2:] == (1600, 900)
    back = G.crop(p, (W, H), box)
    assert Image.open(io.BytesIO(back)).size == (1600, 900)


def test_photoreal_rejects_wrong_geometry_then_takes_next_engine(monkeypatch):
    import asyncio
    import copy
    from engines import geometry_lock as G
    from engines import house3d, image_studio, photoreal as PR
    raw = _case()
    base, mask = house3d.render_png(raw, 1600, 900, "main"), house3d.render_png(raw, 1600, 900, "main", mask=True)
    wrong = copy.deepcopy(raw)
    wrong["openings"] = []
    bad = house3d.render_png(wrong, 1600, 900, "main")

    async def fake_runway(model, prompt, refs, timeout):
        return bad                                    # motor que inventa a casa (sem vãos) → recusado

    async def fake_gen(**kw):
        return [(base, "image/png")]                  # motor que respeita a geometria → aceite
    monkeypatch.setattr(PR, "_runway", fake_runway)
    monkeypatch.setattr(image_studio, "generate", fake_gen)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = asyncio.run(PR.render(base, "x", engines=["openai", "gpt_image_2", "emergent"],
                              verify=lambda img: G.check(img, base, mask)))
    assert r and r[1] == "nano_banana_3.1"
    r2 = asyncio.run(PR.render(base, "x", engines=["gpt_image_2"], verify=lambda img: G.check(img, base, mask)))
    assert r2 is None                                 # nenhum motor respeitou → fica a vista calculada


def test_fast_pass_first_then_openai_upgrade(monkeypatch):
    """Como na conta CLT: o PDF recebe logo as fotos rápidas; a melhoria OpenAI substitui-as depois, em segundo plano."""
    import asyncio
    mm = __import__("pytest").importorskip("mongomock_motor")
    from engines import llm_keys, photoreal as PR
    from engines import quote_building as QB
    db = mm.AsyncMongoMockClient()["t"]
    raw = _case()
    calls = []

    async def fake_render(base, prompt, *, engines=None, verify=None, timeout=0, style_ref=None, **kw):
        calls.append(engines[0])
        if engines == ["openai"]:
            await asyncio.sleep(0.6)                   # OpenAI é lento
            return verify(base)[0], "openai_gpt_image"
        return verify(base)[0], "nano_banana_3.1"
    monkeypatch.setattr(PR, "render", fake_render)
    monkeypatch.setattr(llm_keys, "openai_direct_active", lambda: True)
    from engines import house3d
    monkeypatch.setattr(QB, "computed_views", lambda r: {k: QB._jpeg(house3d.render_png(r, 800, 450, k)) for k in QB.VIEW_KEYS})

    async def run():
        QB._PENDING.clear()
        v = await QB.views(db, raw, wait=0.4)
        first = (await db.house_renders.find_one({}, {"_id": 0}))["quality"]
        await asyncio.sleep(1.5)
        last = (await db.house_renders.find_one({}, {"_id": 0}))["quality"]
        return v, first, last
    v, first, last = asyncio.run(run())
    assert set(v) == set(QB.VIEW_KEYS) and first == "fast" and last == "openai"
    assert calls[0] == "emergent" and "openai" in calls


def test_openai_retries_without_input_fidelity(monkeypatch):
    """gpt-image-2 recusa input_fidelity: repete o MESMO modelo sem o parâmetro antes de passar ao seguinte."""
    import asyncio
    import base64
    import sys
    import types
    from engines import house3d, llm_keys, photoreal as PR
    base = house3d.render_png(_case(), 800, 450, "main")
    calls = []

    class Images:
        async def edit(self, **kw):
            calls.append((kw["model"], "input_fidelity" in kw))
            if "input_fidelity" in kw:
                raise Exception("The model 'gpt-image-2' does not support the 'input_fidelity' parameter.")
            return types.SimpleNamespace(data=[types.SimpleNamespace(b64_json=base64.b64encode(base).decode())])

    class Client:
        def __init__(self, **kw):
            self.images = Images()
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(AsyncOpenAI=Client))
    monkeypatch.setattr(llm_keys, "openai_direct_active", lambda: True)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("OPENAI_IMAGE_MODEL", raising=False)
    out = asyncio.run(PR._openai("x", base, None, 30))
    assert out and calls == [("gpt-image-2", True), ("gpt-image-2", False)]
