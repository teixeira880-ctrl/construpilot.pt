"""StructuroPilot — routes du parcours Étude autonome (Lot A backbone).

Backbone honnête : collecte guidée, modèle tracé, couverture des vérifications,
niveaux de sortie et approbation nominative. AUCUN calcul structurel chiffré :
le niveau « Étude calculée » est verrouillé (moteur non qualifié, normes non licenciées).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field
import asyncio
import hashlib

from core.db import db
from core.uploads import (
    validate_upload, ALLOWED_IMAGE, ALLOWED_DOCUMENT, ALLOWED_CAD,
)
from routes.auth import current_user
from engines import structuro_model as sm
from engines import structuro_ai

router = APIRouter(prefix="/structuro", tags=["structuro"])


async def _get_study(study_id: str, user_id: str) -> dict:
    s = await db.structuro_studies.find_one({"study_id": study_id, "user_id": user_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Estudo não encontrado.")
    return s


async def _save(study: dict) -> dict:
    study.pop("_id", None)
    await db.structuro_studies.update_one(
        {"study_id": study["study_id"], "user_id": study["user_id"]},
        {"$set": study}, upsert=True)
    return study


class CreateIn(BaseModel):
    title: str | None = None
    country: str | None = "PT"
    description: str = Field(default="", max_length=8000)


class DatumIn(BaseModel):
    key: str
    value: str | float | int | None = None
    unit: str | None = None
    source: str = "declaration"
    note: str | None = None


class AnswerIn(BaseModel):
    datum_key: str
    value: str | float | int | None = None
    unit: str | None = None
    source: str = "declaration"      # declaration|mesure|document|essai|observation|inconnu
    note: str | None = None


class ElementIn(BaseModel):
    type: str
    ref: str | None = None
    label: str | None = None
    level: str | None = None


class ApproveIn(BaseModel):
    role: str = Field(min_length=2, max_length=80)
    scope: str = Field(default="", max_length=400)
    reservations: str | None = None


class LevelIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    elevation_m: float | None = None
    source: str = "declaration"


class LevelPatchIn(BaseModel):
    name: str | None = None
    elevation_m: float | None = None
    source: str | None = None


class ElementPatchIn(BaseModel):
    type: str | None = None
    ref: str | None = None
    label: str | None = None
    level: str | None = None


META = {
    "calc_engine_available": sm.CALC_ENGINE_AVAILABLE,
    "rulepack": sm.RULEPACK,
    "output_levels": sm.OUTPUT_LEVELS,
    "sources": sm.SOURCES,
    "element_types": sm.ELEMENT_TYPES,
    "verification_catalogue": sm.VERIFICATIONS,
    "disclaimer": ("O StructuroPilot (Lote A) é uma ferramenta de recolha e estruturação de dados e de esboço. NÃO realiza NENHUM cálculo estrutural quantificado e não substitui a verificação de um engenheiro de estruturas. Nenhum documento é «bom para execução»."),
}


@router.get("/meta")
async def meta(user=Depends(current_user)) -> dict:
    return META


@router.post("/studies")
async def create_study(body: CreateIn, user=Depends(current_user)) -> dict:
    study = sm.new_study(user["user_id"], body.title, body.country, body.description)
    if body.description.strip():
        extracted = await structuro_ai.extract_facts(body.description)
        study["facts"] = [{"id": sm.new_id("f"), "text": f["text"], "source": "declaration"}
                          for f in extracted.get("facts", [])]
        study["ai_engine"] = extracted.get("source_engine")
    study = sm.recompute(study)
    await _save(study)
    return study


@router.post("/studies/demo")
async def create_demo(user=Depends(current_user)) -> dict:
    study = sm.new_study(user["user_id"], "", "FR", sm.DEMO_DESCRIPTION)
    study = sm.build_demo(study)
    await _save(study)
    return study


@router.get("/studies")
async def list_studies(user=Depends(current_user)) -> dict:
    items = await db.structuro_studies.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "study_id": 1, "title": 1, "lifecycle": 1, "output_level": 1,
         "revision": 1, "created_at": 1, "updated_at": 1}).sort("updated_at", -1).to_list(200)
    return {"studies": items}


@router.get("/studies/{study_id}")
async def get_study(study_id: str, user=Depends(current_user)) -> dict:
    s = await _get_study(study_id, user["user_id"])
    s["meta"] = META
    return s


@router.post("/studies/{study_id}/answer")
async def answer_question(study_id: str, body: AnswerIn, user=Depends(current_user)) -> dict:
    """Répond à une question (incl. « Je ne sais pas » → source=inconnu).
    Rendre une donnée critique inconnue périme les résultats/approbations dépendants."""
    s = await _get_study(study_id, user["user_id"])
    s.setdefault("data", {})
    was_documented = sm.is_documented(s["data"].get(body.datum_key))
    src = body.source if body.source in sm.SOURCES else "declaration"
    if src == "inconnu" or body.value in (None, ""):
        s["data"][body.datum_key] = sm.datum(None, body.unit, "inconnu", body.note)
        s = sm.invalidate_dependents(s, body.datum_key) if was_documented else sm.recompute(s)
    else:
        s["data"][body.datum_key] = sm.datum(body.value, body.unit, src, body.note)
        s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.patch("/studies/{study_id}/datum")
async def set_datum(study_id: str, body: DatumIn, user=Depends(current_user)) -> dict:
    s = await _get_study(study_id, user["user_id"])
    s.setdefault("data", {})
    was_documented = sm.is_documented(s["data"].get(body.key))
    src = body.source if body.source in sm.SOURCES else "declaration"
    if src == "inconnu" or body.value in (None, ""):
        s["data"][body.key] = sm.datum(None, body.unit, "inconnu", body.note)
        s = sm.invalidate_dependents(s, body.key) if was_documented else sm.recompute(s)
    else:
        s["data"][body.key] = sm.datum(body.value, body.unit, src, body.note)
        s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.post("/studies/{study_id}/elements")
async def add_element(study_id: str, body: ElementIn, user=Depends(current_user)) -> dict:
    s = await _get_study(study_id, user["user_id"])
    if body.type not in sm.ELEMENT_TYPES:
        raise HTTPException(422, "Tipo de elemento desconhecido.")
    s.setdefault("elements", []).append({
        "id": sm.new_id("el"), "type": body.type,
        "ref": (body.ref or body.type[:2].upper()), "label": body.label or body.type,
        "level": body.level})
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.delete("/studies/{study_id}/elements/{element_id}")
async def delete_element(study_id: str, element_id: str, user=Depends(current_user)) -> dict:
    s = await _get_study(study_id, user["user_id"])
    s["elements"] = [e for e in s.get("elements", []) if e.get("id") != element_id]
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.patch("/studies/{study_id}/elements/{element_id}")
async def patch_element(study_id: str, element_id: str, body: ElementPatchIn,
                        user=Depends(current_user)) -> dict:
    """Édite un élément porteur existant (type/repère/libellé/niveau)."""
    s = await _get_study(study_id, user["user_id"])
    el = next((e for e in s.get("elements", []) if e.get("id") == element_id), None)
    if not el:
        raise HTTPException(404, "Elemento não encontrado.")
    if body.type is not None:
        if body.type not in sm.ELEMENT_TYPES:
            raise HTTPException(422, "Tipo de elemento desconhecido.")
        el["type"] = body.type
    if body.ref is not None:
        el["ref"] = body.ref.strip() or el.get("ref")
    if body.label is not None:
        el["label"] = body.label.strip() or el.get("label")
    if body.level is not None:
        el["level"] = body.level.strip() or None
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.post("/studies/{study_id}/levels")
async def add_level(study_id: str, body: LevelIn, user=Depends(current_user)) -> dict:
    """Ajoute un niveau (esquisse). L'élévation est optionnelle ; sans valeur → inconnue."""
    s = await _get_study(study_id, user["user_id"])
    src = body.source if body.source in sm.SOURCES else "declaration"
    elev = sm.datum(body.elevation_m, "m", src if body.elevation_m is not None else "inconnu")
    s.setdefault("levels", []).append({
        "id": sm.new_id("lvl"), "name": body.name.strip(), "elevation_m": elev})
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.patch("/studies/{study_id}/levels/{level_id}")
async def patch_level(study_id: str, level_id: str, body: LevelPatchIn,
                      user=Depends(current_user)) -> dict:
    s = await _get_study(study_id, user["user_id"])
    lvl = next((l for l in s.get("levels", []) if l.get("id") == level_id), None)
    if not lvl:
        raise HTTPException(404, "Nível não encontrado.")
    if body.name is not None and body.name.strip():
        lvl["name"] = body.name.strip()
    if body.elevation_m is not None:
        src = body.source if body.source in sm.SOURCES else "declaration"
        lvl["elevation_m"] = sm.datum(body.elevation_m, "m", src)
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.delete("/studies/{study_id}/levels/{level_id}")
async def delete_level(study_id: str, level_id: str, user=Depends(current_user)) -> dict:
    s = await _get_study(study_id, user["user_id"])
    before = len(s.get("levels", []))
    s["levels"] = [l for l in s.get("levels", []) if l.get("id") != level_id]
    if len(s["levels"]) == before:
        raise HTTPException(404, "Nível não encontrado.")
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.post("/studies/{study_id}/approve")
async def approve(study_id: str, body: ApproveIn, user=Depends(current_user)) -> dict:
    """Approbation nominative, contrôlée côté serveur. Bloquée tant qu'une vérif est bloquée.
    N'autorise JAMAIS le statut « exécution » (moteur de calcul non qualifié)."""
    s = await _get_study(study_id, user["user_id"])
    blocked = [v for v in s.get("verifications", []) if v["status"] == "bloquee"]
    if blocked:
        raise HTTPException(409, f'Aprovação impossível: {len(blocked)} verificação(ões) bloqueada(s) por dados em falta.')
    s.setdefault("approvals", []).append({
        "id": sm.new_id("ap"),
        "user_id": user["user_id"],
        "name": user.get("name") or user.get("email") or user["user_id"],
        "role": body.role.strip(),
        "scope": body.scope.strip(),
        "reservations": (body.reservations or "").strip() or None,
        "revision": s.get("revision", 1),
        "level": "etude_preliminaire",   # jamais "execution"
        "status": "valide",
        "at": sm.now(),
        "note": "Aprovação de estudo preliminar. NÃO válido para execução: verificação estrutural por um engenheiro necessária (motor de cálculo não qualificado).",
    })
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


class PlanPatchIn(BaseModel):
    level: str | None = None
    kind: str | None = None          # existant | projet | bet
    scale_note: str | None = None    # recalage : cote de référence / échelle


PLAN_KINDS = {"existant", "projet", "bet"}
ALLOWED_EXT = {"pdf", "dxf", "dwg", "ifc", "png", "jpg", "jpeg", "webp"}
MAX_PLAN_BYTES = 30 * 1024 * 1024


@router.post("/studies/{study_id}/plans")
async def upload_plan(study_id: str, file: UploadFile = File(...),
                      level: str = Form(""), kind: str = Form("existant"),
                      scale_note: str = Form(""), user=Depends(current_user)) -> dict:
    """Importe un plan (PDF/DXF/image) dans l'object storage + reconnaissance première passe.
    Le fichier est stocké de façon persistante ; Mongo ne garde que la référence."""
    from engines import object_storage as obj
    from engines import structuro_recognition as reco
    s = await _get_study(study_id, user["user_id"])
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "").lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(422, f"Extensão não suportada ({ext}). Formats : {', '.join(sorted(ALLOWED_EXT))}.")
    file = await validate_upload(
        file,
        ALLOWED_DOCUMENT + ALLOWED_IMAGE + ALLOWED_CAD,
        max_mb=MAX_PLAN_BYTES // (1024 * 1024),
    )
    data = await file.read()
    if not data:
        raise HTTPException(422, "Ficheiro vazio.")
    if len(data) > MAX_PLAN_BYTES:
        raise HTTPException(413, "Ficheiro demasiado volumoso (máx. 30 MB).")
    plan_id = sm.new_id("pl")
    path = f"{obj.APP_NAME}/structuro/{user['user_id']}/{study_id}/{plan_id}.{ext}"
    ctype = obj.mime_for(file.filename)
    try:
        result = await asyncio.to_thread(obj.put_object, path, data, ctype)
    except Exception as e:
        raise HTTPException(502, f'Armazenamento do ficheiro impossível: {str(e)[:120]}')
    recognition = reco.recognize(data, file.filename)
    plan = {
        "id": plan_id,
        "storage_path": result.get("path", path),
        "original_filename": file.filename,
        "content_type": ctype,
        "size": result.get("size", len(data)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "level": (level or "").strip() or None,
        "kind": kind if kind in PLAN_KINDS else "existant",
        "scale_note": (scale_note or "").strip() or None,
        "recognition": recognition,
        "is_deleted": False,
        "uploaded_at": sm.now(),
    }
    s.setdefault("plans", []).append(plan)
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.get("/studies/{study_id}/plans/{plan_id}/file")
async def download_plan(study_id: str, plan_id: str, user=Depends(current_user)):
    from engines import object_storage as obj
    s = await _get_study(study_id, user["user_id"])
    plan = next((p for p in s.get("plans", []) if p["id"] == plan_id and not p.get("is_deleted")), None)
    if not plan:
        raise HTTPException(404, "Planta não encontrada.")
    try:
        content, ctype = await asyncio.to_thread(obj.get_object, plan["storage_path"])
    except Exception as e:
        raise HTTPException(502, f'Leitura do ficheiro impossível: {str(e)[:120]}')
    return Response(content=content, media_type=plan.get("content_type") or ctype, headers={
        "Content-Disposition": f'inline; filename="{plan.get("original_filename", "plan")}"'})


@router.patch("/studies/{study_id}/plans/{plan_id}")
async def patch_plan(study_id: str, plan_id: str, body: PlanPatchIn, user=Depends(current_user)) -> dict:
    """Recalage : réaffecte le niveau / le type / la note d'échelle d'un plan importé."""
    s = await _get_study(study_id, user["user_id"])
    plan = next((p for p in s.get("plans", []) if p["id"] == plan_id and not p.get("is_deleted")), None)
    if not plan:
        raise HTTPException(404, "Planta não encontrada.")
    if body.level is not None:
        plan["level"] = body.level.strip() or None
    if body.kind is not None and body.kind in PLAN_KINDS:
        plan["kind"] = body.kind
    if body.scale_note is not None:
        plan["scale_note"] = body.scale_note.strip() or None
    s = sm.recompute(s)
    await _save(s)
    s["meta"] = META
    return s


@router.delete("/studies/{study_id}/plans/{plan_id}")
async def delete_plan(study_id: str, plan_id: str, user=Depends(current_user)) -> dict:
    """Soft-delete (le stockage n'a pas d'API de suppression)."""
    s = await _get_study(study_id, user["user_id"])
    plan = next((p for p in s.get("plans", []) if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(404, "Planta não encontrada.")
    plan["is_deleted"] = True
    await _save(s)
    s["meta"] = META
    return s


class LintelComputeIn(BaseModel):
    clear_span_m: float | None = None
    wall_thickness_m: float | None = None
    masonry_unit_weight_kn_m3: float | None = None
    masonry_height_above_m: float | None = None
    load_model: str | None = None
    arch_angle_deg: float | None = None
    permanent_line_kn_m: float | None = None
    variable_line_kn_m: float | None = None
    psi2: float | None = None
    bearing_length_m: float | None = None
    masonry_comp_strength_mpa: float | None = None
    deflection_limit_total: float | None = None
    deflection_limit_qp: float | None = None
    material: str | None = None
    steel_grade: str | None = None
    steel_families: list[str] | None = None
    max_profiles: int | None = None
    rc_width_m: float | None = None
    rc_height_m: float | None = None
    fck: float | None = None
    fyk: float | None = None
    steel_eur_per_kg: float | None = None
    concrete_eur_per_m3: float | None = None
    rebar_eur_per_kg: float | None = None


@router.post("/studies/{study_id}/lintel")
async def compute_lintel(study_id: str, body: LintelComputeIn, user=Depends(current_user)) -> dict:
    """Dé-verrouille un calcul INDICATIF du linteau via le moteur BET déterministe (EN 1992/1993).
    Ne change pas le verrouillage global : résultat indicatif, non exécutoire."""
    from engines import structuro_lintel as lintel
    s = await _get_study(study_id, user["user_id"])
    data = s.get("data") or {}

    def dval(key):
        v = (data.get(key) or {}).get("value")
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    opts = {k: v for k, v in body.model_dump().items() if v is not None}
    opts.setdefault("clear_span_m", dval("ouverture.portee"))
    opts.setdefault("wall_thickness_m", dval("mur.epaisseur"))
    if "permanent_line_kn_m" not in opts and dval("ouverture.charges_reprises") is not None:
        opts["permanent_line_kn_m"] = dval("ouverture.charges_reprises")
    if not opts.get("clear_span_m"):
        raise HTTPException(422, "Vão da abertura necessário (documente «ouverture.portee» ou envie clear_span_m).")
    result = lintel.lintel_design(opts)
    s["lintel"] = {"inputs": opts, "result": result, "at": sm.now()}
    await _save(s)
    s["meta"] = META
    return s


@router.delete("/studies/{study_id}/lintel")
async def clear_lintel(study_id: str, user=Depends(current_user)) -> dict:
    s = await _get_study(study_id, user["user_id"])
    s.pop("lintel", None)
    await _save(s)
    s["meta"] = META
    return s


@router.get("/studies/{study_id}/sheets.pdf")
async def study_sheets(study_id: str, user=Depends(current_user)):
    """Feuilles d'étude EXI/STR (esquisses schématiques) depuis le modèle — jamais pour exécution."""
    from engines.structuro_sheets import build_study_sheets
    s = await _get_study(study_id, user["user_id"])
    pdf = build_study_sheets(s)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="structuro-{study_id}-esbocos.pdf"'})


@router.get("/studies/{study_id}/note.pdf")
async def study_note(study_id: str, user=Depends(current_user)):
    """Note d'étude préliminaire au format du rapport de référence (sections + variantes).
    Tout ce qui dépend du moteur verrouillé est marqué « À CALCULER »."""
    from engines.structuro_note import build_study_note
    s = await _get_study(study_id, user["user_id"])
    pdf = build_study_note(s)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="structuro-{study_id}-note.pdf"'})


@router.delete("/studies/{study_id}")
async def delete_study(study_id: str, user=Depends(current_user)) -> dict:
    r = await db.structuro_studies.delete_one({"study_id": study_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Estudo não encontrado.")
    return {"ok": True}
