"""Ferramenta do Assistente « calcul_structure » (versão PT): ponte para os motores de estruturas determinísticos já existentes
(e testados) no ConstruPilot.

Elementos cobertos (pré-dimensionamento, a validar pelo projetista de estruturas):
  - poutre_ba     : viga de betão armado (NP EN 1992-1-1) — esforços por coeficientes simplificados, armadura por structuro_ec2.design_section,
                    escolha dos varões, verificação L/d (EC2 §7.4.2), quantidade de aço (kg);
  - poteau_ba     : pilar de betão armado (NP EN 1992-1-1 §5.8 curvatura nominal, §6.1 flexão composta);
  - poinconnement : punçoamento de laje (NP EN 1992-1-1 §6.4);
  - dalle_ba      : laje armada em duas direções (structuro_slab2way.design, coeficientes μx/μy, malhas eletrossoldadas);
  - linteau       : lintel (padieira) sobre vão em aço e/ou betão armado (structuro_lintel.lintel_design);
  - poutre_bois   : viga de madeira maciça / lamelada-colada (NP EN 1995-1-1, structuro_ec5.verify) + flecha w_fin (kdef);
  - semelle       : capacidade resistente do terreno sob sapata (NP EN 1997-1 anexo D, structuro_ec7.bearing) ou tensão admissível do estudo geotécnico;
  - escalier      : escada (stair_engine, regra de Blondel; RGEU / DL 163/2006 a confirmar).

As chaves dos parâmetros de entrada e do dicionário de resultado são idênticas às da versão FR (esquema da ferramenta partilhado);
apenas os textos apresentados ao utilizador estão em português europeu.
"""
from __future__ import annotations

import math
import re

from . import notes

BARRES = [8, 10, 12, 14, 16, 20, 25, 32]
KG_M = {d: round(math.pi * (d / 1000) ** 2 / 4 * 7850, 3) for d in BARRES}          # kg/m (ρ aço 7850)
APPUIS_POUTRE = {"isostatique": (1 / 8, 0.5, 1.0), "continue_rive": (1 / 10, 0.6, 1.3), "continue_interieure": (1 / 12, 0.55, 1.5),
                 "console": (1 / 2, 1.0, 0.4)}                                               # (coef. M·pL², coef. V·pL, K do EC2 §7.4.2)
APPUIS_PT = {"isostatique": "viga simplesmente apoiada", "continue_rive": "viga contínua, vão extremo",
             "continue_interieure": "viga contínua, vão interior", "console": "consola"}
BORDOS_PT = {"rive": "bordo", "continu": "contínuo", "libre": "livre"}
POSICAO_PT = {"interieur": "pilar interior", "rive": "pilar de bordo", "angle": "pilar de canto"}
DUREE_PT = {"permanent": "permanente", "long": "longa duração", "medium": "média duração", "short": "curta duração", "instantaneous": "instantânea"}
ESCADA_PT = {"straight": "reta", "quarter_turn_bottom": "de um quarto de volta (em baixo)", "quarter_turn_top": "de um quarto de volta (em cima)",
             "half_turn": "de meia-volta", "helicoidal": "helicoidal"}
VARIANTE_PT = {"default": "padrão", "balanced": "degraus em leque", "straight": "com patamar"}
def _variante(v):
    return VARIANTE_PT.get(v) or re.sub(r"sweep_(\d+)", r"rotação \1°", str(v))


NIVEL_PT = {"red": "bloqueante", "orange": "aviso", "green": "ok"}
QUANT_PT = {"beton_m3": "betão (m³)", "acier_kg": "aço (kg)", "ratio_kg_m3": "taxa de armadura (kg/m³)", "bois_m3": "madeira (m³)"}


def _phi(label: str | None) -> str:
    """Designação dos varões no formato PT (HA12 → Ø12)."""
    return re.sub(r"HA(\d+)", r"Ø\1", label or "")


# Tradução das mensagens (FR) devolvidas pelos motores de escadas / lintéis — padrões conhecidos; caso contrário, texto genérico.
_N = r"([\d.,]+)"
_PADROES = [
    (r"Reculement nécessaire " + _N + r" mm > disponible " + _N + r" mm.*", r"Desenvolvimento necessário \1 mm > comprimento disponível \2 mm (a escada não cabe)."),
    (r"Largeur nécessaire pour le demi-tournant " + _N + r" mm > disponible " + _N + r" mm.*", r"Largura necessária para a escada de meia-volta \1 mm > disponível \2 mm."),
    (r"Aucune répartition.*", "Nenhuma distribuição de degraus em leque satisfaz as restrições geométricas."),
    (r"Giron (?:sur )?ligne de foulée " + _N + r" mm < (?:minimum )?" + _N + r" mm.*", r"Cobertor na linha de marcha \1 mm < mínimo \2 mm."),
    (r"Giron intérieur " + _N + r" mm < " + _N + r" mm.*", r"Cobertor interior \1 mm < mínimo \2 mm (aumentar o raio do núcleo central)."),
    (r"Giron " + _N + r" mm < minimum absolu " + _N + r" mm.*", r"Cobertor \1 mm < mínimo absoluto \2 mm."),
    (r"Giron " + _N + r" mm inférieur à la plage optimale \(" + _N + r" mm\).*", r"Cobertor \1 mm abaixo da gama ótima (\2 mm)."),
    (r"Largeur d'escalier " + _N + r" mm < (?:minimum de confort )?" + _N + r" mm.*", r"Largura da escada \1 mm < mínimo \2 mm."),
    (r"Pente " + _N + r"° > " + _N + r"°.*", r"Inclinação \1° > \2° (escada demasiado íngreme)."),
    (r"Pente " + _N + r"° au-delà de la plage confortable \(" + _N + r"°\).*", r"Inclinação \1° acima da gama confortável (\2°)."),
    (r"Formule de Blondel \(2h\+g\) = " + _N + r" mm hors plage acceptable (.*)\.", r"Regra de Blondel (2h + g) = \1 mm fora da gama aceitável \2."),
    (r"Formule de Blondel \(2h\+g\) = " + _N + r" mm hors plage optimale (.*)\.", r"Regra de Blondel (2h + g) = \1 mm fora da gama ótima \2."),
    (r"Hauteur de marche " + _N + r" mm > " + _N + r" mm.*", r"Altura do espelho \1 mm > máximo \2 mm."),
    (r"Hauteur de marche " + _N + r" mm au-delà de la plage optimale \(" + _N + r" mm\).*", r"Altura do espelho \1 mm acima da gama ótima (\2 mm)."),
    (r"Hauteur de marche " + _N + r" mm inférieure au confort recommandé.*", r"Altura do espelho \1 mm abaixo do valor de conforto recomendado."),
    (r"Échappée " + _N + r" mm.*< minimum " + _N + r" mm.*", r"Altura livre \1 mm < mínimo \2 mm."),
    (r"Configuration optimale.*", "Configuração ótima: regra de Blondel e inclinação nas gamas ideais."),
    (r"Géométrie conforme.*", "Geometria dentro dos limites internos do motor de escadas."),
    (r"Répartition automatique : (\d+) marches balancées.*", r"Distribuição automática: \1 degraus em leque."),
    (r"Erreur calcul.*", "Erro de cálculo do motor de escadas."),
    (r"Non constructible.*", "Não construível."),
    (r"Hauteur de maçonnerie \(" + _N + r" m\) < apex de voûte \(" + _N + r" m\).*",
     r"Altura de alvenaria (\1 m) < altura do arco de descarga (\2 m): efeito de arco incompleto, adotada carga retangular (a favor da segurança)."),
]


def _pt(msg: str | None, generico: str) -> str:
    """Traduz uma mensagem de motor (FR) para PT pelos padrões conhecidos; caso contrário devolve o texto genérico."""
    m = (msg or "").strip()
    for pat, rep in _PADROES:
        if re.fullmatch(pat, m, flags=re.S):
            return re.sub(pat, rep, m, flags=re.S)
    return generico


def _choix_barres(as_cm2: float, b_mm: float, enrobage_mm: float, etrier_mm: float = 8) -> dict:
    """Menor número de varões do mesmo diâmetro que cabem numa camada (espaçamento ≥ max(Ø, 20 mm))."""
    options = []
    for d in BARRES[1:]:
        a1 = math.pi * d * d / 4 / 100
        n = max(2, math.ceil(as_cm2 / a1 - 1e-9))
        libre = b_mm - 2 * (enrobage_mm + etrier_mm)
        if n * d + (n - 1) * max(d, 20) > libre:
            continue
        options.append({"n": n, "phi": d, "as_cm2": n * a1, "label": f"{n} Ø{d}"})
    best = None
    if options:   # secção mais económica a 15 % e, depois, o menor número de varões (betonagem mais fácil)
        amin = min(o["as_cm2"] for o in options)
        best = min((o for o in options if o["as_cm2"] <= 1.15 * amin), key=lambda o: (o["n"], o["as_cm2"]))
    if best is None:   # duas camadas
        d = 20
        n = math.ceil(as_cm2 / (math.pi * d * d / 4 / 100))
        best = {"n": n, "phi": d, "as_cm2": n * math.pi * d * d / 4 / 100, "label": f"{n} Ø{d} (2 camadas)", "deux_lits": True}
    return best


def _l_sur_d(rho: float, fck: float, K: float, ratio_as: float, fyk: float) -> float:
    """EC2 §7.4.2 (7.16a/b) com fator 310/σs ≈ (500/fyk)·(As,prov/As,req) limitado a 1,5."""
    r0 = math.sqrt(fck) * 1e-3
    rho = max(rho, 1e-6)
    if rho <= r0:
        base = 11 + 1.5 * math.sqrt(fck) * r0 / rho + 3.2 * math.sqrt(fck) * (r0 / rho - 1) ** 1.5
    else:
        base = 11 + 1.5 * math.sqrt(fck) * r0 / rho
    return K * base * min(1.5, (500 / fyk) * ratio_as)


def poutre_ba(p: dict) -> dict:
    """Viga de betão armado (NP EN 1992-1-1)."""
    from engines.structuro_ec2 import design_section
    L, b, h = float(p["portee_m"]), float(p["b_m"]), float(p["h_m"])
    fck, fyk = float(p.get("fck") or 25), float(p.get("fyk") or 500)
    c = float(p.get("enrobage_mm") or 30)
    appui = p.get("appuis") or "isostatique"
    cm, cv, K = APPUIS_POUTRE[appui]
    pp = 25 * b * h
    g, q = float(p.get("g_kn_m") or 0) + pp, float(p.get("q_kn_m") or 0)
    pu = 1.35 * g + 1.5 * q
    med, ved = cm * pu * L * L, cv * pu * L
    d = h - (c + 8 + 8) / 1000
    r = design_section(med, ved, b_m=b, h_m=h, d_m=d, fck=fck, fyk=fyk)
    fx, sh = r["flexure"], r["shear"]
    bars = _choix_barres(fx["as_req_cm2"], b * 1000, c)
    rho = bars["as_cm2"] / (b * d * 1e4)
    ld_lim = _l_sur_d(rho, fck, K, bars["as_cm2"] / max(fx["as_req_cm2"], 1e-6), fyk)
    ld = L / d
    asw_req = float(sh.get("asw_s_req_cm2_m") or 0)              # cm²/m
    phi_e = 8
    for phi_e in (8, 10, 12):
        a2 = 2 * math.pi * phi_e ** 2 / 4 / 100                   # estribo de 2 ramos, cm²
        s_calc = a2 / asw_req if asw_req > 0 else 9.9
        if s_calc >= 0.10:
            break
    s = max(0.05, min(sh["s_max_m"], 0.6, s_calc))
    s = math.floor(s * 100) / 100
    n_etriers = math.ceil(L / s) + 1
    # quantidades: armadura principal + 2 Ø10 de montagem + estribos (perímetro + ganchos)
    kg_long = bars["n"] * (L + 2 * 0.25) * KG_M[bars["phi"]] + 2 * (L + 0.5) * KG_M[10]
    kg_et = n_etriers * (2 * (b + h) - 8 * c / 1000 + 0.2) * KG_M[phi_e]
    beton = b * h * L
    ctl = [{"ref": "NP EN 1992-1-1 §6.1 flexão ELU", "exigence": f"As ≥ {fx['as_req_cm2']:.2f} cm² (μ = {fx['mu']:.3f} ≤ μlim {fx['mu_lim']:.3f})",
            "valeur": f"{bars['label']} = {bars['as_cm2']:.2f} cm²", "ok": bars["as_cm2"] >= fx["as_req_cm2"] - 1e-9 and fx["mode"] == "simple",
            "taux": fx["as_req_cm2"] / bars["as_cm2"] if bars["as_cm2"] else None, "lib": "Flexão (As necessária / As adotada)",
            "note": "armadura de compressão necessária: aumentar h" if fx["mode"] != "simple" else None},
           {"ref": "NP EN 1992-1-1 §6.2 esforço transverso (bielas)", "exigence": f"V_Ed ≤ V_Rd,max ({sh['vrdmax_kn']:.0f} kN)", "valeur": f"V_Ed {ved:.1f} kN",
            "ok": ved <= sh["vrdmax_kn"], "taux": ved / sh["vrdmax_kn"] if sh["vrdmax_kn"] else None, "lib": "Bielas (V_Ed / V_Rd,max)",
            "note": "aumentar a secção (b ou h)" if ved > sh["vrdmax_kn"] else None},
           {"ref": "NP EN 1992-1-1 §6.2.3 armadura de esforço transverso", "exigence": f"Asw/s ≥ {asw_req:.2f} cm²/m, s ≤ {sh['s_max_m'] * 100:.0f} cm",
            "valeur": f"estribos Ø{phi_e} 2 ramos, s = {s * 100:.0f} cm ({2 * math.pi * phi_e ** 2 / 4 / 100 / s:.2f} cm²/m)",
            "ok": 2 * math.pi * phi_e ** 2 / 4 / 100 / s >= asw_req - 1e-9 and s >= 0.05},
           {"ref": "NP EN 1992-1-1 §7.4.2 flecha (L/d)", "exigence": f"L/d ≤ {ld_lim:.1f}", "valeur": f"{ld:.1f}", "ok": ld <= ld_lim, "taux": ld / ld_lim if ld_lim else None, "lib": "Flecha (L/d / limite)",
            "note": "calcular a flecha ou aumentar a secção" if ld > ld_lim else None}]
    return {"element": "Viga de betão armado", "sollicitations": {"g": g, "q": q, "pu": pu, "med": med, "ved": ved, "poids_propre": pp},
            "section": f"{b * 100:.0f} × {h * 100:.0f} cm, d = {d * 100:.1f} cm, C{fck:g}, A{fyk:g}", "appuis": appui, "barres": bars,
            "etriers": f"estribos Ø{phi_e} s = {s * 100:.0f} cm ({n_etriers} estribos)", "quantites": {"beton_m3": beton, "acier_kg": kg_long + kg_et,
            "ratio_kg_m3": (kg_long + kg_et) / beton}, "controles": ctl, "details": r,
            "hypotheses": [f"momentos por coeficientes simplificados ({APPUIS_PT.get(appui, appui)}): M = pL²×{cm:.3f}, V = pL×{cv:g} (vãos sensivelmente iguais)"]
                          + (["viga contínua: apenas o momento de vão é dimensionado — armadura superior sobre os apoios (≈ pL²/10 a pL²/9) a calcular pelo projetista de estruturas"]
                             if appui.startswith("continue") else []) + [
                           "ELU 1,35 G + 1,5 Q (coeficientes recomendados, a confirmar com o Anexo Nacional português), peso próprio 25 kN/m³ incluído",
                           f"aço A{fyk:g} (ex.: A500 NR), recobrimento {c:g} mm a confirmar pela classe de exposição (NP EN 1992-1-1 §4.4.1)",
                           "quantidades de aço: comprimentos de amarração simplificados de 25 cm por extremidade"]}


def poutre_bois(p: dict) -> dict:
    """Viga de madeira (NP EN 1995-1-1)."""
    from engines.structuro_ec5 import CLASSES, GAMMA_M, KMOD, verify
    cl = p.get("classe") or "C24"
    m = CLASSES[cl]
    L, b, h = float(p["portee_m"]), float(p["b_m"]), float(p["h_m"])
    sc = str(int(p.get("classe_service") or 1))
    duree = p.get("duree_charge") or "medium"
    kmod = KMOD["3" if sc == "3" else "1-2"][duree]
    pp = m["rho_k"] * 1.1 * 9.81e-3 * b * h
    g, q = float(p.get("g_kn_m") or 0) + pp, float(p.get("q_kn_m") or 0)
    pu = 1.35 * g + 1.5 * q
    med, ved = pu * L * L / 8, pu * L / 2
    lef = float(p["lef_m"]) if p.get("lef_m") else None
    r = verify(med, ved, b_m=b, h_m=h, fm_k=m["fm_k"], fv_k=m["fv_k"], E0_05=m["E0_05"], kmod=kmod, gamma_m=GAMMA_M[m["kind"]], kind=m["kind"], lef_m=lef)
    kmod_p = KMOD["3" if sc == "3" else "1-2"]["permanent"]
    rp = verify(1.35 * g * L * L / 8, 1.35 * g * L / 2, b_m=b, h_m=h, fm_k=m["fm_k"], fv_k=m["fv_k"], E0_05=m["E0_05"], kmod=kmod_p,
                gamma_m=GAMMA_M[m["kind"]], kind=m["kind"], lef_m=lef)
    I = b * h ** 3 / 12
    E = m["E0_mean"] * 1e3                                                  # kN/m²
    w = lambda load: 5 * load * L ** 4 / (384 * E * I) * 1000              # mm
    kdef = {"1": 0.6, "2": 0.8, "3": 2.0}[sc]
    psi2 = float(p.get("psi2") if p.get("psi2") is not None else 0.3)
    w_fin = w(g) * (1 + kdef) + w(q) * (1 + psi2 * kdef)
    lim = float(p.get("limite_fleche") or 300)
    ctl = [{"ref": "NP EN 1995-1-1 §6.1.6 flexão", "exigence": "σm,d ≤ kh·fm,d", "valeur": f"{r['bending']['sigma_m_d_mpa']:.1f} / {r['bending']['kh'] * r['bending']['fm_d_mpa']:.1f} MPa",
            "ok": r["bending"]["sigma_m_d_mpa"] <= r["bending"]["kh"] * r["bending"]["fm_d_mpa"] + 1e-9,
            "taux": r["bending"]["sigma_m_d_mpa"] / (r["bending"]["kh"] * r["bending"]["fm_d_mpa"]), "lib": "Flexão"},
           {"ref": "NP EN 1995-1-1 §6.1.7 corte", "exigence": "τd ≤ fv,d", "valeur": f"{r['shear']['tau_d_mpa']:.2f} / {r['shear']['fv_d_mpa']:.2f} MPa",
            "ok": r["shear"]["tau_d_mpa"] <= r["shear"]["fv_d_mpa"] + 1e-9, "taux": r["shear"]["tau_d_mpa"] / r["shear"]["fv_d_mpa"], "lib": "Corte"},
           {"ref": "NP EN 1995-1-1 §7.2 flecha final", "exigence": f"w_fin ≤ L/{lim:g} = {L * 1000 / lim:.1f} mm", "valeur": f"{w_fin:.1f} mm (kdef {kdef:g})",
            "ok": w_fin <= L * 1000 / lim + 1e-9, "taux": w_fin / (L * 1000 / lim), "lib": "Flecha final"}]
    ctl.append({"ref": "NP EN 1995-1-1 flexão sob 1,35 G apenas (kmod permanente)", "exigence": "σm,d ≤ kh·fm,d",
                "valeur": f"{rp['bending']['sigma_m_d_mpa']:.1f} / {rp['bending']['kh'] * rp['bending']['fm_d_mpa']:.1f} MPa (kmod {kmod_p:g})",
                "ok": rp["bending"]["sigma_m_d_mpa"] <= rp["bending"]["kh"] * rp["bending"]["fm_d_mpa"] + 1e-9,
                "taux": rp["bending"]["sigma_m_d_mpa"] / (rp["bending"]["kh"] * rp["bending"]["fm_d_mpa"]), "lib": "Flexão sob 1,35 G (kmod permanente)"})
    if r["lateral_torsional"].get("kcrit") is not None:
        lt = r["lateral_torsional"]
        ctl.append({"ref": "NP EN 1995-1-1 §6.3.3 bambeamento", "exigence": "σm,d ≤ kcrit·fm,d", "valeur": f"kcrit {lt['kcrit']:.2f}",
                    "ok": r["bending"]["sigma_m_d_mpa"] <= lt["kcrit"] * r["bending"]["fm_d_mpa"] + 1e-9,
                    "taux": r["bending"]["sigma_m_d_mpa"] / (lt["kcrit"] * r["bending"]["fm_d_mpa"]), "lib": "Bambeamento"})
    return {"element": f"Viga de madeira {cl}", "section": f"{b * 1000:.0f} × {h * 1000:.0f} mm, vão {L:g} m", "sollicitations": {"g": g, "q": q, "pu": pu, "med": med, "ved": ved},
            "controles": ctl, "details": r, "quantites": {"bois_m3": b * h * L},
            "hypotheses": [f"viga simplesmente apoiada, kmod {kmod:g} (classe de serviço {sc}, duração da carga: {DUREE_PT.get(duree, duree)}), γM {GAMMA_M[m['kind']]:g}",
                           "bambeamento verificado apenas se for indicado o comprimento efetivo lef"]}


def semelle(p: dict) -> dict:
    """Sapata (NP EN 1997-1 anexo D) ou tensão admissível do estudo geotécnico."""
    from engines.structuro_ec7 import bearing
    B, Lg = float(p["b_m"]), float(p.get("l_m") or 1.0)
    filante = not p.get("l_m")
    D = float(p.get("profondeur_m") or 0.5)
    G, Q = float(p.get("g_kn") or 0), float(p.get("q_kn") or 0)       # por m de sapata contínua ou total da sapata isolada
    hs = float(p.get("h_m") or max(0.25, (B - float(p.get("largeur_mur_m") or 0.2)) / 4 + 0.05))
    pp = 25 * B * Lg * hs + 18 * B * Lg * max(0.0, D - hs)
    ned = 1.35 * (G + pp) + 1.5 * Q
    q_ed = ned / (B * Lg)
    ctl, det, hyp = [], {}, []
    if p.get("q_adm_els_kpa"):
        qa = float(p["q_adm_els_kpa"])
        q_els = (G + pp + Q) / (B * Lg)
        ctl.append({"ref": "Tensão admissível (estudo geotécnico)", "exigence": f"q_ELS ≤ {qa:g} kPa", "valeur": f"{q_els:.0f} kPa", "ok": q_els <= qa + 1e-9, "taux": q_els / qa, "lib": "Tensão no terreno / admissível"})
    else:
        mode = "undrained" if p.get("cu_kpa") else "drained"
        det = bearing(mode, B, Lg if not filante else 50.0, q_ed_kpa=q_ed, d_m=D, gamma_soil=float(p.get("gamma_sol") or 18),
                      c_kpa=float(p.get("c_kpa") or 0), phi_deg=float(p.get("phi_deg") or 0), cu_kpa=float(p.get("cu_kpa") or 0))
        if det.get("status") == "missing":
            falta = ["coesão não drenada cu (cu_kpa)"] if mode == "undrained" else (
                ["ângulo de atrito φ' (phi_deg)"] if float(p.get("phi_deg") or 0) <= 0 else []) + (
                ["peso volúmico do solo γ (gamma_sol)"] if float(p.get("gamma_sol") or 18) <= 0 else [])
            raise ValueError("dados do terreno em falta: " + (", ".join(falta) or "parâmetros geotécnicos")
                             + " — ou indicar q_adm_els_kpa do estudo geotécnico")
        ctl.append({"ref": f"NP EN 1997-1 anexo D capacidade resistente ({'não drenada' if mode == 'undrained' else 'drenada'}, γR;v 1,4)",
                    "exigence": f"q_Ed ≤ q_Rd = {det['q_Rd_kpa']:.0f} kPa", "valeur": f"{q_ed:.0f} kPa", "ok": q_ed <= det["q_Rd_kpa"] + 1e-9,
                    "taux": q_ed / det["q_Rd_kpa"] if det["q_Rd_kpa"] else None, "lib": "Capacidade resistente (q_Ed / q_Rd)"})
        hyp.append("carga vertical centrada; assentamentos não calculados (estudo geotécnico indispensável)")
    # armadura transversal pelo método das bielas (sapata contínua / isolada, consola ≥ (B−b)/4)
    bmur = float(p.get("largeur_mur_m") or 0.2)
    d = hs - 0.05
    as_t = ned * (B - bmur) / (8 * d * 500 / 1.15) * 10      # cm² (bielas: Nu·(B−b)/(8·d·fyd)) — por m na contínua, por direção na isolada
    ctl.append({"ref": "Método das bielas — armadura inferior", "exigence": "As ≥ Nu(B − b)/(8·d·fyd)",
                "valeur": f"{as_t:.2f} cm²" + ("/m (transversal)" if filante else " por direção"), "ok": True})
    hyp.append(f"altura da sapata {hs:.2f} m (≥ (B − b)/4 + 5 cm), peso próprio e terras incluídos")
    return {"element": "Sapata " + ("contínua (por metro)" if filante else "isolada"), "section": f"B = {B:g} m" + ("" if filante else f" × L = {Lg:g} m") + f", h = {hs:.2f} m, D = {D:g} m",
            "sollicitations": {"ned": ned, "q_ed": q_ed, "poids_propre": pp}, "controles": ctl, "details": det,
            "quantites": {"beton_m3": B * Lg * hs}, "hypotheses": hyp}


def dalle_ba(p: dict) -> dict:
    """Laje de betão armado armada em duas direções."""
    from engines.structuro_slab2way import design
    lx, ly = float(p["lx_m"]), float(p["ly_m"])
    edges = {k: p.get(k) or "rive" for k in ("x0", "x1", "y0", "y1")}
    if lx > ly:   # lx = menor vão
        lx, ly = ly, lx
        edges = {"x0": edges["y0"], "x1": edges["y1"], "y0": edges["x0"], "y1": edges["x1"]}
    r = design(lx, ly, float(p["h_m"]), float(p.get("g2_kn_m2") or 1.5), float(p.get("q_kn_m2") or 1.5), edges, fck=float(p.get("fck") or 25))

    def _m(v):
        a = v["mesh"].get("as_cm2_m")
        lab = _phi(v["mesh"].get("label"))
        return {"ok": (a is not None and a >= v["as_req_cm2_m"] - 1e-9),
                "lab": f"{lab} ({a:.2f})" if a is not None else "a rever (espessura insuficiente) — varões a calcular"}
    ctl = [{"ref": f"Vão {k} — malha", "exigence": f"As ≥ {v['as_req_cm2_m']:.2f} cm²/m", "valeur": _m(v)["lab"], "ok": _m(v)["ok"]} for k, v in r["span"].items()]
    ctl += [{"ref": f"Apoio {k} ({BORDOS_PT.get(v['type'], v['type'])})", "exigence": f"As ≥ {v['as_req_cm2_m']:.2f} cm²/m em {v['length_from_face_m']:.2f} m", "valeur": _m(v)["lab"],
             "ok": _m(v)["ok"]} for k, v in r["supports"].items() if v["type"] != "libre"]
    sh = r.get("shear") or {}
    if sh:
        ctl.append({"ref": "Esforço transverso (sem armadura específica)", "exigence": f"V_Ed ≤ V_Rd,c = {sh.get('vrdc_kn_m', 0):.0f} kN/m", "valeur": f"{sh.get('v_ed_kn_m', 0):.1f} kN/m",
                    "ok": sh.get("v_ed_kn_m", 0) <= sh.get("vrdc_kn_m", 0), "taux": sh.get("v_ed_kn_m", 0) / sh["vrdc_kn_m"] if sh.get("vrdc_kn_m") else None,
                    "lib": "Esforço transverso"})
    dl = r.get("deflection_ld") or {}
    if "ok" in dl:
        ctl.append({"ref": "Flecha (L/d, EC2 §7.4.2)", "exigence": f"L/d ≤ {dl.get('limit', 0):.1f}", "valeur": f"{dl.get('l_over_d', 0):.1f}", "ok": bool(dl["ok"]),
                    "taux": dl.get("l_over_d", 0) / dl["limit"] if dl.get("limit") else None, "lib": "Flecha (L/d / limite)",
                    "note": None if dl["ok"] else "espessura insuficiente: aumentar h ou calcular a flecha"})
    return {"element": "Laje de BA armada em duas direções", "section": f"{lx:g} × {ly:g} m, h = {float(p['h_m']) * 100:.0f} cm", "sollicitations": r["loads"],
            "controles": ctl, "details": r, "quantites": {"beton_m3": lx * ly * float(p["h_m"])},
            "hypotheses": ["método dos coeficientes μx/μy (tabelas de lajes retangulares) com continuidade simplificada, malhas eletrossoldadas correntes",
                           "designações de malha do motor (ST/PAF) a converter para malhas comerciais equivalentes (ex.: AQ/CQ, aço A500 ER)"]}


def linteau(p: dict) -> dict:
    """Lintel (padieira) sobre vão."""
    from engines.structuro_lintel import lintel_design
    o = {"clear_span_m": float(p["portee_m"]), "wall_thickness_m": float(p.get("epaisseur_mur_m") or 0.2),
         "masonry_height_above_m": float(p.get("hauteur_maconnerie_m") if p.get("hauteur_maconnerie_m") is not None else 10),
         "permanent_line_kn_m": float(p.get("g_kn_m") or 0), "variable_line_kn_m": float(p.get("q_kn_m") or 0), "material": p.get("materiau") or "both"}
    r = lintel_design(o)
    rec = r.get("recommendation") or {}
    mat = {"steel": "aço", "rc": "betão armado"}.get(rec.get("material"), "")
    razao = ("menor custo de material estimado" + (" (empate → aço)" if "æquo" in (rec.get("reason") or "") else "")) if rec else ""
    ctl = [{"ref": "Solução adotada", "exigence": "resistência ELU + flecha ELS", "valeur": f"{rec.get('label', '—')} — {mat}, {razao}" if rec else "—", "ok": bool(rec)}]
    br = r.get("bearing") or {}
    if br:
        ctl.append({"ref": "Apoio na alvenaria (entrega)", "exigence": f"σ ≤ {br.get('allow_kpa', 0):.0f} kPa", "valeur": f"{br.get('sigma_kpa', 0):.0f} kPa em {br.get('bearing_length_m', 0):.2f} m",
                    "ok": br.get("status") != "fails_check",
                    "note": f"entrega necessária {br.get('required_length_m', 0):.2f} m (ou coxim / placa de apoio)" if br.get("status") == "fails_check" else None})
    hyp = [_pt(n, "nota do motor de lintéis (ver detalhes do cálculo)") for n in (r.get("notes") or [])]
    hyp.append("combinação ELU 1,35 G + 1,5 Q; flecha ELS característica e quase-permanente (ψ2); resistência da alvenaria a confirmar")
    return {"element": "Lintel (padieira)", "section": f"vão livre {o['clear_span_m']:g} m, parede {o['wall_thickness_m']:g} m", "sollicitations": r.get("actions", {}),
            "controles": ctl, "details": r, "quantites": {}, "hypotheses": hyp}


_HYP_ESCADA = "regra de Blondel 2h + g = 0,60–0,64 m; requisitos do RGEU e, se aplicável, do DL 163/2006 (acessibilidades) a confirmar pelo projetista"


def escalier(p: dict) -> dict:
    """Escada (stair_engine)."""
    from stair_engine import OptimizeInput, compute_optimize
    kw = {"floor_height_mm": float(p["hauteur_a_monter_mm"]), "available_length_mm": float(p["reculement_mm"]),
          "available_width_mm": float(p.get("largeur_disponible_mm") or p.get("largeur_mm") or 900), "stair_width_mm": float(p.get("largeur_mm") or 900),
          "slab_thickness_mm": float(p.get("epaisseur_dalle_mm") or 200)}
    if p.get("tremie_longueur_mm"):
        kw["stairwell_length_mm"] = float(p["tremie_longueur_mm"])
    opt = compute_optimize(OptimizeInput(**kw, types_to_test=None if p.get("autoriser_tournant", True) else ["straight"])).model_dump(mode="json")
    sols = opt.get("solutions") or []
    # escada reta « compacta »: cobertor reduzido dentro da gama de Blondel (600–640 mm), h ≤ 200 mm, g ≥ 240 mm
    H, Lr = kw["floor_height_mm"], kw["available_length_mm"]
    compact = None
    for n in range(math.ceil(H / 200), math.ceil(H / 150) + 1):
        h = H / n
        g = min(640 - 2 * h, (Lr / (n - 1)) if n > 1 else 9e9, 300)
        if g >= max(240, 600 - 2 * h) and (n - 1) * g <= Lr + 1:
            compact = {"n": n, "h": h, "g": math.floor(g), "run": (n - 1) * math.floor(g), "blondel": 2 * h + math.floor(g)}
            break
    if compact and not any(s_["type"] == "straight" for s_ in sols):
        slope = math.degrees(math.atan(compact["h"] / compact["g"]))
        ctl = [{"ref": "Regra de Blondel (2h + g)", "exigence": "600 a 640 mm", "valeur": f"{compact['blondel']:.0f} mm (h {compact['h']:.0f}, g {compact['g']:.0f})", "ok": True},
               {"ref": "Desenvolvimento em planta", "exigence": f"comprimento disponível ≤ {Lr:.0f} mm", "valeur": f"{compact['run']:.0f} mm", "ok": True},
               {"ref": "Cobertor mínimo / inclinação", "exigence": "g ≥ 240 mm, inclinação ≤ 40°", "valeur": f"{compact['g']:.0f} mm, {slope:.0f}°", "ok": slope <= 40.5}]
        alt = (f"; alternativa de conforto: escada {ESCADA_PT.get(sols[0]['type'], sols[0]['type'])} "
               f"(cobertor {sols[0]['result']['tread_depth_mm']:.0f} mm)") if sols else ""
        return {"element": "Escada reta (compacta)", "section": f"{compact['n']} espelhos de {compact['h']:.0f} mm, {compact['n'] - 1} cobertores de {compact['g']:.0f} mm, inclinação {slope:.0f}°",
                "sollicitations": {}, "controles": ctl, "details": compact, "quantites": {},
                "hypotheses": ["escada reta com cobertor reduzido para caber no comprimento disponível (regra de Blondel respeitada)" + alt,
                               "altura livre sob a abertura da laje e comprimento da abertura (caixa de escada) a verificar; " + _HYP_ESCADA]}
    if not sols:
        # nenhuma solução construível: nota honesta (não conforme) com o comprimento necessário, em vez de um erro
        motivos = [f"{ESCADA_PT.get(e.get('type'), e.get('type'))} ({_variante(e.get('variant'))}) — {_pt(e.get('reason'), 'não construível')}"
                   for e in (opt.get("excluded") or [])[:4]]
        n_ok = next((n for n in range(math.ceil(H / 180), math.ceil(H / 150) + 1) if 600 <= 2 * H / n + max(250, 630 - 2 * H / n) <= 640), math.ceil(H / 175))
        h_ok = H / n_ok
        g_ok = max(250, min(300, 630 - 2 * h_ok))
        L_ok = (n_ok - 1) * g_ok
        ctl = [{"ref": "Desenvolvimento em planta", "exigence": f"comprimento disponível ≤ {Lr:.0f} mm",
                "valeur": f"nenhuma escada construível; escada reta confortável precisa de ≈ {L_ok:.0f} mm", "ok": False,
                "note": "aumentar o comprimento disponível, prever uma escada de um quarto / meia volta com patamar ou rever a altura a vencer"},
               {"ref": "Regra de Blondel (2h + g)", "exigence": "600 a 640 mm", "valeur": f"referência: {n_ok} espelhos de {h_ok:.0f} mm, cobertor {g_ok:.0f} mm",
                "ok": None}]
        return {"element": "Escada (não construível no espaço disponível)",
                "section": f"altura a vencer {H:.0f} mm, comprimento disponível {Lr:.0f} mm, largura {kw['stair_width_mm']:.0f} mm",
                "sollicitations": {}, "controles": ctl, "details": {"excluidas": motivos, "comprimento_necessario_mm": L_ok}, "quantites": {},
                "hypotheses": ["soluções testadas pelo otimizador e excluídas: " + ("; ".join(motivos) or "nenhuma geometria possível"), _HYP_ESCADA]}
    best = next((s_ for s_ in sols if s_["type"] == "straight" and s_["result"]["stair_run_mm"] <= kw["available_length_mm"] + 1), sols[0])
    r = best["result"]
    ctl = [{"ref": "Regra de Blondel (2h + g)", "exigence": "600 a 640 mm (conforto 630)", "valeur": f"{r['blondel_value_mm']:.0f} mm (h {r['riser_height_mm']:.0f}, g {r['tread_depth_mm']:.0f})",
            "ok": 600 <= r["blondel_value_mm"] <= 640},
           {"ref": "Desenvolvimento em planta", "exigence": f"comprimento disponível ≤ {kw['available_length_mm']:.0f} mm", "valeur": f"{r['stair_run_mm']:.0f} mm",
            "ok": r["stair_run_mm"] <= kw["available_length_mm"] + 1},
           {"ref": "Construtibilidade (motor de escadas)", "exigence": "nenhum alerta bloqueante", "valeur": "construível" if r["is_buildable"] else "não construível",
            "ok": bool(r["is_buildable"])}]
    hyp = [f"{NIVEL_PT.get(a.get('level'), a.get('level', ''))}: {_pt(a.get('message'), 'alerta ' + str(a.get('code', '')) + ' do motor de escadas')}"
           for a in r.get("alerts", [])]
    hyp.append(f"solução adotada entre {len(sols)} proposta(s) pelo otimizador: escada {ESCADA_PT.get(best['type'], best['type'])} / "
               f"{_variante(best['variant'])} (pontuação {best['score_global']:.0f})")
    hyp.append("limites geométricos internos do motor de escadas (regras de boa prática); " + _HYP_ESCADA)
    return {"element": "Escada " + ESCADA_PT.get(best["type"], best["type"].replace("_", " ")),
            "section": f"{r['num_steps']} espelhos de {r['riser_height_mm']:.0f} mm, {r['num_treads']} cobertores de {r['tread_depth_mm']:.0f} mm, inclinação {r['slope_deg']:.0f}°",
            "sollicitations": {}, "controles": ctl, "details": r, "quantites": {}, "hypotheses": hyp}


# ---------------------------------------------------------------------------------------------------------------------------------
# Pilar de BA (NP EN 1992-1-1 §5.8 curvatura nominal, §6.1 flexão composta) e punçoamento (§6.4)
ES = 200000.0


def _nm_capacite(b, h, dp, As_face, fcd, fyd, N):
    """Momento resistente (kN·m) de uma secção retangular com armadura simétrica sob o esforço normal N (kN, compressão > 0)."""
    eps_cu = 3.5e-3
    d = h - dp

    def efforts(x):
        a = min(0.8 * x, h)
        Nc = a * b * fcd * 1000                                  # kN (dimensões em m, fcd em MPa)
        e1 = eps_cu * (x - dp) / x                              # armadura do lado comprimido
        e2 = eps_cu * (x - d) / x                               # armadura oposta (negativo = tração)
        s1 = max(-fyd, min(fyd, ES * e1))
        s2 = max(-fyd, min(fyd, ES * e2))
        F1, F2 = As_face * s1 * 1000, As_face * s2 * 1000       # As em m², σ em MPa → kN
        Nint = Nc + F1 + F2
        M = Nc * (h / 2 - a / 2) + F1 * (h / 2 - dp) - F2 * (d - h / 2)
        return Nint, M

    n_max = (b * h * fcd + 2 * As_face * fyd) * 1000
    if N > n_max:
        return None
    lo, hi = 1e-4, 50 * h
    for _ in range(100):
        mid = (lo + hi) / 2
        if efforts(mid)[0] < N:
            lo = mid
        else:
            hi = mid
    return efforts((lo + hi) / 2)[1]


def poteau_ba(p: dict) -> dict:
    """Pilar de betão armado (NP EN 1992-1-1)."""
    b, h = float(p["b_m"]), float(p["h_m"])
    L = float(p.get("hauteur_m") or p.get("portee_m") or 2.7)
    beta = float(p.get("coef_longueur_flambement") or 1.0)
    L0 = beta * L
    N = float(p.get("n_ed_kn") or 0)
    if N <= 0:
        G, Q = float(p.get("g_kn") or 0), float(p.get("q_kn") or 0)
        N = 1.35 * G + 1.5 * Q
    if N <= 0:
        raise ValueError("pilar: esforço normal N_Ed (ou cargas G e Q) obrigatório")
    m01, m02 = sorted([abs(float(p.get("m1_knm") or 0)), abs(float(p.get("m2_knm") or 0))])
    fck, fyk = float(p.get("fck") or 25), float(p.get("fyk") or 500)
    fcd, fyd = fck / 1.5, fyk / 1.15
    c = float(p.get("enrobage_mm") or 30) / 1000
    dp = c + 0.008 + 0.008
    d = h - dp
    Ac = b * h
    n = N / (Ac * fcd * 1000)
    i = h / math.sqrt(12)
    lam = L0 / i
    phi_ef = float(p.get("fluage_phi_ef") if p.get("fluage_phi_ef") is not None else 1.0)
    rm = (m01 / m02) if m02 else 1.0
    C = 1.7 - rm if m02 else 0.7
    A_ = 1 / (1 + 0.2 * phi_ef)
    lam_lim = 20 * A_ * 1.1 * C / math.sqrt(n)
    ei = L0 / 400
    e0 = max(h / 30, 0.02)
    M0 = max(m02 + N * ei, N * e0)
    hyp = [f"comprimento de encurvadura L0 = {beta:g} × {L:g} m; imperfeição ei = L0/400; excentricidade mínima max(h/30; 20 mm)",
           f"esbelteza limite λlim = 20·A·B·C/√n (A = 1/(1+0,2φef), B = 1,1, C = 1,7 − rm), φef = {phi_ef:g}",
           "γc = 1,5 e γs = 1,15 (valores recomendados, a confirmar com o Anexo Nacional português)"]
    # armadura: As total crescente até M_Rd(N) ≥ M_Ed (curvatura nominal recalculada com ω)
    as_min = max(0.10 * N / (fyd * 1000), 0.002 * Ac)
    as_max = 0.04 * Ac
    As = as_min
    res = None
    for _ in range(400):
        M2 = 0.0
        if lam > lam_lim:
            omega = As * fyd / (Ac * fcd)
            nu = 1 + omega
            Kr = min(1.0, (nu - n) / (nu - 0.4)) if nu > 0.4 else 1.0
            Kr = max(0.0, Kr)
            beta_c = 0.35 + fck / 200 - lam / 150
            Kphi = max(1.0, 1 + beta_c * phi_ef)
            inv_r = Kr * Kphi * (fyd / ES) / (0.45 * d)
            e2 = inv_r * L0 ** 2 / 10
            M2 = N * e2
        MEd = M0 + M2
        MRd = _nm_capacite(b, h, dp, As / 2, fcd, fyd, N)
        if MRd is not None and MRd >= MEd:
            res = (As, MEd, M2, MRd)
            break
        As *= 1.03
        if As > as_max:
            break
    ctl = [{"ref": "NP EN 1992-1-1 §5.8.3.1 esbelteza", "exigence": f"λ ≤ λlim = {lam_lim:.1f} (caso contrário, efeitos de segunda ordem)", "valeur": f"λ = {lam:.1f}", "ok": True,
            "note": "segunda ordem considerada (curvatura nominal §5.8.8)" if lam > lam_lim else None}]
    if lam > 90:
        ctl.append({"ref": "Esbelteza", "exigence": "λ ≤ 90 recomendado para o método simplificado", "valeur": f"{lam:.0f}", "ok": None, "note": "análise de segunda ordem detalhada"})
    if res is None:
        ctl.append({"ref": "NP EN 1992-1-1 §6.1 flexão composta", "exigence": f"As ≤ 4 % Ac ({as_max * 1e4:.0f} cm²)", "valeur": "secção insuficiente", "ok": False,
                    "note": "aumentar a secção ou a classe do betão"})
        return {"element": "Pilar de betão armado", "section": f"{b * 100:.0f} × {h * 100:.0f} cm, L0 = {L0:.2f} m", "sollicitations": {"ned": N, "m0": M0},
                "controles": ctl, "details": {"lambda": lam, "lambda_lim": lam_lim}, "quantites": {"beton_m3": Ac * L}, "hypotheses": hyp}
    As, MEd, M2, MRd = res
    bars = None
    for nb in (4, 6, 8, 10, 12):
        phi = next((ph for ph in (12, 14, 16, 20, 25, 32) if nb * math.pi * ph * ph / 4 / 1e6 >= As), None)
        if phi:
            bars = {"n": nb, "phi": phi, "as_cm2": nb * math.pi * phi * phi / 400, "label": f"{nb} Ø{phi}"}
            break
    st = min(20 * bars["phi"] / 1000, min(b, h), 0.40)
    phi_t = max(6, math.ceil(bars["phi"] / 4))
    ctl += [{"ref": "NP EN 1992-1-1 §6.1 flexão composta N + M", "exigence": f"M_Rd(N_Ed) ≥ M_Ed = M0 + M2 = {MEd:.1f} kN·m", "valeur": f"{bars['label']} ({bars['as_cm2']:.2f} cm²) → M_Rd ≥ {MRd:.1f} kN·m",
             "ok": True},
            {"ref": "NP EN 1992-1-1 §9.5.2 armadura longitudinal", "exigence": f"As,min = {as_min * 1e4:.2f} cm² ≤ As ≤ 4 % Ac; Ø ≥ 8 mm (12 recomendado)", "valeur": f"{bars['as_cm2']:.2f} cm²",
             "ok": as_min * 1e4 - 1e-9 <= bars["as_cm2"] <= as_max * 1e4},
            {"ref": "NP EN 1992-1-1 §9.5.3 armadura transversal", "exigence": "estribos Ø ≥ max(6; Ø/4), s ≤ min(20 Ø; b; 400 mm)", "valeur": f"estribos Ø{phi_t} s = {st * 100:.0f} cm",
             "ok": True}]
    kg = bars["n"] * (L + 0.6) * math.pi * (bars["phi"] / 1000) ** 2 / 4 * 7850 + (math.ceil(L / st) + 1) * (2 * (b + h) - 8 * c + 0.2) * math.pi * (phi_t / 1000) ** 2 / 4 * 7850
    return {"element": "Pilar de betão armado", "section": f"{b * 100:.0f} × {h * 100:.0f} cm, L0 = {L0:.2f} m, C{fck:g}", "sollicitations": {"ned": N, "m0": M0, "m2": M2, "med": MEd},
            "barres": bars, "etriers": f"estribos Ø{phi_t} s = {st * 100:.0f} cm", "controles": ctl, "details": {"lambda": lam, "lambda_lim": lam_lim, "n": n},
            "quantites": {"beton_m3": Ac * L, "acier_kg": kg, "ratio_kg_m3": kg / (Ac * L)}, "hypotheses": hyp}


def poinconnement(p: dict) -> dict:
    """Punçoamento de laje (NP EN 1992-1-1 §6.4)."""
    d = float(p.get("d_m") or (float(p["h_m"]) - 0.035 if p.get("h_m") else 0))
    if d <= 0:
        raise ValueError("punçoamento: altura útil d_m (ou espessura h_m) obrigatória")
    c1, c2 = float(p.get("c1_m") or p.get("b_m") or 0.3), float(p.get("c2_m") or p.get("c1_m") or p.get("b_m") or 0.3)
    V = float(p.get("v_ed_kn") or 0)
    if V <= 0:
        raise ValueError("punçoamento: esforço V_Ed (kN) obrigatório")
    pos = p.get("position_poteau") or "interieur"
    beta = {"interieur": 1.15, "rive": 1.4, "angle": 1.5}[pos]
    fck = float(p.get("fck") or 25)
    fcd = fck / 1.5
    rho = min(0.02, float(p.get("rho_l") or 0.005))
    k = min(2.0, 1 + math.sqrt(0.2 / d))
    vrdc = max(0.18 / 1.5 * k * (100 * rho * fck) ** (1 / 3), 0.035 * k ** 1.5 * math.sqrt(fck))
    if p.get("poteau_circulaire"):
        u0 = math.pi * c1
        u1 = math.pi * (c1 + 4 * d)
    else:
        u0 = 2 * (c1 + c2)
        u1 = 2 * (c1 + c2) + 4 * math.pi * d
    if pos == "rive":
        u0, u1 = min(c2 + 3 * d, c2 + 2 * c1), c2 + 2 * c1 + math.pi * 2 * d    # perímetros de bordo simplificados (§6.4.2)
    elif pos == "angle":
        u0, u1 = min(3 * d, c1 + c2), c1 + c2 + math.pi * d
    v_ed = beta * V * 1000 / (u1 * d * 1e6)              # MPa
    v0 = beta * V * 1000 / (u0 * d * 1e6)
    nu = 0.6 * (1 - fck / 250)
    vrdmax = 0.4 * nu * fcd
    ctl = [{"ref": "NP EN 1992-1-1 §6.4.5(3) perímetro do pilar u0", "exigence": f"v_Ed,0 ≤ v_Rd,max = {vrdmax:.2f} MPa", "valeur": f"{v0:.2f} MPa", "ok": v0 <= vrdmax,
            "taux": v0 / vrdmax, "lib": "Bielas no pilar (v_Ed,0 / v_Rd,max)",
            "note": "aumentar a espessura da laje / capitel / aumentar o pilar" if v0 > vrdmax else None},
           {"ref": "NP EN 1992-1-1 §6.4.4 perímetro de controlo u1 (2d)", "exigence": f"v_Ed ≤ v_Rd,c = {vrdc:.3f} MPa (caso contrário, armadura de punçoamento)",
            "valeur": f"{v_ed:.3f} MPa (β = {beta:g})", "ok": True if v_ed <= vrdc else None,
            "taux": v_ed / vrdc, "lib": "Perímetro u1 (v_Ed / v_Rd,c)"}]
    det = {"u0_m": u0, "u1_m": u1, "v_ed_mpa": v_ed, "v_rdc_mpa": vrdc, "v_rdmax_mpa": vrdmax, "k": k}
    if v_ed > vrdc:
        if v_ed > 1.5 * vrdc * 1.0 + 1e-9 and v_ed > 2 * vrdc:
            ctl.append({"ref": "Armadura de punçoamento", "exigence": "v_Ed ≤ 2·v_Rd,c (limite prático / Anexo Nacional)", "valeur": f"{v_ed / vrdc:.2f} × v_Rd,c", "ok": False,
                        "note": "laje demasiado fina: aumentar d ou o pilar"})
        else:
            fywd_ef = min(250 + 0.25 * d * 1000, 500 / 1.15)
            sr = 0.75 * d
            asw = (v_ed - 0.75 * vrdc) * u1 * d * 1e6 / (1.5 * (d / sr) * fywd_ef) / 1e6 * 1e4      # cm² por perímetro
            uout = beta * V * 1000 / (vrdc * d * 1e6)
            ctl.append({"ref": "NP EN 1992-1-1 §6.4.5 armadura de punçoamento", "exigence": "v_Rd,cs ≥ v_Ed", "valeur": f"Asw ≥ {asw:.2f} cm² por perímetro, sr ≤ {sr * 100:.0f} cm, "
                        f"perímetro exterior u_out ≈ {uout:.2f} m", "ok": True})
            det.update({"asw_cm2_contour": asw, "sr_m": sr, "u_out_m": uout})
    return {"element": "Punçoamento de laje", "section": f"pilar {c1 * 100:.0f} × {c2 * 100:.0f} cm ({POSICAO_PT.get(pos, pos)}), d = {d * 100:.0f} cm, C{fck:g}", "sollicitations": {"ved": V},
            "controles": ctl, "details": det, "quantites": {},
            "hypotheses": [f"ρl = {rho:g} (armadura superior sobre o pilar, a confirmar); β simplificado {beta:g} (§6.4.3(6)); perímetros de bordo / canto simplificados",
                           "v_Rd,max = 0,4·ν·fcd (EN 1992-1-1/A1:2014); CRd,c = 0,18/γc e vmin recomendados, a confirmar com o Anexo Nacional português"]}


ELEMENTS = {"poutre_ba": poutre_ba, "poteau_ba": poteau_ba, "poinconnement": poinconnement, "poutre_bois": poutre_bois, "semelle": semelle, "dalle_ba": dalle_ba, "linteau": linteau, "escalier": escalier}


def calculer(params: dict) -> dict:
    el = params.get("element")
    if el not in ELEMENTS:
        raise ValueError(f"elemento desconhecido {el!r} ({', '.join(ELEMENTS)})")
    try:
        return ELEMENTS[el](params)
    except KeyError as exc:
        raise ValueError(f"parâmetro em falta para {el}: {exc.args[0]}") from None


def note(params: dict) -> dict:
    r = calculer(params)
    f = notes._f
    blocs = [("p", "Pré-dimensionamento por motor determinístico ConstruPilot — a validar pelo projetista de estruturas antes da execução."),
             ("h2", f"1. {r['element']}"), ("p", r["section"])]
    so = r.get("sollicitations") or {}
    lab = {"g": "G (kN/m)", "q": "Q (kN/m)", "pu": "p ELU (kN/m)", "med": "M_Ed (kN·m)", "ved": "V_Ed (kN)", "ned": "N_Ed (kN)", "q_ed": "q_Ed (kPa)",
           "poids_propre": "peso próprio", "g_kn_m2": "G (kN/m²)", "ps": "p ELS (kN/m²)", "pqp": "p quase-permanente (kN/m²)",
           "m0": "M0 (kN·m)", "m2": "M2 2.ª ordem (kN·m)", "m_g_knm": "M_G (kN·m)", "m_q_knm": "M_Q (kN·m)", "v_g_kn": "V_G (kN)", "v_q_kn": "V_Q (kN)",
           "m_ed_knm": "M_Ed (kN·m)", "v_ed_kn": "V_Ed (kN)", "m_char_knm": "M característico (kN·m)"}
    rows = [[lab.get(k, k), f(v, 2)] for k, v in so.items() if isinstance(v, (int, float))]
    if rows:
        blocs.append(("table", ["Grandeza", "Valor"], rows, [60 * notes.W, 50 * notes.W]))
    if r.get("barres"):
        blocs.append(("p", f"Armadura longitudinal: {r['barres']['label']} ({r['barres']['as_cm2']:.2f} cm²) · {r['etriers']}"))
    tx = [(c.get("lib") or c["ref"], c["taux"], None) for c in r["controles"] if c.get("taux") is not None]
    if tx:
        blocs.append(("chart", notes.G.jauges(tx, "Taxa de trabalho das verificações"),
                      "Taxa = esforço atuante / resistência (ou valor / limite): 100 % = limite atingido."))
    blocs.append(("controls", r["controles"]))
    q = r.get("quantites") or {}
    if q:
        blocs.append(("p", "Quantidades: " + " · ".join(f"{QUANT_PT.get(k, k.replace('_', ' '))} {f(v, 2)}" for k, v in q.items())))
    kp = [{"label": "Elemento", "value": r["element"].split(" — ")[0][:28]}]
    if tx:
        tmax = max(t for _, t, _ in tx)
        kp.append({"label": "Taxa de trabalho máxima", "value": f"{tmax * 100:.0f}", "unit": "%", "ok": tmax <= 1.0 + 1e-9})
    if r.get("barres"):
        kp.append({"label": "Armadura longitudinal", "value": r["barres"]["label"]})
    if q.get("acier_kg"):
        kp.append({"label": "Aço", "value": f"{q['acier_kg']:.0f}", "unit": "kg"})
    elif q.get("beton_m3"):
        kp.append({"label": "Betão", "value": f(q["beton_m3"], 2), "unit": "m³"})
    blocs = [("kpis", kp)] + blocs
    pdf, png = notes.pdf(f"Nota de pré-dimensionamento — {r['element']}", r["section"], blocs, r.get("hypotheses"))
    return {**r, "titre": f"Pré-dimensionamento — {r['element']}", "pdf": pdf, "png": png}
