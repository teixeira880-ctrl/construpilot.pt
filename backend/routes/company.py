"""Espace Entreprise (Pack Business) — hub, KPIs, rôles & gestion des employés.

Rôles d'organisation : owner, admin, chef_chantier, comptable, ouvrier, member.
Chaque rôle ouvre un jeu de permissions (features) consommé par le frontend.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.security import current_user, hash_password, new_user_id, pro_required
from engines import activity

router = APIRouter(prefix="/company", tags=["company"], dependencies=[Depends(pro_required)])

# Features gérées par le frontend (nav + pages métier).
FEATURES = ["dashboard", "devis", "factures", "situations", "chantier",
            "rh", "catalogue", "entreprise", "pointage"]

ROLE_PERMISSIONS: dict[str, dict] = {
    "owner":         {f: True for f in FEATURES},
    "admin":         {**{f: True for f in FEATURES}, "entreprise": True},
    "chef_chantier": {"dashboard": True, "devis": True, "situations": True,
                      "chantier": True, "rh": True, "catalogue": True,
                      "factures": False, "entreprise": False, "pointage": False},
    "comptable":     {"dashboard": True, "devis": True, "factures": True,
                      "situations": True, "catalogue": True, "chantier": False,
                      "rh": False, "entreprise": False, "pointage": False},
    "member":        {"dashboard": True, "devis": True, "catalogue": True,
                      "factures": False, "situations": False, "chantier": False,
                      "rh": False, "entreprise": False, "pointage": False},
    "ouvrier":       {f: False for f in FEATURES} | {"pointage": True},
}
ASSIGNABLE_ROLES = ["admin", "chef_chantier", "comptable", "member", "ouvrier"]
ROLE_LABELS = {
    "owner": "Proprietário", "admin": "Administrador", "chef_chantier": "Chefe de obra",
    "comptable": "Contabilista", "member": "Membro", "ouvrier": "Trabalhador",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _perms_for(role: str, active: bool = True) -> dict:
    if not active:
        return {f: False for f in FEATURES}
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["member"])


async def _me(user: dict) -> dict:
    return await db.users.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0, "organization_id": 1, "org_role": 1, "company_active": 1}) or {}


async def _require_manager(user: dict) -> dict:
    u = await _me(user)
    if not u.get("organization_id"):
        raise HTTPException(400, "Vous n'avez pas d'entreprise.")
    if u.get("org_role") not in ("owner", "admin"):
        raise HTTPException(403, "Réservé au propriétaire ou à un administrateur.")
    return u


@router.get("/me")
async def company_me(user=Depends(current_user)) -> dict:
    """Rôle + permissions de l'utilisateur courant (utilisé pour le gating frontend)."""
    # Admin plateforme OU solo (sans org) → accès complet, pas de restriction.
    if user.get("role") == "admin":
        return {"in_org": False, "role": "owner", "active": True,
                "permissions": {f: True for f in FEATURES}}
    u = await _me(user)
    if not u.get("organization_id"):
        return {"in_org": False, "role": "owner", "active": True,
                "permissions": {f: True for f in FEATURES}}
    role = u.get("org_role", "member")
    active = u.get("company_active", True)
    return {"in_org": True, "role": role, "role_label": ROLE_LABELS.get(role, role),
            "active": active, "permissions": _perms_for(role, active)}


@router.get("/dashboard")
async def company_dashboard(user=Depends(current_user)) -> dict:
    mgr = await _require_manager(user)
    org_id = mgr["organization_id"]
    members = await db.users.find(
        {"organization_id": org_id},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "org_role": 1,
         "company_active": 1, "role": 1}).to_list(500)
    member_ids = [m["user_id"] for m in members]

    docs = await db.pro_documents.find(
        {"user_id": {"$in": member_ids}, "doc_type": "invoice"},
        {"_id": 0, "totals": 1, "status": 1, "paid": 1, "facturx_validation": 1}
    ).to_list(5000)
    ca_ttc = sum((d.get("totals") or {}).get("ttc", 0) for d in docs)
    encours = sum(((d.get("totals") or {}).get("ttc", 0) - (d.get("paid") or 0))
                  for d in docs if d.get("status") != "paid")
    conformes = sum(1 for d in docs if (d.get("facturx_validation") or {}).get("valid"))

    quotes = await db.pro_documents.count_documents(
        {"user_id": {"$in": member_ids}, "doc_type": "quote"})
    situations = await db.situations.count_documents({"user_id": {"$in": member_ids}})
    projects = await db.site_reports.distinct("project", {"user_id": {"$in": member_ids}})
    open_reserves = await db.site_reserves.count_documents(
        {"user_id": {"$in": member_ids}, "status": {"$ne": "lifted"}})
    workers = sum(1 for m in members if m.get("org_role") == "ouvrier" or m.get("role") == "worker")

    return {
        "kpis": {
            "ca_ttc": round(ca_ttc, 2), "encours": round(encours, 2),
            "invoices": len(docs), "invoices_conformes": conformes,
            "quotes": quotes, "situations": situations,
            "chantiers": len([p for p in projects if p]), "open_reserves": open_reserves,
            "members": len(members), "workers": workers,
        },
        "members": [{
            "user_id": m["user_id"], "name": m.get("name"), "email": m.get("email"),
            "role": m.get("org_role", "member"), "role_label": ROLE_LABELS.get(m.get("org_role", "member")),
            "active": m.get("company_active", True),
            "is_self": m["user_id"] == user["user_id"],
        } for m in members],
        "assignable_roles": [{"value": r, "label": ROLE_LABELS[r]} for r in ASSIGNABLE_ROLES],
    }


class EmployeeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = "member"


@router.post("/employees")
async def create_employee(body: EmployeeIn, user=Depends(current_user)) -> dict:
    mgr = await _require_manager(user)
    if body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(400, "Rôle invalide.")
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Un compte existe déjà avec cet e-mail.")
    is_worker = body.role == "ouvrier"
    doc = {
        "user_id": new_user_id(), "name": body.name.strip(), "email": email,
        "password_hash": hash_password(body.password), "picture": None,
        "role": "worker" if is_worker else "user", "plan": "free",
        "auth_provider": "password", "must_change_password": True,
        "organization_id": mgr["organization_id"], "org_role": body.role,
        "company_active": True, "joined_org_at": _now(), "created_at": _now(),
    }
    if is_worker:
        doc["employer_id"] = user["user_id"]
    await db.users.insert_one(doc)
    await activity.log(user, "employee.create", "employee", doc["name"],
                       {"role": body.role, "email": doc["email"]})
    return {"user_id": doc["user_id"], "name": doc["name"], "email": doc["email"],
            "role": body.role, "role_label": ROLE_LABELS.get(body.role), "active": True}


class MemberUpdate(BaseModel):
    role: str | None = None
    active: bool | None = None


@router.put("/members/{member_user_id}")
async def update_member(member_user_id: str, body: MemberUpdate, user=Depends(current_user)) -> dict:
    mgr = await _require_manager(user)
    if member_user_id == user["user_id"]:
        raise HTTPException(400, "Vous ne pouvez pas modifier votre propre rôle/accès ici.")
    m = await db.users.find_one(
        {"user_id": member_user_id, "organization_id": mgr["organization_id"]},
        {"_id": 0, "org_role": 1})
    if not m:
        raise HTTPException(404, "Employé introuvable dans votre entreprise.")
    if m.get("org_role") == "owner":
        raise HTTPException(400, "Impossible de modifier le propriétaire.")
    upd = {}
    if body.role is not None:
        if body.role not in ASSIGNABLE_ROLES:
            raise HTTPException(400, "Rôle invalide.")
        upd["org_role"] = body.role
        upd["role"] = "worker" if body.role == "ouvrier" else "user"
        if body.role == "ouvrier":
            upd["employer_id"] = user["user_id"]
    if body.active is not None:
        upd["company_active"] = bool(body.active)
    if upd:
        await db.users.update_one({"user_id": member_user_id}, {"$set": upd})
        await activity.log(user, "member.update", "employee", m.get("name") or member_user_id, upd)
    return {"ok": True, **upd}


@router.delete("/members/{member_user_id}")
async def remove_member(member_user_id: str, user=Depends(current_user)) -> dict:
    mgr = await _require_manager(user)
    if member_user_id == user["user_id"]:
        raise HTTPException(400, "Utilisez « Quitter l'organisation » pour vous retirer.")
    m = await db.users.find_one(
        {"user_id": member_user_id, "organization_id": mgr["organization_id"]},
        {"_id": 0, "org_role": 1})
    if not m:
        raise HTTPException(404, "Employé introuvable.")
    if m.get("org_role") == "owner":
        raise HTTPException(400, "Impossible de retirer le propriétaire.")
    await db.users.update_one(
        {"user_id": member_user_id},
        {"$unset": {"organization_id": "", "org_role": "", "company_active": "",
                    "joined_org_at": "", "employer_id": ""}})
    return {"ok": True}



@router.get("/activity")
async def company_activity(action: str = "", actor_id: str = "", user=Depends(current_user)):
    """Journal d'activité de l'entreprise (qui a fait quoi). Réservé owner/admin en organisation."""
    u = await _me(user)
    if u.get("organization_id"):
        if u.get("org_role") not in ("owner", "admin") and user.get("role") != "admin":
            raise HTTPException(403, "Réservé au propriétaire ou à un administrateur.")
        org_id = u["organization_id"]
    else:
        org_id = f"solo:{user['user_id']}"
    return await activity.recent(org_id, 150, action, actor_id)


@router.get("/activity/export")
async def export_activity(actor_id: str = "", user=Depends(current_user)):
    """Export CSV du journal d'activité (filtrable par employé)."""
    from fastapi import Response
    u = await _me(user)
    if u.get("organization_id"):
        if u.get("org_role") not in ("owner", "admin") and user.get("role") != "admin":
            raise HTTPException(403, "Réservé au propriétaire ou à un administrateur.")
        org_id = u["organization_id"]
    else:
        org_id = f"solo:{user['user_id']}"
    rows = await activity.recent(org_id, 2000, "", actor_id)
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Date", "Employé", "Action", "Détail"])
    for r in rows:
        w.writerow([r.get("created_at", "")[:19].replace("T", " "), r.get("actor_name", ""),
                    r.get("action_label", ""), r.get("label", "")])
    return Response(content="\ufeff" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="journal-activite.csv"'})


@router.get("/activity/pdf")
async def export_activity_pdf(actor_id: str = "", user=Depends(current_user)):
    """Export PDF du journal d'activité (remise officielle)."""
    import io
    from fastapi import Response
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    u = await _me(user)
    if u.get("organization_id"):
        if u.get("org_role") not in ("owner", "admin") and user.get("role") != "admin":
            raise HTTPException(403, "Réservé au propriétaire ou à un administrateur.")
        org_id = u["organization_id"]
    else:
        org_id = f"solo:{user['user_id']}"
    rows = await activity.recent(org_id, 500, "", actor_id)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=8)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    data = [["Date", "Employé", "Action", "Détail"]]
    for r in rows:
        data.append([r.get("created_at", "")[:16].replace("T", " "),
                     Paragraph(r.get("actor_name", ""), small),
                     Paragraph(r.get("action_label", ""), small),
                     Paragraph(r.get("label", ""), small)])
    tbl = Table(data, colWidths=[30 * mm, 38 * mm, 46 * mm, 64 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    E = [Paragraph("<b>Journal d'activité — ConstruPilot</b>", styles["Title"]),
         Spacer(1, 8), tbl]
    doc.build(E)
    return Response(content=buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="journal-activite.pdf"'})
