# Copie embarquée de engines/calc_lots (site .pt) pour que le moteur ossature soit identique sur .fr et .pt.
"""Aquecimento (Portugal) — perdas de calor de projeto divisão a divisão (EN 12831-1, método simplificado) e pré-dimensionamento
de bomba de calor ar/água. Pré-dimensionamento indicativo.

Perdas de calor
  Φ_HL,i = Φ_T,i + Φ_V,i (+ Φ_RH,i reaquecimento opcional)
  Φ_T,i = Σ A·(U + ΔU_pt)·b·(θint,i − θe) + Σ ψ·L·(θint,i − θe)           b = 1 exterior, < 1 espaço não útil / solo
  Φ_V,i = 0,34 · [q_ar,i·(θint,i − θar,i) + q_inf,i·(θint,i − θe)]          0,34 W·h/(m³·K) = ρ·cp do ar
Ventilação (tipo de sistema):
  • natural / mecânica simples fluxo: o ar novo entra nas divisões principais à θe; as zonas húmidas recebem ar transferido
    das divisões principais (θar = θint médio das principais) e o extraem — o caudal de extração é contado UMA vez
    (nas divisões principais), nunca somado nas zonas húmidas;
  • dupla fluxo com recuperação: o ar insuflado chega a θsu = θe + η·(θint − θe) → q·(1 − η)·(θint − θe).
  Caudal de projeto = max(Σ extração das zonas húmidas, Rph,mín · V) distribuído pelas divisões principais em proporção do volume.
Infiltrações: classe de estanquidade (renovações/h por defeito) ou n50 medido: q_inf,i = 2·V_i·n50·e_i (EN 12831:2003 anexo D,
  e = 0,02: proteção moderada, uma fachada exposta). Somadas ao caudal de ventilação (abordagem prudente).
Pontes térmicas: ψ·L por divisão quando descritas, senão majoração forfetária ΔU_pt nas paredes em contacto com o exterior / ENU.
Temperatura exterior de projeto θe: indicada pelo utilizador ou, por defeito, θext,i do REH (temperatura média do mês mais frio,
corrigida em altitude) menos um desvio de 8 K (hipótese a validar com os dados climáticos de projeto, p. ex. CLIMAS-SCE).

Bomba de calor ar/água
  Potência à θe: curva ou valor do fabricante, senão lei indicativa P(θ)/P(A7W35) = 1 + 0,018·(θ − 7) (limitada a 0,45–1,1) com
  correção da temperatura de ida (−1 %/K acima de 35 °C, indicativa). Cobertura P(θe)/D; ponto de bivalência = interseção de
  P(θ) com D·(θint − θ)/(θint − θe); apoio = fator·D − P(θe) (fator 1,2 por defeito, regra de boa prática); volume de água mínimo
  (L/kW nominal, ficha do fabricante) e depósito de inércia; vaso de expansão pelo método da EN 12828 (anexo D):
  Vn ≥ (Ve + Vwr)·(pe + 1)/(pe − p0); η_s / SCOP face aos mínimos de ecodesign do Regulamento (UE) 813/2013; alimentação elétrica.
"""
from __future__ import annotations

import math

from . import _reh as reh

T_INT = {"sala": 20, "quarto": 20, "cozinha": 20, "casa_de_banho": 22, "corredor": 18, "escritorio": 20, "lavandaria": 18,
         "arrumos": 15, "outro": 20}
B = {"exterior": 1.0, "enu": 0.8, "enu_ventilado": 1.0, "adjacente": 0.6, "solo": 0.45, "fracao_vizinha": 0.0, "aquecido": 0.0}
INFILTRACAO = {"muito_estanque": 0.05, "estanque": 0.10, "media": 0.20, "antiga": 0.40}       # renovações/h (indicativo)
INFILTRACAO_PT = {"muito_estanque": "muito estanque", "estanque": "estanque", "media": "média", "antiga": "antiga / pouco estanque"}
EXTRACAO = {"cozinha": 75, "casa_de_banho": 45, "lavandaria": 30}       # m³/h (valores de referência NP 1037-1, a confirmar)
VENTILACAO = {
    "natural": {"nome": "natural (admissão por aberturas nas divisões principais, extração por condutas nas zonas húmidas)", "eta": False},
    "mecanica_simples": {"nome": "mecânica simples fluxo (extração mecânica nas zonas húmidas, admissão por grelhas)", "eta": False},
    "dupla_fluxo": {"nome": "mecânica de dupla fluxo com recuperação de calor", "eta": True},
}
VENTILACAO_PT = {"natural": "natural", "mecanica_simples": "mecânica simples fluxo", "dupla_fluxo": "dupla fluxo com recuperação"}
ETA_DUPLA_FLUXO = 0.75             # eficiência por defeito do recuperador (valor indicativo, a substituir pela ficha do equipamento)
COEF_PROTECAO = 0.02               # EN 12831:2003 anexo D — e para uma fachada exposta, proteção moderada
NOMES_PT = {"sala": "Sala", "quarto": "Quarto", "cozinha": "Cozinha", "casa_de_banho": "Casa de banho", "corredor": "Corredor", "escritorio": "Escritório",
            "lavandaria": "Lavandaria", "arrumos": "Arrumos", "outro": "Outro"}
PRINCIPAIS = ("sala", "quarto", "escritorio")
DESVIO_PROJETO = 8.0
RPH_MIN = 0.4                      # h⁻¹ — por defeito (valor a confirmar na Portaria 138-I/2021 / projeto de ventilação)
DELTA_U_PONTES = 0.10              # W/(m².°C) — majoração forfetária indicativa
GAMA_KW = [3, 4, 5, 6, 8, 10, 11, 12, 14, 16]
EMISSORES = {"piso_radiante": (35, 17), "radiadores_bt": (45, 9), "radiadores_ht": (55, 9), "ventiloconvectores": (35, 3)}
EMISSORES_PT = {"piso_radiante": "piso radiante", "radiadores_bt": "radiadores de baixa temperatura", "radiadores_ht": "radiadores de alta temperatura",
                "ventiloconvectores": "ventiloconvectores"}
APOIO_PT = {"resistencia_eletrica": "resistência elétrica", "caldeira": "caldeira", "nenhum": "sem apoio"}
COBERTURA = {"leve": (0.80, 1.00), "media": (0.70, 1.00), "forte": (0.70, 1.00)}      # regra de boa prática (não regulamentar em Portugal)
APOIO_KW = (2, 3, 4, 6, 9, 12)
DEPOSITOS_L = (25, 40, 50, 60, 80, 100, 150, 200, 300, 500)
VASOS_L = (8, 12, 18, 25, 35, 50, 80, 100, 140, 200, 300)
# Reg. (UE) 813/2013 (ecodesign, desde 26/09/2017): η_s mínima das bombas de calor de aquecimento ambiente
ERP_MIN = {"media": 110, "baixa": 125}
# Reg. Delegado (UE) 811/2013 (etiqueta, escala desde 26/09/2019): limiares inferiores de η_s por classe
ERP_CLASSES = {"media": [("A+++", 150), ("A++", 125), ("A+", 98), ("A", 90), ("B", 82), ("C", 75), ("D", 36)],
               "baixa": [("A+++", 175), ("A++", 150), ("A+", 123), ("A", 115), ("B", 107), ("C", 100), ("D", 61)]}
CC_ERP = 2.5                       # coeficiente de conversão de energia primária do Reg. 813/2013 (η_s = 100·SCOP/CC − 3 %)
SCOP_INDICATIVO = [(35, 4.2), (45, 3.6), (55, 3.1)]   # valores típicos de mercado (clima médio EN 14825) — não regulamentares
# Massa volúmica da água (kg/m³) — tabelas de propriedades físicas
RHO_AGUA = [(10, 999.70), (20, 998.21), (30, 995.65), (40, 992.22), (50, 988.04), (60, 983.20), (70, 977.76), (80, 971.79), (90, 965.31)]


def _c(x, n=1) -> str:
    return f"{x:.{n}f}".replace(".", ",")


def _g(x) -> str:
    return f"{x:g}".replace(".", ",")


def theta_projeto(p: dict, hyp: list) -> tuple[float, str]:
    if p.get("theta_e") is not None:
        return float(p["theta_e"]), "indicada"
    c = reh.clima(p.get("concelho"), p.get("nuts"), p.get("altitude_m"))
    if c.get("aviso"):
        hyp.append(c["aviso"])
    te = round(c["theta_i"] - DESVIO_PROJETO, 1)
    hyp.append(f"θe de projeto = θext,i REH {_c(c['theta_i'])} °C ({c['nuts']}, {c['altitude_m']:.0f} m) − {_g(DESVIO_PROJETO)} K = {_g(te)} °C "
               "(desvio indicativo; confirmar com a temperatura exterior de projeto, p. ex. CLIMAS-SCE)")
    return te, f"REH {c['nuts']}"


def _sistema_ventilacao(p: dict, hyp: list) -> tuple[str, float]:
    vent = p.get("ventilacao")
    eta_in = p.get("recuperacao_calor")
    if vent is None:
        vent = "dupla_fluxo" if eta_in else "natural"
    if vent not in VENTILACAO:
        raise ValueError(f"sistema de ventilação desconhecido {vent!r} ({', '.join(VENTILACAO)})")
    if VENTILACAO[vent]["eta"]:
        if eta_in is None:
            eta = ETA_DUPLA_FLUXO
            hyp.append(f"eficiência do recuperador de calor não indicada: η = {_g(ETA_DUPLA_FLUXO)} (indicativo — usar a ficha do equipamento)")
        else:
            eta = float(eta_in)
        if not 0 <= eta < 1:
            raise ValueError("recuperacao_calor: eficiência entre 0 e 1 (p. ex. 0,8)")
    else:
        eta = 0.0
        if eta_in:
            hyp.append(f"recuperação de calor indicada ({_g(float(eta_in))}) ignorada: o sistema «{vent}» não tem recuperador")
    return vent, eta


def perdas(p: dict) -> dict:
    """p : {concelho | nuts, altitude_m, theta_e, ventilacao, recuperacao_calor, estanquidade | n50, coef_protecao, rph_min,
            delta_u_pontes, reaquecimento_w_m2, divisoes: [{nome, tipo, area_m2, pe_direito_m, theta_int, q_extracao_m3h,
            paredes: [{area_m2, U, lado, b}], pontes: [{comprimento_m, psi, designacao}]}]}"""
    hyp: list[str] = []
    te, src = theta_projeto(p, hyp)
    div = p.get("divisoes") or []
    if not div:
        raise ValueError("indicar as divisões (tipo, área, paredes com U)")
    vent, eta = _sistema_ventilacao(p, hyp)
    # infiltrações
    if p.get("n50") is not None:
        n50 = float(p["n50"])
        e = float(p.get("coef_protecao") if p.get("coef_protecao") is not None else COEF_PROTECAO)
        n_inf = 2 * n50 * e
        estanq = f"n50 = {_g(n50)} h⁻¹"
        hyp.append(f"infiltrações a partir do ensaio de pressurização: 2 × n50 × e = 2 × {_g(n50)} × {_g(e)} = {_c(n_inf, 3)} h⁻¹ "
                   "(EN 12831:2003 anexo D; e = 0,02 proteção moderada com uma fachada exposta, ajustar à exposição real)")
    else:
        cls = p.get("estanquidade") or "estanque"
        if cls not in INFILTRACAO:
            raise ValueError(f"classe de estanquidade desconhecida {cls!r} ({', '.join(INFILTRACAO)})")
        n_inf = INFILTRACAO[cls]
        estanq = INFILTRACAO_PT[cls]
        hyp.append(f"infiltrações {_g(n_inf)} h⁻¹ (classe «{estanq}», valor indicativo; um ensaio n50 permite afinar)"
                   + ("" if p.get("estanquidade") else " — classe não indicada"))
    rph = float(p.get("rph_min") or RPH_MIN)
    if p.get("rph_min") is None:
        hyp.append(f"taxa de renovação mínima {_g(RPH_MIN)} h⁻¹ por defeito (valor a confirmar na Portaria 138-I/2021 e no projeto de ventilação)")
    vols = [float(d.get("area_m2") or 0) * float(d.get("pe_direito_m") or 2.6) for d in div]
    tipos = [(d.get("tipo") or "outro") for d in div]
    for t in tipos:
        if t not in T_INT:
            raise ValueError(f"tipo de divisão desconhecido {t!r} ({', '.join(T_INT)})")
    tis = [float(d.get("theta_int") or T_INT[t]) for d, t in zip(div, tipos)]
    v_tot = sum(vols) or 1.0
    q_ext_i = [float(d["q_extracao_m3h"]) if d.get("q_extracao_m3h") is not None else float(EXTRACAO.get(t, 0)) for d, t in zip(div, tipos)]
    q_ext = sum(q_ext_i)
    if any(EXTRACAO.get(t) for d, t in zip(div, tipos) if d.get("q_extracao_m3h") is None):
        hyp.append("caudais de extração das zonas húmidas por defeito: cozinha 75, casa de banho 45, lavandaria 30 m³/h "
                   "(valores de referência NP 1037-1, a confirmar no projeto de ventilação)")
    q_tot = max(q_ext, rph * v_tot)
    v_pr = sum(v for v, t in zip(vols, tipos) if t in PRINCIPAIS) or v_tot
    sem_principais = v_pr == v_tot and not any(t in PRINCIPAIS for t in tipos)
    pr_ti = [(v, ti) for v, ti, t in zip(vols, tis, tipos) if t in PRINCIPAIS]
    th_transf = sum(v * ti for v, ti in pr_ti) / sum(v for v, _ in pr_ti) if pr_ti else 20.0
    # pontes térmicas
    dutb = p.get("delta_u_pontes")
    tem_psi = any(d.get("pontes") for d in div)
    if dutb is None and not tem_psi:
        dutb = DELTA_U_PONTES
        hyp.append(f"pontes térmicas não descritas: majoração forfetária ΔU = {_c(DELTA_U_PONTES, 2)} W/(m².°C) nas paredes da envolvente "
                   "(indicativa; descrever as pontes lineares ψ·L para um cálculo detalhado)")
    elif dutb is not None and tem_psi and float(dutb) > 0:
        hyp.append("pontes térmicas: ΔU forfetário e ψ·L aplicados em simultâneo — verificar que a mesma ponte não é contada duas vezes")
    dutb = float(dutb or 0)
    reaq = float(p.get("reaquecimento_w_m2") or 0)
    rows, tT, tV, tR, sum_psiL, tInf = [], 0.0, 0.0, 0.0, 0.0, 0.0
    for d, V, t, ti, qe in zip(div, vols, tipos, tis, q_ext_i):
        dT = ti - te
        phiT, det = 0.0, []
        for w in d.get("paredes") or []:
            lado = w.get("lado") or "exterior"
            if lado not in B and w.get("b") is None:
                raise ValueError(f"lado desconhecido {lado!r} ({', '.join(B)})")
            b = float(w["b"]) if w.get("b") is not None else B[lado]
            if b <= 0:
                continue
            U = float(w["U"]) + dutb
            phi = float(w["area_m2"]) * U * b * dT
            phiT += phi
            det.append({"designacao": w.get("designacao") or w.get("tipo") or lado, "A": float(w["area_m2"]), "U": U, "b": b, "phi": phi})
        for s in d.get("pontes") or []:
            psiL = float(s["comprimento_m"]) * float(s["psi"])
            phiT += psiL * dT
            sum_psiL += psiL
            det.append({"designacao": s.get("designacao") or "ponte térmica linear", "L": float(s["comprimento_m"]), "psi": float(s["psi"]), "phi": psiL * dT})
        q_inf = n_inf * V
        if t in PRINCIPAIS or sem_principais or not q_ext:
            # ar novo exterior (insuflado ou admitido) nas divisões principais, distribuído pelo volume
            q_ar = q_tot * V / v_pr if (t in PRINCIPAIS or v_pr == v_tot) else 0.0
            th_ar = te + eta * (ti - te)
            fonte = "exterior" + (f" recuperado (η {_g(eta)})" if eta else "")
        else:
            # zonas húmidas e circulações: ar transferido das divisões principais (já contado nelas)
            q_ar = qe
            th_ar = th_transf
            fonte = "transferido" if qe else "—"
        phiVv = 0.34 * q_ar * max(ti - th_ar, 0.0)
        phiVi = 0.34 * q_inf * dT
        phiV = phiVv + phiVi
        A = float(d.get("area_m2") or 0)
        phiR = reaq * A
        tot = phiT + phiV + phiR
        rows.append({"nome": d.get("nome") or t, "tipo": t, "theta_int": ti, "area_m2": A, "volume_m3": V, "phi_T": phiT, "phi_V": phiV,
                     "phi_V_ventilacao": phiVv, "phi_V_infiltracao": phiVi, "phi_RH": phiR, "phi": tot, "w_m2": tot / A if A else 0.0,
                     "q_ar_m3h": q_ar, "theta_ar": th_ar, "origem_ar": fonte, "q_inf_m3h": q_inf, "q_extracao_m3h": qe, "detalhes": det})
        tT += phiT; tV += phiV; tR += phiR; tInf += q_inf
    area = sum(r["area_m2"] for r in rows)
    hyp.append(f"ventilação {VENTILACAO[vent]['nome']}: caudal de projeto max(extração das zonas húmidas {q_ext:.0f} m³/h, {_g(rph)} h⁻¹ × "
               f"{v_tot:.0f} m³) = {q_tot:.0f} m³/h, distribuído pelas divisões principais; zonas húmidas com ar transferido a "
               f"{_c(th_transf)} °C (extração contada uma só vez); infiltrações somadas (abordagem prudente); pavimento sobre o solo por fator b forfetário")
    if reaq:
        hyp.append(f"reaquecimento {_g(reaq)} W/m² acrescentado (relançamento após redução noturna / intermitência) — valor escolhido pelo projetista")
    ctl = [{"ref": "Caudal de ar novo de projeto", "exigencia": f"≥ Rph,mín {_g(rph)} h⁻¹ × V ({rph * v_tot:.0f} m³/h) e ≥ extração das zonas húmidas "
                                                              f"({q_ext:.0f} m³/h) — valores a confirmar no projeto de ventilação",
            "valor": f"{q_tot:.0f} m³/h ({_c(q_tot / v_tot, 2)} h⁻¹)", "ok": True}]
    if eta:
        ctl.append({"ref": "Recuperação de calor (dupla fluxo)", "exigencia": "ar insuflado θsu = θe + η·(θint − θe)",
                    "valor": f"η {_g(eta)} → θsu ≈ {_c(te + eta * (th_transf - te))} °C", "ok": True,
                    "note": "caudais insuflação / extração equilibrados; bypass de verão e filtragem a prever"})
    if sum_psiL:
        h_t = sum(r["phi_T"] / (r["theta_int"] - te) for r in rows if r["theta_int"] > te)
        ctl.append({"ref": "Pontes térmicas lineares", "exigencia": "Σψ·L incluído nas perdas por transmissão",
                    "valor": f"Σψ·L = {_c(sum_psiL, 2)} W/°C ({100 * sum_psiL / h_t:.0f} % de H_T)" if h_t else f"Σψ·L = {_c(sum_psiL, 2)} W/°C", "ok": True})
    return {"theta_e": te, "theta_e_fonte": src, "ventilacao": vent, "ventilacao_nome": VENTILACAO[vent]["nome"], "recuperacao_calor": eta,
            "estanquidade": estanq, "n_inf": n_inf, "rph_min": rph, "q_ventilacao_m3h": q_tot, "q_extracao_m3h": q_ext, "q_infiltracao_m3h": tInf,
            "theta_transferencia": th_transf, "delta_u_pontes": dutb, "soma_psi_l": sum_psiL, "volume_m3": v_tot,
            "divisoes": rows, "phi_T": tT, "phi_V": tV, "phi_RH": tR, "phi_total": tT + tV + tR, "area_m2": area,
            "w_m2": (tT + tV + tR) / area if area else 0.0, "controles": ctl, "hipoteses": hyp}


# ------------------------------------------------------------------------------------------------------------- bomba de calor
def _f(te):
    """P(θe) / P(A7/W35) — lei indicativa de uma bomba de calor inverter recente (a substituir pela curva do fabricante)."""
    return max(0.45, min(1.1, 1 + 0.018 * (te - 7)))


def _f_ida(tv):
    """Correção indicativa da potência com a temperatura de ida (−1 %/K acima de 35 °C)."""
    return max(0.75, min(1.0, 1 - 0.01 * (tv - 35)))


def _cop(te, dep):
    return max(1.3, 4.4 - 0.11 * (7 - te) - 0.06 * (dep - 35))


def _interp(pts, x):
    """Interpolação linear (extrapolação pela inclinação do troço extremo)."""
    pts = sorted(pts)
    if len(pts) == 1:
        return pts[0][1]
    if x <= pts[0][0]:
        (x0, y0), (x1, y1) = pts[0], pts[1]
    elif x >= pts[-1][0]:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
    else:
        (x0, y0), (x1, y1) = next((a, b) for a, b in zip(pts, pts[1:]) if a[0] <= x <= b[0])
    return y0 + (y1 - y0) * (x - x0) / ((x1 - x0) or 1)


def rho_agua(t):
    t = max(RHO_AGUA[0][0], min(RHO_AGUA[-1][0], t))
    return _interp(RHO_AGUA, t)


def vaso_expansao(volume_l: float, t_max_c: float, altura_m: float, p_valvula_bar: float, t_enchimento_c: float = 10.0,
                  margem_p0_bar: float = 0.2) -> dict:
    """Vaso de expansão fechado de membrana — EN 12828, anexo D (pressões relativas em bar).
    p0 = pst + margem ; pe = psv − 0,5 bar (psv ≤ 5 bar) ou 0,9·psv ; Ve = e·V ; Vwr = max(0,5 % V, 3 L) ; Vn ≥ (Ve + Vwr)(pe + 1)/(pe − p0)."""
    pst = altura_m * 0.0981
    p0 = math.ceil((pst + margem_p0_bar) * 10 - 1e-9) / 10
    pe = p_valvula_bar - 0.5 if p_valvula_bar <= 5 else 0.9 * p_valvula_bar
    e = rho_agua(t_enchimento_c) / rho_agua(t_max_c) - 1
    ve = e * volume_l
    vwr = max(0.005 * volume_l, 3.0)
    ok = pe > p0
    vn = (ve + vwr) * (pe + 1) / (pe - p0) if ok else None
    return {"p_estatica_bar": pst, "p0_bar": p0, "pe_bar": pe, "expansao_pct": e * 100, "ve_l": ve, "vwr_l": vwr, "vn_min_l": vn,
            "vaso_l": next((v for v in VASOS_L if vn is not None and v >= vn - 1e-9), None), "realizavel": ok, "volume_l": volume_l,
            "t_max_c": t_max_c, "p_valvula_bar": p_valvula_bar}


def _classe_erp(eta, apl):
    return next((c for c, lim in ERP_CLASSES[apl] if eta >= lim), "< D")


def bomba_calor(D_w: float, te: float, p: dict) -> dict:
    """D_w : perdas de projeto (W) ; te : θe (°C) ; p : {emissores, temperatura_ida, theta_int, inercia, p_nominal_kw, p_theta_e_kw,
    cop_theta_e, curva_fabricante: [{theta_ext, p_kw, cop}], fator_apoio, tipo_apoio, volume_instalacao_l, volume_min_l_kw,
    caudal_emissores_lh, delta_t_k, altura_estatica_m, pressao_valvula_bar, t_max_c, vaso_integrado_l, scop, eta_s_pct,
    baixa_temperatura, alimentacao}"""
    D = D_w / 1000
    if D <= 0:
        raise ValueError("perdas de calor nulas: indicar as paredes / perdas das divisões antes de dimensionar a bomba de calor")
    em = p.get("emissores") or "piso_radiante"
    if em not in EMISSORES:
        raise ValueError(f"emissores desconhecidos {em!r} ({', '.join(EMISSORES)})")
    dep, l_kw = EMISSORES[em]
    tv = float(p.get("temperatura_ida") or dep)
    ti = float(p.get("theta_int") or 20)
    if ti <= te:
        raise ValueError("temperatura interior ≤ temperatura exterior de projeto")
    inercia = p.get("inercia") or "media"
    if inercia not in COBERTURA:
        raise ValueError(f"inércia desconhecida {inercia!r} ({', '.join(COBERTURA)})")
    cmin, cmax = COBERTURA[inercia]
    hyp: list[str] = []
    curva = [(float(c["theta_ext"]), float(c["p_kw"]), float(c["cop"]) if c.get("cop") is not None else None) for c in (p.get("curva_fabricante") or [])]
    fi = _f_ida(tv)
    if curva:
        Pf = lambda th: _interp([(a, b) for a, b, _ in curva], th)
        p_te = Pf(te)
        pn = float(p.get("p_nominal_kw") or Pf(7))
        fonte_p = "curva do fabricante"
        if not (min(a for a, _, _ in curva) - 1e-9 <= te <= max(a for a, _, _ in curva) + 1e-9):
            hyp.append(f"θe = {_g(te)} °C fora da curva do fabricante: potência extrapolada linearmente")
    elif p.get("p_theta_e_kw") is not None:
        p_te = float(p["p_theta_e_kw"])
        pn = float(p.get("p_nominal_kw") or p_te / (_f(te) * fi))
        Pf = lambda th: p_te * _f(th) / _f(te)
        fonte_p = "valor do fabricante a θe"
        hyp.append("variação da potência com θext fora de θe segundo a lei indicativa (curva de bivalência aproximada)")
    else:
        if p.get("p_nominal_kw"):
            pn = float(p["p_nominal_kw"])
        else:
            cov = {g: g * _f(te) * fi / D for g in GAMA_KW}
            ok = [g for g in GAMA_KW if cmin <= cov[g] <= cmax]
            pn = max(ok) if ok else next((g for g in GAMA_KW if cov[g] >= cmin), GAMA_KW[-1])
            hyp.append(f"potência nominal escolhida numa gama corrente: {_g(pn)} kW (A7/W35), " + (
                f"a maior cobertura sem exceder {cmax * 100:.0f} % a θe" if ok else
                (f"a menor da gama ({cov[pn] * 100:.0f} % a θe; perdas inferiores à gama)" if cov[pn] > cmax else
                 f"cobertura {cov[pn] * 100:.0f} % a θe")))
        Pf = lambda th: pn * _f(th) * fi
        p_te = Pf(te)
        fonte_p = "lei indicativa"
        hyp.append(f"potência a θe = {_g(te)} °C estimada em {_f(te) * fi * 100:.0f} % da nominal A7/W35 (lei indicativa"
                   + (f", ida {_g(tv)} °C" if fi < 1 else "") + "): usar a tabela do fabricante")
    # COP
    if curva and all(c is not None for _, _, c in curva):
        c_te = _interp([(a, c) for a, _, c in curva], te)
    elif p.get("cop_theta_e"):
        c_te = float(p["cop_theta_e"])
    else:
        c_te = _cop(te, tv)
        hyp.append(f"COP a θe e ida {_g(tv)} °C estimado em {_c(c_te, 2)} (indicativo): usar o valor do fabricante")
    cob = p_te / D
    # ponto de bivalência : P(θ) = D·(ti − θ)/(ti − te)
    nec = lambda th: D * (ti - th) / (ti - te)
    biv = None
    th, step = ti, 0.05
    prev = Pf(th) - nec(th)
    while th > te - 25:
        th2 = th - step
        cur = Pf(th2) - nec(th2)
        if prev >= 0 > cur:
            biv = th2 + step * cur / (cur - prev)
            break
        th, prev = th2, cur
    # apoio
    fa = float(p.get("fator_apoio") or 1.2)
    if p.get("fator_apoio") is None:
        hyp.append("apoio dimensionado para bomba de calor + apoio ≥ 1,2 × perdas (regra de boa prática; sem exigência regulamentar portuguesa) — "
                   "parâmetro fator_apoio")
    tipo_apoio = p.get("tipo_apoio") or "resistencia_eletrica"
    apoio = max(0.0, fa * D - p_te)
    apoio_kw = 0.0 if apoio <= 0.05 or tipo_apoio == "nenhum" else float(next((k for k in APOIO_KW if k >= apoio - 1e-9), math.ceil(apoio)))
    # hidráulica
    dt = float(p.get("delta_t_k") or 5)
    caudal = p_te * 1000 / (1.163 * dt)
    l_min = float(p.get("volume_min_l_kw") or 10)
    if p.get("volume_min_l_kw") is None:
        hyp.append("volume de água mínimo 10 L/kW de potência nominal (valor típico de fabricante, para descongelação e ciclos; a confirmar na ficha)")
    v_min = l_min * pn
    v_inst = float(p.get("volume_instalacao_l") or l_kw * D)
    if not p.get("volume_instalacao_l"):
        hyp.append(f"volume de água da instalação estimado em {l_kw} L/kW de perdas ({EMISSORES_PT[em]})")
    falta = max(0.0, v_min - v_inst)
    deposito = next((v for v in DEPOSITOS_L if v >= falta - 1e-9), math.ceil(falta / 50) * 50) if falta > 0 else 0
    # vaso de expansão (EN 12828)
    h = p.get("altura_estatica_m")
    if h is None:
        h = 3.0
        hyp.append("altura estática da instalação acima do vaso de expansão: 3 m por defeito (habitação num piso)")
    psv = p.get("pressao_valvula_bar")
    if psv is None:
        psv = 3.0
        hyp.append("válvula de segurança tarada a 3 bar por defeito (substituir pelo valor do equipamento)")
    tmax = p.get("t_max_c")
    if tmax is None:
        tmax = tv + 10
        hyp.append(f"temperatura máxima da água {_g(tmax)} °C (ida + 10 K) para a expansão; enchimento a 10 °C")
    vaso = vaso_expansao(v_inst + deposito, float(tmax), float(h), float(psv))
    vaso["integrado_l"] = float(p["vaso_integrado_l"]) if p.get("vaso_integrado_l") is not None else None
    hyp.append("vaso de expansão: reserva de água Vwr = 0,5 % do volume (mín. 3 L); margem p0 = pst + 0,2 bar (EN 12828 anexo D, a confirmar "
               "na edição em vigor); vaso e válvula ao mesmo nível")
    # eficiência sazonal (ErP) — exigência legal sobre o PRODUTO (aplicação de referência), desempenho do PROJETO à ida real
    produto_bt = bool(p.get("baixa_temperatura"))
    eta_min = ERP_MIN["baixa" if produto_bt else "media"]
    eta_ref = float(p["eta_s_pct"]) if p.get("eta_s_pct") else None
    apl = "baixa" if tv <= 40 else "media"
    if p.get("scop"):
        scop, scop_fonte = float(p["scop"]), "ficha"
    else:
        scop, scop_fonte = _interp(SCOP_INDICATIVO, min(max(tv, 35), 55)), "indicativo"
        hyp.append(f"SCOP indicativo {_c(scop, 1)} para ida {_g(tv)} °C — valor típico de mercado (clima médio EN 14825), NÃO da máquina: "
                   "usar a ficha de produto / EPREL")
    eta_s = 100 * scop / CC_ERP - 3
    hyp.append(f"η_s = 100·SCOP/CC − 3 % com CC = {_g(CC_ERP)} (Reg. (UE) 813/2013; a confirmar se o coeficiente de conversão for revisto); "
               "classes da etiqueta segundo o Reg. Delegado (UE) 811/2013 (indicativas)")
    # alimentação elétrica
    p_comp = p_te / c_te
    p_apoio_el = apoio_kw if tipo_apoio == "resistencia_eletrica" else 0.0
    p_abs = p_comp + p_apoio_el
    i_mono = p_abs * 1000 / (230 * 0.95)
    alim = p.get("alimentacao") or ("mono" if i_mono <= 32 else "tri")
    i_lin = i_mono if alim == "mono" else p_abs * 1000 / (math.sqrt(3) * 400 * 0.95)
    from .instalacoes import CALIBRES
    ib_c = p_comp * 1000 / ((230 if alim == "mono" else math.sqrt(3) * 400) * 0.9)
    disj_c, s_c = next(((c, s) for c, s in CALIBRES if c >= ib_c * 1.1), (None, None))
    ctl = [{"ref": "Cobertura à temperatura de projeto", "exigencia": f"P_BC(θe) entre {cmin * 100:.0f} e {cmax * 100:.0f} % das perdas (inércia {inercia}; "
                                                                    "boa prática, não regulamentar)",
            "valor": f"{_c(p_te)} / {_c(D)} kW = {cob * 100:.0f} %", "ok": cmin - 1e-9 <= cob <= cmax + 0.05,
            "note": "sobredimensionada: ciclos curtos, COP degradado (preferir modelo inverter de menor gama)" if cob > cmax + 0.05 else None},
           {"ref": "Bomba de calor + apoio", "exigencia": f"≥ {_g(fa)} × perdas", "valor": f"{_c(p_te + apoio_kw)} kW ≥ {_c(fa * D)} kW",
            "ok": p_te + apoio_kw >= fa * D - 1e-9 if tipo_apoio != "nenhum" else p_te >= fa * D - 1e-9,
            "note": None if tipo_apoio != "nenhum" or p_te >= fa * D - 1e-9 else "sem apoio: a bomba de calor não cobre o fator de segurança"},
           {"ref": "Ponto de bivalência", "exigencia": "θ de bivalência ≤ θe (a bomba de calor cobre sozinha) ou apoio dimensionado",
            "valor": (f"{_c(biv)} °C" if biv is not None else "< θe − 25 K"), "ok": True if (biv is None or biv <= te + 1e-6 or apoio_kw > 0) else False,
            "note": (f"abaixo de {_c(biv)} °C o apoio completa" if biv is not None and biv > te else None)},
           {"ref": "Volume de água mínimo", "exigencia": f"≥ {_g(l_min)} L/kW nominal ({v_min:.0f} L) — ficha do fabricante", "valor": f"{v_inst:.0f} L",
            "ok": v_inst >= v_min - 1e-9, "note": f"depósito de inércia {deposito:g} L em série no retorno" if deposito else None},
           {"ref": "Temperatura de ida", "exigencia": "≤ 55 °C (bomba de calor standard; acima: modelo de alta temperatura)",
            "valor": f"{_g(tv)} °C ({EMISSORES_PT[em]})", "ok": tv <= 55 or bool(p.get("alta_temperatura"))},
           {"ref": "Vaso de expansão (EN 12828, anexo D)",
            "exigencia": f"p0 ≥ {_c(vaso['p0_bar'])} bar, pressão final ≤ {_c(vaso['pe_bar'])} bar (válvula {_g(psv)} bar)",
            "valor": (f"Vn ≥ {_c(vaso['vn_min_l'])} L → {vaso['vaso_l'] or '> 300'} L (expansão {_c(vaso['expansao_pct'], 2)} % de {vaso['volume_l']:.0f} L, "
                      f"reserva {_c(vaso['vwr_l'])} L)") if vaso["realizavel"] else "pressão final ≤ pressão inicial: aumentar o tarado da válvula",
            "ok": (vaso["realizavel"] and (vaso["integrado_l"] is None or vaso["integrado_l"] >= vaso["vn_min_l"] - 1e-9)),
            "note": (f"vaso integrado de {_g(vaso['integrado_l'])} L insuficiente: vaso suplementar" if vaso["integrado_l"] is not None and vaso["realizavel"]
                     and vaso["integrado_l"] < vaso["vn_min_l"] else None)},
           {"ref": "Eficiência sazonal — Reg. (UE) 813/2013 (ecodesign)",
            "exigencia": f"η_s ≥ {eta_min} % na aplicação de referência do produto ("
                         + ("bomba de calor de baixa temperatura, 35 °C)" if produto_bt else "média temperatura, 55 °C)"),
            "valor": (f"η_s {eta_ref:.0f} % (ficha)" if eta_ref is not None else "a ler na ficha de produto / EPREL")
                     + f"; projeto (ida {_g(tv)} °C): SCOP {_c(scop, 2)} → η_s ≈ {eta_s:.0f} %, classe {_classe_erp(eta_s, apl)}"
                     + (" (indicativo)" if scop_fonte == "indicativo" else ""),
            "ok": (eta_ref >= eta_min) if eta_ref is not None else None},
           {"ref": "Alimentação elétrica", "exigencia": "circuito dedicado, diferencial 30 mA tipo A, disjuntor curva C/D; monofásica até ≈ 32 A (prática)",
            "valor": f"{_c(p_abs)} kW absorvidos → {_c(i_lin)} A ({'monofásica 230 V' if alim == 'mono' else 'trifásica 400 V'})"
                     + (f"; compressor {disj_c} A / {_g(s_c)} mm²" if disj_c else ""),
            "ok": (i_mono <= 32 or alim == "tri") and disj_c is not None}]
    if p.get("caudal_emissores_lh") is not None and float(p["caudal_emissores_lh"]) < 0.9 * caudal:
        ctl.append({"ref": "Caudal da bomba de calor / caudal dos emissores", "exigencia": f"caudal dos emissores ≥ caudal nominal (ΔT {_g(dt)} K)",
                    "valor": f"{float(p['caudal_emissores_lh']):.0f} L/h < {caudal:.0f} L/h", "ok": False,
                    "note": "separador hidráulico ou depósito de inércia em paralelo (≈ 20 L/kW), ou by-pass diferencial"})
    if tipo_apoio not in APOIO_PT:
        raise ValueError(f"tipo de apoio desconhecido {tipo_apoio!r} ({', '.join(APOIO_PT)})")
    hyp.append(f"potência da bomba de calor: {fonte_p}; apoio: {APOIO_PT[tipo_apoio]}")
    regras = ["Unidade exterior: afastamentos e escoamento dos condensados (sem gelo em passagens), apoios antivibráticos; nível sonoro a verificar "
              "face ao Regulamento Geral do Ruído junto dos vizinhos.",
              "Circuito hidráulico: válvula de segurança, purgadores, filtro/separador de lamas magnético antes da bomba de calor, glicol ou proteção anticongelação "
              "se a unidade estiver no exterior com tubagem exposta.",
              "Gases fluorados (Reg. (UE) 2024/573): instalação e manutenção por técnico certificado; monobloco evita manuseamento de fluido em obra.",
              "Programas de apoio do Fundo Ambiental para bombas de calor podem estar abertos: verificar os avisos em vigor (condições e montantes não incluídos)."]
    return {"emissores": em, "temperatura_ida": tv, "theta_e": te, "theta_int": ti, "perdas_kw": D, "inercia": inercia, "p_nominal_kw": pn,
            "p_theta_e_kw": p_te, "fonte_potencia": fonte_p, "cobertura": cob, "cop": c_te, "apoio_kw": apoio_kw, "tipo_apoio": tipo_apoio,
            "fator_apoio": fa, "bivalencia_c": biv, "caudal_lh": caudal, "delta_t_k": dt, "volume_instalacao_l": v_inst, "volume_min_l": v_min,
            "deposito_inercia_l": deposito, "vaso": vaso, "scop": scop, "scop_fonte": scop_fonte, "eta_s_pct": eta_s, "eta_s_produto_pct": eta_ref,
            "eta_s_min_pct": eta_min, "aplicacao_erp": apl,
            "classe_erp": _classe_erp(eta_s, apl), "p_compressor_kw": p_comp, "p_absorvida_kw": p_abs, "corrente_mono_a": i_mono,
            "alimentacao": alim, "corrente_a": i_lin, "disjuntor_compressor_a": disj_c, "seccao_compressor_mm2": s_c,
            "curva": [(round(x, 1), Pf(x)) for x in [te - 5 + 0.5 * k for k in range(int((22 - te) / 0.5) + 1)]],
            "controles": ctl, "hipoteses": hyp, "regras": regras}


def _curva_bc(bc, te=None, D_w=None, ti=None):
    """Potência da bomba de calor e necessidades do edifício em função de θext → (Drawing, bivalência)."""
    from . import graficos as G
    te = bc["theta_e"] if te is None else te
    D = bc["perdas_kw"] if D_w is None else D_w / 1000
    ti = bc.get("theta_int", 20.0) if ti is None else ti
    pts = [(x, y) for x, y in bc["curva"] if x <= 15]
    xs = [x for x, _ in pts]
    nec = lambda x: max(0.0, D * (ti - x) / (ti - te)) if ti > te else 0.0
    series = [("Necessidades do edifício", [nec(x) for x in xs], G.SERIES[1]), ("Bomba de calor", [y for _, y in pts], G.SERIES[0])]
    if bc["apoio_kw"]:
        series.append(("Bomba de calor + apoio", [y + bc["apoio_kw"] for _, y in pts], G.SERIES[2]))
    m = [(te, D, f"θe {_g(te)} °C: {_c(D)} kW")]
    biv = bc.get("bivalencia_c")
    if biv is not None and biv > te + 0.2 and biv <= xs[-1]:
        if biv - te < 4:      # marcadores próximos: um único rótulo para não sobrepor os textos
            m[0] = (te, D, "")
            m.append((biv, nec(biv), f"bivalência {_c(biv)} °C (θe {_g(te)} °C: {_c(D)} kW)"))
        else:
            m.append((biv, nec(biv), f"bivalência {_c(biv)} °C"))
    ticks = [(v, f"{v:g}") for v in range(int(math.ceil(xs[0] / 5)) * 5, int(xs[-1]) + 1, 5)]
    return G.courbes(xs, series, "Potência da bomba de calor e necessidades", "kW", xlab="temperatura exterior (°C)", marques=m, labels_x=ticks), biv


def note(params: dict) -> dict:
    from . import notes
    r = perdas(params)
    hip = list(r["hipoteses"])
    kp = [{"label": f"Perdas de projeto (θe {_g(r['theta_e'])} °C)", "value": _c(r["phi_total"] / 1000, 2), "unit": "kW"},
          {"label": "Perdas por m²", "value": f"{r['w_m2']:.0f}", "unit": "W/m²"},
          {"label": "Caudal de ventilação", "value": f"{r['q_ventilacao_m3h']:.0f}", "unit": "m³/h"}]
    blocs = [("p", "Pré-dimensionamento indicativo — não substitui o projeto de AVAC nem o pré-certificado SCE.")]
    blocs += notes.blocos_perdas(r, "1. ")
    out = {"perdas": r}
    if params.get("bomba_calor") is not None:
        bc = bomba_calor(r["phi_total"], r["theta_e"], params["bomba_calor"] or {})
        out["bomba_calor"] = bc
        hip += bc["hipoteses"]
        blocs += notes.blocos_bomba_calor(bc, "2. ")
        kp.append({"label": "Bomba de calor (A7/W35)", "value": _g(bc["p_nominal_kw"]), "unit": "kW",
                   "ok": all(c["ok"] is not False for c in bc["controles"])})
    blocs = [("kpis", kp)] + blocs
    titre = "Pré-dimensionamento — aquecimento"
    pdf, png = notes.pdf(titre, "EN 12831-1 · REH" + (" · EN 12828 · Reg. (UE) 813/2013" if "bomba_calor" in out else ""), blocs, hip)
    return {**out, "titre": titre, "pdf": pdf, "png": png}
