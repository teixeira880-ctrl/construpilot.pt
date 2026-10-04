"""Coach IA · Claude (primário) + OpenAI (fallback) + Perplexity (web search).

Expõe `coach_ask()` chamado por `routes/coach.py`.

Fluxo:
  1. Buscar projeto (opcional) → resumo PT-PT.
  2. Construir prompt system BTP (RGEU/RJUE/Eurocodes/UE).
  3. Deteção de palavras-chave de atualidade → Perplexity primeiro.
  4. `ai_router.coach_ask()` com Claude→OpenAI fallback.
  5. Falha total → `coach_failures` + email admin + `CoachUnavailableError`.

Nunca fazer log de secrets.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from engines.ai_providers.router import (
    CoachUnavailableError,
    ai_router,
    needs_web_search,
)

logger = logging.getLogger("coach.ai")

DEFAULT_HISTORY_LIMIT = int(os.environ.get("COACH_HISTORY_LIMIT", "10") or "10")
ADMIN_ALERT_EMAIL_DEFAULT = "info@construpilot.pt"

SYSTEM_PROMPT = (
    "És um assistente especialista em BTP (construção civil, obras públicas e "
    "privadas) para o mercado português. Respondes SEMPRE em Português Europeu "
    "(PT-PT), rigoroso, com referências normativas quando aplicável: RGEU "
    "(DL 38 382/1951), RJUE (DL 555/1999), RCCTE/REH (DL 118/2013), RSCIE "
    "(DL 220/2008), RRAE (DL 96/2008), DL 163/2006 (acessibilidade), CCP, e "
    "Eurocodes EN 1990-1999 com os anexos nacionais portugueses. Conheces "
    "também as normas espanholas (CTE, EHE-08, NCSE-02), francesas (RE2020, "
    "DTU), italianas (NTC 2018), alemãs (DIN, GEG), belgas (NBN, PEB/EPB), "
    "neerlandesas (Bouwbesluit) e britânicas (Building Regulations). "
    "Para preços indica intervalos realistas para o mercado português "
    "(Continente) e sinaliza que podem variar por região e fornecedor. "
    "Para projetos de engenharia (estrutura, AVAC, gás, eletricidade, "
    "acústica), recomenda consulta a técnico credenciado. Formato: "
    "resposta curta (3-5 linhas) + Referências normativas (lista) + "
    "Avisos quando necessário. Sê conciso, prático e útil."
)


# ---------------------------------------------------------------------------
# Coach IA · router multi-provedor (Claude · OpenAI · Perplexity).
# ---------------------------------------------------------------------------

def _project_brief(project: dict[str, Any] | None) -> str:
    if not project:
        return "(sem projeto associado)"
    est = project.get("estimation") or {}
    parts = [f"Nome: {project.get('name') or '—'}"]
    ptype = est.get("project_type_name") or project.get("project_type") or "—"
    parts.append(f"Categoria: {ptype}")
    area = est.get("surface") or project.get("area_m2") or project.get("surface_m2")
    if area:
        parts.append(f"Área: {area} m²")
    budget = est.get("total_avg") or project.get("budget") or project.get("estimated_budget")
    if budget:
        parts.append(f"Orçamento estimado: {int(float(budget)):,} €".replace(",", " "))
    city = project.get("city") or project.get("region") or est.get("region")
    if city:
        parts.append(f"Localização: {city}")
    finish = est.get("finish_level_name")
    if finish:
        parts.append(f"Acabamento: {finish}")
    return " | ".join(parts)[:350]


def _format_history(history: list[dict[str, Any]], limit: int) -> list[dict[str, str]]:
    """Devolve lista normalizada [{role, content}, ...] para os provedores."""
    if not history:
        return []
    out = []
    for m in history[-limit:]:
        role = (m.get("role") or "").lower()
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content[:1500]})
    return out


def _build_user_prompt(
    *,
    user_message: str,
    project: dict[str, Any] | None,
) -> str:
    brief = _project_brief(project)
    return (
        f"[PROJETO_ATUAL]\n{brief}\n\n"
        f"[PERGUNTA]\n{user_message.strip()}"
    )


async def _send_admin_alert(
    *,
    user_id: str,
    project_id: str | None,
    user_message: str,
    primary_meta: dict,
    fallback_meta: dict,
) -> None:
    from engines.emailer import send_email, wrap_html

    admin_email = (os.environ.get("ADMIN_ALERT_EMAIL") or ADMIN_ALERT_EMAIL_DEFAULT).strip()
    if not admin_email:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    subject = f"[ConstruPilot] Coach IA falhou — user_id={user_id[:16]}"
    snippet = (user_message or "").strip().replace("<", "&lt;").replace(">", "&gt;")[:500]

    def _row(k: str, v: Any) -> str:
        return f'<tr><td style="padding:4px 12px 4px 0;color:#555"><b>{k}</b></td><td>{v}</td></tr>'

    rows = [
        _row("Timestamp", ts),
        _row("user_id", user_id),
        _row("project_id", project_id or "(nenhum)"),
        _row("Primário · provider", str(primary_meta.get("provider"))),
        _row("Primário · erro", str(primary_meta.get("error") or primary_meta.get("code") or "—")),
        _row("Primário · status", str(primary_meta.get("status_code") or primary_meta.get("latency_ms") or "—")),
        _row("Fallback · provider", str(fallback_meta.get("provider"))),
        _row("Fallback · erro", str(fallback_meta.get("error") or fallback_meta.get("code") or "—")),
        _row("Fallback · status", str(fallback_meta.get("status_code") or fallback_meta.get("latency_ms") or "—")),
    ]
    body_html = (
        "<p>O Coach IA ConstruPilot falhou em <b>ambos</b> os provedores IA "
        "(primário + fallback). Detalhes:</p>"
        f"<table>{''.join(rows)}</table>"
        f"<p><b>Pergunta do utilizador (500 chars max):</b></p>"
        f'<pre style="background:#f5f5f5;padding:12px;border-radius:4px;'
        f'white-space:pre-wrap">{snippet}</pre>'
        "<p>Nenhuma resposta foi enviada ao utilizador — mostrada mensagem de "
        "indisponibilidade genérica.</p>"
    )
    try:
        html = wrap_html(subject, body_html)
        await send_email(admin_email, subject, html, from_name="ConstruPilot Alerts")
    except Exception as e:  # noqa: BLE001
        logger.warning("admin alert email failed: %s", type(e).__name__)


async def _record_failure(
    *,
    db,
    user_id: str,
    project_id: str | None,
    user_message: str,
    primary_meta: dict,
    fallback_meta: dict,
) -> None:
    try:
        await db.coach_failures.insert_one({
            "failure_id": "cf_" + uuid.uuid4().hex[:12],
            "user_id": user_id,
            "project_id": project_id,
            "message_snippet": (user_message or "")[:500],
            "primary_meta": primary_meta,
            "fallback_meta": fallback_meta,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("coach_failure insert failed: %s", type(e).__name__)


async def coach_ask(
    *,
    project_id: str | None,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    user_id: str,
    db,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    """Interface pública do Coach IA.

    Retorno em sucesso:
      {"text", "model", "provider", "mode_used", "request_id",
       "latency_ms", "citations", "web_enriched"}
    Levanta `CoachUnavailableError` se ambos os provedores falharem.
    """
    project = None
    if project_id:
        project = await db.projects.find_one(
            {"project_id": project_id, "user_id": user_id}, {"_id": 0},
        )

    history_norm = _format_history(conversation_history, history_limit)
    user_prompt = _build_user_prompt(user_message=user_message, project=project)
    enrich = needs_web_search(user_message)

    logger.info("coach ask | user=%s project=%s web_enrich=%s",
                user_id[:12], project_id, enrich)

    try:
        resp = await ai_router.coach_ask(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            history=history_norm,
            max_tokens=1024,
            temperature=0.3,
            enrich_with_web=enrich,
        )
    except CoachUnavailableError as e:
        await _record_failure(
            db=db, user_id=user_id, project_id=project_id,
            user_message=user_message,
            primary_meta=e.primary_meta, fallback_meta=e.fallback_meta,
        )
        await _send_admin_alert(
            user_id=user_id, project_id=project_id, user_message=user_message,
            primary_meta=e.primary_meta, fallback_meta=e.fallback_meta,
        )
        raise

    return {
        "text": resp.text.strip(),
        "model": resp.model,
        "provider": resp.provider,
        "mode_used": resp.provider,  # compat com UI antiga
        "request_id": resp.request_id,
        "latency_ms": resp.latency_ms,
        "web_enriched": enrich and bool(resp.citations),
        "citations": [
            {"url": c.url, "title": c.title, "snippet": c.snippet}
            for c in resp.citations
        ],
    }


__all__ = [
    "coach_ask", "CoachUnavailableError",
    "SYSTEM_PROMPT", "DEFAULT_HISTORY_LIMIT",
]
