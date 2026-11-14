"""Livrables systématiques d'un devis de l'assistant : devis PDF + devis Excel + métré PDF + métré Excel.

Chaque création / révision / ajout / relecture d'un devis brouillon par l'Assistant BTP produit ces quatre
fichiers, pour tout compte entreprise. Les fichiers sont des artefacts privés de la conversation
(``assistant_artifacts``), identifiés de façon stable par (devis, version) : un nouvel appel sur la même
version ne régénère rien. Le brouillon n'est jamais numéroté ici (la numérotation reste à l'émission).
"""
import asyncio
import base64
import hashlib
import io
from datetime import datetime, timezone

from core.db import db
from engines.nom_fichier import nom_document

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Instruções do Assistente (acrescentadas a QUOTE_INSTRUCTIONS em routes/assistant.py).
EXPORT_INSTRUCTIONS = (
    "\nORÇAMENTO + MEDIÇÃO (regra absoluta, qualquer conta empresa): cada orçamento criado, completado, revisto ou relido "
    "traz 4 ficheiros anexos (artifacts) — orçamento PDF, orçamento Excel, medição PDF, medição Excel "
    "(devis PDF, devis Excel, métré PDF, métré Excel). Quando te pedem um orçamento e/ou uma medição, anuncia SEMPRE "
    "estes 4 ficheiros. Para fornecer os ficheiros de um orçamento existente, chama read_quote_draft. "
    "Não cries um PDF separado com create_downloadable_file para um orçamento ou medição: usa estes ficheiros. "
    "Se files_error estiver presente, di-lo honestamente e volta a chamar read_quote_draft.\n"
    "MAPA DE QUANTIDADES = ATÉ AOS PARAFUSOS (regra do Martinho, todos os pedidos): a medição traz automaticamente a "
    "decomposição de cada artigo em TODOS os materiais (placas, perfis, parafusos, buchas, pregos, colas, argamassas, "
    "fitas…) e a lista total para encomenda. Para isso: (1) cada artigo tem de ser MEDIDO (quantidade lida nas plantas, "
    "nunca por rácio €/m² nem «1 un» global); (2) escreve na designação as dimensões que o desenho dá (espessura, formato "
    "do tijolo/peça, L×A do vão, n.º de demãos); (3) o que o desenho não dá fica «a confirmar» — nunca inventado. "
    "Uma estimativa por rácios NUNCA se chama mapa de quantidades: chama-se estimativa e diz o que falta para medir.\n"
    "ORÇAMENTO/MAPA COM PREÇOS DE UM DWG/DXF → chama orcamento_cad_completo(plan_id, sistema, …): faz tudo num passo "
    "(medição, estrutura, bases, preços com origem, totais, ficheiros). Não refaças à mão com create_quote_draft. Depois "
    "apresenta o resumo devolvido e as hipóteses; corrige depois com read_quote_draft/update_quote_draft se pedirem.\n"
    "MESMO DESENHO = MESMO RESULTADO (regra do Martinho, todas as contas): a medição, a estrutura e os preços de um DWG/DXF "
    "ficam como referência na primeira vez; repetir o pedido, reformulá-lo ou mudar de conversa dá os MESMOS números. Só um "
    "dado novo dado pelo utilizador (pé-direito, pisos…) acrescenta/revê — passa-o nos argumentos; nunca inventes valores "
    "(null = manter). recalcular=true só se o utilizador pedir explicitamente para recalcular do zero. Mostra sempre a "
    "verificacao_cruzada devolvida (ok e avisos com o detalhe).\n"
    "DESENHO CAD (DWG/DXF) sem preços (só medição) → chama PRIMEIRO medir_camadas_cad(plan_id): devolve os artigos MEDIDOS camada a camada "
    "(áreas das tramas, comprimentos de lancis/muros/vedações, contagens de blocos), com a origem de cada quantidade. "
    "Usa essas linhas TAL COMO VÊM (designação, unidade, quantidade, descrição) como artigos do mapa — são elas que dão "
    "a lista de materiais (blocos de pavê, t de betuminoso, ABGE, lancis, betão, terra vegetal, tinta…). Áreas escritas "
    "no desenho (lotes, área de implantação, domínio público), cadeias de cotas e lugares de estacionamento são "
    "INFORMAÇÃO, não artigos de obra: não as orçamentes como artigos. O edifício nunca vai a €/m²: a estrutura e a "
    "envolvente vêm de calcular_estrutura_cad (abaixo); acabamentos interiores só com as plantas do edifício. As camadas «excluidas» "
    "(levantamento/existente) e «camadas_area_sem_material» são ditas ao utilizador como pontos a confirmar. "
    "ESTRUTURA: um mapa de quantidades de obra INCLUI SEMPRE a estrutura — chama calcular_estrutura_cad(plan_id, sistema) "
    "com o sistema dito pelo utilizador ('é em aço'/'metálica' → metalica; betão armado → betao_armado; se não disse, "
    "pergunta numa linha qual é, sem parar o resto do mapa) e junta as linhas devolvidas. Nunca orçamentes o edifício a €/m².\n"
)
_LINE_KINDS_SKIP = ("section", "subsection", "text", "pagebreak")

L = {
    "fr": {"quote": "Devis", "takeoff": "Métré", "draft": "BROUILLON — à vérifier avant envoi", "lot": "Lot", "designation": "Désignation",
           "description": "Description", "qty": "Quantité", "unit": "Unité", "pu": "PU HT", "vat": "TVA %", "total": "Total HT",
           "origin": "Origine du prix", "status": "Statut", "to_confirm": "Quantité à confirmer", "ok": "Renseignée",
           "ht": "Total HT", "tva": "TVA", "ttc": "Total TTC", "client": "Client", "date": "Date", "general": "Général",
           "summary": "Récapitulatif par lot", "lines": "lignes", "estimated": "Prix estimé — à vérifier", "user": "Prix fourni",
           "library": "Bibliothèque", "missing": "À compléter", "note_metre": "Quantités issues du devis brouillon ; les quantités « à confirmer » doivent être relevées sur plans ou sur site.",
           "file_quote_pdf": "Devis (PDF)", "file_quote_xlsx": "Devis (Excel)", "file_metre_pdf": "Métré (PDF)", "file_metre_xlsx": "Métré (Excel)", "file_economic_pdf": "Dossier économique — coût, vente, marge (PDF)"},
    "pt": {"quote": "Orcamento", "takeoff": "Medicao", "draft": "RASCUNHO — a verificar antes do envio", "lot": "Capítulo", "designation": "Designação",
           "description": "Descrição", "qty": "Quantidade", "unit": "Unidade", "pu": "PU s/ IVA", "vat": "IVA %", "total": "Total s/ IVA",
           "origin": "Origem do preço", "status": "Estado", "to_confirm": "Quantidade a confirmar", "ok": "Indicada",
           "ht": "Total s/ IVA", "tva": "IVA", "ttc": "Total c/ IVA", "client": "Cliente", "date": "Data", "general": "Geral",
           "summary": "Resumo por capítulo", "lines": "linhas", "estimated": "Preço estimado — a verificar", "user": "Preço fornecido",
           "library": "Biblioteca", "missing": "A completar", "note_metre": "Quantidades do rascunho de orçamento; as quantidades «a confirmar» devem ser medidas nas plantas ou em obra.",
           "file_quote_pdf": "Orçamento (PDF)", "file_quote_xlsx": "Orçamento (Excel)", "file_metre_pdf": "Medição (PDF)", "file_metre_xlsx": "Medição (Excel)", "file_economic_pdf": "Dossier económico — custo, venda, margem (PDF)"},
    "en": {"quote": "Quote", "takeoff": "Takeoff", "draft": "DRAFT — to be checked before sending", "lot": "Trade", "designation": "Item",
           "description": "Description", "qty": "Quantity", "unit": "Unit", "pu": "Unit price excl. VAT", "vat": "VAT %", "total": "Total excl. VAT",
           "origin": "Price origin", "status": "Status", "to_confirm": "Quantity to confirm", "ok": "Given",
           "ht": "Total excl. VAT", "tva": "VAT", "ttc": "Total incl. VAT", "client": "Client", "date": "Date", "general": "General",
           "summary": "Summary by trade", "lines": "lines", "estimated": "Estimated price — to check", "user": "Price provided",
           "library": "Library", "missing": "To complete", "note_metre": "Quantities taken from the draft quote; quantities marked 'to confirm' must be measured on drawings or on site.",
           "file_quote_pdf": "Quote (PDF)", "file_quote_xlsx": "Quote (Excel)", "file_metre_pdf": "Takeoff (PDF)", "file_metre_xlsx": "Takeoff (Excel)", "file_economic_pdf": "Economic dossier — cost, sale, margin (PDF)"},
}


def _lang(lang):
    return lang if lang in L else "fr"


def _rows(doc):
    return [r for r in (doc.get("lines") or []) if r.get("kind") not in _LINE_KINDS_SKIP]


def _origin(r, t):
    if r.get("price_missing"):
        return t["missing"]
    if r.get("price_source") == "user_input":
        return t["user"]
    if r.get("price_estimated"):
        return r.get("price_reference_label") or t["estimated"]
    return t["library"]


def _client(doc):
    c = doc.get("client") or {}
    return doc.get("client_name") or c.get("company") or " ".join(filter(None, [c.get("first_name"), c.get("last_name")])) or ""


def _line_total(r):
    from decimal import ROUND_HALF_UP, Decimal
    disc = Decimal(str(r.get("discount_pct") or 0))
    return float((Decimal(str(r.get("qty") or 0)) * Decimal(str(r.get("unit_price_ht") or 0)) * (1 - disc / 100))
                 .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _style_header(ws, row, ncols):
    from openpyxl.styles import Alignment, Font, PatternFill
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _sheet_head(ws, title, doc, branding, t):
    from openpyxl.styles import Font
    ws["A1"] = (branding or {}).get("company_name") or "ConstruPilot"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = title
    ws["A2"].font = Font(bold=True, size=12)
    ws["A3"] = t["draft"]
    ws["A3"].font = Font(italic=True, color="B45309")
    ws["A4"] = f"{t['client']} : {_client(doc) or '—'}"
    ws["A5"] = f"{t['date']} : {datetime.now(timezone.utc).date().isoformat()}"
    return 7


def build_quote_xlsx(doc, branding=None, lang="fr") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    t = L[_lang(lang)]
    wb = Workbook()
    ws = wb.active
    ws.title = t["quote"][:31]
    r0 = _sheet_head(ws, doc.get("title") or t["quote"], doc, branding, t)
    heads = [t["lot"], t["designation"], t["description"], t["qty"], t["unit"], t["pu"], t["vat"], t["total"], t["origin"]]
    for i, h in enumerate(heads, 1):
        ws.cell(row=r0, column=i, value=h)
    _style_header(ws, r0, len(heads))
    rows = _rows(doc)
    first = r0 + 1
    for k, r in enumerate(rows):
        n = first + k
        disc = float(r.get("discount_pct") or 0)
        ws.cell(row=n, column=1, value=r.get("category") or t["general"])
        ws.cell(row=n, column=2, value=r.get("designation") or "")
        ws.cell(row=n, column=3, value=r.get("description") or "").alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=n, column=4, value=None if r.get("quantity_missing") else float(r.get("qty") or 0))
        ws.cell(row=n, column=5, value=r.get("unit") or "")
        ws.cell(row=n, column=6, value=None if r.get("price_missing") else float(r.get("unit_price_ht") or 0))
        ws.cell(row=n, column=7, value=float(r.get("vat_rate") or 0))
        factor = f"*(1-{disc}/100)" if disc else ""
        ws.cell(row=n, column=8, value=f"=ROUND(N(D{n})*N(F{n}){factor},2)")
        ws.cell(row=n, column=9, value=_origin(r, t))
        for c in (4, 6, 8):
            ws.cell(row=n, column=c).number_format = "#,##0.00"
    last = first + len(rows) - 1
    tr = last + 2
    rng_h, rng_g = f"H{first}:H{max(last, first)}", f"G{first}:G{max(last, first)}"
    ws.cell(row=tr, column=7, value=t["ht"]).font = Font(bold=True)
    ws.cell(row=tr, column=8, value=f"=ROUND(SUM({rng_h}),2)")
    ws.cell(row=tr + 1, column=7, value=t["tva"]).font = Font(bold=True)
    ws.cell(row=tr + 1, column=8, value=f"=ROUND(SUMPRODUCT({rng_h},{rng_g})/100,2)")
    ws.cell(row=tr + 2, column=7, value=t["ttc"]).font = Font(bold=True)
    ws.cell(row=tr + 2, column=8, value=f"=H{tr}+H{tr + 1}")
    for rr in range(tr, tr + 3):
        ws.cell(row=rr, column=8).number_format = "#,##0.00"
        ws.cell(row=rr, column=8).font = Font(bold=True)
    for col, w in zip("ABCDEFGHI", (18, 42, 50, 11, 8, 13, 8, 14, 26)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = ws.cell(row=first, column=1)
    _metre_sheet(wb.create_sheet(t["takeoff"][:31]), doc, branding, t)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _metre_sheet(ws, doc, branding, t):
    from openpyxl.styles import Alignment, Font
    r0 = _sheet_head(ws, f"{t['takeoff']} — {doc.get('title') or ''}".strip(" —"), doc, branding, t)
    heads = [t["lot"], t["designation"], t["description"], t["qty"], t["unit"], t["status"]]
    for i, h in enumerate(heads, 1):
        ws.cell(row=r0, column=i, value=h)
    _style_header(ws, r0, len(heads))
    n = r0
    for r in _rows(doc):
        n += 1
        ws.cell(row=n, column=1, value=r.get("category") or t["general"])
        ws.cell(row=n, column=2, value=r.get("designation") or "")
        ws.cell(row=n, column=3, value=r.get("description") or "").alignment = Alignment(wrap_text=True, vertical="top")
        q = ws.cell(row=n, column=4, value=None if r.get("quantity_missing") else float(r.get("qty") or 0))
        q.number_format = "#,##0.00"
        ws.cell(row=n, column=5, value=r.get("unit") or "")
        ws.cell(row=n, column=6, value=t["to_confirm"] if r.get("quantity_missing") else t["ok"])
    ws.cell(row=n + 2, column=1, value=t["note_metre"]).font = Font(italic=True)
    # Récapitulatif par lot et unité
    s = n + 4
    ws.cell(row=s, column=1, value=t["summary"]).font = Font(bold=True)
    agg = {}
    for r in _rows(doc):
        if r.get("quantity_missing"):
            continue
        key = (r.get("category") or t["general"], r.get("unit") or "")
        agg[key] = agg.get(key, 0.0) + float(r.get("qty") or 0)
    for i, ((lot, unit), qty) in enumerate(sorted(agg.items()), 1):
        ws.cell(row=s + i, column=1, value=lot)
        ws.cell(row=s + i, column=4, value=round(qty, 3)).number_format = "#,##0.00"
        ws.cell(row=s + i, column=5, value=unit)
    for col, w in zip("ABCDEF", (18, 42, 50, 11, 8, 22)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)


_MAT = {"fr": ("Matériaux par article", "Liste des matériaux", "Article", "Matériau", "Qté nette", "Perte %", "Qté à commander",
                "Conditionnement", "Source du coefficient", "Manque", "État"),
        "pt": ("Materiais por artigo", "Lista de materiais", "Artigo", "Material", "Qtd. líquida", "Perda %", "Qtd. a encomendar",
               "Embalagens", "Fonte do coeficiente", "Em falta", "Estado"),
        "en": ("Materials by item", "Materials list", "Item", "Material", "Net qty", "Waste %", "Qty to order",
               "Packaging", "Coefficient source", "Missing", "Status")}
_ESTADO = {"pt": {"completo": "Decomposto", "hipotese": "Decomposto — perfil-tipo (hipótese)", "parcial": "Parcial — falta dimensão", "sem_medicao": "Sem medição",
                  "global": "Artigo global — medir", "sem_receita": "Sem decomposição"},
           "fr": {"completo": "Décomposé", "hipotese": "Décomposé — profil-type (hypothèse)", "parcial": "Partiel — dimension manquante", "sem_medicao": "Non métré",
                  "global": "Article global — à métrer", "sem_receita": "Sans décomposition"},
           "en": {"completo": "Broken down", "hipotese": "Broken down — typical section (assumption)", "parcial": "Partial — dimension missing", "sem_medicao": "Not measured",
                  "global": "Lump-sum item — measure", "sem_receita": "No breakdown"}}


def _materiais_sheets(wb, doc, branding, t, lang):
    """Mapa de materiais até aos parafusos (engines.mapa_materiais): por artigo + totais para encomenda."""
    from openpyxl.styles import Alignment, Font
    from engines import mapa_materiais
    lg = _lang(lang)
    h = _MAT[lg]
    est = _ESTADO[lg]
    from engines.mapa_materiais_i18n import traduzir
    r = traduzir(mapa_materiais.mapa(_rows(doc)), lg)
    ws = wb.create_sheet(h[0][:31])
    r0 = _sheet_head(ws, h[0], doc, branding, t)
    heads = [h[2], t["qty"], t["unit"], h[10], h[3], h[4], h[5], h[6], t["unit"], h[7], h[8], h[9]]
    for i, x in enumerate(heads, 1):
        ws.cell(row=r0, column=i, value=x)
    _style_header(ws, r0, len(heads))
    n = r0
    for a in r["artigos"]:
        n += 1
        ws.cell(row=n, column=1, value=a["designacao"]).font = Font(bold=True)
        ws.cell(row=n, column=2, value=a["quantidade"])
        ws.cell(row=n, column=3, value=a["unidade"])
        ws.cell(row=n, column=4, value=est.get(a["estado"], a["estado"]))
        if a.get("motivo") and not a["materiais"]:
            ws.cell(row=n, column=12, value=a["motivo"])
        for m in a["materiais"]:
            n += 1
            vals = [None, None, None, None, m["material"], m["quantidade_liquida"], m["perda_pct"], m["quantidade_encomenda"],
                    m["unidade"], m["embalagens"], m["fonte"], m["em_falta"]]
            for i, v in enumerate(vals, 1):
                c = ws.cell(row=n, column=i, value=v)
                if i in (6, 8) and v is not None:
                    c.number_format = "#,##0.00"
                if i in (11, 12):
                    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=n + 2, column=1, value=r["aviso"]).font = Font(italic=True)
    for col, w in zip("ABCDEFGHIJKL", (40, 10, 7, 22, 44, 12, 8, 14, 7, 22, 46, 40)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)
    wt = wb.create_sheet(h[1][:31])
    r1 = _sheet_head(wt, h[1], doc, branding, t)
    for i, x in enumerate([h[3], h[4], h[6], t["unit"], t["lines"]], 1):
        wt.cell(row=r1, column=i, value=x)
    _style_header(wt, r1, 5)
    for k, m in enumerate(r["totais"], 1):
        for i, v in enumerate([m["material"], m["quantidade_liquida"], m["quantidade_encomenda"], m["unidade"], m["artigos"]], 1):
            c = wt.cell(row=r1 + k, column=i, value=v)
            if i in (2, 3):
                c.number_format = "#,##0.00"
    for col, w in zip("ABCDE", (52, 14, 16, 8, 10)):
        wt.column_dimensions[col].width = w
    return r


def build_metre_xlsx(doc, branding=None, lang="fr") -> bytes:
    from openpyxl import Workbook
    t = L[_lang(lang)]
    wb = Workbook()
    _metre_sheet(wb.active, doc, branding, t)
    wb.active.title = t["takeoff"][:31]
    _materiais_sheets(wb, doc, branding, t, lang)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_metre_pdf(doc, branding=None, lang="fr") -> bytes:
    """Medição do rascunho de orçamento — mesmo nível que o orçamento premium: cores da empresa, resumo por capítulo,
    tabela detalhada e acabamento pdf_premium (capa com indicadores, índice, logótipo, numeração)."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from engines import pdf_premium as PP
    t = L[_lang(lang)]
    lg = PP.lang_of(lang, (branding or {}).get("country"))
    TT = PP.TXT.get(lg, PP.TXT["pt"])
    titulo_tipo = TT["takeoff"]                                     # « Medição » / « Métré » / « Quantity take-off »
    accent = colors.HexColor(PP.cor_empresa(branding))
    dark = colors.HexColor("#1B2430")
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8, leading=10)
    h2 = ss["Heading2"].clone("h2c", textColor=dark, spaceBefore=2, spaceAfter=6)
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"{titulo_tipo} — {doc.get('title') or ''}")
    rows = _rows(doc)
    lots: dict[str, list] = {}
    for r in rows:
        lots.setdefault(r.get("category") or t["general"], []).append(r)
    n_conf = sum(1 for r in rows if r.get("quantity_missing"))
    head_style = [("BACKGROUND", (0, 0), (-1, 0), dark), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("LINEBELOW", (0, 0), (-1, 0), 1.6, accent), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#D7DCE3")),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F8")])]
    story = [Paragraph(escape(t["summary"]), h2),
             Paragraph(escape(f"{t['client']} : {_client(doc) or '—'}  ·  {t['date']} : {datetime.now(timezone.utc).date().isoformat()}"
                              f"  ·  {t['draft']}"), small), Spacer(1, 3 * mm)]
    summ = [[t["lot"], t["lines"].capitalize(), t["to_confirm"]]]
    for lot, rs in lots.items():
        summ.append([Paragraph(escape(lot), small), str(len(rs)), str(sum(1 for r in rs if r.get("quantity_missing")))])
    summ.append([Paragraph(f"<b>{escape(TT['lines'])}</b>", small), f"{len(rows)}", f"{n_conf}"])
    st = Table(summ, colWidths=[150 * mm, 40 * mm, 50 * mm], repeatRows=1)
    st.setStyle(TableStyle(head_style + [("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("LINEABOVE", (0, -1), (-1, -1), 1, accent),
                                         ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF1F4"))]))
    story += [st, PageBreak(), Paragraph(escape(f"{titulo_tipo} — {doc.get('title') or ''}".strip(" —")), h2)]
    data = [[t["lot"], t["designation"], t["description"], t["qty"], t["unit"], t["status"]]]
    for lot, rs in lots.items():
        data.append([Paragraph(f"<b>{escape(lot)}</b>", small), "", "", "", "", ""])
        for r in rs:
            qty = "—" if r.get("quantity_missing") else f"{float(r.get('qty') or 0):,.2f}".replace(",", " ")
            data.append(["", Paragraph(escape(r.get("designation") or ""), small),
                         Paragraph(escape((r.get("description") or "")[:600]), small), qty, r.get("unit") or "",
                         Paragraph(escape(t["to_confirm"] if r.get("quantity_missing") else t["ok"]), small)])
    tbl = LongTable(data, colWidths=[35 * mm, 70 * mm, 105 * mm, 22 * mm, 15 * mm, 26 * mm], repeatRows=1)
    lot_rows = [i for i, d in enumerate(data) if i and d[1] == ""]
    tbl.setStyle(TableStyle(head_style + [("ALIGN", (3, 1), (3, -1), "RIGHT")]
                            + [("SPAN", (0, i), (-1, i)) for i in lot_rows]
                            + [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E9EDF1")) for i in lot_rows]
                            + [("LINEBELOW", (0, i), (-1, i), 0.8, accent) for i in lot_rows]))
    story += [tbl, Spacer(1, 4 * mm), Paragraph(f"<i>{escape(t['note_metre'])}</i>", small)]
    # Mapa de materiais até aos parafusos: totais para encomenda + artigos não decompostos (com o que falta)
    from engines import mapa_materiais
    lg2 = _lang(lang)
    hm, est = _MAT[lg2], _ESTADO[lg2]
    from engines.mapa_materiais_i18n import traduzir
    mm_ = traduzir(mapa_materiais.mapa(rows), lg2)
    story += [PageBreak(), Paragraph(escape(hm[1]), h2), Paragraph(escape(mm_["aviso"]), small), Spacer(1, 3 * mm)]
    dm = [[hm[3], hm[4], hm[6], t["unit"], t["lines"]]]
    for m in mm_["totais"]:
        dm.append([Paragraph(escape(m["material"]), small), f"{m['quantidade_liquida']:,.2f}".replace(",", " "),
                   f"{m['quantidade_encomenda']:,.2f}".replace(",", " "), m["unidade"], str(m["artigos"])])
    if len(dm) == 1:
        dm.append([Paragraph("—", small), "", "", "", ""])
    tm = LongTable(dm, colWidths=[140 * mm, 32 * mm, 36 * mm, 18 * mm, 20 * mm], repeatRows=1)
    tm.setStyle(TableStyle(head_style + [("ALIGN", (1, 1), (-1, -1), "RIGHT")]))
    story += [tm]
    falt = [a for a in mm_["artigos"] if a["estado"] != "completo"]
    if falt:
        dn = [[hm[2], hm[10], hm[9]]]
        for a in falt:
            dn.append([Paragraph(escape(a["designacao"]), small), Paragraph(escape(est.get(a["estado"], a["estado"])), small),
                       Paragraph(escape(a.get("motivo") or ""), small)])
        tn = LongTable(dn, colWidths=[90 * mm, 45 * mm, 111 * mm], repeatRows=1)
        tn.setStyle(TableStyle(head_style))
        story += [Spacer(1, 5 * mm), Paragraph(escape(f"{hm[2]} — {hm[9]}"), h2), tn]
    pdf.build(story)
    raw = buf.getvalue()
    capa = {"tipo": titulo_tipo, "titulo": doc.get("title") or titulo_tipo, "subtitulo": _client(doc) or "",
            "local": "", "data": datetime.now(timezone.utc).date().isoformat(),
            "kpis": [(TT["lines"], str(len(rows)), ""), (TT["lots"], str(len(lots)), ""),
                     (t["to_confirm"], str(n_conf), "")],
            "indice": [t["summary"], titulo_tipo],
            "imagem": ((doc.get("_house_views") or {}).get("main"))}
    return PP.acabar(raw, capa, PP.com_cor(branding) if branding is not None else {}, lg, paginas="completo")


async def _context(doc, user):
    from routes.company_page import pdf_customization
    from routes.documents import _doc_lang
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(user["user_id"]) or {}
    try:
        branding = {**branding, **await pdf_customization(user["user_id"])}
    except Exception:  # noqa: BLE001 — personnalisation facultative
        pass
    lang = await _doc_lang(doc, branding)
    try:                                   # moradia lida nas plantas (Estudo BET): perspetivas 3D + paredes calculadas no PDF
        from engines import quote_building
        doc = await quote_building.enrich(db, doc, user["user_id"], wait=40)
    except Exception:  # noqa: BLE001 — facultativo
        pass
    acct_langs = [x for x in (user.get("doc_langs") or []) if x in ("fr", "pt", "en", "uk")]
    if acct_langs:
        lang = acct_langs[0]
        try:
            from engines.doc_translate import translate_doc
            doc = await translate_doc(db, doc, lang)
        except Exception:  # noqa: BLE001 — sans traduction, le contenu d'origine reste exploitable
            pass
    return doc, branding, lang


def _quote_pdf(doc, branding, lang):
    from engines.pdf_docs import build_document_pdf
    draft = {**doc, "number": None}          # jamais de numéro légal sur un brouillon
    return build_document_pdf(draft, branding=branding, lang=lang)


DEFAULT_COUNTRY = "PT"


async def _economic_builder(doc, uid):
    """Dossier económico do orçamento (custo com a biblioteca de compra e os recursos da empresa, venda, margem, cenários)."""
    from engines import economic_dossier as E
    purchase = await db.library_items.find({"user_id": uid, "cost_price_ht": {"$gt": 0}},
                                           {"_id": 0, "designation": 1, "unit": 1, "cost_price_ht": 1}).to_list(5000)
    saved = await db.company_cost_resources.find_one({"user_id": uid}, {"_id": 0})

    def build(src, branding, lang):
        from engines import economic_dossier_pdf
        # país = língua do ORÇAMENTO (obra), não o país da conta: um orçamento português de uma conta francesa saía com
        # recursos franceses («Maçon», encargos 15 %) — 13/11, Valpaços
        lg0 = str(lang or "").lower()
        country = "PT" if lg0.startswith("pt") else ("FR" if lg0.startswith("fr") else DEFAULT_COUNTRY)
        r = E.compute(src, E.merge(saved, country), purchase, country)
        lg = "pt" if str(lang or "").startswith("pt") else ("fr-FR" if str(lang or "").startswith("fr") else lang)
        return economic_dossier_pdf.build(r, branding or {}, lg)
    return build


async def attach_quote_exports(doc_id, user, conv) -> list[dict]:
    """Produit (ou retrouve) devis PDF/XLSX + métré PDF/XLSX pour la version courante du devis."""
    from engines.assistant_files import public_artifact
    uid = user["user_id"]
    doc = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": uid, "doc_type": "quote"}, {"_id": 0})
    if not doc or not _rows(doc):
        return []
    version = hashlib.sha256(f"{doc_id}|{doc.get('updated_at')}".encode()).hexdigest()[:20]
    kinds = ("quote_pdf", "quote_xlsx", "metre_pdf", "metre_xlsx", "economic_pdf")
    ids = {k: f"qx_{version}_{k}" for k in kinds}
    existing = {a["artifact_id"]: a async for a in db.assistant_artifacts.find(
        {"artifact_id": {"$in": list(ids.values())}, "user_id": uid}, {"_id": 0, "data_b64": 0, "body": 0})}
    if all(ids[k] in existing for k in kinds):
        return [public_artifact(existing[ids[k]]) for k in kinds]
    src, branding, lang = await _context(doc, user)
    try:
        economic = await _economic_builder(doc, uid)
    except Exception:  # noqa: BLE001 — sem dossier económico, os 4 ficheiros do orçamento saem na mesma
        import logging
        logging.getLogger(__name__).warning("economic dossier setup failed", exc_info=True)
        economic = None
    builders = {"quote_pdf": (_quote_pdf, "pdf"), "quote_xlsx": (build_quote_xlsx, "xlsx"),
                "metre_pdf": (build_metre_pdf, "pdf"), "metre_xlsx": (build_metre_xlsx, "xlsx"),
                "economic_pdf": (economic, "pdf")}
    t = L[_lang(lang)]
    out, now = [], datetime.now(timezone.utc).isoformat()
    for k in kinds:
        if ids[k] in existing:
            out.append(public_artifact(existing[ids[k]]))
            continue
        fn, ext = builders[k]
        if fn is None:
            continue
        try:
            data = await asyncio.to_thread(fn, src, branding, lang)
        except Exception:  # noqa: BLE001 — o dossier económico nunca impede os 4 ficheiros do orçamento
            if k != "economic_pdf":
                raise
            import logging
            logging.getLogger(__name__).warning("economic dossier export failed", exc_info=True)
            continue
        type_doc = t["quote"] if k.startswith("quote") else ("Dossier" if k == "economic_pdf" else t["takeoff"])
        art = {"artifact_id": ids[k], "user_id": uid, "conversation_id": conv["conversation_id"],
               "request_id": conv.get("_quote_request_id"), "title": t["file_" + k], "body": f"{type_doc} — {doc.get('title') or ''}",
               "filename": nom_document(type_doc, doc.get("title") or _client(doc), ext=ext), "format": ext,
               "mime": "application/pdf" if ext == "pdf" else XLSX_MIME, "size": len(data),
               "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": now,
               "illustrative": False, "quote_doc_id": doc_id, "quote_export": k,
               "download": f"/assistant/artifacts/{ids[k]}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": ids[k], "user_id": uid}, {"$setOnInsert": art}, upsert=True)
        out.append(public_artifact(art))
    return out


async def with_exports(result, user, conv):
    """Ajoute les 4 fichiers au résultat d'un outil devis ; une erreur d'export ne casse jamais le devis."""
    doc_id = (result or {}).get("doc_id")
    if not doc_id:
        return result
    try:
        files = await attach_quote_exports(doc_id, user, conv)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("quote exports failed for %s", doc_id)
        return {**result, "files_error": f"Fichiers PDF/Excel non générés : {type(exc).__name__}. Le devis est enregistré ; réessayer avec read_quote_draft."}
    if files:
        result = {**result, "artifacts": files,
                  "files_note": "Devis et métré fournis en PDF ET en Excel, plus le dossier économique (coût, vente, marge, bénéfice) : annonce TOUS les fichiers joints."}
    return result


async def study_exports(plan_id, user, conv, study) -> list[dict]:
    """Étude complète d'un permis : devis/métré sourcés en PDF et en Excel (les exports existants de l'étude)."""
    from engines.assistant_files import public_artifact
    from routes.plans_export import export_xlsx
    from routes.plans_pc import export_pc_pdf
    if not study or not study.get("items"):
        return []
    uid = user["user_id"]
    version = hashlib.sha256(f"{plan_id}|{study.get('generated_at') or study.get('updated_at') or len(study.get('items') or [])}|{(study.get('totals') or {})}".encode()).hexdigest()[:20]
    out, now = [], datetime.now(timezone.utc).isoformat()
    for kind, fn, ext, title in (("study_pdf", export_pc_pdf, "pdf", "Devis + métré de l'étude (PDF)"),
                                 ("study_xlsx", export_xlsx, "xlsx", "Devis + métré de l'étude (Excel)")):
        ident = f"sx_{version}_{kind}"
        old = await db.assistant_artifacts.find_one({"artifact_id": ident, "user_id": uid}, {"_id": 0, "data_b64": 0, "body": 0})
        if old:
            out.append(public_artifact(old))
            continue
        resp = await (fn(plan_id, None, user=user) if ext == "pdf" else fn(plan_id, user=user))
        data = bytes(resp.body)
        art = {"artifact_id": ident, "user_id": uid, "conversation_id": conv["conversation_id"], "request_id": conv.get("_quote_request_id"),
               "title": title, "body": title, "filename": nom_document("Etude", study.get("title") or plan_id, ext=ext), "format": ext,
               "mime": "application/pdf" if ext == "pdf" else XLSX_MIME, "size": len(data), "data_b64": base64.b64encode(data).decode(),
               "source_artifact_ids": [], "created_at": now, "illustrative": False, "plan_id": plan_id,
               "download": f"/assistant/artifacts/{ident}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": ident, "user_id": uid}, {"$setOnInsert": art}, upsert=True)
        out.append(public_artifact(art))
    return out
