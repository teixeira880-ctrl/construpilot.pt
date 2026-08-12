from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from core.db import db
from engines import estimation, ai, pdf
from engines.catalog import (PROJECT_TYPES, LOTS, FINISH_LEVELS, REGIONS, DIFFICULTY,
                            CONDITION_COEF)

router = APIRouter(prefix="/estimation", tags=["estimation"])


class EstimateIn(BaseModel):
    project_type: str = "renovation_complete"
    surface: float = 100
    finish_level: str = "standard"
    country: str = "FR"
    region: str | None = None
    city: str | None = None
    building_type: str = "maison"
    condition: str = "bon"
    construction_year: int | None = None
    lots: list[str] | None = None


class DescribeIn(BaseModel):
    description: str


@router.get("/catalog")
async def catalog():
    overrides = {d["key"]: d async for d in db.price_reference.find({}, {"_id": 0})}
    lots = []
    for l in LOTS:
        lots.append({**l, **overrides.get(l["key"], {})})
    region_docs = await db.regions.find({}, {"_id": 0}).to_list(500)
    return {
        "project_types": PROJECT_TYPES, "lots": lots, "finish_levels": FINISH_LEVELS,
        "regions": region_docs or REGIONS, "difficulty": DIFFICULTY,
        "conditions": list(CONDITION_COEF.keys()),
        "building_types": ["maison", "appartement", "commerce"],
    }


def _apply_overrides(overrides: dict):
    from engines.catalog import LOTS_BY_KEY
    for key, ov in overrides.items():
        if key in LOTS_BY_KEY:
            for f in ("mat_eco", "mat_std", "mat_premium", "labour", "hours"):
                if ov.get(f) is not None:
                    LOTS_BY_KEY[key][f] = ov[f]


@router.post("/compute")
async def compute(body: EstimateIn):
    overrides = {d["key"]: d async for d in db.price_reference.find({}, {"_id": 0})}
    _apply_overrides(overrides)
    est = estimation.estimate(
        body.project_type, body.surface, body.finish_level, body.country, body.region,
        body.building_type, body.condition, body.construction_year, body.lots)
    est["planning"] = estimation.planning(est["lots"])
    est["diy_vs_pro"] = estimation.diy_vs_pro(est)
    est["safety_alerts"] = estimation.safety_check("", [l["key"] for l in est["lots"]])
    return est


@router.post("/analyse")
async def analyse(body: DescribeIn):
    """Smart Project : IA comprend -> moteur déterministe estime."""
    analysis = await ai.analyse_description(body.description)
    overrides = {d["key"]: d async for d in db.price_reference.find({}, {"_id": 0})}
    _apply_overrides(overrides)
    est = estimation.estimate(
        analysis["project_type"], analysis["surface"], analysis["finish_level"],
        "FR", None, analysis["building_type"], analysis["condition"], None,
        analysis.get("lots") or None)
    est["planning"] = estimation.planning(est["lots"])
    est["diy_vs_pro"] = estimation.diy_vs_pro(est)
    est["safety_alerts"] = estimation.safety_check(body.description,
                                                   [l["key"] for l in est["lots"]])
    return {"analysis": analysis, "estimation": est}


@router.post("/advice")
async def advice(body: dict):
    est = body.get("estimation")
    if not est:
        raise HTTPException(status_code=400, detail="estimation requise")
    return {"advice": await ai.project_advice(est)}


class MaterialsIn(BaseModel):
    lots: list[dict]


class PdfIn(BaseModel):
    project: dict
    estimation: dict
    advice: str = ""


@router.post("/pdf")
async def estimation_pdf(body: PdfIn):
    """Génère un PDF de devis à partir d'une estimation calculée (avant sauvegarde)."""
    if not body.estimation or not body.estimation.get("lots"):
        raise HTTPException(status_code=400, detail="Estimation requise")
    data = pdf.build_estimation_pdf(body.project or {},
                                    body.estimation,
                                    body.estimation.get("planning") or [],
                                    body.advice or "", None)
    name = (body.project or {}).get("name") or "Projet"
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip() or "projet"
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="Estimation-ConstruPilot-{safe}.pdf"'})


class PdfEmailIn(BaseModel):
    project: dict
    estimation: dict
    advice: str = ""
    to: str
    message: str = ""


@router.post("/pdf/email")
async def estimation_pdf_email(body: PdfEmailIn):
    """Envoie le PDF de devis par email via Resend (route publique)."""
    if not body.estimation or not body.estimation.get("lots"):
        raise HTTPException(status_code=400, detail="Estimation requise")
    from engines import emailer
    name = (body.project or {}).get("name") or "Votre projet"
    data = pdf.build_estimation_pdf(body.project or {}, body.estimation,
                                    body.estimation.get("planning") or [],
                                    body.advice or "", None)
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip() or "projet"
    total = body.estimation.get("total_avg", 0)
    surface = body.estimation.get("surface", 0)
    extra = f"<p style='margin-top:20px;padding:16px;background:#f8fafc;border-left:3px solid #FF5A00'>{body.message}</p>" if body.message else ""
    html = emailer.wrap_html(
        f"Votre estimation : {name}",
        f"""<p>Bonjour,</p>
<p>Vous trouverez en pièce jointe l'estimation détaillée générée par <b>ConstruPilot</b>.</p>
<ul>
<li><b>Surface</b> : {surface} m²</li>
<li><b>Coût moyen estimé</b> : {total:,.0f} €</li>
</ul>
<p>Le PDF détaille chaque lot, le planning, les matériaux et les recommandations.</p>{extra}
<p>Pour affiner ou obtenir une intervention ConstruPilot, revenez sur l'application.</p>""".replace(",", " "))
    try:
        await emailer.send_email_with_pdf(body.to,
                                          f"Estimation ConstruPilot — {name}",
                                          html, data,
                                          filename=f"Estimation-ConstruPilot-{safe}.pdf")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Envoi impossible: {e}")
    return {"ok": True, "to": body.to}


@router.post("/materials")
async def materials_list(body: MaterialsIn):
    """Panier de chantier intelligent : liste d'achats depuis les lots estimés."""
    from engines import calculators
    items = []
    for lot in body.lots:
        key, qty = lot.get("key"), float(lot.get("quantity") or 0)
        if qty <= 0:
            continue
        if key == "placo":
            items += calculators.drywall(qty, structure="cloison")["materials"]
        elif key == "peinture":
            side = max(1.0, (qty / 2.9) ** 0.5)
            items += calculators.paint(side, side, 2.5)["materials"]
        elif key == "carrelage":
            items += calculators.tile(qty)["materials"]
        elif key == "isolation":
            items += calculators.insulation(qty)["materials"]
        elif key == "salle_de_bain":
            items += [
                {"name": "Receveur de douche", "quantity": 1, "unit": "u", "search": "receveur douche 90x90"},
                {"name": "Mitigeur douche", "quantity": 1, "unit": "u", "search": "mitigeur douche"},
                {"name": "WC suspendu", "quantity": 1, "unit": "u", "search": "wc suspendu bati support"},
                {"name": "Meuble vasque", "quantity": 1, "unit": "u", "search": "meuble vasque salle de bain"},
                {"name": "Placo hydrofuge", "quantity": max(4, round(qty * 0.8)), "unit": "plaque",
                 "search": "ba13 hydrofuge 250x120"},
            ]
        elif key == "plomberie":
            items += [
                {"name": "Tube multicouche 16mm", "quantity": max(1, round(qty / 20)), "unit": "couronne 50m",
                 "search": "tube multicouche 16mm 50m"},
                {"name": "Raccords à sertir", "quantity": max(1, round(qty / 10)), "unit": "lot",
                 "search": "raccord multicouche a sertir"},
            ]
        elif key == "electricite":
            items += [
                {"name": "Câble R2V 3G2.5", "quantity": max(1, round(qty / 40)), "unit": "couronne 100m",
                 "search": "cable r2v 3g2.5 100m"},
                {"name": "Gaine ICTA 20mm", "quantity": max(1, round(qty / 30)), "unit": "couronne",
                 "search": "gaine icta 20mm"},
            ]
        elif key == "parquet":
            items.append({"name": "Parquet stratifié", "quantity": round(qty * 1.07, 2), "unit": "m²",
                          "search": "parquet stratifie clipsable"})
        elif key == "menuiseries":
            items.append({"name": "Fenêtre PVC double vitrage", "quantity": round(qty), "unit": "u",
                          "search": "fenetre pvc double vitrage"})
    merged: dict[str, dict] = {}
    for it in items:
        k = it["search"]
        if k in merged:
            merged[k]["quantity"] = round(merged[k]["quantity"] + it["quantity"], 2)
        else:
            merged[k] = dict(it)
    return {"items": list(merged.values())}
