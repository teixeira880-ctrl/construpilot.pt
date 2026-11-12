"""Modelo 3D georreferenciado e renders reais no Blender (Cycles) para o piloto automático de licenciamento.

Separação em duas partes:
  • este módulo (sem Blender): monta a «especificação da cena» a partir do processo — terreno com o ortofotomapa oficial
    colocado nas coordenadas certas, relevo do levantamento altimétrico, casa e garagem com as medidas exatas da
    implantação, vãos das fachadas, materiais escolhidos, edifícios vizinhos (OpenStreetMap), sol na posição real
    (data e hora fixas, latitude/longitude do terreno) e câmaras. Tudo determinístico e testável.
  • blender_run.py: corre noutro processo (`python -m engines.urbanismo_pt.auto.blender_run spec.json pasta`), importa o
    Blender (`bpy`), constrói a cena, faz os renders Cycles (antes / depois) e exporta .glb, .blend e georreferência.

Nada aqui é gerado por IA: as imagens saem do motor de render do Blender a partir da geometria do processo.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from engines.urbanismo_pt import volumes as V
from engines.urbanismo_pt.auto.terreno import Local

VERSAO = 1
DATA_SOL = datetime(2026, 4, 21, 15, 30, tzinfo=timezone.utc)      # 21 de abril, 16h30 em Portugal (luz de fim de tarde)
MAX_ALT_VIZINHO = 30.0


def disponivel() -> bool:
    """O Blender (módulo bpy) está instalado neste servidor?"""
    import importlib.util
    return importlib.util.find_spec("bpy") is not None


# ------------------------------------------------------------------ georreferência
class Georef:
    """Referencial local do processo (origem no canto frente-esquerda do terreno, x ao longo da frente, y para o tardoz)
    ajustado aos vértices do terreno em WGS84. Converte local ↔ lat/lon ↔ PT-TM06 (EPSG:3763)."""

    def __init__(self, pol_m: List, pol_ll: List):
        self.loc = Local(float(pol_ll[0][0]), float(pol_ll[0][1]))
        en = np.array([self.loc.xy(float(la), float(lo)) for la, lo in pol_ll])
        xy = np.array([[float(x), float(y)] for x, y in pol_m])
        A = np.c_[xy, np.ones(len(xy))]
        coef, *_ = np.linalg.lstsq(A, en, rcond=None)              # [E N] = [x y 1] · coef
        self.M = coef[:2].T                                         # 2×2: colunas = ex, ey em EN
        self.o = coef[2]
        self.Minv = np.linalg.inv(self.M)
        self.residuo_m = float(np.abs(A @ coef - en).max())
        self.ex, self.ey = self.M[:, 0], self.M[:, 1]

    def en(self, x: float, y: float) -> Tuple[float, float]:
        e, n = self.M @ np.array([x, y]) + self.o
        return float(e), float(n)

    def local(self, e: float, n: float) -> Tuple[float, float]:
        x, y = self.Minv @ (np.array([e, n]) - self.o)
        return float(x), float(y)

    def ll(self, x: float, y: float) -> Tuple[float, float]:
        return self.loc.ll(*self.en(x, y))

    def de_ll(self, lat: float, lon: float) -> Tuple[float, float]:
        return self.local(*self.loc.xy(lat, lon))

    def dir_local(self, de: float, dn: float) -> Tuple[float, float]:
        """Vetor (este, norte) → vetor no referencial local."""
        x, y = self.Minv @ np.array([de, dn])
        return float(x), float(y)

    def rotacao_graus(self) -> float:
        """Azimute do eixo +y local (direção frente → tardoz), em graus a partir do norte."""
        return (math.degrees(math.atan2(self.ey[0], self.ey[1])) + 360.0) % 360.0


def pt_tm06(lat: float, lon: float) -> Tuple[float, float]:
    """WGS84/ETRS89 → PT-TM06 (EPSG:3763): Transverse Mercator, elipsoide GRS80, série de Krüger (erro < 1 mm)."""
    a, f = 6378137.0, 1 / 298.257222101
    lat0, lon0 = math.radians(39.66825833333333), math.radians(-8.133108333333334)
    n = f / (2 - f)
    A = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    al = [n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16 + 41 * n ** 4 / 180,
          13 * n ** 2 / 48 - 3 * n ** 3 / 5 + 557 * n ** 4 / 1440,
          61 * n ** 3 / 240 - 103 * n ** 4 / 140,
          49561 * n ** 4 / 161280]
    e = math.sqrt(f * (2 - f))

    def xi_eta(phi, lam):
        t = math.sinh(math.atanh(math.sin(phi)) - e * math.atanh(e * math.sin(phi)))
        xi_ = math.atan2(t, math.cos(lam))
        eta_ = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
        x_, y_ = eta_, xi_
        for j, aj in enumerate(al, 1):
            x_ += aj * math.cos(2 * j * xi_) * math.sinh(2 * j * eta_)
            y_ += aj * math.sin(2 * j * xi_) * math.cosh(2 * j * eta_)
        return A * x_, A * y_
    x, y = xi_eta(math.radians(lat), math.radians(lon) - lon0)
    _, y0 = xi_eta(lat0, 0.0)
    return round(x, 3), round(y - y0, 3)


# ------------------------------------------------------------------ sol
def posicao_sol(lat: float, lon: float, quando: datetime = DATA_SOL) -> Tuple[float, float]:
    """(azimute, elevação) do sol em graus — algoritmo da NOAA (erro < 0,5°)."""
    q = quando.astimezone(timezone.utc)
    doy = q.timetuple().tm_yday
    hora = q.hour + q.minute / 60 + q.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hora - 12) / 24)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    dec = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
           - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = hora * 60 + eqt + 4 * lon
    ha = math.radians(tst / 4 - 180)
    la = math.radians(lat)
    cosz = math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha)
    zen = math.acos(max(-1.0, min(1.0, cosz)))
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(la) - math.tan(dec) * math.cos(la))) + 180
    return round(az % 360, 2), round(90 - math.degrees(zen), 2)


# ------------------------------------------------------------------ materiais por fachada
def materiais_paredes(fachada: str, fachada_sol: str, levels: int) -> Dict[str, Any]:
    """Que material vai em cada parede: {'principal': {lado: mat | [(z_ate, mat), ...]}, 'anexo': mat}."""
    lados = ("frente", "tardoz", "esquerda", "direita")
    base = {"granito": "granito", "madeira": "madeira", "xisto": "xisto", "tijolo": "tijolo", "betao": "betao",
            "reboco_branco": "reboco"}.get(fachada)
    if base:
        return {"principal": {l: base for l in lados}, "anexo": base}
    if fachada == "misto_granito_madeira":
        return {"principal": {l: ("madeira" if l == fachada_sol else "granito") for l in lados}, "anexo": "madeira"}
    if fachada == "misto_madeira_reboco":
        return {"principal": {l: ("madeira" if l == fachada_sol else "reboco") for l in lados}, "anexo": "reboco"}
    if fachada == "misto_granito_reboco":
        if levels > 1:
            return {"principal": {l: "faixa_granito_reboco" for l in lados}, "anexo": "granito"}
        return {"principal": {l: ("granito" if l == "frente" else "reboco") for l in lados}, "anexo": "granito"}
    return {"principal": {l: "reboco" for l in lados}, "anexo": "reboco"}


# ------------------------------------------------------------------ especificação da cena
def _plano_z(topo: Dict[str, Any], soleira: Optional[float]):
    """Cota relativa à soleira em (x, y): plano médio do levantamento, limitado à amplitude medida (+/- 2 m)."""
    if not topo or not topo.get("ok") or soleira is None:
        return lambda x, y: 0.0
    pl = topo.get("plano") or {}
    a, b, c = float(pl.get("a", soleira)), float(pl.get("b", 0)), float(pl.get("c", 0))
    zmin, zmax = float(topo.get("z_min", soleira)) - 2.0, float(topo.get("z_max", soleira)) + 2.0
    return lambda x, y: max(zmin, min(zmax, a + b * x + c * y)) - soleira


def _dist_rect(x, y, r):
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


def _suave(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def especificacao(processo: Dict[str, Any], vizinhos: Optional[List[Dict[str, Any]]] = None,
                  qualidade: str = "normal") -> Dict[str, Any]:
    """Tudo o que o Blender precisa, em metros no referencial local (z = 0 na soleira)."""
    a = processo["auto"]
    ter = a["terreno"]
    vol = processo["volume"]
    hh = V.heights(vol)
    g = Georef(ter["poligono_m"], ter["poligono_latlon"])
    impl = a.get("implantacao") or {}
    soleira = impl.get("cota_soleira_m")
    zf = _plano_z(a.get("topografia") or {}, soleira)
    polys = V.building_polygons(vol)
    casa = [p for p in polys if not p["annexe"]]
    xs = [x for p in polys for x, _ in p["pts"]]
    ys = [y for p in polys for _, y in p["pts"]]
    caixa = (min(xs), min(ys), max(xs), max(ys))
    cx, cy = (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2
    diag = math.hypot(caixa[2] - caixa[0], caixa[3] - caixa[1])

    # chão: quadrado do ortofotomapa (norte para cima) em malha, com relevo; plataforma da casa a z = 0
    orto = a.get("orto") or {}
    if orto.get("bbox"):
        lo0, la0, lo1, la1 = (float(v) for v in str(orto["bbox"]).split(","))
    else:
        la_c, lo_c = g.ll(cx, cy)
        d = 60.0 / 111_320.0
        lo0, la0, lo1, la1 = lo_c - d / math.cos(math.radians(la_c)), la_c - d, lo_c + d / math.cos(math.radians(la_c)), la_c + d
    rects_c = [(min(q[0] for q in p["pts"]), min(q[1] for q in p["pts"]), max(q[0] for q in p["pts"]), max(q[1] for q in p["pts"]))
               for p in polys]

    def zdep(x, y):
        """Terreno depois da obra: plataforma à cota da soleira junto à casa, a concordar com o natural em 6 m."""
        return zf(x, y) * _suave((min(_dist_rect(x, y, r) for r in rects_c) - 1.5) / 6.0)
    N = 64
    verts, uvs = [], []
    for j in range(N + 1):
        for i in range(N + 1):
            u, v = i / N, j / N
            x, y = g.de_ll(la0 + (la1 - la0) * v, lo0 + (lo1 - lo0) * u)
            verts.append([round(x, 3), round(y, 3), round(zf(x, y), 3), round(zdep(x, y), 3)])
            uvs.append([round(u, 5), round(v, 5)])
    faces = [[j * (N + 1) + i, j * (N + 1) + i + 1, (j + 1) * (N + 1) + i + 1, (j + 1) * (N + 1) + i]
             for j in range(N) for i in range(N)]

    # volumes da construção
    volumes = []
    for p in polys:
        h = float(p["h_m"] or (hh["altura_fachada_m"] if not p["annexe"] else 3.0))
        base = min(zf(x, y) for x, y in p["pts"]) - 0.4
        volumes.append({"nome": p["name"] or "Construção", "anexo": p["annexe"], "pts": [[round(x, 3), round(y, 3)] for x, y in p["pts"]],
                        "z0": round(min(base, -0.4), 3), "h": round(h, 3)})
    coberturas = []
    for r in V.main_rects(vol):
        coberturas.append({"rect": [round(v, 3) for v in r], "z": hh["altura_fachada_m"], "tipo": hh["roof_type"],
                           "h": hh["roof_h_m"], "beiral": 0.45})
    for p in polys:
        if p["annexe"]:
            xs_, ys_ = [q[0] for q in p["pts"]], [q[1] for q in p["pts"]]
            coberturas.append({"rect": [min(xs_), min(ys_), max(xs_), max(ys_)], "z": float(p["h_m"] or 3.0), "tipo": "plana",
                               "h": 0.0, "beiral": 0.0})

    # vãos: frente em y = y0 da casa, tardoz em y = y1
    plan = a.get("plantas") or {}
    cr = plan.get("casa_rect") or impl.get("casa_rect") or caixa
    vaos = []
    for v in a.get("vaos") or []:
        yv = cr[1] if v["fachada"] == "frente" else cr[3]
        vaos.append({"tipo": v["tipo"], "lado": v["fachada"], "x0": v["x0"], "x1": v["x1"], "z0": v["z0"], "z1": v["z1"], "y": yv})
    garagem = None
    gr = impl.get("garagem_rect")
    if gr:
        garagem = {"rect": list(gr), "porta": {"x0": gr[0] + 0.45, "x1": gr[2] - 0.45, "z1": 2.4, "y": gr[1]}}

    # arranjos exteriores (só «depois»): acesso automóvel à garagem e caminho até à porta principal
    pav = []
    if gr:
        pav.append({"tipo": "acesso", "rect": [gr[0] + 0.2, -3.0, gr[2] - 0.2, gr[1]]})
    porta = next((v for v in vaos if v["tipo"] == "porta"), None)
    if porta:
        pav.append({"tipo": "caminho", "rect": [porta["x0"] - 0.1, -3.0, porta["x1"] + 0.1, cr[1]]})
    sol_lado = impl.get("fachada_sol") or "tardoz"
    if sol_lado == "tardoz":
        pav.append({"tipo": "terraco", "rect": [cr[0] + 0.5, cr[3], cr[2] - 0.5, cr[3] + 3.5]})
    else:
        pav.append({"tipo": "terraco", "rect": [cr[0] + 2.0, cr[1] - 3.0, cr[2] - 0.5, cr[1]]})

    # malhas que seguem o terreno «depois»: relva do lote (células de 1 m recortadas pelo limite) e lajeados
    from shapely.geometry import Polygon, box as sbox
    parcel = Polygon(ter["poligono_m"])

    def malha_sobre(pg, passo, dz):
        vs, fs, idx = [], [], {}
        x0, y0, x1, y1 = pg.bounds
        nx, ny = max(1, math.ceil((x1 - x0) / passo)), max(1, math.ceil((y1 - y0) / passo))
        for j in range(ny):
            for i in range(nx):
                cel = sbox(x0 + i * passo, y0 + j * passo, min(x1, x0 + (i + 1) * passo), min(y1, y0 + (j + 1) * passo))
                inter = cel.intersection(pg)
                for gg in getattr(inter, "geoms", [inter]):
                    if gg.is_empty or gg.geom_type != "Polygon" or gg.area < 1e-4:
                        continue
                    f = []
                    for x, y in list(gg.exterior.coords)[:-1]:
                        k = (round(x, 3), round(y, 3))
                        if k not in idx:
                            idx[k] = len(vs)
                            vs.append([k[0], k[1], round(zdep(x, y) + dz, 3)])
                        f.append(idx[k])
                    if len(f) >= 3:
                        fs.append(f if gg.exterior.is_ccw else f[::-1])
        return {"verts": vs, "faces": fs}
    relva = malha_sobre(parcel.buffer(-0.05), 1.0, 0.03)
    pav_m = []

    # edifícios vizinhos (OpenStreetMap): volumes neutros; os que tocam o terreno só aparecem no «antes»
    viz = []
    for b in (vizinhos or [])[:150]:
        pts = [g.de_ll(la, lo) for la, lo in b["latlon"]]
        try:
            pg = Polygon(pts)
        except Exception:  # noqa: BLE001
            continue
        if not pg.is_valid or pg.area < 8 or max(abs(x - cx) for x, _ in pts) > 140:
            continue
        h = float(b.get("altura_m") or (3.2 if (b.get("tipo") in ("garage", "shed", "garages")) else 6.0))
        viz.append({"pts": [[round(x, 3), round(y, 3)] for x, y in pts], "h": min(h, MAX_ALT_VIZINHO),
                    "z0": round(min(zf(x, y) for x, y in pts) - 0.5, 3), "no_terreno": pg.intersects(parcel)})

    for pv in pav:
        r = pv["rect"]
        pg = sbox(*r).intersection(parcel.buffer(3.5))
        if not pg.is_empty:
            pav_m.append({"tipo": pv["tipo"], **malha_sobre(pg, 1.0, 0.07)})

    # árvores: junto aos cantos e a meio dos limites, longe da casa e dos acessos (sempre as mesmas posições)
    arv = []
    bx0, by0, bx1, by1 = parcel.bounds
    ocupado = [sbox(*r).buffer(4.5) for r in rects_c] + [sbox(*pv["rect"]).buffer(2.0) for pv in pav]
    cand = [(bx0 + 3, by1 - 3), (bx1 - 3, by1 - 3), ((bx0 + bx1) / 2, by1 - 3), (bx0 + 3, (by0 + by1) / 2), (bx1 - 3, (by0 + by1) / 2)]
    from shapely.geometry import Point
    for k, (x, y) in enumerate(cand):
        pt = Point(x, y)
        if parcel.buffer(-2.0).contains(pt) and not any(o.contains(pt) for o in ocupado):
            arv.append({"x": round(x, 2), "y": round(y, 2), "z": round(zdep(x, y), 2), "h": 6.5 + (k % 3) * 0.8, "r": 2.0 + (k % 2) * 0.4})

    # sol e câmaras
    lat_c, lon_c = g.ll(cx, cy)
    az, el = posicao_sol(lat_c, lon_c)
    dsx, dsy = g.dir_local(math.sin(math.radians(az)), math.cos(math.radians(az)))
    nrm = math.hypot(dsx, dsy) or 1.0
    sol = {"azimute": az, "elevacao": el, "dir_local": [dsx / nrm * math.cos(math.radians(el)),
                                                         dsy / nrm * math.cos(math.radians(el)), math.sin(math.radians(el))],
           "data": DATA_SOL.isoformat()}
    alvo = [cx, cy, hh["altura_total_m"] * 0.45]
    D = max(30.0, 2.4 * diag)

    def orbita(ang_graus, elev_graus, dist, alvo_z=None):
        t = math.radians(ang_graus)          # 0 = em frente (lado da via, -y); positivo = para a direita (+x)
        e = math.radians(elev_graus)
        return [round(cx + math.sin(t) * math.cos(e) * dist, 3), round(cy - math.cos(t) * math.cos(e) * dist, 3),
                round((alvo_z if alvo_z is not None else alvo[2]) + math.sin(e) * dist, 3)]
    rua_x = cx + min(8.0, diag * 0.35)
    camaras = [
        {"id": "aerea", "titulo": "Vista aérea", "pos": orbita(-38, 32, D), "alvo": alvo, "lente_mm": 35},
        {"id": "drone", "titulo": "Vista de drone, da rua", "pos": orbita(28, 12, D * 0.75), "alvo": [cx, cy, hh["altura_fachada_m"] * 0.5], "lente_mm": 30},
        {"id": "rua", "titulo": "Vista da rua (altura dos olhos)", "pos": [round(rua_x, 3), -4.5, round(zf(rua_x, -4.5) + 1.65, 3)],
         "alvo": [cx, cy, 2.2], "lente_mm": 24},
    ]
    if sol_lado == "tardoz":
        camaras.append({"id": "jardim", "titulo": "Vista do jardim (fachada ao sol)", "pos": orbita(180 + 25, 9, D * 0.6), "alvo": [cx, cy, 2.0], "lente_mm": 28})
    norte = g.dir_local(0.0, 1.0)
    meia = max(parcel.bounds[2] - parcel.bounds[0], parcel.bounds[3] - parcel.bounds[1]) / 2 + 8.0
    pc = parcel.centroid
    camaras.append({"id": "topo", "titulo": "Planta georreferenciada sobre o ortofotomapa", "pos": [pc.x, pc.y, 200.0],
                    "alvo": [pc.x, pc.y, 0.0], "ortografica": True, "escala": round(2 * meia, 2), "norte": list(norte), "so_depois": True})

    res = {"teste": (320, 180, 4), "rapido": (1280, 720, 24), "normal": (1600, 900, 48), "alta": (2560, 1440, 160)}.get(qualidade, (1600, 900, 48))
    mats = a.get("materiais") or {}
    origem_ll = g.ll(0.0, 0.0)
    return {
        "versao": VERSAO,
        "georef": {"origem_local": "canto frente-esquerda do terreno, cota da soleira",
                   "origem_wgs84": [round(origem_ll[0], 8), round(origem_ll[1], 8)],
                   "origem_pt_tm06": list(pt_tm06(*origem_ll)), "cota_soleira_m": soleira,
                   "azimute_eixo_y": round(g.rotacao_graus(), 3), "residuo_ajuste_m": round(g.residuo_m, 4),
                   "crs": "EPSG:3763 (ETRS89 / PT-TM06); altitudes do levantamento usado no processo",
                   "terreno_wgs84": [[round(la, 8), round(lo, 8)] for la, lo in ter["poligono_latlon"]],
                   "terreno_pt_tm06": [list(pt_tm06(la, lo)) for la, lo in ter["poligono_latlon"]]},
        "chao": {"verts": verts, "uvs": uvs, "faces": faces, "orto_fonte": orto.get("fonte"), "tem_orto": bool(orto.get("b64"))},
        "terreno": [[round(x, 3), round(y, 3), round(zf(x, y) + 0.03, 3)] for x, y in ter["poligono_m"]],
        "volumes": volumes, "coberturas": coberturas, "vaos": vaos, "garagem": garagem, "pavimentos": pav,
        "relva": relva, "pavimentos_malha": pav_m, "arvores": arv,
        "vizinhos": viz,
        "paredes": materiais_paredes(mats.get("fachada") or "reboco_branco", sol_lado, hh["levels"]),
        "cobertura_material": mats.get("cobertura") or "telha_ceramica",
        "caixilharia": mats.get("caixilharia") or "aluminio_antracite",
        "pisos": hh["levels"], "piso_a_piso": hh["storey_h_m"],
        "sol": sol, "camaras": camaras,
        "render": {"largura": res[0], "altura": res[1], "amostras": res[2]},
    }


# ------------------------------------------------------------------ execução (processo separado)
def renderizar(processo: Dict[str, Any], vizinhos: Optional[List[Dict[str, Any]]] = None, qualidade: str = "normal",
               prazo_s: int = 1500) -> Dict[str, Any]:
    """Corre o Blender noutro processo (o bpy não é thread-safe e ocupa muita memória). Devolve os ficheiros em bytes."""
    if not disponivel():
        return {"ok": False, "motivo": "O Blender não está instalado neste servidor (pacote bpy)."}
    spec = especificacao(processo, vizinhos, qualidade)
    pasta = tempfile.mkdtemp(prefix="cp_blender_")
    t0 = time.time()
    try:
        orto = (processo["auto"].get("orto") or {}).get("b64")
        if orto:
            with open(os.path.join(pasta, "orto.jpg"), "wb") as f:
                f.write(base64.b64decode(orto))
        with open(os.path.join(pasta, "spec.json"), "w") as f:
            json.dump(spec, f)
        backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        env = {**os.environ, "PYTHONPATH": backend + os.pathsep + os.environ.get("PYTHONPATH", "")}
        threads = os.environ.get("BLENDER_THREADS")
        if threads:
            env["CP_BLENDER_THREADS"] = threads
        p = subprocess.run([sys.executable, "-m", "engines.urbanismo_pt.auto.blender_run", os.path.join(pasta, "spec.json"), pasta],
                           cwd=backend, env=env, capture_output=True, text=True, timeout=prazo_s)
        manifesto = os.path.join(pasta, "manifesto.json")
        if p.returncode != 0 or not os.path.exists(manifesto):
            return {"ok": False, "motivo": "O Blender terminou com erro.", "log": (p.stderr or p.stdout or "")[-2000:]}
        with open(manifesto) as f:
            man = json.load(f)
        ficheiros = {}
        for nome in man["ficheiros"]:
            with open(os.path.join(pasta, nome), "rb") as f:
                ficheiros[nome] = f.read()
        return {"ok": True, "manifesto": man, "ficheiros": ficheiros, "georef": spec["georef"], "sol": spec["sol"],
                "segundos": round(time.time() - t0, 1), "blender": man.get("blender")}
    except subprocess.TimeoutExpired:
        return {"ok": False, "motivo": f"O Blender excedeu o prazo de {prazo_s} s."}
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


async def renderizar_async(processo: Dict[str, Any], qualidade: str = "normal") -> Dict[str, Any]:
    """Vai buscar os edifícios vizinhos (OpenStreetMap) e renderiza num thread (o Blender corre noutro processo)."""
    from engines.urbanismo_pt.auto import geo as G
    viz = []
    try:
        lat, lon = processo["auto"]["casa_latlon"][0][0] if processo["auto"].get("casa_latlon") else processo["auto"]["terreno"]["poligono_latlon"][0]
        r = await asyncio.wait_for(G.edificios_osm(lat, lon), 25)
        if r.get("ok"):
            viz = r["data"]["edificios"]
    except Exception:  # noqa: BLE001 — sem vizinhos o render faz-se na mesma
        viz = []
    res = await asyncio.to_thread(renderizar, processo, viz, qualidade)
    res["n_vizinhos"] = len(viz)
    return res
