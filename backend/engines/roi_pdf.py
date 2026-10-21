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
                            title="Poupanças e ROI — ConstruPilot")
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
    s.append(Paragraph("Quanto faz o ConstruPilot poupar", h1))
    s.append(Paragraph("Em % do volume de negócios + o pessoal e o tempo automatizados pela IA", sub))
    s.append(Paragraph(
        "O ConstruPilot reduz perdas bem reais E assume, através da IA, uma grande parte do trabalho de estudos: <b>medição, orçamentos, cálculos de quantidades, orçamentação, acompanhamento administrativo</b>. Somamos portanto dois blocos: (A) as perdas evitadas, em % do volume de negócios, e (B) o custo do pessoal / das horas que a empresa já não precisa de mobilizar.", body))

    # ---- A) pertes ----
    s.append(Paragraph("A. Perdas reduzidas (em % do volume de negócios)", h2))
    arows = [
        [Paragraph("<b>Levier</b>", cell), Paragraph("<b>Funcionalidade</b>", cell), Paragraph("<b>% do volume de negócios</b>", cell)],
        [Paragraph("Menos desperdício de materiais", cell), Paragraph("Calculadoras de quantidades exatas", cell), Paragraph("0,5 – 1,5 %", cellb)],
        [Paragraph("Margem protegida (preços justos)", cell), Paragraph("Motores determinísticos + margem no orçamento", cell), Paragraph("0,5 – 1,5 %", cellb)],
        [Paragraph("Menos litígios / esquecimentos", cell), Paragraph("Medição precisa, comparação antes/depois", cell), Paragraph("0,3 – 0,5 %", cellb)],
        [Paragraph("<b>Subtotal A</b>", cellb), Paragraph("típico ~2 % do volume de negócios", cell), Paragraph("<b>1,3 – 3,5 %</b>", cellb)],
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
    s.append(Paragraph("B. Pessoal e tempo automatizados pela IA", h2))
    s.append(Paragraph(
        "A medição, os orçamentos, os cálculos e parte da orçamentação/administração são realizados pelo ConstruPilot. A empresa já não precisa de mobilizar (ou de recrutar) tanto tempo de um perfil <b>medidor / orçamentista / técnico de estudos</b> — ou liberta esse tempo para a obra.", body))
    detrows = [
        [Paragraph("<b>Detalhe do custo real para o empregador (por ETI)</b>", cellb), Paragraph("", cell)],
        [Paragraph("Salário bruto mensal", cell), Paragraph(_eur(salaire_brut), cell)],
        [Paragraph(f'+ Encargos patronais (Segurança Social, seguros…) {charges_pct:.0f} %', cell),
         Paragraph("+ " + _eur(charges_eur), cell)],
        [Paragraph("+ Custos gerados (posto, software, seguros, férias…)", cell),
         Paragraph("+ " + _eur(frais_generes), cell)],
        [Paragraph("<b>= Custo TOTAL para o empregador / mês</b>", cellb), Paragraph("<b>" + _eur(loaded) + "</b>", cellb)],
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
        [Paragraph("<b>Perfil automatizado</b>", cell), Paragraph("<b>Custo com encargos</b>", cell),
         Paragraph("<b>Equivalente ETI</b>", cell), Paragraph("<b>Poupança / mês</b>", cell)],
        [Paragraph("Medidor / orçamentista / técnico de estudos", cell), Paragraph(_eur(loaded) + " / mois", cell),
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
        "O «custo total para o empregador» integra o salário bruto, os encargos patronais (Segurança Social, seguro de acidentes de trabalho, etc.) e os custos gerados (posto de trabalho, software, seguros, férias pagas). Parte automatizável segundo a dimensão: 0,4 ETI para um profissional independente, até 2–2,5 ETI para uma PME estruturada.", small))

    # ---- Encadré entreprise ----
    s.append(Paragraph("Para a sua empresa", h2))
    head = Paragraph(f"CA : <b>{_eur(ca_annual)}</b>/ano &bull; VN/mês: <b>{_eur(ca_month)}</b> &bull; custo para o empregador: <b>{_eur(loaded)}</b>/mês/ETI &bull; automatizado: <b>{('%.2f' % fte_saved).replace('.', ',')} ETI</b>", body)
    cells = Table([[
        Paragraph(_eur(a_typ) + "<br/><font size=7>A · perdas (2%)</font>", big),
        Paragraph(_eur(b_month) + "<br/><font size=7>B · personnel IA</font>", big),
        Paragraph(_eur(tot_typ) + "<br/><font size=7>TOTAL / mês</font>", big),
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
    s.append(Paragraph(f'Intervalo total: <b>{_eur(tot_low)} à {_eur(tot_high)} / mês</b> — ou seja, no cenário típico, <b>{_eur(tot_typ * 12)} / an</b>.', body))

    # ---- Tableau par taille ----
    s.append(Paragraph("Poupança mensal segundo a dimensão (A + B)", h2))
    hdr = [Paragraph("<b>CA annuel</b>", cell), Paragraph("<b>VN / mês</b>", cell),
           Paragraph("<b>A · perdas 2%</b>", cell), Paragraph("<b>B · pessoal (ETI)</b>", cell),
           Paragraph("<b>TOTAL / mês</b>", cell)]
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
        "⚠ Modelo de estimativa com hipóteses explícitas, não uma garantia. O resultado depende do volume de orçamentos, do peso dos materiais no volume de negócios, do custo real com encargos e da adesão das equipas. ConstruPilot — números provenientes de motores determinísticos, nunca inventados.", small))

    doc.build(s)
    return buf.getvalue()
