"""Email marketing opt-out (unsubscribe) — no auth needed, token-based.

Endpoints:
- GET /api/emails/unsubscribe/{token} — sets `email_marketing_opt_out=True` on the user
  identified by the token (HMAC of user_id). Returns a small HTML page.
- Helper `build_unsubscribe_url(user_id)` used by other engines to inject the link.
"""
import hashlib
import hmac
import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from core.db import db

router = APIRouter(prefix="/emails", tags=["emails"])

BRAND = "#FF5A00"


def _secret() -> bytes:
    return (os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY") or "dev").encode()


def _sign(user_id: str) -> str:
    return hmac.new(_secret(), user_id.encode(), hashlib.sha256).hexdigest()[:24]


def make_token(user_id: str) -> str:
    """Format: `<user_id>.<hmac-first-24-chars>`."""
    return f"{user_id}.{_sign(user_id)}"


def build_unsubscribe_url(user_id: str) -> str:
    base = os.environ.get("PUBLIC_APP_URL") or "https://construpilot.fr"
    return f"{base.rstrip('/')}/api/emails/unsubscribe/{make_token(user_id)}"


def _verify(token: str) -> str | None:
    if "." not in token:
        return None
    user_id, sig = token.rsplit(".", 1)
    return user_id if hmac.compare_digest(sig, _sign(user_id)) else None


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{title} · ConstruPilot</title></head>
<body style="margin:0;background:#f5f5f7;font-family:Arial,sans-serif;color:#0A0D14;
padding:60px 20px">
<div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;
border-radius:6px;padding:36px;text-align:center">
<div style="font-size:24px;font-weight:800;letter-spacing:-0.5px;color:{BRAND}">
ConstruPilot</div>
<h1 style="font-size:20px;margin:24px 0 12px">{title}</h1>
<div style="font-size:14px;line-height:1.55;color:#334155">{body}</div>
<div style="margin-top:32px">
<a href="https://construpilot.fr" style="background:{BRAND};color:#fff;text-decoration:none;
padding:12px 24px;border-radius:4px;font-size:14px;font-weight:600;display:inline-block">
Retour à ConstruPilot</a></div></div></body></html>"""


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str):
    user_id = _verify(token)
    if not user_id:
        return HTMLResponse(_page("Lien invalide",
                                  "<p>Ce lien de désinscription est invalide ou a expiré.</p>"),
                            status_code=400)
    res = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"email_marketing_opt_out": True,
                   "email_opt_out_at": _now_iso()}},
    )
    if res.matched_count == 0:
        return HTMLResponse(_page("Utilisateur introuvable",
                                  "<p>Nous n'avons pas retrouvé votre compte.</p>"),
                            status_code=404)
    return HTMLResponse(_page(
        "Désinscription confirmée",
        "<p>Vous ne recevrez plus d'emails marketing ConstruPilot.</p>"
        "<p style='color:#64748B;font-size:12px;margin-top:16px'>"
        "Vous continuerez à recevoir les emails transactionnels essentiels "
        "(devis signés, alertes de sécurité, factures).</p>"
    ))


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ============ MODÈLES DE MESSAGE (iter67) ============
# Messages personnalisés réutilisables pour l'envoi de rapports par email.

import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import current_user

MAX_TEMPLATES = 20


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    body: str = Field(min_length=1, max_length=2000)


@router.get("/templates")
async def list_templates(user=Depends(current_user)) -> dict:
    """Liste les modèles de message de l'utilisateur (plus récents en premier)."""
    docs = await db.message_templates.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(MAX_TEMPLATES)
    return {"templates": docs}


@router.post("/templates")
async def create_template(body: TemplateIn, user=Depends(current_user)) -> dict:
    """Enregistre un modèle de message (max 20 par utilisateur)."""
    count = await db.message_templates.count_documents({"user_id": user["user_id"]})
    if count >= MAX_TEMPLATES:
        raise HTTPException(422, f"Maximum {MAX_TEMPLATES} modèles — supprimez-en un d'abord")
    doc = {
        "template_id": f"tpl_{secrets.token_hex(6)}",
        "user_id": user["user_id"],
        "name": body.name.strip()[:60],
        "body": body.body.strip()[:2000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.message_templates.insert_one({**doc})
    return {"ok": True, "template": doc}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, user=Depends(current_user)) -> dict:
    """Supprime un modèle de message."""
    res = await db.message_templates.delete_one(
        {"template_id": template_id, "user_id": user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Modèle introuvable")
    return {"ok": True}
