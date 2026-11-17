"""PDF → PNG local (sans Autodesk) pour Análise de planta Pro."""
import pymupdf
import pytest

from plans_pro import routes


def _pdf(pages):
    doc = pymupdf.open()
    for n_lines in pages:
        page = doc.new_page(width=1684, height=1191)  # A2 paysage
        for i in range(n_lines):
            page.draw_line((50, 50 + i * 5), (1600, 50 + i * 5))
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_ne_requiert_plus_autodesk():
    assert routes._ACCEPT_MIME[".pdf"][1] is False


def test_pdf_rasterise_page_la_plus_chargee():
    png, meta = routes.pdf_to_png(_pdf([2, 150, 10]))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert meta["page_index"] == 1 and meta["page_count"] == 3
    assert max(meta["width_px"], meta["height_px"]) <= routes.PDF_MAX_SIDE_PX


def test_pdf_corrompu():
    with pytest.raises(ValueError):
        routes.pdf_to_png(b"%PDF-1.4 garbage")
