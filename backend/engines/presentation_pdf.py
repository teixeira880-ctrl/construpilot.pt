"""Plaquettes PDF ConstruPilot : version client (personnalisable) et version investisseur.

- `build_client_pdf(lang, branding)` : plaquette commerciale, en-tête à la marque de
  l'entreprise abonnée (logo, nom, coordonnées) si `branding` est fourni.
- `build_investor_pdf(lang, metrics, budget)` : présentation investisseur ; les KPI de
  traction viennent des mesures réelles (`engines.journey.journey_metrics`). Une valeur
  non mesurable s'affiche « non mesurable », jamais 0 et jamais un chiffre reconstitué.
"""
from __future__ import annotations

import base64
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

FONT_DIR = "/usr/share/fonts/truetype/freefont/"
FALLBACK = {"Sans": "Helvetica", "Sans-Bold": "Helvetica-Bold", "Sans-Italic": "Helvetica-Oblique"}
_FONTS = {"ready": False, "family": "Sans"}


def _ensure_fonts() -> str:
    """Charge FreeSans à la première génération ; repli sur Helvetica si la police est absente.

    L'enregistrement est paresseux : un système sans FreeSans ne doit pas empêcher le
    démarrage du serveur, seulement changer la police du PDF.
    """
    if _FONTS["ready"]:
        return _FONTS["family"]
    _FONTS["ready"] = True
    try:
        for name, file in (("Sans", "FreeSans.ttf"), ("Sans-Bold", "FreeSansBold.ttf"),
                           ("Sans-Italic", "FreeSansOblique.ttf")):
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, FONT_DIR + file))
        pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold",
                                      italic="Sans-Italic", boldItalic="Sans-Bold")
    except Exception:  # noqa: BLE001 — police absente : on bascule sur les polices intégrées
        _FONTS["family"] = "Helvetica"
        for style in S.values():
            style.fontName = FALLBACK.get(style.fontName, "Helvetica")
    return _FONTS["family"]


GREEN = colors.HexColor("#15803D")
DEEP = colors.HexColor("#0B3B25")
DARK = colors.HexColor("#111827")
GREY = colors.HexColor("#5b6472")
LIGHT = colors.HexColor("#F1F6F2")
GRID = colors.HexColor("#D5DDD7")

S = {
    "over": ParagraphStyle("o", fontName="Sans-Bold", fontSize=8, leading=10, textColor=GREEN),
    "title": ParagraphStyle("t", fontName="Sans-Bold", fontSize=25, leading=28, textColor=DEEP),
    "sub": ParagraphStyle("s", fontName="Sans", fontSize=10.5, leading=15, textColor=GREY),
    "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=13, leading=16, textColor=DEEP,
                         spaceBefore=10, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName="Sans-Bold", fontSize=10, leading=13, textColor=GREEN,
                         spaceBefore=6, spaceAfter=2),
    "body": ParagraphStyle("b", fontName="Sans", fontSize=9.4, leading=13.2, textColor=DARK),
    "li": ParagraphStyle("li", fontName="Sans", fontSize=9.2, leading=12.8, textColor=DARK,
                         leftIndent=8, bulletIndent=1, spaceAfter=1.5),
    "cell": ParagraphStyle("c", fontName="Sans", fontSize=8.4, leading=11, textColor=DARK),
    "cellb": ParagraphStyle("cb", fontName="Sans-Bold", fontSize=8.4, leading=11, textColor=DEEP),
    "head": ParagraphStyle("h", fontName="Sans-Bold", fontSize=8.2, leading=10,
                           textColor=colors.white),
    "note": ParagraphStyle("n", fontName="Sans-Italic", fontSize=7.8, leading=10, textColor=GREY),
    "kpi": ParagraphStyle("k", fontName="Sans-Bold", fontSize=14, leading=16, textColor=DEEP),
    "kpil": ParagraphStyle("kl", fontName="Sans", fontSize=7.4, leading=9.2, textColor=GREY),
    "brand": ParagraphStyle("br", fontName="Sans-Bold", fontSize=10.5, leading=13, textColor=DEEP),
    "brandl": ParagraphStyle("brl", fontName="Sans", fontSize=8, leading=10.5, textColor=GREY),
}

SITE = "construpilot.pt"
CONTACT = "info@construpilot.pt"
PATENT = "FR2611044"
# Source unique de l'offre (miroir de GET /api/offer)
OFFER = {"free_promo": True, "trial_days": 7,
         "particulier": 19.0, "pro": 149.0, "api": 99.0, "addon": 5.0}


def _bul(items):
    return [Paragraph(f"• {t}", S["li"]) for t in items]


def _table(rows, widths, header=True):
    data = []
    for i, r in enumerate(rows):
        style = "head" if (header and i == 0) else "cell"
        data.append([Paragraph(str(c), S[style]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.3, GRID),
            ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, LIGHT])]
    if header:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), DEEP))
    t.setStyle(TableStyle(cmds))
    return t


def _kpis(items):
    """items : [(label, valeur)] — 4 colonnes maximum."""
    cols = [Table([[Paragraph(str(v), S["kpi"])], [Paragraph(k, S["kpil"])]]) for k, v in items]
    t = Table([cols], colWidths=[(174 / len(cols)) * mm] * len(cols))
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                           ("BOX", (0, 0), (-1, -1), 0.3, GRID),
                           ("INNERGRID", (0, 0), (-1, -1), 0.3, GRID),
                           ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def _logo(branding: dict | None):
    raw = (branding or {}).get("logo_b64") or (branding or {}).get("photo_b64")
    if not raw:
        return None
    try:
        if "," in raw:
            raw = raw.split(",", 1)[1]
        img = ImageReader(io.BytesIO(base64.b64decode(raw)))
        w, h = img.getSize()
        height = 14 * mm
        return Image(img, width=height * w / h, height=height)
    except Exception:  # noqa: BLE001 — un logo illisible ne bloque pas la plaquette
        return None


def _brand_header(branding: dict | None):
    if not branding:
        return []
    name = branding.get("company_name") or ""
    infos = " · ".join(filter(None, [
        branding.get("contact_line"),
        " ".join(filter(None, [branding.get("postal"), branding.get("city")])),
        branding.get("company_email"),
        f"Estabelecimento {branding['siret']}" if branding.get("siret") else None]))
    if not name and not infos:
        return []
    logo = _logo(branding)
    left = [Paragraph(name, S["brand"])]
    if infos:
        left.append(Paragraph(infos, S["brandl"]))
    row = [[Table([[p] for p in left]), logo or ""]]
    t = Table(row, colWidths=[124 * mm, 50 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.6, GREEN),
                           ("BOTTOMPADDING", (0, 0), (-1, 0), 6)]))
    return [t, Spacer(1, 5 * mm)]


def _cover(title, subtitle, audience, branding=None):
    E = _brand_header(branding)
    E += [Paragraph("CONSTRUPILOT · SOFTWARE DE CONSTRUÇÃO", S["over"]),
          Paragraph(title, S["title"]), Spacer(1, 3 * mm),
          Paragraph(subtitle, S["sub"]), Spacer(1, 4 * mm)]
    band = Table([[Paragraph(audience, S["head"])]], colWidths=[174 * mm])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN),
                              ("TOPPADDING", (0, 0), (-1, -1), 6),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                              ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return E + [band, Spacer(1, 6 * mm)]


def _build(flow, footer_left: str) -> bytes:
    buf = io.BytesIO()
    today = date.today().strftime("%d/%m/%Y")
    base = _ensure_fonts()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(base, 7.2)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 12 * mm, footer_left)
        canvas.drawRightString(192 * mm, 12 * mm, f"{today} · page {doc.page}")
        canvas.setStrokeColor(GRID)
        canvas.line(18 * mm, 15 * mm, 192 * mm, 15 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=20 * mm, title="ConstruPilot",
                            author="ConstruPilot")
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ════════════════════════════════  Plaquette client  ════════════════════════════════

CLIENT = {
    "fr": {
        "title": "Tudo o que o ConstruPilot faz pela sua empresa",
        "sub": "Da primeira chamada do cliente até ao saldo da obra: orçamentação, orçamentos, acompanhamento de obra e faturação numa única ferramenta, pensada para artesãos e PME da construção.",
        "aud": "Apresentação a clientes · artesãos, empresas gerais, PME da construção",
        "h_today": "O dia a dia que o ConstruPilot substitui",
        "p_today": "Um orçamento escrito à noite numa folha de cálculo, uma medição refeita três vezes, um mapa de quantidades do arquiteto orçamentado à mão, avisos esquecidos, adiantamentos que ninguém encontra na hora do auto de medição. O ConstruPilot encadeia estas etapas sem reintroduzir dados: cada informação introduzida uma vez serve em todo o resto.",
        "h1": "1. Orçamentar e fazer assinar",
        "b1": [
            "<b>Estimativa rápida</b>: área, tipo de trabalhos, nível de acabamento — um orçamento inicial para apresentar ao cliente.",
            "<b>Medições sobre planta</b>: importação PDF/DWG, definição de escala, medição de comprimentos e áreas, quantidades exportáveis (Excel/PDF).",
            "<b>DPGF · BPU · DQE do arquiteto</b>: carregue os mapas Excel e os cadernos de encargos, os lotes são detetados, a orçamentação usa <b>os seus</b> preços e depois a IA para as linhas desconhecidas, instruções em linguagem natural («não orçamentes a cerâmica nem o parquet, margem 12 %»), alerta sobre trabalhos exigidos no caderno de encargos mas ausentes do mapa, e passagem a orçamento num clique.",
            "<b>Consulta a subempreiteiros</b>: envio de um lote por e-mail, resposta online sem conta, comparação das propostas com o desvio em % e preço escolhido num clique.",
            "<b>Orçamentos profissionais</b>: 3 apresentações, o seu logótipo e a sua cor, descritivos detalhados, IVA 5,5 / 10 / 20 %, código QR de assinatura, envio por e-mail, reativação automática aos 7 dias, assinatura no local.",
            "<b>Ditado</b>: orçamentos, reservas e mensagens ditados por voz, útil com as mãos sujas na obra.",
        ],
        "h2": "2. Acompanhar a obra",
        "b2": [
            "<b>Processo de obra</b>: planeamento, tarefas, fotografias antes/depois, reservas, relatórios.",
            "<b>Espaço do cliente</b>: o seu cliente segue o progresso, troca mensagens, comunica um problema e encontra os seus documentos — sem ver as outras obras.",
            "<b>Subempreiteiros e fornecedores</b>: fichas, trocas de mensagens, pedidos de preço, acompanhamento dos aprovisionamentos.",
            "<b>Assistente de IA da construção</b>: respostas técnicas (normas DTU, métodos de execução, dosagens) e apoio à redação, com os seus documentos em contexto.",
        ],
        "h3": "3. Faturar sem perder nada",
        "b3": [
            "<b>Adiantamento na assinatura</b>: a fatura de adiantamento é gerada automaticamente assim que o orçamento é assinado.",
            "<b>Autos de medição</b>: faturação por progresso linha a linha, retenção de garantia, conta em PDF e certificado de pagamento.",
            "<b>Adiantamento deduzido automaticamente</b>: só o adiantamento efetivamente recebido é imputado (proporcional, total ou valor escolhido).",
            "<b>Conta final</b>: num clique, o saldo do contrato com o adiantamento restante deduzido e, se quiser, a libertação da retenção de garantia.",
            "<b>Acompanhamento dos pagamentos</b>: pagamentos, valores em dívida, avisos, notas de crédito, exportações contabilísticas.",
        ],
        "h_gain": "O que ganha concretamente",
        "gain": [["Situação", "Com o ConstruPilot"],
                 ["Um mapa do arquiteto com 40 linhas para orçamentar", "Mapa carregado, lotes detetados, preços propostos linha a linha, orçamento gerado com os descritivos"],
                 ["Uma medição para refazer sobre planta", "Medições diretamente no PDF/DWG, quantidades exportadas, transportadas para o orçamento"],
                 ["Um orçamento assinado na semana passada", "Fatura de adiantamento já criada, reativação automática se não houver resposta"],
                 ["Um auto de medição mensal para elaborar", "Progresso em %, adiantamento recebido deduzido, retenção calculada, conta em PDF pronta"],
                 ["O fim da obra", "Conta final: saldo, adiantamento, retenção — um único documento"],
                 ["Um cliente que pergunta como vai a obra", "Abre o seu espaço e vê o progresso, as fotografias e os documentos"]],
        "h_price": "Preços",
        "p_price": f"Uma única fonte de verdade para a oferta, apresentada em tempo real em {SITE}/tarifs. À la date de ce document : essai de {OFFER['trial_days']} jours"
                   + (" e fase de lançamento gratuita em curso." if OFFER["free_promo"] else "."),
        "price": [["Plano", "Para quem", "Preço de entrada"],
                  ["Particular", "Um projeto pessoal, uma estimativa, acompanhamento de obras", f"{OFFER['particulier']:.0f} € / mois"],
                  ["Profissional", "Artesãos e PME: orçamentos, obras, faturas, espaço do cliente", f"{OFFER['pro']:.0f} € / mois"],
                  ["API / integração", "Editores e grandes contas que ligam as suas ferramentas", f"{OFFER['api']:.0f} € / mois"],
                  ["Opções", "Módulos adicionais (faturação avançada, etc.)", f"a partir de {OFFER['addon']:.0f} € / mois"]],
        "note_price": "Os preços apresentados na aplicação prevalecem; este documento é indicativo e não constitui um orçamento contratual.",
        "h_data": "Os seus dados",
        "b_data": [
            "Alojamento na União Europeia, autenticação por cookie seguro, isolamento estrito dos dados entre empresas.",
            "Sem revenda de dados. Os seus preços e os seus clientes continuam a ser seus.",
            f'Eliminação da conta e dos dados de forma autónoma: {SITE}/suppression-compte · demande de suppression de données : {SITE}/suppression-donnees',
            "Estimativas e preços indicativos: ajudam a decidir, o autor do orçamento continua a ser você.",
        ],
        "h_start": "Começar",
        "p_start": f'1. Crie a sua conta em <b>{SITE}</b> · 2. Importe a sua biblioteca de preços (ou deixe o ConstruPilot construí-la a partir das suas orçamentações) · 3. Carregue o seu primeiro mapa de quantidades ou crie o seu primeiro orçamento. Uma pergunta? <b>{CONTACT}</b>.',
    },
    "en": {
        "title": "Everything ConstruPilot does for your construction business",
        "sub": "From the first client call to the final account: pricing, quotes, site monitoring and "
               "invoicing in a single tool, built for trade contractors and construction SMEs.",
        "aud": "Client presentation · trade contractors, main contractors, construction SMEs",
        "h_today": "The daily routine ConstruPilot replaces",
        "p_today": "A quote typed into a spreadsheet at night, a take-off redone three times, an "
                   "architect's priced bill of quantities filled in by hand, forgotten follow-ups, "
                   "deposits nobody can find when the progress invoice is due. ConstruPilot chains "
                   "these steps without re-entry: information entered once is reused everywhere.",
        "h1": "1. Price the job and get it signed",
        "b1": [
            "<b>Fast estimate</b>: area, type of works, finish level — an opening budget to show the client.",
            "<b>On-plan take-off</b>: PDF/DWG import, scaling, length and area measurement, exportable quantities (Excel/PDF).",
            "<b>Architect's bill of quantities (DPGF/BPU/DQE)</b>: drop the Excel schedules and the specifications, lots are detected, pricing uses <b>your</b> price library first then AI for unknown items, plain-language instructions (\"don't price the tiling or the parquet, 12% markup\"), alerts on items required by the specification but missing from the schedule, then one click to a quote.",
            "<b>Subcontractor enquiries</b>: send a lot by e-mail, they answer online without an account, offers compared with the gap in % and the chosen price applied in one click.",
            "<b>Professional quotes</b>: 3 layouts, your logo and colour, detailed descriptions, French VAT rates, signature QR code, e-mail sending, automatic 7-day follow-up, on-site signature.",
            "<b>Voice dictation</b>: quotes, snags and messages dictated hands-free on site.",
        ],
        "h2": "2. Run the site",
        "b2": [
            "<b>Site file</b>: schedule, tasks, before/after photos, snags, reports.",
            "<b>Client portal</b>: your client follows progress, chats, reports an issue and finds their documents — without seeing other projects.",
            "<b>Subcontractors and suppliers</b>: records, messages, price enquiries, deliveries.",
            "<b>Construction AI assistant</b>: technical answers (French DTU standards, methods, mixes) and writing help, using your own documents as context.",
        ],
        "h3": "3. Invoice without losing money",
        "b3": [
            "<b>Deposit on signature</b>: the deposit invoice is created automatically as soon as the quote is signed.",
            "<b>Progress accounts</b>: line-by-line progress invoicing, retention, PDF statement and payment certificate.",
            "<b>Deposit offset automatically</b>: only the deposit actually received is offset (pro rata, in full, or a chosen amount).",
            "<b>Final account</b>: one click for the balance of the contract, remaining deposit offset and, if you wish, release of retention.",
            "<b>Payment tracking</b>: payments, outstanding balances, reminders, credit notes, accounting exports.",
        ],
        "h_gain": "What you gain, concretely",
        "gain": [["Situação", "With ConstruPilot"],
                 ["A 40-line architect's schedule to price", "Schedule uploaded, lots detected, prices proposed line by line, quote generated with descriptions"],
                 ["A take-off to redo on plan", "Measurements straight on the PDF/DWG, quantities exported, carried into the quote"],
                 ["A quote signed last week", "Deposit invoice already created, automatic follow-up if no answer"],
                 ["A monthly progress account", "Progress entered in %, deposit received offset, retention computed, PDF statement ready"],
                 ["End of the project", "Final account: balance, deposit, retention — a single document"],
                 ["A client asking where things stand", "They open their portal and see progress, photos and documents"]],
        "h_price": "Pricing",
        "p_price": f"A single source of truth for the offer, shown live on {SITE}/tarifs. "
                   f"At the date of this document: {OFFER['trial_days']}-day trial"
                   + (" and a free launch phase in progress." if OFFER["free_promo"] else "."),
        "price": [["Planta", "For whom", "Entry price"],
                  ["Individual", "A personal project, an estimate, works monitoring", f"€{OFFER['particulier']:.0f} / month"],
                  ["Professional", "Trade contractors and SMEs: quotes, sites, invoices, client portal", f"€{OFFER['pro']:.0f} / month"],
                  ["API / integration", "Software vendors and large accounts connecting their tools", f"€{OFFER['api']:.0f} / month"],
                  ["Add-ons", "Additional modules (advanced invoicing, etc.)", f"from €{OFFER['addon']:.0f} / month"]],
        "note_price": "Prices displayed in the application prevail; this document is indicative and "
                      "is not a contractual quotation.",
        "h_data": "Your data",
        "b_data": [
            "Hosted in the European Union, secure cookie authentication, strict data isolation between companies.",
            "No data resale. Your prices and your clients remain yours.",
            f"Self-service account and data deletion: {SITE}/delete-account · data deletion request: {SITE}/data-deletion",
            "Estimates and prices are indicative: they help you decide, you remain the author of the quote.",
        ],
        "h_start": "Getting started",
        "p_start": f"1. Create your account on <b>{SITE}</b> · 2. Import your price library (or let "
                   "ConstruPilot build it from your own pricing work) · 3. Upload your first "
                   f"schedule of quantities or create your first quote. Questions? <b>{CONTACT}</b>.",
    },
    "pt": {
        "title": "Tudo o que o ConstruPilot faz pela sua empresa",
        "sub": "Da primeira chamada do cliente até ao saldo da obra: orçamentação, orçamentos, "
               "acompanhamento de obra e faturação numa única ferramenta, pensada para artesãos e "
               "PME da construção.",
        "aud": "Apresentação a clientes · artesãos, empresas gerais, PME da construção",
        "h_today": "O dia a dia que o ConstruPilot substitui",
        "p_today": "Um orçamento escrito à noite numa folha de cálculo, uma medição refeita três "
                   "vezes, um mapa de quantidades do arquiteto orçamentado à mão, avisos esquecidos, "
                   "adiantamentos que ninguém encontra na hora do auto de medição. O ConstruPilot "
                   "encadeia estas etapas sem reintroduzir dados: cada informação introduzida uma "
                   "vez serve em todo o resto.",
        "h1": "1. Orçamentar e fazer assinar",
        "b1": [
            "<b>Estimativa rápida</b>: área, tipo de trabalhos, nível de acabamento — um orçamento inicial para apresentar ao cliente.",
            "<b>Medições sobre planta</b>: importação PDF/DWG, definição de escala, medição de comprimentos e áreas, quantidades exportáveis (Excel/PDF).",
            "<b>DPGF · BPU · DQE do arquiteto</b>: carregue os mapas Excel e os cadernos de encargos, os lotes são detetados, a orçamentação usa <b>os seus</b> preços e depois a IA para as linhas desconhecidas, instruções em linguagem natural (« não orçamentes a cerâmica nem o parquet, margem 12 % »), alerta sobre trabalhos exigidos no caderno de encargos mas ausentes do mapa, e passagem a orçamento num clique.",
            "<b>Consulta a subempreiteiros</b>: envio de um lote por e-mail, resposta online sem conta, comparação das propostas com o desvio em % e preço escolhido num clique.",
            "<b>Orçamentos profissionais</b>: 3 apresentações, o seu logótipo e a sua cor, descritivos detalhados, IVA 5,5 / 10 / 20 %, código QR de assinatura, envio por e-mail, reativação automática aos 7 dias, assinatura no local.",
            "<b>Ditado</b>: orçamentos, reservas e mensagens ditados por voz, útil com as mãos sujas na obra.",
        ],
        "h2": "2. Acompanhar a obra",
        "b2": [
            "<b>Processo de obra</b>: planeamento, tarefas, fotografias antes/depois, reservas, relatórios.",
            "<b>Espaço do cliente</b>: o seu cliente segue o progresso, troca mensagens, comunica um problema e encontra os seus documentos — sem ver as outras obras.",
            "<b>Subempreiteiros e fornecedores</b>: fichas, trocas de mensagens, pedidos de preço, acompanhamento dos aprovisionamentos.",
            "<b>Assistente de IA da construção</b>: respostas técnicas (normas NP EN, especificações LNEC, métodos de execução, dosagens) e apoio à redação, com os seus documentos em contexto.",
        ],
        "h3": "3. Faturar sem perder nada",
        "b3": [
            "<b>Adiantamento na assinatura</b>: a fatura de adiantamento é gerada automaticamente assim que o orçamento é assinado.",
            "<b>Autos de medição</b>: faturação por progresso linha a linha, retenção de garantia, conta em PDF e certificado de pagamento.",
            "<b>Adiantamento deduzido automaticamente</b>: só o adiantamento efetivamente recebido é imputado (proporcional, total ou valor escolhido).",
            "<b>Conta final</b>: num clique, o saldo do contrato com o adiantamento restante deduzido e, se quiser, a libertação da retenção de garantia.",
            "<b>Acompanhamento dos pagamentos</b>: pagamentos, valores em dívida, avisos, notas de crédito, exportações contabilísticas.",
        ],
        "h_gain": "O que ganha concretamente",
        "gain": [["Situação", "Com o ConstruPilot"],
                 ["Um mapa do arquiteto com 40 linhas para orçamentar", "Mapa carregado, lotes detetados, preços propostos linha a linha, orçamento gerado com os descritivos"],
                 ["Uma medição para refazer sobre planta", "Medições diretamente no PDF/DWG, quantidades exportadas, transportadas para o orçamento"],
                 ["Um orçamento assinado na semana passada", "Fatura de adiantamento já criada, reativação automática se não houver resposta"],
                 ["Um auto de medição mensal para elaborar", "Progresso em %, adiantamento recebido deduzido, retenção calculada, conta em PDF pronta"],
                 ["O fim da obra", "Conta final: saldo, adiantamento, retenção — um único documento"],
                 ["Um cliente que pergunta como vai a obra", "Abre o seu espaço e vê o progresso, as fotografias e os documentos"]],
        "h_price": "Preços",
        "p_price": f"Uma única fonte de verdade para a oferta, apresentada em tempo real em {SITE}/tarifs. "
                   f"À data deste documento: teste de {OFFER['trial_days']} dias"
                   + (" e fase de lançamento gratuita em curso." if OFFER["free_promo"] else "."),
        "price": [["Plano", "Para quem", "Preço de entrada"],
                  ["Particular", "Um projeto pessoal, uma estimativa, acompanhamento de obras", f"{OFFER['particulier']:.0f} € / mês"],
                  ["Profissional", "Artesãos e PME: orçamentos, obras, faturas, espaço do cliente", f"{OFFER['pro']:.0f} € / mês"],
                  ["API / integração", "Editores e grandes contas que ligam as suas ferramentas", f"{OFFER['api']:.0f} € / mês"],
                  ["Opções", "Módulos adicionais (faturação avançada, etc.)", f"a partir de {OFFER['addon']:.0f} € / mês"]],
        "note_price": "Os preços apresentados na aplicação prevalecem; este documento é indicativo e "
                      "não constitui um orçamento contratual.",
        "h_data": "Os seus dados",
        "b_data": [
            "Alojamento na União Europeia, autenticação por cookie seguro, isolamento estrito dos dados entre empresas.",
            "Sem revenda de dados. Os seus preços e os seus clientes continuam a ser seus.",
            f"Eliminação autónoma da conta e dos dados: {SITE}/suppression-compte · pedido de eliminação de dados: {SITE}/suppression-donnees",
            "Estimativas e preços indicativos: ajudam a decidir, o autor do orçamento continua a ser você.",
        ],
        "h_start": "Começar",
        "p_start": f"1. Crie a sua conta em <b>{SITE}</b> · 2. Importe a sua biblioteca de preços "
                   "(ou deixe o ConstruPilot construí-la a partir das suas orçamentações) · 3. "
                   f"Carregue o primeiro mapa de quantidades ou crie o primeiro orçamento. Dúvidas? <b>{CONTACT}</b>.",
    },
}

def build_client_pdf(lang: str = "pt", branding: dict | None = None,
                     prospect: str | None = None) -> bytes:
    _ensure_fonts()
    t = CLIENT.get(lang) or CLIENT["fr"]
    E = _cover(t["title"], t["sub"], t["aud"], branding)
    if prospect:
        prepared = {"en": "Prepared for", "pt": "Preparado para"}.get(lang, "Preparado para")
        today = date.today().isoformat() if lang == "en" else date.today().strftime("%d/%m/%Y")
        E += [Paragraph(f"<b>{prepared} {prospect}</b> · {today}", S["body"]), Spacer(1, 4 * mm)]
    E += [Paragraph(t["h_today"], S["h2"]), Paragraph(t["p_today"], S["body"])]
    for h, b in ((t["h1"], t["b1"]), (t["h2"], t["b2"]), (t["h3"], t["b3"])):
        E.append(Paragraph(h, S["h2"]))
        E += _bul(b)
    E += [PageBreak(), Paragraph(t["h_gain"], S["h2"]), _table(t["gain"], [58 * mm, 116 * mm]),
          Paragraph(t["h_price"], S["h2"]), Paragraph(t["p_price"], S["body"]), Spacer(1, 2 * mm),
          _table(t["price"], [34 * mm, 100 * mm, 40 * mm]), Paragraph(t["note_price"], S["note"]),
          Paragraph(t["h_data"], S["h2"])]
    E += _bul(t["b_data"])
    E += [Paragraph(t["h_start"], S["h2"]), Paragraph(t["p_start"], S["body"])]
    who = (branding or {}).get("company_name")
    left = f"{who} · " if who else ""
    return _build(E, f"{left}ConstruPilot · {SITE} · {CONTACT} · "
                     + _patent(lang) + PATENT)


# ═══════════════════════════════  Présentation investisseur  ═══════════════════════════════

INV = {
    "fr": {
        "title": "ConstruPilot — apresentação a investidores",
        "sub": "Software vertical para a construção francesa: o único lugar onde a orçamentação de um mapa de quantidades do arquiteto, as medições sobre planta e a faturação por autos partilham a mesma base de dados.",
        "aud": "Documento de trabalho · confidencial · não difundir publicamente",
        "h1": "1. O problema",
        "b1": ["As pequenas e médias empresas de construção continuam a trabalhar em folhas de cálculo: mapas do arquiteto orçamentados à mão, medições repetidas, orçamentos sem biblioteca de preços fiável.",
               "A margem perde-se nos <b>esquecimentos administrativos</b>: trabalhos do caderno de encargos nunca orçamentados, adiantamentos não deduzidos, autos mal calculados, retenções nunca reclamadas.",
               "As ferramentas existentes cobrem a gestão, ou a orçamentação, ou o acompanhamento de obra. A ligação entre as três continua a ser humana — logo caro e propenso a erros."],
        "h2": "2. O que faz o ConstruPilot",
        "modules": [["Módulo", "Função", "Porque importa"],
                    ["Orçamentação DPGF / BPU / DQE", "Leitura multi-folha dos mapas Excel, deteção de lotes, preços da biblioteca da empresa e depois da IA, instruções em linguagem natural, leitura do caderno de encargos, alerta sobre trabalhos esquecidos", "A tarefa mais longa da profissão passa de horas a minutos; é a porta de entrada do produto"],
                    ["Medições sobre planta", "Importação PDF/DWG, escala, medições, quantidades exportáveis", "Alimenta a orçamentação sem reintroduzir dados"],
                    ["Orçamentos e assinatura", "3 apresentações, QR de assinatura, envio e reativação automática, assinatura no local", "Taxa de retorno dos orçamentos e prazo de assinatura"],
                    ["Consulta a subempreiteiros", "Consulta por lote, resposta online sem conta, comparação das propostas com o desvio em %", "Efeito de rede: cada subempreiteiro consultado descobre o produto"],
                    ["Faturação de obra", "Adiantamento automático na assinatura, autos de medição, adiantamento recebido deduzido, retenção de garantia, conta final", "Tesouraria e margem recuperadas: o benefício é quantificável pelo utilizador"],
                    ["Assistente de IA e espaço do cliente", "Respostas técnicas fundamentadas, mensagens com o cliente, fotografias, reservas, documentos", "Utilização diária e retenção"],
                    ["Gestão interna", "Medição do percurso de aquisição, despesas por envelope, back-office de administração", "Crescimento medido, despesas atribuídas"]],
        "h3": "3. Diferenciação",
        "b3": ["<b>Profundidade do setor</b>: autos de medição, retenção de garantia, adiantamento deduzido, conta final — mecanismos ausentes das ferramentas generalistas.",
               "<b>Cadeia contínua</b>: o mesmo registo serve do mapa do arquiteto à conta final; nenhuma ponte a manter.",
               "<b>Biblioteca de preços proprietária</b>: cada orçamentação validada enriquece a base de preços da empresa — o valor cresce com o uso e cria custo de saída.",
               "<b>IA usada onde é verificável</b>: estimativa proposta e editável, leitura do caderno de encargos, deteção de esquecimentos. Nunca um número inventado apresentado como certo.",
               "<b>Disciplina de comunicação</b>: referencial interno de afirmações, nenhuma promessa pública sem medição; contadores e avaliações falsas retirados do produto."],
        "h4": "4. Modelo de negócio",
        "rev": [["Fonte de receita", "Detalhe", "Preço de entrada"],
                ["Subscrição profissional", "Artesãos e PME, por empresa", f"{OFFER['pro']:.0f} € / mois"],
                ["Subscrição particular", "Projeto pessoal, estimativa, acompanhamento", f"{OFFER['particulier']:.0f} € / mois"],
                ["API / integrações", "Editores, distribuidores, grandes contas", f"{OFFER['api']:.0f} € / mois"],
                ["Opções e módulos", "Extensões faturadas pelo uso", f"dès {OFFER['addon']:.0f} € / mois"]],
        "note_rev": f"Experiência de {OFFER['trial_days']} jours"
                    + (", fase de lançamento gratuita em curso. " if OFFER["free_promo"] else ". ")
                    + "Pagamento pela Stripe. Uma única fonte de verdade para os preços em todo o produto.",
        "h5": "5. Plano de exploração: 500 000 € em 24 meses",
        "b5": ["Captação pretendida: <b>500 000 €</b>, aplicados em <b>24 meses</b> — cerca de <b>20 800 €/mês</b> de despesa média.",
               "As aplicações são repartidas por envelope e seguidas mensalmente no back-office: cada euro está ligado a uma rubrica e a um canal medido.",
               "Marcos: meses 1-6 publicação das aplicações Android e iOS e primeiros clientes pagantes; meses 7-12 aquisição controlada (SEO, conteúdos, terreno) e integrações contabilísticas; meses 13-18 equipa comercial e implantação regional; meses 19-24 abertura da API e parcerias de distribuição.",
               "Estes marcos são objetivos de trabalho, não previsões garantidas; o progresso é publicado tal como é medido."],
        "funds": [["Aplicação dos fundos", "Detalhe", "Montante", "Parte"],
                  ["Produto & tecnologia", "Desenvolvimento, apps Android/iOS, fiabilidade, testes", "150 000 €", "30 %"],
                  ["Aquisição & vendas", "Comerciais no terreno, demonstrações, feiras, CRM", "160 000 €", "32 %"],
                  ["Conteúdo & marketing", "SEO, conteúdos do setor, folhetos com código QR", "60 000 €", "12 %"],
                  ["Infraestrutura & IA", "Alojamento, APIs de IA, armazenamento, segurança", "50 000 €", "10 %"],
                  ["Suporte & sucesso do cliente", "Acompanhamento, formação, migração de preços", "40 000 €", "8 %"],
                  ["Conformidade & jurídico", "RGPD, contratos, patente, contabilidade", "20 000 €", "4 %"],
                  ["Reserva", "Imprevistos e oportunidades não orçamentadas", "20 000 €", "4 %"],
                  ["Total", "24 meses · ~20 800 €/mês", "500 000 €", "100 %"]],
        "h6": "6. Medição e tração",
        "p6": "O produto traz o seu próprio instrumento de medição: origem de cada registo (QR de folheto, recomendação, publicidade, pesquisa, site de referência), ativação «primeiro valor» (primeira estimativa real), funil e retenção. Uma métrica não mensurável é apresentada como «não mensurável» — nunca 0, nunca um número reconstituído.",
        "k_accounts": "Contas existentes (sem testes)",
        "k_active": "Ativos em 30 dias",
        "k_paying": "Subscrições pagas ativas",
        "k_budget": "Despesas do mês em curso",
        "k_signups": "Registos medidos (30 d)",
        "k_activation": "Taxa de ativação (30 d)",
        "k_companies": "Empresas identificadas (SIRET)",
        "k_docs": "Orçamentos e faturas criados",
        "h7": "7. Roteiro",
        "road": [["Etapa", "Conteúdo", "Estado"],
                 ["Base do produto", "Orçamentação DPGF, medições, orçamentos, obras, faturação por autos, conta final, espaço do cliente", "Entregue"],
                 ["Medição e gestão", "Percurso de aquisição, despesas por envelope, back-office de administração", "Entregue"],
                 ["Conformidade e distribuição", "Páginas legais, eliminação de conta e de dados, metadados das lojas", "Entregue"],
                 ["Aplicações móveis", "Publicação das aplicações (obra, colaborador, particular)", "Em preparação"],
                 ["Aquisição controlada", "SEO técnico, estúdio de conteúdos, folhetos com QR, CRM", "Próximo lote"],
                 ["Execução de marketing", "Campanhas e impressões sob autorização, dentro do envelope", "Após validação"]],
        "h8": "8. Riscos e respostas",
        "risk": [["Risco", "Resposta em vigor"],
                 ["Qualidade dos preços propostos pela IA", "Prioridade absoluta à biblioteca da empresa; a IA serve apenas para as linhas desconhecidas, sempre editável, e cada preço validado é arquivado"],
                 ["Dependência de um fornecedor de IA", "Três fornecedores intercambiáveis atrás de uma mesma interface interna"],
                 ["Heterogeneidade dos mapas", "Leitura tolerante (multi-folha, cabeçalhos variáveis, títulos ignorados) e correção manual linha a linha"],
                 ["Desvio de custos", "Aplicações seguidas por envelope no back-office, reconciliação mensal das despesas com os canais de aquisição"],
                 ["Conformidade (RGPD, lojas)", "Páginas legais bilingues, eliminação autónoma, registo de acessos"]],
        "h9": "9. O que procuramos",
        "b9": ["Acesso ao mercado: apresentações a federações, agrupamentos de artesãos, armazenistas e gabinetes de projeto.",
               "Capacidade comercial: financiar um primeiro ciclo de venda no terreno e as contratações associadas ao longo dos 24 meses do plano.",
               "Parcerias de integração: software de contabilidade, distribuidores de materiais, plataformas de plantas."],
        "contact_h": "Contacto",
        "measured": "Números medidos na base em {d} (janela de {w} dias) · definição de ativos: pelo menos uma sessão aberta no período. Objetivo interno de crescimento: 10 000 contas — objetivo privado, nunca apresentado como audiência adquirida.",
        "nomeasure": "não mensurável",
    },
    "en": {
        "title": "ConstruPilot — investor presentation",
        "sub": "Vertical software for the French construction market: the only place where pricing an "
               "architect's bill of quantities, on-plan take-off and progress invoicing share one database.",
        "aud": "Working document · confidential · not for public distribution",
        "h1": "1. The problem",
        "b1": ["Small and mid-sized construction firms still work in spreadsheets: architects' schedules priced by hand, take-offs redone, quotes without a reliable price library.",
               "Margin is lost in <b>administrative omissions</b>: items required by the specification never priced, deposits never offset, progress accounts miscalculated, retention never claimed.",
               "Existing tools cover either admin, or pricing, or site monitoring. Joining the three stays a human task — costly and error-prone."],
        "h2": "2. What ConstruPilot does",
        "modules": [["Módulo", "Function", "Why it matters"],
                    ["Bill of quantities pricing", "Multi-sheet reading of Excel schedules, lot detection, prices from the company library then AI, plain-language instructions, specification reading, alerts on omitted items", "The longest task of the trade drops from hours to minutes; it is the product's entry point"],
                    ["On-plan take-off", "PDF/DWG import, scaling, measurements, exportable quantities", "Feeds pricing with no re-entry"],
                    ["Quotes & signature", "3 layouts, signature QR code, sending and automatic follow-up, on-site signature", "Quote return rate and time to signature"],
                    ["Subcontractor enquiries", "Lot-level RFQ, online answer without an account, offer comparison with the gap in %", "Network effect: every subcontractor consulted discovers the product"],
                    ["Construction invoicing", "Automatic deposit on signature, progress accounts, deposit received offset, retention, final account", "Cash and margin recovered: the benefit is measurable by the user"],
                    ["AI assistant & client portal", "Sourced technical answers, client messaging, photos, snags, documents", "Daily usage and retention"],
                    ["Internal steering", "Acquisition journey measurement, spending cap, admin back office", "Measured growth, costs under control"]],
        "h3": "3. Differentiation",
        "b3": ["<b>Domain depth</b>: progress accounts, retention, deposit offsetting, final account — mechanics absent from generalist tools.",
               "<b>Continuous chain</b>: the same record travels from the architect's schedule to the final account; no integration to maintain.",
               "<b>Proprietary price library</b>: every validated price enriches the company's own database — value grows with usage and creates switching costs.",
               "<b>AI used where it is verifiable</b>: proposed and editable estimates, specification reading, omission detection. Never an invented figure presented as certain.",
               "<b>Communication discipline</b>: an internal claims register; no public promise without measurement; fake counters and fake reviews removed from the product."],
        "h4": "4. Business model",
        "rev": [["Revenue stream", "Detail", "Entry price"],
                ["Professional subscription", "Trade contractors and SMEs, per company", f"€{OFFER['pro']:.0f} / month"],
                ["Individual subscription", "Personal project, estimate, monitoring", f"€{OFFER['particulier']:.0f} / month"],
                ["API / integrations", "Software vendors, distributors, large accounts", f"€{OFFER['api']:.0f} / month"],
                ["Add-ons", "Usage-based extensions", f"from €{OFFER['addon']:.0f} / month"]],
        "note_rev": f"{OFFER['trial_days']}-day trial"
                    + (", free launch phase in progress. " if OFFER["free_promo"] else ". ")
                    + "Stripe payments. A single source of truth for prices across the product.",
        "h5": "5. Funding plan: €500,000 over 24 months",
        "b5": ["Raise sought: <b>€500,000</b>, deployed over <b>24 months</b> — about <b>€20,800</b> of average monthly spend.",
               "Uses of funds are split into envelopes and tracked monthly in the back office: every euro is attached to a line item and a measured channel.",
               "Milestones: months 1-6 Android and iOS apps published and first paying customers; months 7-12 controlled acquisition (SEO, content, field sales) and accounting integrations; months 13-18 sales team and regional roll-out; months 19-24 API opening and distribution partnerships.",
               "These milestones are working objectives, not guaranteed forecasts; progress is published exactly as measured."],
        "funds": [["Use of funds", "Detail", "Amount", "Share"],
                  ["Product & engineering", "Development, Android/iOS apps, reliability, testing", "€150,000", "30%"],
                  ["Acquisition & sales", "Field sales, demos, trade shows, CRM", "€160,000", "32%"],
                  ["Content & marketing", "SEO, trade content, QR-code leaflets", "€60,000", "12%"],
                  ["Infrastructure & AI", "Hosting, AI APIs, storage, security", "€50,000", "10%"],
                  ["Support & customer success", "Onboarding, training, price migration", "€40,000", "8%"],
                  ["Compliance & legal", "GDPR, contracts, patent, accounting", "€20,000", "4%"],
                  ["Reserve", "Contingencies and unbudgeted opportunities", "€20,000", "4%"],
                  ["Total", "24 months · ~€20,800 / month", "€500,000", "100%"]],
        "h6": "6. Measurement and traction",
        "p6": "The product ships with its own measurement: source of every sign-up (leaflet QR, referral, "
              "advertising, search, referring site), \"first value\" activation (first real estimate), "
              "funnel and retention. A metric that cannot be measured is displayed as \"not measurable\" "
              "— never 0, never a reconstructed figure.",
        "k_accounts": "Existing accounts (excl. tests)",
        "k_active": "Active over 30 days",
        "k_paying": "Active paid subscriptions",
        "k_budget": "Spend this month",
        "k_signups": "Measured sign-ups (30 d)",
        "k_activation": "Activation rate (30 d)",
        "k_companies": "Identified companies (SIRET)",
        "k_docs": "Quotes & invoices created",
        "h7": "7. Roadmap",
        "road": [["Stage", "Content", "Status"],
                 ["Product core", "Schedule pricing, take-off, quotes, sites, progress invoicing, final account, client portal", "Shipped"],
                 ["Measurement & steering", "Acquisition journey, spend tracking by envelope, admin back office", "Shipped"],
                 ["Compliance & distribution", "Legal pages, account and data deletion, store metadata", "Shipped"],
                 ["Mobile apps", "Publishing the apps (site, team member, individual)", "In preparation"],
                 ["Controlled acquisition", "Technical SEO, content studio, QR leaflets, CRM", "Next batch"],
                 ["Marketing execution", "Campaigns and print runs under approval, within the budget envelope", "After approval"]],
        "h8": "8. Risks and answers",
        "risk": [["Risk", "Answer in place"],
                 ["Quality of AI-proposed prices", "Absolute priority to the company library; AI only fills unknown lines, always editable, and every validated price is archived"],
                 ["Dependency on one AI vendor", "Three interchangeable vendors behind a single internal interface"],
                 ["Heterogeneous schedules", "Tolerant parsing (multi-sheet, variable headers, titles ignored) and line-by-line manual correction"],
                 ["Cost drift", "Uses of funds tracked by envelope in the back office, monthly reconciliation of spend and acquisition channels"],
                 ["Compliance (GDPR, app stores)", "Bilingual legal pages, self-service deletion, access logging"]],
        "h9": "9. What we are looking for",
        "b9": ["Market access: introductions to trade federations, contractor groups, material distributors and architecture practices.",
               "Commercial capacity: funding a first field sales cycle and the related hires over the 24 months of the plan.",
               "Integration partnerships: accounting software, material distributors, plan platforms."],
        "contact_h": "Contacto",
        "measured": "Figures measured in the database on {d} (rolling {w} days) · active definition: at "
                    "least one session opened during the period. Internal growth target: 10,000 "
                    "accounts — a private objective, never presented as an acquired audience.",
        "nomeasure": "not measurable",
    },
    "pt": {
        "title": "ConstruPilot — apresentação a investidores",
        "sub": "Software vertical para a construção francesa: o único lugar onde a orçamentação de um "
               "mapa de quantidades do arquiteto, as medições sobre planta e a faturação por autos "
               "partilham a mesma base de dados.",
        "aud": "Documento de trabalho · confidencial · não difundir publicamente",
        "h1": "1. O problema",
        "b1": ["As pequenas e médias empresas de construção continuam a trabalhar em folhas de cálculo: mapas do arquiteto orçamentados à mão, medições repetidas, orçamentos sem biblioteca de preços fiável.",
               "A margem perde-se nos <b>esquecimentos administrativos</b>: trabalhos do caderno de encargos nunca orçamentados, adiantamentos não deduzidos, autos mal calculados, retenções nunca reclamadas.",
               "As ferramentas existentes cobrem a gestão, ou a orçamentação, ou o acompanhamento de obra. A ligação entre as três continua a ser humana — logo caro e propenso a erros."],
        "h2": "2. O que faz o ConstruPilot",
        "modules": [["Módulo", "Função", "Porque importa"],
                    ["Orçamentação DPGF / BPU / DQE", "Leitura multi-folha dos mapas Excel, deteção de lotes, preços da biblioteca da empresa e depois da IA, instruções em linguagem natural, leitura do caderno de encargos, alerta sobre trabalhos esquecidos", "A tarefa mais longa da profissão passa de horas a minutos; é a porta de entrada do produto"],
                    ["Medições sobre planta", "Importação PDF/DWG, escala, medições, quantidades exportáveis", "Alimenta a orçamentação sem reintroduzir dados"],
                    ["Orçamentos e assinatura", "3 apresentações, QR de assinatura, envio e reativação automática, assinatura no local", "Taxa de retorno dos orçamentos e prazo de assinatura"],
                    ["Consulta a subempreiteiros", "Consulta por lote, resposta online sem conta, comparação das propostas com o desvio em %", "Efeito de rede: cada subempreiteiro consultado descobre o produto"],
                    ["Faturação de obra", "Adiantamento automático na assinatura, autos de medição, adiantamento recebido deduzido, retenção de garantia, conta final", "Tesouraria e margem recuperadas: o benefício é quantificável pelo utilizador"],
                    ["Assistente de IA e espaço do cliente", "Respostas técnicas fundamentadas, mensagens com o cliente, fotografias, reservas, documentos", "Utilização diária e retenção"],
                    ["Gestão interna", "Medição do percurso de aquisição, despesas por envelope, back-office de administração", "Crescimento medido, despesas atribuídas"]],
        "h3": "3. Diferenciação",
        "b3": ["<b>Profundidade do setor</b>: autos de medição, retenção de garantia, adiantamento deduzido, conta final — mecanismos ausentes das ferramentas generalistas.",
               "<b>Cadeia contínua</b>: o mesmo registo serve do mapa do arquiteto à conta final; nenhuma ponte a manter.",
               "<b>Biblioteca de preços proprietária</b>: cada orçamentação validada enriquece a base de preços da empresa — o valor cresce com o uso e cria custo de saída.",
               "<b>IA usada onde é verificável</b>: estimativa proposta e editável, leitura do caderno de encargos, deteção de esquecimentos. Nunca um número inventado apresentado como certo.",
               "<b>Disciplina de comunicação</b>: referencial interno de afirmações, nenhuma promessa pública sem medição; contadores e avaliações falsas retirados do produto."],
        "h4": "4. Modelo de negócio",
        "rev": [["Fonte de receita", "Detalhe", "Preço de entrada"],
                ["Subscrição profissional", "Artesãos e PME, por empresa", f"{OFFER['pro']:.0f} € / mês"],
                ["Subscrição particular", "Projeto pessoal, estimativa, acompanhamento", f"{OFFER['particulier']:.0f} € / mês"],
                ["API / integrações", "Editores, distribuidores, grandes contas", f"{OFFER['api']:.0f} € / mês"],
                ["Opções e módulos", "Extensões faturadas pelo uso", f"desde {OFFER['addon']:.0f} € / mês"]],
        "note_rev": f"Teste de {OFFER['trial_days']} dias"
                    + (", fase de lançamento gratuita em curso. " if OFFER["free_promo"] else ". ")
                    + "Pagamentos por Stripe. Uma única fonte de verdade para os preços em todo o produto.",
        "h5": "5. Plano de exploração: 500 000 € em 24 meses",
        "b5": ["Captação pretendida: <b>500 000 €</b>, aplicados em <b>24 meses</b> — cerca de <b>20 800 €/mês</b> de despesa média.",
               "As aplicações são repartidas por envelope e seguidas mensalmente no back-office: cada euro está ligado a uma rubrica e a um canal medido.",
               "Marcos: meses 1-6 publicação das aplicações Android e iOS e primeiros clientes pagantes; meses 7-12 aquisição controlada (SEO, conteúdos, terreno) e integrações contabilísticas; meses 13-18 equipa comercial e implantação regional; meses 19-24 abertura da API e parcerias de distribuição.",
               "Estes marcos são objetivos de trabalho, não previsões garantidas; o progresso é publicado tal como é medido."],
        "funds": [["Aplicação dos fundos", "Detalhe", "Montante", "Parte"],
                  ["Produto & tecnologia", "Desenvolvimento, apps Android/iOS, fiabilidade, testes", "150 000 €", "30 %"],
                  ["Aquisição & vendas", "Comerciais no terreno, demonstrações, feiras, CRM", "160 000 €", "32 %"],
                  ["Conteúdo & marketing", "SEO, conteúdos do setor, folhetos com código QR", "60 000 €", "12 %"],
                  ["Infraestrutura & IA", "Alojamento, APIs de IA, armazenamento, segurança", "50 000 €", "10 %"],
                  ["Suporte & sucesso do cliente", "Acompanhamento, formação, migração de preços", "40 000 €", "8 %"],
                  ["Conformidade & jurídico", "RGPD, contratos, patente, contabilidade", "20 000 €", "4 %"],
                  ["Reserva", "Imprevistos e oportunidades não orçamentadas", "20 000 €", "4 %"],
                  ["Total", "24 meses · ~20 800 €/mês", "500 000 €", "100 %"]],
        "h6": "6. Medição e tração",
        "p6": "O produto traz o seu próprio instrumento de medição: origem de cada registo (QR de "
              "folheto, recomendação, publicidade, pesquisa, site de referência), ativação « primeiro "
              "valor » (primeira estimativa real), funil e retenção. Uma métrica não mensurável é "
              "apresentada como « não mensurável » — nunca 0, nunca um número reconstituído.",
        "k_accounts": "Contas existentes (sem testes)",
        "k_active": "Ativos em 30 dias",
        "k_paying": "Subscrições pagas ativas",
        "k_budget": "Despesas do mês em curso",
        "k_signups": "Registos medidos (30 d)",
        "k_activation": "Taxa de ativação (30 d)",
        "k_companies": "Empresas identificadas (SIRET)",
        "k_docs": "Orçamentos e faturas criados",
        "h7": "7. Roteiro",
        "road": [["Etapa", "Conteúdo", "Estado"],
                 ["Base do produto", "Orçamentação DPGF, medições, orçamentos, obras, faturação por autos, conta final, espaço do cliente", "Entregue"],
                 ["Medição e gestão", "Percurso de aquisição, despesas por envelope, back-office de administração", "Entregue"],
                 ["Conformidade e distribuição", "Páginas legais, eliminação de conta e de dados, metadados das lojas", "Entregue"],
                 ["Aplicações móveis", "Publicação das aplicações (obra, colaborador, particular)", "Em preparação"],
                 ["Aquisição controlada", "SEO técnico, estúdio de conteúdos, folhetos com QR, CRM", "Próximo lote"],
                 ["Execução de marketing", "Campanhas e impressões sob autorização, dentro do envelope", "Após validação"]],
        "h8": "8. Riscos e respostas",
        "risk": [["Risco", "Resposta em vigor"],
                 ["Qualidade dos preços propostos pela IA", "Prioridade absoluta à biblioteca da empresa; a IA serve apenas para as linhas desconhecidas, sempre editável, e cada preço validado é arquivado"],
                 ["Dependência de um fornecedor de IA", "Três fornecedores intercambiáveis atrás de uma mesma interface interna"],
                 ["Heterogeneidade dos mapas", "Leitura tolerante (multi-folha, cabeçalhos variáveis, títulos ignorados) e correção manual linha a linha"],
                 ["Desvio de custos", "Aplicações seguidas por envelope no back-office, reconciliação mensal das despesas com os canais de aquisição"],
                 ["Conformidade (RGPD, lojas)", "Páginas legais bilingues, eliminação autónoma, registo de acessos"]],
        "h9": "9. O que procuramos",
        "b9": ["Acesso ao mercado: apresentações a federações, agrupamentos de artesãos, armazenistas e gabinetes de projeto.",
               "Capacidade comercial: financiar um primeiro ciclo de venda no terreno e as contratações associadas ao longo dos 24 meses do plano.",
               "Parcerias de integração: software de contabilidade, distribuidores de materiais, plataformas de plantas."],
        "contact_h": "Contacto",
        "measured": "Números medidos na base em {d} (janela de {w} dias) · definição de ativos: pelo "
                    "menos uma sessão aberta no período. Objetivo interno de crescimento: 10 000 "
                    "contas — objetivo privado, nunca apresentado como audiência adquirida.",
        "nomeasure": "não mensurável",
    },
}


def _patent(lang: str) -> str:
    return {"en": "Patent no. ", "pt": "Patente n.º "}.get(lang, "Brevet n° ")


def _fmt(value, nomeasure: str, suffix: str = "") -> str:
    if value is None:
        return nomeasure
    if isinstance(value, float):
        return f"{value:g}{suffix}"
    return f"{value:,}".replace(",", " ") + suffix


def build_investor_pdf(lang: str = "pt", metrics: dict | None = None,
                       budget: dict | None = None, docs_count: int | None = None) -> bytes:
    _ensure_fonts()
    t = INV.get(lang) or INV["fr"]
    E = _cover(t["title"], t["sub"], t["aud"])
    E.append(Paragraph(t["h1"], S["h2"]))
    E += _bul(t["b1"])
    E += [Paragraph(t["h2"], S["h2"]), _table(t["modules"], [34 * mm, 78 * mm, 62 * mm]),
          PageBreak(), Paragraph(t["h3"], S["h2"])]
    E += _bul(t["b3"])
    E += [Paragraph(t["h4"], S["h2"]), _table(t["rev"], [42 * mm, 92 * mm, 40 * mm]),
          Paragraph(t["note_rev"], S["note"]), Paragraph(t["h5"], S["h2"])]
    E += _bul(t["b5"])
    E += [Spacer(1, 2 * mm), _table(t["funds"], [40 * mm, 76 * mm, 30 * mm, 28 * mm])]
    E += [Paragraph(t["h6"], S["h2"]), Paragraph(t["p6"], S["body"]), Spacer(1, 2 * mm)]

    nm = t["nomeasure"]
    acc = (metrics or {}).get("accounts") or {}
    act = (metrics or {}).get("activity") or {}
    jou = (metrics or {}).get("journey") or {}
    spent = (budget or {}).get("spent_eur")
    cap = (budget or {}).get("cap_eur") or 500
    E.append(_kpis([
        (t["k_accounts"], _fmt(acc.get("existing_excluding_tests"), nm)),
        (t["k_active"], _fmt(act.get("active_users_window"), nm)),
        (t["k_paying"], _fmt(act.get("paying_customers"), nm)),
        (t["k_budget"], f"{spent:g} €" if spent is not None else nm),
    ]))
    E.append(Spacer(1, 2 * mm))
    E.append(_kpis([
        (t["k_signups"], _fmt(jou.get("signups_window"), nm)),
        (t["k_activation"], _fmt(jou.get("activation_rate_pct"), nm, " %")),
        (t["k_companies"], _fmt(acc.get("companies_with_siret"), nm)),
        (t["k_docs"], _fmt(docs_count, nm)),
    ]))
    generated = (metrics or {}).get("generated_at") or ""
    E.append(Paragraph(t["measured"].format(d=generated[:10] or date.today().isoformat(),
                                            w=(metrics or {}).get("window_days", 30)), S["note"]))

    E += [PageBreak(), Paragraph(t["h7"], S["h2"]), _table(t["road"], [34 * mm, 112 * mm, 28 * mm]),
          Paragraph(t["h8"], S["h2"]), _table(t["risk"], [48 * mm, 126 * mm]),
          Paragraph(t["h9"], S["h2"])]
    E += _bul(t["b9"])
    E += [Spacer(1, 3 * mm), KeepTogether([
        Paragraph(t["contact_h"], S["h3"]),
        Paragraph(f"{CONTACT} · {SITE} · "
                  + _patent(lang) + PATENT + ".", S["body"])])]
    return _build(E, f"ConstruPilot · {SITE} · {CONTACT} · "
                     + _patent(lang) + PATENT)
