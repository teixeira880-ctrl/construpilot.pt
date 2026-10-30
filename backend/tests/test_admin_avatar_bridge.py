"""Ponte do avatar admin: chave do agente, só admins, escritas com confirmação, rotas proibidas."""
import asyncio
import os
import sys
import types

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_avatar_bridge")

import pytest  # noqa: E402
from fastapi import APIRouter, Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

import core.security as S  # noqa: E402
from routes import admin_avatar_bridge as B  # noqa: E402

KEY = "k" * 40
ADMIN = {"user_id": "user_admin0000001", "email": "admin@construpilot.pt", "name": "Admin", "role": "admin", "token_version": 0}
PRO = {"user_id": "user_pro000000001", "email": "pro@example.pt", "role": "user"}


@pytest.fixture
def env(monkeypatch):
    mdb = AsyncMongoMockClient()["t"]
    asyncio.get_event_loop_policy().get_event_loop().run_until_complete(mdb.users.insert_many([dict(ADMIN), dict(PRO)]))
    monkeypatch.setattr(B, "db", mdb)
    monkeypatch.setattr(S, "db", mdb)
    monkeypatch.setenv("AVATAR_AGENT_KEY", KEY)
    # app « site » mínima, vista pela ponte via `from server import app`
    site = FastAPI()
    r = APIRouter(prefix="/api")

    @r.get("/admin/stats", summary="Estatísticas admin")
    async def stats(user=Depends(S.admin_user)):
        return {"users": 2, "by": user["email"]}

    @r.post("/admin/notes", summary="Criar nota")
    async def note(user=Depends(S.admin_user)):
        return {"created": True}

    @r.delete("/admin/notes/{nid}", summary="Apagar nota")
    async def del_note(nid: str, user=Depends(S.admin_user)):
        return {"deleted": nid}

    @r.post("/ceo/email/draft")
    async def email_draft(user=Depends(S.admin_user)):
        return {"draft": True}

    @r.post("/ceo/email/{cid}/send")
    async def email_send(cid: str, user=Depends(S.admin_user)):
        return {"sent": cid}

    @r.post("/auth/change-password")
    async def pw():
        return {"changed": True}

    site.include_router(r)
    site.include_router(B.router, prefix="/api")
    mod = types.ModuleType("server")
    mod.app = site
    monkeypatch.setitem(sys.modules, "server", mod)
    return TestClient(site), mdb


H = {"X-Avatar-Agent-Key": KEY}
IDENT = "admin-" + ADMIN["user_id"][:24]


def test_wrong_key_and_non_admin_refused(env):
    c, _ = env
    assert c.get("/api/admin-avatar-bridge/whoami", params={"identity": IDENT}, headers={"X-Avatar-Agent-Key": "x"}).status_code == 401
    assert c.get("/api/admin-avatar-bridge/whoami", params={"identity": "admin-" + PRO["user_id"]}, headers=H).status_code == 403
    assert c.get("/api/admin-avatar-bridge/whoami", params={"identity": IDENT}, headers=H).json()["email"] == ADMIN["email"]


def test_read_runs_as_admin(env):
    c, _ = env
    r = c.post("/api/admin-avatar-bridge/call", headers=H, json={"identity": IDENT, "method": "GET", "path": "/api/admin/stats"}).json()
    assert r["ok"] and '"by": "admin@construpilot.pt"' in r["data"]


def test_ordinary_write_is_autonomous_and_logged(env):
    """Autonomia (31/10/2026): uma escrita comum segue sem confirmação, mas fica registada."""
    c, mdb = env
    for path in ("admin/notes", "/api/ceo/email/draft"):
        r = c.post("/api/admin-avatar-bridge/call", headers=H, json={"identity": IDENT, "method": "POST", "path": path, "summary": "teste"}).json()
        assert r["ok"] and r["status"] == 200, path
    logged = asyncio.get_event_loop_policy().get_event_loop().run_until_complete(mdb.avatar_actions.count_documents({}))
    assert logged == 2


def test_irreversible_or_external_write_needs_confirmation(env):
    c, mdb = env
    for method, path in (("DELETE", "/api/admin/notes/n1"), ("POST", "/api/ceo/email/c1/send")):
        body = {"identity": IDENT, "method": method, "path": path, "summary": "teste"}
        assert c.post("/api/admin-avatar-bridge/call", headers=H, json=body).json()["needs_confirmation"] is True, path
        r = c.post("/api/admin-avatar-bridge/call", headers=H, json={**body, "confirmed": True}).json()
        assert r["ok"] and r["status"] == 200, path
    assert B.needs_confirmation("PUT", "/api/admin/prices/k") and B.needs_confirmation("POST", "/api/faturas/f1/emitir")
    assert not B.needs_confirmation("POST", "/api/assistant/jobs") and not B.needs_confirmation("POST", "/api/devis")


def test_whoami_carries_platform_knowledge_and_overview(env):
    c, _ = env
    k = c.get("/api/admin-avatar-bridge/whoami", params={"identity": IDENT}, headers=H).json()["knowledge"]
    assert "/assistant" in k and "/admin/growth" in k and "assistant_answer_choices" in k
    o = c.get("/api/admin-avatar-bridge/overview", params={"identity": IDENT}, headers=H).json()
    assert o["ok"] and '"users": 2' in o["data"] and "indisponivel" in o["data"]


def test_blocked_routes(env):
    c, _ = env
    for path in ("/api/auth/change-password", "/api/admin/avatar/token", "/api/billing/checkout", "/api/trash/empty"):
        r = c.post("/api/admin-avatar-bridge/call", headers=H, json={"identity": IDENT, "method": "POST", "path": path, "confirmed": True})
        assert r.status_code == 403, path


def test_catalog_hides_blocked(env):
    c, _ = env
    paths = [x["path"] for x in c.get("/api/admin-avatar-bridge/catalog", params={"identity": IDENT}, headers=H).json()["routes"]]
    assert "/api/admin/stats" in paths and not any("auth" in p or "avatar-bridge" in p for p in paths)


def test_live_capabilities_follow_deployed_code():
    """O avatar aprende as novidades sem nova implementação: a lista vem do Assistente BTP implementado."""
    for k, v in {"STUDIES_MODEL_ANALYSIS": "test", "STUDIES_MODEL_LIGHT": "test"}.items():
        os.environ.setdefault(k, v)
    from engines.avatar_knowledge import live_capabilities
    txt = live_capabilities({"user_id": "u", "role": "admin", "account_type": "pro"})
    assert "check_plans_coherence" in txt and "ask_user_choices" in txt
