"""Routes du solveur de problèmes BTP.

- ``POST /api/btp-solver/solve`` : diagnostic complet + solutions + graphiques
- ``GET  /api/btp-solver/history`` : historique des diagnostics
- ``GET  /api/btp-solver/{problem_id}`` : détail d'un diagnostic
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from btp_solver import photos as photo_store
from btp_solver.report_pdf import build_solver_pdf
from btp_solver.solver import solve
from core.db import db
from core.permissions import permissions_for
from core.rate_limit import limiter
from core.security import current_user, pro_required
from routes.documents import DocIn, DocLine

router = APIRouter(prefix="/btp-solver", tags=["btp-solver"])
logger = logging.getLogger(__name__)
DOMAIN_LABELS = {"fissures": "Fissures", "humidite": "Humidité", "thermique": "Thermique", "structure": "Structure",
                 "sinistre": "Sinistre", "reception": "Réception", "autre": "Travaux"}


class SolveIn(BaseModel):
    description: str = Field(..., min_length=10, max_length=4000)
    photos_urls: Optional[list[str]] = None
    photo_ids: list[str] = Field(default_factory=list, max_length=photo_store.MAX_PHOTOS)
    region: Optional[str] = None
    type_batiment: Optional[str] = None
    surface_m2: Optional[float] = Field(None, gt=0, lt=100000)
    age_annees: Optional[int] = Field(None, ge=0, le=1000)
    urgence_ressentie: Optional[str] = None
    budget_max_eur: Optional[float] = Field(None, ge=0, le=100_000_000)
    chantier_id: Optional[str] = Field(None, max_length=40)


@router.post("/photos")
@limiter.limit("30/hour")
async def upload_photo(request: Request, response: Response, file: UploadFile = File(...), user=Depends(current_user)):
    data = await file.read(photo_store.MAX_PHOTO_MB * 1024 * 1024 + 1)
    if not data:
        raise HTTPException(400, "Photo vide")
    return await photo_store.store_photo(user["user_id"], data)


@router.get("/photos/{photo_id}")
async def get_photo(photo_id: str, user=Depends(current_user)):
    data, mime = await photo_store.photo_bytes(user["user_id"], photo_id)
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


class ToQuoteIn(BaseModel):
    solution_id: Optional[str] = None


@router.post("/{problem_id}/to-quote")
async def to_quote(problem_id: str, body: ToQuoteIn, user=Depends(pro_required)):
    """Transforme la solution recommandée (ou choisie) du diagnostic en brouillon de devis."""
    if not permissions_for(user)["devis"]:
        raise HTTPException(403, "Votre rôle ne permet pas de créer des devis.")
    doc = await db.btp_problems.find_one({"problem_id": problem_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Diagnostic introuvable")
    if doc.get("status") != "done" or not doc.get("solutions"):
        raise HTTPException(409, "Diagnostic non terminé")
    sols = doc["solutions"]
    sol = next((s for s in sols if s.get("id") == body.solution_id), None) if body.solution_id else None
    sol = sol or next((s for s in sols if s.get("recommended")), sols[0])
    steps = sorted(sol.get("steps") or [], key=lambda s: s.get("order") or 0)
    mid = round(((sol.get("cost_min_eur") or 0) + (sol.get("cost_max_eur") or sol.get("cost_min_eur") or 0)) / 2, 2)
    n = max(1, len(steps))
    lines = []
    for i, st in enumerate(steps or [{"text": sol["label"], "materials": []}]):
        price = round(mid / n, 2) if i < n - 1 else round(mid - round(mid / n, 2) * (n - 1), 2)
        lines.append(DocLine(designation=(st.get("text") or sol["label"])[:160], description=", ".join(st.get("materials") or [])[:400],
                             unit="forfait", qty=1, unit_price_ht=max(price, 0), vat_rate=10, category=DOMAIN_LABELS.get(doc.get("domain"), "Travaux"),
                             price_source="btp_solver_estimate"))
    notes = (f"Brouillon généré depuis le diagnostic ConstruPilot {problem_id} — solution « {sol['label']} ».\n"
             f"Chiffrage provisionnel (fourchette {sol.get('cost_min_eur') or '—'} € à {sol.get('cost_max_eur') or '—'} € HT, milieu retenu) à ajuster après visite technique. "
             f"Durée estimée : {sol.get('duration_days_min') or '—'}–{sol.get('duration_days_max') or sol.get('duration_days_min') or '—'} jours."
             + (f" Garantie : {sol['warranty_years']} ans." if sol.get("warranty_years") else ""))
    from routes.documents import create_document
    quote = await create_document(DocIn(doc_type="quote", title=f"Devis — {sol['label']}"[:160], lines=lines, notes=notes), user)
    await db.pro_documents.update_one({"doc_id": quote["doc_id"]}, {"$set": {"source": "btp_solver", "source_ref": problem_id}})
    await db.btp_problems.update_one({"problem_id": problem_id}, {"$addToSet": {"quote_doc_ids": quote["doc_id"]}})
    return {"doc_id": quote["doc_id"], "title": quote["title"], "lines": len(lines), "total_ht": quote["totals"].get("ht"),
            "url": f"/devis-editeur/{quote['doc_id']}"}


@router.get("/{problem_id}/report.pdf")
async def report_pdf(problem_id: str, user=Depends(current_user)):
    doc = await db.btp_problems.find_one({"problem_id": problem_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Diagnostic introuvable")
    if doc.get("status") != "done":
        raise HTTPException(409, "Diagnostic non terminé")
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(user["user_id"])
    photos = []
    for p in await photo_store.load_photos(user["user_id"], doc.get("photo_ids") or []):
        photos.append(p["data"])
    pdf = await asyncio.to_thread(build_solver_pdf, doc, branding, photos)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="diagnostic-{problem_id[-6:]}.pdf"', "Cache-Control": "private, no-store"})


@router.post("/solve")
@limiter.limit("10/hour")
async def solve_problem(body: SolveIn, request: Request, response: Response,
                        background: BackgroundTasks, wait: bool = False,
                        user=Depends(current_user)):
    context = {
        "region": body.region,
        "type_batiment": body.type_batiment,
        "surface_m2": body.surface_m2,
        "age_annees": body.age_annees,
        "urgence_ressentie": body.urgence_ressentie,
        "budget_max_eur": body.budget_max_eur,
    }
    photos = await photo_store.load_photos(user["user_id"], body.photo_ids)
    from routes.chantiers import owned_chantier_id
    chantier_id = await owned_chantier_id(user["user_id"], body.chantier_id)
    problem_id = f"prob_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    await db.btp_problems.insert_one({
        "problem_id": problem_id,
        "user_id": user["user_id"],
        "status": "running",
        "chantier_id": chantier_id,
        "description": body.description,
        "context": context,
        "photo_ids": [p["photo_id"] for p in photos],
        "created_at": now,
        "generated_at_iso": now.isoformat(),
    })
    if wait:
        return await _run_solve(problem_id, body.description, body.photos_urls, context, photos)
    background.add_task(_run_solve, problem_id, body.description, body.photos_urls, context, photos)
    response.status_code = 202
    return {"problem_id": problem_id, "status": "running"}


async def _run_solve(problem_id: str, description: str, photos_urls, context: dict, photos: list[dict]) -> dict:
    try:
        photo_analysis = await photo_store.analyze_photos(photos, description)
        if photo_analysis:
            await db.btp_problems.update_one({"problem_id": problem_id}, {"$set": {"photo_analysis": photo_analysis}})
        resp = await solve(description=description, photos_urls=photos_urls, context=context, photo_analysis=photo_analysis)
    except Exception:
        logger.exception("btp_solver failed for %s", problem_id)
        await db.btp_problems.update_one(
            {"problem_id": problem_id},
            {"$set": {"status": "error", "error": "Analyse indisponible momentanément, réessayez dans quelques instants."}},
        )
        return {"problem_id": problem_id, "status": "error"}
    doc = resp.model_dump()
    doc["problem_id"] = problem_id
    doc["status"] = "done"
    doc["photo_analysis"] = photo_analysis
    await db.btp_problems.update_one({"problem_id": problem_id}, {"$set": doc})
    return doc


@router.get("/history")
async def history(limit: int = 20, user=Depends(current_user)):
    items = await db.btp_problems.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "user_id": 0, "created_at": 0, "charts": 0, "action_plan": 0},
    ).sort("generated_at_iso", -1).to_list(max(1, min(limit, 100)))
    return {"items": items}


@router.get("/{problem_id}")
async def detail(problem_id: str, user=Depends(current_user)):
    doc = await db.btp_problems.find_one(
        {"problem_id": problem_id, "user_id": user["user_id"]},
        {"_id": 0, "user_id": 0, "created_at": 0},
    )
    if not doc:
        raise HTTPException(404, "Diagnostic introuvable")
    return doc
