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
    return (os.environ.get("FRONTEND_URL") or "https://construpilot.pt").rstrip("/")


def _template(user: dict) -> tuple[str, str, str]:
    """Retourne (subject, body_html, cta_label)."""
    first = (user.get("name") or "").split(" ")[0].strip()
    hello = f'Olá {first},' if first else "Bom dia,"
    pro = user.get("account_type") in ("pro", "pro_business") or user.get("role") == "pro"
    if pro:
        subject = "Os seus orçamentos em 30 segundos, a sua margem protegida: 7 dias de Pro grátis"
        body = f'<p>{hello}</p>\n<p>Experimentou o ConstruPilot gratuitamente. Eis o que ainda não vê com a conta <b>Pro</b>:</p>\n<ul>\n<li><b>Medição IA sobre planta</b> e leitura de mapas de quantidades / cadernos de encargos: as quantidades saem sozinhas</li>\n<li><b>Orçamentos aos seus preços</b> a partir da sua biblioteca, margem visível capítulo a capítulo, alerta «com prejuízo»</li>\n<li><b>Assinatura online</b>, adiantamento, autos de medição, fatura eletrónica, pagamento</li>\n<li><b>Radar de obras e licenças</b> à sua volta + carta de prospeção enviada num clique</li>\n<li>Acompanhamento de obra, registo de horas da equipa, preços de fornecedores em direto</li>\n</ul>\n<p>Uma orçamentação completa que levava dois dias de escritório faz-se em 30 segundos — continua a ser o senhor da revisão e dos preços.</p>\n<p><b>149 € + IVA/mês, sem fidelização, 7 dias de experiência grátis</b> — o custo de uma hora de escritório por semana para nunca mais orçamentar com prejuízo.</p>'
        return subject, body, "Iniciar a minha experiência Pro"
    subject = "As suas obras merecem mais do que uma estimativa: 7 dias de Premium grátis"
    body = f'<p>{hello}</p>\n<p>Já utilizou o ConstruPilot para estimar as suas obras — é um bom começo. Mas entre a estimativa e a obra concluída, há orçamentos a comparar, preços a negociar e um orçamento a cumprir.</p>\n<p><b>A conta Premium foi concebida exatamente para isso:</b></p>\n<ul>\n<li><b>Projetos ilimitados</b> e estimativas detalhadas, artigo a artigo</li>\n<li><b>Análise de orçamentos ilimitada</b>: identifique os artigos sobrefaturados antes de assinar</li>\n<li><b>Comparação e histórico de preços</b> nos grandes fornecedores + alertas de descida</li>\n<li><b>Orçamento inteligente e planeamento</b> da obra</li>\n<li><b>ConstruPilot AI Advisor</b>: as suas perguntas sobre obras, respostas precisas</li>\n<li>Exportação PDF de todos os seus processos</li>\n</ul>\n<p>O Premium custa <b>19 €/mês, sem fidelização</b>, e os <b>7 primeiros dias são grátis</b>. Cancele com um clique na sua conta: não paga nada durante a experiência.</p>'
    return subject, body, "Ativar a minha experiência Premium grátis"


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
            "subject": "Incentivo Premium / Pro (D+3 automático)", "recipients_count": len(users),
            "sent": sent, "failed": failed, "sent_by": "system", "created_at": res["at"]})
    logger.info(f"Upsell J+{days_after_signup}: {res}")
    return res


# ========= Relance J+10 : code promo limité dans le temps =========

PROMO_PERCENT = 20
PROMO_VALID_DAYS = 7


async def _weekly_promo_code() -> tuple[str, str]:
    """Code promo Stripe -20 % (3 mois), valable 7 jours, partagé par les relances de la semaine."""
    import stripe
    monday = datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())
    code = f"RELANCE{PROMO_PERCENT}-{monday.strftime('%y%m%d')}"
    expires = int((monday + timedelta(days=PROMO_VALID_DAYS)).replace(hour=23, minute=59).timestamp())
    cached = await db.app_settings.find_one({"key": "upsell_promo", "code": code}, {"_id": 0})
    if cached:
        return code, cached["expires_iso"]
    if not stripe.api_key:
        raise RuntimeError("Stripe não configurado")
    coupon_id = f"construpilot_relance_{PROMO_PERCENT}"
    try:
        stripe.Coupon.retrieve(coupon_id)
    except Exception:  # noqa: BLE001
        stripe.Coupon.create(id=coupon_id, percent_off=PROMO_PERCENT, duration="repeating",
                             duration_in_months=3, name=f"Lembrete -{PROMO_PERCENT} % (3 meses)")
    existing = stripe.PromotionCode.list(code=code, limit=1).data
    if not existing:
        stripe.PromotionCode.create(promotion={"type": "coupon", "coupon": coupon_id}, code=code,
                                    expires_at=expires, restrictions={"first_time_transaction": True})
    expires_iso = datetime.fromtimestamp(expires, tz=timezone.utc).isoformat()
    await db.app_settings.update_one({"key": "upsell_promo"},
                                     {"$set": {"key": "upsell_promo", "code": code, "expires_iso": expires_iso}},
                                     upsert=True)
    return code, expires_iso


def _template_j10(user: dict, code: str, expires_iso: str) -> tuple[str, str, str]:
    first = (user.get("name") or "").split(" ")[0].strip()
    hello = f'Olá {first},' if first else "Bom dia,"
    pro = user.get("account_type") in ("pro", "pro_business") or user.get("role") == "pro"
    until = datetime.fromisoformat(expires_iso).strftime("%d/%m")
    plan = "Pro" if pro else "Premium"
    price = "149 €" if pro else "19 €"
    subject = f'-{PROMO_PERCENT} % durante 3 meses no ConstruPilot {plan} — até {until}'
    pitch = ("o seu próximo orçamento pode ser calculado em 30 segundos, aos seus preços, com a margem visível capítulo a capítulo."
             if pro else "os seus próximos orçamentos podem ser comparados artigo a artigo antes de assinar.")
    body = f'<p>{hello}</p>\n<p>A sua conta ConstruPilot continua gratuita — e entretanto, {pitch}</p>\n<p>Para ajudar a decidir, aqui fica um incentivo: <b>-{PROMO_PERCENT} % durante 3 meses</b> na subscrição {plan}\n({price} + IVA/mês), com o código:</p>\n<p style="text-align:center;font-size:22px;letter-spacing:2px;font-weight:bold;background:#F1F5F9;padding:14px;border-radius:8px">{code}</p>\n<p>O código é válido <b>até {until}</b>, a introduzir no momento do pagamento. Sempre sem fidelização, 7 dias de experiência incluídos.</p>'
    return subject, body, f'Ativar a minha oferta -{PROMO_PERCENT} %'


async def run_upsell_j10_emails(days_after_signup: int = 10, limit: int = 200) -> dict:
    from engines.emailer import send_email, wrap_html
    from routes.emails import build_unsubscribe_url
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_after_signup)).isoformat()
    q = {
        "created_at": {"$lte": cutoff},
        "upsell_email_sent_at": {"$exists": True, "$nin": ["skipped"]},
        "upsell_j10_sent_at": {"$exists": False},
        "email_marketing_opt_out": {"$ne": True},
        "role": {"$nin": ["admin"]},
        "$or": [{"active_plan_id": {"$exists": False}}, {"active_plan_id": None},
                {"active_plan_id": {"$nin": list(PAID_PLANS)}}],
    }
    users = await db.users.find(q, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "role": 1,
                                    "account_type": 1}).limit(limit).to_list(limit)
    if not users:
        return {"sent": 0, "failed": 0, "candidates": 0}
    code, expires_iso = await _weekly_promo_code()
    sent = failed = 0
    for u in users:
        email = (u.get("email") or "").lower()
        subject, body, cta = _template_j10(u, code, expires_iso)
        html = wrap_html(subject, body, cta_url=f"{_front()}/tarifs?promo={code}", cta_label=cta,
                         unsubscribe_url=build_unsubscribe_url(u["user_id"]))
        try:
            await send_email(email, subject, html)
            sent += 1
            status = datetime.now(timezone.utc).isoformat()
        except Exception as e:  # noqa: BLE001
            failed += 1
            status = "failed"
            logger.warning(f"Upsell J+10 failed for {email}: {e}")
        await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"upsell_j10_sent_at": status}})
    res = {"sent": sent, "failed": failed, "candidates": len(users), "code": code,
           "expires": expires_iso, "at": datetime.now(timezone.utc).isoformat()}
    await db.email_campaigns.insert_one({
        "campaign_id": "auto_" + os.urandom(5).hex(), "type": "auto_upsell_j10",
        "subject": f"Lembrete D+10 código {code} (-{PROMO_PERCENT} %)", "recipients_count": len(users),
        "sent": sent, "failed": failed, "sent_by": "system", "created_at": res["at"]})
    logger.info(f"Upsell J+10: {res}")
    return res


# ========= Suivi conversion (par semaine ISO) =========

def _week(iso: str | None) -> str | None:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        y, w, _ = d.isocalendar()
        return f"{y}-S{w:02d}"
    except Exception:  # noqa: BLE001
        return None


async def conversion_stats(weeks: int = 12) -> dict:
    """Pour chaque semaine d'envoi : emails J+3 / J+10 envoyés et abonnements payants souscrits ensuite."""
    users = await db.users.find(
        {"$or": [{"upsell_email_sent_at": {"$exists": True}}, {"upsell_j10_sent_at": {"$exists": True}}]},
        {"_id": 0, "user_id": 1, "upsell_email_sent_at": 1, "upsell_j10_sent_at": 1, "active_plan_id": 1}
    ).to_list(20000)
    ids = [u["user_id"] for u in users]
    ents = await db.entitlements.find(
        {"user_id": {"$in": ids}, "status": "active", "plan_id": {"$in": list(PAID_PLANS)}},
        {"_id": 0, "user_id": 1, "granted_at": 1, "plan_id": 1}).to_list(20000)
    paid_at = {}
    for e in ents:
        g = e.get("granted_at") or ""
        if e["user_id"] not in paid_at or g < paid_at[e["user_id"]]:
            paid_at[e["user_id"]] = g
    rows: dict[str, dict] = {}
    tot = {"j3_sent": 0, "j10_sent": 0, "conv_j3": 0, "conv_j10": 0}

    def row(w):
        return rows.setdefault(w, {"week": w, "j3_sent": 0, "j10_sent": 0, "conv_j3": 0, "conv_j10": 0})

    for u in users:
        j3, j10 = u.get("upsell_email_sent_at"), u.get("upsell_j10_sent_at")
        pay = paid_at.get(u["user_id"])
        if j3 and j3 not in ("skipped", "failed") and _week(j3):
            row(_week(j3))["j3_sent"] += 1
            tot["j3_sent"] += 1
        if j10 and j10 != "failed" and _week(j10):
            row(_week(j10))["j10_sent"] += 1
            tot["j10_sent"] += 1
        if not pay:
            continue
        if j10 and j10 != "failed" and pay >= j10:
            row(_week(j10))["conv_j10"] += 1
            tot["conv_j10"] += 1
        elif j3 and j3 not in ("skipped", "failed") and pay >= j3:
            row(_week(j3))["conv_j3"] += 1
            tot["conv_j3"] += 1
    out = sorted(rows.values(), key=lambda r: r["week"], reverse=True)[:weeks]
    for r in out + [tot]:
        r["rate_j3"] = round(r["conv_j3"] / r["j3_sent"] * 100, 1) if r["j3_sent"] else None
        r["rate_j10"] = round(r["conv_j10"] / r["j10_sent"] * 100, 1) if r["j10_sent"] else None
    return {"weeks": out, "total": tot}
