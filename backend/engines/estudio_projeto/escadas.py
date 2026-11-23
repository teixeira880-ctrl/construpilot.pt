"""Escadas do modelo único: reta, em L (quarto de volta com patamar) e em U (meia volta com patamar).

A altura a vencer é a real entre os dois pavimentos (pé-direito + laje de cima). O número de espelhos é o menor que
mantém o espelho ≤ 18,5 cm; o cobertor é o escolhido pelo utilizador. O último espelho chega ao pavimento de cima,
por isso há sempre um cobertor a menos do que espelhos (o patamar conta como um cobertor).

Referencial local: origem a meio do primeiro espelho, subida segundo +y, largura segundo x. `rot` roda este referencial
no terreno (0° = sobe para o tardoz). «sentido» diz para que lado vira o segundo lanço (dir = +x local).

O vazio na laje de cima cobre os degraus e patamares que ficam a menos de 2,00 m da face inferior dessa laje
(pé-direito livre sobre a escada): é uma regra de projeto assumida, escrita aqui e mostrada nos avisos.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import Polygon
from shapely.ops import unary_union

ESPELHO_MAX = 0.185
LIVRE_SOBRE_ESCADA = 2.00
POCO = 0.10                     # folga entre os dois lanços de uma escada em U
R = lambda v, n=3: round(float(v), n)  # noqa: E731


def espelhos(H: float) -> Tuple[int, float]:
    n = max(2, math.ceil(H / ESPELHO_MAX - 1e-9))
    return n, H / n


def _ret(x0, y0, x1, y1):
    return [(min(x0, x1), min(y0, y1)), (max(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1)), (min(x0, x1), max(y0, y1))]


def geometria_local(tipo: str, n: int, c: float, w: float, sentido: str) -> Dict[str, Any]:
    """Degraus e patamares no referencial local: [(retângulo, índice do espelho que lhe dá a cota)] e linha de marcha."""
    s = 1.0 if sentido != "esq" else -1.0
    h = w / 2
    degraus, patamares, marcha = [], [], [(0.0, 0.0)]
    if tipo == "reta":
        for i in range(1, n):
            degraus.append((_ret(-h, (i - 1) * c, h, i * c), i))
        marcha.append((0.0, (n - 1) * c))
        return {"degraus": degraus, "patamares": patamares, "marcha": marcha}
    n1 = (n + 1) // 2                    # o primeiro lanço nunca é mais curto do que o segundo
    n2 = n - n1
    for i in range(1, n1):
        degraus.append((_ret(-h, (i - 1) * c, h, i * c), i))
    yl = (n1 - 1) * c
    if tipo == "l":
        patamares.append((_ret(-h, yl, h, yl + w), n1))
        for j in range(1, n2):
            degraus.append((_ret(s * (h + (j - 1) * c), yl, s * (h + j * c), yl + w), n1 + j))
        marcha += [(0.0, yl + h), (s * (h + (n2 - 1) * c), yl + h)]
    else:                                   # em U
        x2 = s * (h + POCO + h)             # eixo do segundo lanço
        patamares.append((_ret(-s * h, yl, s * (h + POCO + w), yl + w), n1))
        for j in range(1, n2):
            degraus.append((_ret(x2 - h, yl - j * c, x2 + h, yl - (j - 1) * c), n1 + j))
        marcha += [(0.0, yl + h), (x2, yl + h), (x2, yl - (n2 - 1) * c)]
    return {"degraus": degraus, "patamares": patamares, "marcha": marcha}


def _mundo(e: Dict[str, Any]):
    r = math.radians(e.get("rot") or 0.0)
    co, si = math.cos(r), math.sin(r)
    return lambda p: (e["x"] + p[0] * co - p[1] * si, e["y"] + p[0] * si + p[1] * co)


def derivar_escadas(m: Dict[str, Any], cz: List[Dict[str, float]], pegadas: List[Any], unioes: List[Any]):
    """Devolve (escadas derivadas, vazios por índice de piso de chegada, erros, avisos)."""
    out, erros, avisos = [], [], []
    vazios: Dict[int, List[Polygon]] = {}
    idx = {p["id"]: k for k, p in enumerate(m["pisos"])}
    for e in m.get("escadas") or []:
        k = idx[e["piso"]]
        if k + 1 >= len(m["pisos"]):
            erros.append({"codigo": "ESCADA_SEM_PISO", "id": e["id"], "msg": f"A escada {e['id']} está no último piso: não há piso acima para onde subir."})
            continue
        z0 = cz[k]["z0"]
        H = cz[k + 1]["z0"] - z0
        n, esp = espelhos(H)
        c, w = e["cobertor_m"], e["largura_m"]
        loc = geometria_local(e["tipo"], n, c, w, e.get("sentido") or "dir")
        W = _mundo(e)
        degraus = [{"pts": [[R(x), R(y)] for x, y in map(W, r)], "z": R(z0 + i * esp)} for r, i in loc["degraus"]]
        patamares = [{"pts": [[R(x), R(y)] for x, y in map(W, r)], "z": R(z0 + i * esp)} for r, i in loc["patamares"]]
        pecas = [Polygon(d["pts"]) for d in degraus + patamares]
        contorno = unary_union(pecas).buffer(1e-4).buffer(-1e-4)
        # vazio: tudo o que fica a menos de 2,00 m da face inferior da laje de cima
        limite = cz[k]["z1"] - LIVRE_SOBRE_ESCADA
        altos = [Polygon(d["pts"]) for d in degraus + patamares if d["z"] > limite + 1e-6]
        vazio = unary_union(altos).buffer(1e-4).buffer(-1e-4) if altos else None
        if vazio is not None and not vazio.is_empty:
            vazios.setdefault(k + 1, []).append(vazio)
        blondel = 2 * esp + c
        if not 0.60 <= blondel <= 0.65:
            avisos.append({"codigo": "ESCADA_PASSO", "id": e["id"],
                           "msg": f"Escada {e['id']}: 2 × espelho + cobertor = {blondel:.2f} m, fora do intervalo de conforto 0,60–0,65 m (regra de Blondel)."})
        peg = pegadas[k]
        if peg is not None and not peg.is_empty and contorno.difference(peg.buffer(0.01)).area > 0.01:
            avisos.append({"codigo": "ESCADA_FORA", "id": e["id"], "msg": f"Escada {e['id']}: parte da escada fica fora do contorno do piso."})
        if unioes[k] is not None and contorno.intersection(unioes[k]).area > 0.02:
            avisos.append({"codigo": "ESCADA_PAREDE", "id": e["id"], "msg": f"Escada {e['id']}: a escada atravessa uma parede."})
        marcha = [W(p) for p in loc["marcha"]]
        aneis = lambda g: [[[R(x), R(y)] for x, y in list(p.exterior.coords)[:-1]]  # noqa: E731
                           for p in ([g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))) if not p.is_empty]
        out.append({
            "id": e["id"], "piso": e["piso"], "tipo": e["tipo"], "z0": z0, "altura_m": R(H),
            "n_espelhos": n, "n_cobertores": len(degraus) + len(patamares), "espelho_m": R(esp, 4), "cobertor_m": c, "largura_m": w,
            "blondel_m": R(blondel), "degraus": degraus, "patamares": patamares,
            "contorno": aneis(contorno), "vazio": aneis(vazio) if vazio is not None and not vazio.is_empty else [],
            "marcha": [[R(x), R(y)] for x, y in marcha],
            "desenvolvimento_m": R(sum(math.hypot(marcha[i + 1][0] - marcha[i][0], marcha[i + 1][1] - marcha[i][1]) for i in range(len(marcha) - 1)), 2),
            "area_planta_m2": R(contorno.area, 2), "vazio_m2": R(vazio.area, 2) if vazio is not None and not vazio.is_empty else 0.0})
    return out, vazios, erros, avisos


def propor(rect: Tuple[float, float, float, float], H: float, folga: float = 0.06) -> Optional[Dict[str, Any]]:
    """Escada que cabe num compartimento retangular (x0, y0, x1, y1): em U se couber, senão reta. None se nenhuma couber.
    `folga` afasta a escada das faces das paredes (o retângulo é dado pelos eixos)."""
    x0, y0, x1, y1 = rect[0] + folga, rect[1] + folga, rect[2] - folga, rect[3] - folga
    lx, ly = x1 - x0, y1 - y0
    if lx <= 0 or ly <= 0:
        return None
    n, _ = espelhos(H)
    c = 0.25
    ao_longo_y = ly >= lx
    curto, longo = (lx, ly) if ao_longo_y else (ly, lx)
    n1 = (n + 1) // 2
    w = min(0.90, (curto - POCO) / 2)
    if w >= 0.75 and longo >= (n1 - 1) * c + w:
        if ao_longo_y:
            return {"tipo": "u", "x": x0 + w / 2, "y": y0, "rot": 0.0, "largura_m": R(w), "cobertor_m": c, "sentido": "dir"}
        return {"tipo": "u", "x": x0, "y": y1 - w / 2, "rot": 270.0, "largura_m": R(w), "cobertor_m": c, "sentido": "dir"}
    w = min(0.90, curto)
    if w >= 0.75 and longo >= (n - 1) * c:
        if ao_longo_y:
            return {"tipo": "reta", "x": x0 + w / 2, "y": y0, "rot": 0.0, "largura_m": R(w), "cobertor_m": c, "sentido": "dir"}
        return {"tipo": "reta", "x": x0, "y": y0 + w / 2, "rot": 270.0, "largura_m": R(w), "cobertor_m": c, "sentido": "dir"}
    return None
