"""Gros-œuvre (Portugal): verificação estrutural encadeada + caderno de planos de execução COTADOS, das sapatas à cobertura.

Entrada: a estrutura descrita por eixos (grelhas), sapatas isoladas e contínuas, muros, pilares, vigas, lajes / painéis e níveis absolutos
(tudo em metros, cotas em m). Saída determinística, sem IA:
  1. verificação de cada elemento pelos motores ConstruPilot (NP EN 1992 / 1995 / 1997 via structure.calculer; pilar de madeira por
     encurvadura EC5 §6.3.2 aqui), com AJUSTE automático da secção quando um elemento não verifica (o original fica registado);
  2. planos vetoriais a 1:50 (ou 1:100 se o edifício não couber) — GO-01 fundações, GO-02 pavimento, GO-03 cobertura, GO-04 cortes,
     GO-05 quadros — com cadeias de cotas em mm, eixos, níveis e quadro de sapatas com armaduras A500;
  3. nota de cálculo PDF (rendu) seguida das folhas de planos num único PDF.
As secções desenhadas são as secções verificadas (ajustadas). Pré-dimensionamento a validar pelo projetista de estruturas.
"""
from __future__ import annotations

import contextvars
import math
import os

from . import notes, structure

S50 = 72 / 25.4 * 1000 / 50          # pt por metro a 1:50
FOLHAS = {"A0": (3370.39, 2383.94), "A1": (2383.94, 1683.78)}
VERDE, COBRE, CREME, CINZA, BRANCO = (0.09, 0.29, 0.22), (0.72, 0.42, 0.20), (0.98, 0.95, 0.89), (0.38, 0.38, 0.38), (1, 1, 1)
BET, MAD, MAD_E, ISO = (0.80, 0.80, 0.80), (0.93, 0.82, 0.60), (0.80, 0.60, 0.32), (0.75, 0.88, 0.95)
CASTANHO = (0.45, 0.30, 0.10)
FC0K = {"C18": 18.0, "C24": 21.0, "C30": 23.0, "GL24h": 24.0, "GL28h": 28.0}
MADEIRAS = ("C18", "C24", "C30", "GL24h", "GL28h")
LARG_GL = (0.115, 0.14, 0.16, 0.175, 0.20, 0.215, 0.24, 0.265, 0.28, 0.315)


# ================================================================================================================ fontes
def _fontes():
    assets = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "fonts")
    for d in (assets, "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"):
        a, b = os.path.join(d, "DejaVuSans.ttf"), os.path.join(d, "DejaVuSans-Bold.ttf")
        if os.path.exists(a) and os.path.exists(b):
            return a, b
    import reportlab
    d = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    return os.path.join(d, "Vera.ttf"), os.path.join(d, "VeraBd.ttf")


_TR_CV = contextvars.ContextVar("go_lingua", default=None)


def _tr(s: str) -> str:
    """Tradução das peças desenhadas (lingua ≠ pt): substituições por ordem decrescente de comprimento."""
    d = _TR_CV.get()
    if not d or not s:
        return s
    for k in d["_ordem"]:
        if k in s:
            s = s.replace(k, d[k])
    return s


def _dic(lingua):
    if not lingua or lingua == "pt":
        return None
    from .lingua_planos import TRADUCOES
    d = dict(TRADUCOES[lingua])
    d["_ordem"] = sorted(TRADUCOES[lingua], key=len, reverse=True)
    return d


def _c(x, n=2):
    return f"{x:.{n}f}".replace(".", ",")


def _mm(x):
    return f"{round(x * 1000):d}"


# ================================================================================================================ verificação
def _taxa(ctl):
    t = [c["taux"] for c in ctl if c.get("taux") is not None]
    return max(t) if t else None


def _ok(ctl):
    return all(c.get("ok") is not False for c in ctl)


def _pilar_madeira(b, h, L, N_ed, classe, sc=1):
    """Pilar de madeira em compressão axial com encurvadura (NP EN 1995-1-1 §6.3.2), kmod médio, γM 1,25 / 1,3."""
    from engines.structuro_ec5 import CLASSES, GAMMA_M, KMOD
    m = CLASSES[classe]
    kmod = KMOD["3" if sc == 3 else "1-2"]["medium"]
    gm = GAMMA_M[m["kind"]]
    A, i = b * h, min(b, h) / math.sqrt(12)
    lam = L / i
    lam_rel = lam / math.pi * math.sqrt(FC0K[classe] / m["E0_05"])
    beta_c = 0.1 if m["kind"] == "glulam" else 0.2
    k = 0.5 * (1 + beta_c * (lam_rel - 0.3) + lam_rel ** 2)
    kc = min(1.0, 1 / (k + math.sqrt(max(k * k - lam_rel ** 2, 1e-12))))
    sig, fcd = N_ed / A / 1000, kmod * FC0K[classe] / gm
    tx = sig / (kc * fcd)
    ctl = [{"ref": "NP EN 1995-1-1 §6.3.2 encurvadura", "exigence": "σc,0,d ≤ kc·fc,0,d", "valeur": f"{_c(sig)} / {_c(kc * fcd)} MPa (λ {lam:.0f}, kc {_c(kc)})",
            "ok": tx <= 1 + 1e-9, "taux": tx, "lib": "Encurvadura"}]
    return {"element": f"Pilar de madeira {classe}", "section": f"{b * 1000:.0f} × {h * 1000:.0f} mm, L {_c(L)} m", "controles": ctl,
            "sollicitations": {"ned": N_ed}, "quantites": {"bois_m3": A * L}, "lam": lam, "kc": kc}


# ---- painéis CLT: rigidez EI / GA pela analogia de corte (camadas cruzadas, corte de rolamento) e verificação pelo motor
#      bet_clt_ua.engine.panel (flexão, corte, flecha instantânea + fluência com a deformação por corte incluída)
CLT_PROP = {"E0": 11000.0, "G0": 690.0, "GR": 50.0, "fm_k": 24.0, "fv_k": 4.0, "fr_k": 1.1, "rho": 4.7}   # C24 típico (EN 338 / EN 16351)


def clt_rigidez(camadas_mm, kmod=0.8, gm=1.25, produto=None, especie=None, n_tabuas=None):
    """Faixa de 1 m; camadas ímpares (1.ª, 3.ª…) na direção do vão. → EI (kN·m²), GA (kN), M_Rd (kN·m), V_Rd (kN).
    produto = chave de clt_produtos (ETA): E0, G_R, f_m,k × k_sys, f_R,k pela espessura da camada cruzada e espécie."""
    from . import clt_produtos as CP
    pr = CP.produto(produto) if produto else None
    t = [c / 1000 for c in camadas_mm]
    if len(t) < 3 or len(t) % 2 == 0:
        raise ValueError("CLT: número ímpar de camadas (≥ 3)")
    z, zc = 0.0, []
    for ti in t:
        zc.append(z + ti / 2)
        z += ti
    H = z
    lon = [i for i in range(len(t)) if i % 2 == 0]
    zs = sum(t[i] * zc[i] for i in lon) / sum(t[i] for i in lon)
    I = sum(t[i] ** 3 / 12 + t[i] * (zc[i] - zs) ** 2 for i in lon)            # m⁴ por m (só camadas longitudinais)
    if pr:
        E, G0, GR = pr["E0_mean"] * 1e3, pr["G0_mean"] * 1e3, pr["G_R"] * 1e3
        n_t = int(n_tabuas or math.floor(1000 / pr["tabua_b_mm"][1]))          # tábuas da camada exterior na faixa de 1 m (b máx → conservador)
        ksys = CP.k_sys(n_t)
        fm, fv = pr["fm_k"] * ksys, pr["fv_k"]
        frk = min(CP.fr_k(pr, camadas_mm[i], especie) for i in range(1, len(camadas_mm), 2))
    else:
        E, G0, GR = CLT_PROP["E0"] * 1e3, CLT_PROP["G0"] * 1e3, CLT_PROP["GR"] * 1e3
        ksys, fm, fv, frk = 1.0, CLT_PROP["fm_k"], CLT_PROP["fv_k"], CLT_PROP["fr_k"]
    a = zc[-1] - zc[0]
    den = t[0] / (2 * G0) + t[-1] / (2 * G0) + sum(t[i] / (GR if i % 2 else G0) for i in range(1, len(t) - 1))
    GA = a * a / den
    zmax = max(zs, H - zs)
    M_Rd = kmod * fm * 1e3 / gm * I / zmax
    S_R = t[0] * abs(zc[0] - zs)                                                 # momento estático na 1.ª camada transversal
    S_max = 0.0                                                                  # momento estático máximo (no eixo neutro)
    for i in lon:
        top, bot = zc[i] - t[i] / 2, min(zc[i] + t[i] / 2, zs)
        if bot > top:
            S_max += (bot - top) * (zs - (top + bot) / 2)
    S_max = max(S_max, S_R)
    V_R = kmod * frk * 1e3 / gm * I / S_R
    V_v = kmod * fv * 1e3 / gm * I / S_max
    return {"EI": E * I, "GA": GA, "M_Rd": M_Rd, "V_Rd": min(V_R, V_v), "H": H, "I": I, "k_sys": ksys, "f_R_k": frk, "E0": E / 1e3,
            "produto": pr}


def _clt_candidatos(h_min_mm):
    """Composições correntes (tábuas 20-43 mm, âmbito das ETA de CLT), da mais fina para a mais espessa, ≥ h_min."""
    c = [[t] * 5 for t in (28, 30, 32, 34, 36, 38, 40, 42)] + [[t] * 7 for t in (30, 32, 34, 36, 38, 40, 42)]
    return sorted((x for x in c if sum(x) >= h_min_mm - 1e-6), key=lambda x: (sum(x), len(x)))


def clt_painel(lj, vao, kmod=0.8):
    from engines.bet_clt_ua.engine import panel
    from engines.bet_clt_ua.schema import Panel
    from . import clt_produtos as CP
    cam = lj.get("camadas_mm") or [round(float(lj["espessura_m"]) * 1000 / 5, 1)] * 5
    rg = clt_rigidez(cam, kmod, produto=lj.get("produto"), especie=lj.get("especie"), n_tabuas=lj.get("n_tabuas"))
    pr = rg["produto"]
    cobertura = lj.get("piso") == "cobertura"
    psi2 = float(lj["psi2"]) if lj.get("psi2") is not None else (0.0 if cobertura else 0.3)
    basis = {"reference": (f"{pr['nome']} — {pr['eta']}" if pr else "ConstruPilot — CLT C24 valores típicos (EN 338 / EN 16351); substituir pela ETA do fabricante"),
             "revision": "1", "declared_by": pr["fabricante"] if pr else "ConstruPilot calc_lots.gros_oeuvre", "confirmed": False}
    pn = Panel.model_validate({"id": lj.get("ref") or "CLT", "product": pr["nome"] if pr else "CLT C24 (típico)", "layup_id": "-".join(f"{c:g}" for c in cam),
                               "bending_axis": "longitudinal", "application": "roof" if cobertura else "floor",
                               "support_model": "one_way_simply_supported_udl", "span_m": float(vao), "strip_width_m": 1.0,
                               "thickness_m": rg["H"], "density_kn_m3": CLT_PROP["rho"], "ei_eff_kn_m2": rg["EI"], "ga_eff_kn": rg["GA"],
                               "moment_resistance_knm": rg["M_Rd"], "shear_resistance_kn": rg["V_Rd"],
                               "permanent_superimposed_kpa": float(lj.get("g2_kn_m2") or 0.0), "variable_kpa": float(lj.get("q_kn_m2") or 0.0),
                               "gamma_g": 1.35, "gamma_q": 1.5, "creep_factor": 0.8, "quasi_permanent_factor": psi2,
                               "deflection_limit_mm": float(vao) * 1000 / float(lj.get("limite_flecha") or 300),
                               "product_basis": basis, "action_basis": basis})
    r = panel(pn)
    ra = r["ratios"]
    ctl = [{"ref": "NP EN 1995-1-1 §6.1.6 flexão (CLT, analogia de corte)", "exigence": "M_Ed ≤ M_Rd", "valeur": f"{r['moment_knm']:.1f} / {rg['M_Rd']:.1f} kN·m/m",
            "ok": ra["bending"] <= 1 + 1e-9, "taux": ra["bending"], "lib": "Flexão"},
           {"ref": "Corte de rolamento / corte (CLT)", "exigence": "V_Ed ≤ V_Rd", "valeur": f"{r['reaction_each_support_kn']:.1f} / {rg['V_Rd']:.1f} kN/m",
            "ok": ra["shear"] <= 1 + 1e-9, "taux": ra["shear"], "lib": "Corte"},
           {"ref": "Flecha final com deformação por corte e fluência (kdef 0,8)", "exigence": f"w_fin ≤ L/{float(lj.get('limite_flecha') or 300):g}",
            "valeur": f"{r['final_deflection']['total_mm']:.1f} mm (corte {r['final_deflection']['shear_mm']:.1f} mm)",
            "ok": ra["final_deflection"] <= 1 + 1e-9, "taux": ra["final_deflection"], "lib": "Flecha final"}]
    if pr:
        av = CP.validar_camadas(pr, cam)
        ctl.append({"ref": f"Âmbito {pr['eta']}", "exigence": "composição dentro do Anexo 2 da ETA",
                    "valeur": "dentro do âmbito" if not av else "; ".join(av), "ok": True if not av else None, "lib": "Âmbito ETA"})
    if lj.get("fogo_min"):
        prf = pr or CP.produto("generico_c24")
        g_tot = CLT_PROP["rho"] * rg["H"] + float(lj.get("g2_kn_m2") or 0.0)
        psi_fi = float(lj["psi_fogo"]) if lj.get("psi_fogo") is not None else (0.2 if cobertura else 0.5)
        fo = CP.fogo_painel(prf, cam, float(vao), g_tot, float(lj.get("q_kn_m2") or 0.0), psi_fi, float(lj["fogo_min"]),
                            int(lj.get("n_tabuas") or math.floor(1000 / prf["tabua_b_mm"][1])))
        ctl.append({"ref": f"Fogo R{float(lj['fogo_min']):g} — EN 1995-1-2 §3.4.3 / §4.2.2, β0 {prf['beta_0']:g} mm/min ({prf['eta'][:13]})",
                    "exigence": "M_Ed,fi ≤ M_Rd,fi (secção residual)",
                    "valeur": f"{fo['M_ed']:.1f} / {fo['M_rd']:.1f} kN·m/m — carbonização {fo['d_char']:.0f} mm + d0 7 mm, restam {fo['residual_mm']:.0f} mm",
                    "ok": fo["ok"], "taux": fo["taxa"] if math.isfinite(fo["taxa"]) else 9.99, "lib": "Fogo R"})
    nome = f"{pr['nome']} ({pr['eta'].split(' ')[0]})" if pr else "CLT"
    return {"element": "Painel CLT (motor bet_clt_ua)", "section": f"{nome} {'-'.join(f'{c:g}' for c in cam)} mm, vão {vao:g} m", "controles": ctl,
            "quantites": {"bois_m3": rg["H"]}, "rigidez": rg}


def _barras_sapata(ned, B, bmur, h, por_metro):
    """Armadura inferior pelo método das bielas (As = Nu(B − b)/(8·d·fyd)), Ø12 ou Ø16 com espaçamento ≤ 0,25 m."""
    d = max(h - 0.06, 0.15)
    As = ned * max(B - bmur, 0.05) / (8 * d * 500 / 1.15) * 10       # cm² (por m ou por direção)
    for phi, a in ((12, 1.131), (16, 2.011), (20, 3.142)):
        if por_metro:
            s = min(0.25, a / max(As, 1e-6))
            if s >= 0.10:
                return As, f"Ø{phi} // {_c(math.floor(s * 20) / 20)}"
        else:
            n = max(math.ceil(As / a), math.ceil(B / 0.25) + 1)
            if (B - 0.15) / max(n - 1, 1) >= 0.08:
                return As, f"{n} Ø{phi} c/ direção"
    return As, "ver nota"


def _carga_pilares(sap, pilares):
    g = q = 0.0
    for p in pilares:
        if abs(p["x_m"] - sap["x_m"]) <= sap["b_m"] / 2 and abs(p["y_m"] - sap["y_m"]) <= sap["l_m"] / 2:
            g += float(p.get("g_kn") or 0)
            q += float(p.get("q_kn") or 0)
    return g, q


def _seg_len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))


def verificar(m: dict) -> dict:
    """Verifica todos os elementos; ajusta as secções não conformes se m["ajustar"] (por defeito sim). Muta m (secções adotadas)."""
    if not m.get("grelhas_x") or not m.get("grelhas_y"):
        raise ValueError("indicar as grelhas (eixos) nas duas direções: grelhas_x e grelhas_y")
    ajustar = m.get("ajustar") is not False
    alvo = float(m.get("taxa_alvo") or 0.95)          # margem nas secções ajustadas
    bom = lambda ctl: _ok(ctl) and (_taxa(ctl) or 0) <= alvo   # noqa: E731
    qadm = m.get("solo_q_adm_kpa")
    res, ajustes, hip = [], [], []
    pil = m.get("pilares") or []

    def reg(tipo, el, r, orig=None):
        res.append({"tipo": tipo, "ref": el.get("ref") or tipo, "seccao": r["section"], "controles": r["controles"], "taxa": _taxa(r["controles"]),
                    "ok": _ok(r["controles"]), "original": orig, "elemento": r["element"]})

    # --- vigas
    for v in m.get("vigas") or []:
        mat = v.get("material") or "GL24h"
        L = float(v.get("vao_calculo_m") or math.hypot(v["x1_m"] - v["x0_m"], v["y1_m"] - v["y0_m"]))

        def calc(b, h, cl):
            if cl in MADEIRAS:
                return structure.calculer({"element": "poutre_bois", "classe": cl, "portee_m": L, "b_m": b, "h_m": h, "g_kn_m": v.get("g_kn_m") or 0,
                                           "q_kn_m": v.get("q_kn_m") or 0, "psi2": v.get("psi2"), "classe_service": v.get("classe_servico") or 1,
                                           "limite_fleche": v.get("limite_flecha") or 300})
            return structure.calculer({"element": "poutre_ba", "portee_m": L, "b_m": b, "h_m": h, "g_kn_m": v.get("g_kn_m") or 0,
                                       "q_kn_m": v.get("q_kn_m") or 0, "fck": v.get("fck") or 25})
        b0, h0 = float(v["b_m"]), float(v["h_m"])
        r = calc(b0, h0, mat)
        orig = None
        if not _ok(r["controles"]) and ajustar:
            orig = f"{b0 * 1000:.0f} × {h0 * 1000:.0f} {mat if mat in MADEIRAS else 'BA'} — taxa {(_taxa(r['controles']) or 0) * 100:.0f} %"
            cand = []
            if mat in MADEIRAS:
                classes = [mat] + (["GL28h"] if mat == "GL24h" else [])
                for cl in classes:
                    for b in [x for x in LARG_GL if x >= b0 - 1e-9][:4] or [b0]:
                        h = h0
                        while h <= max(h0 * 2.2, h0 + 0.6):
                            cand.append((b * h, b, round(h, 3), cl))
                            h += 0.038
            else:
                cand = [(b0 * (h0 + k * 0.05), b0, round(h0 + k * 0.05, 3), mat) for k in range(1, 15)]
            for _, b, h, cl in sorted(cand):
                rr = calc(b, h, cl)
                if bom(rr["controles"]):
                    r = rr
                    v.update(b_m=b, h_m=h, material=cl)
                    ajustes.append(f"Viga {v.get('ref') or ''}: {orig} → {b * 1000:.0f} × {h * 1000:.0f} {cl if cl in MADEIRAS else 'BA'} "
                                   f"(taxa {(_taxa(rr['controles']) or 0) * 100:.0f} %)")
                    break
        reg("viga", v, r, orig)

    # --- pilares
    for p in pil:
        mat = p.get("material") or "betao"
        L = float(p["cota_topo_m"]) - float(p["cota_base_m"])
        G, Q = float(p.get("g_kn") or 0), float(p.get("q_kn") or 0)
        if G + Q <= 0:
            hip.append(f"Pilar {p.get('ref') or ''}: cargas não indicadas — não verificado")
            continue
        ned = 1.35 * G + 1.5 * Q

        def calc(b, h):
            if mat in MADEIRAS:
                return _pilar_madeira(b, h, float(p.get("comprimento_encurvadura_m") or L), ned, mat)
            return structure.calculer({"element": "poteau_ba", "b_m": b, "h_m": h, "hauteur_m": L, "n_ed_kn": ned, "fck": p.get("fck") or 25})
        b0, h0 = float(p["b_m"]), float(p["h_m"])
        r, orig = calc(b0, h0), None
        if not _ok(r["controles"]) and ajustar:
            orig = f"{b0 * 1000:.0f} × {h0 * 1000:.0f} — taxa {(_taxa(r['controles']) or 0) * 100:.0f} %"
            for k in range(1, 20):
                b, h = round(b0 + 0.025 * k, 3), round(h0 + 0.025 * k, 3)
                rr = calc(b, h)
                if bom(rr["controles"]):
                    r = rr
                    p.update(b_m=b, h_m=h)
                    ajustes.append(f"Pilar {p.get('ref') or ''}: {orig} → {b * 1000:.0f} × {h * 1000:.0f}")
                    break
        reg("pilar", p, r, orig)

    # --- lajes de betão armado (suspensas)
    for lj in m.get("lajes") or []:
        if lj.get("tipo") != "laje_ba":
            continue
        lx, ly = abs(lj["x1_m"] - lj["x0_m"]), abs(lj["y1_m"] - lj["y0_m"])
        r = structure.calculer({"element": "dalle_ba", "lx_m": lx, "ly_m": ly, "h_m": lj["espessura_m"], "g2_kn_m2": lj.get("g2_kn_m2") or 1.5,
                                "q_kn_m2": lj.get("q_kn_m2") or 2.0, "fck": lj.get("fck") or 25})
        reg("laje", lj, r)

    # --- painéis CLT (vão de cálculo indicado)
    for lj in m.get("lajes") or []:
        if lj.get("tipo") == "clt" and lj.get("vao_m"):
            r, orig = clt_painel(lj, float(lj["vao_m"])), None
            if not _ok(r["controles"]) and ajustar:
                cam0 = lj.get("camadas_mm") or [round(float(lj["espessura_m"]) * 1000 / 5, 1)] * 5
                orig = f"CLT {sum(cam0):g} ({len(cam0)} camadas) — taxa {(_taxa(r['controles']) or 0) * 100:.0f} %"
                for cam in _clt_candidatos(sum(cam0)):
                    rr = clt_painel(dict(lj, camadas_mm=cam, espessura_m=sum(cam) / 1000), float(lj["vao_m"]))
                    if bom([c for c in rr["controles"] if c.get("lib") != "Âmbito ETA"]):
                        r = rr
                        lj.update(camadas_mm=cam, espessura_m=sum(cam) / 1000,
                                  descricao=(lj.get("descricao") or "").replace(f"{sum(cam0):g}-{len(cam0)}s", f"{sum(cam):g}-{len(cam)}s")
                                  .replace(f"CLT {sum(cam0):g}", f"CLT {sum(cam):g}") or None)
                        ajustes.append(f"Painel CLT {lj.get('ref') or ''} (vão {float(lj['vao_m']):g} m): {orig} → CLT {sum(cam):g} "
                                       f"({len(cam)} camadas {'-'.join(f'{c:g}' for c in cam)}) — taxa {(_taxa(rr['controles']) or 0) * 100:.0f} %")
                        break
            reg("painel CLT", lj, r, orig)
    prods = {lj.get("produto") for lj in m.get("lajes") or [] if lj.get("tipo") == "clt" and lj.get("vao_m") and lj.get("produto")}
    if prods:
        from . import clt_produtos as CP
        for k in sorted(prods):
            pp = CP.produto(k)
            hip.append(f"Painéis {pp['nome']}: valores declarados na {pp['eta']} — E0,mean {pp['E0_mean']:g} MPa, f_m,k {pp['fm_k']:g} MPa × k_sys, "
                       f"G_R {pp['G_R']:g} MPa, f_R,k pela figura 3 da ETA, carbonização β0 {pp['beta_0']:g} mm/min; vibração, ligações, "
                       "estabilidade lateral, integridade e isolamento ao fogo (E, I) não verificados aqui")
    elif any(lj.get("tipo") == "clt" and lj.get("vao_m") for lj in m.get("lajes") or []):
        hip.append("Painéis CLT: propriedades C24 típicas (EN 338 / EN 16351, f_r,k 1,1 MPa, G_R 50 MPa) — substituir pelos valores da ETA do fabricante; "
                   "vibração dos pavimentos (NP EN 1995-1-1 §7.3), ligações, estabilidade lateral e fogo não verificados aqui")

    # --- sapatas isoladas
    def sap_calc(B, Lg, h, G, Q, bmur, filante):
        par = {"element": "semelle", "b_m": B, "h_m": h, "profondeur_m": 0.8, "largeur_mur_m": bmur}
        if not filante:
            par["l_m"] = Lg
            par.update(g_kn=G, q_kn=Q)
        else:
            par.update(g_kn=G, q_kn=Q)
        if qadm:
            par["q_adm_els_kpa"] = qadm
        else:
            par.update(phi_deg=m.get("solo_phi_deg") or 30, gamma_sol=18)
        return structure.calculer(par)

    if not qadm:
        hip.append("Tensão admissível do terreno não indicada: capacidade resistente NP EN 1997-1 anexo D com φ' 30° e γ 18 kN/m³ — estudo geotécnico indispensável")
    for s in m.get("sapatas") or []:
        s.setdefault("l_m", s["b_m"])
        G, Q = (float(s["g_kn"]), float(s.get("q_kn") or 0)) if s.get("g_kn") else _carga_pilares(s, pil)
        h = float(s.get("h_m") or 0.30)
        if G + Q <= 0:
            hip.append(f"Sapata {s.get('ref') or ''}: sem carga (indicar g_kn / q_kn ou os pilares) — não verificada")
            s["armadura"] = "—"
            continue
        r, orig = sap_calc(s["b_m"], s["l_m"], h, G, Q, s.get("b_pilar_m") or 0.4, False), None
        if not _ok(r["controles"]) and ajustar:
            orig = f"{_c(s['b_m'])} × {_c(s['l_m'])} — taxa {(_taxa(r['controles']) or 0) * 100:.0f} %"
            B, Lg = s["b_m"], s["l_m"]
            while not bom(r["controles"]) and B < 5:
                B, Lg = round(B + 0.10, 2), round(Lg + 0.10, 2)
                h = max(h, round((B - 0.4) / 4 + 0.05, 2))
                r = sap_calc(B, Lg, h, G, Q, s.get("b_pilar_m") or 0.4, False)
            s.update(b_m=B, l_m=Lg)
            ajustes.append(f"Sapata {s.get('ref') or ''}: {orig} → {_c(B)} × {_c(Lg)} × {_c(h)} m")
        s["h_m"] = h
        ned = 1.35 * G + 1.5 * Q
        s["As_cm2"], s["armadura"] = _barras_sapata(ned, max(s["b_m"], s["l_m"]), s.get("b_pilar_m") or 0.4, h, False)
        reg("sapata", s, r, orig)

    # --- sapatas contínuas
    for s in m.get("sapatas_continuas") or []:
        G, Q = float(s.get("g_kn_m") or 0), float(s.get("q_kn_m") or 0)
        h = float(s.get("h_m") or 0.25)
        if G + Q <= 0:
            hip.append(f"Sapata contínua {s.get('ref') or ''}: carga linear não indicada — não verificada")
            s["armadura"] = "3 Ø12 long. + Ø12 // 0,25 (mínimo)"
            continue
        bm = s.get("largura_muro_m") or 0.2
        r, orig = sap_calc(s["b_m"], None, h, G, Q, bm, True), None
        if not _ok(r["controles"]) and ajustar:
            orig = f"B {_c(s['b_m'])} — taxa {(_taxa(r['controles']) or 0) * 100:.0f} %"
            B = s["b_m"]
            while not bom(r["controles"]) and B < 3:
                B = round(B + 0.05, 2)
                r = sap_calc(B, None, h, G, Q, bm, True)
            s["b_m"] = B
            ajustes.append(f"Sapata contínua {s.get('ref') or ''}: {orig} → B {_c(B)} m")
        s["h_m"] = h
        As, lab = _barras_sapata(1.35 * G + 1.5 * Q, s["b_m"], bm, h, True)
        s["armadura"] = f"3 Ø12 long. + {lab} transv."
        reg("sapata contínua", s, r, orig)
    cont = {}
    for a in ajustes:
        cont[a] = cont.get(a, 0) + 1
    ajustes = [a + (f" (× {k})" if k > 1 else "") for a, k in cont.items()]
    return {"elementos": res, "ajustes": ajustes, "hipoteses": hip, "conforme": all(e["ok"] for e in res)}


# ================================================================================================================ desenho
class _Folha:
    def __init__(self, doc, fmt):
        import pymupdf
        self.pm = pymupdf
        self.W, self.H = FOLHAS[fmt]
        self.fmt = fmt
        self.p = doc.new_page(width=self.W, height=self.H)
        self.fr, self.fb = _fontes()
        self.p.insert_font(fontname="cpr", fontfile=self.fr)
        self.p.insert_font(fontname="cpb", fontfile=self.fb)
        self._fonts = {}

    def _font(self, bold):
        k = "b" if bold else "r"
        if k not in self._fonts:
            self._fonts[k] = self.pm.Font(fontfile=self.fb if bold else self.fr)
        return self._fonts[k]

    def lw(self, s, size, bold=False):
        return self._font(bold).text_length(_tr(s), fontsize=size)

    def t(self, x, y, s, size=7, cor=(0, 0, 0), bold=False, centrado=False, rot=0):
        s = _tr(s)
        if centrado:
            L = self.lw(s, size, bold)
            if rot == 90:
                x, y = x + size * 0.35, y + L / 2
            else:
                x -= L / 2
        self.p.insert_text((x, y), s, fontname="cpb" if bold else "cpr", fontsize=size, color=cor, rotate=rot)

    def linha(self, pts, cor=(0, 0, 0), w=0.8, dash=None):
        sh = self.p.new_shape()
        sh.draw_polyline(pts)
        sh.finish(color=cor, width=w, dashes=dash, closePath=False)
        sh.commit()

    def poli(self, pts, cor=(0, 0, 0), fill=None, w=0.8):
        sh = self.p.new_shape()
        sh.draw_polyline(pts + [pts[0]])
        sh.finish(color=cor, fill=fill, width=w, closePath=True)
        sh.commit()

    def ret(self, r, cor=(0, 0, 0), fill=None, w=0.8, dash=None):
        sh = self.p.new_shape()
        sh.draw_rect(self.pm.Rect(*r))
        sh.finish(color=cor, fill=fill, width=w, dashes=dash)
        sh.commit()

    def circ(self, c, r, cor=(0, 0, 0), fill=None, w=0.8):
        sh = self.p.new_shape()
        sh.draw_circle(c, r)
        sh.finish(color=cor, fill=fill, width=w)
        sh.commit()

    def caixa(self, x, y, w, s, size=7, cor=(0, 0, 0)):
        """Texto com quebra de linha; devolve o y seguinte."""
        palavras, linha, yy = _tr(s).split(), "", y
        for pw in palavras:
            tst = (linha + " " + pw).strip()
            if self.lw(tst, size) > w and linha:
                self.t(x, yy, linha, size, cor)
                yy += size * 1.3
                linha = pw
            else:
                linha = tst
        if linha:
            self.t(x, yy, linha, size, cor)
            yy += size * 1.3
        return yy + size * 0.4

    def tabela(self, x, y, cab, linhas, larg, size=8, passo=16):
        tot = sum(larg)
        self.ret((x, y - passo + 4, x + tot, y + 4), VERDE, fill=VERDE, w=0.3)
        xs = [x + sum(larg[:i]) for i in range(len(larg))]
        for j, c in enumerate(cab):
            self.t(xs[j] + 3, y, c, size, BRANCO, True)
        for i, ln in enumerate(linhas):
            yy = y + passo * (i + 1)
            if i % 2 == 0:
                self.ret((x, yy - passo + 4, x + tot, yy + 4), (0.94, 0.95, 0.94), fill=(0.94, 0.95, 0.94), w=0)
            for j, v in enumerate(ln):
                s = _tr(str(v))
                while s and self.lw(s, size) > larg[j] - 6:
                    s = s[:-1]
                ko = s.startswith(("NÃO", "НЕ ", "NOT "))
                self.t(xs[j] + 3, yy, s, size, (0.75, 0.12, 0.12) if ko else (0, 0, 0), ko)
        return y + passo * (len(linhas) + 1)

    def cartucho(self, projeto, local, titulo, num, n, tot, escala, data):
        w, h = 520, 175
        x0, y0 = self.W - w - 30, self.H - h - 25
        self.ret((x0, y0, x0 + w, y0 + h), VERDE, w=1.2)
        self.ret((x0, y0, x0 + w, y0 + 30), VERDE, fill=VERDE)
        self.t(x0 + 10, y0 + 21, "ConstruPilot", 14, BRANCO, True)
        self.t(x0 + 120, y0 + 20, "Gabinete de projeto digital · Portugal", 8, CREME)
        self.t(x0 + 10, y0 + 50, titulo, 11.5, VERDE, True)
        self.t(x0 + 10, y0 + 66, f"Obra: {projeto}"[:110], 7.5)
        self.t(x0 + 10, y0 + 78, f"Local: {local}"[:110], 7.5, CINZA)
        self.t(x0 + 10, y0 + 92, "Projeto de execução — pré-dimensionamento por motores ConstruPilot, a validar pelo projetista de estruturas.", 7, CINZA)
        yy = y0 + 104
        self.linha([(x0, yy), (x0 + w, yy)], VERDE, 0.6)
        cols = [("Escala", escala), ("Desenho", num), ("Folha", f"{n}/{tot}"), ("Data", data), ("Formato", self.fmt)]
        cw = w / len(cols)
        for i, (k, v) in enumerate(cols):
            self.t(x0 + i * cw + 8, yy + 16, k, 7, CINZA)
            self.t(x0 + i * cw + 8, yy + 36, v, 11, VERDE, True)
        self.ret((15, 15, self.W - 15, self.H - 15), (0.2, 0.2, 0.2), w=1.0)

    def escala_grafica(self, x, y, s):
        for i in range(5):
            self.ret((x + i * s, y, x + (i + 1) * s, y + 5), (0, 0, 0), fill=(0, 0, 0) if i % 2 == 0 else BRANCO, w=0.5)
            self.t(x + i * s - 2, y + 16, str(i), 7)
        self.t(x + 5 * s - 2, y + 16, "5 m", 7)

    def norte(self, x, y):
        self.circ((x, y), 18, (0, 0, 0))
        self.poli([(x - 5, y + 10), (x, y - 14), (x + 5, y + 10)], (0, 0, 0), fill=(0, 0, 0))
        self.t(x, y - 24, "N", 10, bold=True, centrado=True)


class _Pl:
    """Desenho em metros: origem (ox, oy) na folha, y do edifício para cima."""

    def __init__(self, fl, ox, oy, s):
        self.fl, self.ox, self.oy, self.s = fl, ox, oy, s

    def P(self, x, y):
        return (self.ox + x * self.s, self.oy - y * self.s)

    def lin(self, pts, cor=(0, 0, 0), w=0.8, dash=None):
        self.fl.linha([self.P(*q) for q in pts], cor, w, dash)

    def rect(self, x0, y0, x1, y1, cor=(0, 0, 0), fill=None, w=0.8, dash=None):
        a, b = self.P(min(x0, x1), max(y0, y1)), self.P(max(x0, x1), min(y0, y1))
        self.fl.ret((a[0], a[1], b[0], b[1]), cor, fill, w, dash)

    def poli(self, pts, cor=(0, 0, 0), fill=None, w=0.8):
        self.fl.poli([self.P(*q) for q in pts], cor, fill, w)

    def txt(self, x, y, s, size=7, cor=(0, 0, 0), bold=False, centrado=True, rot=0):
        q = self.P(x, y)
        self.fl.t(q[0], q[1], s, size, cor, bold, centrado, rot)

    def _tick(self, q):
        self.fl.linha([(q[0] - 3.5, q[1] + 3.5), (q[0] + 3.5, q[1] - 3.5)], (0, 0, 0), 1.0)

    def cota_h(self, y, xs, size=7, ref=None, bold=False):
        xs = sorted(set(round(x, 4) for x in xs))
        if len(xs) < 2:
            return
        self.lin([(xs[0], y), (xs[-1], y)], (0, 0, 0), 0.5)
        for x in xs:
            if ref is not None:
                self.lin([(x, ref), (x, y + (0.15 if y > ref else -0.15))], (0.45, 0.45, 0.45), 0.3)
            self._tick(self.P(x, y))
        for a, b in zip(xs[:-1], xs[1:]):
            if b - a > 1e-3:
                q = self.P((a + b) / 2, y)
                txt = _mm(b - a)
                if self.fl.lw(txt, size) > (b - a) * self.s - 2:
                    q = (q[0], q[1] - size - 2)
                self.fl.t(q[0], q[1] - 2.5, txt, size, (0, 0, 0), bold, True)

    def cota_v(self, x, ys, size=7, ref=None, bold=False):
        ys = sorted(set(round(y, 4) for y in ys))
        if len(ys) < 2:
            return
        self.lin([(x, ys[0]), (x, ys[-1])], (0, 0, 0), 0.5)
        for y in ys:
            if ref is not None:
                self.lin([(ref, y), (x + (0.15 if x > ref else -0.15), y)], (0.45, 0.45, 0.45), 0.3)
            self._tick(self.P(x, y))
        for a, b in zip(ys[:-1], ys[1:]):
            if b - a > 1e-3:
                q = self.P(x, (a + b) / 2)
                self.fl.t(q[0] - 3, q[1], _mm(b - a), size, (0, 0, 0), bold, True, rot=90)

    def nivel(self, x, y, s, size=7.5):
        q = self.P(x, y)
        self.fl.poli([(q[0] - 4.5, q[1] - 8), (q[0] + 4.5, q[1] - 8), (q[0], q[1])], (0, 0, 0), BRANCO, 0.7)
        self.fl.linha([(q[0] - 10, q[1]), (q[0] + 8 + self.fl.lw(s, size, True), q[1])], (0, 0, 0), 0.4)
        self.fl.t(q[0] + 7, q[1] - 2.5, s, size, (0, 0, 0), True)


def _cota_txt(z):
    return f"{'+' if z >= 0 else '−'}{_c(abs(z), 3)}"


def _bbox(m):
    xs = [g["pos_m"] for g in m["grelhas_x"]]
    ys = [g["pos_m"] for g in m["grelhas_y"]]
    for col in ("sapatas_continuas", "muros"):
        for s in m.get(col) or []:
            xs += [p[0] for p in s["pontos"]]
            ys += [p[1] for p in s["pontos"]]
    for lj in m.get("lajes") or []:
        xs += [lj["x0_m"], lj["x1_m"]]
        ys += [lj["y0_m"], lj["y1_m"]]
    return min(xs), max(xs), min(ys), max(ys)


def _escala(m):
    """1:50 em A1 / A0 se couber (coluna lateral de 620 pt para quadros e notas), senão 1:100 em A1."""
    x0, x1, y0, y1 = _bbox(m)
    w, h = x1 - x0 + 7.5, y1 - y0 + 7.5
    for fmt, s, k in (("A1", S50, 50), ("A0", S50, 50), ("A1", S50 / 2, 100), ("A0", S50 / 2, 100)):
        W, H = FOLHAS[fmt]
        if w * s <= W - 720 and h * s <= H - 300:
            return fmt, s, k
    return "A0", S50 / 4, 200


def _base_planta(fl, m, s, titulo, sub):
    x0, x1, y0, y1 = _bbox(m)
    ox = 60 + 3.6 * s - x0 * s
    oy = 130 + (y1 + 3.6) * s
    fl.t(40, 52, titulo, 20, VERDE, True)
    fl.t(40, 74, sub, 10, CINZA)
    p = _Pl(fl, ox, oy, s)
    gx, gy = m["grelhas_x"], m["grelhas_y"]
    xa, xb, ya, yb = x0 - 1.4, x1 + 1.4, y0 - 1.4, y1 + 1.4
    r = 11
    for g in gx:
        p.lin([(g["pos_m"], ya), (g["pos_m"], yb)], (0.5, 0.5, 0.5), 0.4, "[14 3 2 3] 0")
        for yy, d in ((ya, 1), (yb, -1)):
            q = p.P(g["pos_m"], yy)
            q = (q[0], q[1] + d * (r + 1))
            fl.circ(q, r, (0, 0, 0), BRANCO, 0.8)
            fl.t(q[0], q[1] + 3.5, str(g["nome"]), 9, bold=True, centrado=True)
    for g in gy:
        p.lin([(xa, g["pos_m"]), (xb, g["pos_m"])], (0.5, 0.5, 0.5), 0.4, "[14 3 2 3] 0")
        for xx, d in ((xa, -1), (xb, 1)):
            q = p.P(xx, g["pos_m"])
            q = (q[0] + d * (r + 1), q[1])
            fl.circ(q, r, (0, 0, 0), BRANCO, 0.8)
            fl.t(q[0], q[1] + 3.5, str(g["nome"]), 9, bold=True, centrado=True)
    xs, ys = [g["pos_m"] for g in gx], [g["pos_m"] for g in gy]
    p.cota_h(yb + 1.0, xs, ref=None)
    if len(xs) > 2:
        p.cota_h(yb + 1.7, [min(xs), max(xs)], bold=True)
    p.cota_v(xa - 1.0, ys)
    if len(ys) > 2:
        p.cota_v(xa - 1.7, [min(ys), max(ys)], bold=True)
    fl.norte(fl.W - 70, 70)
    fl.escala_grafica(60, fl.H - 70, s)
    return p, (x0, x1, y0, y1)


MURO_FILL = {"gazobeton": (0.95, 0.93, 0.84), "tijolo": (0.86, 0.55, 0.42), "alvenaria": (0.86, 0.55, 0.42), "clt": MAD, "madeira": MAD}


def _paredes(p, lst, esp_key, fill, cor=(0, 0, 0), dash=None, w=0.8):
    for s in lst:
        e = float(s.get(esp_key) or 0.2)
        fill_s = MURO_FILL.get(s.get("material"), fill) if fill is not None else None
        for (xa, ya), (xb, yb) in zip(s["pontos"][:-1], s["pontos"][1:]):
            if abs(ya - yb) < 1e-6:
                p.rect(min(xa, xb) - e / 2, ya - e / 2, max(xa, xb) + e / 2, ya + e / 2, cor, fill_s, w, dash)
            elif abs(xa - xb) < 1e-6:
                p.rect(xa - e / 2, min(ya, yb) - e / 2, xa + e / 2, max(ya, yb) + e / 2, cor, fill_s, w, dash)
            else:
                ang = math.atan2(yb - ya, xb - xa)
                dx, dy = -math.sin(ang) * e / 2, math.cos(ang) * e / 2
                p.poli([(xa + dx, ya + dy), (xb + dx, yb + dy), (xb - dx, yb - dy), (xa - dx, ya - dy)], cor, fill_s, w)


def _lado(fl):
    return fl.W - 660


def _f_fund(doc, m, ver, fmt, s, k, n, tot, data):
    fl = _Folha(doc, fmt)
    p, (x0, x1, y0, y1) = _base_planta(fl, m, s, "GO-01 · PLANTA DE FUNDAÇÕES COTADA",
                                       f"Sapatas isoladas e contínuas, muros de fundação, lajes térreas · escala 1:{k} · cotas em mm, níveis em m")
    for lj in m.get("lajes") or []:
        if lj.get("piso") == "fundacao":
            p.rect(lj["x0_m"], lj["y0_m"], lj["x1_m"], lj["y1_m"], (0.6, 0.6, 0.6), (0.94, 0.94, 0.94), 0.3)
            cx, cy = (lj["x0_m"] + lj["x1_m"]) / 2, (lj["y0_m"] + lj["y1_m"]) / 2
            p.txt(cx, cy + 0.3, lj.get("descricao") or f"laje térrea {_mm(lj['espessura_m'])} mm", 7.5, CINZA, True)
            if lj.get("cota_topo_m") is not None:
                p.nivel(cx - 1.5, cy - 0.4, f"T.O.S. {_cota_txt(lj['cota_topo_m'])}")
    _paredes(p, m.get("sapatas_continuas") or [], "b_m", None, (0, 0, 0), "[5 3] 0", 0.7)
    for sp in m.get("sapatas") or []:
        a, b, x, y = sp["b_m"], sp["l_m"], sp["x_m"], sp["y_m"]
        p.rect(x - a / 2, y - b / 2, x + a / 2, y + b / 2, (0, 0, 0), BRANCO, 0.9, "[5 3] 0")
        p.lin([(x - a / 2, y - b / 2), (x + a / 2, y + b / 2)], (0.55, 0.55, 0.55), 0.3)
        p.lin([(x - a / 2, y + b / 2), (x + a / 2, y - b / 2)], (0.55, 0.55, 0.55), 0.3)
    cp = m.get("cota_pavimento_m")
    _paredes(p, [mu for mu in m.get("muros") or [] if cp is None or mu.get("cota_topo_m") is None or mu["cota_topo_m"] <= cp + 0.05], "espessura_m", BET)
    for pl in m.get("pilares") or []:
        if (pl.get("material") or "betao") == "betao" or pl.get("pedestal_m"):
            e = pl.get("pedestal_m") or max(pl["b_m"], pl["h_m"])
            p.rect(pl["x_m"] - e / 2, pl["y_m"] - e / 2, pl["x_m"] + e / 2, pl["y_m"] + e / 2, (0, 0, 0), (0.55, 0.55, 0.55), 0.8)
    # etiquetas e cotas das sapatas
    vistos = set()
    for sp in m.get("sapatas") or []:
        p.txt(sp["x_m"] + sp["b_m"] / 2 + 0.1, sp["y_m"] + sp["l_m"] / 2 + 0.12, sp.get("ref") or "S", 7, COBRE, True, centrado=False)
        if sp.get("ref") not in vistos:
            vistos.add(sp.get("ref"))
            p.cota_h(sp["y_m"] - sp["l_m"] / 2 - 0.3, [sp["x_m"] - sp["b_m"] / 2, sp["x_m"] + sp["b_m"] / 2], 6.5)
            p.cota_v(sp["x_m"] + sp["b_m"] / 2 + 0.3, [sp["y_m"] - sp["l_m"] / 2, sp["y_m"] + sp["l_m"] / 2], 6.5)
    for sc in m.get("sapatas_continuas") or []:
        (xa, ya), (xb, yb) = sc["pontos"][0], sc["pontos"][1]
        mx, my = (xa + xb) / 2, (ya + yb) / 2
        vert = abs(xa - xb) < 1e-6
        p.txt(mx + (sc["b_m"] / 2 + 0.25 if vert else 0), my + (0 if vert else sc["b_m"] / 2 + 0.15), sc.get("ref") or "SC", 7, COBRE, True, rot=90 if vert else 0)
    sx = sorted({round(sp["x_m"], 3) for sp in m.get("sapatas") or []})
    sy = sorted({round(sp["y_m"], 3) for sp in m.get("sapatas") or []})
    if sx:
        p.cota_h(y0 - 2.4, [x0] + sx + [x1], 6.5)
    if sy:
        p.cota_v(x1 + 2.4, [y0] + sy + [y1], 6.5)
    cotas = sorted({round(sp.get("cota_topo_m"), 3) for sp in (m.get("sapatas") or []) + (m.get("sapatas_continuas") or []) if sp.get("cota_topo_m") is not None})
    xl = _lado(fl)
    rows = []
    for sp in m.get("sapatas") or []:
        if sp.get("ref") in {r[0] for r in rows}:
            continue
        e = next((v for v in ver["elementos"] if v["ref"] == sp.get("ref") and v["tipo"] == "sapata"), None)
        rows.append([sp.get("ref") or "—", f"{_c(sp['b_m'])} × {_c(sp['l_m'])}", _c(sp["h_m"]), sp.get("armadura", "—"),
                     f"{e['taxa'] * 100:.0f} %" if e and e["taxa"] is not None else "—"])
    for sc in m.get("sapatas_continuas") or []:
        if sc.get("ref") in {r[0] for r in rows}:
            continue
        e = next((v for v in ver["elementos"] if v["ref"] == sc.get("ref") and v["tipo"] == "sapata contínua"), None)
        rows.append([sc.get("ref") or "—", f"B {_c(sc['b_m'])} contínua", _c(sc["h_m"]), sc.get("armadura", "—"), f"{e['taxa'] * 100:.0f} %" if e and e["taxa"] is not None else "—"])
    y = fl.tabela(xl, 140, ["Ref.", "Dimensões (m)", "h (m)", "Armadura inferior A500", "Taxa"], rows, [60, 140, 50, 300, 60])
    y = fl.caixa(xl, y + 20, 610, "Notas: betão C25/30 XC2, recobrimento 50 mm (75 mm contra o terreno), betão de limpeza C12/15 50 mm. "
                 + (f"Tensão admissível do terreno {m['solo_q_adm_kpa']:g} kPa (a confirmar pelo estudo geotécnico). " if m.get("solo_q_adm_kpa") else "")
                 + ("Topo das sapatas: " + " / ".join(_cota_txt(c) for c in cotas) + ". " if cotas else "")
                 + "Sapatas centradas nos eixos dos pilares e muros salvo cota em contrário.", 8)
    fl.cartucho(m.get("projeto") or "—", m.get("local") or "—", "Gros-œuvre — planta de fundações", "GO-01", n, tot, f"1:{k}", data)


def _f_piso(doc, m, ver, fmt, s, k, n, tot, data, piso, num, titulo):
    fl = _Folha(doc, fmt)
    p, (x0, x1, y0, y1) = _base_planta(fl, m, s, f"{num} · {titulo.upper()}", f"Vigas, pilares, lajes / painéis e paredes de apoio · escala 1:{k} · cotas em mm, níveis em m")
    for lj in m.get("lajes") or []:
        if lj.get("piso") != piso:
            continue
        tipo = lj.get("tipo") or "laje_ba"
        fill = {"laje_ba": BET, "clt": (0.96, 0.89, 0.74), "vigas_i": (0.98, 0.94, 0.86)}.get(tipo, (0.95, 0.95, 0.95))
        p.rect(lj["x0_m"], lj["y0_m"], lj["x1_m"], lj["y1_m"], CASTANHO if tipo != "laje_ba" else (0, 0, 0), fill, 0.6)
        if tipo == "vigas_i" and lj.get("espacamento_m"):
            d, e = lj.get("direcao_vao") or "x", float(lj["espacamento_m"])
            if d == "x":
                yy = min(lj["y0_m"], lj["y1_m"]) + e / 2
                while yy < max(lj["y0_m"], lj["y1_m"]):
                    p.lin([(lj["x0_m"], yy), (lj["x1_m"], yy)], (0.75, 0.62, 0.40), 0.3)
                    yy += e
            else:
                xx = min(lj["x0_m"], lj["x1_m"]) + e / 2
                while xx < max(lj["x0_m"], lj["x1_m"]):
                    p.lin([(xx, lj["y0_m"]), (xx, lj["y1_m"])], (0.75, 0.62, 0.40), 0.3)
                    xx += e
        cx, cy = (lj["x0_m"] + lj["x1_m"]) / 2, (lj["y0_m"] + lj["y1_m"]) / 2
        d = lj.get("direcao_vao") or "x"
        if d == "x":
            fl.linha([p.P(lj["x0_m"] + 0.3, cy - 0.5), p.P(lj["x1_m"] - 0.3, cy - 0.5)], CASTANHO, 1.0)
        else:
            fl.linha([p.P(cx - 0.5, lj["y0_m"] + 0.3), p.P(cx - 0.5, lj["y1_m"] - 0.3)], CASTANHO, 1.0)
        lab = lj.get("descricao") or {"laje_ba": f"laje BA {_mm(lj['espessura_m'])}", "clt": f"CLT {_mm(lj['espessura_m'])}",
                                      "vigas_i": f"vigas I {_mm(lj['espessura_m'])}"}.get(tipo, tipo)
        w = fl.lw(lab, 7.5, True) / s + 0.4
        p.rect(cx - w / 2, cy - 0.05, cx + w / 2, cy + 0.6, CASTANHO, BRANCO, 0.5)
        p.txt(cx, cy + 0.15, lab, 7.5, CASTANHO, True)
        if lj.get("cota_topo_m") is not None:
            p.nivel(cx + w / 2 + 0.3, cy + 0.1, _cota_txt(lj["cota_topo_m"]))
    _paredes(p, [mu for mu in m.get("muros") or [] if (mu.get("cota_topo_m") or 0) >= (m.get("cota_pavimento_m") or 0) - 0.5], "espessura_m", BET)
    for v in m.get("vigas") or []:
        if v.get("piso") != piso:
            continue
        b = v["b_m"]
        mad = (v.get("material") or "GL24h") in MADEIRAS
        _paredes(p, [{"pontos": [[v["x0_m"], v["y0_m"]], [v["x1_m"], v["y1_m"]]], "e": b}], "e", MAD_E if mad else (0.70, 0.70, 0.70), CASTANHO if mad else (0, 0, 0))
        vert = abs(v["x0_m"] - v["x1_m"]) < 1e-6
        mx, my = (v["x0_m"] + v["x1_m"]) / 2, (v["y0_m"] + v["y1_m"]) / 2
        lab = f"{v.get('ref') or 'V'} {_mm(b)} × {_mm(v['h_m'])} {v.get('material') if mad else 'BA'}"
        p.txt(mx + (b / 2 + 0.28 if vert else 0), my + (0 if vert else b / 2 + 0.15), lab, 7, CASTANHO, True, rot=90 if vert else 0)
        if v.get("cota_topo_ini_m") is not None:
            for (x, y, z) in ((v["x0_m"], v["y0_m"], v["cota_topo_ini_m"]), (v["x1_m"], v["y1_m"], v.get("cota_topo_fim_m", v["cota_topo_ini_m"]))):
                p.nivel(x + 0.25, y + (0.25 if not vert else (0.3 if y > my else -0.5)), "topo " + _cota_txt(z), 6.8)
    for pl in m.get("pilares") or []:
        if True:
            mad = (pl.get("material") or "betao") in MADEIRAS
            p.rect(pl["x_m"] - pl["b_m"] / 2, pl["y_m"] - pl["h_m"] / 2, pl["x_m"] + pl["b_m"] / 2, pl["y_m"] + pl["h_m"] / 2, (0, 0, 0),
                   (0.40, 0.24, 0.08) if mad else (0.35, 0.35, 0.35), 0.8)
    # cadeias de cotas das vigas (posições dos apoios)
    vs = [v for v in m.get("vigas") or [] if v.get("piso") == piso]
    ys = sorted({round(c, 3) for v in vs if abs(v["x0_m"] - v["x1_m"]) < 1e-6 for c in (v["y0_m"], v["y1_m"])})
    xs = sorted({round(c, 3) for v in vs if abs(v["y0_m"] - v["y1_m"]) < 1e-6 for c in (v["x0_m"], v["x1_m"])})
    if ys:
        p.cota_v(x1 + 2.4, [y0] + ys + [y1], 6.5)
    if xs:
        p.cota_h(y0 - 2.4, [x0] + xs + [x1], 6.5)
    xl = _lado(fl)
    rows = []
    for e in ver["elementos"]:
        if e["tipo"] in ("viga", "pilar", "laje", "painel CLT"):
            el = next((v for v in (m.get("vigas") or []) + (m.get("pilares") or []) + (m.get("lajes") or []) if (v.get("ref") or e["tipo"]) == e["ref"]), {})
            if e["tipo"] == "pilar" or el.get("piso") == piso:
                rows.append([e["ref"], e["elemento"], e["seccao"], f"{e['taxa'] * 100:.0f} %" if e["taxa"] is not None else "—", "conforme" if e["ok"] else "NÃO conforme"])
    y = fl.tabela(xl, 140, ["Ref.", "Elemento", "Secção", "Taxa", "Estado"], rows[:40], [60, 170, 220, 60, 100])
    aj = [a for a in ver["ajustes"] if a.startswith(("Viga", "Pilar"))]
    if aj:
        fl.t(xl, y + 24, "Secções ajustadas pelo motor (desenhadas aqui):", 9, (0.75, 0.12, 0.12), True)
        yy = y + 40
        for a in aj[:12]:
            yy = fl.caixa(xl, yy, 610, "• " + a, 8)
    fl.cartucho(m.get("projeto") or "—", m.get("local") or "—", f"Gros-œuvre — {titulo.lower()}", num, n, tot, f"1:{k}", data)


# ------------------------------------------------------------------------------------------------ cortes
def _z_laje(lj, x, y):
    if lj.get("cota_topo_ini_m") is None:
        return lj.get("cota_topo_m")
    d = lj.get("pendente_dir") or "y"
    a, b = (lj["x0_m"], lj["x1_m"]) if d == "x" else (lj["y0_m"], lj["y1_m"])
    t = ((x if d == "x" else y) - min(a, b)) / max(abs(b - a), 1e-6)
    return lj["cota_topo_ini_m"] + t * (lj["cota_topo_fim_m"] - lj["cota_topo_ini_m"])


def _corte(fl, m, c, s, ox, oy_top, zmax, zmin):
    """Corte vertical: direcao 'x' = plano y = pos (abscissa x), 'y' = plano x = pos (abscissa y)."""
    d, pos = c["direcao"], float(c["pos_m"])
    u_of = (lambda x, y: x) if d == "x" else (lambda x, y: y)
    w_of = (lambda x, y: y) if d == "x" else (lambda x, y: x)
    p = _Pl(fl, ox, oy_top + zmax * s, s)          # z absoluto → y da folha
    Z = lambda z: z                                 # noqa: E731
    niveis = set()
    grel = m["grelhas_x"] if d == "x" else m["grelhas_y"]
    us = [g["pos_m"] for g in grel]
    umin, umax = min(us), max(us)

    def seg_corta(pts, e):
        """Intervalos u e se o segmento é paralelo ao corte."""
        out = []
        for (xa, ya), (xb, yb) in zip(pts[:-1], pts[1:]):
            wa, wb, ua, ub = w_of(xa, ya), w_of(xb, yb), u_of(xa, ya), u_of(xb, yb)
            if abs(wa - wb) < 1e-6:
                if abs(wa - pos) <= e / 2 + 1e-6:
                    out.append((min(ua, ub) - e / 2, max(ua, ub) + e / 2, True, ua, ub))
            elif min(wa, wb) - e / 2 <= pos <= max(wa, wb) + e / 2:
                t = (pos - wa) / (wb - wa) if abs(wb - wa) > 1e-9 else 0
                uc = ua + max(0, min(1, t)) * (ub - ua)
                out.append((uc - e / 2, uc + e / 2, False, ua, ub))
        return out

    for sc in m.get("sapatas_continuas") or []:
        if sc.get("cota_topo_m") is None:
            continue
        for a, b, *_ in seg_corta(sc["pontos"], sc["b_m"]):
            p.rect(a, Z(sc["cota_topo_m"] - sc["h_m"]), b, Z(sc["cota_topo_m"]), (0, 0, 0), BET, 0.8)
            niveis.add(sc["cota_topo_m"])
    for sp in m.get("sapatas") or []:
        if sp.get("cota_topo_m") is None:
            continue
        a_w = sp["l_m"] if d == "x" else sp["b_m"]
        a_u = sp["b_m"] if d == "x" else sp["l_m"]
        if abs(w_of(sp["x_m"], sp["y_m"]) - pos) <= a_w / 2:
            uc = u_of(sp["x_m"], sp["y_m"])
            p.rect(uc - a_u / 2, Z(sp["cota_topo_m"] - sp["h_m"]), uc + a_u / 2, Z(sp["cota_topo_m"]), (0, 0, 0), BET, 0.8)
            p.cota_h(sp["cota_topo_m"] - sp["h_m"] - 0.35, [uc - a_u / 2, uc + a_u / 2], 6.5)
            niveis.add(sp["cota_topo_m"])
    for mu in m.get("muros") or []:
        for a, b, *_ in seg_corta(mu["pontos"], mu.get("espessura_m") or 0.2):
            p.rect(a, Z(mu["cota_base_m"]), b, Z(mu["cota_topo_m"]), (0, 0, 0), MURO_FILL.get(mu.get("material"), BET), 0.8)
            niveis.add(mu["cota_topo_m"])
    for lj in m.get("lajes") or []:
        wa, wb = (lj["y0_m"], lj["y1_m"]) if d == "x" else (lj["x0_m"], lj["x1_m"])
        if not min(wa, wb) - 1e-6 <= pos <= max(wa, wb) + 1e-6:
            continue
        ua, ub = (lj["x0_m"], lj["x1_m"]) if d == "x" else (lj["y0_m"], lj["y1_m"])
        ua, ub = min(ua, ub), max(ua, ub)
        e = float(lj.get("espessura_m") or 0.2)
        tipo = lj.get("tipo") or "laje_ba"
        fill = {"laje_ba": BET, "clt": MAD, "vigas_i": (0.97, 0.92, 0.80)}.get(tipo, BET)
        pts_top = []
        for u in (ua, ub):
            x, y = (u, pos) if d == "x" else (pos, u)
            pts_top.append((u, _z_laje(lj, x, y)))
        if None in [z for _, z in pts_top]:
            continue
        p.poli([(pts_top[0][0], pts_top[0][1]), (pts_top[1][0], pts_top[1][1]), (pts_top[1][0], pts_top[1][1] - e), (pts_top[0][0], pts_top[0][1] - e)],
               CASTANHO if tipo != "laje_ba" else (0, 0, 0), fill, 0.7)
        if lj.get("isolamento_m"):
            ei = float(lj["isolamento_m"])
            p.poli([(pts_top[0][0], pts_top[0][1] + ei), (pts_top[1][0], pts_top[1][1] + ei), (pts_top[1][0], pts_top[1][1]), (pts_top[0][0], pts_top[0][1])],
                   (0.2, 0.4, 0.6), ISO, 0.4)
        for _, z in pts_top:
            niveis.add(round(z, 3))
    for pl in m.get("pilares") or []:
        a_w = pl["h_m"] if d == "x" else pl["b_m"]
        a_u = pl["b_m"] if d == "x" else pl["h_m"]
        if abs(w_of(pl["x_m"], pl["y_m"]) - pos) <= max(a_w / 2, 0.35):
            uc = u_of(pl["x_m"], pl["y_m"])
            mad = (pl.get("material") or "betao") in MADEIRAS
            if pl.get("pedestal_m") and pl.get("cota_pedestal_base_m") is not None:
                e = pl["pedestal_m"]
                p.rect(uc - e / 2, pl["cota_pedestal_base_m"], uc + e / 2, pl["cota_base_m"], (0, 0, 0), (0.62, 0.62, 0.62), 0.7)
            p.rect(uc - a_u / 2, pl["cota_base_m"], uc + a_u / 2, pl["cota_topo_m"], CASTANHO if mad else (0, 0, 0), MAD_E if mad else (0.72, 0.72, 0.72), 0.8)
            niveis.add(pl["cota_base_m"])
    for v in m.get("vigas") or []:
        zi = v.get("cota_topo_ini_m")
        if zi is None:
            continue
        zf = v.get("cota_topo_fim_m", zi)
        mad = (v.get("material") or "GL24h") in MADEIRAS
        cor, fill = (CASTANHO, MAD_E) if mad else ((0, 0, 0), (0.70, 0.70, 0.70))
        for a, b, par, ua, ub in seg_corta([[v["x0_m"], v["y0_m"]], [v["x1_m"], v["y1_m"]]], v["b_m"]):
            if par:
                za = zi if ua <= ub else zf
                zb = zf if ua <= ub else zi
                u0, u1 = min(ua, ub), max(ua, ub)
                p.poli([(u0, za), (u1, zb), (u1, zb - v["h_m"]), (u0, za - v["h_m"])], cor, fill, 0.8)
                niveis.update({round(za, 3), round(zb, 3)})
            else:
                t = 0.5
                L = math.hypot(v["x1_m"] - v["x0_m"], v["y1_m"] - v["y0_m"])
                if L > 1e-6:
                    wc = w_of(v["x0_m"], v["y0_m"])
                    wd = w_of(v["x1_m"], v["y1_m"]) - wc
                    t = (pos - wc) / wd if abs(wd) > 1e-9 else 0.5
                z = zi + max(0, min(1, t)) * (zf - zi)
                p.rect(a, z - v["h_m"], b, z, cor, fill, 0.8)
                niveis.add(round(z, 3))
    for nv in m.get("niveis") or []:
        niveis.add(round(nv["cota_m"], 3))
    # eixos, cotas, níveis
    for g in grel:
        p.lin([(g["pos_m"], zmax + 0.2), (g["pos_m"], zmin - 0.2)], (0.5, 0.5, 0.5), 0.3, "[14 3 2 3] 0")
        q = p.P(g["pos_m"], zmax + 0.45)
        fl.circ(q, 10, (0, 0, 0), BRANCO, 0.8)
        fl.t(q[0], q[1] + 3.5, str(g["nome"]), 8.5, bold=True, centrado=True)
    p.cota_h(zmin - 0.7, us, 7)
    zs = sorted(n for n in niveis if zmin - 0.01 <= n <= zmax + 0.01)
    p.cota_v(umin - 1.6, zs, 6.3)
    nom = {round(nv["cota_m"], 3): nv["nome"] for nv in m.get("niveis") or []}
    ult = -1e9
    for z in zs:
        if (z - ult) * s < 11:
            continue
        p.nivel(umax + 1.2, z, _cota_txt(z) + (f"  {nom[z]}" if z in nom else ""), 7)
        ult = z
    q = p.P((umin + umax) / 2, zmax + 1.1)
    fl.t(q[0], q[1], f"CORTE {c.get('nome', '')} — " + ("LONGITUDINAL" if d == "x" else "TRANSVERSAL") + f" ({'y' if d == 'x' else 'x'} = {_c(pos)} m)",
         11, VERDE, True, centrado=True)


def _zrange(m):
    zs = []
    for col, ks in (("sapatas", ("cota_topo_m",)), ("sapatas_continuas", ("cota_topo_m",)), ("muros", ("cota_base_m", "cota_topo_m")),
                    ("pilares", ("cota_base_m", "cota_topo_m")), ("vigas", ("cota_topo_ini_m", "cota_topo_fim_m")),
                    ("lajes", ("cota_topo_m", "cota_topo_ini_m", "cota_topo_fim_m"))):
        for e in m.get(col) or []:
            zs += [e[k] for k in ks if e.get(k) is not None]
    zs += [s["cota_topo_m"] - s["h_m"] for s in (m.get("sapatas") or []) + (m.get("sapatas_continuas") or []) if s.get("cota_topo_m") is not None]
    if not zs:
        return None
    return min(zs) - 0.3, max(zs) + 0.5


def _cortes_auto(m):
    if m.get("cortes"):
        return m["cortes"]
    gx, gy = sorted(g["pos_m"] for g in m["grelhas_x"]), sorted(g["pos_m"] for g in m["grelhas_y"])
    px = next((v["x0_m"] for v in m.get("vigas") or [] if abs(v["x0_m"] - v["x1_m"]) < 1e-6), (gx[0] + gx[1]) / 2 if len(gx) > 1 else gx[0])
    py = next((s["y_m"] for s in m.get("sapatas") or [] if gy[0] < s["y_m"] < gy[-1]), (gy[0] + gy[1]) / 2 if len(gy) > 1 else gy[0])
    return [{"nome": "1-1", "direcao": "y", "pos_m": px}, {"nome": "2-2", "direcao": "x", "pos_m": py}]


def _f_cortes(doc, m, fmt, s, k, n, tot, data):
    zr = _zrange(m)
    if not zr:
        return False
    zmin, zmax = zr
    fl = _Folha(doc, fmt)
    fl.t(40, 52, "GO-04 · CORTES CONSTRUTIVOS COTADOS", 20, VERDE, True)
    fl.t(40, 74, f"Sapatas, muros, pilares, vigas, lajes / painéis com níveis absolutos · escala 1:{k}", 10, CINZA)
    y = 150
    for c in _cortes_auto(m)[:2]:
        grel = m["grelhas_x"] if c["direcao"] == "x" else m["grelhas_y"]
        umin = min(g["pos_m"] for g in grel)
        ox = 60 + 3.2 * s - umin * s
        _corte(fl, m, c, s, ox, y + 1.4 * s, zmax, zmin)
        y += (zmax - zmin + 3.2) * s
    fl.cartucho(m.get("projeto") or "—", m.get("local") or "—", "Gros-œuvre — cortes construtivos", "GO-04", n, tot, f"1:{k}", data)
    return True


def _f_quadros(doc, m, ver, n, tot, data):
    fl = _Folha(doc, "A1")
    fl.t(40, 52, "GO-05 · QUADROS DE ELEMENTOS, VERIFICAÇÕES E AJUSTES", 20, VERDE, True)
    fl.t(40, 74, "Resultados dos motores ConstruPilot (NP EN 1992 / 1995 / 1997) — secções adotadas = secções desenhadas", 10, CINZA)
    rows = [[e["tipo"], e["ref"], e["elemento"], e["seccao"], f"{(e['taxa'] or 0) * 100:.0f} %" if e["taxa"] is not None else "—",
             "conforme" if e["ok"] else "NÃO conforme", (e["original"] or "")] for e in ver["elementos"]]
    y = fl.tabela(40, 140, ["Tipo", "Ref.", "Elemento", "Secção adotada", "Taxa", "Estado", "Secção original (se ajustada)"], rows[:70],
                  [100, 70, 230, 330, 60, 110, 300], size=8, passo=16)
    if y + 40 < fl.H - 500:
        xx, yy = 40, y + 40
    else:
        xx, yy = 1250, 140
    fl.t(xx, yy, "Ajustes automáticos", 11, VERDE, True)
    yy += 18
    for a in ver["ajustes"] or ["Nenhum: todos os elementos verificam com as secções do projeto."]:
        yy = fl.caixa(xx, yy, 1000, "• " + a, 8.5)
    yy += 10
    fl.t(xx, yy, "Hipóteses / a validar", 11, VERDE, True)
    yy += 18
    for h in (ver["hipoteses"] or []) + (m.get("hipoteses") or []) + ["Pré-dimensionamento por motores determinísticos — a validar pelo projetista de estruturas antes da execução."]:
        yy = fl.caixa(xx, yy, 1000, "• " + h, 8.5)
    fl.cartucho(m.get("projeto") or "—", m.get("local") or "—", "Gros-œuvre — quadros e verificações", "GO-05", n, tot, "—", data)


def planos(m: dict, ver: dict, data: str | None = None, lingua: str | None = None) -> bytes:
    """Caderno de planos de gros-œuvre (PDF vetorial); lingua 'uk' / 'en' traduz as peças desenhadas."""
    tok = _TR_CV.set(_dic(lingua))
    try:
        return _planos(m, ver, data)
    finally:
        _TR_CV.reset(tok)



def _paredes_niveis(m):
    """Paredes acima do pavimento agrupadas por cota de base → [(cota_base, [muros])]."""
    cp = m.get("cota_pavimento_m") or 0.0
    g = {}
    for mu in m.get("muros") or []:
        if mu.get("cota_base_m") is not None and mu["cota_base_m"] >= cp - 0.05:
            g.setdefault(round(mu["cota_base_m"], 3), []).append(mu)
    return sorted(g.items())


def _f_paredes(doc, m, ver, fmt, s, k, n, tot, data, cota, muros, num):
    fl = _Folha(doc, fmt)
    nome = next((nv["nome"] for nv in m.get("niveis") or [] if abs(nv["cota_m"] - cota) < 0.05), _cota_txt(cota))
    p, (x0, x1, y0, y1) = _base_planta(fl, m, s, f"{num} · PLANTA DE PAREDES PORTANTES — {nome.upper()}",
                                       f"Paredes estruturais com espessura, material e comprimento de cada troço · escala 1:{k} · cotas em mm, níveis em m")
    _paredes(p, muros, "espessura_m", BET)
    xs, ys = set(), set()
    for mu in muros:
        e = float(mu.get("espessura_m") or 0.2)
        mat = {"clt": "CLT", "gazobeton": "Газобетон", "tijolo": "Alvenaria", "alvenaria": "Alvenaria"}.get(mu.get("material"), "BA")
        for (xa, ya), (xb, yb) in zip(mu["pontos"][:-1], mu["pontos"][1:]):
            xs.update((xa, xb)); ys.update((ya, yb))
            L = math.hypot(xb - xa, yb - ya)
            if L < 0.3:
                continue
            mx, my = (xa + xb) / 2, (ya + yb) / 2
            vert = abs(xa - xb) < 1e-6
            lab = f"{mat} {_mm(e)} · L {_mm(L)}"
            p.txt(mx + (e / 2 + 0.28 if vert else 0), my + (0 if vert else e / 2 + 0.14), lab, 6.8, CASTANHO, True, rot=90 if vert else 0)
    p.cota_h(y0 - 2.4, sorted(xs), 6.5)
    p.cota_v(x1 + 2.4, sorted(ys), 6.5)
    tops = sorted({mu["cota_topo_m"] for mu in muros})
    p.nivel(x0 + 0.6, y0 + 0.6, f"base {_cota_txt(cota)} · topo {' / '.join(_cota_txt(t) for t in tops)}")
    xl = _lado(fl)
    tot_L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for mu in muros for a, b in zip(mu["pontos"][:-1], mu["pontos"][1:]))
    area = sum(math.hypot(b[0] - a[0], b[1] - a[1]) * (mu["cota_topo_m"] - mu["cota_base_m"]) for mu in muros for a, b in zip(mu["pontos"][:-1], mu["pontos"][1:]))
    vol = sum(math.hypot(b[0] - a[0], b[1] - a[1]) * (mu["cota_topo_m"] - mu["cota_base_m"]) * float(mu.get("espessura_m") or 0.2)
              for mu in muros for a, b in zip(mu["pontos"][:-1], mu["pontos"][1:]))
    y = fl.tabela(xl, 140, ["Grandeza", "Valor"], [["Comprimento total de paredes", f"{_c(tot_L, 2)} m"], ["Área bruta de paredes", f"{_c(area, 1)} m²"],
                                                 ["Volume bruto", f"{_c(vol, 2)} m³"], ["Altura", f"{_c(tops[-1] - cota, 2)} m"]], [300, 200])
    fl.caixa(xl, y + 20, 610, "Notas: vãos de portas e janelas conforme o projeto de arquitetura (não representados); ligações parede / laje e parede / "
             "fundação com cantoneiras e chapas perfuradas conforme ETA dos ligadores; juntas entre painéis com tira de contraplacado e parafusos.", 8)
    fl.cartucho(m.get("projeto") or "—", m.get("local") or "—", f"Gros-œuvre — paredes {nome.lower()}", num, n, tot, f"1:{k}", data)


def _f_alcados(doc, m, fmt, s, k, n, tot, data, num):
    """Alçados das quatro fachadas a partir das paredes, lajes e níveis do modelo."""
    zr = _zrange(m)
    if not zr:
        return
    zmin, zmax = zr
    fl = _Folha(doc, fmt)
    fl.t(40, 52, f"{num} · ALÇADOS ESTRUTURAIS COTADOS", 20, VERDE, True)
    fl.t(40, 74, f"Volumes das paredes portantes, lajes e coberturas, com níveis absolutos · escala 1:{k}", 10, CINZA)
    cp = m.get("cota_pavimento_m") or 0.0
    vistas = [("SUL / ПІВДЕНЬ", "x", 0, False), ("NORTE / ПІВНІЧ", "x", 1, True), ("OESTE / ЗАХІД", "y", 0, True), ("ESTE / СХІД", "y", 1, False)]
    larg = max(g["pos_m"] for g in m["grelhas_x"]) - min(g["pos_m"] for g in m["grelhas_x"])
    prof = max(g["pos_m"] for g in m["grelhas_y"]) - min(g["pos_m"] for g in m["grelhas_y"])
    W_av = fl.W - 120
    alt = (zmax - min(zmin, cp - 0.5) + 3.5)
    if (max(larg, prof) + 5) * s * 2 > W_av or alt * s * 2 > fl.H - 330:      # 2 × 2 não cabe → 1:100
        s, k = s / 2, k * 2
        fl.t(40, 90, f"(alçados a 1:{k})", 9, CINZA)
    col_w = (max(larg, prof) + 5) * s
    ncol = max(1, min(2, int(W_av // col_w)))
    for i, (nome, eixo, lado, inv) in enumerate(vistas):
        L = larg if eixo == "x" else prof
        cx = 60 + (i % ncol) * col_w + 2.5 * s
        cy = 120 + (i // ncol) * (alt * s)
        p = _Pl(fl, cx, cy + (zmax + 0.8) * s, s)
        u0 = min(g["pos_m"] for g in (m["grelhas_x"] if eixo == "x" else m["grelhas_y"]))
        U = (lambda u: (u0 + L - (u - u0)) if inv else u)
        # terreno
        p.lin([(U(u0) - 1.5 if not inv else U(u0 + L) - 1.5, cp - 0.15), (U(u0 + L) + 1.5 if not inv else U(u0) + 1.5, cp - 0.15)], (0.35, 0.25, 0.15), 1.2)
        for mu in m.get("muros") or []:
            if mu.get("cota_topo_m") is None or mu["cota_topo_m"] <= cp:
                continue
            us = [pt[0] if eixo == "x" else pt[1] for pt in mu["pontos"]]
            a, b = U(min(us)), U(max(us))
            fill = MURO_FILL.get(mu.get("material"), BET)
            p.rect(min(a, b), max(mu["cota_base_m"], cp - 0.15), max(a, b), mu["cota_topo_m"], (0.25, 0.25, 0.25), fill, 0.7)
        for lj in m.get("lajes") or []:
            if lj.get("piso") == "fundacao":
                continue
            ua, ub = (lj["x0_m"], lj["x1_m"]) if eixo == "x" else (lj["y0_m"], lj["y1_m"])
            zt = lj.get("cota_topo_m") if lj.get("cota_topo_m") is not None else max(lj.get("cota_topo_ini_m") or 0, lj.get("cota_topo_fim_m") or 0)
            e = float(lj.get("espessura_m") or 0.2) + float(lj.get("isolamento_m") or 0)
            p.rect(min(U(ua), U(ub)), zt - float(lj.get("espessura_m") or 0.2), max(U(ua), U(ub)), zt + float(lj.get("isolamento_m") or 0),
                   CASTANHO, (0.80, 0.62, 0.38), 0.6)
        zs = sorted({round(nv["cota_m"], 3) for nv in m.get("niveis") or [] if nv["cota_m"] >= cp - 0.01} |
                    {round(mu["cota_topo_m"], 3) for mu in m.get("muros") or [] if mu.get("cota_topo_m") and mu["cota_topo_m"] > cp} |
                    {round(lj["cota_topo_m"] + float(lj.get("isolamento_m") or 0), 3) for lj in m.get("lajes") or [] if lj.get("cota_topo_m") and lj["cota_topo_m"] > cp})
        p.cota_v(min(U(u0), U(u0 + L)) - 1.0, [cp] + [z for z in zs if z > cp], 6.3)
        last = -1e9
        for z in zs:
            if (z - last) * s < 11:
                continue
            p.nivel(max(U(u0), U(u0 + L)) + 0.6, z, _cota_txt(z), 6.8)
            last = z
        p.cota_h(cp - 0.9, [U(g["pos_m"]) for g in (m["grelhas_x"] if eixo == "x" else m["grelhas_y"])], 6.3)
        q = p.P(U(u0 + L / 2) if not inv else U(u0 + L / 2), max(zs + [cp]) + 0.9)
        fl.t(q[0], q[1], f"ALÇADO {nome}", 10, VERDE, True, centrado=True)
    fl.cartucho(m.get("projeto") or "—", m.get("local") or "—", "Gros-œuvre — alçados", num, n, tot, f"1:{k}", data)
    fl.escala_grafica(60, fl.H - 70, s)


def _planos(m: dict, ver: dict, data: str | None = None) -> bytes:
    import pymupdf
    from datetime import date
    data = data or date.today().strftime("%d/%m/%Y")
    fmt, s, k = _escala(m)
    pisos = [pz for pz in ("pavimento", "cobertura") if any(e.get("piso") == pz for e in (m.get("vigas") or []) + (m.get("lajes") or []))]
    niv = _paredes_niveis(m)
    tot = 1 + len(pisos) + (1 if _zrange(m) else 0) + 1 + len(niv) + (1 if niv and _zrange(m) else 0)
    doc = pymupdf.open()
    i = 1
    _f_fund(doc, m, ver, fmt, s, k, i, tot, data)
    for pz, num, tit in (("pavimento", "GO-02", "Planta estrutural do pavimento"), ("cobertura", "GO-03", "Planta de estrutura da cobertura")):
        if pz in pisos:
            i += 1
            _f_piso(doc, m, ver, fmt, s, k, i, tot, data, pz, num, tit)
    if _zrange(m):
        i += 1
        _f_cortes(doc, m, fmt, s, k, i, tot, data)
    i += 1
    _f_quadros(doc, m, ver, i, tot, data)
    for j, (cota, mus) in enumerate(niv):
        i += 1
        _f_paredes(doc, m, ver, fmt, s, k, i, tot, data, cota, mus, f"GO-{6 + j:02d}")
    if niv and _zrange(m):
        i += 1
        _f_alcados(doc, m, fmt, s, k, i, tot, data, f"GO-{6 + len(niv):02d}")
    return doc.tobytes(garbage=3, deflate=True)


# ================================================================================================================ nota + interface
def calcular(m: dict, lingua: str | None = None) -> dict:
    """→ {"verificacao", "planos_pdf", "escala", "formato"} (m é copiado: a entrada do chamador não é alterada)."""
    import copy
    m = copy.deepcopy(m)
    ver = verificar(m)
    fmt, s, k = _escala(m)
    return {"modelo": m, "verificacao": ver, "planos_pdf": planos(m, ver, lingua=lingua), "escala": k, "formato": fmt}


def note(m: dict) -> dict:
    """Nota de cálculo (rendu) + folhas de planos num único PDF; PNG da primeira página."""
    import pymupdf
    r = calcular(m)
    ver = r["verificacao"]
    titre = f"Gros-œuvre — {m.get('projeto') or 'estrutura'}"
    rows = [[e["tipo"], e["ref"], e["seccao"], f"{(e['taxa'] or 0) * 100:.0f} %" if e["taxa"] is not None else "—", "conforme" if e["ok"] else "NÃO conforme"]
            for e in ver["elementos"]]
    W = notes.W
    blocs = [("p", "Verificação encadeada dos elementos de gros-œuvre pelos motores ConstruPilot e caderno de planos de execução cotados "
                   f"(GO-01 fundações a GO-05 quadros, escala 1:{r['escala']}, formato {r['formato']}) anexo a esta nota."),
             ("h2", "1. Elementos verificados"), ("table", ["Tipo", "Ref.", "Secção adotada", "Taxa", "Estado"], rows, [26 * W, 18 * W, 80 * W, 16 * W, 28 * W])]
    if ver["ajustes"]:
        blocs += [("h2", "2. Secções ajustadas automaticamente"), ("hyp", ver["ajustes"])]
    vistos = set()
    for e in ver["elementos"]:
        chave = (e["tipo"], e["ref"], e["seccao"], e["original"])
        if (e["original"] or not e["ok"]) and chave not in vistos:
            vistos.add(chave)
            blocs += [("h2", f"Controlos — {e['tipo']} {e['ref']}"), ("controls", e["controles"])]
    pdf, _ = notes.pdf(titre, (m.get("local") or "") + " · NP EN 1992 / 1995 / 1997", blocs, ver["hipoteses"] + (m.get("hipoteses") or []))
    d = pymupdf.open(stream=pdf, filetype="pdf")
    d.insert_pdf(pymupdf.open(stream=r["planos_pdf"], filetype="pdf"))
    out = d.tobytes(garbage=3, deflate=True)
    png = d[0].get_pixmap(dpi=110).tobytes("png")
    return {"titre": titre, "pdf": out, "png": png, "verificacao": ver, "escala": r["escala"], "formato": r["formato"], "modelo": r["modelo"]}
