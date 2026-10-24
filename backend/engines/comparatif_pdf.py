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

COLS = ["ConstruPilot", "Obat", "Trustup Pro", "Vertuoza", "Primavera", "Batappli", "Alobees", "BatiChiffrage", "Renalto"]
SLUGS = {"obat": 1, "trustup": 2, "vertuoza": 3, "ebp": 4, "batappli": 5, "alobees": 6, "batichiffrage": 7, "renalto": 8}
FULLNAME = {"obat": "Obat", "trustup": "Trustup Pro", "vertuoza": "Vertuoza", "ebp": "PHC / Primavera",
            "batappli": "Batappli", "alobees": "Alobees", "batichiffrage": "BatiChiffrage", "renalto": "Renalto"}

ROWS = [
    ("Orçamentos e faturas", ["Sim", "Sim", "Sim", "Sim", "Sim", "Sim", "Parcial", "Sim", "Sim"]),
    ("Faturação eletrónica (SAF-T / QR code ATCUD)", ["Sim", "Sim", "Sim", "Sim", "Sim", "Sim", "—", "Sim", "Sim"]),
    ("Biblioteca de artigos e preços", ["Sim", "Sim (30k)", "Sim", "Sim", "Opção", "Sim", "Não", "Sim (80k)", "Sim (≤5k)"]),
    ("Orçamentação 100% determinística (0 IA na matemática)", ["Sim", "—", "—", "—", "—", "—", "—", "—", "Não (IA)"]),
    ("Medição em plantas (PDF/imagem) + calibração", ["Sim", "Em breve", "Não", "Não", "Não", "Não", "Não", "Não", "Parcial"]),
    ("Leitura das cotas nativas DWG / DXF", ["Sim", "Não", "Não", "Não", "Não", "Não", "Não", "Não", "Não"]),
    ("Deteção de paredes e vãos (IA / OpenCV)", ["Sim", "Não", "Não", "Não", "Não", "Não", "Não", "Não", "Parcial"]),
    ("Projetos multinível consolidados (R/C, 1.º andar…)", ["Sim", "Não", "Não", "Não", "Não", "Não", "Não", "Não", "Não"]),
    ("Cálculo de escadas (betão + armaduras + 3D)", ["Sim", "Não", "Não", "Não", "Não", "Não", "Não", "Não", "Não"]),
    ("Leitura de mapas de quantidades / cadernos de encargos → orçamento detalhado", ["Sim", "—", "—", "—", "Opção", "Sim", "—", "Sim", "Sim"]),
    ("Comparação de versões de plantas", ["Sim", "Não", "Não", "Não", "Não", "Não", "Não", "Não", "Não"]),
    ("Assistente IA + agentes especializados orquestrados", ["Sim", "Parcial", "Não", "Parcial", "Não", "Não", "Não", "Parcial", "Sim (Rita)"]),
    ("Acompanhamento de obra / controlo de custos", ["Sim", "Sim", "Sim", "Sim", "Sim", "Sim", "Sim", "Sim", "Parcial"]),
    ("Assinatura eletrónica", ["Sim", "Sim", "—", "—", "Sim", "Sim", "—", "Sim", "—"]),
    ("Processo PDF com a sua marca (página de rosto, logótipo, marca de água)", ["Sim", "Parcial", "Parcial", "Parcial", "Parcial", "Parcial", "—", "Parcial", "Parcial"]),
    ("PDF multilingue (FR / EN / PT)", ["Sim", "—", "—", "—", "—", "—", "—", "—", "—"]),
]

PROFILES = [
    ("ConstruPilot", "desde a experiência",
     "SaaS de medição, orçamentação determinística e gestão de obra. Único a combinar medição em plantas (PDF/imagens + cotas nativas DWG), deteção de paredes/vãos, projetos multinível consolidados, cálculo de escadas em betão/armaduras 3D e agentes IA — com uma orçamentação 0 % alucinações."),
    ("Obat", "25–109 €/mês s/ IVA", "Faturação e acompanhamento de obra, 30 000 artigos, autos de medição, orçamento por voz com IA. Medição a partir de planta «brevemente», sem modo offline."),
    ("Trustup Pro", "desde 49 €/mês", "Simples e acessível para independentes e < 20 trabalhadores: orçamentos/faturas, planeamento, registo de horas móvel, Peppol. Sem fidelização."),
    ("Vertuoza", "2 400–5 000 €/an", "ERP completo para > 30 trabalhadores: stock, contabilidade, planeamento de produção, subempreiteiros, orçamento por voz com IA. Fidelização de 1 ano."),
    ("PHC / Primavera", "29–69 €/mês s/ IVA", "Gama Hubbix/ACTIV/PRO: orçamentos-faturas, stocks, autos de medição, acompanhamento avançado, multiempresa. Biblioteca Batichiffrage/Batiprix em opção."),
    ("Batappli", "39–79 €/mês s/ IVA", "Especialista em profissionais: orçamentos/faturas com Batichiffrage integrado, acompanhamento de obra, stocks, contratos de manutenção, faturação eletrónica incluída."),
    ("Alobees", "40–190 €/mês + 10 €/utiliz.", "Orientado para o acompanhamento de obra e a gestão de equipa, nativamente móvel. Sem biblioteca de preços."),
    ("BatiChiffrage", "desde ~37–42 €/mês s/ IVA", "Referência de biblioteca de preços (80 000+ artigos) + orçamentos/faturas e versão de Estimativas para projetistas."),
    ("Renalto", "25–49 €/mês s/ IVA", "Assistente IA «Rita»: orçamento a partir de voz/fotografia/mapa de quantidades em ~30 s (rascunho a rever). Centrado na orçamentação, sem ERP."),
]

DIFFS = [
    ("Orçamentação 100% determinística", "Zero alucinações nos cálculos: a IA orienta, os motores calculam. Cada montante é rastreável — onde os geradores «IA» produzem um rascunho a rever."),
    ("Da planta ao orçamento, a sério", "Medição em PDF/imagens com calibração, cotas nativas DWG/DXF, deteção de paredes e vãos, projetos multinível: a maioria fica pelo orçamento introduzido à mão."),
    ("Expertise technique rare", "Cálculo de escadas em betão + armaduras com pré-visualização 3D e PDF — inexistente nos softwares de orçamentação generalistas."),
    ("Agentes IA orquestrados", "Processo, orçamento, deteção, comparação, mapa de quantidades→orçamento: o agente encadeia os seus motores, propõe, valida e aprende com as suas correções."),
    ("Entregáveis de topo", "Processo PDF com a sua marca (página de rosto, logótipo, marca de água, total c/ IVA), multilingue PT/EN/FR, assinatura online."),
    ("Comparação e controlo", "Comparação de versões de plantas e controlo das cotas: assegura a medição antes de orçamentar."),
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
    if val == "Sim":
        color, bold = colors.HexColor("#15803D"), True
    elif val in ("Não", "Não (IA)"):
        color = colors.HexColor("#B91C1C")
    elif val in ("Parcial", "Opção", "Em breve") or val.startswith(("Oui (", "Parcial")):
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
        canvas.drawString(14 * mm, 7 * mm, "ConstruPilot — Comparativo de mercado. Dados públicos à data de edição, a verificar antes de uso contratual.")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 7 * mm, f'Página {d.page}')

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])

    story = []
    banner = Table([[_logo_flow(16), [Paragraph("ConstruPilot", WBIG),
                                       Paragraph("Medição · Orçamentação determinística · Gestão de obra", WSM)]]],
                   colWidths=[24 * mm, None])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story.append(banner)
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph("COMPARATIVO DE MERCADO", KICK))
    if focus_idx:
        story.append(Paragraph(f'ConstruPilot, a alternativa a {FULLNAME[focus.lower()]}', H1))
    else:
        story.append(Paragraph("O ConstruPilot face às soluções de construção", H1))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"Obat · Trustup Pro · Vertuoza · EBP Bâtiment · Batappli · Alobees · BatiChiffrage · Renalto — edição de {datetime.now(timezone.utc).strftime('%d/%m/%Y')}.", MUT))
    story.append(Spacer(1, 5 * mm))

    header = [Paragraph("Funcionalidade", CELLH)] + [Paragraph(c, CELLH) for c in COLS]
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
    story.append(Paragraph("Legenda: <b>Sim</b> = disponível · <b>Parcial / Opção / Brevemente</b> = parcial, em opção ou anunciado · <b>Não</b> = não proposto · <b>—</b> = não documentado publicamente.", MUT))

    story.append(PageBreak())
    story.append(Paragraph("O QUE DISTINGUE O CONSTRUPILOT", KICK))
    story.append(Paragraph("As nossas vantagens principais", H1))
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
    story.append(Paragraph("FICHAS RESUMO", KICK))
    story.append(Paragraph("As soluções num relance", H1))
    story.append(Spacer(1, 4 * mm))
    prof = [[Paragraph("Solução", CELLH), Paragraph("Preço indicativo (s/ IVA)", CELLH), Paragraph("Positionnement", CELLH)]]
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
    story.append(Paragraph("Fontes: sites dos editores e comparadores especializados consultados à data de edição. Preços e funcionalidades suscetíveis de evoluir; suporte de posicionamento, não contratual.", MUT))

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
