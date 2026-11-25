"""Avaliação preliminar da viabilidade construtiva de um terreno — orquestração.

Entrada: o terreno (anel lat/lon), opcionalmente os parâmetros do PDM (regulamento municipal), o edifício pretendido
(largura × profundidade × pisos, ou um IFC do projeto) e o tipo de uso.
Saída: características físicas (relevo, sol, acessibilidade), condicionantes territoriais e legais (PDM, REN, RAN,
SRUP), riscos naturais, conforto térmico, potencial construtivo, implantação recomendada e uma classificação final com
fundamentos — tudo com a fonte de cada dado e sem valores inventados (o que falta fica «por confirmar»).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage

from engines.mdt_pt import analise as AN
from engines.mdt_pt import grelha as GR
from engines.mdt_pt import pttm06 as TM
from engines.mdt_pt import saidas as SA
from engines.mdt_pt.geotiff import Raster

from . import conforto as CF
from . import implantacao as IM
from . import ordenamento as OR
from . import relevo as RV
from . import riscos as RK
from . import solar as SO

log = logging.getLogger(__name__)

MARGEM_M = 120.0            # zona envolvente analisada (horizonte, escoamento a montante, acessos)
MAX_CEL = 240               # lado máximo da grelha de análise (células)
EDIFICIO_PADRAO = (12.0, 10.0, 2)
AVISO = ("Avaliação preliminar automática sobre dados oficiais abertos (DGT, APA/REN, ICNF quando publicados) e "
         "cálculos sobre o modelo digital do terreno. Não substitui a certidão / informação prévia da câmara (art.º 14.º "
         "do RJUE), o levantamento topográfico, o estudo geotécnico nem o projeto de comportamento térmico.")


class ViabilidadeErro(ValueError):
    pass


# ------------------------------------------------------------------ geometria (sem shapely)
def _anel(anel: Any) -> List[Tuple[float, float]]:
    try:
        pts = [(float(p[0]), float(p[1])) for p in anel]
    except Exception as e:  # noqa: BLE001
        raise ViabilidadeErro("terreno inválido: indique os vértices [lat, lon]") from e
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        raise ViabilidadeErro("o terreno precisa de pelo menos 3 vértices")
    for a, b in pts:
        if not GR.dentro_de_portugal(a, b):
            raise ViabilidadeErro("o terreno tem de ficar em Portugal continental")
    return pts


def _tm(pts) -> np.ndarray:
    x, y = TM.para_tm(np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
    return np.c_[x, y]


def _area(xy: np.ndarray) -> float:
    x, y = xy[:, 0], xy[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def _contornos(r: Raster, m: np.ndarray, min_m2: float = 4.0) -> List[List[List[float]]]:
    """Contornos (TM) de uma máscara booleana."""
    if not m.any():
        return []
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xc, yc = AN.centros(r)
    fig = plt.figure()
    try:
        cs = plt.contour(xc, yc, m.astype(float), levels=[0.5])
        segs = cs.allsegs[0]
    finally:
        plt.close(fig)
    out = []
    for s in segs:
        if len(s) >= 3 and _area(np.asarray(s)) >= min_m2:
            out.append([[round(float(a), 2), round(float(b), 2)] for a, b in s])
    return out


def _ll(xy) -> List[List[float]]:
    return AN.tm_para_ll_lista(xy)


# ------------------------------------------------------------------ fontes externas
async def _seguro(nome: str, coro, prazo: float):
    try:
        return await asyncio.wait_for(coro, timeout=prazo)
    except asyncio.TimeoutError:
        return {"ok": False, "nota": f"{nome}: sem resposta a tempo"}
    except Exception as e:  # noqa: BLE001 — um tema falhado não pode parar a avaliação
        log.info("viabilidade %s: %s", nome, e)
        return {"ok": False, "nota": f"{nome}: {str(e)[:160] or type(e).__name__}"}


async def _territorio(pts, prazo: float) -> Dict[str, Any]:
    from engines.terrenos_pt import analise as TA
    return await TA.analisar([[a, b] for a, b in pts], prazo_s=prazo)


async def _via(lat, lon):
    from engines.urbanismo_pt.auto import geo
    return await geo.via_proxima(lat, lon, raio_m=150)


async def _edificios(lat, lon):
    from engines.urbanismo_pt.auto import geo
    return await geo.edificios_osm(lat, lon, raio_m=250)


def _grelha(r: Raster) -> Raster:
    rr = r
    while max(rr.z.shape) > MAX_CEL:
        rr = GR.reamostrar(rr, rr.px * 2)
    return rr


# ------------------------------------------------------------------ acessibilidade
def _acessibilidade(r: Raster, via: Dict[str, Any], mascara: np.ndarray, alvo_xy: Tuple[float, float]) -> Dict[str, Any]:
    if not (via or {}).get("ok"):
        return {"ok": False, "estado": "por_confirmar", "nota": (via or {}).get("nota") or "via não consultada",
                "xy_via": None}
    d = via["data"]
    a = np.array(TM.ponto_tm(*d["a"]))
    b = np.array(TM.ponto_tm(*d["b"]))
    # ponto da via mais próximo do terreno
    I, J = np.nonzero(mascara & ~ndimage.binary_erosion(mascara))
    xc, yc = AN.centros(r)
    bx, by = xc[J], yc[I]
    v = b - a
    L2 = float(v @ v) or 1e-9
    t = np.clip(((bx - a[0]) * v[0] + (by - a[1]) * v[1]) / L2, 0, 1)
    px, py = a[0] + t * v[0], a[1] + t * v[1]
    dist = np.hypot(bx - px, by - py)
    k = int(np.argmin(dist))
    dmin = float(dist[k])
    xy_via = (float(px[k]), float(py[k]))
    perc = RV.declive_acesso(r, xy_via, alvo_xy)
    if dmin <= max(3.0, 1.5 * r.px):
        cls, txt = "confinante", "O terreno confina com a via pública"
    elif dmin <= 50:
        cls, txt = "proxima", f"Via pública a {dmin:.0f} m: acesso por servidão ou caminho a constituir"
    else:
        cls, txt = "afastada", f"Via mais próxima a {dmin:.0f} m: acesso a confirmar (pode condicionar o licenciamento)"
    if perc and perc["declive_max_pct"] > 15:
        txt += f"; o percurso até à implantação tem troços com {perc['declive_max_pct']:.0f} % (rampa > 15 %)"
    return {"ok": True, "estado": cls, "texto": txt, "distancia_m": round(dmin, 1), "via": d.get("nome"),
            "seg_via": ((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))),
            "tipo_via": d.get("tipo"), "percurso_implantacao": perc, "fonte": via.get("fonte"),
            "ponto_via_latlon": list(TM.ponto_ll(*xy_via)), "xy_via": xy_via}


# ------------------------------------------------------------------ classificação final
def _classificar(res: Dict[str, Any]) -> Dict[str, Any]:
    fund: List[Dict[str, str]] = []

    def add(peso, txt):
        fund.append({"nivel": peso, "texto": txt})

    orden = res["ordenamento"]
    solo = orden["solo"]
    cond = orden["condicionantes"]
    ren, ran = cond["ren"]["fracao"], cond["ran"]["fracao"]
    impl = res["implantacao"]
    rk = res["riscos"]
    rel = res["relevo"]
    pot = orden["potencial"]
    if solo["solo"] == "urbano":
        add("ok", f"Solo urbano no PDM ({solo.get('categoria') or solo.get('classe') or 'categoria por confirmar'}).")
        if solo.get("habitacional") is False:
            add("aviso", "A categoria de espaço pode não admitir habitação: confirmar os usos no regulamento.")
    elif solo["solo"] == "rustico":
        add("critico", "Solo rústico no PDM: a edificação é excecional (habitação própria do agricultor, apoio agrícola, "
                       "turismo…) e depende das condições do regulamento.")
    else:
        add("info", "Classificação do solo por confirmar (CRUS do PDM indisponível para este local).")
    if ren >= 0.5 or ran >= 0.5:
        add("critico", f"REN/RAN ocupam {round((ren + ran) * 100)} % do terreno: edificação, em regra, interdita nessa área.")
    elif ren > 0 or ran > 0:
        add("aviso", f"REN/RAN em parte do terreno ({round((ren + ran) * 100)} %): implantar fora dessa área.")
    if not cond["consultado"]:
        add("info", "Servidões e restrições (SRUP) por confirmar: serviço da DGT sem resposta.")
    for e in rk["riscos"]:
        if e["nivel"] == "muito_elevado":
            add("critico", f"Risco {e['risco'].replace('_', ' ')} muito elevado.")
        elif e["nivel"] == "elevado":
            add("aviso", f"Risco {e['risco'].replace('_', ' ')} elevado.")
    if rel.get("declive_medio_pct") and rel["declive_medio_pct"] >= 25:
        add("aviso", f"Declive médio de {_pt(rel['declive_medio_pct'], 0)} %: obra com muros de suporte e custos de terraplenagem altos.")
    ac = res["acessibilidade"]
    if ac.get("estado") == "afastada":
        add("aviso", ac["texto"] + ".")
    if not impl.get("ok"):
        add("critico", impl.get("nota") or "Sem implantação possível.")
    else:
        add("ok", f"Implantação de {_pt(impl['area_m2'], 0)} m² possível na zona livre ({_pt(pot['area_livre_para_implantacao_m2'], 0)} m²).")
    crit = sum(1 for f in fund if f["nivel"] == "critico")
    avis = sum(1 for f in fund if f["nivel"] == "aviso")
    if crit >= 2 or (not impl.get("ok")) or ren >= 0.9 or ran >= 0.9:
        cl, rot = "inviavel_provavel", "Inviável (provável)"
    elif crit == 1:
        cl, rot = "condicionada", "Condicionada — exige confirmação prévia na câmara"
    elif avis:
        cl, rot = "viavel_com_condicionantes", "Viável com condicionantes"
    elif solo["solo"] == "urbano":
        cl, rot = "viavel", "Viável"
    else:
        cl, rot = "condicionada", "Por confirmar — falta a classificação do solo"
    nota = round(max(0, 100 - 35 * crit - 10 * avis), 0)
    sint = f"{rot}. " + " ".join(f["texto"] for f in fund if f["nivel"] in ("critico", "aviso"))[:600]
    return {"classificacao": cl, "rotulo": rot, "indice": nota, "fundamentos": fund, "sintese": sint.strip()}


def _pt(v, d: int) -> str:
    """Número à portuguesa (vírgula decimal, espaço nos milhares)."""
    return f"{float(v):,.{d}f}".replace(",", " ").replace(".", ",")


def _recomendacoes(res: Dict[str, Any]) -> List[str]:
    rec: List[str] = []
    impl = res["implantacao"]
    if impl.get("ok"):
        t = impl["terreno_sob_edificio"]
        rec.append(f"Implantar o edifício ({_pt(impl['largura_m'], 0)} × {_pt(impl['profundidade_m'], 0)} m) na posição proposta, "
                   f"com a fachada principal virada a {SO.rumo(impl['azimute_fachada_principal'])} e a soleira à cota "
                   f"{_pt(impl['cota_soleira_sugerida'], 2)} m ({impl['solucao_desnivel']}; desnível sob o edifício "
                   f"{_pt(t['desnivel_m'], 1)} m).")
        mv = impl["movimento_terras"]
        if mv.get("ok") and (mv["escavacao_m3"] + mv["aterro_m3"]) > 0:
            rec.append(f"Movimento de terras estimado da plataforma: {_pt(mv['escavacao_m3'], 0)} m³ de escavação e "
                       f"{_pt(mv['aterro_m3'], 0)} m³ de aterro (sem taludes).")
    for e in res["riscos"]["riscos"]:
        rec += e["recomendacoes"][:2]
    rec += res["conforto"]["recomendacoes"][:3]
    o = res["ordenamento"]
    if o["potencial"]["em_falta"]:
        rec.append("Pedir à câmara a informação prévia / certidão do PDM com os parâmetros: " + ", ".join(o["potencial"]["em_falta"]) + ".")
    if o["condicionantes"]["dominio_hidrico"]:
        rec.append("Linhas de água na envolvente: confirmar a margem do domínio hídrico com a APA.")
    rec.append("Antes do projeto: levantamento topográfico georreferenciado e, com declives ou aterros relevantes, estudo geotécnico.")
    vistos, out = set(), []
    for r in rec:
        if r not in vistos:
            vistos.add(r)
            out.append(r)
    return out


def _camada_rgba(m: np.ndarray, valores: Optional[np.ndarray], cor_lo, cor_hi, alpha=170) -> np.ndarray:
    rgba = np.zeros(m.shape + (4,), dtype=np.uint8)
    if valores is None:
        rgba[m] = (*cor_hi, alpha)
        return rgba
    v = valores.copy()
    ok = m & np.isfinite(v)
    if not ok.any():
        return rgba
    lo, hi = np.nanpercentile(v[ok], 2), np.nanpercentile(v[ok], 98)
    t = np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1)
    for c in range(3):
        rgba[..., c] = np.nan_to_num(cor_lo[c] + (cor_hi[c] - cor_lo[c]) * t).astype(np.uint8)
    rgba[..., 3] = np.where(ok, alpha, 0)
    return rgba


def _camada(r: Raster, rgba: np.ndarray) -> Dict[str, Any]:
    img, bounds = SA.para_latlon(r, rgba, max_px=512)
    return {"png": "data:image/png;base64," + base64.b64encode(SA.png(img)).decode(), "bounds": bounds}


# ------------------------------------------------------------------ cálculo (síncrono, corre numa thread)
def calcular(r: Raster, meta: Dict[str, Any], pts: List[Tuple[float, float]], terr: Dict[str, Any], via: Dict[str, Any],
             edif: Dict[str, Any], pdm_params: Optional[Dict[str, Any]], edificio: Optional[Dict[str, Any]],
             modelo: Optional[Dict[str, Any]] = None, extras: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """extras (opcionais): r_alargado (MDT ±1,4 km → horizonte longínquo), pvgis, ventos (ERA5)."""
    extras = extras or {}
    t0 = time.time()
    r = _grelha(r)
    xy = _tm(pts)
    mascara = AN.mascara_poligono(r, pts)
    area = _area(xy)
    cx, cy = float(xy[:, 0].mean()), float(xy[:, 1].mean())
    clat, clon = TM.ponto_ll(cx, cy)
    rel = RV.analisar(r, mascara)
    if not rel.get("ok"):
        raise ViabilidadeErro("sem cotas do terreno dentro do prédio")
    obst = SO.superficie(r, ((edif or {}).get("data") or {}).get("edificios")) if (edif or {}).get("ok") else None
    h_dist = None
    r_al = extras.get("r_alargado")
    if r_al is not None:
        try:
            z_c = float(AN.amostrar(r, np.array([cx]), np.array([cy]))[0])
            if np.isnan(z_c):
                z_c = float(rel.get("cota_media") or np.nanmean(r.z))
            h_dist = SO.horizonte_distante(r_al, cx, cy, z_c, d_min=min(MARGEM_M, 100.0))
        except Exception as e:  # noqa: BLE001
            log.info("viabilidade: horizonte distante: %s", e)
    sol = SO.analisar(r, mascara, rel["_decl"], rel["_expo"], clat, clon, obst, h_distante=h_dist)
    pv = extras.get("pvgis") or {}
    sol["pvgis"] = pv if pv.get("ok") else None
    srup = (terr or {}).get("servidoes")
    pdm = (terr or {}).get("pdm")
    solo = OR.solo_dominante(pdm)["solo"]
    cel = r.px * r.py
    rk = RK.avaliar(rel, mascara, srup, solo, cel, r.px)
    concelho = ((((terr or {}).get("caop") or {}).get("data") or {}).get("principal") or {}).get("concelho")
    from . import externos as EX
    clima = EX.clima_reh(concelho, rel.get("cota_media"))
    cf = CF.avaliar(clat, clon, sol, rel, extras.get("ventos"), clima)
    ac = _acessibilidade(r, via, mascara, (cx, cy))
    xy_via = ac.get("xy_via")
    # exclusões: talvegues, declives ≥ 45 %, REN/RAN (contornos publicados) e domínio hídrico
    excl = RK.mascaras_exclusao(rel, cel, r.px)
    aneis = []
    for e in (((srup or {}).get("data") or {}).get("afeta") or []):
        if e.get("tipo") in ("RAN", "REN", "recursos_hidricos"):
            aneis += e.get("aneis_latlon") or []
    if aneis:
        excl |= IM.rasterizar(r, aneis)
    afast = OR.afastamentos(pdm_params or {})
    zl = IM.zona_livre(r, mascara, afast["valores_m"], ac.get("seg_via"), excl)
    ed = edificio or {}
    w = float(ed.get("largura_m") or (modelo or {}).get("largura_m") or EDIFICIO_PADRAO[0])
    d = float(ed.get("profundidade_m") or (modelo or {}).get("profundidade_m") or EDIFICIO_PADRAO[1])
    pisos = int(ed.get("n_pisos") or (modelo or {}).get("n_pisos") or (pdm_params or {}).get("n_pisos_max") or EDIFICIO_PADRAO[2])
    if w < d:
        w, d = d, w
    apt = IM.aptidao(r, rel, sol["_mapa_anual"], xy_via)
    impl = IM.recomendar(r, mascara, zl["mascara"], apt, rel, w, d, cf["orientacao_recomendada"]["azimute"])
    if impl.get("ok"):
        impl["n_pisos"] = pisos
        impl["origem_dimensoes"] = "modelo IFC" if modelo and not ed.get("largura_m") else "indicadas" if ed.get("largura_m") else "padrão (moradia 12 × 10 m)"
    orden = OR.avaliar(pdm, srup, area, zl["area_m2"], pdm_params)
    # verificação do edifício pretendido contra o potencial
    verif = []
    pot = orden["potencial"]
    if impl.get("ok"):
        if pot.get("area_implantacao_max_m2") is not None:
            verif.append({"item": "Área de implantação", "valor": impl["area_m2"], "limite": pot["area_implantacao_max_m2"],
                          "resultado": "conforme" if impl["area_m2"] <= pot["area_implantacao_max_m2"] + 1e-6 else "nao_conforme"})
        if pot.get("area_construcao_max_m2") is not None:
            ab = impl["area_m2"] * pisos
            verif.append({"item": "Área de construção", "valor": round(ab, 1), "limite": pot["area_construcao_max_m2"],
                          "resultado": "conforme" if ab <= pot["area_construcao_max_m2"] + 1e-6 else "nao_conforme"})
        if pot.get("n_pisos_max") is not None:
            verif.append({"item": "N.º de pisos", "valor": pisos, "limite": pot["n_pisos_max"],
                          "resultado": "conforme" if pisos <= pot["n_pisos_max"] else "nao_conforme"})
    livre_tm = _contornos(r, zl["mascara"])
    res: Dict[str, Any] = {
        "ok": True,
        "terreno": {"anel_latlon": [[round(a, 7), round(b, 7)] for a, b in pts], "area_m2": round(area, 1),
                    "centroide": [round(clat, 7), round(clon, 7)],
                    "centroide_tm06": [round(cx, 2), round(cy, 2)], "sistema": "PT-TM06/ETRS89 (EPSG:3763)"},
        "mdt": {**{k: v for k, v in meta.items() if k not in ("avisos",)}, "resolucao_analise_m": r.px,
                "avisos": meta.get("avisos") or []},
        "relevo": {k: v for k, v in rel.items() if not k.startswith("_")},
        "solar": {k: v for k, v in sol.items() if not k.startswith("_")},
        "acessibilidade": {k: v for k, v in ac.items() if k not in ("xy_via", "seg_via")},
        "riscos": rk, "conforto": cf, "ordenamento": orden,
        "territorio": {k: (terr or {}).get(k) for k in ("caop", "cadastro", "bupi", "estado", "alertas")} if terr else None,
        "zona_livre": {"area_m2": zl["area_m2"], "aneis_latlon": [_ll(a) for a in livre_tm],
                       "afastamentos_m": afast["valores_m"], "nota_afastamentos": afast["nota"]},
        "implantacao": {k: v for k, v in impl.items() if not k.startswith("_")},
        "verificacao_edificio": verif,
        "aviso_legal": AVISO,
    }
    res["viabilidade"] = _classificar(res)
    res["recomendacoes"] = _recomendacoes(res)
    res["camadas"] = {
        "aptidao": _camada(r, _camada_rgba(zl["mascara"], apt, (240, 200, 60), (20, 150, 80))),
        "irradiacao": _camada(r, _camada_rgba(mascara, sol["_mapa_anual"], (60, 90, 200), (250, 120, 30))),
    }
    res["_interno"] = {"r": r, "mascara": mascara, "anel_tm": xy.tolist(), "zona_livre_tm": livre_tm, "impl": impl}
    res["duracao_s"] = round(time.time() - t0, 2)
    return res


async def avaliar(anel: Any, pdm: Optional[Dict[str, Any]] = None, edificio: Optional[Dict[str, Any]] = None,
                  modelo: Optional[Dict[str, Any]] = None, prazo_s: float = 80.0) -> Dict[str, Any]:
    pts = _anel(anel)
    xy = _tm(pts)
    if _area(xy) < 20:
        raise ViabilidadeErro("terreno com menos de 20 m²")
    lado = max(np.ptp(xy[:, 0]), np.ptp(xy[:, 1]))
    if lado > 1500:
        raise ViabilidadeErro("terreno com mais de 1,5 km de lado: divida-o em prédios")
    cla, clo = TM.ponto_ll(float(xy[:, 0].mean()), float(xy[:, 1].mean()))
    from . import externos as EX
    mdt_t = asyncio.ensure_future(GR.obter(pts, None, margem_m=MARGEM_M))
    cx, cy = float(xy[:, 0].mean()), float(xy[:, 1].mean())
    cantos = [TM.ponto_ll(cx + dx, cy + dy) for dx in (-1400.0, 1400.0) for dy in (-1400.0, 1400.0)]
    terr, via, edif, alarg, pv, vt = await asyncio.gather(
        _seguro("ordenamento (DGT)", _territorio(pts, prazo_s - 5), prazo_s),
        _seguro("via de acesso (OSM)", _via(cla, clo), 25),
        _seguro("edifícios vizinhos (OSM)", _edificios(cla, clo), 25),
        _seguro("relevo envolvente (MDT ±1,4 km)", _mdt_alargado(cantos), 120),
        _seguro("PVGIS", EX.pvgis(cla, clo), 25),
        _seguro("vento ERA5", EX.ventos(cla, clo), 35),
    )
    try:
        r, meta = await mdt_t
    except GR.MdtErro as e:
        raise ViabilidadeErro(str(e)) from e
    extras = {"r_alargado": alarg.get("r") if isinstance(alarg, dict) else None, "pvgis": pv, "ventos": vt}
    return await asyncio.to_thread(calcular, r, meta, pts, terr if (terr or {}).get("geometria") else None, via, edif,
                                   pdm, edificio, modelo, extras)


async def _mdt_alargado(cantos) -> Dict[str, Any]:
    """MDT da envolvente (±1,4 km, grelha de 8 m) para o horizonte longínquo."""
    r, meta = await GR.obter(cantos, 8.0, margem_m=0.0)
    return {"ok": True, "r": r, "fonte": meta.get("fonte")}


def publico(res: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in res.items() if not k.startswith("_")}
