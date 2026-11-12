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
ROLES = {"company", "gc", "architect", "engineer", "qs", "reno", "pm", "owner", "client", "investor", "partner", "other"}
# Tipo de contacto: muda a etiqueta e o próximo passo do e-mail interno.
KIND = {"investor": "investor", "partner": "partner"}   # todos os outros perfis são "customer"
_KIND_PT = {"investor": "INVESTIDOR", "partner": "PARCEIRO"}
CATEGORIES = {"takeoff", "estimation", "drawings", "docs", "coord", "materials", "technical", "other"}
STATUSES = ("discovery_completed", "demo_requested")
_OK_MSG = {"pt": "Obrigado. A equipa ConstruPilot entra em contacto consigo em 2 dias úteis.",
           "fr": "Merci. L'équipe ConstruPilot vous recontacte sous 2 jours ouvrés.",
           "en": "Thank you. The ConstruPilot team will contact you within 2 business days.",
           "uk": "Дякуємо. Команда ConstruPilot зв'яжеться з вами протягом 2 робочих днів."}


def _now() -> datetime:
    return datetime.now(timezone.utc)


DEMO_SLA_BUSINESS_DAYS = 5   # quem responde «Já» e pede demonstração recebe uma demo funcional neste prazo
_SLA_MSG = {"pt": "Obrigado. Como pediu para avançar já, a equipa ConstruPilot mostra-lhe uma demonstração funcional em até 5 dias úteis.",
            "fr": "Merci. Comme vous souhaitez avancer tout de suite, l'équipe ConstruPilot vous présente une démonstration fonctionnelle sous 5 jours ouvrés.",
            "en": "Thank you. Since you want to move now, the ConstruPilot team will show you a working demo within 5 business days.",
            "uk": "Дякуємо. Оскільки ви хочете почати вже зараз, команда ConstruPilot покаже вам робочу демонстрацію протягом 5 робочих днів."}
_WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def add_business_days(start: datetime, days: int) -> datetime:
    """Soma dias úteis (segunda a sexta). Os feriados não são considerados."""
    d = start
    while days > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days -= 1
    return d


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
    lang: Literal["pt", "fr", "en", "uk"] = "pt"
    demo: bool = False
    demo_lang: Literal["pt-PT", "fr-FR", "en", "uk"] = "pt-PT"
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
        ("decision_authority", {"decide": 3, "influence": 2, "user": 1}.get(body.decision, 3 if body.role in ("owner", "client", "investor") else 0)),
        ("budget", 0),   # não perguntado no diagnóstico: a apurar na conversa comercial
        ("next_step_commitment", 3 if body.demo else 2),
    ]
    total = sum(v for _, v in rows)
    return {"rows": [{"criterion": k, "points": v, "max": 3} for k, v in rows], "total": total, "max": 18,
            "suggest_qualified": total >= 9, "has_estimate": bool(h or est.at_stake_eur)}


_PT = {
    "decision": {"decide": "Decide a compra", "influence": "Participa na decisão", "user": "Outra pessoa decide"},
    "urgency": {"now": "Já", "q": "Nos próximos 3 meses", "year": "Este ano", "explore": "Só a explorar"},
    "criterion": {"problem_intensity": "Intensidade do problema", "urgency": "Urgência", "product_fit": "Adequação ao produto",
                  "decision_authority": "Capacidade de decisão", "budget": "Orçamento (não perguntado)",
                  "next_step_commitment": "Compromisso com o próximo passo"},
    "lang": {"pt": "Português", "fr": "Francês", "en": "Inglês", "uk": "Ucraniano", "pt-PT": "português",
             "fr-FR": "francês"},
}
# Paleta escura "cinema", igual à da página /experiencia. Cada gradiente tem cor sólida de recurso
# (clientes de e-mail que ignoram gradientes mostram a cor sólida).
_C = {"ink": "#f2f6f4", "muted": "#9fb0b6", "line": "#22303a", "bg": "#03060b", "card": "#0b1116", "green": "#23c56f",
      "teal": "#1fe3c4", "copper": "#f6a968", "soft": "#0f2a1d", "amber": "#f6c560", "amber_soft": "#2a2212",
      "blue": "#8aa2ff", "blue_soft": "#161d38", "dark": "#02130c",
      "grad": "linear-gradient(100deg,#23c56f 0%,#1fe3c4 55%,#f6a968 100%)",
      "hero": "linear-gradient(135deg,#0e3a27 0%,#0b1116 48%,#2e1c10 100%)"}
LOGO_URL = "https://construpilot.pt/construpilot-icon.png"


def _eur(v) -> str:
    return "—" if v is None else f"{v:,.0f}".replace(",", " ") + " €"


def _num(v, unit: str = "") -> str:
    if v is None:
        return "—"
    t = f"{v:,.1f}".replace(",", " ").replace(".", ",")
    return (t[:-2] if t.endswith(",0") else t) + (f" {unit}" if unit else "")


def _level(total: int) -> tuple[str, str, str]:
    """Etiqueta de leitura rápida da pontuação (resume as respostas; não é probabilidade de compra)."""
    if total >= 12:
        return "Alta", _C["green"], _C["soft"]
    if total >= 9:
        return "Média", _C["amber"], _C["amber_soft"]
    return "Baixa", _C["muted"], _C["bg"]


def email_subject(d: dict) -> str:
    kind = "Demonstração pedida" if d["demo"] else "Relatório pedido"
    if d.get("lead_kind") in _KIND_PT:
        kind = f"{_KIND_PT[d['lead_kind']]} · " + ("Reunião pedida" if d["demo"] else "Contacto pedido")
    if d.get("demo_due_at"):
        due = datetime.fromisoformat(d["demo_due_at"])
        kind = f"DEMO ATÉ {due.strftime('%d/%m')} · {kind}"
    who = d["company"] or d["name"]
    return f"[Experience] {kind} · {who[:60]} · {(d['role_label'] or d['role'])[:40]} · {d['score']['total']}/{d['score']['max']}"


def _email_html(d: dict) -> str:
    """E-mail interno: lê-se de cima para baixo em 10 segundos (quem, o que pede, quanto vale, o que fazer)."""
    e = lambda v: html.escape(str(v)) if v not in (None, "", []) else "—"  # noqa: E731
    c, est, sc = _C, d["estimate"], d["score"]
    lvl, lvl_fg, lvl_bg = _level(sc["total"])
    demo = d["demo"]
    badge_bg, badge_fg, badge = (c["green"], c["dark"], "DEMONSTRAÇÃO PEDIDA") if demo else (c["blue_soft"], c["blue"], "RELATÓRIO PEDIDO")
    first = d["name"].split()[0] if d["name"].split() else d["name"]
    try:
        when = datetime.fromisoformat(d["created_at"]).astimezone(timezone.utc).strftime("%d/%m/%Y · %H:%M UTC")
    except Exception:  # noqa: BLE001
        when = d["created_at"]
    value = est.get("value_month_eur")
    stake = est.get("at_stake_eur")
    money_label, money = ("Em jogo na obra", _eur(stake)) if stake else ("Ganho estimado por mês", _eur(value) if value else "—")
    urgency = _PT["urgency"].get(d["urgency"], "Por apurar")
    reply_subject = "A sua demonstração ConstruPilot" if demo else "O seu diagnóstico ConstruPilot"
    mailto = f"mailto:{html.escape(d['email'])}?subject={html.escape(reply_subject.replace(' ', '%20'))}"
    step = (f"Propor 2 horários reais para a demonstração, em {_PT['lang'].get(d['demo_lang'], d['demo_lang'])}."
            if demo else "Enviar o relatório de diagnóstico e propor uma conversa.")
    lk = d.get("lead_kind")
    if lk in _KIND_PT:
        badge = f"{_KIND_PT[lk]} · " + ("REUNIÃO PEDIDA" if demo else "CONTACTO PEDIDO")
        badge_bg, badge_fg = (c["copper"], c["dark"]) if lk == "investor" else (c["teal"], c["dark"])
        reply_subject = "A sua conversa com a ConstruPilot"
        mailto = f"mailto:{html.escape(d['email'])}?subject={html.escape(reply_subject.replace(' ', '%20'))}"
        step = ("Marcar reunião com os fundadores, com demonstração." if lk == "investor" and demo
                else "Responder e propor uma conversa com os fundadores." if lk == "investor"
                else "Responder e propor uma conversa sobre a parceria.")
    sla = ""
    if d.get("demo_due_at"):
        due = datetime.fromisoformat(d["demo_due_at"])
        due_txt = f"{_WEEKDAYS[due.weekday()]}, {due.strftime('%d/%m/%Y')}"
        step = f"Mostrar uma demonstração funcional até {due_txt}, em {_PT['lang'].get(d['demo_lang'], d['demo_lang'])}."
        sla = (f"<tr><td style='padding:0 24px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
               f"style='margin-top:20px;background:{c['amber_soft']};border:1px solid {c['amber']};border-radius:10px'><tr>"
               f"<td style='padding:14px 16px'><div style='font:700 11px Arial,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:{c['amber']}'>"
               f"Compromisso · {DEMO_SLA_BUSINESS_DAYS} dias úteis</div>"
               f"<div style='font:800 22px/1.2 Arial,sans-serif;color:#ffffff;padding-top:6px'>Demo funcional até {e(due_txt)}</div>"
               f"<div style='font:13px Arial,sans-serif;color:{c['muted']};padding-top:4px'>O visitante respondeu «Já» e pediu demonstração. "
               f"Foi-lhe prometido este prazo no site.</div></td></tr></table></td></tr>")
    label = f"font:700 11px Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:{c['muted']}"

    def tile(title, big, small, fg=c["ink"], bg=c["card"]):
        return (f"<td width='33%' valign='top' style='padding:0 5px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
                f"style='background:{bg};border:1px solid {c['line']};border-radius:10px'><tr><td style='padding:14px 14px 12px'>"
                f"<div style='{label}'>{title}</div><div style='font:800 28px Arial,sans-serif;color:{fg};padding-top:8px;letter-spacing:-.01em'>{big}</div>"
                f"<div style='font:13px Arial,sans-serif;color:{c['muted']};padding-top:2px'>{small}</div></td></tr></table></td>")

    def section(title, body):
        return (f"<tr><td style='padding:22px 24px 0'><div style='{label};padding-bottom:8px'>{title}</div>{body}</td></tr>")

    def rows(pairs):
        out = "".join(f"<tr><td width='42%' valign='top' style='padding:7px 12px 7px 0;font:13px Arial,sans-serif;color:{c['muted']};"
                      f"border-bottom:1px solid {c['line']}'>{e(k)}</td><td valign='top' style='padding:7px 0;font:14px Arial,sans-serif;"
                      f"color:{c['ink']};border-bottom:1px solid {c['line']}'>{v if raw else e(v)}</td></tr>" for k, v, raw in pairs)
        return f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{out}</table>"

    prio = (d["priority"] or {}).get("label")
    chips = "".join(
        f"<span style='display:inline-block;margin:0 6px 6px 0;padding:6px 10px;border-radius:14px;font:13px Arial,sans-serif;"
        f"background:{c['soft'] if n['label'] == prio else c['bg']};color:{c['green'] if n['label'] == prio else c['ink']};"
        f"border:1px solid {c['green'] if n['label'] == prio else c['line']}'>{'★ ' if n['label'] == prio else ''}{e(n['label'])}</span>"
        for n in d["needs"]) or f"<span style='font:14px Arial,sans-serif;color:{c['muted']}'>Nenhuma necessidade indicada.</span>"

    if stake:
        est_rows = [("Valor previsto em risco de derrapagem", _eur(stake), False),
                    ("Cenário de controlo", _num(est.get("scenario_pct"), "%"), False)]
    else:
        est_rows = [("Horas por mês hoje, na prioridade", _num(est.get("hours_month_today"), "h"), False),
                    ("Horas ganhas por mês, prioridade e equipa (cenário)", _num(est.get("hours_month_saved"), "h"), False),
                    ("Valor desse tempo por mês", _eur(value), False),
                    ("Orçamentos a mais por mês", _num(est.get("extra_estimates_month")), False),
                    ("Margem adicional por mês", _eur(est.get("extra_margin_month_eur")), False),
                    ("Cenário de redução de tempo", _num(est.get("scenario_pct"), "%"), False)]
    est_rows = [r for r in est_rows if r[1] != "—"] or [("Estimativa", "O visitante não deu números para calcular.", False)]

    def bar(points, mx):
        cells = "".join(f"<td width='22' height='8' style='background:{(c['green'], c['teal'], c['copper'])[i % 3] if i < points else c['line']};font-size:0;line-height:0'>&nbsp;</td>"
                        f"<td width='3' style='font-size:0;line-height:0'>&nbsp;</td>" for i in range(mx))
        return f"<table role='presentation' cellpadding='0' cellspacing='0' style='display:inline-table;vertical-align:middle'><tr>{cells}</tr></table>"
    score_rows = [(_PT["criterion"].get(r["criterion"], r["criterion"]),
                   f"{bar(r['points'], r['max'])}&nbsp;<span style='font:13px Arial,sans-serif;color:{c['muted']}'>{r['points']} / {r['max']}</span>", True)
                  for r in sc["rows"]]

    contact = [("E-mail", f"<a href='{mailto}' style='color:{c['blue']}'>{e(d['email'])}</a>", True), ("Empresa", d["company"], False),
               ("Perfil", d["role_label"] or d["role"], False), ("País", d["country"], False), ("Tipo de empresa", d["company_type"], False),
               ("Equipa", (d["team"].replace("-", " a ") + " pessoas") if d["team"] else "", False), ("Quem decide", _PT["decision"].get(d["decision"], "Por apurar"), False),
               ("Ferramentas atuais", d["software"], False), ("Idioma no site", _PT["lang"].get(d["lang"], d["lang"]), False)]
    answers = [(k, v, False) for k, v in d["answers"].items()] or [("Respostas", "Sem respostas adicionais.", False)]
    consent_at = d["consent"]["at"][:16].replace("T", " ")

    return (
        f"<div style='display:none;max-height:0;overflow:hidden'>{e(badge.capitalize())} · {e(d['company'] or d['name'])} · "
        f"prioridade: {e(prio)} · {money_label.lower()}: {money}</div>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:{c['bg']}'><tr><td align='center' style='padding:20px 6px'>"
        f"<table role='presentation' width='640' cellpadding='0' cellspacing='0' style='width:100%;max-width:640px;background:{c['card']};border:1px solid {c['line']};border-radius:16px;overflow:hidden'>"
        f"<tr><td height='5' style='height:5px;font-size:0;line-height:0;background:{c['green']};background-image:{c['grad']}'>&nbsp;</td></tr>"
        f"<tr><td style='background:#000000;padding:14px 24px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        f"<td width='34'><img src='{LOGO_URL}' width='26' height='26' alt='' style='display:block;border-radius:6px'></td>"
        f"<td style='font:700 13px Arial,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#ffffff'>ConstruPilot Experience</td>"
        f"<td align='right' style='font:12px Arial,sans-serif;color:{c['muted']}'>{e(when)}</td></tr></table></td></tr>"
        f"<tr><td style='padding:34px 24px 30px;background:{c['card']};background-image:{c['hero']}'>"
        f"<span style='display:inline-block;padding:7px 13px;border-radius:5px;background:{badge_bg};color:{badge_fg};font:700 11px Arial,sans-serif;letter-spacing:.14em'>{badge}</span>"
        f"<div style='font:800 38px/1.02 Arial,sans-serif;letter-spacing:-.02em;text-transform:uppercase;color:#ffffff;padding-top:16px'>{e(d['name'])}</div>"
        f"<div style='font:16px/1.4 Arial,sans-serif;color:{c['ink']};padding-top:8px'>{e(d['company'])} <span style='color:{c['green']}'>·</span> {e(d['role_label'] or d['role'])}</div>"
        f"<div style='padding-top:22px'><a href='{mailto}' style='display:inline-block;padding:13px 22px;border-radius:8px;background:{c['green']};background-image:{c['grad']};"
        f"color:{c['dark']};font:700 15px Arial,sans-serif;text-decoration:none'>Responder a {e(first)} &rarr;</a>"
        f"<div style='font:14px Arial,sans-serif;color:{c['muted']};padding-top:10px'>{e(d['email'])}</div></div></td></tr>"
        + sla +
        f"<tr><td style='padding:20px 19px 0'><table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        + tile("Pontuação", f"{sc['total']} / {sc['max']}", f"Prioridade {lvl.lower()}", lvl_fg, lvl_bg)
        + tile(money_label, money, f"Cenário de {_num(est.get('scenario_pct'), '%')}" if (value or stake) else "Sem números", c["copper"])
        + tile("Urgência", e(urgency), _PT["decision"].get(d["decision"], "Decisão por apurar"), c["teal"])
        + "</tr></table></td></tr>"
        + section("Próximo passo", f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:{c['soft']};border-left:4px solid {c['green']};border-radius:6px'>"
                  f"<tr><td style='padding:16px 16px;font:17px/1.4 Arial,sans-serif;color:#ffffff'><b>{e(step)}</b>"
                  + (f"<br><span style='color:{c['muted']}'>Objetivo indicado: {e(d['goal'])}</span>" if d["goal"] else "") + "</td></tr></table>")
        + section("O que precisa (★ = prioridade)", f"<div>{chips}</div>")
        + section("Estimativa mostrada ao visitante", rows(est_rows))
        + section("Contacto e empresa", rows(contact))
        + section("Pontuação em detalhe", rows(score_rows))
        + section("Todas as respostas", rows(answers))
        + f"<tr><td style='padding:22px 24px 24px;font:12px/1.5 Arial,sans-serif;color:{c['muted']}'>"
        f"Lead {e(d['lead_id'])} · estado {e(d['status'])} · consentimento dado em {e(consent_at)} UTC.<br>"
        "A pontuação resume as respostas; não é uma probabilidade de compra. A estimativa é um cenário escolhido pelo visitante, não um resultado medido.<br>"
        "Responder a este e-mail escreve diretamente ao visitante.</td></tr>"
        "</table></td></tr></table>")


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
    created = _now()
    now = created.isoformat()
    urgent_demo = body.demo and body.urgency == "now"
    demo_due = add_business_days(created, DEMO_SLA_BUSINESS_DAYS).isoformat() if urgent_demo else None
    ok_msg = (_SLA_MSG if urgent_demo else _OK_MSG)[lang]
    doc = {
        "lead_id": "lead_" + secrets.token_hex(8), "market": "pt", "source": "experience",
        "lead_kind": KIND.get(body.role, "customer"),
        "name": body.name.strip(), "company": body.company.strip(), "email": email, "lang": lang,
        "role": body.role, "role_label": body.role_label.strip(), "country": body.country.strip(),
        "company_type": body.company_type.strip(), "team": body.team.strip(), "decision": body.decision,
        "urgency": body.urgency, "software": body.software.strip(),
        "needs": [n.model_dump() for n in body.needs], "priority": body.priority.model_dump() if body.priority else None,
        "features": [f[:120] for f in body.features], "answers": body.answers,
        "estimate": body.estimate.model_dump(), "demo": body.demo, "demo_lang": body.demo_lang, "goal": body.goal.strip(),
        "score": score(body),
        "status": STATUSES[1] if body.demo else STATUSES[0],
        "owner": None, "next_action": "deliver_demo" if urgent_demo else "propose_demo_slot" if body.demo else "send_report",
        "demo_due_at": demo_due, "follow_up_at": demo_due,
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
        subject = email_subject(doc)
        for to in recipients():
            try:
                await emailer.send_email(to, subject, _email_html(doc), reply_to=email)
                sent.append(to)
            except Exception as e:  # noqa: BLE001 — uma caixa em falha não impede as outras
                logger.warning(f"experience lead notification to {to} failed: {e}")
    except Exception as e:  # noqa: BLE001 — a oportunidade fica guardada mesmo sem e-mail
        logger.warning(f"experience lead notification failed: {e}")
    await db.commercial_leads.update_one({"lead_id": doc["lead_id"]}, {"$set": {"notified": sent}})
    return {"ok": True, "lead_id": doc["lead_id"], "message": ok_msg, "demo_due_at": demo_due}


@router.get("/leads")
async def list_leads(limit: int = 100, user=Depends(admin_user)) -> dict:
    """Oportunidades vindas da Experience (só administradores)."""
    cur = db.commercial_leads.find({"source": "experience"}, {"_id": 0, "dedup_key": 0}).sort("created_at", -1)
    return {"leads": await cur.to_list(max(1, min(limit, 500)))}
