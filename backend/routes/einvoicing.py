"""Facturation électronique (réseau national / PDP) — MODE SIMULÉ (MOCKED).

⚠️ Aucune connexion réelle à une Plateforme Agréée (Iopole n°0018 ou autre).
Prêt à brancher : la logique métier (connexion, réception, validation/refus, historique)
est en place ; il suffira de remplacer les appels simulés par l'API PDP réelle.
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import pro_required

router = APIRouter(prefix="/einvoicing", tags=["einvoicing"],
                   dependencies=[Depends(pro_required)])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _seed_inbox(uid: str):
    if await db.einvoice_inbox.count_documents({"user_id": uid}) == 0:
        demo = [
            {"user_id": uid, "inv_id": "einv_demo1", "supplier": "Point.P — Matériaux",
             "supplier_siret": "54210922700018", "number": "FP-2026-0345",
             "amount_ht": 1240.50, "vat": 248.10, "amount_ttc": 1488.60,
             "issued_at": "2026-06-02", "status": "received", "received_at": _now()},
            {"user_id": uid, "inv_id": "einv_demo2", "supplier": "Rexel Électricité",
             "supplier_siret": "30947977000012", "number": "2026-8891",
             "amount_ht": 612.00, "vat": 122.40, "amount_ttc": 734.40,
             "issued_at": "2026-06-05", "status": "received", "received_at": _now()},
        ]
        await db.einvoice_inbox.insert_many(demo)


@router.get("/status")
async def status(user=Depends(pro_required)) -> dict:
    acc = await db.einvoice_accounts.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    if acc.get("connected"):
        await _seed_inbox(user["user_id"])
    return {"connected": bool(acc.get("connected")), "platform": acc.get("platform", "Iopole"),
            "siret": acc.get("siret"), "connected_at": acc.get("connected_at"),
            "mocked": True}


class ConnectIn(BaseModel):
    siret: str
    platform: str = "Iopole"


@router.post("/connect")
async def connect(body: ConnectIn, user=Depends(pro_required)) -> dict:
    siret = "".join(c for c in (body.siret or "") if c.isdigit())
    if len(siret) != 14:
        raise HTTPException(400, "SIRET invalide (14 chiffres attendus)")
    await db.einvoice_accounts.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "connected": True, "siret": siret,
                  "platform": body.platform or "Iopole", "connected_at": _now()}},
        upsert=True)
    await _seed_inbox(user["user_id"])
    return {"ok": True, "connected": True, "mocked": True}


@router.post("/disconnect")
async def disconnect(user=Depends(pro_required)) -> dict:
    await db.einvoice_accounts.update_one({"user_id": user["user_id"]},
                                          {"$set": {"connected": False}})
    return {"ok": True}


@router.get("/inbox")
async def inbox(user=Depends(pro_required)) -> dict:
    rows = await db.einvoice_inbox.find({"user_id": user["user_id"]}, {"_id": 0}) \
        .sort("received_at", -1).to_list(500)
    return {"invoices": rows}


_SIM_SUPPLIERS = [
    ("Cedeo — Sanitaire & Chauffage", "44306184100013"),
    ("Gedimat Négoce", "39284710500021"),
    ("Würth France", "70202599700033"),
    ("Saint-Gobain Distribution", "54210922700018"),
    ("Frans Bonhomme — Canalisations", "31948792600044"),
]


@router.post("/inbox/simulate")
async def simulate_reception(user=Depends(pro_required)) -> dict:
    """Simule la réception d'une nouvelle facture fournisseur via le réseau PDP (MOCKED)."""
    import random
    acc = await db.einvoice_accounts.find_one({"user_id": user["user_id"]})
    if not acc or not acc.get("connected"):
        raise HTTPException(400, "Connectez d'abord une plateforme (PDP)")
    supplier, siret = random.choice(_SIM_SUPPLIERS)
    ht = round(random.uniform(150, 4500), 2)
    vat = round(ht * 0.20, 2)
    row = {"user_id": user["user_id"], "inv_id": f"einv_{uuid4().hex[:10]}",
           "supplier": supplier, "supplier_siret": siret,
           "number": f"F-2026-{random.randint(1000, 9999)}",
           "amount_ht": ht, "vat": vat, "amount_ttc": round(ht + vat, 2),
           "issued_at": datetime.now(timezone.utc).date().isoformat(),
           "status": "received", "received_at": _now()}
    await db.einvoice_inbox.insert_one(row)
    row.pop("_id", None)
    return {"ok": True, "invoice": row, "mocked": True}


class DecisionIn(BaseModel):
    decision: str  # accepted | refused
    reason: str = ""


@router.post("/inbox/{inv_id}/decision")
async def decide(inv_id: str, body: DecisionIn, user=Depends(pro_required)) -> dict:
    if body.decision not in ("accepted", "refused"):
        raise HTTPException(400, "Décision invalide")
    res = await db.einvoice_inbox.update_one(
        {"user_id": user["user_id"], "inv_id": inv_id},
        {"$set": {"status": body.decision, "reason": body.reason[:300],
                  "decided_at": _now(),
                  # Statut transmis à l'administration (SIMULÉ)
                  "admin_status": "transmis (simulé)"}})
    if not res.matched_count:
        raise HTTPException(404, "Facture introuvable")
    return {"ok": True, "status": body.decision, "admin_status": "transmis (simulé)"}


# ---------- Rapprochement facture fournisseur ↔ bon de commande ----------

def _order_est_ht(order: dict) -> float:
    """Estime le montant HT d'un bon de commande à partir des prix unitaires connus."""
    total = 0.0
    for it in order.get("items") or []:
        up = it.get("unit_price") or it.get("pu") or 0
        qty = it.get("commandable_qty") or it.get("qty") or 0
        try:
            total += float(up) * float(qty)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


@router.get("/orders")
async def linkable_orders(user=Depends(pro_required)) -> dict:
    """Bons de commande matériaux de l'utilisateur, pour rapprochement avec une facture."""
    rows = await db.material_orders.find(
        {"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    out = []
    for o in rows:
        out.append({"order_id": o["order_id"], "type": o.get("type"),
                    "supplier": o.get("supplier"), "project": o.get("project"),
                    "status": o.get("status"), "created_at": o.get("created_at"),
                    "item_count": len(o.get("items") or []),
                    "est_ht": _order_est_ht(o)})
    return {"orders": out}


class ReconcileIn(BaseModel):
    order_id: str
    expected_ht: float | None = None


def _gap(invoice_ht: float, expected_ht: float) -> dict:
    diff = round(invoice_ht - expected_ht, 2)
    pct = round((diff / expected_ht * 100), 1) if expected_ht else 0.0
    if abs(pct) <= 2:
        flag = "ok"           # conforme
    elif diff > 0:
        flag = "over"         # facturé plus cher que prévu
    else:
        flag = "under"        # facturé moins cher que prévu
    return {"gap_ht": diff, "gap_pct": pct, "gap_flag": flag}


@router.post("/inbox/{inv_id}/reconcile")
async def reconcile(inv_id: str, body: ReconcileIn, user=Depends(pro_required)) -> dict:
    inv = await db.einvoice_inbox.find_one(
        {"user_id": user["user_id"], "inv_id": inv_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Facture introuvable")
    order = await db.material_orders.find_one(
        {"user_id": user["user_id"], "order_id": body.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Bon de commande introuvable")
    expected = body.expected_ht if body.expected_ht is not None else _order_est_ht(order)
    expected = round(float(expected or 0), 2)
    gap = _gap(float(inv.get("amount_ht") or 0), expected)
    recon = {"order_id": body.order_id, "order_type": order.get("type"),
             "order_supplier": order.get("supplier"),
             "expected_ht": expected, "invoice_ht": float(inv.get("amount_ht") or 0),
             "reconciled_at": _now(), **gap}
    await db.einvoice_inbox.update_one(
        {"user_id": user["user_id"], "inv_id": inv_id},
        {"$set": {"reconciliation": recon}})
    return {"ok": True, "reconciliation": recon}


@router.post("/inbox/{inv_id}/unreconcile")
async def unreconcile(inv_id: str, user=Depends(pro_required)) -> dict:
    res = await db.einvoice_inbox.update_one(
        {"user_id": user["user_id"], "inv_id": inv_id},
        {"$unset": {"reconciliation": ""}})
    if not res.matched_count:
        raise HTTPException(404, "Facture introuvable")
    return {"ok": True}
