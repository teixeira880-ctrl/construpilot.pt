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

TBD = "À CALCULER — moteur de vérification verrouillé"

# Variantes types à étudier (scénario ouverture dans mur porteur). Comparées, jamais calculées.
VARIANTS = [
    ("V1", "2 IPN 500", "Poutre bi-appuyée sur trumeaux (sans poteau)"),
    ("V2", "2 IPN 240", "Poutre bi-appuyée sur trumeaux (section réduite)"),
    ("V3", "2 HEA 240 + poteaux d'extrémité", "Poutre sur poteaux d'extrémité"),
    ("V4", "2 HEA 240 + poteau intermédiaire", "Portée réduite par poteau central"),
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
        return "à documenter"
    v = f"{d.get('value')} {d.get('unit') or ''}".strip()
    if d.get("source") not in sm.DOCUMENTED_SOURCES:
        return f"{v} (déclaré, à confirmer)"
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
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Note d'étude préliminaire — StructuroPilot",
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    data = study.get("data") or {}
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    goal = (study.get("goal") or {}).get("label") or "Étude structurelle"
    story = []

    # ---------- Page de garde ----------
    story.append(Spacer(1, 30 * mm))
    story.append(_p("NOTE D'ÉTUDE STRUCTURE — PRÉLIMINAIRE", ss["CoverTitle"]))
    story.append(_p("Document généré par StructuroPilot (ConstruPilot)", ss["CoverSub"]))
    story.append(Spacer(1, 10 * mm))
    story.append(_p(f"<b>{study.get('title','')}</b>", ss["CoverSub"]))
    story.append(_p(f"Objet : {goal}", ss["CoverSub"]))
    story.append(Spacer(1, 10 * mm))
    story.append(_section_table(ss, [
        ("Référence affaire", study.get("study_id", "")),
        ("Pays", study.get("country", "FR")),
        ("Révision", str(study.get("revision", 1))),
        ("Niveau de sortie", study.get("output_level", "exploration")),
        ("Date d'édition", today),
    ]))
    story.append(Spacer(1, 8 * mm))
    # Tableau "Ind. Evolution" (historique de révision)
    story.append(_p("Indice · Évolution", ss["H2"]))
    evo = [[_p("<b>Ind.</b>", ss["Small"]), _p("<b>Auteur</b>", ss["Small"]),
            _p("<b>Date</b>", ss["Small"]), _p("<b>Objet</b>", ss["Small"])]]
    approvals = study.get("approvals") or []
    if approvals:
        for a in approvals:
            evo.append([_p(str(a.get("revision", "")), ss["Small"]),
                        _p(a.get("name", ""), ss["Small"]),
                        _p((a.get("at", "") or "")[:10], ss["Small"]),
                        _p("Approbation étude préliminaire", ss["Small"])])
    evo.append([_p(str(study.get("revision", 1)), ss["Small"]),
                _p("StructuroPilot", ss["Small"]), _p(today, ss["Small"]),
                _p("Édition note préliminaire", ss["Small"])])
    te = Table(evo, colWidths=[18 * mm, 60 * mm, 30 * mm, 57 * mm])
    te.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(te)
    story.append(Spacer(1, 12 * mm))
    story.append(_p(
        "<b>AVERTISSEMENT —</b> Note d'étude PRÉLIMINAIRE. Elle structure les données, "
        "pose les variantes à étudier et identifie les vérifications. Elle ne contient "
        "AUCUN dimensionnement : le moteur de vérification (Eurocodes / NF-EN) est "
        "verrouillé tant que les textes normatifs licenciés et les cas de référence "
        "validés par un ingénieur ne sont pas fournis. <b>NON VALABLE POUR EXÉCUTION.</b>",
        ss["Tbd"]))
    story.append(PageBreak())

    # ---------- Sommaire ----------
    story.append(_p("Sommaire", ss["H1"]))
    for line in [
        "1. Cahier des charges et contraintes",
        "2. Visite sur site — relevés et constats",
        "3. Étude structurelle (charges, stabilité, géométrie)",
        "4. Variantes de solution à étudier",
        "5. Annexes (notes de calcul, plans)",
        "6. Vérifications & approbation",
    ]:
        story.append(_p(line, ss["Body"]))
    story.append(HRFlowable(width="100%", color=LINE, spaceBefore=6, spaceAfter=6))

    # ---------- 1. Cahier des charges ----------
    story.append(_p("1. Cahier des charges et contraintes", ss["H1"]))
    story.append(_p("1.1 Objet", ss["H2"]))
    story.append(_p(goal, ss["Body"]))
    story.append(_p("1.2 Plans & dimensions", ss["H2"]))
    story.append(_section_table(ss, [
        ("Position de l'ouverture", _fmt_datum(data.get("ouverture.position"))),
        ("Portée / largeur", _fmt_datum(data.get("ouverture.portee"))),
        ("Épaisseur du mur porteur", _fmt_datum(data.get("mur.epaisseur"))),
        ("Charges reprises au-dessus", _fmt_datum(data.get("ouverture.charges_reprises"))),
    ]))
    story.append(_p("1.3 Mode de calcul", ss["H2"]))
    story.append(_tbd_para(ss, "Référentiel & méthode : "))
    story.append(_p(f"Statut du référentiel : {sm.RULEPACK.get('status')} — {sm.RULEPACK.get('note')}", ss["Small"]))
    story.append(_p("1.4 Dispositions urbanistiques / d'exploitation", ss["H2"]))
    story.append(_p("À renseigner par le maître d'ouvrage (PLU, contraintes d'exploitation).", ss["Body"]))
    story.append(_p("1.5 Charges sismiques (EC8)", ss["H2"]))
    story.append(_tbd_para(ss, "Zone, catégorie d'importance, action sismique : "))
    story.append(_p("1.6 Autres ouvrages", ss["H2"]))
    story.append(_p("À documenter (réseaux, planchers adjacents, ouvrages existants).", ss["Body"]))
    story.append(_p("1.7 Chantier & sécurité", ss["H2"]))
    story.append(_p("Étaiement et phasage à définir ; capacité du niveau inférieur « à documenter ».", ss["Body"]))
    story.append(_p("1.8 Maintenance", ss["H2"]))
    story.append(_p("Protection anticorrosion / coupe-feu de l'acier à préciser au stade exécution.", ss["Body"]))

    # ---------- 2. Visite / relevés ----------
    story.append(_p("2. Visite sur site — relevés et constats", ss["H1"]))
    story.append(_p("2.1 Constats (faits déclarés / relevés)", ss["H2"]))
    facts = study.get("facts") or []
    if facts:
        for f in facts:
            story.append(_p(f"• {f.get('text','')} <font color='#6b7280' size=7>[{f.get('source','')}]</font>", ss["Body"]))
    else:
        story.append(_p("Aucun constat enregistré.", ss["Body"]))
    story.append(_p("2.2 Devoir de conseil", ss["H2"]))
    story.append(_p(
        "La reprise d'une ouverture dans un mur porteur impose un étaiement adapté, "
        "la vérification des trumeaux/appuis et de la descente de charges jusqu'au sol, "
        "ainsi qu'un contrôle des fondations. Toute résistance de maçonnerie ou portance "
        "de sol doit provenir d'un essai — l'âge du bâtiment ne la documente pas.", ss["Body"]))

    # ---------- 3. Étude structurelle ----------
    story.append(_p("3. Étude structurelle", ss["H1"]))
    story.append(_p("3.1 Charges permanentes & d'exploitation", ss["H2"]))
    story.append(_section_table(ss, [
        ("Charges permanentes", _fmt_datum(data.get("charges.permanentes"))),
        ("Charges d'exploitation", _fmt_datum(data.get("charges.exploitation"))),
        ("Descente de charges", _tbd_para(ss)),
    ]))
    story.append(_p("3.2 Stabilité au feu de la structure acier", ss["H2"]))
    story.append(_tbd_para(ss, "Degré coupe-feu & section : "))
    story.append(_p("3.3 Géométrie du modèle", ss["H2"]))
    levels = study.get("levels") or []
    if levels:
        ordered = sorted(levels, key=lambda l: (l.get("elevation_m", {}) or {}).get("value") or 0)
        lvl_rows = [[_p("<b>Niveau</b>", ss["Small"]), _p("<b>Élévation</b>", ss["Small"])]]
        for lv in ordered:
            lvl_rows.append([_p(lv.get("name", ""), ss["Small"]),
                             _p(_fmt_datum(lv.get("elevation_m")), ss["Small"])])
        tl = Table(lvl_rows, colWidths=[90 * mm, 75 * mm])
        tl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tl)
    else:
        story.append(_p("Aucun niveau défini — à documenter.", ss["Body"]))
    elements = study.get("elements") or []
    if elements:
        story.append(Spacer(1, 3 * mm))
        story.append(_p("Éléments porteurs :", ss["Body"]))
        for el in elements:
            story.append(_p(f"• [{el.get('ref')}] {el.get('type')} — {el.get('label','')} "
                            f"<font color='#6b7280' size=7>({el.get('level') or '—'})</font>", ss["Body"]))

    # ---------- 3.4 Linteau calculé (indicatif) — dé-verrouillage par le moteur BET ----------
    lint = (study.get("lintel") or {}).get("result")
    if lint:
        story.append(_p("3.4 Dimensionnement indicatif du linteau (EN 1992/1993)", ss["H2"]))
        act = lint.get("actions", {})
        story.append(_p(f"Portée libre {lint.get('clear_span_m')} m — modèle de charge « {lint.get('load_model')} » — "
                        f"M_Ed {act.get('m_ed_knm')} kN·m, V_Ed {act.get('v_ed_kn')} kN ({act.get('combination','')}).", ss["Body"]))
        lh = [_p("<b>Solution</b>", ss["Small"]), _p("<b>Proposition</b>", ss["Small"]),
              _p("<b>Vérifications</b>", ss["Small"]), _p("<b>Coût estimé</b>", ss["Small"])]
        lrows = [lh]
        st = lint.get("steel") or {}
        if st.get("status") == "ok":
            lrows.append([_p("Acier EN 1993", ss["Small"]), _p(st.get("label", ""), ss["Small"]),
                          _p(f"M_Rd {st.get('mrd_knm')} · V_Rd {st.get('vrd_kn')} · flèche {st.get('defl_char_mm')}/{st.get('defl_char_limit_mm')} mm", ss["Small"]),
                          _p(f"{st.get('cost_eur')} € ({st.get('mass_kg')} kg)", ss["Small"])])
        elif st.get("message"):
            lrows.append([_p("Acier EN 1993", ss["Small"]), _p(st.get("message"), ss["Small"]), _p("—", ss["Small"]), _p("—", ss["Small"])])
        rc = lint.get("rc") or {}
        if rc.get("status") == "ok":
            lrows.append([_p("Béton armé EN 1992", ss["Small"]), _p(rc.get("label", ""), ss["Small"]),
                          _p(f"As {rc.get('as_required_cm2')} cm² · Asw/s {rc.get('asw_required_cm2_m')} cm²/m · L/d {rc.get('span_depth_ratio')}", ss["Small"]),
                          _p(f"{rc.get('cost_eur')} € ({rc.get('concrete_m3')} m³)", ss["Small"])])
        elif rc.get("message"):
            lrows.append([_p("Béton armé EN 1992", ss["Small"]), _p(rc.get("message"), ss["Small"]), _p("—", ss["Small"]), _p("—", ss["Small"])])
        tlint = Table(lrows, colWidths=[32 * mm, 43 * mm, 60 * mm, 30 * mm])
        tlint.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tlint)
        reco = lint.get("recommendation")
        if reco:
            story.append(_p(f"<b>Solution la plus économique :</b> {'Acier' if reco['material'] == 'steel' else 'Béton armé'} — "
                            f"{reco.get('label')} ({reco.get('cost_eur')} €). {reco.get('reason')}.", ss["Body"]))
        br = lint.get("bearing") or {}
        story.append(_p(f"Appui sur maçonnerie : pression {br.get('sigma_kpa')} kPa ≤ {br.get('allow_kpa')} kPa → "
                        f"{'OK' if br.get('status') == 'ok' else 'À REVOIR'} (about adopté ≥ {br.get('adopted_length_m')} m).", ss["Body"]))
        st2 = lint.get("steel") or {}
        if st2.get("status") == "ok" and st2.get("bearing_plate"):
            bp = st2["bearing_plate"]
            story.append(_p(f"Platine acier indicative : {bp.get('length_mm')}×{bp.get('width_mm')}×{bp.get('thickness_mm')} mm.", ss["Small"]))
        rc2 = lint.get("rc") or {}
        if rc2.get("status") == "ok" and rc2.get("detailing"):
            an = rc2["detailing"].get("anchorage") or {}
            story.append(_p(f"BA : ancrage barres inférieures {an.get('straight_mm')} mm (crochet {an.get('hook_mm')} mm) ; cadres {rc2.get('asw_required_cm2_m')} cm²/m.", ss["Small"]))
        rk = lint.get("reactions") or {}
        story.append(_p(f"Réaction par trumeau à réinjecter dans la descente : G {rk.get('g_kn')} kN + Q {rk.get('q_kn')} kN.", ss["Small"]))
        try:
            from engines.structuro_lintel_draw import lintel_figure
            story.append(lintel_figure(lint, width=440, height=175))
        except Exception:
            pass
        for n in lint.get("notes", []):
            story.append(_p("• " + n, ss["Small"]))
        story.append(_p(lint.get("note", ""), ss["Small"]))

    # ---------- 4. Variantes ----------
    story.append(_p("4. Variantes de solution à étudier", ss["H1"]))
    story.append(_p("Les variantes ci-dessous sont des options à comparer. Les grandeurs "
                    "mécaniques (section retenue, flèche, vérification des appuis) relèvent du "
                    "moteur de calcul verrouillé et sont marquées « À CALCULER ».", ss["Body"]))
    var_header = [_p("<b>Réf.</b>", ss["Small"]), _p("<b>Solution</b>", ss["Small"]),
                  _p("<b>Principe</b>", ss["Small"]), _p("<b>Section / flèche / appuis</b>", ss["Small"])]
    var_rows = [var_header]
    for ref, sol, principe in VARIANTS:
        var_rows.append([_p(ref, ss["Small"]), _p(sol, ss["Small"]), _p(principe, ss["Small"]),
                         _p(f"<font color='#b45309'>À CALCULER</font>", ss["Small"])])
    tv = Table(var_rows, colWidths=[12 * mm, 45 * mm, 70 * mm, 38 * mm])
    tv.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(tv)

    # ---------- 5. Annexes ----------
    story.append(_p("5. Annexes", ss["H1"]))
    story.append(_p("5.1 Notes de calcul (NdC)", ss["H2"]))
    story.append(_tbd_para(ss, "À produire par le moteur de calcul : "))
    story.append(_p("5.2 Plans importés", ss["H2"]))
    plans = [p for p in (study.get("plans") or []) if not p.get("is_deleted")]
    if plans:
        for p in plans:
            story.append(_p(f"• {p.get('original_filename','plan')} "
                            f"<font color='#6b7280' size=7>({p.get('kind','')} · "
                            f"{p.get('level') or 'niveau ?'} · {(p.get('size',0)/1024):.0f} Ko)</font>", ss["Body"]))
    else:
        story.append(_p("Aucun plan importé.", ss["Body"]))

    # ---------- 6. Vérifications & approbation ----------
    story.append(_p("6. Vérifications & approbation", ss["H1"]))
    verifs = study.get("verifications") or []
    if verifs:
        vh = [_p("<b>Vérification</b>", ss["Small"]), _p("<b>Statut</b>", ss["Small"]),
              _p("<b>Données manquantes</b>", ss["Small"])]
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
            story.append(_p(f"{a.get('name','')} — {a.get('role','')} "
                            f"(rév. {a.get('revision','')}, {(a.get('at','') or '')[:10]})", ss["Body"]))
            story.append(_p("Approbation d'étude préliminaire — NON valable pour exécution.", ss["Small"]))
    else:
        story.append(_p("Non approuvé. Vérification structurelle par un ingénieur requise.", ss["Body"]))

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE); canvas.setLineWidth(0.3)
        canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
        canvas.setFillColor(MUTED); canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 8 * mm, "StructuroPilot · Note préliminaire · NON pour exécution — moteur de calcul verrouillé")
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"Page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
