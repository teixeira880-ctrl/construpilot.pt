"""Excel do estudo CLT: mapa de quantidades com totais por fórmula, lista de painéis (geometria, volumes, massas), ligações por
origem, plano de prensa, vãos medidos e hipóteses. Cores da empresa nos cabeçalhos."""
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
         titulo: str | None = None, aviso_precos: str | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Mapa de quantidades"
    thin = Side(style="thin", color="DFE4E9")
    ws["A1"] = titulo or res.get("nome") or t("titulo", lang)
    ws["A1"].font = Font(bold=True, size=14, color=accent_hex)
    ws["A2"] = (empresa + " · " if empresa else "") + t("pre", lang) + ((" · " + aviso_precos) if aviso_precos else "")
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

    def folha(nome, head, rows, larg, totais=()):
        w = wb.create_sheet(nome)
        for i, h in enumerate(head, 1):
            w.cell(row=1, column=i, value=h)
        _style_header(w, 1, len(head), accent_hex)
        for k, vals in enumerate(rows, 2):
            for i, v in enumerate(vals, 1):
                w.cell(row=k, column=i, value=v)
        n = len(rows) + 1
        if rows and totais:
            w.cell(row=n + 1, column=1, value="Total").font = Font(bold=True)
            for col in totais:
                L = get_column_letter(col)
                w.cell(row=n + 1, column=col, value=f"=SUM({L}2:{L}{n})").font = Font(bold=True)
        for i, wdt in enumerate(larg, 1):
            w.column_dimensions[get_column_letter(i)].width = wdt
        w.freeze_panes = "A2"
        if rows:
            w.auto_filter.ref = f"A1:{get_column_letter(len(head))}{n}"
        return w

    folha("Painéis", ["ID", "Uso", "Elemento", "Nível", "Composição", "Camadas (mm)", "Comprimento (mm)", "Largura / altura (mm)", "Recortes",
                      "m² envolvente", "m² líquidos", "m³ envolvente", "m³ líquidos", "Massa (kg)", "Corte CNC (m)", "Esquadros", "Hold-downs", "Nota"],
          [[p["id"], t(p["tipo"], lang), p["ref"], p.get("nivel") or "", p["painel"], "-".join(str(int(c)) for c in p["camadas"]), p["L"], p["H"],
            "; ".join(f"{r.get('id') or ''} {r['x1'] - r['x0']:.0f}×{r['z1'] - r['z0']:.0f} @ x{r['x0']:.0f} z{r['z0']:.0f}" for r in p.get("recortes") or []),
            round(p["areaBruta"], 3), round(p["areaLiq"], 3), round(p["volBruto"], 4), round(p["volLiq"], 4), round(p["kg"], 1), round(p["corteCNC"], 2),
            p.get("esquadros"), p.get("holdDowns"), p.get("nota") or ""] for p in res["paineis"]],
          [12, 10, 12, 10, 12, 16, 12, 12, 40, 11, 11, 11, 11, 11, 11, 9, 9, 30], (10, 11, 12, 13, 14, 15, 16, 17))
    rows = []
    for grp in ("parafusos", "conectores", "ancoragens"):
        for p in res[grp]:
            for o, q in p["origens"].items():
                rows.append([grp, p["nome"], o, q])
    folha("Ligações", ["Grupo", "Artigo", "Origem (ligação)", "Quantidade"], rows, [12, 60, 50, 12], (4,))
    folha("Bandas e fitas", ["Artigo", "Origem", "Metros"], [[m["nome"], o, round(v, 2)] for m in res["metros"] for o, v in m["origens"].items()],
          [56, 46, 12], (3,))
    rows = []
    for pl in res["planosPrensa"]:
        for fi, f in enumerate(pl["folhas"], 1):
            for p in f["pecas"]:
                rows.append([pl["painel"], fi, f["comprimento"], f["largura"], p.get("ref", ""), f"{p['w']:.0f}×{p['h']:.0f}", f"{p['x']:.0f}, {p['y']:.0f}",
                             "sim" if p.get("rodada") else "não"])
    folha("Plano de prensa", ["Composição", "Bruto n.º", "Comprimento do bruto (mm)", "Largura do bruto (mm)", "Painel", "Painel (mm)", "Posição x,y (mm)",
                              "Rodado"], rows, [14, 9, 14, 14, 14, 16, 16, 8])
    folha("Vãos", ["Parede", "Nível", "Vão", "Tipo", "Largura (mm)", "Altura (mm)", "m²", "m³ recortados"],
          [[v["parede"], v.get("nivel") or "", v.get("id") or "", v["tipo"], v["largura"], v["altura"], round(v["m2"], 3), round(v["m3Recorte"], 4)]
           for v in res["vaos"]], [14, 12, 12, 10, 12, 12, 10, 12], (7, 8))
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
