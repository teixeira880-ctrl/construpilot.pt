"""Génère le PDF comparatif ConstruPilot vs concurrents (positionnement marché).

Données issues d'informations publiques (sites éditeurs / comparateurs) à la date
d'édition — à vérifier avant tout usage contractuel. Les fonctionnalités évoluent.
"""
import base64
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, PageBreak, Image as RLImage)

GREEN = colors.HexColor("#18A858")
DARK = colors.HexColor("#0A0D14")
GREY = colors.HexColor("#64748B")
LIGHT = colors.HexColor("#E2E8F0")
TINT = colors.HexColor("#F1FBF4")
LOGO = "/app/frontend/public/construpilot-logo.png"
OUT = "/app/frontend/public/comparatif-construpilot.pdf"

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=26, textColor=DARK, leading=30)
KICK = ParagraphStyle("kick", fontName="Helvetica-Bold", fontSize=10, textColor=GREEN, leading=13, spaceAfter=3)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, textColor=DARK, leading=16, spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, textColor=DARK, leading=12)
MUT = ParagraphStyle("mut", fontName="Helvetica", fontSize=8, textColor=GREY, leading=11)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=7.3, textColor=DARK, leading=8.6)
CELLH = ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=7.3, textColor=colors.white, leading=8.6, alignment=1)
FEAT = ParagraphStyle("feat", fontName="Helvetica-Bold", fontSize=7.6, textColor=DARK, leading=9)
WBIG = ParagraphStyle("wbig", fontName="Helvetica-Bold", fontSize=15, textColor=colors.white, leading=18)
WSM = ParagraphStyle("wsm", fontName="Helvetica", fontSize=8.5, textColor=colors.white, leading=11)

COLS = ["ConstruPilot", "Obat", "Trustup Pro", "Vertuoza", "EBP Bât.", "Batappli", "Alobees", "BatiChiffrage", "Renalto"]

# Oui / Option / À venir / Non / —
ROWS = [
    ("Devis & factures", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Partiel", "Oui", "Oui"]),
    ("Facturation électronique (Factur-X / Peppol)", ["À venir", "Oui", "Oui", "Oui", "Oui", "Oui", "—", "Oui", "Oui"]),
    ("Bibliothèque d'ouvrages & prix", ["Oui", "Oui (30k)", "Oui", "Oui", "Option", "Oui", "Non", "Oui (80k)", "Oui (≤5k)"]),
    ("Chiffrage 100% déterministe (0 IA sur les maths)", ["Oui", "—", "—", "—", "—", "—", "—", "—", "Non (IA)"]),
    ("Métré sur plans (PDF/image) + étalonnage", ["Oui", "À venir", "Non", "Non", "Non", "Non", "Non", "Non", "Partiel"]),
    ("Lecture des cotes natives DWG / DXF", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]),
    ("Détection murs & ouvertures (IA / OpenCV)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Partiel"]),
    ("Projets multi-niveaux consolidés (RDC/R+1…)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]),
    ("Calcul d'escaliers (béton + ferraillage + 3D)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]),
    ("Lecture DPGF / CCTP → devis chiffré", ["Oui", "—", "—", "—", "Option", "Oui", "—", "Oui", "Oui"]),
    ("Comparaison de versions de plans", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]),
    ("Assistant IA + agents métier orchestrés", ["Oui", "Partiel", "Non", "Partiel", "Non", "Non", "Non", "Partiel", "Oui (Rita)"]),
    ("Suivi de chantier / contrôle des coûts", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Partiel"]),
    ("Signature électronique", ["Oui", "Oui", "—", "—", "Oui", "Oui", "—", "Oui", "—"]),
    ("Dossier PDF brandé (page de garde, logo, filigrane)", ["Oui", "Partiel", "Partiel", "Partiel", "Partiel", "Partiel", "—", "Partiel", "Partiel"]),
    ("PDF multilingue (FR / EN / PT)", ["Oui", "—", "—", "—", "—", "—", "—", "—", "—"]),
]

PROFILES = [
    ("ConstruPilot", "dès l'essai",
     "SaaS de métré, chiffrage déterministe et gestion de chantier. Unique sur le marché à combiner métré sur plans "
     "(PDF/images + cotes natives DWG), détection murs/ouvertures, projets multi-niveaux consolidés, calcul d'escaliers "
     "béton/ferraillage 3D, assistant IA + agents métier — avec un chiffrage 0 % hallucination (l'IA oriente, les moteurs calculent)."),
    ("Obat", "25–109 €/mois HT",
     "Facturation et suivi de chantier BTP, bibliothèque de 30 000 ouvrages, situations de travaux, devis vocal IA. "
     "Métré depuis plan annoncé « à venir », pas de mode hors ligne."),
    ("Trustup Pro", "dès 49 €/mois",
     "Solution simple et abordable (Belgique/France) pour indépendants et < 20 ouvriers : devis/factures, planning, "
     "pointeuse mobile géolocalisée, conformité Peppol. Sans engagement."),
    ("Vertuoza", "2 400–5 000 €/an",
     "ERP complet pour structures > 30 ouvriers : stock, compta, planning de production, sous-traitants, devis vocal IA. "
     "Engagement 1 an, pas d'essai gratuit."),
    ("EBP Bâtiment", "29–69 €/mois HT",
     "Gamme Hubbix/ACTIV/PRO : devis-factures, stocks, situations, suivi de chantier avancé, multi-sociétés. "
     "Biblio Batichiffrage/Batiprix en option."),
    ("Batappli", "39–79 €/mois HT",
     "Spécialiste artisans : devis/factures avec bibliothèque Batichiffrage intégrée, suivi de chantier, stocks, "
     "contrats d'entretien, Factur-X incluse."),
    ("Alobees", "40–190 €/mois + 10 €/util.",
     "Orienté suivi de chantier et gestion d'équipe, nativement mobile. Pas de bibliothèque de prix ; "
     "facturation à l'utilisateur."),
    ("BatiChiffrage", "dès ~37–42 €/mois HT",
     "Référence de la bibliothèque de prix (80 000+ ouvrages, mise à jour permanente) + devis/factures et version "
     "Estimatifs pour MOE. Modes rapide et détaillé."),
    ("Renalto", "25–49 €/mois HT",
     "Assistant IA « Rita » : génère des devis depuis voix/photo/DPGF en ~30 s (brouillon à relire). Centré chiffrage, "
     "pas d'ERP, pas de mode hors ligne."),
]


def _logo_flow(h_mm):
    try:
        with open(LOGO, "rb") as f:
            raw = f.read()
        r = ImageReader(BytesIO(raw))
        iw, ih = r.getSize()
        w = h_mm * mm * iw / ih
        return RLImage(BytesIO(raw), width=w, height=h_mm * mm)
    except Exception:
        return ""


def _cell_para(val, is_cp):
    color = DARK
    bold = False
    if val == "Oui":
        color = colors.HexColor("#15803D"); bold = True
    elif val in ("Non", "Non (IA)"):
        color = colors.HexColor("#B91C1C")
    elif val in ("Partiel", "Option", "À venir") or val.startswith(("Oui (", "Partiel")):
        color = colors.HexColor("#B45309")
    st = ParagraphStyle("c", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=7.2,
                        textColor=color, leading=8.4, alignment=1)
    return Paragraph(val, st)


def build():
    buf = BytesIO()
    doc = BaseDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                          topMargin=14 * mm, bottomMargin=12 * mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")

    wm = None
    try:
        with open(LOGO, "rb") as f:
            wm_reader = ImageReader(BytesIO(f.read()))
        wiw, wih = wm_reader.getSize()
        wm = (wm_reader, wih / wiw)
    except Exception:
        wm = None

    def on_page(canvas, d):
        if wm:
            r, ratio = wm
            W = 90 * mm; H = W * ratio
            canvas.saveState()
            try:
                canvas.setFillAlpha(0.045)
            except Exception:
                pass
            canvas.drawImage(r, (landscape(A4)[0] - W) / 2, (landscape(A4)[1] - H) / 2,
                             width=W, height=H, mask="auto", preserveAspectRatio=True)
            canvas.restoreState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(14 * mm, 7 * mm, "ConstruPilot — Comparatif marché. Données publiques à la date d'édition, à vérifier avant usage contractuel.")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 7 * mm, f"Page {d.page}")

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])

    story = []
    # ----- Bandeau / entête -----
    banner = Table([[_logo_flow(16), [Paragraph("ConstruPilot", WBIG),
                                       Paragraph("Métré · Chiffrage déterministe · Gestion de chantier", WSM)]]],
                   colWidths=[24 * mm, None])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story.append(banner)
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("COMPARATIF MARCHÉ", KICK))
    story.append(Paragraph("ConstruPilot face aux solutions BTP", H1))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Obat · Trustup Pro · Vertuoza · EBP Bâtiment · Batappli · Alobees · BatiChiffrage · Renalto — "
                           f"édition du {datetime.now(timezone.utc).strftime('%d/%m/%Y')}.", MUT))
    story.append(Spacer(1, 5 * mm))

    # ----- Matrice -----
    header = [Paragraph("Fonctionnalité", CELLH)] + [Paragraph(c, CELLH) for c in COLS]
    data = [header]
    for feat, vals in ROWS:
        data.append([Paragraph(feat, FEAT)] + [_cell_para(v, i == 0) for i, v in enumerate(vals)])

    feat_w = 62 * mm
    cp_w = 24 * mm
    other_w = (doc.width - feat_w - cp_w) / (len(COLS) - 1)
    col_widths = [feat_w, cp_w] + [other_w] * (len(COLS) - 1)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("BACKGROUND", (1, 0), (1, 0), GREEN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT),
        ("BACKGROUND", (1, 1), (1, -1), TINT),
        ("LINEAFTER", (1, 0), (1, -1), 1.0, GREEN),
        ("LINEBEFORE", (1, 0), (1, -1), 1.0, GREEN),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in range(1, len(data)):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (0, r), colors.HexColor("#F8FAFC")))
            style.append(("BACKGROUND", (2, r), (-1, r), colors.HexColor("#F8FAFC")))
    t.setStyle(TableStyle(style))
    story.append(t)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Légende : <b>Oui</b> = disponible · <b>Partiel / Option / À venir</b> = partiel, en option ou annoncé · "
                           "<b>Non</b> = non proposé · <b>—</b> = non documenté publiquement.", MUT))

    # ----- Différenciateurs -----
    story.append(PageBreak())
    story.append(Paragraph("CE QUI DISTINGUE CONSTRUPILOT", KICK))
    story.append(Paragraph("Nos avantages clés", H1))
    story.append(Spacer(1, 4 * mm))
    diffs = [
        ("Chiffrage 100% déterministe", "Zéro hallucination sur les calculs : l'IA oriente, les moteurs calculent. Chaque montant est traçable et vérifiable — là où les générateurs « IA » produisent un brouillon à relire."),
        ("Du plan au devis, vraiment", "Métré sur PDF/images avec étalonnage, lecture des cotes natives DWG/DXF, détection murs & ouvertures, projets multi-niveaux consolidés : la plupart des concurrents s'arrêtent au devis saisi à la main."),
        ("Expertise technique rare", "Calcul d'escaliers béton + ferraillage avec aperçu 3D et PDF — introuvable chez les logiciels de devis généralistes."),
        ("Agents IA orchestrés", "Dossier automatique, devis, détection, comparaison, DPGF→devis : l'agent enchaîne vos moteurs, propose, vous validez, il apprend vos corrections."),
        ("Livrables haut de gamme", "Dossier PDF brandé (page de garde, logo, filigrane, total TTC), multilingue FR/EN/PT, signature en ligne."),
        ("Comparaison & contrôle", "Comparaison de versions de plans et contrôle des cotes : vous sécurisez le métré avant de chiffrer."),
    ]
    cards = []
    row = []
    for i, (t_, d_) in enumerate(diffs):
        cell = [Paragraph(t_, ParagraphStyle("dt", fontName="Helvetica-Bold", fontSize=10.5, textColor=GREEN, leading=13, spaceAfter=3)),
                Paragraph(d_, BODY)]
        row.append(cell)
        if len(row) == 3:
            cards.append(row); row = []
    if row:
        while len(row) < 3:
            row.append("")
        cards.append(row)
    ct = Table(cards, colWidths=[doc.width / 3] * 3)
    cst = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
           ("LINEBELOW", (0, 0), (-1, 0), 6, colors.white)]
    ct.setStyle(TableStyle(cst))
    story.append(ct)

    # ----- Fiches concurrents -----
    story.append(PageBreak())
    story.append(Paragraph("FICHES SYNTHÉTIQUES", KICK))
    story.append(Paragraph("Les solutions en un coup d'œil", H1))
    story.append(Spacer(1, 4 * mm))
    prof_rows = [[Paragraph("Solution", CELLH), Paragraph("Tarif indicatif (HT)", CELLH), Paragraph("Positionnement", CELLH)]]
    for name, price, desc in PROFILES:
        nm_style = ParagraphStyle("nm", fontName="Helvetica-Bold", fontSize=9,
                                  textColor=GREEN if name == "ConstruPilot" else DARK, leading=11)
        prof_rows.append([Paragraph(name, nm_style), Paragraph(price, BODY), Paragraph(desc, BODY)])
    pt = Table(prof_rows, colWidths=[34 * mm, 42 * mm, doc.width - 76 * mm], repeatRows=1)
    pstyle = [("BACKGROUND", (0, 0), (-1, 0), DARK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("GRID", (0, 0), (-1, -1), 0.4, LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]
    pstyle.append(("BACKGROUND", (0, 1), (-1, 1), TINT))
    pt.setStyle(TableStyle(pstyle))
    story.append(pt)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Sources : sites éditeurs et comparateurs spécialisés (Obat, Trustup, Vertuoza, EBP, Batappli, Alobees, "
                           "BatiChiffrage, Renalto) consultés à la date d'édition. Tarifs et fonctionnalités susceptibles d'évoluer ; "
                           "ce document est un support de positionnement et ne constitue pas un comparatif contractuel.", MUT))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    with open(OUT, "wb") as f:
        f.write(pdf)
    print("written", OUT, len(pdf), "bytes")


if __name__ == "__main__":
    build()
