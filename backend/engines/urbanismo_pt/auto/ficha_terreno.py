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


# ------------------------------------------------------------------ planta de condicionantes
async def planta_condicionantes(f: Dict[str, Any], casa_latlon: Optional[Sequence[LatLon]] = None, px: int = 1400) -> Optional[bytes]:
    """Ortofotomapa oficial com o terreno, a casa proposta, a REN (verde), a RAN (amarelo) e os limites do PDM."""
    from PIL import Image, ImageDraw
    from engines.urbanismo_pt import volumes as V
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    poly = f["terreno"]["poligono_latlon"]
    L = Local(lat, lon)
    xs = [L.m(p[1], p[0])[0] for p in poly]
    ys = [L.m(p[1], p[0])[1] for p in poly]
    meia = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 + 80.0
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    clat, clon = lat + cy / L.ky, lon + cx / L.kx
    o = await G.ortofoto(clat, clon, meia, px)
    if o["ok"]:
        base = Image.open(io.BytesIO(o["data"]["png"])).convert("RGB").resize((px, px))
        b = [float(v) for v in o["data"]["bbox"].split(",")]
    else:
        base = Image.new("RGB", (px, px), (236, 234, 226))
        dlat, dlon = meia / L.ky, meia / L.kx
        b = [clon - dlon, clat - dlat, clon + dlon, clat + dlat]

    def P(la, lo):
        return ((lo - b[0]) / (b[2] - b[0]) * px, (b[3] - la) / (b[3] - b[1]) * px)
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
                linhas = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
                for ln in linhas:
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
    img = Image.alpha_composite(base.convert("RGBA"), over)
    dr = ImageDraw.Draw(img)
    dr.line([P(*p) for p in poly] + [P(*poly[0])], fill=(230, 30, 30, 255), width=6)
    if casa_latlon:   # um polígono [(lat, lon)…] ou vários (casa + anexos)
        polys = casa_latlon if isinstance(casa_latlon[0][0], (list, tuple)) else [casa_latlon]
        for pg in polys:
            if len(pg) >= 3:
                dr.polygon([P(float(q[0]), float(q[1])) for q in pg], fill=(255, 210, 60, 210), outline=(40, 40, 40, 255))
    dr.ellipse([P(lat, lon)[0] - 7, P(lat, lon)[1] - 7, P(lat, lon)[0] + 7, P(lat, lon)[1] + 7], fill=(230, 30, 30, 255))
    # legenda
    x0, y0 = 20, 20
    dr.rectangle([x0, y0, x0 + 470, y0 + 210], fill=(255, 255, 255, 235), outline=(60, 60, 60, 255))
    itens = [((230, 30, 30), "Limite do terreno — " + f["terreno"]["origem_limite"][:34]), ((255, 210, 60), "Casa proposta"),
             ((40, 170, 80), "REN (DGT)"), ((240, 200, 40), "RAN (DGT)"), ((180, 40, 160), "Limites de classes do PDM (CRUS)")]
    for k, (cor, t) in enumerate(itens):
        dr.rectangle([x0 + 14, y0 + 16 + k * 36, x0 + 44, y0 + 38 + k * 36], fill=cor + (255,))
        dr.text((x0 + 56, y0 + 16 + k * 36), t, fill=(20, 20, 20, 255), font=V._font(18))
    adm = f["administrativo"]
    rod = " · ".join(x for x in (adm.get("lugar"), adm.get("freguesia") and f"{adm['freguesia']} (DICOFRE {adm.get('dicofre') or '?'})",
                                 adm.get("municipio"), adm.get("distrito")) if x)
    dr.rectangle([0, px - 46, px, px], fill=(255, 255, 255, 235))
    dr.text((16, px - 36), (rod + f" · {lat:.6f}, {lon:.6f}")[:140], fill=(20, 20, 20, 255), font=V._font(18))
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()


# ------------------------------------------------------------------ carta de declives e recursos hídricos
CLASSES_DECLIVE = ((0, 5, (120, 200, 110), "0–5 %"), (5, 10, (200, 225, 100), "5–10 %"), (10, 15, (250, 210, 90), "10–15 %"),
                   (15, 25, (240, 140, 60), "15–25 %"), (25, 999, (200, 50, 50), "> 25 %"))


async def declives(f: Dict[str, Any], n: int = 13) -> Dict[str, Any]:
    """Grelha de cotas (EU-DEM 25 m Copernicus ou Google Elevation) sobre o terreno e envolvente → declive por célula,
    declive médio e máximo do terreno, desnível e sentido de escoamento."""
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    poly = f["terreno"]["poligono_latlon"]
    L = Local(lat, lon)
    xs = [L.m(p[1], p[0])[0] for p in poly]
    ys = [L.m(p[1], p[0])[1] for p in poly]
    meia = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 + 80.0
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
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
    return {"ok": True, "celulas": cel, "passo_m": round(passo, 1), "centro": (cx, cy), "meia_m": meia,
            "declive_medio_pct": round(sum(c["declive_pct"] for c in dentro) / len(dentro), 1) if dentro else None,
            "declive_max_pct": max((c["declive_pct"] for c in dentro), default=None),
            "desnivel_m": round(max(zt) - min(zt), 1) if zt else None, "cota_min_m": min(zt) if zt else None,
            "cota_max_m": max(zt) if zt else None, "escoamento_para": nomes[int((rumo + 22.5) // 45) % 8],
            "escoamento_rumo": round(rumo), "fonte": el["fonte"], "resolucao_m": el["data"].get("resolucao_m")}


async def carta_declives(f: Dict[str, Any], dcl: Dict[str, Any], casa_latlon=None, px: int = 1400) -> Optional[bytes]:
    """Carta de declives (classes) + curvas de nível (DGT) + linhas de água e albufeiras (DGT) + sentido de escoamento."""
    from PIL import Image, ImageDraw
    from engines.urbanismo_pt import volumes as V
    if not dcl.get("ok"):
        return None
    lat, lon = f["ponto"]["lat"], f["ponto"]["lon"]
    L = Local(lat, lon)
    cx, cy = dcl["centro"]
    meia = dcl["meia_m"]
    clat, clon = lat + cy / L.ky, lon + cx / L.kx
    o = await G.ortofoto(clat, clon, meia, px)
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
    over = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    dr = ImageDraw.Draw(over)
    for c in dcl["celulas"]:
        cor = next(k[2] for k in CLASSES_DECLIVE if k[0] <= c["declive_pct"] < k[1])
        a, bb = Pm(c["x0"], c["y1"]), Pm(c["x1"], c["y0"])
        dr.rectangle([a[0], a[1], bb[0], bb[1]], fill=cor + (120,))
    img = Image.alpha_composite(base.convert("RGBA"), over)
    dr = ImageDraw.Draw(img)
    bbox = f"{b[0]},{b[1]},{b[2]},{b[3]}"
    fontes = [dcl["fonte"]]
    curvas = await G._dgt_items("altimetria_curvas_nivel", bbox, 200)
    for ft in curvas or []:
        g = ft.get("geometry") or {}
        linhas = [g["coordinates"]] if g.get("type") == "LineString" else g.get("coordinates") or [] if g.get("type") == "MultiLineString" else []
        for ln in linhas:
            dr.line([P(c[1], c[0]) for c in ln], fill=(120, 80, 40, 255), width=2)
        cota = G._pick(_props(ft), "cota", "altitude", "z", "elev")
        if cota and linhas and linhas[0]:
            m = linhas[0][len(linhas[0]) // 2]
            dr.text(P(m[1], m[0]), str(cota).split(".")[0], fill=(90, 50, 20, 255), font=V._font(15))
    if curvas:
        fontes.append("DGT — Altimetria (curvas de nível)")
    agua = []
    for col in ("linhas_agua", "srup_albufeiras"):
        fe = await G._dgt_items(col, bbox, 200)
        for ft in fe or []:
            g = ft.get("geometry") or {}
            if g.get("type") in ("LineString", "MultiLineString"):
                for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
                    dr.line([P(c[1], c[0]) for c in ln], fill=(30, 110, 230, 255), width=5)
            elif g.get("type") in ("Polygon", "MultiPolygon"):
                for pg in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]):
                    dr.polygon([P(c[1], c[0]) for c in pg[0]], fill=(60, 140, 240, 150), outline=(30, 110, 230, 255))
        if fe:
            agua += fe
            fontes.append("DGT — Hidrografia (linhas de água)" if col == "linhas_agua" else "DGT — SRUP Albufeiras")
    poly = f["terreno"]["poligono_latlon"]
    dr.line([P(*p) for p in poly] + [P(*poly[0])], fill=(230, 30, 30, 255), width=6)
    if casa_latlon:
        polys = casa_latlon if isinstance(casa_latlon[0][0], (list, tuple)) else [casa_latlon]
        for pg in polys:
            if len(pg) >= 3:
                dr.polygon([P(float(q[0]), float(q[1])) for q in pg], fill=(255, 210, 60, 200), outline=(40, 40, 40, 255))
    # seta de escoamento
    ax, ay = P(lat, lon)
    r = math.radians(dcl["escoamento_rumo"])
    bx, by = ax + 110 * math.sin(r), ay - 110 * math.cos(r)
    dr.line([ax, ay, bx, by], fill=(20, 60, 200, 255), width=6)
    dr.polygon([(bx, by), (bx - 16 * math.cos(r) - 22 * math.sin(r), by - 16 * math.sin(r) + 22 * math.cos(r)),
                (bx + 16 * math.cos(r) - 22 * math.sin(r), by + 16 * math.sin(r) + 22 * math.cos(r))], fill=(20, 60, 200, 255))
    # legenda
    dr.rectangle([20, 20, 520, 330], fill=(255, 255, 255, 235), outline=(60, 60, 60, 255))
    dr.text((34, 30), "Carta de declives e recursos hídricos", fill=(20, 20, 20, 255), font=V._font(20))
    for k, (_, _, cor, t) in enumerate(CLASSES_DECLIVE):
        dr.rectangle([34, 66 + k * 30, 64, 88 + k * 30], fill=cor + (255,))
        dr.text((74, 66 + k * 30), t, fill=(20, 20, 20, 255), font=V._font(17))
    dr.line([260, 76, 300, 76], fill=(120, 80, 40, 255), width=3)
    dr.text((310, 66), "Curvas de nível (DGT)", fill=(20, 20, 20, 255), font=V._font(17))
    dr.line([260, 106, 300, 106], fill=(30, 110, 230, 255), width=5)
    dr.text((310, 96), "Linhas de água (DGT)", fill=(20, 20, 20, 255), font=V._font(17))
    dr.line([260, 136, 300, 136], fill=(20, 60, 200, 255), width=5)
    dr.text((310, 126), "Escoamento natural", fill=(20, 20, 20, 255), font=V._font(17))
    txt = (f"Terreno: declive médio {dcl['declive_medio_pct']} % · máx. {dcl['declive_max_pct']} % · desnível "
           f"{dcl['desnivel_m']} m · a água escorre para {dcl['escoamento_para']}")
    dr.text((34, 226), txt[:62], fill=(20, 20, 20, 255), font=V._font(16))
    dr.text((34, 250), txt[62:124], fill=(20, 20, 20, 255), font=V._font(16))
    dr.text((34, 284), ("Fontes: " + "; ".join(fontes))[:70], fill=(80, 80, 80, 255), font=V._font(14))
    dr.text((34, 304), ("Fontes: " + "; ".join(fontes))[70:140], fill=(80, 80, 80, 255), font=V._font(14))
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()


def tem_desnivel(dcl: Dict[str, Any]) -> bool:
    return bool(dcl.get("ok") and ((dcl.get("desnivel_m") or 0) >= 1.0 or (dcl.get("declive_medio_pct") or 0) >= 3.0))


# ------------------------------------------------------------------ ficha de condicionantes (PDF A3)
def ficha_pdf(f: Dict[str, Any], planta_png: Optional[bytes], declives_png: Optional[bytes] = None,
              dcl: Optional[Dict[str, Any]] = None, titulo: str = "") -> bytes:
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
