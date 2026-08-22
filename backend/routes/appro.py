"""Approvisionnement — chiffrage transverse + envoi e-mail des bons de commande.
Module « Analyse technique & Approvisionnement IA » — Prix fournisseur & e-mail."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import pricing, order_pdf
from engines.emailer import send_email_with_pdf, wrap_company_html

router = APIRouter(prefix="/pro/appro", tags=["appro"])


def _now():
    return datetime.now(timezone.utc).isoformat()


class PriceIn(BaseModel):
    items: list[dict] = Field(default_factory=list)
    supplier_id: str | None = None
    overrides: dict = Field(default_factory=dict)


@router.post("/price")
async def price(body: PriceIn, user=Depends(current_user)) -> dict:
    """Chiffre un bordereau : override manuel > catalogue fournisseur > DPGF."""
    supplier = None
    if body.supplier_id:
        supplier = await db.suppliers.find_one(
            {"supplier_id": body.supplier_id, "user_id": user["user_id"]}, {"_id": 0})
    dpgf = await db.company_price_libraries.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "designation": 1, "unit": 1, "unit_price": 1}).to_list(2000)
    res = pricing.price_items(body.items, supplier, dpgf, body.overrides)
    return res


class EmailIn(BaseModel):
    to: str | None = None            # override adresse fournisseur
    cc_self: bool = True             # copie à l'utilisateur
    message: str | None = None
    priced_items: list[dict] | None = None   # items chiffrés (avec unit_price/line_total)


@router.get("/orders")
async def list_orders(user=Depends(current_user)) -> dict:
    cur = db.material_orders.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return {"items": await cur.to_list(200)}


@router.post("/orders/{order_id}/email")
async def email_order(order_id: str, body: EmailIn, user=Depends(current_user)) -> dict:
    from routes.plans_common import _resolve_branding
    order = await db.material_orders.find_one(
        {"order_id": order_id, "user_id": user["user_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Bon de commande introuvable")
    if body.priced_items:
        order["items"] = body.priced_items
    supplier = order.get("supplier") or {}
    to = body.to or supplier.get("email")
    if not to:
        raise HTTPException(422, "Aucune adresse e-mail fournisseur")

    branding = await _resolve_branding(user["user_id"]) or {}
    company_name = branding.get("company_name") or user.get("name") or "ConstruPilot"
    pdf = order_pdf.build_order_pdf(order, {"company_name": company_name})
    csv_txt = _csv_from_items(order["items"])

    type_lbl = {"acier": "ferraillage", "etancheite": "étanchéité",
                "toiture": "toiture", "vrd": "VRD"}.get(order.get("type"), "matériaux")
    subject = f"Bon de commande {type_lbl} — {company_name} (n° {order_id})"
    body_html = (f"<p>Bonjour,</p><p>{body.message or f'Veuillez trouver ci-joint notre bon de commande {type_lbl}.'}</p>"
                 f"<p>Le détail est en pièce jointe (PDF + CSV). Merci de nous confirmer "
                 f"disponibilités et délai de livraison.</p>"
                 f"<p>Cordialement,<br/>{company_name}</p>")
    html = wrap_company_html(subject, body_html, company_name=company_name,
                             logo_b64=branding.get("logo_b64"),
                             company_email=user.get("email"))
    try:
        await send_email_with_pdf(
            to, subject, html, pdf, filename=f"bon_commande_{order_id}.pdf",
            cc=user.get("email") if body.cc_self else None,
            extra_attachments=[{"filename": f"bon_commande_{order_id}.csv",
                                "content": csv_txt.encode("utf-8"),
                                "content_type": "text/csv"}],
            reply_to=user.get("email"), from_name=company_name)
    except Exception as e:
        raise HTTPException(502, f"Envoi e-mail impossible : {e}")

    await db.material_orders.update_one(
        {"order_id": order_id, "user_id": user["user_id"]},
        {"$set": {"status": "envoyé", "sent_to": to, "sent_at": _now(),
                  "items": order["items"]}})
    return {"ok": True, "to": to, "cc": user.get("email") if body.cc_self else None}


def _csv_from_items(items: list) -> str:
    priced = any(it.get("unit_price") for it in items)
    head = ["Designation", "Quantite", "Unite", "Commandable_qty", "Commandable_unite"]
    if priced:
        head += ["PU_HT", "Total_HT"]
    rows = [";".join(head)]
    for it in items:
        r = [it.get("designation", ""), it.get("qty", ""), it.get("unit", ""),
             it.get("commandable_qty", ""), it.get("commandable_unit", "")]
        if priced:
            r += [it.get("unit_price", ""), it.get("line_total", "")]
        rows.append(";".join(str(x) for x in r))
    return "\n".join(rows)
