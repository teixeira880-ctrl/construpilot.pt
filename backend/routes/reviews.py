"""Avis Clients — chantier terminé → demande d'avis automatique + collecte publique.

Flux :
1. Le pro marque un devis signé comme « chantier terminé » (`POST /reviews/request/{log_id}`).
   → un email avec un lien public part au client.
2. Le client note (1-5) + laisse un commentaire via `POST /reviews/collect/{token}`.
3. Les avis publiés sont affichés sur les futurs devis PDF + la page « Mes avis ».
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user, admin_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reviews"], prefix="/reviews")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frontend_url() -> str:
    return (os.getenv("FRONTEND_URL") or "https://construpilot.fr").rstrip("/")


async def get_reviews_for_user(user_id: str, limit: int = 3) -> dict:
    """Moyenne + derniers avis publiés d'un pro (réutilisé par le PDF devis)."""
    docs = await db.reviews.find(
        {"user_id": user_id, "submitted": True, "published": True},
        {"_id": 0, "rating": 1, "comment": 1, "author_name": 1, "submitted_at": 1},
    ).sort("submitted_at", -1).to_list(500)
    if not docs:
        return {"count": 0, "average": 0.0, "items": []}
    avg = round(sum(d.get("rating") or 0 for d in docs) / len(docs), 1)
    items = [d for d in docs if (d.get("comment") or "").strip()][:limit]
    return {"count": len(docs), "average": avg, "items": items}


async def _send_review_request_email(to: str, client_name: str, company: str, url: str) -> None:
    from engines.emailer import send_email, wrap_html
    hello = f"Bonjour {client_name}," if client_name else "Bonjour,"
    inner = (
        f"<p>{hello}</p>"
        f"<p>Votre chantier avec <b>{company}</b> est terminé. Nous espérons que "
        f"le résultat est à la hauteur de vos attentes&nbsp;!</p>"
        f"<p>Votre avis compte énormément. Prenez 30 secondes pour noter votre "
        f"expérience — cela aide {company} à s'améliorer et rassure les futurs clients.</p>"
    )
    html = wrap_html(f"Votre avis sur {company}", inner,
                     cta_url=url, cta_label="Laisser mon avis")
    try:
        await send_email(to, f"Comment s'est passé votre chantier avec {company} ?", html)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Review request email failed: {e}")


# ---- PRO : marquer chantier terminé + déclencher la demande d'avis ----------

@router.post("/request/{log_id}")
async def request_review(log_id: str, user=Depends(current_user)) -> dict:
    """Marque le chantier (devis signé) terminé + envoie une demande d'avis au client."""
    send = await db.quote_sends.find_one(
        {"log_id": log_id, "user_id": user["user_id"]}, {"_id": 0})
    if not send:
        raise HTTPException(404, "Devis introuvable")
    client_email = send.get("client_email")
    if not client_email:
        raise HTTPException(400, "Aucun email client sur ce devis")

    existing = await db.reviews.find_one({"log_id": log_id}, {"_id": 0})
    if existing and existing.get("submitted"):
        raise HTTPException(400, "Ce client a déjà laissé un avis")

    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(user["user_id"]) or {}
    sender = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "name": 1})
    company = branding.get("company_name") or (sender or {}).get("name") or "ConstruPilot"

    token = existing["token"] if existing else secrets.token_urlsafe(24)
    if not existing:
        await db.reviews.insert_one({
            "review_id": "rev_" + secrets.token_hex(6),
            "token": token,
            "user_id": user["user_id"],
            "log_id": log_id,
            "plan_id": send.get("plan_id"),
            "client_email": client_email,
            "client_name": send.get("client_name") or "",
            "author_name": send.get("client_name") or "",
            "company_name": company,
            "requested_at": _now(),
            "submitted": False,
            "published": True,
            "rating": None,
            "comment": "",
        })
    else:
        await db.reviews.update_one(
            {"token": token}, {"$set": {"requested_at": _now(), "company_name": company}})

    await db.quote_sends.update_one(
        {"log_id": log_id},
        {"$set": {"worksite_status": "completed", "completed_at": _now(),
                  "review_requested": True}})

    review_url = f"{_frontend_url()}/avis/{token}"
    await _send_review_request_email(
        client_email, send.get("client_name") or "", company, review_url)
    return {"ok": True, "review_url": review_url}


# ---- PUBLIC : collecte de l'avis client -------------------------------------

@router.get("/collect/{token}")
async def get_review_meta(token: str) -> dict:
    r = await db.reviews.find_one({"token": token}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Lien d'avis invalide ou expiré")
    return {
        "company_name": r.get("company_name") or "ConstruPilot",
        "client_name": r.get("client_name") or "",
        "submitted": bool(r.get("submitted")),
        "rating": r.get("rating"),
        "comment": r.get("comment") or "",
    }


class ReviewSubmitIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""
    author_name: str | None = None


@router.post("/collect/{token}")
async def submit_review(token: str, body: ReviewSubmitIn) -> dict:
    r = await db.reviews.find_one({"token": token}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Lien d'avis invalide")
    if r.get("submitted"):
        raise HTTPException(400, "Avis déjà envoyé — merci !")
    author = (body.author_name or r.get("client_name") or "Client").strip()[:80]
    await db.reviews.update_one({"token": token}, {"$set": {
        "submitted": True,
        "submitted_at": _now(),
        "rating": body.rating,
        "comment": (body.comment or "").strip()[:1000],
        "author_name": author,
        "published": True,
    }})
    await db.notifications.insert_one({
        "notif_id": "n_" + secrets.token_hex(5),
        "user_id": r["user_id"], "type": "review_received",
        "log_id": r.get("log_id"),
        "message": f"{author} a laissé un avis {body.rating}/5.",
        "created_at": _now(), "read": False,
    })
    return {"ok": True}


# ---- PRO : gestion de mes avis ----------------------------------------------

@router.get("/me")
async def my_reviews(user=Depends(current_user)) -> dict:
    docs = await db.reviews.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("requested_at", -1).to_list(500)
    submitted = [d for d in docs if d.get("submitted")]
    avg = (round(sum(d.get("rating") or 0 for d in submitted) / len(submitted), 1)
           if submitted else 0.0)
    return {
        "average": avg,
        "count": len(submitted),
        "pending": len(docs) - len(submitted),
        "reviews": docs,
    }


class PublishIn(BaseModel):
    published: bool


# ---- TÉMOIGNAGES DU SITE (produit ConstruPilot) — collecte publique + modération ----

class SiteReviewIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    role: str = Field(default="", max_length=80)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=5, max_length=600)


def _clean_site(d: dict) -> dict:
    return {"review_id": d.get("review_id"), "name": d.get("name", ""),
            "role": d.get("role", ""), "rating": d.get("rating", 5),
            "comment": d.get("comment", ""), "created_at": d.get("created_at"),
            "approved": d.get("approved", False)}


@router.post("/site")
async def submit_site_review(body: SiteReviewIn) -> dict:
    """Avis public sur ConstruPilot (publié après validation admin)."""
    await db.site_reviews.insert_one({
        "review_id": "srev_" + secrets.token_hex(6),
        "name": body.name.strip(), "role": body.role.strip(),
        "rating": int(body.rating), "comment": body.comment.strip(),
        "approved": False, "created_at": _now(),
    })
    return {"ok": True}


@router.get("/site")
async def list_site_reviews(limit: int = 12) -> dict:
    cur = db.site_reviews.find({"approved": True}, {"_id": 0}).sort("created_at", -1).limit(min(limit, 30))
    return {"reviews": [_clean_site(d) for d in await cur.to_list(30)]}


@router.get("/site/pending", dependencies=[Depends(admin_user)])
async def pending_site_reviews() -> dict:
    cur = db.site_reviews.find({"approved": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(100)
    return {"reviews": [_clean_site(d) for d in await cur.to_list(100)]}


@router.post("/site/{review_id}/approve", dependencies=[Depends(admin_user)])
async def approve_site_review(review_id: str) -> dict:
    r = await db.site_reviews.update_one({"review_id": review_id}, {"$set": {"approved": True}})
    if not r.matched_count:
        raise HTTPException(404, "Avis introuvable")
    return {"ok": True}


@router.delete("/site/{review_id}", dependencies=[Depends(admin_user)])
async def delete_site_review(review_id: str) -> dict:
    await db.site_reviews.delete_one({"review_id": review_id})
    return {"ok": True}


@router.patch("/{review_id}/publish")
async def toggle_publish(review_id: str, body: PublishIn,
                         user=Depends(current_user)) -> dict:
    res = await db.reviews.update_one(
        {"review_id": review_id, "user_id": user["user_id"]},
        {"$set": {"published": body.published}})
    if not res.matched_count:
        raise HTTPException(404, "Avis introuvable")
    return {"ok": True}
