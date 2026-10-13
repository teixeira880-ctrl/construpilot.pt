"""Chemin Gemini NATIF (SDK officiel google-genai) — facturation Google directe.

Alternative à la clé LLM universelle Emergent : quand l'admin bascule le backend
Gemini sur « native », les appels Gemini (texte + vision) passent par ce module
avec la clé Google de l'entreprise (GOOGLE_GEMINI_API_KEY), modèles gemini-2.5.
La clé n'est JAMAIS exposée au frontend. Dégrade proprement si absente.
"""
from __future__ import annotations

import base64
import logging
import os

logger = logging.getLogger(__name__)

# Modèles natifs stables (facturation Google). gemini-2.5 est déprécié pour les
# nouveaux projets (2026) → on utilise les alias « latest » maintenus par Google.
NATIVE_PRO = os.environ.get("GOOGLE_GEMINI_MODEL_PRO", "gemini-pro-latest")
NATIVE_FLASH = os.environ.get("GOOGLE_GEMINI_MODEL_FLASH", "gemini-flash-latest")


def native_key() -> str | None:
    return os.environ.get("GOOGLE_GEMINI_API_KEY") or None


def native_available() -> bool:
    return bool(native_key())


def map_model(emergent_model: str) -> str:
    """Traduit un modèle Gemina Emergent (gemini-3.x…) vers le modèle natif 2.5 adéquat."""
    m = (emergent_model or "").lower()
    return NATIVE_FLASH if "flash" in m else NATIVE_PRO


_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        from google import genai
        _CLIENT = genai.Client(api_key=native_key())
    return _CLIENT


async def complete(system: str, text: str, images: list[str] | None = None,
                   model: str | None = None, want_json: bool = False) -> str:
    """Appel Gemini natif (async). `images` = PNG/JPEG en base64. Retourne du texte."""
    from google.genai import types
    parts: list = []
    for img in images or []:
        try:
            raw = base64.b64decode(img)
        except Exception:  # noqa: BLE001
            continue
        parts.append(types.Part.from_bytes(data=raw, mime_type="image/png"))
    parts.append(types.Part.from_text(text=text))
    config = types.GenerateContentConfig(
        system_instruction=system or None,
        temperature=0.1,
        response_mime_type="application/json" if want_json else "text/plain",
    )
    resp = await _client().aio.models.generate_content(
        model=model or NATIVE_PRO, contents=parts, config=config)
    return resp.text or ""


async def check_key() -> tuple[bool, str]:
    """Vérifie la validité réelle de la clé (petit appel authentifié). Ne log jamais la clé."""
    if not native_available():
        return False, "missing"
    try:
        from google.genai import types
        resp = await _client().aio.models.generate_content(
            model=NATIVE_FLASH, contents="Responde apenas: OK",
            config=types.GenerateContentConfig(max_output_tokens=200))
        # Pas d'exception = clé valide (les modèles « thinking » peuvent renvoyer un texte vide
        # si le budget de tokens est consommé par le raisonnement).
        _ = resp.text
        return True, "valid"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if any(s in msg for s in ("401", "403", "unauthenticated", "permission", "api key")):
            return False, "invalid_or_not_authorized"
        if "429" in msg or "quota" in msg:
            return False, "valid_but_quota_or_rate_limited"
        return False, "unreachable_or_request_error"
