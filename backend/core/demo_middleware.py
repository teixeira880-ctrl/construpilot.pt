"""Middleware global para bloquear acções sensíveis em sessões demo.

Em vez de instrumentar centenas de rotas individualmente, intercepta cada request
no entry-point e bloqueia se:
    - sessão (cookie) está marcada `is_demo=True` OU
    - utilizador na BD tem `is_demo=True`

e o path corresponde a um padrão sensível (envio de email, SMS, pagamento,
assinatura, facturação, export de dados externos).

Resposta canónica: 403 com body `{"error":"demo_blocked","action":"<key>"}`.
"""
from __future__ import annotations

import re
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.db import db

# (regex, action_key) — ordem importa (específicos primeiro).
_BLOCKED_PATTERNS = [
    # Pagamentos Stripe
    (re.compile(r"^/api/.*/(payments|charge|checkout|subscribe)(/.*)?$"), "payment"),
    (re.compile(r"^/api/stripe/.*"), "payment"),
    (re.compile(r"^/api/billing/stripe/.*"), "payment"),
    # Facturação e envio de documentos
    (re.compile(r"^/api/documents/[^/]+/send$"), "send_document"),
    (re.compile(r"^/api/documents/[^/]+/email-preview$"), "send_document"),
    (re.compile(r"^/api/invoices?/.*/send"), "send_invoice"),
    (re.compile(r"^/api/.*/(invoice|facture)/send"), "send_invoice"),
    (re.compile(r"^/api/.*/cius-pt.*"), "einvoicing"),
    (re.compile(r"^/api/.*/ubl.*"), "einvoicing"),
    # Assinatura electrónica
    (re.compile(r"^/api/.*/sign($|/.*)"), "sign"),
    (re.compile(r"^/api/.*/signature-link$"), "sign"),
    # SMS
    (re.compile(r"^/api/.*/sms$"), "send_sms"),
    (re.compile(r"^/api/.*/share/sms$"), "send_sms"),
    # Envio de emails a terceiros (proposta, orçamento, relatório, plan)
    (re.compile(r"^/api/.*/send-quote$"), "send_email"),
    (re.compile(r"^/api/.*/send-report$"), "send_email"),
    (re.compile(r"^/api/.*/pdf/email$"), "send_email"),
    (re.compile(r"^/api/.*/purchase-order/send$"), "send_email"),
    (re.compile(r"^/api/.*/ecarts-pdf/send$"), "send_email"),
    (re.compile(r"^/api/.*/orders/[^/]+/email$"), "send_email"),
    (re.compile(r"^/api/.*/cotes/send$"), "send_email"),
    (re.compile(r"^/api/.*/pc-study/send$"), "send_email"),
    (re.compile(r"^/api/ceo/email/[^/]+/send$"), "send_email"),
    (re.compile(r"^/api/ceo/email/[^/]+/test$"), "send_email"),
    (re.compile(r"^/api/newsletter/.*"), "send_email"),
    (re.compile(r"^/api/.*/conversations/[^/]+/state/email$"), "send_email"),
    # Edição de perfil para contas demo (email/password imutáveis)
    (re.compile(r"^/api/auth/profile$"), "edit_profile"),
    (re.compile(r"^/api/auth/change-password$"), "change_password"),
    (re.compile(r"^/api/auth/profile-photo$"), "edit_profile"),
]


def _match_action(path: str, method: str) -> str | None:
    # Só aplicamos a métodos de escrita. GET fica livre.
    if method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    for pat, action in _BLOCKED_PATTERNS:
        if pat.match(path):
            return action
    return None


async def _is_demo_request(request: Request) -> bool:
    """Determina se o request está autenticado por uma sessão/user demo.

    Precedência:
      1. Cookie `session_token` → se linha em `user_sessions` tem `is_demo=True` → True.
      2. Senão lê o user_id e verifica `users.is_demo`.
    """
    token = request.cookies.get("session_token") or request.cookies.get("auth_token")
    if token:
        sess = await db.user_sessions.find_one(
            {"session_token": token},
            {"is_demo": 1, "user_id": 1},
        )
        if sess:
            if sess.get("is_demo"):
                return True
            uid = sess.get("user_id")
            if uid:
                u = await db.users.find_one({"user_id": uid}, {"is_demo": 1})
                if u and u.get("is_demo"):
                    return True
    # Authorization bearer: deixar passar sem check adicional (JWT não transporta
    # is_demo neste codebase). Guards de endpoint individual podem complementar.
    return False


class DemoActionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        action = _match_action(request.url.path, request.method)
        if action:
            try:
                is_demo = await _is_demo_request(request)
            except Exception:  # noqa: BLE001
                is_demo = False
            if is_demo:
                return JSONResponse(
                    status_code=403,
                    content={"error": "demo_blocked", "action": action},
                )
        return await call_next(request)
