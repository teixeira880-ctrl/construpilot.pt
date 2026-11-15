"""Conforto térmico e sustentabilidade do lugar: exposição solar, sombreamento, ventilação natural, orientação
mais favorável e potencial de sobreaquecimento — sobre o horizonte real do terreno (MDT + edifícios vizinhos).

Indicadores de anteprojeto, não substituem o estudo de comportamento térmico (REH / SCE).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from . import solar as S

FACHADAS = {"N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0, "S": 180.0, "SO": 225.0, "O": 270.0, "NO": 315.0}
VERAO = (6, 7, 8)          # junho–agosto
INVERNO = (12, 1, 2)       # dezembro–fevereiro


def irradiacao_fachadas(lat: float, lon: float, horizonte: List[float]) -> Dict[str, Dict[str, float]]:
    """kWh/m² recebidos por uma fachada vertical em cada orientação, no verão e no inverno (com o horizonte do local)."""
    H = np.asarray(horizonte, dtype=float)
    kc = S._KC_NORTE if lat >= 40.0 else S._KC_SUL
    out = {k: {"verao_kwh_m2": 0.0, "inverno_kwh_m2": 0.0} for k in FACHADAS}
    for m in range(1, 13):
        est = "verao_kwh_m2" if m in VERAO else "inverno_kwh_m2" if m in INVERNO else None
        if not est:
            continue
        hs = np.arange(4.0, 21.0, 0.5)
        az, alt = S.posicao(lat, lon, S.DIA_TIPICO[m - 1], hs)
        f = kc[m - 1] * S.DIAS_MES[m - 1] / 1000.0
        for a, b in zip(az, alt):
            if b <= 0:
                continue
            dni, dhi = S._ceu_limpo(float(b))
            k = int(round(a / 10.0)) % 36
            sol = b > H[k]
            for nome, n in FACHADAS.items():
                cosi = math.cos(math.radians(b)) * math.cos(math.radians(a - n))
                d = dni * max(cosi, 0.0) * (1 if sol else 0)
                out[nome][est] += (d + 0.5 * dhi) * 0.5 * f
    return {k: {kk: round(vv, 0) for kk, vv in v.items()} for k, v in out.items()}


def _orientacao_otima(fach: Dict[str, Dict[str, float]], expo_media: Optional[float], declive: float) -> Dict[str, Any]:
    # melhor fachada = máximo ganho de inverno com o mínimo ganho de verão
    nota = {k: v["inverno_kwh_m2"] - 0.6 * v["verao_kwh_m2"] for k, v in fach.items()}
    melhor = max(nota, key=nota.get)
    az = FACHADAS[melhor]
    txt = f"Fachada principal (salas, maiores vãos) virada a {melhor}"
    if declive >= 8 and expo_media is not None:
        dif = abs(((expo_media - az) + 180) % 360 - 180)
        if dif > 60:
            txt += (f"; a vertente desce para {S.rumo(expo_media)}: alinhar o edifício pelas curvas de nível e abrir a "
                    f"fachada {melhor} acima do terreno (pisos desnivelados) para não a enterrar")
    return {"fachada": melhor, "azimute": az, "texto": txt, "tolerancia_graus": 25}


def _ventilacao(horizonte: List[float], forma: Optional[str]) -> Dict[str, Any]:
    H = np.asarray(horizonte, dtype=float)
    # nortada (N–NO) no verão e brisas de SO; abrigo = horizonte alto nessas direções
    nno = float(H[[30, 31, 32, 33, 34, 35, 0]].mean())
    so = float(H[[21, 22, 23, 24]].mean())
    exp = "exposto" if nno < 3 else "parcialmente abrigado" if nno < 8 else "abrigado"
    txt = {"exposto": "Local exposto aos ventos de N–NO dominantes no verão: boa ventilação natural, proteger a fachada "
                      "norte no inverno (vãos menores, quebra-ventos vegetais).",
           "parcialmente abrigado": "Abrigo parcial dos ventos de N–NO: ventilação cruzada NO–SE recomendada.",
           "abrigado": "Relevo a norte/noroeste abriga do vento dominante: ventilação natural reduzida no verão — prever "
                       "ventilação cruzada e efeito chaminé (vãos altos, pátio ou clarabóia)."}[exp]
    if forma in ("vale", "base_encosta"):
        txt += " Fundo de vale: acumulação de ar frio e humidade nas noites de inverno."
    elif forma == "cumeada":
        txt += " Cumeada: rajadas fortes, reforçar a cobertura e a caixilharia."
    return {"exposicao_vento_dominante": exp, "horizonte_nno_graus": round(nno, 1), "horizonte_so_graus": round(so, 1),
            "recomendacao": txt}


def avaliar(lat: float, lon: float, sol: Dict[str, Any], relevo: Dict[str, Any]) -> Dict[str, Any]:
    hz = [h["angulo"] for h in sol["horizonte_centro"]]
    fach = irradiacao_fachadas(lat, lon, hz)
    alt = float(relevo.get("cota_media") or 0)
    decl = float(relevo.get("declive_medio_pct") or 0)
    ori = _orientacao_otima(fach, relevo.get("exposicao_graus"), decl)
    ven = _ventilacao(hz, relevo.get("forma_dominante"))
    # potencial de sobreaquecimento: ganho de verão nas fachadas O/SO + latitude + altitude
    oeste = (fach["O"]["verao_kwh_m2"] + fach["SO"]["verao_kwh_m2"]) / 2
    p = 0.0
    p += min(1.0, oeste / 450.0) * 0.45
    p += max(0.0, min(1.0, (41.5 - lat) / 4.5)) * 0.25                 # mais a sul, mais quente
    p += max(0.0, min(1.0, (500.0 - alt) / 500.0)) * 0.2               # baixa altitude
    p += (0.1 if ven["exposicao_vento_dominante"] == "abrigado" else 0.0)
    sobre = "elevado" if p >= 0.62 else "moderado" if p >= 0.4 else "baixo"
    inv = sol["horas_sol_21dez"]
    sombra = ("forte" if inv["media"] < 0.4 * inv["duracao_dia"] else "moderado" if inv["media"] < 0.75 * inv["duracao_dia"]
              else "fraco")
    frio = alt >= 700 or (decl >= 10 and relevo.get("exposicao") in ("N", "NE", "NO"))
    rec = [ori["texto"] + "."]
    if sombra != "fraco":
        rec.append(f"Sombreamento de inverno {sombra} pelo relevo/edifícios a sul (horizonte a sul ≈ {sol['horizonte_sul_graus']}°): "
                   "subir a cota dos vãos principais ou implantar na zona mais desafogada.")
    if sobre != "baixo":
        rec.append("Potencial de sobreaquecimento " + sobre + ": palas horizontais a sul, proteções exteriores reguláveis a "
                   "nascente/poente, limitar envidraçados a poente, massa térmica interior e cobertura ventilada/clara.")
    rec.append(ven["recomendacao"])
    if frio:
        rec.append("Clima de inverno mais rigoroso (altitude ou vertente norte): reforçar o isolamento e privilegiar ganhos solares diretos.")
    rec.append("Água quente sanitária e fotovoltaico: cobertura ou fachada orientadas a S (±45°) sem sombra relevante.")
    pv = sol["irradiacao_anual_kwh_m2"]["media"]
    return {
        "ok": True,
        "orientacao_recomendada": ori,
        "irradiacao_fachadas": fach,
        "exposicao_solar": {"indice_solar_pct": sol["indice_solar_pct"], "horas_sol_21dez": inv,
                            "horas_sol_21jun": sol["horas_sol_21jun"], "irradiacao_anual_media_kwh_m2": pv},
        "sombreamento": {"nivel_inverno": sombra, "horizonte_sul_graus": sol["horizonte_sul_graus"],
                         "fracao_terreno_sombreada_inverno": sol["fracao_sombra_inverno"]},
        "ventilacao": ven,
        "sobreaquecimento": {"nivel": sobre, "indice": round(p, 2), "ganho_verao_fachada_oeste_kwh_m2": round(oeste, 0)},
        "inverno_rigoroso": frio,
        "recomendacoes": rec,
        "nota": "Indicadores de anteprojeto sobre o horizonte real do terreno. A zona climática (REH, Despacho n.º 15793-F/2013) "
                "e o desempenho energético são verificados no projeto de comportamento térmico.",
    }
