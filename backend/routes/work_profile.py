"""Perfil de trabalho, painel « O que precisas de fazer hoje? », ferramentas por ofício,
orçamento guiado e reutilização de orçamentos.

Segurança:
- Tudo é filtrado por `user_id` do utilizador autenticado (o perfil é por membro, não por organização).
- O perfil nunca altera permissões, papel, plano ou faturação.
- O orçamento guiado e a duplicação passam por `routes.documents.create_document`, que volta a validar
  o nível Pro e a permissão `devis`. Nada é enviado ao cliente: só se cria um rascunho.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.permissions import permissions_for
from core.security import current_user
from engines import trade_calcs as C
from engines import work_profile as W

router = APIRouter(tags=["work-profile"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def load_profile(user_id: str) -> dict:
    row = await db.work_profiles.find_one({"user_id": user_id}, {"_id": 0})
    # Conta antiga / sem registo: perfil genérico guiado, onboarding nunca obrigatório.
    return W.normalize({}, row or {})


# --------------------------------------------------------------------------- perfil

@router.get("/me/work-profile/catalog")
async def get_catalog(user=Depends(current_user)) -> dict:
    return W.catalog()


@router.get("/me/work-profile")
async def get_profile(user=Depends(current_user)) -> dict:
    return await load_profile(user["user_id"])


class ProfileIn(BaseModel):
    professions: list[str] | None = None
    other_profession: str | None = Field(None, max_length=120)
    responsibilities: list[str] | None = None
    frequent_tasks: list[str] | None = None
    mode: str | None = None
    language: str | None = None
    onboarding: str | None = None


@router.put("/me/work-profile")
async def put_profile(body: ProfileIn, user=Depends(current_user)) -> dict:
    current = await load_profile(user["user_id"])
    try:
        profile = W.normalize(body.model_dump(exclude_none=True), current)
    except W.ProfileError as e:
        raise HTTPException(422, str(e))
    await db.work_profiles.update_one(
        {"user_id": user["user_id"]},
        {"$set": {**profile, "user_id": user["user_id"], "updated_at": _now()}}, upsert=True)
    return profile


class SuggestIn(BaseModel):
    text: str = Field(..., min_length=2, max_length=1000)


@router.post("/me/work-profile/suggest")
async def suggest_profile(body: SuggestIn, user=Depends(current_user)) -> dict:
    """Sugestão a confirmar pelo utilizador — nunca gravada aqui."""
    keys = W.suggest_from_text(body.text)
    return {"suggestions": [{"key": k, "label": W.PROFESSIONS[k]} for k in keys], "requires_confirmation": True}


# --------------------------------------------------------------------------- painel

async def _continue_items(uid: str) -> list[dict]:
    items = []
    doc = await db.pro_documents.find_one({"user_id": uid, "status": "draft"}, {"_id": 0, "doc_id": 1, "title": 1, "doc_type": 1, "updated_at": 1},
                                          sort=[("updated_at", -1)])
    if doc:
        kind = "orçamento" if doc.get("doc_type") == "quote" else "documento"
        items.append({"kind": "document", "label": f"Continuar o {kind} «{doc.get('title') or 'sem título'}»",
                      "url": f"/devis-editeur/{doc['doc_id']}", "updated_at": doc.get("updated_at")})
    plan = await db.plans_takeoff.find_one({"user_id": uid, "trashed_at": None}, {"_id": 0, "plan_id": 1, "filename": 1, "updated_at": 1},
                                           sort=[("updated_at", -1)])
    if plan:
        items.append({"kind": "plan", "label": f"Continuar a planta «{plan.get('filename') or 'sem nome'}»",
                      "url": f"/plan?open={plan['plan_id']}", "updated_at": plan.get("updated_at")})
    items.sort(key=lambda i: i.get("updated_at") or "", reverse=True)
    return items[:2]


@router.get("/me/work-profile/home")
async def home(user=Depends(current_user)) -> dict:
    from engines.access import compute_level, meets
    profile = await load_profile(user["user_id"])
    level = "business" if user.get("role") == "admin" else await compute_level(user)
    tasks = W.visible_tasks(profile, permissions_for(user), level, meets=meets)
    return {"profile": profile, "tasks": tasks, "continue": await _continue_items(user["user_id"]),
            "show_onboarding": profile["onboarding"] == "pending"}


# --------------------------------------------------------------------------- ferramentas por ofício

@router.post("/trade-tools/{tool}/compute")
async def compute_tool(tool: str, payload: dict, user=Depends(current_user)) -> dict:
    try:
        return C.compute(tool, payload)
    except C.CalcError as e:
        raise HTTPException(422, str(e))


# --------------------------------------------------------------------------- orçamento guiado (pintura)

class GuidedQuoteIn(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=64)  # evita duplicados em reenvios
    description: str = Field("", max_length=2000)
    client_id: str | None = None
    client_name: str = Field("", max_length=160)
    address: str = Field("", max_length=300)
    job: dict


def _preview(job: dict) -> dict:
    try:
        return C.painting_quote_lines(job)
    except C.CalcError as e:
        raise HTTPException(422, str(e))


@router.post("/guided-quote/preview")
async def guided_preview(body: GuidedQuoteIn, user=Depends(current_user)) -> dict:
    out = _preview(body.job)
    from routes.documents import _compute_totals
    out["totals"] = _compute_totals(out["lines"], 0)
    return out


@router.post("/guided-quote")
async def guided_create(body: GuidedQuoteIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    done = await db.guided_quote_requests.find_one({"user_id": uid, "request_id": body.request_id}, {"_id": 0})
    if done:
        return {"doc_id": done["doc_id"], "duplicate": True, "to_confirm": done.get("to_confirm", [])}
    if body.client_id and not await db.clients.find_one({"client_id": body.client_id, "user_id": uid}, {"_id": 0, "client_id": 1}):
        raise HTTPException(404, "Cliente não encontrado")
    out = _preview(body.job)
    from routes.documents import DocIn, DocLine, create_document
    title = "Pintura" + (f" — {body.client_name.strip()}" if body.client_name.strip() else "")
    notes = []
    if body.description.strip():
        notes.append(f"Pedido: {body.description.strip()}")
    if out["to_confirm"]:
        notes.append("Por confirmar antes de enviar: " + "; ".join(out["to_confirm"]))
    doc = await create_document(DocIn(
        doc_type="quote", client_id=body.client_id, title=title[:160],
        lines=[DocLine(**ln) for ln in out["lines"]], notes="\n".join(notes)[:2000],
        project_address=body.address.strip(), status="draft"), user)
    await db.pro_documents.update_one({"doc_id": doc["doc_id"], "user_id": uid},
                                      {"$set": {"source": "guided", "guided_to_confirm": out["to_confirm"]}})
    await db.guided_quote_requests.insert_one({"user_id": uid, "request_id": body.request_id, "doc_id": doc["doc_id"],
                                               "to_confirm": out["to_confirm"], "created_at": _now()})
    return {"doc_id": doc["doc_id"], "duplicate": False, "to_confirm": out["to_confirm"], "totals": doc.get("totals")}


# --------------------------------------------------------------------------- reutilizar um orçamento

REVIEW_ON_REUSE = ["cliente", "medidas e quantidades", "preços", "taxas de IVA", "condições de pagamento", "datas e validade"]


@router.post("/documents/{doc_id}/reuse")
async def reuse_document(doc_id: str, user=Depends(current_user)) -> dict:
    """Duplica a estrutura de um orçamento num NOVO rascunho, sem tocar no original.
    Não copia: cliente, número, estado (assinado/enviado), pagamentos, assinaturas, datas, ligações."""
    from routes.documents import DocIn, DocLine, _get_owned, create_document
    src = await _get_owned(doc_id, user)
    if src.get("doc_type") != "quote":
        raise HTTPException(422, "Só é possível reutilizar orçamentos.")
    allowed = set(DocLine.model_fields)
    lines = []
    for ln in src.get("lines") or []:
        clean = {k: v for k, v in ln.items() if k in allowed and k not in ("line_id", "photos", "vat_confirmed")}
        lines.append(DocLine(**clean))
    doc = await create_document(DocIn(
        doc_type="quote", client_id=None, title=f"Cópia de {src.get('title') or 'orçamento'}"[:160], lines=lines,
        notes=f"Cópia de um orçamento anterior. Rever antes de enviar: {', '.join(REVIEW_ON_REUSE)}.", payment_terms=src.get("payment_terms") or "", deposit_pct=src.get("deposit_pct") or 0,
        validity_days=src.get("validity_days") or 30, status="draft"), user)
    await db.pro_documents.update_one({"doc_id": doc["doc_id"], "user_id": user["user_id"]},
                                      {"$set": {"source": "reuse", "reused_from": doc_id, "review_required": REVIEW_ON_REUSE}})
    return {"doc_id": doc["doc_id"], "review_required": REVIEW_ON_REUSE}


def new_request_id() -> str:
    return secrets.token_hex(8)
