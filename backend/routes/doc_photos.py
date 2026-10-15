"""Photos attachées aux lignes de devis (jusqu'à 3 par ligne).

Stockées via Emergent Object Storage, normalisées en JPEG. Servies au pro via
un endpoint authentifié (l'éditeur les affiche par <img>, même origine → cookie).
Le PDF récupère les octets directement depuis le storage via `storage_path`.
"""
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from PIL import Image as PILImage

from core.db import db
from core.security import current_user
from engines import storage

router = APIRouter(prefix="/document-photos", tags=["document-photos"])

MAX_BYTES = 12 * 1024 * 1024  # 12 Mo
MAX_DIM = 1400


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("")
async def upload_document_photo(file: UploadFile = File(...), user=Depends(current_user)) -> dict:
    # SEC-X-003 (Y.2): whitelist IMAGE + 12 MB preservado.
    from core.uploads import validate_upload, ALLOWED_IMAGE
    file = await validate_upload(file, ALLOWED_IMAGE, max_mb=12)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Ficheiro vazio")
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Ficheiro demasiado pesado (máx. 12 MB)")
    try:
        img = PILImage.open(io.BytesIO(raw))
        img = img.convert("RGB")
        img.thumbnail((MAX_DIM, MAX_DIM))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=82, optimize=True)
        data = out.getvalue()
    except Exception:
        raise HTTPException(status_code=400, detail="Imagem inválida")

    photo_id = f"dph_{uuid.uuid4().hex[:12]}"
    path = f"{storage.APP_NAME}/pro/{user['user_id']}/doc_photos/{uuid.uuid4().hex}.jpg"
    try:
        result = storage.put_object(path, data, "image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'Carregamento impossível: {e}')

    rec = {
        "photo_id": photo_id,
        "user_id": user["user_id"],
        "storage_path": result.get("path") or path,
        "content_type": "image/jpeg",
        "size": len(data),
        "created_at": _now(),
    }
    await db.doc_photos.insert_one(dict(rec))
    return {
        "photo_id": photo_id,
        "storage_path": rec["storage_path"],
        "url": f"/api/document-photos/{photo_id}/raw",
        "size": rec["size"],
    }


@router.get("/{photo_id}/raw")
async def get_document_photo(photo_id: str, user=Depends(current_user)):
    rec = await db.doc_photos.find_one({"photo_id": photo_id, "user_id": user["user_id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Fotografia não encontrada")
    try:
        data, ctype = storage.get_object(rec["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'Leitura impossível: {e}')
    return Response(content=data,
                    media_type=rec.get("content_type") or ctype,
                    headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/{photo_id}")
async def delete_document_photo(photo_id: str, user=Depends(current_user)) -> dict:
    rec = await db.doc_photos.find_one({"photo_id": photo_id, "user_id": user["user_id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Fotografia não encontrada")
    await db.doc_photos.delete_one({"photo_id": photo_id, "user_id": user["user_id"]})
    return {"ok": True}
