"""Reusable beige/copper estimate dossier approved on the real plan exercises."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, Image, KeepTogether

COPPER, CREAM, PALE = map(HexColor, ("#925535", "#F7F1E9", "#F0E7DC"))
INK, MUTED, LINE = map(HexColor, ("#302B26", "#6E6359", "#DFD1C2"))
WHITE = HexColor("#FFFFFF")
WIDTH = A4[0] - 96


def fonts():
    from reportlab import __file__ as rlfile
    candidates = [Path(__file__).parent.parent / "assets/fonts", Path("/usr/share/fonts/truetype/dejavu")]
    folder = next((p for p in candidates if (p/"DejaVuSans.ttf").exists()), None)
    for name, filename in (("Dossier", "DejaVuSans.ttf"), ("DossierBold", "DejaVuSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            path = folder/filename if folder else Path(rlfile).parent/"fonts"/("VeraBd.ttf" if name.endswith("Bold") else "Vera.ttf")
            pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily("Dossier", normal="Dossier", bold="DossierBold")


def fmt(value, currency=False):
    if value is None:
        return "N/C"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + (" €" if currency else "")


def text(value):
    return escape(str(value or "")).replace("\n", "<br/>")


class NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved_pages = []

    def showPage(self):
        self.saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        count = len(self.saved_pages)
        for state in self.saved_pages:
            self.__dict__.update(state)
            self.setFillColor(MUTED)
            self.setFont("Dossier", 7.2)
            self.drawRightString(A4[0]-48, 29, f"{self._pageNumber} / {count}")
            super().showPage()
        super().save()


def build_dossier_pdf(plan, study, branding=None, source_images=None):
    fonts()
    branding = branding or {}
    title = (study.get("project") or {}).get("title") or plan.get("filename") or "Estudo de construção"
    address = (study.get("project") or {}).get("address") or ""
    ref = str(plan.get("plan_id") or "DOSSIER")[-32:]
    date = str(study.get("generated_at") or "")[:10]
    s = {"body": ParagraphStyle("b", fontName="Dossier", fontSize=9.1, leading=13, textColor=INK, spaceAfter=8),
         "small": ParagraphStyle("s", fontName="Dossier", fontSize=7.9, leading=10.8, textColor=MUTED, spaceAfter=7),
         "cell": ParagraphStyle("c", fontName="Dossier", fontSize=8.1, leading=10.8, textColor=INK),
         "head": ParagraphStyle("h", fontName="DossierBold", fontSize=8, leading=10.8, textColor=WHITE),
         "title": ParagraphStyle("t", fontName="DossierBold", fontSize=21, leading=26, textColor=INK, spaceAfter=14),
         "h2": ParagraphStyle("h2", fontName="DossierBold", fontSize=11, leading=15, textColor=COPPER, spaceBefore=10, spaceAfter=9, keepWithNext=True),
         "money": ParagraphStyle("m", fontName="DossierBold", fontSize=24, leading=32, textColor=WHITE),
         "white": ParagraphStyle("w", fontName="Dossier", fontSize=9, leading=13, textColor=WHITE)}
    def para(value, style="body", raw=False):
        return Paragraph(str(value) if raw else text(value), s[style])
    def table(headers, data, widths, amounts=()):
        rows = [[para(v, "head") for v in headers]]
        rows.extend([[v if isinstance(v, Paragraph) else para(v, "cell") for v in row] for row in data])
        t = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        styles = [("BACKGROUND", (0, 0), (-1, 0), COPPER), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PALE]),
                  ("LINEBELOW", (0, 1), (-1, -1), .3, LINE),
                  ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                  ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
        for col in amounts:
            for row in rows[1:]:
                row[col].style = ParagraphStyle("amount", parent=s["cell"], alignment=2, fontName="DossierBold")
        t.setStyle(TableStyle(styles))
        return t
    def heading(value):
        return para(value, "title")
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=69, bottomMargin=60,
                            title=f'Orçamento estimativo de estrutura e alvenarias - {title}', author=branding.get("company_name") or "ConstruPilot")
    totals = study["totals"]
    story = [heading("Orçamento estimativo de estrutura e alvenarias"), para(title + (" | " + address if address else ""), "small"),
             para(f"Fornecimento e aplicação - {sum((len(l['lines']) for l in study['lots']))} postes. {study.get('scope') or 'Obra grossa'}."),
             para("Estimativa a partir das peças da obra. As quantidades, as suas fórmulas e as provisões estão detalhadas. Preços e opções construtivas ficam por confirmar.")]
    budget = Table([[para("ORÇAMENTO PARCIAL S/ IVA" if totals.get("partial") else "ORÇAMENTO ESTIMATIVO S/ IVA", "white")],
                    [para(fmt(totals["ht"], True), "money")],
                    [para(f"{fmt(totals['ttc'], True)} TTC | TVA {fmt(totals.get('tva_rate')*100) if totals.get('tva_rate') is not None else 'N/C'} %", "white")]], colWidths=[WIDTH])
    budget.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), COPPER), ("LEFTPADDING", (0, 0), (-1, -1), 17),
                                ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [budget, Spacer(1, 18), table(["Artigo", "Montante s/ IVA"], [[l["lot"]+(" (parcial)" if l.get("partial") else ""),fmt(l["total_ht"], True)] for l in study["lots"]], [WIDTH-129,129], (1,))]
    story += [para("Leitura do orçamento", "h2"), para("M: medição controlada pelo utilizador; H: hipótese ou medição extraída a controlar; P: provisão; N/C: sem preço.", "small")]
    for variant in study.get("variants", []):
        story += [para(f"{variant['label']}: dedução de {fmt(variant['deduction_ht'], True)} s/ IVA; orçamento resultante {fmt(variant['total_ht'], True)} HT. {variant.get('note') or ''}", "small")]
    story += [para("Documento orçamental não contratual. As reservas e exclusões fazem parte integrante desta estimativa.", "small"), PageBreak(), heading("Orçamento / trabalhos detalhados")]
    data = []
    for count, r in enumerate([r for lot in study['lots'] for r in lot['lines']], 1):
        data.append([str(count).zfill(2), r['designation'], para(fmt(r['qty'])+"<br/><font color='#925535'>"+text(r['quantity_status'])+"</font>", "cell", True), r['unit'], fmt(r['unit_price']), fmt(r['total'])])
    story.append(table(["N.º", "Designação", "Qtd.", "U", "PU HT €", "Total s/ IVA €"], data, [30,WIDTH-285,54,35,76,90], (4,5)))
    story += [Spacer(1, 14), table(["Resumo", "Montante"], [["Total s/ IVA"+(" partiel" if totals.get("partial") else ""),fmt(totals['ht'], True)],["IVA",fmt(totals['tva'], True)],["Total c/ IVA estimativo",fmt(totals['ttc'], True)]],[WIDTH-150,150],(1,)),
              PageBreak(), heading("Medições / cálculos e fontes")]
    geometry = [r for r in study["items"] if r["included"] and r["unit"] not in ("ft", "ens.", "u", "1") and (r["sources"] or r.get("error"))]
    story.append(para("Cada fórmula utiliza as referências de medição abaixo. Os valores globais continuam a ser provisões, distintas das quantidades geométricas.", "small"))
    story.append(table(["Trabalho / referências de cálculo", "Quantidade", "Estado"],
        [[para(text(r['designation'])+"<br/><font size='7' color='#6E6359'>"+text(r['expression'])+"</font>"+("<br/>"+text(r['error']) if r.get('error') else ''), "cell", True),
          fmt(r['qty'])+" "+r['unit'],r['quantity_status']] for r in geometry], [WIDTH-133,87,46]))
    evidence = {p['id']:p for r in geometry for p in r['sources'] if not p.get('expression')}
    story += [para("Registo das medições / fontes", "h2"), table(["Referência / medição", "Valor", "Fonte / hipótese"],
        [[p['id']+" / "+p['label'], fmt(p['value'])+" "+p['unit'],
          "; ".join(f"p. {x['page']} : {x['text']}" for x in p['sources']) or p.get('note') or "Valor introduzido / a confirmar"]
         for p in evidence.values()], [150,70,WIDTH-220])]
    derived = {p['id']:p for r in geometry for p in r['sources'] if p.get('expression')}
    if derived:
        story += [para("Medições derivadas", "h2"), table(["Referência", "Plano", "Valor"],
            [[p['id'],p['expression'],fmt(p['value'])+" "+p['unit']] for p in derived.values()], [115,WIDTH-195,80])]
    if source_images:
        story += [PageBreak(), heading("Peças de referência")]
        for label, png in source_images:
            from PIL import Image as PILImage
            with PILImage.open(BytesIO(png)) as im:
                width, height = im.size
            ratio = min(WIDTH/width, 440/height)
            story.append(KeepTogether([para(label,"h2"),Image(BytesIO(png), width=width*ratio,height=height*ratio),Spacer(1,12)]))
    story += [PageBreak(), heading("Serviços e convenções")]
    for lot in study['lots']:
        story.append(para(lot['lot'], 'h2'))
        for r in lot['lines']:
            story.append(para("<b>"+text(r['id'])+" · "+text(r['designation'])+"</b> : "+text(r.get('detail') or "Âmbito a confirmar."), 'small', True))
    story += [PageBreak(), heading("Hipóteses e pontos a confirmar")]
    for name, values in (("Hipóteses de obra", study.get("assumptions", [])),
                         ("Controlos e informações em falta", study.get("warnings", [])),
                         ("Controlos de cálculo", [f"{r['item_id']} : {r['message']}" for r in study.get("controls", [])])):
        if values:
            story.append(para(name, "h2"))
            story.extend(para("• "+str(v), "body") for v in values)
    story += [para("Estrutura e execução", "h2"),para("Um projeto de licenciamento não dimensiona as fundações, as contenções nem as armaduras. As hipóteses de material e de sistema construtivo servem o orçamento; devem ser conciliadas com os projetos de execução. Uma quantidade em falta nunca vale zero.")]
    story += [PageBreak(), heading("Preços, âmbito e rastreabilidade"),para("Base dos preços", "h2"),
              para("Preços de venda com fornecimento e aplicação. A tabela orçamental não é uma tabela de fornecedor nem uma proposta de empresa. Nenhuma margem é acrescentada automaticamente; os custos de produção e a margem não são determinados por este estudo."),
              para("Origem dos preços", "h2"),
              table(["Origem", "Artigos"], [[label, ", ".join(str(i+1).zfill(2) for i,r in enumerate([x for x in study['items'] if x['included']]) if r['price_source']==key)]
                  for key,label in [("prix_utilisateur","Preços introduzidos"),("estimation_budgetaire","Tabela orçamental a confirmar"),("non_chiffre","Preços não fornecidos")]
                  if any(r['price_source']==key for r in study['items'] if r['included'])],[185,WIDTH-185]),
              para("Fora do âmbito", "h2")]
    story.extend(para("• "+str(x)) for x in study.get("exclusions", []))
    coverage = study.get("coverage") or {}
    story += [para("Fontes e verificação", "h2"),para(f"Fonte: {(study.get('source') or {}).get('filename') or plan.get('filename') or 'dossier'}. Páginas lidas: {', '.join(map(str, coverage.get('analyzed_pages', []))) or 'introdução documentada'}. Páginas com falha: {', '.join(map(str, coverage.get('failed_pages', []))) or 'nenhuma declarada'}. Páginas fora da seleção: {', '.join(map(str, coverage.get('omitted_pages', []))) or 'aucune'}.","small"),
              para(f"Cálculo {study.get('schema_version')} ; tabela {study.get('catalog_version')}. Révision {study.get('revision', '')[:16]}. Os totais são recalculados a partir das linhas, com arredondamento monetário. A interpretação completa da planta não é certificada pelo controlo aritmético.","small"),
              para("Antes de qualquer compromisso: confirmar os dados em falta, os sistemas construtivos, o terreno, a vizinhança e os preços com os intervenientes. Prazos, seguros e condições comerciais ficam por definir.","small")]
    def on_page(c, doc):
        c.saveState();c.setFillColor(CREAM);c.rect(0,0,A4[0],A4[1],fill=1,stroke=0)
        c.setFillColor(COPPER);c.rect(0,A4[1]-8,A4[0],8,fill=1,stroke=0)
        c.setFont("DossierBold",10);c.drawString(48,A4[1]-42,(branding.get("company_name") or "CONSTRUPILOT")[:55])
        c.setStrokeColor(LINE);c.line(48,43,A4[0]-48,43);c.setFont("Dossier",7.2);c.setFillColor(MUTED)
        c.drawString(48,29,f'{ref} | Estimativa a validar | {date}');c.restoreState()
    pdf.build(story,onFirstPage=on_page,onLaterPages=on_page,canvasmaker=NumberedCanvas)
    return buf.getvalue()


def build_dossier_docx(plan, study, branding=None):
    """Same data/unknowns as PDF; no legacy fixed assumptions in Word exports."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    doc=Document()
    doc.styles['Normal'].font.name='DejaVu Sans'
    doc.styles['Normal'].font.size=Pt(10)
    doc.add_heading("Orçamento estimativo de estrutura e alvenarias",0)
    doc.add_paragraph((study.get('project') or {}).get('title') or plan.get('filename') or '')
    for lot in study['lots']:
        doc.add_heading(lot['lot'],1)
        table=doc.add_table(rows=1, cols=6)
        for c,v in zip(table.rows[0].cells,["Designação","Qtd.",'U',"Estado","PU s/ IVA","Total s/ IVA"]): c.text=v
        for r in lot['lines']:
            for c,v in zip(table.add_row().cells,[r['designation'],fmt(r['qty']),r['unit'],r['quantity_status'],fmt(r['unit_price']),fmt(r['total'])]): c.text=v
    for key,label in [('ht','HT'),('tva',"IVA"),('ttc',"c/ IVA")]:doc.add_paragraph(f"{label} : {fmt(study['totals'][key],True)}")
    doc.add_heading("Medições e fontes",1)
    for r in study['items']:
        doc.add_heading(r['designation'],2)
        doc.add_paragraph(f"{r['expression']} = {fmt(r['qty'])} {r['unit']} [{r['quantity_status']}]")
        doc.add_paragraph(r.get('detail') or '')
        for p in r['sources']:doc.add_paragraph(f"{p['label']} : {fmt(p['value'])} {p['unit']} ; "+'; '.join(f"p. {x['page']} {x['text']}" for x in p['sources'])+" "+p.get('note',''))
    for title,key in [("Hipóteses",'assumptions'),("Pontos a confirmar",'warnings'),("Exclusões",'exclusions')]:
        doc.add_heading(title,1)
        for x in study.get(key,[]):doc.add_paragraph(str(x))
    doc.add_paragraph("Preços orçamentais ou introduzidos pelo utilizador. Estimativa não contratual; projetos de execução e preços de empresa a confirmar.")
    for name in ['Title','Heading 1','Heading 2']:doc.styles[name].font.color.rgb=RGBColor.from_string('925535')
    out=BytesIO();doc.save(out);return out.getvalue()
