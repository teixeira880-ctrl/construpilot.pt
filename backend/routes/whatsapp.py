"""Contactos WhatsApp da empresa: o gerente e os colaboradores escolhidos aparecem num botão WhatsApp
na página pública da empresa, nos orçamentos enviados, no portal da obra e na app dos operários.

Só o titular da conta (ou o proprietário/administrador da empresa) configura. Nada é mostrado sem ativação
explícita, contacto a contacto e sítio a sítio.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import whatsapp as wa

router = APIRouter(prefix="/company/whatsapp", tags=["whatsapp"])


class ContactoIn(BaseModel):
    id: Optional[str] = Field(None, max_length=40)
    nome: str = Field(..., max_length=80)
    funcao: str = Field("", max_length=60)
    telefone: str = Field(..., max_length=30)
    user_id: Optional[str] = Field(None, max_length=60)
    locais: dict[str, bool] = Field(default_factory=dict)


class ConfigIn(BaseModel):
    ativo: bool = True
    contactos: list[ContactoIn] = Field(default_factory=list, max_length=wa.MAX_CONTACTOS)


async def conta_titular(user_id: str) -> str:
    """A configuração pertence à conta da empresa: o próprio utilizador ou o proprietário da sua organização."""
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "organization_id": 1, "role": 1, "employer_id": 1}) or {}
    if u.get("role") == "worker" and u.get("employer_id"):
        return u["employer_id"]
    if u.get("organization_id"):
        dono = await db.users.find_one({"organization_id": u["organization_id"], "org_role": "owner"}, {"_id": 0, "user_id": 1})
        if dono:
            return dono["user_id"]
    return user_id


async def _config(owner_id: str) -> Optional[dict]:
    return await db.whatsapp_contactos.find_one({"owner_id": owner_id}, {"_id": 0})


async def contactos_para(user_id: Optional[str], local: str, empresa: str = "", ref: str = "") -> list[dict]:
    """Contactos públicos de uma empresa para um sítio (nunca falha: devolve [] em caso de dúvida)."""
    if not user_id:
        return []
    try:
        return wa.publicos(await _config(await conta_titular(user_id)), local, empresa, ref)
    except Exception:  # noqa: BLE001
        return []


async def _gestor(user: dict) -> str:
    if user.get("role") == "worker":
        raise HTTPException(403, "Reservado ao gerente da empresa.")
    if user.get("organization_id") and user.get("org_role") not in ("owner", "admin"):
        raise HTTPException(403, "Reservado ao proprietário ou a um administrador.")
    return await conta_titular(user["user_id"])


@router.get("")
async def ver(user=Depends(current_user)) -> dict:
    owner = await _gestor(user)
    cfg = await _config(owner) or {"ativo": False, "contactos": []}
    sug = []
    dono = await db.users.find_one({"user_id": owner}, {"_id": 0, "user_id": 1, "name": 1, "phone": 1, "brand_phone": 1, "organization_id": 1}) or {}
    if dono:
        sug.append({"user_id": dono["user_id"], "nome": dono.get("name") or "", "funcao": wa.WA_TXT["gerente"],
                    "telefone": dono.get("brand_phone") or dono.get("phone") or ""})
    q = [{"employer_id": owner, "role": "worker"}]
    if dono.get("organization_id"):
        q.append({"organization_id": dono["organization_id"]})
    for m in await db.users.find({"$or": q, "user_id": {"$ne": owner}}, {"_id": 0, "user_id": 1, "name": 1, "phone": 1, "poste": 1, "org_role": 1}).to_list(300):
        sug.append({"user_id": m["user_id"], "nome": m.get("name") or "", "funcao": m.get("poste") or wa.WA_TXT["colaborador"],
                    "telefone": m.get("phone") or ""})
    return {"ativo": bool(cfg.get("ativo")), "contactos": cfg.get("contactos") or [], "sugestoes": sug,
            "locais": list(wa.LOCAIS), "indicativo": wa.INDICATIVO, "max": wa.MAX_CONTACTOS}


@router.put("")
async def guardar(body: ConfigIn, user=Depends(current_user)) -> dict:
    owner = await _gestor(user)
    erro, contactos = wa.validar([c.model_dump() for c in body.contactos])
    if erro:
        raise HTTPException(422, erro)
    await db.whatsapp_contactos.update_one(
        {"owner_id": owner},
        {"$set": {"owner_id": owner, "ativo": body.ativo, "contactos": contactos,
                  "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["user_id"]}}, upsert=True)
    return await ver(user)


@router.get("/equipa")
async def equipa(ref: str = "", user=Depends(current_user)) -> dict:
    """Para a app dos operários: contactos da empresa marcados para «operarios»."""
    owner = await conta_titular(user["user_id"])
    return {"itens": wa.publicos(await _config(owner), "operarios", "", ref[:40])}
