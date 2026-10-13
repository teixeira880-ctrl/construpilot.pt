"""Génération du dossier technique PDF (reportlab, A4 portrait, 6 pages max)."""
from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Table, TableStyle, Paragraph


PRIMARY = colors.HexColor("#0B5FFF")
INK = colors.HexColor("#1A1D22")
MUTED = colors.HexColor("#5A6270")
WARN = colors.HexColor("#E38B1E")
DANGER = colors.HexColor("#D64545")
OK = colors.HexColor("#2F8F55")
BORDER = colors.HexColor("#D6D9DE")


def _header(c: pdfcanvas.Canvas, page_num: int, title: str, project_name: str, author: Optional[str]):
    W, H = A4
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 14)
    c.drawString(15 * mm, H - 15 * mm, "STAIRPILOT")
    c.setFont("Helvetica", 8); c.setFillColor(MUTED)
    c.drawString(15 * mm, H - 20 * mm, "Processo técnico de escada de betão — RGEU / DL 163/2006 / NP EN 1992")
    c.setFillColor(INK); c.setFont("Helvetica", 8)
    c.drawRightString(W - 15 * mm, H - 15 * mm, project_name)
    c.setFillColor(MUTED)
    if author:
        c.drawRightString(W - 15 * mm, H - 20 * mm, author)
    c.setStrokeColor(BORDER); c.setLineWidth(0.4)
    c.line(15 * mm, H - 22 * mm, W - 15 * mm, H - 22 * mm)
    c.setFillColor(PRIMARY); c.setFont("Helvetica-Bold", 12)
    c.drawString(15 * mm, H - 30 * mm, title)


def _footer(c: pdfcanvas.Canvas, page_num: int, total: int):
    W, _ = A4
    c.setStrokeColor(BORDER); c.setLineWidth(0.4)
    c.line(15 * mm, 18 * mm, W - 15 * mm, 18 * mm)
    c.setFont("Helvetica", 7); c.setFillColor(MUTED)
    c.drawString(15 * mm, 14 * mm, datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M"))
    c.drawRightString(W - 15 * mm, 14 * mm, f'Página {page_num}/{total}')
    c.drawCentredString(W / 2, 14 * mm, "Gerado pelo STAIRPILOT — indicativo, validação pelo gabinete de projeto obrigatória")


def _kv_table(pairs, col_widths=(85 * mm, 85 * mm)):
    tbl = Table(pairs, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (1, 0), (1, -1), "Courier-Bold", 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tbl


def _dim_h(c, x1, x2, y, label, above=True):
    """Ligne de cote horizontale avec pattes et label centré."""
    c.setStrokeColor(MUTED); c.setLineWidth(0.4)
    c.line(x1, y, x2, y)
    for xx in (x1, x2):
        c.line(xx, y - 2, xx, y + 2)
    c.setFillColor(MUTED); c.setFont("Helvetica", 6.5)
    c.drawCentredString((x1 + x2) / 2, y + (2 if above else -6), label)


def _dim_v(c, x, y1, y2, label, right=True):
    """Ligne de cote verticale avec pattes et label."""
    c.setStrokeColor(MUTED); c.setLineWidth(0.4)
    c.line(x, y1, x, y2)
    for yy in (y1, y2):
        c.line(x - 2, yy, x + 2, yy)
    c.setFillColor(MUTED); c.setFont("Helvetica", 6.5)
    c.saveState(); c.translate(x + (3 if right else -3), (y1 + y2) / 2); c.rotate(90)
    c.drawCentredString(0, 0, label); c.restoreState()


def _draw_stair_plan(c: pdfcanvas.Canvas, x0: float, y0: float, w: float, h: float,
                     result: Dict[str, Any], stair_input: Dict[str, Any]):
    """Vue en plan de la volée qui SUIT la ligne de foulée : marches droites, balancées
    (winders, via angle_deg) et paliers entre volées — conforme au type d'escalier."""
    c.setStrokeColor(BORDER); c.rect(x0, y0, w, h)
    g = result.get("tread_depth_mm", 280)
    stair_width = stair_input.get("stair_width_mm", 900)
    treads = result.get("treads") or []
    stype = (result.get("stair_type") or "straight").lower()
    flights = list(result.get("steps_per_flight") or []) or [result.get("num_treads", 15)]
    has_winders = any(abs((t.get("angle_deg") or 0)) > 0.01 for t in treads)
    total_turn = 180 if ("half" in stype or "demi" in stype) else (90 if ("quarter" in stype or "quart" in stype) else 0)
    landing_turn = (total_turn / (len(flights) - 1)) if (not has_winders and len(flights) > 1) else 0
    sign = -1 if stair_input.get("direction") == "right" else 1

    # 1) Construire les quads (mm) en parcourant la ligne de foulée
    quads = []      # (points[4], is_landing)
    marks = []      # (midx, midy, label)
    px, py, theta, idx = 0.0, 0.0, 0.0, 0
    hw = stair_width / 2.0

    def cell(depth, landing=False):
        nonlocal px, py
        fx, fy = math.cos(theta), math.sin(theta)
        ex, ey = math.sin(theta), -math.cos(theta)  # perp (droite)
        sL = (px + ex * hw, py + ey * hw); sR = (px - ex * hw, py - ey * hw)
        qx, qy = px + fx * depth, py + fy * depth
        eL = (qx + ex * hw, qy + ey * hw); eR = (qx - ex * hw, qy - ey * hw)
        quads.append(([sL, sR, eR, eL], landing))
        if not landing:
            marks.append((px + fx * depth / 2, py + fy * depth / 2, str(idx + 1)))
        px, py = qx, qy

    for fi, count in enumerate(flights):
        for _k in range(int(count)):
            t = treads[idx] if idx < len(treads) else None
            depth = (t.get("depth_walkline_mm") if t else None) or g
            ang = (t.get("angle_deg") if t else 0) or 0
            cell(depth)
            idx += 1
            if abs(ang) > 0.01:
                theta += sign * math.radians(ang)
        if fi < len(flights) - 1 and not has_winders:
            cell(stair_width, landing=True)
            if landing_turn:
                theta += sign * math.radians(landing_turn)
            ex, ey = math.sin(theta), -math.cos(theta)
            px += ex * stair_width * sign; py += ey * stair_width * sign

    # 2) Bbox + échelle pour tenir dans le cadre
    pts = [p for q, _ in quads for p in q]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    dx = max(1.0, max(xs) - min(xs)); dy = max(1.0, max(ys) - min(ys))
    margin = 24
    s = min((w - 2 * margin) / dx, (h - 2 * margin) / dy)
    ox = x0 + (w - dx * s) / 2 - min(xs) * s
    oy = y0 + (h - dy * s) / 2 - min(ys) * s
    T = lambda p: (ox + p[0] * s, oy + p[1] * s)

    # 3) Dessin
    for q, landing in quads:
        path = c.beginPath()
        a = T(q[0]); path.moveTo(*a)
        for p in q[1:]:
            path.lineTo(*T(p))
        path.close()
        if landing:
            c.setFillColor(colors.HexColor("#f1ece6")); c.setStrokeColor(INK); c.setLineWidth(1)
            c.drawPath(path, stroke=1, fill=1)
        else:
            c.setStrokeColor(INK); c.setLineWidth(0.9)
            c.drawPath(path, stroke=1, fill=0)
    # ligne de foulée
    if len(marks) >= 2:
        c.setStrokeColor(PRIMARY); c.setLineWidth(0.7); c.setDash(3, 2)
        wl = c.beginPath(); wl.moveTo(*T((marks[0][0], marks[0][1])))
        for m in marks[1:]:
            wl.lineTo(*T((m[0], m[1])))
        c.drawPath(wl, stroke=1, fill=0); c.setDash()
    # numérotation
    c.setFillColor(MUTED); c.setFont("Helvetica", 5.5)
    for mx, my, lab in marks:
        tx, ty = T((mx, my)); c.drawCentredString(tx, ty - 2, lab)
    # repère montée
    c.setFillColor(PRIMARY); c.setFont("Helvetica-Bold", 7)
    c.drawString(x0 + 6, y0 + h - 12, f"↑ SUBIDA · {stype.replace('_', ' ')}")
    # cotes principales
    c.setFillColor(MUTED); c.setFont("Helvetica", 6)
    c.drawString(x0 + 6, y0 + 6, f"giron {int(g)} mm · largura {int(stair_width)} mm · {result.get('num_treads', len(marks))} girons")


def _draw_stair_section(c: pdfcanvas.Canvas, x0: float, y0: float, w: float, h: float,
                        result: Dict[str, Any], stair_input: Dict[str, Any]):
    """Coupe longitudinale cotée : hauteur totale, reculement, hauteur de marche, giron."""
    n = result.get("num_steps", 16)
    g = result.get("tread_depth_mm", 280)
    hr = result.get("riser_height_mm", 175)
    H = stair_input.get("floor_height_mm", n * hr)
    total_len = max(1, (n - 1) * g)
    c.setStrokeColor(BORDER); c.rect(x0, y0, w, h)
    margin = 26
    sx = (w - 2 * margin) / max(1, total_len)
    sy = (h - 2 * margin) / max(1, H)
    s = min(sx, sy)
    ox = x0 + margin
    oy = y0 + margin
    c.setStrokeColor(INK); c.setLineWidth(1)
    path = c.beginPath()
    path.moveTo(ox, oy)
    for i in range(1, n + 1):
        xx = ox + (i - 1) * g * s
        yl = oy + (i - 1) * hr * s
        yh = oy + i * hr * s
        path.lineTo(xx, yl)
        path.lineTo(xx, yh)
        nx = ox + (i * g if i < n else (i - 1) * g) * s
        path.lineTo(nx, yh)
    c.drawPath(path, stroke=1, fill=0)
    # niveaux
    c.setStrokeColor(PRIMARY); c.setLineWidth(0.4); c.setDash(2, 2)
    c.line(ox - 4, oy, ox + total_len * s + 20, oy)
    c.line(ox - 4, oy + H * s, ox + total_len * s + 20, oy + H * s)
    c.setDash()
    c.setFillColor(PRIMARY); c.setFont("Helvetica", 6.5)
    c.drawString(ox + total_len * s + 2, oy - 2, "± 0.00")
    c.drawString(ox + total_len * s + 2, oy + H * s - 2, f"+{(H/1000):.2f}")
    # cotes
    _dim_v(c, ox - 12, oy, oy + H * s, f'H total = {int(H)} mm')
    _dim_h(c, ox, ox + total_len * s, oy - 12, f"reculement = {int(total_len)} mm", above=False)
    _dim_v(c, ox + total_len * s + 14, oy, oy + hr * s, f"h {int(hr)}")
    _dim_h(c, ox, ox + g * s, oy + H * s + 8, f"giron {int(g)}")



def generate_dossier_pdf(
    project_name: str,
    stair_input: Dict[str, Any],
    stair_result: Dict[str, Any],
    concrete_analysis: Optional[Dict[str, Any]] = None,
    author: Optional[str] = None,
) -> bytes:
    """Génère le dossier PDF complet et retourne les bytes."""
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    W, H = A4
    total_pages = 5 if concrete_analysis else 3

    # ==================== Page 1 — Fiche projet ====================
    _header(c, 1, "Fiche projet", project_name, author)
    y = H - 40 * mm
    pairs = [
        ["Tipo de escada", stair_result.get("stair_type", "—")],
        ["Número de degraus", str(stair_result.get("num_steps", "—"))],
        ["Altura do espelho", f"{stair_result.get('riser_height_mm', '—')} mm"],
        ["Cobertor", f"{stair_result.get('tread_depth_mm', '—')} mm"],
        ["Fórmula de Blondel (2h+g)", f"{stair_result.get('blondel_value_mm', '—')} mm"],
        ["Inclinação", f"{stair_result.get('slope_deg', '—')} °"],
        ["Desenvolvimento real", f"{stair_result.get('stair_run_mm', '—')} mm"],
        ["Comprimento do lanço", f"{stair_result.get('stair_length_mm', '—')} mm"],
        ["Altura livre", f"{stair_result.get('headroom_mm', '—')} mm"],
        ["Conforme", "Sim" if stair_result.get("is_buildable") else "NÃO — não utilizar em habitação"],
    ]
    tbl = _kv_table(pairs)
    tbl.wrapOn(c, W - 30 * mm, y); tbl.drawOn(c, 15 * mm, y - tbl._height)
    y2 = y - tbl._height - 8 * mm
    c.setFont("Helvetica-Bold", 10); c.setFillColor(INK)
    c.drawString(15 * mm, y2, "Alertas")
    c.setFont("Helvetica", 8)
    y2 -= 5 * mm
    for a in (stair_result.get("alerts") or [])[:8]:
        col = {"red": DANGER, "orange": WARN, "green": OK}.get(a.get("level"), INK)
        c.setFillColor(col); c.circle(17 * mm, y2 + 1, 1.2, fill=1, stroke=0)
        c.setFillColor(INK)
        msg = (a.get("message") or a.get("message_fr") or "")[:110]
        c.drawString(21 * mm, y2, f"[{a.get('code','')}] {msg}")
        y2 -= 5 * mm
    _footer(c, 1, total_pages); c.showPage()

    # ==================== Page 2 — Plan technique ====================
    _header(c, 2, "Desenho técnico cotado", project_name, author)
    _draw_stair_plan(c, 15 * mm, 100 * mm, W - 30 * mm, 130 * mm, stair_result, stair_input)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8)
    c.drawString(15 * mm, 90 * mm, "Vista em planta cotada (comprimento total, largura, cobertor). Documento indicativo — validação pelo gabinete de projeto necessária.")
    _footer(c, 2, total_pages); c.showPage()

    # ==================== Page 3 — Coupe longitudinale ====================
    _header(c, 3, "Coupe longitudinale", project_name, author)
    _draw_stair_section(c, 15 * mm, 100 * mm, W - 30 * mm, 130 * mm, stair_result, stair_input)
    c.setFillColor(MUTED); c.setFont("Helvetica", 8)
    c.drawString(15 * mm, 90 * mm, "Corte axial cotado (altura total, desenvolvimento, altura do degrau, cobertor).")
    _footer(c, 3, total_pages); c.showPage()

    # ==================== Page 4 — Métré béton (si concrete_analysis) ====================
    if concrete_analysis:
        _header(c, 4, "Medição de betão armado", project_name, author)
        q = concrete_analysis.get("quantities", {})
        p = concrete_analysis.get("paillasse", {})
        load = concrete_analysis.get("load_breakdown_kN_m2", {})
        pairs2 = [
            ["Volume total de betão", f"{q.get('concrete_volume_m3', 0)} m³"],
            ["Área de cofragem", f"{q.get('formwork_area_m2', 0)} m²"],
            ["Volume da laje da escada", f"{q.get('paillasse_volume_m3', 0)} m³"],
            ["Volume dos degraus", f"{q.get('tread_volume_m3', 0)} m³"],
            ["Espessura da laje da escada", f"{p.get('thickness_recommended_mm', 0)} mm"],
            ["Espessura mínima L/25", f"{p.get('thickness_min_L25_mm', 0)} mm"],
            ["Âmbito", f"{p.get('span_mm', 0)} mm"],
            ["Classe do betão", str(p.get('concrete_class', '—'))],
            ["Classe do aço", str(p.get('steel_grade', '—'))],
            ["Exposition", str(p.get('exposure_class', '—'))],
            ["Carga ELS total", f"{load.get('total_ELS', 0)} kN/m²"],
            ["Charge ELU (1.35G+1.5Q)", f"{load.get('total_ELU', 0)} kN/m²"],
        ]
        t = _kv_table(pairs2)
        t.wrapOn(c, W - 30 * mm, H - 40 * mm)
        t.drawOn(c, 15 * mm, H - 40 * mm - t._height)
        _footer(c, 4, total_pages); c.showPage()

        # ==================== Page 5 — Ferraillage + nomenclature ====================
        _header(c, 5, "Armaduras indicativas", project_name, author)
        nom = concrete_analysis.get("nomenclature", [])
        rf = concrete_analysis.get("reinforcement", {})
        data = [["Rep", "Designação", "Ø", "L (m)", "Nb", "Peso (kg)"]]
        for row in nom:
            data.append([
                str(row.get("repere", "")),
                str(row.get("designation", ""))[:38],
                str(row.get("diameter", "")),
                f"{row.get('total_length_m', 0):.1f}",
                str(row.get("count", 0)),
                f"{row.get('weight_kg', 0):.2f}",
            ])
        data.append(["", "TOTAL AÇO A500", "", "", "", f"{rf.get('total_steel_kg', 0)} kg"])
        tblf = Table(data, colWidths=[12 * mm, 70 * mm, 15 * mm, 18 * mm, 15 * mm, 25 * mm])
        tblf.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F6F8")),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
            ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
            ("LINEBELOW", (0, 1), (-1, -2), 0.3, BORDER),
            ("LINEABOVE", (0, -1), (-1, -1), 0.6, INK),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ]))
        tblf.wrapOn(c, W - 30 * mm, H - 40 * mm)
        tblf.drawOn(c, 15 * mm, H - 45 * mm - tblf._height)
        # Disclaimer bandeau
        y_disc = H - 60 * mm - tblf._height
        c.setFillColor(WARN); c.rect(15 * mm, y_disc - 20 * mm, W - 30 * mm, 20 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 9)
        c.drawString(18 * mm, y_disc - 6 * mm, "AVERTISSEMENT")
        c.setFont("Helvetica", 8)
        styles = getSampleStyleSheet()
        p_style = ParagraphStyle("d", parent=styles["Normal"], fontName="Helvetica",
                                 fontSize=8, textColor=colors.white, leading=10)
        para = Paragraph(concrete_analysis.get("disclaimer", {}).get("message_fr",
            "Pré-dimensionamento indicativo. Validação por engenheiro de estruturas obrigatória."), p_style)
        para.wrapOn(c, W - 40 * mm, 18 * mm)
        para.drawOn(c, 18 * mm, y_disc - 18 * mm)
        _footer(c, 5, total_pages); c.showPage()

    # ==================== Dernière page — Annexes ====================
    last = 5 if concrete_analysis else 3
    _header(c, last, "Anexos e menções legais", project_name, author)
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, H - 42 * mm, "Fórmulas utilizadas")
    c.setFont("Helvetica", 9); c.setFillColor(MUTED)
    lines = [
        "• Blondel : 2h + g ∈ [600, 640] mm (optimal), [580, 660] acceptable",
        "• Pesquisa do n.º de degraus: minimiza |h − 170| com h = H/n ∈ [160, 180] mm",
        "• Cobertor ótimo: g = 630 − 2h, limitado a [220, 320] mm",
        "• Secção de aço ELU: As = M / (0.9 × d × fyd), fyd = 435 MPa (A500/1.15)",
        "• Moment ELU : M = (1.35 G + 1.5 Q) × L² / 8",
        "• Comprimento de amarração: 40 × Ø (A500 em C25/30 condições normais)",
        "• Peso linear do aço A500: 0.006165 × d² kg/m",
    ]
    y = H - 50 * mm
    for l in lines:
        c.drawString(18 * mm, y, l); y -= 4.5 * mm
    y -= 4 * mm
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, y, "Normas de referência"); y -= 6 * mm
    c.setFont("Helvetica", 9); c.setFillColor(MUTED)
    for l in ["• RGEU — Regulamento Geral das Edificações Urbanas (escadas)", "• DL 163/2006 — Acessibilidades (percursos acessíveis)",
              "• Eurocódigo 2 (NP EN 1992-1-1) — Betão armado"]:
        c.drawString(18 * mm, y, l); y -= 4.5 * mm
    y -= 6 * mm
    c.setFillColor(DANGER); c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, y, "Menção legal"); y -= 6 * mm
    c.setFillColor(INK); c.setFont("Helvetica", 8)
    legal = ("Este processo é um pré-dimensionamento indicativo gerado pelo STAIRPILOT. Não substitui um estudo estrutural completo conforme com o Eurocódigo 2. Qualquer execução deve ser validada por um engenheiro de estruturas com as qualificações exigidas. O STAIRPILOT declina qualquer responsabilidade em caso de utilização sem validação profissional.")
    styles = getSampleStyleSheet()
    p_style = ParagraphStyle("legal", parent=styles["Normal"], fontName="Helvetica",
                             fontSize=8, textColor=INK, leading=11)
    para = Paragraph(legal, p_style)
    para.wrapOn(c, W - 30 * mm, 40 * mm)
    para.drawOn(c, 15 * mm, y - 32 * mm)
    _footer(c, last, total_pages)
    c.showPage()
    c.save()
    return buf.getvalue()
