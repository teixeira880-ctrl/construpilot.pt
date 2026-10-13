"""StructuroPilot — Mode « Analyse de dossier BET ».

Import en LECTURE de plans/notes d'un bureau d'études, lecture IA (Claude) des PDF/images,
comparaison de versions (indice A → B), détection d'incohérences entre documents et
rapport de contrôle PDF. Aucun calcul structurel. Réservé aux offres « pro » et plus.
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from core.db import db
from routes.auth import current_user
from engines.access import require_level
from engines import object_storage as obj
from engines import structuro_bet_ai as betai
from engines import structuro_autopilot as autopilot
from engines.structuro_coffrage import build_coffrage_pdf
from engines.structuro_bet_pdf import build_control_report

router = APIRouter(prefix="/structuro/bet", tags=["structuro-bet"],
                   dependencies=[Depends(require_level("pro"))])

ALLOWED_EXT = {"pdf", "png", "jpg", "jpeg", "webp", "dwg", "dxf", "ifc"}
MAX_BYTES = 80 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


async def _get(dossier_id: str, user_id: str) -> dict:
    d = await db.bet_dossiers.find_one({"dossier_id": dossier_id, "user_id": user_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Processo não encontrado.")
    return d


async def _save(d: dict) -> dict:
    d.pop("_id", None)
    d["updated_at"] = _now()
    await db.bet_dossiers.update_one(
        {"dossier_id": d["dossier_id"], "user_id": d["user_id"]}, {"$set": d}, upsert=True)
    return d


def _live_docs(d: dict) -> list[dict]:
    return [x for x in d.get("documents", []) if not x.get("is_deleted")]


class CreateIn(BaseModel):
    title: str = Field(default="", max_length=160)


class MetaIn(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    responsable: str | None = Field(default=None, max_length=120)


class CompareIn(BaseModel):
    doc_a: str
    doc_b: str


@router.get("/studies")
async def list_dossiers(user=Depends(current_user)) -> dict:
    items = await db.bet_dossiers.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "dossier_id": 1, "title": 1, "created_at": 1, "updated_at": 1, "documents": 1}
    ).sort("updated_at", -1).to_list(200)
    for it in items:
        it["document_count"] = len([x for x in it.get("documents", []) if not x.get("is_deleted")])
        it.pop("documents", None)
    return {"studies": items}


@router.post("/studies")
async def create_dossier(body: CreateIn, user=Depends(current_user)) -> dict:
    d = {
        "dossier_id": _nid("bet"), "user_id": user["user_id"],
        "title": body.title.strip() or "Dossier BET",
        "documents": [], "comparisons": [], "inconsistencies": None,
        "created_at": _now(), "updated_at": _now(),
    }
    await _save(d)
    return d


@router.get("/studies/{dossier_id}")
async def get_dossier(dossier_id: str, user=Depends(current_user)) -> dict:
    return await _get(dossier_id, user["user_id"])


@router.patch("/studies/{dossier_id}")
async def update_meta(dossier_id: str, body: MetaIn, user=Depends(current_user)) -> dict:
    d = await _get(dossier_id, user["user_id"])
    if body.title is not None:
        d["title"] = body.title.strip() or d.get("title") or "Dossier BET"
    if body.responsable is not None:
        d["responsable"] = body.responsable.strip()
    await _save(d)
    return d


@router.delete("/studies/{dossier_id}")
async def delete_dossier(dossier_id: str, user=Depends(current_user)) -> dict:
    r = await db.bet_dossiers.delete_one({"dossier_id": dossier_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Processo não encontrado.")
    return {"ok": True}


@router.post("/studies/{dossier_id}/documents")
async def upload_document(dossier_id: str, file: UploadFile = File(...),
                          index: str = Form(""), kind: str = Form("bet"),
                          user=Depends(current_user)) -> dict:
    d = await _get(dossier_id, user["user_id"])
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "").lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(422, f"Extensão não suportada ({ext}). Formats : {', '.join(sorted(ALLOWED_EXT))}.")
    data = await file.read()
    if not data:
        raise HTTPException(422, "Ficheiro vazio.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Ficheiro demasiado volumoso (máx. 30 MB).")
    doc_id = _nid("dc")
    ctype = obj.mime_for(file.filename) if ext not in {"pdf"} else "application/pdf"
    if ext == "pdf":
        ctype = "application/pdf"
    path = f"{obj.APP_NAME}/bet/{user['user_id']}/{dossier_id}/{doc_id}.{ext}"
    try:
        result = await run_in_threadpool(obj.put_object, path, data, ctype)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f'Armazenamento impossível: {str(e)[:120]}')
    extraction = await betai.extract_document(data, ctype, file.filename or "")
    doc = {
        "id": doc_id, "storage_path": result.get("path", path),
        "original_filename": file.filename, "content_type": ctype,
        "size": result.get("size", len(data)), "sha256": hashlib.sha256(data).hexdigest(),
        "index": (index or "").strip() or extraction.get("indice_detecte") or None,
        "kind": kind.strip() or "bet",
        "analyzable": betai.is_analyzable(ctype),
        "extraction": extraction, "is_deleted": False, "uploaded_at": _now(),
    }
    d.setdefault("documents", []).append(doc)
    d["inconsistencies"] = None  # périme l'analyse globale
    await _save(d)
    return d


@router.post("/studies/{dossier_id}/documents/{doc_id}/analyze-autodesk")
async def analyze_autodesk(dossier_id: str, doc_id: str, user=Depends(current_user)) -> dict:
    """Lecture géométrique DWG/IFC via Autodesk APS (traduction payante, mise en cache par fichier),
    puis synthèse IA factuelle dans le schéma BET. Déclenchée explicitement par l'utilisateur."""
    from engines import autodesk_md
    from engines.autodesk_client import AutodeskError
    d = await _get(dossier_id, user["user_id"])
    doc = next((x for x in _live_docs(d) if x["id"] == doc_id), None)
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    ext = (doc.get("original_filename", "").rsplit(".", 1)[-1] if "." in doc.get("original_filename", "") else "").lower()
    if ext not in {"dwg", "dxf", "ifc"}:
        raise HTTPException(422, "Leitura Autodesk reservada aos ficheiros DWG/DXF/IFC.")
    try:
        content, _ = await run_in_threadpool(obj.get_object, doc["storage_path"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f'Leitura do ficheiro impossível: {str(e)[:120]}')
    try:
        md = await autodesk_md.extract(content, doc.get("original_filename") or f"plan.{ext}", user_id=user["user_id"])
    except AutodeskError as e:
        raise HTTPException(502, f"Autodesk : {getattr(e, 'message', str(e))[:160]}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f'Tradução Autodesk impossível: {str(e)[:120]}')
    views = md.get("views", [])
    summary_lines = []
    for v in views[:6]:
        summary_lines.append(f"Vista «{v.get('name')} » : {v.get('objects')} objetos. Camadas: {', '.join((str(x[0]) for x in (v.get('layers') or [])[:20]))}. Catégories: {', '.join((str(x[0]) for x in (v.get('categories') or [])[:20]))}. Propriétés: {', '.join((v.get('property_keys') or [])[:30])}.")
    import json as _json
    sample = md.get("sample_objects") or []
    meta_summary = "\n".join(summary_lines) + "\n\nAmostra de objetos:\n" + _json.dumps(sample[:12], ensure_ascii=False)[:8000]
    extraction = await betai.extract_from_metadata(meta_summary)
    extraction["autodesk"] = {"objects": sum(v.get("objects", 0) for v in views), "views": len(views),
                              "cached": md.get("cached", False)}
    doc["extraction"] = extraction
    doc["analyzable"] = True
    d["inconsistencies"] = None
    await _save(d)
    return d


@router.post("/studies/{dossier_id}/documents/{doc_id}/reanalyze")
async def reanalyze_document(dossier_id: str, doc_id: str, user=Depends(current_user)) -> dict:
    d = await _get(dossier_id, user["user_id"])
    doc = next((x for x in _live_docs(d) if x["id"] == doc_id), None)
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    try:
        content, ctype = await run_in_threadpool(obj.get_object, doc["storage_path"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f'Leitura impossível: {str(e)[:120]}')
    doc["extraction"] = await betai.extract_document(content, doc.get("content_type") or ctype, doc.get("original_filename") or "")
    if not doc.get("index"):
        doc["index"] = doc["extraction"].get("indice_detecte") or None
    d["inconsistencies"] = None
    await _save(d)
    return d


@router.delete("/studies/{dossier_id}/documents/{doc_id}")
async def delete_document(dossier_id: str, doc_id: str, user=Depends(current_user)) -> dict:
    d = await _get(dossier_id, user["user_id"])
    doc = next((x for x in d.get("documents", []) if x["id"] == doc_id), None)
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    doc["is_deleted"] = True
    d["comparisons"] = [c for c in d.get("comparisons", []) if doc_id not in (c.get("doc_a"), c.get("doc_b"))]
    d["inconsistencies"] = None
    await _save(d)
    return d


@router.get("/studies/{dossier_id}/documents/{doc_id}/file")
async def download_document(dossier_id: str, doc_id: str, user=Depends(current_user)):
    d = await _get(dossier_id, user["user_id"])
    doc = next((x for x in _live_docs(d) if x["id"] == doc_id), None)
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    try:
        content, ctype = await run_in_threadpool(obj.get_object, doc["storage_path"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f'Leitura impossível: {str(e)[:120]}')
    return Response(content=content, media_type=doc.get("content_type") or ctype, headers={
        "Content-Disposition": f'inline; filename="{doc.get("original_filename", "document")}"'})


@router.post("/studies/{dossier_id}/compare")
async def compare_versions(dossier_id: str, body: CompareIn, user=Depends(current_user)) -> dict:
    d = await _get(dossier_id, user["user_id"])
    docs = {x["id"]: x for x in _live_docs(d)}
    a, b = docs.get(body.doc_a), docs.get(body.doc_b)
    if not a or not b:
        raise HTTPException(404, "Documento(s) não encontrado(s).")
    if a["id"] == b["id"]:
        raise HTTPException(422, "Escolha dois documentos diferentes.")
    result = await betai.compare_documents(a.get("extraction") or {}, b.get("extraction") or {})
    comp = {"comp_id": _nid("cmp"), "doc_a": a["id"], "doc_b": b["id"],
            "result": result, "created_at": _now()}
    d.setdefault("comparisons", [])
    d["comparisons"] = [c for c in d["comparisons"]
                        if {c.get("doc_a"), c.get("doc_b")} != {a["id"], b["id"]}]
    d["comparisons"].insert(0, comp)
    await _save(d)
    return d


@router.post("/studies/{dossier_id}/inconsistencies")
async def scan_inconsistencies(dossier_id: str, user=Depends(current_user)) -> dict:
    d = await _get(dossier_id, user["user_id"])
    docs = [{"name": x.get("original_filename") or x["id"], "extraction": x.get("extraction")}
            for x in _live_docs(d)]
    d["inconsistencies"] = {**await betai.find_inconsistencies(docs), "scanned_at": _now()}
    await _save(d)
    return d


@router.get("/studies/{dossier_id}/report.pdf")
async def control_report(dossier_id: str, user=Depends(current_user)):
    d = await _get(dossier_id, user["user_id"])
    pdf = await run_in_threadpool(build_control_report, d)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="controle-dossier-bet-{dossier_id}.pdf"'})


# ===================== Auto-pilote BET (import → modèle → descente → dossier) =====================
from pydantic import ConfigDict  # noqa: E402

_AUTOPILOT_KINDS = {"plan", "pc", "g2"}

# Mots-clés des pages structurellement utiles d'un permis de construire / plan coté
_GEOM_KEYWORDS = ("masse", "coupe", "niveau", "façade", "facade", "toiture",
                   "rdc", "étage", "etage", "plancher", "fondation", "coffrage", "r+")
_GEOM_DPI = 150
_GEOM_PER_DOC = 8
_GEOM_TOTAL_CAP = 10
# Le rapport G2 (souvent scanné, >40 pages) est lu INTÉGRALEMENT par lots : la synthèse
# (contrainte admissible, fondations) se trouve en général loin dans le document.
_SOIL_DPI = 135
_SOIL_PER_DOC = 54
_SOIL_TOTAL_CAP = 54


class AutopilotInputsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    building: dict | None = None
    system: dict | None = None
    grid: dict | None = None
    loads: dict | None = None
    sections: dict | None = None
    soil: dict | None = None
    prices: dict | None = None
    incertitudes: list | None = None


class GenerateIn(BaseModel):
    inputs: AutopilotInputsIn | None = None


async def _collect_images(d: dict, kinds: set[str], *, dpi: int, per_doc: int,
                          total_cap: int, keywords: tuple | None) -> list[bytes]:
    imgs: list[bytes] = []
    for doc in _live_docs(d):
        if doc.get("kind") not in kinds:
            continue
        try:
            content, ctype = await run_in_threadpool(obj.get_object, doc["storage_path"])
        except Exception:  # noqa: BLE001
            continue
        ct = (doc.get("content_type") or ctype or "").lower()
        if ct == "application/pdf":
            try:
                imgs += await run_in_threadpool(betai.render_doc_images, content, dpi, per_doc, keywords)
            except Exception:  # noqa: BLE001
                continue
        elif ct in betai.IMAGE_MIMES:
            imgs.append(content)
        if len(imgs) >= total_cap:
            break
    return imgs[:total_cap]


@router.post("/studies/{dossier_id}/autopilot/extract")
async def autopilot_extract(dossier_id: str, user=Depends(current_user)) -> dict:
    """Lit (IA) les documents plan/PC/G2 et pré-remplit les données du modèle (à valider)."""
    d = await _get(dossier_id, user["user_id"])
    tagged = [x for x in _live_docs(d) if x.get("kind") in _AUTOPILOT_KINDS]
    if not tagged:
        raise HTTPException(422, "Importe pelo menos uma planta/projeto ou um estudo geotécnico (botão de importação dedicado do piloto automático).")
    geom = await _collect_images(d, {"plan", "pc"}, dpi=_GEOM_DPI, per_doc=_GEOM_PER_DOC,
                                 total_cap=_GEOM_TOTAL_CAP, keywords=_GEOM_KEYWORDS)
    soil = await _collect_images(d, {"g2"}, dpi=_SOIL_DPI, per_doc=_SOIL_PER_DOC,
                                 total_cap=_SOIL_TOTAL_CAP, keywords=None)
    inputs = await autopilot.extract_inputs(geom, soil)
    d["autopilot"] = {"inputs": inputs, "extracted_at": _now(),
                      "source_docs": [x["id"] for x in tagged], "calc_study_id": d.get("autopilot", {}).get("calc_study_id")}
    await _save(d)
    return d


@router.put("/studies/{dossier_id}/autopilot/inputs")
async def autopilot_save_inputs(dossier_id: str, body: AutopilotInputsIn, user=Depends(current_user)) -> dict:
    d = await _get(dossier_id, user["user_id"])
    inputs = autopilot.normalize_inputs(body.model_dump(exclude_none=False))
    ap = d.get("autopilot") or {}
    ap["inputs"] = inputs
    ap["updated_at"] = _now()
    d["autopilot"] = ap
    await _save(d)
    return d


@router.post("/studies/{dossier_id}/autopilot/generate")
async def autopilot_generate(dossier_id: str, body: GenerateIn, user=Depends(current_user)) -> dict:
    """Construit un modèle déterministe, lance la descente de charges et crée une étude de calcul."""
    d = await _get(dossier_id, user["user_id"])
    raw = body.inputs.model_dump(exclude_none=False) if body.inputs else (d.get("autopilot") or {}).get("inputs")
    if not raw:
        raise HTTPException(422, "Analise os documentos ou preencha os dados antes de gerar.")
    try:
        out = await run_in_threadpool(autopilot.build_and_compute, raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if out["result"].get("status") == "blocked":
        raise HTTPException(422, {"message": "O pré-modelo não é calculável automaticamente.",
                                  "issues": out["result"].get("issues")})
    study_id = "strcalc_" + uuid.uuid4().hex
    study = {"study_id": study_id, "user_id": user["user_id"], "revision": 1,
             "plan_id": None, "source_updated_at": None, "page_count": 0, "page_readings": {},
             "model": out["model"], "result": out["result"],
             "autopilot_origin": {"dossier_id": dossier_id, "footing_sizes": out["footing_sizes"], "soil": out["soil"]},
             "created_at": _now(), "updated_at": _now()}
    await db.structuro_calculations.insert_one(dict(study))
    ap = d.get("autopilot") or {}
    ap["inputs"] = autopilot.normalize_inputs(raw)
    ap["calc_study_id"] = study_id
    ap["summary"] = out["summary"]
    ap["soil"] = out["soil"]
    ap["generated_at"] = _now()
    d["autopilot"] = ap
    await _save(d)
    return {"calc_study_id": study_id, "summary": out["summary"], "soil": out["soil"],
            "footing_sizes": out["footing_sizes"], "dossier": d}



@router.get("/studies/{dossier_id}/autopilot/coffrage.pdf")
async def autopilot_coffrage(dossier_id: str, user=Depends(current_user)):
    """Plantas de cofragem cotadas por piso + mapa de armaduras (a partir do estudo gerado)."""
    d = await _get(dossier_id, user["user_id"])
    ap = d.get("autopilot") or {}
    sid = ap.get("calc_study_id")
    if not sid:
        raise HTTPException(422, "Gere primeiro o modelo (botão «Aceitar e gerar»).")
    study = await db.structuro_calculations.find_one({"study_id": sid, "user_id": user["user_id"]}, {"_id": 0})
    if not study:
        raise HTTPException(404, "Estudo de cálculo não encontrado; relance a geração.")
    model = study.get("model") or {}
    summary = ap.get("summary") or {}
    superst = summary.get("superstructure")
    metre_data = summary.get("metre")
    soil = ap.get("soil") or (study.get("autopilot_origin") or {}).get("soil") or {}
    inputs = ap.get("inputs") or {}
    marks = autopilot.element_marks(model)
    pdf = await run_in_threadpool(build_coffrage_pdf, model, study.get("revision", 1),
                                  model.get("title", "Auto-pilote BET"), superst, metre_data, marks,
                                  summary, soil, inputs)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="cofragem-{dossier_id}.pdf"'})

