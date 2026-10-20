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
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VERT, OCRE, GRIS, ROUGE = colors.HexColor("#17483f"), colors.HexColor("#8a6d00"), colors.HexColor("#555555"), colors.HexColor("#b3261e")
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


def styles():
    fonts()
    return {
        "h1": ParagraphStyle("h1", fontName="CP-Bold", fontSize=14, leading=17, textColor=VERT, spaceAfter=2),
        "sub": ParagraphStyle("sub", fontName="CP", fontSize=8.5, leading=11, textColor=GRIS, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName="CP-Bold", fontSize=10.5, leading=13, textColor=VERT, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", fontName="CP", fontSize=8, leading=10.5, alignment=TA_LEFT),
        "small": ParagraphStyle("small", fontName="CP", fontSize=7, leading=9, textColor=GRIS),
        "hyp": ParagraphStyle("hyp", fontName="CP", fontSize=7.5, leading=9.8, textColor=OCRE, leftIndent=8, bulletIndent=0),
        "cell": ParagraphStyle("cell", fontName="CP", fontSize=7.3, leading=9),
        "cellb": ParagraphStyle("cellb", fontName="CP-Bold", fontSize=7.3, leading=9, textColor=colors.white),
    }


def _esc(t):
    return txt(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(head, rows, widths=None, st=None):
    st = st or styles()
    data = [[Paragraph(_esc(h), st["cellb"]) for h in head]] + [[Paragraph(_esc(c), st["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), VERT), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c8c8c8")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f4")]),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def controls_table(ctl, st=None):
    """Tableau des contrôles : conforme (vert) / non conforme (rouge) / à vérifier (gris)."""
    st = st or styles()
    head = ["Referência", "Exigência", "Valor", "Resultado"]
    rows, bgs = [], []
    for i, c in enumerate(ctl, 1):
        res = "CONFORME" if c.get("ok") is True else ("NÃO CONFORME" if c.get("ok") is False else "A VERIFICAR")
        txt = c.get("exigence", "") + (f" — {c['note']}" if c.get("note") else "")
        rows.append([c.get("ref", ""), txt, c.get("valeur", ""), res])
        bgs.append(("BACKGROUND", (3, i), (3, i), OK_BG if c.get("ok") is True else (KO_BG if c.get("ok") is False else NA_BG)))
    t = table(head, rows, widths=[46 * mm, 72 * mm, 34 * mm, 26 * mm], st=st)
    t.setStyle(TableStyle(bgs))
    return t


def build_pdf(title, subtitle, blocks, footer="ConstruPilot — nota de cálculo gerada por motor determinístico; a validar pelo projetista / técnico responsável antes da execução.") -> bytes:
    """blocks : liste de ("h2", texte) | ("p", texte) | ("table", head, rows, widths) | ("controls", ctl) | ("figure", flowable)
    | ("hyp", [textes]) | ("spacer", h_mm)."""
    st = styles()
    buf = io.BytesIO()

    def on_page(cv, doc):
        cv.saveState()
        cv.setFont("CP", 6.5); cv.setFillColor(GRIS)
        cv.drawString(15 * mm, 9 * mm, txt(footer))
        cv.drawRightString(A4[0] - 15 * mm, 9 * mm, f"{doc.page}")
        cv.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=16 * mm, title=title)
    story = [Paragraph(_esc(title), st["h1"]), Paragraph(_esc(subtitle), st["sub"])]
    for b in blocks:
        k = b[0]
        if k == "h2":
            story.append(Paragraph(_esc(b[1]), st["h2"]))
        elif k == "p":
            story.append(Paragraph(_esc(b[1]), st["p"]))
        elif k == "table":
            story.append(table(b[1], b[2], b[3] if len(b) > 3 else None, st))
        elif k == "controls":
            story.append(controls_table(b[1], st))
        elif k == "figure":
            story.append(KeepTogether([b[1]]))
        elif k == "hyp":
            for h in b[1]:
                story.append(Paragraph(_esc(h), st["hyp"], bulletText="•"))
        elif k == "spacer":
            story.append(Spacer(1, b[1] * mm))
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
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
