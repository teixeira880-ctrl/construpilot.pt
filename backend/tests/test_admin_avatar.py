"""Assistente de vídeo admin: token LiveKit reservado a admins, sem chamadas externas."""
import json
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_admin_avatar")

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core.security import admin_user, current_user  # noqa: E402
from routes import admin_avatar as A  # noqa: E402

LK = {"LIVEKIT_URL": "wss://demo.livekit.cloud", "LIVEKIT_API_KEY": "APIdemo",
      "LIVEKIT_API_SECRET": "s" * 40}


def make_client(user):
    app = FastAPI()
    app.include_router(A.router, prefix="/api")

    async def fake_current_user():
        if user is None:
            raise HTTPException(status_code=401, detail="Não autenticado")
        return user

    app.dependency_overrides[current_user] = fake_current_user
    return TestClient(app)


ADMIN = {"user_id": "u_admin_1", "email": "admin@construpilot.pt", "name": "Admin", "role": "admin"}
PRO = {"user_id": "u_pro_1", "email": "pro@example.pt", "role": "user"}


@pytest.fixture
def livekit_env(monkeypatch):
    for k, v in LK.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AVATAR_DEFAULT_LANG", raising=False)


def test_non_admin_is_refused(livekit_env):
    assert make_client(PRO).get("/api/admin/avatar/token").status_code == 403
    assert make_client(None).get("/api/admin/avatar/token").status_code == 401


def test_not_configured_returns_503(monkeypatch):
    for k in LK:
        monkeypatch.delenv(k, raising=False)
    c = make_client(ADMIN)
    assert c.get("/api/admin/avatar/status").json()["configured"] is False
    r = c.get("/api/admin/avatar/token")
    assert r.status_code == 503 and "LIVEKIT_URL" in r.json()["detail"]


@pytest.mark.parametrize("lang", ["fr", "pt"])
def test_admin_token_dispatches_agent_with_language(livekit_env, lang):
    r = make_client(ADMIN).get(f"/api/admin/avatar/token?lang={lang}")
    assert r.status_code == 200
    body = r.json()
    assert body["url"] == LK["LIVEKIT_URL"] and body["lang"] == lang
    claims = jwt.decode(body["token"], LK["LIVEKIT_API_SECRET"], algorithms=["HS256"])
    assert claims["iss"] == LK["LIVEKIT_API_KEY"]
    assert claims["video"]["roomJoin"] is True and claims["video"]["room"] == body["room"]
    assert body["room"].startswith(f"cp-admin-{lang}-")
    assert claims["exp"] - claims["nbf"] == 900
    cfg = claims["roomConfig"]
    assert cfg["syncStreams"] is True
    assert cfg["agents"] == [{"agentName": "construpilot-avatar",
                              "metadata": json.dumps({"lang": lang})}]
    # O segredo nunca é devolvido ao navegador.
    assert LK["LIVEKIT_API_SECRET"] not in r.text


def test_default_language_and_bad_language(livekit_env, monkeypatch):
    c = make_client(ADMIN)
    assert c.get("/api/admin/avatar/token").json()["lang"] == "pt"
    monkeypatch.setenv("AVATAR_DEFAULT_LANG", "fr")
    assert c.get("/api/admin/avatar/token").json()["lang"] == "fr"
    assert c.get("/api/admin/avatar/token?lang=es").status_code == 400


def test_route_uses_admin_dependency():
    deps = [d.dependency for d in A.router.dependencies]
    assert admin_user in deps
