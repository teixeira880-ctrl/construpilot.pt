"""Excel du métré Revit : synthèse, métré par niveau (avec prix à saisir), contrôle élément par élément."""
from __future__ import annotations

import io
from datetime import datetime, timezone

UNIT_LABEL = {"m2": "m²", "m3": "m³", "ml": "ml", "u": "u", "kg": "kg"}


def revit_workbook(doc: dict, t: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    pt = t.get("lang") == "pt"

    def L(fr, pt_text):
        return pt_text if pt else fr

    green, copper, cream = "0F766E", "B87333", "F7F3EA"
    head_fill, head_font = PatternFill("solid", fgColor=green), Font(bold=True, color="FFFFFF")
    level_fill, level_font = PatternFill("solid", fgColor=cream), Font(bold=True, color=green)
    total_fill, total_font = PatternFill("solid", fgColor=copper), Font(bold=True, color="FFFFFF")
    thin = Border(bottom=Side(style="thin", color="DDDDDD"))

    def header(ws, values):
        ws.append(values)
        r = ws.max_row
        for c in range(1, len(values) + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill, cell.font, cell.alignment = head_fill, head_font, Alignment(horizontal="center", vertical="center", wrap_text=True)
        return r

    def widths(ws, ws_widths):
        for i, w in enumerate(ws_widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

    wb = Workbook()

    # ── Synthèse ────────────────────────────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = L("Synthèse", "Síntese")
    ws.append(["L(ConstruPilot — Métré depuis maquette Revit, ConstruPilot — Medição a partir do modelo Revit)"])
    ws["A1"].font = Font(bold=True, size=16, color=green)
    ws.append([L("Fichier", "Ficheiro"), doc.get("filename") or t.get("filename")])
    ws.append([L("Généré le", "Gerado em"), datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")])
    ws.append([L("Vue lue", "Vista lida"), t.get("view") or "3D"])
    ws.append([L("Éléments mesurés", "Elementos medidos"), t.get("elements_count")])
    ws.append([L("Niveaux", "Níveis"), ", ".join(t.get("levels") or [])])
    ws.append([L("Méthode", "Método"), t.get("method")])
    ws["B7"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[7].height = 45
    ws.append([])
    header(ws, [L("Ouvrage", "Trabalho"), L("Nombre", "Número"), L("Surface (m²)", "Área (m²)"), "Volume (m³)", L("Longueur (ml)", "Comprimento (m)")])
    for ouvrage, q in (t.get("by_ouvrage") or {}).items():
        ws.append([ouvrage, q.get("count"), q.get("total_area_m2"), q.get("total_volume_m3"), q.get("total_length_m")])
        for c in range(1, 6):
            ws.cell(row=ws.max_row, column=c).border = thin
    if t.get("warnings"):
        ws.append([])
        ws.append([L("Points de contrôle", "Pontos de controlo")])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color=copper)
        for w in t["warnings"]:
            ws.append(["•", w])
    widths(ws, [28, 60, 16, 16, 16])

    # ── Métré par niveau (quantités d'abord, prix ensuite) ──────────────────────────────────────
    wm = wb.create_sheet(L("Métré par niveau", "Medição por nível"))
    cols = [L("Niveau", "Nível"), L("Ouvrage", "Trabalho"), L("Famille", "Família"), "Type", L("Unité", "Unidade"), L("Quantité", "Quantidade"), L("Nombre", "Número"), L("Surface (m²)", "Área (m²)"), "Volume (m³)", L("Longueur (ml)", "Comprimento (m)"),
            L("Matériaux", "Materiais"), L("PU HT (€)", "PU s/ IVA (€)"), L("Total HT (€)", "Total s/ IVA (€)"), L("Ids Revit (contrôle)", "IDs Revit (controlo)")]
    header(wm, cols)
    wm.freeze_panes = "A2"
    subtotal_cells = []
    rows = t.get("rows") or []
    for level in t.get("levels") or []:
        wm.append([level])
        r = wm.max_row
        for c in range(1, len(cols) + 1):
            wm.cell(row=r, column=c).fill = level_fill
        wm.cell(row=r, column=1).font = level_font
        first = r + 1
        for row in (x for x in rows if x["level"] == level):
            wm.append([level, row["ouvrage"], row.get("family"), row["type"], UNIT_LABEL.get(row["unit"], row["unit"]), row["quantity"],
                       row["count"], row.get("area_m2"), row.get("volume_m3"), row.get("length_m"), ", ".join(row.get("materials") or []),
                       None, None, " ".join(row.get("revit_ids") or [])[:3000]])
            rr = wm.max_row
            wm.cell(row=rr, column=13).value = f'=IF(L{rr}="","",F{rr}*L{rr})'
            for c in range(1, len(cols) + 1):
                wm.cell(row=rr, column=c).border = thin
            if row.get("quantity_note"):
                wm.cell(row=rr, column=5).font = Font(italic=True, color=copper)
        last = wm.max_row
        wm.append(["", L(f"Sous-total {level}", f"Subtotal {level}")] + [""] * 10 + [f"=SUM(M{first}:M{last})" if last >= first else 0])
        sr = wm.max_row
        subtotal_cells.append(f"M{sr}")
        for c in (2, 13):
            wm.cell(row=sr, column=c).font = Font(bold=True, color=copper)
    wm.append([])
    wm.append(["", L("TOTAL HT", "TOTAL s/ IVA")] + [""] * 10 + ["=" + "+".join(subtotal_cells) if subtotal_cells else 0])
    tr = wm.max_row
    for c in range(1, len(cols) + 1):
        wm.cell(row=tr, column=c).fill = total_fill
        wm.cell(row=tr, column=c).font = total_font
    for r in range(2, tr + 1):
        for c in (6, 8, 9, 10, 12, 13):
            wm.cell(row=r, column=c).number_format = "#,##0.00"
    widths(wm, [16, 24, 24, 32, 8, 12, 9, 13, 13, 13, 26, 12, 14, 40])

    # ── Contrôle élément par élément ────────────────────────────────────────────────────────────
    we = wb.create_sheet(L("Éléments (contrôle)", "Elementos (controlo)"))
    ecols = ["N°", L("Id Revit", "ID Revit"), L("Niveau", "Nível"), L("Ouvrage", "Trabalho"), L("Famille", "Família"), "Type", L("Matériau", "Material"), L("Surface (m²)", "Área (m²)"), "Volume (m³)", L("Longueur (ml)", "Comprimento (m)"),
             L("Largeur / épaisseur (m)", "Largura / espessura (m)"), L("Hauteur (m)", "Altura (m)"), L("Non lu (unité inconnue)", "Não lido (unidade desconhecida)")]
    header(we, ecols)
    we.freeze_panes = "A2"
    for i, e in enumerate(t.get("elements") or [], start=1):
        we.append([i, e.get("revit_id"), e.get("level"), e.get("ouvrage"), e.get("family"), e.get("type"), e.get("material"),
                   e.get("area_m2"), e.get("volume_m3"), e.get("length_m"), e.get("width_m"), e.get("height_m"), ", ".join(e.get("unparsed") or [])])
    if t.get("elements_truncated"):
        we.append(["", L("Liste tronquée : les totaux du métré portent bien sur tous les éléments.", "Lista truncada: os totais da medição incluem todos os elementos.")])
    widths(we, [7, 12, 16, 24, 24, 32, 24, 12, 12, 12, 14, 11, 22])

    if t.get("demolished"):
        wd = wb.create_sheet(L("Démolitions (hors totaux)", "Demolições (fora dos totais)"))
        header(wd, [L("Id Revit", "ID Revit"), L("Niveau", "Nível"), L("Ouvrage", "Trabalho"), "Type", L("Surface (m²)", "Área (m²)"), "Volume (m³)", L("Longueur (ml)", "Comprimento (m)")])
        for e in t["demolished"]:
            wd.append([e.get("revit_id"), e.get("level"), e.get("ouvrage"), e.get("type"), e.get("area_m2"), e.get("volume_m3"), e.get("length_m")])
        widths(wd, [12, 16, 24, 32, 12, 12, 12])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
