"""Aquecimento (Portugal) — perdas de calor de projeto divisão a divisão (EN 12831-1, método simplificado) e pré-dimensionamento
de bomba de calor ar/água. Pré-dimensionamento indicativo.

Φ_HL,i = Φ_T,i + Φ_V,i (+ Φ_RH,i reaquecimento opcional)
  Φ_T,i = Σ A·U·b·(θint,i − θe) + Σ ψ·L·(θint,i − θe)
  Φ_V,i = 0,34 · q_v,i · (θint,i − θe)
Temperatura exterior de projeto θe: indicada pelo utilizador ou, por defeito, θext,i do REH (temperatura média do mês mais frio,
corrigida em altitude) menos um desvio de 8 K (hipótese a validar com os dados climáticos de projeto, p. ex. CLIMAS-SCE).
Caudais de ventilação mínimos por defeito: 0,4 renovações/h (Portaria 138-I/2021, habitação) ou extração das zonas húmidas.
"""
from __future__ import annotations

import math

from . import reh

T_INT = {"sala": 20, "quarto": 20, "cozinha": 20, "casa_de_banho": 22, "corredor": 18, "escritorio": 20, "lavandaria": 18,
         "arrumos": 15, "outro": 20}
B = {"exterior": 1.0, "enu": 0.8, "enu_ventilado": 1.0, "adjacente": 0.6, "solo": 0.45, "fracao_vizinha": 0.0, "aquecido": 0.0}
INFILTRACAO = {"muito_estanque": 0.05, "estanque": 0.10, "media": 0.20, "antiga": 0.40}
EXTRACAO = {"cozinha": 75, "casa_de_banho": 45, "lavandaria": 30}       # m³/h (valores de referência NP 1037-1, a confirmar)
PRINCIPAIS = ("sala", "quarto", "escritorio")
DESVIO_PROJETO = 8.0
GAMA_KW = [3, 4, 5, 6, 8, 10, 11, 12, 14, 16]
EMISSORES = {"piso_radiante": (35, 17), "radiadores_bt": (45, 9), "radiadores_ht": (55, 9), "ventiloconvectores": (35, 3)}


def theta_projeto(p: dict, hyp: list) -> tuple[float, str]:
    if p.get("theta_e") is not None:
        return float(p["theta_e"]), "indicada"
    c = reh.clima(p.get("concelho"), p.get("nuts"), p.get("altitude_m"))
    if c.get("aviso"):
        hyp.append(c["aviso"])
    te = round(c["theta_i"] - DESVIO_PROJETO, 1)
    hyp.append(f"θe de projeto = θext,i REH {c['theta_i']:.1f} °C ({c['nuts']}, {c['altitude_m']:.0f} m) − {DESVIO_PROJETO:g} K = {te:g} °C "
               "(desvio indicativo; confirmar com a temperatura exterior de projeto)")
    return te, f"REH {c['nuts']}"


def perdas(p: dict) -> dict:
    hyp: list[str] = []
    te, src = theta_projeto(p, hyp)
    div = p.get("divisoes") or []
    if not div:
        raise ValueError("indicar as divisões (tipo, área, paredes com U)")
    eta = float(p.get("recuperacao_calor") or 0)
    n_inf = INFILTRACAO.get(p.get("estanquidade") or "estanque", 0.10)
    rph = float(p.get("rph_min") or 0.4)
    vols = [float(d.get("area_m2") or 0) * float(d.get("pe_direito_m") or 2.6) for d in div]
    tipos = [(d.get("tipo") or "outro") for d in div]
    for t in tipos:
        if t not in T_INT:
            raise ValueError(f"tipo de divisão desconhecido {t!r} ({', '.join(T_INT)})")
    v_tot = sum(vols) or 1.0
    q_ext = sum(EXTRACAO.get(t, 0) for t in tipos)
    q_tot = max(q_ext, rph * v_tot)
    v_pr = sum(v for v, t in zip(vols, tipos) if t in PRINCIPAIS) or v_tot
    dutb = p.get("delta_u_pontes")
    if dutb is None and not any(d.get("pontes") for d in div):
        dutb = 0.10
        hyp.append("pontes térmicas não descritas: majoração forfetária ΔU = 0,10 W/(m².°C) nas paredes da envolvente")
    dutb = float(dutb or 0)
    rows, tT, tV, tR = [], 0.0, 0.0, 0.0
    for d, V, t in zip(div, vols, tipos):
        ti = float(d.get("theta_int") or T_INT[t])
        dT = ti - te
        phiT = 0.0
        for w in d.get("paredes") or []:
            lado = w.get("lado") or "exterior"
            if lado not in B and w.get("b") is None:
                raise ValueError(f"lado desconhecido {lado!r} ({', '.join(B)})")
            b = float(w["b"]) if w.get("b") is not None else B[lado]
            if b <= 0:
                continue
            phiT += float(w["area_m2"]) * (float(w["U"]) + dutb) * b * dT
        for s in d.get("pontes") or []:
            phiT += float(s["comprimento_m"]) * float(s["psi"]) * dT
        if t in PRINCIPAIS or not q_ext:
            q = q_tot * V / v_pr * (1 - eta) if (t in PRINCIPAIS or v_pr == v_tot) else 0.0
            phiV = 0.34 * (q + n_inf * V) * dT
        else:
            q = EXTRACAO.get(t, 0)
            phiV = 0.34 * q * max(ti - 20, 0) + 0.34 * n_inf * V * dT
        phiR = float(p.get("reaquecimento_w_m2") or 0) * float(d.get("area_m2") or 0)
        A = float(d.get("area_m2") or 0)
        tot = phiT + phiV + phiR
        rows.append({"nome": d.get("nome") or t, "tipo": t, "theta_int": ti, "area_m2": A, "phi_T": phiT, "phi_V": phiV, "phi_RH": phiR, "phi": tot,
                     "w_m2": tot / A if A else 0.0})
        tT += phiT; tV += phiV; tR += phiR
    area = sum(r["area_m2"] for r in rows)
    hyp.append(f"ventilação: max(extração das zonas húmidas {q_ext:.0f} m³/h, {rph:g} RPH) = {q_tot:.0f} m³/h distribuída pelas divisões principais; "
               f"infiltrações {n_inf:g} RPH somadas (abordagem prudente); pavimento sobre o solo por fator b forfetário")
    return {"theta_e": te, "theta_e_fonte": src, "q_ventilacao_m3h": q_tot, "divisoes": rows, "phi_T": tT, "phi_V": tV, "phi_RH": tR,
            "phi_total": tT + tV + tR, "area_m2": area, "w_m2": (tT + tV + tR) / area if area else 0.0, "hipoteses": hyp}


def _f(te):
    return max(0.45, min(1.1, 1 + 0.018 * (te - 7)))


def _cop(te, dep):
    return max(1.3, 4.4 - 0.11 * (7 - te) - 0.06 * (dep - 35))


def bomba_calor(D_w: float, te: float, p: dict) -> dict:
    D = D_w / 1000
    em = p.get("emissores") or "piso_radiante"
    if em not in EMISSORES:
        raise ValueError(f"emissores desconhecidos {em!r} ({', '.join(EMISSORES)})")
    dep, l_kw = EMISSORES[em]
    hyp = []
    if p.get("p_theta_e_kw") is not None:
        p_te = float(p["p_theta_e_kw"])
        pn = float(p.get("p_nominal_kw") or p_te / _f(te))
    else:
        pn = float(p["p_nominal_kw"]) if p.get("p_nominal_kw") else \
            max([g for g in GAMA_KW if 0.7 <= g * _f(te) / D <= 1.0] or [next((g for g in GAMA_KW if g * _f(te) / D >= 0.7), GAMA_KW[-1])])
        p_te = pn * _f(te)
        hyp.append(f"potência a θe = {te:g} °C estimada em {_f(te) * 100:.0f} % da nominal A7/W35 (lei indicativa): usar a tabela do fabricante")
    c = float(p.get("cop_theta_e") or _cop(te, dep))
    cob = p_te / D if D else 0
    apoio = max(0.0, 1.2 * D - p_te)
    apoio_kw = 0.0 if apoio <= 0.05 else float(next((k for k in (2, 3, 4, 6, 9) if k >= apoio), math.ceil(apoio)))
    v_inst = float(p.get("volume_instalacao_l") or l_kw * D)
    p_abs = p_te / c + apoio_kw
    i_mono = p_abs * 1000 / (230 * 0.95)
    ctl = [{"ref": "Cobertura à temperatura de projeto", "exigencia": "P_BC(θe) entre 70 e 100 % das perdas", "valor": f"{p_te:.1f} / {D:.1f} kW = {cob * 100:.0f} %",
            "ok": 0.7 - 1e-9 <= cob <= 1.05, "note": "sobredimensionada: ciclos curtos, COP degradado (preferir modelo inverter de menor gama)" if cob > 1.05 else None},
           {"ref": "Bomba de calor + apoio", "exigencia": "≥ 1,2 × perdas", "valor": f"{p_te + apoio_kw:.1f} kW ≥ {1.2 * D:.1f} kW", "ok": p_te + apoio_kw >= 1.2 * D - 1e-9},
           {"ref": "Volume de água mínimo", "exigencia": f"≥ 10 L/kW ({10 * pn:.0f} L)", "valor": f"{v_inst:.0f} L", "ok": v_inst >= 10 * pn,
            "note": f"depósito de inércia ≥ {math.ceil((10 * pn - v_inst) / 10) * 10:.0f} L" if v_inst < 10 * pn else None},
           {"ref": "Alimentação elétrica", "exigencia": "monofásica até 32 A; diferencial 30 mA tipo A dedicado", "valor": f"{p_abs:.1f} kW → {i_mono:.1f} A",
            "ok": i_mono <= 32 or p.get("alimentacao") == "tri"}]
    hyp.append(f"COP a θe e ida {dep} °C: {c:.2f}" + ("" if p.get("cop_theta_e") else " (indicativo)"))
    return {"emissores": em, "temperatura_ida": dep, "p_nominal_kw": pn, "p_theta_e_kw": p_te, "cobertura": cob, "cop": c, "apoio_kw": apoio_kw,
            "caudal_lh": p_te * 1000 / (1.163 * 5), "volume_instalacao_l": v_inst, "p_absorvida_kw": p_abs, "corrente_mono_a": i_mono, "controles": ctl, "hipoteses": hyp}


def note(params: dict) -> dict:
    from . import notes
    W = notes.W
    r = perdas(params)
    hip = list(r["hipoteses"])
    blocs = [("p", "Pré-dimensionamento indicativo — não substitui o projeto de AVAC nem o pré-certificado SCE."),
             ("h2", "1. Perdas de calor de projeto (EN 12831-1)"),
             ("p", f"θe = {r['theta_e']:g} °C ({r['theta_e_fonte']}); ventilação {r['q_ventilacao_m3h']:.0f} m³/h; total {r['phi_total']:.0f} W "
                   f"({r['w_m2']:.0f} W/m² sobre {r['area_m2']:.0f} m²)."),
             ("table", ["Divisão", "θint °C", "m²", "Φ_T W", "Φ_V W", "Φ W", "W/m²"],
              [[x["nome"], f"{x['theta_int']:g}", f"{x['area_m2']:.1f}", f"{x['phi_T']:.0f}", f"{x['phi_V']:.0f}", f"{x['phi']:.0f}", f"{x['w_m2']:.0f}"]
               for x in r["divisoes"]], [45 * W, 18 * W, 15 * W, 20 * W, 20 * W, 20 * W, 18 * W])]
    out = {"perdas": r}
    if params.get("bomba_calor") is not None:
        bc = bomba_calor(r["phi_total"], r["theta_e"], params["bomba_calor"] or {})
        out["bomba_calor"] = bc
        hip += bc["hipoteses"]
        blocs += [("h2", "2. Bomba de calor ar/água"),
                  ("p", f"Nominal {bc['p_nominal_kw']:g} kW (A7/W35) → {bc['p_theta_e_kw']:.1f} kW a θe ({bc['cobertura'] * 100:.0f} %), apoio "
                        f"{bc['apoio_kw']:g} kW, caudal {bc['caudal_lh']:.0f} L/h, emissores {bc['emissores'].replace('_', ' ')} (ida {bc['temperatura_ida']} °C)."),
                  ("controls", [{"ref": c["ref"], "exigence": c["exigencia"], "valeur": c["valor"], "ok": c["ok"], "note": c.get("note")} for c in bc["controles"]])]
    titre = "Pré-dimensionamento — aquecimento"
    pdf, png = notes.pdf(titre, "EN 12831-1 · REH", blocs, hip)
    return {**out, "titre": titre, "pdf": pdf, "png": png}
