"""Bloc « Aujourd'hui » : prochaine action et éléments réellement à traiter (aucun indicateur artificiel)."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from core.db import db
from core.security import current_user
from engines.deadline_reminders import parse_deadline

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@router.get("/today")
async def today(user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    is_pro = (user.get("account_type") or "") != "particulier"
    now = datetime.now(timezone.utc)
    items: list[dict] = []

    if is_pro:
        quotes_to_follow = await db.pro_documents.find(
            {"user_id": uid, "doc_type": "quote", "status": "sent", "updated_at": {"$lt": _iso_days_ago(7)}},
            {"_id": 0, "doc_id": 1, "title": 1, "number": 1, "totals.ttc": 1, "updated_at": 1}).sort("updated_at", 1).to_list(5)
        for q in quotes_to_follow:
            items.append({"kind": "quote_followup", "label": f"Relancer le devis {q.get('number') or ''} — {q.get('title') or 'sans titre'}".strip(),
                          "url": f"/devis-editeur/{q['doc_id']}", "amount": (q.get("totals") or {}).get("ttc"), "since": q.get("updated_at")})
        overdue = await db.pro_documents.find(
            {"user_id": uid, "doc_type": "invoice", "status": {"$in": ["issued", "sent", "partial"]}, "due_date": {"$ne": None, "$lt": now.isoformat()}},
            {"_id": 0, "doc_id": 1, "title": 1, "number": 1, "totals.remaining": 1, "totals.ttc": 1, "due_date": 1}).sort("due_date", 1).to_list(5)
        for inv in overdue:
            items.append({"kind": "invoice_overdue", "label": f"Facture {inv.get('number') or ''} en retard — {inv.get('title') or ''}".strip(),
                          "url": f"/devis-editeur/{inv['doc_id']}", "amount": (inv.get("totals") or {}).get("remaining") or (inv.get("totals") or {}).get("ttc"), "since": inv.get("due_date")})
        vat_unset = await db.pro_documents.count_documents({"user_id": uid, "status": "draft", "totals.vat_unset_lines": {"$gt": 0}})
        if vat_unset:
            items.append({"kind": "vat_to_confirm", "label": f"{vat_unset} brouillon{'s' if vat_unset > 1 else ''} avec des lignes sans TVA choisie", "url": "/devis?filtre=brouillons"})
        review_jobs = await db.plans_pro_jobs.find({"user_id": uid, "status": {"$in": ["needs_review", "partial"]}, "reviewed": {"$ne": True}},
                                                   {"_id": 0, "job_id": 1, "filename": 1, "status": 1}).sort("created_at", -1).to_list(5)
        for j in review_jobs:
            items.append({"kind": "plan_review", "label": f"Vérifier l'analyse du plan « {j.get('filename')} » ({'désaccords' if j['status'] == 'needs_review' else 'résultat partiel'})",
                          "url": "/plans-pro"})

    tomorrow = date.today() + timedelta(days=1)
    async for st in db.assistant_project_state.find({"user_id": uid, "$or": [{"open_points.deadline": {"$ne": None}}, {"decisions.deadline": {"$ne": None}}]}, {"_id": 0}):
        for section in ("open_points", "decisions"):
            for e in st.get(section) or []:
                if e.get("status") != "superseded" and e.get("deadline") and parse_deadline(e["deadline"], date.today()) in (date.today(), tomorrow):
                    when = "aujourd'hui" if parse_deadline(e["deadline"], date.today()) == date.today() else "demain"
                    items.append({"kind": "deadline", "label": f"Échéance {when} : {e.get('statement', '')[:90]}" + (f" (resp. {e['owner']})" if e.get("owner") else ""),
                                  "url": f"/assistant?conversation={st['conversation_id']}"})

    running = await db.btp_problems.count_documents({"user_id": uid, "status": "running"}) + await db.plans_pro_jobs.count_documents(
        {"user_id": uid, "status": {"$nin": ["done", "needs_review", "partial", "failed", "cancelled", "autodesk_error", "error"]}})

    counts = {"quotes": await db.pro_documents.count_documents({"user_id": uid, "doc_type": "quote"}) if is_pro else 0,
              "clients": await db.clients.count_documents({"user_id": uid}) if is_pro else 0,
              "projects": await db.projects.count_documents({"$or": [{"user_id": uid}, {"owner_id": uid}]}),
              "plans": await db.plans_takeoff.count_documents({"user_id": uid})}
    branding = await db.users.find_one({"user_id": uid}, {"_id": 0, "brand_company_name": 1, "public_published": 1}) or {}

    if items:
        priority = {"invoice_overdue": 0, "deadline": 1, "quote_followup": 2, "plan_review": 3, "vat_to_confirm": 4}
        items.sort(key=lambda i: priority.get(i["kind"], 9))
        next_action = items[0]
    elif is_pro and not branding.get("brand_company_name"):
        next_action = {"kind": "setup", "label": "Renseignez l'identité de votre entreprise (logo, coordonnées, pays TVA) : elle habille tous vos devis", "url": "/ma-page"}
    elif is_pro and counts["clients"] == 0:
        next_action = {"kind": "setup", "label": "Ajoutez votre premier client pour préparer un devis sans ressaisie", "url": "/clients"}
    elif is_pro and counts["quotes"] == 0:
        next_action = {"kind": "setup", "label": "Créez votre premier devis (dictée, photo, plan ou bibliothèque)", "url": "/devis-editeur"}
    elif is_pro and not branding.get("public_published"):
        next_action = {"kind": "setup", "label": "Publiez votre page entreprise pour que vos clients découvrent vos réalisations", "url": "/ma-page"}
    elif not is_pro and counts["projects"] == 0:
        next_action = {"kind": "setup", "label": "Décrivez votre projet de travaux pour obtenir une estimation", "url": "/estimation"}
    else:
        next_action = {"kind": "clear", "label": "Rien d'urgent aujourd'hui — reprenez un dossier ou demandez à l'assistant", "url": "/assistant"}

    return {"date": date.today().isoformat(), "next_action": next_action, "items": items[:12], "running_analyses": running, "counts": counts,
            "empty_account": all(v == 0 for v in counts.values())}
