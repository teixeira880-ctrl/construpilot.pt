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
    # cleanup inicial — scoped ao prefixo deste teste para não interferir
    # com outros testes paralelos (xdist loadfile corre múltiplos ficheiros).
    PREFIX_FILTER = {"$or": [
        {"user_email": {"$in": ["joao@example.com", "a@b.pt", "cliente@x.pt"]}},
    ]}
    await db[COLLECTION].delete_many(PREFIX_FILTER)
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

            # ─── Lista + filtros + pesquisa (scope restrito aos 3 kinds) ───
            # Em paralelo (xdist loadfile), outros testes podem co-habitar.
            # Filtramos pelos 3 kinds que inserimos.
            r = await c.get("/api/admin/activity?kind=contact&kind=quote&kind=permit",
                            headers=H)
            assert r.status_code == 200
            total_my = r.json()["total"]
            assert total_my >= 3  # pode haver seed concorrente de outros testes

            # Filtro específico aos nossos emails (via pesquisa textual exact)
            r = await c.get("/api/admin/activity?q=example.com", headers=H)
            assert r.json()["total"] >= 1  # joao@example.com

            r = await c.get("/api/admin/activity?kind=contact&q=example.com",
                            headers=H)
            assert r.json()["total"] >= 1

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

            # ─── Stats (contam agregadamente — não assert exacto) ───
            r = await c.get("/api/admin/activity/stats", headers=H)
            body = r.json()
            assert body["total"] >= 3
            assert body["by_kind"].get("contact", 0) >= 1
            assert body["by_kind"].get("quote", 0) >= 1
            assert body["by_kind"].get("permit", 0) >= 1
            assert body["by_state"].get("em_curso", 0) >= 1

            # ─── Export CSV (filtrado por kind para scope limitado) ───
            r = await c.get("/api/admin/activity/export?format=csv&kind=contact",
                            headers=H)
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/csv")
            assert r.content.startswith(b"\xef\xbb\xbf")
            assert b"joao@example.com" in r.content

            # ─── Export XLSX ───
            r = await c.get("/api/admin/activity/export?format=xlsx&kind=quote",
                            headers=H)
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
        # ─── AK.2 integração mínima: contact + permit no CRM lite ───
        # (inserido aqui porque motor+anyio é instável entre múltiplos
        # ficheiros no mesmo xdist worker — ver test_fase_d_portal_cliente)
        ak2 = uuid.uuid4().hex[:6]
        c_id = await record_activity(
            kind="contact",
            user_email=f"ak2_{ak2}_contact@test.pt",
            user_name="João AK2",
            summary="Pedido de muro em Lisboa",
            source_url="/api/leads",
            payload={"lead_id": "lead_x", "source": "landing"},
        )
        p_id = await record_activity(
            kind="permit",
            user_email=f"ak2_{ak2}_permit@test.pt",
            user_name="Maria AK2",
            summary="Dossier autorização obras — Sintra",
            source_url="/api/particulares/autorizacao/dossier/gerar",
            payload={"tipo_obra": "ampliacao", "concelho": "Sintra"},
        )
        assert c_id and p_id
        cdoc = await db[COLLECTION].find_one({"_id": ObjectId(c_id)})
        pdoc = await db[COLLECTION].find_one({"_id": ObjectId(p_id)})
        assert cdoc["kind"] == "contact"
        assert pdoc["payload"]["concelho"] == "Sintra"
        await db[COLLECTION].delete_many(
            {"user_email": {"$regex": f"^ak2_{ak2}"}})

        # ─── AK.4 integração: envio email mock PT + FR + rate-limit + opt-out ───
        from unittest.mock import AsyncMock, patch
        from datetime import datetime, timedelta, timezone
        from engines.activity_crm.email_notifications import maybe_send_state_email
        ak4_pref = f"ak4ak1_{uuid.uuid4().hex[:6]}_"

        async def _mk_act(email_suffix: str, **overrides):
            now_iso = datetime.now(timezone.utc).isoformat()
            doc = {
                "created_at": now_iso, "updated_at": now_iso,
                "kind": "contact",
                "user_email": f"{ak4_pref}{email_suffix}@test.pt",
                "user_name": overrides.get("user_name", "Cliente"),
                "user_phone": None, "summary": "Pediu orçamento",
                "payload": {}, "source_url": None,
                "attachments": [], "state": "novo", "assigned_to": None,
                "internal_notes": [], "state_history": [],
                "is_fr_project": overrides.get("is_fr_project", False),
                "no_email": overrides.get("no_email", False),
                "last_email_at": overrides.get("last_email_at"),
            }
            res = await db[COLLECTION].insert_one(doc)
            doc["_id"] = res.inserted_id
            return doc

        with patch("engines.emailer.send_email",
                   new=AsyncMock(return_value=None)) as mock_send:
            # PT em_curso → envia
            pt = await _mk_act("pt", user_name="João PT")
            out = await maybe_send_state_email(pt, new_state="em_curso")
            assert out["sent"] is True
            assert out["locale"] == "pt"
            assert "Olá João PT" in mock_send.await_args.args[2]

            # FR respondido → template FR
            mock_send.reset_mock()
            fr = await _mk_act("fr", user_name="Jean FR", is_fr_project=True)
            out = await maybe_send_state_email(
                fr, new_state="respondido", custom_text="Mur en pierre")
            assert out["sent"] is True
            assert out["locale"] == "fr"
            assert "Bonjour Jean FR" in mock_send.await_args.args[2]
            assert "répondu" in mock_send.await_args.args[1]

            # Rate-limit (2 min atrás)
            mock_send.reset_mock()
            recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
            rl = await _mk_act("rl", last_email_at=recent)
            out = await maybe_send_state_email(rl, new_state="em_curso")
            assert out["sent"] is False
            assert "rate-limit" in out["reason"]
            assert mock_send.await_count == 0

            # Opt-out
            opt = await _mk_act("opt", no_email=True)
            out = await maybe_send_state_email(opt, new_state="fechado")
            assert out["sent"] is False
            assert "opt-out" in out["reason"]

            # Estado 'novo' não notificável
            nv = await _mk_act("nv")
            out = await maybe_send_state_email(nv, new_state="novo")
            assert out["sent"] is False
            assert "não notificável" in out["reason"]

        await db[COLLECTION].delete_many(
            {"user_email": {"$regex": f"^{ak4_pref}"}})
    finally:
        await db[COLLECTION].delete_many(PREFIX_FILTER)
        await db.users.delete_many({"email": {"$in": list(emails.values())}})
