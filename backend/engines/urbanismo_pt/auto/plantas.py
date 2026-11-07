"""Plantas dos pisos: distribuição dos compartimentos dentro da implantação e desenho esquemático cotado.

Duas faixas ao longo da frente: a faixa «sol» (sala, quartos) do lado da fachada mais bem exposta e a faixa «serviço»
(entrada, cozinha, instalações sanitárias, escada, circulação). A escada ocupa a mesma posição em todos os pisos.
Cada compartimento é verificado contra o mínimo do RGEU; nada é escondido: um compartimento abaixo do mínimo aparece
como «não conforme» e o processo não é dado como pronto.
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from engines.urbanismo_pt import volumes as V

PAREDE_EXT = 0.30
PAREDE_INT = 0.12
LARG_MIN = {"sala": 3.6, "quarto": 2.7, "cozinha": 2.4, "wc": 1.6, "wc_social": 1.2, "escada": 2.2, "entrada": 1.8,
            "lavandaria": 1.5, "circulacao": 1.1, "escritorio": 2.4}
ORDEM_SERVICO = ["lavandaria", "cozinha", "wc_social", "wc", "escada", "entrada", "circulacao", "quarto", "escritorio"]
ORDEM_SOL = ["escritorio", "quarto", "sala"]


FLEX = {"sala", "quarto", "circulacao", "escritorio"}   # absorvem a folga; os restantes mantêm a área de projeto


def _larguras(rooms: List[dict], span: float, d: float) -> Optional[List[float]]:
    """Larguras ao longo da faixa: compartimentos de serviço com a largura de projeto, os flexíveis absorvem a folga.
    None se nem com as larguras mínimas cabem."""
    if not rooms:
        return []
    alvo = [max(r["area_projeto_m2"] / max(d, 0.5), LARG_MIN.get(r["tipo"], 1.0)) for r in rooms]
    mins = [LARG_MIN.get(r["tipo"], 1.0) for r in rooms]
    if sum(mins) > span + 1e-6:
        return None
    fixos = [k for k, r in enumerate(rooms) if r["tipo"] not in FLEX]
    flex = [k for k, r in enumerate(rooms) if r["tipo"] in FLEX]
    w = list(alvo)
    if not flex:   # só serviços: escala proporcional, sem descer dos mínimos
        f = span / sum(alvo)
        w = [max(m, a * f) for a, m in zip(alvo, mins)]
    else:
        livre = span - sum(alvo[k] for k in fixos)
        soma_flex = sum(alvo[k] for k in flex)
        if livre >= sum(mins[k] for k in flex):
            for k in flex:
                w[k] = max(mins[k], livre * alvo[k] / soma_flex)
        else:   # comprime os fixos até ao mínimo
            for k in flex:
                w[k] = mins[k]
            falta = span - sum(mins[k] for k in flex)
            soma_fix = sum(alvo[k] for k in fixos) or 1.0
            for k in fixos:
                w[k] = max(mins[k], falta * alvo[k] / soma_fix)
    f = span / sum(w)            # acerto final para fechar exatamente a faixa
    return [x * f for x in w]


def _row(rooms: List[dict], x0: float, x1: float, y0: float, y1: float, fixa: Optional[Tuple[float, float]] = None) -> Optional[List[dict]]:
    """Distribui os compartimentos ao longo de [x0, x1]; com `fixa`, a escada fica nessa posição (igual em todos os pisos)."""
    d = y1 - y0
    if not rooms:
        return [{"nome": "Circulação", "tipo": "circulacao", "area_projeto_m2": (x1 - x0) * d, "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                 "minimo_m2": None}]
    if fixa:
        esc = [r for r in rooms if r["tipo"] == "escada"]
        resto = [r for r in rooms if r["tipo"] != "escada"]
        alvo_esq = (fixa[0] - x0) * d
        esq, acc = [], 0.0
        for r in resto:   # enche o lado esquerdo pela ordem, até à área disponível
            if acc + r["area_projeto_m2"] / 2 <= alvo_esq:
                esq.append(r)
                acc += r["area_projeto_m2"]
        dirt = [r for r in resto if r not in esq]
        a = _row(esq, x0, fixa[0], y0, y1) if fixa[0] - x0 > 0.3 else []
        b = _row(dirt, fixa[1], x1, y0, y1) if x1 - fixa[1] > 0.3 else ([] if not dirt else None)
        if a is None or b is None:
            return None
        return a + ([{**esc[0], "x0": fixa[0], "x1": fixa[1], "y0": y0, "y1": y1}] if esc else []) + b
    w = _larguras(rooms, x1 - x0, d)
    if w is None:
        return None
    out, x = [], x0
    for r, wi in zip(rooms, w):
        out.append({**r, "x0": x, "x1": x + wi, "y0": y0, "y1": y1})
        x += wi
    out[-1]["x1"] = x1
    return out


def distribuir(volume: dict, prog: dict, fachada_sol: str, lado_garagem: str) -> Dict[str, Any]:
    polys = [p for p in V.building_polygons(volume) if not p["annexe"]]
    x0, y0, x1, y1 = V.bbox(polys)
    W = y1 - y0
    pisos = []
    escada_x = None
    for piso in range(int(volume.get("levels") or 1)):
        rs = [dict(r) for r in prog["compartimentos"] if r["piso"] == piso]
        # a entrada fica sempre na faixa da frente
        for r in rs:
            if r["tipo"] == "entrada":
                r["fila"] = "sol" if fachada_sol == "frente" else "servico"
        sol = [r for r in rs if r["fila"] == "sol"]
        srv = [r for r in rs if r["fila"] != "sol"]
        s_sol = sum(r["area_projeto_m2"] for r in sol) or 1.0
        s_srv = sum(r["area_projeto_m2"] for r in srv) or 1.0
        d_sol = max(3.8, min(W - 2.6, W * s_sol / (s_sol + s_srv)))
        key = {t: i for i, t in enumerate(ORDEM_SERVICO)}
        srv.sort(key=lambda r: key.get(r["tipo"], 99))
        ks = {t: i for i, t in enumerate(ORDEM_SOL)}
        sol.sort(key=lambda r: ks.get(r["tipo"], 99))
        if lado_garagem == "direita":     # serviços do lado da garagem
            srv.reverse()
            sol.reverse()
        if fachada_sol == "tardoz":
            ys_sol, ys_srv = (y1 - d_sol, y1), (y0, y1 - d_sol)
        else:
            ys_sol, ys_srv = (y0, y0 + d_sol), (y0 + d_sol, y1)
        row_srv = _row(srv, x0, x1, *ys_srv, fixa=escada_x if any(r["tipo"] == "escada" for r in srv) else None)
        row_sol = _row(sol, x0, x1, *ys_sol)
        if row_srv is None or row_sol is None:
            return {"ok": False, "motivo": f"Os compartimentos do {('rés-do-chão' if piso == 0 else str(piso) + '.º andar')} "
                                           "não cabem com as larguras mínimas nesta implantação."}
        if escada_x is None:
            for r in row_srv:
                if r["tipo"] == "escada":
                    escada_x = (r["x0"], r["x1"])
        comp = []
        for r in row_sol + row_srv:
            w, d = r["x1"] - r["x0"], r["y1"] - r["y0"]
            util = max(0.0, (w - PAREDE_INT) * (d - PAREDE_INT))
            minimo = r.get("minimo_m2")
            lm = LARG_MIN.get(r["tipo"], 1.0)
            comp.append({"nome": r["nome"], "tipo": r["tipo"], "x0": round(r["x0"], 3), "y0": round(r["y0"], 3),
                         "x1": round(r["x1"], 3), "y1": round(r["y1"], 3), "largura_m": round(min(w, d), 2),
                         "area_m2": round(w * d, 2), "area_util_m2": round(util, 2), "minimo_m2": minimo,
                         "conforme": (minimo is None or util >= minimo - 1e-6) and min(w, d) >= lm - 1e-6})
        pisos.append({"piso": piso, "nome": "Rés-do-chão" if piso == 0 else f"{piso}.º andar", "compartimentos": comp})
    nao = [f"{c['nome']} ({p['nome']}): {c['area_util_m2']:.1f} m²" + (f" < {c['minimo_m2']:.1f} m²" if c["minimo_m2"] else "")
           for p in pisos for c in p["compartimentos"] if not c["conforme"]]
    return {"ok": True, "pisos": pisos, "nao_conformes": nao, "casa_rect": (x0, y0, x1, y1)}


# ------------------------------------------------------------------ desenho
_CURTO = {"lavandaria": "Lav.", "circulacao": "Circ.", "entrada": "Entrada", "wc_social": "I.S.", "wc": "I.S.",
          "escada": "Escada", "cozinha": "Cozinha", "escritorio": "Escrit.", "quarto": "Quarto", "sala": "Sala"}
_COR = {"sala": (232, 242, 236), "quarto": (238, 240, 250), "cozinha": (252, 244, 226), "wc": (226, 240, 248),
        "wc_social": (226, 240, 248), "escada": (236, 236, 236), "entrada": (246, 246, 240), "lavandaria": (240, 236, 246),
        "circulacao": (250, 250, 250), "escritorio": (244, 238, 230)}


def desenho_planta(plan: Dict[str, Any], piso: int, azimute_tardoz: Optional[float] = None, titulo: str = "") -> bytes:
    p = plan["pisos"][piso]
    x0, y0, x1, y1 = plan["casa_rect"]
    Wimg, Himg = 1600, 1130
    margem = 150
    s = min((Wimg - 2 * margem) / (x1 - x0), (Himg - 2 * margem - 60) / (y1 - y0))
    ox = (Wimg - (x1 - x0) * s) / 2
    oy = (Himg + (y1 - y0) * s) / 2 + 10

    def P(x, y):  # y (tardoz) para cima no desenho
        return ox + (x - x0) * s, oy - (y - y0) * s

    img = Image.new("RGB", (Wimg, Himg), "white")
    dr = ImageDraw.Draw(img)
    V._header(dr, Wimg, titulo or f"Planta do {p['nome'].lower()} — esquema de distribuição")
    f_nome, f_area = V._font(19), V._font(16)
    for c in p["compartimentos"]:
        a, b = P(c["x0"], c["y1"]), P(c["x1"], c["y0"])
        dr.rectangle([a, b], fill=_COR.get(c["tipo"], (245, 245, 245)), outline=V.INK, width=max(2, int(PAREDE_INT * s / 2)))
        if c["tipo"] == "escada":
            n = 12
            for k in range(1, n):
                xx = a[0] + (b[0] - a[0]) * k / n
                dr.line([(xx, a[1] + 6), (xx, b[1] - 6)], fill=V.GREY, width=1)
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        col = V.INK if c["conforme"] else V.RED
        largura_px = (b[0] - a[0]) - 14
        nome, fn = c["nome"], f_nome
        for cand, sz in ((c["nome"], 19), (c["nome"], 15), (_CURTO.get(c["tipo"], c["nome"]), 15), (_CURTO.get(c["tipo"], c["nome"]), 12)):
            fn = V._font(sz)
            if dr.textlength(cand, font=fn) <= largura_px:
                nome = cand
                break
            nome = cand
        dr.text((cx, cy - 12), nome, fill=col, font=fn, anchor="mm")
        dr.text((cx, cy + 12), f"{V.fmt(c['area_util_m2'], 1)} m²", fill=col, font=f_area, anchor="mm")
    a, b = P(x0, y1), P(x1, y0)
    dr.rectangle([a, b], outline=V.INK, width=max(4, int(PAREDE_EXT * s * 0.6)))
    # cotas parciais (largura de cada compartimento, nas duas faixas) e cotas gerais
    fc = V._font(15)
    ymid = (y0 + y1) / 2
    for faixa, yy in (([c for c in p["compartimentos"] if c["y0"] < ymid - 0.01], b[1] + 28),
                      ([c for c in p["compartimentos"] if c["y0"] >= ymid - 0.01], a[1] - 28)):
        for c in faixa:
            pa, pb = P(c["x0"], 0)[0], P(c["x1"], 0)[0]
            dr.line([(pa, yy), (pb, yy)], fill=V.GREY, width=1)
            for xx in (pa, pb):
                dr.line([(xx, yy - 6), (xx, yy + 6)], fill=V.GREY, width=1)
            if pb - pa > 34:
                dr.text(((pa + pb) / 2, yy - 10), V.fmt(c["x1"] - c["x0"]), fill=V.GREY, font=fc, anchor="mm")
    yb = b[1] + 70
    dr.line([(a[0], yb), (b[0], yb)], fill=V.RED, width=2)
    for xx in (a[0], b[0]):
        dr.line([(xx, yb - 8), (xx, yb + 8)], fill=V.RED, width=2)
    dr.text(((a[0] + b[0]) / 2, yb + 16), f"{V.fmt(x1 - x0)} m", fill=V.RED, font=V._font(20), anchor="mm")
    xb = b[0] + 60
    dr.line([(xb, a[1]), (xb, b[1])], fill=V.RED, width=2)
    for yy in (a[1], b[1]):
        dr.line([(xb - 8, yy), (xb + 8, yy)], fill=V.RED, width=2)
    dr.text((xb + 14, (a[1] + b[1]) / 2), f"{V.fmt(y1 - y0)} m", fill=V.RED, font=V._font(20), anchor="lm")
    dr.text((a[0], yb + 40), "FRENTE (via pública)", fill=V.GREY, font=V._font(16))
    if azimute_tardoz is not None:
        _norte(dr, Wimg - 110, 140, azimute_tardoz)
    V._footer(dr, Wimg, Himg, "Áreas úteis aproximadas (eixo das paredes interiores descontado). A vermelho: abaixo do mínimo.")
    return V._png(img)


def _norte(dr, cx, cy, az_tardoz):
    """Seta do norte num desenho em que «para cima» = tardoz (azimute az_tardoz)."""
    ang = math.radians(-az_tardoz)   # rotação do norte relativamente ao «cima» do desenho
    L = 45
    tip = (cx + L * math.sin(ang), cy - L * math.cos(ang))
    tail = (cx - L * math.sin(ang), cy + L * math.cos(ang))
    dr.line([tail, tip], fill=V.INK, width=3)
    V._arrow_head(dr, tip, tail, V.INK, size=12)
    dr.text((tip[0] + 10 * math.sin(ang), tip[1] - 22 * math.cos(ang)), "N", fill=V.INK, font=V._font(22), anchor="mm")
