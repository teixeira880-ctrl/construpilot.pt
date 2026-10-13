"""Routes admin — Apprentissage IA (exemples de référence validés, injectés en few-shot)."""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.db import db
from core.security import admin_user
from engines import learning

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/learning", tags=["admin-learning"],
                   dependencies=[Depends(admin_user)])


class ExampleBody(BaseModel):
    scope: str = Field(default="global")
    title: str = Field(default="", max_length=120)
    context: str = Field(default="", max_length=4000)
    content: str = Field(min_length=1, max_length=8000)
    approved: bool = True


class ExamplePatch(BaseModel):
    scope: str | None = None
    title: str | None = None
    context: str | None = None
    content: str | None = None
    approved: bool | None = None


@router.get("")
async def list_examples() -> dict:
    return {"scopes": learning.SCOPES, "examples": await learning.list_examples()}


@router.get("/preview")
async def preview(scope: str = "devis") -> dict:
    """Aperçu du bloc d'exemples injecté dans le prompt pour une portée donnée."""
    if scope not in learning.SCOPES:
        raise HTTPException(400, "Portée inconnue")
    text = await learning.learning_block_for_scope(scope)
    return {"scope": scope, "preview": text, "empty": not text.strip()}


class BulkItem(BaseModel):
    title: str = ""
    context: str = ""
    content: str = ""


class BulkBody(BaseModel):
    scope: str = "global"
    approved: bool = True
    items: list[BulkItem] = Field(default_factory=list)


@router.post("/bulk")
async def create_bulk(body: BulkBody, admin=Depends(admin_user)) -> dict:
    who = (admin or {}).get("email") or (admin or {}).get("user_id")
    items = [{**it.model_dump(), "approved": body.approved} for it in body.items]
    created = await learning.create_many(items, body.scope, who)
    if not created:
        raise HTTPException(400, "Aucun exemple valide (contenu vide).")
    return {"ok": True, "created": len(created), "examples": created}


@router.post("/import-file")
async def import_file(file: UploadFile = File(...), scope: str = "devis",
                      admin=Depends(admin_user)) -> dict:
    """Importe un fichier (PDF/Excel/CSV/Word/TXT) → un exemple de référence (texte extrait)."""
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop volumineux (max 15 Mo).")
    try:
        text = learning.extract_file_text(raw, file.filename or "fichier")
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not (text or "").strip():
        raise HTTPException(400, "Aucun texte exploitable dans le fichier.")
    who = (admin or {}).get("email") or (admin or {}).get("user_id")
    ex = await learning.create_example(
        {"scope": scope, "title": (file.filename or "Import")[:120],
         "context": "", "content": text, "approved": True}, who)
    return {"ok": True, "example": ex, "chars": len(text)}


@router.get("/example-doc-ids")
async def example_doc_ids() -> dict:
    return {"doc_ids": await learning.example_doc_ids()}


@router.post("/from-document/{doc_id}")
async def from_document(doc_id: str, admin=Depends(admin_user)) -> dict:
    doc = await db.pro_documents.find_one(
        {"doc_id": doc_id, "user_id": admin["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Devis introuvable")
    who = (admin or {}).get("email") or (admin or {}).get("user_id")
    ex, already = await learning.create_from_document(doc, who)
    if ex is None:
        raise HTTPException(400, "Ce devis ne contient aucune ligne exploitable.")
    return {"ok": True, "already": already, "example": ex}


@router.post("")
async def create_example(body: ExampleBody, admin=Depends(admin_user)) -> dict:
    who = (admin or {}).get("email") or (admin or {}).get("user_id")
    return {"ok": True, "example": await learning.create_example(body.model_dump(), who)}


@router.put("/{example_id}")
async def update_example(example_id: str, body: ExamplePatch) -> dict:
    updated = await learning.update_example(example_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(404, "Exemple introuvable")
    return {"ok": True, "example": updated}


@router.delete("/{example_id}")
async def delete_example(example_id: str) -> dict:
    if not await learning.delete_example(example_id):
        raise HTTPException(404, "Exemple introuvable")
    return {"ok": True}
