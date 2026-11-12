"""Divisões, paredes e vãos a partir dos traços vetoriais (PDF, DXF, ou digitalização já vetorizada).

Como funciona (sem IA, determinístico):
  1. Traços de anotação fora: cotas e linhas de chamada, tracejados, calques de anotação, arcos de porta.
  2. Vãos fechados: uma abertura é o sítio onde AS DUAS faces de uma parede são interrompidas no mesmo troço;
     só aí é traçada a « ponte ». Um alinhamento acidental de duas paredes nunca é ligado.
  3. Os traços são nodados e poligonizados: cada região fechada é uma face.
  4. Uma divisão é a reunião das faces largas (≥ 0,45 m) que se tocam por um simples traço — mobiliário, hachuras,
     bancadas e folhas de porta não a cortam — e que nunca tocam no exterior do desenho (cotas, cartucho, margem).
  5. Paredes: corpo = implantação − divisões; comprimentos ao eixo pelas faces (exteriores e interiores separadas).

Unidades: as coordenadas de entrada estão numa unidade qualquer `u`; `u_por_m` converte (pt PDF, px, mm DXF…).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

CALQUES_ANOTACAO = re.compile(r"(DIM|COT[AE]|ANNO|TEXT|TXT|HATCH|HACH|TRAM|MOB|FURN|AXE|AXIS|EIXO|GRID|GRELHA|TITLE|CARTOUCHE|CARIMBO)", re.I)
AREA_ESCRITA = re.compile(r"(\d{1,4}(?:[.,]\d{1,3})?)\s*m\s*(?:²|2|\^2)", re.I)

LARGURA_MIN_DIVISAO_M = .45     # um espaço mais estreito que isto não é uma divisão (é parede, vão ou armário)
AREA_MIN_DIVISAO_M2 = 1.0
VAO_MIN_M, VAO_MAX_M = .30, 3.20
ESPESSURA_MIN_M, ESPESSURA_MAX_M = .05, .65


def _seg(a, b):
    return (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))


def linhas_de_vetores(vetores: list[dict], *, excluir_calques: bool = True) -> list[dict]:
    """Primitivas do ConstruPilot (line / rect / quad) → segmentos com metadados. Tracejados e curvas ficam de fora."""
    out = []
    for v in vetores or []:
        if str(v.get("dashes") or "[] 0").strip() not in ("[] 0", "", "None"):
            continue
        if v.get("curve_approximation"):
            continue
        camada = str(v.get("layer") or "")
        if excluir_calques and camada and CALQUES_ANOTACAO.search(camada):
            continue
        meta = {"camada": camada, "largura": v.get("stroke_width_pt")}
        t = v.get("type")
        if t == "line":
            out.append({"p": _seg(v["p1"], v["p2"]), **meta})
        elif t == "quad":
            pts = v["points"]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                out.append({"p": _seg(a, b), **meta})
        elif t == "rect":
            x, y, w, h = v["x"], v["y"], v["w"], v["h"]
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                out.append({"p": _seg(a, b), **meta})
    return out


def _sem_cotas(linhas: list[dict], cotas: list[dict], tol: float) -> list[dict]:
    """Remove a linha de cota e as linhas de chamada (perpendiculares que terminam nas extremidades da cota)."""
    if not cotas:
        return linhas
    traços = []
    for c in cotas:
        a, b = (c["x1"], c["y1"]), (c["x2"], c["y2"])
        if math.dist(a, b) > 0:
            traços.append(LineString([a, b]))
    if not traços:
        return linhas
    arvore = STRtree(traços)
    pontos_fim = [Point(p) for t in traços for p in t.coords]
    arvore_pts = STRtree(pontos_fim)
    out = []
    for ln in linhas:
        g = LineString(ln["p"])
        perto = arvore.query(g.buffer(tol))
        if any(_colinear_sobreposto(g, traços[i], tol) for i in perto):
            continue
        # linha de chamada: uma extremidade em cima da extremidade de uma cota e perpendicular a ela
        chamada = False
        for extremo in (Point(ln["p"][0]), Point(ln["p"][1])):
            for i in arvore_pts.query(extremo.buffer(tol * 2)):
                cota = traços[i // 2]
                if _angulo(g) is not None and abs(abs(_angulo(g) - _angulo(cota)) - 90) < 3:
                    chamada = True
        if not chamada:
            out.append(ln)
    return out


def _angulo(g: LineString):
    (x1, y1), (x2, y2) = g.coords[0], g.coords[-1]
    if x1 == x2 and y1 == y2:
        return None
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180


def _colinear_sobreposto(a: LineString, b: LineString, tol: float) -> bool:
    aa, ab = _angulo(a), _angulo(b)
    if aa is None or ab is None:
        return False
    d = abs(aa - ab)
    if min(d, 180 - d) > 1.5:
        return False
    return a.buffer(tol).intersection(b).length > .5 * min(a.length, b.length)


def _grupos_colineares(linhas: list[dict], tol: float):
    """Agrupa os segmentos pela reta que os suporta → intervalos ao longo da reta.

    Ângulo agrupado ao meio grau; posição transversal agrupada por proximidade (cadeia ≤ tol), não por arredondamento —
    numa digitalização, dois troços da mesma face podem estar a 1 px um do outro e cair em lados opostos de um corte."""
    por_ang = defaultdict(list)
    for k, ln in enumerate(linhas):
        (x1, y1), (x2, y2) = ln["p"]
        if x1 == x2 and y1 == y2:
            continue
        ang = math.atan2(y2 - y1, x2 - x1) % math.pi
        if ang > math.pi - math.radians(.25):
            ang -= math.pi
        por_ang[round(math.degrees(ang) * 2) / 2].append((ang, k))
    reduzidos = []
    for chave, itens in por_ang.items():
        ang = sum(a for a, _ in itens) / len(itens)
        ux, uy = math.cos(ang), math.sin(ang)
        nx, ny = -uy, ux
        proj = []
        for _, k in itens:
            (x1, y1), (x2, y2) = linhas[k]["p"]
            d = ((x1 + x2) / 2) * nx + ((y1 + y2) / 2) * ny
            s1, s2 = sorted((x1 * ux + y1 * uy, x2 * ux + y2 * uy))
            proj.append((d, s1, s2))
        proj.sort()
        cachos, atual = [], [proj[0]]
        for item in proj[1:]:
            if item[0] - atual[-1][0] <= tol:
                atual.append(item)
            else:
                cachos.append(atual)
                atual = [item]
        cachos.append(atual)
        for c in cachos:
            pesos = [max(s2 - s1, 1e-9) for _, s1, s2 in c]
            d = sum(p * x[0] for p, x in zip(pesos, c)) / sum(pesos)
            ivs = sorted((s1, s2) for _, s1, s2 in c)
            fundidos = []
            for s1, s2 in ivs:
                if fundidos and s1 <= fundidos[-1][1] + tol:
                    fundidos[-1][1] = max(fundidos[-1][1], s2)
                else:
                    fundidos.append([s1, s2])
            reduzidos.append({"ang": ang, "u": (ux, uy), "n": (nx, ny), "d": d, "intervalos": fundidos})
    return reduzidos


def _pontes(grupos: list[dict], u_por_m: float) -> list[tuple]:
    """Fecha um vão só quando as duas faces da mesma parede estão interrompidas no mesmo troço."""
    gmin, gmax = VAO_MIN_M * u_por_m, VAO_MAX_M * u_por_m
    emin, emax = ESPESSURA_MIN_M * u_por_m, ESPESSURA_MAX_M * u_por_m
    lacunas = []
    for gi, g in enumerate(grupos):
        iv = g["intervalos"]
        for (a1, a2), (b1, b2) in zip(iv, iv[1:]):
            gap = b1 - a2
            if gmin <= gap <= gmax and (a2 - a1) > emin * .8 and (b2 - b1) > emin * .8:
                lacunas.append((gi, a2, b1))
    por_ang = defaultdict(list)
    for item in lacunas:
        por_ang[round(math.degrees(grupos[item[0]]["ang"]) * 2) / 2].append(item)
    pontes, usadas = [], set()
    for ang, itens in por_ang.items():
        for i, (gi, s1, s2) in enumerate(itens):
            for gj, t1, t2 in itens[i + 1:]:
                if gi == gj:
                    continue
                dist = abs(grupos[gi]["d"] - grupos[gj]["d"])
                if not (emin <= dist <= emax):
                    continue
                sob = min(s2, t2) - max(s1, t1)
                if sob < .7 * max(s2 - s1, t2 - t1):
                    continue
                for g_, a, b in ((gi, s1, s2), (gj, t1, t2)):
                    if (g_, round(a, 3)) in usadas:
                        continue
                    usadas.add((g_, round(a, 3)))
                    G = grupos[g_]
                    (ux, uy), (nx, ny), d = G["u"], G["n"], G["d"]
                    pontes.append(((a * ux + d * nx, a * uy + d * ny), (b * ux + d * nx, b * uy + d * ny)))
    return pontes


def _poligonos(g):
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]


def _larga(face: Polygon, u_por_m: float) -> bool:
    return not face.buffer(-LARGURA_MIN_DIVISAO_M * u_por_m / 2, join_style=2).is_empty


def _textos_dentro(poly: Polygon, textos: list[dict]):
    nomes, areas = [], []
    for t in textos or []:
        txt = str(t.get("text") or "").strip()
        if not txt:
            continue
        cx = t["x"] + (t.get("w") or 0) / 2
        cy = t["y"] + (t.get("h") or 0) / 2
        if not poly.contains(Point(cx, cy)):
            continue
        m = AREA_ESCRITA.search(txt)
        if m:
            areas.append(float(m.group(1).replace(",", ".")))
        elif re.search(r"[A-Za-zÀ-ÿ]{2,}", txt):
            nomes.append(txt)
    return nomes, areas


def analisar(linhas: list[dict], u_por_m: float, *, cotas: list[dict] | None = None, textos: list[dict] | None = None,
             max_segmentos: int = 60000, extensao_m: float = .015, tol_min: float = 0.0) -> dict:
    """Divisões + paredes + vãos a partir de segmentos já limpos (`linhas_de_vetores`). Coordenadas em u, u_por_m > 0."""
    if not u_por_m or u_por_m <= 0 or not math.isfinite(u_por_m):
        return {"ok": False, "motivo": "escala desconhecida", "divisoes": []}
    tol = max(.01 * u_por_m, tol_min, 1e-6)
    linhas = [ln for ln in linhas if math.dist(*ln["p"]) >= .03 * u_por_m]
    linhas = _sem_cotas(linhas, cotas or [], tol)
    avisos = []
    if len(linhas) > max_segmentos:
        linhas.sort(key=lambda ln: -math.dist(*ln["p"]))
        avisos.append(f"planta muito densa: só os {max_segmentos} traços mais longos foram analisados")
        linhas = linhas[:max_segmentos]
    grupos = _grupos_colineares(linhas, tol)
    # Para encontrar os vãos, as duas metades da mesma face podem estar ligeiramente desalinhadas (digitalização):
    # tolerância de 3 cm — abaixo da parede mais fina possível (5 cm), nunca confunde as duas faces de uma parede.
    tol_vao = max(tol * 1.5, .03 * u_por_m)
    pontes = _pontes(_grupos_colineares(linhas, tol_vao) if tol_vao > tol else grupos, u_por_m)
    ext = extensao_m * u_por_m
    geoms = []
    for ln in linhas + [{"p": p} for p in pontes]:
        (x1, y1), (x2, y2) = ln["p"]
        L = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        geoms.append(LineString([(x1 - ux * ext, y1 - uy * ext), (x2 + ux * ext, y2 + uy * ext)]))
    if not geoms:
        return {"ok": False, "motivo": "nenhum traço utilizável", "divisoes": [], "estatisticas": {"tracos": 0}}
    # Nodagem robusta: coordenadas encaixadas numa grelha fina (1 mm real, ou ½ px numa digitalização). Sem isto, traços
    # quase coincidentes (ponte sobre o prolongamento de uma face) podem deixar uma face « escapar » pelo vão.
    import shapely
    grelha = max(.001 * u_por_m, tol_min / 4)
    rede = unary_union([shapely.set_precision(g_, grelha) for g_ in geoms])
    faces = [f for f in polygonize(rede) if f.area > (.02 * u_por_m) ** 2]
    if not faces:
        return {"ok": False, "motivo": "nenhuma região fechada", "divisoes": [], "estatisticas": {"tracos": len(linhas), "pontes": len(pontes)}}
    tudo = unary_union(faces)
    contorno = unary_union([p.exterior for p in _poligonos(tudo)])
    periferia = contorno.buffer(tol)
    largas = [f for f in faces if _larga(f, u_por_m)]
    interiores = [f for f in largas if f.boundary.intersection(periferia).length < .05 * u_por_m]
    interiores = _sem_vizinhas_do_exterior(interiores, [f for f in largas if f.boundary.intersection(periferia).length >= .05 * u_por_m],
                                           tol, u_por_m)
    # Reunião das faces largas separadas por um simples traço (mobiliário, bancada, folha de porta).
    arv = STRtree(interiores)
    pai = list(range(len(interiores)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i, f in enumerate(interiores):
        for j in arv.query(f.buffer(tol)):
            if j <= i:
                continue
            comum = f.boundary.intersection(interiores[j].buffer(tol)).length
            if comum > .2 * u_por_m:
                pai[raiz(i)] = raiz(j)
    grupos_f = defaultdict(list)
    for i in range(len(interiores)):
        grupos_f[raiz(i)].append(interiores[i])
    absorvidas = _absorver_estreitas(grupos_f, faces, largas, periferia, tol, u_por_m)
    ids_largas = {id(f) for f in largas}
    paredes_finas = unary_union([f.buffer(tol) for f in faces if id(f) not in ids_largas and id(f) not in absorvidas])
    divisoes = []
    for membros in grupos_f.values():
        u = unary_union([m.buffer(tol / 2, join_style=2) for m in membros]).buffer(-tol / 2, join_style=2)
        for p in _poligonos(u):
            p = Polygon(p.exterior)
            area = p.area / u_por_m ** 2
            if area < AREA_MIN_DIVISAO_M2:
                continue
            # Uma divisão está rodeada de paredes (faces estreitas: corpos de parede, vãos, janelas) em pelo menos
            # 60 % do contorno; uma faixa de cotas, um cartucho ou uma margem toca numa parede de um lado só (< 50 %).
            if p.boundary.intersection(paredes_finas).length < .6 * p.length:
                continue
            nomes, escritas = _textos_dentro(p, textos)
            divisoes.append({"poligono": p, "area_m2": area, "perimetro_m": p.length / u_por_m, "nomes": nomes,
                             "areas_escritas_m2": escritas, "faces": len(membros)})
    divisoes.sort(key=lambda d: (-d["poligono"].centroid.y, d["poligono"].centroid.x))
    # Implantação: divisões + faces estreitas (paredes, vãos) a menos de uma espessura máxima de parede das divisões.
    # Cotas, cartucho e margens (faces largas exteriores) nunca entram.
    implantacao = None
    if divisoes:
        salas = unary_union([d["poligono"] for d in divisoes])
        ids_largas = {id(f) for f in largas}
        estreitas = [f for f in faces if id(f) not in ids_largas]
        alcance = salas.buffer(ESPESSURA_MAX_M * u_por_m, join_style=2)
        corpo = unary_union([salas.buffer(tol / 2, join_style=2)] + [f.buffer(tol / 2, join_style=2) for f in estreitas
                                                                     if f.intersects(alcance) and f.difference(alcance).area < .25 * f.area])
        corpo = corpo.buffer(-tol / 2, join_style=2)
        blocos = [b for b in _poligonos(corpo) if any(b.buffer(tol).contains(d["poligono"].representative_point()) for d in divisoes)]
        implantacao = unary_union([Polygon(b.exterior) for b in blocos]) if blocos else None
    espessuras = _espessuras(grupos, u_por_m)
    paredes = _paredes(implantacao, divisoes, u_por_m, espessuras) if implantacao is not None and divisoes else {}
    vaos = _vaos(faces, pontes, u_por_m)
    return {"ok": bool(divisoes), "motivo": None if divisoes else "nenhuma divisão fechada encontrada",
            "u_por_m": u_por_m, "divisoes": divisoes, "implantacao": implantacao,
            "area_implantacao_m2": implantacao.area / u_por_m ** 2 if implantacao is not None else None,
            "paredes": paredes, "vaos": vaos,
            "estatisticas": {"tracos": len(linhas), "pontes": len(pontes), "faces": len(faces), "faces_interiores": len(interiores)},
            "avisos": avisos}


def _sem_vizinhas_do_exterior(interiores: list, exteriores: list, tol: float, u_por_m: float) -> list:
    """Uma divisão nunca encosta diretamente a uma face exterior larga (faixa de cotas, margem): entre as duas há sempre
    uma parede. Uma face larga que encosta (> 0,3 m) ao exterior é ela própria exterior — e propaga-se."""
    fora = list(exteriores)
    restantes = list(interiores)
    mudou = True
    while mudou and fora:
        mudou = False
        uniao_fora = unary_union([f.buffer(tol) for f in fora])
        for f in list(restantes):
            if f.boundary.intersection(uniao_fora).length > .3 * u_por_m:
                restantes.remove(f)
                fora.append(f)
                mudou = True
    return restantes


def _absorver_estreitas(grupos_f: dict, faces: list, largas: list, periferia, tol: float, u_por_m: float):
    """Uma face estreita (triângulo de folha de porta, armário, segmento de arco) pertence à divisão que a envolve
    quando mais de metade do seu contorno é partilhado com UMA só divisão e com nenhuma outra. Uma parede entre duas
    divisões toca em duas — nunca é absorvida; uma parede exterior toca no exterior — também não."""
    ids_largas = {id(f) for f in largas}
    candidatas = [f for f in faces if id(f) not in ids_largas and f.boundary.intersection(periferia).length < .05 * u_por_m]
    absorvidas = set()
    if not candidatas or not grupos_f:
        return absorvidas
    chaves = list(grupos_f)
    uniao = {k: unary_union([m.buffer(tol) for m in grupos_f[k]]) for k in chaves}
    mudou = True
    while mudou and candidatas:
        mudou = False
        for f in list(candidatas):
            per = f.length
            partes = [(k, f.boundary.intersection(uniao[k]).length) for k in chaves]
            tocam = [(k, L) for k, L in partes if L > .02 * u_por_m]
            if len(tocam) == 1 and tocam[0][1] > .5 * per:
                k = tocam[0][0]
                grupos_f[k].append(f)
                uniao[k] = uniao[k].union(f.buffer(tol))
                candidatas.remove(f)
                absorvidas.add(id(f))
                mudou = True
    return absorvidas


def _espessuras(grupos: list[dict], u_por_m: float) -> list[float]:
    """Espessuras de parede presentes no desenho: distâncias entre faces paralelas que se sobrepõem, pesadas pelo
    comprimento comum e agrupadas ao centímetro. Só as classes com pelo menos 1 m de faces contam."""
    emin, emax = ESPESSURA_MIN_M * u_por_m, ESPESSURA_MAX_M * u_por_m
    peso = defaultdict(float)
    por_ang = defaultdict(list)
    for g in grupos:
        por_ang[round(math.degrees(g["ang"]))].append(g)
    for gs in por_ang.values():
        gs.sort(key=lambda g: g["d"])
        for i, a in enumerate(gs):
            for b in gs[i + 1:]:
                dist = b["d"] - a["d"]
                if dist > emax:
                    break
                if dist < emin:
                    continue
                sob = sum(max(0.0, min(x2, y2) - max(x1, y1)) for x1, x2 in a["intervalos"] for y1, y2 in b["intervalos"])
                if sob > 0:
                    peso[round(dist / u_por_m, 2)] += sob / u_por_m
                    break          # a face seguinte mais próxima é a outra face desta parede
    classes = []
    for t, w in sorted(peso.items(), key=lambda kv: -kv[1]):
        if w >= 1.0 and not any(abs(t - c) < .015 for c in classes):
            classes.append(t)
    return sorted(classes)


def _paredes(implantacao, divisoes, u_por_m, espessuras: list[float] | None = None) -> dict:
    """Corpo das paredes, espessura exterior e comprimentos ao eixo (exteriores / interiores) pelas faces."""
    salas = unary_union([d["poligono"] for d in divisoes])
    corpo = implantacao.difference(salas)
    contorno = implantacao.boundary
    amostras = [contorno.interpolate(t, normalized=True) for t in [i / 200 for i in range(200)]]
    dists = sorted(salas.boundary.distance(p) for p in amostras)
    # espessura exterior: mediana das distâncias contorno → face interior (as janelas e portas não a falseiam)
    t_ext = dists[len(dists) // 2] if dists else 0
    interior_ext = implantacao.buffer(-t_ext, join_style=2) if t_ext else implantacao
    per_ext_fora = implantacao.length
    per_ext_dentro = interior_ext.length if not interior_ext.is_empty else 0
    exteriores = (per_ext_fora + per_ext_dentro) / 2
    soma_salas = sum(d["poligono"].length for d in divisoes)
    interiores_faces = max(0.0, (soma_salas - per_ext_dentro) / 2)
    divisorias = corpo.intersection(interior_ext.buffer(-.005 * u_por_m, join_style=2)) if not interior_ext.is_empty else corpo
    por_espessura = _comprimento_por_espessura(divisorias, u_por_m, espessuras)
    interiores = sum(por_espessura.values()) if por_espessura else interiores_faces / u_por_m
    return {"area_paredes_m2": corpo.area / u_por_m ** 2, "espessura_exterior_m": t_ext / u_por_m,
            "exteriores_eixo_m": exteriores / u_por_m, "interiores_m": interiores,
            "interiores_por_espessura_m": {f"{t:.2f}": round(L, 3) for t, L in sorted(por_espessura.items())},
            "metodo_interiores": "corpo ÷ espessura local" if por_espessura else "faces das divisões"}


def _comprimento_por_espessura(corpo, u_por_m: float, classes: list[float] | None = None, res_m: float = .005) -> dict:
    """Comprimento das divisórias = Σ (área ÷ espessura local), com a espessura lida no eixo médio (transformada de distância).
    Exato para troços retos de espessura constante; as junções não são contadas duas vezes. Agrupado por espessura (cm)."""
    import cv2
    import numpy as np
    from scipy import ndimage
    from skimage.morphology import skeletonize
    if corpo is None or corpo.is_empty:
        return {}
    minx, miny, maxx, maxy = corpo.bounds
    r = res_m * u_por_m
    W, H = int((maxx - minx) / r) + 4, int((maxy - miny) / r) + 4
    if W * H > 40_000_000 or W <= 4 or H <= 4:
        return {}
    m = np.zeros((H, W), np.uint8)
    for p in _poligonos(corpo):
        ext = np.array([[(x - minx) / r + 2, (y - miny) / r + 2] for x, y in p.exterior.coords], np.int32)
        cv2.fillPoly(m, [ext], 1)
        for hole in p.interiors:
            cv2.fillPoly(m, [np.array([[(x - minx) / r + 2, (y - miny) / r + 2] for x, y in hole.coords], np.int32)], 0)
    if m.sum() == 0:
        return {}
    dt = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    esq = skeletonize(m.astype(bool)) & (dt > 1.5)
    if not esq.any():
        return {}
    _, (iy, ix) = ndimage.distance_transform_edt(~esq, return_indices=True)
    t_px = 2 * dt[iy, ix]
    dentro = m.astype(bool) & (t_px > 2)
    t_loc = t_px[dentro] * res_m
    area_px = float(dentro.sum())
    area_m2 = corpo.area / u_por_m ** 2
    if classes:
        # cada pixel do corpo vai para a classe de espessura do desenho mais próxima da sua espessura local;
        # comprimento = área real da classe ÷ espessura exata da classe (sem enviesamento de pixel)
        cl = np.array(classes)
        idx = np.abs(t_loc[:, None] - cl[None, :]).argmin(axis=1)
        final = {}
        for k, t in enumerate(classes):
            frac = float((idx == k).sum()) / area_px
            if frac > 0:
                final[float(t)] = frac * area_m2 / t
        return {t: L for t, L in final.items() if L >= .1}
    t_m = np.round(t_loc, 2)
    out = defaultdict(float)
    for t in np.unique(t_m):
        if not (ESPESSURA_MIN_M <= t <= ESPESSURA_MAX_M):
            continue
        sel = t_m == t
        out[float(t)] += float((1.0 / t_px[dentro][sel]).sum()) * res_m
    classes_o = sorted(out.items(), key=lambda kv: -kv[1])
    final = {}
    for t, L in classes_o:
        alvo = next((k for k in final if abs(k - t) <= .015), None)
        if alvo is None:
            final[t] = L
        else:
            final[alvo] += L
    return {t: L for t, L in final.items() if L >= .1}


def _vaos(faces, pontes, u_por_m) -> dict:
    """Contagem indicativa: portas = pares de pontes; janelas = conjuntos de faixas finas empilhadas (traços de vidro)."""
    portas = len(pontes) // 2
    finas = []
    for f in faces:
        if _larga(f, u_por_m):
            continue
        r = f.minimum_rotated_rectangle
        if r.area <= 0 or f.area / r.area < .9:
            continue
        cs = list(r.exterior.coords)
        lados = sorted((math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])))
        curto, longo = lados[0] / u_por_m, lados[1] / u_por_m
        if .4 <= longo <= 4.0 and curto <= .35:
            finas.append((f, longo))
    pontes_g = [LineString(p) for p in pontes]
    tol = .01 * u_por_m
    finas = [(f, L) for f, L in finas if not any(f.boundary.intersection(p.buffer(tol)).length > .3 * u_por_m for p in pontes_g)]
    pai = list(range(len(finas)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i in range(len(finas)):
        for j in range(i + 1, len(finas)):
            fi, Li = finas[i]
            fj, Lj = finas[j]
            if abs(Li - Lj) < .02 and fi.boundary.intersection(fj.buffer(tol)).length > .8 * min(Li, Lj) * u_por_m:
                pai[raiz(i)] = raiz(j)
    conj = defaultdict(int)
    for i in range(len(finas)):
        conj[raiz(i)] += 1
    janelas = sum(1 for n in conj.values() if n >= 2)
    return {"portas": portas, "janelas": janelas, "indicativo": True}


def poligono_para_lista(p: Polygon, escala: float = 1.0) -> list[list[float]]:
    return [[round(x * escala, 2), round(y * escala, 2)] for x, y in list(p.exterior.coords)[:-1]]
