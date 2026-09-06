"""Module Suivi de chantier (pack Business) — comptes-rendus, réserves, checklist."""
import asyncio
import base64
import io
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.db import db
from core.security import current_user
from engines import storage, emailer

router = APIRouter(prefix="/site", tags=["site"])


async def _store_photos(photos: list[str], folder: str, uid: str) -> list[str]:
    """Convertit des data URLs base64 en objets stockés, renvoie les chemins."""
    out = []
    for p in (photos or [])[:12]:
        if not isinstance(p, str) or "base64," not in p:
            if isinstance(p, str) and p:
                out.append(p)  # déjà un chemin stocké
            continue
        header, b64 = p.split("base64,", 1)
        ext = "png" if "image/png" in header else "jpg"
        try:
            raw = base64.b64decode(b64)
        except Exception:
            continue
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(413, "Photo trop volumineuse (max 8 Mo)")
        path = f"{storage.APP_NAME}/site/{uid}/{folder}/{uuid.uuid4().hex}.{ext}"
        ct = storage.MIME.get(ext, "image/jpeg")
        res = await asyncio.to_thread(storage.put_object, path, raw, ct)
        out.append(res.get("path", path))
    return out


@router.get("/file")
async def serve_file(path: str):
    data, ct = await asyncio.to_thread(storage.get_object, path)
    return StreamingResponse(io.BytesIO(data), media_type=ct,
                             headers={"Cache-Control": "public, max-age=86400"})


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uid(user):
    return user["user_id"]


# ── Comptes-rendus de visite ──
class ReportIn(BaseModel):
    project: str
    title: str = ""
    notes: str = ""
    lots: list[dict] = []      # [{name, progress}]
    photos: list[str] = []


@router.get("/reports")
async def list_reports(project: str = "", user=Depends(current_user)):
    q = {"user_id": _uid(user)}
    if project:
        q["project"] = project
    return await db.site_reports.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/reports")
async def create_report(body: ReportIn, user=Depends(current_user)):
    photos = await _store_photos(body.photos, "reports", _uid(user))
    doc = {"report_id": "cr_" + secrets.token_hex(6), "user_id": _uid(user),
           **body.model_dump(), "photos": photos, "created_at": _now()}
    await db.site_reports.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str, user=Depends(current_user)):
    await db.site_reports.delete_one({"report_id": report_id, "user_id": _uid(user)})
    return {"ok": True}


# ── Réserves ──
class ReserveIn(BaseModel):
    project: str
    lot: str = ""
    description: str
    company: str = ""
    company_email: str = ""
    photos: list[str] = []


@router.get("/reserves")
async def list_reserves(project: str = "", user=Depends(current_user)):
    q = {"user_id": _uid(user)}
    if project:
        q["project"] = project
    return await db.site_reserves.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/reserves")
async def create_reserve(body: ReserveIn, user=Depends(current_user)):
    photos = await _store_photos(body.photos, "reserves", _uid(user))
    doc = {"reserve_id": "rs_" + secrets.token_hex(6), "user_id": _uid(user),
           **body.model_dump(), "photos": photos, "status": "open",
           "created_at": _now(), "lifted_at": None}
    await db.site_reserves.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.patch("/reserves/{reserve_id}")
async def toggle_reserve(reserve_id: str, user=Depends(current_user)):
    r = await db.site_reserves.find_one({"reserve_id": reserve_id, "user_id": _uid(user)}, {"_id": 0})
    if not r:
        return {"ok": False}
    lifted = r.get("status") != "lifted"
    await db.site_reserves.update_one(
        {"reserve_id": reserve_id},
        {"$set": {"status": "lifted" if lifted else "open", "lifted_at": _now() if lifted else None}})
    return {"ok": True, "status": "lifted" if lifted else "open"}


@router.delete("/reserves/{reserve_id}")
async def delete_reserve(reserve_id: str, user=Depends(current_user)):
    await db.site_reserves.delete_one({"reserve_id": reserve_id, "user_id": _uid(user)})
    return {"ok": True}


# ── Checklist d'avancement ──
class ChecklistIn(BaseModel):
    project: str
    label: str
    lot: str = ""


@router.get("/checklist")
async def list_checklist(project: str = "", user=Depends(current_user)):
    q = {"user_id": _uid(user)}
    if project:
        q["project"] = project
    return await db.site_checklist.find(q, {"_id": 0}).sort("created_at", 1).to_list(1000)


@router.post("/checklist")
async def create_checklist(body: ChecklistIn, user=Depends(current_user)):
    doc = {"item_id": "ck_" + secrets.token_hex(6), "user_id": _uid(user),
           **body.model_dump(), "done": False, "created_at": _now()}
    await db.site_checklist.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.patch("/checklist/{item_id}")
async def toggle_checklist(item_id: str, user=Depends(current_user)):
    r = await db.site_checklist.find_one({"item_id": item_id, "user_id": _uid(user)}, {"_id": 0, "done": 1})
    if not r:
        return {"ok": False}
    await db.site_checklist.update_one({"item_id": item_id}, {"$set": {"done": not r.get("done")}})
    return {"ok": True, "done": not r.get("done")}


@router.delete("/checklist/{item_id}")
async def delete_checklist(item_id: str, user=Depends(current_user)):
    await db.site_checklist.delete_one({"item_id": item_id, "user_id": _uid(user)})
    return {"ok": True}


@router.get("/projects")
async def list_projects(user=Depends(current_user)):
    uid = _uid(user)
    names = set()
    for coll in (db.site_reports, db.site_reserves, db.site_checklist):
        names.update(await coll.distinct("project", {"user_id": uid}))
    return sorted(n for n in names if n)


@router.get("/report-pdf")
async def report_pdf(project: str, user=Depends(current_user)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    uid = _uid(user)
    reports = await db.site_reports.find({"user_id": uid, "project": project}, {"_id": 0}).sort("created_at", -1).to_list(200)
    reserves = await db.site_reserves.find({"user_id": uid, "project": project}, {"_id": 0}).sort("created_at", -1).to_list(500)
    checklist = await db.site_checklist.find({"user_id": uid, "project": project}, {"_id": 0}).to_list(500)
    done = sum(1 for c in checklist if c.get("done"))
    pct = round(done / len(checklist) * 100) if checklist else 0
    GREEN, DARK, GREY, LIGHT = colors.HexColor("#16a34a"), colors.HexColor("#0f172a"), colors.HexColor("#64748b"), colors.HexColor("#f1f5f9")
    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h", parent=st["Title"], textColor=DARK, fontSize=20)
    sub = ParagraphStyle("s", parent=st["Normal"], textColor=GREY, fontSize=10, spaceAfter=12)
    sec = ParagraphStyle("sec", parent=st["Heading2"], textColor=GREEN, fontSize=12, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("b", parent=st["Normal"], fontSize=9.5, leading=13)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=14*mm)
    flow = [Paragraph("Compte-rendu de chantier", h1),
            Paragraph(f"{project} — {datetime.now(timezone.utc).strftime('%d/%m/%Y')} · Avancement global : {pct}%", sub)]
    flow.append(Paragraph("Comptes-rendus de visite", sec))
    if reports:
        for r in reports:
            flow.append(Paragraph(f"<b>{r.get('title') or 'Visite'}</b> — {r.get('created_at','')[:10]}", body))
            if r.get("notes"):
                flow.append(Paragraph(r["notes"].replace("\n", "<br/>"), body))
            flow.append(Spacer(1, 4))
    else:
        flow.append(Paragraph("Aucun compte-rendu.", body))
    flow.append(Paragraph(f"Réserves ({sum(1 for x in reserves if x.get('status')!='lifted')} en cours / {len(reserves)})", sec))
    if reserves:
        rows = [["Lot", "Description", "Entreprise", "Statut"]]
        for r in reserves:
            rows.append([r.get("lot", ""), r.get("description", ""), r.get("company", ""),
                         "Levée" if r.get("status") == "lifted" else "En cours"])
        t = Table(rows, colWidths=[28*mm, 78*mm, 38*mm, 30*mm])
        t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), DARK), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                               ("FONTSIZE", (0,0), (-1,-1), 8.5), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                               ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
                               ("BOTTOMPADDING", (0,0), (-1,-1), 5), ("TOPPADDING", (0,0), (-1,-1), 5),
                               ("VALIGN", (0,0), (-1,-1), "TOP")]))
        flow.append(t)
    else:
        flow.append(Paragraph("Aucune réserve.", body))
    if checklist:
        flow.append(Paragraph(f"Checklist d'avancement — {pct}%", sec))
        for c in checklist:
            mark = "[x]" if c.get("done") else "[ ]"
            flow.append(Paragraph(f"{mark} {c.get('label','')}" + (f" · {c.get('lot')}" if c.get("lot") else ""), body))
    flow.append(Spacer(1, 14))
    flow.append(Paragraph("Généré par ConstruPilot · construpilot.fr", ParagraphStyle("f", parent=st["Normal"], textColor=GREY, fontSize=8)))
    doc.build(flow)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="chantier-{project[:30]}.pdf"'})


@router.post("/reserves/remind")
async def remind_companies(project: str, user=Depends(current_user)):
    uid = _uid(user)
    reserves = await db.site_reserves.find(
        {"user_id": uid, "project": project, "status": {"$ne": "lifted"}}, {"_id": 0}).to_list(500)
    by_email: dict = {}
    for r in reserves:
        em = (r.get("company_email") or "").strip()
        if em and "@" in em:
            by_email.setdefault(em, {"company": r.get("company", ""), "items": []})
            by_email[em]["items"].append(r)
    sent, skipped = 0, len(reserves)
    for email, grp in by_email.items():
        lis = "".join(f"<li>{r.get('lot','')} — {r.get('description','')}</li>" for r in grp["items"])
        html = (f"<p>Olá {grp['company'] or ''},</p>"
                f"<p>Réserves à lever sur le chantier <b>{project}</b> :</p><ul>{lis}</ul>"
                f"<p>Merci de planifier leur reprise au plus vite.</p><p>— {user.get('name') or 'ConstruPilot'}</p>")
        try:
            await emailer.send_email(email, f"Réserves à lever — {project}", html)
            sent += 1
            skipped -= len(grp["items"])
        except Exception:
            pass
    return {"emails_sent": sent, "companies": len(by_email), "reserves_without_email": skipped}
