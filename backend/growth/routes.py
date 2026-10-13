"""ConstruPilot Growth — API (/api/growth). Roles: admin (users.role=admin or growth_members.admin), editor, reader."""
import asyncio
from urllib.parse import urlparse

import httpx
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from core.db import db
from growth import campaigns as camp
from growth import content as ct
from growth import google as gsc
from growth.common import env, get_project, new_id, now_iso, require_growth, spent
from growth.crawler import run_audit
from growth.providers import provider_status
from growth.seed import DEFAULT_SETTINGS, ensure_seed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/growth", tags=["growth"])
reader, editor, admin = require_growth("reader"), require_growth("editor"), require_growth("admin")
TASKS: dict[str, asyncio.Task] = {}


def _clean(d: dict) -> dict:
    d.pop("_id", None)
    return d


# ---------- me / projects / members ----------
@router.get("/me")
async def me(user=Depends(reader)) -> dict:
    await ensure_seed()
    projects = await db.growth_projects.find({}, {"_id": 0}).to_list(20)
    return {"role": user["growth_role"], "projects": projects, "providers": provider_status(), "google": gsc.status(),
            "pt_publish": {"configured": bool(env("GROWTH_PT_SITE_URL") and env("GROWTH_PUBLISH_TOKEN")), "site_url": env("GROWTH_PT_SITE_URL"), "inbox_ready": bool(env("GROWTH_PUBLISH_TOKEN"))}}


class SettingsIn(BaseModel):
    settings: dict


@router.put("/projects/{project_id}/settings")
async def update_settings(project_id: str, body: SettingsIn, user=Depends(admin)) -> dict:
    p = await get_project(project_id)
    merged = {**DEFAULT_SETTINGS, **(p.get("settings") or {}), **body.settings}
    await db.growth_projects.update_one({"project_id": project_id}, {"$set": {"settings": merged, "updated_at": now_iso()}})
    return {"ok": True, "settings": merged}


class MemberIn(BaseModel):
    email: str
    role: Literal["admin", "editor", "reader"]


@router.get("/members")
async def members(user=Depends(admin)) -> dict:
    return {"members": await db.growth_members.find({}, {"_id": 0}).to_list(200)}


@router.put("/members")
async def upsert_member(body: MemberIn, user=Depends(admin)) -> dict:
    u = await db.users.find_one({"email": body.email.lower().strip()}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
    if not u:
        raise HTTPException(404, "Aucun compte ConstruPilot avec cet email")
    await db.growth_members.update_one({"user_id": u["user_id"]}, {"$set": {"user_id": u["user_id"], "email": u["email"], "name": u.get("name"), "role": body.role, "updated_at": now_iso()}}, upsert=True)
    return {"ok": True}


@router.delete("/members/{user_id}")
async def delete_member(user_id: str, user=Depends(admin)) -> dict:
    await db.growth_members.delete_one({"user_id": user_id})
    return {"ok": True}


# ---------- overview ----------
@router.get("/overview")
async def overview(user=Depends(reader)) -> dict:
    await ensure_seed()
    out = []
    for p in await db.growth_projects.find({}, {"_id": 0}).to_list(20):
        pid = p["project_id"]
        audit = await db.growth_audits.find_one({"project_id": pid, "status": {"$in": ["completed", "stopped"]}}, {"_id": 0, }, sort=[("started_at", -1)])
        campaign = await db.growth_campaigns.find_one({"project_id": pid, "status": {"$in": ["completed", "stopped", "budget_reached"]}}, {"_id": 0}, sort=[("started_at", -1)])
        m = await camp.metrics(campaign["campaign_id"]) if campaign else None
        gsc_snap = await db.growth_gsc_snapshots.find_one({"project_id": pid}, {"_id": 0, "data": 0}, sort=[("synced_at", -1)])
        contents = {s: await db.growth_contents.count_documents({"project_id": pid, "status": s}) for s in ct.STATES}
        out.append({"project": p, "last_audit": audit, "last_campaign": {k: m[k] for k in ("campaign", "mention_rate", "citation_rate", "share_of_mentions", "coverage", "valid", "excluded_count")} if m else None,
                    "open_issues": await db.growth_issues.count_documents({"audit_id": audit["audit_id"], "status": "open"}) if audit else 0, "open_actions": await db.growth_actions.count_documents({"project_id": pid, "status": {"$ne": "done"}}),
                    "contents": contents, "spent_month_usd": await spent(pid, "month"), "spent_day_usd": await spent(pid, "day"), "gsc": gsc_snap,
                    "connections": {"search_console": bool(await db.growth_connections.find_one({"project_id": pid, "provider": "google_search_console", "status": "connected"}))}})
    return {"projects": out, "providers": provider_status()}


# ---------- brand facts & brands ----------
class FactIn(BaseModel):
    category: str
    statement: str
    source: str = ""
    date: str = ""
    status: Literal["confirmed", "to_verify", "planned"] = "to_verify"


@router.get("/projects/{project_id}/facts")
async def facts(project_id: str, user=Depends(reader)) -> dict:
    return {"facts": await db.growth_brand_facts.find({"project_id": project_id}, {"_id": 0}).sort("category", 1).to_list(500)}


@router.post("/projects/{project_id}/facts")
async def add_fact(project_id: str, body: FactIn, user=Depends(editor)) -> dict:
    await get_project(project_id)
    f = {"fact_id": new_id("fact"), "project_id": project_id, **body.model_dump(), "created_at": now_iso(), "created_by": user["user_id"]}
    await db.growth_brand_facts.insert_one(dict(f))
    return f


@router.put("/facts/{fact_id}")
async def edit_fact(fact_id: str, body: FactIn, user=Depends(editor)) -> dict:
    r = await db.growth_brand_facts.update_one({"fact_id": fact_id}, {"$set": {**body.model_dump(), "updated_at": now_iso(), "updated_by": user["user_id"]}})
    if not r.matched_count:
        raise HTTPException(404, "Fait introuvable")
    return {"ok": True}


@router.delete("/facts/{fact_id}")
async def del_fact(fact_id: str, user=Depends(editor)) -> dict:
    await db.growth_brand_facts.delete_one({"fact_id": fact_id})
    return {"ok": True}


class BrandIn(BaseModel):
    name: str
    variants: list[str] = []
    domains: list[str] = []
    confirmed: bool = True


@router.get("/projects/{project_id}/brands")
async def brands(project_id: str, user=Depends(reader)) -> dict:
    return {"brands": await db.growth_brands.find({"project_id": project_id}, {"_id": 0}).to_list(200)}


@router.post("/projects/{project_id}/brands")
async def add_brand(project_id: str, body: BrandIn, user=Depends(editor)) -> dict:
    await get_project(project_id)
    b = {"brand_id": new_id("brand"), "project_id": project_id, "name": body.name.strip(), "variants": list({body.name.strip(), *[v.strip() for v in body.variants if v.strip()]}),
         "domains": [d.strip().lower() for d in body.domains if d.strip()], "is_self": False, "confirmed": body.confirmed, "created_at": now_iso()}
    await db.growth_brands.insert_one(dict(b))
    return b


@router.put("/brands/{brand_id}")
async def edit_brand(brand_id: str, body: BrandIn, user=Depends(editor)) -> dict:
    await db.growth_brands.update_one({"brand_id": brand_id}, {"$set": {"name": body.name.strip(), "variants": list({body.name.strip(), *[v.strip() for v in body.variants if v.strip()]}),
                                                                        "domains": [d.strip().lower() for d in body.domains if d.strip()], "confirmed": body.confirmed, "suggested": False}})
    return {"ok": True}


@router.delete("/brands/{brand_id}")
async def del_brand(brand_id: str, user=Depends(editor)) -> dict:
    b = await db.growth_brands.find_one({"brand_id": brand_id}, {"_id": 0})
    if b and b.get("is_self"):
        raise HTTPException(400, "La marque ConstruPilot ne peut pas être retirée")
    await db.growth_brands.delete_one({"brand_id": brand_id})
    return {"ok": True}


# ---------- questions ----------
class QuestionIn(BaseModel):
    text: str = Field(min_length=8, max_length=400)
    intent: str = "découverte"
    branded: bool = False
    active: bool = True


@router.get("/projects/{project_id}/questions")
async def questions(project_id: str, user=Depends(reader)) -> dict:
    return {"questions": await db.growth_questions.find({"project_id": project_id}, {"_id": 0}).sort([("intent", 1), ("created_at", 1)]).to_list(500)}


@router.post("/projects/{project_id}/questions")
async def add_question(project_id: str, body: QuestionIn, user=Depends(editor)) -> dict:
    await get_project(project_id)
    q = {"question_id": new_id("q"), "project_id": project_id, **body.model_dump(), "version": 1, "created_at": now_iso()}
    await db.growth_questions.insert_one(dict(q))
    return q


@router.put("/questions/{question_id}")
async def edit_question(question_id: str, body: QuestionIn, user=Depends(editor)) -> dict:
    q = await db.growth_questions.find_one({"question_id": question_id}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Question introuvable")
    bump = q["text"] != body.text
    await db.growth_questions.update_one({"question_id": question_id}, {"$set": {**body.model_dump(), "updated_at": now_iso()}, **({"$inc": {"version": 1}} if bump else {})})
    return {"ok": True, "version_bumped": bump}


@router.delete("/questions/{question_id}")
async def del_question(question_id: str, user=Depends(editor)) -> dict:
    await db.growth_questions.delete_one({"question_id": question_id})
    return {"ok": True}


# ---------- audits ----------
@router.post("/projects/{project_id}/audits")
async def start_audit(project_id: str, max_pages: int | None = Body(None, embed=True), user=Depends(editor)) -> dict:
    p = await get_project(project_id)
    if await db.growth_audits.find_one({"project_id": project_id, "status": {"$in": ["queued", "running"]}}):
        raise HTTPException(409, "Un audit est déjà en cours pour ce projet")
    a = {"audit_id": new_id("aud"), "project_id": project_id, "status": "queued", "max_pages": min(int(max_pages or (p.get("settings") or {}).get("max_pages") or 50), 300),
         "created_at": now_iso(), "created_by": user["user_id"], "progress": 0, "pages_crawled": 0}
    await db.growth_audits.insert_one(dict(a))
    TASKS[a["audit_id"]] = asyncio.create_task(run_audit(a["audit_id"]))
    return a


@router.get("/projects/{project_id}/audits")
async def list_audits(project_id: str, user=Depends(reader)) -> dict:
    return {"audits": await db.growth_audits.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(50)}


@router.get("/audits/{audit_id}")
async def get_audit(audit_id: str, user=Depends(reader)) -> dict:
    a = await db.growth_audits.find_one({"audit_id": audit_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Audit introuvable")
    issues = await db.growth_issues.find({"audit_id": audit_id}, {"_id": 0}).sort([("severity", 1), ("url", 1)]).to_list(3000)
    pages = await db.growth_pages.find({"audit_id": audit_id}, {"_id": 0, "internal_links": 0}).to_list(500)
    return {"audit": a, "issues": issues, "pages": pages}


@router.post("/audits/{audit_id}/stop")
async def stop_audit(audit_id: str, user=Depends(editor)) -> dict:
    await db.growth_audits.update_one({"audit_id": audit_id}, {"$set": {"stop_requested": True}})
    return {"ok": True}


@router.put("/issues/{issue_id}")
async def update_issue(issue_id: str, status: Literal["open", "fixed", "ignored"] = Body(..., embed=True), user=Depends(editor)) -> dict:
    await db.growth_issues.update_one({"issue_id": issue_id}, {"$set": {"status": status, "updated_at": now_iso(), "updated_by": user["user_id"]}})
    return {"ok": True}


# ---------- campaigns & tests ----------
class ProviderCfg(BaseModel):
    provider: Literal["perplexity", "openai", "gemini", "anthropic"]
    model: str | None = None
    preset: str | None = None


class CampaignIn(BaseModel):
    name: str = "Campagne"
    question_ids: list[str] = Field(min_length=1)
    providers: list[ProviderCfg] = Field(min_length=1)
    repetitions: int = Field(1, ge=1, le=5)


@router.post("/projects/{project_id}/campaigns")
async def create_campaign(project_id: str, body: CampaignIn, user=Depends(editor)) -> dict:
    p = await get_project(project_id)
    st = provider_status()
    missing = [x.provider for x in body.providers if not st[x.provider]["configured"]]
    c = {"campaign_id": new_id("camp"), "project_id": project_id, "name": body.name, "question_ids": body.question_ids, "providers": [x.model_dump() for x in body.providers],
         "repetitions": body.repetitions, "status": "estimated", "protocol_version": camp.PROTOCOL_VERSION, "created_at": now_iso(), "created_by": user["user_id"], "done_tests": 0, "progress": 0}
    c["planned_tests"] = camp.plan_tests(c)
    c["estimated_cost_usd"] = camp.estimate(c)
    c["missing_connections"] = missing
    b = (p.get("settings") or {}).get("budgets") or {}
    c["budget_note"] = f"Plafonds : {b.get('daily_usd') or '∞'} $/jour, {b.get('monthly_usd') or '∞'} $/mois — dépensé aujourd'hui {await spent(project_id, 'day')} $"
    await db.growth_campaigns.insert_one(dict(c))
    return c


@router.get("/projects/{project_id}/campaigns")
async def list_campaigns(project_id: str, user=Depends(reader)) -> dict:
    return {"campaigns": await db.growth_campaigns.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(100)}


@router.post("/campaigns/{campaign_id}/run")
async def run_campaign(campaign_id: str, user=Depends(editor)) -> dict:
    c = await db.growth_campaigns.find_one({"campaign_id": campaign_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Campagne introuvable")
    if c["status"] == "running":
        raise HTTPException(409, "Campagne déjà en cours")
    if c["status"] in ("completed", "budget_reached"):
        raise HTTPException(409, "Campagne déjà terminée : créez une nouvelle campagne pour une nouvelle période")
    await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"status": "running", "stop_requested": False, "run_by": user["user_id"]}})
    camp.RUNNING[campaign_id] = asyncio.create_task(camp.run_campaign(campaign_id))
    return {"ok": True}


@router.post("/campaigns/{campaign_id}/stop")
async def stop_campaign(campaign_id: str, user=Depends(editor)) -> dict:
    await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"stop_requested": True}})
    return {"ok": True}


@router.get("/campaigns/{campaign_id}")
async def campaign_metrics(campaign_id: str, user=Depends(reader)) -> dict:
    if not await db.growth_campaigns.find_one({"campaign_id": campaign_id}):
        raise HTTPException(404, "Campagne introuvable")
    return await camp.metrics(campaign_id)


@router.get("/campaigns/{campaign_id}/tests")
async def campaign_tests(campaign_id: str, user=Depends(reader)) -> dict:
    return {"tests": await db.growth_tests.find({"campaign_id": campaign_id}, {"_id": 0, "response_text": 0}).sort([("question_text", 1), ("provider", 1), ("repetition", 1)]).to_list(5000)}


@router.get("/tests/{test_id}")
async def get_test(test_id: str, user=Depends(reader)) -> dict:
    t = await db.growth_tests.find_one({"test_id": test_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Test introuvable")
    return t


@router.put("/tests/{test_id}/mentions/{brand_id}")
async def flag_mention(test_id: str, brand_id: str, false_positive: bool = Body(..., embed=True), user=Depends(editor)) -> dict:
    t = await db.growth_tests.find_one({"test_id": test_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Test introuvable")
    mentions = t.get("mentions") or []
    for m in mentions:
        if m["brand_id"] == brand_id:
            m["false_positive"] = false_positive
            m["reviewed_by"] = user["user_id"]
    self_m = any(m["is_self"] and m["mention"] and not m.get("false_positive") for m in mentions)
    self_c = any(m["is_self"] and m["domain_citation"] and not m.get("false_positive") for m in mentions)
    await db.growth_tests.update_one({"test_id": test_id}, {"$set": {"mentions": mentions, "self_mentioned": self_m, "self_cited": self_c}})
    return {"ok": True}


@router.get("/campaigns-compare")
async def compare(a: str = Query(...), b: str = Query(...), user=Depends(reader)) -> dict:
    ca, cb = await db.growth_campaigns.find_one({"campaign_id": a}, {"_id": 0}), await db.growth_campaigns.find_one({"campaign_id": b}, {"_id": 0})
    if not ca or not cb:
        raise HTTPException(404, "Campagne introuvable")
    common_q = sorted(set(ca["question_ids"]) & set(cb["question_ids"]))
    same_cfg = sorted((p["provider"], p.get("model") or p.get("preset") or "") for p in ca["providers"]) == sorted((p["provider"], p.get("model") or p.get("preset") or "") for p in cb["providers"])
    changes = []
    if not same_cfg:
        changes.append("fournisseurs/modèles différents")
    if ca.get("protocol_version") != cb.get("protocol_version"):
        changes.append("version de protocole différente")
    if set(ca["question_ids"]) != set(cb["question_ids"]):
        changes.append(f"périmètre de questions différent ({len(common_q)} communes)")

    async def per_q(cid):
        out = {}
        async for t in db.growth_tests.find({"campaign_id": cid, "status": "completed", "question_id": {"$in": common_q}}, {"_id": 0, "question_id": 1, "self_mentioned": 1, "question_text": 1}):
            d = out.setdefault(t["question_id"], {"text": t["question_text"], "valid": 0, "self": 0})
            d["valid"] += 1; d["self"] += 1 if t.get("self_mentioned") else 0
        return out
    pa, pb = await per_q(a), await per_q(b)
    rows = [{"question_id": q, "text": (pa.get(q) or pb.get(q) or {}).get("text"), "a": camp._rate(pa.get(q, {}).get("self", 0), pa.get(q, {}).get("valid", 0)), "b": camp._rate(pb.get(q, {}).get("self", 0), pb.get(q, {}).get("valid", 0))} for q in common_q]
    return {"a": ca, "b": cb, "common_questions": len(common_q), "changes": changes, "rows": rows,
            "caveat": "Comparaison sur les questions communes uniquement. Tout changement listé ci-dessus limite l'interprétation ; une variation n'est pas une preuve de causalité."}


# ---------- actions ----------
class ActionIn(BaseModel):
    title: str
    problem: str = ""
    evidence: str = ""
    url: str = ""
    impact: Literal["fort", "moyen", "faible"] = "moyen"
    effort: Literal["faible", "moyen", "élevé"] = "moyen"
    owner: str = ""
    due_date: str = ""
    kpi: str = ""
    status: Literal["todo", "doing", "done"] = "todo"
    source: str = "manuel"
    source_ref: str = ""


@router.get("/projects/{project_id}/actions")
async def actions(project_id: str, user=Depends(reader)) -> dict:
    return {"actions": await db.growth_actions.find({"project_id": project_id}, {"_id": 0}).sort([("status", 1), ("impact", 1)]).to_list(500)}


@router.post("/projects/{project_id}/actions")
async def add_action(project_id: str, body: ActionIn, user=Depends(editor)) -> dict:
    await get_project(project_id)
    a = {"action_id": new_id("act"), "project_id": project_id, **body.model_dump(), "created_at": now_iso(), "created_by": user["user_id"]}
    await db.growth_actions.insert_one(dict(a))
    return a


@router.put("/actions/{action_id}")
async def edit_action(action_id: str, body: ActionIn, user=Depends(editor)) -> dict:
    await db.growth_actions.update_one({"action_id": action_id}, {"$set": {**body.model_dump(), "updated_at": now_iso()}})
    return {"ok": True}


@router.delete("/actions/{action_id}")
async def del_action(action_id: str, user=Depends(editor)) -> dict:
    await db.growth_actions.delete_one({"action_id": action_id})
    return {"ok": True}


@router.post("/projects/{project_id}/actions/generate")
async def generate_actions(project_id: str, user=Depends(editor)) -> dict:
    """Deterministic action plan from open audit issues (grouped by kind) and from the last campaign's unanswered questions."""
    await get_project(project_id)
    created = 0
    existing = {a.get("source_ref") for a in await db.growth_actions.find({"project_id": project_id}, {"_id": 0, "source_ref": 1}).to_list(1000)}
    last_audit = await db.growth_audits.find_one({"project_id": project_id, "status": {"$in": ["completed", "stopped"]}}, {"_id": 0}, sort=[("started_at", -1)])
    if last_audit:
        groups = {}
        async for i in db.growth_issues.find({"audit_id": last_audit["audit_id"], "status": "open"}, {"_id": 0}):
            groups.setdefault(i["kind"], []).append(i)
        impact = {"haute": "fort", "moyenne": "moyen", "basse": "faible"}
        for kind, items in groups.items():
            ref = f"audit:{last_audit['audit_id']}:{kind}"
            if ref in existing:
                continue
            first = items[0]
            await db.growth_actions.insert_one({"action_id": new_id("act"), "project_id": project_id, "title": f"Corriger « {kind} » sur {len(items)} page(s)", "problem": first["consequence"],
                                                "evidence": first["evidence"], "url": first["url"], "impact": impact[first["severity"]], "effort": first["effort"], "owner": "", "due_date": "",
                                                "kpi": f"0 page avec « {kind} » au prochain audit", "status": "todo", "source": "audit", "source_ref": ref, "issue_ids": [i["issue_id"] for i in items][:200], "created_at": now_iso()})
            created += 1
    campaign = await db.growth_campaigns.find_one({"project_id": project_id, "status": {"$in": ["completed", "stopped", "budget_reached"]}}, {"_id": 0}, sort=[("started_at", -1)])
    if campaign:
        absent = {}
        async for t in db.growth_tests.find({"campaign_id": campaign["campaign_id"], "status": "completed", "branded": False}, {"_id": 0}):
            d = absent.setdefault(t["question_id"], {"text": t["question_text"], "valid": 0, "self": 0, "others": set()})
            d["valid"] += 1; d["self"] += 1 if t.get("self_mentioned") else 0
            d["others"].update(m["name"] for m in t.get("mentions") or [] if not m["is_self"] and m["mention"])
        for qid, d in absent.items():
            ref = f"campaign:{campaign['campaign_id']}:{qid}"
            if d["self"] == 0 and d["valid"] and ref not in existing:
                await db.growth_actions.insert_one({"action_id": new_id("act"), "project_id": project_id, "title": f"Publier une réponse utile à : « {d['text'][:90]} »", "problem": "ConstruPilot absent des réponses IA testées pour cette question",
                                                    "evidence": f"0/{d['valid']} réponses valides mentionnent ConstruPilot ; marques citées : {', '.join(sorted(d['others'])) or 'aucune'} (hypothèse : absence de contenu ciblé)",
                                                    "url": "", "impact": "moyen", "effort": "moyen", "owner": "", "due_date": "", "kpi": "Mention de ConstruPilot sur cette question lors d'une prochaine campagne",
                                                    "status": "todo", "source": "campaign", "source_ref": ref, "question_id": qid, "created_at": now_iso()})
                created += 1
    return {"ok": True, "created": created}


# ---------- contents ----------
class ContentIn(BaseModel):
    topic: str
    intent: str = "découverte"
    audience: str = ""
    format: str = "guide pratique"
    scheduled_for: str = ""
    title: str = ""
    slug: str = ""
    description: str = ""
    body_markdown: str = ""
    cta: str = ""
    question_id: str = ""
    action_id: str = ""


@router.get("/projects/{project_id}/contents")
async def contents(project_id: str, user=Depends(reader)) -> dict:
    items = await db.growth_contents.find({"project_id": project_id}, {"_id": 0, "body_markdown": 0, "versions": 0}).sort("created_at", -1).to_list(500)
    today = datetime.now(timezone.utc).date()
    calendar = [{"date": (today + timedelta(days=i)).isoformat(), "items": [c for c in items if (c.get("scheduled_for") or "")[:10] == (today + timedelta(days=i)).isoformat()]} for i in range(30)]
    return {"contents": items, "calendar": calendar, "states": ct.STATES}


@router.post("/projects/{project_id}/contents")
async def add_content(project_id: str, body: ContentIn, user=Depends(editor)) -> dict:
    await get_project(project_id)
    c = {"content_id": new_id("cnt"), "project_id": project_id, **body.model_dump(), "status": "idea", "version": 1, "versions": [], "checks": None, "created_at": now_iso(), "created_by": user["user_id"]}
    await db.growth_contents.insert_one(dict(c))
    return c


@router.get("/contents/{content_id}")
async def get_content(content_id: str, user=Depends(reader)) -> dict:
    c = await db.growth_contents.find_one({"content_id": content_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contenu introuvable")
    return c


async def _load(content_id: str) -> tuple[dict, dict]:
    c = await db.growth_contents.find_one({"content_id": content_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contenu introuvable")
    return c, await get_project(c["project_id"])


def _snapshot(c: dict) -> dict:
    return {"version": c.get("version", 1), "at": now_iso(), "title": c.get("title"), "slug": c.get("slug"), "description": c.get("description"), "body_markdown": c.get("body_markdown"), "status": c.get("status")}


@router.put("/contents/{content_id}")
async def edit_content(content_id: str, body: ContentIn, user=Depends(editor)) -> dict:
    c, _ = await _load(content_id)
    if c["status"] == "published" and user["growth_role"] != "admin":
        raise HTTPException(403, "Modifier un article publié requiert le rôle admin")
    upd = {k: v for k, v in body.model_dump().items() if v != "" or k in ("body_markdown",)}
    changed = any(c.get(k) != v for k, v in upd.items())
    sets = {**upd, "updated_at": now_iso(), "updated_by": user["user_id"]}
    if changed and c.get("body_markdown"):
        sets["version"] = c.get("version", 1) + 1
        sets["checks"] = None
        if c["status"] in ("approved", "scheduled"):
            sets["status"] = "review"
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": sets, **({"$push": {"versions": _snapshot(c)}} if changed and c.get("body_markdown") else {})})
    return {"ok": True, "version": sets.get("version", c.get("version", 1))}


@router.post("/contents/{content_id}/brief")
async def make_brief(content_id: str, user=Depends(editor)) -> dict:
    c, p = await _load(content_id)
    try:
        b = await ct.generate_brief(p, c)
    except Exception as e:
        raise HTTPException(502, f"Génération du brief impossible : {e}")
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": {**{k: b.get(k) for k in ("title", "slug", "description", "audience", "outline", "internal_links", "sources_to_check", "cta", "search_intent_note")}, "status": "brief", "updated_at": now_iso()}})
    return await get_content(content_id, user)


@router.post("/contents/{content_id}/draft")
async def make_draft(content_id: str, user=Depends(editor)) -> dict:
    c, p = await _load(content_id)
    if not c.get("outline"):
        raise HTTPException(400, "Préparez d'abord le brief")
    try:
        d = await ct.generate_draft(p, c)
    except Exception as e:
        raise HTTPException(502, f"Rédaction impossible : {e}")
    sets = {"title": d.get("title") or c.get("title"), "body_markdown": d.get("body_markdown") or "", "claims_about_construpilot": d.get("claims_about_construpilot") or [], "sources": d.get("sources") or [], "faq": d.get("faq") or [],
            "status": "draft", "checks": None, "updated_at": now_iso(), "version": c.get("version", 1) + (1 if c.get("body_markdown") else 0)}
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": sets, **({"$push": {"versions": _snapshot(c)}} if c.get("body_markdown") else {})})
    return await get_content(content_id, user)


@router.post("/contents/{content_id}/check")
async def check_content(content_id: str, user=Depends(editor)) -> dict:
    c, p = await _load(content_id)
    if not c.get("body_markdown"):
        raise HTTPException(400, "Aucun texte à vérifier")
    checks = await ct.quality_checks(p, c)
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": {"checks": checks, "status": "review" if c["status"] in ("draft", "brief") else c["status"]}})
    return checks


@router.post("/contents/{content_id}/status")
async def set_status(content_id: str, status: str = Body(..., embed=True), scheduled_for: str = Body("", embed=True), user=Depends(editor)) -> dict:
    c, p = await _load(content_id)
    if status not in ct.STATES:
        raise HTTPException(400, "État inconnu")
    if status in ("approved", "scheduled"):
        if not (c.get("checks") or {}).get("passed") or c["checks"].get("checked_at", "") < c.get("updated_at", ""):
            raise HTTPException(409, "Relancez les contrôles de qualité sur la version actuelle avant d'approuver")
        if user["growth_role"] not in ("admin", "editor"):
            raise HTTPException(403, "Approbation réservée aux éditeurs/admins")
    sets = {"status": status, "status_changed_at": now_iso()}
    if status in ("approved", "scheduled"):
        sets["approved_by"] = user["user_id"]; sets["approved_at"] = now_iso()
    if scheduled_for:
        sets["scheduled_for"] = scheduled_for
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": sets})
    return {"ok": True}


@router.post("/contents/{content_id}/publish")
async def publish_content(content_id: str, user=Depends(editor)) -> dict:
    c, p = await _load(content_id)
    if c["status"] not in ("approved", "scheduled", "failed"):
        raise HTTPException(409, "Le contenu doit être approuvé avant publication")
    checks = c.get("checks") or {}
    if not checks.get("passed") or checks.get("checked_at", "") < c.get("updated_at", ""):
        raise HTTPException(409, "Contrôles de qualité manquants ou obsolètes pour cette version : une affirmation non vérifiée bloque la publication")
    if (p.get("settings") or {}).get("publish_mode") != "auto" and not c.get("approved_by"):
        raise HTTPException(409, "Mode validation : une approbation explicite est requise")
    lock = await db.growth_contents.update_one({"content_id": content_id, "publishing": {"$ne": True}}, {"$set": {"publishing": True}})
    if not lock.modified_count:
        raise HTTPException(409, "Publication déjà en cours")
    try:
        res = await ct.publish(p, c, user["user_id"])
        await db.growth_contents.update_one({"content_id": content_id}, {"$set": {"status": "published", **res, "publishing": False, "updated_at": now_iso()}, "$push": {"publications": res}})
        from growth.marketing import on_published
        asyncio.create_task(on_published(p, {**c, **res}))
        return res
    except Exception as e:
        await db.growth_contents.update_one({"content_id": content_id}, {"$set": {"status": "failed", "publish_error": str(e)[:300], "publishing": False}})
        raise HTTPException(502, f"Publication échouée : {e}")


@router.post("/contents/{content_id}/rollback/{version}")
async def rollback(content_id: str, version: int, user=Depends(editor)) -> dict:
    c, p = await _load(content_id)
    snap = next((v for v in c.get("versions") or [] if v.get("version") == version), None)
    if not snap:
        raise HTTPException(404, "Version introuvable")
    sets = {k: snap.get(k) for k in ("title", "slug", "description", "body_markdown")}
    sets.update({"version": c.get("version", 1) + 1, "checks": None, "status": "review", "updated_at": now_iso()})
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": sets, "$push": {"versions": _snapshot(c)}})
    if c["status"] == "published":
        payload = ct.article_payload(p, {**c, **sets})
        await db.autoseo_articles.update_one({"autoseo_id": payload["autoseo_id"]}, {"$set": {"content_html": payload["content_html"], "content_markdown": payload["content_markdown"], "title": payload["title"], "meta_description": payload["meta_description"], "updated_at": now_iso()}})
    return {"ok": True, "version": sets["version"], "blog_updated": c["status"] == "published"}


@router.delete("/contents/{content_id}")
async def archive_content(content_id: str, user=Depends(editor)) -> dict:
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": {"status": "archived", "updated_at": now_iso()}})
    return {"ok": True}


# ---------- publish inbox (received by the .pt deployment) ----------
@router.post("/publish-inbox")
async def publish_inbox(payload: dict = Body(...), authorization: str = Header("")) -> dict:
    token = env("GROWTH_PUBLISH_TOKEN")
    if not token or not secrets.compare_digest(authorization.removeprefix("Bearer ").strip(), token):
        raise HTTPException(401, "Jeton de publication invalide")
    if not payload.get("autoseo_id", "").startswith("growth_") or not payload.get("slug") or not payload.get("content_html"):
        raise HTTPException(422, "Article incomplet")
    allowed = {k: payload.get(k) for k in ("autoseo_id", "title", "slug", "published_url", "meta_description", "content_html", "content_markdown", "keywords", "language_code", "status", "published_at", "updated_at", "faq_schema", "source", "growth_content_id", "growth_version")}
    await db.autoseo_articles.update_one({"autoseo_id": allowed["autoseo_id"]}, {"$set": {**allowed, "received_at": now_iso()}, "$setOnInsert": {"first_received_at": now_iso()}}, upsert=True)
    return {"ok": True, "url": allowed["published_url"]}


# ---------- links & notoriety ----------
class LinkIn(BaseModel):
    kind: Literal["backlink", "opportunity", "mention_no_link"] = "opportunity"
    source_url: str
    target_url: str = ""
    context: str = ""
    category: str = ""
    sponsored: bool = False
    status: Literal["observed", "to_contact", "contacted", "obtained", "declined"] = "observed"
    proposal: str = ""


@router.get("/projects/{project_id}/links")
async def links(project_id: str, user=Depends(reader)) -> dict:
    return {"links": await db.growth_links.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(500)}


@router.post("/projects/{project_id}/links")
async def add_link(project_id: str, body: LinkIn, user=Depends(editor)) -> dict:
    await get_project(project_id)
    l = {"link_id": new_id("lnk"), "project_id": project_id, **body.model_dump(), "verified_at": now_iso(), "created_at": now_iso(), "created_by": user["user_id"]}
    await db.growth_links.insert_one(dict(l))
    return l


@router.put("/links/{link_id}")
async def edit_link(link_id: str, body: LinkIn, user=Depends(editor)) -> dict:
    await db.growth_links.update_one({"link_id": link_id}, {"$set": {**body.model_dump(), "verified_at": now_iso()}})
    return {"ok": True}


@router.delete("/links/{link_id}")
async def del_link(link_id: str, user=Depends(editor)) -> dict:
    await db.growth_links.delete_one({"link_id": link_id})
    return {"ok": True}


# ---------- integrations / google ----------
@router.get("/integrations")
async def integrations(user=Depends(reader)) -> dict:
    conns = await db.growth_connections.find({}, {"_id": 0, "tokens_enc": 0}).to_list(50)
    return {"providers": provider_status(), "google": gsc.status(), "connections": conns,
            "pt_publish": {"configured": bool(env("GROWTH_PT_SITE_URL") and env("GROWTH_PUBLISH_TOKEN")), "site_url": env("GROWTH_PT_SITE_URL"), "inbox_token_set": bool(env("GROWTH_PUBLISH_TOKEN")),
                           "how_to": "Définir GROWTH_PUBLISH_TOKEN (même valeur) sur les deux déploiements et GROWTH_PT_SITE_URL=https://construpilot.pt sur celui-ci."},
            "ga4": {"configured": False, "how_to": "GA4 : nécessite l'API Analytics Data et une propriété ; non connecté."}}


@router.post("/integrations/google/start")
async def google_start(project_id: str = Body(..., embed=True), provider: Literal["google_search_console", "google_ads"] = Body("google_search_console", embed=True), user=Depends(admin)) -> dict:
    if not gsc.status()["client_configured"]:
        raise HTTPException(409, {"message": "Client OAuth Google non configuré", **gsc.status()})
    return {"url": gsc.start_url(project_id, user["user_id"], provider)}


@router.get("/integrations/google/callback")
async def google_callback(code: str = "", state: str = "", error: str = ""):
    if error or not code:
        return RedirectResponse(f"{env('FRONTEND_URL')}/admin/growth?tab=integrations&google=error")
    try:
        data = await gsc.handle_callback(code, state)
    except Exception as e:
        logger.warning("google callback failed: %s", e)
        return RedirectResponse(f"{env('FRONTEND_URL')}/admin/growth?tab=integrations&google=error")
    if data.get("provider") == "google_ads":
        return RedirectResponse(f"{env('FRONTEND_URL')}/admin/growth?tab=marketing&google_ads=connected")
    return RedirectResponse(f"{env('FRONTEND_URL')}/admin/growth?tab=integrations&google=connected")


@router.post("/integrations/google/sync")
async def google_sync(project_id: str = Body(..., embed=True), site_url: str = Body("", embed=True), user=Depends(editor)) -> dict:
    if site_url:
        await db.growth_connections.update_one({"project_id": project_id, "provider": "google_search_console"}, {"$set": {"site_url": site_url}})
    return await gsc.sync(project_id)


@router.get("/projects/{project_id}/search-console")
async def search_console(project_id: str, user=Depends(reader)) -> dict:
    snap = await db.growth_gsc_snapshots.find_one({"project_id": project_id}, {"_id": 0}, sort=[("synced_at", -1)])
    conn = await db.growth_connections.find_one({"project_id": project_id, "provider": "google_search_console"}, {"_id": 0, "tokens_enc": 0})
    return {"connection": conn, "snapshot": snap, "conversions": {"available": False, "note": "Inscriptions / demandes de démo : aucun événement instrumenté relié à Growth — non affiché."}}


# ---------- budget ----------
@router.get("/projects/{project_id}/costs")
async def costs(project_id: str, user=Depends(reader)) -> dict:
    p = await get_project(project_id)
    by_provider = await db.growth_costs.aggregate([{"$match": {"project_id": project_id}}, {"$group": {"_id": {"provider": "$provider", "month": "$month", "estimated": "$estimated"}, "usd": {"$sum": "$usd"}, "n": {"$sum": 1}}}]).to_list(200)
    by_day = await db.growth_costs.aggregate([{"$match": {"project_id": project_id}}, {"$group": {"_id": "$day", "usd": {"$sum": "$usd"}}}, {"$sort": {"_id": -1}}, {"$limit": 31}]).to_list(31)
    return {"budgets": (p.get("settings") or {}).get("budgets"), "spent_day": await spent(project_id, "day"), "spent_month": await spent(project_id, "month"),
            "by_provider": [{"provider": r["_id"]["provider"], "month": r["_id"]["month"], "estimated": r["_id"]["estimated"], "usd": round(r["usd"], 4), "calls": r["n"]} for r in by_provider],
            "by_day": [{"day": r["_id"], "usd": round(r["usd"], 4)} for r in by_day], "note": "Coûts Perplexity = montants réels renvoyés par l'API ; coûts via clé universelle = estimations à partir des tokens."}


# ---------- résultats (article → Search Console → inscriptions) ----------
@router.get("/projects/{project_id}/results")
async def results(project_id: str, user=Depends(reader)) -> dict:
    p = await get_project(project_id)
    site = p["site_url"].rstrip("/")
    snap = await db.growth_gsc_snapshots.find_one({"project_id": project_id}, {"_id": 0}, sort=[("synced_at", -1)])
    gsc_pages = {}
    for row in ((snap or {}).get("data") or {}).get("page") or []:
        gsc_pages[urlparse(row["key"]).path.rstrip("/") or "/"] = row
    users = await db.users.find({"attribution": {"$exists": True}}, {"_id": 0, "attribution": 1, "created_at": 1}).to_list(20000)
    leads = await db.leads.find({}, {"_id": 0, "utm_campaign": 1, "utm_source": 1, "source": 1}).to_list(20000)
    rows = []
    async for c in db.growth_contents.find({"project_id": project_id, "status": "published"}, {"_id": 0, "content_id": 1, "title": 1, "slug": 1, "published_url": 1, "published_at": 1, "created_by": 1}).sort("published_at", -1):
        path = f"/blog/{c['slug']}"
        g = gsc_pages.get(path) or {}
        organic = sum(1 for u in users if (u["attribution"].get("landing_path") or "").rstrip("/") == path and not u["attribution"].get("utm_campaign"))
        paid = sum(1 for u in users if u["attribution"].get("utm_campaign") == c["slug"])
        email = sum(1 for u in users if u["attribution"].get("utm_medium") == "email" and (u["attribution"].get("landing_path") or "").rstrip("/") == path)
        lead_n = sum(1 for l in leads if l.get("utm_campaign") == c["slug"])
        ads_n = await db.growth_ads.count_documents({"content_id": c["content_id"], "status": {"$in": ["approved", "published"]}})
        rows.append({**c, "path": path, "clicks": g.get("clicks", 0), "impressions": g.get("impressions", 0), "ctr": g.get("ctr", 0), "position": g.get("position"),
                     "gsc_available": bool(g), "signups_organic": organic, "signups_ads": paid, "signups_email": email, "leads": lead_n, "ads_ready": ads_n})
    totals = {k: sum(r[k] for r in rows) for k in ("clicks", "impressions", "signups_organic", "signups_ads", "signups_email", "leads")}
    nl_stats = [{"newsletter_id": n["newsletter_id"], "subject": n["subject"], "sent_at": n.get("sent_at"), "sent": (n.get("result") or {}).get("sent", 0),
                 "signups": sum(1 for u in users if u["attribution"].get("utm_campaign") == n["newsletter_id"])}
                async for n in db.growth_newsletters.find({"project_id": project_id, "status": "sent"}, {"_id": 0}).sort("sent_at", -1)]
    return {"rows": rows, "totals": totals, "newsletters": nl_stats, "site": site,
            "gsc": {"connected": bool(snap), "period": {"start": snap["start"], "end": snap["end"]} if snap else None, "synced_at": (snap or {}).get("synced_at")},
            "attributed_users": len(users),
            "limits": ["Search Console : agrégats par page sur 28 jours, décalage ~2 jours ; une page sans ligne n'a pas eu d'impression enregistrée.",
                       "Inscriptions : attribution « premier contact » (page d'entrée / UTM enregistrés dans le navigateur à la première visite, transmis à l'inscription) — depuis la mise en place uniquement ; pas de suivi inter-appareils.",
                       "Annonces : les URL finales portent utm_campaign=<slug de l'article> ; newsletters : utm_campaign=<id newsletter>."]}


# ---------- push vers un autre déploiement (production / .pt) ----------
@router.post("/contents/{content_id}/push")
async def push_content(content_id: str, target_url: str = Body(..., embed=True), user=Depends(admin)) -> dict:
    """Envoie l'article publié ici vers l'inbox d'un autre déploiement (même GROWTH_PUBLISH_TOKEN des deux côtés)."""
    c, p = await _load(content_id)
    if c["status"] != "published":
        raise HTTPException(400, "Publiez d'abord l'article ici")
    token = env("GROWTH_PUBLISH_TOKEN")
    if not token:
        raise HTTPException(409, "GROWTH_PUBLISH_TOKEN manquant sur ce déploiement")
    target = target_url.rstrip("/")
    allowed = {u.rstrip("/") for u in (env("GROWTH_PUSH_TARGETS") or "https://construpilot.fr,https://www.construpilot.fr,https://construpilot.pt,https://www.construpilot.pt").split(",") if u.strip()}
    if env("GROWTH_PT_SITE_URL"):
        allowed.add(env("GROWTH_PT_SITE_URL").rstrip("/"))
    if target not in allowed:
        raise HTTPException(422, f"Cible non autorisée — cibles admises : {', '.join(sorted(allowed))} (variable GROWTH_PUSH_TARGETS)")
    payload = ct.article_payload({**p, "site_url": target}, c)
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(f"{target}/api/growth/publish-inbox", json=payload, headers={"Authorization": f"Bearer {token}"})
        except Exception as e:
            raise HTTPException(502, f"Cible injoignable : {type(e).__name__}")
    if r.status_code == 401:
        raise HTTPException(409, "La cible refuse le jeton : définir la même valeur GROWTH_PUBLISH_TOKEN dans Publish → Secrets puis redéployer")
    if r.status_code >= 300:
        raise HTTPException(502, f"Cible : HTTP {r.status_code} {r.text[:120]}")
    res = {"target": target, "url": r.json().get("url"), "pushed_at": now_iso(), "pushed_by": user["user_id"]}
    await db.growth_contents.update_one({"content_id": content_id}, {"$push": {"pushes": res}})
    return res


# ---------- assistant ----------
_PT_MARKERS = ("orçament", "construção", "renovaç", "casa de banho", "custo",
               "distrito", "portugal", "reabilitaç", "eficiência", "quanto custa",
               "em 30 s", "iva 6", "obra em", "obras com")


def _looks_portuguese(title: str) -> bool:
    """Heuristique légère : détecte un titre portugais pour ne jamais le servir sur un chemin FR."""
    s = (title or "").lower()
    return any(m in s for m in _PT_MARKERS)


@router.get("/seo-overrides")
async def public_seo_overrides() -> dict:
    """Public : surcharges title/description approuvées, appliquées à chaud par le composant SEO du site.
    construpilot.fr est FR : si plusieurs variantes approuvées existent pour un même chemin, on sert la
    variante NON portugaise (évite qu'un titre PT auto-généré écrase le titre FR de la page d'accueil)."""
    out: dict = {}
    titles: dict = {}  # path -> [(title, description), ...] (plus récents d'abord)
    async for o in db.growth_seo_overrides.find(
            {"status": "approved"},
            {"_id": 0, "path": 1, "title": 1, "description": 1, "canonical": 1, "kind": 1}):
        cur = out.setdefault(o["path"], {})
        if o.get("kind") == "canonical":
            cur["canonical"] = o.get("canonical") or o["path"]
        else:
            titles.setdefault(o["path"], []).append((o.get("title"), o.get("description")))
    for path, variants in titles.items():
        # Préfère une variante française quand plusieurs coexistent ; sinon garde la seule disponible (chemins PT légitimes).
        chosen = next((v for v in variants if v[0] and not _looks_portuguese(v[0])), variants[0])
        out.setdefault(path, {}).update({"title": chosen[0], "description": chosen[1]})
    return {"overrides": out}


@router.get("/redirects")
async def public_redirects() -> dict:
    """Public : redirections 404 → page valide décidées par la correction automatique (appliquées par la page 404 du site)."""
    return {"redirects": {r["from_path"]: r["to_path"] async for r in db.growth_redirects.find({"status": "approved"}, {"_id": 0, "from_path": 1, "to_path": 1})}}


@router.get("/projects/{project_id}/autofix")
async def autofix_status(project_id: str, user=Depends(reader)) -> dict:
    p = await get_project(project_id)
    st = {**DEFAULT_SETTINGS, **(p.get("settings") or {})}
    runs = await db.growth_fix_runs.find({"project_id": project_id}, {"_id": 0}).sort("started_at", -1).to_list(5)
    fixing = await db.growth_issues.find({"project_id": project_id, "status": "fixing"}, {"_id": 0, "issue_id": 1, "url": 1, "kind": 1, "fix_applied": 1, "fix_applied_at": 1}).sort("fix_applied_at", -1).to_list(200)
    reappeared = await db.growth_issues.count_documents({"project_id": project_id, "status": "open", "fix_active": True})
    last_audit = await db.growth_audits.find_one({"project_id": project_id, "status": {"$in": ["completed", "stopped"]}}, {"_id": 0, "audit_id": 1}, sort=[("finished_at", -1)])
    return {"enabled": bool(st.get("auto_fix_enabled", True)), "runs": runs, "last_run": runs[0] if runs else None, "fixing": fixing,
            "open": await db.growth_issues.count_documents({"project_id": project_id, "status": "open", "audit_id": last_audit["audit_id"]}) if last_audit else 0, "reappeared": reappeared,
            "redirects": await db.growth_redirects.find({"project_id": project_id, "status": "approved"}, {"_id": 0}).to_list(100),
            "running": any(r["status"] == "running" for r in runs)}


@router.post("/projects/{project_id}/autofix/run")
async def autofix_run(project_id: str, user=Depends(editor)) -> dict:
    from growth import autofix
    p = await get_project(project_id)
    audit = await db.growth_audits.find_one({"project_id": project_id, "status": {"$in": ["completed", "stopped"]}}, {"_id": 0}, sort=[("finished_at", -1)])
    if not audit:
        raise HTTPException(409, "Aucun audit terminé : lancez d'abord un audit.")
    return await autofix.run(p, audit, trigger="manual")


class AutofixSettingsIn(BaseModel):
    enabled: bool


@router.put("/projects/{project_id}/autofix")
async def autofix_toggle(project_id: str, body: AutofixSettingsIn, user=Depends(admin)) -> dict:
    p = await get_project(project_id)
    merged = {**DEFAULT_SETTINGS, **(p.get("settings") or {}), "auto_fix_enabled": body.enabled, "seo_override_mode": "auto" if body.enabled else "review"}
    await db.growth_projects.update_one({"project_id": project_id}, {"$set": {"settings": merged, "updated_at": now_iso()}})
    return {"enabled": body.enabled}


@router.get("/projects/{project_id}/seo-overrides")
async def list_seo_overrides(project_id: str, user=Depends(reader)) -> dict:
    await get_project(project_id)
    rows = await db.growth_seo_overrides.find({"project_id": project_id, "kind": {"$ne": "canonical"}}, {"_id": 0}).sort("created_at", -1).to_list(300)
    return {"overrides": rows, "pending": sum(1 for r in rows if r["status"] == "proposed")}


class OverrideIn(BaseModel):
    status: Literal["proposed", "approved", "rejected"]
    title: str = ""
    description: str = ""


@router.put("/seo-overrides/{override_id}")
async def set_seo_override(override_id: str, body: OverrideIn, user=Depends(editor)) -> dict:
    o = await db.growth_seo_overrides.find_one({"override_id": override_id}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Surcharge introuvable")
    sets = {"status": body.status, "decided_at": now_iso(), "decided_by": user["user_id"]}
    if body.title.strip():
        sets["title"] = body.title.strip()[:60]
    if body.description.strip():
        sets["description"] = body.description.strip()[:160]
    await db.growth_seo_overrides.update_one({"override_id": override_id}, {"$set": sets})
    if body.status == "approved":
        await db.growth_issues.update_many({"issue_id": {"$in": o.get("issue_ids") or []}}, {"$set": {"status": "fixed", "fixed_at": now_iso(), "fixed_by": "surcharge SEO approuvée"}})
    return {**o, **sets}


@router.post("/projects/{project_id}/seo-overrides/approve-all")
async def approve_all_overrides(project_id: str, user=Depends(editor)) -> dict:
    ids = [o["issue_id"] async for o in db.growth_seo_overrides.aggregate([{"$match": {"project_id": project_id, "status": "proposed"}}, {"$unwind": "$issue_ids"}, {"$project": {"issue_id": "$issue_ids"}}])]
    r = await db.growth_seo_overrides.update_many({"project_id": project_id, "status": "proposed"}, {"$set": {"status": "approved", "decided_at": now_iso(), "decided_by": user["user_id"]}})
    if ids:
        await db.growth_issues.update_many({"issue_id": {"$in": ids}}, {"$set": {"status": "fixed", "fixed_at": now_iso(), "fixed_by": "surcharge SEO approuvée"}})
    return {"approved": r.modified_count}


@router.get("/projects/{project_id}/autopilot")
async def autopilot_status(project_id: str, user=Depends(reader)) -> dict:
    from growth import autopilot as ap
    p = await get_project(project_id)
    runs = await db.growth_autopilot_runs.find({"project_id": project_id}, {"_id": 0}).sort("started_at", -1).to_list(10)
    st = {**DEFAULT_SETTINGS, **(p.get("settings") or {})}
    return {"settings": {k: st.get(k) for k in ("autopilot_enabled", "articles_per_week", "autopilot_batch", "seo_override_mode", "publish_mode", "budgets", "auto_fix_enabled")},
            "budget": await ap.budget_state(p), "quota_left_this_week": await ap._weekly_quota_left(p), "runs": runs, "running": any(r["status"] == "running" for r in runs),
            "pending_review": await db.growth_contents.count_documents({"project_id": project_id, "status": "review"}),
            "pending_overrides": await db.growth_seo_overrides.count_documents({"project_id": project_id, "status": "proposed"}),
            "in_progress": await db.growth_contents.count_documents({"project_id": project_id, "created_by": "autopilot", "status": {"$in": ["idea", "brief", "draft"]}}),
            "failed": await db.growth_contents.count_documents({"project_id": project_id, "created_by": "autopilot", "status": "failed"})}


@router.post("/projects/{project_id}/autopilot/run")
async def autopilot_run(project_id: str, resume_only: bool = Body(False, embed=True), user=Depends(editor)) -> dict:
    from growth import autopilot as ap
    await get_project(project_id)
    if await db.growth_autopilot_runs.find_one({"project_id": project_id, "status": "running"}):
        raise HTTPException(409, "Un cycle auto-pilote est déjà en cours")
    asyncio.create_task(ap.run(project_id, "manual", resume_only=resume_only))
    return {"ok": True, "started": True}


@router.post("/contents/{content_id}/research")
async def research_content(content_id: str, user=Depends(editor)) -> dict:
    from growth.research import find_sources
    c, p = await _load(content_id)
    try:
        research = await find_sources(p, c)
    except Exception as e:
        raise HTTPException(502, f"Recherche de sources impossible : {type(e).__name__}: {e}")
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": {"research": research, "updated_at": now_iso()}})
    return research


@router.post("/contents/{content_id}/auto")
async def auto_content(content_id: str, user=Depends(editor)) -> dict:
    """Enchaîne recherche → brief → rédaction → contrôles en tâche de fond ; le contenu passe « à relire »."""
    from growth import autopilot as ap
    c, p = await _load(content_id)
    if c["status"] in ("published", "archived"):
        raise HTTPException(400, "Contenu déjà publié ou archivé")
    await db.growth_contents.update_one({"content_id": content_id}, {"$set": {"status": "idea", "autopilot_log": []}})
    asyncio.create_task(ap.run_pipeline(p, {**c, "status": "idea"}))
    return {"ok": True, "started": True}


# ---------- publicités & newsletters ----------
@router.get("/projects/{project_id}/ads")
async def list_ads(project_id: str, user=Depends(reader)) -> dict:
    from growth import ads_connectors as cx
    await get_project(project_id)
    return {"ads": await db.growth_ads.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(200), "connectors": await cx.status(project_id)}


@router.post("/contents/{content_id}/ads")
async def make_ads(content_id: str, user=Depends(editor)) -> dict:
    from growth import marketing as mk
    c, p = await _load(content_id)
    if not c.get("published_url"):
        raise HTTPException(400, "Publiez l'article avant de générer ses annonces")
    try:
        ad = await mk.generate_ads(p, c)
    except Exception as e:
        raise HTTPException(502, f"Génération des annonces impossible : {e}")
    ad["created_by"] = user["user_id"]
    await db.growth_ads.insert_one(dict(ad))
    return ad


class AdIn(BaseModel):
    status: Literal["proposed", "approved", "rejected"] | None = None
    platforms: dict | None = None


@router.put("/ads/{ad_id}")
async def edit_ad(ad_id: str, body: AdIn, user=Depends(editor)) -> dict:
    from growth import marketing as mk
    ad = await db.growth_ads.find_one({"ad_id": ad_id}, {"_id": 0})
    if not ad:
        raise HTTPException(404, "Annonce introuvable")
    sets = {"updated_at": now_iso()}
    if body.platforms is not None:
        sets["platforms"] = mk.normalize_ads(body.platforms); sets["missing"] = mk.ads_complete(sets["platforms"])
    if body.status:
        sets["status"] = body.status; sets["decided_by"] = user["user_id"]
    await db.growth_ads.update_one({"ad_id": ad_id}, {"$set": sets})
    return {**ad, **sets}


@router.get("/ads/{ad_id}/export.csv")
async def export_ad(ad_id: str, platform: Literal["google", "meta"] = Query("google"), user=Depends(reader)):
    from growth import marketing as mk
    ad = await db.growth_ads.find_one({"ad_id": ad_id}, {"_id": 0})
    if not ad:
        raise HTTPException(404, "Annonce introuvable")
    p = await get_project(ad["project_id"])
    text = (mk.google_csv if platform == "google" else mk.meta_csv)(ad, f"ConstruPilot Growth {p['key'].upper()}")
    return Response(content=text, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{platform}-{ad_id}.csv"'})


@router.post("/ads/{ad_id}/publish")
async def publish_ad(ad_id: str, platform: Literal["google", "meta"] = Body(..., embed=True), daily_budget_eur: float = Body(10.0, embed=True), validate_only: bool = Body(False, embed=True), user=Depends(admin)) -> dict:
    """Crée la campagne en PAUSED sur la plateforme (budget quotidien en €) ; l'activation se fait ensuite dans l'interface Google/Meta."""
    from growth import ads_connectors as cx
    ad = await db.growth_ads.find_one({"ad_id": ad_id}, {"_id": 0})
    if not ad:
        raise HTTPException(404, "Annonce introuvable")
    if ad["status"] not in ("approved", "published"):
        raise HTTPException(400, "Approuvez l'annonce avant publication")
    if any(pub.get("platform") == platform and not pub.get("validate_only") for pub in ad.get("publications") or []):
        raise HTTPException(409, f"Déjà publiée sur {platform} (voir le lien de gestion)")
    p = await get_project(ad["project_id"])
    st = (await cx.status(p["project_id"]))[platform]
    if not st["configured"]:
        raise HTTPException(409, f"Connecteur {platform} non configuré — manque : {', '.join(st['missing'])}. En attendant, utilisez l'export CSV.")
    if not 1 <= daily_budget_eur <= 500:
        raise HTTPException(422, "Budget quotidien entre 1 et 500 €")
    try:
        res = await (cx.publish_google(p, ad, daily_budget_eur, validate_only) if platform == "google" else cx.publish_meta(p, ad, daily_budget_eur))
    except cx.ConnectorError as e:
        raise HTTPException(502, str(e))
    res.update({"daily_budget_eur": daily_budget_eur, "published_by": user["user_id"]})
    if not validate_only:
        await db.growth_ads.update_one({"ad_id": ad_id}, {"$set": {"status": "published", "updated_at": now_iso()}, "$push": {"publications": res}})
    return res


@router.get("/projects/{project_id}/ads/connectors")
async def ads_connectors_status(project_id: str, user=Depends(reader)) -> dict:
    from growth import ads_connectors as cx
    await get_project(project_id)
    return await cx.status(project_id)


@router.post("/projects/{project_id}/ads/connectors/meta/test")
async def meta_test(project_id: str, user=Depends(admin)) -> dict:
    from growth import ads_connectors as cx
    try:
        return await cx.meta_health()
    except cx.ConnectorError as e:
        raise HTTPException(502, str(e))


@router.get("/projects/{project_id}/newsletters")
async def list_newsletters(project_id: str, user=Depends(reader)) -> dict:
    p = await get_project(project_id)
    subs = await db.newsletter_subscribers.count_documents({"unsubscribed_at": None, "lang": p["key"]})
    return {"newsletters": await db.growth_newsletters.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(100), "subscribers": subs}


@router.post("/projects/{project_id}/newsletters/generate")
async def make_newsletter(project_id: str, content_ids: list[str] = Body([], embed=True), user=Depends(editor)) -> dict:
    from growth import marketing as mk
    p = await get_project(project_id)
    q = {"project_id": project_id, "status": "published"}
    if content_ids:
        q["content_id"] = {"$in": content_ids}
    contents = await db.growth_contents.find(q, {"_id": 0}).sort("published_at", -1).to_list(5)
    if not contents:
        raise HTTPException(400, "Aucun article publié à présenter")
    try:
        nl = await mk.generate_newsletter(p, contents)
    except Exception as e:
        raise HTTPException(502, f"Génération de la newsletter impossible : {e}")
    nl["created_by"] = user["user_id"]
    await db.growth_newsletters.insert_one(dict(nl))
    return nl


class NewsletterIn(BaseModel):
    status: Literal["proposed", "approved", "rejected"] | None = None
    subject: str | None = None
    preheader: str | None = None
    intro: str | None = None
    outro: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    items: list[dict] | None = None


@router.put("/newsletters/{newsletter_id}")
async def edit_newsletter(newsletter_id: str, body: NewsletterIn, user=Depends(editor)) -> dict:
    nl = await db.growth_newsletters.find_one({"newsletter_id": newsletter_id}, {"_id": 0})
    if not nl:
        raise HTTPException(404, "Newsletter introuvable")
    if nl["status"] == "sent":
        raise HTTPException(400, "Newsletter déjà envoyée")
    sets = {k: v for k, v in body.model_dump().items() if v is not None}
    if "subject" in sets:
        sets["subject"] = sets["subject"][:60]
    sets["updated_at"] = now_iso()
    await db.growth_newsletters.update_one({"newsletter_id": newsletter_id}, {"$set": sets})
    return {**nl, **sets}


@router.get("/newsletters/{newsletter_id}/preview", response_class=HTMLResponse)
async def preview_newsletter(newsletter_id: str, user=Depends(reader)):
    from growth import marketing as mk
    nl = await db.growth_newsletters.find_one({"newsletter_id": newsletter_id}, {"_id": 0})
    if not nl:
        raise HTTPException(404, "Newsletter introuvable")
    return mk.newsletter_html(nl, "#")


@router.post("/newsletters/{newsletter_id}/send")
async def send_newsletter(newsletter_id: str, test: bool = Body(False, embed=True), user=Depends(editor)) -> dict:
    from growth import marketing as mk
    nl = await db.growth_newsletters.find_one({"newsletter_id": newsletter_id}, {"_id": 0})
    if not nl:
        raise HTTPException(404, "Newsletter introuvable")
    if test:
        me = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "email": 1})
        return await mk.send_newsletter(nl, user["user_id"], test_to=me["email"])
    if user["growth_role"] != "admin":
        raise HTTPException(403, "L'envoi aux abonnés requiert le rôle admin")
    if nl["status"] != "approved":
        raise HTTPException(400, "Approuvez la newsletter avant l'envoi")
    lock = await db.growth_newsletters.update_one({"newsletter_id": newsletter_id, "status": "approved"}, {"$set": {"status": "sending"}})
    if not lock.modified_count:
        raise HTTPException(409, "Envoi déjà en cours")
    try:
        res = await mk.send_newsletter(nl, user["user_id"])
    except Exception as e:  # noqa: BLE001
        await db.growth_newsletters.update_one({"newsletter_id": newsletter_id}, {"$set": {"status": "approved", "send_error": f"{type(e).__name__}: {e}"[:300]}})
        raise HTTPException(502, f"Envoi interrompu ({type(e).__name__}) — la newsletter reste approuvée, relancez l'envoi")
    await db.growth_newsletters.update_one({"newsletter_id": newsletter_id}, {"$set": {"status": "sent", "sent_at": now_iso(), "result": res}})
    return res


@router.post("/assistant")
async def assistant(project_id: str = Body(..., embed=True), question: str = Body(..., embed=True, min_length=3, max_length=1000), user=Depends(reader)) -> dict:
    p = await get_project(project_id)
    ov = await overview(user)
    proj = next((x for x in ov["projects"] if x["project"]["project_id"] == project_id), {})
    issues = await db.growth_issues.find({"project_id": project_id, "status": "open"}, {"_id": 0, "kind": 1, "severity": 1, "url": 1, "evidence": 1}).limit(40).to_list(40)
    campaign = (proj.get("last_campaign") or {}).get("campaign")
    tests = []
    if campaign:
        tests = await db.growth_tests.find({"campaign_id": campaign["campaign_id"], "status": "completed"}, {"_id": 0, "question_text": 1, "provider": 1, "self_mentioned": 1, "mentions.name": 1, "mentions.mention": 1, "citations.url": 1}).limit(120).to_list(120)
    actions = await db.growth_actions.find({"project_id": project_id, "status": {"$ne": "done"}}, {"_id": 0, "title": 1, "impact": 1, "effort": 1, "evidence": 1}).limit(30).to_list(30)
    last_fix = await db.growth_fix_runs.find_one({"project_id": project_id}, {"_id": 0, "finished_at": 1, "counts": 1, "fixed": 1, "manual": 1}, sort=[("started_at", -1)])
    fixing_n = await db.growth_issues.count_documents({"project_id": project_id, "status": "fixing"})
    import json
    data = json.dumps({"corrections_automatiques": last_fix and {"derniere_execution": last_fix.get("finished_at"), "compteurs": last_fix.get("counts"), "corrections_en_attente_de_reaudit": fixing_n,
                                                       "corrigees": (last_fix.get("fixed") or [])[:30], "manuelles": (last_fix.get("manual") or [])[:30]},
                       "projet": {k: p.get(k) for k in ("name", "market", "language")}, "dernier_audit": proj.get("last_audit") and {k: proj["last_audit"].get(k) for k in ("pages_crawled", "issues_count", "summary", "finished_at")},
                       "metriques_campagne": {k: proj.get("last_campaign", {}).get(k) for k in ("mention_rate", "citation_rate", "share_of_mentions", "coverage")} if proj.get("last_campaign") else None,
                       "tests": tests, "problemes_ouverts": issues, "actions_ouvertes": actions, "search_console": proj.get("gsc") and proj["gsc"].get("totals")}, ensure_ascii=False, default=str)[:60000]
    system = ("Tu es l'assistant du module ConstruPilot Growth (SEO et visibilité IA). Tu réponds en français, de façon concise et structurée. "
              "Tu distingues explicitement OBSERVATIONS (issues des données fournies, avec les chiffres et dénominateurs) et HYPOTHÈSES. Tu ne fabriques aucune donnée absente : si une information manque, dis « données indisponibles ». "
              "Tu ne présentes jamais une variation comme la preuve d'un effet d'une action. Termine par une section « Action proposée » applicable (tâche, preuve, indicateur). "
              "Un AUTO-PILOTE existe : chaque nuit il clôture les problèmes disparus au ré-audit, CORRIGE AUTOMATIQUEMENT les titres/descriptions, les canonicals et les redirections 404 "
              "(appliqués à chaud, statut « correction appliquée » jusqu'à confirmation par le ré-audit), et rédige des articles jusqu'à la relecture. "
              "Le champ `corrections_automatiques` liste ce qui a été corrigé et ce qui reste manuel avec sa raison. Ne redemande jamais une correction déjà appliquée ; "
              "pour les problèmes manuels (H1, rendu, performance, hébergement), explique précisément ce qu'il faut changer dans le code ou l'hébergement. "
              "Si un problème réapparaît malgré une correction appliquée, dis que la version déployée du site n'inclut probablement pas encore la correction. "
              f"Rôle de l'utilisateur : {user['growth_role']} — tu ne publies pas d'article toi-même.")
    try:
        answer = await ct._llm(system, f"Données du projet (JSON) :\n{data}\n\nQuestion : {question}", project_id, "assistant")
    except Exception as e:
        raise HTTPException(502, f"Assistant indisponible : {type(e).__name__}")
    await db.growth_assistant_log.insert_one({"project_id": project_id, "user_id": user["user_id"], "question": question, "answer": answer, "at": now_iso()})
    return {"answer": answer, "grounded_on": {"tests": len(tests), "issues": len(issues), "actions": len(actions), "has_audit": bool(proj.get("last_audit")), "has_campaign": bool(campaign)}}
