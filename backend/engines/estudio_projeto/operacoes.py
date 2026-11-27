"""Operações sobre o modelo único, para o Assistente (e a Aurora) editarem o Estúdio por pedidos em linguagem simples.

Cada operação é um dicionário {"op": ..., ...}. `aplicar` devolve o modelo novo, a lista do que foi feito e a lista do
que não pôde ser feito (com o motivo). Nada é adivinhado: uma operação que não encontra a parede, a divisão ou o
material pedido falha com uma mensagem clara em vez de alterar outra coisa.
"""
from __future__ import annotations

import copy
import math
import unicodedata
from typing import Any, Dict, List, Tuple

from engines.estudio_projeto import materiais as MAT
from engines.estudio_projeto import objetos as OBJ
from engines.estudio_projeto.derivar import derivar
from engines.estudio_projeto.modelo import ACABAMENTOS_DIVISAO, COBERTURAS, LIM, TIPOS_ESCADA, TIPOS_VAO, VAO_BASE, normalizar

OPERACOES = ("parede", "sala", "remover_parede", "tipo_parede", "vao", "mudar_vao", "remover_vao", "cobertura", "materiais", "divisao",
             "piso_adicionar", "piso_remover", "pe_direito", "escada", "remover_escada", "objeto", "remover_objeto", "nota")


class Falha(ValueError):
    pass


def _limpo(s: Any) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


def resolver_acabamento(tipo: str, texto: Any) -> str:
    """Identificador de um acabamento a partir do identificador ou de parte do nome («granito», «soalho de carvalho»)."""
    t = _limpo(texto)
    lista = MAT.ACABAMENTOS[tipo]
    for x in lista:
        if _limpo(x["id"]) == t or _limpo(x["nome"]) == t:
            return x["id"]
    achados = [x for x in lista if t and (t in _limpo(x["nome"]) or t.replace(" ", "_") in x["id"])]
    if not achados:
        raise Falha(f"Não conheço o acabamento «{texto}» para {tipo.replace('_', ' ')}.")
    return min(achados, key=lambda x: len(x["nome"]))["id"]


def _novo_id(prefixo: str, existentes: List[dict]) -> str:
    usados = {x["id"] for x in existentes}
    n = len(existentes) + 1
    while f"{prefixo}{n}" in usados:
        n += 1
    return f"{prefixo}{n}"


def _piso(m: dict, ref: Any) -> str:
    if ref in (None, ""):
        return m["pisos"][0]["id"]
    for k, p in enumerate(m["pisos"]):
        if ref == p["id"] or ref == k or str(ref) == str(k) or _limpo(ref) == _limpo(p["nome"]):
            return p["id"]
    raise Falha(f"Piso «{ref}» não existe.")


def _tipo_parede(m: dict, ref: Any, por_omissao: str) -> str:
    if not ref:
        return por_omissao
    if ref in m["tipos_parede"]:
        return ref
    if ref in MAT.PAREDES_TIPO:
        m["tipos_parede"][ref] = copy.deepcopy(MAT.PAREDES_TIPO[ref])
        return ref
    t = _limpo(ref)
    for tid, tp in {**MAT.PAREDES_TIPO, **m["tipos_parede"]}.items():
        if t in _limpo(tp["nome"]):
            m["tipos_parede"].setdefault(tid, copy.deepcopy(tp))
            return tid
    raise Falha(f"Não conheço o tipo de parede «{ref}».")


def _parede_do_lado(m: dict, piso: str, lado: str) -> dict:
    ws = [w for w in m["paredes"] if w["piso"] == piso and m["tipos_parede"][w["tipo"]]["exterior"]]
    if not ws:
        raise Falha("Este piso não tem paredes exteriores.")
    horizontal = lado in ("frente", "tardoz")
    cand = [w for w in ws if (abs(w["a"][1] - w["b"][1]) < 0.05) == horizontal and (abs(w["a"][0] - w["b"][0]) < 0.05) != horizontal]
    if not cand:
        raise Falha(f"Não encontrei uma parede exterior no lado «{lado}».")
    chave = {"frente": lambda w: w["a"][1], "tardoz": lambda w: -w["a"][1], "esquerda": lambda w: w["a"][0], "direita": lambda w: -w["a"][0]}[lado]
    extremo = min(chave(w) for w in cand)
    return max((w for w in cand if chave(w) - extremo < 0.3), key=lambda w: math.hypot(w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]))


def _posicao_livre(m: dict, w: dict, largura: float, pedida: Any) -> float:
    L = math.hypot(w["b"][0] - w["a"][0], w["b"][1] - w["a"][1])
    meio = largura / 2 + 0.05
    if L < 2 * meio:
        raise Falha(f"Um vão de {largura:.2f} m não cabe na parede {w['id']} ({L:.2f} m).")
    outros = [v for v in m["vaos"] if v["parede"] == w["id"]]
    livre = lambda x: all(abs(v["pos_m"] - x) >= (v["largura_m"] + largura) / 2 + 0.02 for v in outros)  # noqa: E731
    alvo = max(meio, min(L - meio, float(pedida))) if pedida is not None else L / 2
    for k in range(0, 400):
        for x in (alvo + k * 0.05, alvo - k * 0.05):
            if meio - 1e-9 <= x <= L - meio + 1e-9 and livre(x):
                return round(x, 3)
    raise Falha(f"Não há espaço livre para o vão na parede {w['id']}.")


def _divisao(m: dict, nome: Any, piso: Any = None) -> dict:
    d = derivar(normalizar(m))
    alvo = _limpo(nome)
    cand = [dv for dv in d["divisoes"] if (piso in (None, "") or dv["piso"] == _piso(m, piso))
            and (alvo == _limpo(dv["nome"]) or (alvo and alvo in _limpo(dv["nome"])))]
    if not cand:
        raise Falha(f"Não encontrei a divisão «{nome}».")
    return min(cand, key=lambda dv: len(dv["nome"]))


def _um(m: dict, o: Dict[str, Any]) -> str:
    op = o.get("op")
    if op == "parede":
        piso = _piso(m, o.get("piso"))
        a, b = [float(v) for v in o["a"]], [float(v) for v in o["b"]]
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 0.1:
            raise Falha("Parede com menos de 10 cm.")
        wid = _novo_id("w", m["paredes"])
        m["paredes"].append({"id": wid, "piso": piso, "a": a, "b": b, "tipo": _tipo_parede(m, o.get("tipo"), "int_12")})
        return f"Parede {wid} criada ({math.hypot(b[0] - a[0], b[1] - a[1]):.2f} m)."
    if op == "sala":
        piso = _piso(m, o.get("piso"))
        x0, y0, x1, y1 = (float(o[k]) for k in ("x0", "y0", "x1", "y1"))
        if abs(x1 - x0) < 0.6 or abs(y1 - y0) < 0.6:
            raise Falha("Sala com menos de 60 cm de lado.")
        tipo = _tipo_parede(m, o.get("tipo"), "int_12")
        for pa, pb in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            m["paredes"].append({"id": _novo_id("w", m["paredes"]), "piso": piso, "a": list(pa), "b": list(pb), "tipo": tipo})
        if o.get("nome"):
            m["rotulos"].append({"piso": piso, "x": (x0 + x1) / 2, "y": (y0 + y1) / 2, "nome": str(o["nome"])[:40]})
        return f"Sala de {abs(x1 - x0):.2f} × {abs(y1 - y0):.2f} m (eixos) criada."
    if op == "remover_parede":
        if not any(w["id"] == o.get("id") for w in m["paredes"]):
            raise Falha(f"Parede «{o.get('id')}» não existe.")
        m["paredes"] = [w for w in m["paredes"] if w["id"] != o["id"]]
        m["vaos"] = [v for v in m["vaos"] if v["parede"] != o["id"]]
        return f"Parede {o['id']} removida (e os seus vãos)."
    if op == "tipo_parede":
        de = o.get("de") or "exteriores"
        tid = _tipo_parede(m, o.get("tipo"), "")
        if not tid:
            raise Falha("Falta o tipo de parede.")
        alvo = [w for w in m["paredes"] if w["id"] == de] or \
            [w for w in m["paredes"] if m["tipos_parede"][w["tipo"]]["exterior"] == (_limpo(de).startswith("ext"))]
        if not alvo:
            raise Falha(f"Não encontrei paredes «{de}».")
        for w in alvo:
            w["tipo"] = tid
        return f"{len(alvo)} parede(s) passam a «{m['tipos_parede'][tid]['nome']}»."
    if op == "vao":
        tipo = o.get("tipo") if o.get("tipo") in TIPOS_VAO else "janela"
        if o.get("parede"):
            w = next((x for x in m["paredes"] if x["id"] == o["parede"]), None)
            if not w:
                raise Falha(f"Parede «{o['parede']}» não existe.")
        else:
            w = _parede_do_lado(m, _piso(m, o.get("piso")), o.get("lado") if o.get("lado") in ("frente", "tardoz", "esquerda", "direita") else "frente")
        base = VAO_BASE[tipo]
        larg = float(o.get("largura_m") or base["largura_m"])
        vid = _novo_id("v", m["vaos"])
        novo = {"id": vid, "parede": w["id"], "tipo": tipo, "pos_m": _posicao_livre(m, w, larg, o.get("pos_m")), "largura_m": larg,
                "altura_m": float(o.get("altura_m") or base["altura_m"]),
                "peitoril_m": float(o["peitoril_m"]) if o.get("peitoril_m") is not None else base["peitoril_m"]}
        for k in ("modelo", "protecao"):
            if o.get(k):
                novo[k] = str(o[k])
        if o.get("caixilharia"):
            novo["caixilharia"] = resolver_acabamento("caixilharia", o["caixilharia"])
        m["vaos"].append(novo)
        return f"{tipo.capitalize()} {vid} de {larg:.2f} × {novo['altura_m']:.2f} m colocada na parede {w['id']}."
    if op == "mudar_vao":
        v = next((x for x in m["vaos"] if x["id"] == o.get("id")), None)
        if not v:
            raise Falha(f"Vão «{o.get('id')}» não existe.")
        for k in ("largura_m", "altura_m", "peitoril_m", "pos_m"):
            if o.get(k) is not None:
                v[k] = float(o[k])
        for k in ("modelo", "protecao"):
            if k in o:
                v[k] = str(o[k] or "")
        if o.get("tipo") in TIPOS_VAO:
            v["tipo"] = o["tipo"]
        if o.get("caixilharia"):
            v["caixilharia"] = resolver_acabamento("caixilharia", o["caixilharia"])
        return f"Vão {v['id']} alterado."
    if op == "remover_vao":
        if not any(v["id"] == o.get("id") for v in m["vaos"]):
            raise Falha(f"Vão «{o.get('id')}» não existe.")
        m["vaos"] = [v for v in m["vaos"] if v["id"] != o["id"]]
        return f"Vão {o['id']} removido."
    if op == "cobertura":
        if o.get("tipo") is not None and o["tipo"] not in COBERTURAS:
            raise Falha(f"Tipo de cobertura desconhecido «{o['tipo']}» (plana, uma_agua, duas_aguas, quatro_aguas).")
        for k in ("tipo", "inclinacao_graus", "beiral_m", "cumeeira", "lado_baixo"):
            if o.get(k) is not None:
                m["cobertura"][k] = o[k]
        return f"Cobertura: {m['cobertura']['tipo'].replace('_', ' ')}, {float(m['cobertura']['inclinacao_graus']):.0f}°."
    if op == "materiais":
        feitos = []
        for k in MAT.ACABAMENTOS:
            if o.get(k):
                m["materiais"][k] = resolver_acabamento(k, o[k])
                feitos.append(f"{k.replace('_', ' ')}: {MAT.acabamento(k, m['materiais'][k])['nome']}")
        if not feitos:
            raise Falha("Nenhum material indicado.")
        return "Acabamentos da casa — " + "; ".join(feitos) + "."
    if op == "divisao":
        dv = _divisao(m, o.get("nome"), o.get("piso"))
        from shapely.geometry import Point, Polygon
        pl = Polygon(dv["pts"])
        rt = next((r for r in m["rotulos"] if r["piso"] == dv["piso"] and pl.contains(Point(r["x"], r["y"]))), None)
        if rt is None:
            rt = {"piso": dv["piso"], "x": dv["centro"][0], "y": dv["centro"][1], "nome": dv["nome"]}
            m["rotulos"].append(rt)
        feitos = []
        if o.get("novo_nome"):
            rt["nome"] = str(o["novo_nome"])[:40]
            feitos.append(f"nome «{rt['nome']}»")
        for k in ACABAMENTOS_DIVISAO:
            if o.get(k):
                rt[k] = resolver_acabamento(k, o[k])
                feitos.append(f"{k.replace('_', ' ')}: {MAT.acabamento(k, rt[k])['nome']}")
        if not feitos:
            raise Falha("Nada para alterar na divisão.")
        return f"Divisão «{dv['nome']}» — " + "; ".join(feitos) + "."
    if op == "piso_adicionar":
        if len(m["pisos"]) >= LIM["pisos"]:
            raise Falha(f"Máximo de {LIM['pisos']} pisos.")
        n = len(m["pisos"])
        base = m["pisos"][-1]
        pid = f"p{n}" if all(p["id"] != f"p{n}" for p in m["pisos"]) else f"p{n}b"
        mapa = {}
        for i, w in enumerate([w for w in m["paredes"] if w["piso"] == base["id"]], 1):
            mapa[w["id"]] = f"{pid}_w{i}"
            m["paredes"].append({**w, "id": mapa[w["id"]], "piso": pid})
        for i, v in enumerate([v for v in m["vaos"] if v["parede"] in mapa and v["tipo"] == "janela"], 1):
            m["vaos"].append({**v, "id": f"{pid}_v{i}", "parede": mapa[v["parede"]]})
        m["pisos"].append({"id": pid, "nome": f"{n}.º andar", "pe_direito_m": base["pe_direito_m"], "laje_m": base["laje_m"]})
        return f"{n}.º andar criado com as paredes e janelas do piso de baixo."
    if op == "piso_remover":
        if len(m["pisos"]) <= 1:
            raise Falha("O edifício tem de ter pelo menos um piso.")
        pid = m["pisos"][-1]["id"]
        ids = {w["id"] for w in m["paredes"] if w["piso"] == pid}
        novo_topo = m["pisos"][-2]["id"]
        m["pisos"] = m["pisos"][:-1]
        m["paredes"] = [w for w in m["paredes"] if w["piso"] != pid]
        m["vaos"] = [v for v in m["vaos"] if v["parede"] not in ids]
        for k in ("rotulos", "objetos", "cotas", "notas"):
            m[k] = [x for x in m.get(k) or [] if x["piso"] != pid]
        m["escadas"] = [e for e in m["escadas"] if e["piso"] not in (pid, novo_topo)]
        return "Último piso removido."
    if op == "pe_direito":
        pid = _piso(m, o.get("piso"))
        next(p for p in m["pisos"] if p["id"] == pid)["pe_direito_m"] = float(o["valor"])
        return f"Pé-direito do piso {pid}: {float(o['valor']):.2f} m."
    if op == "escada":
        piso = _piso(m, o.get("piso"))
        if piso == m["pisos"][-1]["id"]:
            raise Falha("A escada sobe do piso indicado para o de cima: adicione primeiro o piso de cima.")
        eid = _novo_id("e", m["escadas"])
        if o.get("divisao"):
            dv = _divisao(m, o["divisao"], piso)
            x, y = dv["centro"]
        else:
            x, y = float(o["x"]), float(o["y"])
        m["escadas"].append({"id": eid, "piso": piso, "tipo": o.get("tipo") if o.get("tipo") in TIPOS_ESCADA else "u", "x": x, "y": y,
                             "rot": float(o.get("rot") or 0), "largura_m": float(o.get("largura_m") or 0.9),
                             "cobertor_m": float(o.get("cobertor_m") or 0.25), "sentido": o.get("sentido") or "dir"})
        return f"Escada {eid} colocada."
    if op == "remover_escada":
        if not any(e["id"] == o.get("id") for e in m["escadas"]):
            raise Falha(f"Escada «{o.get('id')}» não existe.")
        m["escadas"] = [e for e in m["escadas"] if e["id"] != o["id"]]
        return f"Escada {o['id']} removida."
    if op == "objeto":
        t = _limpo(o.get("tipo"))
        pal = t.replace("_", " ").split()
        tipo = o.get("tipo") if o.get("tipo") in OBJ.OBJETOS else next(
            (k for k, v in OBJ.OBJETOS.items() if pal and all(x in _limpo(v["nome"]) or x in k for x in pal)), None)
        if not tipo:
            raise Falha(f"Não conheço o objeto «{o.get('tipo')}».")
        if o.get("divisao"):
            dv = _divisao(m, o["divisao"], o.get("piso"))
            piso, (x, y) = dv["piso"], dv["centro"]
        else:
            piso, x, y = _piso(m, o.get("piso")), float(o["x"]), float(o["y"])
        oid = _novo_id("o", m["objetos"])
        novo = {"id": oid, "piso": piso, "tipo": tipo, "x": x, "y": y, "rot": float(o.get("rot") or 0)}
        for k in ("largura_m", "prof_m"):               # medidas próprias (opcionais; por omissão as do catálogo)
            if o.get(k):
                novo[k] = float(o[k])
        m["objetos"].append(novo)
        return f"{OBJ.OBJETOS[tipo]['nome']} ({oid}) colocado."
    if op == "remover_objeto":
        if not any(x["id"] == o.get("id") for x in m["objetos"]):
            raise Falha(f"Objeto «{o.get('id')}» não existe.")
        m["objetos"] = [x for x in m["objetos"] if x["id"] != o["id"]]
        return f"Objeto {o['id']} removido."
    if op == "nota":
        piso = _piso(m, o.get("piso"))
        m["notas"].append({"id": _novo_id("n", m["notas"]), "piso": piso, "x": float(o["x"]), "y": float(o["y"]), "texto": str(o.get("texto") or "")[:120]})
        return "Nota acrescentada."
    raise Falha(f"Operação desconhecida «{op}». Disponíveis: {', '.join(OPERACOES)}.")


def aplicar(modelo: Dict[str, Any], operacoes: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Aplica as operações por ordem. Uma operação que falha não altera o modelo e não impede as seguintes."""
    m = normalizar(copy.deepcopy(modelo))
    feitos, falhas = [], []
    for i, o in enumerate(operacoes or [], 1):
        ensaio = copy.deepcopy(m)
        try:
            if not isinstance(o, dict):
                raise Falha("Operação mal formada.")
            msg = _um(ensaio, o)
            m = normalizar(ensaio)                    # a operação só fica se o modelo continuar válido
            feitos.append(msg)
        except (Falha, KeyError, TypeError, ValueError, StopIteration) as e:
            motivo = str(e) if isinstance(e, (Falha, ValueError)) and str(e) else f"dados em falta ({e})"
            falhas.append(f"Operação {i} ({(o or {}).get('op') if isinstance(o, dict) else '?'}): {motivo}")
    return m, feitos, falhas


def resumo(m: Dict[str, Any], d: Dict[str, Any]) -> Dict[str, Any]:
    """O estado do modelo em poucas linhas, com os identificadores de que as operações precisam."""
    md = d["medicoes"]
    return {
        "pisos": [{"id": p["id"], "nome": p["nome"], "area_bruta_m2": p["area_bruta_m2"], "pe_direito_m": p["pe_direito_m"]} for p in d["pisos"]],
        "divisoes": [{"piso": dv["piso"], "nome": dv["nome"], "area_m2": dv["area_m2"], "pavimento": dv["acabamentos"]["pavimento"]["nome"],
                      "paredes": dv["acabamentos"]["parede_interior"]["nome"], "teto": dv["acabamentos"]["teto"]["nome"]} for dv in d["divisoes"]],
        "paredes_exteriores": [{"id": w["id"], "piso": w["piso"], "comprimento_m": w["comprimento_m"], "a": w["a"], "b": w["b"]}
                               for w in d["paredes"] if w["exterior"]],
        "n_paredes_interiores": sum(1 for w in d["paredes"] if not w["exterior"]),
        "mapa_vaos": [{k: l[k] for k in ("codigo", "tipo", "modelo", "largura_m", "altura_m", "quantidade", "caixilharia", "ids")} for l in md["mapa_vaos"]],
        "escadas": md["escadas"], "objetos": md["objetos"],
        "cobertura": md["cobertura"], "acabamentos": md["acabamentos"], "totais": md["totais"], "area_implantacao_m2": md["area_implantacao_m2"],
        "erros": [e["msg"] for e in d["erros"]], "avisos": [a["msg"] for a in d["avisos"]],
        "limites_xy": d.get("limites"),
    }
