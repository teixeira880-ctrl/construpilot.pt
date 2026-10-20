"""Instalações de habitação (Portugal) — eletricidade (RTIEBT, Portaria 949-A/2006 alterada pela Portaria 252/2015) e canalização
(abastecimento de água e drenagem, Decreto Regulamentar 23/95). Pré-dimensionamento indicativo.

Eletricidade: pontos por divisão (recomendações do guia técnico), circuitos (iluminação 1,5 mm²/10 A, tomadas 2,5 mm²/16 A, máx. 8 pontos;
máquinas e termoacumulador 2,5 mm²/16 A dedicados; placa/forno 6 mm²/32 A; climatização ≤ 5 aparelhos), diferenciais 30 mA (tipo A
para máquinas, placa e VE), quedas de tensão (3 % iluminação / 5 % outros nos circuitos finais), potência a contratar (escalões BTN).
Canalização: caudais instantâneos por dispositivo, caudal de cálculo pela curva do Anexo V (forma analítica por troços), velocidade
0,5–2 m/s, diâmetros, pressão; drenagem: caudais de descarga, caudal de cálculo, diâmetros de ramais, tubo de queda e coletor.
Valores não confirmados no texto oficial são parâmetros por defeito assinalados nas hipóteses.
"""
from __future__ import annotations

import math

RHO, LAMBDA = 0.023, 0.08e-3
ESCALOES = [3.45, 4.6, 5.75, 6.9, 10.35, 13.8, 17.25, 20.7, 27.6, 34.5, 41.4]
DIVISOES = {"sala": "Sala", "quarto": "Quarto", "cozinha": "Cozinha", "casa_de_banho": "Casa de banho", "lavandaria": "Lavandaria",
            "corredor": "Corredor / vestíbulo", "escritorio": "Escritório", "arrumos": "Arrecadação / garagem"}


def _tomadas(tipo, area, perimetro=None):
    if tipo == "sala":
        per = perimetro or 4 * math.sqrt(area)
        return max(3, math.ceil(per / 5))
    return {"quarto": 3, "escritorio": 3, "cozinha": 5, "casa_de_banho": 2, "lavandaria": 1, "corredor": 1, "arrumos": 1}.get(tipo, 1)


def _du(b, L, S, ib, cosphi=1.0):
    sinphi = math.sqrt(max(0.0, 1 - cosphi ** 2))
    u = b * (RHO * L / S * cosphi + LAMBDA * L * sinphi) * ib
    return 100 * u / (230 if b == 2 else 400 / math.sqrt(3))


def eletricidade(p: dict) -> dict:
    div = p.get("divisoes") or []
    if not div:
        raise ValueError("indicar as divisões (tipo e área)")
    eq = p.get("equipamentos") or {}
    L = float(p.get("comprimento_medio_circuito_m") or 15)
    pontos, tom, luz = [], 0, 0
    for d in div:
        t = (d.get("tipo") or "").strip().lower().replace(" ", "_")
        if t not in DIVISOES:
            raise ValueError(f"tipo de divisão desconhecido {d.get('tipo')!r} ({', '.join(DIVISOES)})")
        a = float(d.get("area_m2") or 0)
        n_t = _tomadas(t, a, d.get("perimetro_m"))
        n_l = 2 if (t == "sala" and a > 25) or (t == "cozinha" and a > 12) else 1
        if t == "corredor" and d.get("comprimento_m"):
            n_t = max(1, math.ceil(float(d["comprimento_m"]) / 6))
        pontos.append({"divisao": d.get("nome") or DIVISOES[t], "tipo": t, "tomadas": n_t, "pontos_luz": n_l})
        tom += n_t
        luz += n_l
    circ = []

    def add(nome, s, cal, pts=None, p_w=None, diff="A", cosphi=1.0, b=2):
        ib = (p_w / (230 * cosphi)) if (p_w and b == 2) else (p_w / (math.sqrt(3) * 400 * cosphi)) if p_w else cal * 0.5
        circ.append({"nome": nome, "seccao": s, "disjuntor": cal, "pontos": pts, "p_w": p_w, "diferencial": diff, "du": _du(b, L, s, ib, cosphi), "b": b})

    for i in range(math.ceil(luz / 8)):
        add(f"Iluminação {i + 1}", 1.5, 10, min(8, luz - 8 * i), diff="AC")
    for i in range(math.ceil(tom / 8)):
        add(f"Tomadas {i + 1}", 2.5, 16, min(8, tom - 8 * i), diff="AC")
    if eq.get("placa", True):
        tri = eq.get("placa") == "tri"
        add("Placa / fogão" + (" trifásico" if tri else ""), 2.5 if tri else 6.0, 16 if tri else 32, p_w=7200 if not tri else 7200, diff="A", b=3 if tri else 2)
    if eq.get("forno", True):
        add("Forno", 2.5, 16, p_w=3000, diff="A")
    for k, nome, pw in (("maquina_lavar_roupa", "Máquina de lavar roupa", 2200), ("maquina_lavar_loica", "Máquina de lavar loiça", 2200),
                        ("maquina_secar", "Máquina de secar", 2500), ("termoacumulador", "Termoacumulador", 2000)):
        if eq.get(k, k != "maquina_secar"):
            add(nome, 2.5, 16, p_w=pw, diff="A" if k.startswith("maquina") else "AC")
    n_clim = int(eq.get("unidades_climatizacao") or 0)
    for i in range(math.ceil(n_clim / 5)):
        add(f"Climatização {i + 1}", 2.5, 16, min(5, n_clim - 5 * i), diff="A")
    if eq.get("bomba_calor_kw"):
        pw = float(eq["bomba_calor_kw"]) * 1000
        ib = pw / 230
        cal, s = (16, 2.5) if ib <= 16 else (20, 4.0) if ib <= 20 else (32, 6.0) if ib <= 32 else (40, 10.0)
        add("Bomba de calor", s, cal, p_w=pw, diff="A")
    if eq.get("carregamento_ve_kw"):
        pw = float(eq["carregamento_ve_kw"]) * 1000
        tri = pw > 7400
        ib = pw / (230 if not tri else math.sqrt(3) * 400)
        cal = next(c for c in (16, 20, 32, 40) if c >= ib)
        add("Carregamento de veículo elétrico", {16: 2.5, 20: 4.0, 32: 6.0, 40: 10.0}[cal], cal, p_w=pw, diff="B" if tri else "A", b=3 if tri else 2)
    # potência
    area = sum(float(d.get("area_m2") or 0) for d in div)
    pot = 25 * area + 0.5 * sum(c["p_w"] or 0 for c in circ if c["nome"].startswith(("Placa", "Forno", "Máquina"))) + \
        sum(c["p_w"] or 0 for c in circ if c["nome"].startswith(("Termoacumulador", "Bomba", "Carregamento")))
    n_comp = sum(1 for d in div if d.get("tipo") in ("sala", "quarto", "escritorio"))
    p_min = 3.45 if n_comp <= 1 else 6.9 if n_comp <= 6 else 10.35
    kva = next((e for e in ESCALOES if e >= max(pot / 1000, p_min)), ESCALOES[-1])
    alim = "monofásica" if kva <= 13.8 and not any(c["b"] == 3 for c in circ) else "trifásica"
    ctl = []
    for c in circ:
        lim = 3.0 if c["nome"].startswith("Iluminação") else 5.0
        ctl.append({"ref": f"Queda de tensão — {c['nome']}", "exigencia": f"≤ {lim:g} % ({L:g} m)", "valor": f"{c['du']:.2f} %", "ok": c["du"] <= lim + 1e-9})
    n_dif = max(2, math.ceil(len(circ) / 8))
    ctl.append({"ref": "Proteção diferencial", "exigencia": "30 mA nos circuitos de tomadas, casas de banho e VE; tipo A para máquinas, placa e bomba de calor",
                "valor": f"{n_dif} diferenciais 30 mA (≤ 8 circuitos cada)", "ok": True})
    ctl.append({"ref": "Ligação à terra (regime TT)", "exigencia": "R × IΔn ≤ UL (R ≤ 1 670 Ω com 30 mA); recomendado ≤ 100 Ω",
                "valor": f"{float(p['resistencia_terra_ohm']):g} Ω" if p.get("resistencia_terra_ohm") is not None else "a medir",
                "ok": (float(p["resistencia_terra_ohm"]) <= 100) if p.get("resistencia_terra_ohm") is not None else None})
    hip = ["número de tomadas e pontos de luz segundo as recomendações do guia técnico (não mínimos legais explícitos do RTIEBT)",
           f"quedas de tensão calculadas com {L:g} m por circuito; limites 3 % / 5 % nos circuitos finais (a confirmar na secção 525 do RTIEBT)",
           "potência: 25 VA/m² para iluminação e tomadas + 50 % da cozinha e máquinas + 100 % de aquecimento de água, bomba de calor e VE"]
    return {"pontos": pontos, "tomadas": tom, "pontos_luz": luz, "circuitos": circ, "diferenciais": n_dif, "potencia_estimada_w": pot, "potencia_contratada_kva": kva,
            "alimentacao": alim, "controles": ctl, "hipoteses": hip,
            "regras": ["casas de banho: sem tomadas nos volumes 0–2 (exceto máquina de barbear com transformador de separação), ligação equipotencial suplementar",
                       "tomadas ≤ 16 A com alvéolos protegidos; alturas: interruptores 1,10–1,20 m, tomadas da bancada 1,10–1,20 m",
                       "condutor de proteção = secção da fase até 16 mm²; apenas disjuntores (não fusíveis) nos circuitos de habitação",
                       "ITED: projeto de telecomunicações obrigatório (ATE, ATI, tomadas RJ45 / coaxial por divisão)"]}


# ---------------------------------------------------------------------------------------------------------------------------------
DISPOSITIVOS = {   # caudal instantâneo (L/s), água quente, descarga (L/min), Ø ramal de descarga (mm)
    "lavatorio": (0.10, True, 30, 40), "bide": (0.10, True, 30, 40), "banheira": (0.25, True, 60, 40), "chuveiro": (0.15, True, 30, 40),
    "autoclismo": (0.10, False, 90, 90), "lava_loica": (0.20, True, 30, 50), "maquina_lavar_loica": (0.15, False, 60, 50),
    "maquina_lavar_roupa": (0.20, False, 60, 50), "tanque": (0.20, True, 60, 50), "torneira_exterior": (0.30, False, 0, 0)}
TUBOS_PT = [(16, 11.6), (20, 15.0), (25, 19.0), (32, 25.0), (40, 32.0), (50, 40.0)]    # PEX/multicamada : Ø nominal, Ø interior (mm)


def caudal_calculo(qa: float) -> float:
    """Curva do Anexo V do DR 23/95 em forma analítica por troços (nível de conforto médio)."""
    if qa <= 0.5:
        return qa
    if qa <= 3.5:
        return min(qa, 0.5469 * qa ** 0.5137)
    if qa <= 25:
        return 0.5226 * qa ** 0.5364
    return 0.2525 * qa ** 0.7587


def canalizacao(p: dict) -> dict:
    disp = p.get("dispositivos") or []
    if not disp:
        raise ValueError("indicar os dispositivos (tipo e quantidade)")
    qa_f = qa_q = desc = 0.0
    n_wc = 0
    rows = []
    for d in disp:
        t = d.get("tipo")
        if t not in DISPOSITIVOS:
            raise ValueError(f"dispositivo desconhecido {t!r} ({', '.join(DISPOSITIVOS)})")
        n = int(d.get("quantidade") or 1)
        q, aq, qd, dd = DISPOSITIVOS[t]
        qa_f += n * q
        qa_q += n * q if aq else 0.0
        desc += n * qd
        n_wc += n if t == "autoclismo" else 0
        rows.append({"dispositivo": t, "n": n, "q": q, "aq": aq, "descarga_l_min": qd, "ramal_descarga": dd})
    qc = caudal_calculo(qa_f)
    qcq = caudal_calculo(qa_q) if qa_q else 0.0
    vmax = float(p.get("velocidade_max_m_s") or 1.5)
    tubo = next(((dn, di) for dn, di in TUBOS_PT if qc / 1000 / (math.pi * (di / 1000) ** 2 / 4) <= vmax), TUBOS_PT[-1])
    v = qc / 1000 / (math.pi * (tubo[1] / 1000) ** 2 / 4)
    tubo_q = next(((dn, di) for dn, di in TUBOS_PT if qcq / 1000 / (math.pi * (di / 1000) ** 2 / 4) <= vmax), TUBOS_PT[-1]) if qcq else None
    # perda de carga (Darcy, Blasius) até ao dispositivo mais desfavorável
    Lr = float(p.get("comprimento_m") or 25)
    Re = v * tubo[1] / 1000 / 1.0e-6
    f = 0.316 / Re ** 0.25 if Re > 0 else 0.0
    j = f * (Lr * 1.2) / (tubo[1] / 1000) * v * v / 2 / 9.81                     # m (+20 % singularidades)
    h = float(p.get("desnivel_m") or 3)
    pst = float(p.get("pressao_rede_kpa") or 300)
    pres = pst - (j + h) * 9.81
    qd = desc if desc <= 3 * 90 else 7.3497 * desc ** 0.5352
    tq = 100 if n_wc else 75
    ctl = [{"ref": "Velocidade (DR 23/95, art. 94.º)", "exigencia": f"0,5 a 2,0 m/s (adotado ≤ {vmax:g})", "valor": f"{v:.2f} m/s em Ø{tubo[0]}", "ok": 0.5 <= v <= 2.0 or qc < 0.2},
           {"ref": "Pressão no dispositivo mais desfavorável", "exigencia": "≥ 50 kPa (recomendado 150–300 kPa); estática ≤ 600 kPa",
            "valor": f"{pres:.0f} kPa (rede {pst:g} kPa)", "ok": pres >= 50 and pst <= 600,
            "note": "redutor de pressão" if pst > 600 else ("sobrepressora" if pres < 50 else None)}]
    hip = [f"caudal de cálculo pela curva do Anexo V em forma analítica (troços confirmados por fonte secundária); Qa = {qa_f:.2f} L/s → Qc = {qc:.2f} L/s",
           "caudais do chuveiro (0,15 L/s) e da torneira exterior não confirmados no texto oficial; pressões 50 / 600 kPa a confirmar (art. 87.º)",
           f"drenagem: caudal de cálculo {qd:.0f} L/min (Anexo XV, fórmula a confirmar), ramais com inclinação de 10 a 40 mm/m"]
    return {"dispositivos": rows, "qa_l_s": qa_f, "qc_l_s": qc, "qc_aq_l_s": qcq, "tubo_af": f"Ø{tubo[0]} (int. {tubo[1]} mm)", "tubo_aq": f"Ø{tubo_q[0]}" if tubo_q else None,
            "velocidade_m_s": v, "pressao_kpa": pres, "drenagem_qc_l_min": qd, "tubo_queda_mm": tq, "coletor_mm": 100 if n_wc else 75, "controles": ctl, "hipoteses": hip,
            "regras": ["ramais de descarga com inclinação de 10 a 40 mm/m, troço vertical ≤ 2 m; bacia de retrete Ø90 mínimo",
                       f"tubo de queda Ø{tq} com taxa de ocupação ≤ 1/3 (ventilação secundária) ou ≤ 1/7 (sem); ventilação 0,50 m acima da cobertura",
                       "coletores prediais Ø ≥ 100 mm, meia secção, câmaras de inspeção a ≤ 15 m; fecho hídrico dos sifões 50–75 mm",
                       "AQS produzida a ≥ 60 °C (prevenção da legionela), utilização com misturadora"]}


def note(params: dict) -> dict:
    from . import notes
    f, W = notes._f, notes.W
    blocs, hip, out = [("p", "Pré-dimensionamento indicativo — não substitui os projetos de especialidade (eletricidade, ITED, águas e esgotos).")], [], {}
    conv = lambda lst: [{"ref": c["ref"], "exigence": c["exigencia"], "valeur": c["valor"], "ok": c["ok"], "note": c.get("note")} for c in lst]
    n = 1
    if params.get("eletricidade") is not None:
        r = eletricidade(params["eletricidade"])
        out["eletricidade"] = r
        rows = [[c["nome"], f"{c['seccao']:g}", f"{c['disjuntor']}", str(c["pontos"] or ""), c["diferencial"], f"{c['du']:.2f}"] for c in r["circuitos"]]
        blocs += [("h2", f"{n}. Eletricidade (RTIEBT)"),
                  ("table", ["Divisão", "Tomadas", "Pontos de luz"], [[x["divisao"], str(x["tomadas"]), str(x["pontos_luz"])] for x in r["pontos"]], [70 * W, 25 * W, 30 * W]),
                  ("table", ["Circuito", "mm²", "Disjuntor A", "Pontos", "Diferencial", "ΔU %"], rows, [55 * W, 15 * W, 22 * W, 16 * W, 22 * W, 16 * W]),
                  ("p", f"Potência estimada {f(r['potencia_estimada_w'])} W → contratar {r['potencia_contratada_kva']:g} kVA ({r['alimentacao']})."),
                  ("controls", conv(r["controles"])), ("hyp", r["regras"])]
        hip += r["hipoteses"]; n += 1
    if params.get("canalizacao") is not None:
        r = canalizacao(params["canalizacao"])
        out["canalizacao"] = r
        blocs += [("h2", f"{n}. Abastecimento de água e drenagem (DR 23/95)"),
                  ("p", f"Qa {r['qa_l_s']:.2f} L/s → Qc {r['qc_l_s']:.2f} L/s, ramal geral água fria {r['tubo_af']} ({r['velocidade_m_s']:.2f} m/s), água quente "
                        f"{r['tubo_aq'] or '—'}, pressão no dispositivo mais desfavorável {r['pressao_kpa']:.0f} kPa. Drenagem: {r['drenagem_qc_l_min']:.0f} L/min, "
                        f"tubo de queda Ø{r['tubo_queda_mm']}, coletor Ø{r['coletor_mm']}."),
                  ("table", ["Dispositivo", "Nº", "L/s", "AQ", "Descarga L/min", "Ramal Ø"],
                   [[x["dispositivo"], str(x["n"]), f"{x['q']:.2f}", "sim" if x["aq"] else "não", str(x["descarga_l_min"]), str(x["ramal_descarga"] or "—")] for x in r["dispositivos"]],
                   [45 * W, 12 * W, 15 * W, 12 * W, 28 * W, 18 * W]),
                  ("controls", conv(r["controles"])), ("hyp", r["regras"])]
        hip += r["hipoteses"]
    if not out:
        raise ValueError("indicar eletricidade e/ou canalizacao")
    titre = "Pré-dimensionamento — instalações (" + ", ".join(out) + ")"
    pdf, png = notes.pdf(titre, "RTIEBT · DR 23/95", blocs, hip)
    return {**out, "titre": titre, "pdf": pdf, "png": png}
