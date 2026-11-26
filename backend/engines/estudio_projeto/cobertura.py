"""Cobertura inclinada em contornos ortogonais com reentrâncias (plantas em L, T, U, cruz…).

Num contorno em que todos os lados são paralelos ou perpendiculares entre si, a cobertura de inclinação constante é
exata e não precisa de aproximações: a altura num ponto é tan(inclinação) × o meio-lado do maior quadrado centrado
nesse ponto que cabe no contorno. Esse quadrado cabe sempre num dos retângulos máximos inscritos no contorno, logo a
cobertura é a envolvente superior das coberturas desses retângulos:

- quatro águas: cada retângulo com a sua cobertura de quatro águas → rincões e larós certos nas reentrâncias;
- duas águas: cada retângulo com cumeeira ao longo do seu lado maior → corpos cruzados com empenas nos topos livres.

Contornos não ortogonais com reentrâncias não são tratados aqui (o chamador avisa e não inventa geometria).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

R = lambda v, n=3: round(float(v), n)  # noqa: E731
MAX_GRELHA = 48


def _polys(g) -> List[Polygon]:
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon" and not p.is_empty]


def direcao_ortogonal(pg: Polygon) -> Optional[float]:
    """Ângulo (rad) do referencial em que todos os lados ficam horizontais ou verticais; None se o contorno não é ortogonal."""
    c = list(pg.exterior.coords)
    lados = [(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1]) for i in range(len(c) - 1)]
    lados = [(dx, dy) for dx, dy in lados if math.hypot(dx, dy) > 1e-6]
    if len(lados) < 4:
        return None
    dx, dy = max(lados, key=lambda d: math.hypot(*d))
    th = math.atan2(dy, dx)
    co, si = math.cos(th), math.sin(th)
    for ex, ey in lados:
        L = math.hypot(ex, ey)
        u, v = (ex * co + ey * si) / L, (-ex * si + ey * co) / L
        if min(abs(u), abs(v)) > 2e-3:
            return None
    return th


def _rodar(pts, th: float) -> List[Tuple[float, float]]:
    co, si = math.cos(th), math.sin(th)
    return [(x * co + y * si, -x * si + y * co) for x, y in pts]


def retangulos_maximos(pg: Polygon) -> Optional[List[Tuple[float, float, float, float]]]:
    """Retângulos máximos inscritos num contorno já alinhado com os eixos: [(x0, y0, x1, y1)]. None se demasiado recortado."""
    c = list(pg.exterior.coords)
    xs = sorted({round(x, 4) for x, _ in c})
    ys = sorted({round(y, 4) for _, y in c})
    nx, ny = len(xs) - 1, len(ys) - 1
    if nx < 1 or ny < 1 or nx > MAX_GRELHA or ny > MAX_GRELHA:
        return None
    cheio = [[pg.contains(Point((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2)) for j in range(ny)] for i in range(nx)]
    soma = [[0] * (ny + 1) for _ in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            soma[i + 1][j + 1] = soma[i][j + 1] + soma[i + 1][j] - soma[i][j] + (1 if cheio[i][j] else 0)

    def tudo(i0, i1, j0, j1):          # células [i0, i1) × [j0, j1) todas dentro do contorno
        return soma[i1][j1] - soma[i0][j1] - soma[i1][j0] + soma[i0][j0] == (i1 - i0) * (j1 - j0)

    out = []
    for i0 in range(nx):
        for i1 in range(i0 + 1, nx + 1):
            for j0 in range(ny):
                for j1 in range(j0 + 1, ny + 1):
                    if not tudo(i0, i1, j0, j1):
                        continue
                    if (i0 > 0 and tudo(i0 - 1, i1, j0, j1)) or (i1 < nx and tudo(i0, i1 + 1, j0, j1)) \
                            or (j0 > 0 and tudo(i0, i1, j0 - 1, j1)) or (j1 < ny and tudo(i0, i1, j0, j1 + 1)):
                        continue
                    out.append((xs[i0], ys[j0], xs[i1], ys[j1]))
    return out


def _meio_plano(lim, a: float, b: float, c: float) -> Optional[Polygon]:
    """Parte da caixa `lim` onde a·x + b·y ≤ c."""
    x0, y0, x1, y1 = lim
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    out = []
    for i in range(4):
        p, q = pts[i], pts[(i + 1) % 4]
        fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            s = fp / (fp - fq)
            out.append((p[0] + s * (q[0] - p[0]), p[1] + s * (q[1] - p[1])))
    return Polygon(out) if len(out) >= 3 else None


def _pecas(rets, duas_aguas: bool, cumeeira: str) -> List[Dict[str, Any]]:
    """Águas de cada retângulo: polígono em planta + plano d(x, y) = n·p − c (distância ao lado de que a água nasce)."""
    pecas = []
    for k, (x0, y0, x1, y1) in enumerate(rets):
        lados = {"s": ((0.0, 1.0), y0), "n": ((0.0, -1.0), -y1), "o": ((1.0, 0.0), x0), "e": ((-1.0, 0.0), -x1)}
        if duas_aguas:
            ao_longo_x = (x1 - x0) >= (y1 - y0) if cumeeira == "auto" else cumeeira == "x"
            usar = ("s", "n") if ao_longo_x else ("o", "e")
        else:
            usar = ("s", "n", "o", "e")
        ret = box(x0, y0, x1, y1)
        lim = (x0 - 1, y0 - 1, x1 + 1, y1 + 1)
        for nome in usar:
            n, c = lados[nome]
            pl = ret
            for outro in usar:
                if outro == nome or pl.is_empty:
                    continue
                n2, c2 = lados[outro]
                mp = _meio_plano(lim, n[0] - n2[0], n[1] - n2[1], c - c2)        # onde d ≤ d_outro
                pl = pl.intersection(mp) if mp is not None else Polygon()
            if not pl.is_empty and pl.area > 1e-6:
                pecas.append({"pl": pl, "n": n, "c": c, "ret": k, "chave": (round(n[0], 6), round(n[1], 6), round(c, 4))})
    return pecas


def _envolvente(pecas, lim) -> List[Tuple[Polygon, Tuple[float, float], float]]:
    """Parte visível de cada água (onde nenhuma outra passa por cima), com as águas complanares fundidas."""
    visiveis: Dict[tuple, List[Polygon]] = {}
    planos: Dict[tuple, Tuple[Tuple[float, float], float]] = {}
    for i, a in enumerate(pecas):
        vis = a["pl"]
        for j, b in enumerate(pecas):
            if i == j or vis.is_empty:
                continue
            if a["chave"] == b["chave"]:
                if j < i:
                    vis = vis.difference(b["pl"])          # mesma água vista por dois retângulos: conta uma vez
                continue
            comum = vis.intersection(b["pl"])
            if comum.is_empty or comum.area < 1e-9:
                continue
            dn = (a["n"][0] - b["n"][0], a["n"][1] - b["n"][1])
            dc = a["c"] - b["c"]
            if abs(dn[0]) < 1e-9 and abs(dn[1]) < 1e-9:
                if dc > 1e-9:                                # planos paralelos: b está sempre por cima
                    vis = vis.difference(comum)
                continue
            mp = _meio_plano(lim, dn[0], dn[1], dc)          # onde d_a ≤ d_b, isto é, b por cima
            if mp is not None:
                vis = vis.difference(comum.intersection(mp))
        if not vis.is_empty and vis.area > 1e-6:
            visiveis.setdefault(a["chave"], []).append(vis)
            planos[a["chave"]] = (a["n"], a["c"])
    out = []
    for chave, lista in visiveis.items():
        for pl in _polys(unary_union(lista).buffer(0)):
            if pl.area > 1e-4:
                out.append((orient(pl.simplify(1e-5), 1.0), *planos[chave]))
    return out


def triangulos(pl: Polygon) -> List[Polygon]:
    """Triangulação que respeita o contorno (faces com reentrâncias incluídas)."""
    if hasattr(shapely, "constrained_delaunay_triangles"):
        g = shapely.constrained_delaunay_triangles(pl)
        return [t for t in getattr(g, "geoms", []) if t.geom_type == "Polygon" and t.area > 1e-9]
    from shapely.ops import triangulate
    return [t for t in triangulate(pl) if pl.contains(t.representative_point())]


def aguas_ortogonais(pegada: Polygon, cob: Dict[str, Any], z_topo: float) -> Dict[str, Any]:
    """Águas de duas ou de quatro águas num contorno ortogonal (com ou sem reentrâncias).
    Devolve {"faces", "empenas", "z_cumeeira", "z_beirado", "perimetro_beirado_m"} ou {"motivo"}."""
    tipo = cob["tipo"]
    if tipo not in ("duas_aguas", "quatro_aguas"):
        return {"motivo": "A cobertura de uma água pede um último piso retangular; use «duas águas», «quatro águas» ou «plana»."}
    pg = orient(pegada.simplify(0.002), 1.0)
    th = direcao_ortogonal(pg)
    if th is None:
        return {"motivo": "A cobertura inclinada automática existe em plantas convexas e em plantas ortogonais (L, T, U). "
                          "Este contorno tem reentrâncias e lados oblíquos: escolha «plana» ou regularize o último piso."}
    tan, beiral = math.tan(math.radians(cob["inclinacao_graus"])), cob["beiral_m"]
    cos = math.cos(math.radians(cob["inclinacao_graus"]))
    beirado = orient(pg.buffer(beiral, join_style=2, mitre_limit=10.0), 1.0) if beiral > 0 else pg
    if beirado.geom_type != "Polygon":
        return {"motivo": "O beiral funde partes do contorno: reduza o beiral ou escolha cobertura plana."}
    # tudo é calculado no referencial alinhado com o contorno e rodado de volta no fim
    E = Polygon(_rodar(beirado.exterior.coords, th))
    rets = retangulos_maximos(E)
    if not rets:
        return {"motivo": "Contorno demasiado recortado para a cobertura inclinada automática: escolha «plana»."}
    x0, y0, x1, y1 = E.bounds
    lim = (x0 - 5, y0 - 5, x1 + 5, y1 + 5)
    cum = cob.get("cumeeira", "auto")
    if cum != "auto":      # «x»/«y» referem-se aos eixos do terreno: converter para o referencial rodado
        cum = cum if abs(math.cos(th)) >= abs(math.sin(th)) else ("y" if cum == "x" else "x")
    pecas = _pecas(rets, tipo == "duas_aguas", cum)
    z_beirado = z_topo - tan * beiral
    volta = lambda x, y: _rodar([(x, y)], -th)[0]  # noqa: E731

    def altura(x: float, y: float) -> float:          # cota da cobertura num ponto (referencial rodado)
        por_ret: Dict[int, float] = {}
        for p in pecas:
            if p["pl"].buffer(1e-6).contains(Point(x, y)):
                por_ret[p["ret"]] = max(por_ret.get(p["ret"], -1e9), p["n"][0] * x + p["n"][1] * y - p["c"])
        return z_beirado + tan * max(por_ret.values()) if por_ret else z_beirado

    faces, z_max = [], z_topo
    planta_faces = []
    for pl, n, c in _envolvente(pecas, lim):
        def z_de(x, y, _n=n, _c=c):
            return z_beirado + tan * (_n[0] * x + _n[1] * y - _c)
        anel = list(pl.exterior.coords)[:-1]
        pts = [[R(volta(x, y)[0]), R(volta(x, y)[1]), R(z_de(x, y))] for x, y in anel]
        tris = [[[R(volta(x, y)[0]), R(volta(x, y)[1]), R(z_de(x, y))] for x, y in list(t.exterior.coords)[:3]] for t in triangulos(pl)]
        z_max = max(z_max, max(p[2] for p in pts))
        faces.append({"pts": pts, "tris": tris, "area_planta_m2": R(pl.area, 2), "area_m2": R(pl.area / cos, 2)})
        planta_faces.append(pl)

    # empenas: troços do contorno do último piso onde a cobertura fica acima do topo das paredes
    empenas = []
    P = _rodar(list(pg.exterior.coords)[:-1], th)
    fronteiras = unary_union([pl.boundary for pl in planta_faces]) if planta_faces else None
    for k in range(len(P)):
        p, q = P[k], P[(k + 1) % len(P)]
        Lpq = math.hypot(q[0] - p[0], q[1] - p[1])
        if Lpq < 1e-6:
            continue
        ts = {0.0, 1.0}
        if fronteiras is not None:
            g = LineString([p, q]).intersection(fronteiras)
            for geo in ([g] if g.geom_type == "Point" else list(getattr(g, "geoms", []))):
                if geo.geom_type == "Point":
                    ts.add(max(0.0, min(1.0, ((geo.x - p[0]) * (q[0] - p[0]) + (geo.y - p[1]) * (q[1] - p[1])) / (Lpq * Lpq))))
        ts_ord = sorted({round(t, 6) for t in ts})
        topo = []
        for t in ts_ord:
            x, y = p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])
            # ligeiramente para dentro do contorno, para ler a água que cobre este lado
            nx_, ny_ = -(q[1] - p[1]) / Lpq, (q[0] - p[0]) / Lpq
            topo.append((x, y, max(z_topo, altura(x + nx_ * 1e-4, y + ny_ * 1e-4))))
        # corta em troços contínuos acima do topo das paredes
        i = 0
        while i < len(topo) - 1:
            if max(topo[i][2], topo[i + 1][2]) - z_topo <= 0.01:
                i += 1
                continue
            j = i
            while j < len(topo) - 1 and max(topo[j][2], topo[j + 1][2]) - z_topo > 0.01:
                j += 1
            troco = topo[i:j + 1]
            base = [[R(volta(troco[0][0], troco[0][1])[0]), R(volta(troco[0][0], troco[0][1])[1]), R(z_topo)],
                    [R(volta(troco[-1][0], troco[-1][1])[0]), R(volta(troco[-1][0], troco[-1][1])[1]), R(z_topo)]]
            cima = [[R(volta(x, y)[0]), R(volta(x, y)[1]), R(z)] for x, y, z in reversed(troco) if z - z_topo > 1e-6]
            area = sum(math.hypot(troco[s + 1][0] - troco[s][0], troco[s + 1][1] - troco[s][1])
                       * ((troco[s][2] - z_topo) + (troco[s + 1][2] - z_topo)) / 2 for s in range(len(troco) - 1))
            if area > 0.005:
                empenas.append({"pts": base + cima, "area_m2": R(area, 2)})
            i = j
    return {"faces": faces, "empenas": empenas, "z_cumeeira": R(z_max), "z_beirado": R(z_beirado),
            "perimetro_beirado_m": R(beirado.length, 2), "retangulos": len(rets)}
