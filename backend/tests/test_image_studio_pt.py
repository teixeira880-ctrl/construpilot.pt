"""Estúdio de imagens IA (.pt): geração só a pedido, faixa «Ilustração IA não contratual» no ficheiro, referência de custo
única por pedido, encaminhamento Gemini com fotografia, limites — fornecedores IA e armazenamento simulados, sem Mongo."""
import asyncio
import base64
import io
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_image_studio_pt")
os.environ.setdefault("JWT_SECRET", "test")

from fake_mongo_pt import FakeDB  # noqa: E402

S = pytest.importorskip("routes.image_studio")
from fastapi import HTTPException  # noqa: E402
from PIL import Image  # noqa: E402

USER = {"user_id": "u_pro_1", "account_type": "pro"}


def run(coro):
    return asyncio.run(coro)


def _png(w=320, h=200, color=(120, 160, 200)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def env(monkeypatch):
    db, store, calls = FakeDB(), {}, []

    async def fake_generate(**kw):
        calls.append(kw)
        return [(_png(), "image/png")] * kw.get("number", 1)

    monkeypatch.setattr(S, "db", db)
    monkeypatch.setattr(S.image_studio, "generate", fake_generate)
    monkeypatch.setattr(S.obj, "put_object", lambda path, data, ct: store.__setitem__(path, (data, ct)) or {"path": path})
    monkeypatch.setattr(S.obj, "get_object", lambda path: store[path])
    monkeypatch.setattr(S.public_storage, "put_object", lambda path, data, ct: store.__setitem__(path, (data, ct)) or {"path": path})
    return db, store, calls


def test_generate_labels_the_image_and_meters_each_request_separately(env):
    db, store, calls = env
    out = run(S.generate_image(S.GenIn(prompt="Moradia térrea contemporânea ao pôr do sol"), user=USER))
    out2 = run(S.generate_image(S.GenIn(prompt="Fachada reabilitada em Lisboa", number=2), user=USER))
    assert out["ok"] and out["label"] == "Ilustração IA não contratual" and len(out2["images"]) == 2
    img = out["images"][0]
    assert img["illustrative"] is True and img["url"] == f"/image-studio/images/{img['image_id']}/conteudo"
    assert calls[0]["provider"] == "openai" and calls[0]["feature"] == "image_studio"
    assert "não contratual" in calls[0]["prompt"] and calls[0]["prompt"].startswith("Moradia térrea")
    assert calls[0]["session_id"] != calls[1]["session_id"]          # um evento de custo (engines.expenses) por pedido
    rec = db.studio_images.docs[0]
    assert rec["illustrative"] is True and rec["mime"] == "image/jpeg" and rec["prompt"] == "Moradia térrea contemporânea ao pôr do sol"
    data, ct = store[rec["storage_path"]]
    with Image.open(io.BytesIO(data)) as im:                           # faixa acrescentada por baixo da imagem
        assert ct == "image/jpeg" and im.size[0] == 320 and im.size[1] > 200
        assert im.convert("RGB").getpixel((5, im.size[1] - 3)) == (255, 255, 255)


def test_reference_photo_goes_to_gemini_and_is_validated(env):
    _db, _store, calls = env
    ref = "data:image/png;base64," + base64.b64encode(_png()).decode()
    out = run(S.generate_image(S.GenIn(prompt="Acrescente uma piscina", provider="openai", reference_image_b64=ref), user=USER))
    assert out["provider"] == "gemini" and calls[-1]["provider"] == "gemini" and len(calls[-1]["reference_images"]) == 1
    for bad, code in (("@@@", 422), (base64.b64encode(b"<html>not an image</html>").decode(), 415)):
        with pytest.raises(HTTPException) as e:
            run(S.generate_image(S.GenIn(prompt="x" * 5, reference_image_b64=bad), user=USER))
        assert e.value.status_code == code
    with pytest.raises(HTTPException) as e:
        run(S.generate_image(S.GenIn(prompt="abc", provider="midjourney"), user=USER))
    assert e.value.status_code == 422


def test_daily_cap_blocks_before_calling_the_provider(env, monkeypatch):
    _db, _store, calls = env
    monkeypatch.setattr(S, "MAX_PER_DAY", 2)
    run(S.generate_image(S.GenIn(prompt="imagem um"), user=USER))
    run(S.generate_image(S.GenIn(prompt="imagem dois"), user=USER))
    with pytest.raises(HTTPException) as e:
        run(S.generate_image(S.GenIn(prompt="imagem três"), user=USER))
    assert e.value.status_code == 429 and len(calls) == 2


def test_gallery_is_per_account_and_soft_deleted(env):
    db, _store, _calls = env
    img = run(S.generate_image(S.GenIn(prompt="Banner de obra"), user=USER))["images"][0]
    assert [i["image_id"] for i in run(S.list_images(user=USER))["images"]] == [img["image_id"]]
    assert run(S.list_images(user={"user_id": "outro"}))["images"] == []
    resp = run(S.get_image(img["image_id"], user=USER))
    assert resp.media_type == "image/jpeg" and "Ilustracao-IA-" in resp.headers["content-disposition"]
    with pytest.raises(HTTPException) as e:
        run(S.get_image(img["image_id"], user={"user_id": "outro"}))
    assert e.value.status_code == 404
    run(S.delete_image(img["image_id"], user=USER))
    assert run(S.list_images(user=USER))["images"] == [] and db.studio_images.docs[0]["is_deleted"] is True


def test_reuse_as_quote_header_and_public_page(env):
    db, store, _calls = env
    db.users.docs.append({"user_id": USER["user_id"], "showcase_photos": []})
    img = run(S.generate_image(S.GenIn(prompt="Render de moradia"), user=USER))["images"][0]
    assert run(S.use_image(img["image_id"], S.UseIn(target="quote_header"), user=USER))["ok"]
    assert db.users.docs[0]["brand_logo_b64"]
    out = run(S.use_image(img["image_id"], S.UseIn(target="public_page"), user=USER))
    photo = db.users.docs[0]["showcase_photos"][0]
    assert out["photo_id"] == photo["photo_id"] and photo["illustrative"] is True and photo["title"] == "Ilustração IA não contratual"
    assert photo["path"] in store
    db.users.docs[0]["showcase_photos"] = [{}] * S.MAX_SHOWCASE
    with pytest.raises(HTTPException) as e:
        run(S.use_image(img["image_id"], S.UseIn(target="public_page"), user=USER))
    assert e.value.status_code == 409


def test_router_is_reserved_to_pro_accounts():
    deps = [d.dependency for d in S.router.dependencies]
    assert deps and all(callable(d) for d in deps)
