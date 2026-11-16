"""Conta Pro Business de demonstração LevelDesire (potencial cliente) : identidade, palavra-passe, plano, galeria."""
import asyncio

import bcrypt
import pytest

mm = pytest.importorskip("mongomock_motor")

from core import company_seeds as CS  # noqa: E402


def test_leveldesire_account_created(monkeypatch, tmp_path):
    monkeypatch.setenv("GRANT_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("LEVELDESIRE_TEMP_PASSWORD", "Segredo-so-de-teste-1")
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
        return s1, s2, await db.users.find_one({"email": "jorge.gois@leveldesire.com"}), await db.entitlements.count_documents({})
    s1, s2, u, ents = asyncio.run(run())
    assert "created" in s1["jorge.gois@leveldesire.com"] and "+pro_business" in s1["jorge.gois@leveldesire.com"]
    assert s2["jorge.gois@leveldesire.com"] == "exists"
    assert bcrypt.checkpw(b"Segredo-so-de-teste-1", u["password_hash"].encode()) and u["must_change_password"] is False
    assert u["account_type"] == "pro_business" and u["plan"] == "premium" and u["brand_accent_color"] == "#009B95"
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
    c = next(x for x in CS.COMPANIES if x["email"] == "jorge.gois@leveldesire.com")

    async def run():
        await db.users.insert_one({"user_id": "u1", "email": c["email"]})
        await CS._seed_photos(db, "u1", c)
        await CS._seed_photos(db, "u1", c)                                   # sem duplicados
        return await db.users.find_one({"user_id": "u1"})
    u = asyncio.run(run())
    assert len(u["showcase_photos"]) == 16 and len(stored) == 16 and u["company_photos_version"] == 1
    assert u["showcase_photos"][0]["title"] == "Moradia concluída — exterior"


def test_conta_info_renomeada_para_jorge(monkeypatch):
    """A conta existente info@leveldesire.com passa a jorge.gois@ (mesmo user_id, palavra-passe mantida, sem duplicado)."""
    async def fake_photos(db_, uid, c):
        return None
    monkeypatch.setattr(CS, "_seed_photos", fake_photos)
    db = mm.AsyncMongoMockClient()["t"]

    async def run():
        await db.users.insert_one({"user_id": "u9", "email": "info@leveldesire.com", "password_hash": "HASH-DA-EMPRESA",
                                   "temp_password_version": 1, "company_seed_version": 1, "plan": "premium"})
        s = await CS.apply_company_seeds(db, lambda: "novo", None)
        return s, await db.users.find({"email": {"$regex": "leveldesire"}}).to_list(10)
    s, users = asyncio.run(run())
    assert s["jorge.gois@leveldesire.com"].startswith("renamed_from:info@leveldesire.com")
    assert len(users) == 1 and users[0]["user_id"] == "u9" and users[0]["email"] == "jorge.gois@leveldesire.com"
    assert users[0]["password_hash"] == "HASH-DA-EMPRESA"


def test_leveldesire_sem_segredo_nao_ha_palavra_passe_no_codigo(monkeypatch, tmp_path):
    """Sem segredo configurado a conta é criada mas NÃO entra (nada de empreinte no código)."""
    monkeypatch.setenv("GRANT_SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("LEVELDESIRE_TEMP_PASSWORD", raising=False)
    db = mm.AsyncMongoMockClient()["t"]

    async def fake_photos(db_, uid, c):
        return None
    monkeypatch.setattr(CS, "_seed_photos", fake_photos)
    n = iter(range(100))
    asyncio.run(CS.apply_company_seeds(db, lambda: f"user_{next(n)}",
                                       lambda pw: bcrypt.hashpw(pw.encode(), bcrypt.gensalt(4)).decode()))
    u = asyncio.run(db.users.find_one({"email": "jorge.gois@leveldesire.com"}))
    assert not u.get("password_hash")
    assert "QoP5UI8T" not in open(CS.__file__, encoding="utf-8").read()
