"""Photos du désordre jointes au solveur : stockage objet + pré-analyse vision."""
import asyncio
import base64
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from core.db import db
from engines import storage
from engines.assistant_media import normalize_attachment

logger = logging.getLogger(__name__)

MAX_PHOTO_MB = 8
MAX_PHOTOS = 3

VISION_SYSTEM = (
    "És especialista em patologia da construção (Portugal). São-te mostradas 1 a 3 fotografias de uma patologia descrita pelo utilizador. Descreve apenas o que é visível: tipo de patologia (fissura, humidade, descolamento…), localização no elemento, orientação e abertura estimada das fissuras (mm se legível), materiais aparentes, vestígios anexos (eflorescências, bolores, ferrugem), indícios sobre a causa (assentamento, dilatação, infiltração…). Assinala o que a fotografia NÃO permite concluir. Responde em português europeu, 8 a 15 linhas, sem título, sem markdown."
)


async def store_photo(user_id: str, data: bytes) -> dict:
    if len(data) > MAX_PHOTO_MB * 1024 * 1024:
        raise HTTPException(413, f'Fotografia demasiado grande (> {MAX_PHOTO_MB} MB)')
    data, mime = await asyncio.to_thread(normalize_attachment, data)
    if mime == "application/pdf":
        raise HTTPException(415, "Anexe uma fotografia JPG, PNG ou WEBP")
    photo_id = f"sph_{uuid.uuid4().hex[:12]}"
    path = f"private/btp-solver/{user_id}/{photo_id}.jpg"
    try:
        await asyncio.to_thread(storage.put_object, path, data, mime)
    except Exception as exc:  # noqa: BLE001 — stockage objet indisponible
        logger.warning("btp_solver photo storage failed: %s", exc)
        raise HTTPException(503, "Armazenamento das fotografias momentaneamente indisponível") from None
    doc = {"photo_id": photo_id, "user_id": user_id, "path": path, "mime": mime, "size": len(data),
           "created_at": datetime.now(timezone.utc)}
    await db.btp_solver_photos.insert_one(dict(doc))
    return {"photo_id": photo_id, "mime": mime, "size": len(data)}


async def load_photos(user_id: str, photo_ids: list[str]) -> list[dict]:
    """Photos du compte, dans l'ordre demandé, avec leurs octets."""
    ids = list(dict.fromkeys(photo_ids or []))[:MAX_PHOTOS]
    if not ids:
        return []
    docs = {d["photo_id"]: d async for d in db.btp_solver_photos.find({"photo_id": {"$in": ids}, "user_id": user_id}, {"_id": 0})}
    if len(docs) != len(ids):
        raise HTTPException(404, "Fotografia não encontrada")
    out = []
    for pid in ids:
        d = docs[pid]
        data, _ = await asyncio.to_thread(storage.get_object, d["path"])
        out.append({**d, "data": data})
    return out


async def photo_bytes(user_id: str, photo_id: str) -> tuple[bytes, str]:
    d = await db.btp_solver_photos.find_one({"photo_id": photo_id, "user_id": user_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Fotografia não encontrada")
    data, _ = await asyncio.to_thread(storage.get_object, d["path"])
    return data, d.get("mime") or "image/jpeg"


async def analyze_photos(photos: list[dict], description: str) -> str | None:
    """Pré-analyse vision (Claude → GPT-5.5) ; None si aucun fournisseur ne répond."""
    if not photos or not os.environ.get("EMERGENT_LLM_KEY"):
        return None
    from emergentintegrations.llm.chat import ImageContent, UserMessage

    from engines.expenses.metering import MeteredChat
    files = [ImageContent(image_base64=base64.b64encode(p["data"]).decode("ascii")) for p in photos]
    for provider, model in (("anthropic", "claude-sonnet-4-6"), ("openai", "gpt-5.5")):
        try:
            chat = MeteredChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"btp-solver-photos-{uuid.uuid4().hex[:8]}",
                               expense_feature="btp_solver_photos", system_message=VISION_SYSTEM).with_model(provider, model)
            raw = await chat.send_message(UserMessage(text=f'Descrição do utilizador: {description[:1500]}', file_contents=files))
            text = (raw if isinstance(raw, str) else str(raw)).strip()
            if text:
                return text[:4000]
        except Exception as exc:  # noqa: BLE001 — bascule silencieuse
            logger.warning("btp_solver photo vision %s/%s failed: %s", provider, model, exc)
    return None
