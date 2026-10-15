"""Étape 1 — API d'analyse documentaire vérifiable (XLSX + PDF).

- Import idempotent par empreinte de contenu (SHA-256) : ré-importer un fichier
  inchangé ne recrée pas de doublon et ne relance pas l'analyse.
- Isolation stricte par utilisateur/entreprise.
- Chaque donnée renvoie sa provenance (feuille!cellule ou page + zone).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from core.uploads import (
    validate_upload, ALLOWED_DOCUMENT, ALLOWED_IMAGE, ALLOWED_IMPORT, ALLOWED_OFFICE,
)
from engines import doc_intel, storage, doc_reconcile, gemini_ocr
from engines.access import require_level

router = APIRouter(prefix="/doc-intel", tags=["doc-intel"], dependencies=[Depends(require_level("pro"))])

MAX_BYTES = 30 * 1024 * 1024  # 30 Mo

IMAGE_EXTS = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _merge_ocr(result: dict, ocr_data: dict) -> dict:
    """Fusionne la lecture IA (OCR) dans le résultat : lignes de texte par page,
    pages marquées, champs structurés relevés, avertissements. Aucune arithmétique."""
    result["ocr"] = {k: ocr_data.get(k) for k in ("engine", "model", "document", "line_items", "warnings")}
    existing = {p.get("page"): p for p in (result.get("pages") or [])}
    lines = result.setdefault("lines", [])
    for p in ocr_data.get("pages") or []:
        pg, txt = p.get("page"), p.get("text") or ""
        n = 0
        for raw_line in txt.splitlines():
            t = raw_line.strip()
            if not t:
                continue
            n += 1
            lines.append({"line_id": f"ocr_p{pg}_{n}", "page": pg, "text": t[:1000], "ocr": True})
        if pg in existing:
            existing[pg]["scanned"] = True
            existing[pg]["ocr"] = True
            existing[pg]["lines"] = (existing[pg].get("lines") or 0) + n
        else:
            result.setdefault("pages", []).append(
                {"page": pg, "lines": n, "scanned": True, "ocr": True, "images": 1, "tables": 0})
    for w in ocr_data.get("warnings") or []:
        result.setdefault("warnings", []).append({"type": "ocr", "message": w})
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope(user: dict) -> dict:
    """Filtre d'isolation : par entreprise si disponible, sinon par utilisateur."""
    cid = user.get("company_id")
    return {"company_id": cid} if cid else {"user_id": user["user_id"]}


def _summary(doc: dict) -> dict:
    ex = doc.get("result") or {}
    arith = (ex.get("arithmetic") or {}).get("summary") if ex else None
    return {
        "import_id": doc["import_id"], "filename": doc.get("filename"),
        "format": doc.get("format"), "language": ex.get("language"),
        "status": doc.get("status"), "created_at": doc.get("created_at"),
        "warnings": len(ex.get("warnings") or []), "unread": len(ex.get("unread") or []),
        "lines": len(ex.get("lines") or []),
        "ocr": (ex.get("ocr") or {}).get("engine"),
        "arithmetic": arith,
    }


@router.post("/import")
async def import_document(file: UploadFile = File(...),
                         vat_rate: float | None = Form(default=None),
                         project_id: str | None = Form(default=None),
                         force: bool = Form(default=False),
                         user=Depends(current_user)) -> dict:
    filename = getattr(file, "filename", "") or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    is_image = ext in IMAGE_EXTS
    if ext not in ("xlsx", "xlsm", "pdf") and not is_image:
        raise HTTPException(400, "Anexe um ficheiro .xlsx, .pdf ou uma imagem (JPG/PNG/WEBP)")
    file = await validate_upload(
        file,
        ALLOWED_DOCUMENT + ALLOWED_IMAGE + ALLOWED_IMPORT + ALLOWED_OFFICE,
        max_mb=MAX_BYTES // (1024 * 1024),
    )
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Ficheiro vazio")
    if len(raw) > MAX_BYTES:
        raise HTTPException(400, "Ficheiro demasiado volumoso (máx. 30 MB nesta etapa)")

    sha = hashlib.sha256(raw).hexdigest()

    # Idempotence : même contenu déjà analysé pour ce périmètre → on renvoie l'existant.
    if not force:
        existing = await db.doc_imports.find_one(
            {**_scope(user), "content_sha256": sha, "status": "done"}, {"_id": 0})
        if existing:
            return {"reused": True, **existing}

    import_id = "doc_" + uuid.uuid4().hex[:12]
    fmt = "image" if is_image else ("pdf" if ext == "pdf" else "xlsx")

    # Préserver l'original (best-effort : n'échoue pas si le stockage n'est pas configuré).
    file_ref, store_warn = None, None
    try:
        file_ref = storage.put_object(
            f"doc_intel/{user['user_id']}/{import_id}/{filename}", raw,
            storage.mime_for(filename, "application/octet-stream"))
    except Exception as exc:  # pragma: no cover
        store_warn = f'Original não arquivado ({type(exc).__name__})'

    doc = {
        "import_id": import_id, "user_id": user["user_id"],
        "company_id": user.get("company_id"), "project_id": project_id,
        "author": user.get("email") or user.get("user_id"),
        "filename": filename, "content_sha256": sha, "size": len(raw),
        "format": fmt, "file_ref": file_ref,
        "status": "processing", "created_at": _now(), "updated_at": _now(),
    }
    await db.doc_imports.insert_one(dict(doc))

    try:
        if is_image:
            # Une image = toujours OCR (facture/devis/CCTP photographié).
            mime = IMAGE_EXTS[ext]
            result = {"format": "image", "language": None, "pages": [], "lines": [],
                      "tables": [], "warnings": [], "unread": [],
                      "engine_version": doc_intel.ENGINE_VERSION, "arithmetic": None}
            if not gemini_ocr.available():
                raise RuntimeError("Leitura IA (OCR) não configurada")
            ocr_data = await gemini_ocr.ocr(raw, mime, filename)
            _merge_ocr(result, ocr_data)
        else:
            result = doc_intel.analyse(raw, filename, vat_rate=vat_rate)
            # OCR automatique des pages PDF scannées (sans texte natif).
            scanned = any(p.get("scanned") for p in (result.get("pages") or []))
            if scanned and gemini_ocr.available():
                try:
                    ocr_data = await gemini_ocr.ocr(raw, "application/pdf", filename)
                    _merge_ocr(result, ocr_data)
                except Exception as exc:  # pragma: no cover
                    result.setdefault("warnings", []).append(
                        {"type": "ocr", "message": f'OCR indisponível: {type(exc).__name__}'})
        if store_warn:
            result.setdefault("warnings", []).append({"type": "storage", "message": store_warn})
        await db.doc_imports.update_one(
            {"import_id": import_id},
            {"$set": {"status": "done", "result": result,
                      "extraction": {"method": result.get("format"),
                                     "version": result.get("engine_version"),
                                     "ocr_engine": (result.get("ocr") or {}).get("engine"),
                                     "duration_ms": result.get("duration_ms")},
                      "updated_at": _now()}})
    except Exception as exc:
        await db.doc_imports.update_one(
            {"import_id": import_id},
            {"$set": {"status": "error", "error": str(exc)[:500], "updated_at": _now()}})
        raise HTTPException(422, f'Análise impossível: {exc}')

    doc = await db.doc_imports.find_one({"import_id": import_id}, {"_id": 0})
    return {"reused": False, **doc}


@router.get("")
async def list_imports(user=Depends(current_user)) -> list[dict]:
    cur = db.doc_imports.find(_scope(user), {"_id": 0}).sort("created_at", -1).limit(200)
    return [_summary(d) async for d in cur]


class CorrectionIn(BaseModel):
    signature: str
    resolution: str = Field(default="resolved")   # resolved | ignored | note
    scope: str = Field(default="document")         # document | chantier | entreprise
    kind: str = Field(default="error")             # error | preference | exception
    justification: str | None = Field(default=None, max_length=500)
    import_id: str | None = None


@router.post("/corrections")
async def add_correction(body: CorrectionIn, user=Depends(current_user)) -> dict:
    doc = {"user_id": user["user_id"], "company_id": user.get("company_id"),
           "signature": body.signature, "resolution": body.resolution, "scope": body.scope,
           "kind": body.kind, "justification": body.justification, "import_id": body.import_id,
           "author": user.get("email") or user.get("user_id"), "active": True, "updated_at": _now()}
    await db.doc_corrections.update_one(
        {**_scope(user), "signature": body.signature, "scope": body.scope},
        {"$set": doc, "$setOnInsert": {"correction_id": "cor_" + uuid.uuid4().hex[:12],
                                       "created_at": _now()}},
        upsert=True)
    saved = await db.doc_corrections.find_one({**_scope(user), "signature": body.signature,
                                               "scope": body.scope}, {"_id": 0})
    return {"ok": True, "correction": saved}


@router.get("/corrections")
async def list_corrections(user=Depends(current_user)) -> list[dict]:
    return [c async for c in db.doc_corrections.find(_scope(user), {"_id": 0})
            .sort("created_at", -1).limit(500)]


@router.delete("/corrections/{correction_id}")
async def delete_correction(correction_id: str, user=Depends(current_user)) -> dict:
    res = await db.doc_corrections.delete_one({**_scope(user), "correction_id": correction_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Correção não encontrada")
    return {"ok": True}


@router.get("/{import_id}")
async def get_import(import_id: str, user=Depends(current_user)) -> dict:
    doc = await db.doc_imports.find_one({**_scope(user), "import_id": import_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Análise não encontrada")
    return doc


@router.delete("/{import_id}")
async def delete_import(import_id: str, user=Depends(current_user)) -> dict:
    res = await db.doc_imports.delete_one({**_scope(user), "import_id": import_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Análise não encontrada")
    return {"ok": True}


# ===================== ÉTAPE 2 — Rapprochement CCTP ↔ DPGF/devis =====================

@router.post("/{import_id}/reconcile")
async def reconcile(import_id: str,
                    cctp: UploadFile | None = File(default=None),
                    cctp_import_id: str | None = Form(default=None),
                    user=Depends(current_user)) -> dict:
    base = await db.doc_imports.find_one({**_scope(user), "import_id": import_id}, {"_id": 0})
    if not base:
        raise HTTPException(404, "Análise de mapa de quantidades/orçamento não encontrada")
    if base.get("format") != "xlsx":
        raise HTTPException(400, "A conciliação parte de um mapa de quantidades/orçamento Excel")
    devis_lines = (base.get("result") or {}).get("lines") or []

    if cctp is not None and getattr(cctp, "filename", None):
        if not cctp.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "O caderno de encargos deve ser um PDF")
        cctp = await validate_upload(
            cctp, ALLOWED_DOCUMENT, max_mb=MAX_BYTES // (1024 * 1024))
        raw = await cctp.read()
        if len(raw) > MAX_BYTES:
            raise HTTPException(400, "Caderno de encargos demasiado volumoso (máx. 30 MB)")
        pres_lines = doc_intel.analyse(raw, cctp.filename).get("lines") or []
        cctp_ref = {"filename": cctp.filename}
    elif cctp_import_id:
        c = await db.doc_imports.find_one({**_scope(user), "import_id": cctp_import_id}, {"_id": 0})
        if not c:
            raise HTTPException(404, "Caderno de encargos não encontrado")
        if c.get("format") != "pdf":
            raise HTTPException(400, "O caderno de encargos referenciado deve ser um PDF")
        pres_lines = (c.get("result") or {}).get("lines") or []
        cctp_ref = {"import_id": cctp_import_id, "filename": c.get("filename")}
    else:
        raise HTTPException(400, "Forneça um caderno de encargos (ficheiro PDF ou cctp_import_id)")

    prescriptions = doc_reconcile.extract_prescriptions(pres_lines)
    corrections = [c async for c in db.doc_corrections.find(_scope(user), {"_id": 0})]

    # Appoint sémantique (meilleur effort) : embeddings des libellés au-delà des mots-clés.
    vectors = {}
    try:
        from engines import doc_embeddings
        if doc_embeddings.available():
            texts = [l.get("designation") or "" for l in devis_lines if l.get("kind") == "detail"]
            texts += [p["text"] for p in prescriptions]
            vectors = await doc_embeddings.get_or_embed(texts)
    except Exception:
        vectors = {}

    result = doc_reconcile.reconcile(devis_lines, prescriptions, corrections, vectors=vectors or None)
    result["cctp"] = cctp_ref
    await db.doc_imports.update_one({"import_id": import_id},
                                    {"$set": {"reconciliation": result, "updated_at": _now()}})
    return result


class PlanReconcileIn(BaseModel):
    plan_id: str
    page_index: int | None = None


@router.post("/{import_id}/plan-reconcile")
async def plan_reconcile(import_id: str, body: PlanReconcileIn,
                         user=Depends(current_user)) -> dict:
    """Compare les quantités MESURÉES sur un plan (métré) au devis/DPGF importé,
    par libellé, et signale les écarts sourcés (m² / ml). Déterministe."""
    base = await db.doc_imports.find_one({**_scope(user), "import_id": import_id}, {"_id": 0})
    if not base:
        raise HTTPException(404, "Análise de mapa de quantidades/orçamento não encontrada")
    if base.get("format") != "xlsx":
        raise HTTPException(400, "A conciliação parte de um mapa de quantidades/orçamento Excel")
    devis_lines = (base.get("result") or {}).get("lines") or []

    plan = await db.plans_takeoff.find_one(
        {"plan_id": body.plan_id, "user_id": user["user_id"]},
        {"_id": 0, "measurements": 1, "filename": 1, "structural_metre": 1})
    if not plan:
        raise HTTPException(404, "Planta não encontrada")
    measurements = plan.get("measurements") or []
    if body.page_index is not None:
        measurements = [m for m in measurements if m.get("page_index") == body.page_index]
    # Appoint CAD/DXF : quantités des calques (murs, dalle, escaliers…) si présentes.
    dxf_cotes = doc_reconcile.dxf_pseudo_measurements(plan.get("structural_metre"))
    measurements = measurements + dxf_cotes

    vectors = {}
    try:
        from engines import doc_embeddings
        if doc_embeddings.available():
            texts = [m.get("label") or "" for m in measurements if (m.get("label") or "").strip()]
            texts += [l.get("designation") or "" for l in devis_lines if l.get("kind") == "detail"]
            vectors = await doc_embeddings.get_or_embed(texts)
    except Exception:
        vectors = {}

    result = doc_reconcile.reconcile_plan(measurements, devis_lines, plan_id=body.plan_id,
                                          vectors=vectors or None)
    result["plan"] = {"plan_id": body.plan_id, "filename": plan.get("filename"),
                      "dxf_metre": bool(dxf_cotes)}
    await db.doc_imports.update_one(
        {"import_id": import_id},
        {"$set": {"plan_reconciliation": result, "updated_at": _now()}})
    return result


class LineQtyIn(BaseModel):
    qty: float = Field(ge=0)


@router.patch("/{import_id}/lines/{line_id}")
async def correct_line_qty(import_id: str, line_id: str, body: LineQtyIn,
                           user=Depends(current_user)) -> dict:
    """Corrige la quantité d'une ligne du devis/DPGF importé (ex. aligner sur le
    métré du plan). Recalcule le montant de la ligne (si PU connu) et l'arithmétique.
    La correction est tracée (`qty_corrected_from`)."""
    doc = await db.doc_imports.find_one({**_scope(user), "import_id": import_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Análise não encontrada")
    result = doc.get("result") or {}
    lines = result.get("lines") or []
    line = next((l for l in lines if l.get("line_id") == line_id), None)
    if not line:
        raise HTTPException(404, "Linha não encontrada")
    old = (line.get("qty") or {}).get("value")
    line["qty"] = {"value": float(body.qty), "status": "ok", "raw": str(body.qty), "corrected": True}
    line["qty_corrected_from"] = old
    pu = (line.get("pu") or {}).get("value")
    if pu is not None:
        amt = round(float(body.qty) * float(pu), 2)
        line["amount"] = {"value": amt, "status": "ok", "raw": str(amt), "recomputed": True}
    vat = ((result.get("arithmetic") or {}).get("summary") or {}).get("vat_rate")
    result["arithmetic"] = doc_intel.arithmetic_check(lines, vat)
    await db.doc_imports.update_one(
        {"import_id": import_id}, {"$set": {"result": result, "updated_at": _now()}})
    return {"ok": True, "line_id": line_id, "qty": float(body.qty), "old_qty": old,
            "designation": line.get("designation")}


async def _run_plan_reconcile(base: dict, plan: dict, plan_id: str) -> dict:
    devis_lines = (base.get("result") or {}).get("lines") or []
    measurements = plan.get("measurements") or []
    measurements = measurements + doc_reconcile.dxf_pseudo_measurements(plan.get("structural_metre"))
    vectors = {}
    try:
        from engines import doc_embeddings
        if doc_embeddings.available():
            texts = [m.get("label") or "" for m in measurements if (m.get("label") or "").strip()]
            texts += [l.get("designation") or "" for l in devis_lines if l.get("kind") == "detail"]
            vectors = await doc_embeddings.get_or_embed(texts)
    except Exception:
        vectors = {}
    res = doc_reconcile.reconcile_plan(measurements, devis_lines, plan_id=plan_id,
                                       vectors=vectors or None)
    res["plan"] = {"plan_id": plan_id, "filename": plan.get("filename"),
                   "dxf_metre": bool(plan.get("structural_metre"))}
    return res


@router.post("/{import_id}/plan-reconcile/apply-all")
async def plan_reconcile_apply_all(import_id: str, body: PlanReconcileIn,
                                   user=Depends(current_user)) -> dict:
    """« Tout corriger » : aligne d'un coup toutes les quantités de devis en écart (> 5 %)
    sur le métré du plan, recalcule montants + arithmétique, puis renvoie le rapprochement à jour."""
    base = await db.doc_imports.find_one({**_scope(user), "import_id": import_id}, {"_id": 0})
    if not base:
        raise HTTPException(404, "Análise não encontrada")
    plan = await db.plans_takeoff.find_one(
        {"plan_id": body.plan_id, "user_id": user["user_id"]},
        {"_id": 0, "measurements": 1, "filename": 1, "structural_metre": 1})
    if not plan:
        raise HTTPException(404, "Planta não encontrada")

    rec = await _run_plan_reconcile(base, plan, body.plan_id)
    result = base.get("result") or {}
    lines = result.get("lines") or []
    by_id = {l.get("line_id"): l for l in lines}
    corrected = 0
    for c in rec.get("comparisons", []):
        if not c.get("flag") or not c.get("devis_line_id"):
            continue
        line = by_id.get(c["devis_line_id"])
        if not line:
            continue
        old = (line.get("qty") or {}).get("value")
        line["qty"] = {"value": c["measured"], "status": "ok", "raw": str(c["measured"]), "corrected": True}
        line["qty_corrected_from"] = old
        pu = (line.get("pu") or {}).get("value")
        if pu is not None:
            amt = round(float(c["measured"]) * float(pu), 2)
            line["amount"] = {"value": amt, "status": "ok", "raw": str(amt), "recomputed": True}
        corrected += 1

    if corrected:
        vat = ((result.get("arithmetic") or {}).get("summary") or {}).get("vat_rate")
        result["arithmetic"] = doc_intel.arithmetic_check(lines, vat)
        await db.doc_imports.update_one(
            {"import_id": import_id}, {"$set": {"result": result, "updated_at": _now()}})

    base["result"] = result
    fresh = await _run_plan_reconcile(base, plan, body.plan_id)
    await db.doc_imports.update_one(
        {"import_id": import_id}, {"$set": {"plan_reconciliation": fresh, "updated_at": _now()}})
    fresh["corrected"] = corrected
    return fresh
