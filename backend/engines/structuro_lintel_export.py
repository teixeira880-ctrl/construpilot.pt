"""Plan coté exportable d'un linteau de reprise d'ouverture (PDF + DXF).

Dessin schématique COTÉ, construit à partir du résultat déterministe de
structuro_lintel.lintel_design (clé 'geometry'). NON EXÉCUTOIRE — à faire viser
par l'ingénieur / le bureau de contrôle. Le DXF est généré avec ezdxf (unités mm).
"""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

import ezdxf
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_DK = colors.HexColor("#1f2937")
_MUT = colors.HexColor("#6b7280")
_STEEL = colors.HexColor("#334155")
_RC = colors.HexColor("#d1d5db")
_BAR = colors.HexColor("#b91c1c")
_COTE = colors.HexColor("#0f766e")


def _r(x, n=0):
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- reportlab figure (cotée) ----

def _hdim(d, x1, x2, y, text):
    """Cote horizontale entre x1 et x2 à l'altitude y (ticks + texte)."""
    d.add(Line(x1, y, x2, y, strokeColor=_COTE, strokeWidth=0.6))
    for x in (x1, x2):
        d.add(Line(x, y - 3, x, y + 3, strokeColor=_COTE, strokeWidth=0.8))
    d.add(String((x1 + x2) / 2.0, y + 3, text, fontSize=7, fillColor=_COTE, textAnchor="middle"))


def _vdim(d, y1, y2, x, text):
    """Cote verticale entre y1 et y2 à l'abscisse x."""
    d.add(Line(x, y1, x, y2, strokeColor=_COTE, strokeWidth=0.6))
    for y in (y1, y2):
        d.add(Line(x - 3, y, x + 3, y, strokeColor=_COTE, strokeWidth=0.8))
    d.add(String(x - 5, (y1 + y2) / 2.0, text, fontSize=7, fillColor=_COTE, textAnchor="end"))


def _hatch(d, x, y, w, h):
    d.add(Rect(x, y, w, h, strokeColor=_DK, strokeWidth=0.7, fillColor=colors.HexColor("#eef2f1")))
    off, step = 0.0, 7.0
    while off < w + h:
        x1 = x + max(0.0, off - h); y1 = y + min(off, h)
        x2 = x + min(off, w); y2 = y + max(0.0, off - w)
        d.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#9ca3af"), strokeWidth=0.3))
        off += step


def lintel_figure_dim(lint: dict, width: float = 720, height: float = 300) -> Drawing:
    """Figure cotée (élévation + coupe) pour PDF. Dimensions affichées en mm."""
    d = Drawing(width, height)
    geom = (lint or {}).get("geometry") or {}
    L = float(geom.get("clear_span_m") or 1.0)
    a = float(geom.get("bearing_m") or 0.2)
    t = float(geom.get("wall_thickness_m") or 0.2)
    d.add(Rect(0, 0, width, height, strokeColor=colors.HexColor("#e5e7eb"), strokeWidth=0.6, fillColor=colors.white))

    # ---- élévation (moitié gauche) ----
    ox, ow = 0.0, width * 0.6
    pier = 0.4
    total_m = L + 2 * a + 2 * pier
    sc = (ow - 90) / total_m if total_m > 0 else 1.0
    base = 70.0
    op_h = height - 150
    x0 = ox + 50
    _hatch(d, x0, base, pier * sc, op_h)
    xr = x0 + (pier + L + 2 * a) * sc
    _hatch(d, xr, base, pier * sc, op_h)
    opx = x0 + pier * sc
    d.add(Rect(opx, base, (L + 2 * a) * sc, op_h, strokeColor=colors.HexColor("#cbd5e1"),
               strokeWidth=0.5, fillColor=colors.white, strokeDashArray=[3, 2]))
    lint_y = base + op_h
    d.add(Rect(opx, lint_y, (L + 2 * a) * sc, 14, strokeColor=_DK, strokeWidth=1.1, fillColor=_STEEL))
    top = lint_y + 14
    cx = opx + (L + 2 * a) * sc / 2.0
    if geom.get("masonry_model") == "arching":
        apex = min(top + (L / 2.0) * sc, height - 30)
        d.add(Polygon([opx + a * sc, top, cx, apex, opx + (a + L) * sc, top],
                      strokeColor=_MUT, strokeWidth=0.6, fillColor=colors.HexColor("#f3f4f6")))
    else:
        d.add(Rect(opx + a * sc, top, L * sc, min(34, height - 30 - top),
                   strokeColor=_MUT, strokeWidth=0.5, fillColor=colors.HexColor("#f3f4f6")))
    # cotes
    _hdim(d, opx + a * sc, opx + (a + L) * sc, base - 22, f"L = {int(round(L * 1000))} mm")
    _hdim(d, opx, opx + a * sc, base - 10, f"a={int(round(a * 1000))}")
    _hdim(d, opx + (a + L) * sc, opx + (2 * a + L) * sc, base - 10, f"a={int(round(a * 1000))}")
    _vdim(d, base, lint_y, x0 - 14, f"H={int(round(op_h / sc * 1000))}≈")
    d.add(String(ox + 50, height - 16, "ALÇADO (esquema cotado, mm)", fontSize=8, fillColor=_DK))

    # ---- coupe (moitié droite) ----
    sx = width * 0.62
    scx = sx + (width - sx) / 2.0
    sbase = 90.0
    d.add(String(sx + 10, height - 16, "CORTE (esquema cotado, mm)", fontSize=8, fillColor=_DK))
    mat = geom.get("recommended")
    steel, rc = geom.get("steel"), geom.get("rc")
    if mat == "steel" and steel and steel.get("status") == "ok":
        from engines import structuro_profiles as profiles
        pname = steel.get("profile")
        pd = profiles.PROFILE_DATA.get(pname, {})
        hmm, bmm = float(pd.get("h", 200)), float(pd.get("b", 100))
        n = int(steel.get("count", 1))
        scd = min((width - sx - 120) / max(bmm * n + 20 * (n - 1), 1), (height - 170) / max(hmm, 1))
        hh, bf = hmm * scd, bmm * scd
        tf = max(3.0, hh * 0.08); tw = max(2.0, bf * 0.14); gap = 16.0
        tot = n * bf + (n - 1) * gap
        xs = scx - tot / 2.0
        for i in range(n):
            bx = xs + i * (bf + gap)
            d.add(Rect(bx, sbase + hh - tf, bf, tf, strokeColor=_DK, strokeWidth=0.7, fillColor=_STEEL))
            d.add(Rect(bx, sbase, bf, tf, strokeColor=_DK, strokeWidth=0.7, fillColor=_STEEL))
            d.add(Rect(bx + bf / 2 - tw / 2, sbase, tw, hh, strokeColor=_DK, strokeWidth=0.7, fillColor=_STEEL))
        _vdim(d, sbase, sbase + hh, xs - 16, f"h={int(round(hmm))}")
        _hdim(d, xs, xs + bf, sbase - 14, f"b={int(round(bmm))}")
        d.add(String(scx, sbase + hh + 16, steel.get("label", ""), fontSize=9, fillColor=_DK, textAnchor="middle"))
        bp = steel.get("bearing_plate") or {}
        if bp:
            d.add(String(scx, sbase - 26, f"platine {int(bp.get('length_mm', 0))}×{int(bp.get('width_mm', 0))}×{int(bp.get('thickness_mm', 0))} mm",
                         fontSize=7, fillColor=_MUT, textAnchor="middle"))
    elif rc and rc.get("status") == "ok":
        b, hmm = float(rc.get("b_mm", 200)), float(rc.get("h_mm", 300))
        scd = min((width - sx - 120) / max(b, 1), (height - 170) / max(hmm, 1))
        bw, bh = b * scd, hmm * scd
        xs = scx - bw / 2.0
        d.add(Rect(xs, sbase, bw, bh, strokeColor=_DK, strokeWidth=1.1, fillColor=_RC))
        d.add(Rect(xs + 5, sbase + 5, bw - 10, bh - 10, strokeColor=_BAR, strokeWidth=0.7, fillColor=None))
        for k in range(3):
            cxk = xs + 9 + k * (bw - 18) / 2.0
            d.add(Rect(cxk - 2, sbase + 7, 4, 4, strokeColor=_BAR, strokeWidth=0.9, fillColor=_BAR))
        _vdim(d, sbase, sbase + bh, xs - 16, f"h={int(round(hmm))}")
        _hdim(d, xs, xs + bw, sbase - 14, f"b={int(round(b))}")
        d.add(String(scx, sbase + bh + 16, rc.get("label", ""), fontSize=8.5, fillColor=_DK, textAnchor="middle"))
        det = (rc.get("detailing") or {}).get("anchorage") or {}
        if det:
            d.add(String(scx, sbase - 26, f"amarração {int(det.get('straight_mm', 0))} mm · gancho {int(det.get('hook_mm', 0))} mm",
                         fontSize=7, fillColor=_MUT, textAnchor="middle"))
    else:
        d.add(String(scx, sbase + 40, "Secção não resolvida", fontSize=8, fillColor=_MUT, textAnchor="middle"))
    return d


def build_lintel_pdf(lint: dict, name: str, revision: int) -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=35, rightMargin=35, topMargin=40, bottomMargin=40)
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Tiny", parent=ss["BodyText"], fontSize=8.5, leading=12))
    p = lambda t: Paragraph(escape(str(t)), ss["Tiny"])
    act = lint.get("actions", {})
    st = lint.get("steel") or {}
    rc = lint.get("rc") or {}
    reco = lint.get("recommendation") or {}
    br = lint.get("bearing") or {}
    story = [Paragraph("ConstruPilot | Planta cotada da padieira (abertura de vão)", ss["Title"]),
             p(f"{name} · revisão {revision} · motor {lint.get('version', '')}"),
             Paragraph("PLANTA NÃO EXECUTÓRIA — ESQUEMA COTADO INDICATIVO — A VISAR PELO ENGENHEIRO / ENTIDADE DE CONTROLO", ss["Heading2"]),
             p(f"Vão livre L = {lint.get('clear_span_m')} m · modelo de carga «{lint.get('load_model')} » · M_Ed {act.get('m_ed_knm')} kN·m · V_Ed {act.get('v_ed_kn')} kN · {act.get('combination', '')}"),
             Spacer(1, 6), lintel_figure_dim(lint, width=760, height=300), Spacer(1, 8)]
    if reco:
        story.append(p(f"Solução adotada (a mais económica): {('Aço NP EN 1993' if reco.get('material') == 'steel' else 'Betão armado NP EN 1992')} — {reco.get('label')} ({reco.get('cost_eur')} €)."))
    if st.get("status") == "ok":
        line = (f"Aço: {st.get('label')} ({st.get('grade')}) · M_Rd {st.get('mrd_knm')} kN·m · V_Rd {st.get('vrd_kn')} kN · flecha {st.get('defl_char_mm')}/{st.get('defl_char_limit_mm')} mm.")
        if st.get("ltb"):
            lt = st["ltb"]
            line += (f" Encurvadura lateral verificada: Mcr {lt.get('mcr_knm')} kN·m · λ̄LT {lt.get('lambda_lt')} · χLT {lt.get('chi_lt')} · Mb,Rd {lt.get('mb_rd_knm')} kN·m (curva {lt.get('curve')}, C1={lt.get('c1')}).")
        else:
            line += " Encurvadura lateral não verificada (travamento lateral assumido, χLT=1)."
        bp = st.get("bearing_plate")
        if bp:
            line += f" Platina {bp.get('length_mm')}×{bp.get('width_mm')}×{bp.get('thickness_mm')} mm."
        story.append(p(line))
    if rc.get("status") == "ok":
        det = (rc.get("detailing") or {}).get("anchorage") or {}
        story.append(p(f"Betão armado: {rc.get('label')} · As {rc.get('as_required_cm2')} cm² · Asw/s {rc.get('asw_required_cm2_m')} cm²/m · amarração {det.get('straight_mm', '—')} mm (crochet {det.get('hook_mm', '—')} mm, Ø{rc.get('bar_mm')})."))
    story.append(p(f"Apoio na alvenaria: reação ELU {br.get('reaction_kn')} kN · pression {br.get('sigma_kpa')} ≤ {br.get('allow_kpa')} kPa → {('OK' if br.get('status') == 'ok' else 'A REVER')} · entrega adotada {br.get('adopted_length_m')} m (necessária ≥ {br.get('required_length_m')} m)."))
    story += [Spacer(1, 6), p(lint.get("note", ""))]

    def footer(canvas, docu):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#9d3e26"))
        canvas.drawString(35, 20, "PLANTA DE PADIEIRA NÃO EXECUTÓRIA - ESQUEMA COTADO INDICATIVO - A VERIFICAR PELO ENGENHEIRO")
        canvas.drawRightString(806, 20, f'Rev. {revision} | {docu.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


# ---------------------------------------------------------------- DXF (cote, unités mm) ----

def _rect(msp, x, y, w, h, layer):
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
                       close=True, dxfattribs={"layer": layer})


def _hatch_dxf(msp, x, y, w, h, layer):
    _rect(msp, x, y, w, h, layer)
    step = max(w, h) / 6.0 if max(w, h) > 0 else 1.0
    off = step
    while off < w + h:
        x1, y1 = x + max(0.0, off - h), y + min(off, h)
        x2, y2 = x + min(off, w), y + max(0.0, off - w)
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})
        off += step


def build_lintel_dxf(lint: dict, name: str = "linteau") -> bytes:
    """Génère un DXF coté (élévation + coupe), unités mm, prêt bureau de contrôle."""
    geom = (lint or {}).get("geometry") or {}
    L = float(geom.get("clear_span_m") or 1.0) * 1000.0
    a = float(geom.get("bearing_m") or 0.2) * 1000.0
    pier = 400.0
    op_h = 2100.0

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for lyr, col in (("MACONNERIE", 8), ("ABERTURA", 5), ("PADIEIRA", 1), ("AÇO", 1),
                     ("ARMADURAS", 1), ("COTES", 3), ("TEXTO", 7)):
        if lyr not in doc.layers:
            doc.layers.add(lyr, color=col)

    def dim(p1, p2, base_offset, vertical=False):
        if vertical:
            d = msp.add_linear_dim(base=(p1[0] - base_offset, 0), p1=p1, p2=p2, angle=90,
                                   dimstyle="EZDXF", override={"dimtxt": 90, "dimasz": 60})
        else:
            d = msp.add_linear_dim(base=(0, p1[1] - base_offset), p1=p1, p2=p2,
                                   dimstyle="EZDXF", override={"dimtxt": 90, "dimasz": 60})
        d.render()

    # --- élévation ---
    x0, base = 0.0, 0.0
    _hatch_dxf(msp, x0, base, pier, op_h, "MACONNERIE")
    xr = x0 + pier + L + 2 * a
    _hatch_dxf(msp, xr, base, pier, op_h, "MACONNERIE")
    opx = x0 + pier
    _rect(msp, opx, base, L + 2 * a, op_h, "ABERTURA")
    _rect(msp, opx, base + op_h, L + 2 * a, 200.0, "PADIEIRA")
    msp.add_text(f"PADIEIRA — {geom.get('recommended', '').upper() or 'A DEFINIR'}",
                 dxfattribs={"layer": "TEXTO", "height": 120}).set_placement((opx + 60, base + op_h + 260))
    dim((opx + a, base), (opx + a + L, base), 350)              # portée L
    dim((opx, base), (opx + a, base), 650)                      # about gauche
    dim((opx + a + L, base), (opx + 2 * a + L, base), 650)      # about droite
    dim((x0, base), (x0, base + op_h), 350, vertical=True)      # hauteur indicative

    # --- coupe (décalée à droite) ---
    sx = xr + pier + 1200.0
    mat = geom.get("recommended")
    steel, rc = geom.get("steel"), geom.get("rc")
    msp.add_text("COUPE", dxfattribs={"layer": "TEXTO", "height": 120}).set_placement((sx, op_h + 100))
    if mat == "steel" and steel and steel.get("status") == "ok":
        from engines import structuro_profiles as profiles
        pd = profiles.PROFILE_DATA.get(steel.get("profile"), {})
        hmm, bmm = float(pd.get("h", 200)), float(pd.get("b", 100))
        tf = float(pd.get("tf", 10)); tw = float(pd.get("tw", 7))
        n = int(steel.get("count", 1))
        for i in range(n):
            bx = sx + i * (bmm + 150)
            _rect(msp, bx, 0, bmm, tf, "AÇO")                        # semelle inf
            _rect(msp, bx, hmm - tf, bmm, tf, "AÇO")                 # semelle sup
            _rect(msp, bx + bmm / 2 - tw / 2, tf, tw, hmm - 2 * tf, "AÇO")  # âme
        dim((sx, 0), (sx, hmm), 350, vertical=True)
        dim((sx, 0), (sx + bmm, 0), 350)
        msp.add_text(steel.get("label", ""), dxfattribs={"layer": "TEXTO", "height": 90}).set_placement((sx, -500))
    elif rc and rc.get("status") == "ok":
        b, hmm = float(rc.get("b_mm", 200)), float(rc.get("h_mm", 300))
        cover = 40.0
        _rect(msp, sx, 0, b, hmm, "AÇO")
        _rect(msp, sx + cover, 0 + cover, b - 2 * cover, hmm - 2 * cover, "ARMADURAS")  # cadre
        for k in range(3):
            cxk = sx + cover + 20 + k * (b - 2 * cover - 40) / 2.0
            msp.add_circle((cxk, cover + 30), float(rc.get("bar_mm", 12)) / 2.0, dxfattribs={"layer": "ARMADURAS"})
        dim((sx, 0), (sx, hmm), 350, vertical=True)
        dim((sx, 0), (sx + b, 0), 350)
        msp.add_text(rc.get("label", ""), dxfattribs={"layer": "TEXTO", "height": 90}).set_placement((sx, -500))

    msp.add_text(f'{name} — Rev. — NÃO EXECUTÓRIO, A VERIFICAR PELO ENGENHEIRO',
                 dxfattribs={"layer": "TEXTO", "height": 110}).set_placement((0, -900))

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
