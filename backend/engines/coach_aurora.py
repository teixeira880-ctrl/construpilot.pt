"""Coach IA · motor Aurora exclusivo (sem fallback Emergent LLM).

Fluxo:
  1. Buscar projeto (opcional) → resumo estruturado (nome, área, orçamento, morada, categoria).
  2. Construir prompt sistema BTP-PT + histórico N últimas msgs + pergunta.
  3. `ask_with_retry` em `mode=reasoning` (Aurora default) → 3 tentativas.
  4. Se `text` vazio após retries → segundo tentativa em `mode=fast` (via header/param custom).
     Aurora atual não expõe `mode` no payload; usamos `resources=["mode:fast"]` como
     dica textual. Se o wrapper Aurora suportar `mode` nativamente no futuro basta
     passar via body — o call site é isolado neste ficheiro.
  5. Ambos vazios → registar em `coach_failures`, enviar email admin (fire-and-forget),
     levantar `CoachAuroraError`.

Nunca fazer log de secrets / API keys / signing.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from engines.aurora_client import (
    AuroraCompanyClient,
    AuroraConfig,
    AuroraKeyIdInvalid,
    AuroraNotConfigured,
)

logger = logging.getLogger("coach.aurora")

DEFAULT_HISTORY_LIMIT = int(os.environ.get("COACH_HISTORY_LIMIT", "10") or "10")
ADMIN_ALERT_EMAIL_DEFAULT = "info@construpilot.pt"

SYSTEM_PROMPT = (
    "És um assistente especialista em BTP (Bâtiment et Travaux Publics) e construção "
    "civil em Portugal. Respondes SEMPRE em Português Europeu (PT-PT), com termos "
    "técnicos corretos e referências à legislação portuguesa quando relevante "
    "(RGEU, RJUE, RCCTE, EN 1992/1993 para estrutura, DL 118/2013 para eficiência "
    "energética, etc.). Se a pergunta pedir preços, indica intervalos realistas "
    "para o mercado português (Continente) e refere que os valores podem variar "
    "por região e fornecedor. Se algo depender de projeto de engenharia (estrutura, "
    "AVAC, gás, eletricidade), recomenda claramente que o utilizador consulte um "
    "engenheiro/técnico credenciado. Sê conciso, prático e útil."
)


class CoachAuroraError(RuntimeError):
    """Levantada quando Aurora falha em ambos os modos reasoning + fast."""

    def __init__(self, message: str, *, reasoning_meta: dict, fast_meta: dict):
        super().__init__(message)
        self.reasoning_meta = reasoning_meta
        self.fast_meta = fast_meta


def _project_brief(project: dict[str, Any] | None) -> str:
    """Resumo compacto do projeto para o prompt (max ~350 chars)."""
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


def _format_history(history: list[dict[str, Any]], limit: int) -> str:
    """Últimas N msgs em formato 'Utilizador: … / Assistente: …'."""
    if not history:
        return ""
    tail = history[-limit:]
    lines: list[str] = []
    for m in tail:
        role = (m.get("role") or "").lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        prefix = "Utilizador" if role == "user" else "Assistente"
        # cap por linha para evitar prompts gigantes
        lines.append(f"{prefix}: {content[:600]}")
    return "\n".join(lines)


def _build_prompt(
    *,
    user_message: str,
    project: dict[str, Any] | None,
    history: list[dict[str, Any]],
    history_limit: int,
    mode_hint: str | None = None,
) -> str:
    """Prompt único enviado a Aurora `/ask` (Aurora não separa system/user)."""
    brief = _project_brief(project)
    convo = _format_history(history, limit=history_limit)
    mode_line = f"[MODO_SUGERIDO]\n{mode_hint}\n\n" if mode_hint else ""
    return (
        f"[SISTEMA]\n{SYSTEM_PROMPT}\n\n"
        f"[PROJETO_ATUAL]\n{brief}\n\n"
        f"{mode_line}"
        f"[HISTÓRICO_RECENTE]\n{convo if convo else '(nova conversa)'}\n\n"
        f"[PERGUNTA]\n{user_message.strip()}"
    )


async def _send_admin_alert(
    *,
    user_id: str,
    project_id: str | None,
    user_message: str,
    reasoning_meta: dict,
    fast_meta: dict,
) -> None:
    """Envia email ao admin. Fire-and-forget: erros silenciados."""
    from engines.emailer import send_email, wrap_html

    admin_email = (os.environ.get("ADMIN_ALERT_EMAIL") or ADMIN_ALERT_EMAIL_DEFAULT).strip()
    if not admin_email:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    subject = f"[ConstruPilot] Aurora Coach IA falhou — user_id={user_id[:16]}"
    snippet = (user_message or "").strip().replace("<", "&lt;").replace(">", "&gt;")[:500]

    def _row(k: str, v: Any) -> str:
        return f'<tr><td style="padding:4px 12px 4px 0;color:#555"><b>{k}</b></td><td>{v}</td></tr>'

    rows = [
        _row("Timestamp", ts),
        _row("user_id", user_id),
        _row("project_id", project_id or "(nenhum)"),
        _row("reasoning · status", str(reasoning_meta.get("last_status"))),
        _row("reasoning · tentativas", str(reasoning_meta.get("attempts"))),
        _row("reasoning · erro", str(reasoning_meta.get("error") or "empty_text")),
        _row("reasoning · request_id", str(reasoning_meta.get("request_id") or "—")),
        _row("fast · status", str(fast_meta.get("last_status"))),
        _row("fast · tentativas", str(fast_meta.get("attempts"))),
        _row("fast · erro", str(fast_meta.get("error") or "empty_text")),
        _row("fast · request_id", str(fast_meta.get("request_id") or "—")),
    ]
    body_html = (
        "<p>O Coach IA ConstruPilot falhou em ambos os modos Aurora "
        "(<code>reasoning</code> e <code>fast</code>). Detalhes:</p>"
        f"<table>{''.join(rows)}</table>"
        f"<p><b>Pergunta do utilizador (500 chars max):</b></p>"
        f'<pre style="background:#f5f5f5;padding:12px;border-radius:4px;'
        f'white-space:pre-wrap">{snippet}</pre>'
        "<p>Este é um alerta automático — nenhuma resposta foi enviada ao utilizador.</p>"
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
    reasoning_meta: dict,
    fast_meta: dict,
) -> None:
    """Regista incidente em coach_failures. Falhas silenciadas."""
    try:
        await db.coach_failures.insert_one({
            "failure_id": "cf_" + uuid.uuid4().hex[:12],
            "user_id": user_id,
            "project_id": project_id,
            "message_snippet": (user_message or "")[:500],
            "reasoning_meta": reasoning_meta,
            "fast_meta": fast_meta,
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
    """Envia pergunta ao Coach IA (Aurora exclusivo). Ver docstring do módulo.

    Retorno em sucesso:
      {"text", "model", "route", "mode_used", "request_id", "attempts"}
    Levanta:
      CoachAuroraError se ambos os modos falharem (após envio do email admin).
      AuroraNotConfigured / AuroraKeyIdInvalid se .env estiver mal configurado.
    """
    if not AuroraConfig().configured:
        raise AuroraNotConfigured("Aurora não configurado.")

    project = None
    if project_id:
        project = await db.projects.find_one(
            {"project_id": project_id, "user_id": user_id}, {"_id": 0},
        )

    # Aurora exige que o project_id exista do lado dele → upsert on-the-fly.
    # - Se há projeto ConstruPilot, sincronizamos o payload completo.
    # - Se não há, usamos um projeto "guarda-chuva" por utilizador para perguntas gerais.
    from engines.aurora_sync import sync_project_to_aurora

    aurora_project_id: str
    if project:
        aurora_project_id = project_id  # type: ignore[assignment]
        try:
            await sync_project_to_aurora(project)
        except Exception as e:  # noqa: BLE001
            logger.debug("aurora sync skipped: %s", type(e).__name__)
    else:
        # Hash curto e determinístico do user_id — evita colisões com projetos reais
        # e problemas com caracteres especiais no external_ref Aurora.
        import hashlib
        uid_hash = hashlib.md5(user_id.encode("utf-8")).hexdigest()[:12]
        aurora_project_id = f"coach-general-{uid_hash}"
        try:
            await sync_project_to_aurora({
                "project_id": aurora_project_id,
                "user_id": user_id,
                "name": "Sessão Coach IA (perguntas gerais)",
                "status": "active",
                "project_type": "coach_general",
            })
        except Exception as e:  # noqa: BLE001
            logger.debug("aurora sync (coach general) skipped: %s", type(e).__name__)

    # --- Fase 1 · reasoning (default Aurora) --------------------------------
    prompt = _build_prompt(
        user_message=user_message,
        project=project,
        history=conversation_history,
        history_limit=history_limit,
    )
    logger.info("coach ask | user=%s project=%s prompt_len=%d",
                user_id[:12], project_id, len(prompt))

    client = AuroraCompanyClient()
    answer, meta = await client.ask_with_retry(
        question=prompt,
        project_id=aurora_project_id,
        resources=[],
        max_attempts=3,
        base_delay=1.0,
    )
    reasoning_meta = {
        **{k: meta.get(k) for k in ("attempts", "last_status", "error", "model", "route")},
        "mode": "reasoning",
        "request_id": client._last_request_id,
    }

    if meta.get("ok") and answer and answer.text.strip():
        return {
            "text": answer.text.strip(),
            "model": answer.model,
            "route": answer.route,
            "mode_used": answer.mode or "reasoning",
            "request_id": client._last_request_id,
            "attempts": meta.get("attempts"),
        }

    # --- Fase 2 · fast (fallback) -------------------------------------------
    logger.info("coach reasoning failed (%s) → trying fast", meta.get("error"))
    prompt_fast = _build_prompt(
        user_message=user_message,
        project=project,
        history=conversation_history,
        history_limit=history_limit,
        mode_hint=(
            "Responde em modo rápido e objetivo (bullet points, resposta curta). "
            "Não elabores raciocínio interno."
        ),
    )
    client2 = AuroraCompanyClient()
    answer2, meta2 = await client2.ask_with_retry(
        question=prompt_fast,
        project_id=aurora_project_id,
        resources=[],
        max_attempts=2,
        base_delay=1.0,
    )
    fast_meta = {
        **{k: meta2.get(k) for k in ("attempts", "last_status", "error", "model", "route")},
        "mode": "fast",
        "request_id": client2._last_request_id,
    }

    if meta2.get("ok") and answer2 and answer2.text.strip():
        return {
            "text": answer2.text.strip(),
            "model": answer2.model,
            "route": answer2.route,
            "mode_used": "fast",
            "request_id": client2._last_request_id,
            "attempts": meta2.get("attempts"),
        }

    # --- Falha total: registar + email admin --------------------------------
    await _record_failure(
        db=db, user_id=user_id, project_id=project_id, user_message=user_message,
        reasoning_meta=reasoning_meta, fast_meta=fast_meta,
    )
    await _send_admin_alert(
        user_id=user_id, project_id=project_id, user_message=user_message,
        reasoning_meta=reasoning_meta, fast_meta=fast_meta,
    )
    raise CoachAuroraError(
        "Aurora indisponível em ambos os modos (reasoning + fast).",
        reasoning_meta=reasoning_meta,
        fast_meta=fast_meta,
    )


__all__ = [
    "coach_ask",
    "CoachAuroraError",
    "AuroraNotConfigured",
    "AuroraKeyIdInvalid",
    "SYSTEM_PROMPT",
    "DEFAULT_HISTORY_LIMIT",
]
