"""Upload de PDF fora da boucle (PyMuPDF) e rótulos de progresso nunca genéricos."""
import io
import time

from reportlab.pdfgen import canvas

from routes import assistant as A


def _pdf(n):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(n):
        c.drawString(50, 50, f"Planta do piso {i} — escala 1/100 " * 3)
        c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_texto_e_paginas_rapido():
    data = _pdf(60)
    t = time.time()
    text, pages = A._pdf_text_pages(data, 60)
    assert pages == 60 and "Planta do piso 59" in text
    assert time.time() - t < 3


def test_pdf_invalido_nao_rebenta():
    text, pages = A._pdf_text_pages(b"%PDF-1.4 lixo", 60)
    assert text == "" and pages >= 1


def test_rotulos_de_progresso():
    assert A.TOOL_STATUS_PT.get("generate_full_bet_study").startswith("Estudo BET")
    assert A.TOOL_STATUS_PT.get("read_document")                         # herdado de TOOL_STATUS
    assert A.TOOL_STATUS_PT.get("ferramenta_web_nova", "x") == "A pesquisar na Internet…"
    assert A.TOOL_STATUS_PT.get("zzz", "Processamento do processo…") == "A trabalhar no seu pedido…"
