"""Pitch deck investisseurs ConstruPilot — PDF de marque (public).

Reprend le contenu de la page /investisseurs sous forme de slides A4.
Généré à la volée avec ReportLab, sans dépendance à des données utilisateur.
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

GREEN = colors.HexColor("#3F7D54")
GREEN_SOFT = colors.HexColor("#EAF2ED")
DARK = colors.HexColor("#1A1D20")
GREY = colors.HexColor("#78716C")
LINE = colors.HexColor("#E7E5E4")

CONTACT = "info@construpilot.fr"


def _styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle("ck", textColor=GREEN, fontName="Helvetica-Bold",
                                       fontSize=11, leading=14, spaceAfter=10),
        "cover_title": ParagraphStyle("ct", textColor=DARK, fontName="Helvetica-Bold",
                                      fontSize=30, leading=36, spaceAfter=16),
        "cover_sub": ParagraphStyle("cs", textColor=GREY, fontName="Helvetica",
                                    fontSize=13, leading=19),
        "num": ParagraphStyle("num", textColor=GREEN, fontName="Helvetica-Bold",
                              fontSize=10, leading=12),
        "kicker": ParagraphStyle("k", textColor=GREEN, fontName="Helvetica-Bold",
                                 fontSize=10, leading=12, spaceAfter=4),
        "h2": ParagraphStyle("h2", textColor=DARK, fontName="Helvetica-Bold",
                             fontSize=21, leading=26, spaceAfter=14),
        "card_title": ParagraphStyle("ctt", textColor=DARK, fontName="Helvetica-Bold",
                                     fontSize=12, leading=15, spaceAfter=4),
        "card_body": ParagraphStyle("cb", textColor=GREY, fontName="Helvetica",
                                    fontSize=10, leading=14),
        "stat_v": ParagraphStyle("sv", textColor=GREEN, fontName="Helvetica-Bold",
                                fontSize=26, leading=30, alignment=1),
        "stat_l": ParagraphStyle("sl", textColor=GREY, fontName="Helvetica",
                                fontSize=9, leading=12, alignment=1),
        "body": ParagraphStyle("body", textColor=DARK, fontName="Helvetica",
                              fontSize=11, leading=16),
        "muted": ParagraphStyle("mu", textColor=GREY, fontName="Helvetica",
                               fontSize=9, leading=13),
        "bullet": ParagraphStyle("bl", textColor=DARK, fontName="Helvetica",
                                fontSize=11, leading=16, leftIndent=6),
    }


CONTENT_W = A4[0] - 40 * mm


def _cards(items, S, cols=3):
    """items: list of (title, text). Returns a Table of styled cards."""
    gap = 6 * mm
    col_w = (CONTENT_W - gap * (cols - 1)) / cols
    cells = []
    for title, text in items:
        inner = Table(
            [[Paragraph(title, S["card_title"])],
             [Paragraph(text, S["card_body"])]],
            colWidths=[col_w - 12],
        )
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        cells.append(inner)
    # pad to a multiple of cols
    while len(cells) % cols:
        cells.append("")
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    t = Table(rows, colWidths=[col_w] * cols)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, LINE),
    ]))
    return t


def _stats(items, S):
    """items: list of (value, label)."""
    cols = len(items)
    col_w = (CONTENT_W - 6 * mm * (cols - 1)) / cols
    row = [Table([[Paragraph(v, S["stat_v"])], [Paragraph(l, S["stat_l"])]],
                 colWidths=[col_w - 12]) for v, l in items]
    t = Table([row], colWidths=[col_w] * cols)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_SOFT),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
    ]))
    return t


def _slide_header(story, n, kicker, title, S):
    story.append(Paragraph(f"{str(n).zfill(2)} &nbsp;·&nbsp; {kicker}", S["kicker"]))
    story.append(Paragraph(title, S["h2"]))


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    # top brand bar
    canvas.setFillColor(GREEN)
    canvas.rect(0, h - 6, w, 6, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, h - 15 * mm, "ConstruPilot — Dossier investisseurs")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 20 * mm, 12 * mm,
                           f"Confidentiel · {CONTACT} · page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 16 * mm, w - 20 * mm, 16 * mm)
    canvas.restoreState()


def build_pitch_deck_pdf() -> bytes:
    S = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=22 * mm, bottomMargin=22 * mm,
                            title="ConstruPilot — Pitch Deck Investisseurs")
    story = []

    # -------- COVER --------
    story.append(Spacer(1, 40 * mm))
    story.append(Paragraph("Dossier investisseurs · 2026", S["cover_kicker"]))
    story.append(Paragraph(
        "ConstruPilot — L'IA qui transforme un plan en devis chiffré, en secondes.",
        S["cover_title"]))
    story.append(Paragraph(
        "ConstruPilot digitalise tout le cycle du BTP : analyse IA des plans, "
        "métré béton &amp; aciers, maquette 3D et devis automatique — dans une seule "
        "plateforme.", S["cover_sub"]))
    story.append(Spacer(1, 24 * mm))
    story.append(Paragraph(f"Contact : {CONTACT}", S["muted"]))
    story.append(PageBreak())

    # -------- 01 PROBLÈME --------
    _slide_header(story, 1, "Le problème",
                  "Chiffrer un chantier reste lent, manuel et source d'erreurs.", S)
    story.append(_cards([
        ("Des heures perdues", "Un métré manuel depuis un plan prend des heures et retarde l'envoi des devis."),
        ("Marges qui fuient", "Erreurs de quantités, oublis de postes, prix non à jour : la rentabilité s'érode."),
        ("Outils cloisonnés", "Métré, devis, 3D, facturation et chantier vivent dans des logiciels séparés."),
    ], S))
    story.append(PageBreak())

    # -------- 02 SOLUTION --------
    _slide_header(story, 2, "La solution",
                  "Une plateforme unique, du plan au devis signé — propulsée par l'IA.", S)
    story.append(_cards([
        ("Analyse IA du plan", "Détection murs, poteaux, poutres, semelles + métré béton &amp; aciers automatiques."),
        ("Devis instantané", "Depuis un plan, une description ou une vidéo. Chiffrage auto via la bibliothèque de prix."),
        ("Maquette 3D", "Visualisation des volumes détectés, export PNG joint au devis client."),
        ("Assistant IA", "Correction du plan en langage naturel, marge &amp; prix de vente estimés."),
    ], S, cols=2))
    story.append(PageBreak())

    # -------- 03 MARCHÉ --------
    _slide_header(story, 3, "Le marché", "Un secteur immense, encore peu digitalisé.", S)
    story.append(_stats([
        ("+500 Md€", "marché du BTP en France (par an)"),
        ("~600 000", "entreprises du bâtiment en France"),
        ("< 30%", "équipées d'un vrai outil de chiffrage"),
    ], S))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Tendances porteuses 2026 : obligation de facture électronique, pénurie de "
        "main-d'œuvre (besoin de productivité) et adoption rapide de l'IA. "
        "Cible : artisans, PME du BTP et bureaux d'études.", S["muted"]))
    story.append(PageBreak())

    # -------- 04 DIFFÉRENCIATION --------
    _slide_header(story, 4, "Notre avantage",
                  "Le seul outil qui relie IA de plan, métré béton, 3D et devis.", S)
    for t in [
        "IA de plan → métré béton + aciers (unique bout-en-bout)",
        "Devis depuis une vidéo (voix + photos) — inédit sur le marché",
        "Maquette 3D générée automatiquement depuis le métré",
        "ERP intégré : factures, situations, RH, suivi de chantier",
        "Multilingue (7 langues) + Landing B2C particuliers",
        "Conformité facture électronique (Factur-X) déjà en place",
    ]:
        story.append(Paragraph(f"<font color='#3F7D54'>✓</font> &nbsp; {t}", S["bullet"]))
        story.append(Spacer(1, 4))
    story.append(PageBreak())

    # -------- 05 MODÈLE ÉCONOMIQUE --------
    _slide_header(story, 5, "Modèle économique",
                  "SaaS par abonnement, revenus récurrents et scalables.", S)
    story.append(_cards([
        ("Abonnement SaaS", "Formules mensuelles par utilisateur (artisan → PME), montée en gamme par modules."),
        ("Options à la valeur", "Crédits IA, module Entreprise (RBAC/RH/chantier), génération de documents."),
        ("Expansion", "Marché francophone puis Europe du Sud (déjà multilingue), et B2C particuliers."),
    ], S))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Grille tarifaire : Premium 19 €/mois (particuliers) · Pro 299 €/mois · "
        "Pro Business 350 €/mois · options API et crédits 3D.", S["muted"]))
    story.append(PageBreak())

    # -------- 06 POURQUOI MAINTENANT --------
    _slide_header(story, 6, "Pourquoi maintenant", "Le bon produit, au bon moment.", S)
    story.append(_cards([
        ("IA mature", "Les modèles de vision permettent enfin de lire des plans de façon fiable."),
        ("Réglementation", "La facture électronique pousse tout le secteur à s'équiper en 2026-2027."),
        ("Produit déjà avancé", "Plateforme complète et fonctionnelle, prête à passer à l'échelle."),
    ], S))
    story.append(PageBreak())

    # -------- 07 L'ASK --------
    _slide_header(story, 7, "L'opportunité", "Nous levons pour accélérer.", S)
    story.append(_cards([
        ("Produit & IA", "Renforcer la détection (IFC/BIM), la 3D et l'automatisation du chiffrage."),
        ("Go-to-market", "Acquisition artisans/PME, partenariats fournisseurs &amp; fédérations BTP."),
        ("Équipe", "Recrutements produit, IA et commercial pour passer à l'échelle."),
    ], S))
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"Vous souhaitez le dossier complet ou échanger avec l'équipe ? "
        f"Écrivez-nous à <b>{CONTACT}</b>.", S["body"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Document confidentiel destiné aux investisseurs — © {datetime.now(timezone.utc).year} ConstruPilot · Brevet FR261104.",
        S["muted"]))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()
