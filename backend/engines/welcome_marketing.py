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

SUBJECT = "Bem-vindo ao ConstruPilot — os seus orçamentos de construção, sem erros nem aproximações"
PREHEADER = "Medição de plantas, orçamentos determinísticos, reabilitação energética e estudos de estruturas. Experiência grátis, sem cartão."

# Version texte brut (pour l'aperçu et les clients sans HTML)
TEXT = "Bem-vindo ao ConstruPilot.\n\nO ConstruPilot é o copiloto dos profissionais da construção: números exatos, nunca inventados.\nAo contrário das IA genéricas, os nossos cálculos são 100 % determinísticos — cada euro é rastreável.\n\nO que pode fazer desde já:\n- Medição de plantas: importe uma planta, meça áreas e comprimentos em poucos cliques.\n- Orçamentos determinísticos: montantes exatos, calculados (zero alucinações), prontos para o cliente.\n- RenoPilot: reabilitação energética, apoios (Fundo Ambiental) e cálculos de desempenho.\n- StructuroPilot: estudos de estruturas determinísticos, sem hipóteses não verificadas.\n- Faturação eletrónica: faturas conformes com a norma EN 16931.\n\nInicie a sua experiência grátis (sem cartão bancário): {cta_url}\n\nAté breve,\nA equipa ConstruPilot\n"

FEATURES = [
    ("\U0001F4D0", "Medição de plantas",
     "Importe uma planta PDF ou imagem, meça áreas, comprimentos e quantidades à escala. A medição alimenta diretamente o seu orçamento."),
    ("\U0001F9EE", "Orçamentos determinísticos",
     "Montantes <b>exatos e calculados</b>, nunca inventados por uma IA. Cada linha é rastreável, cada total é verificável. Exportação PDF limpa, pronta para o cliente."),
    ("\U0001F343", "RenoPilot — reabilitação energética",
     "Simule obras de reabilitação, identifique os apoios (Fundo Ambiental) e apoie-se em cálculos de desempenho energético."),
    ("\U0001F3D7\uFE0F", "StructuroPilot — estudos de estrutura",
     "Um motor de cálculo <b>determinístico</b> que constrói o modelo a partir dos factos e bloqueia qualquer hipótese não verificada. Sem aproximações na segurança."),
    ("\U0001F9FE", "Faturação eletrónica",
     "Gere faturas eletrónicas conformes à norma EN 16931, prontas para os seus clientes e para a administração."),
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
    greet = f'Olá {first_name},' if first_name else "Bom dia,"
    cta_btn = (
        f'<tr><td align="center" style="padding:28px 0 8px"><a href="{cta_url}" style="background:{BRAND};color:#fff;text-decoration:none;padding:14px 32px;font-family:Arial,sans-serif;font-size:15px;font-weight:bold;border-radius:6px;display:inline-block">Iniciar a minha experiência grátis</a></td></tr><tr><td align="center" style="padding:0 0 4px"><span style="font-size:12px;color:#94A3B8">Sem cartão bancário · ativação imediata</span></td></tr>'
    )
    return f'<!doctype html>\n<html><body style="margin:0;background:#f5f5f7;font-family:Arial,sans-serif;color:#0A0D14">\n<div style="display:none;max-height:0;overflow:hidden;opacity:0">{PREHEADER}</div>\n<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">\n<tr><td align="center">\n<table role="presentation" width="580" cellpadding="0" cellspacing="0"\n       style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">\n<tr><td style="padding:26px 28px;border-bottom:3px solid {BRAND}">\n  <div style="font-size:24px;font-weight:800;letter-spacing:-0.5px">ConstruPilot</div>\n  <div style="color:#64748B;font-size:12px;margin-top:4px">Estime, Compare, Construa.</div>\n</td></tr>\n<tr><td style="padding:30px 28px 8px">\n  <h1 style="font-size:22px;margin:0 0 14px 0;line-height:1.3">\n    {greet}<br/>Bem-vindo ao ConstruPilot 🎉\n  </h1>\n  <div style="font-size:15px;line-height:1.6;color:#334155">\n    <p style="margin:0 0 12px">O ConstruPilot é o <b>copiloto dos profissionais da construção</b>:\n    números <b>exatos</b>, nunca inventados.</p>\n    <p style="margin:0">Ao contrário das IA genéricas, os nossos cálculos são\n    <b>100 % determinísticos</b> — cada euro é calculado e rastreável. Ganha tempo\n    sem nunca sacrificar a fiabilidade.</p>\n  </div>\n</td></tr>\n<tr><td style="padding:16px 28px 0">\n  <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;\n       color:{BRAND};margin-bottom:4px">O que pode fazer desde já</div>\n  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">\n  {_feature_rows()}\n  </table>\n</td></tr>\n<tr><td style="padding:0 28px">\n  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cta_btn}</table>\n</td></tr>\n<tr><td style="padding:18px 28px 28px">\n  <div style="font-size:13px;line-height:1.6;color:#64748B">\n    Precisa de ajuda para começar? Basta responder a este e-mail,\n    a nossa equipa acompanha-o.<br/><br/>\n    Até breve,<br/><b style="color:#334155">A equipa ConstruPilot</b>\n  </div>\n</td></tr>\n{_footer(unsubscribe_url)}\n</table></td></tr></table></body></html>'


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
    front = (os.environ.get("FRONTEND_URL") or "https://construpilot.pt").rstrip("/")
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
