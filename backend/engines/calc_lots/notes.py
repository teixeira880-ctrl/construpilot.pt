"""Blocos comuns das notas de cálculo (versão PT): perdas de calor, bomba de calor, eletricidade, canalização / drenagem.
Usados pelas notas de cada motor e pela nota encadeada das especialidades técnicas (vírgula decimal, controlos exigência / valor / resultado)."""
from __future__ import annotations

from reportlab.lib.units import mm

from . import graficos as G
from . import rendu

W = mm


def _f(x, n=0):
    return f"{x:,.{n}f}".replace(",", " ").replace(".", ",") if n else f"{x:,.0f}".replace(",", " ")


def _c(x, n=1):
    return f"{x:.{n}f}".replace(".", ",")


def _g(x):
    return f"{x:g}".replace(".", ",")


def conv(lst):
    """Controlos do motor (exigencia / valor) → formato do gerador de PDF (exigence / valeur)."""
    return [{"ref": c["ref"], "exigence": c.get("exigencia", c.get("exigence", "")), "valeur": c.get("valor", c.get("valeur", "")), "ok": c["ok"],
             "note": c.get("note")} for c in lst or []]


def _nome(x):
    from .aquecimento import NOMES_PT
    return x["nome"] if x["nome"] != x["tipo"] else NOMES_PT.get(x["tipo"], x["tipo"])


def blocos_perdas(a, num="") -> list:
    tot = a["phi_total"] or 1
    reaq = bool(a["phi_RH"])
    rows = [[_nome(x), _g(x["theta_int"]), _c(x["area_m2"]), _f(x["phi_T"]), _f(x["phi_V_ventilacao"]), _f(x["phi_V_infiltracao"])]
            + ([_f(x["phi_RH"])] if reaq else []) + [_f(x["phi"]), _f(x["w_m2"])] for x in a["divisoes"]]
    rows.append(["TOTAL", "", _c(a["area_m2"]), _f(a["phi_T"]), _f(sum(x["phi_V_ventilacao"] for x in a["divisoes"])),
                 _f(sum(x["phi_V_infiltracao"] for x in a["divisoes"]))] + ([_f(a["phi_RH"])] if reaq else []) + [_f(a["phi_total"]), _f(a["w_m2"])])
    head = ["Divisão", "θint °C", "m²", "Φ_T W", "Φ_V vent. W", "Φ_V infilt. W"] + (["Φ_RH W"] if reaq else []) + ["Φ W", "W/m²"]
    wd = [36 * W, 15 * W, 14 * W, 20 * W, 22 * W, 22 * W] + ([18 * W] if reaq else []) + [18 * W, 15 * W]
    vent = [[_nome(x), _c(x["volume_m3"], 0), x["origem_ar"], _f(x["q_ar_m3h"]), _c(x["theta_ar"]) if x["q_ar_m3h"] else "—", _c(x["q_inf_m3h"], 1)]
            for x in a["divisoes"]]
    pt = (f"ΔU forfetário {_c(a['delta_u_pontes'], 2)} W/(m².°C)" if a["delta_u_pontes"] else "sem majoração ΔU") + \
        (f", Σψ·L {_c(a['soma_psi_l'], 2)} W/°C" if a["soma_psi_l"] else "")
    serie = ["Transmissão", "Ventilação", "Infiltrações"] + (["Reaquecimento"] if reaq else [])
    b = [("h2", f"{num}Perdas de calor de projeto (EN 12831-1)"),
         ("p", f"θe = {_g(a['theta_e'])} °C ({a['theta_e_fonte']}). Ventilação {a['ventilacao_nome']}: {_f(a['q_ventilacao_m3h'])} m³/h de ar novo "
               f"({_c(a['q_ventilacao_m3h'] / (a['volume_m3'] or 1), 2)} h⁻¹ sobre {_f(a['volume_m3'])} m³)"
               + (f", recuperação η = {_g(a['recuperacao_calor'])}" if a["recuperacao_calor"] else "")
               + f". Infiltrações: {a['estanquidade']} ({_c(a['n_inf'], 2)} h⁻¹). Pontes térmicas: {pt}. "
               f"Total {_f(a['phi_total'])} W ({_f(a['w_m2'])} W/m² sobre {_f(a['area_m2'])} m²)."),
         ("table", head, rows, wd),
         ("chart", G.empile_h([(_nome(x), [x["phi_T"], x["phi_V_ventilacao"], x["phi_V_infiltracao"]] + ([x["phi_RH"]] if reaq else [])) for x in a["divisoes"]],
                              serie, "Perdas de calor por divisão", "W"),
          f"Total {_f(a['phi_total'])} W — transmissão {100 * a['phi_T'] / tot:.0f} %, ventilação e infiltrações {100 * a['phi_V'] / tot:.0f} %."),
         ("p", "Ar novo por divisão: entra nas divisões principais (exterior ou recuperado) e é transferido para as zonas húmidas, onde é extraído — "
               f"o caudal de extração é contado uma só vez; ar transferido a {_c(a['theta_transferencia'])} °C."),
         ("table", ["Divisão", "Volume m³", "Origem do ar", "q ar m³/h", "θ ar °C", "q infilt. m³/h"], vent, [40 * W, 20 * W, 46 * W, 24 * W, 20 * W, 26 * W])]
    if a.get("controles"):
        b.append(("controls", conv(a["controles"])))
    return b


def blocos_bomba_calor(bc, num="") -> list:
    from .aquecimento import APOIO_PT, EMISSORES_PT, _curva_bc
    v = bc["vaso"]
    rows = [["Perdas a θe", f"{_c(bc['perdas_kw'], 2)} kW (θe {_g(bc['theta_e'])} °C, θint {_g(bc['theta_int'])} °C)"],
            ["Emissores / ida", f"{EMISSORES_PT[bc['emissores']]} — ida {_g(bc['temperatura_ida'])} °C, ΔT {_g(bc['delta_t_k'])} K"],
            ["Bomba de calor (A7/W35)", f"{_g(bc['p_nominal_kw'])} kW nominal → {_c(bc['p_theta_e_kw'], 2)} kW a θe ({bc['cobertura'] * 100:.0f} %; {bc['fonte_potencia']})"],
            ["COP a θe", _c(bc["cop"], 2)],
            ["Ponto de bivalência", f"{_c(bc['bivalencia_c'])} °C" if bc["bivalencia_c"] is not None else "—"],
            ["Apoio", f"{_g(bc['apoio_kw'])} kW ({APOIO_PT[bc['tipo_apoio']]}; fator {_g(bc['fator_apoio'])} × perdas)" if bc["apoio_kw"] else "não necessário"],
            ["Caudal de água", f"{_f(bc['caudal_lh'])} L/h"],
            ["Volume mínimo / instalação", f"{_f(bc['volume_min_l'])} L / {_f(bc['volume_instalacao_l'])} L"],
            ["Depósito de inércia", f"{_g(bc['deposito_inercia_l'])} L" if bc["deposito_inercia_l"] else "não necessário"],
            ["Vaso de expansão (EN 12828)", (f"Vn ≥ {_c(v['vn_min_l'])} L → {v['vaso_l'] or '> 300'} L; p0 {_c(v['p0_bar'])} bar, pe {_c(v['pe_bar'])} bar"
                                                if v["realizavel"] else "tarado da válvula insuficiente")],
            ["SCOP / η_s (projeto)", f"{_c(bc['scop'], 2)} / {bc['eta_s_pct']:.0f} % — classe {bc['classe_erp']}" + (" (indicativo)" if bc["scop_fonte"] == "indicativo" else "")],
            ["Potência absorvida máx.", f"{_c(bc['p_absorvida_kw'], 2)} kW → {_c(bc['corrente_a'])} A ({'monofásica' if bc['alimentacao'] == 'mono' else 'trifásica'})"
                                        + (f"; compressor {bc['disjuntor_compressor_a']} A / {_g(bc['seccao_compressor_mm2'])} mm²" if bc["disjuntor_compressor_a"] else "")]]
    curva, biv = _curva_bc(bc)
    exp = [("Expansão Ve", v["ve_l"]), ("Reserva Vwr", v["vwr_l"]), ("Volume nominal mínimo Vn", v["vn_min_l"] or 0)]
    return [("h2", f"{num}Bomba de calor ar/água"),
            ("table", ["Grandeza", "Valor"], rows, [55 * W, 125 * W]),
            ("chart", curva, "Potência da bomba de calor segundo a temperatura exterior e necessidades do edifício: "
             + ("o cruzamento é o ponto de bivalência; abaixo dele o apoio completa." if biv is not None and biv > bc["theta_e"] + 0.2
                else "a bomba de calor cobre as necessidades até à temperatura de projeto (sem ponto de bivalência acima de θe).")),
            ("chart", G.barres_h(exp, "Vaso de expansão — volumes (EN 12828, anexo D)", "L",
                                 ref=(float(v["vaso_l"]), f"vaso {v['vaso_l']} L") if v.get("vaso_l") else None, dec=1),
             f"Vn = (Ve + Vwr)·(pe + 1)/(pe − p0) com {_f(v['volume_l'])} L de água, expansão {_c(v['expansao_pct'], 2)} % até {_g(v['t_max_c'])} °C."),
            ("controls", conv(bc["controles"])), ("hyp", bc.get("regras") or [])]


def blocos_eletricidade(e, num="") -> list:
    pcs = [[x["divisao"], _c(x["area_m2"]), str(x["tomadas"]), str(x["pontos_luz"]), str(x["estores"] or "—"), _g(x["distancia_m"])] for x in e["pontos"]]
    rows = [[c["nome"], ", ".join(c["divisoes"]) or "—", _g(c["seccao"]) + (f" → {_g(c['seccao_recomendada'])}" if not c["du_ok"] and c.get("seccao_recomendada") else ""),
             str(c["disjuntor"]), str(c["pontos"] or ""), _g(round(c["comprimento_m"], 1)), _c(c["ib_a"]), _c(c["du"], 2),
             f"{c['diferencial']} (D{c.get('diferencial_n', '')})"] for c in e["circuitos"]]
    difs = [[f"D{i}", f"{x['tipo']} 30 mA {x['polos']}", f"{x['calibre']} A", ("individual — " if x["individual"] else "") + ", ".join(x["circuitos"])]
            for i, x in enumerate(e["diferenciais_lista"], 1)]
    ent = e.get("entrada")
    b = [("h2", f"{num}Eletricidade (RTIEBT)"),
         ("p", f"{e['tomadas']} tomadas e {e['pontos_luz']} pontos de luz em {len(e['pontos'])} divisões; {len(e['circuitos'])} circuitos e "
               f"{e['diferenciais']} diferenciais 30 mA."),
         ("table", ["Divisão", "m²", "Tomadas", "Pontos de luz", "Estores", "Distância ao quadro m"], pcs, [52 * W, 18 * W, 20 * W, 26 * W, 20 * W, 36 * W]),
         ("table", ["Circuito", "Divisões", "mm²", "Disj. A", "Pontos", "L m", "Ib A", "ΔU %", "Diferencial"], rows,
          [36 * W, 42 * W, 14 * W, 13 * W, 13 * W, 12 * W, 13 * W, 14 * W, 23 * W]),
         ("chart", G.jauges([(c["nome"], c["du"] / c["du_lim"], f"ΔU {_c(c['du'], 2)} %") for c in e["circuitos"]],
                            "Queda de tensão por circuito / limite (3 % iluminação, 5 % restantes)")),
         ("table", ["Ref.", "Diferencial", "Calibre", "Circuitos protegidos"], difs, [12 * W, 34 * W, 18 * W, 116 * W]),
         ("p", f"Potência estimada {_f(e['potencia_estimada_w'])} W → contratar {_g(e['potencia_contratada_kva'])} kVA ({e['alimentacao']}, "
               f"{_c(e['corrente_contrato_a'])} A; mínimo {_g(e['potencia_minima_kva'])} kVA pelo número de compartimentos)."
               + (f" Entrada {_g(ent['seccao_mm2'])} mm² em {_g(ent['comprimento_m'])} m: queda de tensão {_c(ent['du'], 2)} %." if ent else "")),
         ("controls", conv(e["controles"])), ("hyp", e["regras"])]
    return b


def blocos_canalizacao(k, num="") -> list:
    from .instalacoes import DISP_PT
    b = [("h2", f"{num}Abastecimento de água e drenagem (DR 23/95)"),
         ("p", f"Qa {_c(k['qa_l_s'], 2)} L/s → Qc {_c(k['qc_l_s'], 2)} L/s, ramal geral água fria {k['tubo_af']} ({_c(k['velocidade_m_s'], 2)} m/s), água quente "
               f"{k['tubo_aq'] or '—'} (Qc {_c(k['qc_aq_l_s'], 2)} L/s), pressão no dispositivo mais desfavorável {k['pressao_kpa']:.0f} kPa. Drenagem: "
               f"{k['drenagem_qa_l_min']:.0f} L/min acumulados → Qc {k['drenagem_qc_l_min']:.0f} L/min, tubo de queda Ø{k['tubo_queda_mm']}, coletor Ø{k['coletor_mm']}."),
         ("table", ["Dispositivo", "Nº", "L/s", "AQ", "Descarga L/min", "Ramal Ø"],
          [[DISP_PT.get(x["dispositivo"], x["dispositivo"]), str(x["n"]), _c(x["q"], 2), "sim" if x["aq"] else "não", str(x["descarga_l_min"]), str(x["ramal_descarga"] or "—")]
           for x in k["dispositivos"]], [50 * W, 14 * W, 18 * W, 14 * W, 30 * W, 22 * W]),
         ("chart", G.barres_h([(f"{DISP_PT.get(x['dispositivo'], x['dispositivo'])} × {x['n']}", x["q"] * x["n"]) for x in k["dispositivos"]],
                              "Caudais instantâneos acumulados por dispositivo", "L/s", ref=(k["qc_l_s"], f"Qc {_c(k['qc_l_s'], 2)} L/s"), dec=2),
          "O caudal de cálculo Qc (simultaneidade, Anexo V) dimensiona o ramal geral, abaixo da soma dos caudais instantâneos."
          if k["qc_l_s"] < k["qa_l_s"] - 1e-6 else "Até Qa = 0,5 L/s o caudal de cálculo é igual à soma dos caudais instantâneos (Anexo V).")]
    rd = k.get("rede")
    if rd:
        rows = [[r["nome"], r["montante"] or "origem", "AQ" if r["agua"] == "quente" else "AF", _g(r["comprimento_m"]), _c(r["qa_l_s"], 2), _c(r["qc_l_s"], 2),
                 f"Ø{r['dn']}", _c(r["velocidade_m_s"], 2), _c(r["perda_kpa"]), _g(r["desnivel_m"]), f"{r['p_fim_kpa']:.0f}"] for r in rd["trocos"]]
        b += [("p", f"Rede de abastecimento troço a troço — dispositivo mais desfavorável no fim do troço «{rd['ponto_desfavoravel']}» "
                    f"({rd['pressao_min_kpa']:.0f} kPa)."),
              ("table", ["Troço", "Montante", "Água", "L m", "Qa L/s", "Qc L/s", "Ø", "v m/s", "ΔH kPa", "Δz m", "P fim kPa"], rows,
               [28 * W, 28 * W, 11 * W, 10 * W, 14 * W, 14 * W, 12 * W, 13 * W, 15 * W, 11 * W, 16 * W]),
              ("chart", G.barres_h([(r["nome"], r["p_fim_kpa"], G.SERIES[0] if r["p_fim_kpa"] >= 150 else (G.SERIES[3] if r["p_fim_kpa"] >= 50 else G.SERIES[7]))
                                    for r in rd["trocos"]], "Pressão no fim de cada troço", "kPa", ref=(50.0, "mínimo 50 kPa"), dec=0),
               "Pressão residual ao longo da rede: azul ≥ 150 kPa (conforto), amarelo entre 50 e 150 kPa, vermelho abaixo do mínimo.")]
    dr = k.get("rede_drenagem")
    if dr:
        rows = [[r["nome"], r["jusante"] or "saída", {"ramal": "ramal", "tubo_queda": "tubo de queda", "coletor": "coletor"}[r["tipo"]], _g(r["comprimento_m"]),
                 _g(r["inclinacao_pct"]) if r["inclinacao_pct"] is not None else "—", f"{r['qa_l_min']:.0f}", f"{r['qc_l_min']:.0f}", f"Ø{r['dn']}",
                 f"{r['capacidade_l_min']:.0f}"] for r in dr["trocos"]]
        b += [("p", "Rede de drenagem troço a troço (de montante para jusante)."),
              ("table", ["Troço", "Jusante", "Tipo", "L m", "i %", "Qa L/min", "Qc L/min", "Ø PVC", "Capacidade L/min"], rows,
               [24 * W, 24 * W, 24 * W, 12 * W, 12 * W, 18 * W, 18 * W, 16 * W, 32 * W]),
              ("chart", G.jauges([(r["nome"], r["qc_l_min"] / r["capacidade_l_min"] if r["capacidade_l_min"] else None, f"Ø{r['dn']}") for r in dr["trocos"]],
                                 "Drenagem — Qc / capacidade de cada troço"))]
    b += [("controls", conv(k["controles"])), ("hyp", k["regras"])]
    return b


def pdf(titre, sous_titre, blocs, hypotheses) -> tuple[bytes, bytes]:
    b = list(blocs) + [("h2", "Hipóteses / a validar"), ("hyp", hypotheses or ["nenhuma"])]
    data = rendu.build_pdf(titre, sous_titre, b)
    return data, rendu.first_page_png(data)
