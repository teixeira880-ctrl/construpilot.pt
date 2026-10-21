"""PDF « Rapport d'analyse OpenAI » généré par ConstruPilot à partir du JSON structuré (présentation stable, brandée)."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from engines.pdf_takeoff import GREY, LIGHT_GREY, ORANGE, _styles
from engines.plan_cotes_pdf import _e, _fit_image, _scope_box, _story_interior
from engines.plan_pdf_i18n import Paragraph, cover_story
_W = A4[0] - 32 * mm
from engines.studies_prompt import MENTION

STATUS = {"confirmed": ("Incoerência confirmada", "#dc2626"), "probable": ("Incoerência provável", "#ea580c"),
          "to_confirm": ("A confirmar", "#ca8a04"), "insufficient_information": ("Information insuffisante", "#64748B")}
STATUS_PT = {"confirmed": "Incoerência confirmada", "probable": "Incoerência provável", "to_confirm": "A confirmar",
             "insufficient_information": "Informação insuficiente"}


def _hdr(rows, widths, S, status_col=None):
    t = Table(rows, colWidths=[_W * w / sum(widths) for w in widths], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A0D14")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
          ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY])]
    t.setStyle(TableStyle(st))
    return t


def _fmt(v, unit=""):
    if v is None:
        return "—"
    return f"{v:g} {unit}".strip() if isinstance(v, (int, float)) else str(v)


def build_studies_report(plan: dict, page_index: int, study: dict, report: dict, image_b64: str | None,
                         branding: dict | None, lang: str = "pt") -> bytes:
    S = _styles()
    a = study.get("analysis") or {}
    ver = study.get("verification") or {}
    pt = lang == "pt"
    L = (lambda fr, ptxt: ptxt if pt else fr)
    now = datetime.now(timezone.utc)
    rid = f"CP-{(plan.get('plan_id') or '')[-6:]}-P{page_index + 1}-{now.strftime('%y%m%d')}-A"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=L("Rapport d'analyse", "Relatório de análise"), author="ConstruPilot")
    story: list = []
    meta = a.get("plan_metadata") or {}
    title_doc = meta.get("title") or plan.get("filename") or "plan"
    story += cover_story(plan, page_index, report, branding, lang, S, _W,
                         subtitle=L("ANALYSE OPENAI GPT-6 ASTRA — ", "ANÁLISE OPENAI GPT-6 ASTRA — ") + _e(str(title_doc)).upper()[:70])
    company = (branding or {}).get("company_name") or "—"
    mention = MENTION["pt" if pt else "pt"].format(plan=f"« {title_doc} »" + (f" ({meta.get('level')})" if meta.get("level") else ""), company=company)
    story += [_scope_box(f"<b>{L('Objeto do documento', 'Objeto do documento')}.</b> {_e(mention)}", S, _W)]
    badge = (L("VERIFICADO — segunda passagem sem anomalia bloqueante", "VERIFICADO — segunda passagem sem anomalia bloqueante") if study.get("verified")
             else L("NÃO VERIFICADO — controlos incompletos ou pontos bloqueantes", "NÃO VERIFICADO — controlos incompletos ou pontos bloqueantes"))
    story += [Spacer(1, 4 * mm), Paragraph(f"<font color='{('#16a34a' if study.get('verified') else '#dc2626')}'><b>{badge}</b></font> · {L('Referência', 'Referência')} {rid} · {L('Modelo', 'Modelo')} {study.get('model')} (reasoning {study.get('effort')}) · {L('Confiança global', 'Confiança global')} {a.get('global_confidence', 0):.0%}", S["muted"])]
    it = study.get("interior") or {}
    if it and not it.get("complete"):
        story += [Spacer(1, 3 * mm), _scope_box(f"<b>{_e(it.get('message') or '')}</b><br/>" + _e(" ; ".join(it.get("reasons") or [])[:1200]), S, _W)]
    story += [PageBreak(), Paragraph(L("RESUMO EXECUTIVO", "RESUMO EXECUTIVO"), S["kicker"]), Paragraph(_e(a.get("report_summary") or "—"), S["body"]),
              Spacer(1, 3 * mm)]
    if it:
        ai = it.get("ai") or {}
        story += [Paragraph(L("DIMENSÕES INTERIORES PAREDE A PAREDE — CONTROLO EM TRÊS PASSAGENS", "DIMENSÕES INTERIORES PAREDE A PAREDE — CONTROLO EM TRÊS PASSAGENS"), S["kicker"]),
                  Paragraph(_e(ai.get("summary") or "—"), S["body"]), Spacer(1, 2 * mm)]
        engine = it.get("engine") or report.get("interior") or {}
        story.append(Paragraph(L("Medições e fechos abaixo: motor geométrico; revisão IA no comentário acima.",
                                  "Medições e fechos abaixo: motor geométrico; releitura IA no comentário acima."), S["muted"]))
        _story_interior(story, {"interior": engine}, S, width=_W)
        for u in ai.get("unreadable_dimensions") or []:
            story.append(Paragraph(f"<font color='#dc2626'><b>{L('Ilegível', 'Ilegível')}</b></font> — {_e(u.get('location'))} : {_e(u.get('comment'))}", S["body"]))
        story.append(Spacer(1, 3 * mm))
    rows = [[L("Tipo de documento", "Tipo de documento"), a.get("document_type") or "—"], [L("Perímetro", "Âmbito"), ", ".join(a.get("analysis_scope") or []) or "—"],
            [L("Páginas analisadas", "Páginas analisadas"), ", ".join(str(p) for p in a.get("pages_analyzed") or []) or str(page_index + 1)],
            [L("Piso", "Nível"), meta.get("level") or "—"], [L("Escala", "Escala"), meta.get("scale") or "—"],
            [L("Índice / data", "Revisão / data"), f"{meta.get('revision') or '—'} / {meta.get('date') or '—'}"]]
    t = Table([[Paragraph(f"<b>{_e(k)}</b>", S["body"]), Paragraph(_e(str(v)), S["body"])] for k, v in rows], colWidths=[45 * mm, _W - 45 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1"))]))
    story += [t, Spacer(1, 5 * mm)]
    # contrôles effectués
    story.append(Paragraph(L("Controlos efetuados", "Controlos efetuados"), S["h2"]))
    rows = [[L("Página", "Página"), L("Zona", "Zona"), L("Cadeia (cotas parciais)", "Cadeia (cotas parciais)"), L("Somme", "Soma"), L("Cota total", "Cota total"), L("Desvio", "Desvio")]]
    for c in a.get("dimension_chains") or []:
        rows.append([str(c.get("page", "")), Paragraph(_e(c.get("zone", "")), S["body"]),
                     Paragraph(" + ".join(f"{v:g}" for v in c.get("partials") or []) + (f" — {_e(c.get('note'))}" if c.get("note") else ""), S["body"]),
                     _fmt(c.get("sum"), c.get("unit", "")), _fmt(c.get("total_indicated"), c.get("unit", "")), _fmt(c.get("difference"), c.get("unit", ""))])
    if len(rows) > 1:
        story.append(_hdr(rows, [12 * mm, 35 * mm, 68 * mm, 20 * mm, 22 * mm, 21 * mm], S))
    for al in a.get("alignment_checks") or []:
        story.append(Paragraph(f"• p.{al.get('page')} — {_e(al.get('zone'))} : <b>{_e(al.get('result'))}</b> — {_e(al.get('note'))}", S["body"]))
    for cp in a.get("conforming_points") or []:
        story.append(Paragraph(f"<font color='#16a34a'>✔</font> {_e(cp)}", S["body"]))
    # incohérences
    story += [PageBreak(), Paragraph(L("QUADRO DAS INCOERÊNCIAS", "QUADRO DAS INCOERÊNCIAS"), S["kicker"])]
    inc = a.get("inconsistencies") or []
    if not inc:
        story.append(Paragraph(L("Nenhuma incoerência demonstrável no documento fornecido.", "Nenhuma incoerência demonstrável no documento fornecido."), S["body"]))
    for x in inc:
        lbl, col = STATUS.get(x.get("status"), ("—", "#64748B"))
        if pt:
            lbl = STATUS_PT.get(x.get("status"), lbl)
        block = [Paragraph(f"<b>{_e(x.get('id'))} — {_e(x.get('category'))}</b> · p.{x.get('page') or '—'} · {_e(x.get('zone'))}", S["h2"]),
                 Paragraph(f"<font color='{col}'><b>{lbl}</b></font> · {L('confiance', 'confiança')} {float(x.get('confidence') or 0):.0%} · "
                           f"{L('observé', 'observado')} {_fmt(x.get('observed_value'), x.get('unit', ''))} · {L('calculé', 'calculado')} "
                           f"{_fmt(x.get('calculated_value'), x.get('unit', ''))} · {L('écart', 'desvio')} <b>{_fmt(x.get('difference'), x.get('unit', ''))}</b>", S["body"]),
                 Paragraph(_e(x.get("explanation") or ""), S["body"])]
        if x.get("evidence"):
            block.append(Paragraph(f"<b>{L('Provas', 'Provas')} :</b> " + " ; ".join(_e(e) for e in x["evidence"]), S["muted"]))
        if x.get("possible_interpretations"):
            block.append(Paragraph(f"<b>{L('Interpretações possíveis', 'Interpretações possíveis')} :</b> " + " ; ".join(_e(e) for e in x["possible_interpretations"]), S["muted"]))
        if x.get("recommended_action"):
            block.append(Paragraph(f"<b>{L('Ação recomendada', 'Ação recomendada')} :</b> {_e(x['recommended_action'])}", S["body"]))
        block.append(Spacer(1, 4 * mm))
        story.append(KeepTogether(block))
    # calculs détaillés
    calcs = a.get("calculations") or []
    if calcs:
        story += [PageBreak(), Paragraph(L("CÁLCULOS DETALHADOS", "CÁLCULOS DETALHADOS"), S["kicker"])]
        rows = [["ID", L("Página", "Pág."), L("Plano", "Fórmula"), L("Resultado", "Resultado"), L("Indicado", "Indicado"), L("Desvio", "Desvio")]]
        for c in calcs:
            rows.append([c.get("id", ""), str(c.get("page", "")), Paragraph(f"<font face='Courier'>{_e(c.get('formula'))}</font>", S["body"]),
                         _fmt(c.get("result"), c.get("unit", "")), _fmt(c.get("indicated"), c.get("unit", "")), _fmt(c.get("difference"), c.get("unit", ""))])
        story.append(_hdr(rows, [14 * mm, 12 * mm, 90 * mm, 22 * mm, 20 * mm, 20 * mm], S))
    # points à confirmer / informations manquantes
    story += [Spacer(1, 5 * mm), Paragraph(L("Pontos a confirmar", "Pontos a confirmar"), S["h2"])]
    story += [Paragraph(f"{i + 1}. {_e(p)}", S["body"]) for i, p in enumerate(a.get("points_to_confirm") or [])] or [Paragraph("—", S["body"])]
    if a.get("missing_information"):
        story.append(Paragraph(L("Informações não fornecidas ou ilegíveis", "Informações não fornecidas ou ilegíveis"), S["h2"]))
        story += [Paragraph(f"• {_e(p)}", S["body"]) for p in a["missing_information"]]
    # seconde passe
    story += [Spacer(1, 4 * mm), Paragraph(L("Segunda passagem — controlador independente", "Segunda passagem — controlador independente"), S["h2"]),
              Paragraph(_e(ver.get("summary") or "—"), S["body"])]
    for f in ver.get("findings") or []:
        story.append(Paragraph(f"• <b>{_e(f.get('severity'))}</b> — {_e(f.get('category'))}{(' (' + _e(f.get('target_id')) + ')') if f.get('target_id') else ''} : "
                               f"{_e(f.get('description'))} → {_e(f.get('correction'))}", S["muted"]))
    story += [Spacer(1, 4 * mm), Paragraph(L("Conclusão", "Conclusão"), S["h2"]), Paragraph(_e(a.get("conclusion") or a.get("report_summary") or ""), S["body"]),
              Spacer(1, 3 * mm), Paragraph(_e(mention), S["muted"])]
    if image_b64:
        from engines.plan_report_pdf import build_controls, render_marked_plan
        png, _ = render_marked_plan(image_b64, build_controls(report, report.get("geometry") or {}), report)
        story += [PageBreak(), Paragraph(L("PLANTA ANOTADA CONSTRUPILOT", "PLANTA ANOTADA CONSTRUPILOT"), S["kicker"]), _fit_image(png, _W, A4[1] - 70 * mm)]

    def _footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"{company} · ConstruPilot.fr · {rid} · {d.page}")
        canvas.setFillColor(ORANGE)
        canvas.rect(16 * mm, 9 * mm, 18 * mm, 1.2, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
