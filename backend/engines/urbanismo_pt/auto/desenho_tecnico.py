"""Peças desenhadas de arquitetura à escala (folhas A3, 1:100) para o processo de licenciamento.

Tudo sai dos MESMOS dados do processo (contorno, compartimentos, vãos, alturas, materiais) que alimentam a memória,
o quadro de áreas e a maquete 3D — nada é inventado à parte:

* planta do piso com paredes (exteriores 0,30 m, interiores 0,12 m), portas com abertura, janelas, cotas e áreas;
* planta de cobertura (cobertura plana com platibanda, pendentes e tubos de queda);
* quatro alçados com os vãos e os revestimentos (granito, ripado de madeira, reboco, xisto);
* dois cortes (transversal e longitudinal) com laje, platibanda, pé-direito e cotas.

As portas interiores são deduzidas da distribuição (cada compartimento abre para a circulação, a sala ou — no caso
da I.S. da suite — para a suite). Os desenhos continuam a ter de ser verificados, completados e assinados por
arquiteto inscrito na Ordem dos Arquitetos antes da submissão (art.º 10.º do RJUE).
"""
from __future__ import annotations

import io
import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from engines.urbanismo_pt import volumes as V

DPI = 150
A3 = (2480, 1754)                       # A3 horizontal a 150 dpi
ESCALA = 100                            # 1:100
PX_M = DPI / 25.4 * 1000 / ESCALA       # píxeis por metro real (≈ 59,06)
P_EXT, P_INT = 0.30, 0.12

INK = (25, 25, 25)
CINZA = (120, 120, 120)
POCHE = (55, 55, 55)
COTA = (170, 30, 30)
VIDRO = (200, 224, 238)
VERDE = (23, 60, 50)
MAT_COR = {"granito": (196, 192, 184), "madeira": (176, 128, 84), "reboco_branco": (243, 241, 236),
           "xisto": (110, 104, 98), "betao": (186, 186, 182), "garagem": (210, 208, 202)}
MAT_NOME = {"granito": "granito natural bujardado", "madeira": "ripado vertical de madeira", "reboco_branco": "reboco pintado branco",
            "xisto": "pedra de xisto", "betao": "betão aparente", "garagem": "reboco pintado"}
NAO_PORTA = {"sala", "circulacao", "entrada"}     # espaços abertos entre si (sem porta)


# ------------------------------------------------------------------ dados
def _dados(processo: Dict[str, Any]) -> Dict[str, Any]:
    a = processo.get("auto") or {}
    vol = processo.get("volume") or {}
    hh = V.heights(vol)
    polys = V.building_polygons(vol)
    casa = [p for p in polys if not p["annexe"]]
    anexos = [p for p in polys if p["annexe"]]
    pl = a.get("plantas") or {}
    cont = [tuple(map(float, p)) for p in (pl.get("contorno") or casa[0]["pts"])]
    if _area(cont) < 0:
        cont = cont[::-1]
    pisos = pl.get("pisos") or []
    mats = a.get("materiais") or {}
    fach = mats.get("fachada") or "reboco_branco"
    yc = None
    if len(cont) == 6:
        ys = sorted({p[1] for p in cont})
        if len(ys) == 3:
            yc = ys[1]
    h_laje = hh["altura_fachada_m"]
    plano = hh["roof_type"] == "plana"
    return {"a": a, "vol": vol, "hh": hh, "cont": cont, "anexos": anexos, "pisos": pisos, "vaos": a.get("vaos") or [],
            "fachada": fach, "yc": yc, "h_laje": h_laje,
            "h_top": (hh["altura_total_m"] if hh["altura_total_m"] > h_laje + 0.05 else h_laje + 0.45) if plano else hh["altura_total_m"],
            "plano": plano, "pd": round(h_laje - 0.30, 2), "mats": mats, "titulo": processo.get("title") or "",
            "local": " · ".join(x for x in ((processo.get("terreno") or {}).get("morada"), (processo.get("terreno") or {}).get("concelho")) if x),
            "requerente": ((processo.get("requerente") or {}).get("nome") or "")}


def _area(P) -> float:
    return sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P))) / 2


def _dentro(pt, P) -> bool:
    x, y = pt
    ins = False
    for i in range(len(P)):
        (x1, y1), (x2, y2) = P[i], P[(i + 1) % len(P)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ins = not ins
    return ins


def _material(D, a, b, anexo=False) -> str:
    fach = D["fachada"]
    p1, p2 = {"misto_granito_reboco": ("reboco_branco", "granito"), "misto_madeira_reboco": ("reboco_branco", "madeira"),
              "misto_granito_madeira": ("granito", "madeira")}.get(fach, (fach if fach in MAT_COR else "reboco_branco",) * 2)
    if anexo:
        return "garagem" if p1 in ("reboco_branco", "betao") else p1
    yc = D["yc"]
    if fach == "misto_granito_madeira" and yc is not None:
        ala = (a[1] + b[1]) / 2 > yc + 1e-6
        patio = abs(a[1] - yc) < 1e-6 and abs(b[1] - yc) < 1e-6
        return "madeira" if (ala or patio) else "granito"
    if p1 != p2:
        comp = math.hypot(b[0] - a[0], b[1] - a[1])
        nx = (b[1] - a[1]) / comp
        ny = -(b[0] - a[0]) / comp
        sol = (D["a"].get("implantacao") or {}).get("fachada_sol", "frente")
        lado_sol = (ny < -0.7 and sol == "frente") or (ny > 0.7 and sol == "tardoz")
        return p2 if lado_sol or (abs(nx) > 0.7 and comp < 10) else p1
    return p1


def _arestas(D) -> List[Tuple[Tuple[float, float], Tuple[float, float], bool]]:
    """Arestas exteriores (a, b, anexo) — as paredes contínuas do L dividem-se na junção (cada parte com o seu material)."""
    out = []
    for P, anexo in [(D["cont"], False)] + [([tuple(p) for p in x["pts"]], True) for x in D["anexos"]]:
        if _area(P) < 0:
            P = P[::-1]
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            yc = D["yc"]
            if not anexo and yc is not None and abs(a[0] - b[0]) < 1e-6 and min(a[1], b[1]) < yc - 1e-6 < yc + 1e-6 < max(a[1], b[1]):
                out += [(a, (a[0], yc), anexo), ((a[0], yc), b, anexo)]
            else:
                out.append((a, b, anexo))
    return out


# ------------------------------------------------------------------ folha
class Folha:
    def __init__(self, titulo: str, D: Dict[str, Any], peca: str, escala: str = "1:100"):
        self.im = Image.new("RGB", A3, "white")
        self.dr = ImageDraw.Draw(self.im)
        W, H = A3
        dr = self.dr
        dr.rectangle([30, 30, W - 30, H - 30], outline=INK, width=3)
        dr.rectangle([30, 30, W - 30, 96], fill=VERDE)
        dr.text((52, 46), titulo, fill="white", font=V._font(30))
        dr.text((W - 560, 52), f"Escala {escala} (folha A3)", fill="white", font=V._font(22))
        # carimbo
        x0, y0 = W - 820, H - 250
        dr.rectangle([x0, y0, W - 30, H - 30], outline=INK, width=2, fill="white")
        linhas = [("Processo", D["titulo"][:50]), ("Local", D["local"][:50] or "—"), ("Requerente", D["requerente"] or "a completar"),
                  ("Peça", peca), ("Escala", escala), ("Data", date.today().strftime("%d/%m/%Y")),
                  ("Autor do projeto", "__________________________  n.º OA ______")]
        for k, (lab, val) in enumerate(linhas):
            yy = y0 + 12 + k * 29
            dr.text((x0 + 16, yy), lab, fill=CINZA, font=V._font(17))
            dr.text((x0 + 230, yy), val, fill=INK, font=V._font(18))
        dr.text((52, H - 70), "Peça desenhada gerada pelo ConstruPilot a partir dos dados do processo — a verificar, completar e "
                              "assinar por arquiteto inscrito na OA antes da submissão (art.º 10.º RJUE).", fill=CINZA, font=V._font(17))
        self.area = (60, 120, W - 60, H - 270)

    def escala_grafica(self, x, y, s=PX_M):
        dr = self.dr
        for k in range(5):
            dr.rectangle([x + k * s, y, x + (k + 1) * s, y + 12], fill=INK if k % 2 == 0 else "white", outline=INK)
        for k in (0, 1, 2, 5):
            dr.text((x + k * s - 5, y + 16), f"{k}", fill=INK, font=V._font(16))
        dr.text((x + 5 * s + 12, y - 2), "m", fill=INK, font=V._font(16))

    def png(self) -> bytes:
        b = io.BytesIO()
        self.im.save(b, "PNG", dpi=(DPI, DPI))
        return b.getvalue()


def _cota_h(dr, x1, x2, y, txt, cor=COTA, f=16):
    dr.line([x1, y, x2, y], fill=cor, width=2)
    for x in (x1, x2):
        dr.line([x - 6, y + 6, x + 6, y - 6], fill=cor, width=2)
        dr.line([x, y - 12, x, y + 12], fill=cor, width=1)
    w = dr.textlength(txt, font=V._font(f))
    dr.text(((x1 + x2) / 2 - w / 2, y - f - 6), txt, fill=cor, font=V._font(f))


def _cota_v(dr, x, y1, y2, txt, cor=COTA, f=16):
    dr.line([x, y1, x, y2], fill=cor, width=2)
    for y in (y1, y2):
        dr.line([x - 6, y + 6, x + 6, y - 6], fill=cor, width=2)
        dr.line([x - 12, y, x + 12, y], fill=cor, width=1)
    dr.text((x + 8, (y1 + y2) / 2 - f / 2), txt, fill=cor, font=V._font(f))


def _cota_nivel(dr, x, y, txt):
    dr.polygon([(x, y), (x - 9, y - 14), (x + 9, y - 14)], outline=INK, fill="white")
    dr.line([x - 30, y, x + 30, y], fill=INK, width=1)
    dr.text((x + 14, y - 22), txt, fill=INK, font=V._font(16))


# ------------------------------------------------------------------ planta
def _portas(comps: List[dict]) -> List[Dict[str, Any]]:
    """Portas interiores: cada compartimento fechado abre para o espaço de circulação vizinho com maior contacto
    (a I.S. da suite abre para a suite). Devolve [{x, y, eixo, larg, para}] no meio da parede comum, perto do canto."""
    def contacto(c, o):
        if abs(c["x1"] - o["x0"]) < 1e-3 or abs(c["x0"] - o["x1"]) < 1e-3:
            lo, hi = max(c["y0"], o["y0"]), min(c["y1"], o["y1"])
            return ("y", c["x1"] if abs(c["x1"] - o["x0"]) < 1e-3 else c["x0"], lo, hi) if hi - lo > 0.85 else None
        if abs(c["y1"] - o["y0"]) < 1e-3 or abs(c["y0"] - o["y1"]) < 1e-3:
            lo, hi = max(c["x0"], o["x0"]), min(c["x1"], o["x1"])
            return ("x", c["y1"] if abs(c["y1"] - o["y0"]) < 1e-3 else c["y0"], lo, hi) if hi - lo > 0.85 else None
        return None
    out = []
    for c in comps:
        if c["tipo"] in NAO_PORTA:
            continue
        alvo = []
        for o in comps:
            if o is c:
                continue
            k = contacto(c, o)
            if not k:
                continue
            pref = 0
            if c["tipo"] == "wc" and "suite" in c["nome"].lower():
                pref = 3 if "suite" in o["nome"].lower() and o["tipo"] == "quarto" else -5
            elif o["tipo"] == "circulacao":
                pref = 2
            elif o["tipo"] in ("sala", "entrada"):
                pref = 1
            elif c["tipo"] in ("lavandaria", "despensa") and o["tipo"] == "cozinha":
                pref = 2
            else:
                continue
            alvo.append((pref, k[3] - k[2], k, o))
        if not alvo:
            continue
        alvo.sort(key=lambda t: (-t[0], -t[1]))
        _, _, (eixo, pos, lo, hi), o = alvo[0]
        larg = 0.70 if c["tipo"] in ("wc", "wc_social", "despensa", "lavandaria") else 0.80
        ini = lo + 0.15 if hi - lo > larg + 0.3 else (lo + hi - larg) / 2
        out.append({"eixo": eixo, "pos": pos, "a": ini, "b": ini + larg, "comp": c, "para": o})
    return out


def planta_piso(processo: Dict[str, Any], piso: int = 0) -> bytes:
    D = _dados(processo)
    pp = next((p for p in D["pisos"] if int(p.get("piso", 0)) == piso), None)
    F = Folha(f"Planta do {('rés-do-chão' if piso == 0 else f'{piso}.º andar')} — arquitetura", D,
              f"Planta do {'rés-do-chão' if piso == 0 else f'{piso}.º andar'}")
    dr = F.dr
    pts_all = list(D["cont"]) + [tuple(p) for x in D["anexos"] for p in x["pts"]]
    X0, X1 = min(p[0] for p in pts_all), max(p[0] for p in pts_all)
    Y0, Y1 = min(p[1] for p in pts_all), max(p[1] for p in pts_all)
    ax0, ay0, ax1, ay1 = F.area
    ox = ax0 + 260 + ((ax1 - ax0 - 520) - (X1 - X0) * PX_M) / 2
    oy = ay1 - 150 - ((ay1 - ay0 - 300) - (Y1 - Y0) * PX_M) / 2

    def T(x, y):
        return (ox + (x - X0) * PX_M, oy - (y - Y0) * PX_M)

    def R(x0, y0, x1, y1, **kw):
        a, b = T(x0, y1), T(x1, y0)
        dr.rectangle([a[0], a[1], b[0], b[1]], **kw)

    cont = D["cont"]
    dr.polygon([T(*p) for p in cont], fill=POCHE)
    comps = (pp or {}).get("compartimentos") or []
    ex = P_EXT
    for c in comps:
        def lado(px, py):   # True se o outro lado da aresta ainda é casa (parede interior)
            return _dentro((px, py), cont)
        mx, my = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        e_x0 = P_INT / 2 if lado(c["x0"] - 0.05, my) else ex
        e_x1 = P_INT / 2 if lado(c["x1"] + 0.05, my) else ex
        e_y0 = P_INT / 2 if lado(mx, c["y0"] - 0.05) else ex
        e_y1 = P_INT / 2 if lado(mx, c["y1"] + 0.05) else ex
        R(c["x0"] + e_x0, c["y0"] + e_y0, c["x1"] - e_x1, c["y1"] - e_y1, fill="white")
    # aberturas entre espaços abertos (sala / entrada / circulação): sem parede
    abertos = [c for c in comps if c["tipo"] in NAO_PORTA]
    for i, c in enumerate(abertos):
        for o in abertos[i + 1:]:
            if abs(c["y1"] - o["y0"]) < 1e-3 or abs(c["y0"] - o["y1"]) < 1e-3:
                lo, hi = max(c["x0"], o["x0"]) + P_INT, min(c["x1"], o["x1"]) - P_INT
                y = c["y1"] if abs(c["y1"] - o["y0"]) < 1e-3 else c["y0"]
                if hi - lo > 0.9:
                    R(lo, y - P_INT, hi, y + P_INT, fill="white")
            if abs(c["x1"] - o["x0"]) < 1e-3 or abs(c["x0"] - o["x1"]) < 1e-3:
                lo, hi = max(c["y0"], o["y0"]) + P_INT, min(c["y1"], o["y1"]) - P_INT
                x = c["x1"] if abs(c["x1"] - o["x0"]) < 1e-3 else c["x0"]
                if hi - lo > 0.9:
                    R(x - P_INT, lo, x + P_INT, hi, fill="white")
    # portas interiores (vão + folha + arco de abertura)
    for p in _portas(comps):
        c = p["comp"]
        if p["eixo"] == "x":     # parede horizontal (y = pos)
            y = p["pos"]
            R(p["a"], y - P_INT, p["b"], y + P_INT, fill="white")
            dentro = 1 if (c["y0"] + c["y1"]) / 2 > y else -1
            hx, hy = T(p["a"], y)
            r = (p["b"] - p["a"]) * PX_M
            fx, fy = T(p["a"], y + dentro * (p["b"] - p["a"]))
            dr.line([hx, hy, fx, fy], fill=INK, width=3)
            bb = [hx - r, hy - r, hx + r, hy + r]
            dr.arc(bb, 270 if dentro > 0 else 0, 360 if dentro > 0 else 90, fill=CINZA, width=1)
        else:                     # parede vertical (x = pos)
            x = p["pos"]
            R(x - P_INT, p["a"], x + P_INT, p["b"], fill="white")
            dentro = 1 if (c["x0"] + c["x1"]) / 2 > x else -1
            hx, hy = T(x, p["a"])
            r = (p["b"] - p["a"]) * PX_M
            fx, fy = T(x + dentro * (p["b"] - p["a"]), p["a"])
            dr.line([hx, hy, fx, fy], fill=INK, width=3)
            bb = [hx - r, hy - r, hx + r, hy + r]
            dr.arc(bb, 270 if dentro > 0 else 180, 360 if dentro > 0 else 270, fill=CINZA, width=1)
    # vãos exteriores
    for v in D["vaos"]:
        if int(v.get("piso", 0)) != piso or v.get("plano_m") is None:
            continue
        u0, u1, pl = float(v["x0"]), float(v["x1"]), float(v["plano_m"])
        horiz = v.get("eixo", "x" if v["fachada"] in ("frente", "tardoz") else "y") == "x"
        fora = {"frente": -1, "tardoz": 1, "esquerda": -1, "direita": 1}.get(v["fachada"], 1)
        if horiz:
            ya, yb = (pl, pl - fora * ex)
            R(u0, min(ya, yb), u1, max(ya, yb), fill="white")
            for k in (0.33, 0.5, 0.67) if v["tipo"] != "porta" else ():
                yy = pl - fora * ex * k
                dr.line([T(u0, yy), T(u1, yy)], fill=INK, width=2 if k == 0.5 else 1)
            dr.line([T(u0, ya), T(u0, yb)], fill=INK, width=2)
            dr.line([T(u1, ya), T(u1, yb)], fill=INK, width=2)
            if v["tipo"] == "porta":
                hx, hy = T(u0, pl - fora * ex)
                r = (u1 - u0) * PX_M
                fx, fy = T(u0, pl - fora * (ex + (u1 - u0)))
                dr.line([hx, hy, fx, fy], fill=INK, width=3)
                dr.arc([hx - r, hy - r, hx + r, hy + r], 270 if fora < 0 else 0, 360 if fora < 0 else 90, fill=CINZA)
            elif v["tipo"] == "envidracado":
                m = (u0 + u1) / 2
                dr.line([T(u0 + 0.1, pl - fora * ex * 0.4), T(m + 0.2, pl - fora * ex * 0.4)], fill=INK, width=3)
                dr.line([T(m - 0.2, pl - fora * ex * 0.6), T(u1 - 0.1, pl - fora * ex * 0.6)], fill=INK, width=3)
        else:
            xa, xb = (pl, pl - fora * ex)
            R(min(xa, xb), u0, max(xa, xb), u1, fill="white")
            for k in (0.33, 0.5, 0.67) if v["tipo"] != "porta" else ():
                xx = pl - fora * ex * k
                dr.line([T(xx, u0), T(xx, u1)], fill=INK, width=2 if k == 0.5 else 1)
            dr.line([T(xa, u0), T(xb, u0)], fill=INK, width=2)
            dr.line([T(xa, u1), T(xb, u1)], fill=INK, width=2)
    # nomes e áreas
    for c in comps:
        cx, cy = T((c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2)
        nome = c["nome"]
        f = V._font(18 if (c["x1"] - c["x0"]) > 2.2 else 14)
        w = dr.textlength(nome, font=f)
        if w > (c["x1"] - c["x0"]) * PX_M - 10:
            nome = nome.replace("Instalação sanitária", "I.S.").replace("Corredor dos quartos", "Corredor").replace(" e jantar", "")
            w = dr.textlength(nome, font=f)
        dr.text((cx - w / 2, cy - 22), nome, fill=INK, font=f)
        t = f"{V.fmt(c.get('area_util_m2'), 2)} m²"
        w2 = dr.textlength(t, font=V._font(16))
        dr.text((cx - w2 / 2, cy + 2), t, fill=CINZA, font=V._font(16))
    # anexo (garagem)
    for x in D["anexos"]:
        P = [tuple(p) for p in x["pts"]]
        xs, ys = [p[0] for p in P], [p[1] for p in P]
        R(min(xs), min(ys), max(xs), max(ys), fill=POCHE)
        R(min(xs) + 0.25, min(ys) + 0.25, max(xs) - 0.25, max(ys) - 0.25, fill="white")
        larg_p = min(5.0, max(xs) - min(xs) - 1.2)
        px0 = (min(xs) + max(xs)) / 2 - larg_p / 2
        R(px0, min(ys), px0 + larg_p, min(ys) + 0.25, fill="white")
        dr.line([T(px0, min(ys) + 0.12), T(px0 + larg_p, min(ys) + 0.12)], fill=INK, width=2)
        cx, cy = T((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        a_g = (max(xs) - min(xs) - 0.5) * (max(ys) - min(ys) - 0.5)
        for k, s in enumerate((x.get("name") or "Garagem", f"{V.fmt(a_g, 2)} m²", f"portão {V.fmt(larg_p, 2)} m")):
            w = dr.textlength(s, font=V._font(18 if k == 0 else 15))
            dr.text((cx - w / 2, cy - 22 + k * 22), s, fill=INK if k == 0 else CINZA, font=V._font(18 if k == 0 else 15))
    # cotas gerais
    ya = Y0 - 1.6
    _cota_h(dr, T(X0, 0)[0], T(max(p[0] for p in cont), 0)[0], T(0, ya)[1], f"{V.fmt(max(p[0] for p in cont) - X0, 2)} m")
    xv = X0 - 1.6
    _cota_v(dr, T(xv, 0)[0], T(0, max(p[1] for p in cont))[1], T(0, Y0)[1], f"{V.fmt(max(p[1] for p in cont) - Y0, 2)} m")
    # cotas parciais da frente (vãos)
    frente = sorted([v for v in D["vaos"] if v["fachada"] == "frente" and int(v.get("piso", 0)) == piso], key=lambda v: v["x0"])
    xs_c = [X0] + [u for v in frente for u in (v["x0"], v["x1"])] + [max(p[0] for p in cont)]
    for a_, b_ in zip(xs_c, xs_c[1:]):
        if b_ - a_ > 0.3:
            _cota_h(dr, T(a_, 0)[0], T(b_, 0)[0], T(0, Y0 - 0.8)[1], V.fmt(b_ - a_, 2), cor=CINZA, f=13)
    if D["yc"] is not None:
        _cota_v(dr, T(X0 - 0.8, 0)[0], T(0, D["yc"])[1], T(0, Y0)[1], V.fmt(D["yc"] - Y0, 2), cor=CINZA, f=13)
        _cota_v(dr, T(X0 - 0.8, 0)[0], T(0, max(p[1] for p in cont))[1], T(0, D["yc"])[1],
                V.fmt(max(p[1] for p in cont) - D["yc"], 2), cor=CINZA, f=13)
    # linhas de corte
    A_y, B_x = _linhas_corte(D)
    for (p, q, lab) in (((X0 - 0.8, A_y), (X1 + 0.8, A_y), "A"), ((B_x, Y0 - 0.5), (B_x, Y1 + 0.8), "B")):
        V._dash_line(dr, T(*p), T(*q), COTA, dash=18, gap=8, width=2)
        for e in (p, q):
            ex_, ey_ = T(*e)
            dr.ellipse([ex_ - 16, ey_ - 16, ex_ + 16, ey_ + 16], outline=COTA, width=2, fill="white")
            dr.text((ex_ - 7, ey_ - 11), lab, fill=COTA, font=V._font(18))
    # cota de soleira + norte + legenda
    cx, cy = T((X0 + max(p[0] for p in cont)) / 2, Y0 + 1.2)
    _cota_nivel(dr, cx + 3 * PX_M, cy, "±0,00 (soleira)")
    az = ((D["a"].get("terreno") or {}).get("azimutes") or {}).get("tardoz")
    nx, ny = ax1 - 130, ay0 + 60
    ang = math.radians(-(az or 0.0))
    tip = (nx + 40 * math.sin(ang), ny + 50 - 40 * math.cos(ang))
    dr.ellipse([nx - 46, ny + 4, nx + 46, ny + 96], outline=INK, width=2)
    dr.polygon([tip, (nx - 10 * math.cos(ang), ny + 50 - 10 * math.sin(ang)), (nx + 10 * math.cos(ang), ny + 50 + 10 * math.sin(ang))], fill=INK)
    dr.text((nx - 7, ny + 100), "N", fill=INK, font=V._font(20))
    lx, ly = ax0 + 10, ay0 + 10
    leg = [("Parede exterior 0,30 m (alvenaria + isolamento + revestimento)", POCHE), ("Parede interior 0,12 m", POCHE)]
    for k, (t, cor) in enumerate(leg):
        dr.rectangle([lx, ly + k * 30, lx + 36, ly + k * 30 + 16], fill=cor)
        dr.text((lx + 48, ly + k * 30 - 2), t, fill=INK, font=V._font(16))
    tot = sum(float(c.get("area_util_m2") or 0) for c in comps)
    dr.text((lx, ly + 76), f"Área útil total do piso: {V.fmt(tot, 2)} m²  ·  pé-direito livre {V.fmt(D['pd'], 2)} m", fill=INK, font=V._font(17))
    sem_janela = [c["nome"] for c in comps if c["tipo"] in ("wc", "wc_social", "despensa")
                  and not any(v.get("compartimento") == c["nome"] for v in D["vaos"])]
    if sem_janela:
        dr.text((lx, ly + 104), "Ventilação mecânica (sem vão exterior): " + ", ".join(sem_janela), fill=CINZA, font=V._font(15))
    F.escala_grafica(ax0 + 10, ay1 - 30)
    return F.png()


def _linhas_corte(D) -> Tuple[float, float]:
    cont = D["cont"]
    ys = [p[1] for p in cont]
    xs = [p[0] for p in cont]
    yc = D["yc"] if D["yc"] is not None else max(ys)
    A_y = (min(ys) + yc) / 2 + 0.35           # transversal, pelo corpo principal (sala / entrada)
    if D["yc"] is not None:                   # longitudinal pela ala dos quartos e pelo corpo
        xa = sorted({p[0] for p in cont})
        B_x = (xa[0] + xa[1]) / 2 + 1.2 if len(xa) >= 3 else (min(xs) + max(xs)) / 2
    else:
        B_x = (min(xs) + max(xs)) / 2
    return A_y, B_x


# ------------------------------------------------------------------ cobertura
def planta_cobertura(processo: Dict[str, Any]) -> bytes:
    D = _dados(processo)
    F = Folha("Planta de cobertura", D, "Planta de cobertura")
    dr = F.dr
    cont = D["cont"]
    pts_all = list(cont) + [tuple(p) for x in D["anexos"] for p in x["pts"]]
    X0, X1 = min(p[0] for p in pts_all), max(p[0] for p in pts_all)
    Y0, Y1 = min(p[1] for p in pts_all), max(p[1] for p in pts_all)
    ax0, ay0, ax1, ay1 = F.area
    ox = ax0 + 900 + ((ax1 - ax0 - 1000) - (X1 - X0) * PX_M) / 2
    oy = ay1 - 60 - ((ay1 - ay0 - 120) - (Y1 - Y0) * PX_M) / 2

    def T(x, y):
        return (ox + (x - X0) * PX_M, oy - (y - Y0) * PX_M)
    cob = (D["mats"].get("cobertura") or "")
    plana = D["plano"]
    dr.polygon([T(*p) for p in cont], fill=(205, 202, 194) if plana else (190, 110, 80), outline=INK)
    if plana:
        # platibanda (0,20 m) — contorno interior
        def offset(P, d):
            out = []
            n = len(P)
            for i in range(n):
                p0, p1, p2 = P[i - 1], P[i], P[(i + 1) % n]
                def nrm(a, b):
                    L = math.hypot(b[0] - a[0], b[1] - a[1])
                    return (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)
                n1, n2 = nrm(p0, p1), nrm(p1, p2)
                bx, by = n1[0] + n2[0], n1[1] + n2[1]
                k = d / max(1e-6, (bx * n1[0] + by * n1[1]))
                out.append((p1[0] + bx * k, p1[1] + by * k))
            return out
        inner = offset(cont, 0.20)
        dr.polygon([T(*p) for p in inner], fill=(214, 211, 203), outline=INK)
        # pendentes 2 % para os tubos de queda nos cantos exteriores
        cx = sum(p[0] for p in inner) / len(inner)
        cy = sum(p[1] for p in inner) / len(inner)
        for p in inner:
            if _dentro(((p[0] + cx) / 2, (p[1] + cy) / 2), cont):
                q = (p[0] + (cx - p[0]) * 0.12, p[1] + (cy - p[1]) * 0.12)
                s = (p[0] + (cx - p[0]) * 0.45, p[1] + (cy - p[1]) * 0.45)
                dr.line([T(*s), T(*q)], fill=INK, width=2)
                V._arrow_head(dr, T(*q), T(*s), INK, size=10)
                tq = T(p[0] + (cx - p[0]) * 0.05, p[1] + (cy - p[1]) * 0.05)
                dr.ellipse([tq[0] - 9, tq[1] - 9, tq[0] + 9, tq[1] + 9], outline=INK, width=2)
                mx, my = T(*s)
                dr.text((mx + 6, my - 20), "i = 2 %", fill=INK, font=V._font(15))
    for x in D["anexos"]:
        P = [tuple(p) for p in x["pts"]]
        dr.polygon([T(*p) for p in P], fill=(205, 202, 194), outline=INK)
        cx_, cy_ = T(sum(p[0] for p in P) / 4, sum(p[1] for p in P) / 4)
        dr.text((cx_ - 70, cy_ - 10), "Garagem — cob. plana i = 2 %", fill=INK, font=V._font(14))
    lx, ly = ax0 + 10, ay1 - 260
    txt = ["Cobertura plana invertida, não acessível (exceto manutenção):",
           "  laje de betão armado + betonilha de forma (i ≥ 2 %) + impermeabilização",
           "  + isolamento térmico XPS + geotêxtil + seixo rolado" if "seixo" in cob else "  + isolamento térmico XPS + acabamento",
           f"Platibanda 0,20 m de espessura até à cota +{V.fmt(D['h_top'], 2)} m; rufo metálico de capeamento",
           "Tubos de queda Ø 90 mm (indicados ◯) ligados à rede de águas pluviais"] if plana else \
          [f"Cobertura inclinada em telha cerâmica — altura total +{V.fmt(D['hh']['altura_total_m'], 2)} m"]
    for k, t in enumerate(txt):
        dr.text((lx, ly + k * 28), t, fill=INK, font=V._font(17))
    F.escala_grafica(ax0 + 10, ay1 - 30)
    return F.png()


# ------------------------------------------------------------------ alçados
_VISTAS = {"frente": ((0, -1), lambda x, y: x), "tardoz": ((0, 1), lambda x, y: -x),
           "esquerda": ((-1, 0), lambda x, y: -y), "direita": ((1, 0), lambda x, y: y)}
_NOMES = {"frente": "Alçado principal", "tardoz": "Alçado de tardoz", "esquerda": "Alçado lateral esquerdo",
          "direita": "Alçado lateral direito"}


def _textura(dr, box, mat, s):
    x0, y0, x1, y1 = box
    dr.rectangle(box, fill=MAT_COR.get(mat, (230, 230, 230)), outline=INK, width=2)
    if mat in ("granito", "xisto"):
        h = 0.40 * s
        row = 0
        y = y1
        while y > y0 + 1:
            yy = max(y0, y - h)
            dr.line([x0, yy, x1, yy], fill=(150, 146, 138), width=1)
            off = (row % 2) * 0.45 * s
            x = x0 + off
            while x < x1:
                dr.line([x, yy, x, y], fill=(150, 146, 138), width=1)
                x += 0.9 * s
            y -= h
            row += 1
    elif mat == "madeira":
        x = x0
        while x < x1:
            dr.line([x, y0, x, y1], fill=(120, 82, 50), width=2)
            x += 0.12 * s


def _alcado(dr, D, vista, ox, base_y, s=PX_M) -> Tuple[float, float]:
    n, U = _VISTAS[vista]
    faces = []
    for a, b, anexo in _arestas(D):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L
        if nx * n[0] + ny * n[1] < 0.7:
            continue
        prof = ((a[0] + b[0]) / 2) * n[0] + ((a[1] + b[1]) / 2) * n[1]
        h = (3.0 if anexo else D["h_top"])
        for x in D["anexos"]:
            if anexo and x.get("h_m"):
                h = float(x["h_m"])
        faces.append((prof, a, b, anexo, h))
    if not faces:
        return 0, 0
    us = [U(*p) for _, a, b, _, _ in faces for p in (a, b)]
    u0 = min(us)
    faces.sort(key=lambda t: t[0])           # primeiro as mais afastadas
    for prof, a, b, anexo, h in faces:
        ua, ub = sorted((U(*a), U(*b)))
        box = (ox + (ua - u0) * s, base_y - h * s, ox + (ub - u0) * s, base_y)
        mat = _material(D, a, b, anexo)
        _textura(dr, box, mat, s)
        if not anexo and D["plano"]:
            yl = base_y - D["h_laje"] * s
            dr.line([box[0], yl, box[2], yl], fill=(90, 90, 90), width=1)
            dr.rectangle([box[0], box[1], box[2], box[1] + 6], fill=(80, 80, 80))   # rufo da platibanda
        if anexo:
            lp = min(5.0, ub - ua - 1.2)
            if vista == "frente" or (abs(a[1] - b[1]) < 1e-6 and n[1] < 0):
                pm = (box[0] + box[2]) / 2
                dr.rectangle([pm - lp * s / 2, base_y - 2.4 * s, pm + lp * s / 2, base_y], fill=(70, 70, 72), outline=INK, width=2)
                for k in range(1, 8):
                    yy = base_y - 2.4 * s * k / 8
                    dr.line([pm - lp * s / 2, yy, pm + lp * s / 2, yy], fill=(110, 110, 112), width=1)
        # vãos desta face
        eixo_x = abs(a[1] - b[1]) < 1e-6
        plano = a[1] if eixo_x else a[0]
        for v in D["vaos"]:
            if anexo or v.get("plano_m") is None:
                continue
            dz = int(v.get("piso", 0)) * float(D["hh"]["storey_h_m"])
            ve = v.get("eixo", "x" if v["fachada"] in ("frente", "tardoz") else "y") == "x"
            if ve != eixo_x or abs(float(v["plano_m"]) - plano) > 0.05:
                continue
            lo, hi = (min(a[0], b[0]), max(a[0], b[0])) if eixo_x else (min(a[1], b[1]), max(a[1], b[1]))
            if float(v["x1"]) < lo - 0.01 or float(v["x0"]) > hi + 0.01:
                continue
            p0 = (float(v["x0"]), plano) if eixo_x else (plano, float(v["x0"]))
            p1 = (float(v["x1"]), plano) if eixo_x else (plano, float(v["x1"]))
            va, vb = sorted((U(*p0), U(*p1)))
            bx = (ox + (va - u0) * s, base_y - (float(v["z1"]) + dz) * s, ox + (vb - u0) * s, base_y - (float(v["z0"]) + dz) * s)
            if v["tipo"] == "porta":
                dr.rectangle(bx, fill=(96, 70, 48), outline=(40, 40, 40), width=3)
                dr.line([bx[2] - 0.15 * s, (bx[1] + bx[3]) / 2, bx[2] - 0.15 * s, (bx[1] + bx[3]) / 2 + 0.3 * s], fill=(220, 220, 220), width=3)
            else:
                dr.rectangle(bx, fill=VIDRO, outline=(45, 45, 48), width=4)
                partes = max(1, round((vb - va) / 1.2))
                for k in range(1, partes):
                    xx = bx[0] + (bx[2] - bx[0]) * k / partes
                    dr.line([xx, bx[1], xx, bx[3]], fill=(45, 45, 48), width=3)
                dr.line([bx[0] + 4, bx[1] + 8, bx[0] + (bx[2] - bx[0]) * 0.3, bx[1] + (bx[3] - bx[1]) * 0.5], fill="white", width=1)
    larg = (max(us) - u0) * s
    dr.line([ox - 1.5 * s, base_y, ox + larg + 1.5 * s, base_y], fill=INK, width=4)
    return larg, max(f[4] for f in faces) * s


def alcados(processo: Dict[str, Any]) -> List[Dict[str, Any]]:
    D = _dados(processo)
    out = []
    for par in (("frente", "tardoz"), ("esquerda", "direita")):
        F = Folha(f"{_NOMES[par[0]]} e {_NOMES[par[1]].lower()}", D, " / ".join(_NOMES[v] for v in par))
        dr = F.dr
        ax0, ay0, ax1, ay1 = F.area
        for k, v in enumerate(par):
            base = ay0 + 330 + k * 560
            larg, alt = _alcado(dr, D, v, ax0 + 260, base)
            dr.text((ax0 + 260, base + 26), _NOMES[v], fill=INK, font=V._font(24))
            xr = ax0 + 260 + larg + 60
            _cota_nivel(dr, xr + 40, base, "±0,00")
            _cota_nivel(dr, xr + 40, base - D["h_laje"] * PX_M, f"+{V.fmt(D['h_laje'], 2)} (laje)")
            if D["h_top"] > D["h_laje"] + 0.01:
                _cota_nivel(dr, xr + 40, base - D["h_top"] * PX_M, f"+{V.fmt(D['h_top'], 2)} (platibanda)")
            _cota_v(dr, ax0 + 200, base - D["h_top"] * PX_M, base, f"{V.fmt(D['h_top'], 2)} m")
        # legenda de materiais
        usados = sorted({_material(D, a, b, an) for a, b, an in _arestas(D)})
        lx, ly = ax0 + 700, ay1 - 210
        dr.text((lx, ly), "Revestimentos:", fill=INK, font=V._font(18))
        for k, m in enumerate(usados):
            _textura(dr, (lx, ly + 34 + k * 40, lx + 70, ly + 64 + k * 40), m, PX_M)
            dr.text((lx + 86, ly + 38 + k * 40), MAT_NOME.get(m, m), fill=INK, font=V._font(17))
        cx = (D["mats"].get("caixilharia") or "").replace("_", " ")
        dr.text((lx, ly + 44 + len(usados) * 40), f"Caixilharia: {cx or 'a definir'}, vidro duplo", fill=INK, font=V._font(17))
        F.escala_grafica(ax0 + 10, ay1 - 30)
        out.append({"code": "ALCADOS", "title": F.dr and " e ".join(_NOMES[v] for v in par),
                    "filename": f"alcados_{par[0]}_{par[1]}.png", "png": F.png()})
    return out


# ------------------------------------------------------------------ cortes
def _corte(dr, D, comps, eixo, pos, ox, base_y, s=PX_M):
    """eixo 'y': plano y = pos, abcissa x; eixo 'x': plano x = pos, abcissa y."""
    cont = D["cont"]
    # troços dentro da casa
    pts = []
    for i in range(len(cont)):
        a, b = cont[i], cont[(i + 1) % len(cont)]
        if eixo == "y" and abs(a[0] - b[0]) < 1e-6 and min(a[1], b[1]) < pos < max(a[1], b[1]):
            pts.append(a[0])
        if eixo == "x" and abs(a[1] - b[1]) < 1e-6 and min(a[0], b[0]) < pos < max(a[0], b[0]):
            pts.append(a[1])
    pts.sort()
    if len(pts) < 2:
        return 0
    u0, u1 = pts[0], pts[-1]
    X = lambda u: ox + (u - u0) * s
    hl, ht = D["h_laje"], D["h_top"]
    # terreno + fundações
    dr.rectangle([X(u0) - 2.0 * s, base_y + 0.02 * s, X(u1) + 2.0 * s, base_y + 1.0 * s], fill=(222, 214, 196))
    for k in range(0, int((u1 - u0 + 4) * 3)):
        x = X(u0) - 2.0 * s + k * s / 3
        dr.line([x, base_y + 1.0 * s, x + 0.3 * s, base_y + 0.7 * s], fill=(190, 180, 160), width=1)
    dr.rectangle([X(u0), base_y - 0.0, X(u1), base_y + 0.25 * s], fill=(150, 150, 150), outline=INK)    # laje térrea + caixa de brita
    # paredes cortadas: exteriores nos troços, interiores nas fronteiras de compartimentos atravessados
    cortados = [c for c in comps if (c["y0"] < pos < c["y1"] if eixo == "y" else c["x0"] < pos < c["x1"])]
    fronteiras = sorted({round(c[k], 3) for c in cortados for k in (("x0", "x1") if eixo == "y" else ("y0", "y1"))})
    for k in range(0, len(pts), 2):
        a, b = pts[k], pts[k + 1] if k + 1 < len(pts) else pts[k]
        for u, d in ((a, 1), (b, -1)):
            x0 = X(u) if d > 0 else X(u) - P_EXT * s
            dr.rectangle([x0, base_y - ht * s, x0 + P_EXT * s, base_y], fill=POCHE)
            dr.rectangle([x0 - 0.15 * s, base_y + 0.25 * s, x0 + P_EXT * s + 0.15 * s, base_y + 0.85 * s], fill=(120, 120, 120))  # sapata
    for u in fronteiras:
        if any(abs(u - p) < 0.05 for p in pts):
            continue
        aberto = all(c["tipo"] in NAO_PORTA for c in cortados if abs((c["x0"] if eixo == "y" else c["y0"]) - u) < 1e-3
                     or abs((c["x1"] if eixo == "y" else c["y1"]) - u) < 1e-3)
        if aberto:
            continue
        dr.rectangle([X(u) - P_INT / 2 * s, base_y - (hl - 0.30) * s, X(u) + P_INT / 2 * s, base_y], fill=POCHE)
    # laje de cobertura, isolamento, platibanda
    dr.rectangle([X(u0), base_y - hl * s, X(u1), base_y - (hl - 0.30) * s], fill=(110, 110, 110), outline=INK)
    dr.rectangle([X(u0) + P_EXT * s, base_y - (hl + 0.12) * s, X(u1) - P_EXT * s, base_y - hl * s], fill=(232, 210, 120))
    dr.rectangle([X(u0) + P_EXT * s, base_y - (hl + 0.18) * s, X(u1) - P_EXT * s, base_y - (hl + 0.12) * s], fill=(170, 165, 150))
    # vãos cortados nas paredes exteriores
    for v in D["vaos"]:
        if v.get("plano_m") is None:
            continue
        ve = v.get("eixo", "x" if v["fachada"] in ("frente", "tardoz") else "y") == "x"
        if (eixo == "y" and ve) or (eixo == "x" and not ve):
            continue
        if float(v["x0"]) < pos < float(v["x1"]):
            u = float(v["plano_m"])
            d = 1 if abs(u - u0) < abs(u - u1) else -1
            x0 = X(u) if d > 0 else X(u) - P_EXT * s
            dr.rectangle([x0, base_y - float(v["z1"]) * s, x0 + P_EXT * s, base_y - float(v["z0"]) * s], fill="white", outline=INK)
            dr.line([x0 + P_EXT * s / 2, base_y - float(v["z1"]) * s, x0 + P_EXT * s / 2, base_y - float(v["z0"]) * s], fill=(60, 110, 160), width=3)
    # nomes dos compartimentos e pé-direito
    for c in cortados:
        a_, b_ = (c["x0"], c["x1"]) if eixo == "y" else (c["y0"], c["y1"])
        if b_ - a_ < 0.9:
            continue
        nome = c["nome"].replace("Instalação sanitária", "I.S.").replace("Corredor dos quartos", "Corredor")
        f = V._font(16)
        w = dr.textlength(nome, font=f)
        dr.text(((X(a_) + X(b_)) / 2 - w / 2, base_y - 1.6 * s), nome, fill=INK, font=f)
    larg_pd = next(((c["x0"], c["x1"]) if eixo == "y" else (c["y0"], c["y1"]) for c in cortados if c["tipo"] in ("sala", "quarto")), None)
    if larg_pd:
        xm = X(larg_pd[0]) + 0.6 * s
        _cota_v(dr, xm, base_y - (hl - 0.30) * s, base_y, f"p.d. {V.fmt(D['pd'], 2)} m")
    xr = X(u1) + 2.4 * s
    _cota_nivel(dr, xr, base_y, "±0,00 soleira")
    _cota_nivel(dr, xr, base_y - hl * s, f"+{V.fmt(hl, 2)}")
    _cota_nivel(dr, xr, base_y - ht * s, f"+{V.fmt(ht, 2)}")
    _cota_h(dr, X(u0), X(u1), base_y + 1.5 * s, f"{V.fmt(u1 - u0, 2)} m")
    return (u1 - u0) * s


def cortes(processo: Dict[str, Any]) -> Dict[str, Any]:
    D = _dados(processo)
    comps = (D["pisos"][0] if D["pisos"] else {}).get("compartimentos") or []
    A_y, B_x = _linhas_corte(D)
    F = Folha("Cortes A-A e B-B", D, "Cortes transversal A-A e longitudinal B-B")
    dr = F.dr
    ax0, ay0, ax1, ay1 = F.area
    _corte(dr, D, comps, "y", A_y, ax0 + 200, ay0 + 360)
    dr.text((ax0 + 200, ay0 + 360 + 2.0 * PX_M), "Corte A-A (transversal)", fill=INK, font=V._font(24))
    _corte(dr, D, comps, "x", B_x, ax0 + 200, ay0 + 900)
    dr.text((ax0 + 200, ay0 + 900 + 2.0 * PX_M), "Corte B-B (longitudinal)", fill=INK, font=V._font(24))
    lx, ly = ax0 + 700, ay1 - 170
    for k, t in enumerate(["Laje de cobertura em betão armado 0,30 m (incl. revestimentos)", "Isolamento térmico XPS + seixo",
                           "Paredes exteriores 0,30 m · interiores 0,12 m", "Laje térrea sobre caixa de brita e isolamento",
                           "Fundações diretas (sapatas) — a dimensionar no projeto de estabilidade"]):
        dr.text((lx, ly + k * 28), "• " + t, fill=INK, font=V._font(16))
    F.escala_grafica(ax0 + 10, ay1 - 30)
    return {"code": "CORTES", "title": "Cortes A-A e B-B", "filename": "cortes_AA_BB.png", "png": F.png()}


def pecas(processo: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Todas as peças de arquitetura à escala, pela ordem do processo."""
    D = _dados(processo)
    out = []
    for p in D["pisos"]:
        k = int(p.get("piso", 0))
        out.append({"code": "PLANTAS_PISOS", "title": f"Planta do {('rés-do-chão' if k == 0 else f'{k}.º andar')} (1:100)",
                    "filename": f"planta_piso_{k}.png", "png": planta_piso(processo, k)})
    out.append({"code": "PLANTA_COBERTURA", "title": "Planta de cobertura (1:100)", "filename": "planta_cobertura.png",
                "png": planta_cobertura(processo)})
    out += alcados(processo)
    out.append(cortes(processo))
    if (D["vol"].get("piscina") or {}).get("l_m"):
        out.append({"code": "PISCINA", "title": "Piscina — planta e corte (1:50)", "filename": "piscina_planta_corte.png",
                    "png": piscina(processo)})
    for x in out:
        x["folha"] = True
    return out


# ------------------------------------------------------------------ piscina
def piscina(processo: Dict[str, Any]) -> bytes:
    """Piscina à escala 1:50: planta (tanque, cais/lajeado, escada, skimmers, afastamentos à casa e aos limites)
    e corte longitudinal (profundidade, laje de fundo, paredes de betão, cais)."""
    D = _dados(processo)
    pi = D["vol"]["piscina"]
    x, y, L, W = (float(pi[k]) for k in ("x_m", "y_m", "l_m", "w_m"))
    prof = float(pi.get("profundidade_m") or 1.5)
    F = Folha("Piscina — planta e corte", D, "Piscina: planta e corte longitudinal", escala="1:50")
    dr = F.dr
    s = PX_M * 2
    ax0, ay0, ax1, ay1 = F.area
    cais = 1.2
    # planta
    ox, oy = ax0 + 200, ay0 + 120 + (W + 2 * cais) * s
    def T(u, v):
        return (ox + (u - (x - cais)) * s, oy - (v - (y - cais)) * s)
    a, b = T(x - cais, y + W + cais), T(x + L + cais, y - cais)
    dr.rectangle([a[0], a[1], b[0], b[1]], fill=MAT_COR["granito"], outline=INK, width=2)
    k = x - cais
    while k < x + L + cais:
        dr.line([T(k, y - cais), T(k, y + W + cais)], fill=(160, 156, 148), width=1)
        k += 0.6
    a, b = T(x, y + W), T(x + L, y)
    dr.rectangle([a[0], a[1], b[0], b[1]], fill=(120, 190, 225), outline=INK, width=4)
    for j in range(4):   # escada de acesso no topo
        aa, bb = T(x + 0.1, y + 0.4 + j * 0.3), T(x + 1.1, y + 0.4 + j * 0.3)
        dr.line([aa, bb], fill=INK, width=2)
    for u in (x + L * 0.3, x + L * 0.7):    # skimmers e bocais
        c = T(u, y + W)
        dr.rectangle([c[0] - 12, c[1] - 8, c[0] + 12, c[1] + 8], fill="white", outline=INK)
    dr.text(T(x + L / 2 - 1.6, y + W / 2 + 0.3), f"Tanque {V.fmt(L, 2)} × {V.fmt(W, 2)} m", fill=INK, font=V._font(22))
    dr.text(T(x + L / 2 - 1.6, y + W / 2 - 0.3), f"Plano de água {V.fmt(L * W, 2)} m²  ·  volume ≈ {V.fmt(L * W * prof, 1)} m³",
            fill=INK, font=V._font(18))
    _cota_h(dr, T(x, 0)[0], T(x + L, 0)[0], T(0, y - cais - 0.5)[1], f"{V.fmt(L, 2)} m")
    _cota_v(dr, T(x + L + cais + 0.5, 0)[0], T(0, y + W)[1], T(0, y)[1], f"{V.fmt(W, 2)} m")
    dr.text(T(x - cais, y + W + cais + 0.5), f"Cais / lajeado em granito antiderrapante, {V.fmt(cais, 2)} m de largura",
            fill=INK, font=V._font(18))
    # afastamentos à casa
    cx0 = min(p[0] for p in D["cont"])
    cy0 = min(p[1] for p in D["cont"])
    lx, ly = ax0 + 1500, ay0 + 40
    linhas = [f"Implantação (coordenadas do terreno): x = {V.fmt(x, 2)} m, y = {V.fmt(y, 2)} m",
              f"Distância à fachada principal da casa: {V.fmt(max(0.0, cy0 - (y + W)), 2)} m",
              f"Distância ao limite frontal: {V.fmt(y, 2)} m · ao limite lateral: {V.fmt(x, 2)} m",
              "Piscina descoberta, sem cobertura — não conta para a área de implantação",
              "Casa das máquinas enterrada junto ao tanque (filtração + bomba de calor)",
              "Vedação ou cobertura de segurança recomendada (segurança de crianças)",
              "Descarga para a rede pluvial / vala, conforme parecer municipal"]
    for k, t in enumerate(linhas):
        dr.text((lx, ly + k * 30), "• " + t, fill=INK, font=V._font(17))
    _ = cx0
    # corte longitudinal
    base = ay1 - 380
    X = lambda u: ax0 + 200 + (u - (x - cais)) * s
    dr.rectangle([X(x - cais) - 40, base, X(x + L + cais) + 40, base + (prof + 0.6) * s], fill=(222, 214, 196))
    dr.rectangle([X(x) - 0.25 * s, base, X(x + L) + 0.25 * s, base + (prof + 0.25) * s], fill=(150, 150, 150), outline=INK)
    dr.rectangle([X(x), base + 0.15 * s, X(x + L), base + prof * s], fill=(120, 190, 225))
    dr.rectangle([X(x), base, X(x + L), base + 0.15 * s], fill="white")
    dr.line([X(x), base + 0.15 * s, X(x + L), base + 0.15 * s], fill=(40, 90, 160), width=3)
    dr.rectangle([X(x - cais), base - 0.06 * s, X(x), base], fill=MAT_COR["granito"], outline=INK)
    dr.rectangle([X(x + L), base - 0.06 * s, X(x + L + cais), base], fill=MAT_COR["granito"], outline=INK)
    for j in range(4):
        yy = base + (0.3 + j * 0.3) * s
        dr.rectangle([X(x), yy, X(x) + (1.0 - j * 0.25) * s, yy + 0.3 * s], fill=(150, 150, 150), outline=INK)
    _cota_v(dr, X(x + L) + 0.25 * s + 40, base, base + prof * s, f"profundidade {V.fmt(prof, 2)} m")
    _cota_nivel(dr, X(x + L + cais) + 120, base, "±0,00 cais")
    dr.text((X(x), base + (prof + 0.7) * s), "Corte longitudinal — tanque em betão armado 0,25 m, impermeabilizado e revestido",
            fill=INK, font=V._font(20))
    F.escala_grafica(ax0 + 10, ay1 - 30, s)
    return F.png()
