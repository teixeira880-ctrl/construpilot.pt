"""Relevo do terreno sobre o MDT: altitude, declive, exposição das vertentes, forma do relevo, rugosidade e
fatores de terreno usados nos riscos (acumulação de escoamento, fator LS da erosão).

Forma do relevo: índice de posição topográfica (TPI, Weiss 2001) em duas escalas → cumeada / encosta alta / encosta /
plano / base de encosta / vale (linha de água). Tudo calculado na grelha PT-TM06 do MDT, sem valores inventados.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import ndimage

from engines.mdt_pt import analise as AN
from engines.mdt_pt.geotiff import Raster

SETORES = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
FORMAS = {
    "cumeada": "Cumeada / topo — exposto ao vento, boa insolação, drenagem natural",
    "encosta_alta": "Encosta alta — exposta, vistas, escoamento a montante reduzido",
    "encosta": "Encosta — implantação com socalcos ou pisos desnivelados",
    "plano": "Plano / planalto — implantação simples",
    "base_encosta": "Base de encosta — recebe escoamento das vertentes a montante",
    "vale": "Vale / linha de água — concentra escoamento, risco de encharcamento e cheia",
}


def _tpi(z: np.ndarray, raio_cel: int) -> np.ndarray:
    """z − média da vizinhança (janela quadrada 2r+1, filtro separável: custo independente do raio)."""
    raio_cel = max(1, int(raio_cel))
    return z - ndimage.uniform_filter(z, size=2 * raio_cel + 1, mode="nearest")


def forma_relevo(r: Raster, decl: np.ndarray) -> np.ndarray:
    """Classe de forma do relevo por célula (códigos de FORMAS, em texto)."""
    z = AN._preencher_nan(r.z.astype(np.float64))
    pequeno = _tpi(z, round(25.0 / r.px))
    grande = _tpi(z, round(120.0 / r.px))
    sp = (pequeno - pequeno.mean()) / (pequeno.std() or 1)
    sg = (grande - grande.mean()) / (grande.std() or 1)
    # limiares absolutos (m) para não classificar micro-relevo de um terreno plano como vale/cumeada
    abs_p = np.abs(pequeno) > 0.3
    abs_g = np.abs(grande) > 1.0
    out = np.full(z.shape, "encosta", dtype=object)
    plano = decl < 5
    out[plano] = "plano"
    out[(sg > 1) & abs_g] = "cumeada"
    out[(sg > 0.5) & (sg <= 1) & ~plano & abs_g] = "encosta_alta"
    out[(sg < -0.5) & ~plano & abs_g] = "base_encosta"
    out[((sp < -1) & abs_p) | ((sg < -1) & abs_g)] = "vale"
    return out


def setores_exposicao(expo: np.ndarray, decl: np.ndarray, mascara: np.ndarray) -> List[Dict[str, Any]]:
    v = mascara & ~np.isnan(expo)
    tot = max(int(v.sum()), 1)
    out = [{"setor": "plano", "pct": round(100.0 * float((v & (decl < 2)).sum()) / tot, 1)}]
    inc = v & (decl >= 2)
    k = (((expo + 22.5) % 360) // 45).astype(int)
    for i, s in enumerate(SETORES):
        out.append({"setor": s, "pct": round(100.0 * float((inc & (k == i)).sum()) / tot, 1)})
    return out


def fator_ls(decl_pct: np.ndarray, acumulacao: np.ndarray, px: float) -> np.ndarray:
    """Fator topográfico LS da RUSLE (Moore & Burch 1986) a partir da área drenada por largura de célula."""
    beta = np.arctan(np.nan_to_num(decl_pct) / 100.0)
    a_s = np.clip(acumulacao * px, px, 400.0)                       # comprimento de rampa limitado a ~400 m
    return (a_s / 22.13) ** 0.4 * (np.sin(beta) / 0.0896) ** 1.3


def _acumulacao(r: Raster) -> Dict[str, Any]:
    esc = AN.escorrencia(r)
    rr: Raster = esc["raster"]
    acc = esc["acumulacao"]
    if rr.z.shape != r.z.shape:                                    # escorrência reamostrada → voltar à grelha base
        fy, fx = r.z.shape[0] / rr.z.shape[0], r.z.shape[1] / rr.z.shape[1]
        acc = ndimage.zoom(acc, (fy, fx), order=0)[: r.z.shape[0], : r.z.shape[1]] * (r.px * r.py) / (rr.px * rr.py)
        if acc.shape != r.z.shape:
            acc = np.pad(acc, ((0, r.z.shape[0] - acc.shape[0]), (0, r.z.shape[1] - acc.shape[1])), mode="edge")
    return {"acc": acc, "linhas": esc["linhas"], "limiar_m2": esc["limiar_m2"]}


def analisar(r: Raster, mascara: np.ndarray) -> Dict[str, Any]:
    decl, expo = AN.declive_exposicao(r)
    est = AN.estatisticas(r, decl, expo, mascara)
    if not est.get("ok"):
        return {"ok": False, "nota": "sem cotas dentro do terreno"}
    cel = r.px * r.py
    forma = forma_relevo(r, np.nan_to_num(decl))
    contagem = {k: int(((forma == k) & mascara).sum()) for k in FORMAS}
    tot = max(int(mascara.sum()), 1)
    formas = [{"forma": k, "descricao": FORMAS[k], "pct": round(100.0 * n / tot, 1)} for k, n in contagem.items() if n]
    formas.sort(key=lambda e: -e["pct"])
    z = AN._preencher_nan(r.z.astype(np.float64))
    m1 = ndimage.uniform_filter(z, 3, mode="nearest")
    rug = np.sqrt(np.clip(ndimage.uniform_filter(z * z, 3, mode="nearest") - m1 * m1, 0, None))
    esc = _acumulacao(r)
    acc = esc["acc"]
    ls = fator_ls(decl, acc, r.px)
    lin_ll = [{"latlon": AN.tm_para_ll_lista(l["xy"]), "bacia_m2": l["bacia_m2"]} for l in esc["linhas"][:60]]
    return {
        "ok": True, **est,
        "classes_declive": AN.classes_declive(decl, mascara, cel),
        "exposicao_setores": setores_exposicao(expo, np.nan_to_num(decl), mascara),
        "forma_dominante": formas[0]["forma"] if formas else None,
        "formas": formas,
        "rugosidade_m": round(float(rug[mascara].mean()), 2),
        "ls_medio": round(float(ls[mascara].mean()), 2),
        "bacia_max_no_terreno_m2": round(float(acc[mascara].max() * cel), 0),
        "linhas_agua": lin_ll, "limiar_linha_agua_m2": esc["limiar_m2"],
        "fracao_vale": round(contagem["vale"] / tot, 3),
        "_decl": decl, "_expo": expo, "_forma": forma, "_acc": acc, "_ls": ls,
    }


def declive_acesso(r: Raster, xy_via: Optional[tuple], xy_alvo: tuple) -> Optional[Dict[str, Any]]:
    """Declive médio e máximo do percurso reto entre a via e o ponto de implantação."""
    if not xy_via:
        return None
    d = math.hypot(xy_alvo[0] - xy_via[0], xy_alvo[1] - xy_via[1])
    if d < 1:
        return {"comprimento_m": round(d, 1), "declive_medio_pct": 0.0, "declive_max_pct": 0.0, "desnivel_m": 0.0}
    n = max(2, int(d / max(r.px, 1.0)) + 1)
    t = np.linspace(0, 1, n)
    xs = xy_via[0] + (xy_alvo[0] - xy_via[0]) * t
    ys = xy_via[1] + (xy_alvo[1] - xy_via[1]) * t
    zz = AN.amostrar(r, xs, ys)
    if np.isnan(zz).all():
        return None
    zz = np.where(np.isnan(zz), np.nanmean(zz), zz)
    passo = d / (n - 1)
    g = np.abs(np.diff(zz)) / passo * 100
    if g.size >= 5:                                            # suaviza o ruído do MDT em troços curtos
        g = np.convolve(g, np.ones(5) / 5, mode="same")
    return {"comprimento_m": round(d, 1), "desnivel_m": round(float(zz[-1] - zz[0]), 2),
            "declive_medio_pct": round(abs(float(zz[-1] - zz[0])) / d * 100, 1),
            "declive_max_pct": round(float(g.max()), 1)}
