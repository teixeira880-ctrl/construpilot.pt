"""Webhook Resend — fecha o ciclo `accepted → delivered/bounced/complained/failed`.

Resend assina os webhooks via Svix (headers `svix-id`/`svix-timestamp`/
`svix-signature`). Verificamos a assinatura no corpo BRUTO antes de
qualquer parsing JSON, com proteção anti-replay (5 minutos).

Actualizações aplicadas:
    * `email_logs`  — por `resend_id` (`data.email_id`)  — fonte-única PT-PT
    * `quote_sends` — por `email_id` (legacy, tracking de leitura)

Idempotente via índice único em `svix_id`.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from core.db import db

logger = logging.getLogger("resend_webhook")
router = APIRouter(tags=["webhooks"])


# --- Mapeamento tipo-evento → estado interno de `email_logs` ---
# Estados finais (nunca retrocedem): `delivered`, `bounced`, `complained`, `failed`
_EVT_PARA_ESTADO: dict[str, str] = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.delivery_delayed": "delayed",
    "email.failed": "failed",
    # 'email.opened' / 'email.clicked' não alteram estado — apenas contadores
}
_ESTADOS_FINAIS = {"delivered", "bounced", "complained", "failed"}
# Permite transições "para cima" (ex: sent → delivered mas NÃO delivered → sent)
_PRECEDENCIA = {"queued": 0, "sent": 1, "delayed": 1, "delivered": 2,
                "bounced": 2, "complained": 2, "failed": 2}

_REPLAY_SEGUNDOS_MAX = 5 * 60  # proteção anti-replay (5 min)


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _actualizar_email_log(
    *, email_id: str, novo_estado: str | None, evento: dict, ts: str,
) -> int:
    """Actualiza `email_logs` para o `resend_id` (`data.email_id`).

    * Nunca retrocede de um estado final.
    * Guarda `last_event`, `events[]` para histórico.
    """
    log = await db.email_logs.find_one({"resend_id": email_id}, {"_id": 0, "status": 1})
    if not log:
        logger.warning("resend_id=%s não corresponde a nenhum email_log", email_id)
        return 0

    estado_actual = log.get("status") or "queued"
    update_set: dict = {
        "last_event": evento.get("type"),
        "updated_at": datetime.now(timezone.utc),
    }
    update_push = {
        "events": {"type": evento.get("type"), "at": ts}
    }
    if novo_estado:
        # Só avança se precedência for maior OU se estado actual não é final
        prec_actual = _PRECEDENCIA.get(estado_actual, 0)
        prec_novo = _PRECEDENCIA.get(novo_estado, 0)
        pode_actualizar = (
            estado_actual not in _ESTADOS_FINAIS
            or prec_novo > prec_actual
        )
        if pode_actualizar:
            update_set["status"] = novo_estado
            # Timestamps dedicados
            if novo_estado == "delivered":
                update_set["delivered_at"] = ts
            elif novo_estado == "bounced":
                update_set["bounced_at"] = ts
                update_set["bounce_reason"] = (
                    (evento.get("data") or {}).get("bounce") or {}
                )
            elif novo_estado == "complained":
                update_set["complained_at"] = ts
            elif novo_estado == "failed":
                update_set["failed_at"] = ts

    r = await db.email_logs.update_one(
        {"resend_id": email_id},
        {"$set": update_set, "$push": update_push},
    )
    return r.modified_count


async def _marcar_aberto_quote_sends(email_id: str, quando: str) -> int:
    """Legacy: marca `quote_sends` como abertos (tracking de leitura)."""
    res = await db.quote_sends.update_many(
        {"email_id": email_id},
        {
            "$set": {"opened": True, "last_opened_at": quando},
            "$inc": {"open_count": 1},
            "$min": {"opened_at": quando},
        },
    )
    return res.matched_count


async def _registar_clique(email_id: str, url: str, quando: str) -> None:
    """Guarda contador + URL do clique em `email_logs` e `quote_sends`."""
    await db.email_logs.update_one(
        {"resend_id": email_id},
        {
            "$inc": {"clicks_count": 1},
            "$push": {"clicks": {"url": url, "at": quando}},
            "$set": {"last_click_at": quando, "last_clicked_url": url},
        },
    )
    await db.quote_sends.update_many(
        {"email_id": email_id},
        {"$inc": {"click_count": 1}, "$set": {"last_click_at": quando}},
    )


@router.post("/webhooks/resend")
async def resend_webhook(request: Request):
    """Endpoint público assinado por HMAC Svix (RESEND_WEBHOOK_SECRET)."""
    secret = os.environ.get("RESEND_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook Resend não configurado (RESEND_WEBHOOK_SECRET em falta).",
        )

    raw = await request.body()
    svix_id = request.headers.get("svix-id")
    svix_ts = request.headers.get("svix-timestamp")
    svix_sig = request.headers.get("svix-signature")
    if not all((svix_id, svix_ts, svix_sig)):
        raise HTTPException(status_code=400, detail="Cabeçalhos Svix em falta.")

    # Proteção anti-replay (5 min)
    try:
        ts_int = int(svix_ts)
        if abs(time.time() - ts_int) > _REPLAY_SEGUNDOS_MAX:
            logger.warning("timestamp svix fora da janela: %s", svix_ts)
            raise HTTPException(status_code=401, detail="Timestamp fora da janela.")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="svix-timestamp inválido.")

    from svix.webhooks import Webhook, WebhookVerificationError

    try:
        Webhook(secret).verify(
            raw,
            {"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": svix_sig},
        )
    except WebhookVerificationError:
        logger.warning("assinatura webhook Resend inválida")
        raise HTTPException(status_code=401, detail="Assinatura inválida.")
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("falha na verificação do webhook Resend")
        raise HTTPException(status_code=400, detail="Webhook inválido.")

    try:
        evento = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Corpo JSON inválido.")

    tipo = evento.get("type")
    data = evento.get("data") or {}
    email_id = data.get("email_id") or data.get("id")
    if not tipo or not email_id:
        raise HTTPException(status_code=400, detail="Evento Resend malformado.")

    # Deduplicação (Resend entrega at-least-once com retries).
    try:
        await db.resend_webhook_events.insert_one({
            "svix_id": svix_id, "event_type": tipo,
            "email_id": email_id, "received_at": _agora_iso(),
        })
    except DuplicateKeyError:
        return {"received": True, "duplicate": True}

    agora = _agora_iso()
    novo_estado = _EVT_PARA_ESTADO.get(tipo)

    # 1. email_logs — fonte-única por resend_id
    modificados = await _actualizar_email_log(
        email_id=email_id, novo_estado=novo_estado, evento=evento, ts=agora,
    )

    # 2. quote_sends — tracking legacy
    if tipo == "email.opened":
        matched = await _marcar_aberto_quote_sends(email_id, agora)
        if matched:
            send = await db.quote_sends.find_one({"email_id": email_id}, {"_id": 0})
            if send and send.get("user_id"):
                await db.notifications.insert_one({
                    "user_id": send["user_id"], "type": "quote_opened",
                    "email_id": email_id, "doc_id": send.get("doc_id"),
                    "client_email": send.get("client_email"),
                    "message": (
                        f"O seu e-mail foi aberto por "
                        f"{send.get('client_email') or 'o destinatário'}"
                    ),
                    "read": False, "created_at": agora,
                })
    elif tipo == "email.clicked":
        url = (data.get("click") or {}).get("link") or data.get("url") or ""
        await _registar_clique(email_id, url, agora)
    elif tipo == "email.delivered":
        await db.quote_sends.update_many(
            {"email_id": email_id},
            {"$set": {"delivered": True, "delivered_at": agora}},
        )
    elif tipo == "email.bounced":
        await db.quote_sends.update_many(
            {"email_id": email_id},
            {"$set": {
                "bounced": True, "bounced_at": agora,
                "bounce": data.get("bounce"),
            }},
        )
    elif tipo == "email.complained":
        await db.quote_sends.update_many(
            {"email_id": email_id},
            {"$set": {"complained": True, "complained_at": agora}},
        )

    return {
        "received": True,
        "type": tipo,
        "email_log_modified": modificados > 0,
    }
