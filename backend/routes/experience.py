"""ConstruPilot Experience — página pública /experiencia (diagnóstico comercial).

Recebe o pedido de relatório/demonstração no fim do diagnóstico e cria a oportunidade no CRM
(coleção ``commercial_leads``, a mesma do contacto Enterprise).

Garantias:
  * Nada é guardado sem consentimento explícito (422 ``consent_required``).
  * Anti-spam: honeypot + formulário demasiado rápido → resposta idêntica a um sucesso, nada guardado.
  * Rate limit por IP e deduplicação (mesmo e-mail + empresa em 24 h, ou mesmo ``submission_id``).
  * A oportunidade fica guardada mesmo que o e-mail interno falhe.
  * Só há notificação INTERNA (caixas comerciais). Nenhum e-mail é enviado ao visitante.
  * A pontuação é calculada no servidor a partir das respostas: nunca se confia no browser.
"""

import hashlib
import html
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.rate_limit import limiter
from core.security import admin_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/experience", tags=["experience"])

# Caixas que recebem cada formulário preenchido (separadas por vírgula em EXPERIENCE_LEAD_EMAILS).
DEFAULT_RECIPIENTS = "info@construpilot.pt,info@construpilot.fr"
ROLES = {"company", "gc", "architect", "engineer", "qs", "reno", "pm", "owner", "other"}
CATEGORIES = {"takeoff", "estimation", "drawings", "docs", "coord", "materials", "technical", "other"}
STATUSES = ("discovery_completed", "demo_requested")
_OK_MSG = {"pt": "Obrigado. A equipa ConstruPilot entra em contacto contigo em 2 dias úteis.",
           "fr": "Merci. L'équipe ConstruPilot vous recontacte sous 2 jours ouvrés.",
           "en": "Thank you. The ConstruPilot team will contact you within 2 business days."}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def recipients() -> list[str]:
    raw = os.environ.get("EXPERIENCE_LEAD_EMAILS") or DEFAULT_RECIPIENTS
    return [e.strip() for e in raw.split(",") if "@" in e]


class Need(BaseModel):
    id: str = Field(max_length=40)
    label: str = Field(max_length=200)


class Estimate(BaseModel):
    """Estimativa mostrada ao visitante. Guardada como informação declarada, não como facto."""
    scenario_pct: float = Field(default=0, ge=0, le=100)
    hours_month_today: float | None = Field(default=None, ge=0, le=100000)
    hours_month_saved: float | None = Field(default=None, ge=0, le=100000)
    value_month_eur: float | None = Field(default=None, ge=0, le=100000000)
    extra_estimates_month: float | None = Field(default=None, ge=0, le=100000)
    extra_margin_month_eur: float | None = Field(default=None, ge=0, le=100000000)
    at_stake_eur: float | None = Field(default=None, ge=0, le=1000000000)


class ExperienceLeadIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    company: str = Field(default="", max_length=160)
    email: EmailStr
    lang: Literal["pt", "fr", "en"] = "pt"
    demo: bool = False
    demo_lang: Literal["pt-PT", "fr-FR", "en"] = "pt-PT"
    goal: str = Field(default="", max_length=200)
    consent: bool
    role: str = Field(max_length=20)
    role_label: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=60)
    company_type: str = Field(default="", max_length=80)
    team: str = Field(default="", max_length=20)
    decision: Literal["decide", "influence", "user", ""] = ""
    urgency: Literal["now", "q", "year", "explore", ""] = ""
    software: str = Field(default="", max_length=300)
    needs: list[Need] = Field(default_factory=list, max_length=12)
    priority: Need | None = None
    features: list[str] = Field(default_factory=list, max_length=12)
    answers: dict[str, str] = Field(default_factory=dict)   # perguntas → respostas legíveis
    estimate: Estimate = Field(default_factory=Estimate)
    website: str = ""          # honeypot: tem de ficar vazio
    elapsed_ms: int = 0        # tempo no formulário (anti-bot)
    submission_id: str = Field(default="", max_length=64)


def score(body: ExperienceLeadIn) -> dict:
    """Pontuação transparente (0–18). Resume as respostas; NÃO é uma probabilidade de compra."""
    est, h = body.estimate, body.estimate.hours_month_today
    rows = [
        ("problem_intensity", (3 if h >= 40 else 2 if h >= 15 else 1) if h else (2 if len(body.needs) >= 3 else 1 if body.needs else 0)),
        ("urgency", {"now": 3, "q": 2, "year": 1}.get(body.urgency, 0)),
        ("product_fit", 2 if body.priority and body.priority.id.split("_")[0] in CATEGORIES - {"other"} else 0),
        ("decision_authority", {"decide": 3, "influence": 2, "user": 1}.get(body.decision, 3 if body.role == "owner" else 0)),
        ("budget", 0),   # não perguntado no diagnóstico: a apurar na conversa comercial
        ("next_step_commitment", 3 if body.demo else 2),
    ]
    total = sum(v for _, v in rows)
    return {"rows": [{"criterion": k, "points": v, "max": 3} for k, v in rows], "total": total, "max": 18,
            "suggest_qualified": total >= 9, "has_estimate": bool(h or est.at_stake_eur)}


def _email_html(d: dict) -> str:
    esc = lambda v: html.escape(str(v if v not in (None, "") else "—"))  # noqa: E731
    est = d["estimate"]
    fields = [("Nome", d["name"]), ("Empresa", d["company"]), ("E-mail", d["email"]), ("Idioma", d["lang"]),
              ("Perfil", d["role_label"] or d["role"]), ("País", d["country"]), ("Tipo de empresa", d["company_type"]),
              ("Equipa", d["team"]), ("Software atual", d["software"]),
              ("Necessidades", ", ".join(n["label"] for n in d["needs"])),
              ("Prioridade", (d["priority"] or {}).get("label")),
              ("Pedido", "Demonstração" + (f" ({d['demo_lang']})" if d["demo"] else "") if d["demo"] else "Relatório"),
              ("Objetivo da reunião", d["goal"]),
              ("Horas por mês hoje", est.get("hours_month_today")), ("Horas ganhas por mês (cenário)", est.get("hours_month_saved")),
              ("Valor por mês (cenário, €)", est.get("value_month_eur")), ("Cenário (%)", est.get("scenario_pct")),
              ("Em jogo na obra (€)", est.get("at_stake_eur")),
              ("Pontuação", f"{d['score']['total']} / {d['score']['max']}"), ("Estado", d["status"]), ("Lead ID", d["lead_id"])]
    rows = "".join(f"<tr><td style='padding:4px 14px 4px 0;color:#666;vertical-align:top'>{esc(k)}</td><td>{esc(v)}</td></tr>"
                   for k, v in fields)
    answers = "".join(f"<tr><td style='padding:3px 14px 3px 0;color:#666;vertical-align:top'>{esc(k)}</td><td>{esc(v)}</td></tr>"
                      for k, v in d["answers"].items())
    return (f"<h2>Novo diagnóstico ConstruPilot Experience</h2><table>{rows}</table>"
            f"<h3>Respostas</h3><table>{answers}</table>"
            "<p style='color:#666'>A pontuação resume as respostas; não é uma probabilidade de compra. "
            "Os valores do cenário foram indicados pelo visitante e não são resultados medidos.</p>")


@router.post("/lead")
@limiter.limit("5/hour")
async def create_lead(body: ExperienceLeadIn, request: Request, response: Response) -> dict:
    lang = body.lang
    if body.website.strip() or (0 < body.elapsed_ms < 2500):
        logger.info("experience lead dropped (anti-spam)")
        return {"ok": True, "message": _OK_MSG[lang]}
    if not body.consent:
        raise HTTPException(422, {"code": "consent_required"})
    if body.role not in ROLES:
        raise HTTPException(422, {"code": "invalid_role"})
    if len(body.answers) > 60 or any(len(k) > 200 or len(v) > 600 for k, v in body.answers.items()):
        raise HTTPException(422, {"code": "answers_too_large"})
    email = body.email.lower().strip()
    dedup_key = hashlib.sha256(f"exp|{email}|{body.company.strip().lower()}".encode()).hexdigest()[:32]
    since = (_now() - timedelta(hours=24)).isoformat()
    dup = await db.commercial_leads.find_one(
        {"$or": [{"dedup_key": dedup_key, "created_at": {"$gt": since}},
                 *([{"submission_id": body.submission_id}] if body.submission_id else [])]},
        {"_id": 0, "lead_id": 1})
    if dup:
        return {"ok": True, "lead_id": dup["lead_id"], "duplicate": True, "message": _OK_MSG[lang]}
    now = _now().isoformat()
    doc = {
        "lead_id": "lead_" + secrets.token_hex(8), "market": "pt", "source": "experience",
        "name": body.name.strip(), "company": body.company.strip(), "email": email, "lang": lang,
        "role": body.role, "role_label": body.role_label.strip(), "country": body.country.strip(),
        "company_type": body.company_type.strip(), "team": body.team.strip(), "decision": body.decision,
        "urgency": body.urgency, "software": body.software.strip(),
        "needs": [n.model_dump() for n in body.needs], "priority": body.priority.model_dump() if body.priority else None,
        "features": [f[:120] for f in body.features], "answers": body.answers,
        "estimate": body.estimate.model_dump(), "demo": body.demo, "demo_lang": body.demo_lang, "goal": body.goal.strip(),
        "score": score(body),
        "status": STATUSES[1] if body.demo else STATUSES[0],
        "owner": None, "next_action": "propose_demo_slot" if body.demo else "send_report", "follow_up_at": None,
        "consent": {"given": True, "at": now, "policy": "/privacidade",
                    "text": "Autorizo a ConstruPilot a usar estes dados para me responder a este pedido."},
        "dedup_key": dedup_key, "submission_id": body.submission_id or None, "created_at": now,
        # RGPD: conservação de um contacto comercial não convertido (3 anos).
        "retain_until": (_now() + timedelta(days=3 * 365)).isoformat(),
    }
    await db.commercial_leads.insert_one(dict(doc))
    sent = []
    try:
        from engines import emailer
        subject = f"[Experience] {'Demonstração' if body.demo else 'Relatório'} — {(doc['company'] or doc['name'])[:80]}"
        for to in recipients():
            try:
                await emailer.send_email(to, subject, _email_html(doc), reply_to=email)
                sent.append(to)
            except Exception as e:  # noqa: BLE001 — uma caixa em falha não impede as outras
                logger.warning(f"experience lead notification to {to} failed: {e}")
    except Exception as e:  # noqa: BLE001 — a oportunidade fica guardada mesmo sem e-mail
        logger.warning(f"experience lead notification failed: {e}")
    await db.commercial_leads.update_one({"lead_id": doc["lead_id"]}, {"$set": {"notified": sent}})
    return {"ok": True, "lead_id": doc["lead_id"], "message": _OK_MSG[lang]}


@router.get("/leads")
async def list_leads(limit: int = 100, user=Depends(admin_user)) -> dict:
    """Oportunidades vindas da Experience (só administradores)."""
    cur = db.commercial_leads.find({"source": "experience"}, {"_id": 0, "dedup_key": 0}).sort("created_at", -1)
    return {"leads": await cur.to_list(max(1, min(limit, 500)))}
