"""Merci Facteur tracking normalisation: accepted → printed → posted → delivered, with return alerts."""
import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

from core.db import db
from engines import mercifacteur as mf

log = logging.getLogger(__name__)
STAGES = ["accepted", "printed", "posted", "delivered"]
LABELS = {"accepted": "Aceite", "printed": "Impressa", "posted": "Enviada", "delivered": "Entregue", "returned": "Devolvida"}
FINAL = {"delivered", "returned"}
TRACK_WINDOW_DAYS = 60


def _lower(value) -> str:
    return str(value or "").lower()


def normalize(tracking: dict) -> dict:
    """Maps a getSuiviEnvoi payload onto a single delivery stage."""
    print_status = str(tracking.get("statutPrintEnvoi") or "")
    letters = tracking.get("suiviCourrier") or []
    letter = letters[0] if isinstance(letters, list) and letters and isinstance(letters[0], dict) else {}
    last_state = str(letter.get("lastState") or tracking.get("lastState") or "")
    event = _lower((letter.get("lastStateCode") or {}).get("event") if isinstance(letter.get("lastStateCode"), dict) else "")
    text, printed = _lower(last_state), _lower(print_status)
    returned = str(letter.get("pnd") or "") == "1" or any(k in text or k in event for k in ("retour", "non distribu", "pnd", "refus", "n'habite", "inconnu"))
    if returned:
        stage = "returned"
    elif any(k in text or k in event for k in ("distribu", "livr", "remis au destinataire", "delivered")):
        stage = "delivered"
    elif last_state.strip() or any(k in printed for k in ("remis", "poste", "expédi", "expedi", "déposé", "depose")):
        stage = "posted"
    elif "terminée" in printed or "terminee" in printed:
        stage = "printed"
    else:
        stage = "accepted"
    return {"stage": stage, "stage_label": LABELS[stage], "returned": returned,
            "provider_status": last_state or print_status or "Em tratamento",
            "print_status": print_status, "last_state": last_state, "tracking_ref": letter.get("refTracking") or None,
            "history": letter.get("historique") or None, "tracked_at": datetime.now(timezone.utc).isoformat()}


async def _notify_return(doc: dict) -> None:
    recipient = doc.get("recipient") or {}
    who = " · ".join(x for x in (recipient.get("nom"), recipient.get("ville")) if x)
    message = f'Carta devolvida / não distribuível: {who}. Verifique a morada antes de qualquer novo envio.'
    await db.notifications.insert_one({"notif_id": "n_" + secrets.token_hex(5), "user_id": doc["user_id"],
        "type": "postal_returned", "postal_id": doc["postal_id"], "message": message, "url": "/radar",
        "created_at": datetime.now(timezone.utc).isoformat(), "read": False})
    try:
        from routes.phase7 import notify_user
        await notify_user(doc["user_id"], "Carta devolvida", message, "/radar")
    except Exception as exc:
        log.warning("Push for returned letter failed: %s", exc)


async def refresh_send(doc: dict) -> dict:
    """Fetches provider tracking for one accepted letter and persists the normalised stage."""
    tracking = await mf.tracking(int(doc["envoi_id"]))
    update = {**normalize(tracking), "tracking": tracking}
    newly_returned = update["returned"] and not doc.get("return_notified")
    if newly_returned:
        update["return_notified"] = True
    await db.radar_postal.update_one({"postal_id": doc["postal_id"]}, {"$set": update})
    if newly_returned:
        await _notify_return(doc)
    return update


async def refresh_all() -> dict:
    """Daily scheduler job: tracks every accepted letter that has not reached a final stage."""
    if not mf.configured():
        return {"skipped": "not_configured"}
    since = (datetime.now(timezone.utc) - timedelta(days=TRACK_WINDOW_DAYS)).isoformat()
    cursor = db.radar_postal.find({"status": "submitted", "envoi_id": {"$ne": None}, "created_at": {"$gt": since},
                                   "stage": {"$nin": list(FINAL)}}, {"_id": 0}).sort("created_at", 1)
    stats = {"checked": 0, "returned": 0, "errors": 0}
    async for doc in cursor:
        try:
            update = await refresh_send(doc)
            stats["checked"] += 1
            stats["returned"] += int(update["returned"])
        except Exception as exc:
            stats["errors"] += 1
            log.warning("Tracking refresh failed for %s: %s", doc.get("postal_id"), exc)
        await asyncio.sleep(0.3)
    log.info("Postal tracking refresh: %s", stats)
    return stats
