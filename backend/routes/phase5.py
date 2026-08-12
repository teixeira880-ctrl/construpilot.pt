"""Routes Phase 5 : White Label + Portail Fournisseurs + Enterprise + Docs.

Toutes ces features sont gouvernées par des feature flags configurables via /api/admin.
"""
from datetime import datetime, timezone
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from core.db import db
from core.security import current_user, admin_user

router = APIRouter(tags=["phase5"])


def _now():
    return datetime.now(timezone.utc).isoformat()


# =============== WHITE LABEL ===============

class WhiteLabelConfigIn(BaseModel):
    tenant_slug: str
    partner_name: str
    primary_color: str = "#FF5A00"
    logo_url: str | None = None
    hero_title: str | None = None
    hero_subtitle: str | None = None
    hide_landing_content: bool = False
    custom_domain: str | None = None
    active: bool = True


@router.get("/whitelabel/config")
async def get_whitelabel(tenant: str):
    """Public: le frontend peut charger la config d'un tenant via ?tenant=slug."""
    doc = await db.whitelabel_tenants.find_one({"tenant_slug": tenant, "active": True},
                                               {"_id": 0})
    if not doc:
        return {"tenant_slug": None, "default": True}
    return doc


@router.get("/admin/whitelabel")
async def list_whitelabel(admin=Depends(admin_user)):
    return await db.whitelabel_tenants.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/admin/whitelabel")
async def upsert_whitelabel(body: WhiteLabelConfigIn, admin=Depends(admin_user)):
    doc = body.model_dump()
    doc["updated_at"] = _now()
    await db.whitelabel_tenants.update_one(
        {"tenant_slug": doc["tenant_slug"]},
        {"$set": doc, "$setOnInsert": {"created_at": _now()}}, upsert=True)
    return doc


@router.delete("/admin/whitelabel/{tenant_slug}")
async def delete_whitelabel(tenant_slug: str, admin=Depends(admin_user)):
    await db.whitelabel_tenants.delete_one({"tenant_slug": tenant_slug})
    return {"ok": True}


# =============== PORTAIL FOURNISSEURS ===============

class SupplierClaimIn(BaseModel):
    supplier_key: str
    contact_name: str
    contact_email: EmailStr


@router.post("/suppliers/claim")
async def claim_supplier(body: SupplierClaimIn, user=Depends(current_user)):
    """Un user réclame la propriété d'un fournisseur (validation admin ensuite)."""
    doc = body.model_dump()
    doc.update({"user_id": user["user_id"], "verified": False,
                "status": "pending", "created_at": _now()})
    await db.supplier_owners.update_one(
        {"supplier_key": body.supplier_key, "user_id": user["user_id"]},
        {"$set": doc}, upsert=True)
    return {"ok": True, "status": "pending"}


async def _resolve_supplier(user_id: str) -> str | None:
    if not user_id:
        return None
    doc = await db.supplier_owners.find_one({"user_id": user_id, "verified": True},
                                            {"_id": 0, "supplier_key": 1})
    return doc.get("supplier_key") if doc else None


@router.get("/suppliers/dashboard")
async def supplier_dashboard(days: int = 30, user=Depends(current_user)):
    """Dashboard fournisseur : clics, redirections, top produits, GMV, commissions."""
    sup = await _resolve_supplier(user["user_id"])
    if not sup and user.get("role") == "admin":
        sup = "leroymerlin"  # fallback admin
    if not sup:
        return {"verified": False, "message": "Réclamez votre fournisseur via /suppliers/claim"}
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    evs = await db.affiliate_events.find(
        {"supplier_key": sup, "at": {"$gte": since}},
        {"_id": 0}).to_list(50000)
    counts = Counter(e["event"] for e in evs)
    urls = Counter(e.get("product_url") for e in evs if e.get("product_url"))
    top_products = [{"url": u, "clicks": c} for u, c in urls.most_common(10)]
    queries = Counter(e.get("query") for e in evs if e.get("query"))
    top_queries = [{"query": q, "count": c} for q, c in queries.most_common(10)]
    gmv_cents = sum(e.get("amount_cents", 0) for e in evs if e["event"] == "purchase_confirmed")
    commission_cents = sum(e.get("commission_cents", 0) for e in evs if e["event"] == "purchase_confirmed")
    return {
        "verified": True,
        "supplier_key": sup,
        "days": days,
        "clicks": counts.get("affiliate_click", 0),
        "redirects": counts.get("supplier_redirect", 0),
        "conversions": counts.get("purchase_confirmed", 0),
        "gmv_cents": gmv_cents,
        "gmv_eur": round(gmv_cents / 100, 2),
        "commission_cents": commission_cents,
        "commission_eur": round(commission_cents / 100, 2),
        "top_products": top_products,
        "top_queries": top_queries,
    }


@router.post("/admin/suppliers/{claim_id}/verify")
async def verify_supplier_claim(claim_id: str, admin=Depends(admin_user)):
    r = await db.supplier_owners.update_one(
        {"user_id": claim_id} if "@" not in claim_id else {"contact_email": claim_id},
        {"$set": {"verified": True, "status": "verified", "verified_at": _now()}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Réclamation introuvable")
    return {"ok": True}


@router.get("/admin/suppliers/claims")
async def list_claims(admin=Depends(admin_user)):
    return await db.supplier_owners.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


# =============== ENTERPRISE LEADS ===============

class EnterpriseLeadIn(BaseModel):
    company_name: str
    contact_name: str
    contact_email: EmailStr
    contact_phone: str | None = None
    company_size: str | None = None  # < 50 | 50-200 | 200-1000 | > 1000
    role: str | None = None
    use_case: str
    volume_estimate: str | None = None
    sso_required: bool = False
    sla_required: bool = False
    message: str | None = None


@router.post("/enterprise/contact")
async def enterprise_contact(body: EnterpriseLeadIn):
    doc = body.model_dump()
    doc.update({"lead_id": f"ent_{int(datetime.now(timezone.utc).timestamp()*1000)}",
                "status": "new", "score": _score_enterprise(doc),
                "created_at": _now()})
    await db.enterprise_leads.insert_one(dict(doc))
    doc.pop("_id", None)
    # Envoi email interne (best effort)
    try:
        from engines import emailer
        html = emailer.wrap_html(
            "Nouveau contact Enterprise",
            f"""<p><b>{doc['company_name']}</b> — {doc.get('company_size') or ''}</p>
<p>Contact : {doc['contact_name']} ({doc['contact_email']})</p>
<p><b>Use case :</b> {doc['use_case']}</p>
<p><b>Score interne :</b> {doc['score']}/100</p>
<p>Message : {doc.get('message') or '—'}</p>""")
        import os
        to = os.environ.get("ENTERPRISE_ALERT_EMAIL") or "onboarding@resend.dev"
        await emailer.send_email(to, f"[Enterprise] {doc['company_name']}", html)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Enterprise notify email failed: {e}")
    return {"ok": True, "lead_id": doc["lead_id"], "message":
            "Merci — notre équipe vous recontacte sous 48 heures ouvrées."}


def _score_enterprise(doc: dict) -> int:
    score = 20
    size = doc.get("company_size") or ""
    score += {"< 50": 10, "50-200": 25, "200-1000": 40, "> 1000": 55}.get(size, 5)
    if doc.get("sso_required"): score += 10
    if doc.get("sla_required"): score += 10
    if len(doc.get("use_case", "")) > 100: score += 10
    return min(100, score)


@router.get("/admin/enterprise/leads")
async def list_enterprise_leads(admin=Depends(admin_user)):
    return await db.enterprise_leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
