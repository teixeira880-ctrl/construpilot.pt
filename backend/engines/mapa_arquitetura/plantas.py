"""Medição de uma PLANTA de arquitetura lida do DWFX : paredes (pares de linhas paralelas), envolvente, compartimentos
(fechados pelas paredes e pelos vãos, nomeados pelos rótulos do desenho), classificação das paredes e portas (raio do arco)."""
from __future__ import annotations

import math
import re

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree


EXTERIOR = re.compile(r"varanda|terra[cç]o|balc[aã]o|alpendre|p[aá]tio|logradouro|terrasse|balcon", re.I)
ANOTACAO = re.compile(r"^(pala|g[aá]s|topo muro|projec|proj\.|limite|cota|n[ií]vel|sobe|desce|corte|alçado|alcado)\b", re.I)
ROTULO = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\.\s/]{2,30}")


def _segs(folha, papeis, papel_alvo, minimo=0.10):
    S = []
    for e in folha.elementos:
        if e.tipo == "path" and papeis.get(e.camada) == papel_alvo:
            for pl in e.pls:
                for a, b in zip(pl, pl[1:]):
                    if math.dist(a, b) >= minimo:
                        S.append((a, b))
    return S


def paredes_duplas(S, tmin=0.07, tmax=0.45):
    """Pares de segmentos paralelos (< 1°) afastados tmin–tmax, sobrepostos ≥ 0,15 m → troço de parede {t, L, eixo, n}."""
    info = []
    for a, b in S:
        L = math.dist(a, b)
        info.append((a, b, (b[0] - a[0]) / L, (b[1] - a[1]) / L, L))
    if not info:
        return []
    tree = STRtree([LineString([a, b]) for a, b, *_ in info])
    usados = {}
    for i, (a, b, ux, uy, L) in enumerate(info):
        best = None
        for j in tree.query(LineString([a, b]).buffer(tmax)):
            j = int(j)
            if j == i:
                continue
            c, d, vx, vy, M = info[j]
            if abs(ux * vy - uy * vx) > 0.017:
                continue
            g = abs((c[0] - a[0]) * (-uy) + (c[1] - a[1]) * ux)
            if not (tmin <= g <= tmax):
                continue
            s1, s2 = sorted(((c[0] - a[0]) * ux + (c[1] - a[1]) * uy, (d[0] - a[0]) * ux + (d[1] - a[1]) * uy))
            ov = min(L, s2) - max(0, s1)
            if ov < 0.15:
                continue
            if best is None or g < best[0] - 1e-6:
                best = (g, j, ov, max(0, s1), min(L, s2))
        if best:
            g, j, ov, o0, o1 = best
            key = (min(i, j), max(i, j))
            if key not in usados:
                usados[key] = {"t": round(g, 3), "L": ov, "eixo": ((a[0] + ux * o0, a[1] + uy * o0), (a[0] + ux * o1, a[1] + uy * o1)),
                               "n": (-uy, ux)}
    return list(usados.values())


def envolvente(folha, papeis):
    par = [LineString(pl) for e in folha.elementos if e.tipo == "path" and papeis.get(e.camada) in ("paredes", "trama")
           for pl in e.pls if len(pl) >= 2]
    if not par:
        return [], [], par
    tree = STRtree(par)

    def toca(p):
        pt = Point(p)
        return any(par[int(i)].distance(pt) < 0.03 for i in tree.query(pt.buffer(0.03)))
    vaos = []
    for a, b in _segs(folha, papeis, "fino", 0.4):
        if math.dist(a, b) <= 6.0 and toca(a) and toca(b):
            vaos.append(LineString([a, b]))
    massa = unary_union([ln.buffer(0.02) for ln in par + vaos])
    fech = massa.buffer(0.3, join_style=2).buffer(-0.3, join_style=2)
    blocos = [Polygon(g.exterior) for g in getattr(fech, "geoms", [fech]) if not g.is_empty and Polygon(g.exterior).area > 20]
    return blocos, vaos, par


def rotulos(folha):
    out = []
    for e in folha.elementos:
        if e.tipo == "texto" and ROTULO.fullmatch(e.texto) and not ANOTACAO.match(e.texto):
            out.append((e.texto.strip(), e.pos))
    return out


def portas(folha):
    """Arcos de folha de porta (raio 0,55–1,30 m) ; a mesma porta desenhada em vários caminhos conta uma vez."""
    out = []
    for e in folha.elementos:
        if e.tipo != "path" or not e.arcos:
            continue
        w = max(e.arcos)
        if not 0.55 <= w <= 1.30:
            continue
        pts = [q for pl in e.pls for q in pl]
        if not pts:
            continue
        x = sum(q[0] for q in pts) / len(pts); y = sum(q[1] for q in pts) / len(pts)
        if not any(abs(x - u["x"]) < 0.3 and abs(y - u["y"]) < 0.3 for u in out):
            out.append({"x": round(x, 2), "y": round(y, 2), "L": round(w, 2)})
    return out


COTA = re.compile(r"[+]?(\d{1,4}[.,]\d{2})")


def _cota_piso(folha, interiores) -> dict | None:
    """Cota do pavimento do piso = valor de cota (nnn.nn) mais repetido DENTRO dos compartimentos interiores da planta
    (as cotas do terreno e dos outros pisos ficam fora). Devolve {valor, ocorrencias, candidatos}."""
    from collections import Counter
    if not interiores:
        return None
    U = unary_union(interiores)
    c, c_cam = Counter(), Counter()
    for e in folha.elementos:
        if e.tipo == "texto":
            m = COTA.fullmatch(e.texto.strip())
            if m and U.contains(Point(e.pos)):
                v = round(float(m.group(1).replace(",", ".")), 2)
                c[v] += 1
                if re.search(r"cota|level|n[ií]v|alt|elev", e.camada or "", re.I):
                    c_cam[v] += 1
    c = c_cam or c                  # há camada de cotas : as áreas escritas (m²) não contam como cota
    if not c:
        return None
    return {"candidatos": dict(c.most_common()), "valor": None, "ocorrencias": 0}


def medir(folha, papeis, ponte=0.55) -> dict:
    blocos, vaos, par = envolvente(folha, papeis)
    if not par:
        return {"ok": False, "aviso": "sem camada de paredes reconhecida"}
    env = unary_union(blocos) if blocos else None
    massa = unary_union([ln.buffer(0.02) for ln in par + vaos])
    M = massa.buffer(ponte, join_style=2)
    labs = rotulos(folha)
    louca = [Point(pl[0]) for e in folha.elementos if e.tipo == "path" and papeis.get(e.camada) == "sanitarios" for pl in e.pls if pl]
    coz = [Point(pl[0]) for e in folha.elementos if e.tipo == "path" and papeis.get(e.camada) == "cozinha" for pl in e.pls if pl]
    duplas = paredes_duplas(_segs(folha, papeis, "paredes"))
    polys = []
    for g in getattr(M, "geoms", [M]):
        for h in getattr(g, "interiors", []):
            r = Polygon(h).buffer(ponte, join_style=2).difference(massa)
            # +0,02 m : repõe a face da parede (a massa das paredes foi engrossada 2 cm para fechar as linhas)
            polys += [p.buffer(0.02, join_style=2) for p in getattr(r, "geoms", [r]) if p.area >= 1.0]
    dentro = [[t for t, q in labs if p.contains(Point(q))] for p in polys]
    soltos = [(t, q) for t, q in labs if not any(p.contains(Point(q)) for p in polys)]   # rótulo fora de todos (sobre a parede)
    areas_txt = []
    for e in folha.elementos:                       # áreas escritas pelo arquiteto dentro do compartimento (controlo cruzado)
        m_ = re.fullmatch(r"(\d{1,3}[.,]\d{1,2})\s*(m2|m²)?", e.texto.strip()) if e.tipo == "texto" else None
        if m_:
            areas_txt.append((float(m_.group(1).replace(",", ".")), e.pos))
    comps = []
    for p, dd in zip(polys, dentro):
        if not dd:
            perto = sorted((p.distance(Point(q)), t) for t, q in soltos)
            dd = [perto[0][1]] if perto and perto[0][0] < 0.6 else []
        nome = " + ".join(sorted(set(dd))) if dd else None
        origem = "rótulo" if nome else "dedução"
        if nome is None:
            rp = p.buffer(-0.05)
            elev = sum(w["L"] for w in duplas if abs(w["t"] - 0.25) < 0.02 and p.buffer(0.3).intersects(LineString(w["eixo"])))
            if sum(1 for q in louca if rp.contains(q)) >= 3:
                nome = "Instalação sanitária"
            elif sum(1 for q in coz if rp.contains(q)) >= 3:
                nome = "Cozinha"
            elif p.area < 6 and elev >= 0.6 * p.exterior.length / 2:
                nome = "Caixa do elevador"
            else:
                nome = "Sem rótulo (hall / circulação / arrumo)"
        ext = bool(EXTERIOR.search(nome)) or (env is not None and not env.contains(p.representative_point()))
        escrita = [v for v, q in areas_txt if p.contains(Point(q)) and 0.5 * p.area <= v <= 1.5 * p.area]
        comps.append({"nome": nome, "origem": origem, "area": round(p.area, 2), "area_no_desenho": escrita[0] if len(escrita) == 1 else None,
                      "perimetro": round(p.exterior.length + sum(i.length for i in p.interiors), 2),
                      "exterior": ext, "_geo": p})
    interiores = unary_union([c["_geo"] for c in comps if not c["exterior"]]) if comps else None
    paredes = []
    for w in duplas:
        (a, b), n, t = w["eixo"], w["n"], w["t"]
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        l1 = Point(m[0] - n[0] * 0.4, m[1] - n[1] * 0.4)
        l2 = Point(m[0] + n[0] * (t + 0.4), m[1] + n[1] * (t + 0.4))
        i1 = interiores is not None and interiores.contains(l1)
        i2 = interiores is not None and interiores.contains(l2)
        tipo = "interior" if (i1 and i2) else ("fachada" if (i1 or i2) else "exterior / muro")
        paredes.append({"espessura": round(t, 2), "comprimento": round(w["L"], 2), "tipo": tipo})
    cota = _cota_piso(folha, [c["_geo"] for c in comps if not c["exterior"]])
    for c in comps:
        g = c.pop("_geo")
        c["_poly"] = [list(g.exterior.coords)]
    pts = portas(folha)
    for d in pts:          # porta a menos de 0,6 m do contorno exterior = porta de fachada / varanda (vai para os vãos)
        d["tipo"] = "fachada" if env is not None and env.boundary.distance(Point(d["x"], d["y"])) < 0.6 else "interior"
    dims = None
    if blocos:
        b = unary_union(blocos).bounds
        dims = (round(b[2] - b[0], 2), round(b[3] - b[1], 2))
    linhas = [list(ln.coords) for ln in par]
    return {"ok": True, "compartimentos": comps, "paredes": paredes, "portas": pts, "_dims": dims, "_linhas": linhas, "cota": cota,
            "envolvente": {"area": round(sum(b.area for b in blocos), 2), "perimetro": round(sum(b.length for b in blocos), 2),
                           "blocos": len(blocos)}}
