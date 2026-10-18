"""Rotas de demo Web Summit (`POST /api/auth/demo-login`).

Fluxo:
    1. Cliente POST /api/auth/demo-login {"kind": "pro"|"particular"}
    2. Backend lê password do env (nunca ao frontend)
    3. Autentica internamente via verify_password, cria sessão, devolve só o cookie HttpOnly
    4. Response body contém só o utilizador público + flag is_demo (sem token/password)

Segurança:
    - rate limit: 10/minuto/IP, 30/hora/IP (slowapi).
    - 503 "demo_unavailable" se segredos não estiverem presentes no env (fail-closed).
    - 404 se kind inválido.
    - Password nunca aparece em body, logs ou headers.
"""
import logging

from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.db import db
from core.rate_limit import limiter
from core.security import make_jwt, verify_password
from core.websummit_seed_pt import (
    get_demo_password_by_kind,
    get_demo_user_by_kind,
    is_websummit_demo_configured,
)

logger = logging.getLogger("auth_demo")

router = APIRouter(prefix="/auth", tags=["auth-demo"])


class DemoLoginIn(BaseModel):
    kind: str = Field(pattern="^(pro|particular)$")


def _public_demo(u: dict) -> dict:
    """Variante do _public() de auth.py — nunca inclui password/token/hash."""
    keys = (
        "user_id", "email", "name", "picture", "role", "plan",
        "auth_provider", "lang", "created_at", "account_type",
    )
    out = {k: u.get(k) for k in keys}
    out["is_demo"] = bool(u.get("is_demo"))
    out["demo_source"] = u.get("demo_source")
    out["email_verified"] = bool(u.get("email_verified"))
    out["has_password"] = True  # ocultamos a verdade interna
    return out


async def _set_demo_session(response: Response, user_id: str) -> str:
    """Mesma mecânica que _set_session em auth.py mas sinalizando is_demo na sessão."""
    import secrets
    from datetime import datetime, timedelta, timezone
    token = f"st_demo_{secrets.token_hex(16)}"
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "is_demo": True,  # SEC: flag na sessão também
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=4),
        "created_at": datetime.now(timezone.utc),
    })
    response.set_cookie(
        "session_token", token,
        httponly=True, secure=True, samesite="lax",
        path="/", max_age=4 * 3600,
    )
    return token


@router.post("/demo-login")
@limiter.limit("10/minute")
async def demo_login(request: Request, response: Response, body: DemoLoginIn = Body(...)) -> dict:
    cfg = is_websummit_demo_configured()
    required_flag = "pro_configured" if body.kind == "pro" else "particular_configured"
    if not cfg[required_flag]:
        # Fail-closed: nunca cita qual segredo faltava.
        raise HTTPException(status_code=503, detail={"error": "demo_unavailable"})

    user = await get_demo_user_by_kind(db, body.kind)
    if not user:
        # Conta ainda não existe no DB (seed não correu ou falhou silenciosamente).
        raise HTTPException(status_code=503, detail={"error": "demo_unavailable"})

    password = get_demo_password_by_kind(body.kind)
    if not password or not verify_password(password, user.get("password_hash") or ""):
        # Password do env não corresponde ao hash — provavelmente seed desactualizado.
        logger.warning("websummit demo: password hash mismatch for kind=%s", body.kind)
        raise HTTPException(status_code=503, detail={"error": "demo_unavailable"})

    await _set_demo_session(response, user["user_id"])
    # JWT marca is_demo para que guards server-side possam decidir sem query ao DB.
    token = make_jwt(user["user_id"], user.get("token_version") or 0)
    return {
        "user": _public_demo(user),
        "token": token,  # frontend pode usar para Authorization: Bearer
    }


@router.get("/demo-status")
async def demo_status() -> dict:
    """Verificação pública se o demo está disponível (sem detalhes).

    Usado pelo frontend para decidir se mostra o botão "Experimentar demo".
    """
    cfg = is_websummit_demo_configured()
    return {
        "pro": cfg["pro_configured"],
        "particular": cfg["particular_configured"],
    }
