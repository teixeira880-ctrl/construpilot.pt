"""Projeto LSF a partir da planta lida pelo ConstruPilot (coleção `plans_takeoff`) ou da entrada do motor MEP.

Mesma leitura geométrica que os planos de execução (`engines.mep.adapter.from_takeoff` → `engines.mep.model.build`):
divisões calibradas (faces interiores reais), aberturas associadas às paredes, pisos empilhados. Daí:

- implantação de cada piso = união das divisões com os vazios entre elas fechados (paredes interiores) → face interior das
  paredes exteriores; a estrutura LSF é posta para fora (gesso + estrutura), o ETICS por fora da estrutura;
- paredes interiores = eixos entre arestas paralelas de divisões vizinhas (vazio ≤ `vazio_max`), fundidas quando colineares
  e prolongadas até à parede de apoio (o motor corta-as depois à face do revestimento e cria o montante de ligação);
- vãos: exteriores → lado do perímetro mais próximo (x medido a partir do canto); interiores → parede interior mais próxima;
- pisos: zonas retangulares da implantação do piso superior; vão das vigas na menor dimensão, partido sobre paredes
  interiores do piso de baixo quando excede o vão máximo; zonas do piso inferior não cobertas → cobertura plana;
- cobertura do último piso: duas águas (asnas Fink) se a implantação for retangular, senão cobertura plana.

Tudo o que a planta não dá (alturas dos vãos, inclinação, beiral, perfis) é uma HIPÓTESE nomeada em `hipoteses`.
Coordenadas: plano em metros com y para baixo → projeto em mm com y para cima.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from . import defaults

ALTURAS = {  # kind → (altura m, peitoril m, tipo LSF)
    "fenetre": (1.20, 0.90, "janela"), "baie": (2.10, 0.0, "porta"), "porte_fenetre": (2.10, 0.0, "porta"),
    "porte": (2.10, 0.0, "porta"), "porte_garage": (2.00, 0.0, "porta"), "passage": (2.10, 0.0, "porta"),
}
NOME_VAO = {"fenetre": "janela", "baie": "vão envidraçado", "porte_fenetre": "porta-janela", "porte": "porta",
            "porte_garage": "portão de garagem", "passage": "passagem"}


class AdapterError(ValueError):
    pass


def _mm(v: float) -> float:
    return round(v * 1000.0, 1)


def _clean_ring(coords, tol=0.02):
    """Remove pontos repetidos e colineares (tolerância em m)."""
    pts = [tuple(p) for p in coords[:-1]] if coords and tuple(coords[0]) == tuple(coords[-1]) else [tuple(p) for p in coords]
    out = []
    for p in pts:
        if not out or math.dist(out[-1], p) > tol:
            out.append(p)
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if area2 / max(math.dist(a, c), 1e-9) < tol:
                out.pop(i)
                changed = True
                break
    return out


def _footprint(rooms, vazio_max):
    polys = [Polygon(r.polygon).buffer(0) for r in rooms if len(r.polygon) >= 3]
    if not polys:
        raise AdapterError("Piso sem divisões utilizáveis.")
    d = vazio_max / 2
    u = unary_union([p.buffer(d, join_style=2) for p in polys]).buffer(-d, join_style=2)
    notas = []
    if u.geom_type == "MultiPolygon":
        parts = sorted(u.geoms, key=lambda g: -g.area)
        notas.append(f"implantação em {len(parts)} partes separadas: só a maior ({parts[0].area:.1f} m²) é modelada")
        u = parts[0]
    vazios = []
    if u.interiors:
        for ring in u.interiors:
            hole = Polygon(ring)
            if hole.area < 0.3:
                continue
            vazios.append(hole)
        if vazios:
            notas.append(f"{len(vazios)} espaço(s) sem divisão desenhada (escada, átrio…; {sum(h.area for h in vazios):.1f} m²) tratado(s) como "
                         "divisão: paredes à volta com 10 cm nominais")
        u = Polygon(u.exterior)
    return orient(u.simplify(0.01), 1.0), notas, vazios


def _sem_degraus(poly: Polygon, dmin: float):
    """Remove degraus de fachada < dmin (imprecisões de desenho) alinhando pelo lado exterior: as divisões ficam dentro."""
    pts = _clean_ring(list(orient(poly, 1.0).exterior.coords))
    removidos = 0
    changed = True
    vistos = 0
    while changed and len(pts) > 4 and vistos < 60:
        vistos += 1
        changed = False
        n = len(pts)
        for i in range(n):
            a, b, c, d = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
            L = math.dist(b, c)
            if L >= dmin:
                continue
            u1 = ((b[0] - a[0]), (b[1] - a[1]))
            u3 = ((d[0] - c[0]), (d[1] - c[1]))
            l1, l3 = math.hypot(*u1), math.hypot(*u3)
            if l1 < 1e-6 or l3 < 1e-6 or (u1[0] * u3[0] + u1[1] * u3[1]) / (l1 * l3) < 0.999:
                continue
            # o lado exterior: a união com o retângulo do degrau
            cand = Polygon(pts).union(Polygon([a, b, c, (a[0] + c[0] - b[0], a[1] + c[1] - b[1])]).buffer(0))
            cand2 = Polygon(pts).union(Polygon([b, c, d, (b[0] + d[0] - c[0], b[1] + d[1] - c[1])]).buffer(0))
            area0 = Polygon(pts).area
            ok = [g for g in (cand, cand2) if g.geom_type == "Polygon" and not g.interiors and area0 + 1e-4 < g.area < area0 + dmin * 50]
            best = min(ok, key=lambda g: g.area, default=None)
            if best is None:
                continue
            pts = _clean_ring(list(orient(best, 1.0).exterior.coords))
            removidos += 1
            changed = True
            break
    return Polygon(pts), removidos


def _interior_walls(rooms, vazio_max, sobrepor_min=0.15):
    """Eixos de paredes interiores entre arestas paralelas de divisões vizinhas."""
    segs = []
    edges = []
    for r in rooms:
        pts = list(orient(Polygon(r.polygon).buffer(0), 1.0).exterior.coords)[:-1] if len(r.polygon) >= 3 else []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            if math.dist(a, b) > 0.05:
                edges.append((r.id, a, b))
    for i in range(len(edges)):
        ri, a1, b1 = edges[i]
        L1 = math.dist(a1, b1)
        d1 = ((b1[0] - a1[0]) / L1, (b1[1] - a1[1]) / L1)
        for j in range(i + 1, len(edges)):
            rj, a2, b2 = edges[j]
            if ri == rj:
                continue
            L2 = math.dist(a2, b2)
            d2 = ((b2[0] - a2[0]) / L2, (b2[1] - a2[1]) / L2)
            if d1[0] * d2[0] + d1[1] * d2[1] > -0.999:     # arestas de divisões vizinhas: sentidos opostos (CCW)
                continue
            n1 = (-d1[1], d1[0])
            gap = (a2[0] - a1[0]) * n1[0] + (a2[1] - a1[1]) * n1[1]
            if not (-vazio_max <= gap <= -0.005):            # a outra divisão fica do lado exterior (à direita) desta aresta
                continue
            t2a = (a2[0] - a1[0]) * d1[0] + (a2[1] - a1[1]) * d1[1]
            t2b = (b2[0] - a1[0]) * d1[0] + (b2[1] - a1[1]) * d1[1]
            s0, s1 = max(0.0, min(t2a, t2b)), min(L1, max(t2a, t2b))
            if s1 - s0 < sobrepor_min:
                continue
            off = gap / 2
            p0 = (a1[0] + d1[0] * s0 + n1[0] * off, a1[1] + d1[1] * s0 + n1[1] * off)
            p1 = (a1[0] + d1[0] * s1 + n1[0] * off, a1[1] + d1[1] * s1 + n1[1] * off)
            segs.append({"a": p0, "b": p1, "vazio": -gap})
    # fusão de segmentos colineares
    merged = []
    for s in segs:
        a, b = s["a"], s["b"]
        L = math.dist(a, b)
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        if d[0] < -1e-9 or (abs(d[0]) < 1e-9 and d[1] < 0):
            a, b, d = b, a, (-d[0], -d[1])
        n = (-d[1], d[0])
        c = a[0] * n[0] + a[1] * n[1]
        t0, t1 = a[0] * d[0] + a[1] * d[1], b[0] * d[0] + b[1] * d[1]
        for m in merged:
            if m["d"][0] * d[0] + m["d"][1] * d[1] > 0.999 and abs(m["c"] - c) < 0.05:
                if t0 <= m["t1"] + vazio_max + 0.05 and t1 >= m["t0"] - vazio_max - 0.05:
                    m["t0"], m["t1"] = min(m["t0"], t0), max(m["t1"], t1)
                    m["vazio"] = max(m["vazio"], s["vazio"])
                    break
        else:
            merged.append({"d": d, "n": n, "c": c, "t0": t0, "t1": t1, "vazio": s["vazio"]})
    # nova passagem de fusão (segmentos que se tornaram contíguos)
    out = []
    for m in sorted(merged, key=lambda m: (round(m["c"], 2), m["t0"])):
        if out and out[-1]["d"][0] * m["d"][0] + out[-1]["d"][1] * m["d"][1] > 0.999 and abs(out[-1]["c"] - m["c"]) < 0.05 \
                and m["t0"] <= out[-1]["t1"] + vazio_max + 0.05:
            out[-1]["t1"] = max(out[-1]["t1"], m["t1"])
            continue
        out.append(dict(m))
    return out


def _pt_of(m, t):
    return (m["d"][0] * t + m["n"][0] * m["c"], m["d"][1] * t + m["n"][1] * m["c"])


def _prolongar(walls, fp: Polygon, banda_ext: float, ext_max: float):
    """Prolonga cada parede interior até ao eixo da parede de apoio (interior) ou à banda da estrutura exterior."""
    ring = fp.exterior
    for w in walls:
        for end in ("t0", "t1"):
            sgn = -1 if end == "t0" else 1
            p = _pt_of(w, w[end])
            dirv = (w["d"][0] * sgn, w["d"][1] * sgn)
            far = (p[0] + dirv[0] * ext_max, p[1] + dirv[1] * ext_max)
            ray = LineString([p, far])
            best = None
            hit = ray.intersection(ring)
            if not hit.is_empty:
                pts = [hit] if hit.geom_type == "Point" else [g for g in getattr(hit, "geoms", []) if g.geom_type == "Point"]
                for q in pts:
                    dd = Point(p).distance(q)
                    if best is None or dd < best[0]:
                        best = (dd + banda_ext, "ext")
            for o in walls:
                if o is w or abs(o["d"][0] * w["d"][0] + o["d"][1] * w["d"][1]) > 0.1:
                    continue
                axis = LineString([_pt_of(o, o["t0"] - 0.05), _pt_of(o, o["t1"] + 0.05)])
                q = ray.intersection(axis)
                if not q.is_empty and q.geom_type == "Point":
                    dd = Point(p).distance(q)
                    if best is None or dd < best[0]:
                        best = (dd, "int")
            if best and best[0] <= ext_max + banda_ext:
                w[end] += sgn * best[0]
    return walls


def _retangulos(poly: Polygon, tol=0.01):
    """Decomposição de um polígono ortogonal em retângulos (grelha das coordenadas dos vértices, faixas fundidas)."""
    xs = sorted({round(x, 4) for x, _ in poly.exterior.coords})
    ys = sorted({round(y, 4) for _, y in poly.exterior.coords})
    cells = {}
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            c = Point((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2)
            cells[(i, j)] = poly.buffer(tol).contains(c)
    free = {k for k, v in cells.items() if v}
    rects = []
    nx, ny = len(xs) - 1, len(ys) - 1
    while free:
        best = None
        for i0 in range(nx):
            for j0 in range(ny):
                if (i0, j0) not in free:
                    continue
                for i1 in range(i0, nx):
                    if (i1, j0) not in free:
                        break
                    j1 = j0
                    while j1 + 1 < ny and all((k, j1 + 1) in free for k in range(i0, i1 + 1)):
                        j1 += 1
                    area = (xs[i1 + 1] - xs[i0]) * (ys[j1 + 1] - ys[j0])
                    if best is None or area > best[0]:
                        best = (area, i0, j0, i1, j1)
        _, i0, j0, i1, j1 = best
        for k in range(i0, i1 + 1):
            for jj in range(j0, j1 + 1):
                free.discard((k, jj))
        rects.append((xs[i0], ys[j0], xs[i1 + 1], ys[j1 + 1]))
    return rects


def _ortogonal(poly: Polygon) -> bool:
    c = list(poly.exterior.coords)
    for i in range(len(c) - 1):
        dx, dy = c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1]
        if abs(dx) > 0.01 and abs(dy) > 0.01:
            return False
    return True


def from_levels(levels, country: str = "PT", nome: str | None = None, opcoes: dict | None = None) -> dict:
    """levels = saída de engines.mep.model.build (divisões com polígonos em m, aberturas associadas)."""
    o = {"vazio_max": 0.60, "degrau_min": 0.25, "inclinacao": 30, "beiral": 500, "cobertura": "auto", "vaoMaxPiso": 5000, "viga": "C200_15",
         "espacamento_piso": 600, **(opcoes or {})}
    proj = defaults.base(country)
    proj["nome"] = nome or "Projeto LSF"
    T = proj["tiposParede"]
    perfis = proj["perfis"]
    st = perfis[T["EXT"]["montante"]]
    dt_ext = st["h"] + 2 * st["t"]
    esp_int = sum(proj["placas"][c["placa"]]["esp"] for c in T["EXT"]["interior"])
    out_off = (esp_int + dt_ext) / 1000.0            # m: face interior → face exterior da estrutura
    hip = proj["hipoteses"]
    hip.append("Geometria lida na planta: faces interiores = divisões calibradas; a estrutura LSF (gesso + perfis) é posta para fora "
               "e o ETICS por fora da estrutura — áreas úteis das divisões preservadas")
    hip.append("Alturas dos vãos não cotadas na planta: " + ", ".join(
        f"{NOME_VAO[k]} {h:g} m" + (f" (peitoril {p:g} m)" if p else "") for k, (h, p, _) in ALTURAS.items()).replace(".", ",")
               + " — substituir pelas cotas do projeto")
    leitura = {"pisos": []}
    lv_sorted = sorted(levels, key=lambda lv: lv.elevation)
    if not lv_sorted:
        raise AdapterError("Nenhum piso na planta.")
    fps, extras_lv = [], []
    for lv in lv_sorted:
        rooms = []
        for r in lv.rooms:
            r2 = type("R", (), {})()
            r2.id, r2.name = r.id, r.name
            r2.polygon = [(p[0], -p[1]) for p in r.polygon]       # y para cima
            rooms.append(r2)
        fp, notas, vazios = _footprint(rooms, o["vazio_max"])
        fp, ndeg = _sem_degraus(fp, o["degrau_min"])
        if ndeg:
            notas.append(f"{ndeg} degrau(s) de fachada < {o['degrau_min'] * 100:.0f} cm alinhado(s) pelo exterior (imprecisão de desenho)")
        for k_, h in enumerate(vazios):
            r2 = type("R", (), {})()
            r2.id, r2.name = f"vazio{k_ + 1}", "Espaço sem divisão"
            r2.polygon = list(h.buffer(-0.10, join_style=2).exterior.coords)[:-1] if not h.buffer(-0.10, join_style=2).is_empty else []
            if len(r2.polygon) >= 3:
                rooms.append(r2)
        hip.extend(f"{lv.name}: {n}" for n in notas)
        fps.append(fp)
        extras_lv.append(rooms)
    minx = min(f.bounds[0] for f in fps) - out_off
    miny = min(f.bounds[1] for f in fps) - out_off

    def mm(p):
        return [_mm(p[0] - minx), _mm(p[1] - miny)]

    viga = perfis[o["viga"]]
    pl_piso = proj["placas"]["OSB22"]
    prof_piso = viga["h"] + 2 * viga["t"] + pl_piso["esp"]
    elev = [round(lv.elevation * 1000) for lv in lv_sorted]
    for k, lv in enumerate(lv_sorted):
        fp, rooms = fps[k], extras_lv[k]
        lid = f"N{k}"
        out_poly = orient(fp.buffer(out_off, join_style=2), 1.0)
        ring = _clean_ring(list(out_poly.exterior.coords))
        if not _ortogonal(Polygon(ring)):
            hip.append(f"{lv.name}: implantação com cantos não ortogonais — pormenores de canto a desenhar")
        z0 = 0 if k == 0 else elev[k]
        if k + 1 < len(lv_sorted):
            altura = elev[k + 1] - z0 - prof_piso
        else:
            altura = round(lv.height * 1000)
        if altura < 2000:
            raise AdapterError(f"{lv.name}: altura de parede {altura} mm incoerente (cotas dos pisos?)")
        per = {"id": lid, "nivel": lv.name, "tipo": "EXT", "z0": z0, "altura": altura, "pontos": [mm(p) for p in ring], "vaos": {}}
        # paredes interiores
        walls = _interior_walls(rooms, o["vazio_max"])
        walls = _prolongar(walls, fp, out_off - dt_ext / 2000.0, o["vazio_max"] + 0.2)
        n_ext, n_int, sem = 0, 0, []
        paredes = []
        for i, w in enumerate(walls):
            a, b = _pt_of(w, w["t0"]), _pt_of(w, w["t1"])
            paredes.append({"id": f"{lid}-I{i + 1}", "nivel": lv.name, "tipo": "INT", "z0": z0, "altura": altura, "a": mm(a), "b": mm(b),
                            "alinhamento": "eixo", "vaos": [], "_w": w})
        # vãos
        ring_pts = per["pontos"]
        nv = 0
        for op in lv.openings:
            kind = op.kind if op.kind in ALTURAS else "porte"
            h, peit, tipo = ALTURAS[kind]
            a = (op.a[0], -op.a[1])
            b = (op.b[0], -op.b[1])
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            larg = math.dist(a, b)
            if larg < 0.3:
                continue
            nv += 1
            vao = {"id": f"{lid}-V{nv}", "tipo": tipo, "largura": _mm(larg), "altura": _mm(h), "origem": NOME_VAO.get(kind, kind)}
            if tipo == "janela":
                vao["peitoril"] = _mm(peit)
            if op.exterior or fp.exterior.distance(Point(mid)) < 0.08 + 0.35:
                # lado do perímetro (face exterior da estrutura) mais próximo e paralelo
                best = None
                mm_mid = mm(mid)
                ua = ((b[0] - a[0]) / larg, (b[1] - a[1]) / larg)
                for i in range(len(ring_pts)):
                    P0, P1 = ring_pts[i], ring_pts[(i + 1) % len(ring_pts)]
                    Ls = math.dist(P0, P1)
                    de = ((P1[0] - P0[0]) / Ls, (P1[1] - P0[1]) / Ls)
                    if abs(de[0] * ua[0] + de[1] * ua[1]) < 0.98:
                        continue
                    t = (mm_mid[0] - P0[0]) * de[0] + (mm_mid[1] - P0[1]) * de[1]
                    if t < 0 or t > Ls:
                        continue
                    dist = abs((mm_mid[0] - P0[0]) * -de[1] + (mm_mid[1] - P0[1]) * de[0])
                    if best is None or dist < best[0]:
                        best = (dist, i, t)
                if best and best[0] < out_off * 1000 + 600:
                    vao["x"] = round(best[2] - vao["largura"] / 2, 1)
                    per["vaos"].setdefault(str(best[1]), []).append(vao)
                    n_ext += 1
                    continue
            best = None
            for pw in paredes:
                w = pw["_w"]
                if abs(w["d"][0] * (b[0] - a[0]) / larg + w["d"][1] * (b[1] - a[1]) / larg) < 0.98:
                    continue
                t = mid[0] * w["d"][0] + mid[1] * w["d"][1]
                if t < w["t0"] - 0.05 or t > w["t1"] + 0.05:
                    continue
                dist = abs(mid[0] * w["n"][0] + mid[1] * w["n"][1] - w["c"])
                if best is None or dist < best[0]:
                    best = (dist, pw, t)
            if best and best[0] < 0.3:
                pw, t = best[1], best[2]
                vao["x"] = round((t - pw["_w"]["t0"]) * 1000 - vao["largura"] / 2, 1)
                pw["vaos"].append(vao)
                n_int += 1
            else:
                sem.append(vao["id"])
        for pw in paredes:
            pw.pop("_w")
        if sem:
            hip.append(f"{lv.name}: {len(sem)} vão(s) sem parede identificada na planta (não modelados): {', '.join(sem)}")
        proj["perimetros"].append(per)
        proj["paredes"].extend(paredes)
        leitura["pisos"].append({"nivel": lv.name, "divisoes": len(lv.rooms), "espacos_sem_divisao": len(rooms) - len(lv.rooms),
                                 "area_interior_m2": round(fp.area, 2),
                                 "paredes_exteriores": len(ring_pts), "paredes_interiores": len(paredes), "vaos_exteriores": n_ext,
                                 "vaos_interiores": n_int, "vaos_sem_parede": len(sem), "z0_mm": z0, "altura_mm": altura})
    # pisos e coberturas
    out_polys = [orient(f.buffer(out_off, join_style=2), 1.0) for f in fps]
    for k in range(1, len(lv_sorted)):
        z = elev[k] - prof_piso
        up, low = out_polys[k], out_polys[k - 1]
        if up.difference(low.buffer(0.01)).area > 0.05:
            hip.append(f"{lv_sorted[k].name}: parte do piso em consola sobre o piso inferior — apoio a verificar")
        _zonas_piso(proj, up.intersection(low.buffer(0.01)), z, f"PISO{k}", o, minx, miny, proj["paredes"], f"N{k - 1}")
        resto = low.difference(up.buffer(0.01))
        if resto.area > 1.0:
            _zonas_piso(proj, resto, z, f"COBP{k}", o, minx, miny, proj["paredes"], f"N{k - 1}", cobertura=True)
            hip.append(f"{lv_sorted[k - 1].name}: zona não coberta pelo piso superior ({resto.area:.1f} m²) tratada como cobertura plana")
    top = out_polys[-1]
    ztop = (0 if len(lv_sorted) == 1 else elev[-1]) + proj["perimetros"][-1]["altura"]
    x0, y0, x1, y1 = top.bounds
    retang = top.area / max((x1 - x0) * (y1 - y0), 1e-9) > 0.97
    tipo_cob = o["cobertura"] if o["cobertura"] != "auto" else ("duas_aguas" if retang else "plana")
    if tipo_cob == "duas_aguas":
        cum = "x" if (x1 - x0) >= (y1 - y0) else "y"
        proj["coberturas"].append({"id": "COB", "x0": _mm(x0 - minx), "y0": _mm(y0 - miny), "x1": _mm(x1 - minx), "y1": _mm(y1 - miny),
                                   "z": ztop, "cumeeira": cum, "inclinacao": o["inclinacao"], "beiral": o["beiral"], "espacamento": 600,
                                   "banzo": "C90_12", "diagonal": "C90_10", "placa": "OSB12",
                                   "subtelha": {"nome": "Subtelha / membrana", "larguraRolo": 1500, "comprimentoRolo": 50000, "sobreposicao": 100}})
        hip.append(f"Cobertura de duas águas com asnas Fink a 600 mm, inclinação {o['inclinacao']}°, beiral {o['beiral']} mm "
                   "(não cotados na planta)")
    else:
        _zonas_piso(proj, top, ztop, "COB", o, minx, miny, proj["paredes"], f"N{len(lv_sorted) - 1}", cobertura=True)
        hip.append("Cobertura plana sobre vigas LSF (implantação não retangular ou opção escolhida); pendentes e impermeabilização a definir")
    proj["leitura"] = leitura
    return proj


def _zonas_piso(proj, poly, z, grupo, o, minx, miny, paredes, nivel_inf, cobertura=False):
    geoms = [poly] if poly.geom_type == "Polygon" else [g for g in getattr(poly, "geoms", []) if g.geom_type == "Polygon"]
    vmax = o["vaoMaxPiso"]
    apoios = [p for p in paredes if p.get("id", "").startswith(nivel_inf + "-I")]
    n = 0
    for g in geoms:
        if g.area < 0.5:
            continue
        rects = _retangulos(g) if _ortogonal(g) else [g.bounds]
        for (rx0, ry0, rx1, ry1) in rects:
            X0, Y0, X1, Y1 = _mm(rx0 - minx), _mm(ry0 - miny), _mm(rx1 - minx), _mm(ry1 - miny)
            if X1 - X0 < 300 or Y1 - Y0 < 300:
                continue
            vao = "y" if (Y1 - Y0) <= (X1 - X0) else "x"
            S0, S1 = (Y0, Y1) if vao == "y" else (X0, X1)
            P0, P1 = (X0, X1) if vao == "y" else (Y0, Y1)
            cortes = []
            if S1 - S0 > vmax:
                cand = []
                for p in apoios:
                    a, b = p["a"], p["b"]
                    if vao == "y" and abs(a[1] - b[1]) < 1 and S0 + 500 < a[1] < S1 - 500:
                        cov = min(max(a[0], b[0]), P1) - max(min(a[0], b[0]), P0)
                        if cov > 0.6 * (P1 - P0):
                            cand.append(a[1])
                    if vao == "x" and abs(a[0] - b[0]) < 1 and S0 + 500 < a[0] < S1 - 500:
                        cov = min(max(a[1], b[1]), P1) - max(min(a[1], b[1]), P0)
                        if cov > 0.6 * (P1 - P0):
                            cand.append(a[0])
                cur = S0
                for c in sorted(set(round(x, 1) for x in cand)):
                    if c - cur <= vmax and (S1 - c > vmax or True):
                        if c - cur > 500:
                            cortes.append(c)
                            cur = c
                if S1 - cur > vmax:
                    nn = math.ceil((S1 - cur) / vmax)
                    for kk in range(1, nn):
                        cortes.append(round(cur + (S1 - cur) * kk / nn, 1))
                    proj["hipoteses"].append(f"{grupo}: vão {round((S1 - cur) / 1000, 2)} m sem parede de apoio — linha(s) de apoio intermédia(s) "
                                             "a prever (viga ou parede resistente)")
            limites = [S0] + sorted(cortes) + [S1]
            for i in range(len(limites) - 1):
                n += 1
                s0, s1 = limites[i], limites[i + 1]
                zona = {"id": f"{grupo}-{n}", "grupo": grupo, "z": z, "vao": vao, "viga": o["viga"], "espacamento": o["espacamento_piso"],
                        "placa": "OSB22" if not cobertura else "OSB18", "travamentoMax": 2500, "vaoMax": vmax, "cobertura": cobertura}
                if vao == "y":
                    zona.update(x0=P0, x1=P1, y0=s0, y1=s1)
                else:
                    zona.update(x0=s0, x1=s1, y0=P0, y1=P1)
                proj["pisos"].append(zona)


def from_mep_input(data: dict, nome: str | None = None, opcoes: dict | None = None) -> dict:
    """Entrada no formato do motor MEP (levels/rooms/openings em m)."""
    from engines.mep.model import build
    levels, _ = build(data)
    if not any(lv.rooms for lv in levels):
        raise AdapterError("Nenhuma divisão utilizável (são necessárias divisões fechadas e calibradas).")
    return from_levels(levels, (data.get("country") or "pt").upper(), nome or (data.get("project") or {}).get("name"), opcoes)


def from_takeoff(plan: dict, levels: list[dict] | None = None, country: str = "pt", opcoes: dict | None = None) -> dict:
    """Planta já lida no ConstruPilot (`plans_takeoff`)."""
    from engines.mep.adapter import AdapterError as MepErr
    from engines.mep.adapter import from_takeoff as mep_ft
    try:
        data = mep_ft(plan, levels, country, {})
    except MepErr as exc:
        raise AdapterError(str(exc)) from exc
    return from_mep_input(data, plan.get("filename"), opcoes)
