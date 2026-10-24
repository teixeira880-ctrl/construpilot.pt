"""Stripe checkout for postal letters beyond the company allowance: per-letter payment and credit packs."""
import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import HTTPException

from core.db import db
from engines import monetization  # noqa: F401  (configures stripe.api_key)
from engines import postal_delivery, postal_offer

log = logging.getLogger(__name__)
LETTER_TYPE = "postal_letter"
CREDITS_TYPE = "postal_credits"
SESSION_TTL = timedelta(minutes=45)
RETURN_PATH = "/radar/courrier/retour"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _urls(origin_url: str) -> dict:
    origin = origin_url.rstrip("/")
    return {"success_url": f"{origin}{RETURN_PATH}?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{origin}{RETURN_PATH}?session_id={{CHECKOUT_SESSION_ID}}&cancelled=1"}


async def _create_session(user: dict, *, name: str, description: str, unit_cents: int, quantity: int,
                          metadata: dict, origin_url: str):
    if not stripe.api_key:
        raise HTTPException(503, "Pagamento indisponível: Stripe não configurado.")
    customer_id = await monetization.get_or_create_customer(user)
    expires = datetime.now(timezone.utc) + SESSION_TTL
    kwargs = {"customer": customer_id, "mode": "payment", "expires_at": int(expires.timestamp()),
              "line_items": [{"price_data": {"currency": "eur", "unit_amount": unit_cents,
                  "product_data": {"name": name, "description": description}}, "quantity": quantity}],
              "metadata": {"user_id": user["user_id"], **metadata}, **_urls(origin_url)}
    try:
        return await asyncio.to_thread(stripe.checkout.Session.create, **kwargs)
    except Exception:
        log.exception("Stripe postal checkout")
        raise HTTPException(502, "Pagamento indisponível — tente novamente dentro de instantes.")


async def _pending_session(query: dict):
    since = (datetime.now(timezone.utc) - SESSION_TTL + timedelta(minutes=5)).isoformat()
    rec = await db.payment_transactions.find_one({**query, "payment_status": "pending", "created_at": {"$gt": since}}, {"_id": 0})
    return rec if rec and rec.get("checkout_url") else None


async def create_letter_checkout(*, user, token, quote_id, recipient, mode, context_hash, origin_url) -> dict:
    quote = await postal_delivery.load_quote(user=user, user_id=user["user_id"], token=token, quote_id=quote_id,
                                             recipient=recipient, mode=mode, context_hash=context_hash)
    offer = await postal_offer.offer_for(user)
    if offer.next_kind != "checkout" or quote.get("offer", {}).get("next_kind") != "checkout":
        raise HTTPException(409, {"code": "postal_free_available", "message":
            "Está disponível um envio oferecido ou um crédito: atualize o preço, este envio não exige pagamento."})
    attempt = await db.radar_postal.find_one({"_id": quote["lock_id"]}, {"_id": 0, "status": 1})
    if attempt and attempt.get("status") != "rejected":
        raise HTTPException(409, {"code": "postal_already_requested", "message": "Já está registado ou a verificar um envio idêntico."})
    pending = await _pending_session({"type": LETTER_TYPE, "lock_id": quote["lock_id"], "user_id": user["user_id"]})
    if pending:
        return {"url": pending["checkout_url"], "session_id": pending["session_id"], "amount_cents": pending["amount_cents"], "reused": True}
    gross = offer.unit_price_gross_cents
    session = await _create_session(user, name="Correio postal ConstruPilot — 1 carta",
        description=f"{offer.unit_price_net_cents / 100:.2f} € s/ IVA + IVA {offer.vat_rate} % · destinatário {recipient.get('nom', '')[:40]}",
        unit_cents=gross, quantity=1, origin_url=origin_url,
        metadata={"type": LETTER_TYPE, "token": token, "quote_id": quote_id, "lock_id": quote["lock_id"]})
    await postal_delivery.extend_quote_for_checkout(quote_id, session.id)
    await db.payment_transactions.insert_one({
        "session_id": session.id, "checkout_url": session.url, "user_id": user["user_id"], "type": LETTER_TYPE,
        "token": token, "quote_id": quote_id, "lock_id": quote["lock_id"], "recipient": recipient, "mode": mode,
        "context_hash": context_hash, "amount_cents": gross, "amount_net_cents": offer.unit_price_net_cents,
        "vat_rate": offer.vat_rate, "currency": "eur", "plan_id": None, "mode_stripe": "payment", "status": "initiated",
        "payment_status": "pending", "fulfillment": "pending", "created_at": _now(), "updated_at": _now()})
    return {"url": session.url, "session_id": session.id, "amount_cents": gross, "reused": False}


async def create_credits_checkout(*, user, pack_id: str, origin_url: str) -> dict:
    letters = postal_offer.PACKS.get(pack_id)
    if not letters:
        raise HTTPException(400, "Pack desconhecido.")
    postal_offer.company_key(user)
    net = letters * postal_offer.UNIT_NET_CENTS
    gross = postal_offer.gross(net)
    session = await _create_session(user, name=f'Pack {letters} cartas postais ConstruPilot',
        description=f"{letters} cartas · {net / 100:.2f} € s/ IVA + IVA {postal_offer.VAT_RATE} %",
        unit_cents=gross, quantity=1, origin_url=origin_url, metadata={"type": CREDITS_TYPE, "pack_id": pack_id, "letters": str(letters)})
    await db.payment_transactions.insert_one({
        "session_id": session.id, "checkout_url": session.url, "user_id": user["user_id"], "type": CREDITS_TYPE,
        "pack_id": pack_id, "letters": letters, "amount_cents": gross, "amount_net_cents": net, "vat_rate": postal_offer.VAT_RATE,
        "currency": "eur", "plan_id": None, "mode_stripe": "payment", "status": "initiated", "payment_status": "pending",
        "fulfillment": "pending", "created_at": _now(), "updated_at": _now()})
    return {"url": session.url, "session_id": session.id, "amount_cents": gross, "letters": letters}


async def _load_user(user_id: str) -> dict | None:
    return await db.users.find_one({"user_id": user_id}, {"_id": 0})


async def apply_letter_payment(rec: dict) -> None:
    """Called once by the paid-webhook/sync path: dispatch the letter or compensate with a credit."""
    claimed = await db.payment_transactions.update_one(
        {"session_id": rec["session_id"], "fulfillment": "pending"}, {"$set": {"fulfillment": "processing", "updated_at": _now()}})
    if not claimed.modified_count:
        return
    user = await _load_user(rec["user_id"])
    outcome = {"fulfillment": "done"}
    try:
        if not user:
            raise HTTPException(404, {"code": "user_missing", "message": "Utilizador não encontrado."})
        doc = await postal_delivery.deliver(user=user, user_id=user["user_id"], token=rec["token"], quote_id=rec["quote_id"],
            recipient=rec["recipient"], mode=rec["mode"], context_hash=rec["context_hash"], paid_session_id=rec["session_id"])
        outcome["postal_id"] = doc["postal_id"]
        outcome["postal_status"] = doc["status"]
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "fulfillment_error", "message": str(exc.detail)}
        outcome.update(fulfillment="credited", fulfillment_error=detail)
        if user:
            await postal_offer.add_credits(user, 1, session_id=rec["session_id"], reason="letter_payment_unfulfilled")
        log.warning("Paid postal letter not dispatched (%s): credited 1 letter", detail.get("code"))
    except Exception:
        log.exception("Paid postal letter fulfillment crashed for %s", rec["session_id"])
        outcome.update(fulfillment="error")
    await db.payment_transactions.update_one({"session_id": rec["session_id"]}, {"$set": {**outcome, "updated_at": _now()}})


async def apply_credits_payment(rec: dict) -> None:
    claimed = await db.payment_transactions.update_one(
        {"session_id": rec["session_id"], "fulfillment": "pending"}, {"$set": {"fulfillment": "processing", "updated_at": _now()}})
    if not claimed.modified_count:
        return
    user = await _load_user(rec["user_id"])
    if not user:
        await db.payment_transactions.update_one({"session_id": rec["session_id"]}, {"$set": {"fulfillment": "error", "updated_at": _now()}})
        return
    balance = await postal_offer.add_credits(user, int(rec.get("letters") or 0), session_id=rec["session_id"])
    await db.payment_transactions.update_one({"session_id": rec["session_id"]}, {"$set": {
        "fulfillment": "done", "credits_balance": balance, "updated_at": _now()}})
    await db.notifications.insert_one({"notif_id": "n_" + secrets.token_hex(5), "user_id": user["user_id"],
        "type": "postal_credits", "message": f"{rec.get('letters')} créditos de correio adicionados à sua empresa (saldo: {balance}).",
        "url": "/radar", "created_at": _now(), "read": False})


async def payment_view(user: dict, session_id: str) -> dict:
    rec = await db.payment_transactions.find_one({"session_id": session_id, "user_id": user["user_id"],
                                                  "type": {"$in": [LETTER_TYPE, CREDITS_TYPE]}}, {"_id": 0, "recipient": 0})
    if not rec:
        raise HTTPException(404, "Pagamento não encontrado.")
    if rec.get("payment_status") != "paid":
        await monetization.sync_status(session_id)
        rec = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0, "recipient": 0})
    postal = None
    if rec.get("postal_id"):
        postal = await db.radar_postal.find_one({"postal_id": rec["postal_id"]}, {"_id": 0, "postal_id": 1, "status": 1,
            "envoi_id": 1, "stage": 1, "error_message": 1, "recipient": 1, "mode": 1, "token": 1})
    return {"session_id": session_id, "type": rec["type"], "payment_status": rec["payment_status"], "status": rec["status"],
            "fulfillment": rec.get("fulfillment"), "fulfillment_error": rec.get("fulfillment_error"),
            "amount_cents": rec.get("amount_cents"), "letters": rec.get("letters"), "token": rec.get("token"),
            "postal": postal, "offer": (await postal_offer.offer_for(user)).model_dump()}
