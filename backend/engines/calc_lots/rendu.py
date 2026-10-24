"""(Versão PT) Note de calcul PDF commune à tous les moteurs de lots (isolation, déperditions, PAC, plancher chauffant, plomberie, électricité).

Une note = titre + sections (texte, tableau, contrôles conformes / non conformes, figure). Rendu reportlab vectoriel, police Vera
(accents FR/PT) livrée avec reportlab ; PNG de la première page via PyMuPDF pour l'aperçu dans l'Assistant.
"""
from __future__ import annotations

import io
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle

from ..identidade_pt import COBALTO_NOITE as _CN, faixa_azulejo as _faixa
VERT, OCRE, GRIS, ROUGE = _CN, colors.HexColor("#8a6d00"), colors.HexColor("#555555"), colors.HexColor("#b3261e")
OK_BG, KO_BG, NA_BG = colors.HexColor("#e5f3ea"), colors.HexColor("#fbe4e2"), colors.HexColor("#f2f2f2")


_UNICODE = {"ok": False}
_ASCII = {"λ": "lambda ", "ψ": "psi ", "Ψ": "Psi ", "Δ": "delta ", "→": "->", "●": "o", "χ": "chi ", "μ": "mu ", "φ": "phi ", "θ": "theta ",
          "η": "eta ", "ρ": "rho ", "Σ": "soma ", "σ": "sigma "}
_DEJAVU = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF")


def fonts():
    """DejaVu Sans si présente (grec, flèches), sinon Vera livrée avec reportlab (les symboles grecs sont alors écrits en toutes lettres)."""
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "CP" in pdfmetrics.getRegisteredFontNames():
        return
    for d in _DEJAVU:
        files = [os.path.join(d, f) for f in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf")]
        if all(os.path.exists(f) for f in files):
            for name, f in zip(("CP", "CP-Bold", "CP-Oblique"), files):
                pdfmetrics.registerFont(TTFont(name, f))
            _UNICODE["ok"] = True
            return
    d = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    for name, f in (("CP", "Vera.ttf"), ("CP-Bold", "VeraBd.ttf"), ("CP-Oblique", "VeraIt.ttf")):
        pdfmetrics.registerFont(TTFont(name, os.path.join(d, f)))


def txt(s) -> str:
    """Texte affichable avec la police chargée."""
    s = str(s)
    if _UNICODE["ok"]:
        return s
    for k, v in _ASCII.items():
        s = s.replace(k, v)
    return s


LANG = {"note": "Nota de cálculo", "page": "página", "ref": "Ref.", "synthese": "Síntese das verificações", "conformes": "conformes",
        "non_conformes": "não conformes", "a_verifier": "a verificar", "verdict_ok": "CONFORME", "verdict_ko": "NÃO CONFORME",
        "verdict_na": "A VERIFICAR", "verdict_glob_ok": "Todas as verificações calculadas estão conformes",
        "verdict_glob_ko": "Pelo menos uma verificação não está conforme", "verdict_glob_na": "Nenhuma não conformidade — pontos a verificar",
        "head": ["Referência", "Exigência", "Valor", "Resultado"], "hyp": "Hipóteses / a validar",
        "brand_sub": "Gabinete de projeto digital"}
CLAIR, ACCENT, AMBRE_BG, OK_C, KO_C, NA_C = (colors.HexColor("#d2e3e6"), colors.HexColor("#1c5778"), colors.HexColor("#fff7e0"),
                                           colors.HexColor("#1f8a52"), colors.HexColor("#c8453c"), colors.HexColor("#c98500"))


def styles():
    fonts()
    return {
        "h1": ParagraphStyle("h1", fontName="CP-Bold", fontSize=15, leading=18.5, textColor=colors.white),
        "sub": ParagraphStyle("sub", fontName="CP", fontSize=8.3, leading=10.8, textColor=CLAIR),
        "h2": ParagraphStyle("h2", fontName="CP-Bold", fontSize=10.5, leading=13, textColor=VERT),
        "p": ParagraphStyle("p", fontName="CP", fontSize=8, leading=10.8, alignment=TA_LEFT, spaceAfter=2),
        "small": ParagraphStyle("small", fontName="CP", fontSize=7, leading=9, textColor=GRIS),
        "hyp": ParagraphStyle("hyp", fontName="CP", fontSize=7.4, leading=9.8, textColor=colors.HexColor("#5c4a00"), leftIndent=8, bulletIndent=0),
        "cell": ParagraphStyle("cell", fontName="CP", fontSize=7.3, leading=9),
        "cellb": ParagraphStyle("cellb", fontName="CP-Bold", fontSize=7.3, leading=9, textColor=colors.white),
        "res": ParagraphStyle("res", fontName="CP-Bold", fontSize=6.8, leading=8.5, textColor=colors.white, alignment=1),
        "kv": ParagraphStyle("kv", fontName="CP-Bold", fontSize=13, leading=15, textColor=VERT),
        "kl": ParagraphStyle("kl", fontName="CP", fontSize=6.6, leading=8.2, textColor=GRIS),
        "cap": ParagraphStyle("cap", fontName="CP-Oblique", fontSize=6.6, leading=8.5, textColor=GRIS, spaceBefore=1, spaceAfter=4),
    }


def _esc(t):
    return txt(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(head, rows, widths=None, st=None):
    st = st or styles()
    data = [[Paragraph(_esc(h), st["cellb"]) for h in head]] + [[Paragraph(_esc(c), st["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), VERT), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dcdcd6")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7f6")]),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _res(ok):
    return (LANG["verdict_ok"], OK_C) if ok is True else ((LANG["verdict_ko"], KO_C) if ok is False else (LANG["verdict_na"], NA_C))


def controls_table(ctl, st=None):
    """Tableau des contrôles : pastille pleine conforme (vert) / non conforme (rouge) / à vérifier (ambre), toujours avec le libellé."""
    st = st or styles()
    rows, sty = [], []
    for i, c in enumerate(ctl, 1):
        lab, col = _res(c.get("ok"))
        txt_ = c.get("exigence", "") + (f" — {c['note']}" if c.get("note") else "")
        rows.append([c.get("ref", ""), txt_, c.get("valeur", ""), lab])
        sty += [("BACKGROUND", (3, i), (3, i), col), ("LINEBEFORE", (0, i), (0, i), 2.2, col)]
    data = [[Paragraph(_esc(h), st["cellb"]) for h in LANG["head"]]] + \
        [[Paragraph(_esc(r[0]), st["cell"]), Paragraph(_esc(r[1]), st["cell"]), Paragraph(_esc(r[2]), st["cell"]), Paragraph(_esc(r[3]), st["res"])] for r in rows]
    t = Table(data, colWidths=[46 * mm, 72 * mm, 36 * mm, 26 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), VERT), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dcdcd6")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7f6")]),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)] + sty))
    return t


def _h2(text, st):
    t = Table([["", Paragraph(_esc(text), st["h2"])]], colWidths=[1.6 * mm, 178.4 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), ACCENT), ("LEFTPADDING", (1, 0), (1, 0), 6), ("LEFTPADDING", (0, 0), (0, 0), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    t.keepWithNext = True
    s1, s2 = Spacer(1, 3.5 * mm), Spacer(1, 2 * mm)
    s1.keepWithNext = s2.keepWithNext = True
    return [s1, t, s2]


def kpis(items, st=None, per_row=4):
    """Tuiles d'indicateurs : items = [{"label", "value", "unit"?, "ok"? (True/False/None → liseré d'état)}]."""
    st = st or styles()
    items = list(items)
    if not items:
        return Spacer(1, 0)
    per_row = min(per_row, len(items))
    w = 180 * mm / per_row
    cells, sty, row, rows = [], [], [], []
    for k, it in enumerate(items):
        v = str(it["value"])
        val = (_esc(v) if len(v) <= 11 else f'<font size="{10 if len(v) <= 18 else 8.5}">{_esc(v)}</font>') + \
            (f' <font size="7.5" color="#555555">{_esc(it["unit"])}</font>' if it.get("unit") else "")
        row.append([Paragraph(val, st["kv"]), Paragraph(_esc(it["label"]), st["kl"])])
        ok = it.get("ok", "x")
        if ok != "x":
            sty.append(("LINEABOVE", (k % per_row, len(rows)), (k % per_row, len(rows)), 2.4, _res(ok)[1]))
        else:
            sty.append(("LINEABOVE", (k % per_row, len(rows)), (k % per_row, len(rows)), 2.4, ACCENT))
        if len(row) == per_row:
            rows.append(row); row = []
    if row:
        rows.append(row + [""] * (per_row - len(row)))
    t = Table(rows, colWidths=[w] * per_row)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#edf4f3")), ("BOX", (0, 0), (-1, -1), 0, colors.white),
                           ("INNERGRID", (0, 0), (-1, -1), 3, colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)] + sty))
    return t


def _synthese(blocks, st):
    ctl = [c for b in blocks if b[0] == "controls" for c in b[1]]
    if not ctl:
        return []
    n_ok = sum(1 for c in ctl if c.get("ok") is True)
    n_ko = sum(1 for c in ctl if c.get("ok") is False)
    n_na = len(ctl) - n_ok - n_ko
    glob = False if n_ko else (True if not n_na else None)
    msg = LANG["verdict_glob_ko"] if n_ko else (LANG["verdict_glob_ok"] if not n_na else LANG["verdict_glob_na"])
    lab, col = _res(glob)
    from reportlab.graphics.shapes import Drawing, Rect, String
    d = Drawing(180 * mm, 16)
    tot = max(1, len(ctl))
    x = 0.0
    for n, c in ((n_ok, OK_C), (n_na, NA_C), (n_ko, KO_C)):
        if n:
            wseg = 180 * mm * n / tot
            d.add(Rect(x, 9, max(0.0, wseg - 1.5), 6, fillColor=c, strokeColor=None, rx=2, ry=2))
            x += wseg
    d.add(String(0, 0, txt(f"{n_ok} {LANG['conformes']} · {n_na} {LANG['a_verifier']} · {n_ko} {LANG['non_conformes']}"), fontName="CP", fontSize=7, fillColor=GRIS))
    pill = Table([[Paragraph(_esc(lab), st["res"]), Paragraph(_esc(msg), ParagraphStyle("m", parent=st["p"], fontName="CP-Bold", textColor=col))]],
                 colWidths=[28 * mm, 152 * mm])
    pill.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), col), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (1, 0), (1, 0), 6),
                              ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return [Paragraph(_esc(LANG["synthese"]), ParagraphStyle("sy", parent=st["kl"], fontName="CP-Bold", textColor=VERT, spaceAfter=2)), pill, Spacer(1, 1.5 * mm), d, Spacer(1, 2 * mm)]


def _hyp_box(lines, st):
    inner = [Paragraph(_esc(h), st["hyp"], bulletText="•") for h in lines]
    t = Table([[inner]], colWidths=[180 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AMBRE_BG), ("LINEBEFORE", (0, 0), (0, -1), 2.2, NA_C),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
    return t


def _ref(title):
    import hashlib
    from datetime import date
    return f"CP-{date.today():%y%m%d}-{hashlib.sha1(title.encode()).hexdigest()[:4].upper()}"


class _NumCanvas(_canvas.Canvas):
    """Canvas en deux passes : « page x / n »."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._pages)
        for st_ in self._pages:
            self.__dict__.update(st_)
            self.setFont("CP", 6.5); self.setFillColor(GRIS)
            self.drawRightString(A4[0] - 15 * mm, 8.5 * mm, f"{LANG['page']} {self._pageNumber} / {n}")
            super().showPage()
        super().save()


def build_pdf(title, subtitle, blocks, footer="ConstruPilot — nota de cálculo gerada por motor determinístico; a validar pelo projetista / técnico responsável antes da execução.") -> bytes:
    """blocks : liste de ("h2", texte) | ("p", texte) | ("table", head, rows, widths) | ("controls", ctl) | ("figure", flowable)
    | ("chart", drawing[, légende]) | ("kpis", [{label, value, unit, ok}]) | ("hyp", [textes]) | ("spacer", h_mm).
    Première page : bandeau de marque, titre, référence et date ; synthèse automatique des contrôles ; pied « page x / n »."""
    from datetime import date
    st = styles()
    buf = io.BytesIO()
    ref = _ref(title)
    W, H = A4
    head = Table([[Paragraph(_esc(title), st["h1"])], [Paragraph(_esc(subtitle), st["sub"])]], colWidths=[180 * mm])
    head.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    head_h = head.wrap(180 * mm, H)[1]
    hdr_h = 23 * mm + head_h + 5 * mm

    def deco(cv, doc, first):
        cv.saveState()
        if first:
            cv.setFillColor(VERT); cv.rect(0, H - hdr_h, W, hdr_h, stroke=0, fill=1)
            _faixa(cv, 0, H - hdr_h - 4.2 * mm, W, 4.2 * mm)   # faixa de azulejos (identidade .pt)
            cv.setFillColor(colors.white); cv.setFont("CP-Bold", 11); cv.drawString(15 * mm, H - 11 * mm, "ConstruPilot")
            cv.setFillColor(CLAIR); cv.setFont("CP", 6.8); cv.drawString(15 * mm, H - 15 * mm, txt(LANG["brand_sub"]))
            cv.setFont("CP-Bold", 7.5); cv.setFillColor(colors.white)
            cv.drawRightString(W - 15 * mm, H - 11 * mm, txt(LANG["note"].upper()))
            cv.setFont("CP", 6.8); cv.setFillColor(CLAIR)
            cv.drawRightString(W - 15 * mm, H - 15 * mm, f"{txt(LANG['ref'])} {ref} · {date.today():%d/%m/%Y}")
        else:
            cv.setFillColor(VERT); cv.rect(0, H - 9 * mm, W, 9 * mm, stroke=0, fill=1)
            _faixa(cv, 0, H - 11 * mm, W, 2 * mm)
            cv.setFillColor(colors.white); cv.setFont("CP-Bold", 7.5); cv.drawString(15 * mm, H - 5.8 * mm, "ConstruPilot")
            cv.setFont("CP", 7); cv.setFillColor(CLAIR)
            t = txt(title)
            cv.drawRightString(W - 15 * mm, H - 5.8 * mm, (t if len(t) <= 95 else t[:93] + "…") + f"  ·  {ref}")
        cv.setStrokeColor(colors.HexColor("#c8dadc")); cv.setLineWidth(0.4); cv.line(15 * mm, 12 * mm, W - 15 * mm, 12 * mm)
        cv.setFont("CP", 6.3); cv.setFillColor(GRIS); cv.drawString(15 * mm, 8.5 * mm, txt(footer))
        cv.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                          title=title, author="ConstruPilot", subject=subtitle, creator="ConstruPilot")
    f1 = Frame(15 * mm, 16 * mm, W - 30 * mm, H - 16 * mm - 18 * mm - 5 * mm, id="f1", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    f2 = Frame(15 * mm, 16 * mm, W - 30 * mm, H - 16 * mm - 14 * mm, id="f2", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate("first", [f1], onPage=lambda c, d: deco(c, d, True), autoNextPageTemplate="later"),
                          PageTemplate("later", [f2], onPage=lambda c, d: deco(c, d, False))])
    # titre dans le bandeau (hauteur ajustée au titre) : la 1re frame commence sous le logo, le titre est posé en blanc sur le vert
    story = [head, Spacer(1, 10 * mm)]
    kp = [b for b in blocks if b[0] == "kpis"]
    for b in kp:
        story += [kpis(b[1], st), Spacer(1, 3 * mm)]
    story += _synthese(blocks, st)
    pend = []
    prev_k, last_p = None, None
    for b in blocks:
        k = b[0]
        if pend and k not in ("h2", "kpis"):
            mark = len(story)
        if k == "h2":
            story += pend
            pend = _h2(b[1], st)
            prev_k = k
            continue
        elif k == "p":
            last_p = Paragraph(_esc(b[1]), st["p"])
            story.append(last_p)
        elif k == "table":
            story += [table(b[1], b[2], b[3] if len(b) > 3 else None, st), Spacer(1, 2 * mm)]
        elif k == "controls":
            story += [controls_table(b[1], st), Spacer(1, 2 * mm)]
        elif k in ("figure", "chart"):
            items = [b[1]] + ([Paragraph(_esc(b[2]), st["cap"])] if len(b) > 2 and b[2] else [Spacer(1, 3 * mm)])
            head_ = []
            if prev_k == "p" and story and not pend:
                # paragraphe d'introduction solidaire du graphique qui le suit (avec son titre de section éventuel)
                if story[-1] is last_p:
                    head_ = [story.pop()]
                elif isinstance(story[-1], KeepTogether) and story[-1]._content and story[-1]._content[-1] is last_p:
                    head_ = list(story.pop()._content)
            story.append(KeepTogether(head_ + [Spacer(1, 1.5 * mm)] + items))
        elif k == "hyp":
            story += [_hyp_box(b[1], st), Spacer(1, 2 * mm)]
        elif k == "spacer":
            story.append(Spacer(1, b[1] * mm))
        if pend and k != "kpis":
            # titre de section solidaire de son premier contenu (jamais seul en bas de page)
            first = story[mark:mark + 1]
            if first and isinstance(first[0], KeepTogether):
                first = list(first[0]._content)      # KeepTogether imbriqué : wrap() renvoie 0xffffff → saut de page forcé
            rest = story[mark + 1:]
            del story[mark:]
            story.append(KeepTogether(pend + first))
            story += rest
            pend = []
        prev_k = k
    story += pend
    doc.build(story, canvasmaker=_NumCanvas)
    return buf.getvalue()


def first_page_png(pdf: bytes, dpi=150) -> bytes:
    import pymupdf
    d = pymupdf.open(stream=pdf, filetype="pdf")
    return d[0].get_pixmap(dpi=dpi).tobytes("png")


# ---------------------------------------------------------------------------------------------------------------- figures
FILL = {"support": "#d6d6d6", "isolant": "#fff3b0", "parement": "#f3efe8", "membrane": "#2c6fb0", "air": "#ffffff"}


class ParoiGlaser(Flowable):
    """Coupe de la paroi à l'échelle (épaisseurs) avec la courbe de température, et dessous le diagramme de Glaser
    (pression de vapeur partielle p et pression saturante psat en fonction de la résistance à la diffusion Sd)."""

    def __init__(self, couches, glaser, width=180 * mm, height=95 * mm):
        super().__init__()
        self.c, self.g, self.width, self.height = couches, glaser, width, height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        cv = self.canv
        fonts()
        W, H = self.width, self.height
        top_h = H * 0.52
        # ---- coupe (épaisseurs ; membranes dessinées à 1,2 mm)
        x0, x1 = 18 * mm, W - 8 * mm
        eps = [max(l["ep_mm"], 0) for l in self.c]
        vis = [e if e > 0 else 4 for e in eps]
        tot = sum(vis)
        ys0, ys1 = H - top_h + 8 * mm, H - 6 * mm
        x = x0
        xs = [x]
        pts = self.g["points"]
        for l, v in zip(self.c, vis):
            w = (x1 - x0) * v / tot
            cv.setFillColor(colors.HexColor(FILL.get(l["role"], "#eeeeee")))
            cv.setStrokeColor(colors.HexColor("#1d1d1d")); cv.setLineWidth(0.5)
            cv.rect(x, ys0, w, ys1 - ys0, stroke=1, fill=1)
            cv.saveState(); cv.translate(x + w / 2 + 2.5, ys0 + 2 * mm); cv.rotate(90)
            cv.setFont("CP", 6.2); cv.setFillColor(colors.HexColor("#1d1d1d"))
            lab = l["nom"] if l["ep_mm"] <= 0 else f"{l['nom'][:34]} · {l['ep_mm']:g} mm"
            cv.drawString(0, 0, txt(lab[:60])); cv.restoreState()
            x += w
            xs.append(x)
        # température (ligne rouge) : T aux interfaces, échelle -10..25 °C sur la hauteur de la coupe
        tmin, tmax = -10.0, 25.0
        ty = lambda t: ys0 + (ys1 - ys0) * (t - tmin) / (tmax - tmin)
        cv.setStrokeColor(ROUGE); cv.setLineWidth(1.3)
        p = cv.beginPath(); p.moveTo(xs[0], ty(pts[0]["T"]))
        for xx, pt in zip(xs[1:], pts[1:]):
            p.lineTo(xx, ty(pt["T"]))
        cv.drawPath(p, stroke=1, fill=0)
        cv.setFont("CP", 6.5); cv.setFillColor(ROUGE)
        cv.drawRightString(x0 - 1.5, ty(pts[0]["T"]) - 2, f"{pts[0]['T']:.1f} °C")
        cv.drawString(x1 + 1.5, ty(pts[-1]["T"]) - 2, f"{pts[-1]['T']:.1f}")
        cv.setFont("CP-Bold", 7); cv.setFillColor(VERT)
        cv.drawString(x0, ys1 + 1.5 * mm, "INTERIOR"); cv.drawRightString(x1, ys1 + 1.5 * mm, "EXTERIOR")
        # ---- Glaser : abscisse = Sd cumulé
        gy0, gy1 = 8 * mm, H - top_h - 2 * mm
        sd_tot = max(self.g["Sd_total"], 1e-6)
        gx = lambda sd: x0 + (x1 - x0) * sd / sd_tot
        pmax = max(max(pt["psat"] for pt in pts), self.g["pi"]) * 1.08
        gp = lambda pa: gy0 + (gy1 - gy0) * pa / pmax
        cv.setStrokeColor(colors.HexColor("#999999")); cv.setLineWidth(0.4)
        cv.rect(x0, gy0, x1 - x0, gy1 - gy0, stroke=1, fill=0)
        for pt in pts[1:-1]:
            cv.setDash([1, 2]); cv.line(gx(pt["sd"]), gy0, gx(pt["sd"]), gy1); cv.setDash([])
        cv.setStrokeColor(colors.HexColor("#1f5f9f")); cv.setLineWidth(1.2); cv.setDash([3, 2])
        p = cv.beginPath(); p.moveTo(gx(pts[0]["sd"]), gp(pts[0]["psat"]))
        for pt in pts[1:]:
            p.lineTo(gx(pt["sd"]), gp(pt["psat"]))
        cv.drawPath(p, stroke=1, fill=0); cv.setDash([])
        cv.setStrokeColor(colors.HexColor("#1d1d1d")); cv.setLineWidth(1.0)
        cv.line(gx(0), gp(self.g["pi"]), gx(sd_tot), gp(self.g["pe"]))
        for pt in pts:
            if pt["condensation"]:
                cv.setFillColor(ROUGE); cv.circle(gx(pt["sd"]), gp(pt["p"]), 1.6, stroke=0, fill=1)
        cv.setFont("CP", 6.3); cv.setFillColor(colors.HexColor("#1d1d1d"))
        cv.drawString(x0 + 2, gy1 - 7, txt("— p vapor (Pa)    - - psat (Pa)    ● condensação"))
        cv.drawString(x0, gy0 - 6, txt(f"Sd acumulado 0 → {sd_tot:.1f} m (abcissa proporcional à resistência à difusão)"))
        cv.drawRightString(x0 - 1.5, gp(self.g["pi"]) - 2, f"{self.g['pi']:.0f}")
