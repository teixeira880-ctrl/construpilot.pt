"""Lajes, vigas e aço base das lajes e dos muros lidos num dossier de estrutura em PDF vetorial (plantas de laje 1:50 rodadas,
como o dossier DUEL / STRUPLANO) — método validado em Coimbra :

- zona da planta = eixos V/H escritos ; laje = polígonos cheios do cinzento da laje ;
- laje aligeirada (LFA) = quadrícula de blocos (linhas pretas finas, células 0,75 × 0,75) + vigas com altura ≥ espessura LFA,
  fechada a 1,5 m ; o resto da laje = laje maciça (LM) ; espessuras lidas nos rótulos «h=0,31 LFA» / «h=0,20 LM» ;
- blocos = células da quadrícula (cada célula dividida pelo comprimento do bloco lido na nota, «0,75 x 0,25 x 0,25 m») ;
- vigas = rótulo b×h (sem parênteses) + par de arestas afastadas b ao longo do texto ; só conta a retombé (h − espessura da laje) ;
- aço base : nota «Armadura base … Ø10 af.0,20» (laje maciça, 4 camadas), «Armadura base entre nervuras : Superior 3Ø10 Inferior
  3Ø10» com «0,90 m entre eixos de nervuras» (LFA), malha da lâmina (Malhasol CQ38, em m²) ; reforços desenhados lidos nos rótulos «Ø10af.0,2L=4,2» ; emendas por sobreposição (nota, varões comerciais de 12 m) ;
- muros : corte tipo do muro (arranques, verticais, horizontais, corridos, armadura da sapata linear) aplicado ao comprimento medido.
Massa nominal dos varões : EN 10080."""
from __future__ import annotations

import math
import re
from collections import Counter

from shapely.geometry import LineString, Polygon, box
from shapely.ops import polygonize, unary_union

from .fundacoes import KG_M, _f

ROT_VIGA = re.compile(r"^(\d,\d+)x(\d,\d+)$")
BARRA_COMERCIAL = 12.0   # m — comprimento comercial dos varões A500 (Portugal) : uma emenda por sobreposição a cada 12 m de varão corrido


def amarracoes(doc) -> tuple:
    """(amarração, sobreposição) em diâmetros, lidos na nota «AMARRAÇÕES E EMENDAS» («50Ø … amarração», «80Ø … sobreposição»)."""
    for page in doc:
        t = " ".join(page.get_text().split())
        a = re.search(r"(\d+)\s*Ø do varão,? para o comprimento de amarra", t)
        b = re.search(r"(\d+)\s*Ø do varão,? para o comprimento de sobreposi", t)
        if a or b:
            return (int(a.group(1)) if a else None, int(b.group(1)) if b else None)
    return (None, None)


def emendas(L: float) -> int:
    """Número de emendas de um varão corrido de comprimento L com varões comerciais de 12 m."""
    return max(0, math.ceil(round(L / BARRA_COMERCIAL, 6)) - 1)


def _escala(page) -> float | None:
    t = " ".join(page.get_text().split())
    m = re.search(r"PLANTA\s+Escala\s+1\s*[:/]\s*(\d+)", t, re.I) or re.search(r"Escala\s+1\s*[:/]\s*(\d+)", t, re.I)
    return 0.0254 / 72 * int(m.group(1)) if m else None


def _zona(page):
    ax = [w for w in page.get_text("words") if re.fullmatch(r"[VH]\d{1,2}", w[4])]
    if len(ax) < 4:
        return None
    xs = [(w[0] + w[2]) / 2 for w in ax]
    ys = [(w[1] + w[3]) / 2 for w in ax]
    return box(min(xs), min(ys), max(xs), max(ys))


def _polys(d):
    out, cur = [], []
    for it in d["items"]:
        if it[0] == "re":
            r = it[1]
            out.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)])
        elif it[0] == "l":
            if not cur or abs(cur[-1][0] - it[1].x) > 0.01 or abs(cur[-1][1] - it[1].y) > 0.01:
                if len(cur) >= 3:
                    out.append(cur)
                cur = [(it[1].x, it[1].y)]
            cur.append((it[2].x, it[2].y))
    if len(cur) >= 3:
        out.append(cur)
    return out


def vigas(page, k, Z, tol=0.35) -> list:
    hs, vs = [], []
    for d in page.get_drawings():
        for it in d["items"]:
            pts = []
            if it[0] == "l":
                pts = [((it[1].x, it[1].y), (it[2].x, it[2].y))]
            elif it[0] == "re":
                r = it[1]
                pts = [((r.x0, r.y0), (r.x1, r.y0)), ((r.x1, r.y0), (r.x1, r.y1)), ((r.x1, r.y1), (r.x0, r.y1)), ((r.x0, r.y1), (r.x0, r.y0))]
            for (x0, y0), (x1, y1) in pts:
                if not (Z[0] <= min(x0, x1) and max(x0, x1) <= Z[2] and Z[1] <= min(y0, y1) and max(y0, y1) <= Z[3]):
                    continue
                if abs(y0 - y1) < 0.3 and abs(x1 - x0) * k >= 0.4:
                    hs.append((y0, min(x0, x1), max(x0, x1)))
                elif abs(x0 - x1) < 0.3 and abs(y1 - y0) * k >= 0.4:
                    vs.append((x0, min(y0, y1), max(y0, y1)))
    curtos = []                                            # segmentos curtos (≤ 1,5 m) : contornos de negativos na laje
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                ls = LineString([(it[1].x, it[1].y), (it[2].x, it[2].y)])
            elif it[0] == "re":
                r = it[1]
                ls = LineString([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)])
            else:
                continue
            if ls.length * k <= (3.5 if it[0] == "re" else 1.5) and Z[0] <= ls.bounds[0] and ls.bounds[2] <= Z[2] and Z[1] <= ls.bounds[1] and ls.bounds[3] <= Z[3]:
                curtos.append(ls)
    caixas = []                                            # contornos SEM enchimento com a forma do rótulo (furo) ; secções de pilar são cheias
    cheios = {(round(d["rect"].x0), round(d["rect"].y0), round(d["rect"].x1), round(d["rect"].y1)) for d in page.get_drawings() if d.get("fill")}
    for d in page.get_drawings():
        r = d["rect"]
        if (round(r.x0), round(r.y0), round(r.x1), round(r.y1)) in cheios:
            continue                                       # contorno de uma secção cheia (pilar / parede), não furo
        if d.get("fill") is None and 0.1 <= r.width * k <= 1.6 and 0.1 <= r.height * k <= 1.6 and Z[0] <= r.x0 and r.x1 <= Z[2] and Z[1] <= r.y0 and r.y1 <= Z[3]:
            caixas.append(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2, sorted((r.width * k, r.height * k))))
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    arv = STRtree(curtos) if curtos else None

    def negativo(cx, cy, b, h) -> bool:
        """Rótulo b×h com um retângulo fechado b×h a menos de 1,5 m = negativo (furo) na laje, não viga."""
        alvo = sorted((b, h))
        for x, y, dims in caixas:
            if ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * k <= 1.5 and abs(dims[0] - alvo[0]) <= 0.03 and abs(dims[1] - alvo[1]) <= 0.03:
                return True
        if arv is None:
            return False
        c = Point(cx, cy)
        loc = [curtos[int(i)] for i in arv.query(c.buffer(1.5 / k))]
        faces = list(polygonize(unary_union(loc))) if loc else []
        juntas = unary_union(faces) if faces else None              # furo desenhado com diagonal : faces juntas = o retângulo
        cands = faces + (list(getattr(juntas, "geoms", [juntas])) if juntas is not None and not juntas.is_empty else [])
        for f in cands:
            x0, y0, x1, y1 = f.bounds
            a_, b_ = sorted(((x1 - x0) * k, (y1 - y0) * k))
            if abs(a_ - min(b, h)) <= 0.03 and abs(b_ - max(b, h)) <= 0.03 and f.area >= 0.9 * (x1 - x0) * (y1 - y0):
                return True
        return False
    out = []
    for w in page.get_text("words"):
        m = ROT_VIGA.match(w[4])
        if not m or not (Z[0] <= w[0] and w[2] <= Z[2] and Z[1] <= w[1] and w[3] <= Z[3]):
            continue
        b, h = _f(m.group(1)), _f(m.group(2))
        if b == h:                                         # quadrado sem parênteses = negativo na laje
            continue
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if negativo(cx, cy, b, h):
            continue
        horiz = (w[2] - w[0]) > (w[3] - w[1])
        segs, cp, ca = (hs, cy, cx) if horiz else (vs, cx, cy)
        near = [s for s in segs if abs(s[0] - cp) * k <= 1.0 and s[1] - 2 <= ca <= s[2] + 2]
        best = None
        for t_ in (tol, 0.90):
            for i_, s1 in enumerate(near):
                for s2 in near[i_ + 1:]:
                    if abs(abs(s1[0] - s2[0]) * k - b) <= 0.03:
                        lo, hi = max(s1[1], s2[1]), min(s1[2], s2[2])
                        L = (hi - lo) * k
                        e0, e1 = min(s1[0], s2[0]), max(s1[0], s2[0])
                        if (e0 - t_ / k) <= cp <= (e1 + t_ / k) and L >= 0.4 and lo - 2 <= ca <= hi + 2 and (best is None or L > best[0]):
                            best = (L, e0, lo, hi)
            if best:
                break
        poly = None
        if best:
            L, c, lo, hi = best
            poly = box(lo, c, hi, c + b / k) if horiz else box(c, lo, c + b / k, hi)
        out.append({"sec": w[4], "b": b, "h": h, "L": round(best[0], 2) if best else None, "poly": poly})
    return out


def ler_laje(page) -> dict:
    k = _escala(page)
    Zp = _zona(page)
    if not k or Zp is None:
        return {}
    t = " ".join(page.get_text().split())
    e_lfa = max((_f(x) for x in re.findall(r"h=(0,\d+)\s*LFA", t)), default=None)
    e_lm = max((_f(x) for x in re.findall(r"h=(0,\d+)\s*LM", t)), default=None)
    if not e_lm and not e_lfa:
        return {}
    bl = re.search(r"blocos de betão leve\s+(\d+[.,]\d+)\s*x\s*(\d+[.,]\d+)\s*x\s*(\d+[.,]\d+)", t, re.I)
    blk = (_f(bl.group(1)), _f(bl.group(2)), _f(bl.group(3))) if bl else None
    tos = re.search(r"COTA DO TOSCO\s+(\d+[.,]\d+)", t, re.I)
    # cor da laje = cinzento claro com maior área dentro da zona
    areas = Counter()
    for d in page.get_drawings():
        f = d.get("fill")
        if f and len(f) >= 3 and all(0.88 <= c <= 0.985 for c in f[:3]) and Zp.intersects(box(*d["rect"])):
            areas[tuple(round(c, 2) for c in f[:3])] += d["rect"].width * d["rect"].height
    if not areas:
        return {}
    cor = areas.most_common(1)[0][0]
    fills, segs = [], []
    for d in page.get_drawings():
        f = d.get("fill")
        if f and tuple(round(c, 2) for c in f[:3]) == cor:
            for pts in _polys(d):
                try:
                    q = Polygon(pts).buffer(0)
                except Exception:  # noqa: BLE001
                    continue
                if q.area > 0 and Zp.intersects(q):
                    fills.append(q.intersection(Zp))
        if tuple(round(c, 2) for c in (d.get("color") or (1, 1, 1))) == (0.0, 0.0, 0.0) and round(d.get("width") or 0, 2) == 0.3:
            for it in d["items"]:
                if it[0] == "l":
                    ls = LineString([(it[1].x, it[1].y), (it[2].x, it[2].y)])
                    if Zp.contains(ls):
                        segs.append(ls)
    if not fills:
        return {}
    laje = unary_union(fills).buffer(0.02 / k).buffer(-0.02 / k)
    lado = blk[0] if blk else 0.75
    cells = [c for c in polygonize(unary_union(segs)) if abs(max(c.bounds[2] - c.bounds[0], c.bounds[3] - c.bounds[1]) * k - lado) < 0.02] if segs else []
    Z = (Zp.bounds[0] - 20, Zp.bounds[1] - 20, Zp.bounds[2] + 20, Zp.bounds[3] + 20)
    vg = vigas(page, k, Z)
    if cells and e_lfa:
        grelha = unary_union([c.buffer(0.15 / k, join_style=2) for c in cells])
        base = unary_union([grelha] + [v["poly"] for v in vg if v["poly"] is not None and v["h"] >= e_lfa - 1e-6])
        lfa = base.buffer(1.5 / k, join_style=2).buffer(-1.5 / k, join_style=2).intersection(laje)
    else:
        lfa = Polygon()
    lm = laje.difference(lfa)
    A_cells = sum(c.area for c in cells if not lfa.is_empty and lfa.contains(c.centroid)) * k * k
    blocos = sum(math.ceil(round(min(c.bounds[2] - c.bounds[0], c.bounds[3] - c.bounds[1]) * k / (blk[1] if blk else 0.25), 3) - 1e-9)
                 for c in cells if not lfa.is_empty and lfa.contains(c.centroid))
    for v in vg:
        if v["poly"] is not None:
            dentro = (not lfa.is_empty) and lfa.intersection(v["poly"]).area > 0.5 * v["poly"].area
            v["e"] = e_lfa if dentro else e_lm
            v["ret"] = round(max(0.0, v["h"] - (v["e"] or 0)), 3)
    comp_lm = [g for g in getattr(lm, "geoms", [lm]) if not g.is_empty and g.area * k * k > 0.5]
    dims_lm = [((g.bounds[2] - g.bounds[0]) * k, (g.bounds[3] - g.bounds[1]) * k, g.area * k * k) for g in comp_lm]
    return {"dims_lm": dims_lm, "tosco": _f(tos.group(1)) if tos else None, "A_total": laje.area * k * k, "A_LFA": lfa.area * k * k, "A_LM": lm.area * k * k,
            "A_celulas": A_cells, "blocos": blocos, "bloco": blk, "e_lfa": e_lfa, "e_lm": e_lm, "per": laje.boundary.length * k,
            "vigas": [{x: v.get(x) for x in ("sec", "b", "h", "L", "e", "ret")} for v in vg]}


def notas_aco(doc) -> dict:
    """Armaduras base das lajes e malhas lidas nas notas das folhas."""
    t = " ".join(" ".join(p.get_text().split()) for p in doc)
    out = {}
    m = re.search(r"Armadura base:\s*-\s*Armadura longitudinal superior:\s*Ø(\d+)\s*af\.?\s*(\d+[.,]\d+)", t)
    if m:
        out["lm"] = {"d": int(m.group(1)), "s": _f(m.group(2)), "camadas": len(re.findall(r"Armadura (?:longitudinal|transversal) (?:superior|inferior):\s*Ø\d+\s*af", t[m.start():m.start() + 400]))}
    m = re.search(r"Armadura base entre nervuras:\s*Superior:\s*(\d+)Ø(\d+)\s*Inferior:\s*(\d+)Ø(\d+)", t)
    e = re.search(r"(\d+[.,]\d+)\s*m entre eixos de nervuras", t)
    if m and e:
        out["lfa"] = {"sup": (int(m.group(1)), int(m.group(2))), "inf": (int(m.group(3)), int(m.group(4))), "eixo": _f(e.group(1))}
    m = re.search(r"Malhasol\s+(C[QR]\s*\d+)", t)
    if m:
        out["malha_lfa"] = m.group(1).replace(" ", "")
    return out


def cortes_muros(doc) -> dict:
    """Cortes tipo «MURO TIPO M1» / «MUROS TIPO M4, M5 e M7» : cada corte ocupa a célula da folha que começa no título.
    Devolve {"M4": {"barras": [...], "corridos": [...], "pagina": i}, …}."""
    out = {}
    for ip, p in enumerate(doc):
        tit = []
        for b in p.get_text("blocks"):
            t = " ".join(b[4].split())
            m = re.fullmatch(r"MUROS? TIPO\s+(.+)", t)
            if m:
                nomes = re.findall(r"M\d+", m.group(1))
                vert = (b[3] - b[1]) > (b[2] - b[0])
                tit.append((nomes, b, vert))
        if not tit:
            continue
        ws = p.get_text("words")
        vert = sum(1 for *_, v in tit if v) > len(tit) / 2
        # eixo «ao longo do título» e eixo das colunas (folha rodada : x = colunas, y = linhas)
        cols = sorted({round((b[0] + b[2]) / 2 / 50) * 50 for _, b, _ in tit}) if vert else sorted({round(b[1] / 50) * 50 for _, b, _ in tit})
        rows = sorted({round(b[1] / 50) * 50 for _, b, _ in tit}) if vert else sorted({round(b[0] / 50) * 50 for _, b, _ in tit})
        for nomes, b, _ in tit:
            c = round((b[0] + b[2]) / 2 / 50) * 50 if vert else round(b[1] / 50) * 50
            r = round(b[1] / 50) * 50 if vert else round(b[0] / 50) * 50
            ic, ir = cols.index(c), rows.index(r)
            c0 = cols[ic - 1] + 20 if ic > 0 else -1e9
            r1 = rows[ir + 1] - 5 if ir + 1 < len(rows) else 1e9
            if vert:
                cel = [w for w in ws if c0 < (w[0] + w[2]) / 2 <= c + 20 and r - 10 <= (w[1] + w[3]) / 2 < r1]
                cel.sort(key=lambda w: (round(w[0] / 6), w[1]))
            else:                                              # folha direita : título por cima, corte por baixo e à direita
                c1 = cols[ic + 1] - 5 if ic + 1 < len(cols) else 1e9
                cel = [w for w in ws if c - 10 <= (w[1] + w[3]) / 2 < c1 and r - 10 <= (w[0] + w[2]) / 2 < r1]
                cel.sort(key=lambda w: (round(w[1] / 6), w[0]))
            txt = " ".join(w[4] for w in cel)
            barras = [{"n": int(m.group(1)) if m.group(1) else None, "d": int(m.group(2)), "s": _f(m.group(3)),
                       "L": _f(m.group(4)) if m.group(4) else None, "txt": m.group(0)}
                      for m in re.finditer(r"(\d+)?Ø(\d+)\s*af\.?\s*(\d+[.,]\d+)(?:\s*\(L=(\d+[.,]?\d*)\))?", txt)]
            corridos = [{"n": int(m.group(1)), "d": int(m.group(2)), "txt": m.group(0)} for m in re.finditer(r"(\d+)Ø(\d+)\s*corridos", txt)]
            for n in nomes:
                out[n] = {"barras": barras, "corridos": corridos, "pagina": ip, "titulo": " ".join(b[4].split())}
        if out:
            return out
    return out


def _moldura(page, w):
    """Menor retângulo desenhado que contém o centro da palavra w (a moldura do pormenor)."""
    import pymupdf
    pt = pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
    rs = [d["rect"] for d in page.get_drawings() if d["rect"].contains(pt) and d["rect"].width > 40 and d["rect"].height > 40]
    return min(rs, key=lambda r: r.width * r.height) if rs else None


def ler_lva(page) -> dict:
    """Laje de vigotas pré-esforçadas (LVA) : área em planta (cinzento da laje), inclinação medida no pormenor do apoio
    (arestas inclinadas da laje), entre-eixo das vigotas e betão complementar medidos na secção tipo desenhada."""
    k = _escala(page)
    Zp = _zona(page)
    t = " ".join(page.get_text().split())
    m = re.search(r"h=(0,\d+)\s*LVA", t)
    if not k or Zp is None or not m:
        return {}
    e = _f(m.group(1))
    tipo = re.search(r"Secção tipo da laje\s+(\S+)", t)
    W = page.get_text("words")
    tit = next((w for w in W if w[4] == "Secção" and "Secção tipo da laje" in " ".join(x[4] for x in W if abs(x[1] - w[1]) < 3 and abs(x[3] - w[3]) < 3
                                                                                   and x[0] >= w[0] - 1 and x[0] < w[0] + 400)), None)
    if tit is None:  # texto rodado : procurar pelo bloco
        tit = next((b[:4] + ("Secção",) for b in page.get_text("blocks") if "Secção tipo da laje" in b[4]), None)
    fr = _moldura(page, tit) if tit else None
    if fr is None:
        return {}
    k25 = None
    mm = re.search(r"Escala\s+1\s*[:/]\s*(\d+)", " ".join(page.get_text(clip=fr).split()))
    if mm:
        k25 = 0.0254 / 72 * int(mm.group(1))
    dims = [_f(w[4]) for w in W if fr.contains(__import__("pymupdf").Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)) and re.fullmatch(r"0,\d{3}", w[4])]
    eixo = max(dims) if dims else None
    # betão complementar : área cinzenta da secção / largura desenhada
    ps = []
    cor = Counter()
    for d in page.get_drawings():
        f = d.get("fill")
        if f and len(f) >= 3 and fr.contains(d["rect"]) and all(0.8 <= c <= 0.95 for c in f[:3]):
            cor[tuple(round(c, 2) for c in f[:3])] += d["rect"].width * d["rect"].height
    if cor and k25:
        c0 = cor.most_common(1)[0][0]
        for d in page.get_drawings():
            f = d.get("fill")
            if f and fr.contains(d["rect"]) and tuple(round(c, 2) for c in f[:3]) == c0:
                for pts in _polys(d):
                    try:
                        q = Polygon(pts).buffer(0)
                    except Exception:  # noqa: BLE001
                        continue
                    if q.area > 0:
                        ps.append(q)
    sec = unary_union(ps) if ps else None
    consumo = None
    if sec is not None and not sec.is_empty:
        bx = sec.bounds
        larg = max(bx[2] - bx[0], bx[3] - bx[1]) * k25
        consumo = sec.area * k25 * k25 / larg if larg > 0.3 else None
    # inclinação : arestas inclinadas longas no pormenor que mostra «abobadilhas» fora da secção tipo
    inc = None
    for w in W:
        if w[4].lower().startswith("abobadilhas"):
            f2 = _moldura(page, w)
            if f2 is None or f2 == fr:
                continue
            ang = Counter()
            for d in page.get_drawings():
                if not f2.contains(d["rect"]):
                    continue
                for it in d["items"]:
                    if it[0] == "l":
                        a, b = it[1], it[2]
                        L = math.hypot(b.x - a.x, b.y - a.y)
                        if L > 80:
                            g = math.degrees(math.atan2(abs(b.y - a.y), abs(b.x - a.x)))
                            g = min(g, 90 - g)
                            if 3 < g < 45:
                                ang[round(g, 1)] += L
            if ang:
                inc = ang.most_common(1)[0][0]
                break
    # área em planta : cinzento da laje dentro da zona dos eixos
    areas = Counter()
    for d in page.get_drawings():
        f = d.get("fill")
        if f and len(f) >= 3 and all(0.88 <= c <= 0.985 for c in f[:3]) and Zp.intersects(box(*d["rect"])):
            areas[tuple(round(c, 2) for c in f[:3])] += d["rect"].width * d["rect"].height
    if not areas:
        return {}
    cor_l = areas.most_common(1)[0][0]
    fills = []
    for d in page.get_drawings():
        f = d.get("fill")
        if f and tuple(round(c, 2) for c in f[:3]) == cor_l:
            for pts in _polys(d):
                try:
                    q = Polygon(pts).buffer(0)
                except Exception:  # noqa: BLE001
                    continue
                if q.area > 0 and Zp.intersects(q):
                    fills.append(q.intersection(Zp))
    if not fills:
        return {}
    A = unary_union(fills).area * k * k
    tos = re.search(r"COTA DO TOSCO\s+(\d+[.,]\d+)", t, re.I)
    return {"A_planta": A, "inclinacao": inc, "A_real": A / math.cos(math.radians(inc)) if inc else A, "e": e,
            "tipo": tipo.group(1) if tipo else "LVA", "eixo": eixo, "consumo": consumo, "tosco": _f(tos.group(1)) if tos else None,
            "malha": "CQ38" if re.search(r"CQ\s*38", t) else None}


def linhas_mapa(pdf: bytes, origem: str = "", muros: dict | None = None) -> list:
    """Capítulo Estrutura : lajes (betão, cofragem, blocos, aço base), vigas (retombé) e aço dos muros (corte tipo)."""
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    out = []
    notas = notas_aco(doc)
    amar, sob = amarracoes(doc)
    vistos = set()
    for ip, page in enumerate(doc):
        try:
            r = ler_laje(page)
        except Exception:  # noqa: BLE001
            r = {}
        if not r or not r.get("A_total") or r["A_total"] < 10:
            try:
                v = ler_lva(page)
            except Exception:  # noqa: BLE001
                v = {}
            if v and v["A_planta"] > 10 and ("lva", round(v["A_planta"], 1)) not in vistos:
                vistos.add(("lva", round(v["A_planta"], 1)))
                out += _linhas_lva(v, f"folha {ip + 1}" + (f" de {origem}" if origem else ""))
            continue
        chave = (round(r["A_total"], 1), r.get("tosco"))
        if chave in vistos:
            continue
        vistos.add(chave)
        piso = f"Laje cota {r['tosco']:.2f}".replace(".", ",") if r.get("tosco") else f"Laje folha {ip + 1}"
        org = f"folha {ip + 1}" + (f" de {origem}" if origem else "")
        if r["A_LM"] > 0.5 and r["e_lm"]:
            out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Laje maciça (LM) h = {r['e_lm']:.2f} — betão",
                            descricao=f"{r['A_LM']:.2f} m² × {r['e_lm']:.2f} ; {org}", qtd=r["A_LM"] * r["e_lm"], un="m³", refs="LM"))
        if r["A_LFA"] > 0.5 and r["e_lfa"]:
            vb = r["A_celulas"] * (r["bloco"][2] if r["bloco"] else 0)
            out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Laje aligeirada (LFA) h = {r['e_lfa']:.2f} — betão",
                            descricao=f"{r['A_LFA']:.2f} m² × {r['e_lfa']:.2f} − blocos {r['A_celulas']:.2f} m² × {(r['bloco'] or (0, 0, 0))[2]:.2f}",
                            qtd=r["A_LFA"] * r["e_lfa"] - vb, un="m³", refs="LFA"))
            out.append(dict(capitulo="Estrutura", piso=piso, designacao="Blocos de aligeiramento " + ("× ".join(f"{x:.2f}" for x in r["bloco"]) if r["bloco"] else ""),
                            descricao="células da quadrícula de blocos contadas uma a uma", qtd=r["blocos"], un="un", refs="LFA"))
        out.append(dict(capitulo="Estrutura", piso=piso, designacao="Cofragem de laje (fundo)", descricao=f"área da laje {r['A_total']:.2f} m²",
                        qtd=r["A_total"], un="m²", refs=""))
        vr = [v for v in r["vigas"] if v.get("L") and v.get("ret")]
        if vr:
            out.append(dict(capitulo="Estrutura", piso=piso, designacao="Vigas — betão da retombé (abaixo da laje)",
                            descricao=f"{len(vr)} vigas : " + ", ".join(f"{v['sec']} {v['L']:.2f} m" for v in vr[:12]),
                            qtd=sum(v["b"] * v["ret"] * v["L"] for v in vr), un="m³", refs="vigas"))
            out.append(dict(capitulo="Estrutura", piso=piso, designacao="Vigas — cofragem (fundo + lados da retombé)",
                            descricao="Σ L × (b + 2 × retombé)", qtd=sum(v["L"] * (v["b"] + 2 * v["ret"]) for v in vr), un="m²", refs="vigas"))
        # aço base das lajes
        lm, lf = notas.get("lm"), notas.get("lfa")
        if lm and r["A_LM"] > 0.5:
            m_m2 = lm["camadas"] / lm["s"]
            out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Aço base da laje maciça Ø{lm['d']} af.{lm['s']:.2f} ({lm['camadas']} camadas)",
                            descricao=f"{r['A_LM']:.2f} m² × {lm['camadas']} × (1 / {lm['s']:.2f}) m/m² × {KG_M[lm['d']]:.3f} kg/m ; reforços desenhados por medir",
                            qtd=r["A_LM"] * m_m2 * KG_M[lm["d"]], un="kg", refs="nota «Armadura base»", estado="medido (sem reforços)"))
            if sob and r.get("dims_lm"):
                n_em, partes = 0.0, []
                for bx, by, a in r["dims_lm"]:
                    for L_, larg in ((bx, a / bx if bx else 0), (by, a / by if by else 0)):
                        e_ = emendas(L_)
                        if e_:
                            nb = larg / lm["s"] * lm["camadas"] / 2
                            n_em += nb * e_
                            partes.append(f"{nb:.0f} varões × {e_} (vão {L_:.2f} m)")
                if n_em:
                    lv = sob * lm["d"] / 1000
                    out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Aço base da laje maciça — emendas {sob}Ø (varões de {BARRA_COMERCIAL:.0f} m)",
                                    descricao=f"{' + '.join(partes)} = {n_em:.0f} emendas × {lv:.2f} m × {KG_M[lm['d']]:.3f} kg/m ; nota «Amarrações e emendas»",
                                    qtd=n_em * lv * KG_M[lm["d"]], un="kg", refs="emendas"))
        if lf and r["A_LFA"] > 0.5:
            (ns, ds), (ni, di) = lf["sup"], lf["inf"]
            kg = r["A_LFA"] / lf["eixo"] * (ns * KG_M[ds] + ni * KG_M[di])
            out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Aço base das nervuras {ns}Ø{ds} sup. + {ni}Ø{di} inf. (nervuras a {lf['eixo']:.2f} m)",
                            descricao=f"{r['A_LFA']:.2f} m² / {lf['eixo']:.2f} m × ({ns} × {KG_M[ds]:.3f} + {ni} × {KG_M[di]:.3f}) kg/m ; reforços por medir",
                            qtd=kg, un="kg", refs="nota «Armadura base entre nervuras»", estado="medido (sem reforços)"))
            if notas.get("malha_lfa"):
                out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Malha da lâmina de compressão {notas['malha_lfa']}",
                                descricao=f"área da laje aligeirada {r['A_LFA']:.2f} m²", qtd=r["A_LFA"], un="m²", refs="LFA"))
    # aço dos muros : corte tipo de cada muro × comprimento desse muro medido na planta de fundação
    cm = cortes_muros(doc)
    if cm and muros:
        H = muros.get("H")
        for nome, L in sorted((muros.get("por_nome") or {}).items(), key=lambda t: int(t[0][1:])):
            c = cm.get(nome)
            if not c or not H or not L:
                out.append(dict(capitulo="Fundações", piso="Cave", designacao=f"Muro {nome} — aço", descricao="sem corte tipo legível para este muro",
                                qtd=None, un="kg", refs=nome, estado="a medir"))
                continue
            for b in c["barras"]:
                if b["n"]:
                    q, d_ = b["n"] * L, f"{b['n']} × {L:.2f} m"
                elif b["L"]:
                    q, d_ = (L / b["s"] + 1) * b["L"], f"({L:.2f}/{b['s']:.2f} + 1) × {b['L']:.2f} m"
                else:
                    q, d_ = (H / b["s"] + 1) * L, f"({H:.2f}/{b['s']:.2f} + 1) × {L:.2f} m"
                nem = 0
                if sob and not b["n"] and not b["L"] and emendas(L):          # horizontais corridas ao longo do muro
                    nem = (H / b["s"] + 1) * emendas(L)
                elif sob and b["n"] and emendas(L):
                    nem = b["n"] * emendas(L)
                ext = nem * sob * b["d"] / 1000 if nem else 0.0
                out.append(dict(capitulo="Fundações", piso="Cave", designacao=f"Muro {nome} — aço {b['txt']}",
                                descricao=(f"{d_}" + (f" + {nem:.0f} emendas × {sob}Ø ({sob * b['d'] / 1000:.2f} m)" if nem else "")
                                           + f" × {KG_M.get(b['d'], 0):.3f} kg/m ; {c['titulo']}"),
                                qtd=(q + ext) * KG_M.get(b["d"], 0), un="kg", refs=nome,
                                estado="medido" + (" (com emendas)" if nem else "")))
            for k_ in c["corridos"]:
                nem = k_["n"] * emendas(L) if sob else 0
                ext = nem * sob * k_["d"] / 1000 if nem else 0.0
                out.append(dict(capitulo="Fundações", piso="Cave", designacao=f"Muro {nome} — aço {k_['txt']}",
                                descricao=(f"{k_['n']} × {L:.2f} m" + (f" + {nem} emendas × {sob}Ø ({sob * k_['d'] / 1000:.2f} m)" if nem else "")
                                           + f" × {KG_M.get(k_['d'], 0):.3f} kg/m ; {c['titulo']}"),
                                qtd=(k_["n"] * L + ext) * KG_M.get(k_["d"], 0), un="kg", refs=nome,
                                estado="medido" + (" (com emendas)" if nem else "")))
    return out


def _linhas_lva(v: dict, org: str) -> list:
    piso = f"Laje cota {v['tosco']:.2f}".replace(".", ",") if v.get("tosco") else "Laje de cobertura (LVA)"
    A, Ap, inc = v["A_real"], v["A_planta"], v.get("inclinacao")
    ar = (f"{Ap:.2f} m² em planta / cos {inc:.1f}° = {A:.2f} m²" if inc else f"{Ap:.2f} m² em planta (inclinação não lida)")
    out = []
    if v.get("consumo"):
        out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Laje de vigotas {v['tipo']} h = {v['e']:.2f} — betão complementar",
                        descricao=f"{ar} × {v['consumo']:.3f} m³/m² (área de betão da secção tipo desenhada / largura) ; {org}",
                        qtd=A * v["consumo"], un="m³", refs="LVA"))
    else:
        out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Laje de vigotas {v['tipo']} h = {v['e']:.2f} — betão complementar",
                        descricao="secção tipo não legível", qtd=None, un="m³", refs="LVA", estado="a medir"))
    out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Laje de vigotas {v['tipo']} h = {v['e']:.2f} — área (vigotas + abobadilhas)",
                    descricao=f"{ar} ; {org}", qtd=A, un="m²", refs="LVA"))
    if v.get("eixo"):
        out.append(dict(capitulo="Estrutura", piso=piso, designacao="Vigotas pré-esforçadas — comprimento",
                        descricao=f"{A:.2f} m² / {v['eixo']:.3f} m entre eixos (secção tipo)", qtd=A / v["eixo"], un="m", refs="LVA"))
    if v.get("malha"):
        out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Malha da lâmina de compressão {v['malha']}",
                        descricao=f"área da laje {A:.2f} m²", qtd=A, un="m²", refs="LVA"))
    return out


ROT_CONT = re.compile(r"^(\d+)Ø(\d+)(?:af\.?0?,\d+)?\s*L\s*=\s*(\d+(?:,\d+)?)$")
ROT_AF = re.compile(r"^Ø(\d+)af\.?(0?,\d+)\s*L\s*=\s*(\d+(?:,\d+)?)(?:-\d+(?:,\d+)?)?$")


def _rotulos(page):
    """Rótulos de armadura da folha, juntando «2Ø16» + «L=2,4» quando vêm em palavras separadas."""
    W = page.get_text("words")
    out = []
    for i, w in enumerate(W):
        t = w[4]
        if "Ø" in t and "L=" not in t and i + 1 < len(W) and W[i + 1][4].startswith("L=") and W[i + 1][5:7] == w[5:7]:
            t = t + W[i + 1][4]
        if "L=" in t and "Ø" in t:
            out.append(t.replace(" ", ""))
    return out


def reforcos(pdf: bytes, origem: str = "", excluir: set | None = None) -> list:
    """Armaduras desenhadas com rótulo (vigas, reforços das lajes, escadas, cobertura) : cada rótulo «nØd L=x» desenhado é contado
    n × x ; os rótulos «Ød af.s L=x» sem número de varões (dependem da faixa de distribuição desenhada) ficam listados a medir.
    Piso = cota do tosco da própria folha ou da última planta de laje anterior."""
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    amar, sob = amarracoes(doc)
    out, piso = [], None
    for ip, page in enumerate(doc):
        t = " ".join(page.get_text().split())
        tos = re.search(r"COTA DO TOSCO\s+(\d+[.,]\d+)", t, re.I)
        if tos:
            piso = f"Laje cota {_f(tos.group(1)):.2f}".replace(".", ",")
        if excluir and ip in excluir:
            continue
        rot = _rotulos(page)
        if not rot:
            continue
        cob = re.search(r"Laje do Teto\s+(\S+(?:\s+\(\w+\))?)", t)
        p_ = "Laje de cobertura (LVA)" if (cob and re.search(r"cobertura", cob.group(0), re.I)) else (piso or f"Folha {ip + 1}")
        org = f"folha {ip + 1}" + (f" de {origem}" if origem else "")
        por_d, n_rot, sem_n = {}, {}, []
        n_emendas = {}
        for r in rot:
            m = ROT_CONT.match(r)
            if m:
                n, d, L = int(m.group(1)), int(m.group(2)), _f(m.group(3))
                if d not in KG_M or not L:
                    continue
                por_d[d] = por_d.get(d, 0.0) + n * L
                n_rot[d] = n_rot.get(d, 0) + 1
                if sob and emendas(L):
                    n_emendas[d] = n_emendas.get(d, 0) + n * emendas(L)
                continue
            m = ROT_AF.match(r)
            if m:
                sem_n.append(r)
        for d in sorted(por_d):
            out.append(dict(capitulo="Estrutura", piso=p_, designacao=f"Armaduras desenhadas Ø{d} (vigas / reforços)",
                            descricao=f"{n_rot[d]} rótulos «nØ{d} L=…» : Σ n × L = {por_d[d]:.2f} m × {KG_M[d]:.3f} kg/m ; {org}",
                            qtd=por_d[d] * KG_M[d], un="kg", refs="rótulos"))
            if n_emendas.get(d):
                lv = sob * d / 1000
                out.append(dict(capitulo="Estrutura", piso=p_, designacao=f"Armaduras desenhadas Ø{d} — emendas {sob}Ø (varões > {BARRA_COMERCIAL:.0f} m)",
                                descricao=f"{n_emendas[d]} emendas × {lv:.2f} m × {KG_M[d]:.3f} kg/m", qtd=n_emendas[d] * lv * KG_M[d], un="kg",
                                refs="emendas"))
        if sem_n:
            out.append(dict(capitulo="Estrutura", piso=p_, designacao="Reforços «Ø af. L=» sem número de varões",
                            descricao=f"{len(sem_n)} rótulos ({', '.join(sorted(set(sem_n))[:6])}{'…' if len(set(sem_n)) > 6 else ''}) : n.º de varões = "
                                      f"faixa de distribuição desenhada / afastamento ; {org}",
                            qtd=None, un="kg", refs="rótulos", estado="a medir"))
    return out
