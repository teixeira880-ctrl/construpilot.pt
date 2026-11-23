"""Alturas lidas nos CORTES verticais do DWFX : lajes cortadas (trama cheia de corte) varridas por linhas verticais, convertidas
em cotas pela coluna de cotas da própria vista. Dá, para cada piso, a altura da parede ENTRE LAJES (face superior da laje do
piso → face inferior da laje de cima) e a espessura das lajes — medidas na geometria, sem depender da posição dos textos."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

CORTE = re.compile(r"corte|sec[cç][aã]o|coupe|section", re.I)
NUM = re.compile(r"[+]?(\d{2,4}[.,]\d{2})")


def _colunas(folha):
    """Colunas de cotas : ≥ 3 textos de cota alinhados na vertical com cota + y constante (mesma vista). → [(x, k, y0, y1)]."""
    pts = []
    for e in folha.elementos:
        if e.tipo == "texto":
            m = NUM.fullmatch(e.texto.strip())
            if m:
                pts.append((float(m.group(1).replace(",", ".")), e.pos))
    grupos = defaultdict(list)
    for v, (x, y) in pts:
        grupos[(round(x), round(v + y, 1))].append((v, x, y))
    out = []
    for (_, k), g in grupos.items():
        if len(g) >= 3:
            ys = [y for _, _, y in g]
            out.append((sum(x for _, x, _ in g) / len(g), sum(v + y for v, _, y in g) / len(g), min(ys), max(ys)))
    return out


def lajes(folha, papeis) -> list:
    """[(k, [(cota_base, cota_topo, n_varrimentos)])] por coluna de cotas da folha."""
    polys = [Polygon(pl).buffer(0) for e in folha.elementos if e.tipo == "path" and e.fill and papeis.get(e.camada) == "trama"
             for pl in e.pls if len(pl) >= 3]
    polys = [p for p in polys if p.area > 0.001]
    if not polys:
        return []
    U = unary_union(polys)
    res = []
    for xc, k, ya, yb in _colunas(folha):
        y0, y1 = ya - 6.0, yb + 6.0
        cnt = Counter()
        x = xc - 30.0
        while x <= xc + 30.0:
            inter = U.intersection(LineString([(x, y0), (x, y1)]))
            for g in getattr(inter, "geoms", [inter]):
                if g.is_empty or g.geom_type != "LineString":
                    continue
                a, b = sorted(c[1] for c in g.coords)
                if 0.08 <= b - a <= 0.6:
                    cnt[(round(k - b, 2), round(k - a, 2))] += 1           # y cresce para baixo : base = k − y_baixo
            x += 0.1
        res.append((k, [(lo, hi, n) for (lo, hi), n in cnt.items() if n >= 5]))
    return res


def alturas_entre_lajes(z, lista, pisos, mapa_camadas=None) -> dict:
    """Para cada piso com cota de pavimento : laje do piso = banda com topo nos 0,6 m abaixo da cota ; laje de cima = banda com
    topo nos 0,6 m abaixo da cota do piso seguinte. Altura entre lajes = base da de cima − topo da do piso (mais frequente)."""
    from . import camadas, dwfx
    bandas = []
    for i, (_, _, nome) in enumerate(lista):
        if CORTE.search(nome):
            f = dwfx.ler(z, i, lista)
            if f.upm:
                for _, ls in lajes(f, camadas.mapa(f.camadas, mapa_camadas)):
                    bandas += ls
    out = {}
    niveis = [(p["piso"], (p.get("cota") or {}).get("valor")) for p in pisos]
    for j, (nome, c) in enumerate(niveis):
        cima = next((v for _, v in niveis[j + 1:] if v is not None), None)
        if c is None or cima is None:
            continue
        lo = Counter()
        for b0, t0, n0 in bandas:
            if c - 0.6 <= t0 <= c + 0.05:
                for b1, t1, n1 in bandas:
                    if cima - 0.6 <= t1 <= cima + 0.05 and b1 > t0:
                        lo[(round(b1 - t0, 2), round(t1 - b1, 2))] += min(n0, n1)
        if lo:
            (h, esp), _ = lo.most_common(1)[0]
            out[nome] = {"entre_lajes": h, "espessura_laje": esp}
    return out
