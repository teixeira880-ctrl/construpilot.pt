"""PDF do estudo de moradia: nota de cálculo A4 + desenhos A3 (plantas de cofragem/armaduras por laje,
fundações, pormenores tipo: cintas, pilaretes, lintéis, muro de cave, escadas)."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engines.structuro_house import USE_LABEL, USE_Q

BRAND = colors.HexColor("#285541")
INK = colors.HexColor("#1f2933")
GREY = colors.HexColor("#6b7280")
WALL = colors.HexColor("#c9ced6")
RED = colors.HexColor("#b42318")
BLUE = colors.HexColor("#1d4ed8")
DISCLAIMER = ("PRÉ-DIMENSIONAMENTO AUTOMÁTICO ConstruPilot — NÃO EXECUTÓRIO sem verificação e assinatura de engenheiro civil. "
              "Ação sísmica NP EN 1998-1 não verificada.")


def _f(v, n=2):
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:,.{n}f}".replace(",", " ").replace(".", ",")
    return str(v)


# ====================================================================== NOTA A4
def _note_pdf(r: dict, project: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"Nota de cálculo — {project}")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, textColor=BRAND, spaceAfter=6)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5, textColor=BRAND, spaceBefore=8, spaceAfter=4)
    B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.8, leading=11.5)
    S = ParagraphStyle("s", parent=B, fontSize=7.6, leading=9.5, textColor=GREY)
    W = ParagraphStyle("w", parent=B, textColor=RED)

    def table(rows, widths=None, head=True):
        t = Table([[Paragraph(str(c), S if i and head else B) if not isinstance(c, Paragraph) else c for c in row]
                   for i, row in enumerate(rows)], colWidths=widths, repeatRows=1 if head else 0)
        st = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("FONTSIZE", (0, 0), (-1, -1), 7.6)]
        if head:
            st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ef"))]
        t.setStyle(TableStyle(st))
        return t

    g = r["geometry"]
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    story = [Paragraph("NOTA DE CÁLCULO ESTRUTURAL — PRÉ-DIMENSIONAMENTO", H1),
             Paragraph(f"<b>{project}</b> · {today} · motor {r['version']}", B),
             Spacer(1, 4), Paragraph(DISCLAIMER, W), Spacer(1, 6)]

    # 1 — Bases
    story += [Paragraph("1. Bases de cálculo e materiais", H2),
              Paragraph("Normas: NP EN 1990, NP EN 1991-1-1, NP EN 1992-1-1, NP EN 1996-3, NP EN 1997-1, com Anexos "
                        "Nacionais portugueses (valores nacionais marcados «a confirmar pelo projetista»). Combinações "
                        "ELU 1,35G + 1,5Q (+0,75 S); ELS característica G+Q; quase-permanente G+ψ2Q.", B),
              table([["Material", "Valor"], ["Betão", r["materials"]["concrete"]], ["Aço", r["materials"]["steel"]],
                     ["Recobrimentos", r["materials"]["cover"]], ["αcc", _f(r["materials"]["alpha_cc"])]],
                    widths=[45 * mm, 130 * mm])]
    # 2 — Geometria
    lv_rows = [["Piso", "Pé-direito (m)", "Utilização"]] + [[lv["name"], _f(lv["storey_height_m"]), USE_LABEL[lv["use"]]] for lv in g["levels"]]
    story += [Paragraph("2. Geometria considerada", H2),
              Paragraph(f"Implantação {_f(g['outer_L_m'])} × {_f(g['outer_W_m'])} m (fora a fora); paredes resistentes "
                        f"e = {_f(g['wall_thickness_m'])} m; sistema: {g['structure']}; cobertura: {g['roof']['type']}; "
                        f"cave: {'sim, ' + _f(g['basement']['height_m']) + ' m' if g['basement']['present'] else 'não'}. "
                        f"Paredes interiores resistentes em X = {', '.join(_f(x) for x in g['interior_walls_x']) or '—'} m; "
                        f"em Y = {', '.join(_f(y) for y in g['interior_walls_y']) or '—'} m.", B),
              table(lv_rows, widths=[45 * mm, 35 * mm, 95 * mm])]
    # 3 — Ações
    ld = g["loads"]
    story += [Paragraph("3. Ações", H2),
              table([["Ação", "Valor", "Origem"],
                     ["Peso próprio betão", "25 kN/m³", "NP EN 1991-1-1"],
                     ["Restantes cargas permanentes (pisos)", f"{_f(ld['g2_floor_kn_m2'])} kN/m²", "revestimentos + divisórias (hipótese)"],
                     ["Cobertura inclinada (em planta)", f"{_f(ld['roof_g_kn_m2'])} kN/m²", "telha + estrutura + isolamento (hipótese)"],
                     ["Alvenaria resistente", f"{_f(ld['masonry_kn_m2'])} kN/m²", "bloco 20 + rebocos (hipótese)"],
                     ["Neve", f"{_f(ld['snow_kn_m2'])} kN/m²", "NP EN 1991-1-3 (zona/altitude a confirmar)"]] +
                    [[f"Sobrecarga — {USE_LABEL[k]}", f"{_f(v[0])} kN/m² (ψ2={_f(v[1], 1)})", "NP EN 1991-1-1 AN PT (a confirmar)"]
                     for k, v in USE_Q.items()], widths=[70 * mm, 45 * mm, 60 * mm])]
    # 4 — Lajes
    story += [Paragraph("4. Lajes maciças armadas em duas direções", H2),
              Paragraph("Método de Pigeaud com regra de continuidade (Mt + (Mw+Me)/2 ≥ 1,25 M0); armaduras NP EN 1992-1-1 §6.1 "
                        "e §9.3; esbelteza L/d §7.4.2. Armadura inferior do vão menor por baixo.", B)]
    for s in r["slabs"]:
        rows = [["Painel", "lx×ly (m)", "h (m)", "pu (kN/m²)", "Inf. vão menor", "Inf. vão maior", "Sup. apoios cont.", "L/d (lim.)", "V ok"]]
        for d in s["panels"]:
            cont = [v for v in d["supports"].values() if v["type"] == "continu" and v["mesh"]]
            rows.append([d["id"], f"{_f(d['lx'])}×{_f(d['ly'])}", _f(d["h"]), _f(d["pu"]),
                         f"{d['mesh_short']['label']} ({_f(d['as_short'])} cm²/m)",
                         f"{d['mesh_long']['label']} ({_f(d['as_long'])})",
                         ", ".join(sorted({c["mesh"]["label"] for c in cont})) or "—",
                         f"{_f(d['ld']['l_over_d'], 1)} ({_f(d['ld']['limit'], 1)})", "sim" if d["shear"]["ok"] else "NÃO"])
        story += [Paragraph(f"<b>{s['name']}</b> — {USE_LABEL[s['use']]}, G2 = {_f(s['g2'])} kN/m², espessura adotada {_f(s['h'])} m", B),
                  table(rows, widths=[13 * mm, 22 * mm, 12 * mm, 16 * mm, 32 * mm, 26 * mm, 24 * mm, 18 * mm, 12 * mm]),
                  Spacer(1, 4)]
    # 5 — Descida de cargas
    rows = [["Alinhamento", "Tipo", "Comp. (m)", "G (kN/m)", "Q (kN/m)", "S (kN/m)", "N_ELS", "N_ELU"]]
    for k, d in r["descent"].items():
        f = d["foundation"]
        rows.append([k, d["kind"], _f(d["length_m"]), _f(f["g"], 1), _f(f["q"], 1), _f(f["s"], 1), _f(f["n_els"], 1), _f(f["n_elu"], 1)])
    story += [Paragraph("5. Descida de cargas (por metro de parede, ao nível da fundação)", H2),
              Paragraph("Reações das lajes pelos coeficientes BAEL E3 (bordos longos 1/(2+ρ)·lx, bordos curtos lx/3); "
                        "cobertura apoiada nas fachadas frente/trás; empenas com triângulo de alvenaria.", B),
              table(rows, widths=[24 * mm, 20 * mm, 18 * mm, 20 * mm, 20 * mm, 18 * mm, 20 * mm, 20 * mm])]
    if r["walls_check"]:
        rows = [["Alinhamento", "N_ELU base R/C (kN/m)", "N_Rd fb4", "N_Rd fb6", "N_Rd fb8", "Solução"]]
        for k, w in r["walls_check"].items():
            c = w["capacities"]
            rows.append([k, _f(w["n_elu_kn_m"], 1), _f(c["fb 4"]["nrd_kn_m"], 1), _f(c["fb 6"]["nrd_kn_m"], 1),
                         _f(c["fb 8"]["nrd_kn_m"], 1), w["choice"]])
        story += [Paragraph("6. Paredes de alvenaria resistente — NP EN 1996-3 §4.2.2 (método simplificado)", H2),
                  Paragraph("fk = K·fb^0,7·fm^0,3 (K=0,45, argamassa M10), γM = 2,5, hef = 0,75 h, Φs = 0,85 − 0,0011(hef/t)². "
                            "Classe dos blocos a confirmar pela ficha técnica do fabricante.", B),
                  table(rows, widths=[26 * mm, 34 * mm, 22 * mm, 22 * mm, 22 * mm, 50 * mm])]
        if r["ties"]:
            story += [Paragraph(f"Alvenaria confinada: cinta {r['ties']['cinta']}; pilarete {r['ties']['pilarete']}. {r['ties']['note']}", B)]
    # 7 — Fundações
    story += [Paragraph("7. Fundações — sapatas contínuas", H2)]
    if r["footings"]:
        rows = [["Alinhamento", "b (m)", "h (m)", "σ_ELS (kPa)", "q_ELS (kPa)", "Transversal", "Longitudinal"]]
        for k, f in r["footings"].items():
            rows.append([k, _f(f["b_m"]), _f(f["h_m"]), _f(f["sigma_els_kpa"], 0), _f(f["q_els_kpa"], 0), f["transv"], f["long"]])
        story += [Paragraph(f"Tensão admissível do estudo geotécnico: q_ELS = {_f(r['soil'].get('q_els_kpa'), 0)} kPa. Armadura "
                            "transversal pelo método das bielas (As = N_ELU(b−t)/(8·d·fyd)), mínimo Ø10//0,20; betão de limpeza 0,05 m.", B),
                  table(rows, widths=[26 * mm, 16 * mm, 16 * mm, 22 * mm, 22 * mm, 32 * mm, 30 * mm])]
    else:
        rows = [["q_ELS (kPa)"] + list(r["descent"].keys())] + [[str(t["q_els"])] + [_f(t[k]) for k in r["descent"]] for t in r["footing_table"]]
        story += [Paragraph("<b>Sem estudo geotécnico confirmado: larguras NÃO definitivas.</b> Larguras necessárias (m) em função da tensão admissível:", W),
                  table(rows)]
    # 8 — Lintéis
    if r["lintels"]:
        rows = [["Ref.", "Piso / fachada", "Vão livre", "b×h (m)", "M_ELU", "V_ELU", "Inferior", "Superior", "Estribos", "Flecha (lim.)"]]
        for li in r["lintels"]:
            if li.get("ok"):
                rows.append([li["rep"], f"{li['level']} / {li['facade']}", _f(li["clear"]), f"{_f(li['b'])}×{_f(li['h'])}",
                             _f(li["m"]), _f(li["v"]), li["bot"], li["top"], li["stirrups"], f"{_f(li['w_el_mm'], 1)} ({_f(li['w_lim_mm'], 1)}) mm"])
            else:
                rows.append([li["rep"], f"{li.get('level')} / {li.get('facade')}", _f(li["clear"]), "—", _f(li["m"]), _f(li["v"]),
                             "VIGA A DIMENSIONAR", "", "", ""])
        story += [Paragraph("8. Lintéis das aberturas", H2),
                  Paragraph("Viga simplesmente apoiada, vão = vão livre + 0,20 m, apoio ≥ 0,25 m sobre alvenaria com pilarete de "
                            "cada lado; carga = tudo o que chega ao topo da parede do piso (sem efeito de arco — a favor da segurança).", B),
                  table(rows, widths=[11 * mm, 27 * mm, 14 * mm, 17 * mm, 13 * mm, 13 * mm, 18 * mm, 15 * mm, 20 * mm, 24 * mm])]
    # 9 — Muros de cave
    if r["retaining"]:
        rt = r["retaining"]
        story += [Paragraph("9. Muros de cave", H2),
                  Paragraph(f"Impulso em repouso K0 = 1 − sin φ = {_f(rt['k0'], 3)} (φ = {_f(rt['phi'], 0)}°, γ = {_f(rt['gamma'], 0)} kN/m³, "
                            f"sobrecarga {_f(rt['surcharge'], 0)} kPa), altura {_f(rt['H_m'])} m, apoiado na laje e na sapata. "
                            f"M_ELU = {_f(rt['m_elu'])} kN·m/m, As = {_f(rt['as_req'])} cm²/m → face terra {rt['face_terra']}, face interior "
                            f"{rt['face_interior']}, horizontais {rt['horizontais']}. Impermeabilização + dreno periférico.", B)]
    # 10 — Escadas
    if r["stairs"]:
        rows = [["Lanço", "Altura (m)", "Degraus", "Espelho (mm)", "Cobertor (mm)", "Inclinação", "Laje", "Armadura principal", "Alertas"]]
        for s in r["stairs"]:
            if s.get("error"):
                rows.append([s["lanco"], "—", "—", "—", "—", "—", "—", "—", s["error"][:60]])
                continue
            rows.append([s["lanco"], _f(s["floor_height_m"]), s["risers"], _f(s["riser_mm"], 1), _f(s["giron_mm"], 1),
                         f"{_f(s['slope_deg'], 1)}°", f"{_f(s['t_m'])} m", s["main"]["label"], ", ".join(s["red_alerts"]) or "—"])
        story += [Paragraph("10. Escadas", H2),
                  Paragraph("Geometria pelo solver de caixa ConstruPilot (degraus em leque/patamar); laje da escada simplesmente "
                            "apoiada, Q = 3,0 kN/m² (AN PT a confirmar); distribuição Ø8//0,25, chapéus Ø8//0,20.", B),
                  table(rows, widths=[11 * mm, 16 * mm, 15 * mm, 19 * mm, 19 * mm, 17 * mm, 13 * mm, 27 * mm, 38 * mm])]
    # 11 — Medições
    q = r["quantities"]
    rows = [["Elemento", "Betão (m³)", "Aço A500 (kg)"]] + [[x["element"], _f(x.get("concrete_m3")), _f(x.get("steel_kg"), 0)] for x in q["rows"]]
    rows.append(["TOTAL", _f(q["concrete_m3"]), _f(q["steel_kg"], 0)])
    story += [Paragraph("11. Medições de betão e aço", H2), table(rows, widths=[95 * mm, 40 * mm, 40 * mm]),
              Paragraph(f"Rácio global ≈ {_f(q['ratio_kg_m3'], 1)} kg/m³. {q['note']}", S)]
    # 12 — Avisos
    story += [Paragraph("12. Avisos, limitações e próximos passos", H2)]
    story += [Paragraph("• " + w, W if ("NÃO" in w or "insuficiente" in w.lower()) else B) for w in r["warnings"]]
    story += [Spacer(1, 10), Paragraph("Projetista responsável (nome, n.º Ordem dos Engenheiros / OET, assinatura): "
                                       "________________________________", B)]

    def _footer(c, d):
        c.saveState()
        c.setFont("Helvetica", 6.8)
        c.setFillColor(GREY)
        c.drawString(16 * mm, 9 * mm, f"ConstruPilot · {project} · nota de cálculo de pré-dimensionamento")
        c.drawRightString(A4[0] - 16 * mm, 9 * mm, f"pág. {d.page}")
        c.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# ====================================================================== DESENHOS A3
class Sheet:
    W, H = landscape(A3)

    def __init__(self, c, project: str, title: str, code: str, scale: str, n: int, total_hint: str = ""):
        self.c, self.project, self.title = c, project, title
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.rect(10 * mm, 10 * mm, self.W - 20 * mm, self.H - 20 * mm)
        # cartouche
        x0, y0, w, h = self.W - 190 * mm, 10 * mm, 180 * mm, 34 * mm
        c.setFillColor(colors.white)
        c.rect(x0, y0, w, h, fill=1)
        c.setFillColor(BRAND)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x0 + 4 * mm, y0 + h - 7 * mm, "CONSTRUPILOT · ESTRUTURAS")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(x0 + 4 * mm, y0 + h - 13 * mm, title[:80])
        c.setFont("Helvetica", 8)
        c.drawString(x0 + 4 * mm, y0 + h - 18.5 * mm, project[:90])
        c.drawString(x0 + 4 * mm, y0 + h - 23.5 * mm, f"Folha {code} · escala {scale} · {datetime.now(timezone.utc):%d/%m/%Y} · rev. 0")
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 6.6)
        c.drawString(x0 + 4 * mm, y0 + 4 * mm, "PRÉ-DIMENSIONAMENTO — NÃO EXECUTÓRIO SEM VERIFICAÇÃO E ASSINATURA DE ENGENHEIRO")
        c.setFillColor(INK)
        self.area = (16 * mm, 50 * mm, self.W - 16 * mm, self.H - 16 * mm)

    def fit(self, L, Wd, reserve_right=0.0):
        x0, y0, x1, y1 = self.area
        x1 -= reserve_right
        sc = min((x1 - x0 - 30 * mm) / L, (y1 - y0 - 30 * mm) / Wd)
        ox = x0 + 18 * mm
        oy = y0 + 18 * mm
        return sc, ox, oy


def _dim(c, x1, y1, x2, y2, txt, off=6 * mm, horizontal=True):
    c.saveState()
    c.setStrokeColor(GREY)
    c.setFillColor(GREY)
    c.setLineWidth(0.4)
    c.setFont("Helvetica", 7)
    if horizontal:
        y = y1 - off
        c.line(x1, y, x2, y)
        for x in (x1, x2):
            c.line(x - 1.5, y - 1.5, x + 1.5, y + 1.5)
            c.line(x, y1, x, y - 2)
        c.drawCentredString((x1 + x2) / 2, y + 1.5, txt)
    else:
        x = x1 - off
        c.line(x, y1, x, y2)
        for y in (y1, y2):
            c.line(x - 1.5, y - 1.5, x + 1.5, y + 1.5)
            c.line(x1, y, x - 2, y)
        c.saveState()
        c.translate(x - 1.5, (y1 + y2) / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, txt)
        c.restoreState()
    c.restoreState()


def _walls(c, g, sc, ox, oy):
    L, Wd, t = g["outer_L_m"], g["outer_W_m"], g["wall_thickness_m"]
    c.setFillColor(WALL)
    c.setStrokeColor(INK)
    c.setLineWidth(0.6)
    rects = [(0, 0, L, t), (0, Wd - t, L, t), (0, 0, t, Wd), (L - t, 0, t, Wd)]
    rects += [(x - t / 2, 0, t, Wd) for x in g["interior_walls_x"]]
    rects += [(0, y - t / 2, L, t) for y in g["interior_walls_y"]]
    for x, y, w, h in rects:
        c.rect(ox + x * sc, oy + y * sc, w * sc, h * sc, fill=1, stroke=1)
    c.setFillColor(INK)


def _slab_sheet(c, r, s, project, n):
    g = r["geometry"]
    sh = Sheet(c, project, f"Cofragem e armaduras — {s['name']}", f"E{n:02d}", "conforme", n)
    L, Wd = g["outer_L_m"], g["outer_W_m"]
    sc, ox, oy = sh.fit(L, Wd, reserve_right=120 * mm)
    _walls(c, g, sc, ox, oy)
    # painéis
    for d in s["panels"]:
        p = d["geom"]
        cx, cy = ox + (p["x0"] + p["x1"]) / 2 * sc, oy + (p["y0"] + p["y1"]) / 2 * sc
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(BRAND)
        c.drawCentredString(cx, cy + 16, f"Laje {d['id']} — h = {d['h']:.2f} m".replace(".", ","))
        c.setFont("Helvetica", 7.5)
        c.setFillColor(INK)
        short = d["short_dir"]
        c.drawCentredString(cx, cy + 4, f"Inf. {short} (vão menor): {d['mesh_short']['label']}")
        c.drawCentredString(cx, cy - 6, f"Inf. {'Y' if short == 'X' else 'X'}: {d['mesh_long']['label']}")
        # seta de armadura principal
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        if short == "X":
            xa, xb = ox + (p["x0"] + 0.25) * sc, ox + (p["x1"] - 0.25) * sc
            c.line(xa, cy - 16, xb, cy - 16)
            c.line(xa, cy - 19, xa, cy - 13); c.line(xb, cy - 19, xb, cy - 13)
        else:
            ya, yb = oy + (p["y0"] + 0.25) * sc, oy + (p["y1"] - 0.25) * sc
            c.line(cx - 40, ya, cx - 40, yb)
            c.line(cx - 43, ya, cx - 37, ya); c.line(cx - 43, yb, cx - 37, yb)
        # chapéus nos apoios contínuos
        c.setStrokeColor(RED)
        c.setLineWidth(0.9)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(RED)
        for side, sp in d["supports"].items():
            if sp["type"] != "continu" or not sp["mesh"]:
                continue
            ln = sp["len"] or 0.5
            # side em coordenadas lx/ly → referencial do edifício
            axis_x = (side.startswith("x") and short == "X") or (side.startswith("y") and short == "Y")
            if axis_x:
                xw = p["x0"] if side.endswith("0") else p["x1"]
                xi = ox + xw * sc + (ln * sc if side.endswith("0") else -ln * sc)
                c.line(ox + xw * sc, cy + 30, xi, cy + 30)
                c.drawString(min(ox + xw * sc, xi) + 2, cy + 33, f"sup. {sp['mesh']['label']} L={ln:.2f}".replace(".", ","))
            else:
                yw = p["y0"] if side.endswith("0") else p["y1"]
                yi = oy + yw * sc + (ln * sc if side.endswith("0") else -ln * sc)
                c.line(cx + 50, oy + yw * sc, cx + 50, yi)
                c.drawString(cx + 53, (oy + yw * sc + yi) / 2, f"sup. {sp['mesh']['label']} L={ln:.2f}".replace(".", ","))
        c.setFillColor(INK)
    # cotas
    _dim(c, ox, oy, ox + L * sc, oy, f"{L:.2f}".replace(".", ","))
    _dim(c, ox, oy, ox, oy + Wd * sc, f"{Wd:.2f}".replace(".", ","), horizontal=False)
    xs = [0.0] + g["interior_walls_x"] + [L]
    for a, b in zip(xs, xs[1:]):
        _dim(c, ox + a * sc, oy + Wd * sc, ox + b * sc, oy + Wd * sc, f"{b - a:.2f}".replace(".", ","), off=-8 * mm)
    c.setFont("Helvetica", 7)
    c.drawString(ox, oy + Wd * sc + 14 * mm, "FRENTE em baixo · X = comprimento · Y = largura · cotas em m, eixos/faces exteriores")
    # legenda à direita
    x = Sheet.W - 128 * mm
    y = Sheet.H - 30 * mm
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(BRAND)
    c.drawString(x, y, "NOTAS")
    c.setFillColor(INK)
    c.setFont("Helvetica", 7.4)
    notes = [f"Laje maciça C25/30, A500 NR, recobrimento 25 mm.", f"Utilização: {USE_LABEL[s['use']]}; G2 = {s['g2']:.2f} kN/m².".replace(".", ","),
             "Armadura inferior do vão menor por baixo (1.ª camada).", "Azul: direção da armadura principal inferior.",
             "Vermelho: armadura superior (chapéus) sobre apoios contínuos,", "   comprimento medido a partir da face do apoio.",
             "Bordos de rive: armadura superior mínima Ø8//0,25 L=0,60 m.",
             "Cinta 0,20×0,20 4Ø10 + Ø6//0,20 em todo o perímetro e paredes resistentes.",
             "Aberturas na laje (escada, courettes): reforço 2Ø12 em cada bordo.",
             "Escoramento a manter até f_c ≥ 70 % f_ck (mín. 14 dias).", "", "Painéis:"]
    for d in s["panels"]:
        notes.append(f" {d['id']}: {d['lx']:.2f}×{d['ly']:.2f} m, L/d {d['ld']['l_over_d']:.1f} ≤ {d['ld']['limit']:.1f}".replace(".", ","))
    for i, t in enumerate(notes):
        c.drawString(x, y - 12 - i * 10, t)
    c.showPage()


def _foundation_sheet(c, r, project, n):
    g = r["geometry"]
    sh = Sheet(c, project, "Planta de fundações — sapatas contínuas", f"F{n:02d}", "conforme", n)
    L, Wd = g["outer_L_m"], g["outer_W_m"]
    sc, ox, oy = sh.fit(L, Wd, reserve_right=120 * mm)
    fts = r["footings"]
    # sapatas (retângulos de largura b centrados nos alinhamentos)
    c.setStrokeColor(BRAND)
    c.setFillColor(colors.HexColor("#e7efe9"))
    t = g["wall_thickness_m"]
    for key, d in r["descent"].items():
        b = fts.get(key, {}).get("b_m") or 0.6
        if d["axis"] == "X":
            y = (t / 2 if d["pos"] == 0 else (Wd - t / 2 if d["kind"] == "fachada" else d["pos"]))
            c.rect(ox - b / 2 * sc, oy + (y - b / 2) * sc, (L + b) * sc, b * sc, fill=1, stroke=1)
        else:
            x = (t / 2 if d["pos"] == 0 else (L - t / 2 if d["kind"] == "empena" else d["pos"]))
            c.rect(ox + (x - b / 2) * sc, oy - b / 2 * sc, b * sc, (Wd + b) * sc, fill=1, stroke=1)
    _walls(c, g, sc, ox, oy)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(BRAND)
    for key, d in r["descent"].items():
        f = fts.get(key)
        lab = f"SC-{key}: b={f['b_m']:.2f} h={f['h_m']:.2f} {f['transv']} + {f['long']}".replace(".", ",") if f else f"SC-{key}: a dimensionar (sem G2)"
        if d["axis"] == "X":
            y = 0 if d["pos"] == 0 else d["pos"]
            c.drawString(ox + 4 * mm, oy + y * sc + (8 if d["pos"] == 0 else -12), lab)
        else:
            x = d["pos"]
            c.saveState()
            c.translate(ox + x * sc + (12 if d["pos"] == 0 else -4), oy + 10 * mm)
            c.rotate(90)
            c.drawString(0, 0, lab)
            c.restoreState()
    c.setFillColor(INK)
    _dim(c, ox, oy, ox + L * sc, oy, f"{L:.2f}".replace(".", ","), off=12 * mm)
    _dim(c, ox, oy, ox, oy + Wd * sc, f"{Wd:.2f}".replace(".", ","), off=12 * mm, horizontal=False)
    # corte tipo
    x, y = Sheet.W - 125 * mm, Sheet.H - 40 * mm
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(BRAND)
    c.drawString(x, y, "CORTE TIPO — SAPATA CONTÍNUA (1:20)")
    c.setFillColor(INK)
    f0 = next(iter(fts.values()), {"b_m": 0.60, "h_m": 0.30, "transv": "Ø10//0,20", "long": "4Ø10"})
    s20 = 48 * mm
    bx, by = x + 10 * mm, y - 95 * mm
    c.setFillColor(colors.HexColor("#eeeeee"))
    c.rect(bx - 0.05 * s20, by - 0.05 * s20, (f0["b_m"] + 0.10) * s20, 0.05 * s20, fill=1)          # betão de limpeza
    c.setFillColor(colors.HexColor("#e7efe9"))
    c.rect(bx, by, f0["b_m"] * s20, f0["h_m"] * s20, fill=1)
    tw = r["geometry"]["wall_thickness_m"]
    c.setFillColor(WALL)
    c.rect(bx + (f0["b_m"] - tw) / 2 * s20, by + f0["h_m"] * s20, tw * s20, 0.6 * s20, fill=1)
    c.setStrokeColor(RED)
    c.setLineWidth(1.4)
    c.line(bx + 0.05 * s20, by + 0.05 * s20, bx + (f0["b_m"] - 0.05) * s20, by + 0.05 * s20)
    c.setFillColor(RED)
    for k in range(4):
        c.circle(bx + (0.08 + k * (f0["b_m"] - 0.16) / 3) * s20, by + 0.08 * s20, 2.2, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica", 7.5)
    c.drawString(bx, by - 0.12 * s20, f"b = {f0['b_m']:.2f} m · h = {f0['h_m']:.2f} m · betão de limpeza 0,05 m".replace(".", ","))
    c.drawString(bx, by - 0.12 * s20 - 10, f"Transversal {f0['transv']} (inferior) · longitudinal {f0['long']}")
    c.drawString(bx, by - 0.12 * s20 - 20, "Recobrimento 50 mm · arranques Ø10 dos pilaretes/paredes, L = 50 Ø")
    if not fts:
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(Sheet.W / 2 - 80 * mm, 60 * mm, "SEM ESTUDO GEOTÉCNICO: larguras a definir — ver tabela na nota de cálculo.")
    c.showPage()


def _details_sheet(c, r, project, n):
    Sheet(c, project, "Pormenores tipo — cintas, pilaretes, lintéis, muro de cave, escadas", f"D{n:02d}", "1:20 / s.e.", n)
    s = 40 * mm      # 1:25 aprox.

    def section(x, y, b, h, n_bars, dia_lbl, title, extra):
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(BRAND)
        c.drawString(x, y + h * s + 14, title)
        c.setFillColor(colors.HexColor("#f3f4f6"))
        c.setStrokeColor(INK)
        c.rect(x, y, b * s, h * s, fill=1)
        c.setStrokeColor(RED)
        c.rect(x + 0.03 * s, y + 0.03 * s, (b - 0.06) * s, (h - 0.06) * s)
        c.setFillColor(RED)
        pts = [(0.05, 0.05), (b - 0.05, 0.05), (0.05, h - 0.05), (b - 0.05, h - 0.05)][:n_bars]
        for px, py in pts:
            c.circle(x + px * s, y + py * s, 2.4, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica", 7.2)
        for i, t in enumerate([f"{b:.2f}×{h:.2f} m".replace(".", ","), dia_lbl] + extra):
            c.drawString(x + b * s + 6, y + h * s - 8 - i * 9, t)

    section(30 * mm, Sheet.H - 90 * mm, 0.20, 0.20, 4, "4Ø10 + est. Ø6//0,20", "CINTA (todos os pisos)", ["amarração nos cantos 50 Ø", "emenda por sobreposição 60 Ø"])
    section(120 * mm, Sheet.H - 90 * mm, 0.20, 0.20, 4, "4Ø12 + est. Ø6//0,15", "PILARETE DE CONFINAMENTO", ["cantos, cruzamentos e aberturas > 1,5 m", "arranque da sapata, emenda 50 Ø"])
    # lintéis — tabela
    x, y = 30 * mm, Sheet.H - 120 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(BRAND)
    c.drawString(x, y, "LINTÉIS (b = espessura da parede; apoio ≥ 0,25 m de cada lado)")
    c.setFillColor(INK)
    c.setFont("Helvetica", 7.2)
    hdr = ["Ref.", "Piso / fachada", "Vão livre", "b×h", "Inferior", "Superior", "Estribos"]
    cols = [0, 14, 52, 70, 92, 115, 135]
    for i, h_ in enumerate(hdr):
        c.drawString(x + cols[i] * mm, y - 12, h_)
    for k, li in enumerate([li for li in r["lintels"]][:16]):
        yy = y - 22 - k * 9
        vals = [li["rep"], f"{li.get('level')} / {li.get('facade')}", f"{li['clear']:.2f}".replace(".", ","),
                f"{li['b']:.2f}×{li['h']:.2f}".replace(".", ",") if li.get("ok") else "—",
                li.get("bot", "VIGA"), li.get("top", "—"), li.get("stirrups", "—")]
        for i, v in enumerate(vals):
            c.drawString(x + cols[i] * mm, yy, str(v)[:26])
    if not r["lintels"]:
        c.drawString(x, y - 22, "Sem aberturas indicadas — lintéis a definir com as plantas de arquitetura.")
    # muro de cave
    rt = r.get("retaining")
    x2 = 210 * mm
    if rt:
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(BRAND)
        c.drawString(x2, Sheet.H - 40 * mm, "MURO DE CAVE (corte)")
        c.setFillColor(INK)
        hh = rt["H_m"] * 30 * mm
        c.setFillColor(colors.HexColor("#f3f4f6"))
        c.rect(x2 + 10 * mm, Sheet.H - 50 * mm - hh, 6 * mm, hh, fill=1)
        c.setStrokeColor(RED)
        c.line(x2 + 10 * mm + 1.2 * mm, Sheet.H - 50 * mm - hh + 2, x2 + 10 * mm + 1.2 * mm, Sheet.H - 52 * mm)
        c.line(x2 + 16 * mm - 1.2 * mm, Sheet.H - 50 * mm - hh + 2, x2 + 16 * mm - 1.2 * mm, Sheet.H - 52 * mm)
        c.setFillColor(INK)
        c.setFont("Helvetica", 7.2)
        for i, t in enumerate([f"e = {rt['t_m']:.2f} m, H = {rt['H_m']:.2f} m".replace(".", ","), f"face terra: {rt['face_terra']}",
                               f"face interior: {rt['face_interior']}", f"horizontais: {rt['horizontais']}",
                               "impermeabilização + membrana pitonada + dreno"]):
            c.drawString(x2 + 22 * mm, Sheet.H - 56 * mm - i * 9, t)
    # escadas
    st = [s for s in r["stairs"] if not s.get("error")]
    if st:
        x3, y3 = 210 * mm, Sheet.H - 140 * mm
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(BRAND)
        c.drawString(x3, y3 + 10, "ESCADAS — laje e armaduras")
        c.setFillColor(INK)
        s0 = st[0]
        n = s0["risers"]
        sx, sy = 2.4 * mm, 2.4 * mm
        px, py = x3, y3 - 75 * mm
        c.setStrokeColor(INK)
        for k in range(n):
            c.line(px + k * s0["giron_mm"] / 100 * sx, py + k * s0["riser_mm"] / 100 * sy,
                   px + k * s0["giron_mm"] / 100 * sx, py + (k + 1) * s0["riser_mm"] / 100 * sy)
            c.line(px + k * s0["giron_mm"] / 100 * sx, py + (k + 1) * s0["riser_mm"] / 100 * sy,
                   px + (k + 1) * s0["giron_mm"] / 100 * sx, py + (k + 1) * s0["riser_mm"] / 100 * sy)
        c.setStrokeColor(RED)
        c.setLineWidth(1.2)
        c.line(px + 4, py - 8, px + n * s0["giron_mm"] / 100 * sx + 4, py + n * s0["riser_mm"] / 100 * sy - 8)
        c.setLineWidth(0.8)
        c.setFont("Helvetica", 7.2)
        c.setFillColor(INK)
        for i, s in enumerate(st):
            c.drawString(x3 + 95 * mm, y3 - 10 - i * 30,
                         f"Lanço {s['lanco']}: {s['risers']} espelhos {s['riser_mm']:.0f} mm, cobertor {s['giron_mm']:.0f} mm, {s['slope_deg']:.0f}°")
            c.drawString(x3 + 95 * mm, y3 - 19 - i * 30, f"laje {s['t_m']:.2f} m: principal {s['main']['label']} · distr. {s['dist']} · chapéus {s['chapeaux']}".replace("0.15", "0,15"))
    c.showPage()


def build_pdf(r: dict, project: str) -> bytes:
    note = _note_pdf(r, project)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A3))
    c.setTitle(f"Desenhos — {project}")
    n = 1
    for s in r["slabs"]:
        _slab_sheet(c, r, s, project, n)
        n += 1
    _foundation_sheet(c, r, project, 1)
    _details_sheet(c, r, project, 1)
    c.save()
    w = PdfWriter()
    for src in (note, buf.getvalue()):
        for p in PdfReader(io.BytesIO(src)).pages:
            w.add_page(p)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()
