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
from engines.estudio_projeto import objetos as OBJ
from engines.estudio_projeto.modelo import ACABAMENTOS_DIVISAO, espessura

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


def _uma_agua(pg: Polygon, cob: Dict[str, Any], z_topo: float) -> Dict[str, Any]:
    """Cobertura de uma água: um plano que sobe a partir do lado baixo (frente, tardoz, esquerda ou direita).
    O plano passa no topo das paredes no ponto mais baixo do contorno; as paredes sobem até ele (empenas)."""
    from engines.estudio_projeto.cobertura import triangulos
    tan, beiral = math.tan(math.radians(cob["inclinacao_graus"])), cob["beiral_m"]
    cos = math.cos(math.radians(cob["inclinacao_graus"]))
    dx, dy = {"frente": (0.0, 1.0), "tardoz": (0.0, -1.0), "esquerda": (1.0, 0.0), "direita": (-1.0, 0.0)}[cob["lado_baixo"]]
    beirado = orient(pg.buffer(beiral, join_style=2, mitre_limit=10.0), 1.0) if beiral > 0 else pg
    if beirado.geom_type != "Polygon":
        return {"motivo": "O beiral funde partes do contorno: reduza o beiral ou escolha cobertura plana."}
    d0 = min(x * dx + y * dy for x, y in pg.exterior.coords)

    def z_de(x, y):
        return z_topo + tan * (x * dx + y * dy - d0)
    E = list(beirado.exterior.coords)[:-1]
    face = {"pts": [[R(x), R(y), R(z_de(x, y))] for x, y in E],
            "tris": [[[R(x), R(y), R(z_de(x, y))] for x, y in list(t.exterior.coords)[:3]] for t in triangulos(beirado)],
            "area_planta_m2": R(beirado.area, 2), "area_m2": R(beirado.area / cos, 2)}
    empenas = []
    P = list(pg.exterior.coords)[:-1]
    for k in range(len(P)):
        p, q = P[k], P[(k + 1) % len(P)]
        zp, zq = z_de(*p), z_de(*q)
        if max(zp, zq) - z_topo <= 0.01:
            continue
        pts3 = [[R(p[0]), R(p[1]), R(z_topo)], [R(q[0]), R(q[1]), R(z_topo)]]
        pts3 += [[R(x), R(y), R(z)] for (x, y), z in ((q, zq), (p, zp)) if z - z_topo > 1e-6]
        L = math.hypot(q[0] - p[0], q[1] - p[1])
        empenas.append({"pts": pts3, "area_m2": R(L * ((zp - z_topo) + (zq - z_topo)) / 2, 2)})
    return {"faces": [face], "empenas": empenas, "z_cumeeira": R(max(p3[2] for p3 in face["pts"])), "z_beirado": R(min(p3[2] for p3 in face["pts"])),
            "beirado": [[R(x), R(y)] for x, y in E], "perimetro_beirado_m": R(beirado.length, 2)}


def _aguas(pegada: Polygon, cob: Dict[str, Any], z_topo: float) -> Dict[str, Any]:
    """Águas de uma cobertura inclinada sobre um contorno convexo. z(p) = z_beirado + tan·min(distância às linhas dos
    lados que escoam). Devolve {"faces", "empenas", "z_cumeeira", "z_beirado"} ou {"motivo"} se a forma não permite."""
    tipo, tan, beiral = cob["tipo"], math.tan(math.radians(cob["inclinacao_graus"])), cob["beiral_m"]
    pg = orient(pegada.simplify(0.002), 1.0)
    if tipo == "uma_agua":                 # um só plano inclinado: vale para qualquer contorno
        return _uma_agua(pg, cob, z_topo)
    if pg.convex_hull.area - pg.area > 1e-4:          # reentrâncias: exato em contornos ortogonais (L, T, U…)
        from engines.estudio_projeto.cobertura import aguas_ortogonais
        return aguas_ortogonais(pegada, cob, z_topo)
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


def _faces_divisao(anel: List[List[float]], vaos_piso: List[dict], geo: Dict[str, dict]) -> List[Dict[str, Any]]:
    """Faces de parede viradas para a divisão (um troço por lado do contorno), com os vãos que se abrem em cada uma.
    Servem para vestir cada face, no 3D, com o acabamento de paredes da divisão."""
    faces = []
    for q in range(len(anel)):
        a, b = anel[q], anel[(q + 1) % len(anel)]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 0.02:
            continue
        ex, ey = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        furos = []
        for v in vaos_piso:
            if not v["valido"]:
                continue
            g = geo[v["parede"]]
            if abs(ex * g["u"][1] - ey * g["u"][0]) > 1e-3:
                continue
            dx, dy = v["centro"][0] - a[0], v["centro"][1] - a[1]
            if abs(-dx * ey + dy * ex) > g["t"] / 2 + 0.03:
                continue
            s = dx * ex + dy * ey
            s0, s1 = max(0.0, s - v["largura_m"] / 2), min(L, s + v["largura_m"] / 2)
            if s1 - s0 > 0.02:
                furos.append({"id": v["id"], "u0": R(s0), "u1": R(s1), "z0": v["peitoril_m"], "z1": R(v["peitoril_m"] + v["altura_m"])})
        faces.append({"a": a, "b": b, "vaos": furos})
    return faces


def _por_material(divisoes, elemento: str, chave: str, campo: str, mat_casa: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Área de um acabamento interior somada por material, divisão a divisão (cada divisão conta uma vez)."""
    tot: Dict[str, float] = {}
    for d in divisoes:
        nome = d["acabamentos"][chave]["nome"]
        tot[nome] = tot.get(nome, 0.0) + d[campo]
    if not tot:
        tot[MAT.acabamento(chave, mat_casa.get(chave))["nome"]] = 0.0
    return [{"elemento": elemento, "material": n, "area_m2": R(a, 2)} for n, a in tot.items()]


# ---------------------------------------------------------------- derivação completa
def derivar(m: Dict[str, Any]) -> Dict[str, Any]:
    erros: List[Dict[str, Any]] = []
    avisos: List[Dict[str, Any]] = []
    tipos = m["tipos_parede"]
    mat_casa = m.get("materiais") or {}
    cz = cotas(m)
    por_piso_vaos: Dict[str, List[dict]] = {}
    for v in m["vaos"]:
        por_piso_vaos.setdefault(v["parede"], []).append(v)

    pisos_out, paredes_out, divisoes_out, lajes_out = [], [], [], []
    pegadas: List[Any] = []
    unioes: List[Any] = []
    med_paredes, med_div = [], []
    fachada = {"perimetro_m": 0.0, "area_bruta_m2": 0.0, "area_vaos_m2": 0.0}
    cont_vaos: Dict[tuple, Dict[str, Any]] = {}
    mapa_v: Dict[tuple, Dict[str, Any]] = {}
    n_pisos = len(m["pisos"])
    fach_casa = MAT.acabamento("fachada", mat_casa.get("fachada"))
    fach_por: Dict[str, float] = {}          # área líquida de fachada por material (parede a parede)
    caix_por: Dict[str, float] = {}          # área de vãos exteriores por caixilharia

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
        unioes.append(uniao)
        # parte de cada parede na planta (sem contar encontros duas vezes)
        ordem = sorted(vivos, key=lambda w: (not tipos[w["tipo"]]["exterior"], -geo[w["id"]]["t"], w["id"]))
        # no 3D cada encontro pertence a uma só parede: a dona do encontro avança até à face exterior, as outras
        # param na face dela — sem volumes sobrepostos, cada parede mostra só o seu acabamento
        posto = {w["id"]: i for i, w in enumerate(ordem)}
        for w in vivos:
            g = geo[w["id"]]
            for ponta, chave in ((w["a"], "e3a"), (w["b"], "e3b")):
                pt = Point(ponta)
                juntas = [o for o in vivos if o["id"] != w["id"] and geo[o["id"]]["eixo"].distance(pt) < JUNTA]
                donas = [geo[o["id"]]["t"] / 2 for o in juntas if posto[o["id"]] < posto[w["id"]]]
                g[chave] = -max(donas) if donas else (max(geo[o["id"]]["t"] / 2 for o in juntas) if juntas else 0.0)
        tomado = None
        parte_area: Dict[str, float] = {}
        for w in ordem:
            c = corpos[w["id"]]
            parte_area[w["id"]] = (c if tomado is None else c.difference(tomado)).area
            tomado = c if tomado is None else unary_union([tomado, c])
        # comprimento de fachada (face exterior real) que cabe a cada parede exterior, sem repetir os cunhais
        fach_len: Dict[str, float] = {}
        e_cima = m["pisos"][k + 1]["laje_m"] if k + 1 < n_pisos else m["cobertura"]["laje_m"]
        if pegada is not None and not pegada.is_empty:
            resto = unary_union([p.exterior for p in _polys(pegada)])
            for w in ordem:
                if tipos[w["tipo"]]["exterior"] and not resto.is_empty:
                    cb = corpos[w["id"]].buffer(1e-4)
                    fach_len[w["id"]] = resto.intersection(cb).length
                    resto = resto.difference(cb)
            if not resto.is_empty and resto.length > 0.01:      # contorno feito por paredes de tipo interior
                fach_por[fach_casa["nome"]] = fach_por.get(fach_casa["nome"], 0.0) + resto.length * (altura + e_cima)
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
            fw = MAT.acabamento("fachada", w.get("fachada") or mat_casa.get("fachada"))
            if tipo["exterior"]:
                fachada["area_vaos_m2"] += a_vaos
                fach_por[fw["nome"]] = fach_por.get(fw["nome"], 0.0) + fach_len.get(w["id"], 0.0) * (altura + e_cima) - a_vaos
                for v in validos:
                    cxn = "Portão de garagem (material por definir)" if v["tipo"] == "portao" else \
                        MAT.acabamento("caixilharia", v.get("caixilharia") or mat_casa.get("caixilharia"))["nome"]
                    caix_por[cxn] = caix_por.get(cxn, 0.0) + v["largura_m"] * v["altura_m"]
            for v in vs:
                cx, cy = w["a"][0] + g["u"][0] * v["pos_m"], w["a"][1] + g["u"][1] * v["pos_m"]
                vaos_piso.append({**v, "piso": piso["id"], "centro": [R(cx), R(cy)], "z0": R(z0 + v["peitoril_m"]),
                                  "z1": R(z0 + v["peitoril_m"] + v["altura_m"]), "exterior": tipo["exterior"]})
                if v["valido"]:
                    mv = OBJ.modelo_vao(v["tipo"], v.get("modelo"))
                    cx_nome = "—" if v["tipo"] == "portao" or (v["tipo"] == "porta" and not tipo["exterior"]) else \
                        MAT.acabamento("caixilharia", v.get("caixilharia") or mat_casa.get("caixilharia"))["nome"]
                    kv = (v["tipo"], mv["id"], v["largura_m"], v["altura_m"], v["peitoril_m"], cx_nome, v.get("protecao") or "", tipo["exterior"])
                    linha = mapa_v.setdefault(kv, {"tipo": v["tipo"], "modelo": mv["nome"], "folhas": mv["folhas"], "largura_m": v["largura_m"],
                                                   "altura_m": v["altura_m"], "peitoril_m": v["peitoril_m"], "caixilharia": cx_nome,
                                                   "protecao": OBJ.PROTECOES.get(v.get("protecao") or "", "Sem proteção"),
                                                   "exterior": tipo["exterior"], "quantidade": 0, "area_m2": 0.0, "ids": []})
                    linha["quantidade"] += 1
                    linha["area_m2"] = R(linha["area_m2"] + v["largura_m"] * v["altura_m"], 2)
                    linha["ids"].append(v["id"])
                    key = (v["tipo"], v["largura_m"], v["altura_m"])
                    c = cont_vaos.setdefault(key, {"tipo": v["tipo"], "largura_m": v["largura_m"], "altura_m": v["altura_m"],
                                                   "quantidade": 0, "area_m2": 0.0, "ids": []})
                    c["quantidade"] += 1
                    c["area_m2"] = R(c["area_m2"] + v["largura_m"] * v["altura_m"], 2)
                    c["ids"].append(v["id"])
            paredes_out.append({"id": w["id"], "piso": piso["id"], "a": w["a"], "b": w["b"], "tipo": w["tipo"],
                                "esp_m": R(g["t"]), "comprimento_m": R(g["L"]), "ext_a": R(g["ea"]), "ext_b": R(g["eb"]),
                                "ext3d_a": R(g["e3a"]), "ext3d_b": R(g["e3b"]),
                                "z0": z0, "altura_m": altura, "exterior": tipo["exterior"],
                                "cor": fw["cor"] if tipo["exterior"] else MAT.acabamento("parede_interior", mat_casa.get("parede_interior"))["cor"],
                                "fachada": {"id": fw["id"], "nome": fw["nome"]} if tipo["exterior"] else None,
                                "fachada_m": R(fach_len.get(w["id"], 0.0), 3),
                                "corpo": _anel(corpos[w["id"]]),
                                "vaos": [{"id": v["id"], "tipo": v["tipo"], "u0": v["u0"], "u1": v["u1"], "z0": v["peitoril_m"],
                                          "z1": R(v["peitoril_m"] + v["altura_m"]), "valido": v["valido"],
                                          "lado": v["lado"], "dobradica": v["dobradica"],
                                          "folhas": OBJ.modelo_vao(v["tipo"], v.get("modelo"))["folhas"],
                                          "cor": MAT.acabamento("caixilharia", v.get("caixilharia") or mat_casa.get("caixilharia"))["cor"]}
                                         for v in vs]})
        for i, pl in enumerate(divs, 1):
            rt = next((r for r in rot if pl.contains(Point(r["x"], r["y"]))), None)
            nome = rt["nome"] if rt else f"Divisão {i}"
            # acabamentos da divisão: os próprios (no rótulo) ou, na falta, os escolhidos para a casa
            acab = {k: MAT.acabamento(k, (rt or {}).get(k) or mat_casa.get(k)) for k in ACABAMENTOS_DIVISAO}
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
                 "area_paredes_m2": R(max(0.0, pl.length * altura - a_vaos_div), 2), "rodape_m": R(max(0.0, pl.length - portas), 2),
                 "faces": _faces_divisao(_anel(pl), vaos_piso, geo), "z0": z0, "z1": z1,
                 "acabamentos": {k: {"id": v["id"], "nome": v["nome"], "cor": v["cor"]} for k, v in acab.items()},
                 "proprios": [k for k in ACABAMENTOS_DIVISAO if (rt or {}).get(k)]}
            divisoes_out.append(d)
            med_div.append({**{kk: d[kk] for kk in ("id", "piso", "nome", "area_m2", "perimetro_m", "area_paredes_m2", "rodape_m")},
                            **{k: v["nome"] for k, v in acab.items()}})
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

    # escadas: degraus pela altura real entre pisos; o vazio de cada uma é aberto na laje do piso de chegada
    from engines.estudio_projeto.escadas import LIVRE_SOBRE_ESCADA, derivar_escadas
    escadas_out, vazios, e_esc, a_esc = derivar_escadas(m, cz, pegadas, unioes)
    erros += e_esc
    avisos += a_esc

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
        if g is not None and vazios.get(k):
            g = g.difference(unary_union(vazios[k]))
        ps = _polys(g)
        if not ps:
            continue
        area = sum(p.area for p in ps)
        lajes_out.append({"nome": nome, "z0": R(zt - e), "z1": R(zt), "polys": [_anel(p) for p in ps],
                          "furos": [[[[R(x), R(y)] for x, y in list(a.coords)[:-1]] for a in p.interiors] for p in ps]})
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
    if a_empenas > 0:                                  # as empenas seguem o acabamento de fachada da casa
        fach_por[fach_casa["nome"]] = fach_por.get(fach_casa["nome"], 0.0) + a_empenas
    if not fach_por:
        fach_por[fach_casa["nome"]] = 0.0
    if not caix_por:
        caix_por[MAT.acabamento("caixilharia", mat_casa.get("caixilharia"))["nome"]] = 0.0
    fachada = {"perimetro_m": R(fachada["perimetro_m"], 2), "area_bruta_m2": R(fachada["area_bruta_m2"], 2),
               "area_vaos_m2": R(fachada["area_vaos_m2"], 2),
               "area_liquida_m2": R(fachada["area_bruta_m2"] - fachada["area_vaos_m2"], 2)}

    # mapa de vãos: um código por conjunto idêntico (tipo, modelo, medidas, caixilharia, proteção)
    prefixo = {"janela": "J", "porta": "P", "portada": "PV", "portao": "PG"}
    conta_pref: Dict[str, int] = {}
    mapa_vaos = []
    for kv in sorted(mapa_v, key=lambda t: (list(prefixo).index(t[0]), not t[7], t[2], t[3], t[1], t[4], t[5], t[6])):
        linha = mapa_v[kv]
        conta_pref[kv[0]] = conta_pref.get(kv[0], 0) + 1
        mapa_vaos.append({"codigo": f"{prefixo[kv[0]]}{conta_pref[kv[0]]}", **linha})
    cod_vao = {i: l["codigo"] for l in mapa_vaos for i in l["ids"]}
    for w in paredes_out:
        for v in w["vaos"]:
            v["codigo"] = cod_vao.get(v["id"])

    # objetos (mobiliário, sanitários, equipamentos): ocupação em planta e em altura
    objetos_out, conta_obj = [], {}
    z_piso = {p["id"]: p["z0"] for p in pisos_out}
    for o in m.get("objetos") or []:
        base = OBJ.OBJETOS[o["tipo"]]
        r_ = math.radians(o["rot"])
        co, si = math.cos(r_), math.sin(r_)
        hw, hp = o["largura_m"] / 2, o["prof_m"] / 2
        if base["forma"] == "circ":
            local = [(hw * math.cos(2 * math.pi * i / 24), hp * math.sin(2 * math.pi * i / 24)) for i in range(24)]
        else:
            local = [(-hw, -hp), (hw, -hp), (hw, hp), (-hw, hp)]
        z0o = z_piso[o["piso"]] + base["base_m"]
        objetos_out.append({"id": o["id"], "piso": o["piso"], "tipo": o["tipo"], "nome": base["nome"], "categoria": base["categoria"],
                            "forma": base["forma"], "cor": base["cor"], "ifc": base["ifc"], "x": o["x"], "y": o["y"], "rot": o["rot"],
                            "largura_m": o["largura_m"], "prof_m": o["prof_m"],
                            "pts": [[R(o["x"] + lx * co - ly * si), R(o["y"] + lx * si + ly * co)] for lx, ly in local],
                            "frente": [R(o["x"] + hp * si), R(o["y"] - hp * co)],        # meio da face da frente (lado −y local)
                            "z0": R(z0o), "z1": R(z0o + base["altura_m"])})
        c_ = conta_obj.setdefault(o["tipo"], {"tipo": o["tipo"], "nome": base["nome"], "categoria": base["categoria"], "quantidade": 0})
        c_["quantidade"] += 1

    quadro_areas = [{"piso": p["nome"], "area_bruta_m2": p["area_bruta_m2"],
                     "area_util_m2": R(sum(dv["area_m2"] for dv in divisoes_out if dv["piso"] == p["id"]), 2),
                     "n_divisoes": sum(1 for dv in divisoes_out if dv["piso"] == p["id"])} for p in pisos_out]
    for q in quadro_areas:
        q["paredes_e_vazios_m2"] = R(q["area_bruta_m2"] - q["area_util_m2"], 2)

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
    acabamentos = [
        *[{"elemento": "Fachada exterior", "material": nm, "area_m2": R(a, 2)} for nm, a in fach_por.items()],
        {"elemento": "Cobertura", "material": MAT.acabamento("cobertura", mat.get("cobertura"))["nome"], "area_m2": cobertura["area_m2"]},
        *_por_material(divisoes_out, "Pavimentos", "pavimento", "area_m2", mat),
        *_por_material(divisoes_out, "Paredes interiores (faces das divisões)", "parede_interior", "area_paredes_m2", mat),
        *_por_material(divisoes_out, "Tetos", "teto", "area_m2", mat),
        *[{"elemento": "Caixilharia (vãos exteriores)", "material": nm, "area_m2": R(a, 2)} for nm, a in caix_por.items()],
    ]
    medicoes = {
        "convencao": ("Medições geométricas do modelo: comprimentos líquidos sem contar encontros duas vezes, áreas "
                      "líquidas com os vãos descontados, volumes por camada. Não incluem fixações, argamassas, perdas "
                      "nem preços: não substituem o mapa de quantidades."),
        "paredes": med_paredes, "por_tipo": list(por_tipo.values()),
        "vaos": sorted(cont_vaos.values(), key=lambda c: (c["tipo"], c["largura_m"], c["altura_m"])),
        "divisoes": med_div, "acabamentos": acabamentos, "lajes": med_lajes,
        "mapa_vaos": mapa_vaos, "quadro_areas": quadro_areas,
        "area_implantacao_m2": pisos_out[0]["area_bruta_m2"] if pisos_out else 0.0,
        "objetos": sorted(conta_obj.values(), key=lambda c: (OBJ.CATEGORIAS_OBJ.index(c["categoria"]), c["nome"])),
        "escadas": [{kk: e[kk] for kk in ("id", "piso", "tipo", "n_espelhos", "n_cobertores", "espelho_m", "cobertor_m", "largura_m",
                                          "blondel_m", "altura_m", "desenvolvimento_m", "area_planta_m2", "vazio_m2")} for e in escadas_out],
        "regra_vazio_escada": f"Vazio aberto na laje onde o pé-direito livre sobre a escada seria inferior a {LIVRE_SOBRE_ESCADA:.2f} m.", "terracos": terracos, "fachada": fachada,
        "cobertura": {"tipo": cob["tipo"], "inclinacao_graus": cob["inclinacao_graus"] if cob["tipo"] != "plana" else 0.0,
                      "area_m2": cobertura["area_m2"], "area_planta_m2": cobertura["area_planta_m2"],
                      "perimetro_beirado_m": cobertura["perimetro_beirado_m"], "empenas_m2": R(a_empenas, 2),
                      "altura_cumeeira_m": R(cobertura["z_cumeeira"], 2)},
        "totais": {"area_bruta_construcao_m2": R(sum(p["area_bruta_m2"] for p in pisos_out), 2),
                   "area_util_m2": R(sum(d["area_m2"] for d in med_div), 2),
                   "n_paredes": len(med_paredes), "n_vaos": sum(c["quantidade"] for c in cont_vaos.values())},
    }
    return {"ok": not erros, "pisos": pisos_out, "paredes": paredes_out, "divisoes": divisoes_out, "lajes": lajes_out, "escadas": escadas_out,
            "objetos": objetos_out, "cobertura": cobertura, "cores": MAT.cores(mat), "medicoes": medicoes, "erros": erros, "avisos": avisos,
            "limites": [R(min(xs)), R(min(ys)), R(max(xs)), R(max(ys))] if xs else None}
