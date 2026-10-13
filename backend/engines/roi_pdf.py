"""Génère le PDF « Économies & ROI ConstruPilot » (reportlab).

Deux blocs d'économie :
 A) Pertes réduites, en % du CA (matériaux, marge, litiges).
 B) Personnel & temps automatisés par l'IA (métré, devis, calculs, chiffrage, admin),
    exprimés en équivalent temps plein (ETP) x coût chargé.
Modèle transparent, hypothèses explicites — pas une garantie.
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

COPPER = colors.HexColor("#E07A5F")
GREEN = colors.HexColor("#0F5257")
CREAM = colors.HexColor("#FAF6EF")
INK = colors.HexColor("#1F2421")
GREY = colors.HexColor("#6B7280")
ALT = colors.HexColor("#F7F4EF")
LINE = colors.HexColor("#E5E1D8")


def _eur(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", " ") + " €"


def _fte_for(ca: float) -> float:
    """Équivalent temps plein (métré/devis/études/admin) automatisable selon la taille."""
    if ca < 300_000:
        return 0.4
    if ca < 750_000:
        return 0.75
    if ca < 1_500_000:
        return 1.25
    if ca < 3_000_000:
        return 2.0
    return 2.5


def build_roi_pdf(ca_annual: float = 500_000, materials_pct: float = 40,
                  salaire_brut: float = 2_900, charges_pct: float = 42,
                  frais_generes: float = 450, loaded_salary: float | None = None,
                  fte: float | None = None) -> bytes:
    ca_annual = max(0.0, float(ca_annual))
    ca_month = ca_annual / 12
    salaire_brut = max(0.0, float(salaire_brut))
    charges_pct = max(0.0, float(charges_pct))
    frais_generes = max(0.0, float(frais_generes))
    charges_eur = salaire_brut * charges_pct / 100
    cout_employeur = salaire_brut + charges_eur + frais_generes
    loaded = float(loaded_salary) if loaded_salary else cout_employeur
    fte_saved = _fte_for(ca_annual) if fte is None else max(0.0, float(fte))

    # A) pertes réduites (% CA) — typique 2 %, fourchette 1,3–3,5 %
    a_low, a_typ, a_high = ca_month * 0.013, ca_month * 0.02, ca_month * 0.035
    # B) personnel automatisé
    b_month = fte_saved * loaded
    tot_low, tot_typ, tot_high = a_low + b_month, a_typ + b_month, a_high + b_month

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=14 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            title="Économies & ROI — ConstruPilot")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=GREEN, fontSize=21, leading=24, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=COPPER, fontSize=10.5, leading=13, spaceAfter=9)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=GREEN, fontSize=12.5, leading=15, spaceBefore=11, spaceAfter=5)
    body = ParagraphStyle("body", parent=ss["Normal"], textColor=INK, fontSize=9.3, leading=13.5)
    small = ParagraphStyle("small", parent=ss["Normal"], textColor=GREY, fontSize=7.8, leading=10.5)
    cell = ParagraphStyle("cell", parent=ss["Normal"], textColor=INK, fontSize=8.4, leading=10.5)
    cellb = ParagraphStyle("cellb", parent=cell, textColor=GREEN, fontName="Helvetica-Bold")
    big = ParagraphStyle("big", parent=ss["Normal"], textColor=GREEN, fontSize=16, leading=18,
                         fontName="Helvetica-Bold", alignment=TA_CENTER)

    s = []
    s.append(Paragraph("Combien ConstruPilot fait économiser", h1))
    s.append(Paragraph("En % du chiffre d'affaires + le personnel et le temps automatisés par l'IA", sub))
    s.append(Paragraph(
        "ConstruPilot réduit des pertes bien réelles ET prend en charge, via l'IA, une grande partie du "
        "travail d'études : <b>métré, devis, calculs de quantités, chiffrage, suivi administratif</b>. "
        "On additionne donc deux blocs : (A) les pertes évitées, en % du CA, et (B) le coût du personnel / "
        "des heures que l'entreprise n'a plus besoin de mobiliser.", body))

    # ---- A) pertes ----
    s.append(Paragraph("A. Pertes réduites (en % du CA)", h2))
    arows = [
        [Paragraph("<b>Levier</b>", cell), Paragraph("<b>Fonctionnalité</b>", cell), Paragraph("<b>% du CA</b>", cell)],
        [Paragraph("Moins de gaspillage matériaux", cell), Paragraph("Calculateurs de quantités exactes", cell), Paragraph("0,5 – 1,5 %", cellb)],
        [Paragraph("Marge protégée (prix justes)", cell), Paragraph("Moteurs déterministes + marge dans le devis", cell), Paragraph("0,5 – 1,5 %", cellb)],
        [Paragraph("Moins de litiges / oublis", cell), Paragraph("Métré précis, comparaison avant/après", cell), Paragraph("0,3 – 0,5 %", cellb)],
        [Paragraph("<b>Sous-total A</b>", cellb), Paragraph("typique ~2 % du CA", cell), Paragraph("<b>1,3 – 3,5 %</b>", cellb)],
    ]
    at = Table(arows, colWidths=[58 * mm, 74 * mm, 36 * mm])
    at.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), CREAM),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, ALT]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    s.append(at)

    # ---- B) personnel ----
    s.append(Paragraph("B. Personnel & temps automatisés par l'IA", h2))
    s.append(Paragraph(
        "Le métré, les devis, les calculs et une partie du chiffrage/administratif sont réalisés par "
        "ConstruPilot. L'entreprise n'a donc plus besoin de mobiliser (ou de recruter) autant de temps "
        "d'un profil <b>métreur / deviseur / chargé d'études</b> — ou libère ce temps pour le chantier.", body))
    detrows = [
        [Paragraph("<b>Détail du coût employeur réel (par ETP)</b>", cellb), Paragraph("", cell)],
        [Paragraph("Salaire brut mensuel", cell), Paragraph(_eur(salaire_brut), cell)],
        [Paragraph(f"+ Charges patronales (URSSAF, retraite, chômage…) {charges_pct:.0f} %", cell),
         Paragraph("+ " + _eur(charges_eur), cell)],
        [Paragraph("+ Frais générés (poste, logiciels, mutuelle, congés…)", cell),
         Paragraph("+ " + _eur(frais_generes), cell)],
        [Paragraph("<b>= Coût employeur TOTAL / mois</b>", cellb), Paragraph("<b>" + _eur(loaded) + "</b>", cellb)],
    ]
    dt = Table(detrows, colWidths=[118 * mm, 50 * mm])
    dt.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), ALT), ("BACKGROUND", (0, -1), (-1, -1), CREAM),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    s.append(dt)
    s.append(Spacer(1, 4))
    brows = [
        [Paragraph("<b>Profil automatisé</b>", cell), Paragraph("<b>Coût chargé</b>", cell),
         Paragraph("<b>Équivalent ETP</b>", cell), Paragraph("<b>Économie / mois</b>", cell)],
        [Paragraph("Métreur / deviseur / chargé d'études", cell), Paragraph(_eur(loaded) + " / mois", cell),
         Paragraph(f"{fte_saved:.2f} ETP".replace(".", ","), cellb), Paragraph(_eur(b_month), cellb)],
    ]
    bt = Table(brows, colWidths=[72 * mm, 36 * mm, 30 * mm, 30 * mm])
    bt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), CREAM),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    s.append(bt)
    s.append(Paragraph(
        "Le « coût employeur total » intègre le salaire brut, les charges patronales (URSSAF, retraite, "
        "chômage, etc.) et les frais générés (poste de travail, logiciels, mutuelle, congés payés). Part "
        "automatisable selon la taille : 0,4 ETP pour un artisan, jusqu'à 2–2,5 ETP pour une PME structurée.", small))

    # ---- Encadré entreprise ----
    s.append(Paragraph("Pour votre entreprise", h2))
    head = Paragraph(f"CA : <b>{_eur(ca_annual)}</b>/an &bull; CA/mois : <b>{_eur(ca_month)}</b> &bull; "
                     f"coût employeur : <b>{_eur(loaded)}</b>/mois/ETP &bull; "
                     f"automatisé : <b>{('%.2f' % fte_saved).replace('.', ',')} ETP</b>", body)
    cells = Table([[
        Paragraph(_eur(a_typ) + "<br/><font size=7>A · pertes (2%)</font>", big),
        Paragraph(_eur(b_month) + "<br/><font size=7>B · personnel IA</font>", big),
        Paragraph(_eur(tot_typ) + "<br/><font size=7>TOTAL / mois</font>", big),
    ]], colWidths=[52 * mm, 52 * mm, 54 * mm])
    cells.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LINEAFTER", (0, 0), (1, 0), 0.5, LINE)]))
    box = Table([[head], [cells]], colWidths=[158 * mm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CREAM), ("BOX", (0, 0), (-1, -1), 1.2, COPPER),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    s.append(box)
    s.append(Spacer(1, 3))
    s.append(Paragraph(f"Fourchette totale : <b>{_eur(tot_low)} à {_eur(tot_high)} / mois</b> — soit, au "
                       f"scénario typique, <b>{_eur(tot_typ * 12)} / an</b>.", body))

    # ---- Tableau par taille ----
    s.append(Paragraph("Économie mensuelle selon la taille (A + B)", h2))
    hdr = [Paragraph("<b>CA annuel</b>", cell), Paragraph("<b>CA / mois</b>", cell),
           Paragraph("<b>A · pertes 2%</b>", cell), Paragraph("<b>B · personnel (ETP)</b>", cell),
           Paragraph("<b>TOTAL / mois</b>", cell)]
    rows = [hdr]
    for ca in (250_000, 500_000, 1_000_000, 2_000_000):
        m = ca / 12
        f = _fte_for(ca)
        b = f * loaded
        rows.append([Paragraph(_eur(ca), cell), Paragraph(_eur(m), cell),
                     Paragraph(_eur(m * 0.02), cell),
                     Paragraph(f"{_eur(b)} ({f:.2f})".replace(".", ","), cell),
                     Paragraph(_eur(m * 0.02 + b), cellb)])
    mt = Table(rows, colWidths=[30 * mm, 28 * mm, 28 * mm, 40 * mm, 32 * mm])
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    s.append(mt)
    s.append(Spacer(1, 7))
    s.append(Paragraph(
        "⚠ Modèle d'estimation avec hypothèses explicites, pas une garantie. Le résultat dépend du "
        "volume de devis, de la part des matériaux dans le CA, du coût chargé réel et de l'adhésion des "
        "équipes. ConstruPilot — des chiffres issus de moteurs déterministes, jamais inventés.", small))

    doc.build(s)
    return buf.getvalue()
