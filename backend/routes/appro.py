"""Approvisionnement — chiffrage transverse + envoi e-mail des bons de commande.
Module « Analyse technique & Approvisionnement IA » — Prix fournisseur & e-mail."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user, pro_required
from engines import pricing, order_pdf
from engines.emailer import send_email_with_pdf, wrap_company_html

router = APIRouter(prefix="/pro/appro", tags=["appro"], dependencies=[Depends(pro_required)])


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


def _fnum(v):
    try:
        return float(str(v).replace(",", ".").split()[0])
    except (ValueError, TypeError, IndexError):
        return 0.0


class MergeOrdersIn(BaseModel):
    order_ids: list[str] = Field(min_length=2, max_length=40)
    project: str = Field(default="", max_length=160)
    supplier_id: str | None = None


@router.post("/orders/merge")
async def merge_orders(body: MergeOrdersIn, user=Depends(current_user)) -> dict:
    """Fusionne plusieurs bons de commande (issus de plans différents d'un même projet)
    en UNE seule commande, en regroupant les quantités des lignes identiques
    (même désignation + unité)."""
    import uuid
    orders = await db.material_orders.find(
        {"order_id": {"$in": body.order_ids}, "user_id": user["user_id"]}, {"_id": 0}).to_list(40)
    if len(orders) < 2:
        raise HTTPException(400, "Sélectionnez au moins 2 bons de commande valides")

    grouped: dict = {}
    order_seq: list = []
    plan_ids: list = []
    types = set()
    for o in orders:
        types.add(o.get("type"))
        if o.get("plan_id"):
            plan_ids.append(o["plan_id"])
        for it in (o.get("items") or []):
            key = (str(it.get("designation", "")).strip().lower(), str(it.get("unit", "")).strip().lower())
            if key not in grouped:
                grouped[key] = {
                    "designation": it.get("designation", ""),
                    "unit": it.get("unit", ""),
                    "qty": 0.0,
                    "commandable_qty": 0.0,
                    "commandable_unit": it.get("commandable_unit", ""),
                }
                order_seq.append(key)
            g = grouped[key]
            g["qty"] += _fnum(it.get("qty"))
            g["commandable_qty"] += _fnum(it.get("commandable_qty"))
            if not g["commandable_unit"]:
                g["commandable_unit"] = it.get("commandable_unit", "")

    items = []
    for key in order_seq:
        g = grouped[key]
        g["qty"] = round(g["qty"], 3)
        g["commandable_qty"] = round(g["commandable_qty"], 3)
        items.append(g)

    supplier = None
    if body.supplier_id:
        supplier = await db.suppliers.find_one(
            {"supplier_id": body.supplier_id, "user_id": user["user_id"]}, {"_id": 0})
    elif len({(o.get("supplier") or {}).get("supplier_id") for o in orders if o.get("supplier")}) == 1:
        supplier = orders[0].get("supplier")

    merged = {
        "order_id": "cmd_" + uuid.uuid4().hex[:12], "user_id": user["user_id"],
        "plan_id": plan_ids[0] if plan_ids else None,
        "plan_ids": plan_ids,
        "merged_from": body.order_ids,
        "project": body.project.strip() or "Commande fusionnée",
        "type": next(iter(types)) if len(types) == 1 else "mixte",
        "supplier": supplier, "items": items, "status": "brouillon",
        "created_at": _now(),
    }
    await db.material_orders.insert_one(dict(merged))
    merged.pop("_id", None)
    return {"ok": True, "order": merged, "item_count": len(items),
            "merged_count": len(orders)}


class OrderStatusIn(BaseModel):
    status: str


@router.patch("/orders/{order_id}/status")
async def set_order_status(order_id: str, body: OrderStatusIn, user=Depends(current_user)) -> dict:
    if body.status not in ("brouillon", "envoyé", "confirmé"):
        raise HTTPException(422, "Statut invalide")
    r = await db.material_orders.update_one(
        {"order_id": order_id, "user_id": user["user_id"]},
        {"$set": {"status": body.status, "updated_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, "Bon de commande introuvable")
    return {"ok": True, "status": body.status}


@router.delete("/orders/{order_id}")
async def delete_order(order_id: str, user=Depends(current_user)) -> dict:
    r = await db.material_orders.delete_one({"order_id": order_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Bon de commande introuvable")
    return {"ok": True}


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
