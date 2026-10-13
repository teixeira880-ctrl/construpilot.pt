"""Rapport PDF « Contrôle des cotes » : plan annoté (cotes mesurées) + tableaux détaillés."""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (Image as RLImage, PageBreak, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from engines.plan_pdf_i18n import LANG as PDF_LANG, Paragraph, cover_story, disclaimer, tr

from engines.pdf_takeoff import DARK, GREY, LIGHT_GREY, ORANGE, _story_header_branding, _styles

COL = {"ok": (22, 163, 74), "warn": (234, 88, 12), "ko": (220, 38, 38), "ignored": (148, 163, 184), "nd": (100, 116, 139)}
RL_COL = {"ok": colors.HexColor("#16a34a"), "warn": colors.HexColor("#ea580c"),
          "ko": colors.HexColor("#dc2626"), "ignored": colors.HexColor("#94a3b8"), "nd": colors.HexColor("#64748b")}
LABEL = {"ok": "OK", "warn": "A verificar", "ko": "INCOERÊNCIA", "ignored": "Ignorada", "nd": "NÃO DETERMINADO"}
_RANK = {"ko": 0, "warn": 1, "nd": 2, "ok": 3, "ignored": 4}
ORIENT = {"h": "horiz.", "v": "vert.", "o": "oblique"}


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, int(size))
        except Exception:
            continue
    return ImageFont.load_default()


def render_cotes_overlay(image_b64: str, report: dict) -> bytes:
    """Plan original + cotes mesurées (vert OK / orange à vérifier / rouge incohérence)."""
    img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    scale = max(img.width, img.height) / 1000.0
    lw = max(2, int(3 * scale))
    font = _font(max(10, 11 * scale))
    tick = max(4, int(7 * scale))
    for it in report.get("items") or []:
        if it.get("ignored"):
            continue
        eff = it["status"]
        for extra in (it.get("facade_status"), it.get("chain_status")):
            if extra == "ko" or (extra == "warn" and eff == "ok"):
                eff = extra
        col = COL[eff] + (255,)
        p1, p2 = (it["x1"], it["y1"]), (it["x2"], it["y2"])
        d.line([p1, p2], fill=col, width=lw)
        horiz = it["orientation"] != "v"
        for (x, y) in (p1, p2):
            if horiz:
                d.line([(x, y - tick), (x, y + tick)], fill=col, width=lw)
            else:
                d.line([(x - tick, y), (x + tick, y)], fill=col, width=lw)
        if it["status"] == "ok" and eff != "ok":
            txt = f"#{it['index']} {it['indicated_m']:.2f} {'FACADE' if it.get('facade_status') else 'CHAINE'} {eff.upper()}"
        elif it["status"] == "ok":
            txt = f"#{it['index']} OK {it['measured_m']:.2f}"
        else:
            txt = f"#{it['index']} {it['indicated_m']:.2f} -> {it['measured_m']:.2f} ({it['delta_cm']:+.0f} cm)"
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        bx1, by1, bx2, by2 = d.textbbox((0, 0), txt, font=font)
        tw, th = bx2 - bx1, by2 - by1
        pad = max(2, int(3 * scale))
        if horiz:
            ox, oy = mx - tw / 2, my - th - tick - pad * 2
        else:
            ox, oy = mx + tick + pad, my - th / 2
        ox = min(max(0, ox), img.width - tw - pad * 2)
        oy = min(max(0, oy), img.height - th - pad * 2)
        d.rectangle([ox - pad, oy - pad, ox + tw + pad, oy + th + pad],
                    fill=COL[it["status"]] + (225,))
        d.text((ox, oy), txt, fill=(255, 255, 255, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fit_image(png: bytes, max_w: float, max_h: float) -> RLImage:
    im = Image.open(io.BytesIO(png))
    ratio = min(max_w / im.width, max_h / im.height)
    return RLImage(io.BytesIO(png), width=im.width * ratio, height=im.height * ratio)


def _tbl(rows, widths, S, status_col: int | None = None, statuses: list | None = None):
    rows = [[tr(c) if isinstance(c, str) else c for c in r] for r in rows]
    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 1), (-1, -1), "RIGHT")]
    if status_col is not None and statuses:
        for i, s in enumerate(statuses, start=1):
            style += [("TEXTCOLOR", (status_col, i), (status_col, i), RL_COL[s]),
                      ("FONTNAME", (status_col, i), (status_col, i), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def _story_summary(story, report, S):
    sm, tol, cal = report["summary"], report["tolerance"], report.get("calibration") or {}
    verdict = LABEL[sm["verdict"]]
    story.append(Paragraph(
        f"<font color='{RL_COL[sm['verdict']].hexval()}'><b>Verdict : {verdict}</b></font> — {sm['total']} cotas controladas: {sm['ok']} OK, {sm['warn']} a verificar, <b>{sm['ko']} incohérence(s)</b>{(' · ' + str(sm['ignored']) + ' ignorée(s)' if sm.get('ignored') else '')} · {sm['chains_total']} cadeia(s) de cotas ({sm['chains_ko']} incohérente(s)){(' · ' + str(sm['facades_total']) + ' fachada(s) oposta(s) (' + str(sm['facades_ko']) + ' incohérente(s))' if sm.get('facades_total') else '')}{(' · ' + str(sm['elements_total']) + ' elemento(s) desenhado(s) (' + str(sm['elements_ko']) + ' incohérent(s))' if sm.get('elements_total') else '')}{(' · ' + str(sm['anchors_ko'] + sm['anchors_warn']) + ' cota(s) não associada(s)' if sm.get('anchors_ko') or sm.get('anchors_warn') else '')} · diferença máx. {sm['max_delta_cm']:.0f} cm.", S["body"]))
    if sm.get("conclusion"):
        story.append(Paragraph(f"<b>Conclusão rápida:</b> {_e(sm['conclusion'])}", S["body"]))
    if report.get("abstention"):
        story.append(Paragraph(f"<b>Abstention ConstruPilot :</b> {report['abstention']} ({sm.get('nd', 0)} cota(s) não determinada(s)).", S["body"]))
    rd = report.get("reading") or {}
    src = {"ai": "leitura IA da planta (imagem)", "dxf": "cotas exatas do ficheiro DXF",
           "pdf_vector+ai": "cotas vetoriais do PDF (medição exata ao mm) cruzadas com a leitura IA"}.get(rd.get("source"), "—")
    eff = cal.get("effective_scale_denominator")
    story.append(Paragraph(
        f"Tolerância: ±{tol['pct']} % (ou ±{tol['cm']} cm) · Fonte das cotas: {src} · Escala: {cal.get('pixels_per_meter', 0):.1f} px/m ({cal.get('method', '—')}{(', calibrada automaticamente' if report.get('auto_calibrated') else '')}){(f' · escala efetiva do PDF 1/{eff:g}' if eff else '')}.", S["muted"]))
    cross = rd.get("cross") or {}
    if cross:
        story.append(Paragraph(
            f"<b>Cruzamento vetorial ↔ IA:</b> {cross.get('vector', 0)} cota(s) medida(s) nos vetores do PDF, {cross.get('confirmed', 0)} confirmada(s) pela leitura IA, {cross.get('ai_only', 0)} lida(s) apenas pela IA (não verificadas, nunca contadas como incoerência)"
            + (" · divergências de leitura (o texto vetorial prevalece): " + " ; ".join(
                f"« {d.get('vector_text')} » lu « {d.get('ai_text')} » par l'IA" for d in cross["divergences"])
               if cross.get("divergences") else "") + ".", S["muted"]))


def _story_items(story, report, S):
    story.append(Paragraph("Detalhe das cotas controladas", S["h2"]))
    rows = [["#", "Localização", "Orient.", "Cota indicada", "Medido", "Desvio", "Diferença %", "Conf.", "Estado"]]
    statuses = []
    for it in sorted(report["items"], key=lambda x: (_RANK[x["status"]], x["index"])):
        loc = it.get("location") or "—"
        if it.get("edited") and it.get("original_m") is not None:
            loc += f" <i>(corrigida: {it['original_m']:.2f} → {it['indicated_m']:.2f})</i>"
        rows.append([str(it["index"]), Paragraph(loc, S["muted"]),
                     ORIENT.get(it["orientation"], "—"), f"{it['indicated_m']:.2f} m",
                     f"{it['measured_m']:.2f} m", f"{it['delta_cm']:+.1f} cm",
                     f"{it['delta_pct']:+.1f} %" if it.get("delta_pct") is not None else "—",
                     f"{int(round(it['confidence'] * 100))} %", LABEL[it["status"]]])
        statuses.append(it["status"])
    story.append(_tbl(rows, [9 * mm, 60 * mm, 16 * mm, 24 * mm, 20 * mm, 20 * mm, 18 * mm, 13 * mm, 26 * mm],
                      S, status_col=8, statuses=statuses))


def _story_facades(story, report, S):
    fac = report.get("facades") or []
    if not fac:
        return
    story.append(Paragraph("Fachadas opostas (dimensões gerais)", S["h2"]))
    rows = [["Orient.", "Cote A", "Cote B", "Desvio", "Piso", "Estado"]]
    for f in fac:
        rows.append([tr("horizontale" if f["orientation"] == "h" else "verticale"),
                     f"#{f['a_index']} {f['a_m']:.2f} m ({tr(f['a_side'])})", f"#{f['b_index']} {f['b_m']:.2f} m ({tr(f['b_side'])})",
                     f"{f['delta_cm']:+.1f} cm", f["niveau"], tr(LABEL[f["status"]])])
    story.append(_tbl(rows, [22 * mm, 60 * mm, 60 * mm, 25 * mm, 25 * mm, 40 * mm], S, status_col=5,
                      statuses=[f["status"] for f in fac]))
    story.append(Paragraph(
        "Duas cotas gerais opostas de uma implantação retangular devem ser iguais. Uma diferença de alguns cm impõe uma cota única, uma diagonal ou uma planta de eixos antes da implantação.", S["muted"]))
    for f in fac:
        dg = f.get("diag")
        if dg:
            story.append(Paragraph(
                f"<b>Esquadria (#{f['a_index']} / #{f['b_index']}):</b> se a diferença de {dg['offset_cm']:g} cm for um defeito de esquadria numa implantação C {dg['L_m']:.2f} m × W {dg['W_m']:.2f} m, as diagonais valem ≈ {dg['d1_m']:.2f} m et {dg['d2_m']:.2f} m, ou seja, uma diferença de diagonais ≈ <b>{abs(dg['diff_cm']):g} cm</b> e um desvio angular ≈ {dg['angle_deg']:g}° — a controlar com fita métrica nas duas diagonais durante a implantação.", S["body"]))
    story.append(Spacer(1, 3 * mm))


def _story_elements(story, report, S):
    el = report.get("elements") or []
    items = report.get("items") or []
    floating = [it for it in items if it.get("anchor_status") in ("warn", "ko") and not it.get("ignored")]
    if not el and not floating:
        return
    if el:
        bad = [e for e in el if e["status"] != "ok"]
        story.append(Paragraph("Elementos desenhados — largura desenhada vs etiqueta (sapatas, vigas, paredes)", S["h2"]))
        story.append(Paragraph(
            f"{len(el)} elemento(s) etiquetado(s) «largura x altura» medido(s) entre os dois traços paralelos que os desenham: {len(el) - len(bad)} conforme(s), {sum((1 for e in bad if e['status'] == 'warn'))} a verificar, {sum((1 for e in bad if e['status'] == 'ko'))} incohérence(s).", S["body"]))
        if bad:
            rows = [["Etiqueta", "Anunciado", "Desenhado", "Desvio", "Piso", "Estado"]]
            for e in bad:
                rows.append([e["label"], f"{e['w_cm']} cm", f"{e['measured_w_m'] * 100:.1f} cm", f"{e['delta_mm']:+.0f} mm", e["niveau"], tr(LABEL[e["status"]])])
            story.append(_tbl(rows, [30 * mm, 25 * mm, 25 * mm, 25 * mm, 25 * mm, 40 * mm], S, status_col=5, statuses=[e["status"] for e in bad]))
        story.append(Spacer(1, 3 * mm))
    if floating:
        story.append(Paragraph("Cotas provavelmente erradas (não alinhadas com o desenho)", S["h2"]))
        story.append(Paragraph(
            "Uma linha de cota é traçada à distância das paredes, mas as suas linhas de chamada devem estar alinhadas (em projeção perpendicular) com uma face ou um eixo de parede desenhado. As cotas seguintes têm uma extremidade a mais de 10 mm (escala da planta) de qualquer traço longo ou eixo: a cota não mede o que está desenhado — cota a considerar errada até confirmação.", S["body"]))
        rows = [["#", "Cote", "Extremidade 1", "Extremidade 2", "Estado"]]
        for it in floating:
            a = it.get("anchor_mm") or [None, None]
            rows.append([str(it["index"]), f"{it['indicated_m']:.2f} m", f"{a[0]:.0f} mm" if a[0] is not None else "—",
                         f"{a[1]:.0f} mm" if a[1] is not None else "—", tr(LABEL[it["anchor_status"]])])
        story.append(_tbl(rows, [12 * mm, 25 * mm, 30 * mm, 30 * mm, 40 * mm], S, status_col=4, statuses=[it["anchor_status"] for it in floating]))
        story.append(Spacer(1, 3 * mm))


def _story_auto_spans(story, report, S):
    spans = report.get("auto_spans") or []
    if not spans:
        return
    story.append(Paragraph("Medições automáticas — distâncias desenhadas sem cota", S["h2"]))
    story.append(Paragraph(
        f'{len(spans)} distância(s) entre traços longos paralelos vizinhos (faces / eixos) que nenhuma cota inscrita cobre: medidas automaticamente à escala efetiva para permitir o cruzamento completo da planta.', S["body"]))
    cells = [f"M{sp['index']} · {'horiz.' if sp['orientation'] == 'h' else 'vert.'} · {sp['measured_m']:.2f} m" for sp in spans[:48]]
    rows = [cells[i:i + 4] + [""] * (4 - len(cells[i:i + 4])) for i in range(0, len(cells), 4)]
    if rows:
        story.append(_tbl([["Medição", "Medição", "Medição", "Medição"]] + rows, [45 * mm] * 4, S))
    story.append(Spacer(1, 3 * mm))


def _story_chains(story, report, S):
    chains = report.get("chains") or []
    story.append(Paragraph("Cadeias de cotas (parciais = total?)", S["h2"]))
    if not chains:
        story.append(Paragraph("Nenhuma cadeia de cotas detetada nesta página.", S["muted"]))
        return
    rows = [["Cota total", "Cotes partielles", "Somme", "Desvio", "Estado"]]
    statuses = []
    for c in chains:
        parts = " + ".join(f"#{i} {v:.2f}" for i, v in zip(c["part_indexes"], c["parts_m"]))
        rows.append([f"#{c['total_index']} = {c['total_m']:.2f} m", Paragraph(parts, S["muted"]),
                     f"{c['sum_m']:.2f} m", f"{c['delta_cm']:+.1f} cm", LABEL[c["status"]]])
        statuses.append(c["status"])
    story.append(_tbl(rows, [32 * mm, 90 * mm, 22 * mm, 22 * mm, 30 * mm], S, status_col=4, statuses=statuses))


def _story_surfaces(story, report, S):
    matches = (report.get("surfaces") or {}).get("matches") or []
    if not matches:
        return
    story.append(Paragraph("Áreas escritas na planta ↔ áreas medidas", S["h2"]))
    rows = [["Divisão", "Escrita", "Medida", "Diferença %"]]
    for m in matches:
        rows.append([m.get("room_name") or m.get("ai_name") or "—", f"{m['written_m2']:.2f} m²",
                     f"{m['measured_m2']:.2f} m²", f"{m['delta_pct']:+.1f} %"])
    story.append(_tbl(rows, [80 * mm, 30 * mm, 30 * mm, 30 * mm], S))


_LVL_COL = {"VERT": "#16a34a", "BLEU": "#2563eb", "JAUNE": "#ca8a04", "ORANGE": "#ea580c", "ROUGE": "#dc2626"}
_LVL_LABEL = {"VERT": "Coerente", "BLEU": "Informação", "JAUNE": "A verificar",
              "ORANGE": "Incoerência", "ROUGE": "Incoerência grave"}


def _e(s) -> str:
    from xml.sax.saxutils import escape
    return escape(str(s if s is not None else ""))


def _story_geometry(story, geo: dict, S):
    """Section « Analyse géométrique ConstruPilot » (double lecture IA)."""
    if not geo:
        return
    story.append(PageBreak())
    story.append(Paragraph("ANÁLISE GEOMÉTRICA CONSTRUPILOT — DUPLA LEITURA", S["kicker"]))
    lvl = geo.get("niveau_global", "VERT")
    story.append(Paragraph(
        f"<font color='{_LVL_COL[lvl]}'><b>Nível global: {_LVL_LABEL[lvl]}</b></font> — {len(geo.get('anomalies') or [])} anomalia(s) · passagem 2: {(geo.get('double_lecture') or {}).get('confirmees', 0)} confirmée(s), {(geo.get('double_lecture') or {}).get('infirmees', 0)} infirmée(s)"
        + (f" · agent adversarial : {geo['adversarial'].get('maintenues', 0)} maintenue(s), "
           f"{geo['adversarial'].get('contestees', 0)} contestée(s), {geo['adversarial'].get('rejetees', 0)} rejetée(s)"
           if (geo.get("adversarial") or {}).get("ok") else "") + ".", S["h1"]))
    if (geo.get("adversarial") or {}).get("conclusion"):
        story.append(Paragraph(f"<b>Agente de controlo adversarial:</b> {_e(geo['adversarial']['conclusion'])}", S["muted"]))
    doc = geo.get("document") or {}
    if doc:
        story.append(Paragraph("Cartouche : " + " · ".join(
            f"{k.replace('_', ' ')} : {_e(v)}" for k, v in doc.items() if v), S["muted"]))
    rep = geo.get("reponses") or {}
    if rep:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>1. Fecho matemático:</b> {_e(rep.get('fermeture') or 'NÃO INDICADO')}", S["body"]))
        story.append(Paragraph(f"<b>2. Compatibilidade geométrica:</b> {_e(rep.get('compatibilite') or 'NÃO INDICADO')}", S["body"]))
        av = rep.get("a_verifier") or []
        story.append(Paragraph("<b>3. A verificar antes da utilização:</b> " + (_e(" ; ".join(map(str, av))) if av else "—"), S["body"]))
    if geo.get("synthese"):
        story.append(Paragraph(_e(geo["synthese"]), S["muted"]))
    ferm = geo.get("fermetures") or []
    if ferm:
        story.append(Paragraph("Fecho das cadeias", S["h2"]))
        rows = [["Dir.", "Cadeia (valores inscritos)", "Calculado", "Cote plan", "Erro", "Estado"]]
        for f in ferm:
            rows.append([_e(f.get("direction")), Paragraph(_e(f.get("chaine")), S["muted"]),
                         f"{float(f.get('cote_calculee_m') or 0):.2f} m", f"{float(f.get('cote_plan_m') or 0):.2f} m",
                         f"{float(f.get('erreur_m') or 0) * 100:+.1f} cm", _e(f.get("statut"))])
        story.append(_tbl(rows, [14 * mm, 110 * mm, 24 * mm, 24 * mm, 24 * mm, 40 * mm], S))
    mat = geo.get("matrice") or []
    if mat:
        story.append(Paragraph("Matriz de coerência", S["h2"]))
        rows = [["Elemento", "Valor da planta", "Calculado", "Desvio", "Fonte do cálculo", "Confiança", "Estado"]]
        for m in mat:
            rows.append([Paragraph(_e(m.get("element")), S["muted"]), f"{float(m.get('valeur_plan_m') or 0):.2f} m",
                         f"{float(m.get('valeur_calculee_m') or 0):.2f} m", f"{float(m.get('ecart_m') or 0) * 100:+.1f} cm",
                         Paragraph(_e(m.get("source_calcul")), S["muted"]), _e(m.get("confiance")), _e(m.get("statut"))])
        story.append(_tbl(rows, [50 * mm, 22 * mm, 22 * mm, 20 * mm, 70 * mm, 22 * mm, 34 * mm], S))
    def _fmt(section, it):
        if section == "controles_croises":
            vals = " / ".join(str(v) for v in (it.get("valeurs") or []))
            return f"{it.get('description', '')} — valeurs : {vals} — diferença {float(it.get('ecart_m') or 0) * 100:+.1f} cm — {it.get('statut', '')}"
        if section == "facades":
            causes = " ; ".join(map(str, it.get("causes_possibles") or []))
            return (f"{it.get('nom', '')} : {float(it.get('longueur_plan_m') or 0):.2f} m vs oposta {float(it.get('longueur_opposee_m') or 0):.2f} m — diferença {float(it.get('ecart_m') or 0) * 100:+.1f} cm — {it.get('statut', '')}{(' (' + causes + ')' if causes else '')}")
        segs = " ; ".join(f"{s.get('segment', '')} : {s.get('statut', '')}"
                          + (f" ({s.get('decalage_mm')} mm)" if s.get("decalage_mm") else "")
                          for s in (it.get("segments") or []) if isinstance(s, dict))
        return f"{it.get('nom', '')} — {segs}"

    for section, title in (("controles_croises", "Controlos cruzados"), ("facades", "Fachadas"), ("alignements", "Alinhamentos")):
        items = [it for it in (geo.get(section) or []) if isinstance(it, dict)]
        if items:
            story.append(Paragraph(title, S["h2"]))
            for it in items:
                story.append(Paragraph("• " + _e(_fmt(section, it)), S["muted"]))
    anoms = geo.get("anomalies") or []
    story.append(Paragraph("Anomalias detalhadas", S["h2"]))
    if not anoms:
        story.append(Paragraph("Nenhuma anomalia detetada pela análise geométrica.", S["muted"]))
    for a in anoms:
        v = a.get("verification") or {}
        story.append(Paragraph(
            f"<font color='{_LVL_COL.get(a['niveau'], '#64748b')}'><b>ANOMALIA #{a['numero']} — {_LVL_LABEL.get(a['niveau'], a['niveau'])}</b></font> · confiança {_e(a.get('confiance'))} · passage 2 : {_e(v.get('verdict') or '—')}", S["body"]))
        for label, key in (("Localização", "localisation"), ("Dado da planta", "donnee_plan"), ("Cálculo ConstruPilot", "calcul"),
                           ("Plano", "formule"), ("Resultado", "resultat"), ("Explication", "explication"),
                           ("Ação recomendada", "action")):
            if a.get(key):
                story.append(Paragraph(f"<b>{label} :</b> {_e(a[key])}", S["muted"]))
        if a.get("ecart_mm") is not None:
            story.append(Paragraph(f"<b>Diferença:</b> {a['ecart_mm']:+.0f} mm", S["muted"]))
        if a.get("hypotheses"):
            story.append(Paragraph("<b>Hipóteses possíveis:</b> " + _e(" · ".join(a["hypotheses"])), S["muted"]))
        if v.get("recalcul") or v.get("commentaire"):
            story.append(Paragraph(f"<b>Recálculo passagem 2:</b> {_e(v.get('recalcul'))} {_e(v.get('commentaire'))}", S["muted"]))
        adv = a.get("adversarial")
        if adv:
            story.append(Paragraph(
                f"<b>Controlo adversarial (passagem 3): {_e(adv.get('verdict'))}</b>"
                + (f" — niveau {_e(a.get('niveau_initial'))} → {_e(a['niveau'])}" if a.get("niveau_initial") and a.get("niveau_initial") != a["niveau"] else "")
                + (f" · attaque : {_e(adv.get('attaque'))}" if adv.get("attaque") else "")
                + (f" · {_e(adv.get('recalcul'))}" if adv.get("recalcul") else ""), S["muted"]))
        story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Limiares de deteção ConstruPilot (0–2 mm desprezável · 2–10 mm baixo · 10–30 mm a verificar · 30–100 mm anomalia importante · > 100 mm anomalia grave) — não são tolerâncias regulamentares de execução. As hipóteses de correção nunca alteram a planta.", S["muted"]))


def _story_interior(story, report, S, overlay_png: bytes | None = None, width: float | None = None):
    """Tableau « dimensions intérieures mur à mur » + fermetures + annexe graphique ; bloc « analyse incomplète » si nécessaire."""
    from reportlab.lib.styles import ParagraphStyle
    W = width if width is not None else landscape(A4)[0] - 28 * mm
    def table(rows, fractions, status_col=None, statuses=None):
        # Les cellules longues doivent rester dans la largeur réelle de la page.
        cells = []
        for i, row in enumerate(rows):
            converted = []
            for j, value in enumerate(row):
                color = colors.white if i == 0 else DARK
                if i and statuses and j == status_col:
                    color = RL_COL[statuses[i - 1]]
                style = ParagraphStyle("interior-cell", parent=S["body"], fontSize=6.5, leading=8,
                                       textColor=color, fontName="Helvetica-Bold" if i == 0 else "Helvetica")
                converted.append(Paragraph(_e(tr(str(value))), style) if not isinstance(value, Paragraph) else value)
            cells.append(converted)
        return _tbl(cells, [W * f / sum(fractions) for f in fractions], S, status_col, statuses)
    it = report.get("interior") or {}
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(tr("Dimensões interiores parede a parede (face interior → face interior)"), S["h2"]))
    if not it or not it.get("walls"):
        story.append(_scope_box(tr("Análise incompleta: as dimensões interiores parede a parede não foram todas estabelecidas. O relatório final ainda não pode ser validado.") + " " +
                                tr("Não foi possível estabelecer nenhuma parede de duas faces nos vetores desta página."), S, W))
        return
    val = it.get("validation") or {}
    if not val.get("complete"):
        story.append(_scope_box("<b>" + tr(val.get("message") or "Análise incompleta") + "</b><br/>" +
                                tr("Controlos falhados") + " : " + _e("; ".join(val.get("failed_checks") or [])), S, W))
        story.append(Spacer(1, 2 * mm))
    st = it.get("stats") or {}
    story.append(Paragraph(tr("{w} parede(s) de duas faces ({a} ambígua(s)) · {m} medição(ões) interior(es) · {c} confirmada(s) por uma cota escrita · {r} fila(s), {rc} fechada(s) · secções ignoradas: {s}").format(
        w=st.get("walls", 0), a=st.get("walls_ambiguous", 0), m=st.get("measurements", 0), c=st.get("confirmed", 0), r=st.get("rows", 0),
        rc=st.get("rows_closed", 0), s=", ".join(it.get("sections_ignored") or []) or "—"), S["body"]))
    story.append(Spacer(1, 2 * mm))
    REF = {"inside_face_to_inside_face": "nu int. → nu int.", "outside_face_to_outside_face": "nu ext. → nu ext.", "axis_to_axis": "eixo → eixo",
           "axis_to_face": "eixo → face", "wall_thickness": "épaisseur", "cumulative": "cumulée", "partial_anchor": "partielle", "unresolved": "não associada"}
    STL = {"confirmed": "confirmée", "probable": "probable", "to_confirm": "a confirmar", "unreadable": "illisible"}
    FACE = {"interior_right": "nu int. droit", "interior_left": "nu int. gauche", "interior_top": "face int. superior", "interior_bottom": "face int. inferior"}
    rows = [[tr("Zona"), tr("Direção"), tr("Parede de partida"), tr("Parede de chegada"), tr("Referência"), tr("Cota lida"), tr("Medição"), tr("Desvio"), tr("Confiança"), tr("Estado")]]
    statuses = []
    for m in it.get("interior_measurements") or []:
        w = m.get("written_dimension_m")
        rows.append([m["measurement_id"], tr("horiz." if m["direction"] == "horizontal" else "vert."),
                     f"{m['from_wall']} ({tr(FACE.get(m['from_face'], m['from_face']))})", f"{m['to_wall']} ({tr(FACE.get(m['to_face'], m['to_face']))})", tr(REF.get(m["reference_type"], m["reference_type"])),
                     f"{w:.2f} m" if w is not None else "—", f"{m['geometric_dimension_m']:.3f} m",
                     f"{m['difference_m'] * 1000:+.0f} mm" if m.get("difference_m") is not None else "—", f"{m['confidence']:.0%}", tr(STL.get(m["status"], m["status"]))])
        statuses.append({"confirmed": "ok", "probable": "ok", "to_confirm": "warn", "unreadable": "ko"}[m["status"]])
    story.append(table(rows, (0.09, 0.08, 0.13, 0.13, 0.12, 0.08, 0.09, 0.08, 0.09, 0.11), status_col=9, statuses=statuses))
    per = it.get("peripheral") or {}
    if per.get("chains"):
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(tr("Cadeias de cotas periféricas (cima / baixo / esquerda / direita) — comparação e incoerências"), S["h2"]))
        rws = [[tr("Cadeia"), tr("Lado"), tr("Partielles"), tr("Somme"), tr("Total escrito"), tr("Desvio"), tr("Estado")]]
        sts = []
        for c in per["chains"]:
            tot = c.get("total_m") if c.get("total_m") is not None else c.get("reference_total_m")
            rws.append([c["chain_id"], tr(c["side"]), Paragraph(_e(" + ".join(f"{x['value_m']:.2f}" for x in c["partials"])), S["body"]), f"{c['sum_m']:.2f} m",
                        (f"{tot:.2f} m" + ("" if c.get("total_m") is not None else " " + tr("(vizinha, cadeia parcial)"))) if tot is not None else "—",
                        f"{c['difference_mm']:+.0f} mm" if c.get("difference_mm") is not None else "—",
                        tr({"ok": "OK", "warn": "écart", "ko": "a verificar", "no_total": "sem total"}[c["status"]])])
            sts.append({"ok": "ok", "warn": "warn", "ko": "ko", "no_total": "warn"}[c["status"]])
        story.append(table(rws, (0.09, 0.09, 0.42, 0.1, 0.14, 0.08, 0.08), status_col=6, statuses=sts))
        for x in per.get("inconsistencies") or []:
            story.append(Paragraph(f"<font color='{('#dc2626' if x['status'] == 'ko' else '#d97706')}'><b>{tr('Incoerência' if x['status'] == 'ko' else 'A verificar')}</b></font> — {_e(x['detail'])}", S["body"]))
        if not per.get("inconsistencies"):
            story.append(Paragraph(tr("Nenhuma incoerência entre as cadeias opostas."), S["body"]))
    eq = it.get("closure_equations") or []
    if eq:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(tr("Equações de fecho (Σ espessuras + Σ vãos = cota exterior)"), S["h2"]))
        rws = [[tr("Fila"), tr("Plano"), tr("Somme"), tr("Cote ext."), tr("Desvio"), tr("Estado")]]
        sts = []
        for r in eq:
            f = " + ".join(f"{t['value_m']:.2f}" for t in r["terms"])
            rws.append([r["row_id"], Paragraph(_e(f), S["body"]), f"{r['sum_m']:.3f} m", f"{r['written_exterior_m']:.2f} m" if r.get("written_exterior_m") is not None else "—",
                        f"{r['difference_m'] * 1000:+.0f} mm" if r.get("difference_m") is not None else "—",
                        tr({"closed": "fermée", "open": "ouverte", "not_compared": "não comparada"}[r["status"]])])
            sts.append({"closed": "ok", "open": "ko", "not_compared": "warn"}[r["status"]])
        story.append(table(rws, (0.1, 0.5, 0.1, 0.1, 0.1, 0.1), status_col=5, statuses=sts))
    if overlay_png:
        story.append(PageBreak())
        story.append(Paragraph(tr("Anexo gráfico — dimensões interiores parede a parede"), S["h2"]))
        story.append(Paragraph(tr("Cada medição liga as duas faces exatas (extremidades marcadas); cor: verde = confirmada por uma cota escrita, azul = medição geométrica provável, laranja = a confirmar, vermelho = ilegível. Paredes detetadas a cinzento com o seu identificador."), S["muted"]))
        Wp, Hp = landscape(A4)
        story.append(_fit_image(overlay_png, Wp - 28 * mm, Hp - 56 * mm))


def _story_page_body(story, report, overlay_png, S, page_title: str):
    story.append(Spacer(1, 3 * mm))
    _story_summary(story, report, S)
    story.append(Spacer(1, 3 * mm))
    _story_items(story, report, S)
    _story_facades(story, report, S)
    _story_elements(story, report, S)
    _story_auto_spans(story, report, S)
    _story_chains(story, report, S)
    _story_surfaces(story, report, S)
    _story_geometry(story, report.get("geometry"), S)
    story.append(PageBreak())
    story.append(Paragraph(page_title, S["h2"]))
    W, H = landscape(A4)
    story.append(_fit_image(overlay_png, W - 28 * mm, H - 48 * mm))
    _story_interior(story, report, S, None)


_LEGEND = ("Legenda da planta anotada: <font color=\'#16a34a\'><b>verde</b></font> = cota conforme · <font color=\'#ea580c\'><b>laranja</b></font> = diferença próxima da tolerância, a verificar · <font color=\'#dc2626\'><b>vermelho</b></font> = incoerência entre a cota indicada e a medição. As diferenças positivas significam que a medição é maior do que a cota inscrita. Leitura IA: posições das linhas de cota aproximadas (±1-2 %) — as incoerências assinaladas devem ser confirmadas na planta original.")


def _doc(buf):
    return SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                             topMargin=12 * mm, bottomMargin=14 * mm,
                             title="Controlo das cotas", author="ConstruPilot")


def _scope_box(text: str, S, width: float = landscape(A4)[0] - 28 * mm):
    t = Table([[Paragraph(text, S["body"])]], colWidths=[width])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, ORANGE), ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def build_cotes_pdf(plan: dict, page_index: int, report: dict, overlay_png: bytes,
                    branding: dict | None, interior_png: bytes | None = None) -> bytes:
    S = _styles()
    buf = io.BytesIO()
    doc = _doc(buf)
    story: list = []
    story += cover_story(plan, page_index, report, branding, PDF_LANG.get(), S, landscape(A4)[0] - 28 * mm)
    story.append(_scope_box(disclaimer(plan, page_index, report, branding, PDF_LANG.get()), S))
    story.append(PageBreak())
    story.append(Paragraph("CONTROLO DAS COTAS", S["kicker"]))
    story.append(Paragraph(f"{plan.get('filename') or 'Planta'} — page {page_index + 1}", S["h1"]))
    story.append(Paragraph(
        f"Relatório gerado em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · Cada cota inscrita na planta é medida à escala e comparada com o seu valor indicado.",
        S["muted"]))
    story.append(Spacer(1, 4 * mm))
    _story_summary(story, report, S)
    story.append(Spacer(1, 3 * mm))
    _story_items(story, report, S)
    _story_facades(story, report, S)
    _story_elements(story, report, S)
    _story_auto_spans(story, report, S)
    _story_chains(story, report, S)
    _story_surfaces(story, report, S)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_LEGEND, S["muted"]))
    _story_geometry(story, report.get("geometry"), S)
    story.append(PageBreak())
    story.append(Paragraph("Planta original — cotas medidas", S["h2"]))
    W, H = landscape(A4)
    story.append(_fit_image(overlay_png, W - 28 * mm, H - 48 * mm))
    _story_interior(story, report, S, interior_png)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def build_cotes_pdf_multi(plan: dict, bundle: list[tuple[int, dict, bytes]], agg: dict,
                          branding: dict | None) -> bytes:
    """Rapport global : synthèse par page puis, pour chaque page, détail + plan annoté."""
    S = _styles()
    buf = io.BytesIO()
    doc = _doc(buf)
    story: list = []
    _story_header_branding(story, branding, S)
    story.append(Paragraph("CONTROLO DAS COTAS — RELATÓRIO GLOBAL", S["kicker"]))
    story.append(Paragraph(f"{plan.get('filename') or 'Planta'} — {agg['pages']} página(s) controlada(s)", S["h1"]))
    story.append(Paragraph(
        f"Relatório gerado em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC.", S["muted"]))
    if bundle:
        story.append(Spacer(1, 2 * mm))
        story.append(_scope_box(disclaimer(plan, bundle[0][0], bundle[0][1], branding, PDF_LANG.get()), S))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f"<font color='{RL_COL[agg['verdict']].hexval()}'><b>Verdict global : {LABEL[agg['verdict']]}</b></font> — {agg['total']} cotas controladas: {agg['ok']} OK, {agg['warn']} a verificar, <b>{agg['ko']} incohérence(s)</b>{(' · ' + str(agg['ignored']) + ' ignorée(s)' if agg.get('ignored') else '')} · {agg['chains_total']} cadeia(s) de cotas ({agg['chains_ko']} incoerente(s)) · diferença máx. {agg['max_delta_cm']:.0f} cm.",
        S["body"]))
    story.append(Spacer(1, 3 * mm))
    rows = [["Página", "Cotas", "OK", "A verificar", "Incoerências", "Cadeias KO", "Diferença máx.", "Verdict"]]
    statuses = []
    for idx, rep, _ in bundle:
        sm = rep["summary"]
        rows.append([f'Página {idx + 1}', str(sm["total"]), str(sm["ok"]), str(sm["warn"]), str(sm["ko"]),
                     f"{sm['chains_ko']}/{sm['chains_total']}", f"{sm['max_delta_cm']:.0f} cm", LABEL[sm["verdict"]]])
        statuses.append(sm["verdict"])
    story.append(_tbl(rows, [26 * mm, 22 * mm, 20 * mm, 26 * mm, 30 * mm, 28 * mm, 26 * mm, 40 * mm],
                      S, status_col=7, statuses=statuses))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_LEGEND, S["muted"]))
    for idx, rep, png in bundle:
        story.append(PageBreak())
        story.append(Paragraph(f"PAGE {idx + 1}", S["kicker"]))
        story.append(Paragraph(f"{plan.get('filename') or 'Planta'} — page {idx + 1}", S["h1"]))
        _story_page_body(story, rep, png, S, f'Página {idx + 1} — planta original, cotas medidas')
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY)
    canvas.drawRightString(doc.pagesize[0] - 14 * mm, 8 * mm,
                           tr(f'ConstruPilot · Controlo das cotas · página {doc.page}'))
    canvas.setFillColor(ORANGE)
    canvas.rect(14 * mm, 8 * mm, 18 * mm, 1.2, fill=1, stroke=0)
    canvas.restoreState()
