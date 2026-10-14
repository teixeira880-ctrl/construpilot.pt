"""Guia PEPU — Plataforma Eletrónica dos Procedimentos Urbanísticos (Lote N4).

Gerado em runtime com reportlab (ficheiro estático curto, cerca de 2 páginas A4).
"""
from __future__ import annotations

import io
from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

SECCOES: List[dict] = [
    {"titulo": "1. O que é a PEPU",
     "texto": "A Plataforma Eletrónica dos Procedimentos Urbanísticos (PEPU) é o portal nacional de "
              "submissão dos processos de licenciamento e comunicação prévia em Portugal, previsto no "
              "RJUE (DL 555/99). A submissão é obrigatoriamente eletrónica."},
    {"titulo": "2. Antes de submeter",
     "texto": "Confirme no site da câmara municipal do concelho se a PEPU está ativa — alguns municípios "
              "usam ainda o seu balcão único eletrónico. Reúna o requerente (NIF, morada), o terreno (artigo "
              "matricial e descrição predial), e todos os projetos e termos de responsabilidade subscritos."},
    {"titulo": "3. Documentos a anexar",
     "texto": "Requerimento, memória descritiva e justificativa, projeto de arquitetura, projetos de "
              "especialidades aplicáveis (estabilidade, redes, SCIE, acústica, térmico), termos de "
              "responsabilidade (art.º 10.º do RJUE), levantamento topográfico, planta de localização e de "
              "implantação, ficha de elementos estatísticos (INE) e estimativa orçamental."},
    {"titulo": "4. Prazos indicativos",
     "texto": "Comunicação prévia: resposta em cerca de 20 dias úteis. Licenciamento: pode ultrapassar 2 "
              "meses dependendo das consultas externas e das correções solicitadas. Confirme os prazos no "
              "regulamento municipal do seu concelho."},
    {"titulo": "5. Taxas",
     "texto": "As taxas urbanísticas são municipais e variam por concelho (valores por m² de construção, "
              "por fogo, por ocupação de espaço público, etc.). Consulte a tabela de taxas em vigor na "
              "câmara municipal."},
    {"titulo": "6. Avisos legais",
     "texto": "Este guia é informativo e meramente indicativo. A responsabilidade legal do processo é "
              "do requerente e dos técnicos subscritores. A submissão oficial é feita exclusivamente "
              "através da PEPU ou do balcão único eletrónico do município."},
]


def _footer(c: rl_canvas.Canvas, doc) -> None:
    c.saveState()
    c.setFont("Helvetica", 7); c.setFillGray(0.45)
    c.drawString(15 * mm, 10 * mm, "ConstruPilot · Guia PEPU · Documento informativo")
    c.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Pág. {c.getPageNumber()}")
    c.restoreState()


def gerar_guia_pepu_pdf() -> bytes:
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                                 fontSize=18, leading=22, alignment=1, spaceAfter=12),
        "sub": ParagraphStyle("s", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=10, leading=13, textColor=colors.grey, alignment=1),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                              fontSize=12, leading=15, spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontName="Helvetica",
                                fontSize=10, leading=14, alignment=4),
    }
    story = [
        Paragraph("GUIA DE SUBMISSÃO — PEPU", styles["title"]),
        Paragraph("Como submeter o seu processo de autorização de obras em Portugal", styles["sub"]),
        Spacer(1, 6 * mm),
    ]
    for s in SECCOES:
        story.append(Paragraph(s["titulo"], styles["h2"]))
        story.append(Paragraph(s["texto"], styles["body"]))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Guia PEPU",
                             leftMargin=18 * mm, rightMargin=18 * mm,
                             topMargin=18 * mm, bottomMargin=18 * mm)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
