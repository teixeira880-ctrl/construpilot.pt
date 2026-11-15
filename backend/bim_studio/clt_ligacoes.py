"""Ligações do CLT contadas peça a peça, como no motor LSF: cada cantoneira, cada ancoragem, cada parafuso e cada
metro de fita sai da geometria medida (eixos das paredes, vãos, juntas, faixas de laje e cobertura), nunca de um rácio.

Entrada: pisos com as paredes (eixo, espessura, altura, vãos) e as faixas de laje / cobertura (retângulos prensados).
Saída: a lista de ligadores com posição, a lista de juntas com comprimento e parafusos, os totais por produto e os
avisos. Só matemática: não depende de shapely nem do resto do motor CLT, e o mesmo desenho dá sempre os mesmos números.

O que é medido e o que é hipótese:
  - medido ......... onde há parede, porta, canto, encontro de paredes, apoio de laje e junta entre faixas;
  - hipótese ....... o espaçamento e o número de fixações por ligador (PARAMETROS): são valores de pré-dimensionamento,
                     editáveis, que o projeto de estabilidade e a ficha do fabricante dos ligadores substituem.
"""
from __future__ import annotations

import math

VERSAO = "clt-ligacoes-1.0"
SNAP_M = 0.005

PARAMETROS = {
    "cantoneira_esp_m": 1.00,          # cantoneiras de corte na base da parede
    "cantoneira_parafusos": 10,        # parafusos de cada cantoneira na parede CLT
    "cantoneira_ancoragens": 2,        # ancoragens de cada cantoneira ao betão (piso térreo)
    "holddown_min_m": 0.60,            # troço de parede mais curto do que isto leva uma só ancoragem de tração
    "holddown_parafusos": 15,          # parafusos de cada hold-down na parede CLT
    "troco_min_m": 0.30,               # troço de parede mais curto do que isto não leva ligador (aviso)
    "laje_parede_esp_m": 0.25,         # parafusos da laje / cobertura para o topo da parede
    "canto_esp_m": 0.30,               # parafusos das juntas verticais parede–parede
    "faixa_esp_m": 0.30,               # parafusos das juntas entre faixas de laje / cobertura
    "faixa_filas": 2,                  # filas de parafusos na junta entre faixas (meia-madeira ou tábua de cobertura)
    "porta_peitoril_max_m": 0.05,      # vão com peitoril até aqui corta a base da parede (porta)
}
_HIP = "hipótese de pré-dimensionamento, a confirmar pelo projeto de estabilidade e pela ficha do fabricante"
FONTES = {k: _HIP for k in PARAMETROS}
FONTES["porta_peitoril_max_m"] = "regra de leitura: um vão que começa no pavimento interrompe a base da parede"

PRODUTOS = {        # chave: (nome pt, nome en, unidade)
    "cantoneira": ("Cantoneira de corte na base da parede", "Shear angle bracket at the wall base", "un"),
    "holddown": ("Ancoragem de tração (hold-down)", "Hold-down", "un"),
    "paraf_ligador": ("Parafuso de ligador na parede CLT", "Connector screw into the CLT wall", "un"),
    "anc_betao": ("Ancoragem da cantoneira ao betão", "Bracket anchor into concrete", "un"),
    "anc_m16": ("Varão / ancoragem M16 do hold-down", "M16 rod / anchor of the hold-down", "un"),
    "paraf_piso": ("Parafuso de ligador na laje CLT de baixo", "Connector screw into the CLT slab below", "un"),
    "paraf_laje_parede": ("Parafuso estrutural laje / cobertura → topo da parede", "Structural screw slab / roof → wall top", "un"),
    "paraf_canto": ("Parafuso estrutural parede–parede (junta vertical)", "Structural screw wall–wall (vertical joint)", "un"),
    "paraf_faixa": ("Parafuso da junta entre faixas", "Screw of the joint between strips", "un"),
    "fita": ("Fita de estanquidade ao ar nas juntas", "Air-tightness tape on the joints", "m"),
}


def _g(o, *names, default=None):
    """Campo de um dicionário ou de um objeto (WallAxis / Opening do clt_walls), pelo primeiro nome que existir."""
    for n in names:
        v = o.get(n) if isinstance(o, dict) else getattr(o, n, None)
        if v is not None:
            return v
    return default


def _parede(w):
    x1, y1, x2, y2 = (float(_g(w, k)) for k in ("x1", "y1", "x2", "y2"))
    vaos = [{"a": float(_g(o, "offset_m")), "l": float(_g(o, "width_m", "largura_m")), "peitoril": float(_g(o, "sill_m", "peitoril_m", default=0.0))}
            for o in (_g(w, "openings", "vaos", default=[]) or [])]
    return {"id": str(_g(w, "id")), "x1": x1, "y1": y1, "x2": x2, "y2": y2, "L": math.hypot(x2 - x1, y2 - y1),
            "t": float(_g(w, "thickness_mm", "espessura_mm")) / 1000, "h": float(_g(w, "height_m", "altura_m")),
            "z": float(_g(w, "base_z_m", default=0.0)), "vaos": vaos}


def _trocos_base(w, peitoril_max):
    """Troços da base da parede onde há madeira: o comprimento menos as portas."""
    cortes = sorted((v["a"], v["a"] + v["l"]) for v in w["vaos"] if v["peitoril"] <= peitoril_max)
    out, pos = [], 0.0
    for a, b in cortes:
        if a - pos > 1e-6:
            out.append((pos, a))
        pos = max(pos, b)
    if w["L"] - pos > 1e-6:
        out.append((pos, w["L"]))
    return out


def _ponto(w, s):
    return (round(w["x1"] + (w["x2"] - w["x1"]) * s / w["L"], 3), round(w["y1"] + (w["y2"] - w["y1"]) * s / w["L"], 3))


def _dist_seg(p, w):
    """Distância do ponto ao eixo da parede e posição ao longo do eixo (0…L)."""
    ux, uy = (w["x2"] - w["x1"]) / w["L"], (w["y2"] - w["y1"]) / w["L"]
    s = (p[0] - w["x1"]) * ux + (p[1] - w["y1"]) * uy
    sc = min(max(s, 0.0), w["L"])
    return math.hypot(p[0] - (w["x1"] + ux * sc), p[1] - (w["y1"] + uy * sc)), s


def _cruzam(a, b):
    """Os dois eixos cruzam-se no interior de ambos."""
    d = (a["x2"] - a["x1"]) * (b["y2"] - b["y1"]) - (a["y2"] - a["y1"]) * (b["x2"] - b["x1"])
    if abs(d) < 1e-12:
        return False
    t = ((b["x1"] - a["x1"]) * (b["y2"] - b["y1"]) - (b["y1"] - a["y1"]) * (b["x2"] - b["x1"])) / d
    u = ((b["x1"] - a["x1"]) * (a["y2"] - a["y1"]) - (b["y1"] - a["y1"]) * (a["x2"] - a["x1"])) / d
    return 0 < t < 1 and 0 < u < 1


def juntas_verticais(paredes):
    """Encontros parede–parede: L (as duas acabam uma na outra), T (uma acaba na outra) ou X (cruzam-se)."""
    out = []
    for i, a in enumerate(paredes):
        for b in paredes[i + 1:]:
            cos = abs((a["x2"] - a["x1"]) * (b["x2"] - b["x1"]) + (a["y2"] - a["y1"]) * (b["y2"] - b["y1"])) / (a["L"] * b["L"])
            if cos > 0.999:
                continue                                       # paredes em linha: é a mesma peça ou uma junta de topo de fabrico
            alcance = (a["t"] + b["t"]) / 2 + SNAP_M
            a_acaba = [p for p in ((a["x1"], a["y1"]), (a["x2"], a["y2"])) if _dist_seg(p, b)[0] <= alcance]
            b_acaba = [p for p in ((b["x1"], b["y1"]), (b["x2"], b["y2"])) if _dist_seg(p, a)[0] <= alcance]
            if a_acaba and b_acaba:
                tipo, onde = "L", a_acaba[0]
            elif a_acaba or b_acaba:
                tipo, onde = "T", (a_acaba or b_acaba)[0]
            elif _cruzam(a, b):
                tipo, onde = "X", None
            else:
                continue
            altura = min(a["z"] + a["h"], b["z"] + b["h"]) - max(a["z"], b["z"])
            if altura > 0:
                out.append({"tipo": tipo, "paredes": [a["id"], b["id"]], "altura_m": round(altura, 4),
                            "xy": [round(onde[0], 3), round(onde[1], 3)] if onde else None})
    return out


def _coberto(w, faixas):
    """Comprimento do eixo da parede que fica debaixo das faixas (soma dos troços dentro de cada retângulo)."""
    total = 0.0
    dx, dy = w["x2"] - w["x1"], w["y2"] - w["y1"]
    for f in faixas:
        x0, y0, x1, y1 = (f["ret"][0] - SNAP_M, f["ret"][1] - SNAP_M, f["ret"][2] + SNAP_M, f["ret"][3] + SNAP_M)
        t0, t1 = 0.0, 1.0                                      # Liang–Barsky: parte do segmento dentro do retângulo
        for p, q in ((-dx, w["x1"] - x0), (dx, x1 - w["x1"]), (-dy, w["y1"] - y0), (dy, y1 - w["y1"])):
            if abs(p) < 1e-12:
                if q < 0:
                    t0, t1 = 1.0, 0.0
                    break
                continue
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
        if t1 > t0:
            total += (t1 - t0) * w["L"]
    return min(total, w["L"])


def juntas_faixas(faixas):
    """Arestas comuns entre faixas vizinhas do mesmo tipo: o comprimento da junta é a sobreposição dos dois lados."""
    out = []
    for i, a in enumerate(faixas):
        for b in faixas[i + 1:]:
            if a["tipo"] != b["tipo"]:
                continue
            ax0, ay0, ax1, ay1 = a["ret"]
            bx0, by0, bx1, by1 = b["ret"]
            comp = 0.0
            if abs(ax1 - bx0) <= SNAP_M or abs(bx1 - ax0) <= SNAP_M:
                comp = min(ay1, by1) - max(ay0, by0)
            elif abs(ay1 - by0) <= SNAP_M or abs(by1 - ay0) <= SNAP_M:
                comp = min(ax1, bx1) - max(ax0, bx0)
            if comp > SNAP_M:
                out.append({"tipo": a["tipo"], "faixas": [a["id"], b["id"]], "comprimento_m": round(comp, 4)})
    return out


def _n_linha(comprimento, esp):
    """Parafusos numa linha: um em cada ponta e os intermédios ao espaçamento máximo."""
    return math.ceil(comprimento / esp - 1e-9) + 1


def calcular(pisos: list[dict], parametros: dict | None = None) -> dict:
    """pisos: [{nome, terreo?, paredes: [parede], faixas: [{id, tipo: 'laje'|'cobertura', ret: (x0, y0, x1, y1)}]}], de baixo
    para cima. parede: dicionário ou WallAxis do clt_walls (x1, y1, x2, y2, thickness_mm, height_m, openings).
    As faixas de um piso são as que assentam nas paredes desse piso."""
    par = {**PARAMETROS, **{k: v for k, v in (parametros or {}).items() if k in PARAMETROS and v is not None}}
    ligadores, juntas, avisos, tot = [], [], [], {k: 0.0 for k in PRODUTOS}
    n = iter(range(1, 1_000_000))

    def ligador(piso, tipo, parede, xy, z, fix):
        ligadores.append({"id": f"{'CT' if tipo == 'cantoneira' else 'HD'}{next(n)}", "piso": piso, "tipo": tipo, "parede": parede,
                          "x": xy[0], "y": xy[1], "z": round(z, 3), "fixacoes": fix})
        tot[tipo] += 1
        for k, v in fix.items():
            tot[k] += v

    for i, piso in enumerate(pisos):
        nome = piso["nome"]
        terreo = piso.get("terreo", i == 0)
        paredes = [_parede(w) for w in piso.get("paredes") or []]
        faixas = [{"id": str(f["id"]), "tipo": f.get("tipo", "laje"), "ret": tuple(float(v) for v in _g(f, "ret", "ret_m"))}
                  for f in piso.get("faixas") or []]
        if not paredes:
            avisos.append(f"{nome}: sem eixos de parede medidos; as ligações deste piso não podem ser contadas peça a peça.")
        # 1. base das paredes: cantoneiras de corte ao espaçamento em cada troço com madeira, hold-down nas pontas de cada troço
        fix_ct = {"paraf_ligador": par["cantoneira_parafusos"], **({"anc_betao": par["cantoneira_ancoragens"]} if terreo
                                                                  else {"paraf_piso": par["cantoneira_parafusos"]})}
        fix_hd = {"paraf_ligador": par["holddown_parafusos"], "anc_m16": 1}
        for w in paredes:
            for a, b in _trocos_base(w, par["porta_peitoril_max_m"]):
                s = b - a
                if s < par["troco_min_m"]:
                    avisos.append(f"{nome} · {w['id']}: troço de {s:.2f} m entre vãos, sem espaço para ligador; verificar a estabilidade deste troço.")
                    continue
                k = max(1, math.ceil(s / par["cantoneira_esp_m"] - 1e-9))
                for j in range(k):
                    ligador(nome, "cantoneira", w["id"], _ponto(w, a + (j + 0.5) * s / k), w["z"], dict(fix_ct))
                pontas = [a, b] if s >= par["holddown_min_m"] else [(a + b) / 2]
                for p in pontas:
                    ligador(nome, "holddown", w["id"], _ponto(w, p), w["z"], dict(fix_hd))
        # 2. juntas verticais parede–parede
        for jv in juntas_verticais(paredes):
            filas = 2 if jv["tipo"] == "X" else 1
            q = _n_linha(jv["altura_m"], par["canto_esp_m"]) * filas
            juntas.append({"id": f"JV{next(n)}", "piso": nome, "tipo": f"parede–parede {jv['tipo']}", "entre": jv["paredes"], "comprimento_m": jv["altura_m"],
                           "parafusos": q, "produto": "paraf_canto", "fita_m": jv["altura_m"], "xy": jv["xy"]})
            tot["paraf_canto"] += q
            tot["fita"] += jv["altura_m"]
        # 3. laje / cobertura sobre o topo das paredes
        if faixas:
            for w in paredes:
                c = _coberto(w, faixas)
                if c < par["troco_min_m"]:
                    continue
                q = _n_linha(c, par["laje_parede_esp_m"])
                juntas.append({"id": f"JH{next(n)}", "piso": nome, "tipo": "laje / cobertura sobre parede", "entre": [w["id"]], "comprimento_m": round(c, 4),
                               "parafusos": q, "produto": "paraf_laje_parede", "fita_m": round(c, 4), "xy": None})
                tot["paraf_laje_parede"] += q
                tot["fita"] += c
        elif paredes:
            avisos.append(f"{nome}: sem faixas de laje ou cobertura medidas; os parafusos laje–parede e as juntas entre faixas deste piso não foram contados.")
        # 4. juntas entre faixas
        for jf in juntas_faixas(faixas):
            q = _n_linha(jf["comprimento_m"], par["faixa_esp_m"]) * par["faixa_filas"]
            juntas.append({"id": f"JF{next(n)}", "piso": nome, "tipo": f"entre faixas de {jf['tipo']}", "entre": jf["faixas"], "comprimento_m": jf["comprimento_m"],
                           "parafusos": q, "produto": "paraf_faixa", "fita_m": jf["comprimento_m"], "xy": None})
            tot["paraf_faixa"] += q
            tot["fita"] += jf["comprimento_m"]

    totais = {k: {"nome": PRODUTOS[k][0], "name": PRODUTOS[k][1], "unidade": PRODUTOS[k][2],
                  "quantidade": round(v, 2) if PRODUTOS[k][2] == "m" else int(round(v))} for k, v in tot.items() if v}
    return {"versao": VERSAO, "parametros": {k: {"valor": par[k], "fonte": FONTES[k]} for k in PARAMETROS}, "ligadores": ligadores, "juntas": juntas,
            "totais": totais, "parafusos_total": sum(v["quantidade"] for k, v in totais.items() if k.startswith("paraf_")), "avisos": avisos}


def pisos_do_calculo(q: dict) -> list[dict]:
    """Pisos para calcular() a partir do resultado de clt_only.compute: os eixos das paredes já ligadas (q['_desenhos'])
    e os retângulos das faixas de laje e cobertura (q['pecas'] com 'ret_m')."""
    staged = (q.get("_desenhos") or ([], None))[0]
    pisos = [{"nome": nome, "paredes": list(walls), "faixas": []} for nome, walls, _pecas in staged]
    por_nome = {p["nome"]: p for p in pisos}
    for p in q.get("pecas") or []:
        if p.get("ret_m") and p["elemento"] in ("Laje", "Cobertura"):
            piso = por_nome.setdefault(p["piso"], {"nome": p["piso"], "paredes": [], "faixas": []})
            if piso not in pisos:
                pisos.append(piso)
            piso["faixas"].append({"id": p["rotulo"], "tipo": p["elemento"].lower(), "ret": p["ret_m"], "espessura_mm": p.get("espessura_mm")})
    return pisos


PRECOS = {"cantoneira": 9.0, "holddown": 28.0, "paraf_ligador": 0.12, "anc_betao": 1.8, "anc_m16": 6.5, "paraf_piso": 0.12,
          "paraf_laje_parede": 0.45, "paraf_canto": 0.45, "paraf_faixa": 0.25, "fita": 1.6}      # provisórios: a empresa substitui


def linhas(resultado: dict) -> list[dict]:
    """As linhas do capítulo «ligacoes» no formato de clt_complements.lines, com a contagem peça a peça em vez dos rácios."""
    regra = {"cantoneira": ("contadas na base de cada troço de parede, ao espaçamento máximo", "counted at the base of each wall run, at the maximum spacing"),
             "holddown": ("uma em cada ponta de parede e de cada lado das portas", "one at each wall end and each side of the doors"),
             "fita": ("comprimento real de cada junta", "actual length of each joint")}
    padrao = ("contados ligador a ligador e junta a junta", "counted connector by connector and joint by joint")
    out = []
    for k, t in resultado["totais"].items():
        pt, en = regra.get(k, padrao)
        out.append({"capitulo": "ligacoes", "nome": {"pt": t["nome"], "en": t["name"]}, "quantidade": t["quantidade"], "unidade": t["unidade"],
                    "custo_un": PRECOS[k], "regra": {"pt": pt, "en": en}, "so_quantidade": False, "contado": True})
    return out
