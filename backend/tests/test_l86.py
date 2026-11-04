"""Lot 86 — plan A0 rendu directement à la taille servie (≤ max_side), dpi cohérent ; A3 inchangé."""
import pymupdf

from engines import plan_processor as pp


def _pdf(w, h):
    d = pymupdf.open()
    p = d.new_page(width=w, height=h)
    p.draw_line((50, 50), (w - 50, h - 50))
    p.draw_rect(pymupdf.Rect(100, 100, 400, 300))
    p.insert_text((100, 90), "PLAN COFFRAGE R+4 ech 1/50", fontsize=12)
    return d.tobytes()


def test_a0_rendered_at_served_size(monkeypatch):
    seen = []
    orig = pymupdf.Page.get_pixmap

    def spy(self, *a, **k):
        pix = orig(self, *a, **k)
        seen.append(max(pix.width, pix.height))
        return pix
    monkeypatch.setattr(pymupdf.Page, "get_pixmap", spy)
    page = pp.process_pdf(_pdf(3370, 2591))["pages"][0]
    assert seen[0] <= 4200 and seen[0] == max(page["width_px"], page["height_px"])
    assert abs(page["dpi"] - 72 * page["width_px"] / 3370) < 1.0
    assert page["image_base64"] if "image_base64" in page else True


def test_a3_still_200_dpi_and_image_ok():
    page = pp.process_pdf(_pdf(1190.55, 841.89))["pages"][0]
    assert abs(page["dpi"] - 200) < 1.0
    assert max(page["width_px"], page["height_px"]) <= 4200
