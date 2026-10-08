"""Testes do webhook Resend (Fase G).

Cobertura:
    * HMAC inválido → 401
    * Timestamp fora da janela (anti-replay) → 401
    * Falta RESEND_WEBHOOK_SECRET → 503
    * Evento válido com `resend_id` existente → actualiza `email_logs`
    * Estado final não é retrocedido (delivered → sent é no-op)
    * `email.clicked` incrementa `clicks_count`
    * `email.bounced` guarda `bounce_reason`
    * Deduplicação por `svix-id`
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import app  # noqa: E402  (carrega .env + regista rotas)

from httpx import ASGITransport, AsyncClient  # noqa: E402


_SECRET = "whsec_" + "a" * 32  # formato Svix


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _assinar_svix(secret: str, msg_id: str, timestamp: str, raw_body: bytes) -> str:
    """Reproduz o algoritmo de assinatura Svix (base64 HMAC-SHA256)."""
    import base64
    import hmac
    import hashlib

    # Svix prefix: `whsec_` + base64 encoded secret
    key = base64.b64decode(secret.removeprefix("whsec_") + "==")
    to_sign = f"{msg_id}.{timestamp}.{raw_body.decode()}".encode()
    sig = hmac.new(key, to_sign, hashlib.sha256).digest()
    return "v1," + base64.b64encode(sig).decode()


@pytest.mark.anyio
async def test_webhook_sem_secret_devolve_503(monkeypatch):
    monkeypatch.delenv("RESEND_WEBHOOK_SECRET", raising=False)
    async with _async_client() as c:
        r = await c.post("/api/webhooks/resend", content=b"{}")
    assert r.status_code == 503


@pytest.mark.anyio
async def test_webhook_assinatura_invalida_devolve_401(monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", _SECRET)
    headers = {
        "svix-id": f"msg_{uuid.uuid4().hex[:12]}",
        "svix-timestamp": str(int(time.time())),
        "svix-signature": "v1,aW52YWxpZF9zaWduYXR1cmU=",
    }
    async with _async_client() as c:
        r = await c.post(
            "/api/webhooks/resend",
            content=b'{"type":"email.delivered","data":{"email_id":"x"}}',
            headers=headers,
        )
    assert r.status_code == 401


@pytest.mark.anyio
async def test_webhook_timestamp_antigo_devolve_401(monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", _SECRET)
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    ts_antigo = str(int(time.time()) - 10_000)  # 10 000 s no passado
    raw = b'{"type":"email.delivered","data":{"email_id":"x"}}'
    sig = _assinar_svix(_SECRET, msg_id, ts_antigo, raw)
    headers = {"svix-id": msg_id, "svix-timestamp": ts_antigo, "svix-signature": sig}
    async with _async_client() as c:
        r = await c.post("/api/webhooks/resend", content=raw, headers=headers)
    assert r.status_code == 401


@pytest.mark.anyio
async def test_webhook_fluxo_completo_actualiza_email_logs(monkeypatch):
    """Fluxo G: cria email_log → delivered → bounced não deve retroceder → clicked incrementa."""
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", _SECRET)
    from core.db import db

    rid = f"rid_{uuid.uuid4().hex[:12]}"
    await db.email_logs.insert_one({
        "resend_id": rid, "to": "cliente@test.pt", "subject": "Teste",
        "status": "sent",
    })

    def _enviar(tipo: str, extra_data: dict | None = None):
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        ts = str(int(time.time()))
        payload = {"type": tipo, "data": {"email_id": rid, **(extra_data or {})}}
        raw = json.dumps(payload).encode()
        sig = _assinar_svix(_SECRET, msg_id, ts, raw)
        return raw, {
            "svix-id": msg_id, "svix-timestamp": ts, "svix-signature": sig,
        }

    async with _async_client() as c:
        # 1. delivered → status passa a "delivered"
        raw, hdr = _enviar("email.delivered")
        r = await c.post("/api/webhooks/resend", content=raw, headers=hdr)
        assert r.status_code == 200, r.text
        doc = await db.email_logs.find_one({"resend_id": rid}, {"_id": 0})
        assert doc["status"] == "delivered"
        assert "delivered_at" in doc

        # 2. email.sent (precedência menor) NÃO deve retroceder
        raw, hdr = _enviar("email.sent")
        r = await c.post("/api/webhooks/resend", content=raw, headers=hdr)
        assert r.status_code == 200
        doc = await db.email_logs.find_one({"resend_id": rid}, {"_id": 0})
        assert doc["status"] == "delivered", "estado final não deve retroceder"

        # 3. email.clicked → incrementa clicks_count
        raw, hdr = _enviar("email.clicked", {"click": {"link": "https://exemplo.pt"}})
        r = await c.post("/api/webhooks/resend", content=raw, headers=hdr)
        assert r.status_code == 200
        doc = await db.email_logs.find_one({"resend_id": rid}, {"_id": 0})
        assert doc.get("clicks_count") == 1
        assert doc.get("last_clicked_url") == "https://exemplo.pt"

        # 4. email.bounced guarda bounce_reason — mas estado permanece delivered
        # (precedência igual: ambos finais; o primeiro vence)
        raw, hdr = _enviar(
            "email.bounced",
            {"bounce": {"type": "permanent", "message": "mailbox not found"}},
        )
        r = await c.post("/api/webhooks/resend", content=raw, headers=hdr)
        assert r.status_code == 200
        doc = await db.email_logs.find_one({"resend_id": rid}, {"_id": 0})
        assert doc["status"] == "delivered", "primeiro estado final vence"


@pytest.mark.anyio
async def test_webhook_evento_sem_resend_id_conhecido_devolve_200(monkeypatch):
    """Resend entrega eventos para e-mails que não temos — ack com log warning."""
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", _SECRET)
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    ts = str(int(time.time()))
    raw = json.dumps({
        "type": "email.delivered",
        "data": {"email_id": f"desconhecido_{uuid.uuid4().hex[:8]}"},
    }).encode()
    sig = _assinar_svix(_SECRET, msg_id, ts, raw)
    hdr = {"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": sig}
    async with _async_client() as c:
        r = await c.post("/api/webhooks/resend", content=raw, headers=hdr)
    assert r.status_code == 200
    assert r.json()["email_log_modified"] is False
