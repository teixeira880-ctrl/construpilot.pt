"""Acabamento premium (capa, índice, marca) dos orçamentos e medições — todas as contas, não só CLT Rezult."""
import base64
import io

import pymupdf
from PIL import Image

from engines import pdf_premium
from engines.pdf_docs import build_document_pdf
from engines.pdf_takeoff import build_quote_pdf, build_takeoff_pdf


def _logo():
    b = io.BytesIO()
    Image.new("RGB", (300, 100), (30, 64, 175)).save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


BR = {"company_name": "Empresa Teste", "logo_b64": _logo(), "accent_color": "#1E40AF", "country": "PT"}


def _doc(kind="quote"):
    lines = [{"kind": "section", "title": "Alvenarias"},
             {"designation": "Parede tijolo 15", "unit": "m²", "qty": 10, "unit_price_ht": 30, "vat_rate": 23},
             {"kind": "section", "title": "Pavimentos"},
             {"designation": "Cerâmico", "unit": "m²", "qty": 20, "unit_price_ht": 40, "vat_rate": 23}]
    return {"doc_type": kind, "number": "ORC-1", "title": "Remodelação T2", "issue_date": "2026-11-11", "validity_days": 30,
            "client": {"name": "Cliente X"}, "lines": lines, "totals": {"ht": 1100, "tva_breakdown": {"23": 253}, "ttc": 1353}}


def test_quote_gets_cover_kpis_and_index():
    d = pymupdf.open(stream=build_document_pdf(_doc(), branding=BR, lang="pt"), filetype="pdf")
    cover = d[0].get_text()
    assert "Total c/ IVA" in cover and "Índice" in cover and "Empresa Teste" in cover and "Alvenarias" in cover
    assert d.metadata["title"] == "Remodelação T2"
    assert [t[1] for t in d.get_toc()][:2] == ["Capa", "Alvenarias"]


def test_invoice_untouched():
    d = pymupdf.open(stream=build_document_pdf(_doc("invoice"), branding=BR, lang="pt"), filetype="pdf")
    assert "Índice" not in d[0].get_text()


def test_french_labels_and_opt_out():
    d = pymupdf.open(stream=build_document_pdf(_doc(), branding=dict(BR, country="FR"), lang="fr-FR"), filetype="pdf")
    assert "Total TTC" in d[0].get_text() and "Sommaire" in d[0].get_text()
    off = pymupdf.open(stream=build_document_pdf(_doc(), branding=dict(BR, premium_pdf=False), lang="pt"), filetype="pdf")
    assert "Índice" not in off[0].get_text()


def test_takeoff_and_estimate_get_cover():
    tk = {"totals": {"floor_m2": 85, "walls_net_m2": 190, "perimeter_m": 96}, "rooms": [{"name": "Sala", "surface_m2": 30}],
          "room_count": 1, "levels": []}
    d = pymupdf.open(stream=build_takeoff_pdf({"plan_id": "p", "filename": "Moradia"}, tk, None, branding=BR), filetype="pdf")
    assert "MEDIÇÃO" in d[0].get_text() and "Pavimento" in d[0].get_text() and "p. 2 / 2" in d[1].get_text()
    q = {"filename": "Moradia", "line_items": [{"name": "Pintura", "quantity": 10, "unit": "m²", "material_total": 50,
                                                 "labour_total": 70, "total": 120}],
         "totals": {"floor_m2": 85}, "subtotal_ht": 120, "total_ttc": 147.6, "subtotal_material": 50, "subtotal_labour": 70}
    d2 = pymupdf.open(stream=build_quote_pdf(q, branding=BR), filetype="pdf")
    assert "Mão de obra" in d2[0].get_text()


def test_finishing_never_breaks_document():
    assert pdf_premium.acabar(b"not a pdf", {"titulo": "x"}, BR) == b"not a pdf"


def _logo_cor(rgb):
    b = io.BytesIO()
    im = Image.new("RGBA", (300, 100), (255, 255, 255, 0))
    im.paste(Image.new("RGBA", (120, 80), rgb + (255,)), (10, 10))
    im.save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


def test_company_colour_chosen_then_logo_then_default():
    assert pdf_premium.cor_empresa({"accent_color": "#e21411"}) == "#E21411"
    c = pdf_premium.cor_empresa({"logo_b64": _logo_cor((200, 30, 40))})
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    assert r > 150 and g < 80 and b < 80                     # vermelho do logótipo
    assert pdf_premium.cor_empresa({"logo_b64": _logo_cor((0, 0, 0))}) == pdf_premium.COR_PADRAO   # logótipo preto
    assert pdf_premium.cor_empresa({}) == pdf_premium.COR_PADRAO


def test_quote_uses_logo_colour_everywhere_when_no_colour_chosen():
    br = {"company_name": "Vermelha", "logo_b64": _logo_cor((200, 30, 40)), "country": "PT"}
    d = pymupdf.open(stream=build_document_pdf(_doc(), branding=br, lang="pt"), filetype="pdf")
    pix = d[0].get_pixmap(dpi=40)
    y = int(300 / 841.89 * pix.height)                       # filete da cor da empresa sob a faixa escura
    r, g, b = pix.pixel(pix.width // 2, y)[:3]
    assert r > 150 and g < 90 and b < 90


def test_metre_pdf_is_premium_with_company_colour():
    import pymupdf
    from engines.assistant_quote_exports import build_metre_pdf
    doc = {"title": "Moradia T4", "client": {"name": "Ana"},
           "lines": [{"category": "LOT 01", "designation": "Estaleiro", "qty": 1, "unit": "vg"},
                     {"category": "LOT 02", "designation": "Enrocamento", "quantity_missing": True, "unit": "m³"}]}
    d = pymupdf.open(stream=build_metre_pdf(doc, {"company_name": "CM RENOV", "accent_color": "#C2410C"}, "pt"), filetype="pdf")
    txt = "".join(p.get_text() for p in d)
    assert len(d) >= 3 and "CM RENOV" in txt and "Resumo por capítulo" in txt and "Quantidade a confirmar" in txt
    assert [t[1] for t in d.get_toc()][:2] == ["Capa", "Resumo por capítulo"]
