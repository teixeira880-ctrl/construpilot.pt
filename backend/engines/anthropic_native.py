"""Chemin Claude NATIF (SDK officiel anthropic) — facturation Anthropic directe.

Alternative à la clé LLM universelle Emergent : quand ANTHROPIC_API_KEY est présente,
les appels Claude (texte + vision) passent par ce module avec la clé Anthropic de
l'entreprise. La clé n'est JAMAIS exposée au frontend. Dégrade proprement si absente.
"""
from __future__ import annotations

import base64
import logging
import os

logger = logging.getLogger(__name__)

# Mapping tier générique → ID modèle API Anthropic direct (surchargeable par env).
MODEL_SONNET = os.environ.get("ANTHROPIC_MODEL_SONNET", "claude-sonnet-5-5")
MODEL_OPUS = os.environ.get("ANTHROPIC_MODEL_OPUS", "claude-opus-5-5")
MODEL_HAIKU = os.environ.get("ANTHROPIC_MODEL_HAIKU", "claude-haiku-5-5")

_CLIENT = None


def native_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def native_available() -> bool:
    return bool(native_key())


def map_model(model: str) -> str:
    """Traduit un nom de modèle Claude (emergent/générique) vers l'ID API direct adéquat."""
    m = (model or "").lower()
    if "opus" in m:
        return MODEL_OPUS
    if "haiku" in m:
        return MODEL_HAIKU
    return MODEL_SONNET


def _client():
    global _CLIENT
    if _CLIENT is None:
        from anthropic import AsyncAnthropic
        _CLIENT = AsyncAnthropic(api_key=native_key())
    return _CLIENT


def _text_of(message) -> str:
    return "".join(b.text for b in (message.content or []) if getattr(b, "type", None) == "text")


async def complete(system: str, text: str, images: list[str] | None = None,
                   model: str | None = None, max_tokens: int = 4096) -> str:
    """Appel Claude direct (async). `images` = PNG/JPEG en base64. Retourne du texte."""
    content: list = []
    for img in images or []:
        try:
            base64.b64decode(img, validate=True)
        except Exception:  # noqa: BLE001
            continue
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": img}})
    content.append({"type": "text", "text": text})
    message = await _client().messages.create(
        model=map_model(model or MODEL_SONNET), max_tokens=max_tokens,
        system=system or "", messages=[{"role": "user", "content": content}])
    return _text_of(message)


async def check_key() -> tuple[bool, str]:
    """Vérifie la validité réelle de la clé (petit appel). Ne log jamais la clé."""
    if not native_available():
        return False, "missing"
    try:
        msg = await _client().messages.create(
            model=MODEL_HAIKU, max_tokens=16, messages=[{"role": "user", "content": "Responde: OK"}])
        return bool(_text_of(msg) is not None), "valid"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "authentication" in msg or "401" in msg or "invalid x-api-key" in msg:
            return False, "invalid_key"
        if "402" in msg or "credit" in msg or "billing" in msg:
            return False, "billing_or_credit"
        if "429" in msg or "rate" in msg or "quota" in msg:
            return False, "rate_or_quota"
        if "not_found" in msg or "404" in msg or "model" in msg:
            return False, "model_not_available"
        return False, "unreachable_or_error"
