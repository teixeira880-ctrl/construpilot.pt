"""Page publique entreprise (site vitrine) + personnalisation en-tête / pied de page des PDF."""
import asyncio
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.rate_limit import limiter
from core.security import current_user, pro_required
from core.uploads import validate_upload, ALLOWED_IMAGE
from engines import storage
from engines.assistant_media import normalize_attachment

router = APIRouter(tags=["company-page"])
PAGE_FIELDS = ("brand_header_text", "brand_footer_text", "brand_accent_color", "brand_doc_layout", "brand_tagline", "brand_description",
               "public_slug", "public_published", "public_show_reviews", "public_contact_phone", "public_website", "showcase_photos")
MAX_PHOTOS = 24


def _slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", t)).strip("-")[:60] or f"entreprise-{uuid.uuid4().hex[:6]}"


class PageIn(BaseModel):
    header_text: Optional[str] = Field(None, max_length=300)
    footer_text: Optional[str] = Field(None, max_length=600)
    accent_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    doc_layout: Optional[str] = Field(None, pattern=r"^(bandeau|classique|compact|essentiel|detaille|signature)$")
    tagline: Optional[str] = Field(None, max_length=140)
    description: Optional[str] = Field(None, max_length=2000)
    slug: Optional[str] = Field(None, max_length=60)
    published: Optional[bool] = None
    show_reviews: Optional[bool] = None
    contact_phone: Optional[str] = Field(None, max_length=30)
    website: Optional[str] = Field(None, max_length=200)


async def pdf_customization(user_id: str) -> dict:
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "brand_header_text": 1, "brand_footer_text": 1,
                                                       "brand_accent_color": 1, "brand_doc_layout": 1}) or {}
    return {"header_text": u.get("brand_header_text"), "footer_text": u.get("brand_footer_text"),
            "accent_color": u.get("brand_accent_color"), "doc_layout": u.get("brand_doc_layout")}


def _public_payload(u: dict) -> dict:
    return {"slug": u.get("public_slug"), "published": bool(u.get("public_published")), "company_name": u.get("brand_company_name") or u.get("company") or u.get("name"),
            "tagline": u.get("brand_tagline"), "description": u.get("brand_description"), "contact_line": u.get("brand_contact_line"),
            "email": u.get("brand_company_email"), "phone": u.get("public_contact_phone"), "website": u.get("public_website"),
            "address": " ".join(filter(None, [u.get("brand_address"), u.get("brand_postal"), u.get("brand_city")])) or None,
            "country": u.get("brand_country"), "certifications": u.get("brand_certifications") or [], "service_zones": u.get("service_zones") or [],
            "has_logo": bool(u.get("brand_logo_b64")), "accent_color": u.get("brand_accent_color") or "#15803D",
            "doc_layout": u.get("brand_doc_layout") or "bandeau",
            "photos": [{k: p.get(k) for k in ("photo_id", "title", "description", "created_at")} for p in (u.get("showcase_photos") or [])],
            "header_text": u.get("brand_header_text"), "footer_text": u.get("brand_footer_text"), "show_reviews": u.get("public_show_reviews", True)}


@router.get("/company/page")
async def get_page(user=Depends(pro_required)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    if not u.get("public_slug"):
        slug = _slugify(u.get("brand_company_name") or u.get("company") or u.get("name") or "")
        while await db.users.find_one({"public_slug": slug, "user_id": {"$ne": user["user_id"]}}, {"_id": 1}):
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"public_slug": slug}})
        u["public_slug"] = slug
    return {**_public_payload(u), "user_id": user["user_id"], "public_url": f"/entreprise/{u['public_slug']}"}


@router.put("/company/page")
async def put_page(body: PageIn, user=Depends(pro_required)) -> dict:
    upd = {}
    mapping = {"header_text": "brand_header_text", "footer_text": "brand_footer_text", "accent_color": "brand_accent_color", "doc_layout": "brand_doc_layout", "tagline": "brand_tagline",
               "description": "brand_description", "published": "public_published", "show_reviews": "public_show_reviews",
               "contact_phone": "public_contact_phone", "website": "public_website"}
    for src, dst in mapping.items():
        v = getattr(body, src)
        if v is not None:
            upd[dst] = v.strip() if isinstance(v, str) else v
    if body.slug is not None:
        slug = _slugify(body.slug)
        if await db.users.find_one({"public_slug": slug, "user_id": {"$ne": user["user_id"]}}, {"_id": 1}):
            raise HTTPException(409, "Este endereço já é utilizado por outra empresa.")
        upd["public_slug"] = slug
    if upd:
        upd["public_updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    return await get_page(user)


@router.post("/company/page/photos")
@limiter.limit("60/hour")
async def add_photo(request: Request, response: Response, file: UploadFile = File(...), title: str = Form(""), description: str = Form(""),
                    user=Depends(pro_required)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "showcase_photos": 1}) or {}
    if len(u.get("showcase_photos") or []) >= MAX_PHOTOS:
        raise HTTPException(409, f'Galeria cheia ({MAX_PHOTOS} photos max)')
    file = await validate_upload(file, ALLOWED_IMAGE, max_mb=12)
    data = await file.read(12 * 1024 * 1024 + 1)
    if not data:
        raise HTTPException(400, "Photo vide")
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Fotografia demasiado volumosa (máx. 12 MB)")
    data, mime = await asyncio.to_thread(normalize_attachment, data)
    if not mime.startswith("image/"):
        raise HTTPException(415, "Anexe uma fotografia JPG, PNG ou WEBP")
    photo_id = f"shw_{uuid.uuid4().hex[:12]}"
    path = f"public/showcase/{user['user_id']}/{photo_id}.jpg"
    try:
        await asyncio.to_thread(storage.put_object, path, data, mime)
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "Armazenamento das fotografias momentaneamente indisponível") from None
    photo = {"photo_id": photo_id, "path": path, "mime": mime, "title": title.strip()[:120], "description": description.strip()[:600],
             "created_at": datetime.now(timezone.utc).isoformat()}
    await db.users.update_one({"user_id": user["user_id"]}, {"$push": {"showcase_photos": photo}})
    return {k: photo[k] for k in ("photo_id", "title", "description", "created_at")}


class PhotoMetaIn(BaseModel):
    title: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=600)


@router.patch("/company/page/photos/{photo_id}")
async def update_photo(photo_id: str, body: PhotoMetaIn, user=Depends(pro_required)) -> dict:
    upd = {f"showcase_photos.$.{k}": v.strip() for k, v in (("title", body.title), ("description", body.description)) if v is not None}
    if not upd:
        return {"ok": True}
    r = await db.users.update_one({"user_id": user["user_id"], "showcase_photos.photo_id": photo_id}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "Fotografia não encontrada")
    return {"ok": True}


@router.delete("/company/page/photos/{photo_id}")
async def delete_photo(photo_id: str, user=Depends(pro_required)) -> dict:
    r = await db.users.update_one({"user_id": user["user_id"]}, {"$pull": {"showcase_photos": {"photo_id": photo_id}}})
    if not r.modified_count:
        raise HTTPException(404, "Fotografia não encontrada")
    return {"ok": True}


@router.get("/public/company/{slug}")
async def public_company(slug: str) -> dict:
    u = await db.users.find_one({"public_slug": slug}, {"_id": 0})
    if not u or not u.get("public_published"):
        raise HTTPException(404, "Página não encontrada ou não publicada")
    payload = _public_payload(u)
    payload["user_id"] = u["user_id"]
    if payload["show_reviews"]:
        try:
            from routes.reviews import get_reviews_for_user
            payload["reviews"] = await get_reviews_for_user(u["user_id"], limit=6)
        except Exception:  # noqa: BLE001
            payload["reviews"] = None
    return payload


class QuoteRequestIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field("", max_length=40)
    description: str = Field(..., min_length=10, max_length=3000)
    address: str = Field("", max_length=200)
    postal_code: str = Field("", max_length=12)
    city: str = Field("", max_length=80)
    website: str = Field("", max_length=200)  # honeypot anti-robots : doit rester vide


async def _client_for_request(pro_id: str, body: QuoteRequestIn) -> tuple[str, bool]:
    """Fiche client CRM du pro, dédoublonnée par e-mail (insensible à la casse)."""
    email = body.email.strip().lower()
    existing = await db.clients.find_one({"user_id": pro_id, "email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}, {"_id": 0, "client_id": 1})
    if existing:
        return existing["client_id"], False
    parts = body.name.strip().split(" ", 1)
    now = datetime.now(timezone.utc).isoformat()
    cid = "cli_" + uuid.uuid4().hex[:12]
    await db.clients.insert_one({"client_id": cid, "user_id": pro_id, "first_name": parts[0][:80], "last_name": (parts[1] if len(parts) > 1 else "")[:80],
                                 "company": "", "email": email[:160], "phone": body.phone.strip()[:40], "address": body.address.strip()[:200],
                                 "postal_code": body.postal_code.strip()[:16], "city": body.city.strip()[:80], "siret": "",
                                 "notes": "Potencial cliente criado a partir do formulário da página da empresa.", "source": "company_page",
                                 "created_at": now, "updated_at": now})
    return cid, True


async def _notify_quote_request(pro: dict, lead: dict) -> None:
    name = lead.get("name") or lead.get("email")
    await db.notifications.insert_one({"notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": pro["user_id"], "type": "company_page_lead",
                                       "lead_id": lead["lead_id"], "url": "/mes-demandes", "read": False,
                                       "message": f'Novo pedido de orçamento através da sua página de empresa: {name}',
                                       "created_at": datetime.now(timezone.utc).isoformat()})
    try:
        from engines.emailer import send_email, wrap_html
        from routes.leads import _frontend_url
        html = wrap_html("Novo pedido de orçamento",
                         f"<p>Olá,</p><p><strong>{name}</strong> enviou-lhe um pedido de orçamento a partir da sua página de empresa ConstruPilot.</p><p><em>{(lead.get('description') or '')[:600]}</em></p><p>Contact : {lead.get('email')} {lead.get('phone') or ''}</p>",
                         cta_url=f"{_frontend_url()}/mes-demandes", cta_label="Ver o pedido")
        if pro.get("email"):
            await send_email(pro["email"], f'Novo pedido de orçamento — {name}', html)
    except Exception:  # noqa: BLE001 — l'e-mail est un plus, la demande est déjà enregistrée
        pass


@router.post("/public/company/{slug}/quote-request", status_code=201)
@limiter.limit("5/hour")
async def public_quote_request(slug: str, body: QuoteRequestIn, request: Request, response: Response) -> dict:
    u = await db.users.find_one({"public_slug": slug}, {"_id": 0, "user_id": 1, "email": 1, "public_published": 1, "brand_company_name": 1})
    if not u or not u.get("public_published"):
        raise HTTPException(404, "Página não encontrada ou não publicada")
    if body.website.strip():
        return {"ok": True}
    from routes.leads import _dept_from_text
    client_id, created = await _client_for_request(u["user_id"], body)
    now = datetime.now(timezone.utc).isoformat()
    lead = {"lead_id": f"lead_{uuid.uuid4().hex[:10]}", "user_id": None, "name": body.name.strip(), "email": body.email.strip().lower(),
            "phone": body.phone.strip(), "address": body.address.strip(), "postal_code": body.postal_code.strip(), "city": body.city.strip(),
            "description": body.description.strip(), "source": "company_page", "company_slug": slug, "client_id": client_id,
            "assigned_to": u["user_id"], "assigned_at": now, "handling_status": "nouvelle", "status": "nouveau",
            "department": _dept_from_text(body.postal_code, body.address), "created_at": now}
    await db.leads.insert_one(dict(lead))
    lead.pop("_id", None)
    asyncio.create_task(_notify_quote_request(u, lead))
    return {"ok": True, "lead_id": lead["lead_id"], "client_created": created}


@router.get("/public/company/{slug}/photo/{photo_id}")
async def public_photo(slug: str, photo_id: str):
    u = await db.users.find_one({"public_slug": slug}, {"_id": 0, "user_id": 1, "public_published": 1, "showcase_photos": 1})
    if not u:
        raise HTTPException(404, "Página não encontrada")
    photo = next((p for p in (u.get("showcase_photos") or []) if p.get("photo_id") == photo_id), None)
    if not photo:
        raise HTTPException(404, "Fotografia não encontrada")
    data, _ = await asyncio.to_thread(storage.get_object, photo["path"])
    return Response(data, media_type=photo.get("mime") or "image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/company/page/photo/{photo_id}")
async def own_photo(photo_id: str, user=Depends(current_user)):
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "showcase_photos": 1}) or {}
    photo = next((p for p in (u.get("showcase_photos") or []) if p.get("photo_id") == photo_id), None)
    if not photo:
        raise HTTPException(404, "Fotografia não encontrada")
    data, _ = await asyncio.to_thread(storage.get_object, photo["path"])
    return Response(data, media_type=photo.get("mime") or "image/jpeg", headers={"Cache-Control": "private, max-age=600"})
