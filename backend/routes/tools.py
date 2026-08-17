import io
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.db import db
from engines import calculators, diy

router = APIRouter(tags=["tools"])


@router.get("/calculators")
async def list_calculators() -> list:
    return [{k: v for k, v in c.items() if k != "fn"} for c in calculators.CALCULATORS.values()]


class CalcIn(BaseModel):
    params: dict


@router.post("/calculators/{key}")
async def run_calculator(key: str, body: CalcIn):
    cfg = calculators.CALCULATORS.get(key)
    if not cfg:
        raise HTTPException(status_code=404, detail="Calculateur inconnu")
    allowed = {f["name"] for f in cfg["fields"]}
    args = {}
    for f in cfg["fields"]:
        v = body.params.get(f["name"], f.get("default"))
        if v is None or v == "":
            continue
        if f["type"] == "number":
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
        if f["type"] == "boolean":
            v = bool(v)
        args[f["name"]] = v
    args = {k: v for k, v in args.items() if k in allowed}
    return cfg["fn"](**args)


class CalcPdfIn(BaseModel):
    name: str = "Calcul matériaux"
    inputs: list[dict] = []
    results: list[dict] = []
    materials: list[dict] = []
    estimated_budget: float = 0
    priced_lines: list[dict] = []       # [{name, quantity, supplier, unit_price, total}]
    priced_total: float | None = None   # total devis prix fournisseurs


@router.post("/calculators-pdf")
async def calculator_pdf(body: CalcPdfIn):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    GREEN = colors.HexColor("#16a34a")
    DARK = colors.HexColor("#0f172a")
    GREY = colors.HexColor("#64748b")
    LIGHT = colors.HexColor("#f1f5f9")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=DARK, fontSize=20, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=GREY, fontSize=10, spaceAfter=14)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], textColor=GREEN, fontSize=12, spaceBefore=14, spaceAfter=6)
    small = ParagraphStyle("small", parent=styles["Normal"], textColor=GREY, fontSize=8, leading=11)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=14 * mm, title="Fiche de calcul")
    flow = [Paragraph("ConstruPilot — Fiche de calcul", h1), Paragraph(body.name, sub)]

    if body.inputs:
        flow.append(Paragraph("Paramètres", sec))
        rows = [[str(i.get("label", "")), str(i.get("value", ""))] for i in body.inputs]
        t = Table(rows, colWidths=[90 * mm, 84 * mm])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), GREY),
            ("TEXTCOLOR", (1, 0), (1, -1), DARK),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LIGHT),
        ]))
        flow.append(t)

    if body.results:
        flow.append(Paragraph("Résultats", sec))
        rows = [["Poste", "Quantité", "Unité"]]
        for r in body.results:
            rows.append([str(r.get("label", "")), str(r.get("value", "")), str(r.get("unit", ""))])
        t = Table(rows, colWidths=[104 * mm, 40 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        flow.append(t)

    if body.materials:
        flow.append(Paragraph("Liste de courses matériaux", sec))
        rows = [["Matériau", "Quantité", "Unité"]]
        for m in body.materials:
            rows.append([str(m.get("name", "")), str(m.get("quantity", "")), str(m.get("unit", ""))])
        t = Table(rows, colWidths=[104 * mm, 40 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        flow.append(t)

    flow.append(Spacer(1, 10))
    if body.priced_lines:
        flow.append(Paragraph("Devis matériaux — prix fournisseurs", sec))
        rows = [["Produit", "Qté", "Fournisseur", "PU", "Total"]]
        for l in body.priced_lines:
            rows.append([str(l.get("name", "")), str(l.get("quantity", "")),
                         str(l.get("supplier", "")),
                         f"{float(l.get('unit_price', 0)):.2f} €",
                         f"{float(l.get('total', 0)):.2f} €"])
        t = Table(rows, colWidths=[64 * mm, 16 * mm, 40 * mm, 26 * mm, 28 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        flow.append(t)
        flow.append(Spacer(1, 8))
        flow.append(Paragraph(
            f"Total devis matériaux (prix fournisseurs) : <b>{(body.priced_total or 0):,.2f} €</b>".replace(",", " "),
            ParagraphStyle("bud2", parent=styles["Normal"], textColor=GREEN, fontSize=13)))
    else:
        flow.append(Paragraph(f"Budget matériaux estimé : <b>{body.estimated_budget:,.0f} €</b>".replace(",", " "),
                              ParagraphStyle("bud", parent=styles["Normal"], textColor=GREEN, fontSize=13)))
    flow.append(Spacer(1, 16))
    flow.append(Paragraph(
        "Estimation indicative avec marges de sécurité incluses. Les quantités peuvent varier selon la mise "
        "en œuvre et les conditions de chantier. Vérifiez avant commande. — Généré par ConstruPilot · construpilot.fr",
        small))

    doc.build(flow)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="fiche-calcul-construpilot.pdf"'})



class ShareCalcIn(BaseModel):
    name: str = "Calcul matériaux"
    inputs: list[dict] = []
    results: list[dict] = []
    materials: list[dict] = []
    estimated_budget: float = 0
    priced_lines: list[dict] = []
    priced_total: float | None = None
    contractor: str = ""


@router.post("/calculators-share")
async def share_calculator(body: ShareCalcIn):
    share_id = secrets.token_urlsafe(9)
    doc = {"share_id": share_id, **body.model_dump(),
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.shared_calcs.insert_one(doc)
    return {"share_id": share_id}


@router.get("/calculators-shared/{share_id}")
async def get_shared_calculator(share_id: str):
    doc = await db.shared_calcs.find_one({"share_id": share_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Fiche introuvable")
    return doc


@router.get("/diy/tasks")
async def diy_tasks() -> list:
    return [{"key": t["key"], "name": t["name"], "difficulty": t["difficulty"],
             "difficulty_label": diy.DIFFICULTY[t["difficulty"]]["label"],
             "difficulty_color": diy.DIFFICULTY[t["difficulty"]]["color"],
             "duration": t["duration"], "lot": t["lot"], "steps_count": len(t["steps"]),
             "calculator": t["calculator"]} for t in diy.TASKS]


@router.post("/diy/guide/{key}")
async def diy_guide(key: str, body: CalcIn):
    try:
        return diy.build_guide(key, body.params)
    except KeyError:
        raise HTTPException(status_code=404, detail="Travail inconnu")
