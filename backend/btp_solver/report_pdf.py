"""PDF brandé du diagnostic du solveur BTP (reportlab, graphiques redessinés)."""
import io
from datetime import datetime, timezone

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.spider import SpiderChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from engines.pdf_takeoff import DARK, _story_header_branding, _styles
from engines.plan_cotes_pdf import _fit_image, _tbl

PALETTE = [colors.HexColor("#0F766E"), colors.HexColor("#F59E0B"), colors.HexColor("#2563EB"), colors.HexColor("#DC2626"), colors.HexColor("#7C3AED")]
DOMAIN = {"fissures": "Fissures", "humidite": "Humidité", "thermique": "Thermique", "structure": "Structure", "sinistre": "Sinistre", "reception": "Réception", "autre": "Autre"}
URGENCY = {"informative": "Informative", "planned": "Planifiée", "urgent": "Urgente", "immediate": "Immédiate"}
RISK = {"low": "faible", "medium": "moyen", "high": "élevé", "critical": "critique"}
CONF = {"low": "faible", "medium": "moyenne", "high": "élevée"}


def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(text, S, style="body"):
    return Paragraph(_esc(text), S[style])


def _eur(v) -> str:
    return "—" if v is None else f"{float(v):,.0f} €".replace(",", " ")


def _bar(chart: dict, width=170 * mm, height=62 * mm) -> Drawing:
    d = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 22 * mm, 20 * mm, width - 70 * mm, height - 26 * mm
    bc.data = [list(map(float, s["data"])) for s in chart["series"]] or [[0]]
    bc.categoryAxis.categoryNames = [lbl[:26] for lbl in chart.get("x_labels") or []]
    bc.categoryAxis.labels.fontSize = 6.5
    bc.categoryAxis.labels.angle = 15
    bc.categoryAxis.labels.boxAnchor = "ne"
    bc.categoryAxis.labels.dy = -2
    bc.valueAxis.labels.fontSize = 6.5
    bc.valueAxis.valueMin = 0
    bc.groupSpacing = 8
    for i in range(len(bc.data)):
        bc.bars[i].fillColor = PALETTE[i % len(PALETTE)]
        bc.bars[i].strokeColor = None
    d.add(bc)
    lg = Legend()
    lg.x, lg.y = width - 44 * mm, height - 10 * mm
    lg.fontSize = 6.5
    lg.alignment = "right"
    lg.colorNamePairs = [(PALETTE[i % len(PALETTE)], s["name"][:24]) for i, s in enumerate(chart["series"])]
    d.add(lg)
    d.add(String(0, height - 5 * mm, chart["title"], fontSize=8, fillColor=DARK, fontName="Helvetica-Bold"))
    return d


def _radar(chart: dict, width=170 * mm, height=70 * mm) -> Drawing:
    d = Drawing(width, height)
    sc = SpiderChart()
    sc.x, sc.y, sc.width, sc.height = 30 * mm, 6 * mm, height - 14 * mm, height - 14 * mm
    sc.data = [list(map(float, s["data"])) for s in chart["series"]] or [[0, 0, 0]]
    sc.labels = list(chart.get("x_labels") or [])
    sc.spokeLabels.fontSize = 6.5
    for i in range(len(sc.data)):
        sc.strands[i].strokeColor = PALETTE[i % len(PALETTE)]
        sc.strands[i].fillColor = colors.Color(*PALETTE[i % len(PALETTE)].rgb(), alpha=0.12)
        sc.strands[i].strokeWidth = 1.2
    d.add(sc)
    lg = Legend()
    lg.x, lg.y = width - 52 * mm, height - 12 * mm
    lg.fontSize = 6.5
    lg.alignment = "right"
    lg.colorNamePairs = [(PALETTE[i % len(PALETTE)], s["name"][:26]) for i, s in enumerate(chart["series"])]
    d.add(lg)
    d.add(String(0, height - 5 * mm, chart["title"], fontSize=8, fillColor=DARK, fontName="Helvetica-Bold"))
    return d


def _pie(chart: dict, width=170 * mm, height=62 * mm) -> Drawing:
    d = Drawing(width, height)
    pie = Pie()
    pie.x, pie.y, pie.width, pie.height = 10 * mm, 6 * mm, height - 16 * mm, height - 16 * mm
    data = list(map(float, (chart["series"][0]["data"] if chart.get("series") else []) or [1]))
    total = sum(data) or 1
    pie.data = data
    pie.labels = None
    pie.slices.strokeColor = colors.white
    for i in range(len(data)):
        pie.slices[i].fillColor = PALETTE[i % len(PALETTE)]
    d.add(pie)
    lg = Legend()
    lg.x, lg.y = 65 * mm, height - 12 * mm
    lg.fontSize = 6.5
    lg.alignment = "right"
    lg.columnMaximum = 6
    lg.colorNamePairs = [(PALETTE[i % len(PALETTE)], f"{lbl[:34]} — {round(100 * data[i] / total)} %") for i, lbl in enumerate(chart.get("x_labels") or [])]
    d.add(lg)
    d.add(String(0, height - 5 * mm, chart["title"], fontSize=8, fillColor=DARK, fontName="Helvetica-Bold"))
    return d


def _chart_flowable(chart: dict):
    try:
        if chart.get("type") == "radar":
            return _radar(chart)
        if chart.get("type") == "pie":
            return _pie(chart)
        return _bar(chart)
    except Exception:  # noqa: BLE001 — un graphique ne doit jamais bloquer le PDF
        return None


def build_solver_pdf(problem: dict, branding: dict | None, photos: list[bytes]) -> bytes:
    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Diagnostic BTP — {problem.get('problem_id')}")
    story = []
    _story_header_branding(story, branding, S)
    gen = problem.get("generated_at_iso") or datetime.now(timezone.utc).isoformat()
    story += [_p("Diagnostic provisionnel — résolution d'un problème BTP", S, "h1"),
              _p(f"Domaine : {DOMAIN.get(problem.get('domain'), problem.get('domain'))} · Urgence : {URGENCY.get(problem.get('urgency'), problem.get('urgency'))} · "
                 f"Réf. {problem.get('problem_id')} · généré le {gen[:10]}", S, "muted"),
              Spacer(1, 4), _p(problem.get("disclaimer") or "", S, "muted"), Spacer(1, 8)]

    story += [_p("Problème décrit", S, "h2"), _p(problem.get("description") or "", S)]
    ctx = problem.get("context") or {}
    ctx_rows = [(lbl, ctx.get(k)) for k, lbl in (("region", "Région"), ("type_batiment", "Type de bâtiment"), ("surface_m2", "Surface (m²)"),
                                                 ("age_annees", "Âge du bâti (années)"), ("budget_max_eur", "Budget max (€)"), ("urgence_ressentie", "Urgence ressentie")) if ctx.get(k)]
    if ctx_rows:
        story.append(Spacer(1, 4))
        story.append(_tbl([["Contexte", "Valeur"]] + [[a, str(b)] for a, b in ctx_rows], [60 * mm, 110 * mm], S))

    story += [_p("Synthèse", S, "h2"), _p(problem.get("summary") or "", S)]
    if problem.get("photo_analysis"):
        story += [_p("Lecture des photos jointes", S, "h2"), _p(problem["photo_analysis"], S)]

    if problem.get("causes"):
        story.append(_p("Causes probables", S, "h2"))
        story.append(_tbl([["Cause", "Confiance", "Explication"]] +
                          [[c.get("label"), CONF.get(c.get("confidence"), c.get("confidence")), c.get("explanation")] for c in problem["causes"]],
                          [50 * mm, 20 * mm, 100 * mm], S))

    if problem.get("solutions"):
        story.append(_p("Solutions proposées (chiffrage provisionnel)", S, "h2"))
        story.append(_tbl([["Solution", "Coût min", "Coût max", "Durée (j)", "Risque", "Garantie", "Reco."]] +
                          [[s.get("label"), _eur(s.get("cost_min_eur")), _eur(s.get("cost_max_eur")),
                            f"{s.get('duration_days_min') or '—'}–{s.get('duration_days_max') or s.get('duration_days_min') or '—'}",
                            RISK.get(s.get("risk"), s.get("risk")), f"{s['warranty_years']} ans" if s.get("warranty_years") else "—", "✔" if s.get("recommended") else ""]
                           for s in problem["solutions"]],
                          [56 * mm, 20 * mm, 20 * mm, 20 * mm, 18 * mm, 20 * mm, 12 * mm], S))
        for s in problem["solutions"]:
            block = [Spacer(1, 4), _p(("★ " if s.get("recommended") else "") + (s.get("label") or ""), S, "kicker"), _p(s.get("description") or "", S)]
            for st in s.get("steps") or []:
                block.append(_p(f"{st.get('order')}. {st.get('text')}" + (f" ({', '.join(st['materials'])})" if st.get("materials") else ""), S, "muted"))
            story.append(KeepTogether(block))

    charts = [c for c in (problem.get("charts") or []) if c.get("series")]
    if charts:
        story += [PageBreak(), _p("Comparatifs visuels", S, "h2")]
        for c in charts:
            fl = _chart_flowable(c)
            if fl is not None:
                story += [fl, Spacer(1, 3)]
                if c.get("caption"):
                    story.append(_p(c["caption"], S, "muted"))
                story.append(Spacer(1, 6))

    if problem.get("action_plan"):
        story.append(_p("Plan d'action", S, "h2"))
        for st in problem["action_plan"]:
            story.append(_p(f"{st.get('order')}. {st.get('text')}", S))

    if problem.get("references"):
        story.append(_p("Références réglementaires et sources", S, "h2"))
        for r in problem["references"]:
            line = f"[{(r.get('kind') or '').upper()}] {r.get('code') or ''}" + (f" — {r['title']}" if r.get("title") else "")
            story.append(Paragraph(_esc(line) + (f' <font color="#2563EB"><u><link href="{_esc(r["url"])}">{_esc(r["url"][:90])}</link></u></font>' if r.get("url") else ""), S["muted"]))

    if photos:
        story += [PageBreak(), _p("Photos jointes", S, "h2")]
        for i, png in enumerate(photos, 1):
            try:
                story += [_p(f"Photo {i}", S, "kicker"), _fit_image(png, 170 * mm, 110 * mm), Spacer(1, 6)]
            except Exception:  # noqa: BLE001
                continue

    story += [Spacer(1, 10), _p("Document généré par ConstruPilot. Diagnostic provisionnel à confirmer par une visite technique ; il ne remplace ni une étude structurelle ni un devis d'entreprise.", S, "muted")]
    doc.build(story)
    return buf.getvalue()
