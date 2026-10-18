"""Guards de runtime para contas demo (Web Summit) — bloqueia acções sensíveis.

Uso:
    from core.demo_guards import ensure_not_demo, consume_demo_ai_quota, demo_blocked_response

    @router.post("/invoices/send")
    async def send(user=Depends(current_user)):
        ensure_not_demo(user, action="send_invoice")
        ...

Comportamento:
    - `ensure_not_demo` levanta HTTPException(403, {"error": "demo_blocked", "action": ...})
      quando `user.is_demo=True`. UI deve interpretar `error==demo_blocked` e mostrar o toast
      "Modo demo — acção não disponível. Crie conta para enviar.".
    - `consume_demo_ai_quota` incrementa a quota diária e levanta 429 ao exceder.

Quotas e política:
    DEMO_AI_QUOTA_DAILY = 20 chamadas IA / dia / conta demo.
    Reset diário via `websummit_seed_pt.reset_websummit_demo_data_pt` ou a cada chamada
    quando a data mudou (fail-safe interno).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from core.db import db

DEMO_AI_QUOTA_DAILY = 20


def is_demo_user(user: dict | None) -> bool:
    """True se o utilizador tem flag `is_demo`."""
    return bool(user and user.get("is_demo"))


def ensure_not_demo(user: dict | None, action: str = "unspecified") -> None:
    """Levanta 403 se o utilizador é demo. Caller descreve a `action` (campo em response).

    IMPORTANTE: a `action` nunca contém segredos — é um identificador funcional
    (ex: `send_invoice`, `send_sms`, `charge_stripe`, `sign_document`).
    """
    if is_demo_user(user):
        raise HTTPException(
            status_code=403,
            detail={"error": "demo_blocked", "action": action},
        )


async def consume_demo_ai_quota(user: dict) -> None:
    """Incrementa a quota IA do dia para contas demo. Levanta 429 se excede o limite.

    Para contas não-demo é no-op (não aplica quota).
    """
    if not is_demo_user(user):
        return
    today = datetime.now(timezone.utc).isoformat()[:10]
    stored_date = user.get("demo_quota_date")
    stored_count = int(user.get("demo_quota_ai_calls_today") or 0)
    if stored_date != today:
        # Novo dia: reset interno (fail-safe se o background task não correu)
        stored_count = 0
    if stored_count >= DEMO_AI_QUOTA_DAILY:
        raise HTTPException(
            status_code=429,
            detail={"error": "demo_quota_exceeded", "limit": DEMO_AI_QUOTA_DAILY},
        )
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {
            "$set": {"demo_quota_date": today},
            "$inc": {"demo_quota_ai_calls_today": 1},
        },
    )


def demo_blocked_response(action: str) -> dict:
    """Shape de resposta JSON canónica para erros de demo. Usada em testes."""
    return {"error": "demo_blocked", "action": action}
