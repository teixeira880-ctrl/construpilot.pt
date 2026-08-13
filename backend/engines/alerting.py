"""Alertes prix : vérification (manuelle + quotidienne) + envoi email Resend."""
import os
import logging
from datetime import datetime, timezone

from core.db import db
from engines import price_search, emailer

logger = logging.getLogger(__name__)


async def _notify_user(user: dict, alert: dict, best: dict) -> bool:
    if not user or not user.get("email"):
        return False
    frontend = os.environ.get("FRONTEND_URL", "")
    html = emailer.wrap_html(
        "Un matériau vient d'atteindre votre prix cible",
        f"""<p>Bonjour {user.get("name") or ""},</p>
<p>Le matériau que vous surveillez sur ConstruPilot est disponible à un prix intéressant :</p>
<ul>
<li><b>Produit</b> : {alert.get("product") or alert.get("query")}</li>
<li><b>Recherche</b> : « {alert.get("query")} »</li>
<li><b>Prix cible</b> : {alert.get("target_price"):.2f} €</li>
<li><b>Meilleure offre</b> : <span style="color:#FF5A00;font-weight:bold">{best.get("price"):.2f} €</span>
    chez <b>{best.get("supplier")}</b></li>
</ul>
<p>Réservez rapidement avant que le prix ne remonte.</p>""",
        cta_url=best.get("url") or f"{frontend}/prix?q={alert.get('query')}",
        cta_label="Voir l'offre")
    try:
        await emailer.send_email(user["email"],
                                 f"Alerte prix ConstruPilot — {alert.get('product') or alert.get('query')}",
                                 html)
        await db.price_alerts.update_one({"alert_id": alert["alert_id"]},
                                         {"$set": {"last_notified_at": datetime.now(timezone.utc).isoformat(),
                                                   "last_notified_price": best.get("price")}})
        return True
    except Exception as e:
        logger.error(f"Alert notify failed for {user.get('email')}: {e}")
        return False


def _best_offer(offers: list) -> dict | None:
    """Return the cheapest offer with a real price (or None)."""
    valid = [o for o in offers if o.get("price") is not None]
    return min(valid, key=lambda o: o["price"]) if valid else None


def _should_notify(alert: dict, best_price: float) -> bool:
    """Decide whether the best offer justifies sending a new notification."""
    if best_price > alert["target_price"]:
        return False
    last = alert.get("last_notified_price")
    # Skip if price hasn't dropped by at least 2% since last notification
    return last is None or best_price < last * 0.98


async def _push_alert(user_id: str, alert: dict, best: dict) -> None:
    """Best-effort push notification (never blocks the email flow)."""
    try:
        from routes.phase7 import notify_user as push_notify
        await push_notify(
            user_id,
            f"💰 {alert.get('product') or alert.get('query')} : {best['price']:.2f} €",
            f"Meilleure offre chez {best.get('supplier')} — cible {alert['target_price']:.2f} €",
            best.get("url") or "/prix",
        )
    except Exception as e:
        logger.warning(f"Push notify failed: {e}")


async def check_user_alerts(user_id: str) -> int:
    """Check a user's active alerts, notify (email + push) when triggered."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return 0
    alerts = await db.price_alerts.find(
        {"user_id": user_id, "active": True}, {"_id": 0}
    ).to_list(200)

    sent = 0
    for a in alerts:
        result = await price_search.search(a["query"], 10)
        best = _best_offer(result.get("results", []))
        if not best or not _should_notify(a, best["price"]):
            continue
        if await _notify_user(user, a, best):
            sent += 1
            await _push_alert(user_id, a, best)
    return sent


async def check_all_alerts():
    """Job quotidien : vérifie toutes les alertes actives, tous users confondus."""
    logger.info("Price alerts: daily check starting")
    user_ids = await db.price_alerts.distinct("user_id", {"active": True})
    total = 0
    for uid in user_ids:
        try:
            total += await check_user_alerts(uid)
        except Exception as e:
            logger.error(f"Alerts check failed for user {uid}: {e}")
    logger.info(f"Price alerts: daily check done, {total} emails envoyés")
    return total
