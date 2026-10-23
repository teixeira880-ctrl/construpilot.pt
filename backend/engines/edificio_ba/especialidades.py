"""Especialidades (Portugal) por fração e por edifício : comportamento térmico (REH), pichelaria (águas, esgotos, pluviais — DR 23/95)
e eletricidade (RTIEBT). Motores ConstruPilot PT : calc_lots.reh, aquecimento, instalacoes, redes. Estudos prévios indicativos.

Divisões das frações (rooms[].kind) : sala, quarto, cozinha, casa_de_banho, lavandaria, corredor, escritorio, arrumos.
"""
from __future__ import annotations

import math
from pathlib import Path

from reportlab.lib.units import mm

from .textos import fmt as f

W = mm
U = {"parede": 0.32, "enu": 0.62, "cobertura": 0.31, "pavimento": 0.29, "envidracado": 1.60, "porta": 1.80, "g": 0.50}
COEF = [(4, 1.00), (9, 0.78), (14, 0.63), (19, 0.53), (24, 0.49), (29, 0.46), (34, 0.44), (39, 0.42), (49, 0.41), (10 ** 6, 0.38)]
IZ = [(10, 60), (16, 80), (25, 101), (35, 126), (50, 153), (70, 196), (95, 238), (120, 276), (150, 319), (185, 364), (240, 430)]
PEAD = [(32, 26.2), (40, 32.6), (50, 40.8), (63, 51.4), (75, 61.4), (90, 73.6), (110, 90.0)]
KINDS = {"sala", "quarto", "cozinha", "casa_de_banho", "lavandaria", "corredor", "escritorio", "arrumos"}


def _mods():
    from engines.calc_lots import aquecimento, instalacoes, redes, reh
    return reh, aquecimento, instalacoes, redes


def _area(u):
    return sum(float(r.get("area") or 0) for r in u.get("rooms") or [])


def _tip(u) -> int:
    t = str(u.get("typology") or "")
    if t.upper().startswith("T") and t[1:2].isdigit():
        return int(t[1])
    return max(1, sum(1 for r in u.get("rooms") or [] if r.get("kind") == "quarto"))


def _n_wc(u):
    return max(1, sum(1 for r in u.get("rooms") or [] if r.get("kind") == "casa_de_banho"))


# ------------------------------------------------------------------ térmica
def _envelope(S, u):
    ch = S.clear_h
    ot = S.opening_types
    env, hp, Lf = [], 0.0, 0.0
    glaz = {}
    for o in u.get("openings") or []:
        d = ot.get(o["type"]) or {}
        glaz[o.get("facade")] = glaz.get(o.get("facade"), 0.0) + int(o.get("count") or 1) * float(d.get("width") or 0) * float(d.get("height") or 0)
    for fa in u.get("facades") or []:
        o = (fa.get("orientation") or "S").upper().replace("W", "O")
        Lx = float(fa.get("length") or 0)
        aw = glaz.get(o, 0.0)
        env.append({"tipo": "parede", "area_m2": round(max(Lx * ch - aw, 0.5), 2), "U": U["parede"], "orientacao": o})
        side = S.side_of_orientation(o)
        shaded = any(b["side"] == side for b in S.balconies) if side else False
        if aw:
            n_v = max(1, round(aw / 3.6))
            env.append({"tipo": "envidracado", "area_m2": round(aw, 2), "U": U["envidracado"], "orientacao": o, "g": U["g"],
                        "Fs": 0.60 if shaded else 0.85, "Fs_v": 0.45 if shaded else 0.80})
            hp += 0.10 * n_v * 4 * math.sqrt(aw / n_v)
        Lf += Lx
    hp += 0.25 * Lf + 0.10 * ch * max(len(u.get("facades") or []) - 1, 0)
    cw = float(u.get("common_wall_m") or 0)
    if cw:
        env.append({"tipo": "parede", "area_m2": round(max(cw * ch - 2.0, 0.5), 2), "U": U["enu"], "fronteira": "enu", "btr": 0.6})
        env.append({"tipo": "porta", "area_m2": 2.0, "U": U["porta"], "fronteira": "enu", "btr": 0.6})
    ap = _area(u)
    lvl = int(u.get("level", 0))
    if lvl == S.n - 1:
        env.append({"tipo": "cobertura", "area_m2": round(1.10 * ap, 1), "U": U["cobertura"], "orientacao": "H"})
        hp += 0.30 * Lf
    if lvl == 0:
        if S.basement:
            env.append({"tipo": "pavimento", "area_m2": round(1.10 * ap, 1), "U": U["pavimento"], "fronteira": "enu", "btr": 0.9})
        else:
            env.append({"tipo": "pavimento", "area_m2": round(1.10 * ap, 1), "U": U["pavimento"], "fronteira": "solo"})
        hp += 0.20 * Lf
    return env, hp


def termico(S):
    reh, aq, _, _ = _mods()
    ap_tot = sum(_area(u) for u in S.units) or 1.0
    pv = float(S.systems.get("pv_kwp") if S.systems.get("pv_kwp") is not None else round(min(0.6 * len(S.units), 0.5 * S.area_floor / 5.5), 1))
    e_pv = pv * 1520.0 * 0.60
    out = []
    for u in S.units:
        env, hp = _envelope(S, u)
        tip = _tip(u)
        p = {"area_util_m2": _area(u), "pe_direito_m": S.clear_h, "tipo": "apartamento", "obra": "nova", "concelho": S.municipality or None,
             "altitude_m": S.altitude, "envolvente": env, "pontes_termicas_w_c": round(hp, 2), "inercia": "forte", "tipologia": tip, "rph": 0.6,
             "ventilacao_mecanica": True, "aquecimento": {"tipo": "split_ar_ar", "eficiencia": 4.0}, "arrefecimento": {"eer": 4.0},
             "aqs": {"tipo": "bomba_calor", "eficiencia": 3.0}}
        if e_pv:
            p["renovavel_kwh"] = round(e_pv * _area(u) / ap_tot, 0)
            p["renovavel_tipo"] = "fotovoltaico"
        r = reh.calcular(p)
        hyp = []
        te, _ = aq.theta_projeto({"concelho": S.municipality or None, "altitude_m": S.altitude}, hyp)
        out.append({"id": u["id"], "level": int(u["level"]), "tip": f"T{tip}", "Ap": _area(u), "r": r, "phi": (r["Htr"] + r["Hve"]) * (20 - te), "te": te})
    return {"units": out, "pv_kwp": pv, "e_pv": e_pv}


# ------------------------------------------------------------------ pichelaria
def _devices(u):
    n = _n_wc(u)
    d = {"lavatorio": n, "autoclismo": n, "chuveiro": 1, "bide": 1, "lava_loica": 1, "maquina_lavar_loica": 1, "maquina_lavar_roupa": 1}
    if n >= 2:
        d["banheira"] = 1
    return d


def _tubo(q, tubos, vmax=1.5):
    for dn, di in tubos:
        v = q / 1000 / (math.pi * (di / 1000) ** 2 / 4)
        if v <= vmax:
            return dn, di, v
    dn, di = tubos[-1]
    return dn, di, q / 1000 / (math.pi * (di / 1000) ** 2 / 4)


def _j(q, di):
    v = q / 1000 / (math.pi * (di / 1000) ** 2 / 4)
    Re = v * di / 1000 / 1.0e-6
    lam = 0.316 / Re ** 0.25 if Re > 0 else 0
    return lam / (di / 1000) * v * v / 2 / 9.81


def _qd(dl):
    return dl if dl <= 270 else 7.3497 * dl ** 0.5352


def pichelaria(S):
    _, _, INS, redes = _mods()
    D = INS.DISPOSITIVOS
    fr = []
    for u in S.units:
        d = _devices(u)
        qa = sum(n * D[k][0] for k, n in d.items())
        qaq = sum(n * D[k][0] for k, n in d.items() if D[k][1])
        qc, qcq = INS.caudal_calculo(qa), INS.caudal_calculo(qaq)
        fr.append({"id": u["id"], "level": int(u["level"]), "tip": f"T{_tip(u)}", "d": d, "qa": qa, "qc": qc, "qcq": qcq,
                   "af": _tubo(qc, INS.TUBOS_PT), "aq": _tubo(qcq, INS.TUBOS_PT), "desc": sum(n * D[k][2] for k, n in d.items()),
                   "z": S.z0 + S.H * int(u["level"])})
    extra = 0.30 * (2 if S.basement else 1) + (0.20 if S.basement else 0.0)
    q_tot = sum(x["qa"] for x in fr) + extra
    qc_tot = INS.caudal_calculo(q_tot)
    rl = _tubo(qc_tot, PEAD)
    col = []
    for k in range(S.n):
        qa_k = sum(x["qa"] for x in fr if x["level"] >= k)
        qc_k = INS.caudal_calculo(qa_k)
        dn, di, v = _tubo(qc_k, PEAD)
        col.append({"troco": (S.t("Entrada → ", "Entrée → ") if k == 0 else S.lname(k - 1) + " → ") + S.lname(k), "qa": qa_k, "qc": qc_k, "dn": dn, "v": v,
                    "L": S.H if k else 6.0, "j": _j(qc_k, di)})
    P = float(S.network.get("water_pressure_kpa") or 300.0)
    zst = float(S.network.get("street_level") or S.z0)
    J_rl = _j(qc_tot, rl[1]) * 25 * 1.2
    J_col = sum(c["j"] * c["L"] for c in col) * 1.2
    top = max(fr, key=lambda x: (x["level"], x["qa"])) if fr else None
    J_fr = (_j(top["qc"], top["af"][1]) * 18 * 1.3 + 3.0) if top else 0.0
    dz = (top["z"] + 1.8 - zst) if top else 0.0
    p_top = P - (J_rl + J_col + J_fr + dz) * 9.81
    p_low = P - (1.8 + 0.3 - (zst - S.z0)) * 9.81
    aqs = []
    for t_ in sorted({x["tip"] for x in fr}):
        n = int(t_[1:])
        oc = {0: 2, 1: 2, 2: 3, 3: 4, 4: 5}.get(n, n + 1)
        aqs.append({"tip": t_, "oc": oc, "l_dia": 40 * oc, "vol": 150 if n <= 1 else 200 if n <= 3 else 300})
    # tubos de queda por « posição » de fração (mesma ordem em cada piso)
    pos = {}
    for k in range(S.n):
        for i, u in enumerate([u for u in S.units if int(u["level"]) == k]):
            pos.setdefault(i, []).append(u)
    WC = ("lavatorio", "autoclismo", "chuveiro", "bide", "banheira")
    tq = []
    for i, us in pos.items():
        for kind, lab in (("wc", S.t("instalações sanitárias", "sanitaires")), ("coz", S.t("cozinha e máquinas", "cuisine et machines"))):
            dl = 0.0
            n_wc = 0
            for u in us:
                for k, n in _devices(u).items():
                    if (k in WC) == (kind == "wc"):
                        dl += n * D[k][2]
                        n_wc += n if k == "autoclismo" else 0
            qd = _qd(dl)
            dmin = 4.4205 * qd ** (3 / 8) * (1 / 3) ** (-5 / 8)
            dn = next(d_ for d_ in redes.DIAM_PVC if redes.DI_PVC[d_] >= dmin)
            dn = max(dn, 110 if n_wc else 75)
            tq.append({"nome": f"TQ{len(tq) + 1}", "desc": f"{lab} — {S.t('frações', 'logements')} {', '.join(u['id'] for u in us)}", "dl": dl, "qd": qd, "dmin": dmin,
                       "dn": dn})
    dl_tot = sum(x["desc"] for x in fr)
    qd_tot = _qd(dl_tot)
    ks = 120

    def cap_meia(dn, i=0.01):
        di = redes.DI_PVC[dn] / 1000
        return ks * math.pi * di ** 2 / 8 * (di / 4) ** (2 / 3) * math.sqrt(i) * 1000 * 60

    col_dn = next((d_ for d_ in redes.DIAM_PVC if d_ >= 110 and cap_meia(d_) >= qd_tot), 200)
    I = redes.intensidade("A", 5, 5)
    roof = S.area_floor + S.balcony_area()
    n_tq_roof = max(2, math.ceil(roof / 100))
    zonas = [(S.t("Cobertura", "Toiture-terrasse"), roof, n_tq_roof)]
    from .medicoes import _footprint_overlap
    A_out = _footprint_overlap(S)
    if A_out > 1:
        zonas.append((S.t("Laje sobre a cave — terraços e jardins", "Dalle sur sous-sol — terrasses et jardins"), A_out, max(2, math.ceil(A_out / 80))))
    if S.basement:
        zonas.append((S.t("Rampa de acesso à cave (grelha + bombagem)", "Rampe d'accès au sous-sol (caniveau + relevage)"), 60.0, 1))
    plu = []
    for nm, A, n in zonas:
        Q = I / 3600 * A
        q1 = Q / n
        dn = next((d_ for d_ in redes.DIAM_PVC if d_ >= 90 and redes._q_tubo_queda(redes.DI_PVC[d_]) >= q1), 200)
        plu.append({"zona": nm, "A": A, "Q": Q, "n": n, "dn": dn, "cap": redes._q_tubo_queda(redes.DI_PVC[dn])})
    Qp = sum(x["Q"] for x in plu if x["n"] > 1 or not S.basement)

    def cap_cheia(dn, i=0.01):
        di = redes.DI_PVC[dn] / 1000
        return ks * math.pi * di ** 2 / 4 * (di / 4) ** (2 / 3) * math.sqrt(i) * 1000
    colp = next((d_ for d_ in redes.DIAM_PVC if d_ >= 110 and cap_cheia(d_) >= Qp), 200)
    ee = None
    if S.basement:
        q_ramp = I / 3600 * 60.0
        Ld = sum(math.dist(S.bpoly[w["i0"]], S.bpoly[w["i1"]]) for w in S.bwalls if w["ht"] > 0)
        q_dr = Ld * 0.02
        ee = {"q": q_ramp + q_dr + 0.5, "vol": q_ramp * 15 * 60 / 1000 * 0.5 + 1.0}
    return {"fr": fr, "q_tot": q_tot, "qc_tot": qc_tot, "rl": rl, "col": col, "J": (J_rl, J_col, J_fr, dz), "p_top": p_top, "p_low": p_low, "P": P,
            "top": top["id"] if top else None, "aqs": aqs, "tq": tq, "dl_tot": dl_tot, "qd_tot": qd_tot, "col_dn": col_dn, "cap_col": cap_meia(col_dn),
            "I": I, "plu": plu, "Qp": Qp, "colp": colp, "cap_colp": cap_cheia(colp), "ee": ee}


# ------------------------------------------------------------------ eletricidade
def eletricidade(S, TH):
    _, _, INS, _ = _mods()
    phi = {x["id"]: x["phi"] for x in TH["units"]}
    fr = []
    for u in S.units:
        div = [{"tipo": r["kind"] if r.get("kind") in KINDS else "arrumos", "nome": r.get("name"), "area_m2": float(r.get("area") or 0)} for r in u.get("rooms") or []]
        div.append({"tipo": "lavandaria", "nome": S.t("Lavandaria / zona técnica", "Buanderie / local technique"), "area_m2": 1.2})
        kw = max(1.0, round(phi.get(u["id"], 2000) / 1000 / 3.0, 1))
        r = INS.eletricidade({"divisoes": div, "equipamentos": {"placa": True, "forno": True, "maquina_lavar_roupa": True, "maquina_lavar_loica": True,
                                                               "termoacumulador": True, "bomba_calor_kw": kw}, "comprimento_medio_circuito_m": 14})
        for c in r["controles"]:
            c["ref"] = c["ref"].replace("Termoacumulador", "Bomba de calor de AQS").replace("— Bomba de calor", "— Climatização")
        for c in r["circuitos"]:
            if c["nome"] == "Termoacumulador":
                c["nome"] = "Bomba de calor de AQS (com apoio)"
            elif c["nome"].startswith("Bomba de calor"):
                c["nome"] = "Climatização (multi-split)"
        coz = sum(c["p_w"] or 0 for c in r["circuitos"] if c["nome"].startswith(("Placa", "Forno", "Máquina")))
        p_dim = 25 * _area(u) + 0.30 * coz + 600 + 1000 * kw
        tip = _tip(u)
        kva = 6.9 if tip <= 2 else 10.35 if tip <= 4 else 13.8
        fr.append({"id": u["id"], "tip": f"T{tip}", "el": r, "kva": kva, "bc_kw": kw, "p_dim": p_dim})
    n = len(fr)
    coef = next(c for lim, c in COEF if n <= lim)
    p_fr = sum(x["kva"] for x in fr)
    p_col = p_fr * coef
    lifts = sum(1 for c in S.cores if c["kind"] == "lift")
    stairs = max(1, sum(1 for c in S.cores if c["kind"] == "stair"))
    SC = []
    if lifts:
        SC.append((f"Elevador ({S.n + (1 if S.basement else 0)} paragens) × {lifts}", 7.5 * lifts, "tri"))
    SC.append(("Iluminação de escada, hall e átrio (LED + emergência)", 0.25 * (S.n + 1) * stairs, "mono"))
    if S.basement:
        A_c = S.basement_area()
        SC += [(f"Iluminação da cave ({f(A_c, 0)} m² × 5 W/m²) + emergência", round(A_c * 0.005, 1), "mono"),
               ("Ventilação / desenfumagem da cave", round(max(2.2, A_c / 140), 1), "tri"), ("Portão automático da garagem", 0.75, "mono"),
               ("Estação elevatória da cave (2 bombas, 1 de reserva)", 2.2, "tri")]
    SC += [("Deteção de incêndio/CO, intercomunicadores, ITED", 0.8, "mono"), ("Grupo hidropressor (se necessário)", 2.2, "tri")]
    if S.parking:
        SC.append((f"Carregamento de veículos elétricos — {S.parking} lugares com gestão dinâmica", round(max(7.4, 1.1 * S.parking), 1), "tri"))
    p_sc = sum(p for _, p, _ in SC)
    sc_kva = next((e for e in [6.9, 10.35, 13.8, 17.25, 20.7, 27.6, 34.5, 41.4] if e >= p_sc / 0.9 * 0.8), 41.4)
    p_ed = p_col + p_sc / 0.9 * 0.8
    I_col = p_col * 1000 / (math.sqrt(3) * 400)
    In = next((c for c in (63, 80, 100, 125, 160, 200, 250, 315, 400) if c >= I_col), 400)
    Lc = 4.0 + S.H * S.n
    for s_, iz in IZ:
        du = math.sqrt(3) * (0.0225 * Lc / s_ * 0.95) * I_col / 400 * 100
        if iz >= In and du <= 1.5:
            break
    der = []
    for kva in sorted({x["kva"] for x in fr}):
        Ii = kva * 1000 / 230
        dj = next(c for c in (16, 20, 25, 32, 40, 50, 63) if c >= Ii)
        for sd in (6, 10, 16, 25):
            du2 = 2 * 0.0225 * 15 / sd * Ii / 230 * 100
            if du2 <= 1.0 and {6: 41, 10: 57, 16: 76, 25: 101}[sd] >= dj:
                break
        der.append({"kva": kva, "dj": dj, "s": sd, "du": du2, "n": sum(1 for x in fr if x["kva"] == kva)})
    return {"fr": fr, "coef": coef, "p_fr": p_fr, "p_col": p_col, "SC": SC, "p_sc": p_sc, "sc_kva": sc_kva, "p_ed": p_ed,
            "col": {"I": I_col, "In": In, "s": s_, "iz": iz, "du": du, "L": Lc}, "der": der}


def calcular(S, R) -> dict:
    if S.country != "PT":
        raise RuntimeError("especialidades PT : perfil FR usa o módulo francês")
    TH = termico(S)
    PI = pichelaria(S)
    EL = eletricidade(S, TH)
    cl = sorted({x["r"]["classe"] for x in TH["units"]})
    return {"TH": TH, "PI": PI, "EL": EL, "summary": {"classes": cl, "pv_kwp": TH["pv_kwp"], "qc_l_s": round(PI["qc_tot"], 2),
                                                       "p_top_kpa": round(PI["p_top"], 0), "kva_edificio": round(EL["p_ed"], 0)}}


# ------------------------------------------------------------------ PDF
def pdfs(S, R, MEP, out: Path, stem: str) -> dict:
    from engines.calc_lots import graficos as G
    from engines.calc_lots import rendu
    reh = _mods()[0]
    TH, PI, EL = MEP["TH"], MEP["PI"], MEP["EL"]
    sub = f"{S.name} · {S.municipality} · {len(S.units)} frações"
    files = {}
    # ---------------- térmica
    us = TH["units"]
    c = us[0]["r"]["clima"]
    ri = c["ri"]
    nic = sum(x["r"]["Nic"] * x["Ap"] for x in us) / sum(x["Ap"] for x in us)
    ni = sum(x["r"]["Ni"] * x["Ap"] for x in us) / sum(x["Ap"] for x in us)
    cls = [x["r"]["classe"] for x in us]
    b = [("kpis", [{"label": "Classes energéticas", "value": " / ".join(sorted(set(cls))), "ok": all(x["r"]["RNt"] <= 0.5 for x in us)},
                   {"label": "Nic/Ni médio", "value": f(nic / ni, 2)}, {"label": "Zona climática", "value": f"{c['zona_i']} / {c['zona_v']}"},
                   {"label": "Potência de aquecimento", "value": f(sum(x["phi"] for x in us) / 1000, 0), "unit": "kW"}])]
    b.append(("p", "Estudo prévio de comportamento térmico (REH — DL 101-D/2020, Portaria 138-I/2021, Despacho 6476-E/2021), fração a fração. Pré-certificado "
                   "INDICATIVO : o projeto térmico e o pré-certificado SCE devem ser elaborados por técnico habilitado / Perito Qualificado (ADENE)."))
    b.append(("table", ["Parâmetro", "Valor"], [["Concelho / NUTS III", f"{S.municipality} / {c['nuts']}"], ["Altitude", f"{f(c['altitude_m'], 0)} m"],
                                              ["GD / M", f"{f(c['GD'], 0)} °C.dia / {f(c['M'], 1)} meses"], ["Zonas", f"{c['zona_i']} / {c['zona_v']}"],
                                              ["θe de projeto", f"{f(us[0]['te'], 1)} °C"], ["Fachada principal", S.front]], [80 * W, 100 * W]))
    sol = [("Parede exterior", "Tijolo 15 + ETICS EPS grafite 8 cm", U["parede"], reh.UMAX["parede"][ri]),
           ("Parede para espaço comum", "Tijolo 11 + lã mineral 4 cm", U["enu"], reh.UMAX_INT["parede"][ri]),
           ("Cobertura", "Cobertura invertida XPS 10 cm", U["cobertura"], reh.UMAX["cobertura"][ri]),
           ("Pavimento sobre cave / solo", "XPS 10 cm sob betonilha", U["pavimento"], reh.UMAX["pavimento"][ri]),
           ("Vãos", "Alumínio RPT, vidro duplo baixo-emissivo, g⊥ 0,50, estore", U["envidracado"], reh.UW_MAX[ri])]
    b.append(("table", ["Elemento", "Solução proposta", "U", "Umáx"], [[a, s_, f(u_, 2), f(m_, 2)] for a, s_, u_, m_ in sol], [42 * W, 92 * W, 22 * W, 22 * W]))
    b.append(("table", ["Uso", "Sistema"], [["Aquecimento / arrefecimento", "Bomba de calor ar-ar multi-split (SCOP 4,0)"],
                                            ["AQS", "Bomba de calor com depósito (COP 3,0)"], ["Ventilação", "Mecânica simples fluxo, Rph 0,6 h⁻¹"],
                                            ["Renováveis", f"Fotovoltaico comum {f(TH['pv_kwp'], 1)} kWp em autoconsumo coletivo (60 %)"]], [50 * W, 130 * W]))
    rows = [[x["id"], S.lname(x["level"]), x["tip"], f(x["Ap"], 1), f(x["r"]["Nic"], 1), f(x["r"]["Ni"], 1), f(x["r"]["Nvc"], 1), f(x["r"]["Ntc"], 1),
             f(x["r"]["RNt"], 2), x["r"]["classe"], f(x["phi"] / 1000, 2)] for x in us]
    b.append(("table", ["Fr.", "Piso", "Tip.", "Ap m²", "Nic", "Ni", "Nvc", "Ntc", "RNt", "Classe", "Φ kW"], rows,
              [10 * W, 16 * W, 11 * W, 15 * W, 16 * W, 16 * W, 16 * W, 18 * W, 16 * W, 16 * W, 16 * W]))
    b.append(("chart", G.barres_h([(f"{x['id']} · {S.lname(x['level'])} · {x['tip']}", x["r"]["RNt"]) for x in us], "RNt por fração", "", ref=(0.50, "NZEB 0,50"), dec=2),
              "Classe A+ se RNt ≤ 0,25 ; A se ≤ 0,50 (mínimo para edifícios novos)."))
    worst = {}
    for x in us:
        for ct in x["r"]["controles"]:
            if ct["ref"] not in worst or (ct.get("taux") or 0) > (worst[ct["ref"]].get("taux") or 0):
                worst[ct["ref"]] = {**ct, "fr": x["id"]}
    b.append(("controls", [{"ref": v["ref"] + f" — fração {v['fr']}", "exigence": v["exigencia"], "valeur": v["valor"],
                            "ok": None if v["ok"] is None else bool(v["ok"])} for v in worst.values()]))
    hyp = ["Envolvente por fração a partir dos comprimentos de fachada e vãos do levantamento ; frações adjacentes aquecidas sem trocas.",
           "Espaços comuns btr 0,6 ; cave btr 0,9 ; eficiências a confirmar nas fichas técnicas."] + [h for h in us[0]["r"]["hipoteses"] if "Perito" in h]
    p = out / f"Estudo_termico_REH_{stem}.pdf"
    p.write_bytes(rendu.build_pdf(f"Estudo térmico (REH) — {len(us)} frações", sub, b + [("h2", "Hipóteses"), ("hyp", hyp)],
                                  footer="ConstruPilot — pré-certificado indicativo REH ; não substitui o projeto térmico nem o certificado SCE."))
    files["termico"] = p
    # ---------------- pichelaria
    J_rl, J_col, J_fr, dz = PI["J"]
    b = [("kpis", [{"label": "Caudal de cálculo", "value": f(PI["qc_tot"], 2), "unit": "L/s"}, {"label": "Ramal de ligação", "value": f"PEAD Ø{PI['rl'][0]}"},
                   {"label": "Pressão no último piso", "value": f(PI["p_top"], 0), "unit": "kPa", "ok": PI["p_top"] >= 100},
                   {"label": "Coletor de esgotos", "value": f"PVC Ø{PI['col_dn']}"}])]
    b.append(("p", "Estudo prévio das redes prediais de água, esgotos e pluviais (Decreto Regulamentar 23/95). Não substitui o projeto da especialidade."))
    rows = []
    for t_ in sorted({x["tip"] for x in PI["fr"]}):
        x = next(y for y in PI["fr"] if y["tip"] == t_)
        rows.append([t_, ", ".join(f"{k.replace('_', ' ')} {n}" for k, n in x["d"].items()), f(x["qa"], 2), f(x["qc"], 2), f"Ø{x['af'][0]}", f"Ø{x['aq'][0]}"])
    b.append(("table", ["Tip.", "Dispositivos", "Qa L/s", "Qc L/s", "AF", "AQ"], rows, [12 * W, 98 * W, 16 * W, 16 * W, 18 * W, 18 * W]))
    rows = [["Ramal de ligação", f(PI["q_tot"], 2), f(PI["qc_tot"], 2), f"PEAD Ø{PI['rl'][0]}", f(PI["rl"][2], 2)]]
    rows += [[c_["troco"], f(c_["qa"], 2), f(c_["qc"], 2), f"PEAD Ø{c_['dn']}", f(c_["v"], 2)] for c_ in PI["col"]]
    b.append(("table", ["Troço", "Qa L/s", "Qc L/s", "Tubagem", "v m/s"], rows, [70 * W, 22 * W, 22 * W, 34 * W, 22 * W]))
    b.append(("table", [f"Pressão no dispositivo mais desfavorável (fração {PI['top']})", "kPa"], [
        ["Rede pública (a confirmar)", f(PI["P"], 0)], [f"Desnível ({f(dz, 1)} m)", f(-dz * 9.81, 0)], ["Ramal de ligação", f(-J_rl * 9.81, 0)],
        ["Coluna montante", f(-J_col * 9.81, 0)], ["Contador, válvulas e ramal interior", f(-J_fr * 9.81, 0)], ["Pressão residual", f(PI["p_top"], 0)],
        ["Pressão estática no piso inferior (≤ 600)", f(PI["p_low"], 0)]], [140 * W, 40 * W]))
    b.append(("controls", [{"ref": "Pressão mínima (art. 87.º)", "exigence": "≥ 50 kPa (conforto ≥ 100–150 kPa)", "valeur": f"{f(PI['p_top'], 0)} kPa",
                            "ok": PI["p_top"] >= 50, "note": None if PI["p_top"] >= 150 else "prever grupo hidropressor"},
                           {"ref": "Pressão estática máxima", "exigence": "≤ 600 kPa", "valeur": f"{f(PI['p_low'], 0)} kPa", "ok": PI["p_low"] <= 600}]))
    b.append(("table", ["Tipologia", "Ocupantes", "L/dia", "Depósito BC AQS"], [[a["tip"], str(a["oc"]), str(a["l_dia"]), f"{a['vol']} L"] for a in PI["aqs"]],
              [30 * W, 30 * W, 40 * W, 50 * W]))
    b.append(("table", ["TQ", "Serve", "Σ L/min", "Qd L/min", "Ø mín.", "Adotado"], [[t["nome"], t["desc"], f(t["dl"], 0), f(t["qd"], 0), f(t["dmin"], 0), f"PVC Ø{t['dn']}"]
                                                                                   for t in PI["tq"]], [12 * W, 80 * W, 20 * W, 20 * W, 18 * W, 26 * W]))
    b.append(("p", f"Coletor predial : {f(PI['qd_tot'], 0)} L/min → PVC Ø{PI['col_dn']} a 1 % (meia secção {f(PI['cap_col'], 0)} L/min), sistema separativo."))
    b.append(("table", ["Pluviais", "A m²", "Q L/s", "Nº TQ", "TQ", "Cap. L/s"], [[x["zona"], f(x["A"], 0), f(x["Q"], 2), str(x["n"]), f"Ø{x['dn']}", f(x["cap"], 2)]
                                                                               for x in PI["plu"]], [74 * W, 18 * W, 18 * W, 18 * W, 20 * W, 22 * W]))
    b.append(("p", f"I = {f(PI['I'], 0)} mm/h (região A, T = 5 anos, 5 min). Coletor de pluviais Ø{PI['colp']} a 1 %."
                   + (f" Estação elevatória da cave ≈ {f(PI['ee']['q'], 1)} L/s, volume útil ≈ {f(PI['ee']['vol'], 1)} m³." if PI["ee"] else "")))
    p = out / f"Estudo_pichelaria_{stem}.pdf"
    p.write_bytes(rendu.build_pdf("Estudo de pichelaria — águas, esgotos e pluviais", sub, b + [("hyp", [
        f"Pressão na rede {f(PI['P'], 0)} kPa (a confirmar pela entidade gestora).", "Dispositivos deduzidos das instalações sanitárias de cada fração.",
        "Diâmetro dos tubos de queda : D = 4,4205·Qd^(3/8)·ts^(−5/8), ts = 1/3 (fórmula a confirmar)."])],
        footer="ConstruPilot — estudo prévio (DR 23/95)."))
    files["pichelaria"] = p
    # ---------------- eletricidade
    col = EL["col"]
    b = [("kpis", [{"label": "Potência das frações", "value": f(EL["p_fr"], 0), "unit": "kVA"},
                   {"label": f"Coluna (coef. {f(EL['coef'], 2)})", "value": f(EL["p_col"], 0), "unit": "kVA"},
                   {"label": "Serviços comuns", "value": f(EL["sc_kva"], 2), "unit": "kVA"}, {"label": "Pedido E-REDES", "value": f(EL["p_ed"], 0), "unit": "kVA"}])]
    b.append(("p", "Estudo prévio das instalações elétricas (RTIEBT) : frações, coluna montante, serviços comuns. Não substitui os projetos de eletricidade e ITED."))
    rows = []
    for t_ in sorted({x["tip"] for x in EL["fr"]}):
        x = next(y for y in EL["fr"] if y["tip"] == t_)
        r = x["el"]
        rows.append([t_, str(r["tomadas"]), str(r["pontos_luz"]), str(len(r["circuitos"])), str(r["diferenciais"]), f(x["bc_kw"], 1), f(x["p_dim"] / 1000, 1), f(x["kva"], 2)])
    b.append(("table", ["Tipo", "Tomadas", "P. luz", "Circ.", "Dif.", "BC kW", "P simult. kW", "Contratar kVA"], rows,
              [20 * W, 18 * W, 16 * W, 16 * W, 14 * W, 20 * W, 24 * W, 26 * W]))
    x = max(EL["fr"], key=lambda y: len(y["el"]["circuitos"]))
    b.append(("table", ["Circuito", "mm²", "Disj. A", "Pontos", "Dif.", "ΔU %"], [[c_["nome"], f(c_["seccao"], 1), str(c_["disjuntor"]), str(c_["pontos"] or "—"),
                                                                                c_["diferencial"], f(c_["du"], 2)] for c_ in x["el"]["circuitos"]],
              [70 * W, 16 * W, 18 * W, 18 * W, 20 * W, 18 * W]))
    b.append(("table", ["Serviços comuns", "kW", "Alim."], [[n_, f(p_, 2), t_] for n_, p_, t_ in EL["SC"]] + [["Total", f(EL["p_sc"], 2), ""]], [130 * W, 22 * W, 28 * W]))
    b.append(("table", ["Coluna montante", "Valor"], [["Frações / coeficiente", f"{len(EL['fr'])} / {f(EL['coef'], 2)}"], ["Corrente", f"{f(col['I'], 0)} A"],
                                                     ["Proteção", f"{col['In']} A"], ["Cabo Cu XV", f"4 × {col['s']} mm² + PE (Iz {col['iz']} A)"],
                                                     ["ΔU", f"{f(col['du'], 2)} % (L = {f(col['L'], 0)} m, ≤ 1,5 %)"]]
              + [[f"Derivação {f(d['kva'], 2)} kVA ({d['n']})", f"2 × {d['s']} mm² + PE, {d['dj']} A, ΔU {f(d['du'], 2)} %"] for d in EL["der"]], [90 * W, 90 * W]))
    b.append(("hyp", ["Terra : anel de fita de aço galvanizado nas fundações, ligado às armaduras ; R ≤ 20 Ω recomendado.",
                      "ITED : ATE, coluna de telecomunicações, ATI por fração (fibra, coaxial, RJ45).",
                      "Coeficientes de simultaneidade e Iz indicativos — a confirmar nas tabelas do RTIEBT."]))
    p = out / f"Estudo_eletricidade_{stem}.pdf"
    p.write_bytes(rendu.build_pdf("Estudo de instalações elétricas", sub, b, footer="ConstruPilot — estudo prévio (RTIEBT)."))
    files["eletricidade"] = p
    return files
