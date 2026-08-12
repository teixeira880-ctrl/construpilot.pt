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
    frontend = os.environ.get("FRONTEND_URL") or "https://cmrenov-ai.preview.emergentagent.com"
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


async def check_user_alerts(user_id: str) -> int:
    """Vérifie les alertes actives d'un user, notifie si triggered depuis dernier envoi."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return 0
    alerts = await db.price_alerts.find({"user_id": user_id, "active": True},
                                        {"_id": 0}).to_list(200)
    sent = 0
    for a in alerts:
        result = await price_search.search(a["query"], 10)
        offers = [o for o in result.get("results", []) if o.get("price") is not None]
        if not offers:
            continue
        best = min(offers, key=lambda o: o["price"])
        if best["price"] > a["target_price"]:
            continue
        last_price = a.get("last_notified_price")
        if last_price is not None and best["price"] >= last_price * 0.98:
            continue  # évite le spam si prix quasi identique au dernier envoi
        if await _notify_user(user, a, best):
            sent += 1
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
