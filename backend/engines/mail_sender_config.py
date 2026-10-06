"""Fonte única de verdade para remetentes Resend (ConstruPilot).

Guard de produção:
  - Bloqueia envios com domínios proibidos (`.local`, `localhost`, `example.com`).
  - Valida que o remetente é um endereço de email bem formado.
  - Em `ENV=production` levanta `ValueError` ANTES de chamar a API Resend.
  - Em dev / teste apenas regista erro em log (não bloqueia para facilitar
    experimentação).

Default universal: `info@construpilot.pt` com nome amigável `ConstruPilot`.
"""
from __future__ import annotations

import logging
import os
import re
from enum import Enum

logger = logging.getLogger("mail.sender")


class Market(str, Enum):
    PT = "pt"
    FR = "fr"
    OTHER = "other"


# Domínios proibidos — qualquer sufixo bate (ex: `foo.local`, `bar.localhost`).
FORBIDDEN_DOMAIN_SUFFIXES: tuple[str, ...] = (
    ".local",
    ".localhost",
    "localhost",
    ".example.com",
    "example.com",
    ".test",
    ".invalid",
)

# Default seguro — nunca `.local`.
_DEFAULT_PT_FROM = "info@construpilot.pt"
_DEFAULT_PT_NAME = "ConstruPilot"

# Email regex (RFC 5322 "liberal", suficiente para validação sanitária).
_EMAIL_RE = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


def _env_market(market: Market) -> dict:
    """Lê overrides por mercado a partir do ambiente. Nunca devolve `.local`."""
    if market == Market.FR:
        return {
            "name": os.getenv("SENDER_FR_NAME", "ConstruPilot"),
            "from": os.getenv("SENDER_FR_FROM", "contact@construpilot.fr"),
            "reply_to": os.getenv("SENDER_FR_REPLY", "contact@construpilot.fr"),
        }
    # PT default + OTHER
    env_from = os.getenv("SENDER_PT_FROM") or os.getenv("SENDER_EMAIL") or _DEFAULT_PT_FROM
    env_reply = os.getenv("SENDER_PT_REPLY") or env_from
    return {
        "name": os.getenv("SENDER_PT_NAME", _DEFAULT_PT_NAME),
        "from": env_from,
        "reply_to": env_reply,
    }


def is_production() -> bool:
    env = (os.getenv("ENV") or os.getenv("APP_ENV") or "development").strip().lower()
    return env in {"production", "prod"}


class ForbiddenSenderError(ValueError):
    """Remetente usa um domínio proibido para envios transacionais."""


def assert_valid_sender(address: str) -> None:
    """Levanta `ForbiddenSenderError` em produção se o remetente for inválido.

    Em dev regista erro mas deixa passar (para desbloquear tooling local).
    """
    addr = (address or "").strip().lower()

    reason: str | None = None
    if not addr:
        reason = "endereço vazio"
    elif not _EMAIL_RE.match(addr):
        reason = f"formato inválido: {address!r}"
    else:
        domain = addr.split("@", 1)[1] if "@" in addr else ""
        for forbidden in FORBIDDEN_DOMAIN_SUFFIXES:
            # bate como sufixo OU como match exato
            if domain == forbidden.lstrip(".") or domain.endswith(forbidden):
                reason = f"domínio proibido: {domain!r}"
                break

    if reason is None:
        return

    if is_production():
        logger.error("[PROD BLOCK] Remetente bloqueado — %s (addr=%r)", reason, address)
        raise ForbiddenSenderError(
            f"Remetente inválido para produção ({reason}). "
            f"Configure SENDER_PT_FROM (ex: info@construpilot.pt)."
        )
    logger.warning(
        "[DEV] Remetente %r seria bloqueado em produção — %s", address, reason,
    )


def get_sender(market: Market = Market.PT, override: dict | None = None) -> dict:
    """Devolve `{name, from, reply_to}` validado para o mercado dado.

    Params
    ------
    market : Market
        Mercado alvo (PT por default).
    override : dict | None
        Pode ter chaves `name`, `from`, `reply_to`. Em produção, o `from`
        também é validado contra `FORBIDDEN_DOMAIN_SUFFIXES`.
    """
    base = _env_market(market)
    if override:
        base = {**base, **{k: v for k, v in override.items() if v}}

    # Validação final (bloqueia em prod).
    assert_valid_sender(base["from"])

    # Reply-to opcional também validado (silencioso em dev se vazio).
    if base.get("reply_to"):
        try:
            assert_valid_sender(base["reply_to"])
        except ForbiddenSenderError:
            if is_production():
                raise
            # cai de volta para o from em dev
            base["reply_to"] = base["from"]

    return base


def format_from_header(sender: dict) -> str:
    """Devolve `"ConstruPilot <info@construpilot.pt>"` ou só o email."""
    name = (sender.get("name") or "").strip().replace('"', "")
    addr = sender["from"]
    if name:
        return f"{name} <{addr}>"
    return addr


__all__ = [
    "Market",
    "ForbiddenSenderError",
    "FORBIDDEN_DOMAIN_SUFFIXES",
    "assert_valid_sender",
    "get_sender",
    "format_from_header",
    "is_production",
]
