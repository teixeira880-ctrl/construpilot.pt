"""Rapport narratif « une section numérotée par grande cote » (style rapport d'ingénieur rédigé). FR / PT."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engines.pdf_takeoff import GREY, LIGHT_GREY, ORANGE, _story_header_branding, _styles
from engines.plan_cotes_pdf import _e, _fit_image, _scope_box
from engines.plan_pdf_i18n import cover_story, disclaimer
from engines.plan_report_pdf import LVL_HEX, _W, build_controls, render_marked_plan

L = {
    "fr": {"kicker": "RAPPORT NARRATIF DE CONTRÔLE DES COTES", "title": "Analyse des cotes du plan",
           "doc": "Document analysé", "page": "page", "date": "Date de l'analyse", "scale": "Échelle effective",
           "scale_decl": "déclarée", "level": "Niveau global", "intro": "Introduction", "method": "Méthode",
           "sections": "Analyse détaillée par grande cote", "calc": "Calcul", "gap": "Écart", "concl": "Conclusion",
           "facades": "Façades opposées", "synth": "Synthèse", "reco": "Recommandations", "final": "Conclusion générale",
           "plan": "Plan annoté", "plan_legend": "Marqueurs CP-xx : vert cohérent · jaune à vérifier · orange incohérence · rouge incohérence majeure",
           "footer": "Rapport narratif de contrôle des cotes", "cotes": "Cotes concernées",
           "disclaimer": "Ce rapport est une aide à la vérification produite automatiquement par ConstruPilot à partir des cotes "
                         "vectorielles du PDF, d'une double lecture IA et d'un contrôle adversarial. Les valeurs recalculées ne "
                         "remplacent jamais les cotes du plan : les points signalés doivent être confirmés avec l'auteur du plan.",
           "lvl": {"VERT": "Cohérent", "BLEU": "Information", "JAUNE": "À vérifier", "ORANGE": "Incohérence", "ROUGE": "Incohérence majeure"}},
    "pt": {"kicker": "RELATÓRIO NARRATIVO DE CONTROLO DE COTAS", "title": "Análise das cotas da planta",
           "doc": "Documento analisado", "page": "página", "date": "Data da análise", "scale": "Escala efetiva",
           "scale_decl": "declarada", "level": "Nível global", "intro": "Introdução", "method": "Método",
           "sections": "Análise detalhada por cota geral", "calc": "Cálculo", "gap": "Desvio", "concl": "Conclusão",
           "facades": "Fachadas opostas", "synth": "Síntese", "reco": "Recomendações", "final": "Conclusão geral",
           "plan": "Planta anotada", "plan_legend": "Marcadores CP-xx: verde coerente · amarelo a verificar · laranja incoerência · vermelho incoerência grave",
           "footer": "Relatório narrativo de controlo de cotas", "cotes": "Cotas em causa",
           "disclaimer": "Este relatório é um auxiliar de verificação produzido automaticamente pela ConstruPilot a partir das cotas "
                         "vetoriais do PDF, de uma dupla leitura por IA e de um controlo adversarial. Os valores recalculados nunca "
                         "substituem as cotas da planta: os pontos assinalados devem ser confirmados com o autor da planta.",
           "lvl": {"VERT": "Coerente", "BLEU": "Informação", "JAUNE": "A verificar", "ORANGE": "Incoerência", "ROUGE": "Incoerência grave"}},
}


def _paras(text: str, style) -> list:
    return [Paragraph(_e(p.strip()), style) for p in str(text or "").split("\n") if p.strip()]


def _section(sec: dict, t: dict, S) -> KeepTogether:
    lvl = sec.get("niveau") or "JAUNE"
    hexc = LVL_HEX.get(lvl, LVL_HEX["JAUNE"])
    block = [Paragraph(f"{sec['numero']}. {_e(sec['titre'])}", S["h1"]),
             Paragraph(f"<font color='{hexc}'>■ <b>{_e(t['lvl'].get(lvl, lvl))}</b></font>"
                       + (f" · {t['gap']} : <b>{sec['ecart_mm']:+.0f} mm</b>" if sec.get("ecart_mm") is not None else ""), S["muted"])]
    block += _paras(sec.get("texte"), S["body"])
    if sec.get("calcul"):
        box = Table([[Paragraph(f"<b>{t['calc']}</b><br/><font face='Courier'>{_e(sec['calcul'])}</font>", S["body"])]],
                    colWidths=[_W - 4 * mm])
        box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(hexc)), ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        block += [Spacer(1, 2 * mm), box, Spacer(1, 2 * mm)]
    if sec.get("conclusion"):
        block.append(Paragraph(f"<b>{t['concl']} :</b> {_e(sec['conclusion'])}", S["body"]))
    if sec.get("cotes_index"):
        block.append(Paragraph(f"{t['cotes']} : " + ", ".join(f"#{i}" for i in sec["cotes_index"]), S["muted"]))
    block.append(Spacer(1, 6 * mm))
    return KeepTogether(block)


def build_narrative_report(plan: dict, page_index: int, report: dict, image_b64: str, branding: dict | None,
                           lang: str = "fr") -> bytes:
    t = L.get(lang, L["fr"])
    S = _styles()
    geo = report.get("geometry") or {}
    nar = geo.get("narratif") or {}
    cal = report.get("calibration") or {}
    now = datetime.now(timezone.utc)
    rid = f"CP-{(plan.get('plan_id') or '')[-6:]}-P{page_index + 1}-{now.strftime('%y%m%d')}-N"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=nar.get("titre") or t["title"], author="ConstruPilot")
    story: list = []
    story += cover_story(plan, page_index, report, branding, lang, S, _W,
                         subtitle=("NARRATIVO — " if lang == "pt" else "NARRATIF — ") + t["title"].upper())
    story += [_scope_box(disclaimer(plan, page_index, report, branding, lang), S, _W), PageBreak()]
    story.append(Paragraph(_e(nar.get("titre") or t["title"]), S["h2"]))
    story.append(Spacer(1, 3 * mm))
    scale = "—"
    if cal.get("effective_scale_denominator"):
        scale = f"1/{cal['effective_scale_denominator']:g}"
        if cal.get("scale_denominator") and abs(cal["effective_scale_denominator"] - cal["scale_denominator"]) > 0.5:
            scale += f" ({t['scale_decl']} 1/{cal['scale_denominator']})"
    elif cal.get("scale_denominator"):
        scale = f"1/{cal['scale_denominator']}"
    lvl = geo.get("niveau_global") or "JAUNE"
    rows = [[t["doc"], f"{plan.get('filename') or 'plan'} — {t['page']} {page_index + 1}"],
            [t["date"], now.strftime("%d/%m/%Y %H:%M UTC")], [t["scale"], scale],
            [t["level"], Paragraph(f"<font color='{LVL_HEX.get(lvl, '#ca8a04')}'><b>{_e(t['lvl'].get(lvl, lvl))}</b></font>", S["body"])],
            ["ID", rid]]
    tb = Table([[Paragraph(f"<b>{_e(k)}</b>", S["body"]), v if not isinstance(v, str) else Paragraph(_e(v), S["body"])] for k, v in rows],
               colWidths=[45 * mm, _W - 45 * mm])
    tb.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [tb, Spacer(1, 5 * mm)]
    if nar.get("introduction"):
        story += [Paragraph(t["intro"], S["h2"]), *_paras(nar["introduction"], S["body"])]
    if nar.get("methode"):
        story += [Spacer(1, 2 * mm), Paragraph(t["method"], S["h2"]), *_paras(nar["methode"], S["body"])]
    story += [PageBreak(), Paragraph(t["sections"].upper(), S["kicker"])]
    for sec in nar.get("sections") or []:
        story.append(_section(sec, t, S))
    tail = []
    if nar.get("facades"):
        tail += [Paragraph(t["facades"], S["h2"]), *_paras(nar["facades"], S["body"])]
    if nar.get("synthese"):
        tail += [Paragraph(t["synth"], S["h2"]), *_paras(nar["synthese"], S["body"])]
    if nar.get("recommandations"):
        tail.append(Paragraph(t["reco"], S["h2"]))
        tail += [Paragraph(f"{i + 1}. {_e(r)}", S["body"]) for i, r in enumerate(nar["recommandations"])]
    if nar.get("conclusion"):
        tail += [Paragraph(t["final"], S["h2"]), *_paras(nar["conclusion"], S["body"])]
    if tail:
        story += [PageBreak(), *tail]
    story += [Spacer(1, 4 * mm), Paragraph(t["disclaimer"], S["muted"])]
    ctrls = build_controls(report, geo)
    marked_png, _ = render_marked_plan(image_b64, ctrls, report)
    story += [PageBreak(), Paragraph(t["plan"].upper(), S["kicker"]), Paragraph(t["plan_legend"], S["muted"]),
              _fit_image(marked_png, _W, A4[1] - 70 * mm)]

    def _footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"ConstruPilot · {t['footer']} · {rid} · {d.page}")
        canvas.setFillColor(ORANGE)
        canvas.rect(16 * mm, 9 * mm, 18 * mm, 1.2, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
