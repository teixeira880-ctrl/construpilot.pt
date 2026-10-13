"""Générateur du PDF comparatif ConstruPilot (réutilisable + ciblage concurrent).

Données issues d'informations publiques à la date d'édition — support de
positionnement, non contractuel.
"""
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
DEFAULT_OUT = "/app/frontend/public/comparatif-construpilot.pdf"

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=24, textColor=DARK, leading=28)
KICK = ParagraphStyle("kick", fontName="Helvetica-Bold", fontSize=10, textColor=GREEN, leading=13, spaceAfter=3)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, textColor=DARK, leading=12)
MUT = ParagraphStyle("mut", fontName="Helvetica", fontSize=8, textColor=GREY, leading=11)
CELLH = ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=7.3, textColor=colors.white, leading=8.6, alignment=1)
FEAT = ParagraphStyle("feat", fontName="Helvetica-Bold", fontSize=7.6, textColor=DARK, leading=9)
WBIG = ParagraphStyle("wbig", fontName="Helvetica-Bold", fontSize=15, textColor=colors.white, leading=18)
WSM = ParagraphStyle("wsm", fontName="Helvetica", fontSize=8.5, textColor=colors.white, leading=11)

COLS = ["ConstruPilot", "Obat", "Trustup Pro", "Vertuoza", "EBP Bât.", "Batappli", "Alobees", "BatiChiffrage", "Renalto"]
SLUGS = {"obat": 1, "trustup": 2, "vertuoza": 3, "ebp": 4, "batappli": 5, "alobees": 6, "batichiffrage": 7, "renalto": 8}
FULLNAME = {"obat": "Obat", "trustup": "Trustup Pro", "vertuoza": "Vertuoza", "ebp": "EBP Bâtiment",
            "batappli": "Batappli", "alobees": "Alobees", "batichiffrage": "BatiChiffrage", "renalto": "Renalto"}

ROWS = [
    ("Devis & factures", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Partiel", "Oui", "Oui"]),
    ("Facturation électronique (Factur-X / Chorus Pro)", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "—", "Oui", "Oui"]),
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
     "SaaS de métré, chiffrage déterministe et gestion de chantier. Unique à combiner métré sur plans (PDF/images + cotes natives DWG), "
     "détection murs/ouvertures, projets multi-niveaux consolidés, calcul d'escaliers béton/ferraillage 3D et agents IA — avec un chiffrage 0 % hallucination."),
    ("Obat", "25–109 €/mois HT", "Facturation et suivi de chantier BTP, 30 000 ouvrages, situations de travaux, devis vocal IA. Métré depuis plan « à venir », pas de hors ligne."),
    ("Trustup Pro", "dès 49 €/mois", "Simple et abordable pour indépendants et < 20 ouvriers : devis/factures, planning, pointeuse mobile, Peppol. Sans engagement."),
    ("Vertuoza", "2 400–5 000 €/an", "ERP complet pour > 30 ouvriers : stock, compta, planning de production, sous-traitants, devis vocal IA. Engagement 1 an."),
    ("EBP Bâtiment", "29–69 €/mois HT", "Gamme Hubbix/ACTIV/PRO : devis-factures, stocks, situations, suivi avancé, multi-sociétés. Biblio Batichiffrage/Batiprix en option."),
    ("Batappli", "39–79 €/mois HT", "Spécialiste artisans : devis/factures avec Batichiffrage intégré, suivi de chantier, stocks, contrats d'entretien, Factur-X incluse."),
    ("Alobees", "40–190 €/mois + 10 €/util.", "Orienté suivi de chantier et gestion d'équipe, nativement mobile. Pas de bibliothèque de prix."),
    ("BatiChiffrage", "dès ~37–42 €/mois HT", "Référence de la bibliothèque de prix (80 000+ ouvrages) + devis/factures et version Estimatifs pour MOE."),
    ("Renalto", "25–49 €/mois HT", "Assistant IA « Rita » : devis depuis voix/photo/DPGF en ~30 s (brouillon à relire). Centré chiffrage, pas d'ERP."),
]

DIFFS = [
    ("Chiffrage 100% déterministe", "Zéro hallucination sur les calculs : l'IA oriente, les moteurs calculent. Chaque montant est traçable — là où les générateurs « IA » produisent un brouillon à relire."),
    ("Du plan au devis, vraiment", "Métré sur PDF/images avec étalonnage, cotes natives DWG/DXF, détection murs & ouvertures, projets multi-niveaux : la plupart s'arrêtent au devis saisi à la main."),
    ("Expertise technique rare", "Calcul d'escaliers béton + ferraillage avec aperçu 3D et PDF — introuvable chez les logiciels de devis généralistes."),
    ("Agents IA orchestrés", "Dossier, devis, détection, comparaison, DPGF→devis : l'agent enchaîne vos moteurs, propose, vous validez, il apprend vos corrections."),
    ("Livrables haut de gamme", "Dossier PDF brandé (page de garde, logo, filigrane, total TTC), multilingue FR/EN/PT, signature en ligne."),
    ("Comparaison & contrôle", "Comparaison de versions de plans et contrôle des cotes : vous sécurisez le métré avant de chiffrer."),
]


def _logo_flow(h_mm):
    try:
        with open(LOGO, "rb") as f:
            raw = f.read()
        r = ImageReader(BytesIO(raw)); iw, ih = r.getSize()
        return RLImage(BytesIO(raw), width=h_mm * mm * iw / ih, height=h_mm * mm)
    except Exception:
        return ""


def _cell_para(val):
    color, bold = DARK, False
    if val == "Oui":
        color, bold = colors.HexColor("#15803D"), True
    elif val in ("Non", "Non (IA)"):
        color = colors.HexColor("#B91C1C")
    elif val in ("Partiel", "Option", "À venir") or val.startswith(("Oui (", "Partiel")):
        color = colors.HexColor("#B45309")
    st = ParagraphStyle("c", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=7.2,
                        textColor=color, leading=8.4, alignment=1)
    return Paragraph(val, st)


def build(focus=None) -> bytes:
    focus_idx = SLUGS.get((focus or "").lower())
    buf = BytesIO()
    doc = BaseDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                          topMargin=14 * mm, bottomMargin=12 * mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")

    wm = None
    try:
        with open(LOGO, "rb") as f:
            wm = (ImageReader(BytesIO(f.read())),)
        wm = (wm[0], wm[0].getSize()[1] / wm[0].getSize()[0])
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
        canvas.setFont("Helvetica", 7); canvas.setFillColor(GREY)
        canvas.drawString(14 * mm, 7 * mm, "ConstruPilot — Comparatif marché. Données publiques à la date d'édition, à vérifier avant usage contractuel.")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 7 * mm, f"Page {d.page}")

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])

    story = []
    banner = Table([[_logo_flow(16), [Paragraph("ConstruPilot", WBIG),
                                       Paragraph("Métré · Chiffrage déterministe · Gestion de chantier", WSM)]]],
                   colWidths=[24 * mm, None])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story.append(banner)
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph("COMPARATIF MARCHÉ", KICK))
    if focus_idx:
        story.append(Paragraph(f"ConstruPilot, l'alternative à {FULLNAME[focus.lower()]}", H1))
    else:
        story.append(Paragraph("ConstruPilot face aux solutions BTP", H1))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Obat · Trustup Pro · Vertuoza · EBP Bâtiment · Batappli · Alobees · BatiChiffrage · Renalto — "
                           f"édition du {datetime.now(timezone.utc).strftime('%d/%m/%Y')}.", MUT))
    story.append(Spacer(1, 5 * mm))

    header = [Paragraph("Fonctionnalité", CELLH)] + [Paragraph(c, CELLH) for c in COLS]
    data = [header]
    for feat, vals in ROWS:
        data.append([Paragraph(feat, FEAT)] + [_cell_para(v) for v in vals])

    feat_w = 62 * mm; cp_w = 24 * mm
    other_w = (doc.width - feat_w - cp_w) / (len(COLS) - 1)
    col_widths = [feat_w, cp_w] + [other_w] * (len(COLS) - 1)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK), ("BACKGROUND", (1, 0), (1, 0), GREEN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT), ("BACKGROUND", (1, 1), (1, -1), TINT),
        ("LINEAFTER", (1, 0), (1, -1), 1.0, GREEN), ("LINEBEFORE", (1, 0), (1, -1), 1.0, GREEN),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in range(1, len(data)):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (0, r), colors.HexColor("#F8FAFC")))
            style.append(("BACKGROUND", (2, r), (-1, r), colors.HexColor("#F8FAFC")))
    col = 1 + focus_idx if focus_idx else None
    if col:
        style += [("BACKGROUND", (col, 0), (col, 0), colors.HexColor("#B45309")),
                  ("LINEBEFORE", (col, 0), (col, -1), 1.2, colors.HexColor("#B45309")),
                  ("LINEAFTER", (col, 0), (col, -1), 1.2, colors.HexColor("#B45309"))]
    t.setStyle(TableStyle(style))
    story.append(t)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Légende : <b>Oui</b> = disponible · <b>Partiel / Option / À venir</b> = partiel, en option ou annoncé · "
                           "<b>Non</b> = non proposé · <b>—</b> = non documenté publiquement.", MUT))

    story.append(PageBreak())
    story.append(Paragraph("CE QUI DISTINGUE CONSTRUPILOT", KICK))
    story.append(Paragraph("Nos avantages clés", H1))
    story.append(Spacer(1, 4 * mm))
    rows3, row = [], []
    for t_, d_ in DIFFS:
        row.append([Paragraph(t_, ParagraphStyle("dt", fontName="Helvetica-Bold", fontSize=10.5, textColor=GREEN, leading=13, spaceAfter=3)),
                    Paragraph(d_, BODY)])
        if len(row) == 3:
            rows3.append(row); row = []
    if row:
        while len(row) < 3:
            row.append("")
        rows3.append(row)
    ct = Table(rows3, colWidths=[doc.width / 3] * 3)
    ct.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story.append(ct)

    story.append(PageBreak())
    story.append(Paragraph("FICHES SYNTHÉTIQUES", KICK))
    story.append(Paragraph("Les solutions en un coup d'œil", H1))
    story.append(Spacer(1, 4 * mm))
    prof = [[Paragraph("Solution", CELLH), Paragraph("Tarif indicatif (HT)", CELLH), Paragraph("Positionnement", CELLH)]]
    for name, price, desc in PROFILES:
        nm = ParagraphStyle("nm", fontName="Helvetica-Bold", fontSize=9,
                            textColor=GREEN if name == "ConstruPilot" else DARK, leading=11)
        prof.append([Paragraph(name, nm), Paragraph(price, BODY), Paragraph(desc, BODY)])
    pt = Table(prof, colWidths=[34 * mm, 42 * mm, doc.width - 76 * mm], repeatRows=1)
    pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), DARK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("GRID", (0, 0), (-1, -1), 0.4, LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("BACKGROUND", (0, 1), (-1, 1), TINT)]))
    story.append(pt)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Sources : sites éditeurs et comparateurs spécialisés consultés à la date d'édition. Tarifs et fonctionnalités "
                           "susceptibles d'évoluer ; support de positionnement, non contractuel.", MUT))

    doc.build(story)
    pdf = buf.getvalue(); buf.close()
    return pdf


def write_default() -> int:
    pdf = build()
    with open(DEFAULT_OUT, "wb") as f:
        f.write(pdf)
    return len(pdf)


if __name__ == "__main__":
    print("written", DEFAULT_OUT, write_default(), "bytes")
