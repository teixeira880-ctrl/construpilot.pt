"""Lot 84 — un plan A0 est rendu à taille utile (pas de pixmap géante) ; un A3 garde 200 dpi."""
import pymupdf

from engines import plan_processor as pp


def _pdf(w, h):
    d = pymupdf.open()
    p = d.new_page(width=w, height=h)
    p.draw_line((50, 50), (w - 50, h - 50))
    p.insert_text((100, 100), "PLAN COFFRAGE R+4  ech 1/50", fontsize=12)
    return d.tobytes()


def test_a0_page_rendered_at_useful_size(monkeypatch):
    seen = []
    orig = pymupdf.Page.get_pixmap

    def spy(self, *a, **k):
        pix = orig(self, *a, **k)
        seen.append((pix.width, pix.height))
        return pix
    monkeypatch.setattr(pymupdf.Page, "get_pixmap", spy)
    out = pp.process_pdf(_pdf(3370, 2591))
    assert max(seen[0]) <= 4200 * 1.25 + 2          # avant : 9 361 px
    page = out["pages"][0]
    assert max(page["width_px"], page["height_px"]) <= 4200
    # dpi effectif cohérent avec l'image servie
    assert abs(page["dpi"] - 72 * page["width_px"] / 3370) < 1.0


def test_a3_page_keeps_200_dpi():
    page = pp.process_pdf(_pdf(1190.55, 841.89))["pages"][0]
    assert abs(page["dpi"] - 200) < 1.0
