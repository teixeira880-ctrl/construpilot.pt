"""User-private Radar contacts and explicitly confirmed public company candidates."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from core.db import db
from core.security import current_user
from engines.company_registry import search_companies
from engines.radar_filters import ClientType
from routes.radar import _get_permits, get_opportunity

router = APIRouter(prefix="/radar/opportunities", tags=["radar-contacts"])
BUSINESS_TYPES = {"ENTREPRISE", "PROMOTEUR", "SCI", "BAILLEUR", "COLLECTIVITE"}


class ContactFields(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    nom: str = Field(default="", max_length=160)
    societe: str = Field(default="", max_length=160)
    adresse1: str = Field(default="", max_length=200)
    adresse2: str = Field(default="", max_length=160)
    cp: str = Field(default="", max_length=12)
    ville: str = Field(default="", max_length=100)
    siren: str = Field(default="", pattern=r"^(\d{9})?$")
    siret: str = Field(default="", pattern=r"^(\d{14})?$")
    email: str = Field(default="", max_length=160)
    telephone: str = Field(default="", max_length=40)


class ManualContactIn(BaseModel):
    contact: ContactFields
    source_note: str = Field(min_length=3, max_length=240)
    source_url: HttpUrl | None = None
    confirmed: Literal[True]


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=120)


class Candidate(ContactFields):
    adresse_complete: str
    source_url: str


class SearchOut(BaseModel):
    search_id: str
    candidates: list[Candidate]
    expires_at: str


class ConfirmIn(BaseModel):
    search_id: str
    siren: str = Field(pattern=r"^\d{9}$")
    confirmed: Literal[True]


class ContactOpportunityOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    promoteur: dict | None = None
    contact_provenance: dict | None = None
    coordonnees_status: str


class QualificationIn(BaseModel):
    category: ClientType
    source_note: str = Field(min_length=3, max_length=240)
    confirmed: Literal[True]


@router.put("/{opp_id}/qualification", response_model=ContactOpportunityOut)
async def qualify_contact(opp_id: str, body: QualificationIn, user=Depends(current_user)):
    await editable_permit(opp_id, user)
    if len(body.source_note.strip()) < 3:
        raise HTTPException(422, "Indiquez l’origine de cette qualification.")
    await db.radar_qualifications.update_one({"_id": f'{user["user_id"]}:{opp_id}'}, {"$set": {
        "user_id": user["user_id"], "opp_id": opp_id, "category": body.category,
        "source_note": body.source_note.strip(), "kind": "user_confirmed",
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }}, upsert=True)
    return await get_opportunity(opp_id, user)


@router.delete("/{opp_id}/qualification", response_model=ContactOpportunityOut)
async def remove_qualification(opp_id: str, user=Depends(current_user)):
    await editable_permit(opp_id, user)
    await db.radar_qualifications.delete_one({"_id": f'{user["user_id"]}:{opp_id}'})
    return await get_opportunity(opp_id, user)


async def editable_permit(opp_id, user):
    if user.get("account_type") != "pro" and user.get("role") != "admin":
        raise HTTPException(403, "Contacts réservés à l'espace professionnel.")
    permit = next((p for p in await _get_permits() if p["id"] == opp_id), None)
    if not permit:
        raise HTTPException(404, "Opportunité introuvable")
    if permit.get("is_demo"):
        raise HTTPException(409, "Fiche fictive : importez un permis réel avant de renseigner un contact.")
    return permit


async def save_contact(opp_id, user, contact, provenance):
    now = datetime.now(timezone.utc).isoformat()
    await db.radar_contacts.update_one(
        {"_id": f'{user["user_id"]}:{opp_id}'},
        {"$set": {"user_id": user["user_id"], "opp_id": opp_id,
                  "contact": contact, "provenance": {**provenance, "confirmed_at": now}}}, upsert=True)
    return await get_opportunity(opp_id, user)


@router.put("/{opp_id}/contact", response_model=ContactOpportunityOut)
async def manual_contact(opp_id: str, body: ManualContactIn, user=Depends(current_user)):
    await editable_permit(opp_id, user)
    contact = body.contact.model_dump()
    if not any(contact.values()) or len(body.source_note.strip()) < 3:
        raise HTTPException(422, "Renseignez au moins une coordonnée et son origine.")
    return await save_contact(opp_id, user, contact, {
        "kind": "manual", "label": body.source_note.strip(),
        "source_url": str(body.source_url) if body.source_url else None})


@router.delete("/{opp_id}/contact", response_model=ContactOpportunityOut)
async def delete_contact(opp_id: str, user=Depends(current_user)):
    await editable_permit(opp_id, user)
    await db.radar_contacts.delete_one({"_id": f'{user["user_id"]}:{opp_id}'})
    return await get_opportunity(opp_id, user)


@router.post("/{opp_id}/contact/search", response_model=SearchOut)
async def search_contact(opp_id: str, body: SearchIn, user=Depends(current_user)):
    permit = await editable_permit(opp_id, user)
    if permit.get("mo") not in BUSINESS_TYPES:
        raise HTTPException(403, "Recherche réservée aux entreprises, jamais aux particuliers.")
    query = body.query.strip()
    if len(query) < 2:
        raise HTTPException(422, "Indiquez la raison sociale ou le SIREN connu de l'entreprise.")
    now = datetime.now(timezone.utc)
    if await db.radar_contact_searches.count_documents({"user_id": user["user_id"], "created_at": {"$gt": now - timedelta(minutes=1)}}) >= 10:
        raise HTTPException(429, "Trop de recherches. Réessayez dans une minute.")
    await db.radar_contact_searches.create_index("expires_at", expireAfterSeconds=0)
    search_id = secrets.token_urlsafe(18)
    expires = now + timedelta(minutes=15)
    await db.radar_contact_searches.insert_one({"search_id": search_id, "user_id": user["user_id"],
        "opp_id": opp_id, "created_at": now, "expires_at": expires, "candidates": []})
    candidates = await search_companies(query)
    await db.radar_contact_searches.update_one({"search_id": search_id}, {"$set": {"candidates": candidates}})
    return SearchOut(search_id=search_id, candidates=candidates, expires_at=expires.isoformat())


@router.post("/{opp_id}/contact/confirm", response_model=ContactOpportunityOut)
async def confirm_contact(opp_id: str, body: ConfirmIn, user=Depends(current_user)):
    permit = await editable_permit(opp_id, user)
    if permit.get("mo") not in BUSINESS_TYPES:
        raise HTTPException(403, "Recherche réservée aux entreprises.")
    result = await db.radar_contact_searches.find_one({"search_id": body.search_id,
        "user_id": user["user_id"], "opp_id": opp_id,
        "expires_at": {"$gt": datetime.now(timezone.utc)}}, {"_id": 0})
    candidate = next((c for c in (result or {}).get("candidates", []) if c["siren"] == body.siren), None)
    if not candidate:
        raise HTTPException(404, "Proposition introuvable ou expirée. Relancez la recherche.")
    contact = {key: candidate.get(key, "") for key in ContactFields.model_fields}
    return await save_contact(opp_id, user, contact, {"kind": "registry",
        "label": "Annuaire des Entreprises · correspondance confirmée par vous",
        "source_url": candidate["source_url"], "retrieved_at": result["created_at"].isoformat()})