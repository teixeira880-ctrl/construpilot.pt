"""Quote-bound consent and persistent reservation before any billable request."""
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO

from fastapi import HTTPException
from pypdf import PdfReader
from pymongo.errors import DuplicateKeyError

from core.db import db
from engines import mercifacteur as mf
from engines import postal_offer

log = logging.getLogger(__name__)
BLOCKED = {"submitting", "unknown", "submitted"}
QUOTE_TTL = timedelta(minutes=15)
CHECKOUT_QUOTE_TTL = timedelta(hours=3)


def identity(user_id, token, recipient, mode):
    destination = {key: " ".join(str(recipient.get(key) or "").upper().split()) for key in ("nom", "societe", "adresse1", "adresse2", "cp", "ville", "pays")}
    content = json.dumps([user_id, token, destination, mode], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def context_digest(message, branding):
    return hashlib.sha256(json.dumps([message, branding], sort_keys=True, default=str).encode()).hexdigest()


def provider_http_error(exc):
    return HTTPException(503, {"code": exc.code, "message": str(exc), "retryable": not exc.uncertain})


def quote_expired():
    return HTTPException(409, {"code": "quote_expired", "message": "Le tarif a expiré ou le courrier a changé. Actualisez le tarif et confirmez-le à nouveau."})


async def create_quote(*, user, user_id, token, opp_id, recipient, mode, address_source, sender, pdf, context_hash):
    if user["user_id"] != user_id:
        raise HTTPException(403, "Accès refusé.")
    offer = await postal_offer.require_available(user)
    lock_id = identity(user_id, token, recipient, mode)
    attempt = await db.radar_postal.find_one({"_id": lock_id}, {"_id": 0, "status": 1})
    if attempt and attempt.get("status") != "rejected":
        raise HTTPException(409, {"code": "postal_already_requested", "message": "Un envoi identique est déjà enregistré ou à vérifier. Consultez son suivi avant toute nouvelle tentative."})
    pages = len(PdfReader(BytesIO(pdf)).pages)
    try:
        price = await mf.postage_price(mode=mode, pages=pages)
    except mf.PostalProviderError as exc:
        raise provider_http_error(exc)
    now = datetime.now(timezone.utc)
    quote_id = secrets.token_urlsafe(24)
    expires = now + QUOTE_TTL
    await db.radar_postal_quotes.create_index("expires_at", expireAfterSeconds=0)
    await db.radar_postal_quotes.insert_one({"quote_id": quote_id, "user_id": user_id, "token": token,
        "opp_id": opp_id, "recipient": recipient, "sender": sender, "mode": mode,
        "address_source": address_source, "pdf": pdf, "context_hash": context_hash,
        "price": price, "expires_at": expires, "lock_id": lock_id,
        "company_key": postal_offer.company_key(user), "offer": offer.model_dump()})
    return {**price, "quote_id": quote_id, "expires_at": expires.isoformat(), "offer": offer.model_dump()}


async def load_quote(*, user, user_id, token, quote_id, recipient, mode, context_hash):
    """Returns the still-valid quote matching the confirmed letter, or raises quote_expired."""
    if user["user_id"] != user_id:
        raise HTTPException(403, "Accès refusé.")
    quote = await db.radar_postal_quotes.find_one({"quote_id": quote_id, "user_id": user_id, "token": token,
        "expires_at": {"$gt": datetime.now(timezone.utc)}}, {"_id": 0})
    if (not quote or quote["recipient"] != recipient or quote["mode"] != mode or quote["context_hash"] != context_hash
            or quote.get("company_key") != postal_offer.company_key(user)
            or quote.get("offer", {}).get("next_kind") not in ("demo", "credit", "checkout")):
        raise quote_expired()
    return quote


async def extend_quote_for_checkout(quote_id: str, session_id: str) -> None:
    await db.radar_postal_quotes.update_one({"quote_id": quote_id}, {"$set": {
        "expires_at": datetime.now(timezone.utc) + CHECKOUT_QUOTE_TTL, "checkout_session_id": session_id}})


def _resolve_kind(quote: dict, offer: postal_offer.PostalOffer, paid_session_id: str | None) -> str:
    quoted = quote.get("offer", {}).get("next_kind")
    if paid_session_id:
        if quoted != "checkout":
            raise quote_expired()
        return "paid"
    if offer.next_kind == "checkout":
        raise HTTPException(402, {"code": "postal_payment_required", "message":
            "Les envois offerts et vos crédits sont épuisés. Réglez cet envoi (20 € HT) ou achetez un pack de crédits.",
            "offer": offer.model_dump()})
    if quoted != offer.next_kind or quote.get("offer", {}).get("customer_amount_cents") != 0:
        raise quote_expired()
    return offer.next_kind


async def deliver(*, user, user_id, token, quote_id, recipient, mode, context_hash, paid_session_id=None):
    quote = await load_quote(user=user, user_id=user_id, token=token, quote_id=quote_id, recipient=recipient,
                             mode=mode, context_hash=context_hash)
    kind = _resolve_kind(quote, await postal_offer.offer_for(user), paid_session_id)
    # Authentication happens before reservation; failure here cannot have created postage.
    try:
        await mf.get_token()
    except mf.PostalProviderError as exc:
        raise provider_http_error(exc)
    billing = {"kind": {"demo": "company_demo", "credit": "prepaid_credit", "paid": "stripe_checkout"}[kind],
               "customer_amount_cents": postal_offer.gross(postal_offer.UNIT_NET_CENTS) if kind == "paid" else 0,
               "currency": "EUR", "operator_pays_postage": kind == "demo", "session_id": paid_session_id}
    doc = {"postal_id": "post_" + secrets.token_hex(8), "token": token, "user_id": user_id, "company_id": user.get("organization_id"),
        "opp_id": quote["opp_id"], "address_source": quote["address_source"], "recipient": recipient,
        "mode": mode, "price": quote["price"], "status": "submitting", "envoi_id": None, "billing": billing,
        "stage": "accepted", "quote_id": quote_id, "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        await db.radar_postal.insert_one({"_id": quote["lock_id"], **doc})
    except DuplicateKeyError:
        previous = await db.radar_postal.find_one({"_id": quote["lock_id"]}, {"_id": 0})
        # A rejected request may only be retried after a NEW price + explicit confirmation.
        if previous.get("status") == "rejected" and previous.get("quote_id") != quote_id:
            result = await db.radar_postal.replace_one({"_id": quote["lock_id"], "postal_id": previous["postal_id"], "status": "rejected"}, {"_id": quote["lock_id"], **doc})
            if not result.modified_count:
                raise HTTPException(409, "Une tentative est déjà en cours.")
        else:
            raise HTTPException(409, {"code": "postal_already_requested", "message": "Un envoi identique est déjà enregistré ou à vérifier. Aucun second envoi n'a été déclenché."})
    try:
        await postal_offer.reserve(user, doc["postal_id"], quote["opp_id"], kind, session_id=paid_session_id)
    except HTTPException as exc:
        # Definitive local refusal: the provider has not been called.
        await db.radar_postal.update_one({"_id": quote["lock_id"]}, {"$set": {
            "status": "rejected", "error_code": exc.detail["code"],
            "error_message": exc.detail["message"]}})
        raise
    try:
        result = await mf.send_letter(bytes(quote["pdf"]), sender=quote["sender"], recipient=recipient,
            mode=mode, filename=f"courrier-{token}", reference=quote["lock_id"])
        envoi = result.get("envoi_id")
        if isinstance(envoi, list):
            envoi = envoi[0] if len(envoi) == 1 else None
        if not envoi or not str(envoi).isdigit():
            raise mf.PostalProviderError("missing_receipt", "Merci Facteur n'a pas fourni de référence d'envoi.", uncertain=True)
        doc.update(status="submitted", envoi_id=str(envoi), provider_price=result.get("price"))
    except mf.PostalProviderError as exc:
        doc.update(status="unknown" if exc.uncertain else "rejected", error_code=exc.code,
            error_message="Résultat incertain : ne renvoyez pas ce courrier. Vérifiez auprès de Merci Facteur avant toute nouvelle tentative." if exc.uncertain else str(exc))
    except Exception:
        log.exception("Unexpected postal result for attempt %s", doc["postal_id"])
        doc.update(status="unknown", error_code="unknown_result", error_message="Résultat incertain : consultez Merci Facteur avant tout nouvel envoi.")
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.radar_postal.update_one({"_id": quote["lock_id"]}, {"$set": doc})
    await postal_offer.settle(user, doc["postal_id"], doc["status"])
    if doc["status"] == "submitted":
        await db.radar_prospections.update_one({"token": token, "user_id": user_id}, {"$inc": {"postal_count": 1}})
    return doc
