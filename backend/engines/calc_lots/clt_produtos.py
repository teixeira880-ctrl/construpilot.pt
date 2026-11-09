"""Biblioteca de produtos CLT com Avaliação Técnica Europeia (ETA) — valores declarados, nunca inventados.

REZULT CLT — ETA-21/0914 de 2021-11-25 (ETA-Danmark A/S, EAD 130005-00-0304), fabricante Ukrainian Sawmill Holding
Company ltd, Kyiv (www.rezult.pro). Valores do Anexo 2 (dimensões), Anexo 3 quadro 2 e figura 3 (resistências e
rigidezes), §3.2 (fogo). Elementos 60-360 mm, 3 a 9 camadas, tábuas 20-43 mm × 105-204 mm, classes de serviço 1 e 2.
"""
from __future__ import annotations

import math

PRODUTOS = {
    "rezult_clt": {
        "nome": "Rezult CLT", "eta": "ETA-21/0914 (2021-11-25, ETA-Danmark, EAD 130005-00-0304)",
        "fabricante": "Ukrainian Sawmill Holding Company ltd, Kyiv (UA)",
        "classe": "C24/T14", "E0_mean": 12000.0, "G0_mean": 690.0, "G_R": 50.0,            # MPa (G0 de EN 338 C24; G9090 da ETA)
        "fm_k": 24.0, "ft0_k": 19.0, "fc0_k": 24.0, "fc90_k": 3.0, "fv_k": 4.0,               # MPa (quadro 2, C24/T14)
        "fv_net_k": 8.0, "fv_tor_k": 2.5,
        "rho_k": {"pinho": 420.0, "outras": 350.0},                                            # kg/m³ C24 (Pinus sylvestris / outras)
        "beta_0": 0.65, "beta_n": 0.70,                                                        # mm/min (§3.2)
        "reacao_fogo": "D-s2,d0 (pavimentos Dfl-s1)",
        "espessura_mm": (60, 360), "camadas": (3, 9), "tabua_t_mm": (20, 43), "tabua_b_mm": (105, 204),
        "largura_max_m": 3.5, "comprimento_max_m": 18.0, "classes_servico": (1, 2),
    },
    "generico_c24": {
        "nome": "CLT C24 (valores típicos)", "eta": "valores típicos EN 338 / EN 16351 — substituir pela ETA do fabricante",
        "fabricante": "—", "classe": "C24", "E0_mean": 11000.0, "G0_mean": 690.0, "G_R": 50.0,
        "fm_k": 24.0, "ft0_k": 14.5, "fc0_k": 21.0, "fc90_k": 2.5, "fv_k": 4.0, "fv_net_k": None, "fv_tor_k": None,
        "rho_k": {"pinho": 350.0, "outras": 350.0}, "beta_0": 0.65, "beta_n": 0.80, "reacao_fogo": "D-s2,d0",
        "espessura_mm": (60, 400), "camadas": (3, 11), "tabua_t_mm": (19, 45), "tabua_b_mm": (80, 240),
        "largura_max_m": 3.5, "comprimento_max_m": 20.0, "classes_servico": (1, 2),
    },
}


def produto(chave: str | None) -> dict:
    k = (chave or "generico_c24").lower().replace(" ", "_").replace("-", "_")
    if k in ("rezult", "rezult_clt", "eta_21_0914"):
        k = "rezult_clt"
    if k not in PRODUTOS:
        raise ValueError(f"produto CLT {chave!r} desconhecido ({', '.join(PRODUTOS)})")
    return dict(PRODUTOS[k], chave=k)


def fr_k(p: dict, t_cruzada_mm: float, especie: str | None) -> float:
    """Resistência ao corte de rolamento (ETA-21/0914 fig. 3): pinho 1,8 − 0,02·(t − 20) N/mm² (1,34 ≤ fR,k ≤ 1,8);
    outras resinosas 1,1 N/mm². Produto genérico: 1,1 N/mm²."""
    if p["chave"] == "rezult_clt" and (especie or "").lower() in ("pinho", "pine", "pinus", "pinus sylvestris", "сосна"):
        t = min(max(float(t_cruzada_mm), 20.0), 43.0)
        return round(1.8 - 0.02 * (t - 20.0), 4)
    return 1.1


def k_sys(n_tabuas: int) -> float:
    """Fator de sistema (ETA anexo 3): k_sys = min(0,975 + 0,025·n ; 1,2), n = tábuas na camada longitudinal exterior."""
    return min(0.975 + 0.025 * max(int(n_tabuas), 1), 1.2)


def validar_camadas(p: dict, camadas_mm) -> list[str]:
    """Avisos se a composição sair do âmbito da ETA (Anexo 2)."""
    av = []
    H = sum(camadas_mm)
    if not p["espessura_mm"][0] <= H <= p["espessura_mm"][1]:
        av.append(f"espessura {H:g} mm fora do âmbito {p['espessura_mm'][0]}-{p['espessura_mm'][1]} mm de {p['eta']}")
    if not p["camadas"][0] <= len(camadas_mm) <= p["camadas"][1]:
        av.append(f"{len(camadas_mm)} camadas fora do âmbito {p['camadas'][0]}-{p['camadas'][1]}")
    fora = [c for c in camadas_mm if not p["tabua_t_mm"][0] <= c <= p["tabua_t_mm"][1]]
    if fora:
        av.append(f"camadas {fora} mm fora das tábuas {p['tabua_t_mm'][0]}-{p['tabua_t_mm'][1]} mm")
    return av


def carbonizacao(camadas_mm, minutos: float, beta: float, d0_mm: float = 7.0) -> dict:
    """Profundidade carbonizada pela face exposta (camada 1 = face exposta), modelo bilinear EN 1995-1-2 §3.4.3 como pede a
    ETA: cada lamela exposta protege a seguinte; após a sua queda a seguinte carboniza a 2·β até 25 mm, depois a β.
    → {"d_char", "d_ef" (= d_char + d0, §4.2.2), "camadas_perdidas"}."""
    t_rest, d, prim = float(minutos), 0.0, True
    for i, ti in enumerate(camadas_mm):
        ti = float(ti)
        if prim:
            tempo = ti / beta
            if t_rest <= tempo:
                d += beta * t_rest
                t_rest = 0
                break
            d += ti
            t_rest -= tempo
            prim = False
            continue
        a = min(25.0, ti)
        tempo_a = a / (2 * beta)
        if t_rest <= tempo_a:
            d += 2 * beta * t_rest
            t_rest = 0
            break
        d += a
        t_rest -= tempo_a
        b = ti - a
        if b > 0:
            tempo_b = b / beta
            if t_rest <= tempo_b:
                d += beta * t_rest
                t_rest = 0
                break
            d += b
            t_rest -= tempo_b
    if t_rest > 0:
        d = float(sum(camadas_mm))
    return {"d_char": d, "d_ef": d + d0_mm, "camadas_perdidas": sum(1 for k in range(len(camadas_mm)) if sum(camadas_mm[:k + 1]) <= d + d0_mm)}


def seccao_residual(camadas_mm, d_ef_mm: float):
    """Camadas que restam após retirar d_ef pela face exposta (camada 1). Devolve [(t_mm, longitudinal?)] do topo para a face exposta."""
    res, z = [], 0.0
    for i, ti in enumerate(camadas_mm):
        top, bot = z, z + ti
        z = bot
        keep = max(0.0, min(bot, sum(camadas_mm)) - max(top, d_ef_mm))
        if keep > 1e-6:
            res.append((keep, i % 2 == 0))
    return list(reversed(res))


def flexao_seccao(partes, E=1.0):
    """partes = [(t_mm, longitudinal)] de cima para baixo → (I m⁴/m, z_max m) só com as camadas longitudinais."""
    z, zc = 0.0, []
    for t, lon in partes:
        zc.append((z + t / 2, t, lon))
        z += t
    lon = [(c, t) for c, t, lg in zc if lg]
    if not lon:
        return 0.0, 1.0
    zs = sum(c * t for c, t in lon) / sum(t for c, t in lon)
    I = sum(t ** 3 / 12 + t * (c - zs) ** 2 for c, t in lon) * 1e-12 * 1000   # mm⁴/mm → m⁴/m
    zmax = max(abs(zs - (c - t / 2)) for c, t in lon) if lon else 0
    zmax = max(zmax, max(abs((c + t / 2) - zs) for c, t in lon)) / 1000
    return I, zmax


def fogo_painel(p: dict, camadas_mm, vao_m: float, g_kpa: float, q_kpa: float, psi_fi: float, minutos: float,
                n_tabuas: int, kfi: float = 1.15) -> dict:
    """R (capacidade resistente) ao fogo de um painel simplesmente apoiado exposto por baixo: secção residual
    (bilinear ETA / EN 1995-1-2 §3.4.3 + d0 7 mm, §4.2.2), f_d,fi = k_fi·k_sys·f_m,k (k_mod,fi = γM,fi = 1),
    E_d,fi = (G + ψ_fi·Q)·L²/8. Integridade / isolamento (E, I), ligações e juntas não verificados."""
    cam = list(camadas_mm)
    ch = carbonizacao(cam, minutos, p["beta_0"])
    partes = seccao_residual(cam, ch["d_ef"])
    I, zmax = flexao_seccao(partes)
    f_fi = kfi * k_sys(n_tabuas) * p["fm_k"] * 1e3
    M_rd = f_fi * I / zmax if I > 0 else 0.0
    M_ed = (g_kpa + psi_fi * q_kpa) * vao_m ** 2 / 8
    tx = M_ed / M_rd if M_rd > 0 else math.inf
    return {"minutos": minutos, "d_char": ch["d_char"], "d_ef": ch["d_ef"], "M_ed": M_ed, "M_rd": M_rd, "taxa": tx, "ok": tx <= 1 + 1e-9,
            "residual_mm": sum(t for t, _ in partes)}
