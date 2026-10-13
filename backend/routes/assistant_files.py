import asyncio
import base64
from typing import Annotated

from core.db import db
from core.security import current_user
from engines.assistant_files import build_document_pdf, owned_artifact
from engines.assistant_media import preview_bytes
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

router = APIRouter(prefix="/assistant", tags=["assistant-files"])


@router.get("/documents/{doc_id}/preview")
async def document_preview(doc_id: str, user: Annotated[dict, Depends(current_user)]):
    from routes.assistant import _allowed_doc
    try:
        doc = await _allowed_doc(doc_id, user["user_id"])
    except PermissionError as exc:
        raise HTTPException(404, "Pièce jointe inaccessible.") from exc
    if doc.get("mime") not in ("application/pdf", "image/png", "image/jpeg", "image/webp"):
        raise HTTPException(415, "Aperçu indisponible pour ce type de fichier.")
    image = await asyncio.to_thread(preview_bytes, base64.b64decode(doc["data_b64"]), doc["mime"])
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/artifacts/{artifact_id}/content")
async def artifact_content(artifact_id: str, user: Annotated[dict, Depends(current_user)]):
    doc = await owned_artifact(artifact_id, user["user_id"])
    return Response(base64.b64decode(doc["data_b64"]), media_type=doc["mime"], headers={
        "Content-Disposition": f'attachment; filename="{doc["filename"]}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/messages/{message_id}/pdf")
async def export_message(message_id: str, user: Annotated[dict, Depends(current_user)]):
    msg = await db.assistant_msgs.find_one({"message_id": message_id, "user_id": user["user_id"], "role": "assistant"}, {"_id": 0})
    if not msg:
        raise HTTPException(404, "Réponse introuvable.")
    text = msg["content"]
    if msg.get("sources"):
        text += "\n\nSources consultées\n" + "\n".join(f'{s.get("title", "Source")} — {s["url"]}' for s in msg["sources"])
    if msg.get("interrupted"):
        text = "RÉPONSE INTERROMPUE — contenu incomplet\n\n" + text
    pdf = await asyncio.to_thread(build_document_pdf, "Solution technique — Assistant BTP", text)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="ConstruPilot-solution-technique.pdf"', "Cache-Control": "private, no-store"})