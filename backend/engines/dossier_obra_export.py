"""Geração dos formatos do Dossier de Obra a partir do modelo congelado de uma emissão.

PDF (apresentação e entrega) · DOCX (relatório editável) · XLSX (medições, materiais, pendências e custos) ·
ZIP (os três ficheiros + manifesto + fotografias acessíveis). Um único modelo alimenta todos os formatos,
para que digam exatamente o mesmo.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import unicodedata
import zipfile
from xml.sax.saxutils import escape

GREEN = "#1F3D2B"      # navegação verde escura ConstruPilot
PRIMARY = "#508662"    # hsl(140 25% 42%) — ações principais
CREAM = "#F6F1E8"      # fundo creme
COPPER = "#B87333"
STATUS_COLORS = {"validado": "#2E7D4F", "pendente": "#B26A00", "rascunho": "#6B7280", "nao_aplicavel": "#9CA3AF", "rejeitado": "#B42318"}
Q_LABELS = {"medida": "Medida", "orcamentada": "Orçamentada", "compra": "Para compra", "encomendada": "Encomendada",
            "recebida": "Recebida", "executada": "Executada", "validada_auto": "Validada p/ auto", "faturada": "Faturada"}


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")[:60] or "dossier"


def filename(model: dict, ext: str) -> str:
    v = (model.get("emission") or {}).get("version", 0)
    return f"{_slug(model['title'])}_{_slug(model['obra']['name'])}_v{v:02d}.{ext}"


def _num(v) -> str:
    if v is None or v == "":
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{f:,.2f}".replace(",", " ").replace(".", ",")
    return s[:-3] if s.endswith(",00") else s


def _logo_bytes(model: dict) -> bytes | None:
    b = (model.get("branding") or {}).get("logo_b64")
    if not b:
        return None
    try:
        return base64.b64decode(b.split(",", 1)[1] if b.startswith("data:") else b)
    except Exception:  # noqa: BLE001
        return None


# ───────────────────────── PDF ─────────────────────────

def to_pdf(model: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    buf = io.BytesIO()
    em = model.get("emission") or {}
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                            title=f"{model['title']} — {model['obra']['name']}", author="ConstruPilot", subject="Dossier de obra")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, textColor=colors.HexColor(GREEN), spaceAfter=8)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor(PRIMARY), spaceBefore=8, spaceAfter=4)
    H3 = ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor(GREEN), spaceBefore=6, spaceAfter=3)
    B = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, alignment=TA_LEFT)
    S = ParagraphStyle("s", parent=B, fontSize=8, leading=10, textColor=colors.HexColor("#4B5563"))
    P = lambda t, st=B: Paragraph(escape(str(t or "")), st)  # noqa: E731

    def table(head, rows, widths=None):
        data = [[P(h, ParagraphStyle("th", parent=S, textColor=colors.white, fontName="Helvetica-Bold")) for h in head]]
        data += [[c if not isinstance(c, (str, int, float)) else P(c, S) for c in r] for r in rows]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(CREAM)]),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8D2C4")),
                               ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
        return t

    def badge(key, label):
        return Paragraph(f'<font color="{STATUS_COLORS.get(key, "#374151")}"><b>{escape(label)}</b></font>', S)

    def on_page(canv, d):
        canv.saveState()
        canv.setFillColor(colors.HexColor(GREEN))
        canv.rect(0, A4[1] - 9 * mm, A4[0], 9 * mm, fill=1, stroke=0)
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 8.5)
        canv.drawString(18 * mm, A4[1] - 6 * mm, f"ConstruPilot · {model['obra']['name']}")
        canv.setFont("Helvetica", 8)
        canv.drawRightString(A4[0] - 18 * mm, A4[1] - 6 * mm, f"{model['title']} · versão {em.get('version', 0):02d}")
        canv.setFillColor(colors.HexColor("#6B7280"))
        canv.drawString(18 * mm, 10 * mm, model["notice"])
        canv.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Página {d.page}")
        canv.restoreState()

    def cover(canv, d):
        canv.saveState()
        canv.setFillColor(colors.HexColor(CREAM))
        canv.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canv.setFillColor(colors.HexColor(GREEN))
        canv.rect(0, A4[1] - 70 * mm, A4[0], 70 * mm, fill=1, stroke=0)
        canv.setFillColor(colors.HexColor(PRIMARY))
        canv.rect(0, A4[1] - 72 * mm, A4[0], 2 * mm, fill=1, stroke=0)
        canv.restoreState()

    story = []
    logo = _logo_bytes(model)
    if logo:
        try:
            story.append(Image(io.BytesIO(logo), width=38 * mm, height=18 * mm, kind="proportional"))
        except Exception:  # noqa: BLE001
            pass
    company = (model.get("branding") or {}).get("company") or ""
    CW = ParagraphStyle("cw", parent=H1, textColor=colors.white, fontSize=26, leading=30)
    story += [Spacer(1, 8 * mm), Paragraph("ConstruPilot" + (f" · {escape(company)}" if company else ""), ParagraphStyle("ct", parent=B, textColor=colors.white, fontSize=11)),
              Spacer(1, 4 * mm), Paragraph(escape(model["title"].upper()), CW),
              Paragraph(escape(model["obra"]["name"]), ParagraphStyle("cn", parent=CW, fontSize=17)), Spacer(1, 40 * mm)]
    ident = [["Obra", model["obra"]["name"]], ["Referência", model["obra"]["ref"]], ["Cliente", model["obra"]["client"] or "—"],
             ["Morada", model["obra"]["address"] or "—"], ["Fase global", model["obra"]["global_phase"]],
             ["Destinatário", model["recipient"]], ["Conteúdo", model["content_label"]],
             ["Versão", f"{em.get('version', 0):02d} · {(em.get('date') or '')[:10]}"]]
    if model["filters"]["phases"]:
        ident.append(["Fases", ", ".join(model["filters"]["phases"])])
    if model["filters"]["locations"]:
        ident.append(["Locais", ", ".join(model["filters"]["locations"])])
    story.append(table(["Identificação da obra", ""], ident, [45 * mm, 125 * mm]))
    if model["obra"].get("demo"):
        story += [Spacer(1, 4 * mm), P("EXEMPLO DEMONSTRATIVO — dados fictícios.", ParagraphStyle("demo", parent=B, textColor=colors.HexColor(COPPER), fontName="Helvetica-Bold"))]
    story += [Spacer(1, 4 * mm), P(model["notice"], S), PageBreak()]

    story.append(Paragraph("Índice", H1))
    story.append(table(["N.º", "Capítulo"], [[f"{i:02d}", t] for i, t in enumerate(model["toc"], 1)], [18 * mm, 152 * mm]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Resumo", H1))
    sm = model["summary"]
    story.append(P(f"{sm['specialties']} especialidade(s) e {sm['items']} registo(s) incluídos."))
    story.append(table(["Validado", "Pendente", "Rascunho", "Não aplicável"],
                       [[str(sm.get("validado", 0)), str(sm.get("pendente", 0)), str(sm.get("rascunho", 0)), str(sm.get("nao_aplicavel", 0))]]))
    for w in model.get("warnings") or []:
        story.append(P("Atenção: " + w, S))

    for ch in model["chapters"]:
        story += [PageBreak(), Paragraph(escape(ch["label"]), H1)]
        for sp in ch["specialties"]:
            head = [Paragraph(escape(sp["label"]), H2),
                    P(f"Estado: {sp['status']} · Etapa: {sp['stage']}" + (f" · Responsável: {sp['responsible']}" if sp["responsible"] else ""), S)]
            if not sp["items"]:
                story.append(KeepTogether(head + [P("Sem registos incluídos para esta seleção.", S)]))
                continue
            rows = [[it["title"] + (f" — {it['element']}" if it["element"] else ""), it["kind"] or "", it["location"] or "—",
                     it["revision"] or "—", badge(it["status_key"], it["status"])] for it in sp["items"]]
            story += head + [table(["Registo", "Tipo", "Local", "Rev.", "Estado"], rows, [70 * mm, 24 * mm, 36 * mm, 14 * mm, 26 * mm])]

    def section(title, head, rows, widths):
        if rows:
            story.extend([PageBreak(), Paragraph(title, H1), table(head, rows, widths)])

    section("Plantas e referências", ["Especialidade", "Registo", "Origem", "Revisão"],
            [[r["specialty"], r["title"], f"{r['ref_kind'] or 'documento'} {r['ref_id'] or ''}".strip(), r["revision"] or "—"] for r in model["references"]],
            [40 * mm, 70 * mm, 40 * mm, 20 * mm])
    if model["measurements"]:
        story += [PageBreak(), Paragraph("Medições", H1),
                  P("Quantidades distintas: medidas, orçamentadas, para compra, encomendadas, recebidas, executadas, validadas para auto e faturadas.", S)]
        for m in model["measurements"]:
            origin = ", ".join(x for x in [m.get("m_document"), f"rev. {m['m_revision']}" if m.get("m_revision") else "",
                                            f"pág. {m['m_page']}" if m.get("m_page") else "", m.get("m_element"),
                                            f"escala {m['m_scale']}" if m.get("m_scale") else "", m.get("m_method")] if x)
            q = m.get("quantities") or {}
            rows = [[Q_LABELS[k], _num(q.get(k)), m.get("m_unit") or ""] for k in Q_LABELS if k in q]
            if m.get("m_quantity") is not None and "medida" not in q:
                rows.insert(0, ["Medida", _num(m.get("m_quantity")), m.get("m_unit") or ""])
            block = [Paragraph(escape(f"{m['specialty']} · {m['title']}"), H3), P(f"Origem: {origin or 'não indicada'} · Estado: {m['status']}", S)]
            if rows:
                block.append(table(["Quantidade", "Valor", "Unidade"], rows, [60 * mm, 40 * mm, 30 * mm]))
            story.append(KeepTogether(block))
    if model["materials"]:
        story += [PageBreak(), Paragraph("Materiais e sistemas", H1)]
        for m in model["materials"]:
            block = [Paragraph(escape(f"{m['specialty']} · {m['title']}"), H3), P(f"Estado: {m['status']} · {m['source']}", S)]
            if m["layers"]:
                block.append(table(["N.º", "Camada", "Material", "Origem", "Validação"],
                                   [[str(lay["order"]), lay["name"], lay["material"], lay["source"], lay["validation"]] for lay in m["layers"]],
                                   [12 * mm, 38 * mm, 50 * mm, 40 * mm, 30 * mm]))
            story.append(KeepTogether(block))
        story.append(P("Uma trama ou legenda não prova, por si só, o material nem todas as camadas.", S))
    section("Registos e verificações", ["Data", "Especialidade", "Registo", "Tipo", "Estado"],
            [[r["date"], r["specialty"], r["title"], r["kind"], r["status"]] for r in model["records"]], [22 * mm, 38 * mm, 62 * mm, 24 * mm, 24 * mm])
    section("Alterações", ["Data", "Especialidade", "Registo", "Ação", "Por"],
            [[c["date"], c["specialty"], c["title"] + (f" — {c['note']}" if c["note"] else ""), c["action"], c["by"] or ""] for c in model["changes"]],
            [22 * mm, 34 * mm, 66 * mm, 26 * mm, 22 * mm])
    section("Pendências", ["Especialidade", "Pendência", "Estado", "Ligada a"],
            [[p["specialty"], p["title"], p["status"], p["related"] or "—"] for p in model["pendencias"]], [40 * mm, 76 * mm, 24 * mm, 30 * mm])
    if model.get("budget"):
        b = model["budget"]
        story += [PageBreak(), Paragraph("Orçamento por especialidade", H1), P(b["note"], S)]
        for g in b["specialties"]:
            story.append(KeepTogether([Paragraph(escape(g["label"]), H3),
                table(["Designação", "Un.", "Qtd.", "Preço unit. (€)", "Total s/ IVA (€)", "Origem do preço"],
                      [[r["title"], r["unit"], _num(r["qty"]), _num(r["unit_price"]), _num(r["total"]) if r["total"] is not None else "a definir",
                        r["price_source"] or "—"] for r in g["lines"]] + [["Subtotal", "", "", "", _num(g["subtotal_ht"]), ""]],
                      [62 * mm, 12 * mm, 18 * mm, 24 * mm, 28 * mm, 26 * mm])]))
        story.append(P(f"Total s/ IVA das especialidades: {_num(b['total_ht'])} €" + (f" · {b['missing_prices']} linha(s) sem preço" if b["missing_prices"] else ""), B))
    if model.get("finance"):
        f = model["finance"]
        k = f.get("kpis") or {}
        section("Informação financeira", ["Número", "Documento", "Tipo", "Estado", "Total s/ IVA", "Total c/ IVA"],
                [[d.get("number") or "—", d.get("title") or "", d.get("type") or "", d.get("status") or "", _num(d.get("total_ht")), _num(d.get("total_ttc"))]
                 for d in f.get("documents") or []] or [["—", "Sem documentos financeiros", "", "", "", ""]],
                [22 * mm, 50 * mm, 18 * mm, 20 * mm, 30 * mm, 30 * mm])
        story.append(P(f"Assinado c/ IVA: {_num(k.get('signed_ttc'))} € · Faturado c/ IVA: {_num(k.get('invoiced_ttc'))} € · Pago: {_num(k.get('paid'))} €", S))
    if model["photos"]:
        section("Anexos — fotografias", ["Relatório", "Ficheiro"], [[p["report"], p["path"].split("/")[-1]] for p in model["photos"]], [80 * mm, 90 * mm])

    story += [PageBreak(), Paragraph("Identificação da emissão", H1),
              table(["Campo", "Valor"], [["Data", (em.get("date") or "")[:19].replace("T", " ") + " UTC"], ["Versão", f"{em.get('version', 0):02d}"],
                                         ["Emitido por", em.get("by") or ""], ["Âmbito", model["title"]],
                                         ["Especialidades", ", ".join(s["label"] for ch in model["chapters"] for s in ch["specialties"])],
                                         ["Revisões incluídas", ", ".join(model["revisions"]) or "—"],
                                         ["Estado", em.get("status") or ""]], [45 * mm, 125 * mm]),
              Spacer(1, 4 * mm), P(model["notice"])]
    doc.build(story, onFirstPage=cover, onLaterPages=on_page)
    return buf.getvalue()


# ───────────────────────── DOCX ─────────────────────────

def to_docx(model: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    em = model.get("emission") or {}
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    green = RGBColor(0x1F, 0x3D, 0x2B)

    def h(text, level=1):
        p = d.add_heading(text, level=level)
        for r in p.runs:
            r.font.color.rgb = green
        return p

    def table(head, rows):
        t = d.add_table(rows=1, cols=len(head))
        t.style = "Light Grid Accent 1"
        for i, x in enumerate(head):
            t.rows[0].cells[i].text = str(x)
        for r in rows:
            cells = t.add_row().cells
            for i, x in enumerate(r):
                cells[i].text = str(x if x is not None else "")
        d.add_paragraph()

    logo = _logo_bytes(model)
    if logo:
        try:
            from docx.shared import Mm
            d.add_picture(io.BytesIO(logo), width=Mm(38))
        except Exception:  # noqa: BLE001
            pass
    t = d.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = t.add_run(model["title"].upper())
    r.bold, r.font.size, r.font.color.rgb = True, Pt(22), green
    d.add_paragraph(model["obra"]["name"]).runs[0].font.size = Pt(15)
    if model["obra"].get("demo"):
        d.add_paragraph("EXEMPLO DEMONSTRATIVO — dados fictícios.")
    h("Identificação da obra", 1)
    table(["Campo", "Valor"], [["Obra", model["obra"]["name"]], ["Referência", model["obra"]["ref"]], ["Cliente", model["obra"]["client"] or "—"],
                               ["Morada", model["obra"]["address"] or "—"], ["Fase global", model["obra"]["global_phase"]],
                               ["Destinatário", model["recipient"]], ["Conteúdo", model["content_label"]],
                               ["Versão", f"{em.get('version', 0):02d} · {(em.get('date') or '')[:10]}"]])
    h("Índice", 1)
    for i, x in enumerate(model["toc"], 1):
        d.add_paragraph(f"{i:02d}  {x}")
    h("Resumo", 1)
    sm = model["summary"]
    d.add_paragraph(f"{sm['specialties']} especialidade(s), {sm['items']} registo(s): {sm.get('validado', 0)} validado(s), "
                    f"{sm.get('pendente', 0)} pendente(s), {sm.get('rascunho', 0)} rascunho(s), {sm.get('nao_aplicavel', 0)} não aplicável(eis).")
    for w in model.get("warnings") or []:
        d.add_paragraph("Atenção: " + w)
    for ch in model["chapters"]:
        h(ch["label"], 1)
        for sp in ch["specialties"]:
            h(sp["label"], 2)
            d.add_paragraph(f"Estado: {sp['status']} · Etapa: {sp['stage']}" + (f" · Responsável: {sp['responsible']}" if sp["responsible"] else ""))
            if sp["items"]:
                table(["Registo", "Tipo", "Local", "Revisão", "Estado"],
                      [[it["title"] + (f" — {it['element']}" if it["element"] else ""), it["kind"], it["location"] or "—", it["revision"] or "—", it["status"]]
                       for it in sp["items"]])
            else:
                d.add_paragraph("Sem registos incluídos para esta seleção.")
    if model["references"]:
        h("Plantas e referências", 1)
        table(["Especialidade", "Registo", "Origem", "Revisão"], [[r["specialty"], r["title"], f"{r['ref_kind'] or 'documento'} {r['ref_id'] or ''}", r["revision"] or "—"] for r in model["references"]])
    if model["measurements"]:
        h("Medições", 1)
        for m in model["measurements"]:
            h(f"{m['specialty']} · {m['title']}", 3)
            origin = ", ".join(x for x in [m.get("m_document"), m.get("m_revision") and f"rev. {m['m_revision']}", m.get("m_page") and f"pág. {m['m_page']}",
                                            m.get("m_element"), m.get("m_scale") and f"escala {m['m_scale']}", m.get("m_method")] if x)
            d.add_paragraph(f"Origem: {origin or 'não indicada'} · Estado: {m['status']}")
            q = m.get("quantities") or {}
            if q:
                table(["Quantidade", "Valor", "Unidade"], [[Q_LABELS[k], _num(q[k]), m.get("m_unit") or ""] for k in Q_LABELS if k in q])
    if model["materials"]:
        h("Materiais e sistemas", 1)
        for m in model["materials"]:
            h(f"{m['specialty']} · {m['title']}", 3)
            d.add_paragraph(f"Estado: {m['status']} · {m['source']}")
            if m["layers"]:
                table(["N.º", "Camada", "Material", "Origem", "Validação"], [[lay["order"], lay["name"], lay["material"], lay["source"], lay["validation"]] for lay in m["layers"]])
    if model["records"]:
        h("Registos e verificações", 1)
        table(["Data", "Especialidade", "Registo", "Tipo", "Estado"], [[r["date"], r["specialty"], r["title"], r["kind"], r["status"]] for r in model["records"]])
    if model["changes"]:
        h("Alterações", 1)
        table(["Data", "Especialidade", "Registo", "Ação", "Por"], [[c["date"], c["specialty"], c["title"], c["action"], c["by"] or ""] for c in model["changes"]])
    if model["pendencias"]:
        h("Pendências", 1)
        table(["Especialidade", "Pendência", "Estado", "Ligada a"], [[p["specialty"], p["title"], p["status"], p["related"] or "—"] for p in model["pendencias"]])
    if model.get("budget"):
        b = model["budget"]
        h("Orçamento por especialidade", 1)
        d.add_paragraph(b["note"])
        for g in b["specialties"]:
            h(g["label"], 3)
            table(["Designação", "Un.", "Qtd.", "Preço unit. (€)", "Total s/ IVA (€)", "Origem"],
                  [[r["title"], r["unit"], _num(r["qty"]), _num(r["unit_price"]), _num(r["total"]) if r["total"] is not None else "a definir", r["price_source"] or "—"] for r in g["lines"]]
                  + [["Subtotal", "", "", "", _num(g["subtotal_ht"]), ""]])
        d.add_paragraph(f"Total s/ IVA: {_num(b['total_ht'])} €")
    if model.get("finance"):
        h("Informação financeira", 1)
        table(["Número", "Documento", "Tipo", "Estado", "Total s/ IVA", "Total c/ IVA"],
              [[x.get("number") or "—", x.get("title") or "", x.get("type") or "", x.get("status") or "", _num(x.get("total_ht")), _num(x.get("total_ttc"))]
               for x in model["finance"].get("documents") or []])
    if model["photos"]:
        h("Anexos", 1)
        for p in model["photos"]:
            d.add_paragraph(f"{p['report']} — {p['path'].split('/')[-1]}", style="List Bullet")
    h("Identificação da emissão", 1)
    table(["Campo", "Valor"], [["Data", (em.get("date") or "")[:19].replace("T", " ") + " UTC"], ["Versão", f"{em.get('version', 0):02d}"],
                               ["Emitido por", em.get("by") or ""], ["Revisões incluídas", ", ".join(model["revisions"]) or "—"], ["Estado", em.get("status") or ""]])
    d.add_paragraph(model["notice"])
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


# ───────────────────────── XLSX ─────────────────────────

def to_xlsx(model: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_fill = PatternFill("solid", fgColor=GREEN[1:])
    head_font = Font(bold=True, color="FFFFFF")

    def sheet(ws, title, head, rows, widths=None):
        ws.title = title[:31]
        ws.append([f"{model['title']} — {model['obra']['name']} — versão {(model.get('emission') or {}).get('version', 0):02d}"])
        ws["A1"].font = Font(bold=True, size=12, color=GREEN[1:])
        ws.append([model["notice"]])
        ws.append([])
        ws.append(head)
        for c in ws[4]:
            c.fill, c.font = head_fill, head_font
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for r in rows:
            ws.append(r)
        for i, w in enumerate(widths or [24] * len(head), 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A5"
        return ws

    qkeys = list(Q_LABELS)
    meas_rows = []
    for m in model["measurements"]:
        q = m.get("quantities") or {}
        if m.get("m_quantity") is not None and "medida" not in q:
            q = {"medida": m["m_quantity"], **q}
        meas_rows.append([m["specialty"], m["title"], m.get("element") or "", m.get("location") or "", m.get("m_document") or "", m.get("m_revision") or "",
                          m.get("m_page") or "", m.get("m_scale") or "", m.get("m_method") or "", m.get("m_unit") or "",
                          *[q.get(k) for k in qkeys], m["status"]])
    sheet(wb.active, "Medições", ["Especialidade", "Registo", "Elemento", "Local", "Documento", "Revisão", "Página", "Escala", "Método", "Unidade",
                                  *[Q_LABELS[k] for k in qkeys], "Estado"], meas_rows,
          [22, 30, 18, 20, 22, 9, 8, 9, 22, 8, *[12] * len(qkeys), 12])
    sheet(wb.create_sheet(), "Materiais e camadas", ["Especialidade", "Material/sistema", "Estado", "N.º", "Camada", "Material", "Origem", "Validação", "Referência"],
          [[m["specialty"], m["title"], m["status"], lay["order"], lay["name"], lay["material"], lay["source"], lay["validation"], lay["reference"]]
           for m in model["materials"] for lay in (m["layers"] or [{"order": "", "name": "", "material": "", "source": m["source"], "validation": "", "reference": ""}])],
          [22, 28, 12, 6, 18, 26, 22, 14, 26])
    sheet(wb.create_sheet(), "Pendências", ["Especialidade", "Pendência", "Estado", "Ligada a"],
          [[p["specialty"], p["title"], p["status"], p["related"]] for p in model["pendencias"]], [24, 50, 14, 24])
    if model.get("budget"):
        ws = sheet(wb.create_sheet(), "Orçamento", ["Especialidade", "Designação", "Unidade", "Quantidade", "Preço unitário (€)", "Total s/ IVA (€)", "Origem do preço"], [], [26, 40, 9, 12, 16, 16, 16])
        sub_cells = []
        for g in model["budget"]["specialties"]:
            first = ws.max_row + 1
            for r in g["lines"]:
                ws.append([g["label"], r["title"], r["unit"], r["qty"], r["unit_price"], None, r["price_source"] or ("a definir" if r["unit_price"] is None else "")])
                n = ws.max_row
                ws.cell(n, 6).value = f'=IF(OR(D{n}="",E{n}=""),"",D{n}*E{n})'
            last = ws.max_row
            ws.append(["", f"Subtotal {g['label']}", "", "", "", f"=SUM(F{first}:F{last})", ""])
            sub_cells.append(f"F{ws.max_row}")
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
        ws.append(["", "TOTAL", "", "", "", "=" + "+".join(sub_cells) if sub_cells else 0, ""])
        for c in ws[ws.max_row]:
            c.font = Font(bold=True, color=GREEN[1:])
    if model.get("finance"):
        rows = [[x.get("number"), x.get("title"), x.get("type"), x.get("status"), x.get("total_ht"), x.get("total_ttc")] for x in model["finance"].get("documents") or []]
        ws = sheet(wb.create_sheet(), "Custos", ["Número", "Documento", "Tipo", "Estado", "Total s/ IVA (€)", "Total c/ IVA (€)"], rows, [14, 40, 12, 12, 16, 16])
        if rows:
            n = 4 + len(rows)
            ws.append(["", "Total", "", "", f"=SUM(E5:E{n})", f"=SUM(F5:F{n})"])
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ───────────────────────── ZIP ─────────────────────────

async def to_zip(model: dict) -> bytes:
    pdf, docx, xlsx = await asyncio.gather(asyncio.to_thread(to_pdf, model), asyncio.to_thread(to_docx, model), asyncio.to_thread(to_xlsx, model))
    buf = io.BytesIO()
    missing = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename(model, "pdf"), pdf)
        z.writestr(filename(model, "docx"), docx)
        z.writestr(filename(model, "xlsx"), xlsx)
        if model.get("photos"):
            from engines import storage
            for i, p in enumerate(model["photos"][:60], 1):
                try:
                    data, _ct = await asyncio.to_thread(storage.get_object, p["path"])
                    z.writestr(f"anexos/fotografias/{i:02d}_{p['path'].split('/')[-1]}", data)
                except Exception:  # noqa: BLE001 — anexos indisponíveis ficam listados no manifesto
                    missing.append(p["path"])
        manifest = {"titulo": model["title"], "obra": model["obra"], "emissao": model.get("emission"), "revisoes": model["revisions"],
                    "conteudo": model["content_label"], "destinatario": model["recipient"], "anexos_indisponiveis": missing,
                    "aviso": model["notice"]}
        z.writestr("manifesto.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buf.getvalue()
