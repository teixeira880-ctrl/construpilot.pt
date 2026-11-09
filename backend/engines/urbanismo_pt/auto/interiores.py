"""Vistas interiores EXATAS dos compartimentos principais (sala, cozinha, suite, instalação sanitária).

Cada compartimento é construído a partir da planta do processo (mesmas medidas das peças desenhadas): chão, teto,
quatro paredes e os vãos exteriores que lhe pertencem, nas posições e dimensões reais. A câmara fica num canto,
à altura dos olhos, a olhar para a parede com mais vãos (como numa fotografia de imobiliário).
O modelo de imagem só pode acrescentar acabamentos, iluminação e mobiliário SUGERIDO — as paredes, o pé-direito
e os vãos ficam onde o projeto os põe; a verificação de geometria compara os vãos e as arestas da sala.
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from engines.urbanismo_pt.auto import render3d as R3

# compartimentos que valem uma imagem, por ordem de prioridade (tipo da planta → nome da vista)
INTERIORES = (("sala", "interior_sala"), ("cozinha", "interior_cozinha"), ("quarto", "interior_suite"),
              ("wc", "interior_wc"))
TITULOS = {"interior_sala": "sala de estar e jantar", "interior_cozinha": "cozinha", "interior_suite": "suite",
           "interior_wc": "instalação sanitária da suite"}

_COR = {"chao": (0.66, 0.52, 0.38), "teto": (0.96, 0.96, 0.95), "vao": (0.78, 0.88, 0.97), "porta": (0.42, 0.30, 0.20),
        "paredes": [(0.90, 0.88, 0.84), (0.84, 0.82, 0.78), (0.88, 0.86, 0.82), (0.80, 0.78, 0.74)]}


def escolher(processo: Dict[str, Any], limite: int = 4) -> List[Tuple[str, Dict[str, Any], int]]:
    """[(vista, compartimento, piso)] — a sala, a cozinha, a suite (o maior quarto) e a I.S. da suite."""
    pisos = ((processo.get("auto") or {}).get("plantas") or {}).get("pisos") or []
    out = []
    for tipo, nome in INTERIORES:
        cand = [(c, p.get("piso", 0)) for p in pisos for c in p.get("compartimentos") or [] if c.get("tipo") == tipo]
        if tipo == "wc":
            cand.sort(key=lambda t: (0 if "suite" in t[0]["nome"].lower() else 1, -t[0]["area_m2"]))
        elif tipo == "quarto":
            cand.sort(key=lambda t: (0 if "suite" in t[0]["nome"].lower() else 1, -t[0]["area_m2"]))
        else:
            cand.sort(key=lambda t: -t[0]["area_m2"])
        if cand:
            out.append((nome, cand[0][0], cand[0][1]))
    return out[:limite]


def _parede(cena: R3.Cena, a, b, h, cor, vaos: List[Tuple[float, float, float, float, str]]):
    """Parede de a→b (pontos 2D) até à altura h, recortada pelos vãos (s0, s1, z0, z1 ao longo da parede)."""
    ax, ay = a
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L

    def P(s, z):
        return (ax + ux * s, ay + uy * s, z)
    vs = sorted((max(0.0, s0), min(L, s1), z0, min(h, z1), t) for s0, s1, z0, z1, t in vaos if s1 > 0 and s0 < L)
    cur = 0.0
    for s0, s1, z0, z1, t in vs:
        if s0 > cur:
            cena.quad(P(cur, 0), P(s0, 0), P(s0, h), P(cur, h), cor, 0)
        if z0 > 0:
            cena.quad(P(s0, 0), P(s1, 0), P(s1, z0), P(s0, z0), cor, 0)
        if z1 < h:
            cena.quad(P(s0, z1), P(s1, z1), P(s1, h), P(s0, h), cor, 0)
        # o vão: claro (vista para o exterior) ou porta — é o que a verificação de geometria segue
        cena.quad(P(s0, z0), P(s1, z0), P(s1, z1), P(s0, z1), _COR["porta"] if t == "porta" else _COR["vao"], 1)
        cur = max(cur, s1)
    if cur < L:
        cena.quad(P(cur, 0), P(L, 0), P(L, h), P(cur, h), cor, 0)


def construir(processo: Dict[str, Any], comp: Dict[str, Any], piso: int = 0, pe_direito: float = 2.7):
    x0, y0, x1, y1 = (float(comp[k]) for k in ("x0", "y0", "x1", "y1"))
    vaos = [v for v in (processo.get("auto") or {}).get("vaos") or []
            if v.get("compartimento") == comp["nome"] and int(v.get("piso", 0)) == int(piso)]
    cena = R3.Cena()
    cena.quad((x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0), _COR["chao"], 0)
    cena.quad((x0, y0, pe_direito), (x1, y0, pe_direito), (x1, y1, pe_direito), (x0, y1, pe_direito), _COR["teto"], 0)
    # paredes: frente (y0), direita (x1), tardoz (y1), esquerda (x0) — cada uma com os seus vãos
    lados = [((x0, y0), (x1, y0), "y", y0), ((x1, y0), (x1, y1), "x", x1), ((x1, y1), (x0, y1), "y", y1),
             ((x0, y1), (x0, y0), "x", x0)]
    por_parede = []
    for i, (a, b, eixo_plano, val) in enumerate(lados):
        vs = []
        for v in vaos:
            plano = v.get("plano_m")
            if plano is None:
                continue
            ao_longo_x = v.get("eixo", "x" if v["fachada"] in ("frente", "tardoz") else "y") == "x"
            if (eixo_plano == "y") != ao_longo_x or abs(float(plano) - val) > 0.35:
                continue
            u0, u1 = float(v["x0"]), float(v["x1"])
            # posição ao longo da parede (a→b)
            ini = a[0] if ao_longo_x else a[1]
            sentido = 1 if ((b[0] - a[0]) if ao_longo_x else (b[1] - a[1])) > 0 else -1
            s0, s1 = sorted(((u0 - ini) * sentido, (u1 - ini) * sentido))
            vs.append((s0, s1, float(v["z0"]), float(v["z1"]), v.get("tipo")))
        por_parede.append(len(vs) + sum(s1 - s0 for s0, s1, *_ in vs) / 10)
        _parede(cena, a, b, pe_direito, _COR["paredes"][i], vs)
    return cena, (x0, y0, x1, y1), por_parede, vaos


def camara(rect, por_parede: List[float], pe_direito: float = 2.7):
    """Como numa fotografia de imobiliário: de costas para a parede oposta à parede principal (a com mais vãos),
    ligeiramente desviado do eixo, à altura de 1,45 m, a olhar para o centro da parede principal."""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    k = int(np.argmax(por_parede)) if any(por_parede) else 0
    m, dx, dy = 0.3, (x1 - x0) * 0.22, (y1 - y0) * 0.22
    olho, alvo = {0: ((cx - dx, y1 - m), (cx + dx * 0.4, y0)), 1: ((x0 + m, cy - dy), (x1, cy + dy * 0.4)),
                  2: ((cx + dx, y0 + m), (cx - dx * 0.4, y1)), 3: ((x1 - m, cy + dy), (x0, cy - dy * 0.4))}[k]
    return np.array([*olho, 1.45]), np.array([*alvo, 1.35]), 62.0


def vista(processo: Dict[str, Any], nome: str, comp: Dict[str, Any], piso: int = 0, W: int = 1536, H: int = 1024) -> Dict[str, Any]:
    pd = float(((processo.get("volume") or {}).get("storey_h_m") or 3.0) - 0.3)
    pd = max(2.4, min(pd, 3.2))
    cena, rect, por_parede, vaos = construir(processo, comp, piso, pd)
    olho, alvo, fov = camara(rect, por_parede, pd)
    im, mask = R3.rasterizar(cena, olho, alvo, fov, W, H, sol=(0.6, -0.5, 0.6), ambiente=0.8)
    b1, b2 = io.BytesIO(), io.BytesIO()
    im.save(b1, "PNG")
    Image.fromarray(mask).save(b2, "PNG")
    return {"vista": nome, "png": b1.getvalue(), "mascara_png": b2.getvalue(), "compartimento": comp["nome"],
            "area_m2": comp.get("area_m2"), "pe_direito_m": round(pd, 2), "n_vaos": len(vaos),
            "cobertura_mascara": float((mask > 0).mean())}


def prompt_interior(processo: Dict[str, Any], vista_nome: str, comp: Dict[str, Any], estrito: bool = False) -> str:
    from engines.urbanismo_pt.auto import estilos as E
    est = E.obter(((processo.get("auto") or {}).get("estilo") or {}).get("id"))
    rustico = est.get("cobertura", {}).get("tipo") != "plana" and est.get("fachada") in ("granito", "xisto", "reboco_branco")
    paleta = ("warm traditional Portuguese interior: lime-washed walls, exposed granite details, solid oak or chestnut floor, "
              "timber ceiling beams, linen fabrics, terracotta accents"
              if rustico else
              "high-end contemporary interior: warm off-white walls, large-format light stone or microcement floor, "
              "walnut timber panelling, hidden LED cove lighting in the ceiling, black metal details, natural linen and boucle fabrics")
    uso = {
        "interior_sala": "open-plan living and dining room: large low sofa, coffee table, rug, dining table for 8 with pendant lights, "
                         "indoor plants, TV wall with timber slats",
        "interior_cozinha": "modern kitchen with an island, handleless walnut and stone cabinets, integrated appliances, "
                            "stone worktop, bar stools, pendant lights",
        "interior_suite": "master bedroom suite: king bed with upholstered headboard and timber slat wall, bedside lamps, "
                          "bench, armchair, soft textiles",
        "interior_wc": "luxury bathroom: floating vanity with stone top and backlit mirror, walk-in shower with glass screen and "
                       "black fittings, large-format stone tiles, freestanding or built-in bathtub only if it fits",
    }.get(vista_nome, "furnished room")
    regra = ("Keep the room geometry EXACTLY as in the reference: same walls, same ceiling height, same camera position, lens "
             "and framing, every window and door opening in exactly the same position and size (the light-blue rectangles are "
             "the windows / glazed doors; show the garden and sky through them). Do not add, remove, move or resize any opening, "
             "wall or column. Furniture and finishes are suggestions and must fit inside the room. ")
    if estrito:
        regra = "STRICT: the window and wall edges must overlay pixel-for-pixel onto the reference. " + regra
    return (f"Award-winning interior architectural photograph of THIS exact room ({comp['nome']}, about "
            f"{round(float(comp.get('area_m2') or 0))} m²): {uso}. {regra}Style: {paleta}. "
            "Soft natural daylight coming through the windows, balanced warm artificial light, physically based materials, "
            "real-estate magazine quality, 24mm lens, vertical lines perfectly straight, sharp 4K detail, no people, no text, "
            "no watermark, no logo.")
