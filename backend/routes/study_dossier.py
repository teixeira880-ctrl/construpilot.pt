"""Review and export the traceable construction dossier under existing plan rights."""
import copy
import math

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from core.db import db
from core.security import current_user
from engines.study_dossier import VERSION, StudyError, build_dossier, fingerprint, quote_lines_hash
from engines.study_dossier_jobs import owned_job, public, now, study_settings
from routes.plans_common import router

jobs_router = APIRouter(prefix="/pc/study-jobs", tags=["pc-study"])


@jobs_router.get("")
async def list_jobs(user=Depends(current_user)):
    rows = await db.pc_study_jobs.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    return {"jobs": [public(j) for j in rows]}


@jobs_router.get("/{job_id}")
async def get_job(job_id: str, user=Depends(current_user)):
    return public(await owned_job(job_id, user))


@jobs_router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, user=Depends(current_user)):
    job = await owned_job(job_id, user)
    if job["status"] == "committing":
        raise HTTPException(409, "Enregistrement du résultat en cours ; il sera disponible dans quelques secondes")
    if job["status"] in ("queued", "running"):
        fields = {"cancel_requested": True, "updated_at": now().isoformat()}
        if job["status"] == "queued":
            fields.update(status="cancelled", active=False)
        changed = await db.pc_study_jobs.update_one({"job_id": job_id, "user_id": user["user_id"], "status": job["status"]}, {"$set": fields})
        if not changed.matched_count:
            await db.pc_study_jobs.update_one({"job_id": job_id, "user_id": user["user_id"], "status": "running"}, {"$set": {"cancel_requested": True}})
    return public(await owned_job(job_id, user))


class DossierRevisionIn(BaseModel):
    expected_revision: str = Field(min_length=1, max_length=100)
    parameter_changes: dict[str, float | None] = Field(default_factory=dict)
    price_changes: dict[str, float | None] = Field(default_factory=dict)
    reviewed_parameters: list[str] = Field(default_factory=list, max_length=1500)
    review_states: dict[str, bool] = Field(default_factory=dict)
    country: str | None = None
    vat_rate: float | None = Field(None, ge=0, le=100, allow_inf_nan=False)

    @field_validator("parameter_changes", "price_changes")
    @classmethod
    def finite_changes(cls, values):
        if len(values) > 1500 or any(v is not None and (not math.isfinite(v) or abs(v) > 1e12) for v in values.values()):
            raise ValueError("Valeurs hors limites")
        return values


@router.post("/{plan_id}/pc-study/revise")
async def revise_dossier(plan_id: str, body: DossierRevisionIn, user=Depends(current_user)):
    from routes.plans_pc import _plan_and_study
    p = await _plan_and_study(plan_id, user, write=True)
    old = p["pc_study"]
    if old.get("schema_version") != VERSION:
        raise HTTPException(409, "Relancez cette ancienne étude pour utiliser les mesures sourcées")
    if old.get("revision") != body.expected_revision:
        raise HTTPException(409, "L’étude a changé ; rechargez avant de corriger")
    spec = copy.deepcopy(old["spec"])
    parameters = {x["id"]: x for x in spec.get("parameters", [])}
    items = {x["id"]: x for x in spec.get("items", [])}
    if not set(body.parameter_changes).issubset(parameters) or not set(body.price_changes).issubset(items) or not (set(body.reviewed_parameters) | set(body.review_states)).issubset(parameters):
        raise HTTPException(422, "Mesure ou poste inconnu")
    for key, value in body.parameter_changes.items():
        if parameters[key].get("expression"):
            raise HTTPException(422, "Corrigez les données de la formule, pas son résultat dérivé")
        previous = parameters[key].get("value")
        parameters[key].update(value=value, status="manual", reviewed=False, conflict=False,
            note=f"Valeur corrigée par l’utilisateur (précédente : {previous}). " + str(parameters[key].get("note") or "")[:1200])
    for key in body.reviewed_parameters:
        parameters[key]["reviewed"] = True
    for key, value in body.review_states.items():
        parameters[key]["reviewed"] = value
    for key, value in body.price_changes.items():
        items[key]["unit_price"] = value
    saved = dict(old.get("settings_snapshot") or {})
    if body.country is not None:
        if body.country not in ("FR", "PT"):
            raise HTTPException(422, "Pays fiscal non pris en charge")
        from core.fiscal import policy_for
        saved.update(country=body.country, vat_rate=policy_for(body.country)["default_rate"], vat_assumed=True)
    if body.vat_rate is not None:
        saved.update(vat_rate=body.vat_rate, vat_assumed=False)
    try:
        settings = await study_settings(p["user_id"], saved)
        updated = build_dossier(spec, page_count=old["page_count"], source=old.get("source"), settings=settings, coverage=old.get("coverage"))
    except StudyError as exc:
        raise HTTPException(422, str(exc)) from None
    updated["page_analyses"] = old.get("page_analyses") or []
    query = {"plan_id": plan_id, "user_id": p["user_id"], "pc_study.revision": body.expected_revision, "updated_at": p.get("updated_at")}
    result = await db.plans_takeoff.update_one(query, {"$set": {"pc_study": updated, "updated_at": now().isoformat()}})
    if not result.matched_count:
        raise HTTPException(409, "Le dossier a changé pendant la correction")
    await db.pc_study_history.insert_one({"plan_id": plan_id, "user_id": p["user_id"], "saved_at": now().isoformat(),
        "source": "révision des mesures/prix", "study": old, "ht": old["totals"]["ht"], "ttc": old["totals"]["ttc"]})
    return updated


class DossierQuoteIn(BaseModel):
    expected_revision: str = Field(min_length=1, max_length=100)


@router.post("/{plan_id}/pc-study/quote")
async def create_quote(plan_id: str, body: DossierQuoteIn, user=Depends(current_user)):
    from core.permissions import require_feature
    from routes.plans_pc import _plan_and_study
    from routes.documents import _compute_totals
    require_feature(user, "devis")
    p = await _plan_and_study(plan_id, user)
    study = p["pc_study"]
    if study.get("schema_version") != VERSION or study.get("revision") != body.expected_revision:
        raise HTTPException(409, "Rechargez la version actuelle de l’étude")
    if study["totals"].get("partial") or study["totals"].get("ttc") is None:
        raise HTTPException(422, "Complétez les quantités, les prix et la TVA avant de créer le devis commercial")
    # Snapshot is reusable, never overwritten when the study or editor is changed.
    ident = "doc_"+fingerprint([user["user_id"],plan_id,study["revision"]])[:24]
    lines=[]
    for r in study["items"]:
        if not r["included"]:
            continue
        lines.append({"line_id": r["id"], "kind": "line", "line_kind": "ouvrage", "designation": r["designation"],
            "description": r["detail"]+f"\nMétré : {r['expression']} [{r['quantity_status']}]", "qty": r["qty"],
            "unit": r["unit"], "unit_price_ht": r["unit_price"], "vat_rate": study["totals"]["tva_rate"]*100,
            "vat_assumed": study.get("settings_snapshot",{}).get("vat_assumed",True), "discount_pct": 0,
            "cost_price_ht": 0, "cost_confirmed_zero": False, "category": r["group"],
            "price_source": "user_input" if r["price_source"] == "prix_utilisateur" else "assistant_estimate",
            "price_estimated": r["price_source"] != "prix_utilisateur", "price_missing": False, "quantity_missing": False})
    totals = _compute_totals(lines, 0)
    timestamp=now().isoformat()
    await db.pro_documents.update_one({"_id": f"study_quote:{ident}"},{"$setOnInsert": {
        "doc_id": ident, "user_id": user["user_id"], "doc_type": "quote", "status": "draft", "signed": False,
        "title": (study.get("project") or {}).get("title") or p.get("filename"), "lines": lines, "totals": totals,
        "number": None, "client_id": None, "client": None, "client_name": "", "deposit_pct": 0,
        "payment_terms": "", "notes": "Hypothèses :\n"+"\n".join(study.get("assumptions", []))+"\nExclusions :\n"+"\n".join(study.get("exclusions", [])), "lang": "fr", "source": "construction_study",
        "source_plan_id": plan_id, "source_study_revision": study["revision"], "study_dossier": study,
        "study_lines_hash": quote_lines_hash(lines), "project_address": (study.get("project") or {}).get("address") or "",
        "created_at": timestamp, "updated_at": timestamp, "assistant_review_required": True}}, upsert=True)
    return {"doc_id": ident, "edit_url": f"/devis-editeur/{ident}", "saved": True}
