"""PDF du plan annoté (murs rouges / fenêtres jaunes / portes violettes / poutres)
+ légende + tableau descriptif chiffré — à joindre au devis client."""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Image as RLImage, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

RED = (220, 38, 38)
RED_LIGHT = (248, 113, 113)
YELLOW = (250, 204, 21)
PURPLE = (168, 85, 247)
BEAM = (99, 40, 150)


def _render_overlay(image_b64: str, structure: dict) -> bytes:
    img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    scale = max(img.width, img.height) / 900.0
    lw = max(2, int(3 * scale))
    for w in structure.get("walls") or []:
        col = RED if w.get("type") == "porteur" else RED_LIGHT
        d.line([(w["x1"], w["y1"]), (w["x2"], w["y2"])],
               fill=col + (255,), width=lw + (2 if w.get("type") == "porteur" else 0))
    for b in structure.get("beams") or []:
        d.line([(b["x1"], b["y1"]), (b["x2"], b["y2"])], fill=BEAM + (230,), width=lw)
    for c in structure.get("columns") or []:
        x0, y0 = min(c["x1"], c["x2"]), min(c["y1"], c["y2"])
        x1, y1 = max(c["x1"], c["x2"]), max(c["y1"], c["y2"])
        d.rectangle([x0, y0, x1, y1], fill=(126, 34, 206, 235), outline=(88, 24, 145, 255))
    for ft in structure.get("footings") or []:
        x0, y0 = min(ft["x1"], ft["x2"]), min(ft["y1"], ft["y2"])
        x1, y1 = max(ft["x1"], ft["x2"]), max(ft["y1"], ft["y2"])
        d.rectangle([x0, y0, x1, y1], fill=(250, 204, 21, 90), outline=(202, 138, 4, 255))
    for o in structure.get("openings") or []:
        col = PURPLE if o.get("kind") == "porte" else YELLOW
        d.line([(o["x1"], o["y1"]), (o["x2"], o["y2"])], fill=col + (255,), width=lw + 3)
        if o.get("kind") == "porte" and o.get("swing"):
            d.line([(o["x1"], o["y1"]), (o["swing"]["x"], o["swing"]["y"])],
                   fill=PURPLE + (150,), width=max(1, lw - 1))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_annotated_plan_pdf(image_b64: str, structure: dict, descriptif: dict,
                             filename: str, branding: dict | None = None) -> bytes:
    overlay_png = _render_overlay(image_b64, structure)
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm)
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#0f172a"))
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"))
    story = []
    company = (branding or {}).get("company_name") or "ConstruPilot"
    story.append(Paragraph(f'Planta anotada — {company}', h))
    story.append(Paragraph(f'Ficheiro: {filename}', sub))
    story.append(Spacer(1, 6))

    # Légende
    legend = Table([[
        _swatch("#dc2626"), Paragraph("Paredes", sub),
        _swatch("#facc15"), Paragraph("Janelas / envidraçados", sub),
        _swatch("#a855f7"), Paragraph("Portas", sub),
        _swatch("#632896"), Paragraph("Vigas", sub),
    ]], colWidths=[8 * mm, 22 * mm, 8 * mm, 34 * mm, 8 * mm, 22 * mm, 8 * mm, 22 * mm])
    legend.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(legend)
    story.append(Spacer(1, 8))

    # Image annotée (adaptée à la largeur page)
    img = Image.open(io.BytesIO(overlay_png))
    max_w = 180 * mm
    ratio = img.height / img.width
    iw = min(max_w, 180 * mm)
    story.append(RLImage(io.BytesIO(overlay_png), width=iw, height=iw * ratio))
    story.append(Spacer(1, 10))

    # Descriptif chiffré
    if not descriptif.get("calibrated"):
        story.append(Paragraph("⚠️ Planta não calibrada — quantidades indisponíveis.", sub))
    story.append(Paragraph("Descritivo da medição", ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=12)))
    rows = [["Artigo", "Quantidade", "Un."]]
    d = descriptif
    def r(lbl, val, unit):
        if val:
            rows.append([lbl, f"{val}", unit])
    r("Pavimento", d.get("planchers_m2"), "m²")
    r("Paredes resistentes (alvenaria)", d.get("murs_porteurs_ml"), "ml")
    r("Divisórias", d.get("cloisons_ml"), "ml")
    r(f"Paredes — reboco/pintura (h={d.get('wall_height_m')} m)", d.get("murs_surface_m2"), "m²")
    r("Portas", d.get("portes"), "u")
    r("Janelas", d.get("fenetres"), "u")
    r("Envidraçados", d.get("baies"), "u")
    r("Vigas / padieiras", d.get("poutres_ml"), "ml")
    r("Pilares de betão", d.get("poteaux"), "u")
    r("Sapatas / fundações", d.get("semelles"), "u")
    r("Betão total", d.get("beton_total_m3"), "m³")
    t = Table(rows, colWidths=[110 * mm, 35 * mm, 25 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    doc.build(story)
    return out.getvalue()


def _swatch(hexcol: str):
    t = Table([[""]], colWidths=[6 * mm], rowHeights=[4 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(hexcol))]))
    return t
