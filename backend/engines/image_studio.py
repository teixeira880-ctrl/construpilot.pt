"""Génération d'images IA générique (universal EMERGENT_LLM_KEY).

Deux fournisseurs :
  • "gemini"  → Nano Banana (gemini-3.1-flash-image-preview) : texte→image ET édition
                 à partir d'une ou plusieurs images de référence (photomontage, insertion, retouche).
  • "openai"  → GPT Image 1 (gpt-image-1) : texte→image haute qualité.

Toute demande avec image(s) de référence est routée vers Gemini (seul l'édition est supportée).
Les octets générés sont renvoyés à l'appelant qui les persiste (object storage).
"""
from __future__ import annotations

import base64
import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)

GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image-preview"  # Nano Banana (dernière version)
OPENAI_IMAGE_MODEL = "gpt-image-1"


async def generate(*, prompt: str, provider: str = "openai", reference_images: list[bytes] | None = None,
                   number: int = 1, feature: str = "image_studio", session_id: str = "studio") -> list[tuple[bytes, str]]:
    api_key = os.getenv("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(500, "EMERGENT_LLM_KEY em falta")
    refs = reference_images or []
    number = max(1, min(int(number or 1), 4))

    if provider == "openai" and not refs:
        from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
        try:
            ig = OpenAIImageGeneration(api_key=api_key)
            imgs = await ig.generate_images(prompt=prompt, model=OPENAI_IMAGE_MODEL, number_of_images=number)
        except Exception as e:  # noqa: BLE001
            logger.error(f"gpt-image-1 error: {type(e).__name__} {e}")
            raise HTTPException(502, f"Geração falhada: {type(e).__name__}") from e
        out = [(b, "image/png") for b in (imgs or []) if b]
        await _meter(session_id, "openai_direct", feature, OPENAI_IMAGE_MODEL, len(out))
    else:
        from emergentintegrations.llm.chat import ImageContent, UserMessage

        from engines.expenses.metering import MeteredChat
        try:
            chat = (MeteredChat(api_key=api_key, expense_feature=feature, session_id=session_id,
                                system_message="You are a professional architectural and marketing image "
                                               "generation and editing AI. Always return a single high quality image.")
                    .with_model("gemini", GEMINI_IMAGE_MODEL).with_params(modalities=["image", "text"]))
            fc = [ImageContent(image_base64=base64.b64encode(b).decode()) for b in refs] if refs else None
            msg = UserMessage(text=prompt, file_contents=fc) if fc else UserMessage(text=prompt)
            _text, images = await chat.send_message_multimodal_response(msg)
        except Exception as e:  # noqa: BLE001
            logger.error(f"gemini image error: {type(e).__name__} {e}")
            raise HTTPException(502, f"Geração falhada: {type(e).__name__}") from e
        out = [(base64.b64decode(im["data"]), im.get("mime_type", "image/png"))
               for im in (images or []) if im.get("data")]

    if not out:
        raise HTTPException(502, "O modelo não devolveu nenhuma imagem. Reformule o pedido.")
    return out


async def _meter(session_id, provider, feature, model, n):
    if n <= 0:
        return
    try:
        from engines.expenses.store import observe
        await observe(source="image_studio", source_id=session_id, provider=provider,
                      feature=feature, model=model, units={"images": n}, state="completed")
    except Exception:  # noqa: BLE001
        pass
