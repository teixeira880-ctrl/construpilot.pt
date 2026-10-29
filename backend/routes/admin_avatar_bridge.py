"""Ponte do avatar admin (agente LiveKit « construpilot-avatar ») → API do site.

O agente de voz corre no LiveKit Cloud. Para agir no site em nome do admin que abriu a
sessão, chama estas rotas com a chave partilhada AVATAR_AGENT_KEY (cabeçalho
X-Avatar-Agent-Key) e a identidade LiveKit do admin (« admin-<user_id> »).

Regras de segurança (aplicadas aqui, no servidor, e não só no prompt do agente):
  - só contas com role « admin » e ativas;
  - leituras (GET) livres; escritas (POST/PUT/PATCH/DELETE) exigem confirmed=true,
    que o agente só envia depois de o admin confirmar em voz alta;
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
    return {"ok": True, "name": u.get("name"), "email": u.get("email"),
            "site": os.environ.get("PUBLIC_SITE_NAME") or os.environ.get("FRONTEND_URL") or ""}


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
    if method in WRITE and not body.confirmed:
        return {"ok": False, "needs_confirmation": True,
                "message": "Ação que altera dados: descrever ao admin e pedir confirmação explícita antes de repetir com confirmed=true."}
    from server import app  # noqa: PLC0415
    token = make_jwt(admin["user_id"], admin.get("token_version") or 0)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://avatar.internal", timeout=120) as client:
        r = await client.request(method, path, params=body.params or None,
                                 json=body.body if method in WRITE else None,
                                 headers={"Authorization": f"Bearer {token}"})
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
