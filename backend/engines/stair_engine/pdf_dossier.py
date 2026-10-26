"""PDF dossier técnico Stair Engine via ReportLab.

Secções:
  1. Cabeçalho com logo + dados projeto
  2. Dados de entrada
  3. Dimensionamento (tabela + fórmula Blondel)
  4. Verificações normativas (tabela colorida)
  5. Alertas
  6. Recomendações IA (se presente)
  7. Diagramas SVG convertidos a imagens
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    PageBreak,
)

PRIMARY = colors.HexColor("#0F766E")
BG = colors.HexColor("#E6F7F3")
BORDER = colors.HexColor("#CBD5E1")
WARN = colors.HexColor("#F59E0B")
FAIL = colors.HexColor("#EF4444")
OK = colors.HexColor("#059669")

STATE_COLOR = {"conforme": OK, "atencao": WARN, "nao_conforme": FAIL}
STATE_LABEL = {"conforme": "✓ Conforme", "atencao": "⚠ Atenção", "nao_conforme": "✗ Não conforme"}


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=22,
                                textColor=PRIMARY, spaceAfter=4, alignment=0),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=9,
                              textColor=colors.HexColor("#64748B")),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=14,
                             textColor=PRIMARY, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10,
                               leading=14),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=8,
                                textColor=colors.HexColor("#64748B")),
    }


def _header_table(plan_name: str, numero: str, data: str) -> Table:
    t = Table([
        ["ConstruPilot — Dossier técnico de escada", ""],
        [f"Projeto: {plan_name}", f"Nº {numero}  ·  {data}"],
    ], colWidths=[13 * cm, 5 * cm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (0, 0), "Helvetica-Bold", 14),
        ("TEXTCOLOR", (0, 0), (0, 0), PRIMARY),
        ("FONT", (0, 1), (-1, 1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#64748B")),
        ("ALIGN", (1, 1), (1, 1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, 1), 1, PRIMARY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _inputs_table(inputs: dict) -> Table:
    uso_label = {"habitacao": "Habitação", "comercio": "Comércio",
                 "evacuacao": "Via de evacuação", "publico": "Público"}.get(inputs["uso"], inputs["uso"])
    mat_label = {"betao": "Betão armado", "madeira": "Madeira", "metal": "Metal"}.get(inputs["material"], inputs["material"])
    rows = [
        ["Parâmetro", "Valor"],
        ["Altura total a vencer", f"{inputs['altura_total_m']:.2f} m"],
        ["Pé-direito sob a escada", f"{inputs['pe_direito_m']:.2f} m"],
        ["Largura da escada", f"{inputs['largura_m']:.2f} m"],
        ["Nº de degraus", str(inputs["num_degraus"])],
        ["Uso previsto", uso_label],
        ["Material", mat_label],
        ["Acessibilidade (DL 163/2006)", "Sim" if inputs.get("acessibilidade") else "Não"],
    ]
    if inputs.get("capacidade"):
        rows.append(["Capacidade (pessoas)", str(inputs["capacidade"])])
    t = Table(rows, colWidths=[8 * cm, 10 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _dim_table(dim: dict) -> Table:
    rows = [
        ["Dimensão", "Valor"],
        ["Altura do espelho (h)", f"{dim['altura_degrau_cm']:.1f} cm"],
        ["Profundidade do cobertor (g)", f"{dim['profundidade_cobertor_cm']:.1f} cm"],
        ["Blondel (2h + g)", f"{dim['blondel']:.1f} cm (60–64 cm = conforto)"],
        ["Inclinação", f"{dim['inclinacao_graus']:.1f}°"],
        ["Projeção horizontal", f"{dim['projecao_horizontal_m']:.2f} m"],
        ["Comprimento do rampante", f"{dim['comprimento_rampante_m']:.2f} m"],
    ]
    t = Table(rows, colWidths=[8 * cm, 10 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
    ]))
    return t


def _verifs_table(verifs: list[dict]) -> Table:
    rows = [["Norma", "Estado", "Mensagem", "Referência"]]
    for v in verifs:
        rows.append([v["norma"], STATE_LABEL.get(v["estado"], v["estado"]),
                     v["mensagem"], v["referencia"]])
    t = Table(rows, colWidths=[2.5 * cm, 2.4 * cm, 10.5 * cm, 3 * cm])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, v in enumerate(verifs, start=1):
        color = STATE_COLOR.get(v["estado"], colors.grey)
        style_cmds.append(("TEXTCOLOR", (1, i), (1, i), color))
        style_cmds.append(("FONT", (1, i), (1, i), "Helvetica-Bold", 9))
    t.setStyle(TableStyle(style_cmds))
    return t


def build_pdf(result: dict, *, project_name: str = "Projeto",
              ia_text: str | None = None,
              branding: dict | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title="ConstruPilot — Processo da escada",
    )
    styles = _styles()
    story: list = []

    numero = f"ESC-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
    data_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    emp = (branding or {}).get("brand_company_name") or "ConstruPilot"

    story.append(_header_table(project_name, numero, data_str))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(f"Empresa: {emp}", styles["sub"]))
    if branding and branding.get("brand_nif"):
        story.append(Paragraph(f"NIF: {branding['brand_nif']}", styles["sub"]))

    story.append(Paragraph("1. Dados de entrada", styles["h2"]))
    story.append(_inputs_table(result["inputs"]))

    story.append(Paragraph("2. Dimensionamento (fórmula Blondel)", styles["h2"]))
    story.append(_dim_table(result["dimensoes"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "A fórmula de Blondel <b>2h + g</b> ∈ [60; 64] cm garante um passo "
        "humano ergonómico. Ideal próximo de 63 cm. "
        f"Conforto estimado: <b>{result['conforto_score']}/10</b>.",
        styles["body"]))

    story.append(Paragraph("3. Verificações normativas PT", styles["h2"]))
    sumr = result["resumo_verificacoes"]
    story.append(Paragraph(
        f"<b>{sumr['conforme']}</b> conforme · <b>{sumr['atencao']}</b> atenção · "
        f"<b>{sumr['nao_conforme']}</b> não conforme (de {sumr['total']} verificações).",
        styles["body"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_verifs_table(result["verificacoes"]))

    if result.get("alertas"):
        story.append(Paragraph("4. Alertas", styles["h2"]))
        for a in result["alertas"]:
            story.append(Paragraph(f"• {a}", styles["body"]))

    if result.get("patamares"):
        story.append(Paragraph("5. Recomendações estruturais", styles["h2"]))
        for p in result["patamares"]:
            story.append(Paragraph(f"• {p}", styles["body"]))

    if ia_text:
        story.append(Paragraph("6. Análise IA (Opus 5.5)", styles["h2"]))
        for p in str(ia_text).split("\n"):
            if p.strip():
                story.append(Paragraph(p.strip(), styles["body"]))

    story.append(PageBreak())
    story.append(Paragraph("Referências normativas", styles["h2"]))
    refs = [
        "RGEU — Regulamento Geral das Edificações Urbanas (DL 38 382/51, consolidado).",
        "REH — Regulamento das Edificações Habitação (DL 101-D/2020).",
        "RSCIE — DL 220/2008 + Portaria 1532/2008 (Regime jurídico da segurança contra incêndio em edifícios).",
        "DL 163/2006 — Acessibilidade a pessoas com mobilidade condicionada.",
        "EN 1991-1-1 — Eurocódigo 1, Ações em estruturas (Anexo A).",
        "EN 1992-1-1 — Eurocódigo 2, Projeto de estruturas de betão (§4.4.1, §9.3.1.1, §9.10).",
    ]
    for r in refs:
        story.append(Paragraph(f"• {r}", styles["body"]))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Documento gerado automaticamente pelo ConstruPilot. "
        "As recomendações têm carácter informativo e não substituem o projeto de "
        "especialidade assinado por técnico competente.",
        styles["small"]))

    doc.build(story)
    return buf.getvalue()
