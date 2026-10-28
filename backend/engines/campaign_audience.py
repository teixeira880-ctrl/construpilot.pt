"""Destinatários das campanhas de e-mail (Agente CEO).

Uma campanha promocional só pode ser enviada a quem aceitou recebê-la (RGPD e
Lei n.º 41/2004, art. 13.º-A — comunicações não solicitadas):
  • subscritores ativos da newsletter (inscrição explícita no blog) ;
  • contas ConstruPilot que marcaram « Quero receber novidades e ofertas »
    (`marketing_consent: True`), na inscrição, nas preferências ou no aviso
    mostrado no painel.

Cada destinatário recebe um link de cancelamento próprio. Um e-mail presente
nas duas listas só recebe uma vez. Cancelar (por qualquer link) desliga as duas
coisas: a subscrição da newsletter e o consentimento da conta.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

UNSUB_PATH = "/api/newsletter/unsubscribe?token="


def _norm(email: str | None) -> str:
    return (email or "").strip().lower()


def merge_recipients(subscribers: list[dict], consenting_users: list[dict]) -> list[dict]:
    """Junta subscritores ativos e contas com consentimento, sem duplicados.

    `subscribers`: [{email, token}] ; `consenting_users`: [{email,
    marketing_unsub_token}]. Devolve [{email, token, source}] — source =
    "newsletter" | "account".
    """
    out: dict[str, dict] = {}
    for s in subscribers:
        e = _norm(s.get("email"))
        if e and e not in out:
            out[e] = {"email": e, "token": s.get("token") or "", "source": "newsletter"}
    for u in consenting_users:
        e = _norm(u.get("email"))
        if e and e not in out:
            out[e] = {"email": e, "token": u.get("marketing_unsub_token") or "", "source": "account"}
    return list(out.values())


async def campaign_recipients(db, limit: int = 20000) -> list[dict]:
    subs = await db.newsletter_subscribers.find(
        {"unsubscribed_at": None}, {"_id": 0, "email": 1, "token": 1}).to_list(limit)
    users = await db.users.find(
        {"marketing_consent": True, "email": {"$nin": [None, ""]}},
        {"_id": 0, "user_id": 1, "email": 1, "marketing_unsub_token": 1}).to_list(limit)
    # Garante um token de cancelamento para cada conta (contas antigas).
    for u in users:
        if not u.get("marketing_unsub_token"):
            tok = secrets.token_urlsafe(24)
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"marketing_unsub_token": tok}})
            u["marketing_unsub_token"] = tok
    return merge_recipients(subs, users)


def consent_fields(consent: bool, source: str) -> dict:
    """Campos guardados na conta quando a pessoa decide (aceita ou recusa)."""
    return {
        "marketing_consent": bool(consent),
        "marketing_consent_at": datetime.now(timezone.utc).isoformat(),
        "marketing_consent_source": source[:40],
    }
