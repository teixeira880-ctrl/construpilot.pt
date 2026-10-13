"""StructuroPilot — Note d'étude préliminaire (format du rapport de référence).

Génère une note structurée reprenant la trame d'un rapport d'étude structure
(cahier des charges → visite/relevés → étude → variantes → annexes → signature),
depuis le modèle tracé. TOUT ce qui dépend du moteur de calcul VERROUILLÉ
(sections, charges, flèches, résistances, dimensionnement) est explicitement
marqué « À CALCULER ». Aucune valeur n'est inventée : les données documentées
s'affichent, les inconnues apparaissent « à documenter ».
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable,
)

from engines import structuro_model as sm

INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
ACCENT = colors.HexColor("#334155")
WARN = colors.HexColor("#b45309")
WARN_BG = colors.HexColor("#fff7ed")
LINE = colors.HexColor("#cbd5e1")
BLUE = colors.HexColor("#1e3a8a")

TBD = "A CALCULAR — motor de verificação bloqueado"

# Variantes types à étudier (scénario ouverture dans mur porteur). Comparées, jamais calculées.
VARIANTS = [
    ("V1", "2 IPN 500", "Viga simplesmente apoiada nos nembos (sem pilar)"),
    ("V2", "2 IPN 240", "Viga simplesmente apoiada nos nembos (secção reduzida)"),
    ("V3", "2 HEA 240 + pilares de extremidade", "Viga sobre pilares de extremidade"),
    ("V4", "2 HEA 240 + pilar intermédio", "Vão reduzido por pilar central"),
]


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("CoverTitle", parent=ss["Title"], fontSize=24, leading=28,
                          textColor=BLUE, spaceAfter=6))
    ss.add(ParagraphStyle("CoverSub", parent=ss["Normal"], fontSize=11, leading=15,
                          textColor=MUTED, alignment=TA_CENTER))
    ss.add(ParagraphStyle("H1", parent=ss["Heading1"], fontSize=14, leading=18,
                          textColor=BLUE, spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("H2", parent=ss["Heading2"], fontSize=11.5, leading=15,
                          textColor=ACCENT, spaceBefore=8, spaceAfter=3))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=9.5, leading=13,
                          textColor=INK, spaceAfter=3))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, leading=10,
                          textColor=MUTED))
    ss.add(ParagraphStyle("Tbd", parent=ss["Normal"], fontSize=9.5, leading=13,
                          textColor=WARN, backColor=WARN_BG, borderPadding=2))
    return ss


def _fmt_datum(d: dict | None) -> str:
    if not d or d.get("value") in (None, ""):
        return "a documentar"
    v = f"{d.get('value')} {d.get('unit') or ''}".strip()
    if d.get("source") not in sm.DOCUMENTED_SOURCES:
        return f'{v} (declarado, a confirmar)'
    return v


def _p(txt, style):
    return Paragraph(txt, style)


def _tbd_para(ss, prefix=""):
    return Paragraph(f"<b>{prefix}</b>{TBD}" if prefix else TBD, ss["Tbd"])


def _section_table(ss, rows):
    """rows = [(label, value_flowable_or_str)] -> 2-col table."""
    data = []
    for label, val in rows:
        v = val if hasattr(val, "wrap") else Paragraph(str(val), ss["Body"])
        data.append([Paragraph(f"<b>{label}</b>", ss["Body"]), v])
    t = Table(data, colWidths=[55 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_study_note(study: dict) -> bytes:
    ss = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Nota de estudo preliminar — StructuroPilot",
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    data = study.get("data") or {}
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    goal = (study.get("goal") or {}).get("label") or "Estudo estrutural"
    story = []

    # ---------- Page de garde ----------
    story.append(Spacer(1, 30 * mm))
    story.append(_p("NOTA DE ESTUDO ESTRUTURAL — PRELIMINAR", ss["CoverTitle"]))
    story.append(_p("Documento gerado pelo StructuroPilot (ConstruPilot)", ss["CoverSub"]))
    story.append(Spacer(1, 10 * mm))
    story.append(_p(f"<b>{study.get('title','')}</b>", ss["CoverSub"]))
    story.append(_p(f"Objet : {goal}", ss["CoverSub"]))
    story.append(Spacer(1, 10 * mm))
    story.append(_section_table(ss, [
        ("Referência do processo", study.get("study_id", "")),
        ("País", study.get("country", "PT")),
        ("Revisão", str(study.get("revision", 1))),
        ("Nível de saída", study.get("output_level", "exploration")),
        ("Data de emissão", today),
    ]))
    story.append(Spacer(1, 8 * mm))
    # Tableau "Ind. Evolution" (historique de révision)
    story.append(_p("Índice · Alteração", ss["H2"]))
    evo = [[_p("<b>Ind.</b>", ss["Small"]), _p("<b>Auteur</b>", ss["Small"]),
            _p("<b>Date</b>", ss["Small"]), _p("<b>Objet</b>", ss["Small"])]]
    approvals = study.get("approvals") or []
    if approvals:
        for a in approvals:
            evo.append([_p(str(a.get("revision", "")), ss["Small"]),
                        _p(a.get("name", ""), ss["Small"]),
                        _p((a.get("at", "") or "")[:10], ss["Small"]),
                        _p("Aprovação do estudo preliminar", ss["Small"])])
    evo.append([_p(str(study.get("revision", 1)), ss["Small"]),
                _p("StructuroPilot", ss["Small"]), _p(today, ss["Small"]),
                _p("Emissão da nota preliminar", ss["Small"])])
    te = Table(evo, colWidths=[18 * mm, 60 * mm, 30 * mm, 57 * mm])
    te.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(te)
    story.append(Spacer(1, 12 * mm))
    story.append(_p(
        "<b>AVISO —</b> Nota de estudo PRELIMINAR. Estrutura os dados, define as variantes a estudar e identifica as verificações. NÃO contém qualquer dimensionamento: o motor de verificação (Eurocódigos / NP EN) está bloqueado enquanto não forem fornecidos os textos normativos licenciados e os casos de referência validados por um engenheiro. <b>NÃO VÁLIDO PARA EXECUÇÃO.</b>",
        ss["Tbd"]))
    story.append(PageBreak())

    # ---------- Sommaire ----------
    story.append(_p("Sommaire", ss["H1"]))
    for line in [
        "1. Caderno de encargos e condicionantes",
        "2. Visita ao local — levantamentos e constatações",
        "3. Estudo estrutural (cargas, estabilidade, geometria)",
        "4. Variantes de solução a estudar",
        "5. Anexos (memórias de cálculo, desenhos)",
        "6. Verificações e aprovação",
    ]:
        story.append(_p(line, ss["Body"]))
    story.append(HRFlowable(width="100%", color=LINE, spaceBefore=6, spaceAfter=6))

    # ---------- 1. Cahier des charges ----------
    story.append(_p("1. Caderno de encargos e condicionantes", ss["H1"]))
    story.append(_p("1.1 Objet", ss["H2"]))
    story.append(_p(goal, ss["Body"]))
    story.append(_p("1.2 Plantas e dimensões", ss["H2"]))
    story.append(_section_table(ss, [
        ("Posição da abertura", _fmt_datum(data.get("ouverture.position"))),
        ("Vão / largura", _fmt_datum(data.get("ouverture.portee"))),
        ("Espessura da parede resistente", _fmt_datum(data.get("mur.epaisseur"))),
        ("Cargas suportadas acima", _fmt_datum(data.get("ouverture.charges_reprises"))),
    ]))
    story.append(_p("1.3 Método de cálculo", ss["H2"]))
    story.append(_tbd_para(ss, "Referencial e método: "))
    story.append(_p(f"Estado do referencial: {sm.RULEPACK.get('status')} — {sm.RULEPACK.get('note')}", ss["Small"]))
    story.append(_p("1.4 Condicionantes urbanísticas / de utilização", ss["H2"]))
    story.append(_p("A preencher pelo dono de obra (PDM, condicionantes de utilização).", ss["Body"]))
    story.append(_p("1.5 Ação sísmica (EC8)", ss["H2"]))
    story.append(_tbd_para(ss, "Zona, classe de importância, ação sísmica: "))
    story.append(_p("1.6 Outras obras", ss["H2"]))
    story.append(_p("A documentar (redes, pavimentos adjacentes, construções existentes).", ss["Body"]))
    story.append(_p("1.7 Obra e segurança", ss["H2"]))
    story.append(_p("Escoramento e faseamento a definir; capacidade do piso inferior «a documentar».", ss["Body"]))
    story.append(_p("1.8 Maintenance", ss["H2"]))
    story.append(_p("Proteção anticorrosiva / resistência ao fogo do aço a precisar na fase de execução.", ss["Body"]))

    # ---------- 2. Visite / relevés ----------
    story.append(_p("2. Visita ao local — levantamentos e constatações", ss["H1"]))
    story.append(_p("2.1 Constatações (factos declarados / levantados)", ss["H2"]))
    facts = study.get("facts") or []
    if facts:
        for f in facts:
            story.append(_p(f"• {f.get('text','')} <font color='#6b7280' size=7>[{f.get('source','')}]</font>", ss["Body"]))
    else:
        story.append(_p("Nenhuma constatação registada.", ss["Body"]))
    story.append(_p("2.2 Dever de aconselhamento", ss["H2"]))
    story.append(_p(
        "A abertura de um vão numa parede resistente exige um escoramento adequado, a verificação dos nembos/apoios e da descida de cargas até ao terreno, bem como um controlo das fundações. Qualquer resistência de alvenaria ou capacidade do terreno deve provir de um ensaio — a idade do edifício não a documenta.", ss["Body"]))

    # ---------- 3. Étude structurelle ----------
    story.append(_p("3. Estudo estrutural", ss["H1"]))
    story.append(_p("3.1 Cargas permanentes e sobrecargas", ss["H2"]))
    story.append(_section_table(ss, [
        ("Cargas permanentes", _fmt_datum(data.get("charges.permanentes"))),
        ("Sobrecargas de utilização", _fmt_datum(data.get("charges.exploitation"))),
        ("Descida de cargas", _tbd_para(ss)),
    ]))
    story.append(_p("3.2 Resistência ao fogo da estrutura de aço", ss["H2"]))
    story.append(_tbd_para(ss, "Classe de resistência ao fogo e secção: "))
    story.append(_p("3.3 Geometria do modelo", ss["H2"]))
    levels = study.get("levels") or []
    if levels:
        ordered = sorted(levels, key=lambda l: (l.get("elevation_m", {}) or {}).get("value") or 0)
        lvl_rows = [[_p("<b>Nível</b>", ss["Small"]), _p("<b>Cota</b>", ss["Small"])]]
        for lv in ordered:
            lvl_rows.append([_p(lv.get("name", ""), ss["Small"]),
                             _p(_fmt_datum(lv.get("elevation_m")), ss["Small"])])
        tl = Table(lvl_rows, colWidths=[90 * mm, 75 * mm])
        tl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tl)
    else:
        story.append(_p("Nenhum nível definido — a documentar.", ss["Body"]))
    elements = study.get("elements") or []
    if elements:
        story.append(Spacer(1, 3 * mm))
        story.append(_p("Elementos resistentes:", ss["Body"]))
        for el in elements:
            story.append(_p(f"• [{el.get('ref')}] {el.get('type')} — {el.get('label','')} "
                            f"<font color='#6b7280' size=7>({el.get('level') or '—'})</font>", ss["Body"]))

    # ---------- 3.4 Linteau calculé (indicatif) — dé-verrouillage par le moteur BET ----------
    lint = (study.get("lintel") or {}).get("result")
    if lint:
        story.append(_p("3.4 Dimensionamento indicativo da padieira (EN 1992/1993)", ss["H2"]))
        act = lint.get("actions", {})
        story.append(_p(f"Vão livre {lint.get('clear_span_m')} m — modelo de carga «{lint.get('load_model')} » — M_Ed {act.get('m_ed_knm')} kN·m, V_Ed {act.get('v_ed_kn')} kN ({act.get('combination', '')}).", ss["Body"]))
        lh = [_p("<b>Solução</b>", ss["Small"]), _p("<b>Proposta</b>", ss["Small"]),
              _p("<b>Verificações</b>", ss["Small"]), _p("<b>Custo estimado</b>", ss["Small"])]
        lrows = [lh]
        st = lint.get("steel") or {}
        if st.get("status") == "ok":
            lrows.append([_p("Aço NP EN 1993", ss["Small"]), _p(st.get("label", ""), ss["Small"]),
                          _p(f"M_Rd {st.get('mrd_knm')} · V_Rd {st.get('vrd_kn')} · flecha {st.get('defl_char_mm')}/{st.get('defl_char_limit_mm')} mm", ss["Small"]),
                          _p(f"{st.get('cost_eur')} € ({st.get('mass_kg')} kg)", ss["Small"])])
        elif st.get("message"):
            lrows.append([_p("Aço NP EN 1993", ss["Small"]), _p(st.get("message"), ss["Small"]), _p("—", ss["Small"]), _p("—", ss["Small"])])
        rc = lint.get("rc") or {}
        if rc.get("status") == "ok":
            lrows.append([_p("Betão armado NP EN 1992", ss["Small"]), _p(rc.get("label", ""), ss["Small"]),
                          _p(f"As {rc.get('as_required_cm2')} cm² · Asw/s {rc.get('asw_required_cm2_m')} cm²/m · L/d {rc.get('span_depth_ratio')}", ss["Small"]),
                          _p(f"{rc.get('cost_eur')} € ({rc.get('concrete_m3')} m³)", ss["Small"])])
        elif rc.get("message"):
            lrows.append([_p("Betão armado NP EN 1992", ss["Small"]), _p(rc.get("message"), ss["Small"]), _p("—", ss["Small"]), _p("—", ss["Small"])])
        tlint = Table(lrows, colWidths=[32 * mm, 43 * mm, 60 * mm, 30 * mm])
        tlint.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tlint)
        reco = lint.get("recommendation")
        if reco:
            story.append(_p(f"<b>Solução mais económica:</b> {('Aço' if reco['material'] == 'steel' else 'Betão armado')} — {reco.get('label')} ({reco.get('cost_eur')} €). {reco.get('reason')}.", ss["Body"]))
        br = lint.get("bearing") or {}
        story.append(_p(f"Apoio em alvenaria: pressão {br.get('sigma_kpa')} kPa ≤ {br.get('allow_kpa')} kPa → {('OK' if br.get('status') == 'ok' else 'A REVER')} (entrega adotada ≥ {br.get('adopted_length_m')} m).", ss["Body"]))
        st2 = lint.get("steel") or {}
        if st2.get("status") == "ok" and st2.get("bearing_plate"):
            bp = st2["bearing_plate"]
            story.append(_p(f"Chapa de aço indicativa: {bp.get('length_mm')}×{bp.get('width_mm')}×{bp.get('thickness_mm')} mm.", ss["Small"]))
        rc2 = lint.get("rc") or {}
        if rc2.get("status") == "ok" and rc2.get("detailing"):
            an = rc2["detailing"].get("anchorage") or {}
            story.append(_p(f"BA: amarração dos varões inferiores {an.get('straight_mm')} mm (crochet {an.get('hook_mm')} mm); estribos {rc2.get('asw_required_cm2_m')} cm²/m.", ss["Small"]))
        rk = lint.get("reactions") or {}
        story.append(_p(f"Reação por nembo a reintroduzir na descida de cargas: G {rk.get('g_kn')} kN + Q {rk.get('q_kn')} kN.", ss["Small"]))
        try:
            from engines.structuro_lintel_draw import lintel_figure
            story.append(lintel_figure(lint, width=440, height=175))
        except Exception:
            pass
        for n in lint.get("notes", []):
            story.append(_p("• " + n, ss["Small"]))
        story.append(_p(lint.get("note", ""), ss["Small"]))

    # ---------- 4. Variantes ----------
    story.append(_p("4. Variantes de solução a estudar", ss["H1"]))
    story.append(_p("As variantes abaixo são opções a comparar. As grandezas mecânicas (secção adotada, flecha, verificação dos apoios) dependem do motor de cálculo bloqueado e estão marcadas «A CALCULAR».", ss["Body"]))
    var_header = [_p("<b>Ref.</b>", ss["Small"]), _p("<b>Solução</b>", ss["Small"]),
                  _p("<b>Principe</b>", ss["Small"]), _p("<b>Secção / flecha / apoios</b>", ss["Small"])]
    var_rows = [var_header]
    for ref, sol, principe in VARIANTS:
        var_rows.append([_p(ref, ss["Small"]), _p(sol, ss["Small"]), _p(principe, ss["Small"]),
                         _p(f"<font color='#b45309'>A CALCULAR</font>", ss["Small"])])
    tv = Table(var_rows, colWidths=[12 * mm, 45 * mm, 70 * mm, 38 * mm])
    tv.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(tv)

    # ---------- 5. Annexes ----------
    story.append(_p("5. Annexes", ss["H1"]))
    story.append(_p("5.1 Memórias de cálculo", ss["H2"]))
    story.append(_tbd_para(ss, "A produzir pelo motor de cálculo: "))
    story.append(_p("5.2 Plantas importadas", ss["H2"]))
    plans = [p for p in (study.get("plans") or []) if not p.get("is_deleted")]
    if plans:
        for p in plans:
            story.append(_p(f"• {p.get('original_filename','plan')} "
                            f"<font color='#6b7280' size=7>({p.get('kind','')} · "
                            f"{p.get('level') or 'niveau ?'} · {(p.get('size',0)/1024):.0f} Ko)</font>", ss["Body"]))
    else:
        story.append(_p("Nenhuma planta importada.", ss["Body"]))

    # ---------- 6. Vérifications & approbation ----------
    story.append(_p("6. Verificações e aprovação", ss["H1"]))
    verifs = study.get("verifications") or []
    if verifs:
        vh = [_p("<b>Verificação</b>", ss["Small"]), _p("<b>Estado</b>", ss["Small"]),
              _p("<b>Dados em falta</b>", ss["Small"])]
        vrows = [vh]
        for v in verifs:
            vrows.append([_p(v.get("label", ""), ss["Small"]),
                          _p(v.get("status", ""), ss["Small"]),
                          _p(", ".join(v.get("missing_inputs") or []) or "—", ss["Small"])])
        tver = Table(vrows, colWidths=[75 * mm, 42 * mm, 48 * mm])
        tver.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE),
                                  ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                                  ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tver)
    story.append(Spacer(1, 6 * mm))
    story.append(_p("Signature", ss["H2"]))
    if approvals:
        for a in approvals:
            story.append(_p(f"{a.get('name', '')} — {a.get('role', '')} (rev. {a.get('revision', '')}, {(a.get('at', '') or '')[:10]})", ss["Body"]))
            story.append(_p("Aprovação do estudo preliminar — NÃO válido para execução.", ss["Small"]))
    else:
        story.append(_p("Não aprovado. Verificação estrutural por um engenheiro necessária.", ss["Body"]))

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE); canvas.setLineWidth(0.3)
        canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
        canvas.setFillColor(MUTED); canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 8 * mm, "StructuroPilot · Nota preliminar · NÃO para execução — motor de cálculo bloqueado")
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f'Página {_doc.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
