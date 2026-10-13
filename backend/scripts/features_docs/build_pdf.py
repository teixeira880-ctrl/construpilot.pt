"""Génère les PDF brochure + catalogue ConstruPilot (reportlab)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                PageBreak, Table, TableStyle, Image, KeepTogether, NextPageTemplate)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from content import BRAND, INTRO, TIERS, TRANSVERSAL, COMPARE, HIGHLIGHTS, CONTACT

FONT_DIR = "/usr/share/fonts/truetype/liberation"
pdfmetrics.registerFont(TTFont("DV", f"{FONT_DIR}/LiberationSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("DVB", f"{FONT_DIR}/LiberationSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("FS", "/usr/share/fonts/truetype/freefont/FreeSans.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DVB", italic="DV", boldItalic="DVB")

DARK, LIME, AMBER, SOFT, GREY, MID = (colors.HexColor(BRAND[k]) for k in ("dark", "lime", "amber", "soft", "grey", "mid"))
W, H = A4
M = 16 * mm

S = {
    "h1": ParagraphStyle("h1", fontName="DVB", fontSize=26, leading=31, textColor=DARK),
    "h2": ParagraphStyle("h2", fontName="DVB", fontSize=15, leading=19, textColor=DARK, spaceBefore=8, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName="DVB", fontSize=10.5, leading=13, textColor=MID, spaceBefore=6, spaceAfter=2),
    "body": ParagraphStyle("body", fontName="DV", fontSize=9.5, leading=13, textColor=colors.HexColor("#1f2a24")),
    "small": ParagraphStyle("small", fontName="DV", fontSize=8, leading=10.5, textColor=GREY),
    "bullet": ParagraphStyle("bullet", fontName="DV", fontSize=9, leading=12.2, leftIndent=9, bulletIndent=0,
                             textColor=colors.HexColor("#1f2a24"), spaceAfter=1.5),
    "big": ParagraphStyle("big", fontName="DVB", fontSize=11, leading=14, textColor=DARK),
    "white": ParagraphStyle("white", fontName="DV", fontSize=11, leading=15, textColor=colors.white),
    "whiteb": ParagraphStyle("whiteb", fontName="DVB", fontSize=34, leading=40, textColor=colors.white),
    "lime": ParagraphStyle("lime", fontName="DVB", fontSize=13, leading=17, textColor=LIME),
}


def _bullets(items):
    return [Paragraph(t, S["bullet"], bulletText="•") for t in items]


def _band(title, price, sub, pitch):
    tbl = Table([[Paragraph(f"<b>{title}</b>", ParagraphStyle("t", parent=S["whiteb"], fontSize=22, leading=26)),
                  Paragraph(price, ParagraphStyle("p", parent=S["lime"], fontSize=18, leading=22, alignment=2))],
                 [Paragraph(sub, S["white"]), ""],
                 [Paragraph(f"<i>{pitch}</i>", ParagraphStyle("pi", parent=S["white"], fontSize=10, textColor=SOFT)), ""]],
                colWidths=[(W - 2 * M) * 0.66, (W - 2 * M) * 0.34])
    tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), DARK), ("SPAN", (0, 1), (1, 1)), ("SPAN", (0, 2), (1, 2)),
                             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, 0), 12),
                             ("BOTTOMPADDING", (0, -1), (-1, -1), 12)]))
    return tbl


def _two_cols(flows_a, flows_b):
    cw = (W - 2 * M - 6 * mm) / 2
    t = Table([[flows_a, flows_b]], colWidths=[cw, cw])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (0, 0), 6 * mm), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    return t


def _split_sections(sections, big=False):
    a, b, la, lb = [], [], 0, 0
    bs = ParagraphStyle("bb", parent=S["bullet"], fontSize=10.5, leading=14.5, spaceAfter=3) if big else S["bullet"]
    hs = ParagraphStyle("hb", parent=S["h3"], fontSize=12.5, leading=16, spaceBefore=10) if big else S["h3"]
    for title, items in sections:
        flow = [Paragraph(title, hs)] + [Paragraph(t, bs, bulletText="•") for t in items]
        n = sum(len(i) for i in items) + 60
        if la <= lb:
            a += flow; la += n
        else:
            b += flow; lb += n
    return a, b


def _cover(c, d, subtitle):
    c.saveState()
    c.setFillColor(DARK); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(LIME); c.rect(0, H * 0.42, W, 3, fill=1, stroke=0)
    c.setFillColor(MID); c.circle(W * 0.85, H * 0.88, 70 * mm, fill=1, stroke=0)
    if os.path.exists(BRAND["logo"]):
        c.drawImage(BRAND["logo"], M, H - 40 * mm - M, width=60 * mm, height=40 * mm, mask="auto", preserveAspectRatio=True, anchor="sw")
    c.setFillColor(colors.white); c.setFont("DVB", 36)
    c.drawString(M, H * 0.48 + 22 * mm, BRAND["name"])
    c.setFont("DV", 15); c.setFillColor(LIME)
    c.drawString(M, H * 0.48 + 12 * mm, BRAND["tagline"])
    c.setFont("DVB", 20); c.setFillColor(colors.white)
    c.drawString(M, H * 0.42 - 14 * mm, subtitle)
    c.setFont("DV", 11); c.setFillColor(SOFT)
    for i, line in enumerate(["Particuliers · Project Pass · Premium · Pro · Pro Business",
                              "Blog & SEO · Radar Chantiers & prospection · API · Administration",
                              "Édition juin 2026 — document en français"]):
        c.drawString(M, H * 0.42 - 26 * mm - i * 6.5 * mm, line)
    c.setFont("DV", 9); c.setFillColor(GREY)
    c.drawString(M, 14 * mm, BRAND["site"])
    c.restoreState()


def _page(c, d):
    c.saveState()
    c.setFillColor(DARK); c.rect(0, H - 6 * mm, W, 6 * mm, fill=1, stroke=0)
    c.setFillColor(LIME); c.rect(0, H - 6 * mm, 40 * mm, 6 * mm, fill=1, stroke=0)
    c.setFont("DV", 8); c.setFillColor(GREY)
    c.drawString(M, 9 * mm, f"{BRAND['name']} — {BRAND['tagline']}")
    c.drawRightString(W - M, 9 * mm, f"{BRAND['site']}  ·  page {d.page}")
    c.restoreState()


def _doc(path, subtitle):
    doc = BaseDocTemplate(path, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=M + 4 * mm, bottomMargin=M,
                          title=f"{BRAND['name']} — Fonctionnalités", author=BRAND["name"])
    frame = Frame(M, M, W - 2 * M, H - 2 * M - 4 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=lambda c, d: _cover(c, d, subtitle)),
                          PageTemplate(id="page", frames=[frame], onPage=_page)])
    return doc


def _compare_table():
    head = ["Fonction", "Particuliers", "Premium", "Pro", "Pro Business"]
    cell = ParagraphStyle("c", parent=S["body"], fontSize=8.2, leading=10)
    rows = [[Paragraph(f"<b>{h}</b>", ParagraphStyle("hh", parent=cell, textColor=colors.white)) for h in head]]
    for r in COMPARE:
        rows.append([Paragraph(r[0], cell)] + [Paragraph(x, ParagraphStyle("cc", parent=cell, alignment=1, fontName="FS")) for x in r[1:]])
    cw = W - 2 * M
    t = Table(rows, colWidths=[cw * 0.4] + [cw * 0.15] * 4, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), DARK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5e3da")), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            st.append(("BACKGROUND", (0, i), (-1, i), SOFT))
    t.setStyle(TableStyle(st))
    return t


def _closing():
    return [Paragraph("Pour aller plus loin", S["h2"]), Spacer(1, 4)] + _bullets(CONTACT)


def build_brochure(path):
    doc = _doc(path, "Toutes les fonctionnalités — brochure")
    st = [NextPageTemplate("page"), PageBreak()]
    st += [Paragraph("Pourquoi ConstruPilot ?", S["h1"]), Spacer(1, 6), Paragraph(INTRO, S["body"]), Spacer(1, 10)]
    cards = []
    for tr in TIERS:
        cards.append([Paragraph(f"<b>{tr['name']}</b>", S["big"]), Paragraph(tr["price"], ParagraphStyle("pp", parent=S["h3"], textColor=AMBER)),
                      Paragraph(tr["audience"], S["small"])])
    t = Table([cards], colWidths=[(W - 2 * M) / 5] * 5)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d5e3da")), ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#d5e3da")),
                           ("BACKGROUND", (0, 0), (-1, -1), SOFT), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    st += [t, Spacer(1, 12), Paragraph("Ce que vous trouverez dans cette brochure", S["h2"])]
    st += _bullets(["Une page par offre : Particuliers, Project Pass, Premium, Pro, Pro Business",
                    "Les modules transversaux : Radar Chantiers & prospection, Blog / SEO / newsletter, acquisition, options & API, administration",
                    "Un tableau comparatif complet des fonctions par offre"])
    for tr in TIERS:
        st += [PageBreak(), _band(tr["name"], tr["price"], tr["sub"], tr["pitch"]), Spacer(1, 10),
               Paragraph("L'essentiel", S["h2"])]
        st += [Paragraph(h, ParagraphStyle("hl", parent=S["bullet"], fontSize=10.5, leading=15, spaceAfter=4), bulletText="•") for h in HIGHLIGHTS[tr["key"]]]
        st += [PageBreak()] if len(tr["sections"]) > 4 else [Spacer(1, 8)]
        st += [Paragraph(f"{tr['name']} — dans le détail", S["h2"])]
        a, b = _split_sections(tr["sections"])
        st += [_two_cols(a, b)]
    for tv in TRANSVERSAL:
        st += [PageBreak(), _band(tv["name"], "", "", tv["pitch"]), Spacer(1, 10)]
        a, b = _split_sections(tv["sections"], big=True)
        st += [_two_cols(a, b)]
    st += [PageBreak(), Paragraph("Comparatif des offres", S["h1"]), Spacer(1, 8), _compare_table(), Spacer(1, 12)] + _closing()
    doc.build(st)


def build_catalogue(path):
    doc = _doc(path, "Catalogue exhaustif des fonctionnalités")
    st = [NextPageTemplate("page"), PageBreak(), Paragraph("Catalogue exhaustif des fonctionnalités", S["h1"]), Spacer(1, 6),
          Paragraph(INTRO, S["body"]), Spacer(1, 8),
          Paragraph("Ce catalogue liste, module par module, l'intégralité des fonctions disponibles dans ConstruPilot, "
                    "classées par offre puis par module transversal. Chaque fonction est numérotée pour faciliter les références.", S["body"]),
          Spacer(1, 10), Paragraph("Sommaire", S["h2"])]
    n = 1
    toc = []
    for tr in TIERS:
        toc.append(f"{n}. {tr['name']} — {tr['price']}"); n += 1
    for tv in TRANSVERSAL:
        toc.append(f"{n}. {tv['name']}"); n += 1
    toc.append(f"{n}. Comparatif des offres")
    st += _bullets(toc)
    num = 1
    for tr in TIERS:
        st += [PageBreak(), Paragraph(f"{num}. {tr['name']}", S["h1"]),
               Paragraph(f"{tr['price']} — {tr['sub']}", ParagraphStyle("ps", parent=S["h3"], textColor=AMBER)),
               Paragraph(f"Public : {tr['audience']}. {tr['pitch']}", S["body"]), Spacer(1, 6)]
        for si, (title, items) in enumerate(tr["sections"], 1):
            block = [Paragraph(f"{num}.{si} {title}", S["h2"])]
            block += [Paragraph(f"<b>{num}.{si}.{k}</b> — {it}", S["bullet"]) for k, it in enumerate(items, 1)]
            st.append(KeepTogether(block))
        num += 1
    for tv in TRANSVERSAL:
        st += [PageBreak(), Paragraph(f"{num}. {tv['name']}", S["h1"]), Paragraph(tv["pitch"], S["body"]), Spacer(1, 6)]
        for si, (title, items) in enumerate(tv["sections"], 1):
            block = [Paragraph(f"{num}.{si} {title}", S["h2"])]
            block += [Paragraph(f"<b>{num}.{si}.{k}</b> — {it}", S["bullet"]) for k, it in enumerate(items, 1)]
            st.append(KeepTogether(block))
        num += 1
    st += [PageBreak(), Paragraph(f"{num}. Comparatif des offres", S["h1"]), Spacer(1, 8), _compare_table(), Spacer(1, 12)] + _closing()
    doc.build(st)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/app/frontend/public/docs"
    os.makedirs(out, exist_ok=True)
    build_brochure(f"{out}/ConstruPilot_Brochure_Fonctionnalites.pdf")
    build_catalogue(f"{out}/ConstruPilot_Catalogue_Complet.pdf")
    print("ok")
