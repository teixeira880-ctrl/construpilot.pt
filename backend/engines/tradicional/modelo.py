"""Adaptador construção tradicional → modelo de estudo comum (engines.estudo_modelo): cada bloco ou tijolo desenhado
no seu sítio, alçados fiada a fiada, mapa de quantidades e lista de cortes. Não recalcula nada."""
from __future__ import annotations

from engines import estudo_modelo as M

CAMADAS = (("alvenaria", "Alvenaria", True), ("cortes", "Unidades cortadas", True), ("linteis", "Lintéis", True))
MAX_SOLIDOS = 15000


def _n(x, d=0):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def _cor(unidade, inteira):
    base = "#9aa0a6" if unidade.startswith("bloco") else "#c0613a"
    return base if inteira else ("#c9ced3" if unidade.startswith("bloco") else "#e3a27f")


def modelo(res: dict, titulo: str | None = None, projeto: dict | None = None) -> dict:
    e = res["estudo"]
    m = M.novo("tradicional", titulo or res.get("nome") or "Construção tradicional", "Alvenaria: cada bloco, cada corte, cada junta", CAMADAS)
    m["kpi"] = [f"{_n(e['unidades'])} unidades assentes", f"{_n(e['a_comprar'])} a comprar", f"{_n(e['argamassa_m3'], 2)} m³ de argamassa"]
    par = {(w["piso"], w["id"]): w for w in res["paredes"]}
    eixo = {}
    for k, w in par.items():
        L = w["L"]
        ux, uy = (w["x2"] - w["x1"]) / L, (w["y2"] - w["y1"]) / L
        eixo[k] = (ux, uy, -uy, ux)
    desenha = len(res["unidades"]) <= MAX_SOLIDOS
    alc = {k: [] for k in par}
    for u in res["unidades"]:
        k = (u["piso"], u["parede"])
        w = par[k]
        ux, uy, nx, ny = eixo[k]
        t = w["t"] * 1000
        alc[k].append({"x": u["s"] * 1000, "y": (u["z"] - w["cota_m"]) * 1000, "w": u["c"] * 1000, "h": u["h"] * 1000, "cor": _cor(u["unidade"], u["inteira"]), "rotulo": u["id"]})
        if desenha:
            o = [u["x"] * 1000 - nx * t / 2, u["y"] * 1000 - ny * t / 2, u["z"] * 1000]
            m["solidos"].append(M.caixa("alvenaria" if u["inteira"] else "cortes", _cor(u["unidade"], u["inteira"]), o, [ux * u["c"] * 1000, uy * u["c"] * 1000, 0],
                                        [nx * t, ny * t, 0], [0, 0, u["h"] * 1000], f"{u['id']} · {'inteira' if u['inteira'] else 'cortada'}",
                                        (f"{u['piso']} · parede {u['parede']} · fiada {u['fiada']}", f"{_n(u['c'] * 1000)} × {_n(u['h'] * 1000)} × {_n(t)} mm")))
    if not desenha:
        for k, w in par.items():
            ux, uy, nx, ny = eixo[k]
            t = w["t"] * 1000
            m["solidos"].append(M.caixa("alvenaria", "#c0613a", [w["x1"] * 1000 - nx * t / 2, w["y1"] * 1000 - ny * t / 2, w["cota_m"] * 1000],
                                        [ux * w["L"] * 1000, uy * w["L"] * 1000, 0], [nx * t, ny * t, 0], [0, 0, w["H"] * 1000], f"{k[0]} · parede {k[1]}",
                                        (f"{w['unidades']} unidades",)))
        m["avisos"].append(f"Mais de {_n(MAX_SOLIDOS)} unidades: no 3D as paredes aparecem inteiras; as unidades estão nos alçados e nas quantidades.")
    for x in res["linteis"]:
        k = (x["piso"], x["parede"])
        ux, uy, nx, ny = eixo[k]
        t = x["espessura_m"] * 1000
        m["solidos"].append(M.caixa("linteis", "#6b7280", [x["x"] * 1000 - nx * t / 2, x["y"] * 1000 - ny * t / 2, x["z"] * 1000], [ux * x["comprimento_m"] * 1000, uy * x["comprimento_m"] * 1000, 0],
                                    [nx * t, ny * t, 0], [0, 0, 200], f"{x['id']} · lintel", (f"{x['piso']} · parede {x['parede']}", f"{_n(x['comprimento_m'], 2)} m")))
    for k, w in par.items():
        m["alcados"].append({"titulo": f"{k[0]} · {k[1]} · {_n(w['L'] * 1000)} × {_n(w['H'] * 1000)} mm · {w['unidades']} unidades", "L": w["L"] * 1000, "H": w["H"] * 1000,
                             "rects": alc[k], "vaos": [{"x": v["a"] * 1000, "y": v["z0"] * 1000, "w": (v["b"] - v["a"]) * 1000, "h": (v["z1"] - v["z0"]) * 1000} for v in w["vaos"]]})
    cortes = {}
    for u in res["unidades"]:
        if not u["inteira"]:
            c = cortes.setdefault((u["unidade"], round(u["c"] * 1000), round(u["h"] * 1000)), 0)
            cortes[(u["unidade"], round(u["c"] * 1000), round(u["h"] * 1000))] = c + 1
    nomes = {r["unidade"]: r["nome"] for r in res["resumo"]}
    esp = {w["unidade"]: round(w["t"] * 1000) for w in res["paredes"]}
    for (un, c, h), q in sorted(cortes.items(), key=lambda kv: (kv[0][0], -kv[0][1], -kv[0][2])):
        m["lista_corte"].append({"grupo": nomes[un], "peca": "corte ao comprimento" if h >= 199 else "corte à altura", "comprimento": c, "largura": h, "espessura": esp[un], "n": q})
    for r in res["resumo"]:
        m["quantidades"].append(M.linha("Alvenaria", r["nome"], r["a_comprar"], "un",
                                        f"{_n(r['inteiras'])} inteiras + {_n(r['unidades_para_cortes'])} para {_n(r['cortes'])} cortes + {_n(r['cortadas_a_altura'])} cortadas à altura"))
        m["quantidades"].append(M.linha("Argamassa de assentamento", f"Juntas de {r['nome']}", r["argamassa_m3"], "m³", "volume das juntas de cada unidade assente"))
    for r in res["reboco"]:
        m["quantidades"].append(M.linha("Reboco", f"Reboco {r['face']} {r['espessura_mm']} mm", r["area_m2"], "m²", f"{_n(r['volume_m3'], 2)} m³ · faces líquidas, vãos descontados"))
    if res["linteis"]:
        m["quantidades"].append(M.linha("Lintéis", "Lintéis pré-fabricados dos vãos", e["linteis_m"], "m", f"{e['linteis']} lintéis, com a entrega de cada lado"))
    m["estudo"] = [["Unidades assentes", _n(e["unidades"])], ["Unidades a comprar", _n(e["a_comprar"])], ["Argamassa de assentamento", f"{_n(e['argamassa_m3'], 2)} m³"],
                   ["Alvenaria (líquida)", f"{_n(e['area_alvenaria_m2'], 1)} m²"], ["Lintéis", f"{e['linteis']} · {_n(e['linteis_m'], 2)} m"]]
    m["avisos"] += list(res["avisos"]) + [f"Hipótese · {k} = {v['valor']}: {v['fonte']}" for k, v in res["parametros"].items()]
    m["projeto"] = projeto or {}
    return m
