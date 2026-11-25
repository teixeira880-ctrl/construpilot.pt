"""Exportação Excel da Carta de Obra de Baixo Carbono — mesma estrutura, cores e fórmulas do quadro ConstruPilot v3 (PT),
avec les colonnes de traçabilité (quantité prévue / livrée, validité FDES, pièces, contrôles) et deux onglets en plus :
« Controles » (croisement avec les imperatifs du chantier) et « Documentos ».

Toutes les valeurs calculées sont des FORMULES : l'entreprise peut corriger une cellule jaune, le tableau se recalcule.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import referentiel as R

FONT = "Calibri"
VERT, VERT2, VERT_CLAIR, ZEBRE, JAUNE = "1B4332", "2D6A4F", "D8F3DC", "F0F7F4", "FFF3CD"
ROUGE, ORANGE, BLEU, GRIS = "F8D7DA", "FFE5CC", "DCEBFA", "EEEEEE"
fill = lambda c: PatternFill("solid", fgColor=c)   # noqa: E731
THIN = Side(style="thin", color="C9D6CF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="center")
NIV_FILL = {"bloquant": ROUGE, "alerte": ORANGE, "manquant": JAUNE, "info": BLEU}
NIV_LIB = {"bloquant": "BLOQUEANTE", "alerte": "FORA DO IMPERATIVO", "manquant": "INFORMAÇÃO EM FALTA", "info": "INFO"}


def _titre(ws, ref, txt, size=14):
    ws[ref] = txt
    ws[ref].font = Font(name=FONT, bold=True, color="FFFFFF", size=size)
    ws[ref].fill = fill(VERT)
    ws[ref].alignment = Alignment(vertical="center")


def _entete(ws, row, cols, start=1, color=VERT2, fg="FFFFFF"):
    for i, h in enumerate(cols):
        c = ws.cell(row=row, column=start + i, value=h)
        c.font = Font(name=FONT, bold=True, color=fg, size=10)
        c.fill = fill(color)
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = BOX


def _cell(ws, row, col, v, fmt=None, bold=False, bg=None, color="000000", wrap=False):
    c = ws.cell(row=row, column=col, value=v)
    c.font = Font(name=FONT, size=10, bold=bold, color=color)
    c.border = BOX
    if fmt:
        c.number_format = fmt
    if bg:
        c.fill = fill(bg)
    if wrap:
        c.alignment = WRAP
    return c


def _largeurs(ws, w):
    for i, x in enumerate(w, 1):
        ws.column_dimensions[get_column_letter(i)].width = x


def construire(res: dict, entreprise: str = "") -> bytes:
    """res : sortie de calcul.calculer(). Renvoie les octets du .xlsx."""
    wb = Workbook()
    syn = wb.active
    syn.title = "Sintese"
    gr = wb.create_sheet("Grelha_Carta")
    sm = wb.create_sheet("Materiais")
    se = wb.create_sheet("Emissoes_Obra")
    co = wb.create_sheet("Controlos")
    pj = wb.create_sheet("Documentos")
    me = wb.create_sheet("Metodo_Fontes")
    docs = {d.get("doc_id"): d for d in res.get("documents") or []}

    # ========================================================================== Materiais
    mats = [m for m in res["materiaux"]]
    _titre(sm, "A1", "ACOMPANHAMENTO DA PEGADA DE CARBONO DOS MATERIAIS (TODAS AS ESPECIALIDADES & DAP)")
    sm.merge_cells("A1:S1")
    sm.row_dimensions[1].height = 24
    hdr = ["Capítulo / Especialidade", "Família de Materiais", "Solução Aplicada", "Tipologia", "Quantidade considerada", "Unidade",
           "FE Referência Standard (kgCO2e/u)", "FE DAP Obra (kgCO2e/u)", "Ref. DAP (n.º de registo)", "Distância Abast. (km)",
           "Peso Referência (kgCO2e)", "Peso Real Obra (kgCO2e)", "Ganho Carbono (kgCO2e)", "Redução (%)",
           "Qtd. prevista (medição)", "Qtd. entregue (guias de remessa)", "Validade DAP", "Documentos justificativos", "Controlos"]
    _entete(sm, 2, hdr)
    sm.row_dimensions[2].height = 42
    r0 = 3
    for i, m in enumerate(mats):
        r = r0 + i
        bg = ZEBRE if i % 2 else "FFFFFF"
        _cell(sm, r, 1, m.get("lot"), bold=True, bg=bg, color=VERT)
        _cell(sm, r, 2, m.get("famille"), bg=bg, wrap=True)
        _cell(sm, r, 3, m.get("solution"), bg=JAUNE, wrap=True)
        _cell(sm, r, 4, m.get("typologie"), bg=JAUNE)
        _cell(sm, r, 5, f"=IF(P{r}>0,P{r},O{r})", "#,##0.00", bg=bg)
        _cell(sm, r, 6, m.get("unite"), bg=bg)
        g = _cell(sm, r, 7, m.get("fe_ref"), "#,##0.00", bg=JAUNE)
        if m.get("fe_ref") is None:
            g.comment = Comment("Sem valor por defeito no referencial : introduzir o dado ambiental genérico ou a DAP.", "ConstruPilot")
        _cell(sm, r, 8, m.get("fe_fdes"), "#,##0.00", bg=JAUNE)
        _cell(sm, r, 9, m.get("ref_fdes") or "", bg=JAUNE, wrap=True)
        dk = _cell(sm, r, 10, m.get("distance_km"), "#,##0", bg=JAUNE)
        if m.get("distance_source"):
            dk.comment = Comment(str(m["distance_source"])[:250], "ConstruPilot")
        _cell(sm, r, 11, f'=E{r}*IF(G{r}="",0,G{r})', "#,##0.0", bg=bg)
        _cell(sm, r, 12, f'=E{r}*IF(H{r}="",IF(G{r}="",0,G{r}),H{r})', "#,##0.0", bg=bg)
        _cell(sm, r, 13, f"=K{r}-L{r}", "#,##0.0", bg=bg)
        _cell(sm, r, 14, f"=IF(K{r}>0,M{r}/K{r},0)", "0.0%", bg=bg)
        _cell(sm, r, 15, m.get("quantite_prevue") or 0, "#,##0.00", bg=JAUNE)
        _cell(sm, r, 16, m.get("quantite_livree"), "#,##0.00", bg=JAUNE)
        _cell(sm, r, 17, m.get("fdes_validite") or "", bg=bg)
        _cell(sm, r, 18, " ; ".join(docs.get(p, {}).get("nom", p) for p in m.get("pieces") or []), bg=bg, wrap=True)
        ctl = m.get("controles") or []
        worst = next((n for n in ("bloquant", "alerte", "manquant", "info") if any(c["niveau"] == n for c in ctl)), None)
        _cell(sm, r, 19, " | ".join(f"{c['code']} {c['message']}" for c in ctl)[:900] or "OK", bg=NIV_FILL.get(worst, VERT_CLAIR), wrap=True)
    rl = r0 + len(mats) - 1 if mats else r0
    rt = rl + 1
    _cell(sm, rt, 1, "TOTAL PEGADA MATERIAIS (kgCO2e)", bold=True, bg=VERT, color="FFFFFF")
    sm.merge_cells(start_row=rt, start_column=1, end_row=rt, end_column=10)
    for col, f, fmt in ((11, f"=SUM(K{r0}:K{rl})", "#,##0.0"), (12, f"=SUM(L{r0}:L{rl})", "#,##0.0"), (13, f"=SUM(M{r0}:M{rl})", "#,##0.0"),
                        (14, f"=IF(K{rt}>0,M{rt}/K{rt},0)", "0.0%")):
        _cell(sm, rt, col, f, fmt, bold=True, bg=VERT, color="FFFFFF")
    _cell(sm, rt + 1, 1, "TOTAL PEGADA MATERIAIS (tCO2e)", bold=True, bg=VERT, color="FFFFFF")
    sm.merge_cells(start_row=rt + 1, start_column=1, end_row=rt + 1, end_column=10)
    for col in (11, 12, 13):
        L = get_column_letter(col)
        _cell(sm, rt + 1, col, f"={L}{rt}/1000", "#,##0.00", bold=True, bg=VERT, color="FFFFFF")
    _cell(sm, rt + 1, 14, "-", bold=True, bg=VERT, color="FFFFFF")
    dv = DataValidation(type="list", formula1='"' + ",".join(R.TYPOLOGIES_MATERIAU) + '"', allow_blank=True)
    sm.add_data_validation(dv)
    dv.add(f"D{r0}:D{rl}")
    dvl = DataValidation(type="list", formula1='"' + ",".join(R.LOTS) + '"', allow_blank=False)
    sm.add_data_validation(dvl)
    dvl.add(f"A{r0}:A{rl}")
    sm.conditional_formatting.add(f"N{r0}:N{rl}", CellIsRule(operator="lessThan", formula=["0"], fill=fill(ROUGE)))
    sm.freeze_panes = "C3"
    _largeurs(sm, [26, 30, 34, 13, 12, 8, 14, 14, 24, 11, 15, 15, 14, 11, 12, 14, 12, 28, 60])
    leg = rt + 3
    sm.cell(row=leg, column=1, value="Legenda : células amarelas = a introduzir / corrigir pela empresa (ou preenchidas automaticamente a partir das DAP e guias de remessa).").font = Font(name=FONT, italic=True, size=9)
    sm.cell(row=leg + 1, column=1, value="Quantidade considerada = quantidade entregue (guias) se existir, senão a quantidade prevista na medição. Sem DAP, o peso real = peso de referência (nenhum ganho reivindicado).").font = Font(name=FONT, italic=True, size=9)
    RNG = lambda c: f"Materiais!${c}${r0}:${c}${rl}"   # noqa: E731

    # ========================================================================== Emissoes_Obra
    _titre(se, "A1", "ACOMPANHAMENTO QUANTITATIVO DAS EMISSÕES DE GEE NA FASE DE OBRA (EXECUÇÃO)")
    se.merge_cells("A1:H1")
    _entete(se, 2, ["Fonte de Emissão", "Subcategoria / Recurso", "Quantidade Consumida", "Unidade", "Fator de Emissão (FE)", "Unidade FE",
                    "Emissões Totais (kgCO2e)", "Documentos justificativos"])
    ems = res["emissions"]
    for i, e in enumerate(ems):
        r = 3 + i
        bg = ZEBRE if i % 2 else "FFFFFF"
        _cell(se, r, 1, e.get("poste"), bg=bg)
        _cell(se, r, 2, e.get("ressource"), bg=bg, wrap=True)
        _cell(se, r, 3, e.get("quantite") or 0, "#,##0.00", bg=JAUNE)
        _cell(se, r, 4, e.get("unite"), bg=bg)
        _cell(se, r, 5, e.get("fe"), "#,##0.000", bg=JAUNE)
        _cell(se, r, 6, e.get("unite_fe"), bg=bg)
        _cell(se, r, 7, f"=C{r}*E{r}", "#,##0.00", bold=True, bg=bg, color=VERT)
        _cell(se, r, 8, " ; ".join(docs.get(p, {}).get("nom", p) for p in e.get("pieces") or []), bg=bg, wrap=True)
    el = 2 + len(ems)
    et = el + 1
    _cell(se, et, 1, "TOTAL EMISSÕES FASE DE OBRA (kgCO2e)", bold=True, bg=VERT, color="FFFFFF")
    se.merge_cells(start_row=et, start_column=1, end_row=et, end_column=6)
    _cell(se, et, 7, f"=SUM(G3:G{el})", "#,##0.00", bold=True, bg=VERT, color="FFFFFF")
    _cell(se, et + 1, 1, "TOTAL EMISSÕES FASE DE OBRA (tCO2e)", bold=True, bg=VERT, color="FFFFFF")
    se.merge_cells(start_row=et + 1, start_column=1, end_row=et + 1, end_column=6)
    _cell(se, et + 1, 7, f"=G{et}/1000", "#,##0.00", bold=True, bg=VERT, color="FFFFFF")
    _largeurs(se, [26, 46, 18, 10, 20, 15, 24, 36])
    se.freeze_panes = "A3"

    # ========================================================================== Grille charte
    _titre(gr, "A1", "CARTA DE OBRA DE BAIXO CARBONO - GRELHA DE ACOMPANHAMENTO OPERACIONAL")
    gr.merge_cells("A1:N1")
    _entete(gr, 2, ["Eixo Temático", "Ação / Compromisso de Baixo Carbono", "Indicador de Desempenho (KPI)", "Objetivo", "Valor Realizado",
                    "Unidade", "Responsável", "Estado de Implementação", "Comentários / Provas (DAP, e-GAR, Faturas)",
                    "Operador", "Objetivo (valor)", "Origem do valor", "Estado forçado (opcional)", "Documentos anexos"])
    gr.row_dimensions[2].height = 40
    ch = res["charte"]
    for i, c in enumerate(ch):
        r = 3 + i
        bg = ZEBRE if i % 2 else "FFFFFF"
        sym = "≥" if c.get("op") == ">=" else "≤"
        _cell(gr, r, 1, c.get("axe"), bold=True, bg=bg, color=VERT, wrap=True)
        _cell(gr, r, 2, c.get("action"), bg=bg, wrap=True)
        _cell(gr, r, 3, c.get("kpi"), bg=bg, wrap=True)
        _cell(gr, r, 4, f"{sym} {c.get('cible'):g}" + ("" if c.get("unite") == "%" else ""), bg=bg)
        _cell(gr, r, 5, c.get("realise"), "#,##0.0", bg=JAUNE)
        _cell(gr, r, 6, c.get("unite"), bg=bg)
        _cell(gr, r, 7, c.get("acteur"), bg=bg, wrap=True)
        _cell(gr, r, 8, f'=IF(M{r}<>"",M{r},IF(E{r}="",IF(N{r}>0,"Em curso","A iniciar"),'
                        f'IF(OR(AND(J{r}=">=",E{r}>=K{r}),AND(J{r}="<=",E{r}<=K{r})),"Conforme","Não conforme")))', bold=True, bg=bg)
        _cell(gr, r, 9, (c.get("preuve") or "") + (f" — {c['commentaire']}" if c.get("commentaire") else ""), bg=bg, wrap=True)
        _cell(gr, r, 10, c.get("op"), bg=bg)
        _cell(gr, r, 11, c.get("cible"), "#,##0.##", bg=JAUNE)
        _cell(gr, r, 12, c.get("source_realise") or "", bg=bg)
        _cell(gr, r, 13, c.get("statut_force") or None, bg=JAUNE)
        _cell(gr, r, 14, len(c.get("pieces") or []), "0", bg=bg)
        gr.row_dimensions[r].height = 42
    gl = 2 + len(ch)
    dvs = DataValidation(type="list", formula1='"' + ",".join(R.STATUTS) + '"', allow_blank=True)
    gr.add_data_validation(dvs)
    dvs.add(f"M3:M{gl}")
    for txt, col in (("Conforme", "D8F3DC"), ("Não conforme", ROUGE), ("Em curso", BLEU), ("A iniciar", JAUNE)):
        gr.conditional_formatting.add(f"H3:H{gl}", FormulaRule(formula=[f'H3="{txt}"'], fill=fill(col)))
    _largeurs(gr, [26, 44, 36, 14, 12, 12, 20, 16, 36, 9, 10, 18, 16, 9])
    gr.freeze_panes = "C3"

    # ========================================================================== Synthèse
    pr = res["projet"]
    _titre(syn, "A1", "PAINEL DE CARBONO DA OBRA & CUMPRIMENTO DA META" + (f" — {pr.get('nom')}" if pr.get("nom") else ""))
    syn.merge_cells("A1:I1")
    syn.row_dimensions[1].height = 26
    sub = " · ".join(x for x in (entreprise, pr.get("adresse"), f"emitido em {pr.get('date', '')}") if x)
    syn["A2"] = sub
    syn["A2"].font = Font(name=FONT, italic=True, size=9, color="555555")
    for ref, txt in (("A3", "1. PARÂMETROS DO PROJETO & META DE CARBONO"), ("F3", "2. BALANÇO DE CARBONO CONSOLIDADO (MATERIAIS + OBRA)")):
        syn[ref] = txt
        syn[ref].font = Font(name=FONT, bold=True, color="FFFFFF", size=11)
        syn[ref].fill = fill(VERT2)
    syn.merge_cells("A3:D3")
    syn.merge_cells("F3:I3")
    params = [
        ("Tipologia do edifício", pr.get("typologie"), "Texto", "Lista"),
        ("Área útil de referência", pr.get("sref_m2"), "m²", "A introduzir (célula amarela)"),
        ("Enquadramento", pr.get("jalon"), "-", "PAG do ciclo de vida : cálculo obrigatório (edifícios novos > 1000 m² a partir de 2028, todos a partir de 2030)"),
        ("Meta de carbono (dono de obra)", pr.get("seuil_ic"), "kgCO2e/m²", pr.get("seuil_source") or "A introduzir (sem valor-limite legal em Portugal)"),
        ("Rácio de Referência", "=IF(B5>0, G5/B5, 0)", "kgCO2e/m²", "Calculado automaticamente (Materiais Ref.)"),
        ("Rácio Real da Obra", "=IF(B5>0, G8/B5, 0)", "kgCO2e/m²", "Calculado automaticamente (Materiais + Obra)"),
        ("Estado face à meta", '=IF(OR(B5="",B5=0,B7="",G6=0),"DADOS EM FALTA",IF(SUMPRODUCT((' + RNG("E") + '>0)*(' + RNG("G") + '="")*(' + RNG("H") + '=""))>0,'
         '"INCOMPLETO : "&SUMPRODUCT((' + RNG("E") + '>0)*(' + RNG("G") + '="")*(' + RNG("H") + '=""))&" família(s) sem FE",IF(B9<=B7, "CUMPRE A META", "ACIMA DA META")))',
         "-", "Comparação Real vs Meta (avaliável quando todas as famílias têm FE)"),
    ]
    for i, (a, b, c_, d_) in enumerate(params):
        r = 4 + i
        _cell(syn, r, 1, a, bg=ZEBRE)
        inp = i in (0, 1, 2, 3)
        _cell(syn, r, 2, b, "#,##0" if i in (1, 3, 4, 5) else None, bg=JAUNE if inp else "FFFFFF", bold=i == 6)
        _cell(syn, r, 3, c_, bg=ZEBRE)
        _cell(syn, r, 4, d_, bg=ZEBRE, wrap=True)
    syn["D7"].comment = Comment("Meta de carbono. Fonte : " + (pr.get("seuil_source") or "a introduzir"), "ConstruPilot")
    syn.conditional_formatting.add("B10", FormulaRule(formula=['B10="CUMPRE A META"'], fill=fill(VERT_CLAIR)))
    syn.conditional_formatting.add("B10", FormulaRule(formula=['B10="ACIMA DA META"'], fill=fill(ROUGE)))
    syn.conditional_formatting.add("B10", FormulaRule(formula=['LEFT(B10,10)="INCOMPLETO"'], fill=fill(JAUNE)))
    dvt = DataValidation(type="list", formula1='"' + ",".join(R.TYPOLOGIES) + '"')
    dvj = DataValidation(type="list", formula1='"' + ",".join(R.JALONS) + '"')
    syn.add_data_validation(dvt)
    syn.add_data_validation(dvj)
    dvt.add("B4")
    dvj.add("B6")
    _entete(syn, 4, ["Rubrica do Balanço", "Total (kgCO2e)", "Total (tCO2e)", "Parte (%)"], start=6, color=VERT_CLAIR, fg=VERT)
    bil = [("Pegada Materiais (Solução de Referência)", f"=Materiais!K{rt}", "-"),
           ("Pegada Materiais (Real da Obra)", f"=Materiais!L{rt}", "=IF(G8>0, G6/G8, 0)"),
           ("Emissões Fase de Obra (Execução)", f"=Emissoes_Obra!G{et}", "=IF(G8>0, G7/G8, 0)"),
           ("TOTAL BALANÇO DE CARBONO DO PROJETO (Real)", "=G6+G7", "=IF(G8>0, 1, 0)"),
           ("GANHO DE CARBONO NOS MATERIAIS", f"=Materiais!M{rt}", f"=Materiais!N{rt}")]
    for i, (a, g, p_) in enumerate(bil):
        r = 5 + i
        b = i in (3, 4)
        _cell(syn, r, 6, a, bold=b, bg=VERT_CLAIR if b else "FFFFFF")
        _cell(syn, r, 7, g, "#,##0.0", bold=b, bg=VERT_CLAIR if b else "FFFFFF")
        _cell(syn, r, 8, f"=G{r}/1000", "#,##0.00", bold=b, bg=VERT_CLAIR if b else "FFFFFF")
        _cell(syn, r, 9, p_, "0.0%", bold=b, bg=VERT_CLAIR if b else "FFFFFF")
    syn["A12"] = "3. REPARTIÇÃO DO CARBONO POR CAPÍTULO (MATERIAIS)"
    syn["A12"].font = Font(name=FONT, bold=True, color="FFFFFF", size=11)
    syn["A12"].fill = fill(VERT2)
    syn.merge_cells("A12:D12")
    _entete(syn, 13, ["Capítulo / Especialidade", "Referência (kgCO2e)", "Real (kgCO2e)", "Ganho (kgCO2e)"], color=VERT_CLAIR, fg=VERT)
    for i, lot in enumerate(R.LOTS):
        r = 14 + i
        _cell(syn, r, 1, lot, bg=ZEBRE if i % 2 else "FFFFFF")
        for col, L in ((2, "K"), (3, "L"), (4, "M")):
            _cell(syn, r, col, f"=SUMIF({RNG('A')}, A{r}, {RNG(L)})", "#,##0.0", bg=ZEBRE if i % 2 else "FFFFFF")
    syn["A23"] = "4. AVANÇO DOS COMPROMISSOS DA CARTA"
    syn["A23"].font = Font(name=FONT, bold=True, color="FFFFFF", size=11)
    syn["A23"].fill = fill(VERT2)
    syn.merge_cells("A23:D23")
    _entete(syn, 24, ["Estado das Ações", "N.º de Ações", "Repartição (%)", "Observação"], color=VERT_CLAIR, fg=VERT)
    obs = {"Conforme": "Compromisso validado com prova", "Em curso": "Ação em implementação na obra", "A iniciar": "Ação por lançar",
           "Não conforme": "Desvio constatado - ação corretiva necessária", "Não aplicável": "Fora do âmbito da empreitada"}
    for i, s in enumerate(["Conforme", "Em curso", "A iniciar", "Não conforme", "Não aplicável"]):
        r = 25 + i
        _cell(syn, r, 1, s)
        _cell(syn, r, 2, f"=COUNTIF(Grelha_Carta!$H$3:$H${gl}, A{r})", "0")
        _cell(syn, r, 3, f"=IF(SUM($B$25:$B$29)>0, B{r}/SUM($B$25:$B$29), 0)", "0.0%")
        _cell(syn, r, 4, obs[s])
    syn["F12"] = "5. CRUZAMENTO COM OS IMPERATIVOS DA OBRA"
    syn["F12"].font = Font(name=FONT, bold=True, color="FFFFFF", size=11)
    syn["F12"].fill = fill(VERT2)
    syn.merge_cells("F12:I12")
    _entete(syn, 13, ["Nível", "N.º", "Significado", ""], start=6, color=VERT_CLAIR, fg=VERT)
    sig = {"bloquant": "Dado incoerente a corrigir (unidade, valor impossível)", "alerte": "Resultado fora dos imperativos da obra",
           "manquant": "Informação ou documento justificativo em falta", "info": "Ponto de atenção"}
    n_ctrl = len(res["controles"])
    for i, n in enumerate(("bloquant", "alerte", "manquant", "info")):
        r = 14 + i
        _cell(syn, r, 6, NIV_LIB[n], bold=True, bg=NIV_FILL[n])
        _cell(syn, r, 7, f'=COUNTIF(Controlos!$A$3:$A${max(3, 2 + n_ctrl)}, F{r})', "0", bold=True, bg=NIV_FILL[n])
        _cell(syn, r, 8, sig[n], bg=NIV_FILL[n], wrap=True)
        syn.merge_cells(start_row=r, start_column=8, end_row=r, end_column=9)
    cp = res["completude"]
    _cell(syn, 19, 6, "Linhas de materiais justificadas por uma DAP", bg=ZEBRE)
    _cell(syn, 19, 7, f"{cp['avec_fdes']} / {cp['lignes']}", bold=True, bg=ZEBRE)
    _cell(syn, 19, 8, cp["taux_fdes"], "0%", bold=True, bg=ZEBRE)
    _largeurs(syn, [36, 22, 16, 34, 3, 40, 18, 16, 14])

    # ========================================================================== Contrôles
    _titre(co, "A1", "CONTROLOS — O QUE FALTA E O QUE SAI DOS IMPERATIVOS DA OBRA")
    co.merge_cells("A1:E1")
    _entete(co, 2, ["Nível", "Código", "Constatação", "Ação esperada da empresa", "Separador"])
    for i, c in enumerate(res["controles"]):
        r = 3 + i
        bg = NIV_FILL.get(c["niveau"], "FFFFFF")
        _cell(co, r, 1, NIV_LIB[c["niveau"]], bold=True, bg=bg)
        _cell(co, r, 2, c["code"], bg=bg)
        _cell(co, r, 3, c["message"], bg=bg, wrap=True)
        _cell(co, r, 4, c.get("action") or "", bg=bg, wrap=True)
        _cell(co, r, 5, {"materiau": "Materiais", "charte": "Grelha_Carta", "emissions": "Emissoes_Obra",
                         "projet": "Sintese", "document": "Documentos", "dechets": "Grelha_Carta"}.get(c.get("cible"), ""), bg=bg)
    if not res["controles"]:
        _cell(co, 3, 1, "NENHUM", bold=True, bg=VERT_CLAIR)
        _cell(co, 3, 3, "Todas as informações esperadas estão presentes e dentro dos imperativos da obra.", bg=VERT_CLAIR)
    _largeurs(co, [18, 9, 80, 60, 26])
    co.freeze_panes = "A3"

    # ========================================================================== Pièces
    _titre(pj, "A1", "DOCUMENTOS JUSTIFICATIVOS DEPOSITADOS (DAP, FICHAS TÉCNICAS, GUIAS DE REMESSA, e-GAR, FATURAS)")
    pj.merge_cells("A1:G1")
    _entete(pj, 2, ["Ficheiro", "Tipo reconhecido", "Estado", "Leitura", "Valores extraídos", "Associado a", "Observações"])
    ids = {m["id"]: m.get("famille") for m in res["materiaux"]}
    for i, d_ in enumerate(res.get("documents") or []):
        r = 3 + i
        ex = d_.get("extrait") or {}
        vals = []
        for k, lib in (("fe_fdes", "FE"), ("fdes_unite", "UF"), ("ref_fdes", "registo"), ("fdes_validite", "validade"), ("numero", "n.º"),
                       ("origine", "carga"), ("distance_km", "km")):
            if ex.get(k) not in (None, ""):
                vals.append(f"{lib} {ex[k]}")
        for q in ex.get("quantites") or []:
            vals.append(f"{q.get('quantite')} {q.get('unite')} {q.get('designation', '')[:40]}")
        if ex.get("dechets"):
            vals.append(f"resíduos {ex['dechets'].get('total_t')} t (valorizados {ex['dechets'].get('valorise_t')} t)")
        if ex.get("carburant"):
            vals.append(f"Gasóleo {ex['carburant'].get('gnr_l')} L / HVO {ex['carburant'].get('hvo_l')} L")
        _cell(pj, r, 1, d_.get("nom"), wrap=True)
        _cell(pj, r, 2, d_.get("type_libelle") or d_.get("type"))
        _cell(pj, r, 3, d_.get("statut"), bg=ROUGE if d_.get("statut") in ("ilegivel", "duplicado") else None)
        _cell(pj, r, 4, ex.get("lecture", ""))
        _cell(pj, r, 5, " ; ".join(map(str, vals))[:900], wrap=True)
        _cell(pj, r, 6, ids.get(d_.get("rattache_a"), d_.get("rattache_a") or "NÃO ASSOCIADO"), bg=None if d_.get("rattache_a") else JAUNE)
        _cell(pj, r, 7, " | ".join(d_.get("notes") or [])[:600], wrap=True)
    if not res.get("documents"):
        _cell(pj, 3, 1, "Nenhum documento depositado : deposite as DAP, fichas técnicas e guias de remessa no ConstruPilot (Obra › Baixo carbono).", wrap=True)
        pj.merge_cells("A3:G3")
    _largeurs(pj, [34, 26, 11, 13, 60, 30, 50])

    # ========================================================================== Méthode
    _titre(me, "A1", "MÉTODO, FONTES E LIMITES")
    lignes = [
        ("Meta de carbono", f"{R.SOURCE_RE2020}. Sem meta introduzida, o estado fica « dados em falta »."),
        ("Fatores de referência", f"{R.SOURCE_TABLEAU} — a substituir pelos dados genéricos / DAP do projeto se o dono de obra o exigir."),
        ("Eletricidade", R.SOURCE_ELEC + "."),
        ("Rácio do quadro", "Indicador de PILOTAGEM da obra (soma estática quantidade × FE / área). O PAG do ciclo de vida da Diretiva (UE) 2024/1275 é uma ACV completa feita com software próprio : não confundir."),
        ("DAP lidas", "Indicador « alterações climáticas — total » (GWP-total), ciclo de vida A1 a C4 sem o módulo D. Um valor lido pela IA só é aceite se figurar no documento."),
        ("Guias de remessa", "Quantidades acumuladas por família ; uma guia com o mesmo número e o mesmo fornecedor só conta uma vez. Distância : a escrita na guia, senão em linha reta por geocodificação (a confirmar)."),
        ("KPI calculados", "Parte de baixo carbono / reutilização : parte do peso de carbono de referência das linhas justificadas (DAP ou documento) com tipologia não standard. Máquinas de baixo carbono : parte HVO + elétrica (1 L de gasóleo ≈ 10 kWh) na energia das máquinas."),
        ("Validade DAP", f"{R.FDES_VALIDITE_ANS} anos (EN 15804 / programas DAPHabitat, EPD) ; uma DAP expirada é assinalada."),
        ("Desvio de entrega", f"Alerta se a quantidade entregue se afastar mais de ±{R.ECART_LIVRAISON:.0%} da quantidade prevista na medição."),
        ("Resíduos", "e-GAR (SILiAmb) : operações R (valorização) e D (eliminação) ; PPGRCD nas obras sujeitas."),
    ]
    for i, (a, b) in enumerate(lignes):
        _cell(me, 3 + i, 1, a, bold=True, bg=ZEBRE)
        _cell(me, 3 + i, 2, b, wrap=True)
        me.row_dimensions[3 + i].height = 44
    for j, dline in enumerate(res.get("decisions") or []):
        if j == 0:
            _cell(me, 14, 1, "Decisões registadas", bold=True, bg=VERT_CLAIR)
        _cell(me, 14 + j, 2, dline, wrap=True)
    _largeurs(me, [26, 120])

    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
