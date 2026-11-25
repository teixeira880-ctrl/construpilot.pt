"""PDF do plano de estaleiro (PT): planta (A3 horizontal) + memória de verificação
(gruas, curvas de carga, cobertura, material, pontos de atenção)."""
import base64
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from engines import pic
from engines import pic_relief as relief

GREEN = colors.HexColor("#0F5257")
COPPER = colors.HexColor("#E07A5F")
DARK = colors.HexColor("#0A0D14")
GREY = colors.HexColor("#64748B")
LIGHT = colors.HexColor("#E2E8F0")
RED = colors.HexColor("#FF1744")
LIFT = colors.HexColor("#00C853")
BLUE = colors.HexColor("#2979FF")
BUILDING = colors.HexColor("#FFC400")
OBST = {"ligne_electrique": colors.HexColor("#FFEA00"), "arbre": colors.HexColor("#00E676")}

BODY = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, textColor=DARK, leading=11)
BOLD = ParagraphStyle("bb", parent=BODY, fontName="Helvetica-Bold")
SMALL = ParagraphStyle("s", fontName="Helvetica", fontSize=7.5, textColor=GREY, leading=9.5, spaceAfter=5)
HEAD = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white, leading=11)
TITLE = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=11, textColor=GREEN, leading=14,
                       spaceBefore=6, spaceAfter=3)
BULLET = ParagraphStyle("bu", parent=BODY, leftIndent=8, firstLineIndent=-8, spaceAfter=2)

W, H = landscape(A3)
M = 12 * mm
TOP = 23.2 * mm + 5 * mm     # bandeau + marge
BOTTOM = 11 * mm
GAP = 8 * mm
COLW = (W - 2 * M - GAP) / 2
LEG_W = 92 * mm


def _fr(v, nd=2):
    if v is None:
        return "—"
    s = f"{float(v):.{nd}f}".rstrip("0").rstrip(".") if nd else f"{float(v):.0f}"
    return s.replace(".", ",")


def _hex(col) -> str:
    return "#" + col.hexval()[2:]


def _logo(branding):
    b64 = (branding or {}).get("logo_b64")
    if not b64:
        return None
    try:
        r = ImageReader(BytesIO(base64.b64decode(b64.split(",", 1)[-1])))
        r.getSize()
        return r
    except Exception:  # noqa: BLE001 — logo illisible : le PDF sort sans logo
        return None


def _page(branding, logo, sub, credit=""):
    """Bandeau, filigrane et pied de page communs."""
    def draw(c, doc):
        c.saveState()
        if logo:  # filigrane
            iw, ih = logo.getSize()
            w = 110 * mm
            c.saveState()
            c.setFillAlpha(0.05)
            c.drawImage(logo, (W - w) / 2, (H - w * ih / iw) / 2, width=w, height=w * ih / iw, mask="auto")
            c.restoreState()
        c.setFillColor(GREEN)
        c.rect(0, H - 22 * mm, W, 22 * mm, stroke=0, fill=1)
        c.setFillColor(COPPER)
        c.rect(0, H - 23.2 * mm, W, 1.2 * mm, stroke=0, fill=1)
        x = M
        if logo:
            iw, ih = logo.getSize()
            h = 15 * mm
            w = min(h * iw / ih, 45 * mm)
            c.setFillColor(colors.white)
            c.roundRect(x - 1.5 * mm, H - 20 * mm, w + 3 * mm, h + 3 * mm, 1.5 * mm, stroke=0, fill=1)
            c.drawImage(logo, x, H - 18.5 * mm, width=w, height=h, mask="auto", preserveAspectRatio=True)
            x += w + 7 * mm
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x, H - 11.5 * mm, "Plano de estaleiro")
        c.setFont("Helvetica", 9)
        c.drawString(x, H - 17 * mm, sub)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(W - M, H - 11.5 * mm, (branding or {}).get("company_name") or "")
        c.setFont("Helvetica", 8)
        c.drawRightString(W - M, H - 17 * mm, datetime.now(timezone.utc).strftime("Emitido em %d/%m/%Y"))
        c.setFont("Helvetica", 7)
        c.setFillColor(GREY)
        c.drawString(M, 6 * mm, "Plano de estaleiro — documento de preparação. As características da grua devem ser "
                                "confirmadas com a ficha técnica da empresa de aluguer antes da entrada em serviço.")
        if credit:
            c.drawString(M, 2.8 * mm, credit)
        c.drawRightString(W - M, 6 * mm, f"Página {doc.page}")
        c.restoreState()
    return draw


# ---------------------------------------------------------------------------
# Tableaux
# ---------------------------------------------------------------------------
def _tbl(rows, widths, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, LIGHT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), GREEN))
    t.setStyle(TableStyle(st))
    t.hAlign = "LEFT"
    return t


def _verdict(ok, yes="Conforme", no="Insuficiente"):
    return Paragraph(f'<font color="{"#15803D" if ok else "#B91C1C"}"><b>{yes if ok else no}</b></font>', BODY)


def _bullets(title, items, color="#0A0D14"):
    if not items:
        return []
    out = [Paragraph(title, TITLE)]
    out += [Paragraph(f'<font color="{color}">•</font> {it}', BULLET) for it in items]
    return out


# ---------------------------------------------------------------------------
# Page 1 : plan
# ---------------------------------------------------------------------------
class PlanPage(Flowable):
    def __init__(self, d, image_bytes, width, height):
        super().__init__()
        self.d, self.image, self.width, self.height = d, image_bytes, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c, d = self.canv, self.d
        res = d["result"]
        legend = _draw_plan(c, d, self.image, 0, 0, self.width - LEG_W - 6 * mm, self.height)
        flow = [Paragraph("Legenda", TITLE)]
        rows = [[Paragraph("N.º", HEAD), Paragraph("Elemento", HEAD)]]
        for num, label, col in legend:
            rows.append([Paragraph(f'<font color="{_hex(col)}"><b>{num}</b></font>', BODY), Paragraph(label, BODY)])
        rows.append([Paragraph('<font color="#FF1744"><b>- -</b></font>', BODY),
                     Paragraph("Limite do estaleiro"
                               + (f" — vedação {_fr(res['cloture_ml'], 1)} m" if res.get("cloture_ml") else ""), BODY)])
        cranes = [cr for cr in res.get("cranes") or [] if cr.get("label")]
        if cranes:
            rows.append([Paragraph('<font color="#FF1744"><b>- -</b></font>', BODY),
                         Paragraph("Zona varrida pela lança", BODY)])
            if any(cr.get("lift_radius_m") and cr["lift_radius_m"] < cr["jib_m"] - 0.05 for cr in cranes):
                rows.append([Paragraph('<font color="#00C853"><b>· ·</b></font>', BODY),
                             Paragraph("Limite de elevação da carga mais pesada", BODY)])
        flow.append(_tbl(rows, [10 * mm, LEG_W - 10 * mm]))
        for cr in cranes:
            flow.append(Paragraph(f"Grua {cr['num']}" if len(cranes) > 1 else "Grua", TITLE))
            flow.append(_tbl([
                [Paragraph("Modelo", BOLD), Paragraph(cr["label"], BODY)],
                [Paragraph("Lança", BOLD), Paragraph(f"{_fr(cr['jib_m'])} m", BODY)],
                [Paragraph("Alcance necessário", BOLD), Paragraph(f"{_fr(cr['reach_required_m'], 1)} m", BODY)],
                [Paragraph("Carga na ponta da lança", BOLD), Paragraph(f"{_fr(cr['tip_t'])} t", BODY)],
                [Paragraph("Carga no raio útil", BOLD), Paragraph(f"{_fr(cr['capacity_at_reach_t'])} t", BODY)],
                [Paragraph("Carga a elevar", BOLD), Paragraph(f"{_fr(cr['load']['t'])} t", BODY)],
                [Paragraph("Veredicto", BOLD), _verdict(cr["ok"], "Grua adequada", "A rever — ver a memória")],
            ], [42 * mm, LEG_W - 42 * mm], header=False))
        y = self.height
        x = self.width - LEG_W
        for f in flow:
            _, h = f.wrap(LEG_W, y)
            if h > y:
                break
            y -= h + getattr(f.style, "spaceBefore", 0) if isinstance(f, Paragraph) else h
            f.drawOn(c, x, y)
            y -= 2 * mm


def _draw_plan(c, d, image_bytes, x0, y0, bw, bh):
    res = d["result"]
    site = d["site"]
    wm, hm = res["site"]["width_m"], res["site"]["height_m"]
    k = min(bw / wm, bh / hm)
    dw, dh = wm * k, hm * k
    ox, oy = x0 + (bw - dw) / 2, y0 + (bh - dh)

    def P(x, y):
        return ox + x * k, oy + dh - y * k

    c.drawImage(ImageReader(BytesIO(image_bytes)), ox, oy, width=dw, height=dh, mask="auto")
    c.saveState()
    clip = c.beginPath()
    clip.rect(ox, oy, dw, dh)
    c.clipPath(clip, stroke=0, fill=0)

    def poly(pts, stroke, fill=None, alpha=0.18, width=1.2, dash=None):
        path = c.beginPath()
        for i, (x, y) in enumerate(pts):
            (path.moveTo if i == 0 else path.lineTo)(*P(x, y))
        path.close()
        c.saveState()
        c.setStrokeColor(stroke)
        c.setLineWidth(width)
        if dash:
            c.setDash(*dash)
        if fill is not None:
            c.setFillColor(fill)
            c.setFillAlpha(alpha)
            c.drawPath(path, stroke=0, fill=1)
            c.setFillAlpha(1)
        c.drawPath(path, stroke=1, fill=0)
        c.restoreState()

    parcel = [pic.to_m(site, p) for p in site.get("parcel") or []]
    if len(parcel) >= 3:
        poly(parcel, colors.white, width=3.4)                      # liseré blanc : lisible sur photo
        poly(parcel, RED, width=2.0, dash=(7, 3))
    for b in site.get("buildings") or []:
        poly([pic.to_m(site, p) for p in b], DARK, fill=BUILDING, alpha=0.45, width=1.6)
    for o in res.get("obstacles") or []:
        col = OBST.get(o["type"], GREY)
        poly(list(pic._rect(o["x"], o["y"], o["w"], o["h"]).exterior.coords)[:-1], col, fill=col,
             alpha=0.2, width=0.8, dash=(3, 2))
        px, py = P(o["x"] - o["w"] / 2, o["y"] - o["h"] / 2)
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(px + 1.5 * mm, py - 3.5 * mm, o["label"])

    n = 0
    legend = []
    for e in res["elements"]:
        col = colors.HexColor(e.get("color") or "#334155")
        if e["type"] == "acces":
            px, py = P(e["x"], e["y"])
            c.setFillColor(col)
            c.circle(px, py, 3.2 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(px, py - 1 * mm, "A")
            legend.append(("A", e["label"], col))
            continue
        n += 1
        rect = pic._rect(e["x"], e["y"], e["w"], e["h"], e["rot"])
        poly(list(rect.exterior.coords)[:-1], col, fill=col, alpha=0.6, width=1.4)
        px, py = P(e["x"], e["y"])
        if e["type"] == "grue" and e.get("jib_m"):
            c.saveState()
            c.setFillColor(col)
            c.setFillAlpha(0.07)
            c.circle(px, py, e["jib_m"] * k, stroke=0, fill=1)
            c.setFillAlpha(1)
            c.setStrokeColor(col)
            c.setLineWidth(1.8)
            c.setDash(8, 4)
            c.circle(px, py, e["jib_m"] * k, stroke=1, fill=0)
            lift = e.get("lift_radius_m")
            if lift and lift < e["jib_m"] - 0.05:
                c.setStrokeColor(LIFT)
                c.setLineWidth(1.6)
                c.setDash(3, 3)
                c.circle(px, py, lift * k, stroke=1, fill=0)
                c.setStrokeColor(col)
            c.setDash()
            c.setLineWidth(1.0)
            c.line(px, py, px + e["jib_m"] * k, py)
            c.setFillColor(col)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(px + 3.5 * mm, py + 1.5 * mm, f"R = {_fr(e['jib_m'])} m")
            c.restoreState()
        c.setFillColor(colors.white)
        c.circle(px, py, 2.6 * mm, stroke=0, fill=1)
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(px, py - 1 * mm, str(n))
        dims = f" ({_fr(e['w'])} × {_fr(e['h'])} m)" if e["w"] and e["h"] else ""
        legend.append((str(n), e["label"] + dims, col))
    sec = res.get("section")
    if sec and sec.get("axis"):            # traço do corte A–A′
        (ax, ay), (bx, by) = sec["axis"]
        c.saveState()
        c.setStrokeColor(colors.HexColor("#0F5257"))
        c.setLineWidth(1.8)
        c.setDash([14, 4, 3, 4], 0)
        c.line(*P(ax, ay), *P(bx, by))
        c.setDash()
        c.setFillColor(colors.HexColor("#0F5257"))
        c.setFont("Helvetica-Bold", 12)
        (pax, pay), (pbx, pby) = P(ax, ay), P(bx, by)
        ln = max(((pbx - pax) ** 2 + (pby - pay) ** 2) ** 0.5, 1e-6)
        ux, uy = (pbx - pax) / ln, (pby - pay) / ln
        ins = min(7 * mm, ln / 4)                 # marcas ligeiramente para dentro: nunca cortadas pelo quadro
        for (px, py), lab in (((pax + ux * ins, pay + uy * ins), "A"), ((pbx - ux * ins, pby - uy * ins), "A'")):
            c.circle(px, py, 2.2 * mm, stroke=0, fill=1)
            c.drawString(px - uy * 5 * mm + 1 * mm, py + ux * 5 * mm - 1.5 * mm, lab)
        c.restoreState()
    c.restoreState()
    c.setStrokeColor(LIGHT)
    c.rect(ox, oy, dw, dh, stroke=1, fill=0)

    # barre d'échelle
    bar = next((b for b in (50, 20, 10, 5) if b <= wm / 4), 5)
    c.setStrokeColor(DARK)
    c.setLineWidth(2)
    c.line(ox + 4 * mm, oy + 5 * mm, ox + 4 * mm + bar * k, oy + 5 * mm)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(DARK)
    c.drawString(ox + 4 * mm, oy + 7 * mm, f"{bar} m")
    return legend


# ---------------------------------------------------------------------------
# Courbe de charge
# ---------------------------------------------------------------------------
class LoadChart(Flowable):
    """Charge admissible (t) selon le rayon (m) — tracé en escalier prudent."""

    def __init__(self, crane, width, height=52 * mm):
        super().__init__()
        self.cr, self.width, self.height = crane, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c, cr = self.canv, self.cr
        pts = cr.get("curve") or []
        if len(pts) < 2:
            return
        left, right, top, bottom = 11 * mm, 3 * mm, 3 * mm, 9 * mm
        load = (cr.get("load") or {}).get("t")
        xmax = float(cr["jib_m"])
        ymax = max(float(cr["cmax_t"]), load or 0) * 1.08

        def X(r):
            return left + r / xmax * (self.width - left - right)

        def Y(t):
            return bottom + t / ymax * (self.height - top - bottom)

        c.setFont("Helvetica", 7)
        step = 2 if ymax > 6 else 1
        t = 0
        while t <= ymax:
            c.setStrokeColor(LIGHT)
            c.setLineWidth(0.4)
            c.line(left, Y(t), self.width - right, Y(t))
            c.setFillColor(GREY)
            c.drawRightString(left - 1.5 * mm, Y(t) - 1 * mm, str(t))
            t += step
        r = 0
        while r <= xmax + 1e-6:
            c.drawCentredString(X(r), bottom - 4 * mm, str(r))
            r += 10 if xmax > 40 else 5
        c.drawRightString(self.width - right, 0.5 * mm, "raio (m)")
        c.drawString(0, self.height - 2.5 * mm, "carga (t)")
        path = c.beginPath()
        path.moveTo(X(0), Y(pts[0]["t"]))
        path.lineTo(X(pts[0]["r_m"]), Y(pts[0]["t"]))
        for prev, p in zip(pts, pts[1:]):
            path.lineTo(X(prev["r_m"]), Y(p["t"]))
            path.lineTo(X(p["r_m"]), Y(p["t"]))
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.6)
        c.drawPath(path, stroke=1, fill=0)
        c.setLineWidth(0.8)
        c.setDash(4, 2)
        if load is not None:
            c.setStrokeColor(RED)
            c.line(left, Y(load), self.width - right, Y(load))
            c.setFillColor(RED)
            c.drawRightString(self.width - right - 1 * mm, Y(load) + 1 * mm, f"carga a elevar {_fr(load)} t")
        reach = min(float(cr["reach_required_m"]), xmax)
        c.setStrokeColor(BLUE)
        c.line(X(reach), bottom, X(reach), self.height - top)
        c.setFillColor(BLUE)
        c.drawRightString(X(reach) - 1 * mm, self.height - top - 2.5 * mm, f"alcance {_fr(reach, 1)} m")
        c.setDash()


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------
def _crane_section(cr, many) -> list:
    name = f"Grua {cr['num']} — " if many else ""
    out = [Paragraph(f"{name}{cr.get('label') or 'grua a definir'}", TITLE)]
    if not cr.get("label"):
        out.append(Paragraph("Nenhuma grua adotada: ver os pontos de atenção.", BODY))
        return out
    rows = [[Paragraph("Verificação", HEAD), Paragraph("Detalhe", HEAD), Paragraph("Resultado", HEAD)]]
    for ch in cr.get("checks") or []:
        rows.append([Paragraph(ch["label"], BODY), Paragraph(ch["detail"], BODY), _verdict(ch["ok"])])
    out.append(_tbl(rows, [COLW * 0.3, COLW * 0.52, COLW * 0.18]))
    out.append(Spacer(1, 3 * mm))
    if cr.get("table"):
        n = len(cr["table"])
        out.append(_tbl([[Paragraph("Raio (m)", HEAD)] + [Paragraph(_fr(r["r_m"], 1), HEAD) for r in cr["table"]],
                         [Paragraph("Carga (t)", BOLD)] + [Paragraph(_fr(r["t"]), BODY) for r in cr["table"]]],
                        [COLW * 0.25] + [COLW * 0.75 / n] * n))
        out.append(Spacer(1, 2 * mm))
    out.append(LoadChart(cr, COLW))
    out.append(Paragraph(f"Fonte: {cr.get('source') or '—'} — {cr.get('capacity_method') or ''}. "
                         f"Alcance até ao edifício {_fr(cr['reach_building_m'], 1)} m; zona servida: "
                         f"{', '.join(cr.get('covered') or []) or '—'}.", SMALL))
    return [KeepTogether(out)]


class Snapshot(Flowable):
    """Capture de la vue 3D, ajustée à la page."""

    def __init__(self, data: bytes, width, height, title="Vista 3D do estaleiro",
                 note="Volumes à escala da planta; alturas das instalações indicativas."):
        super().__init__()
        self.img = ImageReader(BytesIO(data))
        self.img.getSize()
        self.width, self.height, self.title, self.note = width, height, title, note

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(GREEN)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(0, self.height - 5 * mm, self.title)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GREY)
        c.drawString(c.stringWidth(self.title, "Helvetica-Bold", 11) + 5 * mm, self.height - 5 * mm, self.note)
        iw, ih = self.img.getSize()
        bh = self.height - 9 * mm
        k = min(self.width / iw, bh / ih)
        c.drawImage(self.img, (self.width - iw * k) / 2, bh - ih * k, width=iw * k, height=ih * k)


class SectionSlot(Flowable):
    """Lugar reservado ao corte vertical: o SVG vetorial é colocado aqui depois da paginação."""

    def __init__(self, width, height, slots: list):
        super().__init__()
        self.width, self.height, self.slots = width, height, slots

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        x, y = self.canv.absolutePosition(0, 0)
        self.slots.append((self.canv.getPageNumber(), x, y, self.width, self.height))


def _place_svg(pdf_bytes: bytes, svg: str, slots: list) -> bytes:
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    src = pymupdf.open("pdf", pymupdf.open(stream=svg.encode("utf-8"), filetype="svg").convert_to_pdf())
    for page_no, x, y, w, h in slots:
        page = doc[page_no - 1]
        ph = page.rect.height
        page.show_pdf_page(pymupdf.Rect(x, ph - y - h, x + w, ph - y), src, 0, keep_proportion=True)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


def build(d: dict, image_bytes: bytes, branding: dict | None = None, snapshot: bytes | None = None,
          render_ia: bytes | None = None, snapshot_aerial: bytes | None = None) -> bytes:
    res = d["result"]
    logo = _logo(branding)
    sub = (f"{d.get('filename') or ''} — estaleiro {_fr(res['site']['parcel_m2'], 0)} m², edifício "
           f"{_fr(res['site']['building_m2'], 0)} m²")
    buf = BytesIO()
    doc = BaseDocTemplate(buf, pagesize=landscape(A3), leftMargin=M, rightMargin=M, topMargin=TOP,
                          bottomMargin=BOTTOM, title="Plano de estaleiro",
                          author=(branding or {}).get("company_name") or "ConstruPilot")
    fh = H - TOP - BOTTOM
    aerial = (d.get("site") or {}).get("base") == "aerial"
    on_page = _page(branding, logo, sub, "Fundo: ortofotomapa da DGT (OrtoSat) — prédio: cadastro predial da DGT, onde existe."
                    if aerial else "")
    pad = dict(leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate("plan", [Frame(M, BOTTOM, W - 2 * M, fh, **pad)], onPage=on_page),
        PageTemplate("notice", [Frame(M, BOTTOM, COLW, fh, **pad),
                                Frame(M + COLW + GAP, BOTTOM, COLW, fh, **pad)], onPage=on_page),
    ])
    story = [PlanPage(d, image_bytes, W - 2 * M, fh - 1)]
    slots: list = []
    sec = (d.get("result") or {}).get("section")
    if sec and sec.get("svg"):
        story += [PageBreak(), SectionSlot(W - 2 * M, fh - 1, slots)]
    for data, title, note in (
            (snapshot, "Vista 3D do estaleiro", "Volumes à escala da planta; alturas das instalações indicativas."),
            (snapshot_aerial, relief.T["pdf_aerial"], relief.T["pdf_aerial_note"]),
            (render_ia, "Imagem de ambiente fotorrealista",
             "Gerada por IA a partir da vista 3D — não contratual: só a planta e a memória fazem fé.")):
        if not data:
            continue
        try:
            story += [PageBreak(), Snapshot(data, W - 2 * M, fh - 1, title, note)]
        except Exception:  # noqa: BLE001 — image illisible : le PDF sort sans cette page
            pass
    story += [NextPageTemplate("notice"), PageBreak()]

    cranes = res.get("cranes") or ([res["crane"]] if res.get("crane") else [])
    for cr in cranes:
        story += _crane_section(cr, len(cranes) > 1)
    if cranes:
        load = cranes[0].get("load") or {}
        if load.get("detail"):
            rows = [[Paragraph("Componente", HEAD), Paragraph("t", HEAD)]]
            rows += [[Paragraph(r["label"], BODY), Paragraph(_fr(r["t"], 3), BODY)] for r in load["detail"]]
            rows.append([Paragraph("Carga de cálculo adotada (a mais pesada, acessórios incluídos)", BOLD),
                         Paragraph(_fr(load["t"], 3), BOLD)])
            story.append(KeepTogether([Paragraph("Carga de cálculo", TITLE), _tbl(rows, [COLW * 0.8, COLW * 0.2])]))
        cov, inter = res.get("coverage"), res.get("interference")
        block = [Paragraph("Cobertura do edifício", TITLE)]
        if cov:
            txt = f"Área do edifício sob a lança: <b>{_fr(cov['portee_pct'], 1)} %</b>."
            if cov.get("charge_pct") is not None:
                txt += f" Área onde a carga de cálculo pode ser elevada: <b>{_fr(cov['charge_pct'], 1)} %</b>."
            block.append(Paragraph(txt, BODY))
        if inter:
            block.append(Paragraph(f"Interferência entre gruas: {inter['detail']} — "
                                   f"<b>{'aceitável com sistema anticolisão' if inter['ok'] else 'a corrigir'}</b>.", BODY))
        if res.get("loads"):
            rows = [[Paragraph(h, HEAD) for h in ("Carga", "Peso (t)", "Raio de elevação (m)", "Edifício coberto")]]
            for row in res["loads"]:
                rows.append([Paragraph(row["label"], BODY), Paragraph(_fr(row["t"], 3), BODY),
                             Paragraph(" / ".join(_fr(r, 1) for r in row["radius_m"]), BODY),
                             _verdict(row["ok"], f"{_fr(row['coverage_pct'], 1)} %", f"{_fr(row['coverage_pct'], 1)} %")])
            block += [Spacer(1, 2 * mm), _tbl(rows, [COLW * 0.46, COLW * 0.14, COLW * 0.2, COLW * 0.2])]
        if len(block) > 1:
            story.append(KeepTogether(block))

    if res.get("materiel"):
        rows = [[Paragraph(h, HEAD) for h in ("Designação", "Quantidade", "Unidade", "Base de cálculo")]]
        for m in res["materiel"]:
            rows.append([Paragraph(m["designation"], BODY), Paragraph(_fr(m["quantite"], 1), BOLD),
                         Paragraph(m["unite"], BODY), Paragraph(m["base"], SMALL)])
        story += [Paragraph("Material de estaleiro", TITLE),
                  _tbl(rows, [COLW * 0.42, COLW * 0.12, COLW * 0.08, COLW * 0.38])]
    if res.get("base_vie"):
        bv = res["base_vie"]
        story.append(KeepTogether([
            Paragraph("Instalações sociais — mínimo sanitário", TITLE),
            _tbl([[Paragraph(h, HEAD) for h in ("Trabalhadores em simultâneo", "Retretes (mínimo)")],
                  [Paragraph(str(bv[k]), BODY) for k in ("effectif", "wc")]], [COLW / 2] * 2),
            Paragraph(f"{bv['ref']}. {bv.get('nota') or ''}", SMALL)]))

    story += _bullets("Informações em falta", res.get("missing"), "#B91C1C")
    story += _bullets("Pontos de atenção", res.get("warnings"), "#B45309")
    story += _bullets("Hipóteses adotadas", res.get("hypotheses"))
    story += _bullets("A fazer antes do arranque", res.get("checklist"))
    doc.build(story)
    if slots:
        return _place_svg(buf.getvalue(), sec["svg"], slots)
    return buf.getvalue()
