"""E-mail publicitaire de bienvenue pour les nouveaux utilisateurs ConstruPilot (français).

Objectif : présentation produit + inscription à l'essai gratuit.
Ton : direct/commercial, professionnel/technique, chaleureux.
Réutilise l'identité de marque (orange #FF5A00) et le pied de page de `emailer`.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from engines.emailer import BRAND, _footer

logger = logging.getLogger(__name__)

SUBJECT = "Bienvenue sur ConstruPilot — vos devis BTP, sans erreur ni approximation"
PREHEADER = "Métré de plans, devis déterministes, rénovation énergétique et études structure. Essai gratuit, sans carte."

# Version texte brut (pour l'aperçu et les clients sans HTML)
TEXT = """Bienvenue sur ConstruPilot.

ConstruPilot est le copilote des pros du bâtiment : des chiffres exacts, jamais inventés.
Contrairement aux IA génériques, nos calculs sont 100 % déterministes — chaque euro est traçable.

Ce que vous pouvez faire dès aujourd'hui :
- Métré de plans : importez un plan, mesurez surfaces et longueurs en quelques clics.
- Devis déterministes : des montants exacts, calculés (zéro hallucination), prêts pour le client.
- RenoPilot : rénovation énergétique, aides (MaPrimeRénov') et calculs ADEME/Publicodes.
- StructuroPilot : études de structure déterministes, sans hypothèse non vérifiée.
- Facturation Factur-X : factures électroniques conformes à la norme EN 16931.

Démarrez votre essai gratuit (sans carte bancaire) : {cta_url}

À très vite,
L'équipe ConstruPilot
"""

FEATURES = [
    ("\U0001F4D0", "Métré de plans",
     "Importez un plan PDF ou image, mesurez surfaces, longueurs et quantités à l'échelle. "
     "Le métré alimente directement votre devis."),
    ("\U0001F9EE", "Devis déterministes",
     "Des montants <b>exacts et calculés</b>, jamais inventés par une IA. Chaque ligne est "
     "traçable, chaque total est vérifiable. Export PDF propre, prêt pour le client."),
    ("\U0001F343", "RenoPilot — rénovation énergétique",
     "Simulez des travaux de rénovation, identifiez les aides (MaPrimeRénov') et appuyez-vous "
     "sur les calculs officiels ADEME / Publicodes."),
    ("\U0001F3D7\uFE0F", "StructuroPilot — études de structure",
     "Un moteur de calcul <b>déterministe</b> qui construit le modèle à partir des faits et "
     "bloque toute hypothèse non vérifiée. Pas d'approximation sur la sécurité."),
    ("\U0001F9FE", "Facturation Factur-X",
     "Générez des factures électroniques conformes à la norme EN 16931, prêtes pour vos clients "
     "et l'administration."),
]


def _feature_rows() -> str:
    rows = ""
    for icon, title, desc in FEATURES:
        rows += (
            '<tr><td style="padding:14px 0;border-bottom:1px solid #eef1f5">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td width="44" valign="top" style="font-size:24px;line-height:28px">{icon}</td>'
            '<td valign="top">'
            f'<div style="font-size:15px;font-weight:700;color:#0A0D14;margin-bottom:3px">{title}</div>'
            f'<div style="font-size:13px;line-height:1.55;color:#475569">{desc}</div>'
            '</td></tr></table></td></tr>'
        )
    return rows


def welcome_marketing_html(first_name: str | None, cta_url: str,
                           unsubscribe_url: str | None = None) -> str:
    """Construit l'e-mail HTML de bienvenue (inline CSS, tables, compatible Gmail/Outlook)."""
    greet = f"Bonjour {first_name}," if first_name else "Bonjour,"
    cta_btn = (
        f'<tr><td align="center" style="padding:28px 0 8px">'
        f'<a href="{cta_url}" style="background:{BRAND};color:#fff;text-decoration:none;'
        f'padding:14px 32px;font-family:Arial,sans-serif;font-size:15px;font-weight:bold;'
        f'border-radius:6px;display:inline-block">Démarrer mon essai gratuit</a></td></tr>'
        f'<tr><td align="center" style="padding:0 0 4px">'
        f'<span style="font-size:12px;color:#94A3B8">Sans carte bancaire · activation immédiate</span>'
        f'</td></tr>'
    )
    return f"""<!doctype html>
<html><body style="margin:0;background:#f5f5f7;font-family:Arial,sans-serif;color:#0A0D14">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{PREHEADER}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">
<tr><td align="center">
<table role="presentation" width="580" cellpadding="0" cellspacing="0"
       style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
<tr><td style="padding:26px 28px;border-bottom:3px solid {BRAND}">
  <div style="font-size:24px;font-weight:800;letter-spacing:-0.5px">ConstruPilot</div>
  <div style="color:#64748B;font-size:12px;margin-top:4px">Estimez, Comparez, Construisez.</div>
</td></tr>
<tr><td style="padding:30px 28px 8px">
  <h1 style="font-size:22px;margin:0 0 14px 0;line-height:1.3">
    {greet}<br/>Bienvenue sur ConstruPilot \U0001F389
  </h1>
  <div style="font-size:15px;line-height:1.6;color:#334155">
    <p style="margin:0 0 12px">ConstruPilot est le <b>copilote des pros du bâtiment</b> :
    des chiffres <b>exacts</b>, jamais inventés.</p>
    <p style="margin:0">Contrairement aux IA génériques, nos calculs sont
    <b>100 % déterministes</b> — chaque euro est calculé et traçable. Vous gagnez du temps
    sans jamais sacrifier la fiabilité.</p>
  </div>
</td></tr>
<tr><td style="padding:16px 28px 0">
  <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
       color:{BRAND};margin-bottom:4px">Ce que vous pouvez faire dès aujourd'hui</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  {_feature_rows()}
  </table>
</td></tr>
<tr><td style="padding:0 28px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cta_btn}</table>
</td></tr>
<tr><td style="padding:18px 28px 28px">
  <div style="font-size:13px;line-height:1.6;color:#64748B">
    Besoin d'un coup de main pour démarrer ? Répondez simplement à cet e-mail,
    notre équipe vous accompagne.<br/><br/>
    À très vite,<br/><b style="color:#334155">L'équipe ConstruPilot</b>
  </div>
</td></tr>
{_footer(unsubscribe_url)}
</table></td></tr></table></body></html>"""


async def run_welcome_marketing_emails(limit: int = 500) -> dict:
    """Envoie l'e-mail publicitaire de bienvenue ~1 jour après l'inscription.

    Envoyé une seule fois par utilisateur (flag `welcome_marketing_sent_at`),
    respecte `email_marketing_opt_out`, ignore les comptes admin et de test.
    À appeler quotidiennement par le scheduler.
    """
    from core.db import db
    from engines.emailer import send_email
    from routes.emails import build_unsubscribe_url

    now = datetime.now(timezone.utc)
    lo = (now - timedelta(days=2)).isoformat()
    hi = (now - timedelta(days=1)).isoformat()
    users = await db.users.find({
        "created_at": {"$gte": lo, "$lte": hi},
        "welcome_marketing_sent_at": {"$exists": False},
        "email_marketing_opt_out": {"$ne": True},
        "role": {"$nin": ["admin"]},
    }, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).limit(limit).to_list(limit)

    sent = failed = skipped = 0
    front = (os.environ.get("FRONTEND_URL") or "https://construpilot.fr").rstrip("/")
    cta = f"{front}/?utm_source=email&utm_medium=welcome&utm_campaign=onboarding"
    for u in users:
        email = (u.get("email") or "").lower()
        if not email or "@" not in email or email.endswith(("@example.com", "@construpilot-test.fr")):
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"welcome_marketing_sent_at": "skipped"}})
            skipped += 1
            continue
        first = (u.get("name") or "").split(" ")[0] or None
        html = welcome_marketing_html(first, cta, unsubscribe_url=build_unsubscribe_url(u["user_id"]))
        try:
            await send_email(email, SUBJECT, html, from_name="ConstruPilot")
            sent += 1
            status = now.isoformat()
        except Exception as e:  # noqa: BLE001
            failed += 1
            status = "failed"
            logger.warning(f"Welcome marketing email failed for {email}: {e}")
        await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"welcome_marketing_sent_at": status}})
    res = {"sent": sent, "failed": failed, "skipped": skipped, "candidates": len(users),
           "at": now.isoformat()}
    if users:
        await db.email_campaigns.insert_one({
            "campaign_id": "auto_" + os.urandom(5).hex(), "type": "auto_welcome_j1",
            "subject": SUBJECT, "recipients_count": len(users),
            "sent": sent, "failed": failed, "sent_by": "system", "created_at": res["at"]})
    logger.info(f"Welcome marketing J+1: {res}")
    return res
