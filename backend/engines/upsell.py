"""Email d'incitation automatique : J+3 après inscription, comptes gratuits, une seule fois.

Particulier → Premium (19 €/mois) · Pro → Pro (149 €/mois). Respecte `email_marketing_opt_out`.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from core.db import db

logger = logging.getLogger(__name__)
PAID_PLANS = ("premium_monthly", "premium_yearly", "pro_monthly", "pro_yearly",
              "pro_business_monthly", "pro_business_yearly", "project_pass")


def _front() -> str:
    return (os.environ.get("FRONTEND_URL") or "https://construpilot.fr").rstrip("/")


def _template(user: dict) -> tuple[str, str, str]:
    """Retourne (subject, body_html, cta_label)."""
    first = (user.get("name") or "").split(" ")[0].strip()
    hello = f"Bonjour {first}," if first else "Bonjour,"
    pro = user.get("account_type") in ("pro", "pro_business") or user.get("role") == "pro"
    if pro:
        subject = "Vos devis en 30 secondes, votre marge protégée : 7 jours de Pro offerts"
        body = f"""<p>{hello}</p>
<p>Vous avez testé ConstruPilot gratuitement. Voici ce que vous ne voyez pas encore avec le compte <b>Pro</b> :</p>
<ul>
<li><b>Métré IA sur plan</b> et lecture de DPGF / CCTP : les quantités sortent seules</li>
<li><b>Devis à vos prix</b> depuis votre bibliothèque, marge visible lot par lot, alerte « à perte »</li>
<li><b>Signature en ligne</b>, acompte, situations, facture Factur-X, paiement</li>
<li><b>Radar des permis de construire</b> autour de vous + courrier de prospection posté en un clic</li>
<li>Suivi de chantier, pointage d'équipe, prix fournisseurs en direct</li>
</ul>
<p>Un chiffrage complet qui prenait deux jours de bureau se fait en 30 secondes — vous gardez la relecture et les prix.</p>
<p><b>149 € HT/mois, sans engagement, 7 jours d'essai offerts</b> — le coût d'une heure de bureau par semaine pour ne plus jamais chiffrer à perte.</p>"""
        return subject, body, "Démarrer mon essai Pro"
    subject = "Vos travaux méritent mieux qu'une estimation : 7 jours de Premium offerts"
    body = f"""<p>{hello}</p>
<p>Vous avez déjà utilisé ConstruPilot pour estimer vos travaux — c'est le bon départ. Mais entre l'estimation et le chantier terminé, il y a les devis à comparer, les prix à négocier et le budget à tenir.</p>
<p><b>Le compte Premium a été conçu exactement pour ça :</b></p>
<ul>
<li><b>Projets illimités</b> et estimations détaillées, poste par poste</li>
<li><b>Analyse de devis illimitée</b> : repérez les postes surfacturés avant de signer</li>
<li><b>Comparaison et historique des prix</b> chez les grands fournisseurs + alertes baisse</li>
<li><b>Budget intelligent et planning</b> de chantier</li>
<li><b>ConstruPilot AI Advisor</b> : vos questions travaux, réponses précises</li>
<li>Export PDF de tous vos dossiers</li>
</ul>
<p>Le Premium coûte <b>19 €/mois, sans engagement</b>, et les <b>7 premiers jours sont offerts</b>. Annulez en un clic depuis votre compte : vous ne payez rien pendant l'essai.</p>"""
    return subject, body, "Activer mon essai Premium gratuit"


async def run_upsell_emails(days_after_signup: int = 3, limit: int = 200) -> dict:
    from engines.emailer import send_email, wrap_html
    from routes.emails import build_unsubscribe_url
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_after_signup)).isoformat()
    q = {
        "created_at": {"$lte": cutoff},
        "upsell_email_sent_at": {"$exists": False},
        "email_marketing_opt_out": {"$ne": True},
        "role": {"$nin": ["admin"]},
        "$or": [{"active_plan_id": {"$exists": False}}, {"active_plan_id": None},
                {"active_plan_id": {"$nin": list(PAID_PLANS)}}],
    }
    users = await db.users.find(q, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "role": 1,
                                    "account_type": 1, "created_at": 1}).limit(limit).to_list(limit)
    sent = failed = skipped = 0
    for u in users:
        email = (u.get("email") or "").lower()
        if not email or "@" not in email or email.endswith(("@example.com", "@construpilot-test.fr")):
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"upsell_email_sent_at": "skipped"}})
            skipped += 1
            continue
        subject, body, cta = _template(u)
        html = wrap_html(subject, body, cta_url=f"{_front()}/tarifs", cta_label=cta,
                         unsubscribe_url=build_unsubscribe_url(u["user_id"]))
        try:
            await send_email(email, subject, html)
            sent += 1
            status = datetime.now(timezone.utc).isoformat()
        except Exception as e:  # noqa: BLE001
            failed += 1
            status = "failed"
            logger.warning(f"Upsell email failed for {email}: {e}")
        await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"upsell_email_sent_at": status}})
    res = {"sent": sent, "failed": failed, "skipped": skipped, "candidates": len(users),
           "at": datetime.now(timezone.utc).isoformat()}
    if users:
        await db.email_campaigns.insert_one({
            "campaign_id": "auto_" + os.urandom(5).hex(), "type": "auto_upsell_j3",
            "subject": "Incitation Premium / Pro (J+3 automatique)", "recipients_count": len(users),
            "sent": sent, "failed": failed, "sent_by": "system", "created_at": res["at"]})
    logger.info(f"Upsell J+{days_after_signup}: {res}")
    return res
