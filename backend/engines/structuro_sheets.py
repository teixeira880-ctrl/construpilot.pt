"""StructuroPilot — feuilles d'étude EXI/STR (esquisses schématiques).

Génère un PDF vectoriel d'ESQUISSE depuis le modèle (niveaux + éléments + données tracées).
AUCUNE cote n'est inventée : seules les valeurs DOCUMENTÉES sont affichées ; les inconnues
apparaissent « ? (à documenter) ». Schématique, non à l'échelle, jamais « bon pour exécution ».
"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from engines import structuro_model as sm

PAGE = landscape(A4)
W, H = PAGE
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
ACCENT = colors.HexColor("#334155")
WARN = colors.HexColor("#b45309")
LINE = colors.HexColor("#cbd5e1")


def _fmt_datum(d: dict | None) -> str:
    if not d or d.get("value") in (None, ""):
        return "? (a documentar)"
    if d.get("source") not in sm.DOCUMENTED_SOURCES:
        return f"{d.get('value')} {d.get('unit') or ''} (declarado, a confirmar)".strip()
    return f"{d.get('value')} {d.get('unit') or ''}".strip()


def _header(c, study: dict, sheet_code: str, sheet_title: str):
    c.setFillColor(ACCENT)
    c.rect(0, H - 16 * mm, W, 16 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(10 * mm, H - 11 * mm, f"StructuroPilot — {sheet_code} · {sheet_title}")
    c.setFont("Helvetica", 8)
    c.drawRightString(W - 10 * mm, H - 7 * mm, (study.get("title") or "")[:70])
    c.drawRightString(W - 10 * mm, H - 12 * mm,
                      f"Rev. {study.get('revision', 1)} · Nível: {study.get('output_level', 'exploration')}")
    # Bandeau statut (honnêteté)
    c.setFillColor(colors.HexColor("#fff7ed"))
    c.rect(0, H - 24 * mm, W, 8 * mm, fill=1, stroke=0)
    c.setFillColor(WARN)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(10 * mm, H - 21.5 * mm,
                 "ESBOÇO — ESTUDO PRELIMINAR, SEM ESCALA, COTAS A CONFIRMAR. NÃO VÁLIDO PARA EXECUÇÃO. Motor de cálculo indisponível (nenhum dimensionamento).")


def _footer(c, study: dict):
    c.setStrokeColor(LINE)
    c.line(10 * mm, 12 * mm, W - 10 * mm, 12 * mm)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    note = sm.RULEPACK.get("note", "")
    c.drawString(10 * mm, 8 * mm, f"Référentiel calcul : {sm.RULEPACK.get('status')} — {note}"[:150])
    c.drawRightString(W - 10 * mm, 8 * mm, "StructuroPilot · Lote A · esboço associado à revisão acima")


def _draw_elevation(c, study: dict, x0: float, y0: float, w: float, h: float, project: bool):
    """Schéma d'élévation : niveaux empilés (hauteurs documentées sinon équiréparties)."""
    levels = study.get("levels") or []
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(INK)
    c.drawString(x0, y0 + h + 4 * mm, "Alçado esquemático (níveis)")
    if not levels:
        c.setFont("Helvetica", 8); c.setFillColor(MUTED)
        c.drawString(x0, y0 + h / 2, "Nenhum nível definido — a documentar.")
        return
    n = len(levels)
    band = h / n
    # du haut vers le bas en ordre inverse (élévation croissante vers le haut)
    ordered = sorted(levels, key=lambda l: (l.get("elevation_m", {}) or {}).get("value") or 0)
    for i, lvl in enumerate(ordered):
        y = y0 + i * band
        c.setStrokeColor(ACCENT); c.setLineWidth(0.8)
        c.setFillColor(colors.HexColor("#f1f5f9"))
        c.rect(x0, y, w, band - 2, fill=1, stroke=1)
        c.setFillColor(INK); c.setFont("Helvetica-Bold", 8)
        c.drawString(x0 + 3 * mm, y + band / 2 - 1 * mm, lvl.get("name", "Piso"))
        c.setFont("Helvetica", 7); c.setFillColor(MUTED)
        c.drawRightString(x0 + w - 3 * mm, y + band / 2 - 1 * mm,
                          "±" + _fmt_datum(lvl.get("elevation_m")))
    # Repère de l'ouverture projetée (STR) sur le niveau RDC
    if project:
        rdc_i = next((i for i, l in enumerate(ordered) if "rez" in (l.get("name", "").lower())), 0)
        y = y0 + rdc_i * band
        ow = w * 0.25
        c.setFillColor(colors.HexColor("#fde68a")); c.setStrokeColor(WARN); c.setLineWidth(1)
        c.rect(x0 + w * 0.35, y + 2, ow, band - 6, fill=1, stroke=1)
        c.setFillColor(WARN); c.setFont("Helvetica-Bold", 6.5)
        op = _fmt_datum((study.get("data") or {}).get("ouverture.portee"))
        c.drawCentredString(x0 + w * 0.35 + ow / 2, y + band / 2 - 1 * mm, f'Vão {op}')


def _draw_tables(c, study: dict, x0: float, y_top: float):
    data = study.get("data") or {}
    # Éléments
    c.setFont("Helvetica-Bold", 9); c.setFillColor(INK)
    c.drawString(x0, y_top, "Elementos do modelo")
    y = y_top - 5 * mm
    c.setFont("Helvetica", 7.5)
    for el in (study.get("elements") or [])[:10]:
        c.setFillColor(INK)
        c.drawString(x0, y, f"[{el.get('ref')}] {el.get('type')} — {el.get('label','')[:40]} "
                            f"({el.get('level') or '—'})")
        y -= 4.2 * mm
    if not study.get("elements"):
        c.setFillColor(MUTED); c.drawString(x0, y, "Nenhum elemento."); y -= 4.2 * mm

    # Données géométriques documentées / inconnues
    y -= 3 * mm
    c.setFont("Helvetica-Bold", 9); c.setFillColor(INK)
    c.drawString(x0, y, "Dados e zonas a reconhecer")
    y -= 5 * mm
    c.setFont("Helvetica", 7.5)
    shown = ["ouverture.position", "ouverture.portee", "mur.epaisseur", "mur.materiau_resistance",
             "plancher.sens_porteur", "plancher.portee", "fondation.geometrie", "sol.portance"]
    for k in shown:
        d = data.get(k)
        txt = _fmt_datum(d)
        unknown = (not d) or d.get("value") in (None, "")
        c.setFillColor(WARN if unknown else INK)
        c.drawString(x0, y, f"• {k} : {txt}")
        y -= 4.2 * mm


def _sheet(c, study: dict, code: str, title: str, project: bool):
    _header(c, study, code, title)
    top = H - 30 * mm
    _draw_elevation(c, study, 10 * mm, top - 90 * mm, 120 * mm, 85 * mm, project)
    _draw_tables(c, study, 145 * mm, top)
    _footer(c, study)
    c.showPage()


def build_study_sheets(study: dict) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    _sheet(c, study, "EXI", "Existente (esboço)", project=False)
    _sheet(c, study, "STR", "Projeto — abertura (esboço)", project=True)
    c.save()
    return buf.getvalue()
