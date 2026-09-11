"""Rapport PDF « Contrôle des cotes » : plan annoté (cotes mesurées) + tableaux détaillés."""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from engines.pdf_takeoff import DARK, GREY, LIGHT_GREY, ORANGE, _story_header_branding, _styles

COL = {"ok": (22, 163, 74), "warn": (234, 88, 12), "ko": (220, 38, 38), "ignored": (148, 163, 184), "nd": (100, 116, 139)}
RL_COL = {"ok": colors.HexColor("#16a34a"), "warn": colors.HexColor("#ea580c"),
          "ko": colors.HexColor("#dc2626"), "ignored": colors.HexColor("#94a3b8"), "nd": colors.HexColor("#64748b")}
LABEL = {"ok": "OK", "warn": "À vérifier", "ko": "INCOHÉRENCE", "ignored": "Ignorée", "nd": "NON DÉTERMINÉ"}
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
        col = COL[it["status"]] + (255,)
        p1, p2 = (it["x1"], it["y1"]), (it["x2"], it["y2"])
        d.line([p1, p2], fill=col, width=lw)
        horiz = it["orientation"] != "v"
        for (x, y) in (p1, p2):
            if horiz:
                d.line([(x, y - tick), (x, y + tick)], fill=col, width=lw)
            else:
                d.line([(x - tick, y), (x + tick, y)], fill=col, width=lw)
        if it["status"] == "ok":
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
        f"<font color='{RL_COL[sm['verdict']].hexval()}'><b>Verdict : {verdict}</b></font> — "
        f"{sm['total']} cotes contrôlées : {sm['ok']} OK, {sm['warn']} à vérifier, "
        f"<b>{sm['ko']} incohérence(s)</b>"
        f"{' · ' + str(sm['ignored']) + ' ignorée(s)' if sm.get('ignored') else ''} · "
        f"{sm['chains_total']} chaîne(s) de cotes "
        f"({sm['chains_ko']} incohérente(s)) · écart max {sm['max_delta_cm']:.0f} cm.", S["body"]))
    if report.get("abstention"):
        story.append(Paragraph(f"<b>Abstention ConstruPilot :</b> {report['abstention']} "
                               f"({sm.get('nd', 0)} cote(s) non déterminée(s)).", S["body"]))
    src = {"ai": "lecture IA du plan (image)", "dxf": "cotes exactes du fichier DXF"}.get(
        (report.get("reading") or {}).get("source"), "—")
    story.append(Paragraph(
        f"Tolérance : ±{tol['pct']} % (ou ±{tol['cm']} cm) · Source des cotes : {src} · "
        f"Échelle : {cal.get('pixels_per_meter', 0):.1f} px/m ({cal.get('method', '—')}"
        f"{', calibrée automatiquement' if report.get('auto_calibrated') else ''}).", S["muted"]))


def _story_items(story, report, S):
    story.append(Paragraph("Détail des cotes contrôlées", S["h2"]))
    rows = [["#", "Localisation", "Orient.", "Cote indiquée", "Mesuré", "Écart", "Écart %", "Conf.", "Statut"]]
    statuses = []
    for it in sorted(report["items"], key=lambda x: (_RANK[x["status"]], x["index"])):
        loc = it.get("location") or "—"
        if it.get("edited") and it.get("original_m") is not None:
            loc += f" <i>(corrigée : {it['original_m']:.2f} → {it['indicated_m']:.2f})</i>"
        rows.append([str(it["index"]), Paragraph(loc, S["muted"]),
                     ORIENT.get(it["orientation"], "—"), f"{it['indicated_m']:.2f} m",
                     f"{it['measured_m']:.2f} m", f"{it['delta_cm']:+.1f} cm",
                     f"{it['delta_pct']:+.1f} %" if it.get("delta_pct") is not None else "—",
                     f"{int(round(it['confidence'] * 100))} %", LABEL[it["status"]]])
        statuses.append(it["status"])
    story.append(_tbl(rows, [9 * mm, 60 * mm, 16 * mm, 24 * mm, 20 * mm, 20 * mm, 18 * mm, 13 * mm, 26 * mm],
                      S, status_col=8, statuses=statuses))


def _story_chains(story, report, S):
    chains = report.get("chains") or []
    story.append(Paragraph("Chaînes de cotes (partielles = totale ?)", S["h2"]))
    if not chains:
        story.append(Paragraph("Aucune chaîne de cotes détectée sur cette page.", S["muted"]))
        return
    rows = [["Cote totale", "Cotes partielles", "Somme", "Écart", "Statut"]]
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
    story.append(Paragraph("Surfaces écrites sur le plan ↔ surfaces mesurées", S["h2"]))
    rows = [["Pièce", "Écrite", "Mesurée", "Écart %"]]
    for m in matches:
        rows.append([m.get("room_name") or m.get("ai_name") or "—", f"{m['written_m2']:.2f} m²",
                     f"{m['measured_m2']:.2f} m²", f"{m['delta_pct']:+.1f} %"])
    story.append(_tbl(rows, [80 * mm, 30 * mm, 30 * mm, 30 * mm], S))


_LVL_COL = {"VERT": "#16a34a", "BLEU": "#2563eb", "JAUNE": "#ca8a04", "ORANGE": "#ea580c", "ROUGE": "#dc2626"}
_LVL_LABEL = {"VERT": "Cohérent", "BLEU": "Information", "JAUNE": "À vérifier",
              "ORANGE": "Incohérence", "ROUGE": "Incohérence majeure"}


def _e(s) -> str:
    from xml.sax.saxutils import escape
    return escape(str(s if s is not None else ""))


def _story_geometry(story, geo: dict, S):
    """Section « Analyse géométrique ConstruPilot » (double lecture IA)."""
    if not geo:
        return
    story.append(PageBreak())
    story.append(Paragraph("ANALYSE GÉOMÉTRIQUE CONSTRUPILOT — DOUBLE LECTURE", S["kicker"]))
    lvl = geo.get("niveau_global", "VERT")
    story.append(Paragraph(
        f"<font color='{_LVL_COL[lvl]}'><b>Niveau global : {_LVL_LABEL[lvl]}</b></font> — "
        f"{len(geo.get('anomalies') or [])} anomalie(s) · passage 2 : "
        f"{(geo.get('double_lecture') or {}).get('confirmees', 0)} confirmée(s), "
        f"{(geo.get('double_lecture') or {}).get('infirmees', 0)} infirmée(s).", S["h1"]))
    doc = geo.get("document") or {}
    if doc:
        story.append(Paragraph("Cartouche : " + " · ".join(
            f"{k.replace('_', ' ')} : {_e(v)}" for k, v in doc.items() if v), S["muted"]))
    rep = geo.get("reponses") or {}
    if rep:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>1. Fermeture mathématique :</b> {_e(rep.get('fermeture') or 'NON INDIQUÉ')}", S["body"]))
        story.append(Paragraph(f"<b>2. Compatibilité géométrique :</b> {_e(rep.get('compatibilite') or 'NON INDIQUÉ')}", S["body"]))
        av = rep.get("a_verifier") or []
        story.append(Paragraph("<b>3. À vérifier avant utilisation :</b> " + (_e(" ; ".join(map(str, av))) if av else "—"), S["body"]))
    if geo.get("synthese"):
        story.append(Paragraph(_e(geo["synthese"]), S["muted"]))
    ferm = geo.get("fermetures") or []
    if ferm:
        story.append(Paragraph("Fermeture des chaînes", S["h2"]))
        rows = [["Dir.", "Chaîne (valeurs inscrites)", "Calculé", "Cote plan", "Erreur", "Statut"]]
        for f in ferm:
            rows.append([_e(f.get("direction")), Paragraph(_e(f.get("chaine")), S["muted"]),
                         f"{float(f.get('cote_calculee_m') or 0):.2f} m", f"{float(f.get('cote_plan_m') or 0):.2f} m",
                         f"{float(f.get('erreur_m') or 0) * 100:+.1f} cm", _e(f.get("statut"))])
        story.append(_tbl(rows, [14 * mm, 110 * mm, 24 * mm, 24 * mm, 24 * mm, 40 * mm], S))
    mat = geo.get("matrice") or []
    if mat:
        story.append(Paragraph("Matrice de cohérence", S["h2"]))
        rows = [["Élément", "Valeur plan", "Calculée", "Écart", "Source du calcul", "Confiance", "Statut"]]
        for m in mat:
            rows.append([Paragraph(_e(m.get("element")), S["muted"]), f"{float(m.get('valeur_plan_m') or 0):.2f} m",
                         f"{float(m.get('valeur_calculee_m') or 0):.2f} m", f"{float(m.get('ecart_m') or 0) * 100:+.1f} cm",
                         Paragraph(_e(m.get("source_calcul")), S["muted"]), _e(m.get("confiance")), _e(m.get("statut"))])
        story.append(_tbl(rows, [50 * mm, 22 * mm, 22 * mm, 20 * mm, 70 * mm, 22 * mm, 34 * mm], S))
    def _fmt(section, it):
        if section == "controles_croises":
            vals = " / ".join(str(v) for v in (it.get("valeurs") or []))
            return f"{it.get('description', '')} — valeurs : {vals} — écart {float(it.get('ecart_m') or 0) * 100:+.1f} cm — {it.get('statut', '')}"
        if section == "facades":
            causes = " ; ".join(map(str, it.get("causes_possibles") or []))
            return (f"{it.get('nom', '')} : {float(it.get('longueur_plan_m') or 0):.2f} m vs opposée "
                    f"{float(it.get('longueur_opposee_m') or 0):.2f} m — écart {float(it.get('ecart_m') or 0) * 100:+.1f} cm — "
                    f"{it.get('statut', '')}{' (' + causes + ')' if causes else ''}")
        segs = " ; ".join(f"{s.get('segment', '')} : {s.get('statut', '')}"
                          + (f" ({s.get('decalage_mm')} mm)" if s.get("decalage_mm") else "")
                          for s in (it.get("segments") or []) if isinstance(s, dict))
        return f"{it.get('nom', '')} — {segs}"

    for section, title in (("controles_croises", "Contrôles croisés"), ("facades", "Façades"), ("alignements", "Alignements")):
        items = [it for it in (geo.get(section) or []) if isinstance(it, dict)]
        if items:
            story.append(Paragraph(title, S["h2"]))
            for it in items:
                story.append(Paragraph("• " + _e(_fmt(section, it)), S["muted"]))
    anoms = geo.get("anomalies") or []
    story.append(Paragraph("Anomalies détaillées", S["h2"]))
    if not anoms:
        story.append(Paragraph("Aucune anomalie détectée par l'analyse géométrique.", S["muted"]))
    for a in anoms:
        v = a.get("verification") or {}
        story.append(Paragraph(
            f"<font color='{_LVL_COL.get(a['niveau'], '#64748b')}'><b>ANOMALIE #{a['numero']} — {_LVL_LABEL.get(a['niveau'], a['niveau'])}</b></font>"
            f" · confiance {_e(a.get('confiance'))} · passage 2 : {_e(v.get('verdict') or '—')}", S["body"]))
        for label, key in (("Localisation", "localisation"), ("Donnée du plan", "donnee_plan"), ("Calcul ConstruPilot", "calcul"),
                           ("Formule", "formule"), ("Résultat", "resultat"), ("Explication", "explication"),
                           ("Action recommandée", "action")):
            if a.get(key):
                story.append(Paragraph(f"<b>{label} :</b> {_e(a[key])}", S["muted"]))
        if a.get("ecart_mm") is not None:
            story.append(Paragraph(f"<b>Écart :</b> {a['ecart_mm']:+.0f} mm", S["muted"]))
        if a.get("hypotheses"):
            story.append(Paragraph("<b>Hypothèses possibles :</b> " + _e(" · ".join(a["hypotheses"])), S["muted"]))
        if v.get("recalcul") or v.get("commentaire"):
            story.append(Paragraph(f"<b>Recalcul passage 2 :</b> {_e(v.get('recalcul'))} {_e(v.get('commentaire'))}", S["muted"]))
        story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Seuils de détection ConstruPilot (0–2 mm négligeable · 2–10 mm faible · 10–30 mm à vérifier · 30–100 mm anomalie "
        "importante · > 100 mm anomalie majeure) — ce ne sont pas des tolérances réglementaires d'exécution. "
        "Les hypothèses de correction ne modifient jamais le plan.", S["muted"]))


def _story_page_body(story, report, overlay_png, S, page_title: str):
    story.append(Spacer(1, 3 * mm))
    _story_summary(story, report, S)
    story.append(Spacer(1, 3 * mm))
    _story_items(story, report, S)
    _story_chains(story, report, S)
    _story_surfaces(story, report, S)
    _story_geometry(story, report.get("geometry"), S)
    story.append(PageBreak())
    story.append(Paragraph(page_title, S["h2"]))
    W, H = landscape(A4)
    story.append(_fit_image(overlay_png, W - 28 * mm, H - 48 * mm))


_LEGEND = ("Légende du plan annoté : <font color='#16a34a'><b>vert</b></font> = cote conforme · "
           "<font color='#ea580c'><b>orange</b></font> = écart proche de la tolérance, à vérifier · "
           "<font color='#dc2626'><b>rouge</b></font> = incohérence entre la cote indiquée et la mesure. "
           "Les écarts positifs signifient que la mesure est plus grande que la cote inscrite. "
           "Lecture IA : positions des traits de cote approximatives (±1-2 %) — les incohérences "
           "signalées doivent être confirmées sur le plan d'origine.")


def _doc(buf):
    return SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                             topMargin=12 * mm, bottomMargin=14 * mm,
                             title="Contrôle des cotes", author="ConstruPilot")


def build_cotes_pdf(plan: dict, page_index: int, report: dict, overlay_png: bytes,
                    branding: dict | None) -> bytes:
    S = _styles()
    buf = io.BytesIO()
    doc = _doc(buf)
    story: list = []
    _story_header_branding(story, branding, S)
    story.append(Paragraph("CONTRÔLE DES COTES", S["kicker"]))
    story.append(Paragraph(f"{plan.get('filename') or 'Plan'} — page {page_index + 1}", S["h1"]))
    story.append(Paragraph(
        f"Rapport généré le {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        "Chaque cote inscrite sur le plan est mesurée à l'échelle et comparée à sa valeur indiquée.",
        S["muted"]))
    story.append(Spacer(1, 4 * mm))
    _story_summary(story, report, S)
    story.append(Spacer(1, 3 * mm))
    _story_items(story, report, S)
    _story_chains(story, report, S)
    _story_surfaces(story, report, S)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_LEGEND, S["muted"]))
    _story_geometry(story, report.get("geometry"), S)
    story.append(PageBreak())
    story.append(Paragraph("Plan original — cotes mesurées", S["h2"]))
    W, H = landscape(A4)
    story.append(_fit_image(overlay_png, W - 28 * mm, H - 48 * mm))
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
    story.append(Paragraph("CONTRÔLE DES COTES — RAPPORT GLOBAL", S["kicker"]))
    story.append(Paragraph(f"{plan.get('filename') or 'Plan'} — {agg['pages']} page(s) contrôlée(s)", S["h1"]))
    story.append(Paragraph(
        f"Rapport généré le {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC.", S["muted"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f"<font color='{RL_COL[agg['verdict']].hexval()}'><b>Verdict global : {LABEL[agg['verdict']]}</b></font> — "
        f"{agg['total']} cotes contrôlées : {agg['ok']} OK, {agg['warn']} à vérifier, <b>{agg['ko']} incohérence(s)</b>"
        f"{' · ' + str(agg['ignored']) + ' ignorée(s)' if agg.get('ignored') else ''} · "
        f"{agg['chains_total']} chaîne(s) de cotes ({agg['chains_ko']} incohérente(s)) · écart max {agg['max_delta_cm']:.0f} cm.",
        S["body"]))
    story.append(Spacer(1, 3 * mm))
    rows = [["Page", "Cotes", "OK", "À vérifier", "Incohérences", "Chaînes KO", "Écart max", "Verdict"]]
    statuses = []
    for idx, rep, _ in bundle:
        sm = rep["summary"]
        rows.append([f"Page {idx + 1}", str(sm["total"]), str(sm["ok"]), str(sm["warn"]), str(sm["ko"]),
                     f"{sm['chains_ko']}/{sm['chains_total']}", f"{sm['max_delta_cm']:.0f} cm", LABEL[sm["verdict"]]])
        statuses.append(sm["verdict"])
    story.append(_tbl(rows, [26 * mm, 22 * mm, 20 * mm, 26 * mm, 30 * mm, 28 * mm, 26 * mm, 40 * mm],
                      S, status_col=7, statuses=statuses))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_LEGEND, S["muted"]))
    for idx, rep, png in bundle:
        story.append(PageBreak())
        story.append(Paragraph(f"PAGE {idx + 1}", S["kicker"]))
        story.append(Paragraph(f"{plan.get('filename') or 'Plan'} — page {idx + 1}", S["h1"]))
        _story_page_body(story, rep, png, S, f"Page {idx + 1} — plan original, cotes mesurées")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY)
    canvas.drawRightString(doc.pagesize[0] - 14 * mm, 8 * mm,
                           f"ConstruPilot · Contrôle des cotes · page {doc.page}")
    canvas.setFillColor(ORANGE)
    canvas.rect(14 * mm, 8 * mm, 18 * mm, 1.2, fill=1, stroke=0)
    canvas.restoreState()
