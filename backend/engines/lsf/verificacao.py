"""Verificação estrutural do motor LSF (aço leve enformado a frio) — determinística, sem IA.

Reaproveita os motores existentes do ConstruPilot:
  - combinações EN 1990 ............ engines.structuro_eurocode.generate (γG 1,35 / γQ 1,5 / ψ por categoria)
  - neve, vento, sobrecargas PT ...... engines.acoes_pt (NP EN 1991-1-1 / -1-3 zonas Z1–Z3 / -1-4 zonas A/B)
  - encurvadura + flexão composta .... engines.structuro_ec3.verify_column (§6.3.1 e §6.3.3 método 2, Anexo B)
  - estado de utilização ............. engines.structuro_check.util_status / DISCLAIMER

e acrescenta o que é próprio do aço enformado a frio (NP EN 1993-1-3 / NP EN 1993-1-5):
  - secção efetiva dos perfis C com reforço de bordo: larguras efetivas (1-5 §4.4) e encurvadura distorcional
    do reforço (1-3 §5.5.3.2, mola K do eq. 5.10b, χd do eq. 5.12) → Aeff, Weff,y
  - resistência ao esforço transverso com encurvadura da alma (1-3 §6.1.5, Quadro 6.1, sem reforço no apoio)
  - asnas Fink resolvidas como treliça de nós articulados (método dos deslocamentos) + flexão local dos banzos
  - descida de cargas: cobertura → paredes de apoio → pisos → paredes inferiores, por linha de apoio geométrica

Âmbito (dito no resultado): pré-dimensionamento indicativo. NÃO verifica: encurvadura por flexão-torção dos montantes
(supõe-se o travamento pelas placas parafusadas), esmagamento da alma nos apoios (1-3 §6.1.7), ligações aparafusadas,
resistência das ancoragens e da parede ao corte (dados do fabricante), ação sísmica (NP EN 1998-1), fogo.
Todos os coeficientes são parâmetros com a sua origem e podem ser alterados no projeto (chave « verificacao »).
"""
from __future__ import annotations

import math
import re

import numpy as np

from engines import structuro_ec3 as EC3
from engines import structuro_eurocode as EN1990
from engines.structuro_calc import Action
from engines.structuro_check import DISCLAIMER, util_status
from engines import acoes_pt as NORMAS

VERSAO = "lsf-verificacao-1.0"
E = 210000.0          # MPa
NU = 0.3
G_ACO = 78.5          # kN/m³

# --------------------------------------------------------------------------------------------- parâmetros por omissão
PARAMETROS = {
    "uso": "habitation",                 # categoria A (NP EN 1991-1-1) → qk = 2,0 kN/m² em PT
    "divisorias_kn_m2": 0.5,             # divisórias amovíveis ≤ 1 kN/m (NP EN 1991-1-1 §6.3.1.2(8))
    "g_piso_kn_m2": 0.60,                # OSB + revestimento + teto + isolamento (sem peso das vigas, calculado à parte)
    "g_cobertura_kn_m2": 0.70,           # telha cerâmica + ripado + OSB + subtelha, na vertente
    "g_teto_kn_m2": 0.30,                # teto de gesso + isolamento suspensos no banzo inferior
    "g_parede_ext_kn_m2": 0.45,          # OSB + gesso + isolamento + ETICS (sem perfis)
    "g_parede_int_kn_m2": 0.30,          # gesso nas duas faces + isolamento (sem perfis)
    "zona_vento": "A", "zona_neve": "Z2", "altitude_m": 100.0,
    "cpe_parede_pressao": 0.8,           # zona D
    "cpe_parede_succao": -1.2,           # zona A (cantos) — governa os montantes
    "cpi_pos": 0.2, "cpi_neg": -0.3,
    "cpe_cob_pressao": 0.5,              # vertentes a ~30°, θ = 0°, média F/G/H
    "cpe_cob_succao": -0.5,
    "cf_global": 1.1,                    # (cpe,D − cpe,E) × 0,85 — força global para o contraventamento
    "flecha_piso_total": 250, "flecha_piso_q": 300, "flecha_verga": 300,
    "gamma_m0": 1.0, "gamma_m1": 1.0,
    "ancoragem_resistencia_kn": None,    # resistência de cálculo de uma ancoragem (fabricante) — sem valor, só o esforço
    "contraventamento_vrd_kn_m": None,   # resistência ao corte da parede contraventada (ensaio / fabricante)
}
FONTES = {
    "uso": "NP EN 1991-1-1 Quadro 6.2 (valores do AN PT via engines.acoes_pt)",
    "divisorias_kn_m2": "NP EN 1991-1-1 §6.3.1.2(8)",
    "g_piso_kn_m2": "hipótese de projeto — a confirmar com os acabamentos",
    "g_cobertura_kn_m2": "hipótese de projeto — a confirmar com o revestimento da cobertura",
    "g_teto_kn_m2": "hipótese de projeto",
    "g_parede_ext_kn_m2": "hipótese de projeto (camadas do tipo de parede)",
    "g_parede_int_kn_m2": "hipótese de projeto",
    "zona_vento": "NP EN 1991-1-4 AN PT (zonas A/B)", "zona_neve": "NP EN 1991-1-3 AN PT (Z1–Z3)",
    "cpe_parede_pressao": "NP EN 1991-1-4 Quadro 7.1 zona D", "cpe_parede_succao": "NP EN 1991-1-4 Quadro 7.1 zona A (cpe,10)",
    "cpi_pos": "NP EN 1991-1-4 §7.2.9(6) nota 2", "cpi_neg": "NP EN 1991-1-4 §7.2.9(6) nota 2",
    "cpe_cob_pressao": "NP EN 1991-1-4 Quadro 7.4a (média, a confirmar)", "cpe_cob_succao": "NP EN 1991-1-4 Quadro 7.4a (média, a confirmar)",
    "cf_global": "NP EN 1991-1-4 Quadro 7.1 + §7.2.2(3) (falta de correlação)",
    "flecha_piso_total": "NP EN 1990 A1.4 / prática corrente", "flecha_piso_q": "NP EN 1990 A1.4 / prática corrente",
    "flecha_verga": "prática corrente",
    "gamma_m0": "NP EN 1993-1-3 §2(3) (valor recomendado)", "gamma_m1": "NP EN 1993-1-3 §2(3) (valor recomendado)",
}

CATEGORIAS = {"Q": "A", "H": "H", "S": "neige_bas", "W": "vent"}


def _fy(projeto: dict) -> float:
    m = re.search(r"(\d{3})", str((projeto.get("aco") or {}).get("grau") or "S350GD"))
    return float(m.group(1)) if m else 350.0


# =========================================================================================== secção efetiva (1-3 / 1-5)
def _rho_interno(lp: float, psi: float) -> float:
    lim = 0.5 + math.sqrt(0.085 - 0.055 * psi)
    return 1.0 if lp <= lim else min(1.0, (lp - 0.055 * (3 + psi)) / lp ** 2)


def _rho_saliente(lp: float) -> float:
    return 1.0 if lp <= 0.748 else min(1.0, (lp - 0.188) / lp ** 2)


def _lambda_p(bp: float, t: float, ksig: float, fy: float) -> float:
    eps = math.sqrt(235.0 / fy)
    return (bp / t) / (28.4 * eps * math.sqrt(ksig))


def _props(segs):
    """Propriedades de uma secção de paredes finas: segs = [(y1, z1, y2, z2, t)] (linha média, mm)."""
    A = sum(math.hypot(y2 - y1, z2 - z1) * t for y1, z1, y2, z2, t in segs)
    if A <= 0:
        return {"A": 0.0, "yc": 0.0, "zc": 0.0, "Iy": 0.0, "Iz": 0.0, "zmax": 0.0, "zmin": 0.0}
    yc = sum(math.hypot(y2 - y1, z2 - z1) * t * (y1 + y2) / 2 for y1, z1, y2, z2, t in segs) / A
    zc = sum(math.hypot(y2 - y1, z2 - z1) * t * (z1 + z2) / 2 for y1, z1, y2, z2, t in segs) / A
    Iy = Iz = 0.0
    for y1, z1, y2, z2, t in segs:
        L = math.hypot(y2 - y1, z2 - z1)
        a1, a2 = z1 - zc, z2 - zc
        b1, b2 = y1 - yc, y2 - yc
        Iy += t * L * (a1 * a1 + a1 * a2 + a2 * a2) / 3      # ∫ z² ds·t
        Iz += t * L * (b1 * b1 + b1 * b2 + b2 * b2) / 3
    zs = [z for s in segs for z in (s[1], s[3])]
    return {"A": A, "yc": yc, "zc": zc, "Iy": Iy, "Iz": Iz, "zmax": max(zs) - zc, "zmin": zc - min(zs)}


def _reforco(bc, cc, be2, t, fy, hw):
    """Reforço de bordo (banzo be2 + lábio): lábio efetivo (kσ eq. 5.13b/c), mola K (1-3 eq. 5.10b, kf = 1),
    σcr,s (eq. 5.15), χd (eq. 5.12). b1 = distância da junção alma-banzo ao centro de gravidade do reforço."""
    lp = _lambda_p(cc, t, 0.5 if cc / bc <= 0.35 else 0.5 + 0.83 * ((cc / bc - 0.35) ** 2) ** (1 / 3), fy)
    ceff = _rho_saliente(lp) * cc
    b1 = (be2 * (bc - be2 / 2) + ceff * bc) / (be2 + ceff)
    As = t * (be2 + ceff)
    zc = -(ceff * ceff / 2) / (be2 + ceff)                    # eixo paralelo ao banzo (lábio para dentro)
    Is = be2 * t * zc * zc + t * ceff ** 3 / 12 + ceff * t * (ceff / 2 + zc) ** 2
    K = E * t ** 3 / (4 * (1 - NU ** 2)) / (b1 * b1 * hw + b1 ** 3 + 0.5 * b1 * b1 * hw)
    scr = 2 * math.sqrt(K * E * Is) / As if As > 0 else 0.0
    ld = math.sqrt(fy / scr) if scr > 0 else 9.9
    chi = 1.0 if ld <= 0.65 else (1.47 - 0.723 * ld if ld < 1.38 else 0.66 / ld)
    return ceff, max(0.0, min(1.0, chi)), scr


def seccao(sec: dict, fy: float) -> dict:
    """Propriedades brutas e efetivas de um perfil C (com lábios) ou U (sem lábios); mm, mm², mm⁴, mm³."""
    h, b, t = float(sec["h"]), float(sec["b"]), float(sec["t"])
    c = float(sec.get("c") or 0.0)
    hc, bc, cc = h - t, b - t, (c - t / 2 if c > 0 else 0.0)
    zt, zb = hc / 2, -hc / 2
    bruta = [(0, zb, 0, zt, t), (0, zt, bc, zt, t), (0, zb, bc, zb, t)]
    if cc > 0:
        bruta += [(bc, zt, bc, zt - cc, t), (bc, zb, bc, zb + cc, t)]
    G = _props(bruta)
    avisos = []

    def banzo(z, sinal):
        """Banzo comprimido + lábio efetivos → lista de segmentos e χd."""
        if cc > 0:
            rf = _rho_interno(_lambda_p(bc, t, 4.0, fy), 1.0)
            be = rf * bc
            be1, be2 = 0.5 * be, 0.5 * be
            ceff, chi, _ = _reforco(bc, cc, be2, t, fy, hc)
            tr = chi * t
            return [(0, z, be1, z, t), (bc - be2, z, bc, z, tr), (bc, z, bc, z - sinal * ceff, tr)], chi
        lp = _lambda_p(bc, t, 0.43, fy)
        return [(0, z, _rho_saliente(lp) * bc, z, t)], 1.0

    # compressão uniforme
    rw = _rho_interno(_lambda_p(hc, t, 4.0, fy), 1.0)
    bew = rw * hc
    sup, chi_s = banzo(zt, +1)
    inf, _ = banzo(zb, -1)
    comp = [(0, zt, 0, zt - bew / 2, t), (0, zb, 0, zb + bew / 2, t)] + sup + inf
    C = _props(comp)
    # flexão segundo y (banzo superior comprimido): alma com ψ = −1 (kσ = 23,9)
    rwb = _rho_interno(_lambda_p(hc, t, 23.9, fy), -1.0)
    bc_w = hc / 2
    beff = rwb * bc_w
    flex = [(0, zt, 0, zt - 0.4 * beff, t), (0, zt - 0.4 * beff - (bc_w - beff), 0, zb, t)] + sup
    flex += [(0, zb, bc, zb, t)] + ([(bc, zb, bc, zb + cc, t)] if cc > 0 else [])
    if rwb >= 1.0:
        flex[0:2] = [(0, zt, 0, zb, t)]
    F = _props(flex)
    weff = F["Iy"] / max(F["zmax"], F["zmin"]) if F["Iy"] > 0 else 0.0
    # esforço transverso (1-3 §6.1.5, Quadro 6.1 sem reforço no apoio)
    lw = 0.346 * (hc / t) * math.sqrt(fy / E)
    fbv = 0.58 * fy if lw <= 0.83 else (0.48 * fy / lw if lw < 1.40 else 0.67 * fy / lw ** 2)
    if cc > 0 and not (0.2 <= cc / bc <= 0.6):
        avisos.append(f"Lábio c/b = {cc / bc:.2f} fora de 0,2–0,6 (1-3 §5.2): reforço de bordo pouco eficaz.")
    return {"tipo": sec.get("tipo"), "h": h, "b": b, "c": c, "t": t, "fy": fy,
            "A": G["A"], "Iy": G["Iy"], "Iz": G["Iz"], "Wel_y": G["Iy"] / (hc / 2 + t / 2),
            "Aeff": C["A"], "Weff_y": weff, "Ieff_y": F["Iy"], "chi_d": chi_s, "rho_alma": rw,
            "Vb_N": hc * t * fbv, "fbv": fbv, "lambda_w": lw, "kg_m": G["A"] * 7850e-9 * 1000,
            "avisos": avisos}


# =========================================================================================== ações
def acoes(projeto: dict, par: dict, H_total_m: float, inclinacao: float | None) -> dict:
    warns: list = []
    raw = {"project": {"snow_zone": par["zona_neve"], "altitude_m": par["altitude_m"], "wind_zone": par["zona_vento"]}}
    sn = NORMAS.snow(raw, "PT", warns)
    wd = NORMAS.wind(raw, "PT", max(H_total_m, 1.0), warns)
    a = inclinacao or 0.0
    mu1 = 0.8 if a <= 30 else (0.8 * (60 - a) / 30 if a < 60 else 0.0)
    s = mu1 * sn["sk"]
    q = NORMAS.q_use("PT", par["uso"]) + par["divisorias_kn_m2"]
    qH = NORMAS.q_use("PT", "toiture")
    qp = wd["qp"]
    return {"sk": sn["sk"], "mu1": round(mu1, 3), "s": round(s, 3), "fonte_neve": sn["source"],
            "qp": qp, "vb": wd["vb"], "fonte_vento": wd["source"] + " (categoria de terreno III)",
            "q_piso": q, "q_cobertura": qH,
            "w_parede": qp * max(par["cpe_parede_pressao"] - par["cpi_neg"], -(par["cpe_parede_succao"] - par["cpi_pos"])),
            "w_cob_baixo": qp * (par["cpe_cob_pressao"] - par["cpi_neg"]),
            "w_cob_cima": qp * (par["cpe_cob_succao"] - par["cpi_pos"]),       # negativo = levantamento
            "w_global": qp * par["cf_global"]}


def combinacoes() -> list[dict]:
    acts = [Action(id="G", kind="G", label="Permanentes"), Action(id="Q", kind="Q", label="Sobrecarga de piso"),
            Action(id="H", kind="Q", label="Sobrecarga de cobertura"), Action(id="S", kind="Q", label="Neve"),
            Action(id="W", kind="Q", label="Vento")]
    out = []
    for c in EN1990.generate(acts, CATEGORIAS, {"uls": True, "sls_char": True, "sls_freq": False, "sls_qp": True}):
        f = dict(c.factors)
        if f.get("H", 0) > 0:                       # NP EN 1991-1-1 §3.3.2(1): H não simultânea com neve nem vento
            f["S"] = f["W"] = 0.0
        out.append({"id": c.id, "label": c.label, "factors": f, "fonte": c.source.note})
    out.append({"id": "ELU_lev", "label": "ELU STR — vento de levantamento (permanentes favoráveis)",
                "factors": {"G": EN1990.GAMMA["G_inf"], "Q": 0.0, "H": 0.0, "S": 0.0, "Wup": EN1990.GAMMA["Q"]},
                "fonte": "EN 1990 eq. 6.10, γG,inf = 1,0, γQ = 1,5 no vento de sucção na cobertura"})
    return out


def _uls(cs):
    return [c for c in cs if c["id"].startswith("ELU")]


def _comb(f: dict, ef: dict) -> float:
    return sum(f.get(k, 0.0) * v for k, v in ef.items())


# =========================================================================================== asna Fink
def _trelica(nos, barras, apoios, cargas):
    """Treliça plana de nós articulados (rigidez axial EA = 1). nos: [(x, z)] m ; cargas {nó: (Fx, Fz)} kN → esforços (tração +)."""
    n = len(nos)
    K = np.zeros((2 * n, 2 * n))
    for i, j in barras:
        (x1, z1), (x2, z2) = nos[i], nos[j]
        L = math.hypot(x2 - x1, z2 - z1)
        c, s = (x2 - x1) / L, (z2 - z1) / L
        k = np.array([[c * c, c * s], [c * s, s * s]]) / L
        for a, b, sg in ((i, i, 1), (j, j, 1), (i, j, -1), (j, i, -1)):
            K[2 * a:2 * a + 2, 2 * b:2 * b + 2] += sg * k
    F = np.zeros(2 * n)
    for no, (fx, fz) in cargas.items():
        F[2 * no] += fx
        F[2 * no + 1] += fz
    fixos = sorted(apoios)
    livres = [d for d in range(2 * n) if d not in fixos]
    U = np.zeros(2 * n)
    U[livres] = np.linalg.solve(K[np.ix_(livres, livres)], F[livres])
    R = K @ U - F
    N = []
    for i, j in barras:
        (x1, z1), (x2, z2) = nos[i], nos[j]
        L = math.hypot(x2 - x1, z2 - z1)
        c, s = (x2 - x1) / L, (z2 - z1) / L
        N.append(((U[2 * j] - U[2 * i]) * c + (U[2 * j + 1] - U[2 * i + 1]) * s) / L)
    return N, {d: R[d] for d in fixos}


def _fink(S, alfa_deg, beiral, cargas_m):
    """Asna Fink (nós a S/4, S/2, 3S/4 no banzo superior; S/3, 2S/3 no inferior). cargas_m: {'sup': (qx, qz) por m de banzo,
    'inf': qz por m} — devolve esforços por barra e reações verticais (kN)."""
    t = math.tan(math.radians(alfa_deg))
    h = S / 2 * t
    nos = [(0, 0), (S / 4, h / 2), (S / 2, h), (3 * S / 4, h / 2), (S, 0), (S / 3, 0), (2 * S / 3, 0)]
    barras = {"BS1": (0, 1), "BS2": (1, 2), "BS3": (2, 3), "BS4": (3, 4), "BI1": (0, 5), "BI2": (5, 6), "BI3": (6, 4),
              "D1": (5, 1), "D2": (5, 2), "D3": (6, 2), "D4": (6, 3)}
    Ls = (S / 4) / math.cos(math.radians(alfa_deg))
    qx, qz = cargas_m.get("sup", (0.0, 0.0))
    qi = cargas_m.get("inf", 0.0)
    car = {k: [0.0, 0.0] for k in range(7)}
    for no, trib in ((0, Ls / 2), (1, Ls), (2, Ls), (3, Ls), (4, Ls / 2)):
        car[no][0] += qx * trib
        car[no][1] += qz * trib
    for no, trib in ((0, S / 6), (5, S / 3), (6, S / 3), (4, S / 6)):
        car[no][1] += qi * trib
    lb = beiral / math.cos(math.radians(alfa_deg))
    for no in (0, 4):                                           # beirais: carga ao apoio (momento local desprezado)
        car[no][1] += qz * lb
    N, R = _trelica(nos, list(barras.values()), {0, 1, 9}, {k: tuple(v) for k, v in car.items()})
    comp = {nome: math.hypot(nos[j][0] - nos[i][0], nos[j][1] - nos[i][1]) for nome, (i, j) in barras.items()}
    return {nome: N[i] for i, nome in enumerate(barras)}, {"A": R[1], "B": R[9]}, comp


# =========================================================================================== utilidades geométricas
def _linha_parede(w):
    A = np.array(w["A"][:2], float)
    d = np.array(w["d"][:2], float)
    d = d / (np.linalg.norm(d) or 1)
    return A, d


def _sobre_linha(w, p0, p1, tol=250.0):
    """Comprimento de sobreposição (mm) entre o eixo da parede e o segmento p0–p1, se paralelos e a ≤ tol."""
    A, d = _linha_parede(w)
    n = np.array([-d[1], d[0]])
    off = (w.get("Dt") or 0) / 2
    p0, p1 = np.array(p0, float), np.array(p1, float)
    s = p1 - p0
    Ls = np.linalg.norm(s)
    if Ls < 1:
        return 0.0
    if abs(abs(float(np.dot(s / Ls, d))) - 1) > 0.02:
        return 0.0
    dist = min(abs(float(np.dot(p0 - A, n)) - k) for k in (off, -off, 0.0))
    if dist > tol:
        return 0.0
    t0, t1 = sorted((float(np.dot(p0 - A, d)), float(np.dot(p1 - A, d))))
    return max(0.0, min(t1, w["L"]) - max(t0, 0.0))


def _mesma_linha(a, b, tol=250.0):
    A, d = _linha_parede(b)
    return _sobre_linha(a, A, A + d * b["L"], tol)


# =========================================================================================== verificação
def _ck(lista, grupo, elemento, ref, membros, perfil, ratio, combinacao, esforcos, resist, formula, notas=None, sub=None):
    st = util_status(ratio)
    lista.append({"id": f"{grupo}:{elemento}" + (f":{sub}" if sub else ""), "grupo": grupo, "elemento": elemento, "ref": ref,
                  "membros": membros, "perfil": perfil, "ratio": st["ratio"], "status": st["status"], "label": st["label"],
                  "combinacao": combinacao, "esforcos": esforcos, "resistencias": resist, "formula": formula, "notas": notas or []})


def _col(N_kn, M_knm, P, lcr_y, lcr_z, par):
    """Montante / barra comprimida: EC3 §6.3 com as propriedades EFETIVAS (1-3 §6.2: Aeff, Weff, curva b)."""
    r = EC3.verify_column(max(N_kn, 0.0), max(M_knm, 0.0), A_cm2=P["Aeff"] / 100, iy_cm4=P["Iy"] / 1e4, iz_cm4=P["Iz"] / 1e4,
                          it_cm4=0.0, iw_cm6=0.0, wpl_y_cm3=P["Weff_y"] / 1000, wel_y_cm3=P["Weff_y"] / 1000,
                          b_fl_mm=P["b"], h_mm=P["h"], tf_mm=P["t"], fy_mpa=P["fy"], lcr_y_m=lcr_y, lcr_z_m=lcr_z,
                          section_class=4, gamma_m0=par["gamma_m0"], gamma_m1=par["gamma_m1"], curve_y="b", curve_z="b",
                          cmy=0.95, cm_lt=0.95, lateral_restraint=True, mono=True)
    ratio = r["buckling"]["utilisation"]["ratio"] or 0.0
    if "interaction" in r:
        ratio = max(ratio, r["interaction"]["value"])
    if N_kn <= 0 and M_knm > 0:
        ratio = M_knm * 1e6 / (P["Weff_y"] * P["fy"] / par["gamma_m0"])
    return ratio, r


def _tracao(N_kn, M_knm, P, par):
    """Tração + flexão (1-3 §6.1.2 e §6.1.8 simplificado): N/(A·fy) + M/(Weff·fy) ≤ 1."""
    return (max(N_kn, 0) * 1e3 / (P["A"] * P["fy"] / par["gamma_m0"]) +
            abs(M_knm) * 1e6 / (P["Weff_y"] * P["fy"] / par["gamma_m0"]))


def _json(v):
    """numpy → tipos Python (resultado gravado em MongoDB e devolvido pela API)."""
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json(x) for x in v]
    if isinstance(v, np.generic):
        return v.item()
    return v


def verificar(projeto: dict, resultado: dict) -> dict:
    """Verificação de todos os elementos portantes do estudo LSF (resultado = engines.lsf.engine.calcular(projeto))."""
    par = {**PARAMETROS, **{k: v for k, v in (projeto.get("verificacao") or {}).items() if k in PARAMETROS and v is not None}}
    if (projeto.get("verificacao") or {}).get("ancoragem_resistencia_kn") is None:
        par["ancoragem_resistencia_kn"] = None
    if (projeto.get("verificacao") or {}).get("contraventamento_vrd_kn_m") is None:
        par["contraventamento_vrd_kn_m"] = None
    fy = _fy(projeto)
    perfis = projeto.get("perfis") or {}
    secs: dict[str, dict] = {}

    def S(nome):
        if nome not in secs:
            secs[nome] = seccao(perfis[nome], fy)
        return secs[nome]

    avisos: list[str] = []
    checks: list[dict] = []
    paredes = resultado.get("paredes") or []
    por_ref: dict[str, list] = {}
    for m in resultado.get("membros") or []:
        por_ref.setdefault(m["ref"], []).append(m)
    tipos = projeto.get("tiposParede") or {}
    topo_max = max((w["z0"] + w["H"] for w in paredes), default=0.0)
    cob_in = projeto.get("coberturas") or []
    cob_out = {c["id"]: c for c in resultado.get("coberturas") or []}
    alfa = float(cob_in[0].get("inclinacao") or 0) if cob_in else 0.0
    h_cob = max((cob_out.get(c["id"], {}).get("S", 0) / 2 * math.tan(math.radians(float(c.get("inclinacao") or 0)))
                 for c in cob_in), default=0.0)
    H_total = (topo_max + h_cob) / 1000
    ac = acoes(projeto, par, H_total, alfa if cob_in else None)
    cs = combinacoes()
    uls, sls = _uls(cs), [c for c in cs if c["id"].startswith("ELScar")]

    # cargas por linha (kN/m) no topo de cada parede, por ação: {parede_id: {acao: kN/m}}
    linha: dict[str, dict] = {w["id"]: {} for w in paredes}

    def soma(wid, ef):
        for k, v in ef.items():
            linha[wid][k] = linha[wid].get(k, 0.0) + v

    # ---------------------------------------------------------------------------------------- cobertura (asnas Fink)
    for c in cob_in:
        co = cob_out.get(c["id"])
        if not co or not co.get("S"):
            continue
        Sm, sp = co["S"] / 1000, float(c.get("espacamento") or 600) / 1000
        a = float(c.get("inclinacao") or 30)
        ca = math.cos(math.radians(a))
        bei = float(c.get("beiral") or 0) / 1000
        banzo, diag = S(c["banzo"]), S(c["diagonal"])
        pp_b, pp_d = banzo["kg_m"] * 9.81e-3, diag["kg_m"] * 9.81e-3
        # cargas por metro de banzo superior (componentes globais x, z; z para cima) e por metro de banzo inferior
        ef_sup = {"G": (0.0, -(par["g_cobertura_kn_m2"] * sp + pp_b)), "H": (0.0, -ac["q_cobertura"] * sp * ca),
                  "S": (0.0, -ac["s"] * sp * ca), "W": (None, ac["w_cob_baixo"] * sp), "Wup": (None, ac["w_cob_cima"] * sp)}
        _, _, comp = _fink(Sm, a, 0.0, {})
        L_diag = sum(v for k, v in comp.items() if k.startswith("D"))
        ef_inf = {"G": -(par["g_teto_kn_m2"] * sp + pp_b + pp_d * L_diag / Sm)}
        esf: dict[str, dict] = {}
        reac: dict[str, float] = {}
        for k, (qx, qz) in ef_sup.items():
            if qx is None:                                     # vento normal à vertente (+ = para baixo): componente vertical
                qx, qz = 0.0, -qz * ca                         # (componentes horizontais das duas vertentes compensam-se)
            N, R, comp = _fink(Sm, a, bei, {"sup": (qx, qz), "inf": ef_inf.get(k, 0.0)})
            esf[k], reac[k] = N, max(R["A"], R["B"])
        ef_q = {k: v[1] for k, v in ef_sup.items()}            # p/ flexão local do banzo superior
        q_perp = {"G": -ef_q["G"] * ca, "H": -ef_q["H"] * ca, "S": -ef_q["S"] * ca, "W": ef_sup["W"][1], "Wup": ef_sup["Wup"][1]}
        for barra, grupo_b, P, nome_perfil in (("BS", "Banzo superior", banzo, c["banzo"]),
                                               ("BI", "Banzo inferior", banzo, c["banzo"]), ("D", "Diagonal", diag, c["diagonal"])):
            pior = (0.0, None, {}, {})
            nomes = [b for b in esf["G"] if b.startswith(barra)]
            for cb in uls:
                for nb in nomes:
                    Nt = _comb(cb["factors"], {k: esf[k][nb] for k in esf})          # tração +
                    Lr = comp[nb]
                    if barra == "D":
                        M = 0.0
                    else:
                        qq = _comb(cb["factors"], q_perp) if barra == "BS" else -_comb(cb["factors"], ef_inf)
                        M = abs(qq) * Lr ** 2 / 8
                    if Nt >= 0:
                        r, det = _tracao(Nt, M, P, par), {}
                    else:
                        r, det = _col(-Nt, M, P, Lr, Lr, par)
                    if r > pior[0]:
                        pior = (r, cb, {"N_kN": round(Nt, 2), "M_kNm": round(M, 3), "barra": nb, "L_m": round(Lr, 3)},
                                {"Nb_Rd_kN": det.get("nb_rd_kn"), "Aeff_mm2": round(P["Aeff"]), "Weff_mm3": round(P["Weff_y"])})
            _ck(checks, "Asnas", f"{c['id']} — {grupo_b}", c["id"], [m["id"] for m in por_ref.get(c["id"], []) if m["tipoPeca"] == grupo_b],
                nome_perfil, pior[0], pior[1]["id"] if pior[1] else None, pior[2], pior[3],
                "Treliça Fink de nós articulados; compressão: EC3 §6.3 com Aeff/Weff (1-3 §6.2.2, curva b); tração: N/(A·fy)+M/(Weff·fy)",
                ["Flexão local do banzo entre nós: q·L²/8 (apoios simples, a favor da segurança).",
                 "Encurvadura fora do plano travada pelo OSB / ripado (comprimento = painel entre nós)."])
        # reações → paredes de apoio (linhas y = y0 e y = y1 se cumeeira em x)
        x0, y0, x1, y1 = (float(c.get(k, 0)) for k in ("x0", "y0", "x1", "y1"))
        linhas_apoio = ([((x0, y0), (x1, y0)), ((x0, y1), (x1, y1))] if c.get("cumeeira", "x") == "x"
                        else [((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))])
        apoiada = False
        for w in paredes:
            if abs(w["z0"] + w["H"] - topo_max) > 60:
                continue
            for p0, p1 in linhas_apoio:
                if _sobre_linha(w, p0, p1) > 0:
                    soma(w["id"], {k: v / sp for k, v in reac.items()})
                    apoiada = True
        if not apoiada:
            avisos.append(f"{c['id']}: nenhuma parede de apoio encontrada sob as asnas — reações não transmitidas.")

    # ---------------------------------------------------------------------------------------- pisos (vigas)
    for f in resultado.get("pisos") or []:
        vigas = [m for m in por_ref.get(f["id"], []) if m["tipoPeca"] == "Viga de piso"]
        if not vigas:
            continue
        P = S(f["viga"])
        sp = float(f.get("espacamento") or 600) / 1000
        L = max(m["L"] for m in vigas) / 1000
        pp = P["kg_m"] * 9.81e-3
        w = {"G": par["g_piso_kn_m2"] * sp + pp, "Q": ac["q_piso"] * sp}
        pior_m = pior_v = (0.0, None)
        for cb in uls:
            q = _comb(cb["factors"], w)
            rm = q * L * L / 8 * 1e6 / (P["Weff_y"] * P["fy"] / par["gamma_m0"])
            rv = q * L / 2 * 1e3 / (P["Vb_N"] / par["gamma_m0"])
            if rm > pior_m[0]:
                pior_m = (rm, cb)
            if rv > pior_v[0]:
                pior_v = (rv, cb)
        ids = [m["id"] for m in vigas]
        qm = _comb(pior_m[1]["factors"], w)
        _ck(checks, "Vigas de piso", f"{f['id']} — flexão", f["id"], ids, f["viga"], pior_m[0], pior_m[1]["id"],
            {"q_kN_m": round(qm, 3), "L_m": round(L, 3), "M_Ed_kNm": round(qm * L * L / 8, 3)},
            {"Weff_mm3": round(P["Weff_y"]), "M_c_Rd_kNm": round(P["Weff_y"] * P["fy"] / par["gamma_m0"] / 1e6, 3)},
            "M_Ed = q·L²/8 ≤ M_c,Rd = Weff·fy/γM0 (1-3 §6.1.4; banzo comprimido travado pelo OSB do piso)")
        qv = _comb(pior_v[1]["factors"], w)
        _ck(checks, "Vigas de piso", f"{f['id']} — esforço transverso", f["id"], ids, f["viga"], pior_v[0], pior_v[1]["id"],
            {"V_Ed_kN": round(qv * L / 2, 3)}, {"V_b_Rd_kN": round(P["Vb_N"] / par["gamma_m0"] / 1e3, 3), "lambda_w": round(P["lambda_w"], 3)},
            "V_Ed ≤ V_b,Rd = hw·t·fbv/γM0 (1-3 §6.1.5, Quadro 6.1 sem reforço no apoio)",
            ["Esmagamento local da alma nos apoios (1-3 §6.1.7) não verificado: prever reforço de alma ou guia de bordadura."])
        EI = E * P["Iy"] * 1e-9                                   # kN·m²
        d_tot = max(5 * _comb(c["factors"], w) * L ** 4 / (384 * EI) for c in sls) * 1000
        d_q = 5 * w["Q"] * L ** 4 / (384 * EI) * 1000
        lim_t, lim_q = L * 1000 / par["flecha_piso_total"], L * 1000 / par["flecha_piso_q"]
        _ck(checks, "Vigas de piso", f"{f['id']} — flecha", f["id"], ids, f["viga"], max(d_tot / lim_t, d_q / lim_q), "ELS característica",
            {"flecha_total_mm": round(d_tot, 1), "flecha_Q_mm": round(d_q, 1)},
            {"limite_total_mm": round(lim_t, 1), "limite_Q_mm": round(lim_q, 1)},
            f"δ = 5qL⁴/(384EI) ≤ L/{par['flecha_piso_total']} (total) e ≤ L/{par['flecha_piso_q']} (sobrecarga)",
            ["Inércia bruta (1-3 §7.1: secção efetiva nas tensões de serviço — diferença pequena com tensões baixas)."])
        f_hz = math.pi / 2 * math.sqrt(EI * 1000 / ((w["G"] / sp) / 9.81 * sp * 1000 * L ** 4)) if w["G"] > 0 else None
        if f_hz and f_hz < 8:
            avisos.append(f"{f['id']}: frequência própria das vigas ≈ {f_hz:.1f} Hz < 8 Hz — verificar as vibrações do piso.")
        # reações → paredes de apoio do piso
        x0, y0, x1, y1 = (float(f[k]) for k in ("x0", "y0", "x1", "y1"))
        la = ([((x0, y0), (x1, y0)), ((x0, y1), (x1, y1))] if f.get("vao", "y") == "y"
              else [((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))])
        for p0, p1 in la:
            ok = False
            for wl in paredes:
                if abs(wl["z0"] + wl["H"] - float(f["z"])) > 60:
                    continue
                if _sobre_linha(wl, p0, p1) > 0:
                    soma(wl["id"], {k: v * L / 2 / sp for k, v in w.items()})
                    ok = True
            if not ok:
                avisos.append(f"{f['id']}: linha de apoio sem parede por baixo ({p0} → {p1}) — reação não transmitida.")

    # ---------------------------------------------------------------------------------------- paredes (de cima para baixo)
    ordem = sorted(paredes, key=lambda w: -w["z0"])
    for w in ordem:
        tp = tipos.get(w["tipo"]) or {}
        g_pp = (par["g_parede_ext_kn_m2"] if w["tipo"] == "EXT" else par["g_parede_int_kn_m2"]) * w["H"] / 1000
        kgm = sum(m["kg"] for m in por_ref.get(w["id"], [])) / max(w["L"] / 1000, 0.1) * 9.81e-3
        base = dict(linha[w["id"]])
        base["G"] = base.get("G", 0.0) + g_pp + kgm
        w["_base"] = base                                        # carga por metro na base da parede
        abaixo = False
        for wb in paredes:
            if wb is w or abs(wb["z0"] + wb["H"] - w["z0"]) > 400 or wb["z0"] >= w["z0"]:
                continue
            if _mesma_linha(w, wb) > 0:
                soma(wb["id"], base)
                abaixo = True
        if w["z0"] > 100 and not abaixo:
            avisos.append(f"{w['id']}: parede sem parede por baixo — a sua carga ({base['G']:.2f} kN/m perm.) assenta nas vigas de piso, "
                          "o que não é verificado aqui.")

    for w in paredes:
        tp = tipos.get(w["tipo"]) or {}
        if w["tipo"] != "EXT" and linha[w["id"]].get("G", 0.0) > 0.5:
            avisos.append(f"{w['id']}: parede «{tp.get('nome') or w['tipo']}» é PORTANTE (recebe {linha[w['id']].get('G', 0.0):.1f} kN/m "
                          f"permanentes de pisos/paredes) — confirmar o tipo de parede e o perfil dos montantes ({tp.get('montante')}).")
        if not tp.get("montante") or tp["montante"] not in perfis:
            continue
        P = S(tp["montante"])
        sp = float(tp.get("espacamento") or 600) / 1000
        Hm = w["H"] / 1000
        topo = linha[w["id"]]
        nbl = int(tp.get("bloqueadores") or 0)
        lz = Hm / (nbl + 1)
        ext = w["tipo"] == "EXT"
        ids_m = [m["id"] for m in por_ref.get(w["id"], []) if m["tipoPeca"] in ("Montante", "Montante de extremo", "Montante de canto",
                                                                                   "Montante de ligação")]
        pior = (0.0, None, {}, {})
        for cb in uls:
            if cb["id"] == "ELU_lev":
                continue
            N = _comb(cb["factors"], topo) * sp + _comb(cb["factors"], {"G": (w["_base"]["G"] - topo.get("G", 0.0)) / 2}) * sp
            M = cb["factors"].get("W", 0.0) * ac["w_parede"] * sp * Hm * Hm / 8 if ext else 0.0
            r, det = _col(N, M, P, Hm, lz, par)
            if r > pior[0]:
                pior = (r, cb, {"N_Ed_kN": round(N, 2), "M_Ed_kNm": round(M, 3)},
                        {"Nb_Rd_kN": det.get("nb_rd_kn"), "chi_y": det.get("chi_y"), "chi_z": det.get("chi_z"),
                         "interacao": (det.get("interaction") or {}).get("value")})
        _ck(checks, "Montantes", f"{w['id']} — montante corrente", w["id"], ids_m, tp["montante"], pior[0],
            pior[1]["id"] if pior[1] else None, pior[2], pior[3],
            "N+M: EC3 §6.3.3 método 2 com Aeff/Weff (1-3 §6.2.4/§6.2.5), Lcr,y = H, Lcr,z = H/(bloqueadores+1), curva b",
            ["Encurvadura por flexão-torção e distorcional global travadas pelas placas parafusadas nas duas faces (hipótese)."] +
            (["Vento: q_p·(cpe − cpi) na zona A (cantos), a favor da segurança."] if ext else []))

        # vãos: vergas (caixão de 2 C) + montantes de apoio
        vg = tp.get("verga")
        for ab in w.get("aberturas") or []:
            if not vg or vg not in perfis:
                break
            Pv = S(vg)
            Lv = (ab["x1"] - ab["x0"]) / 1000 + 2 * P["b"] / 1000
            ids_v = [m["id"] for m in por_ref.get(w["id"], []) if m["tipoPeca"] == "Verga"
                     and m["elev"]["x0"] < ab["x1"] and m["elev"]["x1"] > ab["x0"]]
            nv = max(len(ids_v), 1)
            pm = pv = (0.0, None)
            for cb in uls:
                if cb["id"] == "ELU_lev":
                    continue
                q = _comb(cb["factors"], topo)
                rm = q * Lv * Lv / 8 * 1e6 / (nv * Pv["Weff_y"] * Pv["fy"] / par["gamma_m0"])
                rv = q * Lv / 2 * 1e3 / (nv * Pv["Vb_N"] / par["gamma_m0"])
                pm = max(pm, (rm, cb), key=lambda x: x[0])
                pv = max(pv, (rv, cb), key=lambda x: x[0])
            qd = _comb(pm[1]["factors"], topo) if pm[1] else 0.0
            EI = nv * E * Pv["Iy"] * 1e-9
            dl = max((5 * _comb(c["factors"], topo) * Lv ** 4 / (384 * EI) for c in sls), default=0.0) * 1000
            rr = max(pm[0], pv[0], dl / (Lv * 1000 / par["flecha_verga"]))
            if not pm[1]:
                pm = (0.0, {"id": "sem carga"})
            _ck(checks, "Vergas", f"{w['id']} — verga {ab['id']}", w["id"], ids_v, f"{nv}×{vg}", rr, pm[1]["id"] if pm[1] else None,
                {"q_kN_m": round(qd, 3), "L_m": round(Lv, 3), "M_Ed_kNm": round(qd * Lv * Lv / 8, 3), "V_Ed_kN": round(qd * Lv / 2, 3),
                 "flecha_mm": round(dl, 1)},
                {"M_c_Rd_kNm": round(nv * Pv["Weff_y"] * Pv["fy"] / par["gamma_m0"] / 1e6, 3),
                 "V_b_Rd_kN": round(nv * Pv["Vb_N"] / par["gamma_m0"] / 1e3, 3), "limite_flecha_mm": round(Lv * 1000 / par["flecha_verga"], 1)},
                f"Viga simplesmente apoiada sob a carga da linha (sem efeito de arco): flexão, esforço transverso e flecha L/{par['flecha_verga']}")
            # montante de apoio (reação da verga) e montante rei (vento sobre metade do vão)
            ids_a = [m["id"] for m in por_ref.get(w["id"], []) if m["tipoPeca"] == "Montante de apoio"
                     and (abs(m["elev"]["x1"] - ab["x0"]) < 200 or abs(m["elev"]["x0"] - ab["x1"]) < 200)]
            La = max(ab["z1"] / 1000, 0.3)
            pa = pr = (0.0, None, {})
            for cb in uls:
                if cb["id"] == "ELU_lev":
                    continue
                Na = _comb(cb["factors"], topo) * Lv / 2
                ra, _ = _col(Na, 0.0, P, La, La, par)
                pa = max(pa, (ra, cb, {"N_Ed_kN": round(Na, 2)}), key=lambda x: x[0])
                trib = (ab["x1"] - ab["x0"]) / 2000 + sp / 2
                Nr = _comb(cb["factors"], topo) * sp / 2
                Mr = cb["factors"].get("W", 0.0) * ac["w_parede"] * trib * Hm * Hm / 8 if ext else 0.0
                rk, _ = _col(Nr, Mr, P, Hm, lz, par)
                pr = max(pr, (rk, cb, {"N_Ed_kN": round(Nr, 2), "M_Ed_kNm": round(Mr, 3)}), key=lambda x: x[0])
            _ck(checks, "Montantes", f"{w['id']} — montante de apoio {ab['id']}", w["id"], ids_a, tp["montante"], pa[0],
                pa[1]["id"] if pa[1] else "sem carga", pa[2], {}, "Reação da verga q·L/2 num só perfil; EC3 §6.3.1 com Aeff, Lcr = altura do vão",
                ["Em caixão (2 perfis) a resistência real é maior — verificação a favor da segurança."])
            ids_r = [m["id"] for m in por_ref.get(w["id"], []) if m["tipoPeca"] == "Montante rei"
                     and (abs(m["elev"]["x1"] - ab["x0"]) < 300 or abs(m["elev"]["x0"] - ab["x1"]) < 300)]
            if ext:
                _ck(checks, "Montantes", f"{w['id']} — montante rei {ab['id']}", w["id"], ids_r, tp["montante"], pr[0],
                    pr[1]["id"] if pr[1] else None, pr[2], {}, "Vento sobre metade do vão + meio espaçamento; N+M §6.3.3 com Aeff/Weff")

    # ---------------------------------------------------------------------------------------- ancoragens (levantamento)
    lev = next(c for c in cs if c["id"] == "ELU_lev")
    for w in paredes:
        tp = tipos.get(w["tipo"]) or {}
        anc = tp.get("ancoragem") or {}
        base = w.get("_base") or {}
        net = _comb(lev["factors"], base)                        # kN/m, + = compressão, − = levantamento
        if net >= 0 or (w["z0"] > 100 and any(_mesma_linha(w, wb) > 0 for wb in paredes if wb["z0"] < w["z0"])):
            continue
        passo = float(anc.get("passoMax") or 600) / 1000
        Fa = -net * passo
        Rd = par["ancoragem_resistencia_kn"]
        _ck(checks, "Ancoragens", f"{w['id']} — levantamento", w["id"], [], anc.get("nome") or "ancoragem",
            (Fa / Rd) if Rd else None, "ELU_lev", {"levantamento_kN_m": round(-net, 3), "F_ancoragem_kN": round(Fa, 2), "passo_m": passo},
            {"F_Rd_kN": Rd}, "1,0·G + 1,5·W (sucção na cobertura) na base da parede; força por ancoragem = levantamento × passo",
            [] if Rd else ["Indique a resistência de cálculo da ancoragem (fabricante) em verificacao.ancoragem_resistencia_kn."])

    # ---------------------------------------------------------------------------------------- contraventamento (vento global)
    niveis = sorted({round(w["z0"]) for w in paredes})
    xs = [p for w in paredes for p in (w["A"][0], w["A"][0] + w["d"][0] * w["L"])]
    ys = [p for w in paredes for p in (w["A"][1], w["A"][1] + w["d"][1] * w["L"])]
    Lx, Ly = (max(xs) - min(xs)) / 1000 if xs else 0, (max(ys) - min(ys)) / 1000 if ys else 0
    cume = (cob_in[0].get("cumeeira", "x") if cob_in else "x")
    for z in niveis:
        acima = (topo_max - z) / 1000
        for dirn, larg, eixo in (("y", Lx, 1), ("x", Ly, 0)):      # vento segundo y: fachada de comprimento Lx, paredes paralelas a y
            area = larg * acima
            if cob_in:
                area += (larg * h_cob / 1000) if ((dirn == "y") == (cume == "x")) else (larg * h_cob / 1000 / 2)
            V = 1.5 * ac["w_global"] * area
            Lc = 0.0
            for w in paredes:
                if round(w["z0"]) != z or w["tipo"] != "EXT":
                    continue
                if (tipos.get(w["tipo"]) or {}).get("contraventamento", "OSB") in ("nenhum", None):
                    continue
                if abs(w["d"][eixo]) > 0.9:                       # parede paralela ao vento
                    Lc += (w["L"] - sum(a["x1"] - a["x0"] for a in w.get("aberturas") or [])) / 1000
            v = V / Lc if Lc > 0 else None
            Rd = par["contraventamento_vrd_kn_m"]
            _ck(checks, "Contraventamento", f"Piso z={z / 1000:.2f} m — vento segundo {dirn}", f"z{z}", [], "paredes OSB",
                (v / Rd) if (Rd and v) else None, "ELU vento dominante",
                {"V_Ed_kN": round(V, 2), "comprimento_contraventado_m": round(Lc, 2), "v_Ed_kN_m": round(v, 2) if v else None},
                {"v_Rd_kN_m": Rd},
                "V = 1,5·q_p·cf·área exposta acima do nível; v = V / comprimento de paredes contraventadas sem vãos",
                [] if Rd else ["Indique a resistência ao corte da parede contraventada (ensaio / fabricante) em "
                               "verificacao.contraventamento_vrd_kn_m; prever hold-downs nos extremos dos painéis."])

    for k in list(secs):
        for a in secs[k]["avisos"]:
            avisos.append(f"{k}: {a}")
    avisos.append("Ação sísmica (NP EN 1998-1) não verificada — obrigatória em Portugal, a efetuar pelo projetista.")
    avisos.append("Ligações aparafusadas (NP EN 1993-1-3 §8) e esmagamento da alma nos apoios (§6.1.7) não verificados.")

    validos = [c for c in checks if c["ratio"] is not None]
    ratio_membro: dict[str, float] = {}
    for c in validos:
        for mid in c["membros"]:
            ratio_membro[mid] = max(ratio_membro.get(mid, 0.0), c["ratio"])
    gov = max(validos, key=lambda c: c["ratio"], default=None)
    cont = {s: sum(1 for c in checks if c["status"] == s) for s in ("ok", "proche", "a_revoir", "non_calcule")}
    return _json({
        "versao": VERSAO, "execution_ready": False, "disclaimer": DISCLAIMER,
        "normas": ["NP EN 1990", "NP EN 1991-1-1", "NP EN 1991-1-3", "NP EN 1991-1-4", "NP EN 1993-1-1", "NP EN 1993-1-3",
                   "NP EN 1993-1-5"],
        "motores": ["structuro_eurocode (combinações)", "acoes_pt (neve, vento, sobrecargas PT)",
                    "structuro_ec3.verify_column (encurvadura, N+M)", "structuro_check (estado)"],
        "parametros": {k: {"valor": par[k], "fonte": FONTES.get(k, "")} for k in PARAMETROS},
        "aco": {"grau": (projeto.get("aco") or {}).get("grau"), "fy_MPa": fy},
        "acoes": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in ac.items()},
        "combinacoes": cs,
        "seccoes": {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items() if kk != "avisos"} for k, v in secs.items()},
        "verificacoes": checks,
        "resumo": {"n": len(checks), "ok": cont["ok"], "proximo": cont["proche"], "a_rever": cont["a_revoir"],
                   "nao_calculado": cont["non_calcule"], "ratio_max": gov["ratio"] if gov else None,
                   "governante": gov["id"] if gov else None},
        "ratio_membro": ratio_membro,
        "avisos": avisos,
    })
