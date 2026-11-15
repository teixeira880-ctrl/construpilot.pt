"""Motor de construção tradicional (alvenaria): cada bloco ou tijolo no seu sítio, fiada a fiada, como o motor LSF faz
com os perfis. Nenhuma quantidade vem de um rácio por m²: as unidades são assentes sobre a geometria medida das paredes,
com as juntas, os vãos, os cortes e o desencontro das fiadas, e a argamassa é o volume real das juntas.

Entrada (metros): {nome, pisos: [{nome, cota_m, paredes: [{id, x1, y1, x2, y2, tipo, altura_m, vaos: [{offset_m,
largura_m, peitoril_m, altura_m}]}]}], tipos_parede: {chave: {unidade, reboco_ext_mm, reboco_int_mm}}, junta_mm}.
Saída: unidades (posição e medida de cada uma), lintéis, resumo por material, cortes e avisos.

Âmbito desta versão: alvenaria, argamassa de assentamento, reboco e lintéis dos vãos. A estrutura de betão armado
(pilares, vigas, lajes, cintas) não é calculada aqui; uma parede é assente em todo o seu comprimento e é dito nos avisos.
"""
from __future__ import annotations

import math

VERSAO = "tradicional-1.0"
# Formatos correntes em Portugal (comprimento × altura × espessura, mm) — a confirmar com o fornecedor.
UNIDADES = {
    "tijolo_30x20x7": ("Tijolo cerâmico furado 30×20×7", 300, 200, 70), "tijolo_30x20x9": ("Tijolo cerâmico furado 30×20×9", 300, 200, 90),
    "tijolo_30x20x11": ("Tijolo cerâmico furado 30×20×11", 300, 200, 110), "tijolo_30x20x15": ("Tijolo cerâmico furado 30×20×15", 300, 200, 150),
    "tijolo_30x20x22": ("Tijolo cerâmico furado 30×20×22", 300, 200, 220),
    "bloco_50x20x10": ("Bloco de betão 50×20×10", 500, 200, 100), "bloco_50x20x15": ("Bloco de betão 50×20×15", 500, 200, 150),
    "bloco_50x20x20": ("Bloco de betão 50×20×20", 500, 200, 200), "bloco_50x20x25": ("Bloco de betão 50×20×25", 500, 200, 250),
}
TIPOS_PAREDE = {"EXT": {"unidade": "tijolo_30x20x22", "reboco_ext_mm": 20, "reboco_int_mm": 15},
                "INT": {"unidade": "tijolo_30x20x11", "reboco_ext_mm": 15, "reboco_int_mm": 15},
                "EXT_BLOCO": {"unidade": "bloco_50x20x20", "reboco_ext_mm": 20, "reboco_int_mm": 15},
                "INT_BLOCO": {"unidade": "bloco_50x20x10", "reboco_ext_mm": 15, "reboco_int_mm": 15}}
PARAMETROS = {"junta_mm": 10, "lintel_apoio_m": 0.20, "corte_min_mm": 30, "serra_mm": 3}
FONTES = {"junta_mm": "junta de argamassa corrente de 10 mm (a confirmar em obra)",
          "lintel_apoio_m": "entrega de 20 cm de cada lado do vão (hipótese, a confirmar pelo projetista)",
          "corte_min_mm": "um resto menor do que isto é fechado com argamassa, não com um corte",
          "serra_mm": "espessura do disco, perdida em cada corte"}
SNAP = 0.005


def _parede(w, tipos):
    tipo = tipos.get(w.get("tipo") or "EXT")
    if not tipo or tipo["unidade"] not in UNIDADES:
        raise ValueError(f"Parede {w.get('id')}: tipo de parede ou unidade desconhecidos ({w.get('tipo')}).")
    x1, y1, x2, y2 = (float(w[k]) for k in ("x1", "y1", "x2", "y2"))
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 0.05:
        raise ValueError(f"Parede {w.get('id')}: menos de 5 cm de comprimento.")
    nome, ul, uh, ut = UNIDADES[tipo["unidade"]]
    vaos = sorted(({"a": float(v["offset_m"]), "b": float(v["offset_m"]) + float(v["largura_m"]), "z0": float(v.get("peitoril_m") or 0.0),
                    "z1": float(v.get("peitoril_m") or 0.0) + float(v["altura_m"]), "id": v.get("id")} for v in w.get("vaos") or []), key=lambda v: v["a"])
    for v in vaos:
        if v["a"] < -1e-6 or v["b"] > L + 1e-6 or v["z1"] > float(w["altura_m"]) + 1e-6:
            raise ValueError(f"Parede {w['id']}: um vão sai da parede.")
    return {"id": str(w["id"]), "x1": x1, "y1": y1, "x2": x2, "y2": y2, "L": L, "H": float(w["altura_m"]), "tipo": w.get("tipo") or "EXT", "t": ut / 1000,
            "unidade": tipo["unidade"], "nome": nome, "ul": ul / 1000, "uh": uh / 1000, "reb": (tipo.get("reboco_ext_mm", 0), tipo.get("reboco_int_mm", 0)),
            "vaos": vaos, "ini": 0.0, "fim": L}


def _dist(p, w):
    ux, uy = (w["x2"] - w["x1"]) / w["L"], (w["y2"] - w["y1"]) / w["L"]
    s = min(max((p[0] - w["x1"]) * ux + (p[1] - w["y1"]) * uy, 0.0), w["L"])
    return math.hypot(p[0] - (w["x1"] + ux * s), p[1] - (w["y1"] + uy * s)), s


def _encontros(paredes, avisos, piso):
    """Num encontro em T, a parede que acaba na outra é encurtada meia espessura da que passa, para o canto não ser
    assente duas vezes. Num canto em L os dois eixos acabam no mesmo ponto e o volume já fica certo."""
    for a in paredes:
        for b in paredes:
            if a is b:
                continue
            cos = abs((a["x2"] - a["x1"]) * (b["x2"] - b["x1"]) + (a["y2"] - a["y1"]) * (b["y2"] - b["y1"])) / (a["L"] * b["L"])
            if cos > 0.999:
                continue
            for ponta, p in (("ini", (a["x1"], a["y1"])), ("fim", (a["x2"], a["y2"]))):
                d, s = _dist(p, b)
                if d <= SNAP and SNAP < s < b["L"] - SNAP and (b["t"] / 2) < s < b["L"] - b["t"] / 2:      # a acaba a meio de b: T
                    if ponta == "ini":
                        a["ini"] = max(a["ini"], b["t"] / 2)
                    else:
                        a["fim"] = min(a["fim"], a["L"] - b["t"] / 2)
    for i, a in enumerate(paredes):
        for b in paredes[i + 1:]:
            d = (a["x2"] - a["x1"]) * (b["y2"] - b["y1"]) - (a["y2"] - a["y1"]) * (b["x2"] - b["x1"])
            if abs(d) < 1e-12:
                continue
            t = ((b["x1"] - a["x1"]) * (b["y2"] - b["y1"]) - (b["y1"] - a["y1"]) * (b["x2"] - b["x1"])) / d
            u = ((b["x1"] - a["x1"]) * (a["y2"] - a["y1"]) - (b["y1"] - a["y1"]) * (a["x2"] - a["x1"])) / d
            if SNAP / a["L"] < t < 1 - SNAP / a["L"] and SNAP / b["L"] < u < 1 - SNAP / b["L"]:
                avisos.append(f"{piso} · paredes {a['id']} e {b['id']} cruzam-se: o cruzamento é assente nas duas (dividir uma delas para o contar uma só vez).")


def _troços(w, z0, z1):
    """Troços com alvenaria numa fiada (banda z0–z1): o comprimento útil menos os vãos que a cortam por inteiro.
    Devolve também os vãos que só a cortam em parte da altura (fiada de ajuste, com as unidades cortadas à altura)."""
    cheios, parciais, pos = [], [], w["ini"]
    for v in w["vaos"]:
        if v["z1"] <= z0 + 1e-6 or v["z0"] >= z1 - 1e-6:
            continue                                               # o vão não toca nesta fiada
        a, b = max(v["a"], w["ini"]), min(v["b"], w["fim"])
        if b <= a:
            continue
        if a - pos > 1e-6:
            cheios.append((pos, a))
        resto = max(0.0, v["z0"] - z0) + max(0.0, z1 - v["z1"])   # altura de alvenaria que sobra dentro da banda
        if resto > 1e-6:
            parciais.append((a, b, max(0.0, v["z0"] - z0), max(0.0, z1 - v["z1"])))
        pos = max(pos, b)
    if w["fim"] - pos > 1e-6:
        cheios.append((pos, w["fim"]))
    return cheios, parciais


def calcular(projeto: dict) -> dict:
    par = {**PARAMETROS, **{k: v for k, v in projeto.items() if k in PARAMETROS and v is not None}}
    tipos = {**TIPOS_PAREDE, **(projeto.get("tipos_parede") or {})}
    j, cmin = par["junta_mm"] / 1000, par["corte_min_mm"] / 1000
    unidades, linteis, avisos, paredes_out = [], [], [], []
    mat = {}
    n = iter(range(1, 10_000_000))
    for piso in projeto.get("pisos") or []:
        nome_p, cota = piso["nome"], float(piso.get("cota_m") or 0.0)
        paredes = [_parede(w, tipos) for w in piso.get("paredes") or []]
        _encontros(paredes, avisos, nome_p)
        for w in paredes:
            m = mat.setdefault(w["unidade"], {"unidade": w["unidade"], "nome": w["nome"], "inteiras": 0, "cortes": [], "ajuste": 0, "t": w["t"], "ul": w["ul"], "uh": w["uh"],
                                              "argamassa_m3": 0.0})
            ux, uy = (w["x2"] - w["x1"]) / w["L"], (w["y2"] - w["y1"]) / w["L"]
            passo, n_w, face = w["uh"] + j, 0, 0.0
            fiadas = math.ceil((w["H"] - 1e-9) / passo)
            for f in range(fiadas):
                z0 = f * passo
                h = min(w["uh"], w["H"] - z0 - (j if z0 + passo <= w["H"] + 1e-9 else 0.0))
                if h < cmin:
                    continue                                       # sobra menor do que o corte mínimo: fecha-se com argamassa
                cheios, parciais = _troços(w, z0, z0 + h)

                def assenta(a, b, alt, dz, desencontro):
                    nonlocal n_w, face
                    x = a
                    primeiro = w["ul"] / 2 if desencontro else w["ul"]
                    while b - x > cmin:
                        c = min(primeiro, b - x)
                        primeiro = w["ul"]
                        if b - (x + c) <= cmin:                    # o resto não chega para um corte: a última unidade fecha o troço
                            c = b - x if b - x <= w["ul"] + 1e-9 else c
                        inteira = abs(c - w["ul"]) < 1e-6 and abs(alt - w["uh"]) < 1e-6
                        unidades.append({"id": f"U{next(n)}", "piso": nome_p, "parede": w["id"], "unidade": w["unidade"], "fiada": f + 1, "s": round(x, 4),
                                         "z": round(cota + z0 + dz, 4), "c": round(c, 4), "h": round(alt, 4), "inteira": inteira,
                                         "x": round(w["x1"] + ux * x, 4), "y": round(w["y1"] + uy * x, 4)})
                        if inteira:
                            m["inteiras"] += 1
                        elif abs(alt - w["uh"]) < 1e-6:
                            m["cortes"].append(round(c, 4))
                        else:
                            m["ajuste"] += 1                       # cortada à altura (fiada de ajuste): uma unidade por peça
                        m["argamassa_m3"] += (c * w["t"] * j) + (alt * w["t"] * j)        # junta de assentamento + junta vertical
                        n_w += 1
                        face += c * alt
                        x += c + j

                for a, b in cheios:
                    assenta(a, b, h, 0.0, f % 2 == 1 and abs(a - w["ini"]) < 1e-9)
                for a, b, baixo, cima in parciais:
                    if baixo >= cmin:
                        assenta(a, b, baixo, 0.0, False)
                    if cima >= cmin:
                        assenta(a, b, cima, h - cima, False)
            for v in w["vaos"]:
                comp = (v["b"] - v["a"]) + 2 * par["lintel_apoio_m"]
                linteis.append({"id": f"LT{next(n)}", "piso": nome_p, "parede": w["id"], "comprimento_m": round(comp, 3), "espessura_m": w["t"],
                                "s": round(v["a"] - par["lintel_apoio_m"], 4), "z": round(cota + v["z1"], 4), "x": round(w["x1"] + ux * (v["a"] - par["lintel_apoio_m"]), 4),
                                "y": round(w["y1"] + uy * (v["a"] - par["lintel_apoio_m"]), 4)})
                if v["a"] - par["lintel_apoio_m"] < -1e-6 or v["b"] + par["lintel_apoio_m"] > w["L"] + 1e-6:
                    avisos.append(f"{nome_p} · {w['id']}: o lintel do vão a {v['a']:.2f} m não tem entrega completa de um dos lados.")
            bruta = (w["fim"] - w["ini"]) * w["H"]
            vaos_m2 = sum((min(v["b"], w["fim"]) - max(v["a"], w["ini"])) * (v["z1"] - v["z0"]) for v in w["vaos"])
            paredes_out.append({"id": w["id"], "piso": nome_p, "tipo": w["tipo"], "unidade": w["unidade"], "L": round(w["L"], 4), "H": w["H"], "t": w["t"],
                                "cota_m": cota, "x1": w["x1"], "y1": w["y1"], "x2": w["x2"], "y2": w["y2"], "util_m": round(w["fim"] - w["ini"], 4),
                                "vaos": [{"a": v["a"], "b": v["b"], "z0": v["z0"], "z1": v["z1"]} for v in w["vaos"]], "unidades": n_w,
                                "area_liquida_m2": round(bruta - vaos_m2, 4), "reboco_ext_mm": w["reb"][0], "reboco_int_mm": w["reb"][1]})
    serra = par["serra_mm"] / 1000
    resumo = []
    for m in mat.values():
        # cada corte sai de uma unidade inteira; a sobra serve para outro corte se ainda chegar (maiores primeiro)
        sobras, novas = [], 0
        for c in sorted(m["cortes"], reverse=True):
            i = next((k for k, s in enumerate(sobras) if s >= c - 1e-9), None)
            if i is None:
                novas += 1
                sobras.append(m["ul"] - c - serra)
            else:
                sobras[i] -= c + serra
        resumo.append({"unidade": m["unidade"], "nome": m["nome"], "inteiras": m["inteiras"], "cortes": len(m["cortes"]), "unidades_para_cortes": novas,
                       "cortadas_a_altura": m["ajuste"], "a_comprar": m["inteiras"] + novas + m["ajuste"], "argamassa_m3": round(m["argamassa_m3"], 4)})
    reboco = {}
    for w in paredes_out:
        for lado, mm in (("exterior" if w["tipo"].startswith("EXT") else "interior", w["reboco_ext_mm"]), ("interior", w["reboco_int_mm"])):
            if mm:
                e = reboco.setdefault((lado, mm), {"face": lado, "espessura_mm": mm, "area_m2": 0.0})
                e["area_m2"] += w["area_liquida_m2"]
    for e in reboco.values():
        e["area_m2"] = round(e["area_m2"], 3)
        e["volume_m3"] = round(e["area_m2"] * e["espessura_mm"] / 1000, 4)
    if paredes_out:
        avisos.append("Estrutura de betão armado (pilares, vigas, cintas, lajes) fora desta versão: as paredes foram assentes em todo o comprimento.")
    return {"versao": VERSAO, "nome": projeto.get("nome") or "Construção tradicional", "parametros": {k: {"valor": par[k], "fonte": FONTES[k]} for k in PARAMETROS},
            "unidades": unidades, "linteis": linteis, "paredes": paredes_out, "resumo": resumo, "reboco": sorted(reboco.values(), key=lambda e: (e["face"], e["espessura_mm"])),
            "estudo": {"unidades": len(unidades), "a_comprar": sum(r["a_comprar"] for r in resumo), "argamassa_m3": round(sum(r["argamassa_m3"] for r in resumo), 3),
                       "linteis": len(linteis), "linteis_m": round(sum(x["comprimento_m"] for x in linteis), 2),
                       "area_alvenaria_m2": round(sum(w["area_liquida_m2"] for w in paredes_out), 2)}, "avisos": avisos}


def exemplo() -> dict:
    """Moradia 10 × 8 m, um piso: exterior em tijolo de 22, uma divisória em tijolo de 11, porta e janelas."""
    return {"nome": "Moradia exemplo — alvenaria", "pisos": [{"nome": "R/C", "cota_m": 0.0, "paredes": [
        {"id": "S", "x1": 0, "y1": 0, "x2": 10, "y2": 0, "tipo": "EXT", "altura_m": 2.7, "vaos": [{"offset_m": 4.0, "largura_m": 1.0, "peitoril_m": 0, "altura_m": 2.1}]},
        {"id": "E", "x1": 10, "y1": 0, "x2": 10, "y2": 8, "tipo": "EXT", "altura_m": 2.7, "vaos": [{"offset_m": 3.0, "largura_m": 1.5, "peitoril_m": 0.9, "altura_m": 1.2}]},
        {"id": "N", "x1": 10, "y1": 8, "x2": 0, "y2": 8, "tipo": "EXT", "altura_m": 2.7, "vaos": [{"offset_m": 2.0, "largura_m": 1.2, "peitoril_m": 0.9, "altura_m": 1.2}]},
        {"id": "O", "x1": 0, "y1": 8, "x2": 0, "y2": 0, "tipo": "EXT", "altura_m": 2.7, "vaos": []},
        {"id": "I", "x1": 5, "y1": 0, "x2": 5, "y2": 8, "tipo": "INT", "altura_m": 2.7, "vaos": [{"offset_m": 3.5, "largura_m": 0.8, "peitoril_m": 0, "altura_m": 2.1}]}]}]}
