"""Excel da construção tradicional: mapa por piso com totais por fórmula, quadro de elementos e armaduras, paredes (fiadas e
unidades), hipóteses. Cores da empresa nos cabeçalhos."""
from __future__ import annotations

from engines.clt import xlsx as CX


def xlsx(res: dict, lin: list[dict], tot: dict | None, accent_hex: str = "203B2D", empresa: str | None = None, titulo: str | None = None,
         aviso_precos: str | None = None) -> bytes:
    import io

    from openpyxl import load_workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    fake = {"nome": res.get("nome"), "paineis": [], "parafusos": [], "conectores": [], "ancoragens": [], "metros": [], "planosPrensa": [], "vaos": [],
            "hipoteses": res.get("hipoteses"), "avisos": res.get("avisos")}
    wb = load_workbook(io.BytesIO(CX.xlsx(fake, lin, tot, "pt", accent_hex, empresa, titulo, aviso_precos)))
    for nm in ("Painéis", "Ligações", "Bandas e fitas", "Plano de prensa", "Vãos"):
        if nm in wb.sheetnames:
            del wb[nm]
    wb["Mapa de quantidades"]["A2"] = (empresa + " · " if empresa else "") + "Pré-dimensionamento e quantidades — a verificar por engenheiro de estruturas"

    def folha(nome, head, rows, larg, totais=()):
        w = wb.create_sheet(nome, 1)
        for i, h in enumerate(head, 1):
            w.cell(row=1, column=i, value=h)
        CX._style_header(w, 1, len(head), accent_hex)
        for k, vals in enumerate(rows, 2):
            for i, v in enumerate(vals, 1):
                w.cell(row=k, column=i, value=v)
        n = len(rows) + 1
        for col in totais:
            L = get_column_letter(col)
            w.cell(row=n + 1, column=col, value=f"=SUM({L}2:{L}{n})").font = Font(bold=True)
        for i, wd in enumerate(larg, 1):
            w.column_dimensions[get_column_letter(i)].width = wd
        w.freeze_panes = "A2"

    rows = []
    for p in res["pilares"]:
        rows.append(["Pilar", p["id"], p.get("nivel"), f"{p['b']:.0f}×{p['h']:.0f}", p["H"], p["armadura"], p["estribos"], round(p["Ntot_G"], 1), round(p["Ntot_Q"], 1),
                     round(p["m3"], 4), round(p["kg"], 2), round(p["cofragem"], 3)])
    for v in res["vigas"]:
        rows.append(["Viga", v["id"], v.get("nivel"), f"{v['b']:.0f}×{v['h']:.0f}", v["L"], v["armadura"], v["estribos"], round(v["g"], 2), round(v["q"], 2),
                     round(v["m3"], 4), round(v["kg"], 2), round(v["cofragem"], 3)])
    for s in res["sapatas"]:
        rows.append(["Sapata", s["id"], s["pilar"], f"{s['B']:.0f}×{s['B']:.0f}×{s['hs']:.0f}", None, s["armadura"], "", round(s["G"], 1), round(s["Q"], 1),
                     round(s["m3"], 4), round(s["kg"], 2), round(s["cofragem"], 3)])
    for v in res["vigasFundacao"]:
        rows.append(["Viga de fundação", v["id"], v["parede"], f"{v['b']:.0f}×{v['h']:.0f}", v["L"], v["armadura"], v["estribos"], None, None, round(v["m3"], 4),
                     round(v["kg"], 2), round(v["cofragem"], 3)])
    for g in res["vergas"]:
        rows.append(["Verga", g["id"], g["parede"], f"{g['b']:.0f}×{g['h']:.0f}", g["L"], g["armadura"], "", None, None, round(g["m3"], 4), round(g["kg"], 2),
                     round(g["cofragem"], 3)])
    for f in res["lajes"]:
        rows.append(["Laje", f["id"], f.get("grupo"), f["seccao"], None, "malhas calculadas", "", f["g2"], f["q"], round(f["m3"], 4), round(f["kg"], 2), round(f["cofragem"], 3)])
    for c in res["coberturas"]:
        rows.append(["Cobertura", c["id"], "", c["seccao"], None, "malhas calculadas", "", None, None, round(c["m3"], 4), round(c["kg"], 2), round(c["cofragem"], 3)])
    folha("Elementos e armaduras", ["Elemento", "ID", "Nível / apoio", "Secção (mm)", "Comprimento / altura (mm)", "Armadura", "Estribos",
                                     "G (kN ou kN/m)", "Q (kN ou kN/m)", "Betão (m³)", "Aço (kg)", "Cofragem (m²)"], rows,
          [16, 18, 16, 22, 14, 30, 30, 12, 12, 11, 11, 12], (10, 11, 12))
    folha("Paredes", ["Parede", "Nível", "Unidade", "Resistente", "Comprimento (mm)", "Altura de alvenaria (mm)", "Fiadas", "Unidades", "m² de alvenaria",
                      "Argamassa (m³)", "Vigas"],
          [[w["id"], w.get("nivel"), w["unidade"], "sim" if w["resistente"] else "não", round(w["L"], 1), w["Halv"], w["fiadas"], w["unidades"], round(w["areaAlv"], 3),
            round(w["argamassa"], 4), ", ".join(w["vigas"])] for w in res["paredes"]], [12, 12, 34, 10, 14, 14, 8, 10, 12, 12, 20], (8, 9, 10))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
