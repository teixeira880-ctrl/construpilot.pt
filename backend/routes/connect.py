"""ConstruPilot Discovery Engine (/connect) + Commercial Hub — exclusivo do construpilot.pt.

Público (sem conta, com limite de pedidos):
  GET  /api/connect/catalog
  POST /api/connect/sessions                       → cria sessão anónima (devolve token uma única vez)
  PUT  /api/connect/sessions/{sid}/answers         → valida e guarda respostas, devolve recomendação
  GET  /api/connect/sessions/{sid}                 → resultado (requer X-Connect-Token)
  POST /api/connect/sessions/{sid}/demo            → regista progresso numa demonstração
  POST /api/connect/sessions/{sid}/events          → eventos de analytics (só com consentimento)
  POST /api/connect/sessions/{sid}/contact         → cria/atualiza a oportunidade no CRM
  POST /api/connect/demo/{demo_id}/compute         → cálculo pelos motores reais (projeto de exemplo)
Admin (role=admin):
  /api/connect/admin/...                           → leads, detalhe, funil, notas, tarefas, dashboard,
                                                     export CSV, definições, e-mails individuais, RGPD

Isolamento: feature flag CONNECT_ENABLED (por defeito ativo apenas quando o mercado é "pt").
Coleções novas e exclusivas: connect_sessions, connect_leads, connect_events, connect_settings,
connect_audit, connect_email_log. Nenhuma coleção existente é alterada (apenas inserções fail-soft
em `customer_activity` e `notifications`, como as rotas existentes já fazem).
"""

import asyncio
import csv
import hashlib
import io
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field, field_validator

from core.db import db
from core.rate_limit import limiter
from core.security import admin_user
from engines.connect import business_time, catalog as C, demo_compute, emails as E, recommend as R, scoring as S

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/connect", tags=["connect"])

PROFILES = ("client", "investor", "partner")
LANGS = ("pt", "en", "fr")
NEXT_STEPS = ("meeting", "individual_demo", "pilot", "report", "none")
CHANNELS = ("email", "phone", "whatsapp", "video")
STAGES = {
    "client": ["new", "qualification_pending", "qualified", "demo_requested", "demo_done", "pilot_proposed",
               "pilot_running", "proposal_sent", "negotiation", "won", "lost", "nurture"],
    "investor": ["new", "identity_check", "qualification", "meeting_requested", "first_meeting", "interest_confirmed",
                 "docs_authorized", "due_diligence", "negotiation", "invested", "no_interest"],
    "partner": ["new", "qualification", "meeting", "evaluation", "pilot_negotiation", "agreement", "active", "no_follow_up"],
}
CLOSED_STAGES = {"won", "lost", "nurture", "invested", "no_interest", "agreement", "active", "no_follow_up"}
EVENT_NAMES = {
    "connect_page_view", "profile_selected", "qualification_started", "qualification_step_completed",
    "qualification_abandoned", "qualification_completed", "recommendation_viewed", "demo_started",
    "demo_step_completed", "demo_completed", "meeting_requested", "pilot_requested",
}
SLUG = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,59}$")
PHONE = re.compile(r"^[0-9+()\s.-]{6,25}$")

DEFAULT_SETTINGS = {
    "owners": {
        "client": {"name": "Diana Araujo", "email": "dianaaraujo@construpilot.pt"},
        "investor": {"name": "Ângelo Cunha", "email": ""},
        "partner": {"name": "Ângelo Cunha", "email": ""},
    },
    "sla_hours": {"high": 2, "medium": 9, "low": 18, "investor": 9, "partner": 18},
    "retention_days": 365,
    "notify_admins": True,
    "scoring": {},
}


# ------------------------------------------------------------------ util

def connect_enabled() -> bool:
    raw = (os.environ.get("CONNECT_ENABLED") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    try:
        from engines.commercial_plans import market
        return market() == "pt"
    except Exception:
        return False


async def require_enabled() -> None:
    if not connect_enabled():
        raise HTTPException(404, "Not Found")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


def _hash(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _frontend_url() -> str:
    return (os.environ.get("FRONTEND_URL") or "https://construpilot.pt").rstrip("/")


_indexes_ready = False
_BACKGROUND: set = set()  # mantém referência às tarefas pós-submissão até terminarem


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await db.connect_sessions.create_index("session_id", unique=True)
        await db.connect_leads.create_index("lead_id", unique=True)
        await db.connect_leads.create_index([("email_hash", 1), ("profile", 1)])
        await db.connect_leads.create_index("created_at")
        await db.connect_events.create_index("session_id")
        await db.connect_email_log.create_index("dedupe_key", unique=True)
        _indexes_ready = True
    except Exception as exc:  # pragma: no cover - fail-soft, as rotas continuam a funcionar
        logger.warning("connect indexes: %s", exc)


async def get_settings() -> dict:
    doc = await db.connect_settings.find_one({"_id": "settings"}) or {}
    out = {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k != "_id"}}
    out["owners"] = {**DEFAULT_SETTINGS["owners"], **(doc.get("owners") or {})}
    out["sla_hours"] = {**DEFAULT_SETTINGS["sla_hours"], **(doc.get("sla_hours") or {})}
    return out


async def _session_or_403(sid: str, token: str | None) -> dict:
    if not token or len(token) > 200 or not re.fullmatch(r"cs_[A-Za-z0-9_-]{8,40}", sid or ""):
        raise HTTPException(403, "Acesso negado")
    s = await db.connect_sessions.find_one({"session_id": sid}, {"_id": 0})
    if not s or not secrets.compare_digest(s.get("token_hash", ""), _hash(token)):
        raise HTTPException(403, "Acesso negado")  # mesma resposta para inexistente e token errado
    return s


# ------------------------------------------------------------------ validação de respostas

def _one(value, allowed: set[str], name: str, required: bool = False):
    if value in (None, ""):
        if required:
            raise HTTPException(422, f"{name} em falta")
        return None
    if not isinstance(value, str) or value not in allowed:
        raise HTTPException(422, f"{name} inválido")
    return value


def _many(value, allowed: set[str], name: str, max_n: int = 8) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or len(value) > max_n or any(not isinstance(v, str) or v not in allowed for v in value):
        raise HTTPException(422, f"{name} inválido")
    return list(dict.fromkeys(value))


def _text(value, name: str, max_len: int) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value) > max_len:
        raise HTTPException(422, f"{name} inválido")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value).strip()


def _ids(items: list[dict]) -> set[str]:
    return {i["id"] for i in items}


def clean_answers(profile: str, raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise HTTPException(422, "respostas inválidas")
    cat = C.load()
    if profile == "client":
        acts = C.activities_by_id()
        out: dict = {"activity": _one(raw.get("activity"), set(acts), "activity")}
        vol = raw.get("volume") or {}
        if not isinstance(vol, dict) or len(vol) > 3:
            raise HTTPException(422, "volume inválido")
        out["volume"] = {k: _one(v, _ids(cat["ranges"][k]), f"volume.{k}")
                         for k, v in vol.items() if k in ("quotes_per_month", "projects_parallel", "team_size")}
        if set(vol) - set(out["volume"]):
            raise HTTPException(422, "volume inválido")
        out["pains"] = _many(raw.get("pains"), set(C.pains_by_id()), "pains", 3)
        out["other_text"] = _text(raw.get("other_text"), "other_text", 500)
        deep_allowed = C.all_deep_question_ids()
        track_q = {q["id"]: _ids(q["options"]) for q in cat["track_questions"].values()}
        deep = raw.get("deep") or {}
        if not isinstance(deep, dict) or len(deep) > 30:
            raise HTTPException(422, "deep inválido")
        clean_deep = {}
        for qid, v in deep.items():
            allowed = deep_allowed.get(qid) or track_q.get(qid)
            if allowed is None:
                raise HTTPException(422, f"pergunta desconhecida {qid}")
            clean_deep[qid] = _many(v, allowed, qid, 8) if isinstance(v, list) else _one(v, allowed, qid)
        out["deep"] = clean_deep
        extra = raw.get("extra") or {}
        if not isinstance(extra, dict):
            raise HTTPException(422, "extra inválido")
        out["extra"] = {k: _one(extra.get(k), _ids(cat["ranges"][k]), k) for k in ("team_size", "job_value", "market") if extra.get(k)}
        out["urgency"] = _one(raw.get("urgency"), {"immediate", "d30", "m3", "exploring"}, "urgency")
        out["decision"] = _one(raw.get("decision"), {"decide", "evaluate", "other", "personal"}, "decision")
        out["mode"] = _one(raw.get("mode"), {"quick", "deep", "stand"}, "mode") or "quick"
        return out
    if profile == "investor":
        inv = cat["investor"]
        return {
            "investor_type": _one(raw.get("investor_type"), _ids(inv["types"]), "investor_type"),
            "sectors": _many(raw.get("sectors"), _ids(inv["sectors"]), "sectors"),
            "stages": _many(raw.get("stages"), _ids(inv["stages"]), "stages"),
            "geos": _many(raw.get("geos"), _ids(inv["geos"]), "geos"),
            "ticket": _one(raw.get("ticket"), _ids(inv["tickets"]), "ticket"),
            "collab": _one(raw.get("collab"), _ids(inv["collab"]), "collab"),
            "availability": _one(raw.get("availability"), _ids(inv["availability"]), "availability"),
            "organization": _text(raw.get("organization"), "organization", 120),
            "website": _url(raw.get("website")),
        }
    if profile == "partner":
        par = cat["partner"]
        return {
            "partner_type": _one(raw.get("partner_type"), _ids(par["types"]), "partner_type"),
            "kinds": _many(raw.get("kinds"), _ids(par["kinds"]), "kinds"),
            "geos": _many(raw.get("geos"), _ids(cat["investor"]["geos"]), "geos"),
            "clients_desc": _text(raw.get("clients_desc"), "clients_desc", 300),
            "scale": _one(raw.get("scale"), _ids(par["scale"]), "scale"),
            "timeline": _one(raw.get("timeline"), _ids(par["timeline"]), "timeline"),
            "organization": _text(raw.get("organization"), "organization", 120),
            "website": _url(raw.get("website")),
        }
    raise HTTPException(422, "perfil inválido")


def _url(v) -> str:
    v = _text(v, "website", 200)
    if v and not re.fullmatch(r"(https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/[^\s<>\"']*)?", v):
        raise HTTPException(422, "website inválido")
    return v


def is_answers_complete(profile: str, a: dict) -> bool:
    if profile == "client":
        return bool(a.get("activity") and a.get("pains") and a.get("urgency"))
    if profile == "investor":
        return bool(a.get("investor_type"))
    return bool(a.get("partner_type"))


# ------------------------------------------------------------------ modelos

class SessionIn(BaseModel):
    profile: Literal["client", "investor", "partner"]
    lang: Literal["pt", "en", "fr"] = "pt"
    source: str = ""
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    stand: bool = False

    @field_validator("source", "utm_source", "utm_medium", "utm_campaign")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = (v or "").strip().lower()[:60]
        return v if not v or SLUG.match(v) else ""


class AnswersIn(BaseModel):
    answers: dict
    step: int = Field(default=0, ge=0, le=50)
    lang: Literal["pt", "en", "fr"] | None = None


class DemoProgressIn(BaseModel):
    demo_id: str = Field(max_length=40)
    event: Literal["started", "step", "completed"]
    step: int = Field(default=0, ge=0, le=30)


class EventIn(BaseModel):
    name: str = Field(max_length=60)
    analytics_consent: bool = False
    step: int | None = Field(default=None, ge=0, le=50)
    ref: str = Field(default="", max_length=40)


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    company: str = Field(default="", max_length=120)
    email: EmailStr
    phone: str = Field(default="", max_length=25)
    country: str = Field(default="", max_length=60)
    channel: Literal["email", "phone", "whatsapp", "video"] = "email"
    next_step: Literal["meeting", "individual_demo", "pilot", "report", "none"] = "none"
    message: str = Field(default="", max_length=1000)
    privacy_ack: bool
    marketing_consent: bool = False
    email_copy: bool = False
    website_url: str = Field(default="", max_length=200)  # honeypot: tem de vir vazio

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        v = (v or "").strip()
        if v and not PHONE.match(v):
            raise ValueError("telefone inválido")
        return v

    @field_validator("name", "company", "country", "message")
    @classmethod
    def _strip(cls, v: str) -> str:
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", v or "").strip()


class DemoComputeIn(BaseModel):
    params: dict = Field(default_factory=dict)


# ------------------------------------------------------------------ rotas públicas

@router.get("/catalog", dependencies=[Depends(require_enabled)])
async def get_catalog() -> dict:
    cat = C.load()
    return {**cat, "capabilities": [C.public_capability(c) for c in cat["capabilities"]]}


@router.post("/sessions", dependencies=[Depends(require_enabled)])
@limiter.limit("30/hour")
async def create_session(request: Request, response: Response, body: SessionIn) -> dict:
    await _ensure_indexes()
    sid = "cs_" + secrets.token_urlsafe(16)
    token = secrets.token_urlsafe(32)
    doc = {
        "session_id": sid, "token_hash": _hash(token), "profile": body.profile, "lang": body.lang,
        "source": body.source or ("websummit2026" if body.stand else "direct"),
        "utm": {"source": body.utm_source, "medium": body.utm_medium, "campaign": body.utm_campaign},
        "stand": body.stand, "answers": {}, "recommendation": None, "max_step": 0,
        "completed_at": None, "demos": {}, "lead_id": None,
        "created_at": _iso(), "updated_at": _iso(),
    }
    await db.connect_sessions.insert_one(doc)
    return {"session_id": sid, "token": token}


@router.put("/sessions/{sid}/answers", dependencies=[Depends(require_enabled)])
@limiter.limit("240/hour")
async def save_answers(request: Request, response: Response, sid: str, body: AnswersIn,
                       x_connect_token: str | None = Header(default=None)) -> dict:
    s = await _session_or_403(sid, x_connect_token)
    answers = clean_answers(s["profile"], body.answers)
    complete = is_answers_complete(s["profile"], answers)
    rec = R.recommend(s["profile"], answers) if complete else None
    upd = {"answers": answers, "recommendation": rec, "updated_at": _iso(),
           "max_step": max(int(s.get("max_step") or 0), body.step)}
    if body.lang:
        upd["lang"] = body.lang
    if complete and not s.get("completed_at"):
        upd["completed_at"] = _iso()
    await db.connect_sessions.update_one({"session_id": sid}, {"$set": upd})
    if s.get("lead_id") and rec:
        await db.connect_leads.update_one({"lead_id": s["lead_id"]}, {"$set": {
            "answers": answers, "recommendation": rec, "pains": rec.get("pains", []), "updated_at": _iso()}})
    return {"ok": True, "complete": complete, "recommendation": rec}


@router.get("/sessions/{sid}", dependencies=[Depends(require_enabled)])
@limiter.limit("240/hour")
async def get_session(request: Request, response: Response, sid: str, x_connect_token: str | None = Header(default=None)) -> dict:
    s = await _session_or_403(sid, x_connect_token)
    return {k: s.get(k) for k in ("session_id", "profile", "lang", "answers", "recommendation", "demos", "completed_at")} | \
        {"has_contact": bool(s.get("lead_id"))}


@router.post("/sessions/{sid}/demo", dependencies=[Depends(require_enabled)])
@limiter.limit("600/hour")
async def demo_progress(request: Request, response: Response, sid: str, body: DemoProgressIn,
                        x_connect_token: str | None = Header(default=None)) -> dict:
    s = await _session_or_403(sid, x_connect_token)
    if body.demo_id not in {d["id"] for d in C.load()["demos"]}:
        raise HTTPException(422, "demo inválida")
    key = f"demos.{body.demo_id}"
    cur = (s.get("demos") or {}).get(body.demo_id) or {}
    upd = {f"{key}.max_step": max(int(cur.get("max_step") or 0), body.step), f"{key}.updated_at": _iso()}
    if body.event == "started" and not cur.get("started_at"):
        upd[f"{key}.started_at"] = _iso()
    if body.event == "completed":
        upd[f"{key}.completed_at"] = _iso()
    await db.connect_sessions.update_one({"session_id": sid}, {"$set": upd})
    if s.get("lead_id"):
        await db.connect_leads.update_one({"lead_id": s["lead_id"]}, {"$addToSet": {"demos_viewed": body.demo_id},
                                                                     "$set": {"last_interaction_at": _iso()}})
    return {"ok": True}


@router.post("/sessions/{sid}/events", dependencies=[Depends(require_enabled)])
@limiter.limit("600/hour")
async def track_event(request: Request, response: Response, sid: str, body: EventIn,
                      x_connect_token: str | None = Header(default=None)) -> dict:
    await _session_or_403(sid, x_connect_token)
    if body.name not in EVENT_NAMES:
        raise HTTPException(422, "evento desconhecido")
    if not body.analytics_consent:
        return {"ok": True, "stored": False}  # sem consentimento: nada é guardado
    await db.connect_events.insert_one({"session_id": sid, "name": body.name, "step": body.step,
                                        "ref": re.sub(r"[^a-z0-9_]", "", body.ref.lower())[:40], "at": _iso()})
    return {"ok": True, "stored": True}


@router.post("/demo/{demo_id}/compute", dependencies=[Depends(require_enabled)])
@limiter.limit("120/minute")
async def compute_demo(request: Request, response: Response, demo_id: str, body: DemoComputeIn) -> dict:
    try:
        return demo_compute.compute(demo_id, body.params)
    except demo_compute.DemoInputError as exc:
        raise HTTPException(422, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


# ------------------------------------------------------------------ contacto → oportunidade

def _initial_stage(profile: str, next_step: str, priority: str) -> str:
    if profile == "client":
        if next_step in ("individual_demo", "meeting"):
            return "demo_requested"
        return "qualified" if priority in ("high", "medium") else "qualification_pending"
    if profile == "investor":
        return "meeting_requested" if next_step == "meeting" else "identity_check"
    return "meeting" if next_step == "meeting" else "qualification"


def _tasks_for(profile: str, priority: str, next_step: str, settings: dict, owner: dict, rec: dict | None) -> list[dict]:
    now = _now()
    sla = settings["sla_hours"]
    tasks = []

    def task(title: str, hours: float, kind: str) -> dict:
        return {"task_id": "t_" + secrets.token_hex(5), "title": title, "kind": kind, "owner": owner.get("name", ""),
                "due_at": _iso(business_time.add_business_hours(now, hours)), "done": False, "created_at": _iso(now),
                "auto": True}

    if profile == "client":
        demo = (rec or {}).get("demo")
        if priority == "high":
            demo_title = next((d["title"]["pt"] for d in C.load()["demos"] if d["id"] == demo), demo)
            tasks.append(task(f"Contactar em até {sla['high']} h úteis — sugerir a demonstração «{demo_title}»", sla["high"], "first_contact"))
        elif priority == "medium":
            tasks.append(task("Propor reunião ou piloto (1 dia útil)", sla["medium"], "first_contact"))
        elif next_step != "none":
            tasks.append(task("Responder ao pedido do visitante", sla["low"], "first_contact"))
        if next_step == "pilot":
            tasks.append(task("Preparar proposta de piloto com métricas (calculadora do diagnóstico)", sla["medium"], "pilot"))
    elif profile == "investor":
        tasks.append(task("Analisar o investidor e responder pessoalmente", sla["investor"], "investor_review"))
    else:
        tasks.append(task("Avaliar potencial de parceria e propor reunião de descoberta", sla["partner"], "partner_review"))
    return tasks


async def _notify_admins(lead: dict, settings: dict) -> None:
    """Sino do admin (coleção notifications existente) + e-mail ao responsável. Fail-soft."""
    label = {"client": "cliente", "investor": "investidor", "partner": "parceiro"}[lead["profile"]]
    msg = f"Connect: novo {label} — {lead['contact']['name']} · prioridade {lead['priority']} ({lead['score']})"
    try:
        admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}).to_list(20)
        for a in admins:
            await db.notifications.insert_one({"notif_id": "n_" + secrets.token_hex(5), "user_id": a["user_id"],
                                               "type": "connect_lead", "lead_id": lead["lead_id"], "message": msg[:200],
                                               "created_at": _iso(), "read": False})
    except Exception as exc:
        logger.warning("connect notify bell: %s", exc)
    to = (settings["owners"].get(lead["profile"]) or {}).get("email")
    if not to:
        return
    try:
        from html import escape
        body = (f"<p><b>{escape(lead['contact']['name'])}</b> — {escape(lead['contact'].get('company') or '—')}</p>"
                f"<p>Prioridade <b>{lead['priority']}</b> ({lead['score']}/100): {escape(lead['score_detail']['explanation'])}</p>"
                f"<p>Próximo passo pedido: {escape(lead['next_step'])}</p>")
        _, html = E.render("follow_up", "pt", note="", cta_url=None)
        html = html.replace("<p></p>", body)
        await _send_logged(f"owner:{lead['lead_id']}:{lead['updated_at'][:16]}", to, msg[:120], html, lead["lead_id"], "owner_alert")
    except Exception as exc:
        logger.warning("connect owner mail: %s", exc)


async def _send_logged(dedupe_key: str, to: str, subject: str, html: str, lead_id: str, template: str) -> bool:
    """Envia no máximo uma vez por dedupe_key; regista sucesso/falha sem dados de conteúdo."""
    try:
        await db.connect_email_log.insert_one({"dedupe_key": dedupe_key, "lead_id": lead_id, "template": template,
                                               "status": "pending", "created_at": _iso()})
    except Exception:
        return False  # já enviado/pendente (chave única)
    try:
        from engines.emailer import send_email
        res = await send_email(to, subject, html)
        await db.connect_email_log.update_one({"dedupe_key": dedupe_key}, {"$set": {"status": "sent", "provider_id": (res or {}).get("id")}})
        return True
    except Exception as exc:
        await db.connect_email_log.update_one({"dedupe_key": dedupe_key}, {"$set": {"status": "failed", "error": str(exc)[:200]}})
        return False


def _result_url(sid: str) -> str:
    # O token NÃO vai no e-mail: o visitante reabre o resultado no mesmo navegador; senão, a demo pública.
    return f"{_frontend_url()}/connect/result/{sid}"


async def _visitor_email(lead: dict, session: dict, body: ContactIn) -> str | None:
    lang = session.get("lang") or "pt"
    rec = session.get("recommendation") or {}
    demo_url = f"{_frontend_url()}/connect/demo/{rec.get('demo') or 'demo_quote'}?lang={lang}"
    window = _now().strftime("%Y%m%d%H")
    if lead["profile"] == "investor":
        key, extra = "investor_received", {}
    elif lead["profile"] == "partner":
        key, extra = "partner_received", {}
    elif body.next_step == "report" or body.email_copy:
        pains = C.pains_by_id()
        caps = C.caps_by_id()
        challenge = " + ".join(pains[p]["summary"][lang] for p in rec.get("pains", []) if p in pains) or "—"
        capabilities = ", ".join(caps[c["id"]]["name"][lang] for c in rec.get("capabilities", []))
        key, extra = "diagnosis_summary", {"challenge": challenge, "capabilities": capabilities}
    elif body.next_step in ("meeting", "individual_demo", "pilot"):
        key, extra = "request_received", {"next_step": E.NEXT_STEP_LABEL[body.next_step][lang]}
    else:
        return None
    subject, html = E.render(key, lang, name=body.name, cta_url=demo_url, **extra)
    ok = await _send_logged(f"visitor:{lead['lead_id']}:{key}:{window}", str(body.email), subject, html, lead["lead_id"], key)
    return key if ok else None


@router.post("/sessions/{sid}/contact", dependencies=[Depends(require_enabled)])
@limiter.limit("10/hour")
async def submit_contact(request: Request, response: Response, sid: str, body: ContactIn,
                         x_connect_token: str | None = Header(default=None)) -> dict:
    s = await _session_or_403(sid, x_connect_token)
    if body.website_url.strip():  # bot: resposta neutra, nada é guardado
        return {"ok": True}
    if not body.privacy_ack:
        raise HTTPException(422, "É necessário tomar conhecimento da informação de privacidade")
    answers = s.get("answers") or {}
    if not is_answers_complete(s["profile"], answers):
        raise HTTPException(409, "Diagnóstico incompleto")
    await _ensure_indexes()
    settings = await get_settings()
    rec = s.get("recommendation") or R.recommend(s["profile"], answers)
    demos = s.get("demos") or {}
    demo_completed = any(d.get("completed_at") for d in demos.values())
    group = rec.get("group", "other") if s["profile"] == "client" else "other"
    sc = S.score(s["profile"], answers, group=group, next_step=body.next_step, demo_completed=demo_completed,
                 overrides=settings.get("scoring"))
    email = str(body.email).strip().lower()
    email_hash = _hash(email)
    now = _iso()
    consent = {"privacy_ack": True, "marketing": bool(body.marketing_consent), "at": now,
               "origin": f"/connect/{s['profile']}", "lang": s.get("lang"), "text_version": "connect-2026-11-10"}
    owner = settings["owners"].get(s["profile"]) or {}

    lead = None
    if s.get("lead_id"):
        lead = await db.connect_leads.find_one({"lead_id": s["lead_id"]}, {"_id": 0})
    if lead is None:
        since = _iso(_now() - timedelta(days=30))
        cands = await db.connect_leads.find({"email_hash": email_hash, "profile": s["profile"]}, {"_id": 0}) \
            .sort("created_at", -1).to_list(5)
        lead = next((c for c in cands if c.get("created_at", "") >= since and c.get("stage") not in CLOSED_STAGES), None)

    contact = {"name": body.name, "company": body.company, "email": email, "phone": body.phone,
               "country": body.country, "channel": body.channel}
    common = {
        "contact": contact, "lang": s.get("lang"), "answers": answers, "recommendation": rec,
        "pains": rec.get("pains", []) if s["profile"] == "client" else [],
        "solutions": [c["id"] for c in rec.get("capabilities", [])] if s["profile"] == "client" else [rec.get("use_case")] if rec.get("use_case") else [],
        "score": sc["score"], "priority": sc["priority"], "score_detail": sc, "next_step": body.next_step,
        "last_interaction_at": now, "updated_at": now,
    }
    activity = {"activity_id": "a_" + secrets.token_hex(5), "at": now, "type": "form_submitted", "author": "visitor",
                "text": (f"Pedido: {body.next_step}. " + (body.message[:500] if body.message else "")).strip()}
    if lead:
        await db.connect_leads.update_one({"lead_id": lead["lead_id"]}, {
            "$set": {**common, "marketing_consent": bool(body.marketing_consent) or bool(lead.get("marketing_consent"))},
            "$addToSet": {"session_ids": sid, "demos_viewed": {"$each": [k for k in demos]}},
            "$push": {"activities": activity, "consents": consent}})
        lead = await db.connect_leads.find_one({"lead_id": lead["lead_id"]}, {"_id": 0})
        created = False
    else:
        lead = {
            "lead_id": "cl_" + secrets.token_hex(8), "profile": s["profile"], "email_hash": email_hash,
            "source": s.get("source"), "utm": s.get("utm") or {}, "stand": bool(s.get("stand")),
            "session_ids": [sid], "demos_viewed": list(demos), **common,
            "stage": _initial_stage(s["profile"], body.next_step, sc["priority"]),
            "owner": owner.get("name", ""), "owner_email": owner.get("email", ""),
            "next_action": "", "next_contact_at": None, "interest": "", "loss_reason": "",
            "marketing_consent": bool(body.marketing_consent), "consents": [consent],
            "activities": [activity], "tasks": _tasks_for(s["profile"], sc["priority"], body.next_step, settings, owner, rec),
            "first_response_at": None, "created_at": now, "anonymized": False,
        }
        if lead["tasks"]:
            lead["next_action"] = lead["tasks"][0]["title"]
            lead["next_contact_at"] = lead["tasks"][0]["due_at"]
        await db.connect_leads.insert_one(dict(lead))
        lead.pop("_id", None)
        created = True
    await db.connect_sessions.update_one({"session_id": sid}, {"$set": {"lead_id": lead["lead_id"], "updated_at": now}})

    task = asyncio.create_task(_after_submit(lead, s, body, settings, created))
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)
    return {"ok": True, "created": created, "next_step": body.next_step}


async def _after_submit(lead: dict, session: dict, body: ContactIn, settings: dict, created: bool) -> None:
    try:
        sent = await _visitor_email(lead, session, body)
        if sent:
            await db.connect_leads.update_one({"lead_id": lead["lead_id"]}, {"$push": {"activities": {
                "activity_id": "a_" + secrets.token_hex(5), "at": _iso(), "type": "email_sent", "author": "system",
                "text": f"E-mail transacional enviado: {sent}"}}})
        if created and settings.get("notify_admins", True):
            await _notify_admins(lead, settings)
        if created:
            from engines.activity_crm.record import record_activity
            await record_activity(kind="contact", user_email=lead["contact"]["email"], user_name=lead["contact"]["name"],
                                  user_phone=lead["contact"].get("phone") or None,
                                  summary=f"Connect ({lead['profile']}): prioridade {lead['priority']} {lead['score']}/100"[:160],
                                  source_url="/api/connect", payload={"connect_lead_id": lead["lead_id"]}, no_email=True)
    except Exception as exc:  # pragma: no cover
        logger.warning("connect after_submit: %s", exc)


# ------------------------------------------------------------------ admin — Commercial Hub

class LeadPatch(BaseModel):
    stage: str | None = None
    owner: str | None = Field(default=None, max_length=80)
    owner_email: str | None = Field(default=None, max_length=120)
    next_action: str | None = Field(default=None, max_length=300)
    next_contact_at: str | None = Field(default=None, max_length=40)
    interest: str | None = Field(default=None, max_length=300)
    loss_reason: str | None = Field(default=None, max_length=300)
    priority_override: Literal["high", "medium", "low", ""] | None = None


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    type: Literal["note", "call", "email", "meeting", "demo"] = "note"


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: str | None = Field(default=None, max_length=40)
    owner: str = Field(default="", max_length=80)


class TaskPatch(BaseModel):
    done: bool | None = None
    title: str | None = Field(default=None, max_length=200)
    due_at: str | None = Field(default=None, max_length=40)


class SendEmailIn(BaseModel):
    template: Literal["meeting_confirmation", "follow_up", "pilot_invite", "partner_meeting_invite"]
    note: str = Field(default="", max_length=2000)
    when: str = Field(default="", max_length=80)


class SettingsIn(BaseModel):
    owners: dict | None = None
    sla_hours: dict | None = None
    retention_days: int | None = Field(default=None, ge=30, le=3650)
    notify_admins: bool | None = None
    scoring: dict | None = None


def _iso_or_none(v: str | None) -> str | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()
    except ValueError:
        raise HTTPException(422, "data inválida")


async def _audit(admin: dict, action: str, lead_id: str | None, detail: dict | None = None) -> None:
    await db.connect_audit.insert_one({"at": _iso(), "admin": admin.get("email") or admin.get("user_id"),
                                       "action": action, "lead_id": lead_id, "detail": detail or {}})


async def _lead_or_404(lead_id: str) -> dict:
    lead = await db.connect_leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Oportunidade não encontrada")
    return lead


def _lead_row(l: dict) -> dict:
    c = l.get("contact") or {}
    open_tasks = [t for t in l.get("tasks") or [] if not t.get("done")]
    return {
        "lead_id": l["lead_id"], "profile": l["profile"], "name": c.get("name"), "company": c.get("company"),
        "email": c.get("email"), "country": c.get("country"), "lang": l.get("lang"), "source": l.get("source"),
        "stage": l.get("stage"), "priority": l.get("priority_override") or l.get("priority"), "score": l.get("score"),
        "owner": l.get("owner"), "next_action": l.get("next_action"), "next_contact_at": l.get("next_contact_at"),
        "pains": l.get("pains", []), "next_step": l.get("next_step"), "created_at": l.get("created_at"),
        "last_interaction_at": l.get("last_interaction_at"), "open_tasks": len(open_tasks),
        "overdue": any((t.get("due_at") or "9") < _iso() for t in open_tasks), "anonymized": l.get("anonymized", False),
    }


@router.get("/admin/leads", dependencies=[Depends(require_enabled)])
async def admin_list(admin=Depends(admin_user), profile: str | None = None, stage: str | None = None,
                     priority: str | None = None, owner: str | None = None, source: str | None = None,
                     q: str | None = Query(default=None, max_length=80), overdue: bool = False,
                     skip: int = Query(default=0, ge=0, le=100000), limit: int = Query(default=50, ge=1, le=200)) -> dict:
    flt: dict = {}
    for k, v in (("profile", profile), ("stage", stage), ("owner", owner), ("source", source)):
        if v:
            flt[k] = v
    rows = await db.connect_leads.find(flt, {"_id": 0}).sort("created_at", -1).to_list(5000)
    out = [_lead_row(l) for l in rows]
    if priority:
        out = [r for r in out if r["priority"] == priority]
    if q:
        ql = q.lower()
        out = [r for r in out if any(ql in str(r.get(k) or "").lower() for k in ("name", "company", "email"))]
    if overdue:
        out = [r for r in out if r["overdue"]]
    return {"total": len(out), "items": out[skip:skip + limit], "stages": STAGES}


@router.get("/admin/leads/{lead_id}", dependencies=[Depends(require_enabled)])
async def admin_get(lead_id: str, admin=Depends(admin_user)) -> dict:
    lead = await _lead_or_404(lead_id)
    lead.pop("email_hash", None)
    await _audit(admin, "view", lead_id)
    return {**lead, "stages": STAGES[lead["profile"]]}


@router.patch("/admin/leads/{lead_id}", dependencies=[Depends(require_enabled)])
async def admin_patch(lead_id: str, body: LeadPatch, admin=Depends(admin_user)) -> dict:
    lead = await _lead_or_404(lead_id)
    upd: dict = {}
    data = body.model_dump(exclude_none=True)
    if "stage" in data:
        if data["stage"] not in STAGES[lead["profile"]]:
            raise HTTPException(422, "Etapa inválida para este perfil")
        upd["stage"] = data["stage"]
    for k in ("owner", "owner_email", "next_action", "interest", "loss_reason", "priority_override"):
        if k in data:
            upd[k] = data[k].strip() if isinstance(data[k], str) else data[k]
    if "next_contact_at" in data:
        upd["next_contact_at"] = _iso_or_none(data["next_contact_at"])
    if not upd:
        return lead
    now = _iso()
    upd["updated_at"] = now
    act = {"activity_id": "a_" + secrets.token_hex(5), "at": now, "type": "update", "author": admin.get("email", "admin"),
           "text": "; ".join(f"{k}: {lead.get(k) or '—'} → {v or '—'}" for k, v in upd.items() if k != "updated_at")[:500]}
    await db.connect_leads.update_one({"lead_id": lead_id}, {"$set": upd, "$push": {"activities": act}})
    await _audit(admin, "update", lead_id, {k: v for k, v in upd.items() if k != "updated_at"})
    return await _lead_or_404(lead_id)


@router.post("/admin/leads/{lead_id}/notes", dependencies=[Depends(require_enabled)])
async def admin_note(lead_id: str, body: NoteIn, admin=Depends(admin_user)) -> dict:
    lead = await _lead_or_404(lead_id)
    now = _iso()
    act = {"activity_id": "a_" + secrets.token_hex(5), "at": now, "type": body.type, "author": admin.get("email", "admin"),
           "text": body.text.strip()}
    upd = {"last_interaction_at": now, "updated_at": now}
    if body.type in ("call", "email", "meeting", "demo") and not lead.get("first_response_at"):
        upd["first_response_at"] = now
    await db.connect_leads.update_one({"lead_id": lead_id}, {"$push": {"activities": act}, "$set": upd})
    await _audit(admin, "note", lead_id, {"type": body.type})
    return act


@router.post("/admin/leads/{lead_id}/tasks", dependencies=[Depends(require_enabled)])
async def admin_task_add(lead_id: str, body: TaskIn, admin=Depends(admin_user)) -> dict:
    await _lead_or_404(lead_id)
    t = {"task_id": "t_" + secrets.token_hex(5), "title": body.title.strip(), "kind": "manual",
         "owner": body.owner.strip(), "due_at": _iso_or_none(body.due_at), "done": False, "created_at": _iso(), "auto": False}
    await db.connect_leads.update_one({"lead_id": lead_id}, {"$push": {"tasks": t}, "$set": {"updated_at": _iso()}})
    await _audit(admin, "task_add", lead_id, {"task_id": t["task_id"]})
    return t


@router.patch("/admin/leads/{lead_id}/tasks/{task_id}", dependencies=[Depends(require_enabled)])
async def admin_task_patch(lead_id: str, task_id: str, body: TaskPatch, admin=Depends(admin_user)) -> dict:
    lead = await _lead_or_404(lead_id)
    tasks = lead.get("tasks") or []
    t = next((x for x in tasks if x["task_id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada")
    if body.done is not None:
        t["done"] = body.done
        t["done_at"] = _iso() if body.done else None
    if body.title is not None:
        t["title"] = body.title.strip()
    if body.due_at is not None:
        t["due_at"] = _iso_or_none(body.due_at)
    await db.connect_leads.update_one({"lead_id": lead_id}, {"$set": {"tasks": tasks, "updated_at": _iso()}})
    await _audit(admin, "task_update", lead_id, {"task_id": task_id})
    return t


@router.post("/admin/leads/{lead_id}/email", dependencies=[Depends(require_enabled)])
async def admin_send_email(lead_id: str, body: SendEmailIn, admin=Depends(admin_user)) -> dict:
    """Envio individual de um modelo pelo admin. A confirmação de reunião exige a data/hora real."""
    lead = await _lead_or_404(lead_id)
    if lead.get("anonymized"):
        raise HTTPException(409, "Dados pessoais eliminados")
    if body.template == "meeting_confirmation" and not body.when.strip():
        raise HTTPException(422, "Indique a data e hora reais da reunião")
    lang = lead.get("lang") or "pt"
    cta = None
    if body.template == "follow_up":
        cta = f"{_frontend_url()}/connect/demo/{(lead.get('recommendation') or {}).get('demo') or 'demo_quote'}?lang={lang}"
    subject, html = E.render(body.template, lang, name=lead["contact"]["name"], cta_url=cta, note=body.note, when=body.when)
    key = f"admin:{lead_id}:{body.template}:{_hash(body.note + body.when)[:12]}"
    ok = await _send_logged(key, lead["contact"]["email"], subject, html, lead_id, body.template)
    now = _iso()
    act = {"activity_id": "a_" + secrets.token_hex(5), "at": now, "type": "email", "author": admin.get("email", "admin"),
           "text": f"E-mail {body.template}: {'enviado' if ok else 'não enviado (duplicado ou falha de envio)'}"}
    upd = {"last_interaction_at": now, "updated_at": now}
    if ok and not lead.get("first_response_at"):
        upd["first_response_at"] = now
    await db.connect_leads.update_one({"lead_id": lead_id}, {"$push": {"activities": act}, "$set": upd})
    await _audit(admin, "email", lead_id, {"template": body.template, "sent": ok})
    return {"ok": ok}


@router.get("/admin/leads/{lead_id}/personal-data", dependencies=[Depends(require_enabled)])
async def admin_export_one(lead_id: str, admin=Depends(admin_user)) -> dict:
    """Exportação dos dados de uma pessoa (direito de acesso / portabilidade)."""
    lead = await _lead_or_404(lead_id)
    lead.pop("email_hash", None)
    await _audit(admin, "export_personal_data", lead_id)
    return lead


@router.post("/admin/leads/{lead_id}/anonymize", dependencies=[Depends(require_enabled)])
async def admin_anonymize(lead_id: str, admin=Depends(admin_user), confirm: bool = Body(False, embed=True)) -> dict:
    """Apaga os dados pessoais (direito ao apagamento) mantendo o registo agregado sem identificação."""
    if not confirm:
        raise HTTPException(422, "Confirmação necessária")
    await _lead_or_404(lead_id)
    await _anonymize(lead_id, f"admin:{admin.get('email', 'admin')}")
    await _audit(admin, "anonymize", lead_id)
    return {"ok": True}


async def _anonymize(lead_id: str, by: str) -> None:
    now = _iso()
    await db.connect_leads.update_one({"lead_id": lead_id}, {"$set": {
        "contact": {"name": "[eliminado]", "company": "", "email": "", "phone": "", "country": "", "channel": ""},
        "email_hash": "", "answers.other_text": "", "answers.organization": "", "answers.website": "",
        "answers.clients_desc": "", "anonymized": True, "anonymized_at": now, "anonymized_by": by,
        "activities": [{"activity_id": "a_" + secrets.token_hex(5), "at": now, "type": "update", "author": by,
                        "text": "Dados pessoais eliminados"}],
    }})


@router.post("/admin/retention/run", dependencies=[Depends(require_enabled)])
async def admin_retention(admin=Depends(admin_user)) -> dict:
    """Anonimiza oportunidades fechadas sem interação há mais de `retention_days`."""
    settings = await get_settings()
    limit = _iso(_now() - timedelta(days=int(settings["retention_days"])))
    rows = await db.connect_leads.find({"anonymized": False}, {"_id": 0, "lead_id": 1, "stage": 1, "last_interaction_at": 1}).to_list(10000)
    done = 0
    for r in rows:
        if r.get("stage") in {"lost", "no_interest", "no_follow_up"} and (r.get("last_interaction_at") or "") < limit:
            await _anonymize(r["lead_id"], "retention")
            done += 1
    await _audit(admin, "retention_run", None, {"anonymized": done})
    return {"anonymized": done}


@router.get("/admin/dashboard", dependencies=[Depends(require_enabled)])
async def admin_dashboard(admin=Depends(admin_user), days: int = Query(default=90, ge=1, le=730)) -> dict:
    since = _iso(_now() - timedelta(days=days))
    sessions = await db.connect_sessions.find({}, {"_id": 0, "profile": 1, "source": 1, "completed_at": 1, "max_step": 1,
                                                    "demos": 1, "created_at": 1, "lead_id": 1, "answers.activity": 1}).to_list(50000)
    sessions = [s for s in sessions if (s.get("created_at") or "") >= since]
    leads = await db.connect_leads.find({}, {"_id": 0}).to_list(50000)
    leads = [l for l in leads if (l.get("created_at") or "") >= since]

    def count(items, key):
        out: dict = {}
        for i in items:
            k = key(i) or "—"
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    started = len(sessions)
    completed = sum(1 for s in sessions if s.get("completed_at"))
    demo_started = sum(1 for s in sessions for d in (s.get("demos") or {}).values() if d.get("started_at"))
    demo_completed = sum(1 for s in sessions for d in (s.get("demos") or {}).values() if d.get("completed_at"))
    pain_counts: dict = {}
    for l in leads:
        for p in l.get("pains") or []:
            pain_counts[p] = pain_counts.get(p, 0) + 1
    seg = count([s for s in sessions if s.get("profile") == "client"], lambda s: (s.get("answers") or {}).get("activity"))
    resp_times = []
    for l in leads:
        if l.get("first_response_at") and l.get("created_at"):
            try:
                d = datetime.fromisoformat(l["first_response_at"]) - datetime.fromisoformat(l["created_at"])
                resp_times.append(d.total_seconds() / 3600)
            except ValueError:
                pass
    now = _iso()
    no_follow = [l["lead_id"] for l in leads if l.get("stage") not in CLOSED_STAGES and not l.get("anonymized")
                 and not any(not t.get("done") and (t.get("due_at") or "") >= now for t in l.get("tasks") or [])
                 and not l.get("first_response_at")]
    funnel = {p: {st: sum(1 for l in leads if l["profile"] == p and l.get("stage") == st) for st in STAGES[p]} for p in PROFILES}
    return {
        "period_days": days,
        "sessions_by_source": count(sessions, lambda s: s.get("source")),
        "sessions_by_profile": count(sessions, lambda s: s.get("profile")),
        "leads_by_source": count(leads, lambda l: l.get("source")),
        "leads_by_profile": count(leads, lambda l: l.get("profile")),
        "leads_by_priority": count(leads, lambda l: l.get("priority_override") or l.get("priority")),
        "top_pains": dict(sorted(pain_counts.items(), key=lambda kv: -kv[1])),
        "segments": seg,
        "diagnosis": {"started": started, "completed": completed,
                      "completion_rate": round(completed / started * 100, 1) if started else None,
                      "converted_to_lead": sum(1 for s in sessions if s.get("lead_id"))},
        "demos": {"started": demo_started, "completed": demo_completed},
        "requests": {k: sum(1 for l in leads if l.get("next_step") == k) for k in ("meeting", "individual_demo", "pilot", "report")},
        "funnel": funnel,
        "first_response_hours": {"count": len(resp_times),
                                 "median": round(sorted(resp_times)[len(resp_times) // 2], 1) if resp_times else None},
        "without_follow_up": len(no_follow),
        "pilots_and_proposals": sum(1 for l in leads if l.get("stage") in ("pilot_proposed", "pilot_running", "proposal_sent", "negotiation")),
        "won": sum(1 for l in leads if l.get("stage") in ("won", "invested", "active")),
        "investors_by_stage": funnel["investor"],
        "note": "Todos os indicadores derivam de sessões e oportunidades reais registadas. Receita atribuível não é calculada: não existe ligação verificada entre oportunidades e faturação.",
    }


@router.get("/admin/export.csv", dependencies=[Depends(require_enabled)])
async def admin_export(admin=Depends(admin_user), profile: str | None = None) -> Response:
    flt = {"profile": profile} if profile in PROFILES else {}
    rows = await db.connect_leads.find(flt, {"_id": 0}).sort("created_at", -1).to_list(20000)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["ID", "Perfil", "Data", "Nome", "Empresa", "E-mail", "Telefone", "País", "Idioma", "Origem", "Campanha",
                "Etapa", "Prioridade", "Score", "Justificação", "Dores", "Soluções", "Demos vistas", "Próximo passo pedido",
                "Responsável", "Próxima ação", "Próximo contacto", "Consentimento marketing"])

    def safe(v):
        s = str(v or "")
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s  # proteção contra injeção de fórmulas

    for l in rows:
        c = l.get("contact") or {}
        w.writerow([safe(x) for x in [
            l["lead_id"], l["profile"], (l.get("created_at") or "")[:16].replace("T", " "), c.get("name"), c.get("company"),
            c.get("email"), c.get("phone"), c.get("country"), l.get("lang"), l.get("source"), (l.get("utm") or {}).get("campaign"),
            l.get("stage"), l.get("priority_override") or l.get("priority"), l.get("score"),
            (l.get("score_detail") or {}).get("explanation"), ",".join(l.get("pains") or []), ",".join(x for x in l.get("solutions") or [] if x),
            ",".join(l.get("demos_viewed") or []), l.get("next_step"), l.get("owner"), l.get("next_action"),
            (l.get("next_contact_at") or "")[:16], "sim" if l.get("marketing_consent") else "não"]])
    await _audit(admin, "export_csv", None, {"rows": len(rows), "profile": profile})
    return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=connect-oportunidades.csv",
                             "Cache-Control": "no-store"})


@router.get("/admin/settings", dependencies=[Depends(require_enabled)])
async def admin_settings_get(admin=Depends(admin_user)) -> dict:
    s = await get_settings()
    return {**s, "scoring_effective": S.merged_config(s.get("scoring")), "stages": STAGES}


@router.put("/admin/settings", dependencies=[Depends(require_enabled)])
async def admin_settings_put(body: SettingsIn, admin=Depends(admin_user)) -> dict:
    data = body.model_dump(exclude_none=True)
    if "owners" in data:
        owners = {}
        for p, o in data["owners"].items():
            if p not in PROFILES or not isinstance(o, dict):
                raise HTTPException(422, "responsável inválido")
            owners[p] = {"name": str(o.get("name") or "")[:80], "email": str(o.get("email") or "")[:120]}
        data["owners"] = owners
    if "sla_hours" in data:
        data["sla_hours"] = {k: float(v) for k, v in data["sla_hours"].items()
                             if k in DEFAULT_SETTINGS["sla_hours"] and isinstance(v, (int, float)) and 0 < v <= 200}
    if "scoring" in data:
        thr = (data["scoring"].get("thresholds") or {}) if isinstance(data["scoring"], dict) else {}
        if thr and not (0 < thr.get("medium", 45) < thr.get("high", 75) <= 100):
            raise HTTPException(422, "limiares inválidos")
    await db.connect_settings.update_one({"_id": "settings"}, {"$set": data}, upsert=True)
    await _audit(admin, "settings", None, {"keys": sorted(data)})
    return await admin_settings_get(admin)


@router.get("/admin/audit", dependencies=[Depends(require_enabled)])
async def admin_audit_list(admin=Depends(admin_user), lead_id: str | None = None) -> list[dict]:
    flt = {"lead_id": lead_id} if lead_id else {}
    return await db.connect_audit.find(flt, {"_id": 0}).sort("at", -1).to_list(200)


@router.get("/status")
async def connect_status() -> dict:
    """Usado pelo frontend para mostrar/esconder a entrada; nunca revela dados."""
    return {"enabled": connect_enabled()}
