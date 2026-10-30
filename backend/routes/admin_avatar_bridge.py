"""Ponte do avatar admin (agente LiveKit « construpilot-avatar ») → API do site.

O agente de voz corre no LiveKit Cloud. Para agir no site em nome do admin que abriu a
sessão, chama estas rotas com a chave partilhada AVATAR_AGENT_KEY (cabeçalho
X-Avatar-Agent-Key) e a identidade LiveKit do admin (« admin-<user_id> »).

Regras de segurança (aplicadas aqui, no servidor, e não só no prompt do agente):
  - só contas com role « admin » e ativas;
  - leituras (GET) livres; escritas livres (autonomia pedida pelo fundador, 31/10/2026), EXCETO as irreversíveis ou
    que saem para terceiros (DELETE, envio de e-mail/fatura/orçamento, publicação, emissão, preços, ofertas, direitos de
    utilizadores, feature flags, modelo IA, orçamentos de despesas): essas exigem confirmed=true após o « sim » do admin;
  - rotas proibidas: autenticação e palavras-passe, pagamentos e faturação Stripe,
    segredos, eliminação definitiva, a própria ponte e o token do avatar;
  - cada escrita fica registada em avatar_actions (quem, o quê, quando, resultado).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import make_jwt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin-avatar-bridge", tags=["admin-avatar-bridge"])

WRITE = {"POST", "PUT", "PATCH", "DELETE"}
BLOCKED = [re.compile(p, re.I) for p in (
    r"^/api/auth(/|$)", r"password|passe|senha|2fa|two[-_]?fa|otp",
    r"stripe|checkout|payment|pagamento|paiement|billing/(subscribe|cancel|portal|webhook)|webhook",
    r"secret|segredo|api[-_]?key|token",
    r"purge|hard[-_]?delete|permanent|definitiv|trash/empty|corbeille/vider|reciclagem/esvaziar",
    r"^/api/admin-avatar-bridge", r"^/api/admin/avatar",
    r"impersonat|login[-_]?as|sudo",
)]
MAX_OUT = 14000
# Escritas que exigem o « sim » explícito do admin (irreversível, sai para terceiros, ou muda a configuração do negócio).
CONFIRM_PATHS = re.compile(
    r"send|envoi|enviar|e-?mail|mail|bulk|invite|convite|publish|publier|publicar|emit|emett|finali|sign|assin|"
    r"/admin/(prices|regions|plans|users|feature-flags|ai-model|ai-openai-key|campaigns/.+/run)|"
    r"/admin/expenses/(budgets|rates|cap)|deactivat|desativ|d[ée]sactiv|block|bloque|revoke|revog|/(copy|creative)/[^/]+/(approve|publish|send)",
    re.I)


def needs_confirmation(method: str, path: str) -> bool:
    if method == "DELETE":
        return True
    if method == "POST" and re.search(r"/drafts?$", path):
        return False          # um rascunho (CEO, orçamento…) não compromete nada: é revisto antes de qualquer envio
    return method in WRITE and bool(CONFIRM_PATHS.search(path))


def _check_key(key: str | None) -> None:
    expected = (os.environ.get("AVATAR_AGENT_KEY") or "").strip()
    if not expected:
        raise HTTPException(503, "AVATAR_AGENT_KEY não configurada no servidor")
    if not key or not hmac.compare_digest(key.strip(), expected):
        raise HTTPException(401, "Chave do agente inválida")


async def _admin_from_identity(identity: str) -> dict:
    ident = (identity or "").strip()
    if not ident.startswith("admin-") or len(ident) < 10:
        raise HTTPException(403, "Identidade de sessão inválida")
    prefix = ident[len("admin-"):]
    user = await db.users.find_one({"user_id": {"$regex": "^" + re.escape(prefix)}, "role": "admin"},
                                   {"_id": 0, "user_id": 1, "email": 1, "name": 1, "active": 1, "token_version": 1})
    if not user or user.get("active") is False:
        raise HTTPException(403, "Administrador desconhecido ou inativo")
    return user


def _blocked(path: str) -> bool:
    return any(p.search(path) for p in BLOCKED)


class CallIn(BaseModel):
    identity: str = Field(min_length=7, max_length=80)
    method: str = Field(pattern="^(GET|POST|PUT|PATCH|DELETE)$")
    path: str = Field(min_length=5, max_length=400)
    params: dict = Field(default_factory=dict)
    body: dict | list | None = None
    confirmed: bool = False
    summary: str = Field(default="", max_length=400)


@router.get("/whoami")
async def whoami(identity: str, x_avatar_agent_key: str | None = Header(default=None)) -> dict:
    _check_key(x_avatar_agent_key)
    u = await _admin_from_identity(identity)
    from engines.avatar_knowledge import SITE_MAP, WORK_RULES, live_capabilities
    full = await db.users.find_one({"user_id": u["user_id"]}, {"_id": 0, "password_hash": 0, "password": 0}) or u
    return {"ok": True, "name": u.get("name"), "email": u.get("email"),
            "site": os.environ.get("PUBLIC_SITE_NAME") or os.environ.get("FRONTEND_URL") or "",
            "knowledge": SITE_MAP + WORK_RULES + live_capabilities(full)}


async def _internal(admin: dict, method: str, path: str, params: dict | None = None, body=None):
    """Chamada interna à API do site, com os direitos do admin (token de sessão assinado para ele)."""
    from server import app  # noqa: PLC0415
    token = make_jwt(admin["user_id"], admin.get("token_version") or 0)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://avatar.internal", timeout=120) as client:
        return await client.request(method, path, params=params or None, json=body if method in WRITE else None,
                                    headers={"Authorization": f"Bearer {token}"})


OVERVIEW = {"stats": "/api/admin/stats", "revenue_kpis": "/api/admin/revenue/kpis", "expenses": "/api/admin/expenses/overview",
            "leads": "/api/admin/leads/stats", "assistente_btp": "/api/admin/btp-assistant/metrics", "uso_ia": "/api/admin/ai-usage"}


def _compact(v, depth: int = 0):
    """Reduz uma resposta JSON (listas longas cortadas, textos longos truncados) para caber numa mensagem de voz."""
    if isinstance(v, dict):
        return {k: _compact(x, depth + 1) for k, x in list(v.items())[:40] if k not in ("traceback", "data_b64")}
    if isinstance(v, list):
        return [_compact(x, depth + 1) for x in v[: (5 if depth else 8)]] + ([f"… {len(v) - (5 if depth else 8)} autres"] if len(v) > (5 if depth else 8) else [])
    if isinstance(v, str) and len(v) > 200:
        return v[:200] + "…"
    return v


@router.get("/overview")
async def overview(identity: str, x_avatar_agent_key: str | None = Header(default=None)) -> dict:
    """Painel numa só chamada (estatísticas, receitas, despesas IA, leads, métricas do Assistente BTP, uso de IA)."""
    _check_key(x_avatar_agent_key)
    admin = await _admin_from_identity(identity)
    import asyncio  # noqa: PLC0415
    rs = await asyncio.gather(*(_internal(admin, "GET", p) for p in OVERVIEW.values()), return_exceptions=True)
    out = {}
    for key, r in zip(OVERVIEW, rs):
        if isinstance(r, Exception) or r.status_code >= 400:
            out[key] = {"indisponivel": True}
            continue
        try:
            data = r.json()
        except ValueError:
            continue
        if key == "reliability" and isinstance(data, dict):
            data = {"erros_recentes": [{k: e.get(k) for k in ("ref", "tool", "created_at")} for e in (data.get("errors") or [])[:8]],
                    "saude": [{k: h.get(k) for k in ("created_at", "status", "ok")} for h in (data.get("health") or [])[:3]]}
        out[key] = _compact(data)
    text = json.dumps(out, ensure_ascii=False, default=str)
    return {"ok": True, "data": text[:MAX_OUT], "truncated": len(text) > MAX_OUT}


@router.get("/catalog")
async def catalog(identity: str, q: str = "", x_avatar_agent_key: str | None = Header(default=None)) -> dict:
    """Rotas da API (método, caminho, resumo) filtradas por palavras: o agente descobre o que o site sabe fazer."""
    _check_key(x_avatar_agent_key)
    await _admin_from_identity(identity)
    from server import app  # noqa: PLC0415 — app FastAPI carregado pelo uvicorn
    words = [w for w in re.split(r"\s+", q.lower().strip()) if len(w) > 2]
    out = []
    for path, ops in (app.openapi().get("paths") or {}).items():
        if _blocked(path):
            continue
        for meth, op in ops.items():
            text = f"{path} {op.get('summary') or ''} {' '.join(op.get('tags') or [])}".lower()
            if words and not any(w in text for w in words):
                continue
            params = [p.get("name") for p in op.get("parameters") or [] if p.get("in") in ("query", "path")]
            out.append({"method": meth.upper(), "path": path, "summary": (op.get("summary") or "")[:90], "params": params[:8]})
    return {"count": len(out), "routes": out[:60], "truncated": len(out) > 60}


@router.post("/call")
async def call(body: CallIn, x_avatar_agent_key: str | None = Header(default=None)) -> dict:
    _check_key(x_avatar_agent_key)
    admin = await _admin_from_identity(body.identity)
    path = body.path if body.path.startswith("/api/") else "/api/" + body.path.lstrip("/")
    if ".." in path or "://" in path or _blocked(path):
        raise HTTPException(403, "Ação não permitida ao assistente de vídeo (fazer no site, à mão)")
    method = body.method.upper()
    if needs_confirmation(method, path) and not body.confirmed:
        return {"ok": False, "needs_confirmation": True,
                "message": "Ação irreversível ou que chega a terceiros: descrevê-la ao admin numa frase e pedir « sim » antes de repetir com confirmed=true."}
    r = await _internal(admin, method, path, body.params, body.body)
    ctype = r.headers.get("content-type", "")
    if "json" in ctype:
        try:
            data = r.json()
            text = json.dumps(data, ensure_ascii=False, default=str)
        except ValueError:
            text = r.text
    else:
        text = f"[{ctype or 'conteúdo'} — {len(r.content)} bytes: ficheiro disponível no site, não lido pelo assistente]"
    if method in WRITE:
        await db.avatar_actions.insert_one({"user_id": admin["user_id"], "email": admin.get("email"), "method": method, "path": path,
                                            "params": body.params, "summary": body.summary, "status": r.status_code,
                                            "created_at": datetime.now(timezone.utc).isoformat()})
        logger.info("avatar admin %s: %s %s → %s", admin.get("email"), method, path, r.status_code)
    return {"ok": r.status_code < 400, "status": r.status_code, "data": text[:MAX_OUT], "truncated": len(text) > MAX_OUT}
