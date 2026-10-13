"""StructuroPilot — Rapport de contrôle de dossier BET (LECTURE SEULE).

Produit un PDF de « points de vigilance » : inventaire des documents importés,
indices/révisions lus, comparaisons de versions et incohérences signalées entre
documents. AUCUN calcul, AUCUNE conclusion structurelle : document de contrôle
qui ne remplace pas la vérification d'un ingénieur et n'est pas « bon pour exécution ».
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
GREEN = colors.HexColor("#18A858")
WARN = colors.HexColor("#b45309")
WARN_BG = colors.HexColor("#fff7ed")
RED = colors.HexColor("#dc2626")
RED_BG = colors.HexColor("#fef2f2")
LINE = colors.HexColor("#cbd5e1")
HEAD_BG = colors.HexColor("#f1f5f9")

DISCLAIMER = (
    "Rapport de CONTRÔLE en lecture seule. StructuroPilot n'effectue aucun calcul "
    "structurel et ne décide pas quelle valeur est correcte : il rapporte ce qui est écrit "
    "dans les documents et signale les écarts à faire vérifier. Ce document ne remplace pas "
    "la vérification d'un ingénieur structure et n'est pas « bon pour exécution »."
)


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("CPTitle", parent=ss["Title"], fontSize=18, textColor=INK, spaceAfter=2))
    ss.add(ParagraphStyle("CPSub", parent=ss["Normal"], fontSize=9, textColor=MUTED))
    ss.add(ParagraphStyle("CPH2", parent=ss["Heading2"], fontSize=12, textColor=INK, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("CPBody", parent=ss["Normal"], fontSize=9, textColor=INK, leading=13, alignment=TA_LEFT))
    ss.add(ParagraphStyle("CPWarn", parent=ss["Normal"], fontSize=9, textColor=WARN, leading=13))
    ss.add(ParagraphStyle("CPRed", parent=ss["Normal"], fontSize=9, textColor=RED, leading=13))
    ss.add(ParagraphStyle("CPRedBold", parent=ss["Normal"], fontSize=9.5, textColor=RED, leading=13, fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle("CPCell", parent=ss["Normal"], fontSize=8.5, textColor=INK, leading=12))
    return ss


def _p(text, st):
    return Paragraph((text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), st)


def _table(rows, col_widths, ss, header=True):
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                  ("FONTSIZE", (0, 0), (-1, 0), 8.5)]
    t.setStyle(TableStyle(style))
    return t


def build_control_report(dossier: dict) -> bytes:
    ss = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            title=f"Contrôle dossier BET — {dossier.get('title', '')}")
    story = []
    docs = [d for d in dossier.get("documents", []) if not d.get("is_deleted")]

    story.append(_p("Rapport de contrôle — Dossier BET", ss["CPTitle"]))
    story.append(_p(dossier.get("title") or "Dossier sans titre", ss["CPSub"]))
    story.append(_p("Généré le " + datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M") + " · StructuroPilot (lecture seule)", ss["CPSub"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE))

    # Avertissement
    story.append(Spacer(1, 8))
    warn = _table([[_p(DISCLAIMER, ss["CPWarn"])]], [180 * mm], ss, header=False)
    warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN_BG),
                              ("BOX", (0, 0), (-1, -1), 0.6, WARN),
                              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(warn)

    # Synthèse des points à vérifier (en rouge) — collectés des comparaisons + incohérences.
    by_id0 = {d["id"]: d for d in docs}
    flags = []
    for c in dossier.get("comparisons", []):
        na = by_id0.get(c.get("doc_a"), {}).get("original_filename", "A")
        nb = by_id0.get(c.get("doc_b"), {}).get("original_filename", "B")
        for cf in (c.get("result", {}) or {}).get("conflits_a_verifier", []):
            flags.append(f"{na} → {nb} · {cf.get('sujet','')} — {cf.get('detail','')}")
    for it in (dossier.get("inconsistencies") or {}).get("incoherences", []):
        vals = ", ".join(f"{v.get('document','?')}={v.get('valeur','')}" for v in it.get("valeurs", []))
        flags.append(f"{it.get('sujet','')} · {vals}")
    story.append(_p("Points à vérifier", ss["CPH2"]))
    if not flags:
        story.append(_p("Aucun conflit signalé à ce stade (ou analyses non lancées).", ss["CPBody"]))
    else:
        srows = [[_p(f"⚠ {f}", ss["CPRed"])] for f in flags]
        summary = _table(srows, [180 * mm], ss, header=False)
        summary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), RED_BG),
                                     ("BOX", (0, 0), (-1, -1), 0.6, RED),
                                     ("INNERGRID", (0, 0), (-1, -1), 0.3, RED),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                     ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.append(summary)

    # 1. Inventaire des documents
    story.append(_p("1. Documents importés", ss["CPH2"]))
    rows = [["Document", "Type", "Indice", "Lecture IA"]]
    for d in docs:
        ext = (d.get("extraction") or {})
        idx = d.get("index") or ext.get("indice_detecte") or "—"
        eng = ext.get("source_engine")
        read = {"claude": "Analysé", "skipped": "Non lisible (DWG/IFC)", "error": "Échec", "fallback": "Partiel"}.get(eng, "En attente")
        rows.append([_p(d.get("original_filename", "—"), ss["CPCell"]),
                     _p((d.get("kind") or "").upper() or "—", ss["CPCell"]),
                     _p(str(idx), ss["CPCell"]), _p(read, ss["CPCell"])])
    if len(rows) == 1:
        rows.append([_p("Aucun document importé.", ss["CPCell"]), "", "", ""])
    story.append(_table(rows, [78 * mm, 26 * mm, 24 * mm, 42 * mm], ss))

    # 2. Comparaisons de versions
    story.append(_p("2. Comparaisons de versions (A → B)", ss["CPH2"]))
    comps = dossier.get("comparisons", [])
    by_id = {d["id"]: d for d in docs}
    if not comps:
        story.append(_p("Aucune comparaison enregistrée.", ss["CPBody"]))
    for c in comps:
        res = c.get("result", {})
        na = by_id.get(c.get("doc_a"), {}).get("original_filename", c.get("doc_a", "?"))
        nb = by_id.get(c.get("doc_b"), {}).get("original_filename", c.get("doc_b", "?"))
        story.append(Spacer(1, 4))
        story.append(_p(f"• {na}  →  {nb}", ss["CPBody"]))
        crows = [["Nature", "Détail"]]
        for m in res.get("modifications", []):
            crows.append([_p("Modifié", ss["CPCell"]),
                          _p(f"{m.get('sujet','')} : « {m.get('avant','')} » → « {m.get('apres','')} »", ss["CPCell"])])
        for a in res.get("ajouts", []):
            crows.append([_p("Ajout", ss["CPCell"]), _p(str(a), ss["CPCell"])])
        for s in res.get("suppressions", []):
            crows.append([_p("Suppression", ss["CPCell"]), _p(str(s), ss["CPCell"])])
        for cf in res.get("conflits_a_verifier", []):
            crows.append([_p("⚠ Conflit", ss["CPRedBold"]),
                          _p(f"{cf.get('sujet','')} — {cf.get('detail','')}", ss["CPRed"])])
        if len(crows) == 1:
            crows.append([_p("Aucune différence détectée.", ss["CPCell"]), ""])
        story.append(_table(crows, [30 * mm, 150 * mm], ss))

    # 3. Incohérences entre documents
    story.append(_p("3. Incohérences signalées entre documents", ss["CPH2"]))
    inco = (dossier.get("inconsistencies") or {}).get("incoherences", [])
    if not inco:
        story.append(_p("Aucune incohérence signalée (ou analyse non lancée).", ss["CPBody"]))
    else:
        irows = [["Sujet", "Valeurs relevées", "Note"]]
        for it in inco:
            vals = "  |  ".join(f"{v.get('document','?')}: {v.get('valeur','')}" for v in it.get("valeurs", []))
            irows.append([_p(it.get("sujet", ""), ss["CPCell"]),
                          _p(vals, ss["CPCell"]), _p(it.get("note", ""), ss["CPCell"])])
        story.append(_table(irows, [44 * mm, 86 * mm, 50 * mm], ss))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE))
    story.append(Spacer(1, 4))
    story.append(_p("Points de vigilance à faire vérifier par un ingénieur structure. "
                    "Aucune valeur n'a été recalculée ni validée par StructuroPilot.", ss["CPSub"]))

    # Bloc signature — établi par le responsable du contrôle.
    story.append(Spacer(1, 16))
    resp = (dossier.get("responsable") or "").strip()
    sig_rows = [[
        _p("Contrôle établi par", ss["CPCell"]),
        _p("Date", ss["CPCell"]),
        _p("Signature", ss["CPCell"]),
    ], [
        _p(f"<b>{resp}</b>" if resp else "…………………………………", ss["CPBody"]),
        _p(datetime.now(timezone.utc).strftime("%d/%m/%Y"), ss["CPBody"]),
        _p("…………………………………", ss["CPBody"]),
    ]]
    sig = _table(sig_rows, [70 * mm, 40 * mm, 70 * mm], ss)
    sig.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE),
                             ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                             ("TOPPADDING", (0, 1), (-1, 1), 16), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                             ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(sig)

    doc.build(story)
    return buf.getvalue()
