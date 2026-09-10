"""Génération du dossier technique PDF (reportlab, A4 portrait, 6 pages max)."""
from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Table, TableStyle, Paragraph


PRIMARY = colors.HexColor("#0B5FFF")
INK = colors.HexColor("#1A1D22")
MUTED = colors.HexColor("#5A6270")
WARN = colors.HexColor("#E38B1E")
DANGER = colors.HexColor("#D64545")
OK = colors.HexColor("#2F8F55")
BORDER = colors.HexColor("#D6D9DE")


def _header(c: pdfcanvas.Canvas, page_num: int, title: str, project_name: str, author: Optional[str]):
    W, H = A4
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 14)
    c.drawString(15 * mm, H - 15 * mm, "STAIRPILOT")
    c.setFont("Helvetica", 8); c.setFillColor(MUTED)
    c.drawString(15 * mm, H - 20 * mm, "Dossier technique escalier béton — DTU 36.3 / DTU 21")
    c.setFillColor(INK); c.setFont("Helvetica", 8)
    c.drawRightString(W - 15 * mm, H - 15 * mm, project_name)
    c.setFillColor(MUTED)
    if author:
        c.drawRightString(W - 15 * mm, H - 20 * mm, author)
    c.setStrokeColor(BORDER); c.setLineWidth(0.4)
    c.line(15 * mm, H - 22 * mm, W - 15 * mm, H - 22 * mm)
    c.setFillColor(PRIMARY); c.setFont("Helvetica-Bold", 12)
    c.drawString(15 * mm, H - 30 * mm, title)


def _footer(c: pdfcanvas.Canvas, page_num: int, total: int):
    W, _ = A4
    c.setStrokeColor(BORDER); c.setLineWidth(0.4)
    c.line(15 * mm, 18 * mm, W - 15 * mm, 18 * mm)
    c.setFont("Helvetica", 7); c.setFillColor(MUTED)
    c.drawString(15 * mm, 14 * mm, datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M"))
    c.drawRightString(W - 15 * mm, 14 * mm, f"Page {page_num}/{total}")
    c.drawCentredString(W / 2, 14 * mm, "Généré par STAIRPILOT — indicatif, validation BE obligatoire")


def _kv_table(pairs, col_widths=(85 * mm, 85 * mm)):
    tbl = Table(pairs, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (1, 0), (1, -1), "Courier-Bold", 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tbl


def _draw_stair_plan(c: pdfcanvas.Canvas, x0: float, y0: float, w: float, h: float,
                     result: Dict[str, Any], stair_input: Dict[str, Any]):
    """Dessine un plan simplifié de la volée droite dans un rect (x0,y0,w,h)."""
    n = result.get("num_treads", 15)
    g = result.get("tread_depth_mm", 280)
    stair_width = stair_input.get("stair_width_mm", 900)
    total_len = n * g
    c.setStrokeColor(BORDER); c.rect(x0, y0, w, h)
    c.setStrokeColor(INK); c.setLineWidth(1)
    margin = 10
    sx = (w - 2 * margin) / total_len
    sy = (h - 2 * margin) / stair_width
    s = min(sx, sy)
    pw = total_len * s
    ph = stair_width * s
    ox = x0 + (w - pw) / 2
    oy = y0 + (h - ph) / 2
    c.rect(ox, oy, pw, ph, stroke=1, fill=0)
    for i in range(1, n):
        xi = ox + i * g * s
        c.line(xi, oy, xi, oy + ph)
    c.setStrokeColor(PRIMARY); c.setLineWidth(0.5)
    c.setDash(2, 2)
    c.line(ox + 3, oy + ph / 2, ox + pw - 3, oy + ph / 2)
    c.setDash()
    c.setFillColor(PRIMARY); c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(ox + pw / 2, oy + ph / 2 + 4, "MONTÉE →")
    c.setFillColor(MUTED); c.setFont("Helvetica", 7)
    c.drawCentredString(ox + pw / 2, oy - 6, f"L={int(total_len)} mm · {n} marches · giron={int(g)} mm")


def _draw_stair_section(c: pdfcanvas.Canvas, x0: float, y0: float, w: float, h: float,
                        result: Dict[str, Any], stair_input: Dict[str, Any]):
    """Coupe longitudinale simplifiée."""
    n = result.get("num_steps", 16)
    g = result.get("tread_depth_mm", 280)
    hr = result.get("riser_height_mm", 175)
    H = stair_input.get("floor_height_mm", n * hr)
    total_len = (n - 1) * g
    c.setStrokeColor(BORDER); c.rect(x0, y0, w, h)
    margin = 15
    sx = (w - 2 * margin) / max(1, total_len)
    sy = (h - 2 * margin) / max(1, H)
    s = min(sx, sy)
    ox = x0 + margin
    oy = y0 + margin
    c.setStrokeColor(INK); c.setLineWidth(1)
    path = c.beginPath()
    path.moveTo(ox, oy)
    for i in range(1, n + 1):
        xx = ox + (i - 1) * g * s
        yl = oy + (i - 1) * hr * s
        yh = oy + i * hr * s
        path.lineTo(xx, yl)
        path.lineTo(xx, yh)
        nx = ox + (i * g if i < n else (i - 1) * g) * s
        path.lineTo(nx, yh)
    c.drawPath(path, stroke=1, fill=0)
    c.setFillColor(MUTED); c.setFont("Helvetica", 7)
    c.drawString(ox, oy - 8, f"0.00")
    c.drawString(ox + total_len * s - 15, oy + H * s + 3, f"+{int(H)} mm")


def generate_dossier_pdf(
    project_name: str,
    stair_input: Dict[str, Any],
    stair_result: Dict[str, Any],
    concrete_analysis: Optional[Dict[str, Any]] = None,
    author: Optional[str] = None,
) -> bytes:
    """Génère le dossier PDF complet et retourne les bytes."""
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    W, H = A4
    total_pages = 5 if concrete_analysis else 3

    # ==================== Page 1 — Fiche projet ====================
    _header(c, 1, "Fiche projet", project_name, author)
    y = H - 40 * mm
    pairs = [
        ["Type d'escalier", stair_result.get("stair_type", "—")],
        ["Nombre de marches", str(stair_result.get("num_steps", "—"))],
        ["Hauteur de marche", f"{stair_result.get('riser_height_mm', '—')} mm"],
        ["Giron", f"{stair_result.get('tread_depth_mm', '—')} mm"],
        ["Formule de Blondel (2h+g)", f"{stair_result.get('blondel_value_mm', '—')} mm"],
        ["Pente", f"{stair_result.get('slope_deg', '—')} °"],
        ["Reculement réel", f"{stair_result.get('stair_run_mm', '—')} mm"],
        ["Longueur volée", f"{stair_result.get('stair_length_mm', '—')} mm"],
        ["Échappée", f"{stair_result.get('headroom_mm', '—')} mm"],
        ["Constructible", "Oui" if stair_result.get("is_buildable") else "Non"],
    ]
    tbl = _kv_table(pairs)
    tbl.wrapOn(c, W - 30 * mm, y); tbl.drawOn(c, 15 * mm, y - tbl._height)
    y2 = y - tbl._height - 8 * mm
    c.setFont("Helvetica-Bold", 10); c.setFillColor(INK)
    c.drawString(15 * mm, y2, "Alertes")
    c.setFont("Helvetica", 8)
    y2 -= 5 * mm
    for a in (stair_result.get("alerts") or [])[:8]:
        col = {"red": DANGER, "orange": WARN, "green": OK}.get(a.get("level"), INK)
        c.setFillColor(col); c.circle(17 * mm, y2 + 1, 1.2, fill=1, stroke=0)
        c.setFillColor(INK)
        msg = (a.get("message") or a.get("message_fr") or "")[:110]
        c.drawString(21 * mm, y2, f"[{a.get('code','')}] {msg}")
        y2 -= 5 * mm
    _footer(c, 1, total_pages); c.showPage()

    # ==================== Page 2 — Plan technique ====================
    _header(c, 2, "Plan technique coté", project_name, author)
    _draw_stair_plan(c, 15 * mm, 100 * mm, W - 30 * mm, 130 * mm, stair_result, stair_input)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8)
    c.drawString(15 * mm, 90 * mm, "Vue en plan schématique — se référer à l'application STAIRPILOT pour cotes détaillées.")
    _footer(c, 2, total_pages); c.showPage()

    # ==================== Page 3 — Coupe longitudinale ====================
    _header(c, 3, "Coupe longitudinale", project_name, author)
    _draw_stair_section(c, 15 * mm, 100 * mm, W - 30 * mm, 130 * mm, stair_result, stair_input)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8)
    c.drawString(15 * mm, 90 * mm, "Coupe axiale schématique.")
    _footer(c, 3, total_pages); c.showPage()

    # ==================== Page 4 — Métré béton (si concrete_analysis) ====================
    if concrete_analysis:
        _header(c, 4, "Métré béton armé", project_name, author)
        q = concrete_analysis.get("quantities", {})
        p = concrete_analysis.get("paillasse", {})
        load = concrete_analysis.get("load_breakdown_kN_m2", {})
        pairs2 = [
            ["Volume béton total", f"{q.get('concrete_volume_m3', 0)} m³"],
            ["Surface coffrage", f"{q.get('formwork_area_m2', 0)} m²"],
            ["Volume paillasse", f"{q.get('paillasse_volume_m3', 0)} m³"],
            ["Volume marches", f"{q.get('tread_volume_m3', 0)} m³"],
            ["Épaisseur paillasse", f"{p.get('thickness_recommended_mm', 0)} mm"],
            ["Épaisseur mini L/25", f"{p.get('thickness_min_L25_mm', 0)} mm"],
            ["Portée", f"{p.get('span_mm', 0)} mm"],
            ["Classe béton", str(p.get('concrete_class', '—'))],
            ["Nuance acier", str(p.get('steel_grade', '—'))],
            ["Exposition", str(p.get('exposure_class', '—'))],
            ["Charge ELS totale", f"{load.get('total_ELS', 0)} kN/m²"],
            ["Charge ELU (1.35G+1.5Q)", f"{load.get('total_ELU', 0)} kN/m²"],
        ]
        t = _kv_table(pairs2)
        t.wrapOn(c, W - 30 * mm, H - 40 * mm)
        t.drawOn(c, 15 * mm, H - 40 * mm - t._height)
        _footer(c, 4, total_pages); c.showPage()

        # ==================== Page 5 — Ferraillage + nomenclature ====================
        _header(c, 5, "Ferraillage indicatif", project_name, author)
        nom = concrete_analysis.get("nomenclature", [])
        rf = concrete_analysis.get("reinforcement", {})
        data = [["Rep", "Désignation", "Ø", "L (m)", "Nb", "Poids (kg)"]]
        for row in nom:
            data.append([
                str(row.get("repere", "")),
                str(row.get("designation", ""))[:38],
                str(row.get("diameter", "")),
                f"{row.get('total_length_m', 0):.1f}",
                str(row.get("count", 0)),
                f"{row.get('weight_kg', 0):.2f}",
            ])
        data.append(["", "TOTAL ACIER HA", "", "", "", f"{rf.get('total_steel_kg', 0)} kg"])
        tblf = Table(data, colWidths=[12 * mm, 70 * mm, 15 * mm, 18 * mm, 15 * mm, 25 * mm])
        tblf.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F6F8")),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
            ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
            ("LINEBELOW", (0, 1), (-1, -2), 0.3, BORDER),
            ("LINEABOVE", (0, -1), (-1, -1), 0.6, INK),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ]))
        tblf.wrapOn(c, W - 30 * mm, H - 40 * mm)
        tblf.drawOn(c, 15 * mm, H - 45 * mm - tblf._height)
        # Disclaimer bandeau
        y_disc = H - 60 * mm - tblf._height
        c.setFillColor(WARN); c.rect(15 * mm, y_disc - 20 * mm, W - 30 * mm, 20 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 9)
        c.drawString(18 * mm, y_disc - 6 * mm, "AVERTISSEMENT")
        c.setFont("Helvetica", 8)
        styles = getSampleStyleSheet()
        p_style = ParagraphStyle("d", parent=styles["Normal"], fontName="Helvetica",
                                 fontSize=8, textColor=colors.white, leading=10)
        para = Paragraph(concrete_analysis.get("disclaimer", {}).get("message_fr",
            "Pré-dimensionnement indicatif. Validation ingénieur structure obligatoire."), p_style)
        para.wrapOn(c, W - 40 * mm, 18 * mm)
        para.drawOn(c, 18 * mm, y_disc - 18 * mm)
        _footer(c, 5, total_pages); c.showPage()

    # ==================== Dernière page — Annexes ====================
    last = 5 if concrete_analysis else 3
    _header(c, last, "Annexes & mentions légales", project_name, author)
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, H - 42 * mm, "Formules utilisées")
    c.setFont("Helvetica", 9); c.setFillColor(MUTED)
    lines = [
        "• Blondel : 2h + g ∈ [600, 640] mm (optimal), [580, 660] acceptable",
        "• Recherche n de marches : minimise |h − 170| avec h = H/n ∈ [160, 180] mm",
        "• Giron optimal : g = 630 − 2h, clampé [220, 320] mm",
        "• Section acier ELU : As = M / (0.9 × d × fyd), fyd = 435 MPa (B500B/1.15)",
        "• Moment ELU : M = (1.35 G + 1.5 Q) × L² / 8",
        "• Longueur d'ancrage : 40 × Ø (B500B en C25/30 conditions normales)",
        "• Poids linéique acier HA : 0.006165 × d² kg/m",
    ]
    y = H - 50 * mm
    for l in lines:
        c.drawString(18 * mm, y, l); y -= 4.5 * mm
    y -= 4 * mm
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, y, "Normes de référence"); y -= 6 * mm
    c.setFont("Helvetica", 9); c.setFillColor(MUTED)
    for l in ["• DTU 36.3 — Escaliers en béton", "• DTU 21 — Exécution ouvrages béton",
              "• Eurocode 2 (EN 1992-1-1) — Béton armé"]:
        c.drawString(18 * mm, y, l); y -= 4.5 * mm
    y -= 6 * mm
    c.setFillColor(DANGER); c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, y, "Mention légale"); y -= 6 * mm
    c.setFillColor(INK); c.setFont("Helvetica", 8)
    legal = ("Ce dossier est un pré-dimensionnement indicatif généré par STAIRPILOT. "
             "Il ne remplace pas une étude structurelle complète conforme à l'Eurocode 2. "
             "Toute exécution doit être validée par un ingénieur structure titulaire "
             "des qualifications requises. STAIRPILOT décline toute responsabilité en cas "
             "d'utilisation sans validation professionnelle.")
    styles = getSampleStyleSheet()
    p_style = ParagraphStyle("legal", parent=styles["Normal"], fontName="Helvetica",
                             fontSize=8, textColor=INK, leading=11)
    para = Paragraph(legal, p_style)
    para.wrapOn(c, W - 30 * mm, 40 * mm)
    para.drawOn(c, 15 * mm, y - 32 * mm)
    _footer(c, last, total_pages)
    c.showPage()
    c.save()
    return buf.getvalue()
