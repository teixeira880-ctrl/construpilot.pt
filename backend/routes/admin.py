from datetime import datetime, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import admin_user, current_user
from engines.catalog import LOTS, REGIONS
from engines import price_search

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/inbox")
async def admin_inbox(hours: int = 168) -> dict:
    """Boîte de réception admin — vue consolidée des demandes et incidents récents.

    Renvoie leads récents + nouveaux users + devis envoyés + erreurs client
    pour permettre à l'équipe de tout suivre depuis une seule page.
    """
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    since_iso = since.isoformat()

    # Leads (contact form / lead gen)
    leads_cur = db.leads.find({"created_at": {"$gte": since_iso}},
                                {"_id": 0}).sort("created_at", -1).limit(50)
    leads = await leads_cur.to_list(50)

    # Nouveaux utilisateurs (>= depuis N heures)
    users_cur = db.users.find({"created_at": {"$gte": since_iso}},
                                {"_id": 0, "user_id": 1, "email": 1, "name": 1,
                                 "role": 1, "plan": 1, "created_at": 1}
                                ).sort("created_at", -1).limit(50)
    new_users = await users_cur.to_list(50)

    # Devis envoyés (activité pros)
    sends_cur = db.quote_sends.find({"sent_at": {"$gte": since_iso}},
                                     {"_id": 0, "log_id": 1, "user_id": 1,
                                      "client_email": 1, "client_name": 1,
                                      "total_ttc": 1, "sent_at": 1,
                                      "signed": 1, "opened_at": 1}
                                     ).sort("sent_at", -1).limit(50)
    sends = await sends_cur.to_list(50)

    # Erreurs client
    errs_cur = db.client_errors.find({"created_at": {"$gte": since}},
                                       {"_id": 0}).sort("created_at", -1).limit(30)
    errs = await errs_cur.to_list(30)

    # Téléchargements du pitch deck investisseurs (leads VC)
    deck_cur = db.deck_downloads.find({"created_at": {"$gte": since_iso}},
                                       {"_id": 0}).sort("created_at", -1).limit(50)
    deck_downloads = await deck_cur.to_list(50)

    # Devis signés dans la fenêtre (à célébrer)
    signed_count = sum(1 for s in sends if s.get("signed"))
    open_count = sum(1 for s in sends if s.get("opened_at") and not s.get("signed"))

    return {
        "hours": hours,
        "counts": {
            "new_leads": len(leads),
            "new_users": len(new_users),
            "quotes_sent": len(sends),
            "quotes_signed": signed_count,
            "quotes_opened": open_count,
            "client_errors": len(errs),
            "deck_downloads": len(deck_downloads),
        },
        "leads": leads,
        "new_users": new_users,
        "recent_sends": sends,
        "deck_downloads": deck_downloads,
        "recent_errors": [
            {"created_at": (e.get("created_at").isoformat()
                             if hasattr(e.get("created_at"), "isoformat")
                             else e.get("created_at_iso")),
             "message": e.get("message"), "url": e.get("url"),
             "user_id": e.get("user_id")}
            for e in errs
        ],
    }


@router.get("/stats")
async def stats() -> dict:
    users = await db.users.count_documents({})
    projects = await db.projects.count_documents({})
    leads = await db.leads.count_documents({})
    quotes = await db.quote_analyses.count_documents({})
    top = await db.search_stats.find({}, {"_id": 0}).sort("count", -1).to_list(10)
    plans = await db.users.aggregate([{"$group": {"_id": "$plan", "count": {"$sum": 1}}}]).to_list(10)
    agg = await db.projects.aggregate([
        {"$group": {"_id": None,
                    "volume": {"$sum": {"$ifNull": ["$estimation.total_avg", 0]}}}},
    ]).to_list(1)
    volume = round((agg[0]["volume"] if agg else 0) or 0, 2)
    return {"users": users, "projects": projects, "leads": leads, "quote_analyses": quotes,
            "top_searches": top, "plans": [{"plan": p["_id"] or "free", "count": p["count"]} for p in plans],
            "estimated_volume": volume}


@router.get("/drill/{metric}")
async def drill_metric(metric: str) -> dict:
    """Détail cliquable d'un indicateur du tableau de bord admin.

    Retourne { title, description, columns:[{key,label}], rows:[...] } avec les coordonnées
    (nom, e-mail, téléphone, société) pour cibler une campagne publicitaire.
    """
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "name": 1, "email": 1,
                                      "plan": 1, "role": 1, "phone": 1, "city": 1,
                                      "brand_city": 1, "company": 1, "brand_company_name": 1,
                                      "brand_phone": 1, "created_at": 1}).to_list(10000)
    umap = {u["user_id"]: u for u in users}

    def _contact(uid):
        u = umap.get(uid, {})
        return {
            "user_name": u.get("name") or "—",
            "user_email": u.get("email") or "—",
            "user_phone": u.get("phone") or u.get("brand_phone") or "—",
            "user_company": u.get("company") or u.get("brand_company_name") or "—",
            "user_plan": u.get("plan") or "free",
        }

    CONTACT_COLS = [
        {"key": "user_name", "label": "Nom"},
        {"key": "user_email", "label": "E-mail"},
        {"key": "user_phone", "label": "Téléphone"},
        {"key": "user_company", "label": "Société"},
        {"key": "user_plan", "label": "Plan"},
    ]

    if metric == "users":
        devs = await db.known_devices.find({}, {"_id": 0, "user_id": 1, "last_seen": 1}).to_list(50000)
        seen: dict[str, str] = {}
        for d in devs:
            uid, ls = d.get("user_id"), d.get("last_seen")
            if uid and ls and ls > seen.get(uid, ""):
                seen[uid] = ls
        rows = [{**_contact(u["user_id"]), "role": u.get("role") or "user",
                 "city": u.get("city") or u.get("brand_city") or "—",
                 "last_seen": seen.get(u["user_id"]) or "",
                 "created_at": u.get("created_at")} for u in users]
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return {"title": "Utilisateurs", "description": "Tous les comptes inscrits — cible publicitaire directe.",
                "columns": CONTACT_COLS + [{"key": "role", "label": "Rôle"},
                                           {"key": "city", "label": "Ville"},
                                           {"key": "last_seen", "label": "Dernière activité"},
                                           {"key": "created_at", "label": "Inscrit le"}],
                "rows": rows}

    if metric in ("projects", "estimated_volume"):
        projs = await db.projects.find({}, {"_id": 0, "estimation.lots": 0}).to_list(10000)
        rows = []
        for p in projs:
            val = round(((p.get("estimation") or {}).get("total_avg") or 0), 2)
            rows.append({**_contact(p.get("user_id")),
                         "project": p.get("name") or "Projet",
                         "project_type": p.get("project_type") or "—",
                         "city": p.get("city") or p.get("region") or "—",
                         "value_eur": val,
                         "created_at": p.get("created_at")})
        rows.sort(key=lambda r: r["value_eur"] if metric == "estimated_volume" else (r.get("created_at") or ""),
                  reverse=True)
        title = "Volume estimé (par projet)" if metric == "estimated_volume" else "Projets"
        return {"title": title,
                "description": "Projets et leurs porteurs — potentiel de dépense et coordonnées.",
                "columns": [{"key": "project", "label": "Projet"},
                            {"key": "project_type", "label": "Type"},
                            {"key": "city", "label": "Ville"},
                            {"key": "value_eur", "label": "Valeur estimée (€)"}] + CONTACT_COLS
                + [{"key": "created_at", "label": "Créé le"}],
                "rows": rows}

    if metric == "leads":
        leads = await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
        rows = [{"name": l.get("name") or "—", "email": l.get("email") or "—",
                 "phone": l.get("phone") or "—", "address": l.get("address") or "—",
                 "budget": l.get("budget") or "—", "status": l.get("status") or "nouveau",
                 "description": (l.get("description") or "")[:160],
                 "created_at": l.get("created_at")} for l in leads]
        return {"title": "Demandes de devis",
                "description": "Prospects ayant demandé un devis — cible publicitaire chaude.",
                "columns": [{"key": "name", "label": "Nom"}, {"key": "email", "label": "E-mail"},
                            {"key": "phone", "label": "Téléphone"}, {"key": "address", "label": "Adresse"},
                            {"key": "budget", "label": "Budget"}, {"key": "status", "label": "Statut"},
                            {"key": "description", "label": "Besoin"},
                            {"key": "created_at", "label": "Reçu le"}],
                "rows": rows}

    if metric == "quote_analyses":
        qs = await db.quote_analyses.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
        projs = await db.projects.find({}, {"_id": 0, "project_id": 1, "name": 1}).to_list(10000)
        pmap = {p["project_id"]: p.get("name") for p in projs}
        rows = [{**_contact(q.get("user_id")),
                 "company_analysed": q.get("company") or "—",
                 "project": pmap.get(q.get("project_id")) or "—",
                 "created_at": q.get("created_at")} for q in qs]
        return {"title": "Devis analysés",
                "description": "Utilisateurs ayant analysé un devis — fort intérêt produit.",
                "columns": [{"key": "company_analysed", "label": "Entreprise analysée"},
                            {"key": "project", "label": "Projet"}] + CONTACT_COLS
                + [{"key": "created_at", "label": "Analysé le"}],
                "rows": rows}

    if metric in ("total_revenue", "transactions"):
        q = {"payment_status": "paid"} if metric == "total_revenue" else {}
        txs = await db.payment_transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
        rows = [{**_contact(t.get("user_id")),
                 "plan_bought": t.get("plan_id") or "—",
                 "amount_eur": round((t.get("amount_cents") or 0) / 100, 2),
                 "status": t.get("payment_status") or t.get("status") or "—",
                 "created_at": t.get("created_at")} for t in txs]
        title = "Revenu total (paiements)" if metric == "total_revenue" else "Transactions"
        return {"title": title, "description": "Clients payants — cible de rétention et d'upsell.",
                "columns": CONTACT_COLS + [{"key": "plan_bought", "label": "Plan acheté"},
                                           {"key": "amount_eur", "label": "Montant (€)"},
                                           {"key": "status", "label": "Statut"},
                                           {"key": "created_at", "label": "Date"}],
                "rows": rows}

    if metric in ("active_subscriptions", "active_project_pass"):
        kind = "subscription" if metric == "active_subscriptions" else "one_time"
        q = {"status": "active", "kind": kind}
        if kind == "one_time":
            q["$or"] = [{"expires_at": {"$exists": False}},
                        {"expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}}]
        ents = await db.entitlements.find(q, {"_id": 0}).to_list(5000)
        rows = [{**_contact(e.get("user_id")),
                 "plan_code": e.get("plan_code") or e.get("plan_id") or "—",
                 "granted_at": e.get("granted_at")} for e in ents]
        title = "Abonnements actifs" if kind == "subscription" else "Project Pass actifs"
        return {"title": title, "description": "Clients avec un accès actif — cible d'upsell prioritaire.",
                "columns": CONTACT_COLS + [{"key": "plan_code", "label": "Offre"},
                                           {"key": "granted_at", "label": "Depuis"}],
                "rows": rows}

    raise HTTPException(404, "Indicateur inconnu")



class BulkEmailBody(BaseModel):
    recipients: list[str]
    subject: str
    message: str


@router.post("/bulk-email")
async def admin_bulk_email(body: BulkEmailBody, admin=Depends(admin_user)) -> dict:
    """Envoie un e-mail promotionnel à une liste de contacts sélectionnés dans le détail admin."""
    import os
    import re
    import asyncio
    from engines.emailer import send_email, wrap_html
    seen: set[str] = set()
    emails: list[str] = []
    for e in body.recipients or []:
        e = (e or "").strip().lower()
        if e and e not in seen and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            seen.add(e)
            emails.append(e)
    emails = emails[:200]
    if not emails:
        raise HTTPException(400, "Aucun destinataire valide")
    subject = (body.subject or "").strip()[:200] or "ConstruPilot"
    msg_html = (body.message or "").strip()
    if not msg_html:
        raise HTTPException(400, "Message vide")
    html = wrap_html(subject, msg_html.replace("\n", "<br>"),
                     unsubscribe_url=f"{os.getenv('FRONTEND_URL', '')}/desinscription")

    async def _one(addr: str) -> bool:
        try:
            await send_email(addr, subject, html)
            return True
        except Exception:  # noqa: BLE001
            return False

    sent = 0
    for i in range(0, len(emails), 10):
        chunk = emails[i:i + 10]
        res = await asyncio.gather(*[_one(a) for a in chunk])
        sent += sum(1 for r in res if r)
    await db.email_campaigns.insert_one({
        "campaign_id": "camp_" + os.urandom(5).hex(),
        "subject": subject,
        "message": msg_html[:5000],
        "recipients_count": len(emails),
        "recipients_sample": emails[:50],
        "sent": sent,
        "failed": len(emails) - sent,
        "sent_by": (admin or {}).get("email") or (admin or {}).get("user_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "sent": sent, "failed": len(emails) - sent, "total": len(emails)}


@router.get("/campaigns")
async def admin_campaigns() -> dict:
    """Historique des campagnes e-mail groupées."""
    rows = await db.email_campaigns.find({}, {"_id": 0, "message": 0, "recipients_sample": 0}) \
        .sort("created_at", -1).to_list(500)
    return {"campaigns": rows}




@router.get("/prices")
async def prices() -> list:
    overrides = {d["key"]: d async for d in db.price_reference.find({}, {"_id": 0})}
    return [{**l, **overrides.get(l["key"], {}), "overridden": l["key"] in overrides} for l in LOTS]


class PriceIn(BaseModel):
    mat_eco: float | None = None
    mat_std: float | None = None
    mat_premium: float | None = None
    labour: float | None = None
    hours: float | None = None


@router.put("/prices/{key}")
async def update_price(key: str, body: PriceIn) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.price_reference.update_one(
        {"key": key}, {"$set": {**updates, "key": key,
                                "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    from engines.catalog import LOTS_BY_KEY
    if key in LOTS_BY_KEY:
        LOTS_BY_KEY[key].update(updates)
    return {"key": key, **updates}


@router.delete("/prices/{key}")
async def reset_price(key: str) -> dict:
    await db.price_reference.delete_one({"key": key})
    return {"ok": True}


@router.get("/regions")
async def regions():
    docs = await db.regions.find({}, {"_id": 0}).to_list(500)
    return docs or REGIONS


class RegionIn(BaseModel):
    country: str
    region: str
    coef: float


@router.put("/regions")
async def upsert_region(body: RegionIn):
    from engines.catalog import REGIONS as R
    existing = next((r for r in R if r["country"] == body.country and r["region"] == body.region), None)
    if existing:
        existing["coef"] = body.coef
    else:
        R.append(body.model_dump())
    await db.regions.delete_many({})
    await db.regions.insert_many([dict(r) for r in R])
    return body.model_dump()


@router.get("/users")
async def users():
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)


class UserIn(BaseModel):
    role: str | None = None
    plan: str | None = None
    two_fa_enabled: bool | None = None
    two_fa_email: str | None = None


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserIn):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "two_fa_email" in updates:
        updates["two_fa_email"] = updates["two_fa_email"].strip().lower() or None
    await db.users.update_one({"user_id": user_id}, {"$set": updates})
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


# Collections purgées lors de la suppression définitive d'un compte (clé user_id).
_PURGE_COLLECTIONS = [
    "projects", "leads", "quote_analyses", "quote_sends", "quote_templates",
    "clients", "entitlements", "payment_transactions", "plans_takeoff",
    "plans_takeoff_history", "material_orders", "notifications", "photo_analyses",
    "pro_documents", "doc_counters", "steel_analyses", "roofing_analyses",
    "waterproofing_analyses", "vrd_analyses", "dpgf_imports",
    "company_price_libraries", "library_items", "suppliers", "situations",
    "prorata", "site_reports", "site_reserves", "site_checklist", "hr_files",
    "hr_notes", "hr_photos", "hr_timesheets", "push_subscriptions",
    "price_alerts", "api_keys", "referrals", "einvoice_accounts",
    "einvoice_inbox", "shared_calcs", "tool_presets", "pc_settings",
    "pc_study_history", "chat_messages", "activity_log", "user_sessions",
    "two_fa_codes", "password_reset_tokens", "known_devices", "login_attempts",
    "evolution_runs", "evolution_compares", "pro_documents_files",
    "photo_analyses", "marketplace_pros",
]


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(admin_user)) -> dict:
    """Supprime DÉFINITIVEMENT un compte et purge toutes ses données (irréversible)."""
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Utilisateur introuvable")
    if target.get("role") == "admin":
        raise HTTPException(403, "Impossible de supprimer un compte administrateur")
    if user_id == admin["user_id"]:
        raise HTTPException(403, "Vous ne pouvez pas supprimer votre propre compte")
    purged: dict[str, int] = {}
    owner_keys = ("user_id", "owner_user_id", "created_by", "pro_user_id",
                  "owner_id", "author_id", "from_user_id", "assigned_to")
    owner_filter = {"$or": [{k: user_id} for k in owner_keys]}
    for coll in dict.fromkeys(_PURGE_COLLECTIONS):
        try:
            res = await db[coll].delete_many(owner_filter)
            if res.deleted_count:
                purged[coll] = purged.get(coll, 0) + res.deleted_count
        except Exception:  # noqa: BLE001 — collection absente/robustesse
            continue
    # Organisations détenues par l'utilisateur + retrait des adhésions.
    try:
        org_res = await db.organizations.delete_many(
            {"$or": [{"owner_user_id": user_id}, {"owner_id": user_id}, {"user_id": user_id}]})
        if org_res.deleted_count:
            purged["organizations"] = purged.get("organizations", 0) + org_res.deleted_count
        await db.organizations.update_many(
            {"members.user_id": user_id},
            {"$pull": {"members": {"user_id": user_id}}})
        await db.org_members.delete_many({"user_id": user_id})
    except Exception:  # noqa: BLE001
        pass
    await db.users.delete_one({"user_id": user_id})
    return {"ok": True, "deleted_user": user_id,
            "email": target.get("email"), "purged": purged,
            "purged_total": sum(purged.values())}


@router.get("/projects")
async def all_projects():
    return await db.projects.find({}, {"_id": 0, "estimation.lots": 0}) \
        .sort("created_at", -1).to_list(300)


@router.get("/leads")
async def all_leads():
    return await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


@router.get("/leads/stats")
async def leads_stats() -> dict:
    total = await db.leads.count_documents({})
    particulier = await db.leads.count_documents({"source": {"$regex": "particulier$"}})
    pro = await db.leads.count_documents({"source": {"$regex": "pro$"}})
    landing = await db.leads.count_documents({"source": {"$regex": "^landing"}})
    nouveau = await db.leads.count_documents({"status": "nouveau"})
    gagne = await db.leads.count_documents({"status": "gagné"})
    assignes = await db.leads.count_documents({"assigned_to": {"$nin": [None, ""]}})
    en_attente = await db.leads.count_documents({"assigned_to": {"$nin": [None, ""]}, "handling_status": {"$in": [None, "en_cours"]}})
    pris_en_charge = await db.leads.count_documents({"handling_status": "acceptee"})
    refuses = await db.leads.count_documents({"handling_status": "refusee"})
    auto_assignes = await db.leads.count_documents({"auto_assigned": True})
    conversion = round(pris_en_charge / total * 100) if total else 0
    return {"total": total, "particulier": particulier, "pro": pro,
            "landing": landing, "nouveau": nouveau, "gagne": gagne,
            "assignes": assignes, "en_attente": en_attente,
            "pris_en_charge": pris_en_charge, "refuses": refuses,
            "auto_assignes": auto_assignes, "conversion": conversion}


class LeadStatusIn(BaseModel):
    status: str | None = None
    assigned_to: str | None = None


async def _notify_assigned_pro(pro: dict, lead: dict) -> None:
    """Notifie le pro qu'une demande de travaux lui a été assignée (cloche + e-mail)."""
    name = lead.get("name") or lead.get("email") or "un client"
    try:
        await db.notifications.insert_one({
            "notif_id": "n_" + secrets.token_hex(5),
            "user_id": pro["user_id"], "type": "lead_assigned",
            "lead_id": lead.get("lead_id"),
            "message": f"Nouvelle demande de travaux à prendre en charge : {name}",
            "created_at": datetime.now(timezone.utc).isoformat(), "read": False,
        })
    except Exception:
        pass
    try:
        from engines.emailer import send_email, wrap_html
        rows = [
            ("Client", lead.get("name") or "—"),
            ("E-mail", lead.get("email") or "—"),
            ("Téléphone", lead.get("phone") or "—"),
            ("Adresse", lead.get("address") or "—"),
            ("Disponibilité", lead.get("availability") or "—"),
            ("Budget", f"{lead.get('budget')} €" if lead.get("budget") else "—"),
            ("Demande", lead.get("description") or "—"),
        ]
        body = "".join(f'<p style="margin:0 0 8px 0"><b>{k} :</b> {v}</p>' for k, v in rows)
        html = wrap_html("Nouvelle demande de travaux à prendre en charge",
                         f"<p>Olá,</p><p>Une demande de travaux vous a été assignée :</p>{body}"
                         f"<p>Contactez le client pour la prendre en charge.</p>")
        await send_email(pro["email"], "Une demande de travaux vous a été assignée — ConstruPilot", html)
    except Exception:
        pass


@router.post("/leads/{lead_id}/invite")
async def invite_lead(lead_id: str) -> dict:
    """Envoie au lead un e-mail l'incitant à créer un compte."""
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Demande introuvable")
    if not lead.get("email"):
        raise HTTPException(400, "Cette demande n'a pas d'adresse e-mail")
    from routes.leads import send_account_invite
    try:
        await send_account_invite(lead["email"], lead.get("name") or "")
    except Exception as e:
        raise HTTPException(502, f"Envoi impossible : {e}")
    await db.leads.update_one({"lead_id": lead_id},
                              {"$set": {"invited_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "email": lead["email"]}


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadStatusIn):
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Demande introuvable")
    upd = {}
    if body.status is not None:
        upd["status"] = body.status
    notify_pro = None
    if body.assigned_to is not None:
        if body.assigned_to == "":
            upd["assigned_to"] = None
            upd["assigned_to_name"] = None
            upd["assigned_at"] = None
        else:
            pro = await db.users.find_one(
                {"user_id": body.assigned_to},
                {"_id": 0, "user_id": 1, "email": 1, "name": 1})
            if not pro:
                raise HTTPException(404, "Professionnel introuvable")
            upd["assigned_to"] = pro["user_id"]
            upd["assigned_to_name"] = pro.get("name") or pro.get("email")
            upd["assigned_at"] = datetime.now(timezone.utc).isoformat()
            upd["candidates"] = []  # attribution manuelle directe : plus de mise en concurrence
            upd["handling_status"] = None
            if lead.get("assigned_to") != pro["user_id"]:
                notify_pro = pro
    if upd:
        await db.leads.update_one({"lead_id": lead_id}, {"$set": upd})
    if notify_pro:
        await _notify_assigned_pro(notify_pro, {**lead, **upd})
        try:
            await db.leads.update_one({"lead_id": lead_id}, {"$push": {"assignment_log": {
                "action": "assignee_manuelle", "user_id": notify_pro["user_id"],
                "user_name": notify_pro.get("name") or notify_pro.get("email"),
                "at": datetime.now(timezone.utc).isoformat()}}})
        except Exception:
            pass
    return await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})


@router.get("/suppliers")
async def suppliers() -> dict:
    extra = await db.suppliers.find({}, {"_id": 0}).to_list(200)
    return {"builtin": price_search.SUPPLIERS, "custom": extra}


class SupplierIn(BaseModel):
    key: str
    name: str
    domain: str
    shipping: float = 30
    free_from: float = 300
    min_order: float = 0
    delivery_days: int = 4
    rating: float = 4.0
    stores: int = 0


@router.post("/suppliers")
async def add_supplier(body: SupplierIn):
    doc = body.model_dump()
    await db.suppliers.update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)
    if not any(s["key"] == doc["key"] for s in price_search.SUPPLIERS):
        price_search.SUPPLIERS.append(doc)
        price_search.SUPPLIERS_BY_KEY[doc["key"]] = doc
    return doc


@router.delete("/suppliers/{key}")
async def delete_supplier(key: str) -> dict:
    await db.suppliers.delete_one({"key": key})
    return {"ok": True}



# ---------- Plans & Monétisation ----------

@router.get("/plans")
async def list_all_plans():
    return await db.plans.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)


class PlanIn(BaseModel):
    plan_id: str
    code: str
    name: str
    tagline: str | None = None
    description: str | None = None
    audience: str = "particulier"
    kind: str = "subscription"
    amount_cents: int = 0
    currency: str = "eur"
    interval: str | None = None
    lookup_key: str | None = None
    trial_days: int | None = None
    features: list[str] = []
    quotas: dict = {}
    sort_order: int = 100
    active: bool = True
    highlight: bool = False
    badge: str | None = None


@router.post("/plans")
async def upsert_plan(body: PlanIn):
    doc = body.model_dump()
    # Préserver les IDs Stripe existants (ils sont re-synchronisés par sync-stripe)
    existing = await db.plans.find_one({"plan_id": doc["plan_id"]}, {"_id": 0})
    if existing:
        for k in ("stripe_product_id", "stripe_price_id", "synced_at"):
            if existing.get(k):
                doc.setdefault(k, existing[k])
    await db.plans.update_one({"plan_id": doc["plan_id"]}, {"$set": doc}, upsert=True)
    return doc


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str) -> dict:
    await db.plans.delete_one({"plan_id": plan_id})
    return {"ok": True}


@router.post("/plans/sync-stripe")
async def sync_stripe() -> dict:
    from engines import monetization
    await monetization.ensure_stripe_catalog()
    return {"ok": True}


@router.get("/feature-flags")
async def get_flags():
    flags = await db.feature_flags.find_one({"_id": "global"})
    if flags:
        flags.pop("_id", None)
    return flags or {}


@router.put("/feature-flags")
async def set_flags(body: dict):
    body.pop("_id", None)
    await db.feature_flags.update_one({"_id": "global"}, {"$set": body}, upsert=True)
    return body


# ---------- Revenue dashboard (Phase 1 : basique) ----------

@router.get("/revenue")
async def revenue_dashboard() -> dict:
    paid = await db.payment_transactions.find(
        {"payment_status": "paid"}, {"_id": 0}).to_list(5000)
    from collections import defaultdict
    by_plan = defaultdict(lambda: {"count": 0, "revenue_cents": 0})
    total = 0
    for p in paid:
        by_plan[p["plan_id"]]["count"] += 1
        by_plan[p["plan_id"]]["revenue_cents"] += p.get("amount_cents", 0)
        total += p.get("amount_cents", 0)
    active_subs = await db.entitlements.count_documents(
        {"status": "active", "kind": "subscription"})
    active_passes = await db.entitlements.count_documents(
        {"status": "active", "kind": "one_time",
         "$or": [{"expires_at": {"$exists": False}},
                 {"expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}}]})
    return {
        "total_revenue_cents": total,
        "total_revenue_eur": round(total / 100, 2),
        "active_subscriptions": active_subs,
        "active_project_pass": active_passes,
        "by_plan": [{"plan_id": k, **v} for k, v in by_plan.items()],
        "transactions_count": len(paid),
    }


# ---------- Sélecteur de modèle IA ----------

class AiModelIn(BaseModel):
    tier: str


@router.get("/ai-model")
async def get_ai_model() -> dict:
    from engines import ai
    current = await ai.get_text_tier()
    return {
        "current": current,
        "options": [
            {"tier": k, "label": v["label"], "desc": v["desc"], "model": v["model"],
             "quality": v.get("quality"), "speed": v.get("speed"), "cost": v.get("cost")}
            for k, v in ai.AI_TEXT_MODELS.items()
        ],
    }


@router.put("/ai-model")
async def set_ai_model(body: AiModelIn) -> dict:
    from fastapi import HTTPException
    from engines import ai
    if body.tier not in ai.AI_TEXT_MODELS:
        raise HTTPException(400, f"tier inconnu: {body.tier}")
    tier = await ai.set_text_tier(body.tier)
    return {"current": tier}


# Libellés lisibles des fonctionnalités IA
_AI_FEATURE_LABELS = {
    "smart_project": "Estimation Smart Project",
    "photo_analyse": "Analyse photo",
    "quote_scan": "Scanner de devis",
    "quote_compare": "Comparaison de devis",
    "project_advice": "Conseils projet",
    "coach": "Coach IA",
    "misc": "Autre",
}


@router.get("/ai-usage")
async def ai_usage() -> dict:
    """Compteur d'appels IA par fonctionnalité et par modèle."""
    from collections import defaultdict
    rows = await db.ai_usage.find({}, {"_id": 0}).to_list(1000)
    by_feature = defaultdict(int)
    by_model = defaultdict(int)
    total = 0
    detail = []
    for r in rows:
        calls = r.get("calls", 0)
        feat = r.get("feature", "misc")
        model = r.get("model", "?")
        by_feature[feat] += calls
        by_model[model] += calls
        total += calls
        detail.append({
            "feature": feat,
            "feature_label": _AI_FEATURE_LABELS.get(feat, feat),
            "provider": r.get("provider"),
            "model": model,
            "calls": calls,
            "last_used": r.get("last_used"),
        })
    detail.sort(key=lambda x: x["calls"], reverse=True)
    return {
        "total_calls": total,
        "by_feature": [{"feature": k, "feature_label": _AI_FEATURE_LABELS.get(k, k),
                        "calls": v} for k, v in sorted(by_feature.items(),
                                                       key=lambda i: -i[1])],
        "by_model": [{"model": k, "calls": v} for k, v in sorted(by_model.items(),
                                                                 key=lambda i: -i[1])],
        "detail": detail,
    }


@router.get("/ai-usage-daily")
async def ai_usage_daily(days: int = 30) -> dict:
    """Appels IA par jour sur les N derniers jours (pour le graphique de consommation)."""
    from datetime import datetime, timezone, timedelta
    days = max(1, min(days, 90))
    today = datetime.now(timezone.utc).date()
    rows = await db.ai_usage_daily.find({}, {"_id": 1, "calls": 1}).to_list(200)
    by_day = {r["_id"]: r.get("calls", 0) for r in rows}
    series = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append({"date": d, "calls": by_day.get(d, 0)})
    return {"days": days, "series": series, "total": sum(s["calls"] for s in series)}


class AiBudgetIn(BaseModel):
    threshold: int | None = None
    alert_email: str | None = None


@router.get("/ai-budget")
async def get_ai_budget() -> dict:
    from datetime import datetime, timezone
    doc = await db.app_settings.find_one({"_id": "ai"}) or {}
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = await db.ai_usage_daily.find({"_id": {"$regex": f"^{month}"}}).to_list(40)
    month_calls = sum(r.get("calls", 0) for r in rows)
    return {
        "threshold": doc.get("budget_threshold"),
        "alert_email": doc.get("budget_email"),
        "month": month,
        "month_calls": month_calls,
        "alert_sent_this_month": doc.get("budget_alert_month") == month,
    }


@router.put("/ai-budget")
async def set_ai_budget(body: AiBudgetIn) -> dict:
    updates = {}
    if body.threshold is not None:
        updates["budget_threshold"] = max(0, int(body.threshold))
    if body.alert_email is not None:
        updates["budget_email"] = body.alert_email.strip() or None
    # Réinitialise le verrou d'alerte quand le seuil change (nouvelle config)
    updates["budget_alert_month"] = None
    await db.app_settings.update_one({"_id": "ai"}, {"$set": updates}, upsert=True)
    return await get_ai_budget()


# ---------- Mode démo : débloquer toutes les options (Pro Business) ----------

@router.post("/demo-unlock")
async def demo_unlock(user=Depends(current_user)) -> dict:
    """Octroie au compte courant une entitlement Pro Business (démo, 10 ans) + l'add-on
    Facturation, pour débloquer toutes les options sans passer par Stripe.
    Stripe reste en mode test : la carte 4242 4242 4242 4242 fonctionne aussi dans le checkout."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    ent = {
        "entitlement_id": f"demo_{user['user_id']}",
        "user_id": user["user_id"], "plan_id": "pro_business_yearly",
        "status": "active", "source": "demo",
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(days=3650)).isoformat(),
    }
    await db.entitlements.update_one(
        {"entitlement_id": ent["entitlement_id"]}, {"$set": ent}, upsert=True)
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"invoicing_addon": True, "demo_mode": True}})
    from engines.monetization import user_tier
    return {"ok": True, "tier": await user_tier(user["user_id"]),
            "invoicing_addon": True, "card": "4242 4242 4242 4242 (Stripe test)"}


@router.post("/demo-lock")
async def demo_lock(user=Depends(current_user)) -> dict:
    """Désactive le mode démo (retire l'entitlement démo + l'add-on)."""
    await db.entitlements.delete_one({"entitlement_id": f"demo_{user['user_id']}"})
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"invoicing_addon": False, "demo_mode": False}})
    from engines.monetization import user_tier
    return {"ok": True, "tier": await user_tier(user["user_id"])}
