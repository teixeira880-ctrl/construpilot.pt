"""AK.1 — Testes do CRM lite (modelo + API admin + helper record_activity).

Padrão do projecto: um só event loop por teste (motor+anyio incompatível com
múltiplos loops). Agrupamos todas as asserções API no fluxo completo.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import app  # noqa: E402  (carrega .env + regista rotas)
from httpx import ASGITransport, AsyncClient  # noqa: E402

from core.db import db  # noqa: E402
from engines.activity_crm.models import COLLECTION, mask_email  # noqa: E402
from engines.activity_crm.record import record_activity  # noqa: E402


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _seed_user(email: str, role: str = "user") -> str:
    from core.security import hash_password, new_user_id
    uid = new_user_id()
    await db.users.update_one(
        {"email": email},
        {"$set": {
            "user_id": uid, "email": email, "role": role, "active": True,
            "password_hash": hash_password("Teste#2026"),
            "token_version": 0, "email_verified": True, "name": "Teste AK1",
        }},
        upsert=True,
    )
    return uid


async def _login_token(c: AsyncClient, email: str) -> str:
    r = await c.post("/api/auth/login",
                     json={"email": email, "password": "Teste#2026"})
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("token") or body.get("access_token") or body.get("session_token")


# ─── Sync-only: utilitário ────────────────────────────────────────────────
def test_mask_email_variants():
    assert mask_email("joao.silva@domain.com") == "j***@domain.com"
    assert mask_email("") == "***"
    assert mask_email("invalid") == "***"


# ─── Fluxo completo (todas asserções num só event loop) ───────────────────
@pytest.mark.anyio
async def test_ak1_crm_lite_fluxo_completo():
    # cleanup inicial
    await db[COLLECTION].delete_many({})
    suffix = uuid.uuid4().hex[:6]
    emails = {
        "admin": f"adm_{suffix}@test.pt",
        "user": f"usr_{suffix}@test.pt",
    }
    await db.users.delete_many({"email": {"$in": list(emails.values())}})
    try:
        await _seed_user(emails["admin"], role="admin")
        await _seed_user(emails["user"], role="user")

        # ─── Helper record_activity ───
        oid_contact = await record_activity(
            kind="contact", user_email="joao@example.com",
            user_name="João", summary="Pediu orçamento para muro de 20m",
            source_url="/contactos", payload={"origem": "landing"},
        )
        assert oid_contact
        doc = await db[COLLECTION].find_one({"_id": ObjectId(oid_contact)})
        assert doc["kind"] == "contact"
        assert doc["state"] == "novo"
        assert doc["summary"].startswith("Pediu orçamento")
        assert "ext_id" in doc

        # Truncate summary
        long_summary = "x" * 1000
        oid_long = await record_activity(
            kind="quote", user_email="a@b.pt", summary=long_summary)
        doc_long = await db[COLLECTION].find_one({"_id": ObjectId(oid_long)})
        assert len(doc_long["summary"]) <= 400

        # Fail-soft em email inválido
        bad = await record_activity(kind="contact", user_email="not-an-email",
                                    summary="x")
        assert bad is None

        # Mais seed para API
        oid_permit = await record_activity(
            kind="permit", user_email="cliente@x.pt", user_name="Cliente",
            summary="Pedido autorização obras", source_url="/autorizacao",
        )
        assert oid_permit

        async with _async_client() as c:
            # ─── Auth guards ───
            r = await c.get("/api/admin/activity")
            assert r.status_code in (401, 403)

            tok_user = await _login_token(c, emails["user"])
            r = await c.get("/api/admin/activity",
                            headers={"Authorization": f"Bearer {tok_user}"})
            assert r.status_code == 403, r.text

            tok_admin = await _login_token(c, emails["admin"])
            H = {"Authorization": f"Bearer {tok_admin}"}

            # ─── Lista + filtros + pesquisa ───
            r = await c.get("/api/admin/activity", headers=H)
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 3

            r = await c.get("/api/admin/activity?kind=contact", headers=H)
            assert r.json()["total"] == 1

            # Pesquisa case-insensitive
            r = await c.get("/api/admin/activity?q=AUTORIZA", headers=H)
            assert r.json()["total"] == 1

            # ─── Patch estado + histórico ───
            r = await c.patch(f"/api/admin/activity/{oid_contact}",
                              json={"state": "em_curso", "note": "a analisar"},
                              headers=H)
            assert r.status_code == 200, r.text
            patched = r.json()
            assert patched["state"] == "em_curso"
            assert len(patched["state_history"]) == 1
            assert patched["state_history"][0]["to"] == "em_curso"
            assert patched["state_history"][0]["from"] == "novo"
            assert patched["state_history"][0]["author"] == emails["admin"]

            # Nota solta via POST /notes
            r = await c.post(f"/api/admin/activity/{oid_contact}/notes",
                             json={"text": "cliente respondeu por email"},
                             headers=H)
            assert r.status_code == 200
            assert len(r.json()["internal_notes"]) == 1

            # Assigned_to
            r = await c.patch(f"/api/admin/activity/{oid_permit}",
                              json={"assigned_to": emails["admin"]},
                              headers=H)
            assert r.json()["assigned_to"] == emails["admin"]

            # ─── Stats ───
            r = await c.get("/api/admin/activity/stats", headers=H)
            body = r.json()
            assert body["total"] == 3
            assert body["by_kind"].get("contact") == 1
            assert body["by_kind"].get("quote") == 1
            assert body["by_kind"].get("permit") == 1
            # Depois do patch acima: 1 em_curso + 2 novos
            assert body["by_state"].get("novo") == 2
            assert body["by_state"].get("em_curso") == 1

            # ─── Export CSV ───
            r = await c.get("/api/admin/activity/export?format=csv", headers=H)
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/csv")
            assert r.content.startswith(b"\xef\xbb\xbf")
            assert b"joao@example.com" in r.content

            # ─── Export XLSX ───
            r = await c.get("/api/admin/activity/export?format=xlsx", headers=H)
            assert r.status_code == 200
            assert r.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            assert r.content[:2] == b"PK"

            # ─── GET single ───
            r = await c.get(f"/api/admin/activity/{oid_contact}", headers=H)
            assert r.status_code == 200
            assert r.json()["id"] == oid_contact

            # ─── 404 em id inexistente / 400 em id inválido ───
            r = await c.get("/api/admin/activity/not-an-oid", headers=H)
            assert r.status_code == 400
            r = await c.get(f"/api/admin/activity/{'0' * 24}", headers=H)
            assert r.status_code == 404

            # ─── Filtro inválido ───
            r = await c.get("/api/admin/activity?kind=hacker", headers=H)
            assert r.status_code == 400
    finally:
        await db[COLLECTION].delete_many({})
        await db.users.delete_many({"email": {"$in": list(emails.values())}})
