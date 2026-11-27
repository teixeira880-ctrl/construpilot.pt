"""Edição do projeto por frase (escrita ou dita): «aumenta a sala 2 metros», «põe janelas maiores no quarto 2»,
«agrandis la cuisine de 1,5 m», «piscine de 10 x 5», «pavimento da suite em soalho de carvalho».

1) Frases correntes → ações determinísticas (PT / FR / EN), sem IA: o mesmo pedido dá sempre o mesmo resultado.
2) O que não for reconhecido pode ser lido pela IA (opcional), que só pode devolver operações da lista conhecida.
3) Cada ação é aplicada sobre o modelo único e só fica se o modelo continuar válido; tudo o resto (plantas, 3D,
   medições, IFC, DCE, verificação) segue automaticamente.

Ações próprias desta camada (as outras são as operações do Estúdio, engines/estudio_projeto/operacoes.py):
- esticar      : alarga uma divisão empurrando a parede de um lado; tudo o que está para lá desse lado (paredes,
                 vãos, objetos, escada, rótulos) desloca-se com ela, em todos os pisos — a casa cresce sem se partir.
- vaos_maiores : alarga as janelas/portas-janela exteriores de uma divisão (dentro do espaço livre da parede).
- objeto_medidas : muda as medidas de um objeto (ex.: piscina 10 × 5 m).
"""
from __future__ import annotations

import copy
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from engines import estudio_projeto as EP
from engines.estudio_projeto import operacoes as OP
from engines.estudio_projeto import materiais as MAT
from engines.estudio_projeto import sitio

PAIS = sitio.PAIS
EPS = 0.01


def _t(fr: str, pt: str) -> str:
    return fr if PAIS == "FR" else pt


def _fold(s: Any) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


def _num(s: str) -> float:
    return float(s.replace(",", "."))


class Falha(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ ações geométricas
def _divisao(m: Dict[str, Any], nome: str) -> Dict[str, Any]:
    try:
        return OP._divisao(m, nome)
    except OP.Falha as e:
        raise Falha(str(e)) from e


def _lado_por_omissao(m: Dict[str, Any], dv: Dict[str, Any], der: Dict[str, Any]) -> str:
    """Lado mais natural para crescer: ao longo do maior lado da divisão, para o lado de fora da casa."""
    xs = [p[0] for p in dv["pts"]]
    ys = [p[1] for p in dv["pts"]]
    lim = der.get("limites") or [min(xs), min(ys), max(xs), max(ys)]
    cx, cy = (lim[0] + lim[2]) / 2, (lim[1] + lim[3]) / 2
    if (max(xs) - min(xs)) >= (max(ys) - min(ys)):
        return "direita" if (min(xs) + max(xs)) / 2 >= cx else "esquerda"
    return "tardoz" if (min(ys) + max(ys)) / 2 >= cy else "frente"


def esticar(m: Dict[str, Any], nome: str, metros: float, lado: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
    m = EP.normalizar(copy.deepcopy(m))
    der = EP.derivar(m)
    dv = _divisao(m, nome)
    xs = [p[0] for p in dv["pts"]]
    ys = [p[1] for p in dv["pts"]]
    lado = lado or _lado_por_omissao(m, dv, der)
    eixo = 0 if lado in ("direita", "esquerda") else 1
    sinal = 1 if lado in ("direita", "tardoz") else -1
    c = (max(xs) + EPS) if lado == "direita" else (min(xs) - EPS) if lado == "esquerda" else (max(ys) + EPS) if lado == "tardoz" else (min(ys) - EPS)
    d = float(metros)
    if abs(d) < 0.05 or abs(d) > 20:
        raise Falha(_t("Valeur entre 5 cm et 20 m.", "Valor entre 5 cm e 20 m."))
    dim = (max(xs) - min(xs)) if eixo == 0 else (max(ys) - min(ys))
    if d < 0 and dim + d < 1.2:
        raise Falha(_t("La pièce deviendrait trop étroite (< 1,20 m).", "A divisão ficaria demasiado estreita (< 1,20 m)."))
    alem = (lambda v: v > c) if sinal > 0 else (lambda v: v < c)
    desl = sinal * d

    if d < 0:                                       # reduzir: nada pode ficar entre a nova e a antiga posição
        lo, hi = sorted((c, c + desl))
        pts = [w[k][eixo] for w in m["paredes"] for k in ("a", "b")]
        if any(lo + 0.02 < v < hi - 0.02 for v in pts):
            raise Falha(_t("Réduction plus grande que l'espace libre de ce côté.", "Redução maior do que o espaço livre deste lado."))

    def mover(p: List[float]) -> List[float]:
        q = list(p)
        if alem(q[eixo]):
            q[eixo] = round(q[eixo] + desl, 3)
        return q

    antes = {w["id"]: (list(w["a"]), list(w["b"])) for w in m["paredes"]}
    for w in m["paredes"]:
        w["a"], w["b"] = mover(w["a"]), mover(w["b"])
    for v in m["vaos"]:                             # vão: posição absoluta antiga → nova, medida a partir do novo «a»
        a0, b0 = antes[v["parede"]]
        L0 = math.hypot(b0[0] - a0[0], b0[1] - a0[1]) or 1.0
        u0 = ((b0[0] - a0[0]) / L0, (b0[1] - a0[1]) / L0)
        p_abs = mover([a0[0] + u0[0] * v["pos_m"], a0[1] + u0[1] * v["pos_m"]])
        w = next(x for x in m["paredes"] if x["id"] == v["parede"])
        L1 = math.hypot(w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]) or 1.0
        u1 = ((w["b"][0] - w["a"][0]) / L1, (w["b"][1] - w["a"][1]) / L1)
        v["pos_m"] = round((p_abs[0] - w["a"][0]) * u1[0] + (p_abs[1] - w["a"][1]) * u1[1], 3)
    for lista in ("rotulos", "objetos", "escadas", "notas"):
        for o in m.get(lista) or []:
            o["x"], o["y"] = mover([o["x"], o["y"]])
    for ct in m.get("cotas") or []:
        ct["a"], ct["b"] = mover(ct["a"]), mover(ct["b"])
    m2 = EP.normalizar(m)
    d2 = EP.derivar(m2)
    if d2.get("erros"):
        raise Falha(_t("La modification casserait la maquette : ", "A alteração partiria o modelo: ") + d2["erros"][0]["msg"])
    novo = next((x for x in d2["divisoes"] if x["nome"] == dv["nome"] and x["piso"] == dv["piso"]), None)
    area = f" ({dv['area_m2']:.1f} → {novo['area_m2']:.1f} m²)".replace(".", ",") if novo else ""
    nomes_lado = {"direita": _t("droite", "direita"), "esquerda": _t("gauche", "esquerda"), "frente": _t("façade avant", "frente"),
                  "tardoz": _t("façade arrière", "tardoz")}
    verbo = _t("agrandie", "aumentada") if d > 0 else _t("réduite", "reduzida")
    dd = f"{abs(d):g}".replace(".", ",")
    return m2, _t(f"« {dv['nome']} » {verbo} de {dd} m côté {nomes_lado[lado]}{area}.",
                  f"«{dv['nome']}» {verbo} {dd} m do lado {nomes_lado[lado]}{area}.")


def vaos_maiores(m: Dict[str, Any], nome: str, metros: float = 0.4) -> Tuple[Dict[str, Any], str]:
    m = EP.normalizar(copy.deepcopy(m))
    der = EP.derivar(m)
    dv = next((x for x in der["divisoes"] if x["nome"] == _divisao(m, nome)["nome"]), None)
    ext = {w["id"] for w in m["paredes"] if (m["tipos_parede"].get(w["tipo"]) or {}).get("exterior")}
    ids = {v["id"] for f in (dv or {}).get("faces") or [] for v in f.get("vaos") or []}
    alvo = [v for v in m["vaos"] if v["id"] in ids and v["parede"] in ext and v["tipo"] in ("janela", "portada")]
    if not alvo:
        raise Falha(_t(f"« {nome} » n'a pas de fenêtre sur l'extérieur.", f"«{nome}» não tem janelas para o exterior."))
    feitos = 0
    for v in alvo:
        w = next(x for x in m["paredes"] if x["id"] == v["parede"])
        L = math.hypot(w["b"][0] - w["a"][0], w["b"][1] - w["a"][1])
        outros = [o for o in m["vaos"] if o["parede"] == w["id"] and o["id"] != v["id"]]
        esq = min([v["pos_m"] - v["largura_m"] / 2] + [v["pos_m"] - v["largura_m"] / 2 - (o["pos_m"] + o["largura_m"] / 2) - 0.3
                                                        for o in outros if o["pos_m"] < v["pos_m"]] + [v["pos_m"] - v["largura_m"] / 2 - 0.3])
        dir_ = min([L - (v["pos_m"] + v["largura_m"] / 2) - 0.3] + [(o["pos_m"] - o["largura_m"] / 2) - (v["pos_m"] + v["largura_m"] / 2) - 0.3
                                                                     for o in outros if o["pos_m"] > v["pos_m"]])
        ganho = max(0.0, min(float(metros), 2 * min(esq, dir_)))
        if ganho >= 0.05:
            v["largura_m"] = round(v["largura_m"] + ganho, 2)
            feitos += 1
    if not feitos:
        raise Falha(_t("Pas de place pour agrandir les fenêtres de cette pièce.", "Não há espaço para alargar as janelas desta divisão."))
    m2 = EP.normalizar(m)
    return m2, _t(f"{feitos} baie(s) de « {dv['nome']} » élargie(s) jusqu'à {metros:g} m.",
                  f"{feitos} vão(s) de «{dv['nome']}» alargado(s) até {metros:g} m.")


def objeto_medidas(m: Dict[str, Any], tipo_ou_nome: str, largura: float, prof: float) -> Tuple[Dict[str, Any], str]:
    m = EP.normalizar(copy.deepcopy(m))
    alvo = _fold(tipo_ou_nome)
    from engines.estudio_projeto.objetos import OBJETOS
    cand = [o for o in m.get("objetos") or [] if alvo in o["tipo"] or alvo in _fold(OBJETOS[o["tipo"]]["nome"])]
    cand.sort(key=lambda o: (not o["tipo"].startswith(alvo), "deck" in o["tipo"], len(o["tipo"])))   # «piscina» antes de «deck de piscina»
    if not cand:                                 # ainda não existe: cria-o no jardim, atrás da casa, com estas medidas
        tipo = _tipo_exterior(tipo_ou_nome)
        piso, x0, y0, x1, y1 = _casa_limites(m)
        a_, b_ = max(float(largura), float(prof)), min(float(largura), float(prof))
        _por_objeto(m, piso, tipo, (x0 + x1) / 2, y1 + 3.0 + b_ / 2, a_, b_, True)
        m2 = _validar(m)
        return m2, _t(f"{OBJETOS[tipo]['nome']} créé(e) derrière la maison : {a_:g} × {b_:g} m.",
                      f"{OBJETOS[tipo]['nome']} criado atrás da casa: {a_:g} × {b_:g} m.")
    o = cand[0]
    o["largura_m"], o["prof_m"] = float(largura), float(prof)
    return EP.normalizar(m), _t(f"{OBJETOS[o['tipo']]['nome']} : {largura:g} × {prof:g} m.", f"{OBJETOS[o['tipo']]['nome']}: {largura:g} × {prof:g} m.")


# ------------------------------------------------------------------------------------------------ exteriores à volta da casa
_EXT_TIPO = {"piscina": "piscina", "piscine": "piscina", "pool": "piscina", "jacuzzi": "jacuzzi", "spa": "jacuzzi",
             "terraco": "terraco_pedra", "terrasse": "terraco_pedra", "terrace": "terraco_pedra", "deck": "deck_madeira",
             "relvado": "relvado", "pelouse": "relvado", "lawn": "relvado", "pergola": "pergola", "caminho": "caminho",
             "allee": "caminho", "muro": "muro_vedacao", "cloture": "muro_vedacao", "fence": "muro_vedacao"}
MAX_OBJ = 40.0          # medida máxima de um objeto no modelo (m); peças maiores são divididas em troços


def _tipo_exterior(alvo: Any) -> str:
    from engines.estudio_projeto.objetos import OBJETOS
    a = _fold(alvo).replace(" ", "_")
    if a in OBJETOS:
        return a
    for k, v in _EXT_TIPO.items():
        if k in a:
            return v
    raise Falha(_t(f"Je ne connais pas l'élément extérieur « {alvo} ».", f"Não conheço o elemento exterior «{alvo}»."))


def _casa_limites(m: Dict[str, Any]) -> Tuple[str, float, float, float, float]:
    """Piso térreo e limites exteriores da casa (faces exteriores das paredes; ignora piscinas, terraços…)."""
    from engines.estudio_projeto.modelo import espessura
    piso = m["pisos"][0]["id"]
    ws = [w for w in m["paredes"] if w["piso"] == piso] or m["paredes"]
    if not ws:
        raise Falha(_t("Le projet n'a pas encore de murs.", "O projeto ainda não tem paredes."))
    xs, ys = [], []
    for w in ws:
        e = espessura(m["tipos_parede"][w["tipo"]]) / 2 if w["tipo"] in m["tipos_parede"] else 0.15
        for p in (w["a"], w["b"]):
            xs += [p[0] - e, p[0] + e]
            ys += [p[1] - e, p[1] + e]
    return piso, min(xs), min(ys), max(xs), max(ys)


def _por_objeto(m: Dict[str, Any], piso: str, tipo: str, cx: float, cy: float, comp: float, prof: float, horizontal: bool) -> int:
    """Coloca um objeto retangular (dividido em troços de ≤ 40 m) com o comprimento ao longo de x (horizontal) ou de y."""
    n = max(1, math.ceil(comp / MAX_OBJ - 1e-9))
    passo = comp / n
    for i in range(n):
        off = -comp / 2 + passo * (i + 0.5)
        x, y = (cx + off, cy) if horizontal else (cx, cy + off)
        m["objetos"].append({"id": OP._novo_id("o", m["objetos"]), "piso": piso, "tipo": tipo, "x": round(x, 3), "y": round(y, 3),
                             "rot": 0.0 if horizontal else 90.0, "largura_m": round(passo, 3), "prof_m": round(min(prof, MAX_OBJ), 3)})
    return n


def _validar(m: Dict[str, Any]) -> Dict[str, Any]:
    m2 = EP.normalizar(m)
    d2 = EP.derivar(m2)
    if d2.get("erros"):
        raise Falha(_t("La modification casserait la maquette : ", "A alteração partiria o modelo: ") + d2["erros"][0]["msg"])
    return m2


def _lado_da_divisao(m: Dict[str, Any], dv: Dict[str, Any], lim: Tuple[float, float, float, float]) -> str:
    """Fachada da casa em que a divisão está encostada; havendo várias, a que tem mais janelas / portas-janela da divisão."""
    x0, y0, x1, y1 = lim
    xs = [p[0] for p in dv["pts"]]
    ys = [p[1] for p in dv["pts"]]
    folga = {"frente": min(ys) - y0, "tardoz": y1 - max(ys), "esquerda": min(xs) - x0, "direita": x1 - max(xs)}
    enc = [k for k, v in folga.items() if v < 0.8] or [min(folga, key=folga.get)]
    ws = {w["id"]: w for w in m["paredes"]}

    def vaos(lado: str) -> float:
        tot = 0.0
        for v in m["vaos"]:
            w = ws.get(v["parede"])
            if not w or w["piso"] != dv["piso"]:
                continue
            (ax, ay), (bx, by) = w["a"], w["b"]
            if lado in ("frente", "tardoz"):
                alvo = y0 if lado == "frente" else y1
                ok = abs(ay - by) < 0.05 and abs(ay - alvo) < 0.8 and min(xs) - 0.3 <= (ax + bx) / 2 <= max(xs) + 0.3 or (
                    abs(ay - by) < 0.05 and abs(ay - alvo) < 0.8 and max(min(ax, bx), min(xs)) < min(max(ax, bx), max(xs)))
            else:
                alvo = x0 if lado == "esquerda" else x1
                ok = abs(ax - bx) < 0.05 and abs(ax - alvo) < 0.8 and max(min(ay, by), min(ys)) < min(max(ay, by), max(ys))
            if ok:
                tot += v["largura_m"] * (2 if v["tipo"] == "portada" else 1)
        return tot
    return max(enc, key=lambda k: (vaos(k), k == "frente", k == "tardoz"))


def faixa_exterior(m: Dict[str, Any], alvo: str = "terraco", divisao: Optional[str] = None, lado: Optional[str] = None,
                   comprimento: Any = "casa", prof: Optional[float] = None) -> Tuple[Dict[str, Any], str]:
    """Terraço, deck, caminho… encostado a uma fachada: «terrasse devant le séjour sur toute la longueur de la maison»."""
    m = EP.normalizar(copy.deepcopy(m))
    tipo = _tipo_exterior(alvo)
    piso, x0, y0, x1, y1 = _casa_limites(m)
    dv = _divisao(m, divisao) if divisao else None
    if lado not in ("frente", "tardoz", "esquerda", "direita"):
        lado = _lado_da_divisao(m, dv, (x0, y0, x1, y1)) if dv else "frente"
    horizontal = lado in ("frente", "tardoz")
    a0, a1 = (x0, x1) if horizontal else (y0, y1)
    if dv:
        k = 0 if horizontal else 1
        d0, d1 = min(p[k] for p in dv["pts"]), max(p[k] for p in dv["pts"])
    else:
        d0, d1 = a0, a1
    if isinstance(comprimento, (int, float)) and comprimento > 0:
        L, c = float(comprimento), (d0 + d1) / 2
    elif comprimento == "divisao" and dv:
        L, c = d1 - d0, (d0 + d1) / 2
    else:
        L, c = a1 - a0, (a0 + a1) / 2
    P = float(prof) if prof else (1.2 if tipo == "caminho" else 3.0)
    if not (0.3 <= P <= 40) or L < 0.5:
        raise Falha(_t("Dimensions hors limites.", "Medidas fora dos limites."))
    if horizontal:
        cx, cy = c, (y0 - P / 2) if lado == "frente" else (y1 + P / 2)
    else:
        cx, cy = (x0 - P / 2) if lado == "esquerda" else (x1 + P / 2), c
    _por_objeto(m, piso, tipo, cx, cy, L, P, horizontal)
    m2 = _validar(m)
    from engines.estudio_projeto.objetos import OBJETOS
    nomes_lado = {"direita": _t("droite", "direita"), "esquerda": _t("gauche", "esquerda"), "frente": _t("avant", "frente"),
                  "tardoz": _t("arrière", "tardoz")}
    onde = (_t(f" devant « {dv['nome']} »", f" à frente de «{dv['nome']}»") if dv else "")
    f2 = lambda v: f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return m2, _t(f"{OBJETOS[tipo]['nome']} ajouté(e){onde}, façade {nomes_lado[lado]} : {f2(L)} × {f2(P)} m ({f2(L * P)} m²).",
                  f"{OBJETOS[tipo]['nome']} acrescentado{onde}, fachada {nomes_lado[lado]}: {f2(L)} × {f2(P)} m ({f2(L * P)} m²).")


def contorno_exterior(m: Dict[str, Any], alvo: str = "muro", area_m2: Optional[float] = None,
                      margem: Optional[float] = None, altura: Optional[float] = None) -> Tuple[Dict[str, Any], str]:
    """Muro de vedação (ou sebe, caminho…) à volta da casa, num terreno quadrado de `area_m2` centrado na casa,
    ou a `margem` metros das fachadas."""
    m = EP.normalizar(copy.deepcopy(m))
    tipo = _tipo_exterior(alvo)
    piso, x0, y0, x1, y1 = _casa_limites(m)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w0, h0 = x1 - x0, y1 - y0
    if area_m2:
        lado = math.sqrt(float(area_m2))
        W, H = max(lado, w0 + 2), max(lado, h0 + 2)
        if lado * lado < (w0 + 2) * (h0 + 2):
            W, H = w0 + 2, h0 + 2
    else:
        mg = float(margem) if margem else 5.0
        W, H = w0 + 2 * mg, h0 + 2 * mg
    if max(W, H) > 400:
        raise Falha(_t("Terrain trop grand (plus de 400 m de côté).", "Terreno demasiado grande (mais de 400 m de lado)."))
    esp = 0.2 if tipo == "muro_vedacao" else 1.2 if tipo == "caminho" else 0.6
    for (x, y, comp, hor) in ((cx, cy - H / 2, W, True), (cx, cy + H / 2, W, True), (cx - W / 2, cy, H, False), (cx + W / 2, cy, H, False)):
        _por_objeto(m, piso, tipo, x, y, comp, esp, hor)
    m2 = _validar(m)
    f2 = lambda v: f"{v:,.1f}".replace(",", " ").replace(".", ",")
    from engines.estudio_projeto.objetos import OBJETOS
    return m2, _t(f"{OBJETOS[tipo]['nome']} autour de la maison : terrain {f2(W)} × {f2(H)} m ({f2(W * H)} m²), "
                  f"{f2(2 * (W + H))} m linéaires.",
                  f"{OBJETOS[tipo]['nome']} à volta da casa: terreno {f2(W)} × {f2(H)} m ({f2(W * H)} m²), {f2(2 * (W + H))} m lineares.")


def nota_pedido(m: Dict[str, Any], texto: str) -> Tuple[Dict[str, Any], str]:
    """Último recurso: o pedido fica escrito no plano para o projetista (nunca se perde, nunca dá erro)."""
    m = EP.normalizar(copy.deepcopy(m))
    try:
        piso, x0, y0, x1, y1 = _casa_limites(m)
        x, y = (x0 + x1) / 2, y1 + 1.5
    except Falha:
        piso, x, y = m["pisos"][0]["id"], 0.0, 0.0
    m.setdefault("notas", []).append({"id": OP._novo_id("n", m.get("notas") or []), "piso": piso, "x": round(x, 2), "y": round(y, 2),
                                      "texto": str(texto)[:120]})
    return EP.normalizar(m), _t(f"Demande notée sur le plan : « {str(texto)[:80]} ».", f"Pedido anotado no plano: «{str(texto)[:80]}».")



# ------------------------------------------------------------------------------------------------ arranjos exteriores compostos
def _obj(m: Dict[str, Any], piso: str, tipo: str, x: float, y: float, larg: Optional[float] = None, prof: Optional[float] = None,
         rot: float = 0.0) -> None:
    from engines.estudio_projeto.objetos import OBJETOS
    b = OBJETOS[tipo]
    m["objetos"].append({"id": OP._novo_id("o", m["objetos"]), "piso": piso, "tipo": tipo, "x": round(x, 3), "y": round(y, 3),
                         "rot": rot, "largura_m": round(min(larg or b["largura_m"], MAX_OBJ), 3),
                         "prof_m": round(min(prof or b["prof_m"], MAX_OBJ), 3)})


def _nome(tipo: str) -> str:
    from engines.estudio_projeto.objetos import OBJETOS
    return OBJETOS[tipo]["nome"]


def acesso_estrada(m: Dict[str, Any], recuo: float = 10.0, largura_estrada: float = 6.0) -> Tuple[Dict[str, Any], str]:
    """Estrada à frente da casa + acesso privado automóvel até à garagem (ou ao centro da fachada) + caminho pedonal."""
    m = EP.normalizar(copy.deepcopy(m))
    piso, x0, y0, x1, y1 = _casa_limites(m)
    der = EP.derivar(m)
    gar = next((d for d in der["divisoes"] if re.search(r"garag", _fold(d["nome"])) and d["piso"] == piso), None)
    gx = sum(p[0] for p in gar["pts"]) / len(gar["pts"]) if gar else (x0 + x1) / 2
    L = min(max(x1 - x0 + 30, 40), 120)
    _por_objeto(m, piso, "estrada", (x0 + x1) / 2, y0 - recuo - largura_estrada / 2, L, largura_estrada, True)
    _obj(m, piso, "acesso_viaturas", gx, y0 - recuo / 2, 3.5, recuo)
    px = x0 + 1.5 if abs(gx - x0) > 3 else x1 - 1.5
    _obj(m, piso, "caminho", px, y0 - recuo / 2, 1.2, recuo)
    return _validar(m), _t(f"Route de {largura_estrada:g} m devant la maison (à {recuo:g} m), accès voiture privé de {recuo:g} m jusqu'"
                           f"{'au garage' if gar else 'à la façade'} et allée piétonne.",
                           f"Estrada de {largura_estrada:g} m à frente da casa (a {recuo:g} m), acesso automóvel privado de {recuo:g} m até "
                           f"{'à garagem' if gar else 'à fachada'} e caminho pedonal.")


def jardim(m: Dict[str, Any], prof: float = 12.0, arvores: int = 4) -> Tuple[Dict[str, Any], str]:
    """Jardim nas traseiras: relvado a toda a largura da casa, árvores e arbustos na orla, canteiros encostados à casa."""
    m = EP.normalizar(copy.deepcopy(m))
    piso, x0, y0, x1, y1 = _casa_limites(m)
    W = min(x1 - x0 + 8, MAX_OBJ)
    cx = (x0 + x1) / 2
    _obj(m, piso, "relvado", cx, y1 + 1.5 + prof / 2, W, prof)
    _obj(m, piso, "canteiro", cx, y1 + 0.9, min(x1 - x0, MAX_OBJ), 0.8)
    n = max(0, min(int(arvores), 30))
    for i in range(n):
        _obj(m, piso, "arvore", cx - W / 2 + 1.5 + i * (W - 3) / max(n - 1, 1), y1 + 1.5 + prof - 1.5)
    for i in range(3):
        _obj(m, piso, "arbusto", cx - W / 2 + 0.8, y1 + 3 + i * (prof - 4) / 2)
    return _validar(m), _t(f"Jardin derrière la maison : pelouse {W:g} × {prof:g} m, massif le long de la façade, {n} arbre(s) et 3 arbustes.",
                           f"Jardim nas traseiras: relvado {W:g} × {prof:g} m, canteiro ao longo da fachada, {n} árvore(s) e 3 arbustos.")


def plantar_arvores(m: Dict[str, Any], n: int = 5) -> Tuple[Dict[str, Any], str]:
    m = EP.normalizar(copy.deepcopy(m))
    piso, x0, y0, x1, y1 = _casa_limites(m)
    n = max(1, min(int(n), 60))
    # à volta da casa, a 4 m das fachadas, distribuídas pelo perímetro
    X0, Y0, X1, Y1 = x0 - 4, y0 - 4, x1 + 4, y1 + 4
    per = 2 * ((X1 - X0) + (Y1 - Y0))
    for i in range(n):
        d = per * (i + 0.5) / n
        for (ax, ay, bx, by) in ((X0, Y1, X1, Y1), (X1, Y1, X1, Y0), (X1, Y0, X0, Y0), (X0, Y0, X0, Y1)):
            seg = abs(bx - ax) + abs(by - ay)
            if d <= seg:
                t = d / seg
                _obj(m, piso, "arvore", ax + (bx - ax) * t, ay + (by - ay) * t)
                break
            d -= seg
    return _validar(m), _t(f"{n} arbre(s) planté(s) autour de la maison.", f"{n} árvore(s) plantada(s) à volta da casa.")


def zona_jogos(m: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """Parque infantil no jardim (lado direito das traseiras): solo amortecedor, baloiço, escorrega, caixa de areia e casinha."""
    m = EP.normalizar(copy.deepcopy(m))
    piso, x0, y0, x1, y1 = _casa_limites(m)
    cx, cy = x1 + 6.0, y1 + 6.0
    _obj(m, piso, "parque_infantil", cx, cy, 8.0, 6.0)
    _obj(m, piso, "baloico", cx - 2.2, cy - 1.5)
    _obj(m, piso, "escorrega", cx + 1.5, cy - 1.8)
    _obj(m, piso, "caixa_areia", cx - 2.5, cy + 1.6)
    _obj(m, piso, "casinha_criancas", cx + 2.5, cy + 1.6)
    return _validar(m), _t("Aire de jeux pour enfants dans le jardin : sol amortissant 8 × 6 m, balançoire, toboggan, bac à sable et cabane.",
                           "Parque infantil no jardim: piso amortecedor 8 × 6 m, baloiço, escorrega, caixa de areia e casinha.")


def terraco_sobre_piscina(m: Dict[str, Any], prof: float = 3.0) -> Tuple[Dict[str, Any], str]:
    """Andar superior com terraço em balanço sobre a piscina: terraço suspenso no último piso, nas traseiras, e a piscina
    colocada (ou criada) por baixo, de modo que o terraço avança sobre o plano de água."""
    m = EP.normalizar(copy.deepcopy(m))
    piso0, x0, y0, x1, y1 = _casa_limites(m)
    topo = m["pisos"][-1]["id"]
    W = min(x1 - x0, MAX_OBJ)
    cx = (x0 + x1) / 2
    pis = [o for o in m["objetos"] if o["tipo"] in ("piscina", "piscina_infinita")]
    if pis:
        p = pis[0]
    else:
        _obj(m, piso0, "piscina", cx, 0, min(8.0, W), 4.0)
        p = m["objetos"][-1]
    p["x"], p["rot"] = round(cx, 3), 0.0
    p["y"] = round(y1 + 1.0 + p["prof_m"] / 2, 3)            # bordo da piscina a 1 m da fachada → o terraço avança sobre a água
    _obj(m, topo, "terraco_suspenso", cx, y1 + prof / 2, W, prof)
    nome_topo = m["pisos"][-1]["nome"]
    sobre = max(0.0, prof - 1.0)
    msg = _t(f"Terrasse en porte-à-faux de {W:g} × {prof:g} m au niveau « {nome_topo} », qui déborde de {sobre:g} m au-dessus de la piscine"
             f"{'' if pis else ' (piscine 8 × 4 m créée)'}.",
             f"Terraço em balanço de {W:g} × {prof:g} m no piso «{nome_topo}», a avançar {sobre:g} m sobre a piscina"
             f"{'' if pis else ' (piscina 8 × 4 m criada)'}.")
    if len(m["pisos"]) == 1:
        msg += _t(" La maison n'a qu'un niveau : la terrasse est posée en toiture-terrasse ; ajoutez un niveau pour l'avoir à l'étage.",
                  " A casa só tem um piso: o terraço fica ao nível da cobertura; acrescente um piso para o ter no andar.")
    return _validar(m), msg


_FACH_PAL = [("granit", "granito"), ("bois", "madeira"), ("madeira", "madeira"), ("wood", "madeira"), ("pierre", "pedra_seca"),
             ("pedra", "pedra_seca"), ("stone", "pedra_seca"), ("schiste", "xisto"), ("xisto", "xisto"), ("brique", "tijolo"),
             ("tijolo", "tijolo"), ("brick", "tijolo"), ("beton", "betao"), ("betao", "betao"), ("concrete", "betao"),
             ("ardoise", "ardosia"), ("ardosia", "ardosia"), ("calcaire", "calcario"), ("calcario", "calcario"),
             ("marbre", "marmore_branco"), ("marmore", "marmore_branco"), ("zinc", "zinco_natural"), ("cuivre", "cobre"),
             ("cobre", "cobre"), ("corten", "aco_corten"), ("enduit", "reboco_branco"), ("reboco", "reboco_branco"),
             ("crepi", "reboco_branco"), ("azulejo", "azulejo_azul"), ("travertin", "travertino"), ("basalt", "basalto")]


def fachada_material(frase: str) -> Optional[str]:
    """«façades en granit et bois» → misto_granito_madeira; «fachada em xisto» → xisto."""
    f = _fold(frase)
    achados = []
    for pal, mid in _FACH_PAL:
        if re.search(r"\b" + pal, f) and mid not in achados:
            achados.append(mid)
    if not achados:
        return None
    if len(achados) >= 2:
        par = {frozenset(("granito", "madeira")): "misto_granito_madeira", frozenset(("granito", "reboco_branco")): "misto_granito_reboco",
               frozenset(("madeira", "reboco_branco")): "misto_madeira_reboco"}.get(frozenset(achados[:2]))
        if par:
            return par
    return achados[0]


# ------------------------------------------------------------------------------------------------ leitura da frase
_N = r"(\d+(?:[.,]\d+)?)"
_UN = r"\s*(m|metros?|metres?|meters?|cm|centimetros?|centimetres?)?"
_LADOS = [("direita", r"direita|droite|right"), ("esquerda", r"esquerda|gauche|left"),
          ("tardoz", r"tardoz|tras|traseir|arriere|jardim|jardin|back|rear"), ("frente", r"frente|devant|avant|rua|front|street")]
_MAIS = r"aumenta|aumentar|alarga|alargar|estica|esticar|amplia|ampliar|agrandi|agrandir|elargi|elargir|allonge|rallonge|enlarge|extend|increase|widen|make .* bigger"
_MENOS = r"diminui|diminuir|reduz|reduzir|encurta|encolhe|reduis|reduire|retreci|shrink|reduce|make .* smaller"
_JANELAS = r"janelas?|vaos?|fenetres?|baies?|windows?"
_GRANDES = r"maiores|mais largas|grandes|plus grandes|plus larges|bigger|larger|wider"
_PAV = {"pavimento": r"pavimento|chao|piso de|sol|revetement de sol|floor(ing)?",
        "parede_interior": r"paredes?|murs?|walls?", "teto": r"teto|tecto|plafond|ceiling"}


def _medida(txt: str) -> Optional[float]:
    m = re.search(_N + _UN + r"\b", txt)
    if not m:
        return None
    v = _num(m.group(1))
    if (m.group(2) or "").startswith("c"):
        v /= 100.0
    return v


def _nome_divisao(txt: str, nomes: List[str]) -> Optional[str]:
    """A divisão do projeto citada na frase (o nome mais longo que aparece primeiro; «quarto 2» antes de «quarto»)."""
    f = _fold(txt)
    melhor = None
    for n in nomes:
        nf = _fold(n)
        palavras = [p for p in re.split(r"[^a-z0-9]+", nf) if p and p not in ("de", "da", "do", "e", "et", "la", "le", "em", "com")]
        if not palavras:
            continue
        chave = palavras[0] if len(palavras) == 1 or not palavras[1].isdigit() else f"{palavras[0]} {palavras[1]}"
        rx = r"\b" + re.escape(chave) + r"\b"
        if chave in ("casa", "salle", "instalacao", "instalacoes", "piece") and len(palavras) > 1:   # «casa de banho» ≠ «a casa»
            chave = f"{palavras[0]} {palavras[1]}"
            rx = r"\b" + re.escape(palavras[0]) + r"\b.{0,12}\b" + re.escape(palavras[1]) + r"\b"
        if re.search(rx, f):
            pont = (len(chave), -len(nf))
            if melhor is None or pont > melhor[0]:
                melhor = (pont, n)
    if melhor:
        return melhor[1]
    # sinónimos noutras línguas («cuisine», «kitchen» → a cozinha do projeto): pelo tipo de divisão
    from engines.atelier_archi.programme import _tipo
    pedidas = [_tipo(w) for w in re.findall(r"[a-z]+(?:\s+[a-z]+)?", f)]
    for cle in [c for c in pedidas if c and not c.startswith("_")]:
        n = next((n for n in nomes if _tipo(_fold(n)) == cle), None)
        if not n and cle in ("sejour", "cuisine", "sejour_cuisine"):      # «séjour» pedido, projeto com «Sala / cozinha» (e vice-versa)
            n = next((n for n in nomes if _tipo(_fold(n)) in ("sejour", "cuisine", "sejour_cuisine")
                      and (cle != "cuisine" or _tipo(_fold(n)) != "sejour")), None)
        if n:
            return n
    return None


_FORMA_L = r"\b(?:em|en|in|forma de|formato(?: de)?|shape(?:d)?|planta em)\s+(?:um\s+|une?\s+|an?\s+)?l\b|\bl[- ]shaped?\b|\bem l\b"
_FORMA_U = r"\b(?:em|en|in|forma de|formato(?: de)?)\s+(?:um\s+|une?\s+)?u\b|\bu[- ]shaped?\b"
_FORMA_RET = r"retangul|rectangul|rectangle|retangulo|forma simples|plan simple"
_INTERIOR = r"interior|interieur|inside|dentro|decora|decor"
_EXTERIOR = r"exterior|exterieur|fachada|facade|outside|fora"


def _forma_e_estilo(frase: str) -> Tuple[List[Dict[str, Any]], str]:
    """Pedidos que valem para a casa inteira: forma (L, retângulo) e estilo (provençal, rústico…). Devolve as ações e a
    frase sem esses pedidos (o resto continua a ser lido normalmente)."""
    from engines.atelier_archi import forma as FO
    f = _fold(frase)
    acoes: List[Dict[str, Any]] = []
    if re.search(_FORMA_L, f):
        acoes.append({"acao": "forma", "forma": "l"})
    elif re.search(_FORMA_U, f):
        acoes.append({"acao": "forma", "forma": "u"})
    elif re.search(r"(?:casa|maison|planta|plan|house)\b.*\b(?:" + _FORMA_RET + r")", f):
        acoes.append({"acao": "forma", "forma": "retangular"})
    for nome, rx in FO.RX_ESTILO.items():
        mt = re.search(rx, f)
        if not mt:
            continue
        antes = f[max(0, mt.start() - 40):mt.start()]
        ambito = "interior" if re.search(_INTERIOR, antes) else "exterior" if re.search(_EXTERIOR, antes) else "tudo"
        acoes.append({"acao": "estilo", "estilo": nome, "ambito": ambito})
        break
    if not acoes:
        return [], frase
    # o que sobra da frase (ex.: «… e aumenta a sala 2 metros») continua a ser interpretado
    resto = re.sub(r"(?i)\b(faz|fazer|fais|faire|make|torna|transforma|muda|passa|coloca|poe|põe)\b[^.;]*?\b(?:em|en|in)\s+(?:um\s+)?[lu]\b", " ", frase)
    resto = re.sub(r"(?i)(?:\b(?:a|à|la|the)\s+)?\b(?:casa|maison|planta|plan|house)?\s*\b(?:em|en|in)\s+(?:um\s+|une?\s+)?[lu]\b", " ", resto)
    resto = re.sub(r"(?i)\bcom\s+v[aá]rios\s+recortes\b|\bavec\s+(?:plusieurs\s+)?d[ée]crochements\b", " ", resto)
    resto = re.sub(r"(?i)\b(?:e\s+)?(?:o\s+|l'|le\s+|the\s+)?(?:interior|int[ée]rieur|exterior|ext[ée]rieur|fachada|fa[çc]ade)?\s*(?:em\s+|de\s+)?(?:estilo\s+|style\s+)?\w*"
                   + r"(?:proven[çc]\w*|r[uú]stic\w*|mediterr\w*|modern\w*|minimal\w*|escandinav\w*|scandinav\w*|industri\w*|cl[aá]ssic\w*|contempor\w*|tradicion\w*|traditionn\w*)", " ", resto)
    return acoes, resto


def _global(f: str) -> bool:
    """Parte da frase que só fala da forma ou do estilo da casa (já tratada)."""
    from engines.atelier_archi import forma as FO
    return bool(re.search(_FORMA_L, f) or re.search(_FORMA_U, f) or re.search(_FORMA_RET, f)
                or any(re.search(rx, f) for rx in FO.RX_ESTILO.values()) or re.search(r"recortes?|decrochement", f))


def interpretar(frase: str, m: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Frase → lista de ações. Vazia se nada for reconhecido."""
    return interpretar_partes(frase, m)[0]


def interpretar_partes(frase: str, m: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Frase → (ações reconhecidas pelas regras, partes da frase que as regras não perceberam)."""
    der = EP.derivar(EP.normalizar(m))
    nomes = sorted({d["nome"] for d in der["divisoes"]}, key=len)
    globais, frase = _forma_e_estilo(frase or "")
    acoes: List[Dict[str, Any]] = []
    sobras: List[str] = []
    for parte in re.split(r"\s*(?:;|\.\s|\be depois\b|\bpuis\b|\bthen\b)\s*", frase or ""):
        f = _fold(parte)
        if not f or len(re.sub(r"\b(e|et|and|o|a|os|as|com|de|da|do)\b|[^a-z0-9]", "", f)) < 3:
            continue
        n_antes = len(acoes)
        _uma_parte(parte, f, nomes, acoes)
        if len(acoes) == n_antes and not (globais and (_global(f) or len(f.split()) <= 3)):
            sobras.append(parte.strip())
    return globais + acoes, sobras


def _uma_parte(parte: str, f: str, nomes: List[str], acoes: List[Dict[str, Any]]) -> None:
    for _ in (0,):
        div = _nome_divisao(f, nomes)
        dims = re.search(_N + r"\s*(?:m\s*)?[x×]\s*" + _N, parte.replace("×", "x"))
        sem_nome = re.sub(r"\b(?!de\b|em\b|by\b|of\b|par\b)[a-z]+\s+\d+\b(?![.,]\d)(?!\s*(?:m\b|cm|metro|metre|meter|x))", " ", f)   # «quarto 2» não é uma medida
        # andar com terraço em balanço sobre a piscina
        if re.search(r"terras|terrac|varanda|balcon|balcao", f) and re.search(
                r"debord|balanc|suspens|porte.a.faux|sur la piscine|au.dessus|sobre a piscina|por cima|over the pool|cantilever", f):
            pr = re.search(_N + r"\s*m?\s*(?:de\s+)?(?:profondeur|large|largeur|fundo|profundidade|deep)", f)
            acoes.append({"acao": "terraco_sobre_piscina", "prof": _num(pr.group(1)) if pr else 3.0})
            continue
        # fachadas: «façades en granit et bois», «fachada em xisto»
        if re.search(r"fachad|facade|bardage|revetement exterieur|revestimento exterior|parement", f):
            mat = fachada_material(f)
            if mat:
                acoes.append({"acao": "op", "op": {"op": "materiais", "fachada": mat}})
                continue
        compostos = []
        if re.search(r"\b(?:estrad|route|rua\b|arruament|voirie|chemin d.acces|acces? priv|acesso|entree carross|road|driveway)", f):
            compostos.append({"acao": "acesso_estrada"})
        if re.search(r"jeux|jogos|infantil|enfants|criancas|kids|playground|balancoire|baloico|toboggan|escorrega", f):
            compostos.append({"acao": "zona_jogos"})
        if re.search(r"\bjardi|\bgarden", f) and not re.search(
                r"(?:dans|au|no|num|in|sur|cote|lado|vers|para|do lado)\s+(?:le\s+|un\s+|the\s+|du\s+|do\s+|o\s+)?jardi", f):
            compostos.append({"acao": "jardim"})
        elif re.search(r"arbres?|arvores?|\btrees?", f):
            nm = re.search(r"(\d+)\s*(?:arbres?|arvores?|trees?)", f)
            compostos.append({"acao": "plantar_arvores", "n": int(nm.group(1)) if nm else 5})
        if compostos:
            if re.search(r"piscin|\bpool", f) and not any(o for o in acoes if o.get("alvo") == "piscina"):
                compostos.insert(0, {"acao": "objeto_medidas", "alvo": "piscina", "largura": _num(dims.group(1)) if dims else 8.0,
                                     "prof": _num(dims.group(2)) if dims else 4.0})
            acoes.extend(compostos)
            continue
        # muro de vedação / sebe à volta da casa, num terreno de N m²
        if re.search(r"clotur|vedac|cerca|grillage|\bhaie|\bsebe|\bfence|muret|\bmurs? de|\bmuros?\b|\bmus\b", f) and \
                re.search(r"autour|tour\b|volta|contorno|perimet|around|entoure|rodeia|limite|terrain|terreno|lote|parcelle", f):
            ar = re.search(_N + r"\s*(?:m2|m²|m\s*2|metres? carres?|metros? quadrados?|sqm)", parte.lower().replace("²", "2"))
            mg = re.search(r"\ba\s+" + _N + r"\s*m\b", f)
            alvo = "relvado" if re.search(r"haie|sebe|hedge", f) else "muro"
            acoes.append({"acao": "contorno_exterior", "alvo": alvo, "area_m2": _num(ar.group(1)) if ar else None,
                          "margem": _num(mg.group(1)) if (mg and not ar) else None})
            continue
        # terraço / deck / caminho encostado a uma fachada: «terrasse devant le séjour sur toute la longueur de la maison»
        if re.search(r"terras|terrac|deck|esplanad|patio|allee|caminho|passeio|calcada|trottoir|walkway|path\b", f) and not dims:
            alvo = ("caminho" if re.search(r"allee|caminho|passeio|calcada|trottoir|walkway|path", f)
                    else "deck" if re.search(r"bois|madeira|deck|wood", f) else "terraco")
            toda = re.search(r"\btout\w*\s+(?:la|le|l'|a|o)?\s*(?:longueur|largeur|facade|long)|\btod[oa]s?\s+(?:o|a)\s+"
                             r"(?:comprimento|largura|fachada|frente)|\bwhole\s+(?:length|width)|full length|ao longo da casa|le long de la maison", f)
            pr = re.search(_N + r"\s*m?\s*(?:de\s+)?(?:profondeur|profond|large|largeur|fundo|profundidade|deep|wide)", f)
            lado = next((k for k, rx in _LADOS if re.search(r"\b(" + rx + r")", f)), None)
            if div and lado == "frente":
                lado = None          # «devant le séjour» = a fachada do séjour, não forçosamente a frente da casa
            acoes.append({"acao": "faixa_exterior", "alvo": alvo, "divisao": div, "lado": lado,
                          "comprimento": "casa" if (toda or not div) else "divisao", "prof": _num(pr.group(1)) if pr else None})
            continue
        # piscina / objeto com medidas «10 x 5»
        dims = re.search(_N + r"\s*(?:m\s*)?[x×]\s*" + _N, parte.replace("×", "x"))
        if dims and re.search(r"piscin|pool|jacuzzi|terra[cç]|deck|relvad|pelouse|pergol", f):
            alvo = next(k for k in ("piscin", "pool", "jacuzzi", "terrac", "terras", "deck", "relvad", "pelouse", "pergol") if k in f)
            a, b = _num(dims.group(1)), _num(dims.group(2))
            acoes.append({"acao": "objeto_medidas", "alvo": {"pool": "piscina", "piscin": "piscina", "terras": "terraco", "terrac": "terraco", "pelouse": "relvado", "relvad": "relvado",
                                                     "pergol": "pergola"}.get(alvo, alvo),
                          "largura": max(a, b), "prof": min(a, b)})
            continue
        if div and re.search(_JANELAS, f) and re.search(_GRANDES, f):
            acoes.append({"acao": "vaos_maiores", "divisao": div, "metros": _medida(sem_nome) or 0.4})
            continue
        if div and (re.search(_MAIS, f) or re.search(_MENOS, f)):
            d = _medida(sem_nome)
            if d:
                lado = next((k for k, rx in _LADOS if re.search(r"\b(" + rx + r")", f)), None)
                acoes.append({"acao": "esticar", "divisao": div, "metros": d if not re.search(_MENOS, f) else -d, "lado": lado})
                continue
        # acabamentos de uma divisão: «pavimento da suite em soalho de carvalho»
        mat = re.search(r".*\b(?:em|para|en|in|to|par|com)\s+(.+)$", parte.strip(), re.I)
        chave = next((k for k, rx in _PAV.items() if re.search(r"\b(" + rx + r")", f)), None)
        if div and chave and mat:
            acoes.append({"acao": "op", "op": {"op": "divisao", "nome": div, chave: mat.group(1).strip(" .")}})
            continue
        if re.search(r"telhado|cobertura|toit|toiture|roof", f):
            tipo = ("plana" if re.search(r"plan|plat|flat", f) else "quatro_aguas" if re.search(r"4|quatro|quatre|hip", f)
                    else "uma_agua" if re.search(r"uma agua|un pan|monopente|shed", f) else "duas_aguas" if re.search(r"2|duas|deux|gable", f) else None)
            if tipo:
                acoes.append({"acao": "op", "op": {"op": "cobertura", "tipo": tipo}})
                continue


_CHAVES_OP = {"op", "operacao", "operation", "tipo_op", "acao_op"}


def normalizar_acao(a: Any) -> Optional[Dict[str, Any]]:
    """Ações vindas da IA em formatos aproximados → formato canónico (nunca «Operação desconhecida None»)."""
    if not isinstance(a, dict):
        return None
    a = dict(a)
    nome = a.get("acao") or a.get("action") or a.get("tipo_acao")
    if nome in OP.OPERACOES:                              # {"acao": "parede", ...} → operação do Estúdio
        return {"acao": "op", "op": {**{k: v for k, v in a.items() if k not in ("acao", "action", "tipo_acao")}, "op": nome}}
    if nome == "op" or (nome is None and any(k in a for k in _CHAVES_OP)):
        op = a.get("op")
        if isinstance(op, str):                           # {"acao": "op", "op": "cobertura", "tipo": ...}
            return {"acao": "op", "op": {**{k: v for k, v in a.items() if k not in ("acao", "op")}, "op": op}}
        if isinstance(op, dict):
            op = dict(op)
            if not op.get("op"):
                cand = next((op.get(k) for k in ("operacao", "operation", "tipo_op", "acao", "nome_op") if op.get(k) in OP.OPERACOES), None)
                if cand:
                    op["op"] = cand
                elif set(op) & set(MAT.ACABAMENTOS) and not op.get("nome"):
                    op["op"] = "materiais"
                elif set(op) & {"pavimento", "parede_interior", "teto", "novo_nome"} and op.get("nome"):
                    op["op"] = "divisao"
                elif op.get("tipo") in ("plana", "uma_agua", "duas_aguas", "quatro_aguas"):
                    op["op"] = "cobertura"
            if not op.get("op"):
                return None
            return {"acao": "op", "op": op}
        return None
    if nome in ("esticar", "vaos_maiores", "objeto_medidas", "forma", "estilo", "faixa_exterior", "contorno_exterior", "nota_pedido", "acesso_estrada", "jardim", "plantar_arvores", "zona_jogos", "terraco_sobre_piscina"):
        a["acao"] = nome
        return a
    return None


def executar(m: Dict[str, Any], acoes: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    from engines.atelier_archi import forma as FO
    feitos, falhas = [], []
    for i, a in enumerate(acoes, 1):
        try:
            if a["acao"] == "forma":
                if a.get("forma") == "l":
                    m, msg, av = FO.em_l(m)
                    feitos.extend(av)
                elif a.get("forma") == "retangular":
                    m, msg = FO.retangular(m)
                else:
                    raise Falha(_t("Forme en U : faites d'abord la forme en L, puis ajoutez la deuxième aile au Studio (outil Pièce).",
                                   "Forma em U: peça primeiro a forma em L e acrescente a segunda ala no Estúdio (ferramenta Sala)."))
            elif a["acao"] == "estilo":
                m, msg = FO.estilo(m, a.get("estilo"), a.get("ambito") or "tudo")
            elif a["acao"] == "esticar":
                m, msg = esticar(m, a["divisao"], float(a["metros"]), a.get("lado"))
            elif a["acao"] == "vaos_maiores":
                m, msg = vaos_maiores(m, a["divisao"], float(a.get("metros") or 0.4))
            elif a["acao"] == "objeto_medidas":
                m, msg = objeto_medidas(m, a["alvo"], float(a["largura"]), float(a["prof"]))
            elif a["acao"] == "faixa_exterior":
                m, msg = faixa_exterior(m, a.get("alvo") or "terraco", a.get("divisao"), a.get("lado"),
                                        a.get("comprimento") or "casa", a.get("prof"))
            elif a["acao"] == "contorno_exterior":
                m, msg = contorno_exterior(m, a.get("alvo") or "muro", a.get("area_m2"), a.get("margem"))
            elif a["acao"] == "acesso_estrada":
                m, msg = acesso_estrada(m, float(a.get("recuo") or 10.0), float(a.get("largura") or 6.0))
            elif a["acao"] == "jardim":
                m, msg = jardim(m, float(a.get("prof") or 12.0), int(a.get("arvores") or 4))
            elif a["acao"] == "plantar_arvores":
                m, msg = plantar_arvores(m, int(a.get("n") or 5))
            elif a["acao"] == "zona_jogos":
                m, msg = zona_jogos(m)
            elif a["acao"] == "terraco_sobre_piscina":
                m, msg = terraco_sobre_piscina(m, float(a.get("prof") or 3.0))
            elif a["acao"] == "nota_pedido":
                m, msg = nota_pedido(m, a.get("texto") or "")
            elif a["acao"] == "op":
                m, f_, x_ = OP.aplicar(m, [a["op"]])
                if x_:
                    raise Falha(x_[0])
                msg = f_[0]
            else:
                raise Falha(_t("Action inconnue.", "Ação desconhecida."))
            feitos.append(msg)
        except Exception as e:  # noqa: BLE001 — uma ação que falha nunca derruba o pedido inteiro
            falhas.append(f"{i}: {e}")
    return m, feitos, falhas


AJUDA_IA = (
    "És o editor de um modelo de casa (Estúdio de projeto). Converte o pedido em ações. Responde SÓ com JSON "
    "{\"acoes\": [...]} — no máximo 12 ações, cada uma num destes formatos EXATOS:\n"
    "{\"acao\":\"forma\",\"forma\":\"l\"|\"retangular\"} (refaz a planta em L ou retângulo com o mesmo programa);\n"
    "{\"acao\":\"estilo\",\"estilo\":\"provencal|rustico|mediterranico|moderno|minimalista|escandinavo|industrial|classico|"
    "contemporaneo|tradicional\",\"ambito\":\"interior|exterior|tudo\"};\n"
    "{\"acao\":\"esticar\",\"divisao\":NOME,\"metros\":N (negativo reduz),\"lado\":\"direita|esquerda|frente|tardoz\"|null};\n"
    "{\"acao\":\"vaos_maiores\",\"divisao\":NOME,\"metros\":N};\n"
    "{\"acao\":\"objeto_medidas\",\"alvo\":\"piscina|terraco|relvado|pergola\",\"largura\":N,\"prof\":N};\n"
    "{\"acao\":\"faixa_exterior\",\"alvo\":\"terraco|deck|caminho|relvado|piscina\",\"divisao\":NOME|null,\"lado\":"
    "\"frente|tardoz|esquerda|direita\"|null,\"comprimento\":\"casa\"|\"divisao\"|N,\"prof\":N|null} (faixa encostada a uma fachada, "
    "ex.: terraço à frente da sala a todo o comprimento da casa);\n"
    "{\"acao\":\"contorno_exterior\",\"alvo\":\"muro|caminho|relvado\",\"area_m2\":N|null,\"margem\":N|null} (muro de vedação ou "
    "faixa à volta da casa, num terreno de N m² ou a N m das fachadas);\n"
    "{\"acao\":\"acesso_estrada\",\"recuo\":N,\"largura\":N} (estrada à frente + acesso privado + caminho); "
    "{\"acao\":\"jardim\",\"prof\":N,\"arvores\":N}; {\"acao\":\"plantar_arvores\",\"n\":N}; {\"acao\":\"zona_jogos\"} "
    "(parque infantil completo); {\"acao\":\"terraco_sobre_piscina\",\"prof\":N} (andar com terraço em balanço sobre a piscina);\n"
    "{\"acao\":\"nota_pedido\",\"texto\":TEXTO} (só se nada mais for possível: o pedido fica escrito no plano);\n"
    "{\"acao\":\"op\",\"op\":{\"op\":NOME_OP, ...}} com NOME_OP e campos:\n"
    "  divisao {nome, novo_nome?, pavimento?, parede_interior?, teto?, piso?}; materiais {fachada?, cobertura?, caixilharia?, "
    "pavimento?, parede_interior?, teto?}; cobertura {tipo: plana|uma_agua|duas_aguas|quatro_aguas, inclinacao_graus?}; "
    "objeto {tipo, divisao? ou x,y, piso?, rot?, largura_m?, prof_m?}; remover_objeto {id}; vao {parede, tipo: porta|janela|portada|portao, pos_m, largura_m, "
    "altura_m?, peitoril_m?}; mudar_vao {id, largura_m?, altura_m?, pos_m?, tipo?}; remover_vao {id}; parede {piso, a:[x,y], b:[x,y], "
    "tipo?}; remover_parede {id}; tipo_parede {id, tipo}; sala {piso, x, y, nome}; pe_direito {piso, valor}; piso_adicionar {}; "
    "piso_remover {piso}; escada {piso, divisao? ou x,y, tipo?}; remover_escada {id}; nota {piso, x, y, texto}.\n"
    "O campo \"op\" dentro de \"op\" é OBRIGATÓRIO. Usa só nomes de divisões, ids de paredes/vãos/objetos e códigos de "
    "acabamentos que aparecem no contexto. Unidades em metros. O pedido pode vir em português, francês ou outra língua, com "
    "erros de escrita, em maiúsculas ou ser estranho: interpreta-o SEMPRE da forma mais plausível e executa-o por completo, "
    "decidindo sozinho as medidas e posições em falta (nunca perguntes). Nunca devolvas uma lista vazia: se nenhuma ação "
    "for possível, devolve uma ação nota_pedido com o pedido."
)


def contexto_ia(m: Dict[str, Any]) -> str:
    """Resumo do modelo para a IA: divisões, paredes, vãos, objetos e códigos de acabamentos (limitado em tamanho)."""
    m = EP.normalizar(m)
    der = EP.derivar(m)
    linhas = ["Pisos: " + ", ".join(f"{p['id']} ({p['nome']})" for p in m["pisos"])]
    linhas.append("Divisões: " + "; ".join(
        f"{d['nome']} [{d['piso']}, {d['area_m2']:.1f} m², x {min(p[0] for p in d['pts']):.2f}–{max(p[0] for p in d['pts']):.2f}, "
        f"y {min(p[1] for p in d['pts']):.2f}–{max(p[1] for p in d['pts']):.2f}]" for d in der["divisoes"]))
    linhas.append("Paredes: " + "; ".join(f"{w['id']} {w['piso']} {w['a']}→{w['b']} {w['tipo']}" for w in m["paredes"][:80]))
    linhas.append("Vãos: " + "; ".join(f"{v['id']} {v['tipo']} parede {v['parede']} pos {v['pos_m']} larg {v['largura_m']}" for v in m["vaos"][:80]))
    linhas.append("Objetos: " + "; ".join(f"{o['id']} {o['tipo']} ({o['x']},{o['y']})" for o in (m.get("objetos") or [])[:40]))
    linhas.append("Cobertura: " + str((m.get("cobertura") or {}).get("tipo")))
    from engines.estudio_projeto.objetos import OBJETOS
    linhas.append("Tipos de objeto (op objeto aceita também largura_m, prof_m ≤ 40 e rot): "
                  + ", ".join(f"{k} ({v['nome']})" for k, v in OBJETOS.items()))
    try:
        _, x0, y0, x1, y1 = _casa_limites(m)
        linhas.append(f"Casa (faces exteriores): x {x0:.2f}–{x1:.2f}, y {y0:.2f}–{y1:.2f} (frente = y mínimo, tardoz = y máximo)")
    except Falha:
        pass
    linhas.append("Acabamentos: " + " | ".join(f"{k}: " + ", ".join(x["id"] for x in v) for k, v in MAT.ACABAMENTOS.items()))
    return "\n".join(linhas)[:14000]
