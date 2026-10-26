"""Exportação Excel das quantidades e orçamento Plans Pro.

Gera `.xlsx` profissional com 3 folhas:
  1. "Resumo"       — cabeçalho projeto + totais
  2. "Quantidades"  — ouvrages Autodesk Model Derivative (categorias/layers)
  3. "Orçamento"    — tabela PT c/ IVA configurável (23%/6%/22%/16%)

Formato numérico EUR com separador decimal gerido pelo locale do Excel do utilizador.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger("plans_pro.excel")

# Taxas IVA PT suportadas (DL n.º 102/2008 + Lei do OE)
IVA_RATES_PT: dict[str, dict[str, Any]] = {
    "23": {"rate": 0.23, "label": "IVA 23% — Continente (regime geral)"},
    "22": {"rate": 0.22, "label": "IVA 22% — Açores (regime geral)"},
    "16": {"rate": 0.16, "label": "IVA 16% — Madeira (regime geral)"},
    "6":  {"rate": 0.06, "label": "IVA 6% — Reabilitação urbana (ARU) / reforma pensionistas"},
    "0":  {"rate": 0.00, "label": "IVA 0% — Isento (ex.: exportação)"},
}

# Paleta ConstruPilot
HEAD_FILL = PatternFill("solid", fgColor="0F766E")
HEAD_FONT = Font(bold=True, color="FFFFFF", size=11)
SUB_FILL = PatternFill("solid", fgColor="E6F7F3")
TOTAL_FILL = PatternFill("solid", fgColor="FEF3C7")
TITLE_FONT = Font(bold=True, size=16, color="0F766E")
LABEL_FONT = Font(bold=True, size=10, color="334155")
THIN_SIDE = Side(border_style="thin", color="CBD5E1")
BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

CURRENCY_FMT = '#,##0.00" €"'
QTY_FMT = "#,##0.00"
PCT_FMT = "0%"


def _header_cell(ws, row: int, col: int, value: str) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = HEAD_FILL
    cell.font = HEAD_FONT
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = BORDER


def _set_widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_project_header(ws, *, plan_doc: dict, iva_label: str, numero_orc: str,
                          branding: dict | None = None) -> int:
    """Grava cabeçalho na folha Resumo. Devolve próxima linha livre.

    Se `branding` tiver `brand_logo_b64`, insere o logo em A1. Caso contrário,
    coloca "ConstruPilot" como título.
    """
    branding = branding or {}
    logo_b64 = (branding.get("brand_logo_b64") or "").split(",")[-1]  # tira prefixo data:
    row_offset = 0
    if logo_b64:
        try:
            import base64 as _b64
            import io as _io
            from openpyxl.drawing.image import Image as XlImage
            raw = _b64.b64decode(logo_b64)
            img = XlImage(_io.BytesIO(raw))
            # Redimensionar para caber em 2 linhas (~60px alto)
            try:
                ratio = (img.width or 100) / max(img.height or 60, 1)
                img.height = 60
                img.width = int(60 * ratio)
            except Exception:
                pass
            img.anchor = "A1"
            ws.add_image(img)
            ws.row_dimensions[1].height = 50
            ws.row_dimensions[2].height = 20
            row_offset = 2
        except Exception as e:  # noqa: BLE001
            logger.info("Logo render falhou: %s", type(e).__name__)

    title_row = 1 + row_offset
    ws.cell(row=title_row, column=1).value = branding.get("brand_company_name") or "ConstruPilot — Orçamento preliminar"
    ws.cell(row=title_row, column=1).font = TITLE_FONT
    ws.merge_cells(start_row=title_row, start_column=1, end_row=title_row, end_column=6)

    gen = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    rows: list[tuple[str, Any]] = [
        ("Ficheiro:", plan_doc.get("file_name") or "—"),
        ("Formato:", (plan_doc.get("file_type") or "").upper() or "—"),
        ("Projeto / ID:", plan_doc.get("project_id") or "—"),
        ("Nº orçamento:", numero_orc),
        ("Data de geração:", gen),
        ("Regime IVA:", iva_label),
        ("Modelo IA:", plan_doc.get("model_used") or "—"),
    ]
    if branding.get("brand_nif"):
        rows.append(("NIF:", str(branding["brand_nif"])))
    if branding.get("brand_address"):
        morada = str(branding.get("brand_address") or "")
        cidade = str(branding.get("brand_city") or "")
        postal = str(branding.get("brand_postal") or "")
        full = f"{morada}, {postal} {cidade}".strip(", ")
        if full:
            rows.append(("Morada:", full))
    if branding.get("brand_contact_line"):
        rows.append(("Contacto:", str(branding["brand_contact_line"])))
    if plan_doc.get("autodesk_urn"):
        rows.append(("URN Autodesk:", (plan_doc["autodesk_urn"][:60] + "…")))

    row = title_row + 2
    for label, value in rows:
        c = ws.cell(row=row, column=1, value=label)
        c.font = LABEL_FONT
        c.alignment = Alignment(horizontal="right")
        ws.cell(row=row, column=2, value=value)
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
        row += 1
    return row + 1


def _write_quantities_sheet(ws, quantities: dict[str, dict[str, Any]]) -> None:
    ws.title = "Quantidades"
    _set_widths(ws, [24, 16, 14, 72])
    headers = ["Ouvrage", "N.º entidades", "Fonte", "Layers / notas"]
    for col, h in enumerate(headers, start=1):
        _header_cell(ws, 1, col, h)
    r = 2
    for cat, data in (quantities or {}).items():
        ws.cell(row=r, column=1, value=cat).border = BORDER
        q = ws.cell(row=r, column=2, value=data.get("count"))
        q.number_format = "#,##0"
        q.alignment = Alignment(horizontal="right")
        q.border = BORDER
        ws.cell(row=r, column=3, value="layers" if data.get("source") == "layers" else "categorias").border = BORDER
        layers = data.get("layers") or []
        notes = " ; ".join(f"{l['layer']} ({l['count']})" for l in layers[:8]) if layers else ""
        c = ws.cell(row=r, column=4, value=notes)
        c.alignment = Alignment(wrap_text=True)
        c.border = BORDER
        r += 1
    ws.freeze_panes = "A2"


def _write_budget_sheet(
    ws,
    *,
    ouvrages: list[dict[str, Any]],
    iva_rate: float,
    iva_label: str,
) -> dict[str, float]:
    """Preenche folha Orçamento com fórmulas Excel. Devolve totais."""
    ws.title = "Orçamento"
    _set_widths(ws, [36, 10, 10, 15, 15, 15, 15, 15, 34])
    headers = [
        "Designação",
        "Un",
        "Quantidade",
        "Preço Unit. (€)",
        "Total s/ IVA",
        f"IVA ({int(iva_rate * 100)}%)",
        "Total c/ IVA",
        "Ref. Biblioteca PT",
        "Observações",
    ]
    for col, h in enumerate(headers, start=1):
        _header_cell(ws, 1, col, h)

    r = 2
    sum_ht = 0.0
    for item in (ouvrages or []):
        nome = str(item.get("nome") or "")
        unidade = str(item.get("unidade") or "u")
        qtd = item.get("quantidade")
        pu = item.get("pu_eur")
        obs = str(item.get("observacoes") or "")
        ref = str(item.get("ref_biblioteca") or item.get("ref") or "")

        ws.cell(row=r, column=1, value=nome).border = BORDER
        ws.cell(row=r, column=2, value=unidade).border = BORDER
        q_cell = ws.cell(row=r, column=3, value=qtd)
        q_cell.number_format = QTY_FMT
        q_cell.alignment = Alignment(horizontal="right")
        q_cell.border = BORDER
        pu_cell = ws.cell(row=r, column=4, value=pu)
        pu_cell.number_format = CURRENCY_FMT
        pu_cell.border = BORDER
        # Fórmulas: C*D, E*iva, E+F
        total_ht_formula = f"=IFERROR(C{r}*D{r},0)"
        iva_formula = f"=E{r}*{iva_rate}"
        total_ttc_formula = f"=E{r}+F{r}"
        e = ws.cell(row=r, column=5, value=total_ht_formula)
        e.number_format = CURRENCY_FMT
        e.border = BORDER
        f = ws.cell(row=r, column=6, value=iva_formula)
        f.number_format = CURRENCY_FMT
        f.border = BORDER
        g = ws.cell(row=r, column=7, value=total_ttc_formula)
        g.number_format = CURRENCY_FMT
        g.font = Font(bold=True)
        g.border = BORDER
        ws.cell(row=r, column=8, value=ref).border = BORDER
        obs_cell = ws.cell(row=r, column=9, value=obs)
        obs_cell.alignment = Alignment(wrap_text=True)
        obs_cell.border = BORDER
        try:
            if isinstance(qtd, (int, float)) and isinstance(pu, (int, float)):
                sum_ht += float(qtd) * float(pu)
        except Exception:
            pass
        r += 1

    # Linha de totais (fórmulas)
    last_data_row = r - 1
    if last_data_row >= 2:
        total_row = r + 1
        for col in range(1, 10):
            ws.cell(row=total_row, column=col).fill = TOTAL_FILL
        ws.cell(row=total_row, column=4, value="TOTAL").font = Font(bold=True)
        ws.cell(row=total_row, column=4).alignment = Alignment(horizontal="right")
        tht = ws.cell(row=total_row, column=5, value=f"=SUM(E2:E{last_data_row})")
        tht.number_format = CURRENCY_FMT
        tht.font = Font(bold=True)
        tht.border = BORDER
        tiva = ws.cell(row=total_row, column=6, value=f"=SUM(F2:F{last_data_row})")
        tiva.number_format = CURRENCY_FMT
        tiva.font = Font(bold=True)
        tiva.border = BORDER
        tttc = ws.cell(row=total_row, column=7, value=f"=SUM(G2:G{last_data_row})")
        tttc.number_format = CURRENCY_FMT
        tttc.font = Font(bold=True, size=12, color="0F766E")
        tttc.border = BORDER
        # Legenda IVA
        ws.cell(row=total_row + 2, column=1, value=iva_label).font = Font(italic=True, color="64748B")
        ws.merge_cells(start_row=total_row + 2, start_column=1, end_row=total_row + 2, end_column=9)

    ws.freeze_panes = "A2"
    iva_total = sum_ht * iva_rate
    return {
        "total_ht_eur": round(sum_ht, 2),
        "iva_eur": round(iva_total, 2),
        "total_ttc_eur": round(sum_ht + iva_total, 2),
    }


def _write_resumo_sheet(
    ws,
    *,
    plan_doc: dict,
    totals: dict[str, float],
    iva_label: str,
    numero_orc: str,
    ouvrages_count: int,
    quantities_count: int,
    resumo: str | None,
    normas: list[str],
    branding: dict | None = None,
) -> None:
    ws.title = "Resumo"
    _set_widths(ws, [22, 20, 20, 20, 20, 20])
    next_row = _write_project_header(
        ws, plan_doc=plan_doc, iva_label=iva_label,
        numero_orc=numero_orc, branding=branding,
    )

    # Totais destaque
    ws.cell(row=next_row, column=1, value="Totais").font = Font(bold=True, size=12, color="0F766E")
    next_row += 1
    cells = [
        ("Total s/ IVA", totals["total_ht_eur"]),
        ("Total IVA", totals["iva_eur"]),
        ("Total c/ IVA", totals["total_ttc_eur"]),
    ]
    for i, (label, val) in enumerate(cells):
        c_label = ws.cell(row=next_row, column=1 + i * 2, value=label)
        c_label.font = LABEL_FONT
        c_label.alignment = Alignment(horizontal="right")
        c_val = ws.cell(row=next_row, column=2 + i * 2, value=val)
        c_val.number_format = CURRENCY_FMT
        c_val.font = Font(bold=True, size=12)
        c_val.fill = SUB_FILL
    next_row += 2

    ws.cell(row=next_row, column=1, value="Contagens").font = Font(bold=True, size=11, color="0F766E")
    next_row += 1
    ws.cell(row=next_row, column=1, value="Trabalhos orçamentados:").font = LABEL_FONT
    ws.cell(row=next_row, column=2, value=ouvrages_count)
    next_row += 1
    ws.cell(row=next_row, column=1, value="Categorias Autodesk:").font = LABEL_FONT
    ws.cell(row=next_row, column=2, value=quantities_count)
    next_row += 2

    if resumo:
        ws.cell(row=next_row, column=1, value="Resumo técnico").font = Font(bold=True, size=11, color="0F766E")
        next_row += 1
        c = ws.cell(row=next_row, column=1, value=resumo)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=next_row, start_column=1, end_row=next_row + 4, end_column=6)
        ws.row_dimensions[next_row].height = 100
        next_row += 6

    if normas:
        ws.cell(row=next_row, column=1, value="Normas aplicáveis").font = Font(bold=True, size=11, color="0F766E")
        next_row += 1
        for n in normas[:8]:
            ws.cell(row=next_row, column=1, value=f"• {n}")
            ws.merge_cells(start_row=next_row, start_column=1, end_row=next_row, end_column=6)
            next_row += 1


def build_workbook(
    *,
    plan_doc: dict,
    iva_rate: str = "23",
    branding: dict | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Gera workbook .xlsx em memória. Devolve `(bytes, meta_dict)`."""
    iva_cfg = IVA_RATES_PT.get(str(iva_rate), IVA_RATES_PT["23"])
    rate = iva_cfg["rate"]
    label = iva_cfg["label"]

    ai = plan_doc.get("ai_analysis") or {}
    synthesis = ai.get("synthesis") or {}
    vision = ai.get("vision") or {}
    quantities = plan_doc.get("quantities") or {}
    ouvrages = synthesis.get("ouvrages") or []
    normas = synthesis.get("normas_aplicaveis") or []
    resumo = synthesis.get("resumo")

    numero_orc = f"ORC-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{(plan_doc.get('plan_id') or '')[-6:]}"

    wb = Workbook()
    resumo_ws = wb.active  # será renomeado em _write_resumo_sheet
    budget_ws = wb.create_sheet("Orçamento")
    qty_ws = wb.create_sheet("Quantidades")

    totals = _write_budget_sheet(
        budget_ws,
        ouvrages=ouvrages,
        iva_rate=rate,
        iva_label=label,
    )
    _write_quantities_sheet(qty_ws, quantities)
    _write_resumo_sheet(
        resumo_ws,
        plan_doc=plan_doc,
        totals=totals,
        iva_label=label,
        numero_orc=numero_orc,
        ouvrages_count=len(ouvrages),
        quantities_count=len(quantities),
        resumo=resumo,
        normas=normas,
        branding=branding,
    )

    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    return data, {
        "numero_orc": numero_orc,
        "iva_rate": rate,
        "iva_label": label,
        "totals": totals,
        "ouvrages": len(ouvrages),
        "quantities": len(quantities),
    }
