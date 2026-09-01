"""Rendu IA avant/après du chantier via Runway (Pro/Business uniquement).

L'utilisateur envoie une photo du chantier actuel + un prompt optionnel ;
Runway génère l'image (gen4_image) ou la vidéo (gen4_turbo) « après rénovation ».
La génération est asynchrone : on soumet la tâche, on la sonde en tâche de fond,
puis on télécharge le résultat (URL temporaire Runway) dans le stockage objet permanent.
"""
import io
import os
import base64
import uuid
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from PIL import Image
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response

from core.db import db
from core.security import pro_required, current_user
from engines import storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runway", tags=["runway"])

MAX_BYTES = 12 * 1024 * 1024  # 12 Mo en entrée
MAX_SIDE = 1280               # on réduit l'image d'entrée (data URI léger)
ALLOWED_RATIOS = {"1280:720", "720:1280", "960:960"}
POLL_TIMEOUT_S = 600

_runway = None


def _client():
    global _runway
    if _runway is None:
        from runwayml import AsyncRunwayML
        secret = os.environ.get("RUNWAYML_API_SECRET")
        if not secret:
            raise HTTPException(status_code=503, detail="Rendu IA indisponible (clé Runway manquante)")
        _runway = AsyncRunwayML(api_key=secret)
    return _runway


def _now():
    return datetime.now(timezone.utc).isoformat()


def _downscale_to_jpeg(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB",):
        img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, MAX_SIDE / float(max(w, h)))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue()


def _public_doc(d: dict) -> dict:
    return {
        "render_id": d["render_id"],
        "kind": d["kind"],
        "status": d["status"],
        "prompt": d.get("prompt") or "",
        "ratio": d.get("ratio"),
        "duration": d.get("duration"),
        "error": d.get("error"),
        "content_type": d.get("content_type"),
        "created_at": d.get("created_at"),
        "finished_at": d.get("finished_at"),
        "has_output": bool(d.get("output_path")),
        "has_input": bool(d.get("input_path")),
    }


async def _poll_and_store(render_id: str, task_id: str):
    """Tâche de fond : sonde Runway puis télécharge le résultat dans le stockage."""
    try:
        client = _client()
        deadline = asyncio.get_running_loop().time() + POLL_TIMEOUT_S
        delay = 3.0
        task = None
        while True:
            task = await client.tasks.retrieve(task_id)
            status = getattr(task, "status", None)
            if status == "SUCCEEDED":
                break
            if status in {"FAILED", "CANCELLED"}:
                raise RuntimeError(getattr(task, "failure", None) or "Échec de la génération Runway")
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError("Délai de génération dépassé")
            await asyncio.sleep(delay)
            delay = min(delay * 1.4, 15)

        outputs = getattr(task, "output", None) or []
        if not outputs:
            raise RuntimeError("Aucun résultat renvoyé par Runway")
        url = outputs[0]

        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as hc:
            r = await hc.get(url)
            r.raise_for_status()
            content = r.content
            ctype = r.headers.get("content-type", "").split(";")[0].strip()

        doc = await db.runway_renders.find_one({"render_id": render_id}, {"_id": 0, "kind": 1})
        kind = (doc or {}).get("kind", "image")
        if not ctype:
            ctype = "video/mp4" if kind == "video" else "image/png"
        ext = "mp4" if kind == "video" else ("jpg" if "jpeg" in ctype else "png")
        path = f"{storage.APP_NAME}/runway/{render_id}/output.{ext}"
        await asyncio.to_thread(storage.put_object, path, content, ctype)

        await db.runway_renders.update_one(
            {"render_id": render_id},
            {"$set": {"status": "done", "output_path": path, "content_type": ctype,
                      "finished_at": _now()}})
        logger.info("Rendu Runway terminé: %s", render_id)
    except Exception as e:
        logger.error("Rendu Runway échoué %s: %s", render_id, e)
        await db.runway_renders.update_one(
            {"render_id": render_id},
            {"$set": {"status": "failed", "error": str(e)[:500], "finished_at": _now()}})


@router.post("/generate")
async def generate(file: UploadFile = File(...),
                   prompt: str = Form(""),
                   kind: str = Form("image"),
                   ratio: str = Form("1280:720"),
                   duration: int = Form(5),
                   user=Depends(pro_required)):
    if kind not in {"image", "video"}:
        raise HTTPException(status_code=400, detail="Type invalide (image|video)")
    if ratio not in ALLOWED_RATIOS:
        raise HTTPException(status_code=400, detail="Format invalide")
    duration = 5 if kind == "image" else max(2, min(10, int(duration or 5)))

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image trop lourde (max 12 Mo)")
    try:
        jpeg = await asyncio.to_thread(_downscale_to_jpeg, data)
    except Exception:
        raise HTTPException(status_code=400, detail="Image illisible")

    render_id = f"rw_{uuid.uuid4().hex[:12]}"
    # stocke l'image d'entrée (« avant ») pour l'historique
    input_path = f"{storage.APP_NAME}/runway/{render_id}/input.jpg"
    try:
        await asyncio.to_thread(storage.put_object, input_path, jpeg, "image/jpeg")
    except Exception:
        input_path = None

    data_uri = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    clean_prompt = (prompt or "").strip()[:1000]
    base_prompt = clean_prompt or (
        "Rendu photoréaliste du chantier une fois les travaux terminés : "
        "finitions propres, matériaux réalistes, même angle de prise de vue et même architecture"
    )

    client = _client()
    try:
        if kind == "video":
            created = await client.image_to_video.create(
                model="gen4_turbo",
                prompt_image=data_uri,
                prompt_text=base_prompt,
                ratio=ratio,
                duration=duration,
            )
        else:
            created = await client.text_to_image.create(
                model="gen4_image",
                prompt_text="Utilise @AvantChantier comme référence exacte du chantier existant. " + base_prompt,
                reference_images=[{"uri": data_uri, "tag": "AvantChantier"}],
                ratio=ratio,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Soumission Runway échouée: %s", e)
        raise HTTPException(status_code=502, detail=f"Runway a refusé la demande: {str(e)[:200]}")

    task_id = getattr(created, "id", None)
    doc = {
        "render_id": render_id, "user_id": user["user_id"], "task_id": task_id,
        "kind": kind, "prompt": clean_prompt, "ratio": ratio,
        "duration": duration if kind == "video" else None,
        "status": "processing", "input_path": input_path,
        "output_path": None, "content_type": None, "error": None,
        "created_at": _now(), "finished_at": None,
    }
    await db.runway_renders.insert_one(doc)
    asyncio.create_task(_poll_and_store(render_id, task_id))
    return _public_doc(doc)


@router.get("/renders")
async def list_renders(user=Depends(current_user)) -> dict:
    items = []
    cur = db.runway_renders.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(60)
    async for d in cur:
        items.append(_public_doc(d))
    return {"renders": items}


@router.get("/renders/{render_id}")
async def get_render(render_id: str, user=Depends(current_user)) -> dict:
    d = await db.runway_renders.find_one({"render_id": render_id, "user_id": user["user_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Rendu introuvable")
    return _public_doc(d)


@router.get("/renders/{render_id}/file")
async def get_render_file(render_id: str, which: str = "output", user=Depends(current_user)):
    d = await db.runway_renders.find_one({"render_id": render_id, "user_id": user["user_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Rendu introuvable")
    path = d.get("input_path") if which == "input" else d.get("output_path")
    if not path:
        raise HTTPException(status_code=404, detail="Fichier indisponible")
    try:
        content, ctype = await asyncio.to_thread(storage.get_object, path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Lecture impossible: {e}")
    return Response(content=content,
                    media_type=(d.get("content_type") if which == "output" else "image/jpeg") or ctype,
                    headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/renders/{render_id}")
async def delete_render(render_id: str, user=Depends(current_user)) -> dict:
    res = await db.runway_renders.delete_one({"render_id": render_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Rendu introuvable")
    return {"ok": True}
