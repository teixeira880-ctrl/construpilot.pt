"""ConstruPilot IA BTP — /api/btp-ai : traceable plan analysis (elements, quantities, proofs), corrections, quote draft, documented research."""
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from btp_ai import metre
from btp_ai.research import configured, search_technical_docs
from core.db import db
from core.rate_limit import limiter
from core.security import current_user

router = APIRouter(prefix="/btp-ai", tags=["btp-ai"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _plan(plan_id: str, user: dict) -> dict:
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages.image_png_b64": 0, "pages.vectors": 0, "pages.text_blocks": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    return p


@router.get("/plans/{plan_id}/analysis")
async def get_analysis(plan_id: str, user=Depends(current_user)) -> dict:
    p = await _plan(plan_id, user)
    a = await db.btp_analyses.find_one({"plan_id": plan_id}, {"_id": 0})
    if not a or a.get("revision") != metre.revision_of(p):
        await metre.rebuild(p, user["user_id"])
        a = await db.btp_analyses.find_one({"plan_id": plan_id}, {"_id": 0})
    elements = await db.btp_elements.find({"plan_id": plan_id}, {"_id": 0}).to_list(2000)
    lines = await db.btp_quantities.find({"plan_id": plan_id, "superseded": {"$ne": True}}, {"_id": 0}).to_list(5000)
    overrides = await db.btp_overrides.find({"plan_id": plan_id}, {"_id": 0}).to_list(500)
    pages = [{"index": pg.get("index", i), "width_px": pg.get("width_px"), "height_px": pg.get("height_px"), "calibrated": str(pg.get("index", i)) in (p.get("calibrations") or {})} for i, pg in enumerate(p.get("pages") or [])]
    stat = {s: sum(1 for q in lines if q["status"] == s) for s in ("to_verify", "provisional", "validated", "undetermined")}
    return {"plan": {"plan_id": plan_id, "filename": p.get("filename"), "project_id": p.get("project_id"), "updated_at": p.get("updated_at"), "pages": pages}, "analysis": a, "elements": elements, "quantities": lines,
            "overrides": overrides, "stats": stat, "state": "en erreur" if not elements and (p.get("rooms")) else ("partiellement analysé" if a.get("missing") else "analysé"),
            "disclaimer": "Contrôle de cohérence et métré à partir des pièces tracées et calibrées du plan. Ne constitue pas une note de calcul structurel."}


@router.post("/plans/{plan_id}/rebuild")
async def rebuild(plan_id: str, user=Depends(current_user)) -> dict:
    return await metre.rebuild(await _plan(plan_id, user), user["user_id"])


class OverrideIn(BaseModel):
    hauteur_m: float | None = Field(None, gt=0, lt=20)
    epaisseur_m: float | None = Field(None, gt=0, lt=2)
    reason: str = Field("", max_length=300)


@router.put("/plans/{plan_id}/elements/{element_id}/assumptions")
async def set_assumption(plan_id: str, element_id: str, body: OverrideIn, user=Depends(current_user)) -> dict:
    """Explicit, visible assumption for a missing dimension (never a silent default). Dependent lines are recomputed as « provisoire »."""
    p = await _plan(plan_id, user)
    if not await db.btp_elements.find_one({"plan_id": plan_id, "element_id": element_id}):
        raise HTTPException(404, "Ouvrage introuvable")
    sets = {k: v for k, v in body.model_dump().items() if v is not None and k != "reason"}
    if not sets:
        await db.btp_overrides.delete_one({"plan_id": plan_id, "element_id": element_id})
    else:
        await db.btp_overrides.update_one({"plan_id": plan_id, "element_id": element_id}, {"$set": {"plan_id": plan_id, "element_id": element_id, **sets, "reason": body.reason, "by": user.get("email") or user["user_id"], "at": _now()}}, upsert=True)
    return await metre.rebuild(p, user["user_id"])


class ReviewIn(BaseModel):
    status: Literal["validated", "to_verify", "rejected"]
    quantity_override: float | None = Field(None, ge=0, le=1e10, allow_inf_nan=False)
    comment: str = Field("", max_length=300)


@router.put("/plans/{plan_id}/quantities/{quantity_id}")
async def review_quantity(plan_id: str, quantity_id: str, body: ReviewIn, user=Depends(current_user)) -> dict:
    q = await db.btp_quantities.find_one({"plan_id": plan_id, "quantity_id": quantity_id, "superseded": {"$ne": True}, "user_id": user["user_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Ligne introuvable")
    sets = {"status": body.status, "reviewed_by": user.get("email") or user["user_id"], "reviewed_at": _now(), "comment": body.comment}
    if body.status == "validated":
        sets.update({"validated_by": sets["reviewed_by"], "validated_at": sets["reviewed_at"]})
    if body.quantity_override is not None:
        sets.update({"quantity_computed": q.get("quantity_net"), "quantity_net": body.quantity_override, "quantity_to_order": round(body.quantity_override * (1 + (q.get("waste_pct") or 0) / 100), 3), "manual_correction": True})
    await db.btp_quantities.update_one({"plan_id": plan_id, "quantity_id": quantity_id, "superseded": {"$ne": True}}, {"$set": sets})
    return {"ok": True, **sets}


@router.post("/plans/{plan_id}/quote-draft")
async def quote_draft(plan_id: str, client_name: str = Body("", embed=True), include_undetermined: bool = Body(False, embed=True), user=Depends(current_user)) -> dict:
    """Editable quote draft in « Suivi devis » built from the current lines (quantities kept traceable via line_id = quantity_id)."""
    from engines.assistant_quote_service import save_quote
    p = await _plan(plan_id, user)
    lines = await db.btp_quantities.find({"plan_id": plan_id, "superseded": {"$ne": True}, "status": {"$ne": "rejected"}}, {"_id": 0}).to_list(500)
    usable = [q for q in lines if q.get("quantity_net") is not None or include_undetermined]
    if not usable:
        raise HTTPException(400, "Aucune quantité déterminée à reporter")
    conv = {"conversation_id": f"conv_btp_{plan_id[-8:]}", "user_id": user["user_id"], "_quote_request_id": uuid.uuid4().hex}
    if p.get("chantier_id"):
        from routes.chantiers import _get
        chantier = await _get(p["chantier_id"], user["user_id"])
        conv["_chantier"] = {"chantier_id": chantier["chantier_id"], "client_id": chantier.get("client_id")}

    q_lines = [{"line_id": None, "designation": q["designation"], "description": f"Métré {q['quantity_id']} · {q['formula']} · {q['rule_version']} · statut {q['status']}" + (f" · hypothèses : {', '.join(a['name'] + '=' + str(a['value']) + a['unit'] for a in q['assumptions'])}" if q.get("assumptions") else ""),
                "quantity": q.get("quantity_to_order"), "unit": q["unit"], "unit_price": None, "price_origin": "unpriced", "vat_rate": None, "lot": q["lot"]} for q in usable]
    args = {"title": f"Devis d'après métré — {p.get('filename') or plan_id}", "client_name": client_name or "", "vat_rate": None, "lines": q_lines,
            "notes": f"Brouillon généré depuis l'analyse traçable du plan {plan_id} (révision {metre.revision_of(p)}). Prix à compléter depuis la bibliothèque ; quantités indéterminées non reportées." if not include_undetermined else f"Brouillon depuis le plan {plan_id} ; certaines quantités sont indéterminées (à compléter)."}
    res = await save_quote(args, user, conv)
    doc_id = res.get("doc_id") if isinstance(res, dict) else getattr(res, "doc_id", None)
    await db.btp_quantities.update_many({"quantity_id": {"$in": [q["quantity_id"] for q in usable]}, "superseded": {"$ne": True}}, {"$addToSet": {"dependent_documents": doc_id}})
    return {"ok": True, "doc_id": doc_id, "lines": len(q_lines), "skipped_undetermined": len(lines) - len(usable), "editor_url": f"/devis-editeur/{doc_id}", "tracking_url": f"/devis?highlight={doc_id}"}


class ResearchIn(BaseModel):
    question: str = Field(min_length=8, max_length=1500)
    country: Literal["FR", "PT"] = "FR"
    project_id: str | None = None
    preset: Literal["fast", "low", "medium", "high"] = "medium"


@router.get("/research/status")
async def research_status(user=Depends(current_user)) -> dict:
    return configured()


@router.post("/research")
@limiter.limit("15/hour")
async def research(body: ResearchIn, request: Request, response: Response, user=Depends(current_user)) -> dict:
    res = await search_technical_docs(body.question, body.country, user["user_id"], body.project_id, body.preset)
    if not res.get("ok"):
        raise HTTPException(503, res.get("error"))
    return res


@router.get("/research")
async def research_history(limit: int = 20, user=Depends(current_user)) -> dict:
    return {"items": await db.btp_research.find({"user_id": user["user_id"]}, {"_id": 0}).sort("at", -1).to_list(min(limit, 100))}


# ---------- revisions, quote impact, amendment ----------
@router.get("/plans/{plan_id}/revisions")
async def revisions(plan_id: str, user=Depends(current_user)) -> dict:
    await _plan(plan_id, user)
    revs = await db.btp_revisions.find({"plan_id": plan_id}, {"_id": 0, "lines": 0}).sort("at", -1).to_list(50)
    return {"revisions": revs}


async def _quote_prices(plan_id: str, user_id: str) -> dict:
    """quantity_id → (doc_id, number, unit_price_ht) for quote lines created from this plan (description « Métré q_… »)."""
    doc_ids = set()
    async for q in db.btp_quantities.find({"plan_id": plan_id, "user_id": user_id, "dependent_documents.0": {"$exists": True}}, {"_id": 0, "dependent_documents": 1}):
        doc_ids.update(d for d in q["dependent_documents"] if d)
    out = {}
    from engines.chantier_costs import number, EXCLUDED_QUOTES
    async for d in db.pro_documents.find({"doc_id": {"$in": list(doc_ids)}, "user_id": user_id, "doc_type": "quote", "trashed_at": None}, {"_id": 0, "doc_id": 1, "number": 1, "status": 1, "lines": 1, "title": 1}):
        if d.get("status") in EXCLUDED_QUOTES:
            continue
        for ln in d.get("lines") or []:
            desc = ln.get("description") or ""
            if desc.startswith("Métré q_") and ln.get("price_source") != "revision_reference":
                qid = desc.split()[1]
                price, discount = number(ln.get("unit_price_ht")), number(ln.get("discount_pct", 0))
                usable = not ln.get("price_missing") and price is not None and discount is not None and 0 <= discount <= 100
                row = {"doc_id": d["doc_id"], "number": d.get("number"), "status": d.get("status"), "title": d.get("title"),
                       "unit_price_ht": round(price * (1 - discount / 100), 6) if usable else None,
                       "unit": ln.get("unit"), "quantity": number(ln.get("qty")), "ambiguous": False}
                if qid in out:
                    out[qid].update(ambiguous=True, unit_price_ht=None)
                else:
                    out[qid] = row
    return out


async def _diff(plan_id: str, a: str, b: str, user_id: str) -> dict:
    ra = await db.btp_revisions.find_one({"plan_id": plan_id, "revision": a, "user_id": user_id}, {"_id": 0})
    rb = await db.btp_revisions.find_one({"plan_id": plan_id, "revision": b, "user_id": user_id}, {"_id": 0})
    if not ra or not rb:
        raise HTTPException(404, "Révision introuvable")
    la = {x["quantity_id"]: x for x in ra["lines"]}
    lb = {x["quantity_id"]: x for x in rb["lines"]}
    prices = await _quote_prices(plan_id, user_id)
    from engines.revision_impact import revision_delta
    rows, total = [], 0.0
    for qid in sorted(set(la) | set(lb), key=lambda k: (lb.get(k) or la.get(k))["lot"] + (lb.get(k) or la.get(k))["designation"]):
        xa, xb = la.get(qid), lb.get(qid)
        pr = prices.get(qid)
        result = revision_delta(xa, xb, pr)
        impact = result["impact_ht"]
        if impact is not None:
            total += impact
        rows.append({"quantity_id": qid, "designation": (xb or xa)["designation"], "lot": (xb or xa)["lot"], "unit": (xb or xa)["unit"], **result,
                     "status_before": (xa or {}).get("status"), "status_after": (xb or {}).get("status"), "quote": pr, "impact_ht": impact})
    linked = {p["doc_id"]: {k: p[k] for k in ("doc_id", "number", "status", "title")} for p in prices.values()}
    return {"a": {k: ra[k] for k in ("revision", "at", "count")}, "b": {k: rb[k] for k in ("revision", "at", "count")}, "rows": rows, "changed": sum(1 for r in rows if r["kind"] in ("modifiée", "ajoutée", "supprimée")),
            "impact_total_ht": round(total, 2), "priced_rows": sum(1 for r in rows if r["impact_ht"] is not None), "unpriced_changes": sum(1 for r in rows if r["kind"] in ("modifiée", "ajoutée", "supprimée") and r["impact_ht"] is None),
            "linked_documents": list(linked.values()), "note": "Incidence = écart des quantités à commander × prix HT remisé du devis de référence. Prix multiples, unités différentes ou quantité du devis modifiée : incidence indéterminée."}


@router.get("/plans/{plan_id}/revisions/diff")
async def revisions_diff(plan_id: str, a: str, b: str, user=Depends(current_user)) -> dict:
    await _plan(plan_id, user)
    return await _diff(plan_id, a, b, user["user_id"])


@router.post("/plans/{plan_id}/amendment-draft")
async def amendment_draft(plan_id: str, a: str = Body(..., embed=True), b: str = Body(..., embed=True), client_name: str = Body("", embed=True), user=Depends(current_user)) -> dict:
    """Draft amendment quote with only the changed lines (Δ quantities), priced from the linked quote when available. Never sent."""
    from routes.documents import DocIn, DocLine, create_document
    p = await _plan(plan_id, user)
    d = await _diff(plan_id, a, b, user["user_id"])
    changes = [r for r in d["rows"] if r["kind"] in ("modifiée", "ajoutée", "supprimée") and r["delta_to_order"] is not None]
    if not changes:
        raise HTTPException(400, "Aucun écart déterminé à reporter entre ces révisions")
    lines = []
    for r in changes:
        price = (r["quote"] or {}).get("unit_price_ht") if r["pricing_usable"] else None
        lines.append(DocLine(designation=f"Avenant — {r['designation']}",
            description=f"Métré {r['quantity_id']} · {r['kind']} · net {r['before']} → {r['after']} {r['unit']} · écart à commander {r['delta_to_order']} {r['unit']} (révision {a[:6]} → {b[:6]})",
            qty=r["delta_to_order"], unit=r["unit"], unit_price_ht=price if price is not None else 0,
            price_missing=price is None, price_source="revision_reference" if price is not None else "unpriced",
            vat_rate=None, category=r["lot"]))
    client_id = None
    if p.get("chantier_id"):
        from routes.chantiers import _get
        chantier = await _get(p["chantier_id"], user["user_id"])
        client_id = chantier.get("client_id")
    linked = ", ".join(x.get("number") or x["doc_id"] for x in d["linked_documents"]) or "aucun devis rattaché"
    skipped = sum(r["kind"] != "inchangée" and r["delta_to_order"] is None for r in d["rows"])
    # The document API supports negative quantities for reductions. The assistant schema intentionally does not.
    res = await create_document(DocIn(doc_type="quote", status="draft", chantier_id=p.get("chantier_id"), client_id=client_id,
        title=f"Avenant — {p.get('filename') or plan_id} — révision {b[:6]}", lines=lines,
        notes=f"Écarts entre révisions {a} et {b} du plan {plan_id}. Référence : {linked}. Incidence partielle {d['impact_total_ht']} € HT ; {d['unpriced_changes']} écart(s) sans prix et {skipped} indéterminé(s) non reporté(s). TVA et métrés à vérifier."), user)
    doc_id = res["doc_id"]
    if client_name.strip() and not client_id:
        await db.pro_documents.update_one({"doc_id": doc_id, "user_id": user["user_id"], "status": "draft"},
            {"$set": {"client_name": client_name.strip()[:200], "client": {"last_name": client_name.strip()[:200]}}})
    return {"ok": True, "doc_id": doc_id, "lines": len(lines), "skipped_undetermined": skipped,
            "impact_total_ht": d["impact_total_ht"], "editor_url": f"/devis-editeur/{doc_id}"}


@router.get("/plans/{plan_id}/report.pdf")
async def report_pdf(plan_id: str, user=Depends(current_user)):
    from fastapi.responses import Response
    from btp_ai.report_pdf import build_analysis_report
    from routes.plans_common import _resolve_branding
    p = await _plan(plan_id, user)
    a = await db.btp_analyses.find_one({"plan_id": plan_id}, {"_id": 0})
    if not a:
        await metre.rebuild(p, user["user_id"])
        a = await db.btp_analyses.find_one({"plan_id": plan_id}, {"_id": 0})
    full = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages.image_png_b64": 1, "pages.index": 1})
    pages = [{**pg, "index": pg.get("index", i)} for i, pg in enumerate((full or {}).get("pages") or [])]
    elements = await db.btp_elements.find({"plan_id": plan_id}, {"_id": 0}).to_list(2000)
    lines = await db.btp_quantities.find({"plan_id": plan_id, "superseded": {"$ne": True}}, {"_id": 0}).to_list(5000)
    overrides = await db.btp_overrides.find({"plan_id": plan_id}, {"_id": 0}).to_list(500)
    branding = await _resolve_branding(user["user_id"]) or {}
    pdf = build_analysis_report(p, a, elements, lines, overrides, pages, branding)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="rapport-analyse-{plan_id}.pdf"'})
