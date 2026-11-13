"""Análise de um terreno delimitado — só fontes oficiais, cada resultado com a sua fonte e o seu estado.

Para o polígono inteiro (não só para um ponto, como num visualizador):
- CAOP (DGT): distrito, concelho, freguesia(s) e código DICOFRE, com a fração do terreno em cada freguesia;
- Carta Cadastral (DGT): prédios cadastrados que o terreno cruza, com sobreposição em m² e %, e o melhor candidato;
- RGG do BUPi (eBUPi): RGG já submetidas que o terreno toca → risco de conflito de estremas;
- PDM / CRUS (DGT): classe e categoria de espaço, em % da área;
- Servidões e restrições (SRUP, DGT): RAN, REN, domínio hídrico, Rede Natura… área afetada; linhas (estradas, linhas
  elétricas, cursos de água) com distância ao terreno;
- Declives: modelo digital de terreno, declive médio e máximo, classes — indicativo, não substitui a topografia.

Nada é inventado: um serviço que não responde fica «por confirmar», nunca «sem restrições».
"""
from __future__ import annotations

import asyncio
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from engines.urbanismo_pt.auto import geo as G

from . import bupi as B
from . import geometria as GM

_HIDRO_PAT = re.compile(r"(hidrogr|curso.{0,4}d.{0,3}[aá]gua|linha.{0,4}d.{0,3}[aá]gua|massas? de [aá]gua|albufeir|"
                        r"dom[ií]nio h[ií]dric|leito|cheia|inunda)", re.I)
_RAN_PAT = re.compile(r"(\bran\b|reserva agr)", re.I)
_REN_PAT = re.compile(r"(\bren\b|reserva ecol)", re.I)


def _pontos_interiores(poly_m, n_max: int = 16) -> List[Tuple[float, float]]:
    """Grelha regular dentro do terreno, afastada 1 m dos limites (em PT-TM06), sempre com o ponto representativo."""
    inner = poly_m.buffer(-1.0)
    if inner.is_empty:
        inner = poly_m
    rp = inner.representative_point()
    pts = [(rp.x, rp.y)]
    minx, miny, maxx, maxy = inner.bounds
    from shapely.geometry import Point
    for k in (3, 4, 5, 6, 8):
        sx, sy = (maxx - minx) / k, (maxy - miny) / k
        cand = [(minx + sx * (i + .5), miny + sy * (j + .5)) for i in range(k) for j in range(k)]
        cand = [c for c in cand if inner.contains(Point(c))]
        if len(cand) + 1 >= min(n_max, 6) or k == 8:
            pts += cand[: n_max - 1]
            break
    return pts


def _ll(xy: Tuple[float, float]) -> List[float]:
    la, lo = GM.tm06_inv(*xy)
    return [round(la, 7), round(lo, 7)]


# ------------------------------------------------------------------ CAOP
async def caop(poly_m, bbox: str) -> Dict[str, Any]:
    feats = await G._dgt_items("freguesias", bbox, 20, {})
    if feats is None:
        return G._res(False, nota="CAOP indisponível", url=f"{G.DGT}/collections/freguesias")
    area = poly_m.area
    lista = []
    for f in feats:
        g = GM.geom_para_m(f.get("geometry"))
        if g is None:
            continue
        a = g.intersection(poly_m).area
        if a <= 0.01:
            continue
        p = G._props_text(f.get("properties"))
        lista.append({
            "freguesia": G._pick(p, "freguesia", "nome", "designacao"),
            "concelho": G._pick(p, "municipio", "concelho"),
            "distrito": G._pick(p, "distrito", "ilha"),
            "dicofre": G._pick(p, "dtmnfr", "dicofre", "dicofr", "codigo"),
            "area_m2": round(a, 1), "fracao": round(a / area, 4),
        })
    lista.sort(key=lambda e: -e["fracao"])
    if not lista:
        return G._res(False, nota="o terreno não cruza nenhuma freguesia da CAOP (fora do território?)",
                      url=f"{G.DGT}/collections/freguesias")
    return G._res(True, {"principal": lista[0], "freguesias": lista, "atravessa_limite": len(lista) > 1},
                  "DGT — Carta Administrativa Oficial de Portugal (CAOP)", f"{G.DGT}/collections/freguesias")


# ------------------------------------------------------------------ cadastro
async def cadastro(poly_m, bbox: str) -> Dict[str, Any]:
    cols = [c for c in await G.dgt_collections() if "cadastr" in (c["id"] + " " + c["title"]).lower()]
    if not cols:
        return G._res(False, nota="lista de coleções da DGT indisponível")
    area = poly_m.area
    predios, consultadas, falhas = [], 0, 0
    for c in cols[:4]:
        feats = await G._dgt_items(c["id"], bbox, 60)
        if feats is None:
            falhas += 1
            continue
        consultadas += 1
        for f in feats:
            g = GM.geom_para_m(f.get("geometry"))
            if g is None:
                continue
            inter = g.intersection(poly_m).area
            if inter <= 0.5:
                continue
            p = G._props_text(f.get("properties"))
            predios.append({
                "colecao": c["id"],
                "referencia": G._pick(p, "nic", "num_predio", "artigo", "seccao", "id") or "",
                "atributos": p,
                "area_predio_m2": round(g.area, 1),
                "sobreposicao_m2": round(inter, 1),
                "fracao_do_terreno": round(inter / area, 4),
                "fracao_do_predio": round(inter / g.area, 4) if g.area else 0,
                "iou": round(inter / g.union(poly_m).area, 4),
                "anel_latlon": GM.anel_de_geojson(f.get("geometry")),
            })
    if consultadas == 0:
        return G._res(False, nota="cadastro da DGT indisponível")
    predios.sort(key=lambda e: -e["iou"])
    melhor = predios[0] if predios and predios[0]["iou"] >= 0.6 else None
    return G._res(True, {"predios": predios[:20], "melhor_correspondencia": melhor, "sem_cadastro": not predios,
                         "incompleta": falhas > 0},
                  "DGT — Carta Cadastral (cadastro predial / geométrico)", f"{G.DGT}/collections")


# ------------------------------------------------------------------ PDM (CRUS)
async def crus(poly_m, bbox: str) -> Dict[str, Any]:
    feats = await G._dgt_items("crus", bbox, 60)
    if feats is None:
        return G._res(False, nota="CRUS indisponível", url=f"{G.DGT}/collections/crus")
    area = poly_m.area
    grupos: Dict[str, Dict[str, Any]] = {}
    for f in feats:
        g = GM.geom_para_m(f.get("geometry"))
        if g is None:
            continue
        a = g.intersection(poly_m).area
        if a <= 0.5:
            continue
        c = G.classificar_solo(G._props_text(f.get("properties")))
        k = f"{c['solo']}|{c.get('classe') or ''}|{c.get('categoria') or ''}"
        e = grupos.setdefault(k, {"solo": c["solo"], "classe": c.get("classe"), "categoria": c.get("categoria"),
                                  "habitacional": c["habitacional"], "area_m2": 0.0})
        e["area_m2"] += a
    lista = sorted(grupos.values(), key=lambda e: -e["area_m2"])
    for e in lista:
        e["area_m2"] = round(e["area_m2"], 1)
        e["fracao"] = round(e["area_m2"] / area, 4)
    coberto = sum(e["fracao"] for e in lista)
    if not lista:
        return G._res(False, nota="sem CRUS publicada para este terreno (o município pode ainda não a ter enviado à DGT)",
                      url=f"{G.DGT}/collections/crus")
    return G._res(True, {"classes": lista, "fracao_coberta": round(min(1.0, coberto), 4)},
                  "DGT — Carta do Regime de Uso do Solo (PDM em vigor)", f"{G.DGT}/collections/crus")


# ------------------------------------------------------------------ servidões, RAN, REN, recursos hídricos
def _tipo(titulo: str) -> str:
    t = titulo or ""
    if _RAN_PAT.search(t):
        return "RAN"
    if _REN_PAT.search(t):
        return "REN"
    if _HIDRO_PAT.search(t):
        return "recursos_hidricos"
    return "servidao"


async def servidoes(poly_m, anel: List[List[float]], prazo_s: float = 75.0) -> Dict[str, Any]:
    fim = time.monotonic() + prazo_s
    todas = await G.dgt_collections()
    cols = [c for c in todas if G._SRUP_PAT.search(c["id"].replace("_", " ") + " " + c["title"])
            or _HIDRO_PAT.search(c["id"].replace("_", " ") + " " + c["title"])]
    if not cols:
        return G._res(False, nota="lista de servidões da DGT indisponível")
    bbox = GM.bbox_txt(anel, 60.0)
    area = poly_m.area
    sem = asyncio.Semaphore(3)

    async def uma(c):
        async with sem:
            return c, await G._dgt_items(c["id"], bbox, 40)

    tarefas = [asyncio.ensure_future(uma(c)) for c in cols[:60]]
    feitas, pend = await asyncio.wait(tarefas, timeout=max(1.0, fim - time.monotonic()))
    for t in pend:
        t.cancel()
    afeta, proximas, por_confirmar = [], [], []
    for t, c in zip(tarefas, cols[:60]):
        if t not in feitas or t.exception() or t.result()[1] is None:
            por_confirmar.append({"id": c["id"], "titulo": c["title"], "tipo": _tipo(c["title"] or c["id"])})
            continue
        feats = t.result()[1]
        a_tot, dmin, comp = 0.0, None, 0.0
        for f in feats:
            gm = GM.geom_para_m(f.get("geometry"))
            if gm is not None:
                a_tot += gm.intersection(poly_m).area
                d = gm.distance(poly_m)
            else:
                gl = GM.geom_linha_para_m(f.get("geometry"))
                if gl is None:
                    continue
                comp += gl.intersection(poly_m).length
                d = gl.distance(poly_m)
            dmin = d if dmin is None else min(dmin, d)
        if dmin is None:
            continue
        e = {"id": c["id"], "titulo": c["title"], "tipo": _tipo(c["title"] or c["id"]),
             "area_afetada_m2": round(a_tot, 1), "fracao": round(a_tot / area, 4),
             "comprimento_no_terreno_m": round(comp, 1), "distancia_m": round(dmin, 1),
             "url": f"{G.DGT}/collections/{c['id']}"}
        (afeta if (a_tot > 0.5 or comp > 0.1 or dmin < 0.05) else proximas).append(e)
    afeta.sort(key=lambda e: (-e["fracao"], e["distancia_m"]))
    proximas.sort(key=lambda e: e["distancia_m"])
    return G._res(True, {
        "afeta": afeta, "proximas_60m": proximas, "por_confirmar": por_confirmar,
        "consultadas": len(cols[:60]) - len(por_confirmar), "incompleta": bool(por_confirmar),
        "ran": [e for e in afeta if e["tipo"] == "RAN"], "ren": [e for e in afeta if e["tipo"] == "REN"],
        "hidricos": [e for e in afeta + proximas if e["tipo"] == "recursos_hidricos"],
        "nota_ren": "A REN vetorial não dispensa a confirmação na delimitação publicada em Diário da República.",
    }, "DGT — Servidões e Restrições de Utilidade Pública (SRUP)", f"{G.DGT}/collections")


# ------------------------------------------------------------------ declives
def _classe_declive(p: float) -> str:
    if p < 8:
        return "suave (< 8 %)"
    if p < 15:
        return "moderado (8–15 %)"
    if p < 25:
        return "acentuado (15–25 %)"
    return "muito acentuado (> 25 %)"


async def declives(poly_m) -> Dict[str, Any]:
    minx, miny, maxx, maxy = poly_m.bounds
    from shapely.geometry import Point
    k = 7
    sx, sy = (maxx - minx) / (k - 1), (maxy - miny) / (k - 1)
    grelha = [(minx + sx * i, miny + sy * j) for j in range(k) for i in range(k)]
    dentro = [p for p in grelha if poly_m.buffer(max(sx, sy) * 0.5).contains(Point(p))]
    if len(dentro) < 4:
        dentro = grelha
    r = await G.elevacoes([tuple(_ll(p)) for p in dentro], verificar=True, prazo_oficial_s=60.0)
    if not r["ok"]:
        return G._res(False, nota=r.get("nota") or "altimetria indisponível")
    zs = r["data"]["z"]
    pts = [(x, y, z) for (x, y), z in zip(dentro, zs) if isinstance(z, (int, float))]
    if len(pts) < 4:
        return G._res(False, nota="altimetria incompleta")
    # plano médio z = a x + b y + c (mínimos quadrados)
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    mz = sum(p[2] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    sxz = sum((p[0] - mx) * (p[2] - mz) for p in pts)
    syz = sum((p[1] - my) * (p[2] - mz) for p in pts)
    det = sxx * syy - sxy * sxy
    a = (sxz * syy - syz * sxy) / det if det else 0.0
    b = (syz * sxx - sxz * sxy) / det if det else 0.0
    medio = math.hypot(a, b) * 100
    orient = (math.degrees(math.atan2(-a, -b)) + 360) % 360     # sentido da descida
    maximo = 0.0
    for i, p in enumerate(pts):
        for q in pts[i + 1:]:
            d = math.hypot(p[0] - q[0], p[1] - q[1])
            if 0 < d <= max(sx, sy) * 1.5:
                maximo = max(maximo, abs(p[2] - q[2]) / d * 100)
    zmin, zmax = min(p[2] for p in pts), max(p[2] for p in pts)
    rumos = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    res_m = r["data"].get("resolucao_m")
    pequeno = res_m and max(maxx - minx, maxy - miny) < 2 * res_m
    return G._res(True, {
        "declive_medio_pct": round(medio, 1), "declive_max_pct": round(max(maximo, medio), 1),
        "classe": _classe_declive(medio), "desnivel_m": round(zmax - zmin, 1), "cota_min": round(zmin, 1),
        "cota_max": round(zmax, 1), "exposicao": rumos[int((orient + 22.5) // 45) % 8] if medio >= 2 else "plano",
        "com_desnivel": medio >= 5 or (zmax - zmin) >= 2.0, "amostras": len(pts),
        "pontos": [{"latlon": _ll((x, y)), "z": round(z, 1)} for x, y, z in pts],
        "aviso_resolucao": bool(pequeno), "resolucao_m": res_m, "tipo_modelo": r["data"].get("tipo"),
        "verificacao": r["data"].get("verificacao"),
    }, r["fonte"], r.get("url"), r.get("nota"))


# ------------------------------------------------------------------ orquestração
def _n(v: float, d: int = 1) -> str:
    """Número à portuguesa (vírgula decimal, espaço nos milhares)."""
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def _alertas(res: Dict[str, Any]) -> List[Dict[str, str]]:
    al: List[Dict[str, str]] = []

    def add(nivel, txt):
        al.append({"nivel": nivel, "texto": txt})

    g = res["geometria"]
    for a in g.get("avisos", []):
        add("aviso", a)
    b = res.get("bupi") or {}
    if b.get("ok"):
        for r in (b["data"] or {}).get("rgg", []):
            pct = round(r["fracao_amostras"] * 100)
            add("critico" if pct >= 30 else "aviso",
                f"Já existe uma RGG no BUPi ({r['id']}) em cerca de {pct} % do terreno: confirme as estremas com o titular antes de submeter.")
    elif b and not b.get("ok"):
        add("info", "Não foi possível consultar as RGG do BUPi neste momento — repita a análise antes de submeter.")
    c = res.get("cadastro") or {}
    if c.get("ok"):
        m = (c["data"] or {}).get("melhor_correspondencia")
        if m:
            add("info", f"O terreno coincide em {round(m['iou'] * 100)} % com um prédio da Carta Cadastral"
                        f"{' (' + m['referencia'] + ')' if m['referencia'] else ''}. Pode usar o limite oficial.")
        elif (c["data"] or {}).get("predios"):
            add("aviso", f"O terreno cruza {len(c['data']['predios'])} prédio(s) cadastrado(s) sem coincidir com nenhum.")
    k = res.get("caop") or {}
    if k.get("ok") and k["data"]["atravessa_limite"]:
        add("aviso", "O terreno atravessa um limite de freguesia (CAOP): confirme a freguesia de inscrição matricial.")
    s = res.get("servidoes") or {}
    if s.get("ok"):
        d = s["data"]
        for e in d["afeta"]:
            nivel = "critico" if e["tipo"] in ("RAN", "REN") and e["fracao"] >= 0.05 else "aviso"
            if e["area_afetada_m2"] > 0.5:
                add(nivel, f"{e['titulo']}: {_n(e['fracao'] * 100)} % do terreno ({_n(e['area_afetada_m2'], 0)} m²).")
            else:
                add(nivel, f"{e['titulo']}: atravessa ou toca o terreno.")
        for e in d["hidricos"]:
            if e not in d["afeta"]:
                add("aviso", f"{e['titulo']} a {_n(e['distancia_m'], 0)} m do terreno — verificar margens e domínio hídrico.")
        if d["incompleta"]:
            add("info", f"{len(d['por_confirmar'])} tema(s) de servidões ficaram por confirmar (serviço da DGT lento).")
    elif s:
        add("info", "Servidões e restrições por confirmar (serviço da DGT indisponível).")
    dcl = res.get("declives") or {}
    if dcl.get("ok") and dcl["data"]["com_desnivel"]:
        add("info", f"Terreno com desnível ({_n(dcl['data']['desnivel_m'])} m, declive médio {_n(dcl['data']['declive_medio_pct'])} %): "
                    "carta de declives e levantamento topográfico recomendados.")
    ordem = {"critico": 0, "aviso": 1, "info": 2}
    al.sort(key=lambda a: ordem.get(a["nivel"], 3))
    return al


async def analisar(anel: Any, prazo_s: float = 90.0) -> Dict[str, Any]:
    """Análise completa do terreno. Levanta GeometriaInvalida se o polígono não for válido."""
    geom = GM.medir(anel)
    pts = geom["anel_latlon"]
    poly_m = GM.poligono_m(pts)
    bbox = GM.bbox_txt(pts, 2.0)
    interiores = [_ll(p) for p in _pontos_interiores(poly_m)]

    async def seguro(nome, coro):
        try:
            return await asyncio.wait_for(coro, timeout=prazo_s)
        except asyncio.TimeoutError:
            return G._res(False, nota=f"{nome}: sem resposta a tempo")
        except Exception as e:  # noqa: BLE001 — um tema falhado não pode parar a análise
            return G._res(False, nota=f"{nome}: erro ({type(e).__name__})")

    r_caop, r_cad, r_bupi, r_crus, r_srup, r_dcl = await asyncio.gather(
        seguro("CAOP", caop(poly_m, bbox)),
        seguro("cadastro", cadastro(poly_m, bbox)),
        seguro("BUPi", B.rgg_no_terreno(interiores)),
        seguro("PDM", crus(poly_m, bbox)),
        seguro("servidões", servidoes(poly_m, pts, prazo_s=max(10.0, prazo_s - 10))),
        seguro("declives", declives(poly_m)),
    )
    res = {"geometria": geom, "caop": r_caop, "cadastro": r_cad, "bupi": r_bupi, "pdm": r_crus,
           "servidoes": r_srup, "declives": r_dcl,
           "aviso_legal": ("Análise técnica indicativa sobre dados oficiais abertos. Não substitui a Representação Gráfica "
                           "Georreferenciada (RGG) no BUPi, o registo predial, a certidão de PDM nem o levantamento topográfico.")}
    res["alertas"] = _alertas(res)
    temas = ("caop", "cadastro", "bupi", "pdm", "servidoes", "declives")
    res["estado"] = {t: ("ok" if res[t].get("ok") and not (res[t].get("data") or {}).get("incompleta") else
                         "parcial" if res[t].get("ok") else "por_confirmar") for t in temas}
    return res
