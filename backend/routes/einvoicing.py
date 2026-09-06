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
            "overspend_threshold_pct": acc.get("overspend_threshold_pct", 5),
            "mocked": True}


class SettingsIn(BaseModel):
    overspend_threshold_pct: float


@router.post("/settings")
async def update_settings(body: SettingsIn, user=Depends(pro_required)) -> dict:
    pct = max(0, min(100, float(body.overspend_threshold_pct)))
    await db.einvoice_accounts.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "overspend_threshold_pct": pct}}, upsert=True)
    return {"ok": True, "overspend_threshold_pct": pct}


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
    project_id: str | None = None  # chantier pour créer une dépense auto (si accepté)


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
    expense = None
    if body.decision == "accepted" and body.project_id:
        inv = await db.einvoice_inbox.find_one(
            {"user_id": user["user_id"], "inv_id": inv_id}, {"_id": 0})
        expense = await _create_einvoice_expense(user, inv, body.project_id)
    return {"ok": True, "status": body.decision,
            "admin_status": "transmis (simulé)", "expense": expense}


# ---------- Dépense chantier automatique depuis une facture acceptée ----------

@router.get("/projects")
async def list_user_projects(user=Depends(pro_required)) -> dict:
    rows = await db.projects.find(
        {"user_id": user["user_id"]}, {"_id": 0, "project_id": 1, "name": 1}) \
        .sort("created_at", -1).to_list(300)
    return {"projects": [{"project_id": r["project_id"], "name": r.get("name") or "Chantier"}
                         for r in rows]}


async def _create_einvoice_expense(user: dict, inv: dict, project_id: str) -> dict:
    """Crée (ou remplace) une dépense chantier depuis une facture fournisseur acceptée."""
    proj = await db.projects.find_one(
        {"project_id": project_id, "user_id": user["user_id"]}, {"_id": 0, "name": 1})
    if not proj:
        raise HTTPException(404, "Chantier introuvable")
    prev = inv.get("expense")
    if prev and prev.get("project_id") and prev.get("expense_id"):
        await db.projects.update_one(
            {"project_id": prev["project_id"]},
            {"$pull": {"expenses": {"expense_id": prev["expense_id"]}}})
    exp_id = f"exp_{uuid4().hex[:8]}"
    amount = round(float(inv.get("amount_ht") or 0), 2)
    exp = {"expense_id": exp_id,
           "label": f"Facture {inv.get('supplier')} · {inv.get('number')}",
           "amount": amount, "lot": None, "date": _now(),
           "source": "einvoice", "einvoice_id": inv.get("inv_id")}
    await db.projects.update_one(
        {"project_id": project_id},
        {"$push": {"expenses": exp}, "$set": {"updated_at": _now()}})
    link = {"project_id": project_id, "project_name": proj.get("name"),
            "expense_id": exp_id, "amount": amount}
    await db.einvoice_inbox.update_one(
        {"user_id": user["user_id"], "inv_id": inv.get("inv_id")},
        {"$set": {"expense": link}})
    return link


class ExpenseLinkIn(BaseModel):
    project_id: str


@router.post("/inbox/{inv_id}/expense")
async def link_expense(inv_id: str, body: ExpenseLinkIn, user=Depends(pro_required)) -> dict:
    inv = await db.einvoice_inbox.find_one(
        {"user_id": user["user_id"], "inv_id": inv_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Facture introuvable")
    if inv.get("status") != "accepted":
        raise HTTPException(400, "Seule une facture acceptée peut être enregistrée en dépense")
    link = await _create_einvoice_expense(user, inv, body.project_id)
    return {"ok": True, "expense": link}


@router.post("/inbox/{inv_id}/expense/remove")
async def unlink_expense(inv_id: str, user=Depends(pro_required)) -> dict:
    inv = await db.einvoice_inbox.find_one(
        {"user_id": user["user_id"], "inv_id": inv_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Facture introuvable")
    prev = inv.get("expense")
    if prev and prev.get("project_id") and prev.get("expense_id"):
        await db.projects.update_one(
            {"project_id": prev["project_id"]},
            {"$pull": {"expenses": {"expense_id": prev["expense_id"]}}})
    await db.einvoice_inbox.update_one(
        {"user_id": user["user_id"], "inv_id": inv_id}, {"$unset": {"expense": ""}})
    return {"ok": True}


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
    alert = await _maybe_overspend_alert(user, inv, recon)
    return {"ok": True, "reconciliation": recon, "alert": alert}


async def _maybe_overspend_alert(user: dict, inv: dict, recon: dict) -> dict | None:
    """Alerte le pro si la facture dépasse le bon de commande de plus du seuil configuré."""
    if recon.get("gap_flag") != "over":
        return None
    acc = await db.einvoice_accounts.find_one(
        {"user_id": user["user_id"]}, {"_id": 0, "overspend_threshold_pct": 1}) or {}
    threshold = acc.get("overspend_threshold_pct", 5)
    if recon.get("gap_pct", 0) < threshold:
        return None
    msg = (f"Surcoût détecté : la facture {inv.get('supplier')} ({inv.get('number')}) dépasse "
           f"le bon de commande de {recon['gap_pct']}% (+{recon['gap_ht']:.2f} € HT).")
    await db.notifications.insert_one({
        "user_id": user["user_id"], "type": "einvoice_overspend",
        "inv_id": inv.get("inv_id"), "order_id": recon.get("order_id"),
        "gap_ht": recon["gap_ht"], "gap_pct": recon["gap_pct"], "threshold_pct": threshold,
        "message": msg, "read": False, "created_at": _now()})
    try:
        if user.get("email"):
            from engines.emailer import send_email
            html = (f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto">'
                    f'<h2 style="color:#B91C1C">⚠️ Surcoût fournisseur détecté</h2>'
                    f'<p>{msg}</p>'
                    f'<ul><li>Montant prévu (commande) : <b>{recon["expected_ht"]:.2f} € HT</b></li>'
                    f'<li>Montant facturé : <b>{recon["invoice_ht"]:.2f} € HT</b></li>'
                    f'<li>Écart : <b style="color:#B91C1C">+{recon["gap_ht"]:.2f} € ({recon["gap_pct"]}%)</b></li></ul>'
                    f'<p style="color:#64748B;font-size:13px">Seuil d\'alerte configuré : {threshold}%. '
                    f'Vérifiez la facture avant de l\'accepter.</p></div>')
            await send_email(user["email"], "⚠️ Surcoût fournisseur détecté · ConstruPilot", html)
    except Exception:  # noqa: BLE001
        pass
    return {"overspend": True, "gap_pct": recon["gap_pct"], "threshold_pct": threshold}


@router.post("/inbox/{inv_id}/unreconcile")
async def unreconcile(inv_id: str, user=Depends(pro_required)) -> dict:
    res = await db.einvoice_inbox.update_one(
        {"user_id": user["user_id"], "inv_id": inv_id},
        {"$unset": {"reconciliation": ""}})
    if not res.matched_count:
        raise HTTPException(404, "Facture introuvable")
    return {"ok": True}


# ---------- Résumé mensuel des surcoûts / économies fournisseurs ----------

def _prev_month_range(ref: datetime | None = None) -> tuple[datetime, datetime, str]:
    ref = ref or datetime.now(timezone.utc)
    first_this = ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = first_this
    prev_last = first_this.replace(tzinfo=timezone.utc)
    start = (first_this.replace(year=first_this.year - 1, month=12) if first_this.month == 1
             else first_this.replace(month=first_this.month - 1))
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]
    label = f"{months[start.month - 1]} {start.year}"
    return start, end, label


async def _user_overspend_summary(user_id: str, start: datetime, end: datetime) -> dict:
    """Agrège les rapprochements du mois pour un pro (surcoûts + économies)."""
    rows = await db.einvoice_inbox.find(
        {"user_id": user_id, "reconciliation": {"$exists": True}},
        {"_id": 0, "supplier": 1, "number": 1, "reconciliation": 1}).to_list(2000)
    overspend_total = savings_total = 0.0
    over_items, under_items = [], []
    for r in rows:
        rec = r.get("reconciliation") or {}
        ra = rec.get("reconciled_at")
        if not ra:
            continue
        try:
            dt = datetime.fromisoformat(ra)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if not (start <= dt < end):
            continue
        gap = rec.get("gap_ht", 0)
        if rec.get("gap_flag") == "over" and gap > 0:
            overspend_total += gap
            over_items.append({"supplier": r.get("supplier"), "number": r.get("number"),
                               "gap_ht": round(gap, 2), "gap_pct": rec.get("gap_pct")})
        elif rec.get("gap_flag") == "under" and gap < 0:
            savings_total += abs(gap)
            under_items.append({"supplier": r.get("supplier"), "number": r.get("number"),
                                "gap_ht": round(abs(gap), 2), "gap_pct": rec.get("gap_pct")})
    return {"overspend_total": round(overspend_total, 2),
            "savings_total": round(savings_total, 2),
            "over_count": len(over_items), "under_count": len(under_items),
            "over_items": over_items[:10], "under_items": under_items[:10]}


def _monthly_report_html(name: str, label: str, s: dict) -> str:
    def _eur(v):
        return f"{v:,.2f} €".replace(",", " ")
    rows = "".join(
        f'<tr><td style="padding:6px 0">{i["supplier"]} · {i["number"]}</td>'
        f'<td style="text-align:right;color:#B91C1C;padding:6px 0">+{_eur(i["gap_ht"])} ({i["gap_pct"]}%)</td></tr>'
        for i in s["over_items"]) or '<tr><td style="color:#059669;padding:6px 0">Aucun surcoût ce mois-ci 🎉</td></tr>'
    return f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#0A0D14">
  <div style="text-align:center;padding:20px 0">
    <div style="font-size:24px;font-weight:800"><span style="color:#FF5A00">Constru</span>Pilot</div>
  </div>
  <h2 style="margin:0 0 4px">Résumé fournisseurs — {label}</h2>
  <p style="color:#64748B;margin:0 0 18px">Olá {name}, voici votre bilan des factures fournisseurs rapprochées.</p>
  <div style="display:flex;gap:12px;margin-bottom:18px">
    <div style="flex:1;background:#FEF2F2;border:1px solid #FECACA;border-radius:12px;padding:16px">
      <div style="font-size:22px;font-weight:800;color:#B91C1C">+{_eur(s['overspend_total'])}</div>
      <div style="font-size:12px;color:#64748B">Surcoûts détectés ({s['over_count']})</div></div>
    <div style="flex:1;background:#ECFDF5;border:1px solid #A7F3D0;border-radius:12px;padding:16px">
      <div style="font-size:22px;font-weight:800;color:#059669">{_eur(s['savings_total'])}</div>
      <div style="font-size:12px;color:#64748B">Économies réalisées ({s['under_count']})</div></div>
  </div>
  <h3 style="font-size:15px;margin:0 0 6px">Principaux surcoûts</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px">{rows}</table>
  <p style="color:#94A3B8;font-size:12px;text-align:center;margin-top:22px">
    ConstruPilot · Suivez votre marge en temps réel</p>
</div>"""


async def run_monthly_overspend_reports(ref: datetime | None = None) -> dict:
    """Job mensuel : envoie à chaque pro connecté un récap surcoûts/économies du mois écoulé."""
    from engines.emailer import send_email
    start, end, label = _prev_month_range(ref)
    accounts = await db.einvoice_accounts.find(
        {"connected": True}, {"_id": 0, "user_id": 1}).to_list(5000)
    sent = 0
    for acc in accounts:
        uid = acc["user_id"]
        s = await _user_overspend_summary(uid, start, end)
        if s["over_count"] == 0 and s["under_count"] == 0:
            continue
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1, "name": 1})
        if not u or not u.get("email"):
            continue
        try:
            html = _monthly_report_html((u.get("name") or "").split(" ")[0] or "cher pro", label, s)
            await send_email(u["email"], f"Votre résumé fournisseurs — {label} · ConstruPilot", html)
            sent += 1
        except Exception:  # noqa: BLE001
            continue
    return {"month": label, "reports_sent": sent, "accounts": len(accounts)}


@router.post("/reports/monthly/preview")
async def preview_monthly_report(user=Depends(pro_required)) -> dict:
    """Aperçu du résumé mensuel pour le pro courant (mois précédent), sans envoi."""
    start, end, label = _prev_month_range()
    s = await _user_overspend_summary(user["user_id"], start, end)
    return {"month": label, **s}
