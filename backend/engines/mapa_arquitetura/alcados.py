"""Vãos medidos nos ALÇADOS do DWFX : cada vista é localizada pelo título («Alçado …») ; o vão é o retângulo exterior do aro
desenhado nas camadas de traço fino / vãos / paredes ; folhas encostadas juntam-se num vão ; portas cujo terço inferior não
fecha como retângulo são prolongadas pelas ombreiras ; níveis por passos de ~3,1 m a partir da fila de cima."""
from __future__ import annotations

import re

from shapely.geometry import LineString, box
from shapely.ops import polygonize, unary_union

TITULO = re.compile(r"al[cç]ado", re.I)
EXCLUI = re.compile(r"conjunto|^\s*corte", re.I)        # vistas de conjunto (repetem o edifício) e cortes não contam como fachada
CAM_VAO = ("fino", "paredes")


def vistas(folha, papeis) -> list:
    """[(título, (x0, y0, x1, y1))] — zona do edifício = extensão das linhas de parede do bloco de desenho por cima do título."""
    segs = [LineString([a, b]) for e in folha.elementos if e.tipo == "path" and papeis.get(e.camada) in ("paredes", "fino", "trama")
            for pl in e.pls for a, b in zip(pl, pl[1:]) if a != b]
    if not segs:
        return []
    U = unary_union([s.buffer(0.5) for s in segs])
    comps = [g for g in getattr(U, "geoms", [U]) if (g.bounds[2] - g.bounds[0]) > 5 and (g.bounds[3] - g.bounds[1]) > 3]
    out = []
    for e in folha.elementos:
        if e.tipo != "texto" or not TITULO.search(e.texto) or EXCLUI.search(e.texto):
            continue
        x, y = e.pos
        cand = [g for g in comps if g.bounds[0] - 6 <= x <= g.bounds[2] + 6 and 0 <= y - g.bounds[3] <= 4.0]
        if not cand:
            continue
        g = min(cand, key=lambda g: y - g.bounds[3])
        pp = [s for s in segs if g.contains(s.centroid)]
        xs = [c[0] for s in pp for c in s.coords]; ys = [c[1] for s in pp for c in s.coords]
        out.append((e.texto.strip(), (min(xs), min(ys), max(xs), max(ys))))
    return out


def _retangulos(folha, papeis, zona):
    Z = box(*zona)
    segs = []
    for e in folha.elementos:
        if e.tipo == "path" and papeis.get(e.camada) in CAM_VAO:
            for pl in e.pls:
                for a, b in zip(pl, pl[1:]):
                    s = LineString([a, b])
                    if s.length > 0.05 and Z.intersects(s):
                        segs.append(s)
    rect = []
    for p in polygonize(unary_union(segs)) if segs else []:
        x0, y0, x1, y1 = p.bounds
        w, h = x1 - x0, y1 - y0
        if 0.4 <= w <= 4.5 and 0.4 <= h <= 3.2 and p.area >= 0.97 * w * h:
            rect.append(box(x0, y0, x1, y1))
    rect.sort(key=lambda b: -b.area)
    vaos = []
    for b in rect:
        if not any(v.buffer(0.02).contains(b) for v in vaos):
            vaos.append(b)
    return [v for v in vaos if Z.contains(v)]


def _junta(rs, tol=0.07):
    rs = [list(r.bounds) for r in rs]
    mudou = True
    while mudou:
        mudou = False
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                lado = abs(a[1] - b[1]) <= tol and abs(a[3] - b[3]) <= tol and (abs(a[2] - b[0]) <= tol or abs(b[2] - a[0]) <= tol)
                cima = abs(a[0] - b[0]) <= tol and abs(a[2] - b[2]) <= tol and (abs(a[3] - b[1]) <= tol or abs(b[3] - a[1]) <= tol)
                if lado or cima:
                    rs[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    rs.pop(j); mudou = True
                    break
            if mudou:
                break
    return [box(*r) for r in rs]


def _prolonga(V, folha, papeis, tol=0.05, maxext=1.3):
    vert = []
    for e in folha.elementos:
        if e.tipo == "path" and papeis.get(e.camada) in CAM_VAO:
            for pl in e.pls:
                for a, b in zip(pl, pl[1:]):
                    if abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) > 0.2:
                        vert.append((a[0], min(a[1], b[1]), max(a[1], b[1])))
    out = []
    for v in V:
        x0, y0, x1, y1 = v.bounds

        def fundo(x):
            ys = [yb for xv, ya, yb in vert if abs(xv - x) <= tol and ya <= y1 + tol and yb > y1 + 0.2]
            return max(ys) if ys else None
        e0, e1 = fundo(x0), fundo(x1)
        if e0 is not None and e1 is not None and min(e0, e1) - y1 <= maxext:
            y1 = min(e0, e1)
        out.append(box(x0, y0, x1, y1))
    return out


def _isola(V, zona, largura):
    """Edifícios vizinhos desenhados na mesma vista : janela horizontal com a largura da fachada (lida na planta, + 1 m) na
    posição que contém mais área de vãos. Sem largura conhecida, fica a vista inteira."""
    if not largura or largura >= zona[2] - zona[0] or not V:
        return V, zona
    best = None
    for x0 in sorted({v.bounds[0] - 0.5 for v in V} | {v.bounds[2] + 0.5 - largura for v in V}):
        a = sum(v.area for v in V if v.bounds[0] >= x0 - 1e-6 and v.bounds[2] <= x0 + largura + 1e-6)
        if best is None or a > best[0] + 1e-6:
            best = (a, x0)
    x0 = best[1]
    z = (x0, zona[1], x0 + largura, zona[3])
    return [v for v in V if v.bounds[0] >= x0 - 1e-6 and v.bounds[2] <= x0 + largura + 1e-6], z


def medir(folha, papeis, passo=3.1, larguras=None) -> list:
    """[{vista, vaos:[{nivel, L, H, x}]}] — y do desenho cresce para baixo ; nível 0 = fila de cima.
    larguras = (frente, lateral) do edifício lidas na planta tipo, para separar os edifícios vizinhos da vista."""
    res = []
    for titulo, zona in vistas(folha, papeis):
        V = _retangulos(folha, papeis, zona)
        if larguras:
            V, zona = _isola(V, zona, (larguras[1] if re.search(r"lat", titulo, re.I) else larguras[0]) + 1.0)
        V = _junta(_prolonga(_junta(V), folha, papeis))
        V = [v for v in V if not any(u is not v and u.buffer(0.03).contains(v) for u in V)]
        altos = [v.bounds[3] for v in V if v.bounds[3] - v.bounds[1] > 0.8]
        topo = min(altos) if altos else 0.0
        vaos = [{"nivel": int(round((v.bounds[3] - topo) / passo)), "x": round(v.bounds[0], 2),
                 "L": round(v.bounds[2] - v.bounds[0], 2), "H": round(v.bounds[3] - v.bounds[1], 2)} for v in V]
        Z = box(*zona).buffer(1.0)
        linhas = [pl for e in folha.elementos if e.tipo == "path" and papeis.get(e.camada) in ("paredes", "fino", "trama")
                  for pl in e.pls if len(pl) > 1 and Z.contains(LineString(pl))]
        res.append({"vista": titulo, "folha": folha.nome, "zona": [round(z, 2) for z in zona], "_linhas": linhas,
                    "_caixas": [list(v.bounds) for v in V],
                    "vaos": sorted(vaos, key=lambda d: (d["nivel"], d["x"]))})
    return res
