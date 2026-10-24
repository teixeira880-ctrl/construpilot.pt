"""Instalações de habitação (Portugal) — eletricidade (RTIEBT, Portaria 949-A/2006 alterada pela Portaria 252/2015) e canalização
(abastecimento de água e drenagem, Decreto Regulamentar 23/95). Pré-dimensionamento indicativo.

Eletricidade: pontos por divisão (recomendações do guia técnico), circuitos atribuídos às divisões (iluminação 1,5 mm²/10 A,
tomadas 2,5 mm²/16 A, máx. 8 pontos; máquinas e termoacumulador 2,5 mm²/16 A dedicados; placa 6 mm²/32 A; climatização ≤ 5
aparelhos; aquecimento elétrico por divisão, bomba de calor e apoio, carregamento VE), comprimento real de cada circuito (distância
ao quadro da divisão mais afastada) e queda de tensão u = b·(ρ·L/S·cosφ + λ·L·sinφ)·Ib (b = 2 monofásico, 1 trifásico equilibrado;
ρ = 0,023 Ω·mm²/m, λ = 0,08 mΩ/m), secção recomendada se o limite for excedido, diferenciais 30 mA agrupados por tipo (AC / A / B),
potência a contratar (escalões BTN) e entrada (contador → quadro).
Canalização: caudais instantâneos por dispositivo, caudal de cálculo pela curva do Anexo V (forma analítica por troços), velocidade
0,5–2 m/s, diâmetros, perdas de carga (Darcy-Weisbach) e pressão; quando a rede é descrita, cálculo TROÇO A TROÇO (caudal acumulado,
caudal de cálculo, diâmetro, velocidade, perda de carga, pressão no fim de cada troço, dispositivo mais desfavorável). Drenagem: caudais
de descarga, caudal de cálculo, ramais e coletores por Manning-Strickler a meia secção, tubos de queda pela taxa de ocupação, troço a troço.
Valores não confirmados no texto oficial são parâmetros por defeito assinalados nas hipóteses.
"""
from __future__ import annotations

import math

RHO, LAMBDA = 0.023, 0.08e-3
CALIBRES = [(16, 2.5), (20, 4.0), (32, 6.0), (40, 10.0), (50, 16.0), (63, 16.0)]   # disjuntor A → secção Cu mm² (instalação embebida, indicativo)
SECCOES = [1.5, 2.5, 4.0, 6.0, 10.0, 16.0, 25.0]
ESCALOES = [3.45, 4.6, 5.75, 6.9, 10.35, 13.8, 17.25, 20.7, 27.6, 34.5, 41.4]
MONO_MAX_KVA = 13.8                                                                # 60 A em 230 V (prática BTN)
DIF_CALIBRES = [25, 40, 63, 80, 100]
ENTRADA = [(30, 6.0), (45, 10.0), (60, 16.0)]                                      # corrente de contrato → secção da entrada (fonte secundária)
P_PONTO_LUZ = 100                                                                  # W por ponto de luz (queda de tensão)
DIVISOES = {"sala": "Sala", "quarto": "Quarto", "cozinha": "Cozinha", "casa_de_banho": "Casa de banho", "lavandaria": "Lavandaria",
            "corredor": "Corredor / vestíbulo", "escritorio": "Escritório", "arrumos": "Arrecadação / garagem"}
_COMP_EQ = ("placa", "forno", "maquina_lavar_roupa", "maquina_lavar_loica", "maquina_secar", "termoacumulador", "climatizacao", "bomba_calor",
            "carregamento_ve")


def _c(x, n=1) -> str:
    return f"{x:.{n}f}".replace(".", ",")


def _g(x) -> str:
    return f"{x:g}".replace(".", ",")


def _tomadas(tipo, area, perimetro=None):
    if tipo == "sala":
        per = perimetro or 4 * math.sqrt(area)
        return max(3, math.ceil(per / 5))
    return {"quarto": 3, "escritorio": 3, "cozinha": 5, "casa_de_banho": 2, "lavandaria": 1, "corredor": 1, "arrumos": 1}.get(tipo, 1)


def _du(b, L, S, ib, cosphi=1.0):
    """Queda de tensão relativa (%). b = 2 monofásico (ida e volta, 230 V); b = 3 (ou 1) trifásico equilibrado (fator 1, tensão simples)."""
    k = 2 if b == 2 else 1
    sinphi = math.sqrt(max(0.0, 1 - cosphi ** 2))
    u = k * (RHO * L / S * cosphi + LAMBDA * L * sinphi) * ib
    return 100 * u / (230 if b == 2 else 400 / math.sqrt(3))


def eletricidade(p: dict) -> dict:
    """p : {divisoes: [{nome, tipo, area_m2, perimetro_m, comprimento_m, distancia_quadro_m, tomadas, pontos_luz, estores, aquecimento_w}],
            equipamentos: {placa, forno, maquina_lavar_roupa, maquina_lavar_loica, maquina_secar, termoacumulador, unidades_climatizacao,
                           bomba_calor_kw, apoio_bomba_calor_kw, carregamento_ve_kw},
            comprimento_medio_circuito_m, comprimentos_m: {placa, …, carregamento_ve}, comprimento_entrada_m, seccao_entrada_mm2,
            alimentacao ('monofasica' | 'trifasica'), circuitos_max_diferencial, resistencia_terra_ohm}"""
    div = p.get("divisoes") or []
    if not div:
        raise ValueError("indicar as divisões (tipo e área)")
    eq = p.get("equipamentos") or {}
    L = float(p.get("comprimento_medio_circuito_m") or 15)
    comp = {k: float(v) for k, v in (p.get("comprimentos_m") or {}).items() if v is not None}
    hip: list[str] = []
    pontos, tom, luz = [], 0, 0
    reais = False
    for d in div:
        t = (d.get("tipo") or "").strip().lower().replace(" ", "_")
        if t not in DIVISOES:
            raise ValueError(f"tipo de divisão desconhecido {d.get('tipo')!r} ({', '.join(DIVISOES)})")
        a = float(d.get("area_m2") or 0)
        n_t = _tomadas(t, a, d.get("perimetro_m"))
        n_l = 2 if (t == "sala" and a > 25) or (t == "cozinha" and a > 12) else 1
        if t == "corredor" and d.get("comprimento_m"):
            n_t = max(1, math.ceil(float(d["comprimento_m"]) / 6))
        if d.get("tomadas") is not None:
            n_t = int(d["tomadas"])
        if d.get("pontos_luz") is not None:
            n_l = int(d["pontos_luz"])
        dist = float(d["distancia_quadro_m"]) if d.get("distancia_quadro_m") is not None else None
        reais = reais or dist is not None
        pontos.append({"divisao": d.get("nome") or DIVISOES[t], "tipo": t, "area_m2": a, "tomadas": n_t, "pontos_luz": n_l,
                       "estores": int(d.get("estores") or 0), "aquecimento_w": float(d.get("aquecimento_w") or 0),
                       "distancia_m": dist if dist is not None else L})
        tom += n_t
        luz += n_l
    circ = []

    def add(nome, s, cal, pts=None, p_w=None, diff="A", cosphi=1.0, b=2, comprimento=None, divs=None, familia="dedicado", ib=None):
        if ib is None:
            ib = (p_w / (230 * cosphi)) if (p_w and b == 2) else (p_w / (math.sqrt(3) * 400 * cosphi)) if p_w else cal * 0.5
        Lc = float(comprimento if comprimento is not None else L)
        circ.append({"nome": nome, "seccao": s, "disjuntor": cal, "pontos": pts, "p_w": p_w, "diferencial": diff, "b": b, "cosphi": cosphi,
                     "ib_a": ib, "comprimento_m": Lc, "divisoes": divs or [], "familia": familia, "du": _du(b, Lc, s, ib, cosphi)})

    def dist_tipo(*tipos):
        for t in tipos:                                 # por ordem de preferência; a divisão mais afastada desse tipo
            ds = [x["distancia_m"] for x in pontos if x["tipo"] == t]
            if ds:
                return max(ds)
        return None

    def nome_tipo(*tipos):
        x = next((x for t in tipos for x in pontos if x["tipo"] == t), None)
        return x["divisao"] if x else DIVISOES[tipos[0]]

    def pack(chave, maxp, extra=None):
        """Divisões atribuídas a circuitos de ≤ maxp pontos, sem partir uma divisão salvo se tiver mais de maxp pontos."""
        grupos, cur = [], None
        for x in pontos:
            n = x[chave] + (x[extra] if extra else 0)
            while n > 0:
                if cur is None or cur["pts"] + min(n, maxp) > maxp:
                    cur = {"pts": 0, "divs": [], "L": 0.0}
                    grupos.append(cur)
                take = min(n, maxp - cur["pts"])
                cur["pts"] += take
                if x["divisao"] not in cur["divs"]:
                    cur["divs"].append(x["divisao"])
                cur["L"] = max(cur["L"], x["distancia_m"])
                n -= take
        return grupos

    for i, g in enumerate(pack("pontos_luz", 8, "estores")):
        add(f"Iluminação {i + 1}", 1.5, 10, g["pts"], p_w=g["pts"] * P_PONTO_LUZ, diff="AC", comprimento=g["L"], divs=g["divs"], familia="iluminacao")
    if any(x["estores"] for x in pontos):
        hip.append("estores elétricos ligados aos circuitos de iluminação (1,5 mm² / 10 A, contados como pontos)")
    for i, g in enumerate(pack("tomadas", 8)):
        add(f"Tomadas {i + 1}", 2.5, 16, g["pts"], diff="AC", comprimento=g["L"], divs=g["divs"], familia="tomadas")
    L_coz = comp.get("placa") or dist_tipo("cozinha")
    if eq.get("placa", True):
        tri = eq.get("placa") == "tri"
        add("Placa / fogão" + (" trifásico" if tri else ""), 2.5 if tri else 6.0, 16 if tri else 32, p_w=7200, diff="A", b=3 if tri else 2,
            comprimento=L_coz, divs=[nome_tipo("cozinha")])
    if eq.get("forno", True):
        add("Forno", 2.5, 16, p_w=3000, diff="A", comprimento=comp.get("forno") or dist_tipo("cozinha"), divs=[nome_tipo("cozinha")])
    lav = ("lavandaria",) if dist_tipo("lavandaria") is not None else ("cozinha",)
    for k, nome, pw, tps in (("maquina_lavar_roupa", "Máquina de lavar roupa", 2200, lav), ("maquina_lavar_loica", "Máquina de lavar loiça", 2200, ("cozinha",)),
                             ("maquina_secar", "Máquina de secar", 2500, lav), ("termoacumulador", "Termoacumulador", 2000, ("lavandaria", "casa_de_banho"))):
        if eq.get(k, k != "maquina_secar"):
            add(nome, 2.5, 16, p_w=pw, diff="A" if k.startswith("maquina") else "AC", comprimento=comp.get(k) or dist_tipo(*tps),
                divs=[nome_tipo(*tps)] if (dist_tipo(*tps) is not None and not comp.get(k)) else [])
    n_clim = int(eq.get("unidades_climatizacao") or 0)
    for i in range(math.ceil(n_clim / 5)):
        add(f"Climatização {i + 1}", 2.5, 16, min(5, n_clim - 5 * i), diff="A", comprimento=comp.get("climatizacao"))
    for x in pontos:
        if x["aquecimento_w"] > 0:
            pw = x["aquecimento_w"]
            cal, s = next(((c, sc) for c, sc in CALIBRES if c >= pw / 230), (None, None))
            if cal is None:
                raise ValueError(f"aquecimento elétrico de {pw:g} W em {x['divisao']}: dividir em vários circuitos (> 63 A)")
            add(f"Aquecimento elétrico — {x['divisao']}", s, cal, p_w=pw, diff="AC", comprimento=x["distancia_m"], divs=[x["divisao"]], familia="aquecimento")
    if eq.get("bomba_calor_kw"):
        pw = float(eq["bomba_calor_kw"]) * 1000
        tri_bc = pw / 230 > 32
        ib = pw / (math.sqrt(3) * 400) if tri_bc else pw / 230
        cal, s = next(((c, sc) for c, sc in CALIBRES if c >= ib), (None, None))
        if cal is None:
            raise ValueError(f"bomba de calor de {pw / 1000:g} kW ({ib:.0f} A) fora do âmbito do pré-dimensionamento (> 63 A)")
        add("Bomba de calor" + (" trifásica" if tri_bc else ""), s, cal, p_w=pw, diff="A", b=3 if tri_bc else 2, comprimento=comp.get("bomba_calor"),
            familia="aquecimento")
    if eq.get("apoio_bomba_calor_kw"):
        pw = float(eq["apoio_bomba_calor_kw"]) * 1000
        tri_a = pw / 230 > 32
        ib = pw / (math.sqrt(3) * 400) if tri_a else pw / 230
        cal, s = next(((c, sc) for c, sc in CALIBRES if c >= ib), (None, None))
        if cal is None:
            raise ValueError(f"apoio elétrico de {pw / 1000:g} kW fora do âmbito do pré-dimensionamento (> 63 A)")
        add("Apoio elétrico da bomba de calor" + (" trifásico" if tri_a else ""), s, cal, p_w=pw, diff="A", b=3 if tri_a else 2,
            comprimento=comp.get("bomba_calor"), familia="aquecimento")
    if eq.get("carregamento_ve_kw"):
        pw = float(eq["carregamento_ve_kw"]) * 1000
        tri = pw > 7400
        ib = pw / (230 if not tri else math.sqrt(3) * 400)
        cal, s = next(((c, sc) for c, sc in CALIBRES if c >= ib), (None, None))
        if cal is None:
            raise ValueError(f"posto de carregamento de {pw / 1000:g} kW ({ib:.0f} A) fora do âmbito do pré-dimensionamento (> 63 A)")
        add("Carregamento de veículo elétrico", s, cal, p_w=pw, diff="B" if tri else "A", b=3 if tri else 2, comprimento=comp.get("carregamento_ve"), familia="ve")
    # quedas de tensão: secção recomendada quando o limite é excedido
    for c in circ:
        lim = 5.0 if c["familia"] != "iluminacao" else 3.0
        c["du_lim"] = lim
        c["du_ok"] = c["du"] <= lim + 1e-9
        c["seccao_recomendada"] = c["seccao"] if c["du_ok"] else next((s for s in SECCOES if s > c["seccao"] and _du(c["b"], c["comprimento_m"], s, c["ib_a"], c["cosphi"]) <= lim), None)
    # potência
    area = sum(float(d.get("area_m2") or 0) for d in div)
    pot = 25 * area + 0.5 * sum(c["p_w"] or 0 for c in circ if c["nome"].startswith(("Placa", "Forno", "Máquina"))) + \
        sum(c["p_w"] or 0 for c in circ if c["nome"].startswith(("Termoacumulador", "Bomba", "Carregamento", "Apoio", "Aquecimento")))
    n_comp = sum(1 for d in div if d.get("tipo") in ("sala", "quarto", "escritorio"))
    p_min = 3.45 if n_comp <= 1 else 6.9 if n_comp <= 6 else 10.35
    kva = next((e for e in ESCALOES if e >= max(pot / 1000, p_min) - 1e-9), ESCALOES[-1])
    alim_in = p.get("alimentacao")
    alim = ("monofásica" if alim_in == "monofasica" else "trifásica") if alim_in else \
        ("monofásica" if kva <= MONO_MAX_KVA and not any(c["b"] == 3 for c in circ) else "trifásica")
    i_contr = kva * 1000 / 230 if alim == "monofásica" else kva * 1000 / (math.sqrt(3) * 400)
    # entrada (contador / portinhola → quadro)
    entrada = None
    if p.get("comprimento_entrada_m"):
        Le = float(p["comprimento_entrada_m"])
        se = float(p["seccao_entrada_mm2"]) if p.get("seccao_entrada_mm2") else next((s for a_, s in ENTRADA if i_contr <= a_ + 1e-9), 25.0)
        due = _du(2 if alim == "monofásica" else 3, Le, se, i_contr)
        entrada = {"comprimento_m": Le, "seccao_mm2": se, "corrente_a": i_contr, "du": due}
        if not p.get("seccao_entrada_mm2"):
            hip.append("secção da entrada pela corrente de contrato (6 mm² até 30 A, 10 mm² até 45 A, 16 mm² até 60 A — fonte secundária, a confirmar "
                       "com o distribuidor / RTIEBT)")
    # diferenciais 30 mA
    nmax = int(p.get("circuitos_max_diferencial") or 8)
    grupos = []
    for c in circ:
        if c["nome"].startswith("Carregamento"):
            grupos.append({"tipo": c["diferencial"], "circuitos": [c], "individual": True})
    tipo_a = [c for c in circ if c["diferencial"] == "A" and not c["nome"].startswith("Carregamento")]
    for k in range(0, len(tipo_a), nmax):
        grupos.append({"tipo": "A", "circuitos": tipo_a[k:k + nmax], "individual": False})
    tipo_ac = [c for c in circ if c["diferencial"] == "AC"]
    if tipo_ac:
        n_ac = max(2 if len(tipo_ac) > 1 else 1, math.ceil(len(tipo_ac) / nmax))
        bk = [[] for _ in range(n_ac)]
        ilu = [c for c in tipo_ac if c["familia"] == "iluminacao"]
        tm = [c for c in tipo_ac if c["familia"] == "tomadas"]
        rest = [c for c in tipo_ac if c["familia"] not in ("iluminacao", "tomadas")]
        for k, c in enumerate(ilu):                   # iluminação e tomadas repartidas: um defeito não deixa a habitação às escuras
            bk[k % n_ac].append(c)
        for k, c in enumerate(tm):
            bk[(k + 1) % n_ac].append(c)
        for c in rest:
            min(bk, key=len).append(c)
        grupos += [{"tipo": "AC", "circuitos": b, "individual": False} for b in bk if b]
    difs = []
    for g in grupos:
        soma = sum(c["disjuntor"] for c in g["circuitos"])
        base = max(max(c["disjuntor"] for c in g["circuitos"]), min(soma, i_contr))
        cal = next((x for x in DIF_CALIBRES if x >= base - 1e-9), DIF_CALIBRES[-1])
        difs.append({"tipo": g["tipo"], "calibre": cal, "sensibilidade_ma": 30, "polos": "4P" if any(c["b"] == 3 for c in g["circuitos"]) else "2P",
                     "circuitos": [c["nome"] for c in g["circuitos"]], "individual": g["individual"]})
        for c in g["circuitos"]:
            c["diferencial_n"] = len(difs)
    # controlos
    du_max = max(c["du"] for c in circ)
    ctl = [{"ref": "Quedas de tensão nos circuitos finais", "exigencia": "≤ 3 % iluminação, ≤ 5 % restantes usos (a confirmar na secção 525 do RTIEBT)",
            "valor": f"máx. {_c(du_max, 2)} %" + (" (comprimentos reais)" if reais or comp else f" ({_g(L)} m por circuito)"), "ok": all(c["du_ok"] for c in circ)}]
    for c in circ:
        if not c["du_ok"]:
            ctl.append({"ref": f"Queda de tensão — {c['nome']}", "exigencia": f"≤ {_g(c['du_lim'])} %",
                        "valor": f"{_c(c['du'], 2)} % em {_g(c['comprimento_m'])} m ({_g(c['seccao'])} mm²)", "ok": False,
                        "note": (f"secção {_g(c['seccao_recomendada'])} mm² (verificar a compatibilidade com o disjuntor e os bornes)" if c["seccao_recomendada"]
                                 else "aproximar o quadro ou criar um quadro parcial")})
    if entrada:
        ctl.append({"ref": "Queda de tensão na entrada", "exigencia": "≤ 1,5 % da portinhola à origem da instalação (moradia; fonte secundária, a confirmar)",
                    "valor": f"{_c(entrada['du'], 2)} % ({_g(entrada['comprimento_m'])} m, {_g(entrada['seccao_mm2'])} mm², {_c(i_contr)} A)",
                    "ok": entrada["du"] <= 1.5 + 1e-9})
    ctl.append({"ref": "Proteção diferencial", "exigencia": "30 mA nos circuitos de tomadas, casas de banho e VE; tipo A para máquinas, placa e bomba de calor; "
                                                         "VE com diferencial individual (tipo B ou A + deteção DC 6 mA se trifásico)",
                "valor": f"{len(difs)} diferenciais 30 mA (" + ", ".join(f"{x['tipo']} {x['calibre']} A" for x in difs) + ")",
                "ok": all(len(x["circuitos"]) <= nmax for x in difs)})
    ctl.append({"ref": "Potência a contratar (BTN)", "exigencia": f"escalão ≥ potência estimada e ≥ {_g(p_min)} kVA (mínimo por n.º de compartimentos, fonte secundária); "
                                                               f"monofásica até {_g(MONO_MAX_KVA)} kVA (prática BTN)",
                "valor": f"{_g(kva)} kVA {alim} ({_c(i_contr)} A) para {pot / 1000:.1f} kW estimados".replace(".", ","),
                "ok": not (alim == "monofásica" and (kva > MONO_MAX_KVA or any(c["b"] == 3 for c in circ)))})
    ctl.append({"ref": "Ligação à terra (regime TT)", "exigencia": "R × IΔn ≤ UL (R ≤ 1 670 Ω com 30 mA e UL 50 V; 833 Ω com UL 25 V); recomendado ≤ 100 Ω",
                "valor": f"{_g(float(p['resistencia_terra_ohm']))} Ω" if p.get("resistencia_terra_ohm") is not None else "a medir",
                "ok": (float(p["resistencia_terra_ohm"]) <= 100) if p.get("resistencia_terra_ohm") is not None else None})
    hip += ["número de tomadas e pontos de luz segundo as recomendações do guia técnico (não mínimos legais explícitos do RTIEBT)",
            (f"comprimentos de circuito: distância ao quadro da divisão mais afastada servida (indicada); {_g(L)} m onde não indicada" if reais or comp
             else f"quedas de tensão calculadas com {_g(L)} m por circuito (indicar distancia_quadro_m por divisão para o comprimento real)"),
            f"corrente de cálculo: iluminação {P_PONTO_LUZ} W por ponto, tomadas 50 % do calibre, circuitos dedicados à potência do aparelho (carga no fim do circuito)",
            "limites de queda de tensão 3 % / 5 % nos circuitos finais (a confirmar na secção 525 do RTIEBT)",
            "potência: 25 VA/m² para iluminação e tomadas + 50 % da cozinha e máquinas + 100 % de aquecimento, água quente, bomba de calor e VE",
            f"diferenciais: no máximo {nmax} circuitos por aparelho (boa prática, sem limite numérico confirmado no RTIEBT); "
            "calibre ≥ maior disjuntor a jusante e ≥ min(Σ disjuntores, corrente de contrato)"]
    return {"pontos": pontos, "tomadas": tom, "pontos_luz": luz, "circuitos": circ, "diferenciais": len(difs), "diferenciais_lista": difs,
            "potencia_estimada_w": pot, "potencia_contratada_kva": kva, "potencia_minima_kva": p_min, "corrente_contrato_a": i_contr,
            "alimentacao": alim, "entrada": entrada, "du_max": du_max, "controles": ctl, "hipoteses": hip,
            "regras": ["casas de banho: sem tomadas nos volumes 0–2 (exceto máquina de barbear com transformador de separação), ligação equipotencial suplementar",
                       "tomadas ≤ 16 A com alvéolos protegidos; alturas: interruptores 1,10–1,20 m, tomadas da bancada 1,10–1,20 m",
                       "condutor de proteção = secção da fase até 16 mm²; apenas disjuntores (não fusíveis) nos circuitos de habitação",
                       "circuitos separados por tipo de uso (iluminação, tomadas, cozinha, máquinas, aquecimento); VE com circuito dedicado ≥ 16 A, curva C ou D",
                       "ITED: projeto de telecomunicações obrigatório (ATE, ATI, tomadas RJ45 / coaxial por divisão)"]}


# ---------------------------------------------------------------------------------------------------------------------------------
DISPOSITIVOS = {   # caudal instantâneo (L/s), água quente, descarga (L/min), Ø ramal de descarga (mm)
    "lavatorio": (0.10, True, 30, 40), "bide": (0.10, True, 30, 40), "banheira": (0.25, True, 60, 40), "chuveiro": (0.15, True, 30, 40),
    "autoclismo": (0.10, False, 90, 90), "lava_loica": (0.20, True, 30, 50), "maquina_lavar_loica": (0.15, False, 60, 50),
    "maquina_lavar_roupa": (0.20, False, 60, 50), "tanque": (0.20, True, 60, 50), "torneira_exterior": (0.30, False, 0, 0)}
DISP_PT = {"lavatorio": "Lavatório", "bide": "Bidé", "banheira": "Banheira", "chuveiro": "Chuveiro", "autoclismo": "Autoclismo", "lava_loica": "Lava-loiça",
           "maquina_lavar_loica": "Máquina de lavar loiça", "maquina_lavar_roupa": "Máquina de lavar roupa", "tanque": "Tanque", "torneira_exterior": "Torneira exterior"}
TUBOS_PT = [(16, 11.6), (20, 15.0), (25, 19.0), (32, 25.0), (40, 32.0), (50, 40.0)]    # PEX/multicamada : Ø nominal, Ø interior (mm)
PVC_DRENAGEM = {40: 36.4, 50: 46.4, 75: 70.6, 90: 85.6, 110: 104.6, 125: 118.6, 160: 152.0, 200: 190.2}   # Ø nominal → Ø interior (mm, indicativo)
KS_PVC = 120.0                     # m^(1/3)/s — Manning-Strickler, PVC (indicativo)
P_MIN_KPA, P_MAX_KPA = 50.0, 600.0  # DR 23/95 art. 87.º (a confirmar)
NU = {"fria": 1.0e-6, "quente": 0.47e-6}   # viscosidade cinemática da água a ≈ 20 °C / 60 °C (m²/s)


def caudal_calculo(qa: float) -> float:
    """Curva do Anexo V do DR 23/95 em forma analítica por troços (nível de conforto médio)."""
    if qa <= 0.5:
        return qa
    if qa <= 3.5:
        return min(qa, 0.5469 * qa ** 0.5137)
    if qa <= 25:
        return 0.5226 * qa ** 0.5364
    return 0.2525 * qa ** 0.7587


def caudal_calculo_drenagem(qa_l_min: float) -> float:
    """Caudal de cálculo da drenagem (L/min): curva do Anexo XV em forma analítica Qc = 7,3497·Qa^0,5352 (a confirmar), nunca superior a Qa."""
    if qa_l_min <= 0:
        return 0.0
    return min(qa_l_min, 7.3497 * qa_l_min ** 0.5352)


def _v(q_ls, di_mm):
    return q_ls / 1000 / (math.pi * (di_mm / 1000) ** 2 / 4)


def _tubo(q_ls, vmax):
    return next(((dn, di) for dn, di in TUBOS_PT if _v(q_ls, di) <= vmax), TUBOS_PT[-1])


def _perda(q_ls, di_mm, L, agua="fria", k_sing=0.2):
    """Perda de carga (m c.a.) — Darcy-Weisbach (64/Re laminar, Blasius turbulento liso) + k_sing de singularidades. → (ΔH, v, J m/m)."""
    v = _v(q_ls, di_mm)
    d = di_mm / 1000
    re = v * d / NU[agua]
    if re <= 0:
        return 0.0, 0.0, 0.0
    lam = 64 / re if re < 2300 else 0.3164 / re ** 0.25
    J = lam / d * v * v / (2 * 9.81)
    return J * L * (1 + k_sing), v, J


def _dispositivos(lst):
    out = []
    for d in lst or []:
        t = d.get("tipo")
        if t not in DISPOSITIVOS:
            raise ValueError(f"dispositivo desconhecido {t!r} ({', '.join(DISPOSITIVOS)})")
        out.append((t, int(d.get("quantidade") or 1)))
    return out


def _arvore(trocos, chave_pai, rotulo):
    nomes = [str(t.get("nome") or f"T{i + 1}") for i, t in enumerate(trocos)]
    if len(set(nomes)) != len(nomes):
        raise ValueError(f"{rotulo}: nomes de troços repetidos")
    pai = {}
    for n, t in zip(nomes, trocos):
        m = t.get(chave_pai)
        if m is not None and str(m) not in nomes:
            raise ValueError(f"{rotulo}: troço {n!r} liga a {m!r}, inexistente")
        pai[n] = str(m) if m is not None else None
    for n in nomes:                                   # ciclos
        seen, x = set(), n
        while x is not None:
            if x in seen:
                raise ValueError(f"{rotulo}: rede com ciclo (troço {n!r})")
            seen.add(x)
            x = pai[x]
    filhos = {n: [m for m in nomes if pai[m] == n] for n in nomes}
    return nomes, pai, filhos


def rede_agua(trocos: list, p_origem_kpa: float, vmax: float = 1.5, k_sing: float = 0.2) -> dict:
    """Cálculo troço a troço. trocos = [{nome, montante, comprimento_m, desnivel_m, agua ('fria'|'quente'), dispositivos: [{tipo, quantidade}]}].
    Caudal acumulado Qa (dispositivos do troço e de jusante; água quente: só dispositivos com AQ), Qc pelo Anexo V, diâmetro pela
    velocidade ≤ vmax, perda de carga, pressão no início e no fim de cada troço (P_fim = P_início − 9,81·(ΔH + Δz))."""
    nomes, pai, filhos = _arvore(trocos, "montante", "rede de água")
    T = dict(zip(nomes, trocos))
    qa_proprio = {}
    for n in nomes:
        agua = T[n].get("agua") or "fria"
        if agua not in NU:
            raise ValueError(f"troço {n!r}: agua 'fria' ou 'quente'")
        qa_proprio[n] = sum(k * DISPOSITIVOS[t][0] for t, k in _dispositivos(T[n].get("dispositivos")) if agua == "fria" or DISPOSITIVOS[t][1])
    memo = {}

    def qa(n):
        if n not in memo:
            memo[n] = qa_proprio[n] + sum(qa(f) for f in filhos[n])
        return memo[n]

    rows, ordem = {}, [n for n in nomes if pai[n] is None]
    k = 0
    while k < len(ordem):
        ordem += filhos[ordem[k]]
        k += 1
    for n in ordem:
        t = T[n]
        agua = t.get("agua") or "fria"
        Qa = qa(n)
        Qc = caudal_calculo(Qa)
        dn, di = _tubo(Qc, vmax)
        Lt = float(t.get("comprimento_m") or 0)
        dz = float(t.get("desnivel_m") or 0)
        dH, v, J = _perda(Qc, di, Lt, agua, k_sing)
        p0 = rows[pai[n]]["p_fim_kpa"] if pai[n] else float(t.get("pressao_inicio_kpa") or p_origem_kpa)
        p1 = p0 - 9.81 * (dH + dz)
        ok_v = v <= 2.0 + 1e-9 and (v >= 0.5 - 1e-9 or dn == TUBOS_PT[0][0])
        rows[n] = {"nome": n, "montante": pai[n], "agua": agua, "comprimento_m": Lt, "desnivel_m": dz, "qa_l_s": Qa, "qc_l_s": Qc, "dn": dn, "di_mm": di,
                   "velocidade_m_s": v, "j_kpa_m": J * 9.81, "perda_kpa": dH * 9.81, "p_inicio_kpa": p0, "p_fim_kpa": p1, "terminal": not filhos[n],
                   "dispositivos": [(DISP_PT[a], b) for a, b in _dispositivos(t.get("dispositivos"))], "ok_v": ok_v,
                   "v_baixa": v < 0.5 - 1e-9}
    lst = [rows[n] for n in ordem]
    com_disp = [r for r in lst if r["dispositivos"]] or lst
    pior = min(com_disp, key=lambda r: r["p_fim_kpa"])
    return {"trocos": lst, "ponto_desfavoravel": pior["nome"], "pressao_min_kpa": pior["p_fim_kpa"]}


def _q_meia_seccao(di_mm, i):
    """L/min — Manning-Strickler, tubo circular a meia secção: A = πD²/8, R = D/4."""
    D = di_mm / 1000
    return KS_PVC * (math.pi * D * D / 8) * (D / 4) ** (2 / 3) * math.sqrt(i) * 60000


def _di_tubo_queda(qc_l_min, ts):
    """Ø interior mínimo do tubo de queda (mm): D = 4,4205·Qc^(3/8)·ts^(−5/8) (Qc em L/min; fórmula a confirmar no DR 23/95)."""
    return 4.4205 * qc_l_min ** 0.375 * ts ** (-0.625) if qc_l_min > 0 else 0.0


def rede_drenagem(trocos: list, ts: float = 1 / 7) -> dict:
    """Drenagem troço a troço. trocos = [{nome, jusante, tipo ('ramal'|'tubo_queda'|'coletor'), comprimento_m, inclinacao_pct, dispositivos}].
    Qa = descargas do troço e de montante; Qc = Anexo XV; ramais / coletores a meia secção (Manning-Strickler); tubos de queda pela
    taxa de ocupação; diâmetros nunca decrescentes para jusante; Ø ≥ maior ramal individual ligado; coletor ≥ 100 mm."""
    nomes, jus, mont = _arvore(trocos, "jusante", "rede de drenagem")
    T = dict(zip(nomes, trocos))
    memo = {}

    def calc(n):
        if n in memo:
            return memo[n]
        t = T[n]
        tipo = t.get("tipo") or "ramal"
        if tipo not in ("ramal", "tubo_queda", "coletor"):
            raise ValueError(f"troço {n!r}: tipo 'ramal', 'tubo_queda' ou 'coletor'")
        disp = _dispositivos(t.get("dispositivos"))
        up = [calc(m) for m in mont[n]]
        Qa = sum(k * DISPOSITIVOS[a][2] for a, k in disp) + sum(u["qa_l_min"] for u in up)
        Qc = caudal_calculo_drenagem(Qa)
        dmin = max([DISPOSITIVOS[a][3] for a, _ in disp] + [u["dn"] for u in up] + [50 if tipo == "tubo_queda" else 40] + ([100] if tipo == "coletor" else []))
        wc = any(a == "autoclismo" for a, _ in disp) or any(u["wc"] for u in up)
        if wc:
            dmin = max(dmin, 90)
        i = float(t.get("inclinacao_pct") or 2.0) / 100
        cands = [d for d in sorted(PVC_DRENAGEM) if d >= dmin]
        if tipo == "tubo_queda":
            need = _di_tubo_queda(Qc, ts)
            dn = next((d for d in cands if PVC_DRENAGEM[d] >= need - 1e-9), cands[-1] if cands else max(PVC_DRENAGEM))
            cap = (PVC_DRENAGEM[dn] / 4.4205 / ts ** (-0.625)) ** (8 / 3)
            ok_i = None
        else:
            dn = next((d for d in cands if _q_meia_seccao(PVC_DRENAGEM[d], i) >= Qc - 1e-9), cands[-1] if cands else max(PVC_DRENAGEM))
            cap = _q_meia_seccao(PVC_DRENAGEM[dn], i)
            ok_i = 0.01 - 1e-9 <= i <= 0.04 + 1e-9
        memo[n] = {"nome": n, "jusante": jus[n], "tipo": tipo, "comprimento_m": float(t.get("comprimento_m") or 0), "inclinacao_pct": i * 100 if tipo != "tubo_queda" else None,
                   "qa_l_min": Qa, "qc_l_min": Qc, "dn": dn, "di_mm": PVC_DRENAGEM[dn], "capacidade_l_min": cap, "ok": Qc <= cap + 1e-6, "ok_inclinacao": ok_i,
                   "wc": wc, "dispositivos": [(DISP_PT[a], k) for a, k in disp]}
        return memo[n]

    for n in nomes:
        calc(n)
    # ordem de montante para jusante
    ordem, feitos = [], set()

    def visita(n):
        for m in mont[n]:
            visita(m)
        if n not in feitos:
            feitos.add(n)
            ordem.append(memo[n])

    for n in nomes:
        if jus[n] is None:
            visita(n)
    return {"trocos": ordem, "taxa_ocupacao": ts}


def canalizacao(p: dict) -> dict:
    """p : {dispositivos: [{tipo, quantidade}], velocidade_max_m_s, comprimento_m, desnivel_m, pressao_rede_kpa,
            rede: [{nome, montante, comprimento_m, desnivel_m, agua, dispositivos}],            (abastecimento troço a troço, opcional)
            rede_drenagem: [{nome, jusante, tipo, comprimento_m, inclinacao_pct, dispositivos}], ventilacao_secundaria (bool)}"""
    disp = p.get("dispositivos") or []
    rede = p.get("rede") or []
    if not disp and rede:                              # dispositivos deduzidos da rede descrita
        cnt: dict = {}
        for t in rede:
            if (t.get("agua") or "fria") == "fria":
                for a, k in _dispositivos(t.get("dispositivos")):
                    cnt[a] = cnt.get(a, 0) + k
        disp = [{"tipo": a, "quantidade": k} for a, k in cnt.items()]
    if not disp:
        raise ValueError("indicar os dispositivos (tipo e quantidade)")
    qa_f = qa_q = desc = 0.0
    n_wc = 0
    rows = []
    for t, n in _dispositivos(disp):
        q, aq, qd, dd = DISPOSITIVOS[t]
        qa_f += n * q
        qa_q += n * q if aq else 0.0
        desc += n * qd
        n_wc += n if t == "autoclismo" else 0
        rows.append({"dispositivo": t, "n": n, "q": q, "aq": aq, "descarga_l_min": qd, "ramal_descarga": dd})
    qc = caudal_calculo(qa_f)
    qcq = caudal_calculo(qa_q) if qa_q else 0.0
    vmax = float(p.get("velocidade_max_m_s") or 1.5)
    tubo = _tubo(qc, vmax)
    v = _v(qc, tubo[1])
    tubo_q = _tubo(qcq, vmax) if qcq else None
    # perda de carga (Darcy, Blasius) até ao dispositivo mais desfavorável
    Lr = float(p.get("comprimento_m") or 25)
    Re = v * tubo[1] / 1000 / 1.0e-6
    f = 0.316 / Re ** 0.25 if Re > 0 else 0.0
    j = f * (Lr * 1.2) / (tubo[1] / 1000) * v * v / 2 / 9.81                     # m (+20 % singularidades)
    h = float(p.get("desnivel_m") or 3)
    pst = float(p.get("pressao_rede_kpa") or 300)
    pres = pst - (j + h) * 9.81
    hip = [f"caudal de cálculo pela curva do Anexo V em forma analítica (troços confirmados por fonte secundária); Qa = {_c(qa_f, 2)} L/s → Qc = {_c(qc, 2)} L/s",
           "caudais do chuveiro (0,15 L/s) e da torneira exterior não confirmados no texto oficial; pressões 50 / 600 kPa a confirmar (art. 87.º)"]
    rd = None
    if rede:
        rd = rede_agua(rede, pst, vmax)
        pres = rd["pressao_min_kpa"]
        hip.append("rede descrita troço a troço: Darcy-Weisbach (Blasius), +20 % de singularidades; água quente a ≈ 60 °C; a rede de água quente parte "
                   "à pressão do troço a montante (perdas no aparelho de produção não contadas)")
    elif p.get("comprimento_m") is None:
        hip.append(f"percurso até ao dispositivo mais desfavorável não descrito: {_g(Lr)} m com o diâmetro do ramal geral e desnível {_g(h)} m")
    if p.get("pressao_rede_kpa") is None:
        hip.append(f"pressão disponível na rede {_g(pst)} kPa por defeito (pedir o valor à entidade gestora)")
    qd = caudal_calculo_drenagem(desc)
    tq = 100 if n_wc else 75
    ctl = [{"ref": "Velocidade (DR 23/95, art. 94.º)", "exigencia": f"0,5 a 2,0 m/s (adotado ≤ {_g(vmax)})", "valor": f"{_c(v, 2)} m/s em Ø{tubo[0]}",
            "ok": 0.5 <= v <= 2.0 or qc < 0.2},
           {"ref": "Pressão no dispositivo mais desfavorável", "exigencia": f"≥ {P_MIN_KPA:.0f} kPa (recomendado 150–300 kPa); estática ≤ {P_MAX_KPA:.0f} kPa (art. 87.º, a confirmar)",
            "valor": f"{pres:.0f} kPa (rede {_g(pst)} kPa" + (f", troço {rd['ponto_desfavoravel']})" if rd else ")"),
            "ok": pres >= P_MIN_KPA and pst <= P_MAX_KPA,
            "note": "redutor de pressão" if pst > P_MAX_KPA else ("sobrepressora" if pres < P_MIN_KPA else
                                                                 ("abaixo do conforto recomendado" if pres < 150 else None))}]
    if rd:
        lentos = [r["nome"] for r in rd["trocos"] if not r["ok_v"]]
        baixos = [r["nome"] for r in rd["trocos"] if r["v_baixa"] and r["ok_v"]]
        ctl.append({"ref": "Velocidade em cada troço (art. 94.º)", "exigencia": "0,5 a 2,0 m/s",
                    "valor": f"{_c(min(r['velocidade_m_s'] for r in rd['trocos']), 2)} a {_c(max(r['velocidade_m_s'] for r in rd['trocos']), 2)} m/s",
                    "ok": not lentos, "note": ("troços fora do intervalo: " + ", ".join(lentos)) if lentos else
                    (("< 0,5 m/s com o menor diâmetro (aceitável, ramais de um dispositivo): " + ", ".join(baixos)) if baixos else None)})
    drn = None
    if p.get("rede_drenagem"):
        ts = float(p.get("taxa_ocupacao") or (1 / 3 if p.get("ventilacao_secundaria") else 1 / 7))
        drn = rede_drenagem(p["rede_drenagem"], ts)
        maus = [r["nome"] for r in drn["trocos"] if not r["ok"]]
        incl = [r["nome"] for r in drn["trocos"] if r["ok_inclinacao"] is False]
        ctl.append({"ref": "Drenagem — capacidade dos troços", "exigencia": f"ramais e coletores a meia secção (Ks {_g(KS_PVC)}); tubos de queda com taxa de "
                                                                          f"ocupação ≤ {_c(ts, 3)}",
                    "valor": f"{len(drn['trocos'])} troços, Qc máx. {max(r['qc_l_min'] for r in drn['trocos']):.0f} L/min", "ok": not maus,
                    "note": ("insuficientes: " + ", ".join(maus)) if maus else None})
        if any(r["ok_inclinacao"] is not None for r in drn["trocos"]):
            ctl.append({"ref": "Drenagem — inclinação de ramais e coletores", "exigencia": "10 a 40 mm/m (1 a 4 %)",
                        "valor": ", ".join(f"{r['nome']} {_g(r['inclinacao_pct'])} %" for r in drn["trocos"] if r["inclinacao_pct"] is not None),
                        "ok": not incl})
        hip.append(f"drenagem troço a troço: Manning-Strickler Ks = {_g(KS_PVC)} m^(1/3)/s (PVC), altura de escoamento ≤ 0,5·D; tubo de queda "
                   f"D = 4,4205·Qc^(3/8)·ts^(−5/8) com ts = {_c(ts, 3)} ({'com' if p.get('ventilacao_secundaria') else 'sem'} ventilação secundária) — "
                   "fórmula e taxa de ocupação a confirmar no DR 23/95; coletor predial Ø ≥ 100 mm (fonte secundária, a confirmar); diâmetros interiores "
                   "PVC indicativos; ramais individuais a secção cheia (Anexo XVI) não considerados")
        tq = max([r["dn"] for r in drn["trocos"] if r["tipo"] == "tubo_queda"] or [tq])
    hip.append(f"drenagem: caudal de cálculo {qd:.0f} L/min para {desc:.0f} L/min acumulados (Anexo XV, Qc = 7,3497·Qa^0,5352 limitado a Qa, a confirmar), "
               "ramais com inclinação de 10 a 40 mm/m")
    coletor = max([r["dn"] for r in (drn or {}).get("trocos", []) if r["tipo"] == "coletor"] or [100 if n_wc else 75])
    return {"dispositivos": rows, "qa_l_s": qa_f, "qc_l_s": qc, "qa_aq_l_s": qa_q, "qc_aq_l_s": qcq, "tubo_af": f"Ø{tubo[0]} (int. {_g(tubo[1])} mm)",
            "tubo_aq": f"Ø{tubo_q[0]}" if tubo_q else None, "velocidade_m_s": v, "pressao_kpa": pres, "pressao_rede_kpa": pst,
            "drenagem_qa_l_min": desc, "drenagem_qc_l_min": qd, "tubo_queda_mm": tq, "coletor_mm": coletor,
            "rede": rd, "rede_drenagem": drn, "controles": ctl, "hipoteses": hip,
            "regras": ["ramais de descarga com inclinação de 10 a 40 mm/m, troço vertical ≤ 2 m; bacia de retrete Ø90 mínimo",
                       f"tubo de queda Ø{tq} com taxa de ocupação ≤ 1/3 (ventilação secundária) ou ≤ 1/7 (sem); ventilação 0,50 m acima da cobertura",
                       "coletores prediais Ø ≥ 100 mm, meia secção, câmaras de inspeção a ≤ 15 m; fecho hídrico dos sifões 50–75 mm",
                       "AQS produzida a ≥ 60 °C (prevenção da legionela), utilização com misturadora"]}


def note(params: dict) -> dict:
    from . import notes
    kp = []
    blocs, hip, out = [("p", "Pré-dimensionamento indicativo — não substitui os projetos de especialidade (eletricidade, ITED, águas e esgotos).")], [], {}
    n = 1
    if params.get("eletricidade") is not None:
        r = eletricidade(params["eletricidade"])
        out["eletricidade"] = r
        blocs += notes.blocos_eletricidade(r, f"{n}. ")
        hip += r["hipoteses"]; n += 1
        kp += [{"label": "Potência a contratar", "value": _g(r["potencia_contratada_kva"]), "unit": "kVA"},
               {"label": "Circuitos", "value": str(len(r["circuitos"])), "ok": r["controles"][0]["ok"]},
               {"label": "Diferenciais 30 mA", "value": str(r["diferenciais"])}]
    if params.get("canalizacao") is not None:
        r = canalizacao(params["canalizacao"])
        out["canalizacao"] = r
        blocs += notes.blocos_canalizacao(r, f"{n}. ")
        hip += r["hipoteses"]
        kp += [{"label": "Caudal de cálculo Qc", "value": _c(r["qc_l_s"], 2), "unit": "L/s"},
               {"label": "Ramal geral (água fria)", "value": r["tubo_af"].split(" ")[0]},
               {"label": "Pressão no dispositivo mais desfavorável", "value": f"{r['pressao_kpa']:.0f}", "unit": "kPa", "ok": r["controles"][1]["ok"]}]
    if not out:
        raise ValueError("indicar eletricidade e/ou canalizacao")
    titre = "Pré-dimensionamento — instalações (" + ", ".join({"eletricidade": "eletricidade", "canalizacao": "canalização"}[k] for k in out) + ")"
    pdf, png = notes.pdf(titre, "RTIEBT · DR 23/95", [("kpis", kp)] + blocs, hip)
    return {**out, "titre": titre, "pdf": pdf, "png": png}
