"""Livro Excel do mapa de quantidades da estrutura, com fórmulas : azul = valor medido ou pressuposto (editável) ; preto = fórmula.
Folhas : Mapa (resumo por artigo), Pressupostos, Verticais (pilares, paredes, núcleos), Lajes, Vigas."""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HDR = PatternFill("solid", fgColor="1F4E46")
TOT = PatternFill("solid", fgColor="E8F3F0")
INP = Font(name="Arial", size=10, color="0000FF")
TXT = Font(name="Arial", size=10)
BLD = Font(name="Arial", size=10, bold=True)
thin = Side(style="thin", color="BBBBBB")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
N2, N3, N0 = "#,##0.00", "0.000", "#,##0"


def _folha(wb, titulo, cab, larguras, nota):
    ws = wb.create_sheet(titulo)
    ws["A1"] = titulo
    ws["A1"].font = Font(name="Arial", size=13, bold=True, color="1F4E46")
    ws["A2"] = nota
    ws["A2"].font = Font(name="Arial", size=9, italic=True, color="666666")
    for j, (h, w) in enumerate(zip(cab, larguras), 1):
        c = ws.cell(row=4, column=j, value=h)
        c.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        c.fill = HDR
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[4].height = 32
    ws.freeze_panes = "A5"
    return ws


def _linha(ws, r, vals, fmt=None, entradas=(), negrito=False):
    for j, v in enumerate(vals, 1):
        c = ws.cell(row=r, column=j, value=v)
        formula = isinstance(v, str) and v.startswith("=")
        c.font = BLD if negrito else (INP if (j in entradas and not formula and v is not None) else TXT)
        c.border = BOX
        if negrito:
            c.fill = TOT
        if fmt and j in fmt and v is not None:
            c.number_format = fmt[j]
        if isinstance(v, str) and not formula and len(v) > 40:
            c.alignment = Alignment(wrap_text=True, vertical="top")


def gerar(modelo: dict, caminho: str, titulo: str = "") -> str:
    par, niv = modelo["parametros"], modelo["niveis"]
    wb = Workbook()
    wb.remove(wb.active)
    AZ = "Azul = medido no desenho ou pressuposto (editável) ; preto = fórmula."

    # Pressupostos
    wp = _folha(wb, "Pressupostos", ["Parâmetro", "Valor", "Un", "Origem"], [58, 12, 8, 70], AZ)
    linhas = [("Escala do desenho 1/", modelo.get("escala"), "", "Desenho"),
              ("Cota de arranque dos pilares e paredes", par["cota_base"], "m", "PRESSUPOSTO se não foi indicada : as fundações / piso inferior não estão nestas plantas"),
              ("Altura das vigas sem secção indicada", par["h_vigas"], "m", "PRESSUPOSTO : só usada nas vigas sem secção escrita no desenho"),
              ("Lâmina de betão sobre os moldes", par["lamina"], "m", "Nota do desenho, ou valor corrente"),
              ("Largura média da nervura entre moldes", par["nervura"], "m", "PRESSUPOSTO : confirmar com a ficha do fabricante dos moldes"),
              ("Taxa de aço das lajes", par["taxa_lajes"], "kg/m³", "ESTIMATIVA : não há desenhos de armaduras"),
              ("Taxa de aço dos pilares", par["taxa_pilares"], "kg/m³", "ESTIMATIVA"),
              ("Taxa de aço das paredes e núcleos", par["taxa_paredes"], "kg/m³", "ESTIMATIVA"),
              ("Taxa de aço das vigas", par["taxa_vigas"], "kg/m³", "ESTIMATIVA")]
    for i, ln in enumerate(linhas):
        _linha(wp, 5 + i, list(ln), {2: N3 if i in (1, 2, 3, 4) else N0}, entradas=(2,))
    P = {"base": "Pressupostos!$B$6", "hv": "Pressupostos!$B$7", "lam": "Pressupostos!$B$8", "nerv": "Pressupostos!$B$9",
         "tl": "Pressupostos!$B$10", "tp": "Pressupostos!$B$11", "tw": "Pressupostos!$B$12", "tv": "Pressupostos!$B$13"}
    r0 = 5 + len(linhas) + 2
    wp.cell(row=r0 - 1, column=1, value="Níveis lidos nas caixas de nível do desenho").font = BLD
    _linha(wp, r0, ["Nível", "Zsup (m)", "e (m)", "Altura livre até à laje de baixo (m)"], negrito=True)
    for i, n in enumerate(niv):
        r = r0 + 1 + i
        baixo = P["base"] if i == 0 else f"B{r - 1}"
        _linha(wp, r, [n["nome"], n["zsup"], n["e"], f"=B{r}-C{r}-{baixo}"], {2: N3, 3: N3, 4: N3}, entradas=(2, 3))
    lin_niv = {n["nome"]: r0 + 1 + i for i, n in enumerate(niv)}
    h1 = f"Pressupostos!$D${r0 + 1}"                         # altura livre do tramo de base (depende da cota de arranque)

    # Verticais
    wv = _folha(wb, "Verticais", ["Elemento", "Tipo", "a (m)", "b (m)", "Área da secção (m²)", "Perímetro (m)", "Níveis suportados",
                                  "Altura acima do 1.º nível (m)", "Tramo de base (0/1)", "Altura total (m)", "Betão (m³)", "Cofragem (m²)", "Observações"],
                [26, 9, 8, 8, 11, 11, 30, 12, 9, 10, 11, 11, 60], AZ + " Altura livre entre lajes.")
    r = 5
    for v in modelo["verticais"]:
        ret = v["retangular"]
        _linha(wv, r, [v["nome"], v["tipo"], v["a"], v["b"], f"=C{r}*D{r}" if ret else v["area"], f"=2*(C{r}+D{r})" if ret else v["perimetro"],
                       ", ".join(v["niveis"]), v["h_fixa"], 1 if v["tramo_base"] else 0, f"=H{r}+I{r}*{h1}", f"=E{r}*J{r}", f"=F{r}*J{r}",
                       " ; ".join(v["notas"] + ([] if ret else ["secção não retangular : área e perímetro medidos no desenho"]))],
               {3: N2, 4: N2, 5: N3, 6: N2, 8: N3, 10: N3, 11: N2, 12: N2}, entradas=(3, 4, 5, 6, 8, 9))
        r += 1
    fv = r - 1
    _linha(wv, r, ["Total", None, None, None, None, None, None, None, None, None, f"=SUM(K5:K{fv})", f"=SUM(L5:L{fv})", None], {11: N2, 12: N2}, negrito=True)

    # Lajes
    wl = _folha(wb, "Lajes", ["Nível", "Área bruta (m²)", "Aberturas (m²)", "Área de laje (m²)", "da qual fora do perímetro dos pilares (m²)", "N.º de moldes",
                              "Módulo (m)", "Área aligeirada (m²)", "Área maciça (m²)", "e (m)", "Betão/m² zona aligeirada (m)", "Betão (m³)",
                              "Perímetro (m)", "Cofragem de bordo (m²)"],
                [16, 11, 11, 11, 14, 9, 9, 11, 11, 8, 12, 11, 10, 11], AZ + " Pilares e paredes não deduzidos.")
    r = 5
    for lj in modelo["lajes"]:
        e = f"Pressupostos!$C${lin_niv[lj['nivel']]}"
        _linha(wl, r, [lj["nivel"], lj["area_bruta"], lj["aberturas"], f"=B{r}-C{r}", lj["fora_do_perimetro"], lj["moldes"], lj["modulo"] or None,
                       f"=F{r}*G{r}^2" if lj["moldes"] else 0, f"=D{r}-H{r}", f"={e}",
                       f"=J{r}-(G{r}-{P['nerv']})^2*(J{r}-{P['lam']})/G{r}^2" if lj["moldes"] else f"=J{r}",
                       f"=I{r}*J{r}+H{r}*K{r}", lj["perimetro"], f"=M{r}*J{r}"],
               {2: N2, 3: N2, 4: N2, 5: N2, 6: N0, 7: N3, 8: N2, 9: N2, 10: N3, 11: N3, 12: N2, 13: N2, 14: N2}, entradas=(2, 3, 5, 6, 7, 13))
        r += 1
    fl = r - 1
    _linha(wl, r, ["Total", f"=SUM(B5:B{fl})", f"=SUM(C5:C{fl})", f"=SUM(D5:D{fl})", f"=SUM(E5:E{fl})", f"=SUM(F5:F{fl})", None, f"=SUM(H5:H{fl})",
                   f"=SUM(I5:I{fl})", None, None, f"=SUM(L5:L{fl})", None, f"=SUM(N5:N{fl})"],
           {2: N2, 3: N2, 4: N2, 5: N2, 6: N0, 8: N2, 9: N2, 12: N2, 14: N2}, negrito=True)

    # Vigas
    wg = _folha(wb, "Vigas", ["Viga", "Níveis", "N.º de níveis", "b (m)", "h (m)", "Vão livre (m)", "e da laje (m)", "h abaixo da laje (m)",
                              "Betão (m³)", "Cofragem lateral (m²)", "Observações"], [10, 28, 8, 8, 8, 10, 9, 10, 11, 11, 52],
                AZ + " Só o volume abaixo da laje ; o fundo da viga está na cofragem da laje.")
    r = 5
    for v in modelo["vigas"]:
        obs = [] if v["h_lida"] else ["altura por pressuposto"]
        obs += [] if v["b_lida"] else ["largura medida no desenho"]
        e = f"Pressupostos!$C${lin_niv[v['niveis'][0]]}"
        _linha(wg, r, [v["nome"], ", ".join(v["niveis"]), v["n"], v["b"], v["h"] if v["h_lida"] else f"={P['hv']}", v["vao"], f"={e}",
                       f"=MAX(E{r}-G{r},0)", f"=D{r}*H{r}*F{r}*C{r}", f"=2*H{r}*F{r}*C{r}", " ; ".join(obs)],
               {4: N2, 5: N2, 6: N2, 7: N3, 8: N3, 9: N2, 10: N2}, entradas=(3, 4, 5, 6))
        r += 1
    fg = max(r - 1, 5)
    _linha(wg, r, ["Total", None, None, None, None, f"=SUM(F5:F{fg})", None, None, f"=SUM(I5:I{fg})", f"=SUM(J5:J{fg})", None], {6: N2, 9: N2, 10: N2}, negrito=True)

    # Mapa
    wm = _folha(wb, "Mapa", ["Art.", "Designação", "Un", "Quantidade", "Observações"], [7, 58, 7, 14, 70],
                (titulo + " — " if titulo else "") + "Mapa de quantidades da estrutura medido na planta. Estudo a validar pelo projetista.")
    pil = f'SUMIFS(Verticais!K5:K{fv},Verticais!B5:B{fv},"Pilar")'
    cpil = f'SUMIFS(Verticais!L5:L{fv},Verticais!B5:B{fv},"Pilar")'
    itens = [("1", "BETÃO ESTRUTURAL", None, None, "Classe conforme o quadro de materiais do desenho"),
             ("1.1", "Pilares", "m³", f"={pil}", "Altura livre entre lajes"),
             ("1.2", "Paredes e núcleos", "m³", f"=Verticais!K{fv + 1}-{pil}", None),
             ("1.3", "Lajes (maciças e aligeiradas)", "m³", f"=Lajes!L{fl + 1}", "Zona aligeirada pelo betão equivalente"),
             ("1.4", "Vigas (volume abaixo da laje)", "m³", f"=Vigas!I{fg + 1}", None),
             (None, "Total de betão", "m³", "=SUM(D6:D9)", None),
             ("2", "COFRAGEM", None, None, None),
             ("2.1", "Pilares", "m²", f"={cpil}", None),
             ("2.2", "Paredes e núcleos", "m²", f"=Verticais!L{fv + 1}-{cpil}", None),
             ("2.3", "Lajes, fundo", "m²", f"=Lajes!D{fl + 1}", "Não deduz a secção dos pilares e paredes"),
             ("2.4", "Lajes, bordos", "m²", f"=Lajes!N{fl + 1}", None),
             ("2.5", "Vigas, faces laterais abaixo da laje", "m²", f"=Vigas!J{fg + 1}", None),
             (None, "Total de cofragem", "m²", "=SUM(D12:D16)", None),
             ("3", "ALIGEIRAMENTO", None, None, None),
             ("3.1", "Moldes de aligeiramento", "un", f"=Lajes!F{fl + 1}", "Contados um a um no desenho"),
             ("4", "AÇO — ESTIMATIVA", None, None, "Por taxas kg/m³ (folha Pressupostos) : não há desenhos de armaduras"),
             ("4.1", "Pilares", "kg", f"=D6*{P['tp']}", "Estimativa"),
             ("4.2", "Paredes e núcleos", "kg", f"=D7*{P['tw']}", "Estimativa"),
             ("4.3", "Lajes", "kg", f"=D8*{P['tl']}", "Estimativa"),
             ("4.4", "Vigas", "kg", f"=D9*{P['tv']}", "Estimativa"),
             (None, "Total de aço (estimativa)", "kg", "=SUM(D21:D24)", None),
             ("5", "ÁREAS", None, None, None),
             ("5.1", "Área total de laje", "m²", f"=Lajes!D{fl + 1}", "Aberturas deduzidas")]
    for i, it in enumerate(itens):
        sec = it[2] is None and it[0] is not None
        _linha(wm, 5 + i, list(it), {4: N0 if it[2] in ("kg", "un") else N2}, negrito=sec or it[0] is None)
    r = 5 + len(itens) + 1
    for cab, lst in (("Pressupostos", [f"{p['nome']} : {p['valor']} {p['un']}" for p in modelo["pressupostos"]]),
                     ("A confirmar", modelo["perguntas"]), ("Avisos", modelo["avisos"]),
                     ("Não incluído", ["; ".join(modelo.get("fora_do_ambito", []))])):
        if not lst or not lst[0]:
            continue
        wm.cell(row=r, column=2, value=cab).font = BLD
        for t in lst:
            r += 1
            c = wm.cell(row=r, column=2, value=t)
            c.font = TXT
            c.alignment = Alignment(wrap_text=True, vertical="top")
            wm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
            wm.row_dimensions[r].height = 15 * (1 + len(t) // 120)
        r += 2
    wb.move_sheet("Mapa", -(len(wb.sheetnames) - 1))
    wb.active = 0
    wb.save(caminho)
    return caminho
