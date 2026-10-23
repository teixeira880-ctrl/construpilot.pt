"""Drenagem das águas pluviais de um pátio rebaixado (pátio interior, pátio inglês) — pré-dimensionamento (Portugal).

Um pátio cujo fundo está abaixo do nível do arruamento não pode descarregar por gravidade no coletor público sem risco de refluxo
quando a rede entra em carga (trovoada): o DR 23/95 impõe a elevação das águas residuais recolhidas abaixo do nível do arruamento,
com proteção contra o refluxo (EN 12056-4: estações elevatórias; EN 752). Solução de referência:
  ralos sifonados + coletor → poço → estação elevatória com 2 bombas alternadas (uma de reserva) → compressão com válvula de
  retenção e "pescoço de cisne" acima do nível do arruamento → caixa de águas pluviais do lote (e depois rede ou infiltração).
O fundo do pátio serve de bacia de retenção em caso de avaria (altura de água admissível abaixo das soleiras das portas).

Caudal de projeto: DR 23/95, curvas IDF I = a·t^b (região A, B ou C), período de retorno 10 anos e duração 5 min por defeito (pátio
rebaixado: transbordamento danoso), área em planta + 50 % da maior parede vertical que escorre para o pátio, coeficiente de
escoamento 1, majorado por um coeficiente de risco (EN 12056-3, quadro 2: 1,5).
Poço: volume útil ≥ Q·T/4 com T = 3600 / Z (Z arranques / h). Compressão: Darcy-Weisbach (Swamee-Jain), velocidade 0,7 a 2,0 m/s.
Muros do pátio em blocos de cofragem perdida: verificação em consola (impulso de terras em repouso + sobrecarga) se não travados no topo.
"""
from __future__ import annotations

import math

from . import redes

PVC_PRESSION = [(40, 36.2), (50, 45.2), (63, 57.0), (75, 67.8)]          # DN ext, Ø int (mm), PN10
POMPES_M3H = [6, 8, 10, 12, 15, 20, 25, 30]
POCOS = [(0.6, "PE Ø 600"), (0.8, "PE Ø 800"), (1.0, "PE / betão Ø 1000"), (1.2, "betão Ø 1200")]


def _f(x, n=2):
    return f"{x:.{n}f}".replace(".", ",")


def _dp_darcy(q_ls, di_mm, L, k_sing, eps_mm=0.05):
    d = di_mm / 1000
    v = q_ls / 1000 / (math.pi * d * d / 4)
    re = v * d / 1.0e-6
    lam = 0.25 / math.log10(eps_mm / 1000 / (3.7 * d) + 5.74 / re ** 0.9) ** 2
    return v, lam * L / d * v * v / 19.62 + k_sing * v * v / 19.62


def _manning_plein(di_mm, pente, n=0.010):
    d = di_mm / 1000
    return 1000 * (1 / n) * (math.pi * d * d / 4) * (d / 4) ** (2 / 3) * pente ** 0.5     # L/s




def calcular(p: dict) -> dict:
    A = float(p.get("area_m2") or 20)
    prof = float(p.get("profundidade_m") or 1.0)
    a = float(p.get("comprimento_m") or math.sqrt(A))
    b = A / a
    h_fac = float(p.get("altura_fachadas_m") if p.get("altura_fachadas_m") is not None else 3.0)   # fachadas acima do terreno
    cob = float(p.get("coberturas_descarregadas_m2") or 0)
    k_risco = float(p.get("coef_risco") or 1.5)
    reg = p.get("regiao_pluviometrica") or "A"
    T = int(p.get("periodo_retorno_anos") or 10)
    if T not in redes.IDF_A:
        T = min(redes.IDF_A, key=lambda x: abs(x - T))
    hyp, ctl = [], []

    # 1. caudal de projeto
    I = redes.intensidade(reg, T, 5.0)                                           # mm/h
    i_ls = I / 3600                                                              # L/s/m²
    parede = max(a, b) * (prof + h_fac)
    A_calc = A + 0.5 * parede + cob
    Q = i_ls * k_risco * A_calc                                                  # L/s
    hyp.append(f"Chuvada de projeto DR 23/95: região {reg}, T = {T} anos, 5 min → I = {_f(I, 0)} mm/h × coeficiente de risco {_f(k_risco, 1)} "
               f"(EN 12056-3: transbordamento danoso para a habitação); área em planta {_f(A, 0)} m² + 50 % da maior parede "
               f"({_f(max(a, b), 2)} × {_f(prof + h_fac, 2)} m)"
               + (f" + {_f(cob, 0)} m² de coberturas descarregadas no pátio" if cob else " ; nenhuma cobertura descarrega no pátio (tubos de queda ligados noutro ponto)"))

    # 2. descarga gravítica possível ?
    fe = p.get("cota_soleira_descarga_m")      # profundidade da soleira da caixa de descarga sob o terreno
    dist = float(p.get("distancia_descarga_m") or 15)
    z_rl = -(prof + 0.30)                      # saída do ralo sifonado sob o terreno
    gravit = fe is not None and z_rl - 0.01 * dist >= -float(fe)
    solucao = "gravitica" if (p.get("descarga_infiltracao") and gravit) else "elevatoria"

    # 3. ralos e coletor
    n_rl = 2
    q_col = _manning_plein(96.8, 0.02)
    ctl.append({"ref": "Ralos sifonados (300 × 300, saída DN 110)", "exigencia": f"cada um ≥ {_f(Q)} L/s sozinho (o outro obstruído por folhas)",
                "valor": f"{n_rl} ralos, caudal unitário ≥ {_f(Q)} L/s na ficha do fabricante", "ok": None,
                "note": "grelha em ferro fundido classe adequada (A15 peões), cesto de folhas amovível"})
    ctl.append({"ref": "Coletor ralos → poço (PVC SN8 DN 110, inclinação 2 %)", "exigencia": f"capacidade ≥ {_f(Q)} L/s",
                "valor": f"{_f(q_col, 1)} L/s a secção cheia", "ok": q_col >= Q})

    # 4. bombas
    Z = int(p.get("arranques_h") or 12)
    q_b_m3h = next((x for x in POMPES_M3H if x / 3.6 >= Q * 1.05), POMPES_M3H[-1])
    Qb = q_b_m3h / 3.6
    z_pc = float(p.get("altura_pescoco_cisne_m") or 0.30)
    L_imp = float(p.get("comprimento_compressao_m") or dist)
    dn, di = next(((d, i) for d, i in PVC_PRESSION if _dp_darcy(Qb, i, 1, 0)[0] <= 2.0), PVC_PRESSION[-1])
    k_sing = 2.0 + 0.3 + 4 * 0.5 + 1.0                                # válvula de retenção de esfera, válvula, 4 curvas, saída
    v, dH = _dp_darcy(Qb, di, L_imp, k_sing)

    # 5. poço
    Vu = Qb / 1000 * (3600 / Z) / 4
    D, poco_lib = next(((d, lib) for d, lib in POCOS if Vu / (math.pi * d * d / 4) <= 0.45), POCOS[-1])
    S_p = math.pi * D * D / 4
    h_u = Vu / S_p
    h_morto, h_alarme, h_guarda = 0.30, 0.10, 0.10
    h_poco = h_morto + h_u + h_alarme + h_guarda
    z_ent = z_rl - 0.02 * 3.0
    z_fundo = z_ent - h_poco
    H_geo = z_pc - (z_fundo + h_morto)
    AMT = H_geo + dH
    P_abs = 1000 * 9.81 * Qb / 1000 * AMT / 0.35 / 1000
    P_nom = next((x for x in (0.25, 0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3.0) if x >= P_abs * 1.2), 3.0)
    ctl.append({"ref": "Bombas (2 bombas submersíveis alternadas, uma de reserva)", "exigencia": f"cada uma ≥ {_f(Q)} L/s ({_f(Q * 3.6, 1)} m³/h) à AMT",
                "valor": f"{q_b_m3h} m³/h a {_f(AMT, 1)} m c.a., ≈ {_f(P_nom, 2)} kW", "ok": P_abs * 1.2 <= 3.0})
    ctl.append({"ref": f"Compressão PVC pressão DN {dn} PN10 (EN 12056-4)", "exigencia": "velocidade 0,7 a 2,0 m/s (autolimpeza, golpe de aríete)",
                "valor": f"{_f(v)} m/s, perdas de carga {_f(dH)} m em {_f(L_imp, 0)} m", "ok": 0.7 <= v <= 2.0})
    ctl.append({"ref": "Poço de bombagem (volume útil)", "exigencia": f"Vu ≥ Q·T/4 com {Z} arranques / h",
                "valor": f"{poco_lib}, Vu = {_f(Vu * 1000, 0)} L (curso {_f(h_u)} m), profundidade {_f(h_poco)} m abaixo da entrada", "ok": True})
    ctl.append({"ref": "Proteção contra o refluxo (DR 23/95, EN 12056-4)", "exigencia": "ponto alto da compressão acima do nível do arruamento + válvula de retenção",
                "valor": f"pescoço de cisne a +{_f(z_pc)} m, válvula de retenção de esfera + válvula de seccionamento por bomba", "ok": True})

    # 6. avaria (pátio = bacia de retenção)
    h_max = float(p.get("altura_agua_admissivel_m") or 0.15)
    V_ret = A * h_max * 0.9 + S_p * (h_alarme + h_guarda)
    h10 = float(p.get("chuva_1h_10anos_mm") or redes.intensidade(reg, 10, 60.0))
    h100 = float(p.get("chuva_1h_100anos_mm") or redes.intensidade(reg, 100, 60.0))
    V10, V100 = h10 * A_calc / 1000, h100 * A_calc / 1000
    t_ench = V_ret * 1000 / Q / 60
    ctl.append({"ref": "Avaria total (corte de energia durante a trovoada)", "exigencia": f"chuvada de 1 h a 10 anos ({_f(h10, 0)} mm) retida abaixo das soleiras (≤ {_f(h_max * 100, 0)} cm de água)",
                "valor": f"retenção {_f(V_ret, 1)} m³ ≥ {_f(V10, 1)} m³ ; chuvada de 100 anos ({_f(h100, 0)} mm): {_f(V100, 1)} m³", "ok": V_ret >= V10,
                "note": None if V_ret >= V100 else "chuvada de 100 anos não retida: bateria ou gerador de socorro numa bomba"})
    hyp.append(f"Chuvadas de 1 h ({_f(h10, 0)} mm a 10 anos, {_f(h100, 0)} mm a 100 anos) pelas curvas IDF do DR 23/95 extrapoladas a 60 min, região {reg}: "
               "confirmar com os dados do município / da entidade gestora")
    hyp.append(f"Soleiras das portas para o pátio pelo menos +{_f(h_max + 0.05)} m acima do fundo do pátio (a verificar nas plantas)")

    # 7. muros em blocos de cofragem perdida (consola)
    Ko, gam, q_s = 0.5, 20.0, float(p.get("sobrecarga_kpa") or 2.5)
    M_elu = 1.35 * Ko * gam * prof ** 3 / 6 + 1.5 * Ko * q_s * prof ** 2 / 2
    As = M_elu / 1000 / (0.9 * 0.10 * 435) * 1e4
    ctl.append({"ref": "Muros do pátio em blocos de cofragem perdida 20 cm (consola, NP EN 1992-1-1)", "exigencia": f"M_Ed = {_f(M_elu)} kN.m/m → As ≥ {_f(As)} cm²/m (d = 0,10 m)",
                "valor": "Ø10 a cada 20 cm (3,93 cm²/m) em arranques da sapata + enchimento em betão C25/30", "ok": As <= 3.93})
    hyp.append("Muros: impulso em repouso K0 = 0,5, γ = 20 kN/m³, sobrecarga 2,5 kPa, sem nível freático (a confirmar pelo estudo geotécnico); se o muro "
               "suportar a laje da habitação fica travado no topo e a verificação é menos severa")

    return {"area_m2": A, "a": a, "b": b, "profundidade": prof, "A_calc": A_calc, "I": I, "T": T, "regiao": reg, "Q": Q, "k_risco": k_risco, "solucao": solucao,
            "gravitica_possivel": gravit, "bomba_m3h": q_b_m3h, "AMT": AMT, "P_kW": P_nom, "dn_imp": dn, "v_imp": v, "dH": dH,
            "poco": poco_lib, "D_poco": D, "Vu_L": Vu * 1000, "h_u": h_u, "h_poco": h_poco, "z_fundo": z_fundo, "z_ent": z_ent, "z_rl": z_rl,
            "z_pc": z_pc, "h_morto": h_morto, "V_ret": V_ret, "V10": V10, "V100": V100, "t_ench_min": t_ench, "h_max": h_max,
            "As": As, "M_elu": M_elu, "Z": Z, "controles": ctl, "hipoteses": hyp}


# ----------------------------------------------------------------------------------------------------------------------------- corte
def coupe(r: dict):
    from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from . import rendu
    rendu.fonts()
    C = colors.HexColor
    W, H = 180 * mm, 92 * mm
    d = Drawing(W, H)
    s = 17 * mm                                            # escala: 1 m = 17 mm
    x0, y0 = 8 * mm, 72 * mm                              # origem: terreno natural à esquerda do pátio
    a = min(r["a"], 4.6)
    X = lambda x: x0 + x * s
    Y = lambda z: y0 + z * s
    t = lambda x, y, txt, sz=6.4, col=C("#1d2422"), anc="start", bold=False: String(x, y, rendu.txt(txt), fontName="CP-Bold" if bold else "CP",
                                                                                       fontSize=sz, fillColor=col, textAnchor=anc)
    terre, beton, eau = C("#c9b79c"), C("#b8b8b8"), C("#9cc9ee")
    prof = r["profundidade"]
    xm1, xm2 = 0.6, 0.6 + 0.2 + a + 0.2                     # muros do pátio
    # terras
    xe_ = xm2 + 0.2 + 0.5 + r["D_poco"] + 1.3
    d.add(Rect(X(0), Y(-3.0), X(xe_ + 0.7) - X(0), Y(0) - Y(-3.0), fillColor=terre, strokeColor=None))
    d.add(Rect(X(xm1 + 0.2), Y(-prof), X(xm2) - X(xm1 + 0.2), Y(0.05) - Y(-prof), fillColor=C("#ffffff"), strokeColor=None))
    # laje de fundo + muros
    d.add(Rect(X(xm1), Y(-prof - 0.35), X(xm2 + 0.2) - X(xm1), 0.35 * s, fillColor=beton, strokeColor=C("#555555"), strokeWidth=0.5))
    for xm in (xm1, xm2):
        d.add(Rect(X(xm), Y(-prof - 0.15), 0.2 * s, (prof + 0.15) * s, fillColor=beton, strokeColor=C("#555555"), strokeWidth=0.5))
        d.add(Line(X(xm) + 0.2 * s * 0.5, Y(-prof), X(xm) + 0.2 * s * 0.5, Y(-0.05), strokeColor=C("#c8453c"), strokeWidth=0.6, strokeDashArray=[2, 1.5]))
    # drenos do lado das terras
    for xd in (xm1 - 0.15, xm2 + 0.35):
        d.add(Circle(X(xd), Y(-prof - 0.20), 0.07 * s, fillColor=C("#ffffff"), strokeColor=C("#2a78d6"), strokeWidth=0.7))
    # pendente e ralo
    xav = xm1 + 0.2 + a * 0.62
    d.add(Line(X(xm1 + 0.2), Y(-prof + 0.02), X(xav), Y(-prof), strokeColor=C("#1d2422"), strokeWidth=0.4))
    d.add(Rect(X(xav) - 0.15 * s, Y(-prof - 0.30), 0.30 * s, 0.30 * s, fillColor=C("#6d6d6d"), strokeColor=C("#333333"), strokeWidth=0.5))
    # poço
    xf = xm2 + 0.2 + 0.5
    zf, zt = r["z_fundo"], -0.05
    Df = r["D_poco"]
    d.add(Rect(X(xf), Y(zf), Df * s, Y(zt) - Y(zf), fillColor=C("#ffffff"), strokeColor=C("#1d2422"), strokeWidth=0.8))
    z_stop, z_start = zf + r["h_morto"], zf + r["h_morto"] + r["h_u"]
    d.add(Rect(X(xf) + 1, Y(zf) + 1, Df * s - 2, Y(z_start) - Y(zf), fillColor=eau, strokeColor=None))
    for z, lab, col in ((z_stop, "paragem", "#1f8a52"), (z_start, "arranque", "#2a78d6"), (z_start + 0.10, "alarme", "#c8453c")):
        d.add(Line(X(xf), Y(z), X(xf + Df), Y(z), strokeColor=C(col), strokeWidth=0.5, strokeDashArray=[2, 1.2]))
        d.add(t(X(xf + Df) + 2, Y(z) - 2, lab, 5.6, C(col)))
    for k in (0, 1):
        px = X(xf) + (0.18 + 0.42 * k) * Df * s
        d.add(Rect(px, Y(zf) + 2, 0.22 * Df * s, 0.28 * s, fillColor=C("#2a78d6"), strokeColor=C("#1d2422"), strokeWidth=0.4))
    # coletor ralo → poço
    d.add(Line(X(xav) + 0.15 * s, Y(-prof - 0.22), X(xf), Y(r["z_ent"]), strokeColor=C("#2a78d6"), strokeWidth=1.6))
    # compressão + pescoço de cisne
    xr = xf + Df * 0.5
    zc = r["z_pc"]
    xe = xf + Df + 1.3
    pts = [(xr, zf + 0.35), (xr, zc), (xe, zc), (xe, -0.55)]
    for (xa, za), (xb, zb) in zip(pts, pts[1:]):
        d.add(Line(X(xa), Y(za), X(xb), Y(zb), strokeColor=C("#eb6834"), strokeWidth=1.4))
    d.add(Rect(X(xe) - 0.25 * s, Y(-0.95), 0.5 * s, 0.9 * s, fillColor=C("#ffffff"), strokeColor=C("#1d2422"), strokeWidth=0.6))
    d.add(Polygon([X(xr) - 3, Y(-0.25), X(xr) + 3, Y(-0.25), X(xr), Y(-0.35)], fillColor=C("#eb6834"), strokeColor=None))
    # níveis e textos
    d.add(Line(X(0), Y(0), X(xe + 0.7), Y(0), strokeColor=C("#1d2422"), strokeWidth=0.8))
    d.add(t(X(0), Y(0) + 3, "Terreno / arruamento ±0,00", 6.4, bold=True))
    d.add(t(X(xm1 + 0.3), Y(-prof) + 4, f"Fundo do pátio −{_f(prof)} (pendente 1,5 a 2 % para os ralos)", 6.2))
    d.add(t(X(xm1 + 0.3), Y(-prof) + 12, f"Pátio ≈ {_f(r['area_m2'], 0)} m² — altura de água admissível {_f(r['h_max'] * 100, 0)} cm", 6.2, C("#2a78d6")))
    d.add(t(X(xav), Y(-prof - 0.30) - 8, "Ralo sifonado 300×300 (×2)", 6.0, anc="middle"))
    d.add(t(X(xm1) - 2, Y(-prof - 0.85), "Dreno DN110 + membrana alveolar", 5.8, anc="start"))
    d.add(t(X(xf + Df * 0.5), Y(zf) - 8, f"Poço {r['poco']} — fundo {_f(r['z_fundo'])}", 6.0, anc="middle"))
    d.add(t(X(xf + Df * 0.5), Y(zf) - 15, f"2 bombas {r['bomba_m3h']} m³/h a {_f(r['AMT'], 1)} m c.a., alternadas", 6.0, anc="middle", bold=True))
    d.add(t(X(xe), Y(zc) + 3, f"Pescoço de cisne +{_f(zc)} (acima do arruamento)", 6.0, C("#eb6834"), anc="middle"))
    d.add(t(X(xr) + 4, Y(-0.30), "válvula de retenção", 5.6, C("#eb6834")))
    d.add(t(X(xe), Y(-0.95) - 8, "Caixa de águas pluviais do lote", 6.0, anc="middle"))
    d.add(t(X(xm1 + 0.3), Y(-0.05) - 8, "Muros em blocos de cofragem perdida 20 cm — impermeabilização do lado das terras", 5.8, C("#c8453c")))
    return d




def note(p: dict) -> dict:
    from . import graficos as G
    from . import notes
    r = calcular(p)
    W = notes.W
    sol = ("Descarga gravítica possível para um órgão de infiltração do lote, com válvula de retenção." if r["solucao"] == "gravitica" else
           "O fundo do pátio está abaixo do nível do arruamento: uma descarga gravítica no coletor público faria refluir a rede para o pátio "
           "durante as trovoadas (rede em carga). Solução adotada: estação elevatória com duas bombas e compressão acima do nível do arruamento.")
    kp = [{"label": "Caudal de projeto", "value": _f(r["Q"]), "unit": "L/s"},
          {"label": "Bombas (×2)", "value": f"{r['bomba_m3h']}", "unit": f"m³/h a {_f(r['AMT'], 1)} m"},
          {"label": "Poço", "value": _f(r["Vu_L"], 0), "unit": "L úteis"},
          {"label": "Retenção em avaria", "value": _f(r["V_ret"], 1), "unit": "m³", "ok": r["V_ret"] >= r["V10"]}]
    rows = [["Área em planta do pátio", f"{_f(r['area_m2'], 0)} m²"], ["Área de cálculo (com 50 % de parede)", f"{_f(r['A_calc'], 1)} m²"],
            ["Intensidade IDF (DR 23/95)", f"região {r['regiao']}, T = {r['T']} anos, 5 min: {_f(r['I'], 0)} mm/h"],
            ["Coeficiente de risco", _f(r["k_risco"], 1)], ["Caudal de projeto", f"{_f(r['Q'])} L/s = {_f(r['Q'] * 3.6, 1)} m³/h"]]
    bomba = [["Caudal unitário adotado", f"{r['bomba_m3h']} m³/h ({_f(r['bomba_m3h'] / 3.6)} L/s)"],
             ["Altura geométrica (paragem → pescoço de cisne)", f"{_f(r['AMT'] - r['dH'])} m"], ["Perdas de carga", f"{_f(r['dH'])} m"],
             ["AMT", f"{_f(r['AMT'], 1)} m c.a."], ["Potência indicativa", f"≈ {_f(r['P_kW'], 2)} kW por bomba, 230 V"],
             ["Compressão", f"PVC pressão DN {r['dn_imp']} PN10, {_f(r['v_imp'])} m/s"],
             ["Poço", f"{r['poco']}, profundidade ≈ {_f(r['h_poco'] + abs(r['z_ent']), 2)} m sob o terreno"],
             ["Volume útil / curso", f"{_f(r['Vu_L'], 0)} L / {_f(r['h_u'])} m ({r['Z']} arranques / h máx.)"]]
    conv = [{"ref": c["ref"], "exigence": c["exigencia"], "valeur": c["valor"], "ok": c["ok"], "note": c.get("note")} for c in r["controles"]]
    blocs = [("p", "Pré-dimensionamento indicativo — a validar com o estudo geotécnico, o projeto de execução e as regras da entidade gestora."),
             ("h2", "1. Princípio adotado"), ("p", sol),
             ("chart", coupe(r), "Corte de princípio (não cotado para execução): ralos → poço → 2 bombas → compressão em pescoço de cisne → caixa de águas pluviais."),
             ("h2", "2. Caudal pluvial a escoar"), ("table", ["Grandeza", "Valor"], rows, [110 * W, 70 * W]),
             ("h2", "3. Estação elevatória"), ("table", ["Grandeza", "Valor"], bomba, [110 * W, 70 * W]),
             ("p", "Equipamentos: 2 bombas submersíveis para águas pouco carregadas (passagem de sólidos ≥ 10 mm), funcionamento alternado com "
                   "permuta automática e marcha simultânea em nível alto; boias ou sonda de nível (paragem, arranque, alarme); válvula de retenção "
                   "de esfera e válvula de seccionamento por bomba; barra-guia ou corrente de elevação; tampa estanque com fecho; ventilação do "
                   "poço; quadro de comando fora de água com alarme sonoro + aviso SMS; circuito dedicado 16 A com diferencial 30 mA."),
             ("h2", "4. Se faltar a energia durante a trovoada"),
             ("chart", G.barres_h([("Retenção disponível abaixo das soleiras", r["V_ret"]), ("Chuvada de 1 h — 10 anos", r["V10"]), ("Chuvada de 1 h — 100 anos", r["V100"])],
                                  "Volumes (m³)", "m³", couleur=G.SERIES[0]),
              f"O fundo do pátio serve de bacia de retenção: {_f(r['V_ret'], 1)} m³ antes de atingir {_f(r['h_max'] * 100, 0)} cm de água, ou seja "
              f"≈ {_f(r['t_ench_min'], 0)} min ao caudal de ponta."),
             ("p", "Recomendado: bateria de socorro (ou UPS) numa das duas bombas e soleiras das portas elevadas pelo menos 15 a 20 cm acima do fundo do pátio."),
             ("h2", "5. Muros, impermeabilização e drenagem"),
             ("p", f"Muros em blocos de cofragem perdida 20 cm cheios com betão C25/30, armados com Ø10 a cada 20 cm em arranques da sapata "
                   f"(M_Ed = {_f(r['M_elu'])} kN.m/m, As necessário {_f(r['As'])} cm²/m). Lado das terras: pintura betuminosa + membrana alveolar "
                   "e dreno DN 110 com geotêxtil no pé do muro, em massame de brita 20/40, ligado ao poço por uma caixa de visita. Lado do pátio: "
                   "reboco hidrófugo; remate da impermeabilização entre a laje de fundo e os muros (junta + mástique)."),
             ("h2", "6. Controlos"), ("controls", conv)]
    titre = "Drenagem das águas pluviais — pátio rebaixado"
    pdf, png = notes.pdf(titre, f"Pátio ≈ {_f(r['area_m2'], 0)} m², fundo a −{_f(r['profundidade'])} m, muros em blocos de cofragem perdida", [("kpis", kp)] + blocs,
                         r["hipoteses"])
    return {**r, "titre": titre, "pdf": pdf, "png": png}
