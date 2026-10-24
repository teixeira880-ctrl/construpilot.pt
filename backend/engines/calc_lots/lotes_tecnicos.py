"""Especialidades técnicas de uma habitação encadeadas (Portugal) — uma só entrada, uma só nota de cálculo.

Cadeia: isolamento das paredes (U corrigido, Umáx REH) → perdas de calor divisão a divisão (EN 12831-1) → piso radiante (NP EN 1264)
→ bomba de calor ar/água (temperatura de ida e volume de água do piso radiante) → eletricidade (RTIEBT, com o circuito da bomba de
calor) → canalização e drenagem (DR 23/95, dispositivos deduzidos das divisões se não indicados) → solar térmico (opcional).
Cada etapa reutiliza o resultado da anterior; os valores por defeito são assinalados nas hipóteses. Pré-dimensionamento indicativo.
"""
from __future__ import annotations

from . import aquecimento, instalacoes, isolamento, piso_radiante, solar_termico

U_DEFEITO = {"nova": {"parede": 0.40, "envidracado": 1.9, "porta": 2.0, "pavimento": 0.35, "cobertura": 0.30},
             "renovacao": {"parede": 0.60, "envidracado": 2.4, "porta": 2.5, "pavimento": 0.50, "cobertura": 0.45}}
DISPOSITIVOS_DIVISAO = {"cozinha": ["lava_loica", "maquina_lavar_loica"], "casa_de_banho": ["lavatorio", "autoclismo", "chuveiro"],
                        "lavandaria": ["maquina_lavar_roupa", "tanque"]}
LOTES = ("isolamento", "aquecimento", "piso_radiante", "bomba_calor", "eletricidade", "canalizacao", "solar_termico")


def calcular(params: dict, lotes=LOTES) -> dict:
    p = dict(params or {})
    obra = p.get("obra") or "renovacao"
    if obra not in U_DEFEITO:
        obra = "renovacao"
    hyp: list[str] = []
    res: dict = {}
    div = p.get("divisoes") or []
    if not div:
        raise ValueError("indicar as divisões (tipo, área e paredes) — necessárias às perdas de calor e à eletricidade")
    loc = {k: p.get(k) for k in ("concelho", "nuts", "altitude_m")}
    # 1. isolamento das paredes exteriores
    u_par = None
    if "isolamento" in lotes and p.get("isolamento_paredes"):
        iso = isolamento.calcular({**loc, **p["isolamento_paredes"]})
        res["isolamento"] = iso
        u_par = iso["U"]
    # 2. perdas de calor
    usados = set()
    div_aq = []
    for d in div:
        paredes = []
        for w in d.get("paredes") or []:
            t = w.get("tipo") or "parede"
            U = w.get("U")
            lado = w.get("lado") or "exterior"
            if U is None:
                if t == "parede" and u_par and lado == "exterior":
                    U = u_par
                else:
                    U = U_DEFEITO[obra].get(t, 0.5)
                    usados.add(t)
            paredes.append({"area_m2": float(w["area_m2"]), "U": float(U), "lado": lado, "b": w.get("b")})
        div_aq.append({**{k: d.get(k) for k in ("nome", "tipo", "area_m2", "pe_direito_m", "theta_int", "pontes")}, "paredes": paredes})
    if not any(w for d in div_aq for w in d["paredes"]) and not all(d.get("phi_w") for d in div):
        hyp.append("nenhuma parede / envidraçado descrito: perdas por transmissão nulas — indicar as paredes ou as perdas de calor (phi_w) por divisão")
    if usados:
        hyp.append(f"U por defeito ({'construção nova' if obra == 'nova' else 'renovação'}) para: "
                   + ", ".join(f"{t} {U_DEFEITO[obra][t]:g}" for t in sorted(usados)) + " W/(m².°C)")
    per = None
    if any(k in lotes for k in ("aquecimento", "piso_radiante", "bomba_calor")):
        te = p.get("theta_e")
        if te is None and not (p.get("concelho") or p.get("nuts")):
            te = 0.0
            hyp.append("concelho não indicado: temperatura exterior de projeto θe = 0 °C por defeito (indicar o concelho para o clima REH)")
        per = aquecimento.perdas({**loc, "theta_e": te, "divisoes": div_aq, "estanquidade": p.get("estanquidade"),
                                  "recuperacao_calor": p.get("recuperacao_calor"), "rph_min": p.get("rph_min")})
        dadas = [(i, float(d["phi_w"])) for i, d in enumerate(div) if d.get("phi_w")]
        if dadas:                                           # perdas indicadas pelo utilizador / pelo projeto térmico: prevalecem sobre o cálculo
            for i, phi in dadas:
                r = per["divisoes"][i]
                r.update(phi_T=phi, phi_V=0.0, phi_RH=0.0, phi=phi, w_m2=phi / r["area_m2"] if r["area_m2"] else 0.0)
            tot = sum(r["phi"] for r in per["divisoes"])
            per.update(phi_T=sum(r["phi_T"] for r in per["divisoes"]), phi_V=sum(r["phi_V"] for r in per["divisoes"]), phi_RH=0.0,
                       phi_total=tot, w_m2=tot / per["area_m2"] if per["area_m2"] else 0.0)
            hyp.append("perdas de calor indicadas para " + ", ".join(per["divisoes"][i]["nome"] for i, _ in dadas)
                       + ": usadas tal como dadas (não recalculadas)")
        res["aquecimento"] = per
    em = p.get("emissores") or "piso_radiante"
    # 3. piso radiante
    tv = None
    if per and "piso_radiante" in lotes and em == "piso_radiante":
        pr = piso_radiante.calcular({"divisoes": [{"nome": r["nome"], "tipo": r["tipo"], "area_m2": r["area_m2"], "phi_w": r["phi"], "theta_int": r["theta_int"],
                                                   "revestimento": src.get("revestimento"), "local_inferior": src.get("local_inferior"),
                                                   "r_isolante": src.get("r_isolante_piso"), "comprimento_m": src.get("comprimento_m"),
                                                   "largura_m": src.get("largura_m")}
                                                  for r, src in zip(per["divisoes"], div)], "ida_max": p.get("ida_max")})
        res["piso_radiante"] = pr
        tv = round(pr["theta_ida"] * 2) / 2
    # 4. bomba de calor
    if per and "bomba_calor" in lotes and (p.get("gerador") or "bomba_calor") == "bomba_calor":
        bcp = dict(p.get("bomba_calor") or {})
        bcp.setdefault("emissores", em if em in aquecimento.EMISSORES else "piso_radiante")
        if "piso_radiante" in res and bcp.get("volume_instalacao_l") is None:
            bcp["volume_instalacao_l"] = res["piso_radiante"]["volume_agua_l"] + 20
        bc = aquecimento.bomba_calor(per["phi_total"], per["theta_e"], bcp)
        if tv is not None:
            bc["temperatura_ida"] = tv
            bc["hipoteses"].append(f"temperatura de ida do piso radiante {tv:g} °C (o COP indicativo foi estimado para a ida de referência dos emissores)")
        res["bomba_calor"] = bc
    # 5. eletricidade
    if "eletricidade" in lotes:
        eq = dict(p.get("equipamentos") or {})
        if "bomba_calor" in res and not eq.get("bomba_calor_kw"):
            eq["bomba_calor_kw"] = round(res["bomba_calor"]["p_absorvida_kw"], 1)
        res["eletricidade"] = instalacoes.eletricidade({"divisoes": [{"nome": d.get("nome"), "tipo": d.get("tipo"), "area_m2": d.get("area_m2")} for d in div],
                                                        "equipamentos": eq, "comprimento_medio_circuito_m": p.get("comprimento_medio_circuito_m"),
                                                        "resistencia_terra_ohm": p.get("resistencia_terra_ohm")})
    # 6. canalização
    if "canalizacao" in lotes:
        disp = p.get("dispositivos")
        if not disp:
            cnt: dict = {}
            for d in div:
                for a in DISPOSITIVOS_DIVISAO.get(d.get("tipo"), []):
                    cnt[a] = cnt.get(a, 0) + 1
            if not any(d.get("tipo") == "lavandaria" for d in div):
                cnt["maquina_lavar_roupa"] = cnt.get("maquina_lavar_roupa", 0) + 1
            disp = [{"tipo": k, "quantidade": v} for k, v in cnt.items()]
            hyp.append("dispositivos sanitários deduzidos das divisões (cozinha: lava-loiça + máquina de loiça; casa de banho: lavatório, "
                       "autoclismo, chuveiro; lavandaria: máquina de roupa + tanque)")
        if disp:
            res["canalizacao"] = instalacoes.canalizacao({"dispositivos": disp, "pressao_rede_kpa": p.get("pressao_rede_kpa"),
                                                          "comprimento_m": p.get("comprimento_alimentacao_m"), "desnivel_m": p.get("desnivel_m")})
    # 7. solar térmico
    if "solar_termico" in lotes and p.get("solar_termico") is not None:
        st = dict(p.get("solar_termico") or {})
        if st.get("tipologia") is None and st.get("ocupantes") is None:
            st["tipologia"] = p.get("tipologia") if p.get("tipologia") is not None else max(0, sum(1 for d in div if d.get("tipo") == "quarto"))
        st.setdefault("tipo_habitacao", p.get("tipo_habitacao"))
        res["solar_termico"] = solar_termico.calcular(st)
    for k in LOTES:
        if k in res:
            hyp += [f"[{k}] {h}" for h in res[k].get("hipoteses", [])]
    res["hipoteses"] = hyp
    return res


def _c(x, n=None) -> str:
    return (f"{x:.{n}f}" if n is not None else f"{x:g}").replace(".", ",")


def _conv(lst):
    return [{"ref": c["ref"], "exigence": c["exigencia"], "valeur": c["valor"], "ok": c["ok"], "note": c.get("note")} for c in lst]


def note(params: dict, lotes=LOTES) -> dict:
    from . import notes
    W, f = notes.W, notes._f
    r = calcular(params, lotes)
    blocs = [("p", "Pré-dimensionamento indicativo encadeado — não substitui os projetos de especialidade (AVAC, eletricidade, águas e esgotos) "
                   "nem o pré-certificado SCE.")]
    kp = []
    n = 1
    if "isolamento" in r:
        iso = r["isolamento"]
        blocs += [("h2", f"{n}. Isolamento das paredes — {iso['sistema_nome']}"),
                  ("p", f"R parede {_c(iso['R_parede'], 2)} m².°C/W, U = {_c(iso['U'], 3)} W/(m².°C) (Umáx {_c(iso['umax'])})."),
                  ("controls", _conv(iso.get("controles") or []))]
        kp.append({"label": "U parede isolada", "value": f"{iso['U']:.3f}".replace(".", ","), "unit": "W/m².°C"})
        n += 1
    if "aquecimento" in r:
        a = r["aquecimento"]
        blocs += [("h2", f"{n}. Perdas de calor de projeto (EN 12831-1)"),
                  ("p", f"θe = {a['theta_e']:g} °C ({a['theta_e_fonte']}); ventilação {a['q_ventilacao_m3h']:.0f} m³/h; total {f(a['phi_total'])} W "
                        f"({a['w_m2']:.0f} W/m² sobre {a['area_m2']:.0f} m²)."),
                  ("table", ["Divisão", "θint °C", "m²", "Φ_T W", "Φ_V W", "Φ W", "W/m²"],
                   [[x["nome"], f"{x['theta_int']:g}", f"{x['area_m2']:.1f}", f"{x['phi_T']:.0f}", f"{x['phi_V']:.0f}", f"{x['phi']:.0f}", f"{x['w_m2']:.0f}"]
                    for x in a["divisoes"]], [45 * W, 18 * W, 15 * W, 20 * W, 20 * W, 20 * W, 18 * W])]
        kp += [{"label": f"Perdas a θe {a['theta_e']:g} °C".replace(".", ","), "value": f"{a['phi_total'] / 1000:.2f}".replace(".", ","), "unit": "kW"},
               {"label": "Perdas por m²", "value": f"{a['w_m2']:.0f}", "unit": "W/m²"}]
        n += 1
    if "piso_radiante" in r:
        blocs += piso_radiante.blocos(r["piso_radiante"], f"{n}. ")
        kp.append({"label": "Piso radiante", "value": str(r["piso_radiante"]["circuitos"]), "unit": "circuitos"})
        n += 1
    if "bomba_calor" in r:
        bc = r["bomba_calor"]
        blocs += [("h2", f"{n}. Bomba de calor ar/água"),
                  ("p", f"Nominal {bc['p_nominal_kw']:g} kW (A7/W35) → {bc['p_theta_e_kw']:.1f} kW a θe ({bc['cobertura'] * 100:.0f} %), apoio {bc['apoio_kw']:g} kW, "
                        f"COP {bc['cop']:.2f}, ida {bc['temperatura_ida']:g} °C, volume de água {bc['volume_instalacao_l']:.0f} L, {bc['p_absorvida_kw']:.1f} kW absorvidos."),
                  ("controls", _conv(bc["controles"]))]
        kp.append({"label": "Bomba de calor (A7/W35)", "value": f"{bc['p_nominal_kw']:g}".replace(".", ","), "unit": "kW",
                   "ok": all(c["ok"] is not False for c in bc["controles"])})
        n += 1
    if "eletricidade" in r:
        e = r["eletricidade"]
        blocs += [("h2", f"{n}. Eletricidade (RTIEBT)"),
                  ("table", ["Circuito", "mm²", "Disjuntor A", "Pontos", "Diferencial", "ΔU %"],
                   [[c["nome"], f"{c['seccao']:g}", f"{c['disjuntor']}", str(c["pontos"] or ""), c["diferencial"], f"{c['du']:.2f}"] for c in e["circuitos"]],
                   [55 * W, 15 * W, 22 * W, 16 * W, 22 * W, 16 * W]),
                  ("p", f"{e['tomadas']} tomadas, {e['pontos_luz']} pontos de luz; potência estimada {f(e['potencia_estimada_w'])} W → contratar "
                        f"{e['potencia_contratada_kva']:g} kVA ({e['alimentacao']})."),
                  ("controls", _conv(e["controles"]))]
        kp.append({"label": "Potência a contratar", "value": f"{e['potencia_contratada_kva']:g}".replace(".", ","), "unit": "kVA"})
        n += 1
    if "canalizacao" in r:
        k = r["canalizacao"]
        blocs += [("h2", f"{n}. Abastecimento de água e drenagem (DR 23/95)"),
                  ("p", f"Qa {k['qa_l_s']:.2f} L/s → Qc {k['qc_l_s']:.2f} L/s, ramal água fria {k['tubo_af']} ({k['velocidade_m_s']:.2f} m/s), água quente "
                        f"{k['tubo_aq'] or '—'}, pressão {k['pressao_kpa']:.0f} kPa; drenagem {k['drenagem_qc_l_min']:.0f} L/min, tubo de queda Ø{k['tubo_queda_mm']}, "
                        f"coletor Ø{k['coletor_mm']}."),
                  ("controls", _conv(k["controles"]))]
        kp.append({"label": "Caudal de cálculo", "value": f"{k['qc_l_s']:.2f}".replace(".", ","), "unit": "L/s"})
        n += 1
    if "solar_termico" in r:
        s = r["solar_termico"]
        d = s["dimensionamento"]
        txt = (f"{d['ocupantes']} ocupantes, Qa {f(d['Qa_kwh'])} kWh/ano, área sugerida {d['area_sugerida_m2']:.1f} m²".replace(".", ",") if d else "")
        if d.get("fracao_solar") is not None:
            txt += f", fração solar estimada {d['fracao_solar'] * 100:.0f} %"
        blocs += [("h2", f"{n}. Solar térmico"), ("p", (txt + ".") if txt else "Dados de AQS em falta."), ("controls", _conv(s["controles"]))]
        n += 1
    titre = "Nota de cálculo — especialidades técnicas da habitação"
    a = r.get("aquecimento")
    sous = (("Construção nova" if (params.get("obra") or "renovacao") == "nova" else "Renovação") + " · "
            + (params.get("concelho") or "concelho não indicado")
            + (f" · θe {a['theta_e']:g} °C · perdas {a['phi_total'] / 1000:.2f} kW".replace(".", ",") if a else ""))
    pdf, png = notes.pdf(titre, sous, [("kpis", kp[:8])] + blocs, r["hipoteses"])
    return {**r, "titre": titre, "sous_titre": sous, "pdf": pdf, "png": png}
