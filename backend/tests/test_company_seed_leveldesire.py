"""Conta Pro Business de demonstração LevelDesire (potencial cliente) : identidade, palavra-passe, plano, galeria."""
import asyncio

import bcrypt
import pytest

mm = pytest.importorskip("mongomock_motor")

from core import company_seeds as CS  # noqa: E402


def test_leveldesire_account_created(monkeypatch):
    db = mm.AsyncMongoMockClient()["t"]
    photos = []

    async def fake_photos(db_, uid, c):
        photos.append((uid, len(c["photos"])))
    monkeypatch.setattr(CS, "_seed_photos", fake_photos)

    async def run():
        n = iter(range(100))
        s1 = await CS.apply_company_seeds(db, lambda: f"user_{next(n)}", lambda pw: bcrypt.hashpw(pw.encode(), bcrypt.gensalt(4)).decode())
        await asyncio.sleep(0)
        s2 = await CS.apply_company_seeds(db, lambda: f"user_{next(n)}", None)        # 2.º arranque: idempotente
        return s1, s2, await db.users.find_one({"email": "info@leveldesire.com"}), await db.entitlements.count_documents({})
    s1, s2, u, ents = asyncio.run(run())
    assert "created" in s1["info@leveldesire.com"] and "+pro_business" in s1["info@leveldesire.com"]
    assert s2["info@leveldesire.com"] == "exists"
    assert bcrypt.checkpw(b"Ruquinha2020", u["password_hash"].encode()) and u["must_change_password"] is False
    assert u["account_type"] == "pro_business" and u["brand_accent_color"] == "#009B95"
    assert u["public_slug"] == "leveldesire" and u["brand_logo_b64"].startswith("data:image/png;base64,")
    assert "Avenida João XXI" in u["brand_address"] and u["public_contact_phone"] == "+351 968 364 515"
    assert ents == 1 and photos and photos[0][1] == 16


def test_gallery_downloaded_once(monkeypatch):
    import io

    import httpx
    from PIL import Image

    from engines import storage
    db = mm.AsyncMongoMockClient()["t"]
    b = io.BytesIO()
    Image.effect_noise((828, 554), 40).convert("RGB").save(b, "JPEG")
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b.getvalue())), **kw))
    stored = []
    monkeypatch.setattr(storage, "put_object", lambda path, data, mime: stored.append(path) or {})
    c = next(x for x in CS.COMPANIES if x["email"] == "info@leveldesire.com")

    async def run():
        await db.users.insert_one({"user_id": "u1", "email": c["email"]})
        await CS._seed_photos(db, "u1", c)
        await CS._seed_photos(db, "u1", c)                                   # sem duplicados
        return await db.users.find_one({"user_id": "u1"})
    u = asyncio.run(run())
    assert len(u["showcase_photos"]) == 16 and len(stored) == 16 and u["company_photos_version"] == 1
    assert u["showcase_photos"][0]["title"] == "Moradia concluída — exterior"
