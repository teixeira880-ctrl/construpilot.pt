"""Peças desenhadas a partir do modelo único: planta cotada por piso, quatro alçados e cortes.

Cada desenho é uma lista de primitivas em metros (y para cima) calculada do resultado de `derivar` — a mesma geometria
do 3D e das medições — e depois escrita em SVG (ecrã) ou PNG (pranchas PDF do processo).
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from shapely.geometry import LineString, Polygon

INK = (31, 41, 51)
GREY = (130, 136, 140)
RED = (190, 40, 40)
POCHE = (58, 68, 76)
VIDRO = (150, 190, 215)
LADOS = {"frente": ((1, 0), (0, 1)), "tardoz": ((-1, 0), (0, -1)), "esquerda": ((0, -1), (1, 0)), "direita": ((0, 1), (-1, 0))}
NOME_LADO = {"frente": "Alçado principal (frente)", "tardoz": "Alçado de tardoz", "esquerda": "Alçado lateral esquerdo",
             "direita": "Alçado lateral direito"}
COR_FACHADA = {"reboco_branco": (243, 241, 235), "granito": (176, 172, 162), "madeira": (186, 140, 96), "xisto": (104, 98, 92),
               "tijolo": (190, 110, 84), "betao": (176, 176, 172)}
COR_COBERTURA = {"telha_ceramica": (186, 96, 66), "telha_preta": (70, 72, 76), "zinco": (140, 150, 156), "plana_seixo": (182, 176, 164)}


def fmt(v: float, nd: int = 2) -> str:
    return f"{float(v):.{nd}f}".replace(".", ",")


def _poly(pts, fill=None, stroke=INK, lw=1.5, furos=None):
    return {"t": "poly", "pts": [tuple(p) for p in pts], "furos": [[tuple(p) for p in f] for f in (furos or [])],
            "fill": fill, "stroke": stroke, "lw": lw}


def _line(pts, stroke=INK, lw=1.2, dash=False):
    return {"t": "line", "pts": [tuple(p) for p in pts], "stroke": stroke, "lw": lw, "dash": dash}


def _text(x, y, txt, sz=15, cor=INK, anchor="mm", dx=0, dy=0):
    return {"t": "text", "x": x, "y": y, "txt": str(txt), "sz": sz, "cor": cor, "anchor": anchor, "dx": dx, "dy": dy}


def _cadeia(itens, pontos: List[float], fixo: float, horizontal: bool, cor=GREY, sz=13, lado=1):
    """Cadeia de cotas ao longo de um eixo: `pontos` ordenados na direção da cadeia, `fixo` a outra coordenada."""
    pts = sorted({round(p, 3) for p in pontos})
    if len(pts) < 2:
        return
    P = (lambda t: (t, fixo)) if horizontal else (lambda t: (fixo, t))
    itens.append(_line([P(pts[0]), P(pts[-1])], cor, 1.0))
    for t in pts:
        itens.append({"t": "tick", "p": P(t), "horizontal": horizontal, "stroke": cor})
    for a, b in zip(pts, pts[1:]):
        if b - a < 0.02:
            continue
        mx, my = P((a + b) / 2)
        if horizontal:
            itens.append(_text(mx, my, fmt(b - a), sz, cor, "mm", 0, -11 * lado))
        else:
            itens.append(_text(mx, my, fmt(b - a), sz, cor, "lm" if lado > 0 else "rm", 8 * lado, 0))


# ---------------------------------------------------------------- planta
def planta(m: Dict[str, Any], d: Dict[str, Any], k: int) -> Dict[str, Any]:
    piso = d["pisos"][k]
    itens: List[dict] = []
    for dv in d["divisoes"]:
        if dv["piso"] == piso["id"]:
            itens.append(_poly(dv["pts"], (248, 249, 246), None, 0))
    for pp in piso["paredes_planta"]:
        itens.append(_poly(pp["ext"], POCHE, INK, 1.0, pp["furos"]))
    paredes = [w for w in d["paredes"] if w["piso"] == piso["id"]]
    for w in paredes:
        L = w["comprimento_m"]
        ux, uy = (w["b"][0] - w["a"][0]) / L, (w["b"][1] - w["a"][1]) / L
        nx, ny = -uy, ux
        h = w["esp_m"] / 2

        def pt(u, v, _w=w, _ux=ux, _uy=uy, _nx=nx, _ny=ny):
            return (_w["a"][0] + _ux * u + _nx * v, _w["a"][1] + _uy * u + _ny * v)
        for v in w["vaos"]:
            cor = INK if v["valido"] else RED
            itens.append(_poly([pt(v["u0"], h + 0.004), pt(v["u1"], h + 0.004), pt(v["u1"], -h - 0.004), pt(v["u0"], -h - 0.004)],
                               (255, 255, 255), None, 0))
            for u in (v["u0"], v["u1"]):
                itens.append(_line([pt(u, h), pt(u, -h)], cor, 1.4))
            if v["tipo"] == "porta":
                s = v["lado"]
                larg = v["u1"] - v["u0"]
                ub, sentido = (v["u0"], 1) if v["dobradica"] == "a" else (v["u1"], -1)
                itens.append(_line([pt(ub, s * h), pt(ub, s * (h + larg))], cor, 1.6))
                arco = [pt(ub + sentido * larg * math.sin(t), s * (h + larg * math.cos(t))) for t in (i * math.pi / 2 / 14 for i in range(15))]
                itens.append(_line(arco, cor, 0.9))
            else:
                for off in (h, h / 3, -h / 3, -h):
                    itens.append(_line([pt(v["u0"], off), pt(v["u1"], off)], cor, 1.0))
    for dv in d["divisoes"]:
        if dv["piso"] == piso["id"]:
            cx, cy = dv["centro"]
            itens.append(_text(cx, cy, dv["nome"], 17, INK, "mm", 0, -10))
            itens.append(_text(cx, cy, f"{fmt(dv['area_m2'])} m²", 14, GREY, "mm", 0, 10))
    aneis = [p for a in piso["pegada"] for p in a]
    if aneis:
        x0, x1 = min(p[0] for p in aneis), max(p[0] for p in aneis)
        y0, y1 = min(p[1] for p in aneis), max(p[1] for p in aneis)
        un = max(x1 - x0, y1 - y0) / 22
        lados = {"baixo": [x0, x1], "cima": [x0, x1], "esq": [y0, y1], "dir": [y0, y1]}
        for w in paredes:
            if not w["exterior"]:
                continue
            L = w["comprimento_m"]
            ux, uy = (w["b"][0] - w["a"][0]) / L, (w["b"][1] - w["a"][1]) / L
            tol = w["esp_m"] / 2 + 0.03
            for v in w["vaos"]:
                if not v["valido"]:
                    continue
                pa = (w["a"][0] + ux * v["u0"], w["a"][1] + uy * v["u0"])
                pb = (w["a"][0] + ux * v["u1"], w["a"][1] + uy * v["u1"])
                if abs(uy) < 1e-3:
                    if abs(w["a"][1] - y0) <= tol:
                        lados["baixo"] += [pa[0], pb[0]]
                    elif abs(w["a"][1] - y1) <= tol:
                        lados["cima"] += [pa[0], pb[0]]
                elif abs(ux) < 1e-3:
                    if abs(w["a"][0] - x0) <= tol:
                        lados["esq"] += [pa[1], pb[1]]
                    elif abs(w["a"][0] - x1) <= tol:
                        lados["dir"] += [pa[1], pb[1]]
        for nome, fixo, horiz, sinal in (("baixo", y0 - 1.1 * un, True, 1), ("cima", y1 + 1.1 * un, True, 1),
                                         ("esq", x0 - 1.1 * un, False, -1), ("dir", x1 + 1.1 * un, False, 1)):
            if len({round(p, 3) for p in lados[nome]}) > 2:      # só há cadeia parcial onde existem vãos
                _cadeia(itens, lados[nome], fixo, horiz, lado=sinal)
        _cadeia(itens, [x0, x1], y0 - 2.3 * un, True, RED, 16, 1)
        _cadeia(itens, [y0, y1], x0 - 2.6 * un, False, RED, 16, -1)
        itens.append(_text((x0 + x1) / 2, y0 - 3.2 * un, "FRENTE", 13, GREY))
    return {"titulo": f"Planta do {piso['nome'].lower()} — cotada", "itens": itens,
            "rodape": f"Área bruta do piso {fmt(piso['area_bruta_m2'])} m² · cotas em metros · áreas úteis entre faces de parede.",
            "code": "PLANTAS", "filename": f"estudio_planta_piso_{k}.png"}


# ---------------------------------------------------------------- alçados e cortes
def _proj(lado: str):
    (rx, ry), (fx, fy) = LADOS[lado]
    return (lambda x, y: rx * x + ry * y), (lambda x, y: fx * x + fy * y)


def _cores(m):
    mat = m.get("materiais") or {}
    fach = (mat.get("fachada") or "reboco_branco").replace("misto_granito_reboco", "reboco_branco").replace("misto_madeira_reboco", "reboco_branco")
    return COR_FACHADA.get(fach, COR_FACHADA["reboco_branco"]), COR_COBERTURA.get(mat.get("cobertura") or "telha_ceramica", COR_COBERTURA["telha_ceramica"])


def _vista(m, d, lado: str, prof_min: Optional[float] = None, claro: bool = False) -> List[Tuple[float, dict]]:
    """Elementos em projeção ortogonal, do mais afastado para o mais próximo (algoritmo do pintor)."""
    U, F = _proj(lado)
    cf, cc = _cores(m)
    if claro:
        cf, cc = (246, 246, 244), (236, 232, 228)
    tr = GREY if claro else INK
    el: List[Tuple[float, dict]] = []
    for w in d["paredes"]:
        us = [U(x, y) for x, y in w["corpo"]]
        fs = [F(x, y) for x, y in w["corpo"]]
        prof = sum(fs) / 4
        if prof_min is not None and min(fs) < prof_min - 1e-6:
            continue
        z0, z1 = w["z0"], w["z0"] + w["altura_m"]
        cor = cf if w["exterior"] else (236, 236, 232)
        el.append((prof, _poly([(min(us), z0), (max(us), z0), (max(us), z1), (min(us), z1)], cor, tr, 1.2)))
        L = w["comprimento_m"]
        ux, uy = (w["b"][0] - w["a"][0]) / L, (w["b"][1] - w["a"][1]) / L
        if abs(U(ux, uy)) > 0.5:
            for v in w["vaos"]:
                if not v["valido"]:
                    continue
                a = U(w["a"][0] + ux * v["u0"], w["a"][1] + uy * v["u0"])
                b = U(w["a"][0] + ux * v["u1"], w["a"][1] + uy * v["u1"])
                a, b = min(a, b), max(a, b)
                za, zb = w["z0"] + v["z0"], w["z0"] + v["z1"]
                cv = (150, 110, 78) if v["tipo"] == "porta" else VIDRO
                if claro:
                    cv = (232, 238, 242)
                el.append((prof - 0.02, _poly([(a, za), (b, za), (b, zb), (a, zb)], cv, tr, 1.4)))
                if v["tipo"] != "porta":
                    folhas = max(1, round((b - a) / 1.2))
                    for i in range(1, folhas):
                        el.append((prof - 0.03, _line([(a + (b - a) * i / folhas, za), (a + (b - a) * i / folhas, zb)], tr, 1.0)))
    for lj in d["lajes"]:
        for anel in lj["polys"]:
            us = [U(x, y) for x, y in anel]
            fs = [F(x, y) for x, y in anel]
            if prof_min is not None and min(fs) < prof_min - 1e-6:
                continue
            el.append((sum(fs) / len(fs) + 0.01, _poly([(min(us), lj["z0"]), (max(us), lj["z0"]), (max(us), lj["z1"]), (min(us), lj["z1"])],
                                                    cf, tr, 1.0)))
    for f in d["cobertura"]["faces"]:
        fs = [F(x, y) for x, y, _ in f["pts"]]
        if prof_min is not None and max(fs) < prof_min:
            continue
        el.append((sum(fs) / len(fs), _poly([(U(x, y), z) for x, y, z in f["pts"]], cc, tr, 1.2)))
    for e in d["cobertura"]["empenas"]:
        fs = [F(x, y) for x, y, _ in e["pts"]]
        if prof_min is not None and min(fs) < prof_min - 1e-6:
            continue
        el.append((sum(fs) / len(fs), _poly([(U(x, y), z) for x, y, z in e["pts"]], cf, tr, 1.2)))
    el.sort(key=lambda t: -t[0])
    return el


def _niveis(itens, d, u_dir: float, extra: Optional[List[Tuple[float, str]]] = None):
    marcas = [(p["z0"], f"{p['nome']}  {'+' if p['z0'] >= 0 else ''}{fmt(p['z0'])}") for p in d["pisos"]]
    marcas.append((d["cobertura"]["z_topo_paredes"], f"Topo das paredes  +{fmt(d['cobertura']['z_topo_paredes'])}"))
    if d["cobertura"]["z_cumeeira"] > d["cobertura"]["z_topo_paredes"] + 0.01:
        marcas.append((d["cobertura"]["z_cumeeira"], f"Cumeeira  +{fmt(d['cobertura']['z_cumeeira'])}"))
    for z, txt in marcas + (extra or []):
        itens.append(_line([(u_dir + 1.3, z), (u_dir + 2.1, z)], RED, 1.0))
        itens.append(_text(u_dir + 2.2, z, txt, 13, RED, "lm"))


def _extensao_u(d, U) -> Tuple[float, float]:
    us = [U(x, y) for w in d["paredes"] for x, y in w["corpo"]]
    us += [U(x, y) for f in d["cobertura"]["faces"] for x, y, _ in f["pts"]]
    return (min(us), max(us)) if us else (0.0, 1.0)


def alcado(m: Dict[str, Any], d: Dict[str, Any], lado: str) -> Dict[str, Any]:
    U, _ = _proj(lado)
    itens = [it for _, it in _vista(m, d, lado)]
    u0, u1 = _extensao_u(d, U)
    zs = d["pisos"][0]["z0"] if d["pisos"] else 0.0
    itens.append(_line([(u0 - 1.0, zs), (u1 + 1.0, zs)], INK, 2.4))
    _niveis(itens, d, u1)
    return {"titulo": NOME_LADO[lado], "itens": itens, "code": "ALCADOS", "filename": f"estudio_alcado_{lado}.png",
            "rodape": "Projeção ortogonal do modelo; cotas altimétricas relativas à soleira (±0,00)."}


def corte(m: Dict[str, Any], d: Dict[str, Any], eixo: str = "x", pos: Optional[float] = None) -> Dict[str, Any]:
    """Corte vertical pelo plano x = pos (eixo «x», olha-se para a direita) ou y = pos (eixo «y», olha-se para o tardoz)."""
    lado = "esquerda" if eixo == "x" else "frente"       # mesma direção de observação do alçado correspondente
    U, F = _proj(lado)
    lim = d.get("limites") or [0, 0, 1, 1]
    if pos is None:
        pos = (lim[0] + lim[2]) / 2 if eixo == "x" else (lim[1] + lim[3]) / 2
        for _ in range(8):   # não cortar ao longo do eixo de uma parede paralela ao plano
            if not any(abs((w["a"][0] if eixo == "x" else w["a"][1]) - pos) < w["esp_m"] / 2 + 0.05
                       and abs((w["b"][0] - w["a"][0]) if eixo == "x" else (w["b"][1] - w["a"][1])) < 1e-3 for w in d["paredes"]):
                break
            pos += 0.45
    itens = [it for _, it in _vista(m, d, lado, prof_min=pos, claro=True)]
    plano = LineString([(pos, lim[1] - 50), (pos, lim[3] + 50)] if eixo == "x" else [(lim[0] - 50, pos), (lim[2] + 50, pos)])
    for lj in d["lajes"]:
        for anel in lj["polys"]:
            g = Polygon(anel).intersection(plano)
            for s in ([g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))):
                if s.geom_type != "LineString" or s.length < 0.01:
                    continue
                us = [U(x, y) for x, y in s.coords]
                itens.append(_poly([(min(us), lj["z0"]), (max(us), lj["z0"]), (max(us), lj["z1"]), (min(us), lj["z1"])], (150, 156, 160), INK, 1.6))
    for w in d["paredes"]:
        g = Polygon(w["corpo"]).intersection(plano)
        if g.is_empty or g.geom_type != "LineString" or g.length < 0.01:
            continue
        us = [U(x, y) for x, y in g.coords]
        a, b = min(us), max(us)
        z0, z1 = w["z0"], w["z0"] + w["altura_m"]
        L = w["comprimento_m"]
        ux, uy = (w["b"][0] - w["a"][0]) / L, (w["b"][1] - w["a"][1]) / L
        mx, my = g.interpolate(0.5, normalized=True).coords[0]
        s = (mx - w["a"][0]) * ux + (my - w["a"][1]) * uy
        faixas = [(z0, z1)]
        for v in w["vaos"]:
            if v["valido"] and v["u0"] < s < v["u1"]:
                faixas = [(z0, z0 + v["z0"]), (z0 + v["z1"], z1)]
        for za, zb in faixas:
            if zb - za > 0.005:
                itens.append(_poly([(a, za), (b, za), (b, zb), (a, zb)], POCHE, INK, 1.6))
    for f in d["cobertura"]["faces"]:
        pts, corta = f["pts"], []
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            cp, cq = (p[0] if eixo == "x" else p[1]) - pos, (q[0] if eixo == "x" else q[1]) - pos
            if (cp <= 0 < cq) or (cq <= 0 < cp):
                t = cp / (cp - cq)
                x, y, z = (p[j] + t * (q[j] - p[j]) for j in range(3))
                corta.append((U(x, y), z))
        if len(corta) >= 2:
            corta.sort()
            itens.append(_line([corta[0], corta[-1]], INK, 4.0))
    u0, u1 = _extensao_u(d, U)
    zs = d["pisos"][0]["z0"] if d["pisos"] else 0.0
    itens.append(_line([(u0 - 1.0, zs), (u1 + 1.0, zs)], INK, 2.4))
    for p in d["pisos"]:
        itens.append(_text(u0 - 0.4, (p["z0"] + p["z1"]) / 2, f"pé-direito {fmt(p['pe_direito_m'])}", 13, GREY, "rm"))
    _niveis(itens, d, u1)
    nome = "A-A (transversal)" if eixo == "x" else "B-B (longitudinal)"
    return {"titulo": f"Corte {nome} — plano {eixo} = {fmt(pos)} m", "itens": itens, "code": "CORTES",
            "filename": f"estudio_corte_{eixo}.png", "pos": round(pos, 3),
            "rodape": "A escuro: elementos cortados (paredes, lajes, cobertura). A claro: o que fica para lá do plano de corte."}


# ---------------------------------------------------------------- escrita (SVG e PNG)
W, H, MARGEM, TOPO = 1600, 1130, 130, 36


def _escala(des: Dict[str, Any]):
    xs, ys = [], []
    for it in des["itens"]:
        if it["t"] in ("poly", "line"):
            xs += [p[0] for p in it["pts"]]
            ys += [p[1] for p in it["pts"]]
        elif it["t"] == "text":
            xs.append(it["x"])
            ys.append(it["y"])
        elif it["t"] == "tick":
            xs.append(it["p"][0])
            ys.append(it["p"][1])
    if not xs:
        xs, ys = [0, 1], [0, 1]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    dx, dy = max(x1 - x0, 0.5), max(y1 - y0, 0.5)
    s = min((W - 2 * MARGEM - 120) / dx, (H - TOPO - 2 * 90) / dy)
    ox = (W - 120 - dx * s) / 2 - x0 * s
    oy = TOPO + (H - TOPO - 40 + dy * s) / 2 + y0 * s
    return lambda p: (round(ox + p[0] * s, 2), round(oy - p[1] * s, 2))


def _rgb(c) -> str:
    return "none" if c is None else f"rgb({c[0]},{c[1]},{c[2]})"


def svg(des: Dict[str, Any]) -> str:
    P = _escala(des)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#fff"/>',
         f'<rect width="{W}" height="{TOPO}" fill="rgb(23,60,50)"/>',
         f'<text x="12" y="24" font-size="16" fill="#fff">{escape(des["titulo"])}</text>']
    for it in des["itens"]:
        if it["t"] == "poly":
            dpath = "M" + " L".join(f"{x},{y}" for x, y in map(P, it["pts"])) + " Z"
            for f in it["furos"]:
                dpath += " M" + " L".join(f"{x},{y}" for x, y in map(P, f)) + " Z"
            o.append(f'<path d="{dpath}" fill="{_rgb(it["fill"])}" fill-rule="evenodd" stroke="{_rgb(it["stroke"])}" '
                     f'stroke-width="{it["lw"]}" stroke-linejoin="round"/>')
        elif it["t"] == "line":
            pts = " ".join(f"{x},{y}" for x, y in map(P, it["pts"]))
            dash = ' stroke-dasharray="8 6"' if it["dash"] else ""
            o.append(f'<polyline points="{pts}" fill="none" stroke="{_rgb(it["stroke"])}" stroke-width="{it["lw"]}"{dash}/>')
        elif it["t"] == "tick":
            x, y = P(it["p"])
            a, b = ((x, y - 6), (x, y + 6)) if it["horizontal"] else ((x - 6, y), (x + 6, y))
            o.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{_rgb(it["stroke"])}" stroke-width="1.2"/>')
        elif it["t"] == "text":
            x, y = P((it["x"], it["y"]))
            anc = {"m": "middle", "l": "start", "r": "end"}[it["anchor"][0]]
            o.append(f'<text x="{x + it["dx"]}" y="{y + it["dy"]}" font-size="{it["sz"]}" fill="{_rgb(it["cor"])}" '
                     f'text-anchor="{anc}" dominant-baseline="middle">{escape(it["txt"])}</text>')
    if des.get("rodape"):
        o.append(f'<text x="12" y="{H - 14}" font-size="12" fill="{_rgb(GREY)}">{escape(des["rodape"])}</text>')
    o.append("</svg>")
    return "".join(o)


def png(des: Dict[str, Any]) -> bytes:
    from PIL import Image, ImageDraw
    from engines.urbanismo_pt import volumes as V
    P = _escala(des)
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img)
    for it in des["itens"]:
        if it["t"] == "poly":
            pts = [P(p) for p in it["pts"]]
            if it["fill"] is not None:
                dr.polygon(pts, fill=it["fill"])
                for f in it["furos"]:
                    dr.polygon([P(p) for p in f], fill="white")
            if it["stroke"] is not None and it["lw"] > 0:
                lw = max(1, round(it["lw"]))
                dr.line(pts + [pts[0]], fill=it["stroke"], width=lw)
                for f in it["furos"]:
                    fp = [P(p) for p in f]
                    dr.line(fp + [fp[0]], fill=it["stroke"], width=lw)
        elif it["t"] == "line":
            dr.line([P(p) for p in it["pts"]], fill=it["stroke"], width=max(1, round(it["lw"])))
        elif it["t"] == "tick":
            x, y = P(it["p"])
            dr.line([(x, y - 6), (x, y + 6)] if it["horizontal"] else [(x - 6, y), (x + 6, y)], fill=it["stroke"], width=1)
        elif it["t"] == "text":
            x, y = P((it["x"], it["y"]))
            dr.text((x + it["dx"], y + it["dy"]), it["txt"], fill=it["cor"], font=V._font(it["sz"]), anchor=it["anchor"])
    V._header(dr, W, des["titulo"])
    if des.get("rodape"):
        dr.text((12, H - 22), des["rodape"], fill=GREY, font=V._font(12))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def conjunto(m: Dict[str, Any], d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Todas as peças do Estúdio, pela ordem das pranchas: plantas, alçados, cortes."""
    out = [planta(m, d, k) for k in range(len(d["pisos"]))]
    if d["paredes"]:
        out += [alcado(m, d, lado) for lado in ("frente", "tardoz", "esquerda", "direita")]
        out += [corte(m, d, "x"), corte(m, d, "y")]
    return out


def pecas_png(m: Dict[str, Any], d: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"code": x["code"], "title": x["titulo"], "filename": x["filename"], "png": png(x)} for x in conjunto(m, d)]
