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
    if not cand:
        raise Falha(_t(f"Pas d'objet « {tipo_ou_nome} » dans le projet.", f"Não há «{tipo_ou_nome}» no projeto."))
    o = cand[0]
    o["largura_m"], o["prof_m"] = float(largura), float(prof)
    return EP.normalizar(m), _t(f"{OBJETOS[o['tipo']]['nome']} : {largura:g} × {prof:g} m.", f"{OBJETOS[o['tipo']]['nome']}: {largura:g} × {prof:g} m.")


# ------------------------------------------------------------------------------------------------ leitura da frase
_N = r"(\d+(?:[.,]\d+)?)"
_UN = r"\s*(m|metros?|metres?|meters?|cm|centimetros?|centimetres?)?"
_LADOS = [("direita", r"direita|droite|right"), ("esquerda", r"esquerda|gauche|left"),
          ("tardoz", r"tardoz|tras|traseir|arriere|jardim|jardin|back|rear"), ("frente", r"frente|avant|rua|front|street")]
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
        sem_nome = re.sub(r"\b(?!de\b|em\b|by\b|of\b|par\b)[a-z]+\s+\d+\b(?![.,]\d)(?!\s*(?:m\b|cm|metro|metre|meter|x))", " ", f)   # «quarto 2» não é uma medida
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
    if nome in ("esticar", "vaos_maiores", "objeto_medidas", "forma", "estilo"):
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
            elif a["acao"] == "op":
                m, f_, x_ = OP.aplicar(m, [a["op"]])
                if x_:
                    raise Falha(x_[0])
                msg = f_[0]
            else:
                raise Falha(_t("Action inconnue.", "Ação desconhecida."))
            feitos.append(msg)
        except (Falha, FO.Falha, OP.Falha, EP.ErroModelo, KeyError, ValueError, TypeError, StopIteration) as e:
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
    "{\"acao\":\"op\",\"op\":{\"op\":NOME_OP, ...}} com NOME_OP e campos:\n"
    "  divisao {nome, novo_nome?, pavimento?, parede_interior?, teto?, piso?}; materiais {fachada?, cobertura?, caixilharia?, "
    "pavimento?, parede_interior?, teto?}; cobertura {tipo: plana|uma_agua|duas_aguas|quatro_aguas, inclinacao_graus?}; "
    "objeto {tipo, divisao? ou x,y, piso?, rot?}; remover_objeto {id}; vao {parede, tipo: porta|janela|portada|portao, pos_m, largura_m, "
    "altura_m?, peitoril_m?}; mudar_vao {id, largura_m?, altura_m?, pos_m?, tipo?}; remover_vao {id}; parede {piso, a:[x,y], b:[x,y], "
    "tipo?}; remover_parede {id}; tipo_parede {id, tipo}; sala {piso, x, y, nome}; pe_direito {piso, valor}; piso_adicionar {}; "
    "piso_remover {piso}; escada {piso, divisao? ou x,y, tipo?}; remover_escada {id}; nota {piso, x, y, texto}.\n"
    "O campo \"op\" dentro de \"op\" é OBRIGATÓRIO. Usa só nomes de divisões, ids de paredes/vãos/objetos e códigos de "
    "acabamentos que aparecem no contexto. Unidades em metros. Se uma parte do pedido não for possível, ignora só essa parte. "
    "Se nada for possível, devolve {\"acoes\": []}."
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
    linhas.append("Acabamentos: " + " | ".join(f"{k}: " + ", ".join(x["id"] for x in v) for k, v in MAT.ACABAMENTOS.items()))
    return "\n".join(linhas)[:14000]
