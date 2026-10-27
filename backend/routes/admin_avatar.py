"""Rotas admin — Assistente de vídeo interno (avatar Synthesia via LiveKit).

Reservado a administradores (dependência `admin_user`, como todo o /admin).
O backend só emite um token LiveKit de curta duração que envia o agente
« construpilot-avatar » para uma sala privada. As chaves Synthesia e OpenAI
ficam no agente (LiveKit Cloud), nunca no site nem no navegador.

Variáveis de ambiente do backend:
  LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET   (projeto LiveKit do agente)
  AVATAR_DEFAULT_LANG   fr | pt | en  (opcional, « pt » por defeito em construpilot.pt)
"""
import json
import logging
import os
import time
import uuid

import jwt

from fastapi import APIRouter, Depends, HTTPException

from core.security import admin_user

logger = logging.getLogger(__name__)

AGENT_NAME = "construpilot-avatar"  # tem de corresponder ao agent_name do worker
LANGS = ("fr", "pt", "en")

router = APIRouter(prefix="/admin/avatar", tags=["admin-avatar"],
                   dependencies=[Depends(admin_user)])


def _livekit_env() -> tuple[str, str, str]:
    url = (os.environ.get("LIVEKIT_URL") or "").strip()
    key = (os.environ.get("LIVEKIT_API_KEY") or "").strip()
    secret = (os.environ.get("LIVEKIT_API_SECRET") or "").strip()
    return url, key, secret


def _default_lang() -> str:
    lang = (os.environ.get("AVATAR_DEFAULT_LANG") or "pt").strip().lower()
    return lang if lang in LANGS else "pt"


def mint_livekit_token(api_key: str, api_secret: str, *, identity: str, name: str,
                       room: str, lang: str, ttl_seconds: int = 900) -> str:
    """Token de acesso LiveKit (formato oficial, HS256) sem dependência livekit-api.

    - acesso a UMA sala privada, 15 min (verificado só à entrada);
    - roomConfig.agents envia o worker « construpilot-avatar » com a língua;
    - syncStreams mantém o áudio e o vídeo do avatar sincronizados.
    """
    now = int(time.time())
    claims = {
        "iss": api_key,
        "sub": identity,
        "name": name,
        "nbf": now,
        "exp": now + ttl_seconds,
        "video": {"roomJoin": True, "room": room, "canPublish": True,
                  "canSubscribe": True, "canPublishData": True},
        "roomConfig": {
            "syncStreams": True,
            "agents": [{"agentName": AGENT_NAME, "metadata": json.dumps({"lang": lang})}],
        },
    }
    return jwt.encode(claims, api_secret, algorithm="HS256")


@router.get("/status")
async def avatar_status() -> dict:
    url, key, secret = _livekit_env()
    return {"configured": bool(url and key and secret), "default_lang": _default_lang(),
            "langs": list(LANGS)}


@router.get("/token")
async def avatar_token(lang: str | None = None, user=Depends(admin_user)) -> dict:
    url, key, secret = _livekit_env()
    if not (url and key and secret):
        raise HTTPException(status_code=503,
                            detail="Assistente de vídeo não configurado: faltam LIVEKIT_URL, "
                                   "LIVEKIT_API_KEY e LIVEKIT_API_SECRET no servidor.")
    lang = (lang or _default_lang()).lower()
    if lang not in LANGS:
        raise HTTPException(status_code=400, detail="Língua desconhecida (fr, pt ou en).")

    room = f"cp-admin-{lang}-{uuid.uuid4().hex[:10]}"
    identity = f"admin-{(user.get('user_id') or uuid.uuid4().hex)[:24]}"
    token = mint_livekit_token(key, secret, identity=identity,
                               name=user.get("name") or user.get("email") or "Admin",
                               room=room, lang=lang)
    logger.info("avatar admin: sessão %s (%s) para %s", room, lang, user.get("email"))
    return {"url": url, "token": token, "room": room, "lang": lang}
