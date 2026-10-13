"""Export PDF du planning de chantier (Gantt + tableau + propositions)."""
from __future__ import annotations

import io
from datetime import date, datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Flowable

_ORANGE = colors.HexColor("#E8562A")
_DARK = colors.HexColor("#1A1A1A")
_GREY = colors.HexColor("#9CA3AF")
_SEV = {"critical": colors.HexColor("#DC2626"), "high": colors.HexColor("#EA580C"), "medium": colors.HexColor("#D97706"),
        "info": colors.HexColor("#2563EB"), "success": colors.HexColor("#16A34A")}


def _fr(d: str | None) -> str:
    if not d:
        return "—"
    y, m, dd = d.split("-")
    return f"{dd}/{m}/{y}"


class Gantt(Flowable):
    def __init__(self, tasks: list[dict], width: float, row_h: float = 6.5 * mm):
        super().__init__()
        self.tasks, self.w, self.row_h = tasks, width, row_h
        self.label_w = 62 * mm
        self.height = row_h * (len(tasks) + 1) + 4 * mm
        self.width = width

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        tasks = self.tasks
        if not tasks:
            return
        total = max(t["end_idx"] for t in tasks) or 1
        gw = self.w - self.label_w - 30 * mm
        unit = gw / total
        top = self.height - 3 * mm
        c.setFont("Helvetica", 6.5)
        c.setFillColor(_GREY)
        step = max(1, total // 12)
        for i in range(0, total + 1, step):
            x = self.label_w + i * unit
            c.setStrokeColor(colors.HexColor("#E5E7EB"))
            c.line(x, top, x, top - self.row_h * (len(tasks) + 1))
            c.drawString(x + 1, top - 3 * mm, f"J{i}")
        for n, t in enumerate(tasks):
            y = top - self.row_h * (n + 1) - self.row_h + 1.5 * mm
            c.setFillColor(_DARK)
            c.setFont("Helvetica", 7.5)
            label = t["name"] if len(t["name"]) <= 34 else t["name"][:33] + "…"
            c.drawString(0, y + 1.2 * mm, label)
            x0 = self.label_w + t["start_idx"] * unit
            bw = max(1.0, (t["end_idx"] - t["start_idx"]) * unit)
            c.setFillColor(_ORANGE if t.get("critical") else colors.HexColor("#CBD5E1"))
            c.roundRect(x0, y, bw, self.row_h - 2.2 * mm, 1, stroke=0, fill=1)
            if t.get("progress"):
                c.setFillColor(colors.HexColor("#16A34A"))
                c.roundRect(x0, y, bw * min(100, t["progress"]) / 100, self.row_h - 2.2 * mm, 1, stroke=0, fill=1)
            c.setFillColor(_DARK)
            c.setFont("Helvetica", 6)
            c.drawString(x0 + bw + 1, y + 1.2 * mm, f"{_fr(t['start_date'])} → {_fr(t['end_date'])}")


def build_planning_pdf(chantier: dict, plan: dict, result: dict, suggestions: list[dict], branding: dict | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=14 * mm, bottomMargin=12 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=_DARK, fontSize=17, alignment=0, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=colors.grey, fontSize=8.5)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=_ORANGE, fontSize=11.5, spaceBefore=8, spaceAfter=3)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=8.5, leading=11)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=7.5, textColor=colors.grey, leading=10)
    story = []
    company = (branding or {}).get("company") or "ConstruPilot"
    story.append(Paragraph(f"Planeamento da obra — {chantier.get('name', '')}", h1))
    p = result["project"]
    story.append(Paragraph(
        f"{company} · Início {_fr(p['start_date'])} · Fim previsto <b>{_fr(p['end_date'])}</b> · {p['duration_workdays']} dias úteis"
        + (f" · Objectif {_fr(p['deadline'])} ({'+' if p['deadline_gap_days'] >= 0 else ''}{p['deadline_gap_days']} j)" if p.get("deadline") else "")
        + f" · Situação em {_fr(p['as_of'])} · Emitido em {datetime.now(timezone.utc).strftime('%d/%m/%Y')}", sub))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Diagrama de Gantt (dias úteis — laranja = caminho crítico, verde = avanço introduzido)", h2))
    story.append(Gantt(result["tasks"], doc.width))

    story.append(Paragraph("Tarefas", h2))
    rows = [["#", "Tarefa", "Equipa / capítulo", "Duração", "Início", "Fim", "Margem", "Avanc.", "Antecessoras"]]
    for t in result["tasks"]:
        rows.append([t["id"], Paragraph(t["name"], body), t["resource"], f"{t['duration']} j", _fr(t["start_date"]), _fr(t["end_date"]),
                     "critique" if t["critical"] else f"{t['slack']} j", f"{t['progress']} %",
                     ", ".join(pp["id"] + (f" ({pp['lag']:+d})" if pp.get("lag") else "") for pp in t["predecessors"]) or "—"])
    tbl = Table(rows, colWidths=[10 * mm, 72 * mm, 42 * mm, 14 * mm, 22 * mm, 22 * mm, 18 * mm, 16 * mm, 40 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")])]))
    for i, t in enumerate(result["tasks"], 1):
        if t["critical"]:
            tbl.setStyle(TableStyle([("TEXTCOLOR", (6, i), (6, i), _ORANGE), ("FONTNAME", (6, i), (6, i), "Helvetica-Bold")]))
    story.append(tbl)

    if suggestions:
        story.append(Paragraph("Propostas de reorganização (ganhos medidos repetindo o planeamento)", h2))
        for s in suggestions:
            col = _SEV.get(s["severity"], _GREY)
            story.append(Paragraph(f"<font color='{col.hexval()}'>■</font> <b>{s['title']}</b> — {s['detail']}", body))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Planeamento determinístico (caminho crítico + capacidade das equipas). As durações marcadas «por omissão» devem ser confirmadas pela empresa; nenhuma duração é estimada por IA.", small))
    doc.build(story)
    return buf.getvalue()
