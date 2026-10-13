"""Export PDF du métré de structure (Lecture de plan)."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)

_ORANGE = colors.HexColor("#E8562A")
_DARK = colors.HexColor("#1A1A1A")
_TYPE_LABEL = {
    "semelle_isolee": "Semelle isolée", "semelle_filante": "Semelle filante",
    "longrine": "Longrine", "chainage": "Chaînage", "poteau": "Poteau",
}


def _n(v, suffix=""):
    return (f"{v}{suffix}" if v is not None else "—")


def build_structure_report(read: dict, title: str = "Métré structure") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=_DARK, fontSize=18, spaceAfter=4)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=colors.grey, fontSize=9)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=_ORANGE, fontSize=12, spaceBefore=10)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=colors.grey)
    story = []

    story.append(Paragraph(title, h1))
    m = read.get("metre", {})
    scale = read.get("scale_detected") or "non détectée"
    story.append(Paragraph(
        f"ConstruPilot · StructuroPilot — Lecture de plan · Échelle {scale} · "
        + datetime.now(timezone.utc).strftime("%d/%m/%Y"), sub))
    story.append(Spacer(1, 6))

    # Récapitulatif métré
    story.append(Paragraph("Récapitulatif", h2))
    recap = [
        ["Béton total", _n(m.get("beton_total_m3"), " m³")],
        ["Acier total" + ("" if m.get("acier_complet") else " (incomplet)"), _n(m.get("acier_total_kg"), " kg")],
        ["Semelles", str(m.get("nb_semelles", 0))],
        ["Poteaux", str(m.get("nb_poteaux", 0))],
        ["Longrines/chaînages", _n(m.get("lineaire_longrines_ml"), " ml")],
        ["Surface murs", _n(m.get("surface_murs_m2"), " m²")],
    ]
    t = Table(recap, colWidths=[70 * mm, 50 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), _DARK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)

    # Fondations
    fonds = read.get("fondations", [])
    if fonds:
        story.append(Paragraph("Éléments de fondation / gros œuvre", h2))
        head = ["Type", "Repère", "L (m)", "l (m)", "h (m)", "Nb", "Béton m³", "Acier kg", "Vérif."]
        rows = [head]
        for f in fonds:
            arm = f.get("armature") or {}
            rows.append([
                _TYPE_LABEL.get(f.get("type"), f.get("type", "")),
                _n(f.get("repere")), _n(f.get("longueur_m")), _n(f.get("largeur_m")),
                _n(f.get("hauteur_m")), str(f.get("nombre", 1)),
                _n(f.get("volume_beton_m3")), _n(arm.get("total_kg")),
                "⚠" if f.get("a_verifier") else "✓",
            ])
        ft = Table(rows, repeatRows=1)
        ft.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF7F5")]),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(ft)

    # Murs
    murs = read.get("murs", [])
    if murs:
        story.append(Paragraph("Murs de soubassement", h2))
        rows = [["Repère", "Matériau", "Épais. (m)", "Long. (m)", "Haut. (m)", "Surface m²", "Assise"]]
        for w in murs:
            h = _n(w.get("hauteur_m")) + (" (déduite)" if w.get("hauteur_deduite") else "")
            rows.append([
                _n(w.get("repere")), w.get("materiau", ""), _n(w.get("epaisseur_m")),
                _n(w.get("longueur_m")), h, _n(w.get("surface_m2")), _n(w.get("niveau_assise_m"), " m"),
            ])
        wt = Table(rows, repeatRows=1)
        wt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF7F5")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(wt)

    # Déductions
    for d in read.get("deductions", []):
        story.append(Paragraph("➤ " + d, small))

    # Données manquantes
    md = read.get("missing_data", [])
    if md:
        story.append(Paragraph("Données à fournir (non devinées)", h2))
        for q in md:
            story.append(Paragraph(f"• {q.get('question')}", ss["Normal"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Métré établi par lecture assistée : vérifiez les éléments marqués ⚠ avant usage. "
        "Les quantités déterministes (béton, linéaire) reposent sur les cotes lues.", small))
    doc.build(story)
    return buf.getvalue()
