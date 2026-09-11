"""Rapport de contrôle du plan ConstruPilot (PDF A4) — structure §18-§37 du prompt système.

Couverture + résumé → résumé exécutif & données → grandes cotes → chaînes → façades/alignements →
plan annoté (marqueurs CP-xx) → fiches CP-xx avec zoom → tableau général → checklist + conclusion.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (Image as RLImage, KeepTogether, PageBreak, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from engines.plan_pdf_i18n import LANG as PDF_LANG, Paragraph, cover_story, disclaimer, tr
from engines.plan_cotes_pdf import _scope_box

from engines.pdf_takeoff import DARK, GREY, LIGHT_GREY, ORANGE, _story_header_branding, _styles
from engines.plan_cotes_pdf import COL, _e, _fit_image, _font, _tbl

LVL_HEX = {"VERT": "#16a34a", "BLEU": "#2563eb", "JAUNE": "#ca8a04", "ORANGE": "#ea580c", "ROUGE": "#dc2626"}
LVL_LABEL = {"VERT": "Cohérent", "BLEU": "Information", "JAUNE": "À vérifier",
             "ORANGE": "Incohérence", "ROUGE": "Incohérence majeure"}
LVL_RGB = {"VERT": COL["ok"], "BLEU": (37, 99, 235), "JAUNE": (202, 138, 4), "ORANGE": COL["warn"], "ROUGE": COL["ko"]}
_STATUS_LVL = {"ok": "VERT", "warn": "JAUNE", "ko": "ORANGE", "nd": "BLEU", "ignored": "BLEU"}
_W = A4[0] - 28 * mm


def _m(v) -> str:
    try:
        return f"{float(v):.2f} m".replace(".", ",")
    except (TypeError, ValueError):
        return "NON INDIQUÉ"


def _cm(v_m) -> str:
    try:
        return f"{float(v_m) * 100:+.0f} cm"
    except (TypeError, ValueError):
        return "—"


def _lvl_from_status(statut: str | None, ecart_m) -> str:
    s = (statut or "").upper()
    if "MAJEURE" in s:
        return "ROUGE"
    if "INCOH" in s:
        return "ORANGE"
    if "VÉRIF" in s or "VERIF" in s:
        return "JAUNE"
    if "COH" in s:
        return "VERT"
    try:
        a = abs(float(ecart_m)) * 1000
    except (TypeError, ValueError):
        return "JAUNE"
    return "VERT" if a <= 2 else "BLEU" if a <= 10 else "JAUNE" if a <= 30 else "ORANGE" if a <= 100 else "ROUGE"


def build_controls(report: dict, geo: dict | None) -> list[dict]:
    """Liste unifiée des contrôles CP-xx (fermetures, anomalies IA, chaînes ConstruPilot, façades)."""
    items = {it["index"]: it for it in report.get("items") or []}
    ctrls: list[dict] = []

    def add(kind, titre, plan, calc, ecart_m, lvl, cotes, **extra):
        ctrls.append({"id": f"CP-{len(ctrls) + 1:02d}", "kind": kind, "titre": titre, "plan": plan, "calc": calc,
                      "ecart_m": ecart_m, "niveau": lvl, "cotes": [c for c in cotes if c in items], **extra})

    geo = geo or {}
    for i, f in enumerate(geo.get("fermetures") or []):
        idx = f.get("cote_plan_index")
        expl = next((x.get("texte") for x in geo.get("explications") or [] if x.get("fermeture_index") == i), "")
        hyps = [h for h in geo.get("hypotheses_fermeture") or [] if h.get("fermeture_index") == i]
        add("fermeture", f"Fermeture chaîne {f.get('direction', '')} — {_m(f.get('cote_plan_m'))}", f.get("cote_plan_m"),
            f.get("cote_calculee_m"), f.get("erreur_m"), _lvl_from_status(f.get("statut"), f.get("erreur_m")),
            [idx] if isinstance(idx, int) else [], chaine=f.get("chaine") or "", explication=expl, hypotheses=hyps)
    for a in geo.get("anomalies") or []:
        if a.get("niveau") == "VERT":
            continue
        ecart = (a.get("ecart_mm") or 0) / 1000 if a.get("ecart_mm") is not None else None
        add("anomalie", a.get("localisation") or "Anomalie", a.get("donnee_plan"), a.get("resultat"), ecart,
            a.get("niveau") or "JAUNE", a.get("cotes_index") or [], formule=a.get("formule") or "",
            calcul=a.get("calcul") or "", explication=a.get("explication") or "", hypotheses_txt=a.get("hypotheses") or [],
            action=a.get("action") or "", confiance=a.get("confiance") or "MOYEN",
            verification=(a.get("verification") or {}).get("verdict"),
            adversarial=(a.get("adversarial") or {}).get("verdict"), adv_attaque=(a.get("adversarial") or {}).get("attaque"))
    for c in report.get("chains") or []:
        lvl = _STATUS_LVL.get(c["status"], "JAUNE")
        add("chaine", f"Chaîne de cotes → cote #{c['total_index']} ({_m(c['total_m'])})", c["total_m"], c["sum_m"], c["delta_m"],
            lvl, [c["total_index"], *c["part_indexes"]],
            chaine=" + ".join(f"{v:.2f}".replace(".", ",") for v in c["parts_m"]))
    for f in geo.get("facades") or []:
        add("facade", f"Façades opposées — {f.get('nom', '')}", f.get("longueur_plan_m"), f.get("longueur_opposee_m"),
            f.get("ecart_m"), _lvl_from_status(f.get("statut"), f.get("ecart_m")), [],
            causes=f.get("causes_possibles") or [])
    return ctrls


def _marker_positions(ctrls, items_by_index):
    pos = []
    for c in ctrls:
        pts = [items_by_index[i] for i in c["cotes"] if i in items_by_index]
        if not pts:
            continue
        xs = [v for it in pts for v in (it["x1"], it["x2"])]
        ys = [v for it in pts for v in (it["y1"], it["y2"])]
        pos.append((c, (min(xs), min(ys), max(xs), max(ys))))
    return pos


def render_marked_plan(image_b64: str, ctrls: list[dict], report: dict) -> tuple[bytes, dict[str, bytes]]:
    """Plan annoté avec marqueurs CP-xx colorés + zooms par contrôle."""
    base = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    items = {it["index"]: it for it in report.get("items") or []}
    positions = _marker_positions(ctrls, items)
    img = base.copy()
    d = ImageDraw.Draw(img, "RGBA")
    scale = max(img.width, img.height) / 1000.0
    font = _font(max(11, 13 * scale))
    lw = max(2, int(3 * scale))
    for c, (x1, y1, x2, y2) in positions:
        rgb = LVL_RGB.get(c["niveau"], LVL_RGB["JAUNE"])
        pad = max(6, int(8 * scale))
        d.rectangle([x1 - pad, y1 - pad, x2 + pad, y2 + pad], outline=rgb + (230,), width=lw)
        txt = c["id"]
        bx1, by1, bx2, by2 = d.textbbox((0, 0), txt, font=font)
        tw, th = bx2 - bx1, by2 - by1
        lx, ly = max(0, x1 - pad), max(0, y1 - pad - th - 6)
        d.rectangle([lx, ly, lx + tw + 8, ly + th + 4], fill=rgb + (235,))
        d.text((lx + 4, ly + 2), txt, fill=(255, 255, 255, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    zooms: dict[str, bytes] = {}
    for c, (x1, y1, x2, y2) in positions:
        if c["niveau"] in ("VERT", "BLEU"):
            continue
        mx = max(80, int((x2 - x1) * 0.35)) + int(40 * scale)
        my = max(80, int((y2 - y1) * 0.35)) + int(40 * scale)
        crop = img.crop((max(0, int(x1 - mx)), max(0, int(y1 - my)), min(img.width, int(x2 + mx)), min(img.height, int(y2 + my))))
        zb = io.BytesIO()
        crop.save(zb, format="PNG")
        zooms[c["id"]] = zb.getvalue()
    return buf.getvalue(), zooms


def _cards(counts: dict, S):
    cells, style = [], [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 20),
                        ("FONTSIZE", (0, 1), (-1, 1), 7.5), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 8)]
    labels = [("total", "Contrôles réalisés", "#0A0D14"), ("VERT", "Éléments cohérents", LVL_HEX["VERT"]),
              ("JAUNE", "Points à vérifier", LVL_HEX["JAUNE"]), ("ORANGE", "Incohérences", LVL_HEX["ORANGE"]),
              ("ROUGE", "Incohérences majeures", LVL_HEX["ROUGE"])]
    for i, (k, lab, hexc) in enumerate(labels):
        cells.append((str(counts.get(k, 0)), tr(lab)))
        style.append(("BACKGROUND", (i, 0), (i, 1), colors.HexColor(hexc)))
    t = Table([[c[0] for c in cells], [c[1] for c in cells]], colWidths=[_W / 5 - 2 * mm] * 5, hAlign="LEFT")
    t.setStyle(TableStyle(style))
    return t


def _equation(chaine: str, calc, plan, ecart_m, lvl, S):
    parts = [p.strip() for p in str(chaine or "").replace("−", "-").split("+") if p.strip()]
    lines = ["<font face='Courier'>" + _e(parts[0]) + "</font>"] if parts else []
    lines += ["<font face='Courier'>+ " + _e(p) + "</font>" for p in parts[1:]]
    lines.append("<font face='Courier'>────────</font>")
    lines.append(f"<font face='Courier'><b>= {_e(_m(calc))}</b></font>")
    body = "<br/>".join(lines)
    txt = (f"{body}<br/><br/>Cote indiquée sur le plan : <b>{_e(_m(plan))}</b> · Valeur recalculée : <b>{_e(_m(calc))}</b>"
           f"<br/>ÉCART : <b>{_e(_cm(ecart_m))}</b> · STATUT : <font color='{LVL_HEX[lvl]}'><b>{LVL_LABEL[lvl]}</b></font>")
    t = Table([[Paragraph(txt, S["body"])]], colWidths=[_W - 4 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(LVL_HEX[lvl])),
                           ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _fiche(c: dict, zoom: bytes | None, S):
    lvl = c["niveau"]
    block = [Paragraph(f"<font color='{LVL_HEX[lvl]}'><b>{c['id']} — {LVL_LABEL[lvl]}</b></font> · {_e(c['titre'])}", S["h2"])]
    if zoom:
        block.append(_fit_image(zoom, _W * 0.6, 70 * mm))
    if c.get("chaine"):
        block.append(_equation(c["chaine"], c["calc"], c["plan"], c["ecart_m"], lvl, S))
    else:
        block.append(Paragraph(
            f"Donnée du plan : <b>{_e(c.get('plan') or 'NON INDIQUÉ')}</b> · Valeur recalculée : <b>{_e(c.get('calc') or '—')}</b>"
            f" · Écart : <b>{_e(_cm(c['ecart_m']))}</b>" + (f"<br/>Formule : <font face='Courier'>{_e(c['formule'])}</font>" if c.get("formule") else ""), S["body"]))
    if c.get("calcul"):
        block.append(Paragraph(f"<b>Calcul ConstruPilot :</b> {_e(c['calcul'])}", S["muted"]))
    if c.get("explication"):
        block.append(Paragraph(f"<b>Explication :</b> {_e(c['explication'])}", S["body"]))
    for h in c.get("hypotheses") or []:
        block.append(Paragraph(
            f"<b>HYPOTHÈSE {_e(h.get('hypothese', ''))}</b> — {_e(h.get('dimension', ''))} devrait être <b>{_e(_m(h.get('valeur_theorique_m')))}</b>"
            f" au lieu de {_e(_m(h.get('au_lieu_de_m')))} · <font face='Courier'>{_e(h.get('calcul', ''))}</font>", S["muted"]))
    if c.get("hypotheses"):
        block.append(Paragraph("<i>Hypothèses mathématiques permettant la fermeture de la chaîne — le plan n'est pas modifié.</i>", S["muted"]))
    if c.get("hypotheses_txt"):
        block.append(Paragraph("<b>Hypothèses possibles :</b> " + _e(" · ".join(c["hypotheses_txt"])), S["muted"]))
    if c.get("causes"):
        block.append(Paragraph("<b>Causes possibles :</b> " + _e(" ; ".join(map(str, c["causes"]))), S["muted"]))
    if c.get("action"):
        block.append(Paragraph(f"<b>Action recommandée :</b> {_e(c['action'])}", S["muted"]))
    meta = f"Confiance : {_e(c.get('confiance') or 'ÉLEVÉ')}"
    if c.get("verification"):
        meta += f" · Recalcul indépendant (passage 2) : {_e(c['verification'])}"
    if c.get("adversarial"):
        meta += f" · Contrôle adversarial : <b>{_e(c['adversarial'])}</b>"
        if c.get("adv_attaque"):
            meta += f" ({_e(c['adv_attaque'])})"
    if c.get("cotes"):
        meta += " · Cotes concernées : " + ", ".join(f"#{i}" for i in c["cotes"])
    block.append(Paragraph(meta, S["muted"]))
    block.append(Spacer(1, 5 * mm))
    return KeepTogether(block)


def build_control_report(plan: dict, page_index: int, report: dict, image_b64: str, branding: dict | None,
                         court: bool = False) -> bytes:
    S = _styles()
    geo = report.get("geometry") or {}
    ctrls = build_controls(report, geo)
    marked_png, zooms = render_marked_plan(image_b64, ctrls, report)
    counts = {lv: sum(1 for c in ctrls if c["niveau"] == lv) for lv in LVL_HEX}
    active_items = [it for it in report.get("items") or [] if not it.get("ignored")]
    nd_items = [it for it in active_items if it["status"] == "nd"]
    for it in active_items:
        if it["status"] == "nd":
            continue
        lv = it.get("niveau") or _STATUS_LVL.get(it["status"], "JAUNE")
        counts[lv] = counts.get(lv, 0) + 1
    counts["VERT"] += counts.pop("BLEU", 0)
    counts["total"] = len(ctrls) + len(active_items)
    doc_info = geo.get("document") or {}
    now = datetime.now(timezone.utc)
    rid = f"CP-{plan.get('plan_id', '')[-6:].upper()}-P{page_index + 1}-{now.strftime('%y%m%d')}"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"Rapport de contrôle du plan {rid}", author="ConstruPilot")
    story: list = []

    # PAGE 1 — couverture + résumé
    story += cover_story(plan, page_index, report, branding, PDF_LANG.get(), S, _W)
    story += [_scope_box(disclaimer(plan, page_index, report, branding, PDF_LANG.get()), S, _W), PageBreak()]
    story.append(Paragraph("Analyse automatique de cohérence du plan — contrôle géométrique et dimensionnel", S["h2"]))
    story.append(Spacer(1, 4 * mm))
    rows = [["Projet", doc_info.get("projet") or "NON INDIQUÉ"], ["Localisation", doc_info.get("localisation") or "NON INDIQUÉ"],
            ["Document analysé", f"{plan.get('filename') or 'plan'} — page {page_index + 1}"],
            ["Type de plan", doc_info.get("type_plan") or doc_info.get("discipline") or "NON INDIQUÉ"],
            ["Date du plan", doc_info.get("date") or "NON INDIQUÉ"], ["Révision", doc_info.get("revision") or "NON INDIQUÉ"],
            ["Échelle", doc_info.get("echelle") or (report.get("reading") or {}).get("scale_text") or "NON INDIQUÉ"],
            ["Date de l'analyse", now.strftime("%d/%m/%Y %H:%M UTC")], ["Identifiant du rapport", rid]]
    t = Table([[Paragraph(f"<b>{_e(k)}</b>", S["body"]), Paragraph(_e(tr(v)), S["body"])] for k, v in rows], colWidths=[50 * mm, _W - 50 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 5 * mm), Paragraph("Objet du rapport", S["h2"])]
    story.append(Paragraph(
        f"Contrôle automatique de cohérence géométrique et dimensionnelle du plan « {_e(plan.get('filename') or 'plan')} » "
        f"(page {page_index + 1}) : lecture des cotes inscrites, recalcul indépendant des chaînes et des grandes cotes, "
        "comparaison des façades opposées, contrôle des alignements et identification des points à clarifier avant "
        "utilisation des dimensions pour l'implantation ou l'exécution.", S["body"]))
    murs = geo.get("murs") or {}
    hyp = []
    if murs.get("epaisseurs_m"):
        hyp.append("épaisseur(s) de murs prise(s) en compte : " + ", ".join(_m(v) for v in murs["epaisseurs_m"]) + " (LUE / DÉDUIT)")
    hyp.append("référence de cotation : " + (murs.get("reference_cotation") or "non déterminable avec certitude — HYPOTHÈSE : cotes entre faces"))
    hyp.append(f"tolérance de détection : ±{report['tolerance']['pct']} % ou ±{report['tolerance']['cm']} cm ; seuils mm ConstruPilot pour les niveaux")
    cal = report.get("calibration") or {}
    hyp.append("échelle : " + (f"{cal.get('pixels_per_meter', 0):.0f} px/m ({cal.get('method', '—')})")
               + (f" — échelle effective du PDF 1/{cal['effective_scale_denominator']:g}"
                  + (f" alors que le cartouche indique 1/{cal['scale_denominator']} (PDF réduit à l'impression)"
                     if cal.get("scale_denominator") and abs(cal["effective_scale_denominator"] - cal["scale_denominator"]) > 0.5 else "")
                  if cal.get("effective_scale_denominator") else ""))
    cross = (report.get("reading") or {}).get("cross") or {}
    if cross:
        hyp.append(f"source des cotes : extraction vectorielle du PDF ({cross.get('vector', 0)} cotes mesurées au millimètre entre "
                   f"lignes d'attache) croisée avec la lecture IA ({cross.get('confirmed', 0)} confirmées, "
                   f"{cross.get('ai_only', 0)} lues par l'IA seule et non vérifiées"
                   + (f", {len(cross['divergences'])} divergence(s) de lecture tranchée(s) par le texte vectoriel" if cross.get("divergences") else "") + ")")
    story.append(Paragraph("Hypothèses retenues", S["h2"]))
    for line in hyp:
        story.append(Paragraph(f"• {_e(line)}", S["muted"]))
    if report.get("abstention"):
        story.append(Paragraph(f"<b>Abstention ConstruPilot :</b> {_e(report['abstention'])} "
                               f"{len(nd_items)} cote(s) classée(s) NON DÉTERMINÉ.", S["body"]))
    story += [Spacer(1, 4 * mm), Paragraph("Résumé du contrôle", S["h2"]), _cards(counts, S), Spacer(1, 6 * mm)]
    story.append(Paragraph(
        "Ce rapport est produit par le contrôle ConstruPilot : chaque cote est relue, mesurée à l'échelle et confrontée aux autres "
        "données du plan par recalcul indépendant. Les valeurs recalculées et les hypothèses sont toujours distinguées des valeurs "
        "inscrites. Ce document n'est pas une étude d'exécution : les points signalés sont des points nécessitant vérification.", S["muted"]))

    # PAGE 2 — résumé exécutif + données extraites
    story.append(PageBreak())
    story.append(Paragraph("RÉSUMÉ EXÉCUTIF", S["kicker"]))
    story.append(Paragraph("Résultat global", S["h1"]))
    for lv in ("VERT", "JAUNE", "ORANGE", "ROUGE"):
        if counts.get(lv):
            story.append(Paragraph(f"<font color='{LVL_HEX[lv]}'>■</font> <b>{counts[lv]}</b> {LVL_LABEL[lv].lower()}(s)", S["body"]))
    main = next((c for lv in ("ROUGE", "ORANGE", "JAUNE") for c in ctrls if c["niveau"] == lv), None)
    if main:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Principale incohérence", S["h2"]))
        pv = _m(main["plan"]) if isinstance(main.get("plan"), (int, float)) else (main.get("plan") or "NON INDIQUÉ")
        cv = _m(main["calc"]) if isinstance(main.get("calc"), (int, float)) else (main.get("calc") or "—")
        story.append(Paragraph(
            f"<b>{main['id']} · {_e(main['titre'])}</b><br/>Valeur indiquée : <b>{_e(pv)}</b>"
            f" · Valeur recalculée : <b>{_e(cv)}</b>"
            f" · Écart : <b>{_e(_cm(main['ecart_m']))}</b><br/>{_e(main.get('explication') or main.get('calcul') or '')}", S["body"]))
    if geo.get("synthese"):
        story.append(Paragraph(_e(geo["synthese"]), S["muted"]))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Données extraites du plan", S["h2"]))
    data_rows = [["Élément", "Valeur", "Type", "Source", "Confiance"]]
    for dx in (geo.get("donnees_extraites") or [])[:40]:
        data_rows.append([Paragraph(_e(dx.get("element")), S["muted"]), _m(dx.get("valeur_m")), _e(dx.get("type") or "—"),
                          _e(dx.get("source") or "LUE"), _e(dx.get("confiance") or "—")])
    if len(data_rows) == 1:
        for it in (report.get("items") or [])[:40]:
            data_rows.append([Paragraph(_e(it.get("location") or f"Cote #{it['index']}"), S["muted"]), _m(it["indicated_m"]),
                              {"h": "horizontale", "v": "verticale"}.get(it["orientation"], "oblique"),
                              "VALEUR CALCULÉE" if it.get("edited") else "LUE SUR PLAN", f"{int(it['confidence'] * 100)} %"])
    story.append(_tbl(data_rows, [70 * mm, 28 * mm, 30 * mm, 30 * mm, 24 * mm], S))
    story.append(Paragraph("Légende des sources : LUE SUR PLAN · FOURNIE PAR L'UTILISATEUR (cote corrigée) · VALEUR CALCULÉE · HYPOTHÈSE.", S["muted"]))

    # PAGE 3 — grandes cotes (fermetures) ; PAGE 4 — chaînes intérieures
    story.append(PageBreak())
    story.append(Paragraph("CONTRÔLE DES GRANDES COTES", S["kicker"]))
    story.append(Paragraph("Fermeture des chaînes sur les cotes générales", S["h1"]))
    ferms = [c for c in ctrls if c["kind"] == "fermeture"]
    if not ferms:
        story.append(Paragraph("Aucune chaîne générale n'a pu être reconstruite à partir des cotes lisibles (NON INDIQUÉ).", S["muted"]))
    for c in ferms:
        story.append(_fiche(c, None, S))
    story.append(PageBreak())
    story.append(Paragraph("CONTRÔLE DÉTAILLÉ DES CHAÎNES", S["kicker"]))
    story.append(Paragraph("Cotes partielles ↔ cotes totales (mesure ConstruPilot)", S["h1"]))
    chains = [c for c in ctrls if c["kind"] == "chaine"]
    if not chains:
        story.append(Paragraph("Aucune chaîne partielle contiguë détectée sur cette page.", S["muted"]))
    for c in chains:
        story.append(_fiche(c, None, S))
    rows = [["#", "Localisation", "Cote inscrite", "Mesure", "Écart", "Niveau"]]
    statuses = []
    for it in sorted(report["items"], key=lambda x: -abs(x["delta_cm"])):
        if it.get("ignored"):
            continue
        lv = it.get("niveau") or _STATUS_LVL.get(it["status"], "JAUNE")
        if it["status"] == "nd":
            lv = "BLEU"
        rows.append([str(it["index"]), Paragraph(_e(it.get("location") or "—"), S["muted"]), _m(it["indicated_m"]),
                     _m(it["measured_m"]), f"{it['delta_cm']:+.1f} cm", "NON DÉTERMINÉ" if it["status"] == "nd" else LVL_LABEL[lv]])
        statuses.append({"VERT": "ok", "BLEU": "ok", "JAUNE": "warn", "ORANGE": "ko", "ROUGE": "ko"}[lv])
    story.append(Paragraph("Toutes les cotes contrôlées (cote inscrite vs mesure à l'échelle)", S["h2"]))
    story.append(_tbl(rows, [10 * mm, 70 * mm, 26 * mm, 26 * mm, 22 * mm, 28 * mm], S, status_col=5, statuses=statuses))

    # PAGE 5 — façades & alignements
    story.append(PageBreak())
    story.append(Paragraph("CONTRÔLE DES FAÇADES ET ALIGNEMENTS", S["kicker"]))
    story.append(Paragraph("Façades opposées", S["h1"]))
    fac = geo.get("facades") or []
    if fac:
        rows = [["Façades opposées", "Cote A", "Cote B", "Écart", "Statut"]]
        for f in fac:
            rows.append([Paragraph(_e(f.get("nom")), S["muted"]), _m(f.get("longueur_plan_m")), _m(f.get("longueur_opposee_m")),
                         _cm(f.get("ecart_m")), LVL_LABEL[_lvl_from_status(f.get("statut"), f.get("ecart_m"))]])
        story.append(_tbl(rows, [70 * mm, 26 * mm, 26 * mm, 24 * mm, 36 * mm], S))
    else:
        story.append(Paragraph("Façades opposées : NON INDIQUÉ — les cotes lisibles ne permettent pas la comparaison.", S["muted"]))
    story.append(Paragraph(
        "Des façades opposées parallèles et cotées selon les mêmes références devraient présenter des dimensions compatibles. "
        "Un écart peut provenir d'un décrochement volontaire, d'une géométrie non rectangulaire, de références de cotation "
        "différentes (axes d'un côté, faces de l'autre), d'une erreur de dessin ou de cotation. Le plan seul ne permet pas de "
        "déterminer automatiquement laquelle de ces hypothèses est correcte.", S["muted"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Alignements", S["h1"]))
    als = geo.get("alignements") or []
    if not als:
        story.append(Paragraph("Alignement apparent à vérifier — précision insuffisante pour une mesure fiable.", S["muted"]))
    for a in als:
        segs = " ; ".join(f"{s.get('segment', '')} : {s.get('statut', '')}" + (f" ({s.get('decalage_mm')} mm)" if s.get("decalage_mm") else "")
                          for s in (a.get("segments") or []) if isinstance(s, dict))
        story.append(Paragraph(f"<b>{_e(a.get('nom'))}</b> — {_e(segs)}", S["body"]))

    # PAGE 6 — plan annoté (omis en rapport court)
    if not court:
        story.append(PageBreak())
        story.append(Paragraph("PLAN ANNOTÉ CONSTRUPILOT", S["kicker"]))
        story.append(Paragraph("Marqueurs CP-xx : vert conforme · jaune à vérifier · orange incohérence · rouge incohérence majeure", S["muted"]))
        story.append(_fit_image(marked_png, _W, A4[1] - 70 * mm))
        story.append(Paragraph(" · ".join(f"{c['id']} → {c['titre']}" for c in ctrls if c["cotes"])[:1500], S["muted"]))

    # Fiches CP-xx (anomalies & façades, avec zoom) — sans zoom en rapport court
    fiches = [c for c in ctrls if c["kind"] in ("anomalie", "facade")]
    if fiches:
        story.append(PageBreak())
        story.append(Paragraph("FICHES DÉTAILLÉES", S["kicker"]))
        story.append(Paragraph("Points nécessitant vérification", S["h1"]))
        for c in fiches:
            story.append(_fiche(c, None if court else zooms.get(c["id"]), S))

    # Tableau général
    story.append(PageBreak())
    story.append(Paragraph("TABLEAU GÉNÉRAL DES CONTRÔLES", S["kicker"]))
    rows = [["ID", "Contrôle", "Plan", "Calcul", "Écart", "Statut"]]
    statuses = []
    for c in ctrls:
        pv = _m(c["plan"]) if isinstance(c["plan"], (int, float)) else _e(c["plan"] or "—")
        cv = _m(c["calc"]) if isinstance(c["calc"], (int, float)) else _e(c["calc"] or "—")
        rows.append([c["id"], Paragraph(_e(c["titre"]), S["muted"]), pv, cv, _cm(c["ecart_m"]), LVL_LABEL[c["niveau"]]])
        statuses.append({"VERT": "ok", "BLEU": "ok", "JAUNE": "warn", "ORANGE": "ko", "ROUGE": "ko"}[c["niveau"]])
    story.append(_tbl(rows, [16 * mm, 74 * mm, 26 * mm, 26 * mm, 20 * mm, 20 * mm], S, status_col=5, statuses=statuses))

    # Dernière page — checklist + conclusion
    story.append(PageBreak())
    story.append(Paragraph("POINTS À CLARIFIER AVANT EXÉCUTION", S["kicker"]))
    checklist = list(geo.get("checklist") or [])
    checklist += [f"Confirmer la cote #{it['index']} ({_m(it['indicated_m'])}) : mesure {_m(it['measured_m'])}"
                  for it in report["items"] if it["status"] == "ko" and not it.get("ignored")][:8]
    checklist += ["Confirmer les références de cotation face/axe", "Comparer avec le plan architectural / structure",
                  "Vérifier la correspondance murs / fondations"]
    for line in dict.fromkeys(checklist):
        story.append(Paragraph(f"☐  {_e(line)}", S["body"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Conclusion", S["h1"]))
    concl = geo.get("conclusion") or (
        f"Le contrôle géométrique a porté sur {report['summary']['total']} cotes et {len(ctrls)} contrôles. "
        f"{counts['ORANGE'] + counts['ROUGE']} incohérence(s) détectée(s) et {counts['JAUNE']} point(s) à clarifier "
        "nécessitent une clarification des références de cotation et de la géométrie définitive avant utilisation des "
        "dimensions concernées pour l'implantation.")
    story.append(Paragraph(_e(concl), S["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Traçabilité : chaque résultat est reproductible à partir des valeurs sources, de la formule et de l'écart indiqués. "
        "Seuils de détection ConstruPilot : 0–2 mm négligeable · 2–10 mm faible · 10–30 mm à vérifier · 30–100 mm anomalie "
        "importante · > 100 mm anomalie majeure — ce ne sont pas des tolérances réglementaires d'exécution.", S["muted"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Périmètre : cette analyse est limitée au document fourni (page indiquée), à ses cotes lisibles et à l'échelle "
        "déclarée ou calibrée. Elle ne constitue ni une étude d'exécution ni une validation structurelle : les valeurs "
        "recalculées et les hypothèses de fermeture sont des aides à la vérification, jamais des cotes de remplacement. "
        "Les points signalés doivent être confirmés avec l'auteur du plan.", S["muted"]))

    def _footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(A4[0] - 14 * mm, 9 * mm, tr(f"ConstruPilot · Rapport de contrôle du plan · {rid} · page {d.page}"))
        canvas.setFillColor(ORANGE)
        canvas.rect(14 * mm, 9 * mm, 18 * mm, 1.2, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
