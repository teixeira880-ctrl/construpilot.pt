"""Digest hebdomadaire par email (chaque lundi 09:00 UTC).

Contenu : alertes déclenchées, top matériaux surveillés, suggestion d'économies
pour les projets récents.
"""
import logging
import os
from datetime import datetime, timezone

from core.db import db
from engines import emailer, price_search, savings

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc)


async def build_digest(user: dict) -> dict:
    # Alertes actives + best price actuel
    alerts = await db.price_alerts.find({"user_id": user["user_id"], "active": True},
                                        {"_id": 0}).to_list(20)
    watched = []
    for a in alerts[:5]:
        try:
            res = await price_search.search(a["query"], 5)
            offers = [o for o in res.get("results", []) if o.get("price")]
            if offers:
                best = min(offers, key=lambda o: o["price"])
                triggered = best["price"] <= a["target_price"]
                watched.append({"query": a["query"], "target": a["target_price"],
                                "current": best["price"], "supplier": best["supplier"],
                                "triggered": triggered, "url": best.get("url")})
        except Exception:
            continue
    # Projets récents avec économies
    recent_projects = await db.projects.find({"user_id": user["user_id"]},
                                             {"_id": 0}).sort("created_at", -1).limit(3).to_list(3)
    savings_hints = []
    for p in recent_projects:
        try:
            s = savings.compute(p.get("estimation") or {})
            if s.get("total", 0) > 100:
                savings_hints.append({"name": p.get("name"),
                                      "total": s["total"],
                                      "roi": s.get("roi_multiplier")})
        except Exception:
            continue
    return {"watched": watched, "savings": savings_hints,
            "user_name": user.get("name"), "user_email": user.get("email")}


def _fmt_digest_html(digest: dict) -> str:
    body = f"<p>Olá {digest.get('user_name') or ''},</p>"
    body += "<p>Votre récap hebdomadaire ConstruPilot :</p>"
    w = digest.get("watched") or []
    if w:
        body += "<h3 style='margin-top:24px'>📉 Matériaux surveillés</h3><ul>"
        for x in w:
            arrow = "✅ Sous le prix cible" if x["triggered"] else "⏳ Au-dessus"
            body += (f"<li><b>{x['query']}</b> — meilleur : "
                     f"<span style='color:#FF5A00;font-weight:bold'>{x['current']:.2f} €</span>"
                     f" chez {x['supplier']} (cible {x['target']:.2f} €) — {arrow}</li>")
        body += "</ul>"
    else:
        body += "<p style='color:#64748B;font-size:13px'>Aucune alerte prix active — créez-en depuis la page Prix pour être notifié.</p>"

    s = digest.get("savings") or []
    if s:
        body += "<h3 style='margin-top:24px'>💰 Économies identifiées sur vos projets</h3><ul>"
        for x in s:
            body += (f"<li><b>{x['name']}</b> : jusqu'à "
                     f"<span style='color:#FF5A00;font-weight:bold'>{x['total']:,.0f} €</span>"
                     f" d'économies (ROI ~{x['roi']}× le Project Pass)</li>")
        body += "</ul>"
    body = body.replace(",", " ")
    frontend = os.environ.get("FRONTEND_URL", "")
    return emailer.wrap_html("Votre récap hebdo ConstruPilot", body,
                             cta_url=f"{frontend}/dashboard" if frontend else None,
                             cta_label="Ouvrir mon tableau de bord")


async def send_weekly_digests() -> int:
    """Envoie le digest à tous les utilisateurs opt-in (par défaut : tous)."""
    users = await db.users.find({"weekly_digest": {"$ne": False}},
                                {"_id": 0}).to_list(5000)
    sent = 0
    for u in users:
        try:
            digest = await build_digest(u)
            if not digest["watched"] and not digest["savings"]:
                continue
            await emailer.send_email(u["email"],
                                     "Votre récap hebdo ConstruPilot",
                                     _fmt_digest_html(digest))
            sent += 1
        except Exception as e:
            logger.warning(f"Digest failed for {u.get('email')}: {e}")
    logger.info(f"Weekly digests sent: {sent}")
    return sent
