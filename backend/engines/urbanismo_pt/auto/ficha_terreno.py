"""Ficha oficial do terreno a partir de um par de coordenadas (ou do polígono do terreno).

Consulta DIRETA dos serviços oficiais da DGT (OGC API), com geometria, e cruza-os com o polígono do terreno:

* CAOP — distrito, município (DICO) e freguesia (DICOFRE) que contêm o ponto;
* lugar — povoação/lugar mais próximo (OpenStreetMap, geocodificação inversa);
* PDM — classe e categoria de espaço da Carta do Regime de Uso do Solo (CRUS) que tocam o terreno, com a % de área;
* REN e RAN — interseção com o terreno (% e m²) ou distância ao limite mais próximo;
* outras servidões (domínio hídrico, Rede Natura, perigosidade de incêndio, estradas, linhas elétricas…) — distância;
* cadastro predial — prédio que contém o ponto (quando existe cadastro geométrico).

Daqui sai um parecer prévio honesto («compatível em princípio», «condicionado», «inviável», «por confirmar») com o
fundamento e a fonte de cada linha, e a planta de condicionantes sobre o ortofotomapa (terreno, casa, REN, RAN, PDM).
Nada é inventado: o que um serviço não devolve fica «por confirmar».
"""
from __future__ import annotations

import asyncio
import io
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import unary_union

from engines.urbanismo_pt.auto import geo as G

LatLon = Tuple[float, float]

# coleções da DGT (ids publicados em ogcapi.dgterritorio.gov.pt/collections)
REN = ("srup_ren_areal", "srup_ren_linear")
RAN = ("srup_ran",)
OUTRAS = ("srup_areas_protegidas", "srup_zec", "srup_zpe", "srup_perigosidade_inc_rural", "srup_albufeiras",
          "srup_aquiferos", "srup_rede_viaria", "srup_rede_ferroviaria", "srup_rede_eletrica", "srup_defesa_militar",
          "srup_defesa_militar_zonas", "srup_aeronautica", "srup_marcos_geod", "srup_arvores_areal", "linhas_agua")
RAIO_VIZINHANCA_M = 150.0
NOMES = {"linhas_agua": "Linhas de água (hidrografia)", "srup_rede_eletrica": "Rede elétrica", "srup_rede_viaria": "Rede rodoviária nacional",
         "srup_rede_ferroviaria": "Rede ferroviária", "srup_perigosidade_inc_rural": "Perigosidade de incêndio rural",
         "srup_albufeiras": "Albufeiras de águas públicas", "srup_aquiferos": "Captações de água subterrânea",
         "srup_areas_protegidas": "Áreas protegidas", "srup_zec": "Rede Natura — ZEC", "srup_zpe": "Rede Natura — ZPE",
         "srup_defesa_militar": "Defesa nacional", "srup_defesa_militar_zonas": "Defesa nacional (zonas)",
         "srup_aeronautica": "Servidão aeronáutica", "srup_marcos_geod": "Marcos geodésicos", "srup_arvores_areal": "Árvores de interesse público"}


# ------------------------------------------------------------------ geometria (projeção local métrica)
class Local:
    """Projeção equirretangular local (erro < 0,1 % a poucas centenas de metros): graus ↔ metros."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111_320.0 * math.cos(math.radians(lat0))
        self.ky = 110_574.0

    def m(self, lon: float, lat: float) -> Tuple[float, float]:
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    def geom(self, g: dict):
        """GeoJSON (lon/lat) → geometria shapely em metros."""
        def conv(c):
            if isinstance(c[0], (int, float)):
                return list(self.m(c[0], c[1]))
            return [conv(x) for x in c]
        return shape({"type": g["type"], "coordinates": conv(g["coordinates"])})


def _bbox_m(lat: float, lon: float, poly_ll: Sequence[LatLon], margem_m: float) -> str:
    lats = [p[0] for p in poly_ll] or [lat]
    lons = [p[1] for p in poly_ll] or [lon]
    dlat = margem_m / 110_574.0
    dlon = margem_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return f"{min(lons) - dlon},{min(lats) - dlat},{max(lons) + dlon},{max(lats) + dlat}"


def terreno_aproximado(lat: float, lon: float, area_m2: float = 1000.0) -> List[LatLon]:
    """Quadrado com a área indicada centrado no ponto (quando não há cadastro nem levantamento)."""
    s = math.sqrt(max(area_m2, 50.0)) / 2
    dlat = s / 110_574.0
    dlon = s / (111_320.0 * math.cos(math.radians(lat)))
    return [(lat - dlat, lon - dlon), (lat - dlat, lon + dlon), (lat + dlat, lon + dlon), (lat + dlat, lon - dlon)]


# ------------------------------------------------------------------ consultas
async def _itens(col: str, bbox: str, limit: int = 50) -> Optional[List[dict]]:
    return await G._dgt_items(col, bbox, limit)


def _props(f: dict) -> Dict[str, str]:
    return G._props_text(f.get("properties"))


def _cruzar(feats: List[dict], L: Local, terreno, ponto) -> Dict[str, Any]:
    """Interseção (m², % do terreno) e distância mínima (m) de um conjunto de elementos ao terreno."""
    area_t = terreno.area or 1.0
    inter, dist, toca = 0.0, None, []
    for f in feats or []:
        g = f.get("geometry")
        if not g:
            continue
        try:
            s = L.geom(g)
        except Exception:  # noqa: BLE001 — geometria inválida da fonte: ignora este elemento
            continue
        if not s.is_valid:
            s = s.buffer(0)
        d = s.distance(terreno)
        dist = d if dist is None else min(dist, d)
        if s.intersects(terreno):
            a = s.intersection(terreno).area if s.geom_type in ("Polygon", "MultiPolygon") else 0.0
            inter += a
            toca.append({"props": _props(f), "area_m2": round(a, 1), "sobre_o_ponto": s.contains(ponto)})
    return {"area_m2": round(min(inter, area_t), 1), "pct": round(100 * min(inter, area_t) / area_t, 1),
            "distancia_m": None if dist is None else round(dist, 1), "elementos": toca, "n": len(feats or [])}


async def lugar(lat: float, lon: float) -> Optional[str]:
    st, js = await G._get(f"{G.NOMINATIM}/reverse", {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 16, "format": "jsonv2",
                                                    "accept-language": "pt-PT"})
    a = (js or {}).get("address") or {}
    return a.get("hamlet") or a.get("isolated_dwelling") or a.get("locality") or a.get("neighbourhood") or a.get("village")


async def ficha(lat: float, lon: float, poligono_latlon: Optional[Sequence[LatLon]] = None,
                area_m2: Optional[float] = None) -> Dict[str, Any]:
    """Ficha oficial do terreno. `poligono_latlon`: limites do terreno [(lat, lon), …]; sem ele usa o prédio do cadastro
    (se existir) ou um quadrado com `area_m2` à volta do ponto (indicado como aproximação)."""
    fontes: List[Dict[str, str]] = []
    por_confirmar: List[str] = []
    origem_limite = "indicado"
    poly = list(poligono_latlon or [])
    cad = None
    if len(poly) < 3:
        cad = await G.cadastro(lat, lon)
        if cad["ok"]:
            poly = [(p[1], p[0]) for p in cad["data"]["anel_lonlat"]]
            origem_limite = "cadastro predial (DGT)"
            fontes.append({"fonte": cad["fonte"], "url": cad.get("url")})
        else:
            poly = terreno_aproximado(lat, lon, area_m2 or 1000.0)
            origem_limite = f"aproximado (quadrado de {round(area_m2 or 1000)} m² centrado no ponto)"
    L = Local(lat, lon)
    terreno = Polygon([L.m(p[1], p[0]) for p in poly]).buffer(0)
    ponto = Point(L.m(lon, lat))
    bbox_t = _bbox_m(lat, lon, poly, 5.0)
    bbox_v = _bbox_m(lat, lon, poly, RAIO_VIZINHANCA_M)
    tiny = G._tiny_bbox(lat, lon)

    cols_publicadas = {c["id"] for c in await G.dgt_collections()}
    pedidos = {"municipios": _itens("municipios", tiny, 3), "freguesias": _itens("freguesias", tiny, 3),
               "crus": _itens("crus", bbox_t, 30), "lugar": lugar(lat, lon)}
    for c in REN + RAN + OUTRAS:
        if not cols_publicadas or c in cols_publicadas:
            pedidos[c] = _itens(c, bbox_v, 50)
    chaves = list(pedidos)
    sem = asyncio.Semaphore(4)

    async def um(coro):
        async with sem:
            return await coro
    res = dict(zip(chaves, await asyncio.gather(*(um(pedidos[k]) for k in chaves), return_exceptions=True)))
    res = {k: (None if isinstance(v, BaseException) else v) for k, v in res.items()}

    # CAOP
    adm: Dict[str, Any] = {}
    if res["municipios"]:
        p = _props(res["municipios"][0])
        adm.update(municipio=G._pick(p, "municipio", "concelho", "nome"), distrito=G._pick(p, "distrito"),
                   dico=G._pick(p, "dtmn", "dico", "dtcc"), nuts3=G._pick(p, "nuts3"), nuts2=G._pick(p, "nuts2"))
        fontes.append({"fonte": "DGT — CAOP (municípios)", "url": f"{G.DGT}/collections/municipios"})
    else:
        por_confirmar.append("município (CAOP)")
    if res["freguesias"]:
        p = _props(res["freguesias"][0])
        adm.update(freguesia=G._pick(p, "freguesia", "nome", "designacao"),
                   dicofre=G._pick(p, "dtmnfr", "dicofre", "dtccfr", "cod"))
        fontes.append({"fonte": "DGT — CAOP (freguesias)", "url": f"{G.DGT}/collections/freguesias"})
    else:
        por_confirmar.append("freguesia e DICOFRE (CAOP)")
    adm["lugar"] = res.get("lugar")

    # PDM (CRUS) — todas as classes que tocam o terreno, com a % de área
    pdm: List[Dict[str, Any]] = []
    if res["crus"] is None:
        por_confirmar.append("classe de espaço do PDM (CRUS)")
    else:
        cr = _cruzar(res["crus"], L, terreno, ponto)
        for e in sorted(cr["elementos"], key=lambda e: -e["area_m2"]):
            c = G.classificar_solo(e["props"])
            pdm.append({"classe": G._pick(e["props"], "classe_2021", "classe") or c["classe"],
                        "categoria": G._pick(e["props"], "categoria_2021", "categoria") or c["categoria"],
                        "designacao": G._pick(e["props"], "designacao_no_plano", "designacao"),
                        "solo": c["solo"], "pct_terreno": round(100 * e["area_m2"] / (terreno.area or 1), 1),
                        "sobre_o_ponto": e["sobre_o_ponto"], "pdm_registo": G._pick(e["props"], "registo"),
                        "pdm_situacao": G._pick(e["props"], "situacao"), "pdm_data": G._pick(e["props"], "data_pub")})
        fontes.append({"fonte": "DGT — Carta do Regime de Uso do Solo (PDM)", "url": f"{G.DGT}/collections/crus"})
        if not pdm:
            por_confirmar.append("classe de espaço do PDM (sem polígono CRUS no terreno)")

    def restr(cols):
        feats, falhou = [], []
        for c in cols:
            if c not in res:
                continue
            if res[c] is None:
                falhou.append(c)
            else:
                feats += res[c]
        if falhou and not feats:
            return None
        return _cruzar(feats, L, terreno, ponto) | {"incompleto": bool(falhou)}

    ren, ran = restr(REN), restr(RAN)
    if ren is None:
        por_confirmar.append("REN")
    else:
        fontes.append({"fonte": "DGT — SRUP Reserva Ecológica Nacional", "url": f"{G.DGT}/collections/srup_ren_areal"})
    if ran is None:
        por_confirmar.append("RAN")
    else:
        fontes.append({"fonte": "DGT — SRUP Reserva Agrícola Nacional", "url": f"{G.DGT}/collections/srup_ran"})
    outras = []
    for c in OUTRAS:
        if res.get(c):
            x = _cruzar(res[c], L, terreno, ponto)
            tit = NOMES.get(c) or next((k["title"] for k in G._COLLECTIONS.get("list") or [] if k["id"] == c), c)
            p0 = _props(res[c][0])
            outras.append({"id": c, "titulo": tit, "distancia_m": x["distancia_m"], "pct": x["pct"],
                           "tipo": G._pick(p0, "tipologia", "servidao", "designacao", "nome")})
    outras.sort(key=lambda o: (o["distancia_m"] is None, o["distancia_m"] or 0))

    parecer = _parecer(pdm, ren, ran, outras, por_confirmar)
    return {"ok": True, "ponto": {"lat": lat, "lon": lon}, "terreno": {"poligono_latlon": poly, "area_m2": round(terreno.area, 1),
                                                                       "origem_limite": origem_limite,
                                                                       "cadastro": (cad or {}).get("data", {}).get("props") if cad and cad["ok"] else None},
            "administrativo": adm, "pdm": pdm, "ren": ren, "ran": ran, "outras_servidoes": outras,
            "parecer": parecer, "por_confirmar": por_confirmar, "fontes": fontes,
            "nota": "Parecer prévio automático a partir dos dados abertos oficiais. Não substitui o pedido de informação "
                    "prévia (PIP) nem a planta de condicionantes oficial do PDM emitida pela câmara."}


def _parecer(pdm, ren, ran, outras, por_confirmar) -> Dict[str, Any]:
    motivos, condicoes = [], []
    estado = "compativel"
    urb = [p for p in pdm if p["solo"] == "urbano"]
    rus = [p for p in pdm if p["solo"] == "rustico"]
    if rus and sum(p["pct_terreno"] for p in rus) >= 50:
        estado = "inviavel"
        motivos.append(f"PDM: {sum(p['pct_terreno'] for p in rus):.0f} % do terreno é solo rústico "
                       f"({rus[0]['categoria'] or rus[0]['classe'] or 'rústico'}) — moradia nova só em situações excecionais.")
    elif rus:
        estado = "condicionado"
        condicoes.append(f"PDM: parte do terreno ({sum(p['pct_terreno'] for p in rus):.0f} %) é solo rústico — a casa tem de ficar "
                         f"na parte urbana ({', '.join(sorted({p['categoria'] or '' for p in urb})) or 'solo urbano'}).")
    if urb and not rus:
        motivos.append(f"PDM: {urb[0]['categoria'] or 'solo urbano'} ({urb[0]['pct_terreno']:.0f} % do terreno).")
    for nome, r in (("REN", ren), ("RAN", ran)):
        if r is None:
            continue
        if r["pct"] >= 50:
            estado = "inviavel"
            motivos.append(f"{nome}: {r['pct']:.0f} % do terreno ({r['area_m2']:.0f} m²) está em {nome} — construção em regra "
                           f"interdita (parecer da {'CCDR' if nome == 'REN' else 'entidade regional da RAN'}).")
        elif r["pct"] > 0:
            estado = "condicionado" if estado != "inviavel" else estado
            condicoes.append(f"{nome}: {r['pct']:.0f} % do terreno ({r['area_m2']:.0f} m²) em {nome} — implantar a casa fora "
                             "dessa área.")
        elif r["distancia_m"] is not None and r["distancia_m"] < 20:
            condicoes.append(f"{nome} a {r['distancia_m']:.0f} m do limite do terreno — confirmar na planta de condicionantes.")
        else:
            motivos.append(f"{nome}: o terreno não está abrangido"
                           + (f" (mais próxima a {r['distancia_m']:.0f} m)." if r["distancia_m"] is not None else "."))
    for o in outras:
        if "perigosidade" in (o["id"] + " " + (o.get("titulo") or "")).lower() and re.search(r"baixa", (o.get("tipo") or "").lower()):
            motivos.append(f"Perigosidade de incêndio rural: {o['tipo']} — sem condicionamento à construção por este motivo.")
            continue
        if o["pct"] > 0 or (o["distancia_m"] is not None and o["distancia_m"] < 30):
            condicoes.append(f"{o['titulo']}{' — ' + o['tipo'] if o.get('tipo') else ''}: "
                             + (f"{o['pct']:.0f} % do terreno." if o["pct"] > 0 else f"a {o['distancia_m']:.0f} m."))
    if por_confirmar and estado == "compativel":
        estado = "por_confirmar"
    texto = {"compativel": "Compatível em princípio com uma moradia (sujeito ao regulamento do PDM e ao licenciamento).",
             "condicionado": "Possível com condições: a implantação tem de respeitar as restrições indicadas.",
             "inviavel": "Em regra não é possível construir uma moradia nova neste terreno.",
             "por_confirmar": "Os dados oficiais não responderam todos: falta confirmar " + ", ".join(por_confirmar) + "."}[estado]
    return {"estado": estado, "resumo": texto, "fundamentos": motivos, "condicoes": condicoes}


# ------------------------------------------------------------------ apoio às cartas: ortofoto, coleções, casa indicativa
_ORTO: Dict[Tuple, Dict[str, Any]] = {}


async def _orto(clat: float, clon: float, meia: float, px: int) -> Dict[str, Any]:
    """Ortofotomapa da DGT; a planta e a carta usam o mesmo enquadramento, por isso um só pedido serve as duas."""
    k = (round(clat, 6), round(clon, 6), round(meia, 1), px)
    o = _ORTO.get(k)
    if o is None:
        o = await G.ortofoto(clat, clon, meia, px)
        if o.get("ok"):
            if len(_ORTO) > 16:
                _ORTO.clear()
            _ORTO[k] = o
    return o


async def _colecao(preferida: str, *padroes: str) -> Optional[str]:
    """Id publicado pela DGT para um tema (a lista de coleções muda de nome de tempos a tempos)."""
    cols = [c["id"] for c in await G.dgt_collections()]
    if not cols or preferida in cols:
        return preferida
    for c in cols:
        if any(re.search(p, c, re.I) for p in padroes):
            return c
    return None


def _quadro(f: Dict[str, Any]) -> Tuple[Local, float, float, float, float, float]:
    """Enquadramento comum à planta e à carta: centro do terreno + 80 m de envolvente."""
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    poly = f["terreno"]["poligono_latlon"]
    L = Local(lat, lon)
    xs = [L.m(p[1], p[0])[0] for p in poly]
    ys = [L.m(p[1], p[0])[1] for p in poly]
    meia = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 + 80.0
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return L, cx, cy, meia, lat + cy / L.ky, lon + cx / L.kx


def casa_indicativa(poly_ll: Sequence[LatLon], area_m2: float = 200.0, forma: str = "L", piscina: bool = False,
                    garagem: bool = False, afastamento_m: float = 3.0) -> Dict[str, Any]:
    """Implantação INDICATIVA da casa (polígono à escala) dentro do terreno, alinhada com o lado maior e afastada dos
    limites; usada na ficha quando ainda não há projeto. Em L: corpo + ala com o pátio virado para dentro."""
    from shapely import affinity
    from shapely.geometry import box
    lat0 = sum(p[0] for p in poly_ll) / len(poly_ll)
    lon0 = sum(p[1] for p in poly_ll) / len(poly_ll)
    L = Local(lat0, lon0)
    T = Polygon([L.m(p[1], p[0]) for p in poly_ll]).buffer(0)
    dentro = T.buffer(-afastamento_m)
    if dentro.is_empty:
        dentro = T
    rr = list(T.minimum_rotated_rectangle.exterior.coords)
    lados = [(math.hypot(rr[i + 1][0] - rr[i][0], rr[i + 1][1] - rr[i][1]), rr[i], rr[i + 1]) for i in range(4)]
    _, a, b = max(lados)
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    s = math.sqrt(max(area_m2, 40.0) / 200.0)
    if forma.lower().startswith("l"):
        corpo = box(0, 0, 20 * s, 6.5 * s).union(box(0, 6.5 * s, 7 * s, 16.5 * s))
    else:
        w = math.sqrt(area_m2 * 2.2)
        corpo = box(0, 0, w, area_m2 / w)
    pis = box(7 * s + 2.5, 6.5 * s + 2.5, 7 * s + 12.5, 6.5 * s + 6.5) if piscina else None
    gar = box(20 * s + 2.0, 0, 20 * s + 8.0, 6.0) if garagem else None
    partes = [g for g in (corpo, pis, gar) if g is not None]
    grupo = unary_union(partes)
    c0 = grupo.centroid
    alvo = dentro.centroid
    melhor = None
    for rot in (ang, ang + 180, ang + 90, ang + 270):
        for r in range(0, 41, 2):
            passos = [(0, 0)] if r == 0 else [(r * math.cos(t * math.pi / 8), r * math.sin(t * math.pi / 8)) for t in range(16)]
            for dx, dy in passos:
                def pos(g):
                    g = affinity.translate(g, -c0.x, -c0.y)
                    g = affinity.rotate(g, rot, origin=(0, 0))
                    return affinity.translate(g, alvo.x + dx, alvo.y + dy)
                if dentro.contains(pos(grupo)):
                    melhor = pos
                    break
            if melhor:
                break
        if melhor:
            break
    cabe = melhor is not None
    if not cabe:
        def melhor(g):
            g = affinity.translate(g, -c0.x, -c0.y)
            return affinity.translate(affinity.rotate(g, ang, origin=(0, 0)), alvo.x, alvo.y)

    def ll(g):
        return [(lat0 + y / L.ky, lon0 + x / L.kx) for x, y in list(g.exterior.coords)[:-1]]
    return {"casa": [ll(melhor(corpo))] + ([ll(melhor(gar))] if gar else []), "piscina": ll(melhor(pis)) if pis else None,
            "area_m2": round(corpo.area, 1), "forma": "L" if forma.lower().startswith("l") else "retangular", "cabe": cabe,
            "afastamento_m": afastamento_m}


# ------------------------------------------------------------------ curvas de nível e linhas de água
def _grelha_fina(Z: List[List[Optional[float]]], k: int = 4) -> List[List[Optional[float]]]:
    """Interpolação bilinear da grelha do MDT (curvas mais suaves; não acrescenta informação)."""
    n = len(Z)
    m = (n - 1) * k + 1
    out = [[None] * m for _ in range(m)]
    for J in range(m):
        j, fy = divmod(J, k)
        for I in range(m):
            i, fx = divmod(I, k)
            j1, i1 = min(j + 1, n - 1), min(i + 1, n - 1)
            q = (Z[j][i], Z[j][i1], Z[j1][i], Z[j1][i1])
            if any(v is None for v in q):
                continue
            tx, ty = fx / k, fy / k
            out[J][I] = (q[0] * (1 - tx) + q[1] * tx) * (1 - ty) + (q[2] * (1 - tx) + q[3] * tx) * ty
    return out


def curvas_mdt(dcl: Dict[str, Any], equidistancia: Optional[float] = None) -> Dict[str, Any]:
    """Curvas de nível traçadas do modelo digital de terreno (quadrados marchantes), em metros locais."""
    Z0 = dcl.get("Z")
    if not Z0:
        return {"equidistancia": None, "segmentos": []}
    k = 4
    Z = _grelha_fina(Z0, k)
    passo = dcl["passo_m"] / k
    x0, y0 = dcl["centro"][0] - dcl["meia_m"], dcl["centro"][1] - dcl["meia_m"]
    zs = [v for row in Z for v in row if v is not None]
    lo, hi = min(zs), max(zs)
    eq = equidistancia or (1.0 if hi - lo <= 12 else 2.0 if hi - lo <= 30 else 5.0 if hi - lo <= 80 else 10.0)
    segs = []
    h = math.ceil(lo / eq) * eq
    while h <= hi:
        for j in range(len(Z) - 1):
            for i in range(len(Z) - 1):
                cs = ((Z[j][i], x0 + i * passo, y0 + j * passo), (Z[j][i + 1], x0 + (i + 1) * passo, y0 + j * passo),
                      (Z[j + 1][i + 1], x0 + (i + 1) * passo, y0 + (j + 1) * passo), (Z[j + 1][i], x0 + i * passo, y0 + (j + 1) * passo))
                if any(c[0] is None for c in cs):
                    continue
                pts = []
                for e in range(4):
                    (za, xa, ya), (zb, xb, yb) = cs[e], cs[(e + 1) % 4]
                    if (za - h) * (zb - h) < 0:
                        t = (h - za) / (zb - za)
                        pts.append((xa + t * (xb - xa), ya + t * (yb - ya)))
                if len(pts) >= 2:
                    segs.append((h, pts[0], pts[1]))
                if len(pts) == 4:
                    segs.append((h, pts[2], pts[3]))
        h += eq
    return {"equidistancia": eq, "segmentos": segs, "mestra": eq * 5}


async def _curvas_dgt(bbox: str) -> Tuple[Optional[str], Optional[List[dict]]]:
    col = await _colecao("altimetria_curvas_nivel", r"curva", r"altimetria")
    return col, (await G._dgt_items(col, bbox, 300) if col else None)


async def hidrografia(f: Dict[str, Any], raio_m: float = 600.0) -> Dict[str, Any]:
    """Linhas de água da DGT num raio à volta do terreno, com a distância e o rumo da mais próxima."""
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    L = Local(lat, lon)
    terreno = Polygon([L.m(p[1], p[0]) for p in f["terreno"]["poligono_latlon"]]).buffer(0)
    out: Dict[str, Any] = {"feats": [], "consultado": False, "raio_m": raio_m, "dist_m": None, "rumo": None, "nome": None}
    bb = _bbox_m(lat, lon, f["terreno"]["poligono_latlon"], raio_m)
    for preferida, pads in (("linhas_agua", (r"linha.*agua", r"hidrograf", r"curso.*agua")), ("srup_albufeiras", (r"albufeira",))):
        col = await _colecao(preferida, *pads)
        fe = await G._dgt_items(col, bb, 300) if col else None
        if fe is None:
            continue
        out["consultado"] = True
        out["feats"] += fe
    from shapely.ops import nearest_points
    for ft in out["feats"]:
        try:
            g = L.geom(ft["geometry"])
        except Exception:  # noqa: BLE001
            continue
        d = g.distance(terreno)
        if out["dist_m"] is None or d < out["dist_m"]:
            a, b = nearest_points(terreno, g)
            out.update(dist_m=round(d, 1), rumo=(math.degrees(math.atan2(b.x - a.x, b.y - a.y)) + 360) % 360,
                       nome=G._pick(_props(ft), "nome", "designacao", "toponimo"), alvo=(b.x, b.y))
    nomes = ["norte", "nordeste", "este", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]
    if not out["consultado"]:
        out["txt"] = "hidrografia da DGT indisponível no momento — por confirmar"
    elif out["dist_m"] is None:
        out["txt"] = f"nenhuma linha de água cartografada num raio de {raio_m:.0f} m"
    elif out["dist_m"] < 0.5:
        out["txt"] = "linha de água a atravessar o terreno" + (f" ({out['nome']})" if out["nome"] else "") + \
            " — domínio hídrico: faixa de 10 m non aedificandi"
    else:
        out["txt"] = (f"linha de água mais próxima a {out['dist_m']:.0f} m, para {nomes[int((out['rumo'] + 22.5) // 45) % 8]}"
                      + (f" ({out['nome']})" if out["nome"] else "") + (" — dentro dos 10 m do domínio hídrico" if out["dist_m"] < 10 else ""))
    return out


def _linhas(g: dict):
    t = g.get("type")
    if t == "LineString":
        return [g["coordinates"]]
    if t == "MultiLineString":
        return g["coordinates"]
    if t == "Polygon":
        return [g["coordinates"][0]]
    if t == "MultiPolygon":
        return [p[0] for p in g["coordinates"]]
    return []


def _desenha_relevo_agua(dr, P, Pm, px: int, curvas_dgt, mdt, hidro, font, forte: bool) -> List[str]:
    """Curvas (DGT ou, sem elas, traçadas do MDT), linhas de água e seta para a mais próxima fora do quadro."""
    fontes = []
    cor_c, cor_m = ((120, 80, 40, 230), (95, 55, 20, 255)) if forte else ((200, 150, 90, 220), (170, 110, 50, 255))
    if curvas_dgt:
        for ft in curvas_dgt:
            for ln in _linhas(ft.get("geometry") or {}):
                dr.line([P(c[1], c[0]) for c in ln], fill=cor_c, width=2)
            cota = G._pick(_props(ft), "cota", "altitude", "z", "elev")
            lns = _linhas(ft.get("geometry") or {})
            if cota and lns and lns[0]:
                m = lns[0][len(lns[0]) // 2]
                dr.text(P(m[1], m[0]), str(cota).split(".")[0], fill=cor_m, font=font)
        fontes.append("curvas de nível: DGT — Altimetria")
    elif mdt and mdt["segmentos"]:
        rotulado = set()
        for h, a, b in mdt["segmentos"]:
            mestra = abs(h / mdt["mestra"] - round(h / mdt["mestra"])) < 1e-6
            dr.line([Pm(*a), Pm(*b)], fill=cor_m if mestra else cor_c, width=3 if mestra else 2)
            q = Pm(*a)
            if h not in rotulado and 0.15 * px < q[0] < 0.85 * px and 0.3 * px < q[1] < 0.9 * px:
                if mestra or len(mdt["segmentos"]) < 400:
                    dr.text((q[0] + 3, q[1] - 9), f"{h:.0f}", fill=cor_m, font=font)
                    rotulado.add(h)
        fontes.append(f"curvas de nível (equidistância {mdt['equidistancia']:.0f} m) traçadas do MDT")
    if hidro:
        for ft in hidro["feats"]:
            g = ft.get("geometry") or {}
            if g.get("type") in ("Polygon", "MultiPolygon"):
                for ln in _linhas(g):
                    dr.polygon([P(c[1], c[0]) for c in ln], fill=(60, 140, 240, 150), outline=(30, 110, 230, 255))
            else:
                for ln in _linhas(g):
                    dr.line([P(c[1], c[0]) for c in ln], fill=(30, 110, 230, 255), width=5)
        if hidro["feats"]:
            fontes.append("linhas de água: DGT — Hidrografia")
        if hidro.get("alvo"):
            hidro["_alvo_px"] = Pm(*hidro["alvo"])
    return fontes


def _seta_agua(dr, px: int, hidro: Optional[Dict[str, Any]], font, legenda=(0, 0, 0, 0)) -> None:
    """Linha de água fora do quadro: seta na margem (por cima da legenda) com a distância."""
    if not hidro or not hidro.get("_alvo_px") or hidro.get("dist_m") is None:
        return
    tx, ty = hidro["_alvo_px"]
    if 0 <= tx <= px and 0 <= ty <= px:
        return
    r = math.radians(hidro["rumo"])
    ux, uy = math.sin(r), -math.cos(r)
    t = min((px / 2 - 30) / abs(ux) if abs(ux) > 1e-6 else 1e9, (px / 2 - 30) / abs(uy) if abs(uy) > 1e-6 else 1e9)
    bx, by = px / 2 + ux * t, px / 2 + uy * t
    lx0, ly0, lx1, ly1 = legenda
    if lx0 - 40 <= bx <= lx1 + 40 and ly0 - 40 <= by <= ly1 + 40:   # não tapar a legenda: desliza na margem
        if by <= ly0 + 40:
            bx = lx1 + 70
        else:
            by = ly1 + 70
    ax, ay = bx - ux * 90, by - uy * 90
    dr.line([ax, ay, bx, by], fill=(255, 255, 255, 255), width=12)
    dr.line([ax, ay, bx, by], fill=(30, 110, 230, 255), width=7)
    dr.polygon([(bx + ux * 18, by + uy * 18), (bx - uy * 14, by + ux * 14), (bx + uy * 14, by - ux * 14)], fill=(30, 110, 230, 255))
    lbl = f"linha de água a {hidro['dist_m']:.0f} m" + (f" ({hidro['nome']})" if hidro.get("nome") else "")
    w = 11 * len(lbl)
    lx = min(max(ax - w / 2, 10), px - w - 10)
    ly = min(max(ay + (14 if uy < 0 else -40), 10), px - 90)
    dr.rectangle([lx - 6, ly - 4, lx + w, ly + 26], fill=(255, 255, 255, 235), outline=(30, 110, 230, 255))
    dr.text((lx, ly), lbl, fill=(20, 70, 180, 255), font=font)


def _tracejado(dr, pts, cor, w=5, traco=18, vazio=12) -> None:
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        d = math.hypot(x2 - x1, y2 - y1)
        t = 0.0
        while t < d:
            t2 = min(t + traco, d)
            dr.line([x1 + (x2 - x1) * t / d, y1 + (y2 - y1) * t / d, x1 + (x2 - x1) * t2 / d, y1 + (y2 - y1) * t2 / d], fill=cor, width=w)
            t = t2 + vazio


def _aproximado(f: Dict[str, Any]) -> bool:
    return str(f["terreno"].get("origem_limite", "")).startswith("aproximado")


def _terreno_e_casa(dr, P, f: Dict[str, Any], casa_latlon, piscina_latlon, font) -> None:
    """Limite do terreno e casa. Sem limite real (sem cadastro nem limites indicados) o terreno é tracejado e a casa
    aparece só como contorno de exemplo — não se pode afirmar que cabe ali nem que não colide com o que já existe."""
    poly = f["terreno"]["poligono_latlon"]
    pts = [P(*p) for p in poly] + [P(*poly[0])]
    if _aproximado(f):
        _tracejado(dr, pts, (255, 255, 255, 255), 9)
        _tracejado(dr, pts, (230, 30, 30, 255), 5)
        polys = []
        if casa_latlon:
            polys = casa_latlon if isinstance(casa_latlon[0][0], (list, tuple)) else [casa_latlon]
        for pg in polys + ([piscina_latlon] if piscina_latlon else []):
            q = [P(float(a[0]), float(a[1])) for a in pg]
            _tracejado(dr, q + [q[0]], (255, 220, 60, 255), 4, 10, 7)
        msg = "TERRENO APROXIMADO — sem cadastro: indique os limites ou as coordenadas do terreno"
        w = 9 * len(msg)
        xs = [p[0] for p in pts]
        x0 = min(max((min(xs) + max(xs)) / 2 - w / 2, 10), 1400 - w - 10)
        y0 = max(min(p[1] for p in pts) - 40, 420)
        dr.rectangle([x0 - 6, y0 - 2, x0 + w, y0 + 26], fill=(255, 255, 255, 240), outline=(230, 30, 30, 255))
        dr.text((x0, y0), msg, fill=(200, 20, 20, 255), font=font)
    else:
        dr.line(pts, fill=(230, 30, 30, 255), width=6)
        _desenha_casa(dr, P, casa_latlon, piscina_latlon)


def _desenha_casa(dr, P, casa_latlon, piscina_latlon) -> None:
    if casa_latlon:   # um polígono [(lat, lon)…] ou vários (casa + anexos)
        polys = casa_latlon if isinstance(casa_latlon[0][0], (list, tuple)) else [casa_latlon]
        for pg in polys:
            if len(pg) >= 3:
                dr.polygon([P(float(q[0]), float(q[1])) for q in pg], fill=(255, 210, 60, 215), outline=(30, 30, 30, 255))
                pts = [P(float(q[0]), float(q[1])) for q in pg] + [P(float(pg[0][0]), float(pg[0][1]))]
                dr.line(pts, fill=(30, 30, 30, 255), width=3)
    if piscina_latlon and len(piscina_latlon) >= 3:
        dr.polygon([P(float(q[0]), float(q[1])) for q in piscina_latlon], fill=(70, 190, 235, 230), outline=(20, 90, 150, 255))


# ------------------------------------------------------------------ planta de condicionantes
async def planta_condicionantes(f: Dict[str, Any], casa_latlon: Optional[Sequence] = None, px: int = 1400,
                                dcl: Optional[Dict[str, Any]] = None, hidro: Optional[Dict[str, Any]] = None,
                                piscina_latlon: Optional[Sequence[LatLon]] = None, casa_rotulo: str = "Casa proposta") -> Optional[bytes]:
    """Ortofotomapa oficial com o terreno, a casa proposta (polígono à escala), a REN (verde), a RAN (amarelo), os
    limites do PDM, as curvas de nível e as linhas de água."""
    from PIL import Image, ImageDraw
    from engines.urbanismo_pt import volumes as V
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    poly = f["terreno"]["poligono_latlon"]
    L, cx, cy, meia, clat, clon = _quadro(f)
    o = await _orto(clat, clon, meia, px)
    if o["ok"]:
        base = Image.open(io.BytesIO(o["data"]["png"])).convert("RGB").resize((px, px))
        b = [float(v) for v in o["data"]["bbox"].split(",")]
    else:
        base = Image.new("RGB", (px, px), (236, 234, 226))
        dlat, dlon = meia / L.ky, meia / L.kx
        b = [clon - dlon, clat - dlat, clon + dlon, clat + dlat]

    def P(la, lo):
        return ((lo - b[0]) / (b[2] - b[0]) * px, (b[3] - la) / (b[3] - b[1]) * px)

    def Pm(x, y):
        return P(lat + y / L.ky, lon + x / L.kx)
    over = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    dr = ImageDraw.Draw(over)
    bbox = f"{b[0]},{b[1]},{b[2]},{b[3]}"

    def desenha(feats, cor, contorno):
        for ft in feats or []:
            g = ft.get("geometry") or {}
            polys = [g["coordinates"]] if g.get("type") == "Polygon" else (g.get("coordinates") or []) if g.get("type") == "MultiPolygon" else []
            for pg in polys:
                if pg and len(pg[0]) >= 3:
                    dr.polygon([P(c[1], c[0]) for c in pg[0]], fill=cor, outline=contorno)
            if g.get("type") in ("LineString", "MultiLineString"):
                for ln in _linhas(g):
                    dr.line([P(c[1], c[0]) for c in ln], fill=contorno, width=4)
    for c, cor, cont in ((RAN[0], (240, 200, 40, 90), (200, 150, 0, 255)), (REN[0], (40, 170, 80, 90), (20, 120, 50, 255)),
                         (REN[1], (40, 170, 80, 90), (20, 120, 50, 255))):
        desenha(await G._dgt_items(c, bbox, 100), cor, cont)
    for ft in await G._dgt_items("crus", bbox, 50) or []:   # limites e designação do PDM
        g = ft.get("geometry") or {}
        polys = [g["coordinates"]] if g.get("type") == "Polygon" else (g.get("coordinates") or []) if g.get("type") == "MultiPolygon" else []
        for pg in polys:
            if pg and len(pg[0]) >= 3:
                dr.line([P(c[1], c[0]) for c in pg[0]] + [P(pg[0][0][1], pg[0][0][0])], fill=(180, 40, 160, 220), width=3)
    _, curvas = await _curvas_dgt(bbox)
    if hidro is None:
        hidro = await hidrografia(f)
    fontes_rel = _desenha_relevo_agua(dr, P, Pm, px, curvas, None if curvas else (curvas_mdt(dcl) if dcl and dcl.get("ok") else None),
                                      hidro, V._font(15), forte=False)
    img = Image.alpha_composite(base.convert("RGBA"), over)
    dr = ImageDraw.Draw(img)
    _terreno_e_casa(dr, P, f, casa_latlon, piscina_latlon, V._font(15))
    dr.ellipse([P(lat, lon)[0] - 7, P(lat, lon)[1] - 7, P(lat, lon)[0] + 7, P(lat, lon)[1] + 7], fill=(230, 30, 30, 255))
    # legenda
    itens = [("r", (230, 30, 30), "Limite do terreno — " + f["terreno"]["origem_limite"].split(" (")[0][:30])]
    if casa_latlon:
        itens.append(("r", (255, 210, 60), ("Exemplo de implantação (posição a confirmar)" if _aproximado(f) else
                                           casa_rotulo.replace(" (implantação indicativa)", " (indicativa)"))[:46]))
    if piscina_latlon:
        itens.append(("r", (70, 190, 235), "Piscina"))
    itens += [("r", (40, 170, 80), "REN (DGT)"), ("r", (240, 200, 40), "RAN (DGT)"), ("r", (180, 40, 160), "Limites de classes do PDM (CRUS)"),
              ("l", (120, 80, 40), "Curvas de nível" + (" (DGT)" if curvas else " (MDT)" if dcl and dcl.get("ok") else " — indisponíveis")),
              ("l", (30, 110, 230), "Linhas de água (DGT)")]
    x0, y0 = 20, 20
    alt = 22 + len(itens) * 34 + 40
    dr.rectangle([x0, y0, x0 + 560, y0 + alt], fill=(255, 255, 255, 235), outline=(60, 60, 60, 255))
    for k, (tipo, cor, t) in enumerate(itens):
        yy = y0 + 16 + k * 34
        if tipo == "r":
            dr.rectangle([x0 + 14, yy, x0 + 44, yy + 22], fill=cor + (255,))
        else:
            dr.line([x0 + 14, yy + 11, x0 + 44, yy + 11], fill=cor + (255,), width=4)
        dr.text((x0 + 56, yy), t, fill=(20, 20, 20, 255), font=V._font(18))
    import textwrap
    for k, ln in enumerate(textwrap.wrap("Água: " + (hidro or {}).get("txt", "por confirmar"), 62)[:2]):
        dr.text((x0 + 14, y0 + 14 + len(itens) * 34 + k * 18), ln, fill=(20, 70, 180, 255), font=V._font(15))
    _seta_agua(dr, px, hidro, V._font(18), (x0, y0, x0 + 560, y0 + alt))
    # norte e escala gráfica
    dr.polygon([(px - 60, 40), (px - 75, 85), (px - 60, 75), (px - 45, 85)], fill=(20, 20, 20, 255))
    dr.text((px - 67, 90), "N", fill=(20, 20, 20, 255), font=V._font(20))
    m_px = px / (2 * meia)
    esc = 50 if meia > 120 else 20
    dr.rectangle([px - 40 - esc * m_px - 10, px - 100, px - 30, px - 58], fill=(255, 255, 255, 230))
    dr.line([px - 40 - esc * m_px, px - 70, px - 40, px - 70], fill=(20, 20, 20, 255), width=5)
    dr.text((px - 40 - esc * m_px, px - 98), f"0      {esc} m", fill=(20, 20, 20, 255), font=V._font(16))
    adm = f["administrativo"]
    rod = " · ".join(x for x in (adm.get("lugar"), adm.get("freguesia") and f"{adm['freguesia']} (DICOFRE {adm.get('dicofre') or '?'})",
                                 adm.get("municipio"), adm.get("distrito")) if x)
    fonte_orto = o.get("fonte") if o["ok"] else "ortofotomapa indisponível no momento"
    dr.rectangle([0, px - 46, px, px], fill=(255, 255, 255, 235))
    dr.text((16, px - 36), (rod + f" · {lat:.6f}, {lon:.6f} · {fonte_orto}")[:150], fill=(20, 20, 20, 255), font=V._font(17))
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()


# ------------------------------------------------------------------ carta de declives e recursos hídricos
CLASSES_DECLIVE = ((0, 5, (120, 200, 110), "0–5 %"), (5, 10, (200, 225, 100), "5–10 %"), (10, 15, (250, 210, 90), "10–15 %"),
                   (15, 25, (240, 140, 60), "15–25 %"), (25, 999, (200, 50, 50), "> 25 %"))


async def declives(f: Dict[str, Any], n: int = 17) -> Dict[str, Any]:
    """Grelha de cotas (EU-DEM 25 m Copernicus ou Google Elevation) sobre o terreno e envolvente → declive por célula,
    declive médio e máximo do terreno, desnível e sentido de escoamento."""
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    poly = f["terreno"]["poligono_latlon"]
    L, cx, cy, meia, _, _ = _quadro(f)
    passo = 2 * meia / (n - 1)
    pts = [(cx - meia + i * passo, cy - meia + j * passo) for j in range(n) for i in range(n)]
    ll = [(lat + y / L.ky, lon + x / L.kx) for x, y in pts]
    el = await G.elevacoes(ll)
    if not el["ok"]:
        return {"ok": False, "nota": el.get("nota") or "altimetria indisponível"}
    z = el["data"]["z"]
    Z = [[z[j * n + i] for i in range(n)] for j in range(n)]
    terreno = Polygon([L.m(p[1], p[0]) for p in poly]).buffer(0)
    cel, dentro = [], []
    for j in range(n - 1):
        for i in range(n - 1):
            q = [Z[j][i], Z[j][i + 1], Z[j + 1][i], Z[j + 1][i + 1]]
            if any(v is None for v in q):
                continue
            gx = ((q[1] - q[0]) + (q[3] - q[2])) / (2 * passo)
            gy = ((q[2] - q[0]) + (q[3] - q[1])) / (2 * passo)
            d = 100 * math.hypot(gx, gy)
            x0, y0 = cx - meia + i * passo, cy - meia + j * passo
            c = {"x0": x0, "y0": y0, "x1": x0 + passo, "y1": y0 + passo, "declive_pct": round(d, 1), "gx": gx, "gy": gy}
            cel.append(c)
            if terreno.intersects(Polygon([(x0, y0), (x0 + passo, y0), (x0 + passo, y0 + passo), (x0, y0 + passo)])):
                dentro.append(c)
    zt = [Z[j][i] for j in range(n) for i in range(n) if Z[j][i] is not None
          and terreno.buffer(passo / 2).contains(Point(cx - meia + i * passo, cy - meia + j * passo))]
    gxm = sum(c["gx"] for c in dentro) / len(dentro) if dentro else 0.0
    gym = sum(c["gy"] for c in dentro) / len(dentro) if dentro else 0.0
    rumo = (math.degrees(math.atan2(-gxm, -gym)) + 360) % 360      # sentido em que a água corre (para baixo)
    nomes = ["norte", "nordeste", "este", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]
    return {"ok": True, "celulas": cel, "passo_m": round(passo, 3), "centro": (cx, cy), "meia_m": meia, "Z": Z,
            "declive_medio_pct": round(sum(c["declive_pct"] for c in dentro) / len(dentro), 1) if dentro else None,
            "declive_max_pct": max((c["declive_pct"] for c in dentro), default=None),
            "desnivel_m": round(max(zt) - min(zt), 1) if zt else None, "cota_min_m": min(zt) if zt else None,
            "cota_max_m": max(zt) if zt else None, "escoamento_para": nomes[int((rumo + 22.5) // 45) % 8],
            "escoamento_rumo": round(rumo), "fonte": el["fonte"], "resolucao_m": el["data"].get("resolucao_m")}


def _raster_declives(dcl: Dict[str, Any], Pm, px: int):
    """Classes de declive em mancha contínua: declive calculado na grelha do MDT afinada (interpolação bilinear) e
    imagem suavizada — sem os quadrados de 25 m."""
    from PIL import Image, ImageFilter
    k = 6
    Z = _grelha_fina(dcl["Z"], k)
    m = len(Z)
    h = dcl["passo_m"] / k
    x0, y0 = dcl["centro"][0] - dcl["meia_m"], dcl["centro"][1] - dcl["meia_m"]
    img = Image.new("RGBA", (m - 1, m - 1), (0, 0, 0, 0))
    pix = img.load()
    for j in range(m - 1):
        for i in range(m - 1):
            q = (Z[j][i], Z[j][i + 1], Z[j + 1][i], Z[j + 1][i + 1])
            if any(v is None for v in q):
                continue
            gx = ((q[1] - q[0]) + (q[3] - q[2])) / (2 * h)
            gy = ((q[2] - q[0]) + (q[3] - q[1])) / (2 * h)
            d = 100 * math.hypot(gx, gy)
            cor = next(c[2] for c in CLASSES_DECLIVE if c[0] <= d < c[1])
            pix[i, m - 2 - j] = cor + (105,)          # linha 0 da imagem = norte
    a = Pm(x0, y0 + (m - 1) * h)
    b = Pm(x0 + (m - 1) * h, y0)
    w, hh = max(1, int(round(b[0] - a[0]))), max(1, int(round(b[1] - a[1])))
    img = img.resize((w, hh), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    over = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    over.paste(img, (int(round(a[0])), int(round(a[1]))))
    return over


def _seta_escoamento(dr, P, Pm, f: Dict[str, Any], dcl: Dict[str, Any]) -> None:
    """Seta do escoamento a sair do limite do terreno no sentido em que a água corre (não por cima da casa)."""
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    L = Local(lat, lon)
    T = Polygon([L.m(p[1], p[0]) for p in f["terreno"]["poligono_latlon"]]).buffer(0)
    c = T.centroid
    r = math.radians(dcl["escoamento_rumo"])
    from shapely.geometry import LineString
    raio = LineString([(c.x, c.y), (c.x + 1000 * math.sin(r), c.y + 1000 * math.cos(r))])
    sai = raio.intersection(T.exterior)
    p0 = sai if sai.geom_type == "Point" else (list(sai.geoms)[0] if hasattr(sai, "geoms") and len(sai.geoms) else c)
    ax, ay = Pm(p0.x, p0.y)
    bx, by = ax + 120 * math.sin(r), ay - 120 * math.cos(r)
    ax, ay = ax + 12 * math.sin(r), ay - 12 * math.cos(r)
    dr.line([ax, ay, bx, by], fill=(255, 255, 255, 255), width=11)
    dr.line([ax, ay, bx, by], fill=(20, 60, 200, 255), width=6)
    e = (bx + 18 * math.sin(r), by - 18 * math.cos(r))
    dr.polygon([e, (bx - 13 * math.cos(r), by - 13 * math.sin(r)), (bx + 13 * math.cos(r), by + 13 * math.sin(r))], fill=(20, 60, 200, 255))


async def carta_declives(f: Dict[str, Any], dcl: Dict[str, Any], casa_latlon=None, px: int = 1400,
                         hidro: Optional[Dict[str, Any]] = None, piscina_latlon=None) -> Optional[bytes]:
    """Carta de declives (classes) + curvas de nível (DGT; sem elas, traçadas do MDT) + linhas de água e albufeiras
    (DGT) + sentido de escoamento + casa proposta."""
    from PIL import Image, ImageDraw
    from engines.urbanismo_pt import volumes as V
    if not dcl.get("ok"):
        return None
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    L = Local(lat, lon)
    cx, cy = dcl["centro"]
    meia = dcl["meia_m"]
    clat, clon = lat + cy / L.ky, lon + cx / L.kx
    o = await _orto(clat, clon, meia, px)
    if o["ok"]:
        base = Image.open(io.BytesIO(o["data"]["png"])).convert("L").convert("RGB").resize((px, px))
        b = [float(v) for v in o["data"]["bbox"].split(",")]
    else:
        base = Image.new("RGB", (px, px), (236, 234, 226))
        b = [clon - meia / L.kx, clat - meia / L.ky, clon + meia / L.kx, clat + meia / L.ky]

    def P(la, lo):
        return ((lo - b[0]) / (b[2] - b[0]) * px, (b[3] - la) / (b[3] - b[1]) * px)

    def Pm(x, y):
        return P(lat + y / L.ky, lon + x / L.kx)
    over = _raster_declives(dcl, Pm, px)
    img = Image.alpha_composite(base.convert("RGBA"), over)
    dr = ImageDraw.Draw(img)
    bbox = f"{b[0]},{b[1]},{b[2]},{b[3]}"
    fontes = [dcl["fonte"]]
    _, curvas = await _curvas_dgt(bbox)
    if hidro is None:
        hidro = await hidrografia(f)
    mdt = None if curvas else curvas_mdt(dcl)
    fontes += _desenha_relevo_agua(dr, P, Pm, px, curvas, mdt, hidro, V._font(16), forte=True)
    dcl["hidro_txt"] = hidro.get("txt")
    dcl["curvas_fonte"] = "DGT — Altimetria" if curvas else (f"traçadas do MDT ({dcl['fonte']}), equidistância "
                                                             f"{mdt['equidistancia']:.0f} m" if mdt and mdt['segmentos'] else None)
    _terreno_e_casa(dr, P, f, casa_latlon, piscina_latlon, V._font(15))
    _seta_escoamento(dr, P, Pm, f, dcl)
    # legenda
    dr.rectangle([20, 20, 560, 400], fill=(255, 255, 255, 235), outline=(60, 60, 60, 255))
    dr.text((34, 30), "Carta de declives e recursos hídricos", fill=(20, 20, 20, 255), font=V._font(20))
    for k, (_, _, cor, t) in enumerate(CLASSES_DECLIVE):
        dr.rectangle([34, 66 + k * 30, 64, 88 + k * 30], fill=cor + (255,))
        dr.text((74, 66 + k * 30), t, fill=(20, 20, 20, 255), font=V._font(17))
    leg = [((120, 80, 40), 3, "Curvas de nível" + (" (DGT)" if curvas else " (MDT)")), ((30, 110, 230), 5, "Linhas de água (DGT)"),
           ((20, 60, 200), 5, "Escoamento natural"), ((230, 30, 30), 5, "Limite do terreno")]
    for k, (cor, w, t) in enumerate(leg):
        dr.line([200, 76 + k * 30, 240, 76 + k * 30], fill=cor + (255,), width=w)
        dr.text((250, 66 + k * 30), t, fill=(20, 20, 20, 255), font=V._font(17))
    if casa_latlon:
        dr.rectangle([200, 186, 240, 206], fill=(255, 210, 60, 255), outline=(30, 30, 30, 255))
        dr.text((250, 186), "Exemplo de casa (a confirmar)" if _aproximado(f) else "Casa proposta", fill=(20, 20, 20, 255), font=V._font(17))
    txt = (f"Terreno: declive médio {dcl['declive_medio_pct']} % · máx. {dcl['declive_max_pct']} % · desnível "
           f"{dcl['desnivel_m']} m · a água escorre para {dcl['escoamento_para']}")
    import textwrap
    for k, ln in enumerate(textwrap.wrap(txt, 58)[:2]):
        dr.text((34, 226 + k * 22), ln, fill=(20, 20, 20, 255), font=V._font(16))
    for k, ln in enumerate(textwrap.wrap("Água: " + (hidro.get("txt") or ""), 58)[:2]):
        dr.text((34, 278 + k * 22), ln, fill=(20, 70, 180, 255), font=V._font(16))
    ft = "Fontes: " + "; ".join(fontes) + "; " + (o.get("fonte") if o["ok"] else "ortofotomapa indisponível")
    for k, ln in enumerate(textwrap.wrap(ft, 68)[:3]):
        dr.text((34, 330 + k * 20), ln, fill=(80, 80, 80, 255), font=V._font(14))
    _seta_agua(dr, px, hidro, V._font(18), (20, 20, 560, 400))
    dr.polygon([(px - 60, 40), (px - 75, 85), (px - 60, 75), (px - 45, 85)], fill=(20, 20, 20, 255))
    dr.text((px - 67, 90), "N", fill=(20, 20, 20, 255), font=V._font(20))
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()


async def cartas(f: Dict[str, Any], casa_latlon=None, piscina_latlon=None, casa_rotulo: str = "Casa proposta") -> Dict[str, Any]:
    """Planta de condicionantes + (se houver desnível) carta de declives e recursos hídricos, com a hidrografia e a
    altimetria consultadas uma só vez."""
    dcl = await declives(f)
    hidro = await hidrografia(f)
    dcl["hidro_txt"] = hidro.get("txt")
    planta = await planta_condicionantes(f, casa_latlon, dcl=dcl, hidro=hidro, piscina_latlon=piscina_latlon, casa_rotulo=casa_rotulo)
    carta = await carta_declives(f, dcl, casa_latlon, hidro=hidro, piscina_latlon=piscina_latlon) if tem_desnivel(dcl) else None
    return {"planta": planta, "declives": dcl, "carta": carta, "hidro": {k: v for k, v in hidro.items() if k != "feats"}}


def tem_desnivel(dcl: Dict[str, Any]) -> bool:
    return bool(dcl.get("ok") and ((dcl.get("desnivel_m") or 0) >= 1.0 or (dcl.get("declive_medio_pct") or 0) >= 3.0))


# ------------------------------------------------------------------ ficha de condicionantes (PDF A3)
def ficha_pdf(f: Dict[str, Any], planta_png: Optional[bytes], declives_png: Optional[bytes] = None,
              dcl: Optional[Dict[str, Any]] = None, titulo: str = "", casa_txt: Optional[str] = None) -> bytes:
    """Ficha de condicionantes em A3: planta sobre o ortofotomapa + quadro de todos os fatores com a fonte oficial;
    segunda folha com a carta de declives e recursos hídricos, quando o terreno tem desnível."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from engines.urbanismo_pt import pdf as UP
    fn = UP._fonts()
    buf = io.BytesIO()
    W, H = landscape(A3)
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle("Ficha de condicionantes — ConstruPilot")

    def cab(t):
        c.setFillColor(colors.HexColor("#173C32"))
        c.rect(12 * mm, H - 26 * mm, W - 24 * mm, 14 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(fn["bold"], 15)
        c.drawString(18 * mm, H - 21 * mm, t)
        c.setFont(fn["regular"], 9)
        c.drawRightString(W - 18 * mm, H - 21 * mm, f"{f['ponto']['lat']:.6f}, {f['ponto']['lon']:.6f} · {UP._hoje()}")
        c.setStrokeColor(colors.black)
        c.rect(12 * mm, 12 * mm, W - 24 * mm, H - 24 * mm)

    cab("Ficha de condicionantes do terreno" + (f" — {titulo}" if titulo else ""))
    lado = H - 52 * mm
    if planta_png:
        c.drawImage(ImageReader(io.BytesIO(planta_png)), 18 * mm, 18 * mm, lado, lado)
    x = 18 * mm + lado + 10 * mm
    y = H - 36 * mm
    par = f["parecer"]
    cor = {"compativel": "#1D7A46", "condicionado": "#B8860B", "inviavel": "#B22222", "por_confirmar": "#555555"}[par["estado"]]

    def linha(rotulo, valor, fonte=None, bold=False):
        nonlocal y
        c.setFillColor(colors.HexColor("#555555"))
        c.setFont(fn["regular"], 9)
        c.drawString(x, y, rotulo)
        c.setFillColor(colors.black)
        c.setFont(fn["bold"] if bold else fn["regular"], 10.5)
        txt = str(valor if valor not in (None, "") else "por confirmar")
        largura = W - x - 18 * mm - 48 * mm
        palavras, atual, linhas = txt.split(), "", []
        for p_ in palavras:
            t2 = (atual + " " + p_).strip()
            if c.stringWidth(t2, fn["regular"], 10.5) > largura and atual:
                linhas.append(atual)
                atual = p_
            else:
                atual = t2
        linhas.append(atual)
        for k, ln in enumerate(linhas):
            c.drawString(x + 48 * mm, y - k * 4.6 * mm, ln)
        if fonte:
            c.setFillColor(colors.HexColor("#777777"))
            c.setFont(fn["regular"], 7.5)
            c.drawString(x + 48 * mm, y - len(linhas) * 4.6 * mm + 1 * mm, "Fonte: " + fonte)
            y -= 3.2 * mm
        y -= len(linhas) * 4.6 * mm + 2.4 * mm

    c.setFillColor(colors.HexColor(cor))
    c.roundRect(x, y - 16 * mm, W - x - 18 * mm, 18 * mm, 3 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(fn["bold"], 13)
    c.drawString(x + 5 * mm, y - 6 * mm, {"compativel": "COMPATÍVEL EM PRINCÍPIO", "condicionado": "POSSÍVEL COM CONDIÇÕES",
                                          "inviavel": "EM REGRA NÃO É POSSÍVEL CONSTRUIR",
                                          "por_confirmar": "POR CONFIRMAR"}[par["estado"]])
    c.setFont(fn["regular"], 9)
    c.drawString(x + 5 * mm, y - 12 * mm, par["resumo"][:120])
    y -= 26 * mm
    ad = f["administrativo"]
    caop = "DGT — CAOP"
    linha("Distrito", ad.get("distrito"), caop)
    linha("Município (DICO)", f"{ad.get('municipio') or '—'} ({ad.get('dico') or '—'})", caop)
    linha("Freguesia (DICOFRE)", f"{ad.get('freguesia') or '—'} ({ad.get('dicofre') or '—'})", caop)
    linha("Lugar", ad.get("lugar"), "OpenStreetMap (geocodificação inversa)")
    linha("Terreno", f"{f['terreno']['area_m2']:.0f} m² — limite {f['terreno']['origem_limite']}")
    for p in f["pdm"] or [None]:
        linha("PDM (classe / categoria)", p and f"{p['classe']} — {p['categoria']} ({p['pct_terreno']:.0f} % do terreno)"
              + (f"; {p['pdm_situacao']}, registo {p['pdm_registo']}" if p and p.get("pdm_registo") else ""),
              "DGT — Carta do Regime de Uso do Solo (CRUS)", bold=True)
    for nome, r, src in (("REN", f["ren"], "DGT — SRUP REN"), ("RAN", f["ran"], "DGT — SRUP RAN")):
        v = None if r is None else (f"{r['pct']:.0f} % do terreno ({r['area_m2']:.0f} m²)" if r["pct"] > 0 else
                                     "não abrange o terreno" + (f" (limite a {r['distancia_m']:.0f} m)" if r["distancia_m"] is not None else ""))
        linha(nome, v, src, bold=True)
    for o in (f["outras_servidoes"] or [])[:7]:
        linha(o["titulo"].replace("SRUP - ", "")[:40], (f"{o['pct']:.0f} % do terreno" if o["pct"] > 0 else f"a {o['distancia_m']:.0f} m")
              + (f" — {o['tipo']}" if o.get("tipo") else ""), "DGT — SRUP")
    if dcl and dcl.get("ok"):
        linha("Declive do terreno", f"médio {dcl['declive_medio_pct']} %, máx. {dcl['declive_max_pct']} %, desnível "
              f"{dcl['desnivel_m']} m; a água escorre para {dcl['escoamento_para']}", dcl["fonte"])
        if dcl.get("curvas_fonte"):
            linha("Curvas de nível", dcl["curvas_fonte"])
    if dcl and dcl.get("hidro_txt"):
        linha("Recursos hídricos", dcl["hidro_txt"], "DGT — Hidrografia (linhas de água) e SRUP albufeiras")
    if casa_txt:
        linha("Casa proposta", casa_txt)
    for t in par["condicoes"][:5]:
        linha("Condição", t)
    if f["por_confirmar"]:
        linha("Por confirmar", ", ".join(f["por_confirmar"]))
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont(fn["regular"], 7.5)
    c.drawString(18 * mm, 14 * mm, f["nota"][:200])
    c.showPage()
    if declives_png:
        cab("Carta de declives e recursos hídricos" + (f" — {titulo}" if titulo else ""))
        lado = H - 52 * mm
        c.drawImage(ImageReader(io.BytesIO(declives_png)), (W - lado) / 2, 18 * mm, lado, lado)
        c.showPage()
    c.save()
    return buf.getvalue()
