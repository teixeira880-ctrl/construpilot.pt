"""Estúdio de imagens IA (PT-PT) — Nano Banana (edição de fotografia) + GPT Image 1 (texto → imagem).

Geração SÓ a pedido explícito do utilizador (botão «Gerar»), nunca automática. Cada imagem é marcada no próprio ficheiro com a
faixa «Ilustração IA não contratual» e guardada com illustrative=True. Custos medidos pelo motor engines.image_studio
(engines.expenses: GPT Image via observe, Gemini via MeteredChat) com uma referência única por pedido.
As imagens ficam no Object Storage; o Mongo guarda só a referência (storage_path) + metadados. Eliminação lógica.
Porta de routes/image_studio.py do .fr.
"""
import base64
import io
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import image_studio
from engines import object_storage as obj
from engines import storage as public_storage
from engines.access import require_level

router = APIRouter(prefix="/image-studio", tags=["image-studio"], dependencies=[Depends(require_level("pro"))])

PROVIDERS = {"gemini", "openai"}
MAX_REF_MB = 10
KEEP_LAST = 40
MAX_PER_DAY = 30            # teto de custos por conta (imagens geradas em 24 h)
MAX_SHOWCASE = 24
LABEL = "Ilustração IA não contratual"
PROMPT_GUARD = (" Imagem ilustrativa (não contratual), sem texto, sem cotas, sem logótipos nem marcas de água; "
                "não representa uma planta de execução.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GenIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    provider: str = Field(default="openai")
    number: int = Field(default=1, ge=1, le=4)
    reference_image_b64: Optional[str] = None  # data URL ou base64 simples


def label_band(data: bytes) -> bytes:
    """Acrescenta por baixo da imagem a faixa «ConstruPilot | Ilustração IA não contratual» (JPEG)."""
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(io.BytesIO(data)) as original:
        image = original.convert("RGB")
        band = max(44, image.width // 24)
        out = Image.new("RGB", (image.width, image.height + band), "white")
        out.paste(image, (0, 0))
        try:
            font = ImageFont.load_default(size=max(13, image.width // 60))
        except TypeError:  # Pillow antigo
            font = ImageFont.load_default()
        ImageDraw.Draw(out).text((16, image.height + band // 3), f"ConstruPilot | {LABEL}", fill="#17483f", font=font)
        buf = io.BytesIO()
        out.save(buf, "JPEG", quality=92)
        return buf.getvalue()


def _public(doc: dict) -> dict:
    return {"image_id": doc["image_id"], "url": f"/image-studio/images/{doc['image_id']}/conteudo", "provider": doc.get("provider"),
            "prompt": doc.get("prompt"), "created_at": doc.get("created_at"), "illustrative": True, "label": LABEL}


async def _store(user_id: str, data: bytes, prompt: str, provider: str) -> dict:
    image_id = "img_" + secrets.token_hex(6)
    path = f"{obj.APP_NAME}/image-studio/{user_id}/{image_id}.jpg"
    res = await run_in_threadpool(obj.put_object, path, data, "image/jpeg")
    doc = {"image_id": image_id, "user_id": user_id, "prompt": prompt[:1000], "provider": provider, "usage": "studio",
           "mime": "image/jpeg", "size": len(data), "storage_path": (res or {}).get("path", path), "illustrative": True,
           "label": LABEL, "is_deleted": False, "created_at": _now()}
    await db.studio_images.insert_one(dict(doc))
    return doc


@router.post("/generate")
async def generate_image(body: GenIn, user=Depends(current_user)):
    if body.provider not in PROVIDERS:
        raise HTTPException(422, "Fornecedor desconhecido.")
    uid = user["user_id"]
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    if await db.studio_images.count_documents({"user_id": uid, "created_at": {"$gte": since}}) + body.number > MAX_PER_DAY:
        raise HTTPException(429, f"Limite de {MAX_PER_DAY} imagens por 24 h atingido. Tente novamente mais tarde.")
    refs: list = []
    if body.reference_image_b64:
        raw = body.reference_image_b64.split(",", 1)[-1]
        try:
            refs = [base64.b64decode(raw, validate=True)]
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, "Imagem de referência inválida.") from e
        if len(refs[0]) > MAX_REF_MB * 1024 * 1024:
            raise HTTPException(413, f"Imagem de referência demasiado volumosa (máx. {MAX_REF_MB} MB).")
        if not (refs[0][:3] == b"\xff\xd8\xff" or refs[0][:8] == b"\x89PNG\r\n\x1a\n" or refs[0][8:12] == b"WEBP"):
            raise HTTPException(415, "Imagem de referência: JPG, PNG ou WEBP.")
    provider = "gemini" if refs else body.provider
    results = await image_studio.generate(prompt=body.prompt.strip() + PROMPT_GUARD, provider=provider, reference_images=refs,
                                          number=body.number, feature="image_studio",
                                          session_id=f"studio_{uid[:8]}_{secrets.token_hex(6)}")   # referência única: 1 evento de custo por pedido
    stored = []
    for data, _mime in results:
        if len(data) > 12 * 1024 * 1024:
            continue
        labelled = await run_in_threadpool(label_band, data)
        stored.append(_public(await _store(uid, labelled, body.prompt.strip(), provider)))
    old = await (db.studio_images.find({"user_id": uid, "is_deleted": False}, {"_id": 1})
                 .sort("created_at", -1).skip(KEEP_LAST).to_list(100))
    if old:
        await db.studio_images.update_many({"_id": {"$in": [o["_id"] for o in old]}}, {"$set": {"is_deleted": True}})
    return {"ok": True, "provider": provider, "images": stored, "label": LABEL}


@router.get("/images")
async def list_images(user=Depends(current_user)):
    rows = await (db.studio_images.find({"user_id": user["user_id"], "is_deleted": False}, {"_id": 0, "storage_path": 0})
                  .sort("created_at", -1).to_list(60))
    return {"images": [_public(r) for r in rows], "label": LABEL}


async def _owned(image_id: str, uid: str) -> dict:
    rec = await db.studio_images.find_one({"image_id": image_id, "user_id": uid, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Imagem não encontrada.")
    return rec


@router.get("/images/{image_id}/conteudo")
async def get_image(image_id: str, user=Depends(current_user)):
    rec = await _owned(image_id, user["user_id"])
    content, ct = await run_in_threadpool(obj.get_object, rec["storage_path"])
    return Response(content=content, media_type=rec.get("mime") or ct,
                    headers={"Content-Disposition": f'inline; filename="Ilustracao-IA-{image_id}.jpg"', "X-Content-Type-Options": "nosniff"})


@router.delete("/images/{image_id}")
async def delete_image(image_id: str, user=Depends(current_user)):
    await db.studio_images.update_one({"image_id": image_id, "user_id": user["user_id"]}, {"$set": {"is_deleted": True}})
    return {"ok": True}


def _fit(data: bytes, max_w: int = 1000) -> bytes:
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        return buf.getvalue()


class UseIn(BaseModel):
    target: str = Field(pattern="^(quote_header|public_page)$")
    title: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=600)


@router.post("/images/{image_id}/use")
async def use_image(image_id: str, body: UseIn, user=Depends(current_user)):
    rec = await _owned(image_id, user["user_id"])
    data, _ct = await run_in_threadpool(obj.get_object, rec["storage_path"])
    if body.target == "quote_header":
        jpg = await run_in_threadpool(_fit, data, 1000)
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"brand_logo_b64": base64.b64encode(jpg).decode()}})
        return {"ok": True, "target": "quote_header"}
    # public_page → galeria da página pública da empresa (a faixa «não contratual» mantém-se na imagem)
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "showcase_photos": 1}) or {}
    if len(u.get("showcase_photos") or []) >= MAX_SHOWCASE:
        raise HTTPException(409, f"Galeria da página pública cheia ({MAX_SHOWCASE} fotografias no máximo).")
    jpg = await run_in_threadpool(_fit, data, 1600)
    photo_id = "shw_" + secrets.token_hex(6)
    path = f"public/showcase/{user['user_id']}/{photo_id}.jpg"
    try:
        await run_in_threadpool(public_storage.put_object, path, jpg, "image/jpeg")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, "Armazenamento das fotografias indisponível.") from e
    photo = {"photo_id": photo_id, "path": path, "mime": "image/jpeg", "title": (body.title or LABEL)[:120],
             "description": (body.description or LABEL)[:600], "illustrative": True, "created_at": _now()}
    await db.users.update_one({"user_id": user["user_id"]}, {"$push": {"showcase_photos": photo}})
    return {"ok": True, "target": "public_page", "photo_id": photo_id}
