"""Fournisseurs propres à chaque entreprise (Business Pro)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/pro/suppliers", tags=["suppliers"])


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    agency: str | None = Field(default=None, max_length=120)
    client_number: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    categories: list[str] = Field(default_factory=list)
    delivery_address: str | None = Field(default=None, max_length=300)
    api_endpoint: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=1000)
    price_list: list[dict] = Field(default_factory=list)


def _now():
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def list_suppliers(user=Depends(current_user)) -> dict:
    cur = db.suppliers.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return {"items": await cur.to_list(500)}


@router.post("")
async def create_supplier(body: SupplierIn, user=Depends(current_user)) -> dict:
    doc = {"supplier_id": "sup_" + uuid.uuid4().hex[:12], "user_id": user["user_id"],
           **body.model_dump(), "created_at": _now()}
    await db.suppliers.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{supplier_id}")
async def update_supplier(supplier_id: str, body: SupplierIn, user=Depends(current_user)) -> dict:
    r = await db.suppliers.update_one(
        {"supplier_id": supplier_id, "user_id": user["user_id"]},
        {"$set": {**body.model_dump(), "updated_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, "Fournisseur introuvable")
    return {"ok": True}


@router.delete("/{supplier_id}")
async def delete_supplier(supplier_id: str, user=Depends(current_user)) -> dict:
    r = await db.suppliers.delete_one({"supplier_id": supplier_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Fournisseur introuvable")
    return {"deleted": 1}
