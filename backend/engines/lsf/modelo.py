"""Adaptador LSF → modelo de estudo comum (engines.estudo_modelo): o resultado de engines.lsf.engine.calcular
tal como está, organizado nos separadores do visualizador. Não recalcula nada."""
from __future__ import annotations

import re

from engines import estudo_modelo as M

CAMADAS = (("estrutura", "Estrutura", True), ("osb", "OSB", False), ("gesso", "Gesso cartonado", False), ("etics", "ETICS", False),
           ("piso", "Pavimento", True), ("cobertura", "Cobertura", False))
_CORES = ((r"rei|apoio", "#2f5f8f"), (r"curto", "#86a9cc"), (r"^Montante", "#5b84ad"), (r"Guia de verga|Verga", "#c9772b"), (r"peitoril", "#b08a5a"),
          (r"^Guia", "#a9b6c3"), (r"Bloqueador de piso", "#7aa585"), (r"^Bloqueador", "#8c9aa6"), (r"Fita", "#c0392b"), (r"Viga de piso", "#4f8a5f"),
          (r"bordadura", "#96bf9d"), (r"Banzo", "#7a5ea8"), (r"Diagonal", "#a98fcf"))


def _cor(tipo):
    return next((c for p, c in _CORES if re.search(p, tipo)), "#888888")


def _n(x, d=0):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def _placa(p):
    """Caixas de uma placa (parede, piso ou vertente), com a mesma geometria do visualizador 3D do LSF."""
    etics, gesso = p["placa"] == "ETICS", p["placa"].startswith("GC")
    camada = "etics" if etics else "piso" if p["grupo"] == "Pisos" else "cobertura" if p["grupo"] == "Cobertura" else "gesso" if gesso else "osb"
    cor = "#eeeeea" if etics else "#f4f1e8" if gesso else "#c79f5c" if p["grupo"] == "Pisos" else "#d8b475"
    op = 0.55 if etics else 0.8 if gesso else 0.88
    pl, cel = p["plano"], p["cell"]
    linhas = (f"{p['ref']} · {p['face']}" + (f" · camada {p['camada']}" if p.get("camada") else ""),
              f"{_n(cel['x1'] - cel['x0'])} × {_n(cel['z1'] - cel['z0'])} mm · {p.get('parafusos', 0)} parafusos")
    for r in p["pecas"]:
        dx, dz = r["x1"] - r["x0"], r["z1"] - r["z0"]
        if pl["tipo"] == "parede":
            o = [pl["A"][0] + pl["d"][0] * r["x0"] + pl["n"][0] * pl["y"], pl["A"][1] + pl["d"][1] * r["x0"] + pl["n"][1] * pl["y"], pl["z0"] + r["z0"]]
            a, b, c = [x * dx for x in pl["d"]], [x * pl["esp"] for x in pl["n"]], [0, 0, dz]
        elif pl["tipo"] == "piso":
            o = [pl["O"][0] + pl["Pd"][0] * r["x0"] + pl["Sd"][0] * r["z0"], pl["O"][1] + pl["Pd"][1] * r["x0"] + pl["Sd"][1] * r["z0"], pl["z"]]
            a, b, c = [x * dx for x in pl["Pd"]], [x * dz for x in pl["Sd"]], [0, 0, pl["esp"]]
        else:
            o = [pl["O"][i] + pl["U"][i] * r["x0"] + pl["Vv"][i] * r["z0"] for i in range(3)]
            a, b, c = [x * dx for x in pl["U"]], [x * dz for x in pl["Vv"]], [x * pl["esp"] for x in pl["N"]]
        yield M.caixa(camada, cor, o, a, b, c, p["nome"], linhas, op)


def modelo(res: dict, titulo: str | None = None, projeto: dict | None = None) -> dict:
    e = res["estudo"]
    m = M.novo("lsf", titulo or res.get("nome") or "Estrutura LSF", "Aço leve: cada perfil, cada placa, cada parafuso", CAMADAS)
    m["kpi"] = [f"{e['nMembros']} peças", f"{_n(e['nParafusos'])} parafusos", f"{_n(e['kgAco'] / 1000, 2)} t de aço"]
    por_id = {}
    for x in res["membros"]:
        por_id[x["id"]] = x
        m["solidos"].append(M.perfil("estrutura", _cor(x["tipoPeca"]), x["o"], x["u"], x["v"], x["w"], x["sec"], x["L"], f"{x['id']} · {x['tipoPeca']}",
                                     (f"{x['perfilNome']} · {_n(x['L'], 1)} mm · {_n(x['kg'], 2)} kg", x.get("nota"))))
    for p in res["placas"]:
        m["solidos"].extend(_placa(p))
    for w in res["paredes"]:
        linhas = [{"x": el["x0"], "y": el["z0"], "w": el["x1"] - el["x0"], "h": el["z1"] - el["z0"], "cor": _cor(por_id[i]["tipoPeca"]), "rotulo": i}
                  for i in w["membros"] if i in por_id for el in [por_id[i].get("elev")] if el]
        m["alcados"].append({"titulo": f"{w['id']} · {w['tipo']} · {_n(w['L'])} × {_n(w['H'])} mm", "L": w["L"], "H": w["H"], "rects": linhas,
                             "vaos": [{"x": a["x0"], "y": a["z0"], "w": a["x1"] - a["x0"], "h": a["z1"] - a["z0"]} for a in w.get("aberturas") or []]})
    for p in res["perfis"]:
        m["quantidades"].append(M.linha("Perfis", p["perfil"], p["metros"], "m", f"{p['pecas']} peças · {_n(p['kg'], 1)} kg · {p['barras']} barras"))
        for c in p["cortes"]:
            m["lista_corte"].append({"grupo": p["perfil"], "peca": c["tipoPeca"], "comprimento": c["L"], "largura": None, "espessura": None, "n": c["n"]})
    for p in res["placasResumo"]:
        m["quantidades"].append(M.linha("Placas", p["nome"], p["un"], "un", f"{_n(p['area'], 2)} m² aplicados · {_n(p['desperdicio'] * 100, 1)} % de desperdício"))
    for p in res["parafusos"]:
        m["quantidades"].append(M.linha("Parafusos", p["nome"], p["qtd"], "un", " · ".join(f"{k}: {_n(v)}" for k, v in p["origens"].items())))
    for p in res["ancoragens"]:
        m["quantidades"].append(M.linha("Ancoragens", p["nome"], p["qtd"], "un", " · ".join(p["origens"])))
    for x in res["extras"]:
        m["quantidades"].append(M.linha(x["cat"], x["item"], x["qtd"], x["un"], " · ".join(x.get("refs") or [])))
    for c in res["planosCorte"]:
        for i, folha in enumerate(c["folhas"] or [], 1):
            usado = sum(q["w"] * q["h"] for q in folha)
            m["planos_corte"].append({"titulo": f"{c['nome']} · chapa {i} de {len(c['folhas'])}", "W": c["W"], "H": c["H"],
                                      "pecas": [{"x": q["x"], "y": q["y"], "w": q["w"], "h": q["h"], "rotulo": q["ref"]} for q in folha],
                                      "aproveitamento": round(usado / (c["W"] * c["H"]) * 100, 1)})
    m["estudo"] = [["Aço", f"{_n(e['kgAco'], 0)} kg"], ["Peças", _n(e["nMembros"])], ["Parafusos", _n(e["nParafusos"])],
                   ["Área de pisos", f"{_n(e['areaPisos'], 1)} m²"]] + ([["Aço por m² de piso", f"{_n(e['kgPorM2'], 1)} kg/m²"]] if e.get("kgPorM2") else []) + \
                  [[f"Aço · {g}", f"{_n(v, 0)} kg"] for g, v in e["kgPorGrupo"].items()]
    m["avisos"] = list(res.get("avisos") or []) + [f"Hipótese: {h}" for h in res.get("hipoteses") or []]
    m["projeto"] = projeto or {}
    return m
