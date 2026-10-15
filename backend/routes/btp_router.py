"""Route de l'Assistant BTP autonome (cerveau Gemini + métré + recherche web)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from engines.access import require_level
from engines import btp_assistant_router as brain
from routes.auth import current_user

router = APIRouter(prefix="/assistant/autonomous", tags=["assistant-autonomous"],
                   dependencies=[Depends(require_level("particulier_payant"))])


@router.get("/status")
async def status(user=Depends(current_user)) -> dict:
    return {"web_search_enabled": brain.web_search_enabled()}


@router.post("")
async def ask(prompt: str = Form(...), force_json: bool = Form(False),
              steel_ratios: str = Form(""), files: list[UploadFile] = File(default=[]),
              user=Depends(current_user)) -> dict:
    # SEC-X-003 (Y.2): valida cada ficheiro — CAD + DOC + IMAGE, max 25 MB preservado.
    from core.uploads import (
        validate_upload, ALLOWED_CAD, ALLOWED_DOCUMENT, ALLOWED_IMAGE,
    )
    if not (prompt or "").strip() and not files:
        raise HTTPException(400, "Forneça um pedido ou um anexo.")
    attachments = []
    for f in files or []:
        f = await validate_upload(
            f, ALLOWED_CAD + ALLOWED_DOCUMENT + ALLOWED_IMAGE, max_mb=25,
        )
        data = await f.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(400, f'{f.filename} demasiado volumoso (máx. 25 MB).')
        attachments.append({"filename": f.filename, "data": data})
    ratios = None
    if steel_ratios:
        try:
            ratios = {k: float(v) for k, v in json.loads(steel_ratios).items()}
        except Exception:
            ratios = None
    return await brain.route_user_request(prompt, attachments, force_json=force_json,
                                          steel_ratios=ratios)
