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


def perfil_cobertura(z, lista, cota_piso, mapa_camadas=None) -> dict | None:
    """Último piso (sótão) : altura da parede = face superior da laje do piso → face inferior da cobertura, ponto a ponto, nos
    cortes. Devolve o corte com o perfil mais variável (o que atravessa a cumeeira) : vão, altura no beirado, na cumeeira, média
    e a área do perfil (= área de uma empena interior entre beirados, triângulo + retângulo)."""
    from . import camadas, dwfx
    melhor = None
    for i, (_, _, nome) in enumerate(lista):
        if not CORTE.search(nome):
            continue
        f = dwfx.ler(z, i, lista)
        if not f.upm:
            continue
        pap = camadas.mapa(f.camadas, mapa_camadas)
        polys = [Polygon(pl).buffer(0) for e in f.elementos if e.tipo == "path" and e.fill and pap.get(e.camada) == "trama"
                 for pl in e.pls if len(pl) >= 3]
        polys = [p for p in polys if p.area > 0.001]
        if not polys:
            continue
        U = unary_union(polys)
        for xc, k, ya, yb in _colunas(f):
            perfil, passo = [], 0.05
            x = xc - 30.0
            while x <= xc + 30.0:
                inter = U.intersection(LineString([(x, ya - 10.0), (x, yb + 6.0)]))
                cot = sorted((round(k - max(c[1] for c in g.coords), 3), round(k - min(c[1] for c in g.coords), 3))
                             for g in getattr(inter, "geoms", [inter]) if not g.is_empty and g.geom_type == "LineString")
                laje = [c for c in cot if cota_piso - 0.6 <= c[1] <= cota_piso + 0.05 and 0.08 <= c[1] - c[0] <= 0.6]
                if laje:
                    topo = laje[0][1]
                    cima = [c for c in cot if c[0] > topo + 0.2]
                    if cima and not (0.08 <= min(cima)[1] - min(cima)[0] <= 0.6):
                        cima = []               # o que está por cima é parede / platibanda (alta), não a laje da cobertura
                    if cima:
                        perfil.append((x, min(c[0] for c in cima) - topo, topo))
                x += passo
            if len(perfil) < 20:
                continue
            # troço contínuo mais longo (entre as paredes do beirado)
            runs, cur = [], [perfil[0]]
            for a, b in zip(perfil, perfil[1:]):
                if b[0] - a[0] <= 0.5 and abs(b[1] - a[1]) < 0.3:           # falhas da trama até 0,5 m
                    cur.append(b)
                else:
                    runs.append(cur); cur = [b]
            runs.append(cur)
            r = max(runs, key=len)
            hs = [h for _, h, _ in r]
            d = {"corte": nome, "vao": round(r[-1][0] - r[0][0], 2), "h_min": round(min(hs), 2), "h_max": round(max(hs), 2),
                 "h_media": round(sum(hs) / len(hs), 2),
                 "area_perfil": round(sum((b[0] - a[0]) * (a[1] + b[1]) / 2 for a, b in zip(r, r[1:])), 2),
                 # para o desenho de controlo (coordenadas da folha : y = k − cota)
                 "_poly": [(px, k - t) for px, _, t in r] + [(px, k - t - h) for px, h, t in reversed(r)],
                 "_linhas": [pl for e in f.elementos if e.tipo == "path" for pl in e.pls if len(pl) > 1
                             and all(r[0][0] - 3 <= q[0] <= r[-1][0] + 3 and k - (r[0][2] + max(hs) + 2.5) <= q[1] <= k - (r[0][2] - 3) for q in pl)],
                 "_caixa": (r[0][0] - 3, k - (r[0][2] + max(hs) + 2.5), r[-1][0] + 3, k - (r[0][2] - 3)),
                 "_x": (round(r[0][0], 2), round(r[-1][0], 2))}
            if melhor is None or (d["h_max"] - d["h_min"], d["vao"]) > (melhor["h_max"] - melhor["h_min"], melhor["vao"]):
                melhor = d
    return melhor
