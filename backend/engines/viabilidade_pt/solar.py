"""Sol, horizonte e sombreamento sobre o MDT (e os edifícios vizinhos, quando há altura conhecida).

- posição do sol: equações da NOAA simplificadas (declinação de Cooper, equação do tempo de Spencer), erro < 0,5°;
- horizonte de cada célula: ângulo máximo do relevo (e dos obstáculos) em 36 direções, até 600 m;
- irradiação: céu limpo (Meinel) + difusa isotrópica × fator de céu visível, corrigida por uma fração média de céu
  limpo mensal típica de Portugal continental (mais nublado a norte). É um valor INDICATIVO para comparar zonas do
  terreno e orientações; para dimensionar painéis usar o PVGIS (Comissão Europeia) ou dados climáticos do LNEG.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from engines.mdt_pt.analise import _preencher_nan, amostrar
from engines.mdt_pt.geotiff import Raster

N_AZ = 36                                   # direções do horizonte (10°)
DIAS_MES = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
DIA_TIPICO = (17, 47, 75, 105, 135, 162, 198, 228, 258, 288, 318, 344)      # dias médios de Klein
# fração média de céu limpo (irradiação global média / céu limpo), Portugal continental — sul / norte do Tejo-Mondego
_KC_SUL = (0.71, 0.76, 0.80, 0.83, 0.87, 0.94, 0.96, 0.96, 0.92, 0.80, 0.71, 0.67)
_KC_NORTE = (0.60, 0.66, 0.72, 0.75, 0.80, 0.88, 0.92, 0.92, 0.85, 0.71, 0.61, 0.58)
FONTE = ("Cálculo ConstruPilot: posição solar (NOAA), horizonte sobre o MDT da envolvente analisada (~120 m) e os edifícios "
         "vizinhos com altura conhecida, céu limpo de Meinel corrigido por "
         "nebulosidade média de Portugal continental — indicativo (confirmar com PVGIS para sistemas solares).")
RUMOS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]


def rumo(az: Optional[float]) -> str:
    if az is None:
        return "—"
    return RUMOS[int(((az % 360) + 11.25) // 22.5) % 16]


# ------------------------------------------------------------------ posição do sol
def posicao(lat: float, lon: float, dia: int, hora_utc) -> Tuple[np.ndarray, np.ndarray]:
    """(azimute°, altura°) do sol; azimute a partir do norte, sentido horário. hora_utc pode ser vetor."""
    h = np.asarray(hora_utc, dtype=float)
    g = 2 * math.pi / 365.0 * (dia - 1 + (h - 12) / 24.0)
    eqt = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g) - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    dec = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g) + 0.000907 * np.sin(2 * g)
           - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    t_solar = h * 60.0 + eqt + 4.0 * lon                       # minutos
    ha = np.radians(t_solar / 4.0 - 180.0)
    phi = math.radians(lat)
    cz = np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(ha)
    zen = np.arccos(np.clip(cz, -1, 1))
    alt = 90.0 - np.degrees(zen)
    az = (np.degrees(np.arctan2(np.sin(ha), np.cos(ha) * np.sin(phi) - np.tan(dec) * np.cos(phi))) + 180.0) % 360.0
    return az, alt


def trajetorias(lat: float, lon: float) -> List[Dict[str, Any]]:
    """Trajetória do sol nos solstícios e no equinócio (para o diagrama solar)."""
    out = []
    for nome, dia in (("21 de junho", 172), ("21 de março / 23 de setembro", 80), ("21 de dezembro", 355)):
        hs = np.arange(4.0, 21.01, 0.25)
        az, alt = posicao(lat, lon, dia, hs)
        m = alt > 0
        out.append({"dia": nome, "pontos": [{"hora_utc": round(float(a), 2), "azimute": round(float(b), 1),
                                              "altura": round(float(c), 1)} for a, b, c in zip(hs[m], az[m], alt[m])],
                    "altura_max": round(float(alt.max()), 1)})
    return out


# ------------------------------------------------------------------ superfície com obstáculos
def superficie(r: Raster, edificios: Optional[Sequence[Dict[str, Any]]] = None) -> Raster:
    """MDT + edifícios vizinhos com altura conhecida (só para o cálculo de sombras)."""
    if not edificios:
        return r
    from matplotlib.path import Path
    from engines.mdt_pt import pttm06 as TM
    from engines.mdt_pt.analise import centros
    z = r.z.copy()
    xc, yc = centros(r)
    X, Y = np.meshgrid(xc, yc)
    P = np.c_[X.ravel(), Y.ravel()]
    for e in edificios:
        h = e.get("altura_m")
        ll = e.get("latlon") or []
        if not h or h <= 0 or len(ll) < 3:
            continue
        x, y = TM.para_tm(np.array([p[0] for p in ll]), np.array([p[1] for p in ll]))
        if x.max() < xc[0] or x.min() > xc[-1] or y.max() < yc[-1] or y.min() > yc[0]:
            continue
        m = Path(np.c_[x, y]).contains_points(P).reshape(z.shape)
        if m.any():
            base = np.nanmin(np.where(m, r.z, np.nan))
            z[m] = np.maximum(z[m], base + float(h))
    return Raster(z, r.x0, r.y0, r.px, r.py)


# ------------------------------------------------------------------ horizonte
def horizonte(r: Raster, alvo: Optional[np.ndarray] = None, dist_max: float = 600.0) -> np.ndarray:
    """Ângulo do horizonte (graus) em N_AZ direções para as células `alvo` (máscara) → [N_AZ, n_células]."""
    ny, nx = r.z.shape
    z = _preencher_nan(r.z.astype(np.float64))
    rr = Raster(z.astype(np.float32), r.x0, r.y0, r.px, r.py)
    if alvo is None:
        alvo = np.ones(z.shape, dtype=bool)
    I, J = np.nonzero(alvo)
    x = r.x0 + (J + 0.5) * r.px
    y = r.y0 - (I + 0.5) * r.py
    z0 = z[I, J] + 1.5                                     # olhos / janela a 1,5 m do chão
    lado = max(nx * r.px, ny * r.py)
    dmax = min(dist_max, lado)
    passos = []
    d = max(r.px, 1.0)
    while d <= dmax:
        passos.append(d)
        d = d * 1.18 + r.px * 0.5
    out = np.zeros((N_AZ, I.size), dtype=np.float32)
    for k in range(N_AZ):
        a = math.radians(k * 360.0 / N_AZ)
        sx, sy = math.sin(a), math.cos(a)
        best = np.full(I.size, -90.0)
        for d in passos:
            zz = amostrar(rr, x + sx * d, y + sy * d)
            ang = np.degrees(np.arctan2(zz - z0, d))
            best = np.where(np.isnan(ang), best, np.maximum(best, ang))
        out[k] = np.clip(best, 0, 90)
    return out


def _svf(h: np.ndarray) -> np.ndarray:
    """Fator de céu visível aproximado a partir do horizonte (média de cos² do ângulo de horizonte)."""
    return np.cos(np.radians(h)) ** 2


# ------------------------------------------------------------------ irradiação
def _ceu_limpo(alt: float) -> Tuple[float, float]:
    """(normal direta, difusa horizontal) W/m² em céu limpo para a altura do sol (graus)."""
    if alt <= 0:
        return 0.0, 0.0
    am = 1.0 / (math.sin(math.radians(alt)) + 0.50572 * (alt + 6.07995) ** -1.6364)
    dni = 1353.0 * 0.7 ** (am ** 0.678)
    return dni, 0.1 * dni


def analisar(r: Raster, mascara: np.ndarray, decl_pct: np.ndarray, expo: np.ndarray, lat: float, lon: float,
             obstaculos: Optional[Raster] = None, passo_h: float = 0.5) -> Dict[str, Any]:
    """Irradiação anual por célula do terreno, horas de sol nos solstícios e horizonte no centro."""
    sup = obstaculos or r
    H = horizonte(sup, mascara)                                  # [36, n]
    I, J = np.nonzero(mascara)
    s = np.arctan(np.nan_to_num(decl_pct[I, J]) / 100.0)
    asp = np.radians(np.nan_to_num(expo[I, J]))
    svf = _svf(H).mean(axis=0)
    kc = _KC_NORTE if lat >= 40.0 else _KC_SUL
    anual = np.zeros(I.size)
    anual_h_livre = 0.0                                          # horizontal sem obstáculos (referência)
    horas_dez = np.zeros(I.size)
    horas_jun = np.zeros(I.size)
    mensal = []
    for m in range(12):
        dia = DIA_TIPICO[m]
        hs = np.arange(4.0, 21.0, passo_h)
        az, alt = posicao(lat, lon, dia, hs)
        tot = np.zeros(I.size)
        ref = 0.0
        for a, b in zip(az, alt):
            if b <= 0:
                continue
            dni, dhi = _ceu_limpo(float(b))
            k = int(round(a / (360.0 / N_AZ))) % N_AZ
            ao_sol = b > H[k]
            ar, br = math.radians(a), math.radians(b)
            cosi = np.sin(br) * np.cos(s) + np.cos(br) * np.sin(s) * np.cos(ar - asp)
            dirc = np.where(ao_sol, dni * np.clip(cosi, 0, None), 0.0)
            dif = dhi * svf * (1 + np.cos(s)) / 2
            tot += (dirc + dif) * passo_h
            ref += (dni * math.sin(br) + dhi) * passo_h
        f = kc[m] * DIAS_MES[m] / 1000.0                          # Wh/m²/dia → kWh/m²/mês
        anual += tot * f
        anual_h_livre += ref * f
        mensal.append({"mes": m + 1, "media_kwh_m2": round(float((tot * f).mean()), 1), "horizontal_livre_kwh_m2": round(ref * f, 1)})
    for dia, acc in ((355, horas_dez), (172, horas_jun)):
        hs = np.arange(4.0, 21.0, 0.25)
        az, alt = posicao(lat, lon, dia, hs)
        for a, b in zip(az, alt):
            if b <= 0:
                continue
            k = int(round(a / (360.0 / N_AZ))) % N_AZ
            acc += (b > H[k]) * 0.25
    # centro (célula da máscara mais próxima do centroide)
    ci, cj = I.mean(), J.mean()
    c = int(np.argmin((I - ci) ** 2 + (J - cj) ** 2))
    mapa = np.full(r.z.shape, np.nan, dtype=np.float32)
    mapa[I, J] = anual
    sombra_dez = np.full(r.z.shape, np.nan, dtype=np.float32)
    sombra_dez[I, J] = horas_dez
    _, alt_dez = posicao(lat, lon, 355, np.arange(4.0, 21.0, 0.25))
    dur_dez = float((alt_dez > 0).sum() * 0.25)
    rel = anual / max(anual_h_livre, 1e-6)
    return {
        "ok": True, "fonte": FONTE,
        "irradiacao_anual_kwh_m2": {"min": round(float(anual.min()), 0), "media": round(float(anual.mean()), 0),
                                    "max": round(float(anual.max()), 0)},
        "referencia_horizontal_livre_kwh_m2": round(anual_h_livre, 0),
        "indice_solar_pct": round(float(rel.mean() * 100), 0),
        "fracao_bem_exposta": round(float((rel >= 0.95).mean()), 3),
        "horas_sol_21dez": {"media": round(float(horas_dez.mean()), 1), "min": round(float(horas_dez.min()), 1),
                            "max": round(float(horas_dez.max()), 1), "duracao_dia": round(dur_dez, 1)},
        "horas_sol_21jun": {"media": round(float(horas_jun.mean()), 1), "min": round(float(horas_jun.min()), 1),
                            "max": round(float(horas_jun.max()), 1)},
        "fracao_sombra_inverno": round(float((horas_dez < 0.5 * dur_dez).mean()), 3),
        "horizonte_centro": [{"azimute": round(k * 360.0 / N_AZ, 0), "angulo": round(float(H[k, c]), 1)} for k in range(N_AZ)],
        "horizonte_sul_graus": round(float(H[[15, 16, 17, 18, 19, 20, 21], :].mean()), 1),
        "ceu_visivel": round(float(svf.mean()), 3),
        "mensal": mensal, "trajetorias": trajetorias(lat, lon),
        "_mapa_anual": mapa, "_horas_dez": sombra_dez,
    }
