"""Tudo o que se deriva do modelo único: corpos das paredes, divisões, lajes, cobertura, sólidos 3D e medições.

Regras de medição (geométricas, sem rácios):
- A planta de cada piso é a união exata dos corpos das paredes; nos encontros nenhuma área é contada duas vezes
  (cada parede fica com a sua parte, por ordem: exteriores, depois as mais espessas).
- Comprimento líquido de uma parede = área em planta que lhe cabe / espessura. Área líquida = comprimento líquido
  × altura − vãos. Volume de cada camada = área líquida × espessura da camada.
- Divisões = vazios fechados por paredes (área útil entre faces). Sem paredes a fechar, não há divisão.
- Cobertura: águas calculadas sobre o contorno do último piso + beiral; área real = área em planta / cos(inclinação).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from engines.estudio_projeto import materiais as MAT
from engines.estudio_projeto.modelo import espessura

JUNTA = 0.012          # dois eixos a menos desta distância encontram-se
FOLGA_VAO = 0.05       # distância mínima de um vão ao extremo da parede
AREA_MIN_DIVISAO = 0.30
R = lambda v, n=3: round(float(v), n)  # noqa: E731


def _polys(g) -> List[Polygon]:
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon" and not p.is_empty]


def _anel(p: Polygon) -> List[List[float]]:
    return [[R(x), R(y)] for x, y in list(orient(p, 1.0).exterior.coords)[:-1]]


def cotas(m: Dict[str, Any]) -> List[Dict[str, float]]:
    """Cotas por piso: z0 = pavimento (AS), z1 = face inferior da laje de cima (AI), laje sob o piso de z0 − e a z0."""
    out, z = [], 0.0
    for k, p in enumerate(m["pisos"]):
        e = m["laje_terrea_m"] if k == 0 else p["laje_m"]
        if k > 0:
            z += e
        out.append({"id": p["id"], "z0": R(z), "z1": R(z + p["pe_direito_m"]), "laje_sob_m": e})
        z += p["pe_direito_m"]
    return out


# ---------------------------------------------------------------- paredes
def _parede_geo(w: Dict[str, Any], t: float) -> Optional[Dict[str, Any]]:
    ax, ay = w["a"]
    bx, by = w["b"]
    L = math.hypot(bx - ax, by - ay)
    if L < 0.05:
        return None
    ux, uy = (bx - ax) / L, (by - ay) / L
    return {"L": L, "u": (ux, uy), "n": (-uy, ux), "t": t, "eixo": LineString([(ax, ay), (bx, by)])}


def _corpo(w: Dict[str, Any], g: Dict[str, Any], ea: float, eb: float) -> Polygon:
    (ux, uy), (nx, ny), h = g["u"], g["n"], g["t"] / 2
    ax, ay = w["a"][0] - ux * ea, w["a"][1] - uy * ea
    bx, by = w["b"][0] + ux * eb, w["b"][1] + uy * eb
    return Polygon([(ax + nx * h, ay + ny * h), (bx + nx * h, by + ny * h), (bx - nx * h, by - ny * h), (ax - nx * h, ay - ny * h)])


def _vaos_da_parede(w, g, vs, altura, erros) -> List[Dict[str, Any]]:
    out, ocupado = [], []
    for v in sorted(vs, key=lambda v: v["pos_m"]):
        u0, u1 = v["pos_m"] - v["largura_m"] / 2, v["pos_m"] + v["largura_m"] / 2
        motivo = None
        if u0 < FOLGA_VAO - 1e-6 or u1 > g["L"] - FOLGA_VAO + 1e-6:
            motivo = "não cabe no comprimento da parede"
        elif v["peitoril_m"] + v["altura_m"] > altura + 1e-6:
            motivo = "é mais alto do que a parede"
        elif any(u0 < b - 1e-6 and u1 > a + 1e-6 for a, b in ocupado):
            motivo = "sobrepõe-se a outro vão"
        if motivo:
            erros.append({"codigo": "VAO_INVALIDO", "id": v["id"], "msg": f"O vão {v['id']} {motivo}."})
        else:
            ocupado.append((u0, u1))
        out.append({**v, "u0": R(u0), "u1": R(u1), "valido": motivo is None})
    return out


# ---------------------------------------------------------------- cobertura
def _retangulo(p: Polygon) -> bool:
    c = list(p.exterior.coords)[:-1]
    if len(c) != 4:
        return False
    for i in range(4):
        (x0, y0), (x1, y1), (x2, y2) = c[i], c[(i + 1) % 4], c[(i + 2) % 4]
        d1, d2 = (x1 - x0, y1 - y0), (x2 - x1, y2 - y1)
        if abs(d1[0] * d2[0] + d1[1] * d2[1]) > 1e-3 * math.hypot(*d1) * math.hypot(*d2):
            return False
    return True


def _clip(pts: List[Tuple[float, float]], a: float, b: float, c: float) -> List[Tuple[float, float]]:
    """Parte do polígono convexo com a·x + b·y ≤ c."""
    out: List[Tuple[float, float]] = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
        if fp <= 1e-9:
            out.append(p)
        if (fp < -1e-9 and fq > 1e-9) or (fp > 1e-9 and fq < -1e-9):
            s = fp / (fp - fq)
            out.append((p[0] + s * (q[0] - p[0]), p[1] + s * (q[1] - p[1])))
    return out


def _aguas(pegada: Polygon, cob: Dict[str, Any], z_topo: float) -> Dict[str, Any]:
    """Águas de uma cobertura inclinada sobre um contorno convexo. z(p) = z_beirado + tan·min(distância às linhas dos
    lados que escoam). Devolve {"faces", "empenas", "z_cumeeira", "z_beirado"} ou {"motivo"} se a forma não permite."""
    tipo, tan, beiral = cob["tipo"], math.tan(math.radians(cob["inclinacao_graus"])), cob["beiral_m"]
    pg = orient(pegada.simplify(0.002), 1.0)
    if pg.convex_hull.area - pg.area > 1e-4:
        return {"motivo": "A cobertura inclinada automática só existe, para já, em plantas convexas (sem reentrâncias). "
                          "Nesta planta escolha «plana» ou simplifique o contorno do último piso."}
    if tipo in ("duas_aguas", "uma_agua") and not _retangulo(pg):
        return {"motivo": "As coberturas de uma e de duas águas pedem um último piso retangular; use «quatro águas» ou «plana»."}
    beirado = orient(pg.buffer(beiral, join_style=2, mitre_limit=10.0), 1.0) if beiral > 0 else pg
    E = list(beirado.exterior.coords)[:-1]
    n = len(E)
    arestas = []
    for i in range(n):
        (x0, y0), (x1, y1) = E[i], E[(i + 1) % n]
        L = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L          # normal para dentro (anel anti-horário)
        arestas.append({"n": (nx, ny), "c": nx * x0 + ny * y0, "L": L, "dir": ((x1 - x0) / L, (y1 - y0) / L),
                        "meio": ((x0 + x1) / 2, (y0 + y1) / 2)})
    if tipo == "quatro_aguas":
        escoam = list(range(n))
    else:
        eixo = cob["cumeeira"]
        if eixo == "auto":
            i0 = max(range(n), key=lambda i: arestas[i]["L"])
        else:
            alvo = (1.0, 0.0) if eixo == "x" else (0.0, 1.0)
            i0 = max(range(n), key=lambda i: abs(arestas[i]["dir"][0] * alvo[0] + arestas[i]["dir"][1] * alvo[1]))
        if tipo == "duas_aguas":
            escoam = [i0, (i0 + 2) % n]          # os dois lados paralelos à cumeeira (contorno retangular)
        else:
            chave = {"frente": lambda a: a["meio"][1], "tardoz": lambda a: -a["meio"][1],
                     "esquerda": lambda a: a["meio"][0], "direita": lambda a: -a["meio"][0]}[cob["lado_baixo"]]
            escoam = [min(range(n), key=lambda i: chave(arestas[i]))]
    z_beirado = z_topo - tan * beiral

    def dist(i, p):
        return arestas[i]["n"][0] * p[0] + arestas[i]["n"][1] * p[1] - arestas[i]["c"]

    def z_em(p):
        return z_beirado + tan * min(dist(i, p) for i in escoam)

    faces, z_max = [], z_topo
    cos = math.cos(math.radians(cob["inclinacao_graus"]))
    for i in escoam:
        pts = list(E)
        for j in escoam:
            if j == i:
                continue
            ni, nj = arestas[i]["n"], arestas[j]["n"]
            pts = _clip(pts, ni[0] - nj[0], ni[1] - nj[1], arestas[i]["c"] - arestas[j]["c"])
            if len(pts) < 3:
                break
        if len(pts) < 3:
            continue
        pl = Polygon(pts)
        if pl.area < 1e-4:
            continue
        p3 = [[R(x), R(y), R(z_beirado + tan * dist(i, (x, y)))] for x, y in pts]
        z_max = max(z_max, max(p[2] for p in p3))
        faces.append({"pts": p3, "area_planta_m2": R(pl.area, 2), "area_m2": R(pl.area / cos, 2)})
    # empenas: onde a cobertura fica acima do topo das paredes ao longo do contorno do último piso
    empenas = []
    P = list(pg.exterior.coords)[:-1]
    for k in range(len(P)):
        p, q = P[k], P[(k + 1) % len(P)]
        ts = {0.0, 1.0}
        for a in range(len(escoam)):
            for b in range(a + 1, len(escoam)):
                i, j = escoam[a], escoam[b]
                fp, fq = dist(i, p) - dist(j, p), dist(i, q) - dist(j, q)
                if (fp < -1e-9 and fq > 1e-9) or (fp > 1e-9 and fq < -1e-9):
                    ts.add(fp / (fp - fq))
        topo = []
        for t in sorted(ts):
            x, y = p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])
            topo.append((x, y, max(z_topo, z_em((x, y)))))
        if max(z for _, _, z in topo) - z_topo > 0.01:
            base = [[R(p[0]), R(p[1]), R(z_topo)], [R(q[0]), R(q[1]), R(z_topo)]]
            cima = [[R(x), R(y), R(z)] for x, y, z in reversed(topo) if z - z_topo > 1e-6]
            pts3 = base + cima
            # área no plano vertical da empena (trapézios entre pontos consecutivos do topo)
            Lpq = math.hypot(q[0] - p[0], q[1] - p[1])
            ts_ord = sorted(ts)
            area = sum((ts_ord[s + 1] - ts_ord[s]) * Lpq * ((topo[s][2] - z_topo) + (topo[s + 1][2] - z_topo)) / 2
                       for s in range(len(ts_ord) - 1))
            empenas.append({"pts": pts3, "area_m2": R(area, 2)})
    return {"faces": faces, "empenas": empenas, "z_cumeeira": R(z_max), "z_beirado": R(z_beirado),
            "beirado": [[R(x), R(y)] for x, y in E], "perimetro_beirado_m": R(beirado.length, 2)}


# ---------------------------------------------------------------- derivação completa
def derivar(m: Dict[str, Any]) -> Dict[str, Any]:
    erros: List[Dict[str, Any]] = []
    avisos: List[Dict[str, Any]] = []
    tipos = m["tipos_parede"]
    cz = cotas(m)
    por_piso_vaos: Dict[str, List[dict]] = {}
    for v in m["vaos"]:
        por_piso_vaos.setdefault(v["parede"], []).append(v)

    pisos_out, paredes_out, divisoes_out, lajes_out = [], [], [], []
    pegadas: List[Any] = []
    med_paredes, med_div = [], []
    fachada = {"perimetro_m": 0.0, "area_bruta_m2": 0.0, "area_vaos_m2": 0.0}
    cont_vaos: Dict[tuple, Dict[str, Any]] = {}

    for k, piso in enumerate(m["pisos"]):
        z0, z1 = cz[k]["z0"], cz[k]["z1"]
        altura = piso["pe_direito_m"]
        ws = [w for w in m["paredes"] if w["piso"] == piso["id"]]
        geo: Dict[str, Dict[str, Any]] = {}
        for w in ws:
            g = _parede_geo(w, espessura(tipos[w["tipo"]]))
            if g is None:
                erros.append({"codigo": "PAREDE_CURTA", "id": w["id"], "msg": f"A parede {w['id']} tem menos de 5 cm."})
                continue
            geo[w["id"]] = g
        vivos = [w for w in ws if w["id"] in geo]
        corpos: Dict[str, Polygon] = {}
        for w in vivos:
            g = geo[w["id"]]
            ext = []
            for ponta in (w["a"], w["b"]):
                pt, e = Point(ponta), 0.0
                for o in vivos:
                    if o["id"] != w["id"] and geo[o["id"]]["eixo"].distance(pt) < JUNTA:
                        e = max(e, geo[o["id"]]["t"] / 2)
                ext.append(e)
            g["ea"], g["eb"] = ext
            corpos[w["id"]] = _corpo(w, g, *ext)
        uniao = unary_union(list(corpos.values())) if corpos else None
        partes = _polys(uniao)
        pegada = unary_union([Polygon(p.exterior) for p in partes]) if partes else None
        pegadas.append(pegada)
        # parte de cada parede na planta (sem contar encontros duas vezes)
        ordem = sorted(vivos, key=lambda w: (not tipos[w["tipo"]]["exterior"], -geo[w["id"]]["t"], w["id"]))
        tomado = None
        parte_area: Dict[str, float] = {}
        for w in ordem:
            c = corpos[w["id"]]
            parte_area[w["id"]] = (c if tomado is None else c.difference(tomado)).area
            tomado = c if tomado is None else unary_union([tomado, c])
        # divisões
        divs = []
        for p in partes:
            for anel in p.interiors:
                pl = Polygon(anel)
                if pl.area >= AREA_MIN_DIVISAO:
                    divs.append(pl)
        divs.sort(key=lambda pl: (round(pl.centroid.y, 2), round(pl.centroid.x, 2)))
        rot = [r for r in m["rotulos"] if r["piso"] == piso["id"]]
        vaos_piso = []
        for w in vivos:
            g = geo[w["id"]]
            tipo = tipos[w["tipo"]]
            vs = _vaos_da_parede(w, g, por_piso_vaos.get(w["id"], []), altura, erros)
            validos = [v for v in vs if v["valido"]]
            a_vaos = sum(v["largura_m"] * v["altura_m"] for v in validos)
            comp_liq = parte_area[w["id"]] / g["t"]
            a_bruta = comp_liq * altura
            a_liq = max(0.0, a_bruta - a_vaos)
            med_paredes.append({
                "id": w["id"], "piso": piso["id"], "tipo": w["tipo"], "nome_tipo": tipo["nome"], "exterior": tipo["exterior"],
                "comprimento_eixo_m": R(g["L"], 3), "comprimento_liquido_m": R(comp_liq, 3), "altura_m": R(altura, 3),
                "espessura_m": R(g["t"], 3), "area_bruta_m2": R(a_bruta, 2), "area_vaos_m2": R(a_vaos, 2),
                "area_liquida_m2": R(a_liq, 2), "volume_m3": R(a_liq * g["t"], 3),
                "camadas": [{"material": c["material"], "esp_m": c["esp_m"], "area_m2": R(a_liq, 2),
                             "volume_m3": R(a_liq * c["esp_m"], 3)} for c in tipo["camadas"]]})
            if tipo["exterior"]:
                fachada["area_vaos_m2"] += a_vaos
            for v in vs:
                cx, cy = w["a"][0] + g["u"][0] * v["pos_m"], w["a"][1] + g["u"][1] * v["pos_m"]
                vaos_piso.append({**v, "piso": piso["id"], "centro": [R(cx), R(cy)], "z0": R(z0 + v["peitoril_m"]),
                                  "z1": R(z0 + v["peitoril_m"] + v["altura_m"]), "exterior": tipo["exterior"]})
                if v["valido"]:
                    key = (v["tipo"], v["largura_m"], v["altura_m"])
                    c = cont_vaos.setdefault(key, {"tipo": v["tipo"], "largura_m": v["largura_m"], "altura_m": v["altura_m"],
                                                   "quantidade": 0, "area_m2": 0.0, "ids": []})
                    c["quantidade"] += 1
                    c["area_m2"] = R(c["area_m2"] + v["largura_m"] * v["altura_m"], 2)
                    c["ids"].append(v["id"])
            paredes_out.append({"id": w["id"], "piso": piso["id"], "a": w["a"], "b": w["b"], "tipo": w["tipo"],
                                "esp_m": R(g["t"]), "comprimento_m": R(g["L"]), "ext_a": R(g["ea"]), "ext_b": R(g["eb"]),
                                "z0": z0, "altura_m": altura, "exterior": tipo["exterior"],
                                "corpo": _anel(corpos[w["id"]]),
                                "vaos": [{"id": v["id"], "tipo": v["tipo"], "u0": v["u0"], "u1": v["u1"], "z0": v["peitoril_m"],
                                          "z1": R(v["peitoril_m"] + v["altura_m"]), "valido": v["valido"],
                                          "lado": v["lado"], "dobradica": v["dobradica"]} for v in vs]})
        for i, pl in enumerate(divs, 1):
            nome = next((r["nome"] for r in rot if pl.contains(Point(r["x"], r["y"]))), f"Divisão {i}")
            a_vaos_div, portas = 0.0, 0.0
            for v in vaos_piso:
                if not v["valido"]:
                    continue
                g = geo[v["parede"]]
                (ux, uy), (nx, ny), hw, ht = g["u"], g["n"], v["largura_m"] / 2, g["t"] / 2 + 0.03
                cx, cy = v["centro"]
                caixa = Polygon([(cx - ux * hw + nx * ht, cy - uy * hw + ny * ht), (cx + ux * hw + nx * ht, cy + uy * hw + ny * ht),
                                 (cx + ux * hw - nx * ht, cy + uy * hw - ny * ht), (cx - ux * hw - nx * ht, cy - uy * hw - ny * ht)])
                if caixa.intersects(pl):
                    a_vaos_div += v["largura_m"] * v["altura_m"]
                    if v["peitoril_m"] < 0.05:
                        portas += v["largura_m"]
            rp = pl.representative_point()
            d = {"id": f"{piso['id']}_d{i}", "piso": piso["id"], "nome": nome, "area_m2": R(pl.area, 2),
                 "perimetro_m": R(pl.length, 2), "pts": _anel(pl), "centro": [R(rp.x), R(rp.y)],
                 "area_paredes_m2": R(max(0.0, pl.length * altura - a_vaos_div), 2), "rodape_m": R(max(0.0, pl.length - portas), 2)}
            divisoes_out.append(d)
            med_div.append({kk: d[kk] for kk in ("id", "piso", "nome", "area_m2", "perimetro_m", "area_paredes_m2", "rodape_m")})
        soltas = [w["id"] for w in vivos if geo[w["id"]]["ea"] == 0 and geo[w["id"]]["eb"] == 0 and len(vivos) > 1]
        if soltas:
            avisos.append({"codigo": "PAREDES_SOLTAS", "ids": soltas, "msg": f"{piso['nome']}: {len(soltas)} parede(s) sem ligação a outras."})
        if vivos and not divs:
            avisos.append({"codigo": "SEM_DIVISOES", "msg": f"{piso['nome']}: as paredes não fecham nenhuma divisão."})
        if k == 0 and pegada is not None and not pegada.is_empty:
            fachada["perimetro_m"] = pegada.length
        pisos_out.append({"id": piso["id"], "nome": piso["nome"], "z0": z0, "z1": z1, "pe_direito_m": altura,
                          "area_bruta_m2": R(pegada.area, 2) if pegada is not None else 0.0,
                          "pegada": [_anel(p) for p in _polys(pegada)],
                          "paredes_planta": [{"ext": _anel(p), "furos": [[[R(x), R(y)] for x, y in list(a.coords)[:-1]] for a in p.interiors]}
                                             for p in partes]})

    # lajes: sob cada piso (cobre o piso de baixo e apoia o de cima) e laje de cobertura
    med_lajes = []
    n = len(m["pisos"])
    for k in range(n + 1):
        if k == 0:
            g, e, zt, nome = pegadas[0], m["laje_terrea_m"], cz[0]["z0"], "Laje térrea"
        elif k < n:
            vivas = [x for x in (pegadas[k - 1], pegadas[k]) if x is not None and not x.is_empty]
            g = unary_union(vivas) if vivas else None
            e, zt, nome = m["pisos"][k]["laje_m"], cz[k]["z0"], f"Laje do {m['pisos'][k]['nome'].lower()}"
        else:
            g, e, nome = pegadas[n - 1], m["cobertura"]["laje_m"], "Laje de cobertura"
            zt = cz[n - 1]["z1"] + e
        ps = _polys(g)
        if not ps:
            continue
        area = sum(p.area for p in ps)
        lajes_out.append({"nome": nome, "z0": R(zt - e), "z1": R(zt), "polys": [_anel(p) for p in ps]})
        med_lajes.append({"nome": nome, "area_m2": R(area, 2), "espessura_m": R(e, 3), "volume_m3": R(area * e, 3)})

    # terraços: parte de um piso que não tem piso por cima
    terracos = []
    for k in range(n - 1):
        if pegadas[k] is None or pegadas[k + 1] is None:
            continue
        dif = pegadas[k].difference(pegadas[k + 1])
        a = sum(p.area for p in _polys(dif) if p.area > 0.05)
        if a > 0.05:
            terracos.append({"sobre": m["pisos"][k]["nome"], "area_m2": R(a, 2)})

    # cobertura
    cob = m["cobertura"]
    topo = pegadas[-1] if pegadas else None
    z_topo = (cz[-1]["z1"] + cob["laje_m"]) if cz else 0.0
    cobertura = {"tipo": cob["tipo"], "faces": [], "empenas": [], "z_topo_paredes": R(z_topo), "z_cumeeira": R(z_topo),
                 "area_m2": 0.0, "area_planta_m2": 0.0, "perimetro_beirado_m": 0.0}
    for p in _polys(topo):
        if cob["tipo"] == "plana":
            cobertura["area_m2"] = R(cobertura["area_m2"] + p.area, 2)
            cobertura["area_planta_m2"] = R(cobertura["area_planta_m2"] + p.area, 2)
            cobertura["perimetro_beirado_m"] = R(cobertura["perimetro_beirado_m"] + p.length, 2)
            continue
        r = _aguas(p, cob, z_topo)
        if r.get("motivo"):
            avisos.append({"codigo": "COBERTURA_FORMA", "msg": r["motivo"]})
            continue
        cobertura["faces"] += r["faces"]
        cobertura["empenas"] += r["empenas"]
        cobertura["z_cumeeira"] = max(cobertura["z_cumeeira"], r["z_cumeeira"])
        cobertura["z_beirado"] = r["z_beirado"]
        cobertura["area_m2"] = R(cobertura["area_m2"] + sum(f["area_m2"] for f in r["faces"]), 2)
        cobertura["area_planta_m2"] = R(cobertura["area_planta_m2"] + sum(f["area_planta_m2"] for f in r["faces"]), 2)
        cobertura["perimetro_beirado_m"] = R(cobertura["perimetro_beirado_m"] + r["perimetro_beirado_m"], 2)
    a_empenas = sum(e["area_m2"] for e in cobertura["empenas"])

    # fachada exterior (face exterior real: perímetro do contorno × altura de piso a piso, mais empenas, menos vãos)
    for k, p in enumerate(pisos_out):
        per = sum(Polygon(a).length for a in p["pegada"])
        e_cima = m["pisos"][k + 1]["laje_m"] if k + 1 < n else cob["laje_m"]
        fachada["area_bruta_m2"] += per * (m["pisos"][k]["pe_direito_m"] + e_cima)
    fachada["area_bruta_m2"] += a_empenas
    fachada = {"perimetro_m": R(fachada["perimetro_m"], 2), "area_bruta_m2": R(fachada["area_bruta_m2"], 2),
               "area_vaos_m2": R(fachada["area_vaos_m2"], 2),
               "area_liquida_m2": R(fachada["area_bruta_m2"] - fachada["area_vaos_m2"], 2)}

    por_tipo: Dict[str, Dict[str, Any]] = {}
    for w in med_paredes:
        t = por_tipo.setdefault(w["tipo"], {"tipo": w["tipo"], "nome": w["nome_tipo"], "comprimento_liquido_m": 0.0,
                                            "area_liquida_m2": 0.0, "camadas": [dict(c, area_m2=0.0, volume_m3=0.0) for c in w["camadas"]]})
        t["comprimento_liquido_m"] = R(t["comprimento_liquido_m"] + w["comprimento_liquido_m"], 3)
        t["area_liquida_m2"] = R(t["area_liquida_m2"] + w["area_liquida_m2"], 2)
        for c, cw in zip(t["camadas"], w["camadas"]):
            c["area_m2"] = R(c["area_m2"] + cw["area_m2"], 2)
            c["volume_m3"] = R(c["volume_m3"] + cw["volume_m3"], 3)

    xs = [c for w in m["paredes"] for c in (w["a"][0], w["b"][0])]
    ys = [c for w in m["paredes"] for c in (w["a"][1], w["b"][1])]
    mat = m.get("materiais") or {}
    a_util = sum(d["area_m2"] for d in med_div)
    acabamentos = [
        {"elemento": "Fachada exterior", "material": MAT.acabamento("fachada", mat.get("fachada"))["nome"], "area_m2": fachada["area_liquida_m2"]},
        {"elemento": "Cobertura", "material": MAT.acabamento("cobertura", mat.get("cobertura"))["nome"], "area_m2": cobertura["area_m2"]},
        {"elemento": "Pavimentos", "material": MAT.acabamento("pavimento", mat.get("pavimento"))["nome"], "area_m2": R(a_util, 2)},
        {"elemento": "Paredes interiores (faces das divisões)", "material": MAT.acabamento("parede_interior", mat.get("parede_interior"))["nome"],
         "area_m2": R(sum(d["area_paredes_m2"] for d in med_div), 2)},
        {"elemento": "Tetos", "material": MAT.acabamento("teto", mat.get("teto"))["nome"], "area_m2": R(a_util, 2)},
        {"elemento": "Caixilharia (vãos exteriores)", "material": MAT.acabamento("caixilharia", mat.get("caixilharia"))["nome"],
         "area_m2": fachada["area_vaos_m2"]},
    ]
    medicoes = {
        "convencao": ("Medições geométricas do modelo: comprimentos líquidos sem contar encontros duas vezes, áreas "
                      "líquidas com os vãos descontados, volumes por camada. Não incluem fixações, argamassas, perdas "
                      "nem preços: não substituem o mapa de quantidades."),
        "paredes": med_paredes, "por_tipo": list(por_tipo.values()),
        "vaos": sorted(cont_vaos.values(), key=lambda c: (c["tipo"], c["largura_m"], c["altura_m"])),
        "divisoes": med_div, "acabamentos": acabamentos, "lajes": med_lajes, "terracos": terracos, "fachada": fachada,
        "cobertura": {"tipo": cob["tipo"], "inclinacao_graus": cob["inclinacao_graus"] if cob["tipo"] != "plana" else 0.0,
                      "area_m2": cobertura["area_m2"], "area_planta_m2": cobertura["area_planta_m2"],
                      "perimetro_beirado_m": cobertura["perimetro_beirado_m"], "empenas_m2": R(a_empenas, 2),
                      "altura_cumeeira_m": R(cobertura["z_cumeeira"], 2)},
        "totais": {"area_bruta_construcao_m2": R(sum(p["area_bruta_m2"] for p in pisos_out), 2),
                   "area_util_m2": R(sum(d["area_m2"] for d in med_div), 2),
                   "n_paredes": len(med_paredes), "n_vaos": sum(c["quantidade"] for c in cont_vaos.values())},
    }
    return {"ok": not erros, "pisos": pisos_out, "paredes": paredes_out, "divisoes": divisoes_out, "lajes": lajes_out,
            "cobertura": cobertura, "cores": MAT.cores(mat), "medicoes": medicoes, "erros": erros, "avisos": avisos,
            "limites": [R(min(xs)), R(min(ys)), R(max(xs)), R(max(ys))] if xs else None}
