"""Génération d'images marketing (créatifs, flyers, hero d'articles) pour l'Agent CEO.

Fournisseur : Google Gemini « Nano Banana » via emergentintegrations (clé universelle
EMERGENT_LLM_KEY). Renvoie les octets bruts de l'image pour stockage dans l'object storage.
GPT Image 1 pourra être ajouté comme fournisseur alternatif ultérieurement.
"""
import base64
import logging
import os

from emergentintegrations.llm.chat import LlmChat, UserMessage

log = logging.getLogger("ceo_media")

NANO_MODEL = "gemini-3.1-flash-image-preview"
_SYSTEM = ("You are a world-class brand designer for ConstruPilot, a French construction (BTP) SaaS. "
           "You craft clean, modern, professional marketing visuals. Palette: warm cream background, "
           "deep green (#0F5257) and copper accent (#E07A5F). No watermark, no stock-photo clichés.")


async def generate_image(prompt: str, *, session_id: str) -> tuple[bytes, str]:
    """Génère une image à partir d'un prompt texte. Renvoie (octets, content_type)."""
    api_key = os.environ["EMERGENT_LLM_KEY"]
    chat = LlmChat(api_key=api_key, session_id=session_id, system_message=_SYSTEM)
    chat.with_model("gemini", NANO_MODEL).with_params(modalities=["image", "text"])
    _text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
    if not images:
        raise RuntimeError("Aucune image générée par le modèle.")
    img = images[0]
    data = base64.b64decode(img["data"])
    ctype = img.get("mime_type") or "image/png"
    return data, ctype
