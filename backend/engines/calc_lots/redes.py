"""Águas pluviais, fossa séptica / infiltração e ventilação — pré-dimensionamento indicativo (Portugal).

Águas pluviais prediais (Decreto Regulamentar 23/95, RGSPPDADAR): curvas IDF I = a·t^b (regiões A, B, C; B = 0,8·A, C = 1,2·A),
período de retorno 5 anos e duração 5 min por defeito, C = 1 em coberturas; caleiras por Manning-Strickler (altura de água ≤ 7/10,
inclinação ≥ 0,5 %); tubos de queda por descarregador circular (α = 0,453 aresta viva, H = carga à entrada), Ø ≥ 50 mm;
coletores prediais Ø ≥ 100 mm com 0,5–4 %.
Fossa séptica (guia técnico ERSAR): volume útil = volume líquido (tr 3 dias) + lamas digeridas + lamas em digestão; infiltração em
trincheiras por taxa de aplicação conforme o solo (valores por defeito do tipo US EPA, a confirmar pelo regulamento municipal).
Ventilação (Portaria 138-I/2021, NP 1037-1): Rph ≥ 0,5 h⁻¹; admissão ≈ 1 renovação/h nos compartimentos principais, extração ≈ 4/h
na cozinha e instalações sanitárias; grelhas autorreguláveis ≥ 25 m³/h a 2 Pa.
Valores não confirmados no texto oficial assinalados nas hipóteses; regulamentos municipais prevalecem.
"""
from __future__ import annotations

import math

IDF_A = {2: (202.72, -0.577), 5: (259.26, -0.562), 10: (290.68, -0.549), 20: (317.74, -0.538), 50: (349.54, -0.524), 100: (365.62, -0.508)}
REGIAO = {"A": 1.0, "B": 0.8, "C": 1.2}
DIAM_PVC = [50, 63, 75, 90, 110, 125, 140, 160, 200]                      # Ø nominal PVC
DI_PVC = {50: 46.4, 63: 59.0, 75: 70.6, 90: 85.6, 110: 104.6, 125: 118.6, 140: 133.0, 160: 152.0, 200: 190.2}   # Ø interior (mm)
CALEIRAS = [("meia-cana 100", 100), ("meia-cana 125", 125), ("meia-cana 150", 150), ("meia-cana 200", 200), ("retangular 150×100", None),
            ("retangular 200×120", None), ("retangular 250×150", None)]


def intensidade(regiao: str = "A", T: int = 5, t_min: float = 5.0) -> float:
    """mm/h"""
    a, b = IDF_A[T]
    return a * REGIAO[regiao] * t_min ** b


def _q_meia_cana(D_mm: float, i: float, ks: float, enchimento: float = 0.7) -> float:
    """Caudal (L/s) de uma caleira semicircular com altura de água = enchimento × raio (Manning-Strickler)."""
    r = D_mm / 2000
    h = enchimento * r
    th = 2 * math.acos((r - h) / r)
    A = r * r * (th - math.sin(th)) / 2
    P = r * th
    return ks * A * (A / P) ** (2 / 3) * math.sqrt(i) * 1000


def _q_retangular(b_mm: float, h_mm: float, i: float, ks: float, enchimento: float = 0.7) -> float:
    b, h = b_mm / 1000, enchimento * h_mm / 1000
    A, P = b * h, b + 2 * h
    return ks * A * (A / P) ** (2 / 3) * math.sqrt(i) * 1000


def _q_tubo_queda(D_mm: float, H_m: float = 0.025, alfa: float = 0.453) -> float:
    """Descarregador circular à entrada do tubo de queda: Q = α·π·D·H·√(2gH) (L/s)."""
    return alfa * math.pi * D_mm / 1000 * H_m * math.sqrt(2 * 9.81 * H_m) * 1000


def aguas_pluviais(p: dict) -> dict:
    reg = (p.get("regiao") or "A").upper()
    if reg not in REGIAO:
        raise ValueError("região pluviométrica: A, B ou C (Anexo IX do DR 23/95)")
    T = int(p.get("periodo_retorno") or 5)
    if T not in IDF_A:
        raise ValueError("período de retorno: 2, 5, 10, 20, 50 ou 100 anos")
    t = float(p.get("duracao_min") or 5)
    I = intensidade(reg, T, t)
    ks = float(p.get("ks") or 120)
    hyp = [f"precipitação: região {reg}, T = {T} anos, duração {t:g} min → I = {I:.0f} mm/h ({I / 3600:.4f} L/s/m²), C = 1 (cobertura)",
           "região pluviométrica a confirmar no mapa do Anexo IX (C: zonas acima de 700 m e Madeira)" if not p.get("regiao") else "região indicada pelo utilizador",
           f"caleiras: Manning-Strickler, Ks = {ks:g}, altura de água ≤ 7/10; tubos de queda: descarregador α = 0,453, carga 25 mm (a confirmar no DR 23/95)"]
    rows, ctl = [], []
    for k, v in enumerate(p.get("vertentes") or [], 1):
        A = float(v.get("area_planta_m2") or 0)
        if A <= 0:
            raise ValueError(f"vertente {k}: área em planta > 0")
        Q = I / 3600 * A * float(v.get("coef_escoamento") or 1.0)
        inc = float(v["inclinacao_pct"]) if v.get("inclinacao_pct") is not None else 0.5
        i = max(0.001, inc / 100)
        L = float(v.get("comprimento_caleira_m") or math.sqrt(A) * 1.5)
        n = max(1, math.ceil(L / 20)) if not v.get("tubos_queda") else int(v["tubos_queda"])
        q_tq = Q / n
        cal = None
        for nome, D in CALEIRAS:
            if D:
                cap = _q_meia_cana(D, i, ks)
            else:
                b, h = (float(x) for x in nome.split()[1].split("×"))
                cap = _q_retangular(b, h, i, ks)
            if cap >= q_tq / (2 if v.get("descarga_central") else 1):
                cal = (nome, cap)
                break
        if cal is None:
            raise ValueError(f"vertente {k}: caudal elevado — aumentar o número de tubos de queda ou prever algeroz dimensionado")
        dtq = next((d for d in DIAM_PVC if _q_tubo_queda(DI_PVC[d]) >= q_tq), None)
        if dtq is None:
            n = math.ceil(Q / _q_tubo_queda(DI_PVC[200]))
            dtq = 200
            q_tq = Q / n
        dtq = max(dtq, int(v.get("diametro_min") or 75))
        rows.append({"vertente": v.get("nome") or f"vertente {k}", "A": A, "Q": Q, "caleira": cal[0], "cap_caleira": cal[1], "tubos_queda": n, "phi": dtq,
                     "ocupacao_caleira": q_tq / (2 if v.get("descarga_central") else 1) / cal[1] if cal[1] else None})
        ctl.append({"ref": f"{v.get('nome') or f'Vertente {k}'} — caleira", "exigencia": f"Q ≥ {q_tq:.2f} L/s com i ≥ 0,5 %", "valor": f"{cal[0]}: {cal[1]:.2f} L/s (i {inc:g} %)",
                    "ok": inc >= 0.5 and cal[1] >= q_tq / (2 if v.get("descarga_central") else 1) - 1e-9})
        ctl.append({"ref": f"{v.get('nome') or f'Vertente {k}'} — tubos de queda", "exigencia": "Ø ≥ 50 mm, capacidade ≥ caudal por tubo", "valor": f"{n} × Ø{dtq} ({q_tq:.2f} L/s cada)",
                    "ok": _q_tubo_queda(DI_PVC[dtq]) >= q_tq - 1e-9})
    Qt = sum(r["Q"] for r in rows)
    col = None
    if rows:
        ic = float(p["inclinacao_coletor_pct"]) if p.get("inclinacao_coletor_pct") is not None else 1.0
        i_col = max(0.001, ic / 100)
        cap = lambda d: ks * math.pi * (DI_PVC[d] / 1000) ** 2 / 4 * (DI_PVC[d] / 4000) ** (2 / 3) * math.sqrt(i_col) * 1000
        col = next((d for d in DIAM_PVC[4:] if cap(d) >= Qt), None)
        cap_col = cap(col) if col else cap(200)
        ctl.append({"ref": "Coletor predial de águas pluviais", "exigencia": "Ø ≥ 100 mm, inclinação 0,5 a 4 %, secção cheia", "valor": (f"Ø{col} a {ic:g} % para {Qt:.2f} L/s" if col else f"Ø200 insuficiente ({cap_col:.1f} L/s < {Qt:.2f} L/s): dividir em vários coletores ou aumentar a inclinação"),
                    "ok": col is not None and 0.5 <= ic <= 4})
    return {"intensidade_mm_h": I, "vertentes": rows, "coletor": col, "caudal_total_l_s": Qt, "controles": ctl, "hipoteses": hyp}


TAXA_SOLO = {"areia_grossa": 45.0, "areia_fina": 30.0, "franco_limoso": 17.0, "argiloso": 0.0}


def fossa_septica(p: dict) -> dict:
    tip = p.get("tipologia")
    pop = int(p.get("habitantes") or ((int(tip) + 1) if tip is not None else 4))
    cap = float(p.get("capitacao_l_hab_dia") or 150)
    faf = float(p.get("fator_afluencia") or 0.8)
    tr = float(p.get("tempo_retencao_dias") or 3)
    tl = float(p.get("intervalo_limpeza_dias") or 730)
    q = pop * cap * faf / 1000                     # m³/dia
    v_liq = q * tr
    v_lm = pop * 0.11 * (tl - 60) / 1000
    v_ld = pop * (0.45 + 0.11) / 2 * 60 / 1000
    V = max(2.0, v_liq + v_lm + v_ld)
    hyp = [f"{pop} habitantes ({'T%s → n + 1' % tip if tip is not None and not p.get('habitantes') else 'indicado'}), capitação {cap:g} L/hab.dia, fator de afluência {faf:g}",
           f"volume útil = líquido (tr {tr:g} dias) + lamas digeridas (0,11 L/hab.dia, limpeza a cada {tl:g} dias) + lamas em digestão (60 dias) — guia técnico ERSAR",
           "a destinação final e as distâncias dependem do regulamento municipal / entidade gestora (licença da APA para rejeição)"]
    ctl = []
    solo = p.get("solo")
    dest = {}
    if solo:
        if solo not in TAXA_SOLO:
            raise ValueError(f"solo desconhecido {solo!r} ({', '.join(TAXA_SOLO)})")
        taxa = TAXA_SOLO[solo]
        if taxa <= 0:
            dest = {"solucao": "fossa estanque (vazamento periódico) ou filtro de areia drenado", "motivo": "solo pouco permeável"}
        elif p.get("nivel_freatico_m") is not None and float(p["nivel_freatico_m"]) < 2:
            dest = {"solucao": "aterro filtrante", "motivo": "nível freático a menos de 2 m"}
        elif p.get("nivel_freatico_m") is not None and float(p["nivel_freatico_m"]) < 3:
            dest = {"solucao": "aterro filtrante ou filtro de areia", "motivo": "nível freático a menos de 3 m (trincheiras desaconselhadas)"}
        else:
            area = q * 1000 / taxa
            larg = 0.6
            comp = area / larg
            n = math.ceil(comp / 20)
            dest = {"solucao": "trincheiras de infiltração", "area_fundo_m2": area, "comprimento_total_m": comp, "n_trincheiras": n, "largura_m": larg,
                    "taxa_l_m2_dia": taxa}
            hyp.append(f"taxa de aplicação {taxa:g} L/m².dia ({solo}) — valor por defeito, a substituir pelos Quadros 4.12/4.13 do guia ERSAR ou ensaio de percolação")
    for ref, key, lim in (("Distância a poço / captação", "distancia_poco_m", 30), ("Distância à habitação", "distancia_habitacao_m", 3)):
        v = p.get(key)
        ctl.append({"ref": ref, "exigencia": f"≥ {lim} m (valor por defeito, confirmar no regulamento municipal)", "valor": f"{float(v):g} m" if v is not None else "a verificar",
                    "ok": (float(v) >= lim) if v is not None else None})
    geo = {"altura_agua_m": 1.2 if V <= 4 else 1.5, "compartimentos": 2 if V <= 6 else 3}
    geo["comprimento_m"] = round(math.sqrt(V / geo["altura_agua_m"] * 2.5), 2)
    geo["largura_m"] = round(geo["comprimento_m"] / 2.5, 2)
    return {"habitantes": pop, "caudal_m3_dia": q, "volume_util_m3": V, "parcelas": {"liquido": v_liq, "lamas_digeridas": v_lm, "lamas_digestao": v_ld},
            "geometria": geo, "destino": dest, "controles": ctl, "hipoteses": hyp}


def ventilacao(p: dict) -> dict:
    pd = float(p.get("pe_direito_m") or 2.6)
    comp = [{**c, "tipo": (c.get("tipo") or "").strip().lower().replace(" ", "_")} for c in (p.get("compartimentos") or [])]
    if not comp:
        raise ValueError("indicar os compartimentos (tipo e área)")
    if any(not c.get("area_m2") or float(c["area_m2"]) <= 0 for c in comp):
        raise ValueError("cada compartimento precisa de uma área > 0")
    v_tot = sum(float(c["area_m2"]) * pd for c in comp)
    adm = sum(1.0 * float(c["area_m2"]) * pd for c in comp if c["tipo"] in ("sala", "quarto", "escritorio"))
    ext = sum(4.0 * float(c["area_m2"]) * pd for c in comp if c["tipo"] in ("cozinha", "instalacao_sanitaria", "lavandaria"))
    q_min = 0.5 * v_tot
    q = max(q_min, ext, adm)
    grelhas = []
    for c in comp:
        if c["tipo"] in ("sala", "quarto", "escritorio"):
            qc = max(1.0 * float(c["area_m2"]) * pd, q * float(c["area_m2"]) / max(1e-9, sum(float(x["area_m2"]) for x in comp if x["tipo"] in ("sala", "quarto", "escritorio"))))
            grelhas.append((c.get("nome") or c["tipo"], math.ceil(qc / 25) * 25))
    soma = sum(g for _, g in grelhas)
    rph_proj = float(p["rph_projeto"]) if p.get("rph_projeto") is not None else q / v_tot
    ctl = [{"ref": "Portaria 138-I/2021 — taxa de renovação", "exigencia": "Rph ≥ 0,50 h⁻¹", "valor": f"{rph_proj:.2f} h⁻¹ ({rph_proj * v_tot:.0f} m³/h para {v_tot:.0f} m³)"
            + ("" if p.get("rph_projeto") is not None else " — caudal recomendado"), "ok": rph_proj >= 0.5 - 1e-9},
           {"ref": "Admissão de ar (grelhas autorreguláveis NP EN 13141-1)", "exigencia": f"Σ admissão ≥ caudal extraído ({q:.0f} m³/h)", "valor": f"Σ = {soma} m³/h", "ok": soma >= q - 1e-9}]
    return {"volume_m3": v_tot, "caudal_m3h": q, "rph": q / v_tot, "admissao_min_m3h": adm, "extracao_m3h": ext, "grelhas": grelhas, "controles": ctl,
            "hipoteses": ["NP 1037-1: admissão ≈ 1 renovação/h nos compartimentos principais e extração ≈ 4 renovações/h na cozinha e instalações sanitárias (ordem de grandeza)",
                          "grelhas autorreguláveis em módulos de 25 m³/h (a 2 Pa)", "secções das aberturas e condutas segundo a NP 1037-1/-2 (não reproduzidas)"]}


def note(params: dict) -> dict:
    from . import notes
    f, W = notes._f, notes.W
    blocs, hyp, sous, out, n = [("p", "Pré-dimensionamento indicativo — não substitui o projeto da especialidade nem o parecer da entidade gestora / regulamento municipal.")], [], [], {}, 1
    from . import graficos as G
    kp = []

    def ctl(lst):
        return [{"ref": c["ref"], "exigence": c["exigencia"], "valeur": c["valor"], "ok": c["ok"]} for c in lst]
    if params.get("aguas_pluviais") is not None:
        r = aguas_pluviais(params["aguas_pluviais"])
        out["aguas_pluviais"] = r
        rows = [[v["vertente"], f(v["A"], 0), f"{v['Q']:.2f}", v["caleira"], f"{v['tubos_queda']} × Ø{v['phi']}"] for v in r["vertentes"]]
        blocs += [("h2", f"{n}. Águas pluviais (DR 23/95)"), ("table", ["Vertente", "m²", "L/s", "Caleira", "Tubos de queda"], rows, [35 * W, 18 * W, 18 * W, 45 * W, 35 * W]),
                  ("chart", G.jauges([(v["vertente"], v.get("ocupacao_caleira"), f"{v['Q'] / v['tubos_queda']:.2f} / {v['cap_caleira']:.2f} L/s".replace(".", ","))
                                      for v in r["vertentes"]], "Taxa de ocupação das caleiras (caudal por tubo de queda / capacidade)")),
                  ("controls", ctl(r["controles"]))]
        kp.append({"label": "Caudal pluvial total", "value": f"{r['caudal_total_l_s']:.2f}".replace(".", ","), "unit": "L/s"})
        if r.get("coletor"):
            kp.append({"label": "Coletor predial", "value": f"Ø{r['coletor']}", "unit": "mm", "ok": all(c["ok"] is not False for c in r["controles"])})
        hyp += r["hipoteses"]; sous.append("águas pluviais"); n += 1
    if params.get("fossa_septica") is not None:
        r = fossa_septica(params["fossa_septica"])
        out["fossa_septica"] = r
        g, d = r["geometria"], r["destino"]
        txt = f"Fossa séptica {r['volume_util_m3']:.2f} m³ úteis ({r['habitantes']} habitantes, {r['caudal_m3_dia'] * 1000:.0f} L/dia), {g['compartimentos']} compartimentos, " \
              f"≈ {g['comprimento_m']} × {g['largura_m']} m, altura de água {g['altura_agua_m']} m."
        if d.get("solucao") == "trincheiras de infiltração":
            txt += f" Infiltração: {d['comprimento_total_m']:.0f} m de trincheiras ({d['n_trincheiras']} × {d['comprimento_total_m'] / d['n_trincheiras']:.1f} m, largura 0,60 m)."
        elif d:
            txt += f" Destino final: {d['solucao']} ({d['motivo']})."
        pc = r["parcelas"]
        blocs += [("h2", f"{n}. Fossa séptica e destino final"), ("p", txt),
                  ("chart", G.donut([("Volume líquido (retenção)", pc["liquido"]), ("Lamas digeridas", pc["lamas_digeridas"]), ("Lamas em digestão", pc["lamas_digestao"])],
                                    "Composição do volume útil da fossa", f"{r['volume_util_m3']:.2f}".replace(".", ","), "m³ úteis", w=120 * W),
                   "Volume mínimo de 2 m³ quando a soma das parcelas é inferior." if r["volume_util_m3"] > sum(pc.values()) + 1e-6 else None),
                  ("controls", ctl(r["controles"]))]
        kp.append({"label": "Fossa séptica (volume útil)", "value": f"{r['volume_util_m3']:.2f}".replace(".", ","), "unit": "m³", "ok": all(c["ok"] is not False for c in r["controles"])})
        hyp += r["hipoteses"]; sous.append("fossa séptica"); n += 1
    if params.get("ventilacao") is not None:
        r = ventilacao(params["ventilacao"])
        out["ventilacao"] = r
        crit = G.barres_h([("Admissão (principais)", r["admissao_min_m3h"], G.SERIES[2]), ("Extração (húmidos)", r["extracao_m3h"], G.SERIES[0]),
                           ("Mínimo 0,5 Rph", 0.5 * r["volume_m3"], G.SERIES[1])], "Critérios de caudal", "m³/h", w=86 * W,
                          ref=(r["caudal_m3h"], f"adotado {r['caudal_m3h']:.0f}"), dec=0)
        gr = G.barres_h([(a, float(b)) for a, b in r["grelhas"]], "Grelhas de admissão", "m³/h", w=86 * W, couleur=G.SERIES[2], dec=0) if r["grelhas"] else None
        blocs += [("h2", f"{n}. Ventilação"), ("p", f"Caudal {r['caudal_m3h']:.0f} m³/h (Rph {r['rph']:.2f} h⁻¹). Grelhas de admissão: " + ", ".join(f"{a} {b} m³/h" for a, b in r["grelhas"]) + "."),
                  ("chart", G.cote_a_cote(crit, gr) if gr else crit, "O caudal adotado é o maior dos três critérios; a admissão total deve igualar a extração."),
                  ("controls", ctl(r["controles"]))]
        kp.append({"label": "Caudal de ventilação", "value": f"{r['caudal_m3h']:.0f}", "unit": "m³/h", "ok": all(c["ok"] is not False for c in r["controles"])})
        hyp += r["hipoteses"]; sous.append("ventilação")
    if not out:
        raise ValueError("indicar pelo menos: aguas_pluviais, fossa_septica ou ventilacao")
    titre = "Pré-dimensionamento — " + ", ".join(sous)
    pdf, png = notes.pdf(titre, "Águas pluviais · saneamento autónomo · ventilação (Portugal)", [("kpis", kp)] + blocs, hyp)
    return {**out, "titre": titre, "pdf": pdf, "png": png}
