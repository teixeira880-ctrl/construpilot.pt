"""Excel do estudo LSF: mapa de quantidades com totais por fórmula, lista de corte peça a peça, parafusos por origem,
planos de corte das placas e hipóteses. Cores da empresa nos cabeçalhos."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .i18n import t


def _style_header(ws, row, ncol, hexcor):
    fill = PatternFill("solid", fgColor=hexcor)
    for c in range(1, ncol + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def xlsx(res: dict, lin: list[dict], tot: dict | None, lang: str = "pt", accent_hex: str = "203B2D", empresa: str | None = None,
         titulo: str | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Mapa de quantidades"
    thin = Side(style="thin", color="DFE4E9")
    ws["A1"] = titulo or res.get("nome") or t("titulo", lang)
    ws["A1"].font = Font(bold=True, size=14, color=accent_hex)
    ws["A2"] = (empresa + " · " if empresa else "") + t("pre", lang)
    ws["A2"].font = Font(italic=True, size=9, color="9A3D0A")
    head = ["Código", "Capítulo", "Designação", "Un.", "Quantidade", "Preço unitário (€)", "Total (€)", "Origem do preço", "Fonte / referência",
            "Detalhe (rastreio)"]
    r0 = 4
    for i, h in enumerate(head, 1):
        ws.cell(row=r0, column=i, value=h)
    _style_header(ws, r0, len(head), accent_hex)
    r = r0 + 1
    first = r
    cats = []
    for l in lin:
        if l["cat"] not in cats:
            cats.append(l["cat"])
    sub_cells = []
    for c in cats:
        cr = r
        for l in (x for x in lin if x["cat"] == c):
            pr = l.get("preco") or {}
            ws.cell(row=r, column=1, value=l["code"])
            ws.cell(row=r, column=2, value=c)
            ws.cell(row=r, column=3, value=l["designacao"])
            ws.cell(row=r, column=4, value=l["un"])
            ws.cell(row=r, column=5, value=l["qtd"]).number_format = "#,##0.00" if l["un"] != "un" else "#,##0"
            if pr:
                ws.cell(row=r, column=6, value=pr["unit"]).number_format = "#,##0.00"
            ws.cell(row=r, column=7, value=f'=IF(F{r}="","",E{r}*F{r})').number_format = "#,##0.00"
            ws.cell(row=r, column=8, value={"biblioteca": "Biblioteca da empresa", "projeto": "Projeto",
                                            "mercado": "Mercado online — A ANALISAR"}.get(pr.get("origem"), "A orçamentar"))
            ws.cell(row=r, column=9, value=(pr.get("ref") or " · ".join(x for x in (pr.get("fonte"), pr.get("url"), pr.get("data")) if x)) if pr else "")
            ws.cell(row=r, column=10, value=l.get("detalhe") or "")
            if pr.get("origem") == "mercado":
                for col in (6, 7, 8):
                    ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor="FFF2CC")
            r += 1
        ws.cell(row=r, column=3, value=f"Subtotal — {c}").font = Font(bold=True)
        ws.cell(row=r, column=7, value=f"=SUM(G{cr}:G{r - 1})").number_format = "#,##0.00"
        ws.cell(row=r, column=7).font = Font(bold=True)
        sub_cells.append(f"G{r}")
        for col in range(1, len(head) + 1):
            ws.cell(row=r, column=col).border = Border(top=thin)
        r += 2
    ws.cell(row=r, column=3, value="TOTAL (linhas com preço)").font = Font(bold=True, size=12)
    ws.cell(row=r, column=7, value="=" + "+".join(sub_cells) if sub_cells else 0).number_format = "#,##0.00"
    ws.cell(row=r, column=7).font = Font(bold=True, size=12, color=accent_hex)
    ws.cell(row=r + 1, column=3, value="Linhas a orçamentar (sem preço)")
    ws.cell(row=r + 1, column=7, value=f'=COUNTIFS(H{first}:H{r - 1},"A orçamentar")')
    for i, wdt in enumerate([26, 22, 58, 6, 13, 15, 14, 24, 40, 70], 1):
        ws.column_dimensions[get_column_letter(i)].width = wdt
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)

    # lista de corte
    w2 = wb.create_sheet("Lista de corte")
    h2 = ["ID", "Grupo", "Elemento", "Nível", "Tipo de peça", "Perfil", "Comprimento (mm)", "Massa (kg)", "Nota"]
    for i, h in enumerate(h2, 1):
        w2.cell(row=1, column=i, value=h)
    _style_header(w2, 1, len(h2), accent_hex)
    for k, m in enumerate(res["membros"], 2):
        vals = [m["id"], t(m["grupo"], lang), m["ref"], m.get("nivel") or "", t(m["tipoPeca"], lang), m["perfilNome"], m["L"], round(m["kg"], 3), m.get("nota") or ""]
        for i, v in enumerate(vals, 1):
            w2.cell(row=k, column=i, value=v)
    n = len(res["membros"]) + 1
    w2.cell(row=n + 1, column=6, value="Total").font = Font(bold=True)
    w2.cell(row=n + 1, column=7, value=f"=SUM(G2:G{n})")
    w2.cell(row=n + 1, column=8, value=f"=SUM(H2:H{n})").font = Font(bold=True)
    for i, wdt in enumerate([18, 12, 12, 10, 30, 20, 16, 11, 50], 1):
        w2.column_dimensions[get_column_letter(i)].width = wdt
    w2.freeze_panes = "A2"
    w2.auto_filter.ref = f"A1:I{n}"

    # parafusos
    w3 = wb.create_sheet("Parafusos")
    for i, h in enumerate(["Parafuso", "Origem (ligação / placa)", "Quantidade"], 1):
        w3.cell(row=1, column=i, value=h)
    _style_header(w3, 1, 3, accent_hex)
    k = 2
    for p in res["parafusos"]:
        for o, q in p["origens"].items():
            w3.cell(row=k, column=1, value=p["nome"])
            w3.cell(row=k, column=2, value=o)
            w3.cell(row=k, column=3, value=q)
            k += 1
    w3.cell(row=k, column=2, value="Total").font = Font(bold=True)
    w3.cell(row=k, column=3, value=f"=SUM(C2:C{k - 1})").font = Font(bold=True)
    for i, wdt in enumerate([46, 46, 14], 1):
        w3.column_dimensions[get_column_letter(i)].width = wdt

    # placas
    w4 = wb.create_sheet("Placas — corte")
    for i, h in enumerate(["Material", "Placa (mm)", "Folha n.º", "Peça (mm)", "Posição x,y (mm)", "Rodada", "Origem"], 1):
        w4.cell(row=1, column=i, value=h)
    _style_header(w4, 1, 7, accent_hex)
    k = 2
    for c in res["planosCorte"]:
        for fi, f in enumerate(c["folhas"], 1):
            for p in f:
                for i, v in enumerate([c["nome"], f"{c['W']}×{c['H']}", fi, f"{p['w']:.0f}×{p['h']:.0f}", f"{p['x']:.0f}, {p['y']:.0f}",
                                       "sim" if p.get("rodada") else "não", p.get("ref", "")], 1):
                    w4.cell(row=k, column=i, value=v)
                k += 1
    for i, wdt in enumerate([34, 14, 10, 14, 18, 8, 30], 1):
        w4.column_dimensions[get_column_letter(i)].width = wdt

    # hipóteses
    w5 = wb.create_sheet("Hipóteses e avisos")
    w5["A1"] = "Hipóteses (a validar)"
    w5["A1"].font = Font(bold=True, color=accent_hex)
    k = 2
    for h in res.get("hipoteses") or []:
        w5.cell(row=k, column=1, value=h)
        k += 1
    k += 1
    w5.cell(row=k, column=1, value="Pontos a verificar").font = Font(bold=True, color="9A3D0A")
    for a in res.get("avisos") or []:
        k += 1
        w5.cell(row=k, column=1, value=a)
    w5.column_dimensions["A"].width = 160
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
