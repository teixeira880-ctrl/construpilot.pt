"""Adaptador CLT → modelo de estudo comum (engines.estudo_modelo): painéis de parede com os vãos cortados, faixas de
laje e cobertura, ligadores posicionados (clt_ligacoes), lista de peças, planos de prensa e mapa de quantidades.
Só organiza o que os motores CLT já mediram; não depende de shapely."""
from __future__ import annotations

import math

from bim_studio import clt_ligacoes as LG
from engines import estudo_modelo as M

CAMADAS = (("paredes", "Paredes CLT", True), ("lajes", "Lajes", True), ("cobertura", "Cobertura", False), ("ligadores", "Ligadores", True))
COR = {"paredes": "#d8b475", "lajes": "#c79f5c", "cobertura": "#b98a4a", "cantoneira": "#4d5a66", "holddown": "#c0392b"}


def _n(x, d=0):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def _retangulos(L, H, vaos):
    """A face da parede (L × H) menos os vãos, em retângulos: troços inteiros entre vãos, peitoril e padieira de cada vão."""
    out, pos = [], 0.0
    for v in sorted(vaos, key=lambda v: v["a"]):
        if v["a"] - pos > 1e-6:
            out.append((pos, 0.0, v["a"] - pos, H))
        if v["peitoril"] > 1e-6:
            out.append((v["a"], 0.0, v["l"], v["peitoril"]))
        topo = v["peitoril"] + v["alt"]
        if H - topo > 1e-6:
            out.append((v["a"], topo, v["l"], H - topo))
        pos = max(pos, v["a"] + v["l"])
    if L - pos > 1e-6:
        out.append((pos, 0.0, L - pos, H))
    return out


def modelo(pisos: list[dict], corte: dict | None = None, titulo: str = "Estudo CLT", parametros: dict | None = None, projeto: dict | None = None) -> dict:
    """pisos: [{nome, cota_m, paredes: [WallAxis ou dicionário], faixas: [{id, tipo, ret, espessura_mm}]}] de baixo para cima;
    corte: o plano de clt_nesting.plan (opcional)."""
    m = M.novo("clt", titulo, "CLT: cada painel, cada ligador, cada parafuso", CAMADAS)
    lig = LG.calcular([{"nome": p["nome"], "paredes": p.get("paredes") or [], "faixas": p.get("faixas") or [], **({"terreo": p["terreo"]} if "terreo" in p else {})}
                       for p in pisos], parametros)
    cota = {p["nome"]: float(p.get("cota_m") or 0.0) * 1000 for p in pisos}
    vol = area = n_pecas = 0.0
    for p in pisos:
        z0 = cota[p["nome"]]
        topo = z0
        for w0 in p.get("paredes") or []:
            w = LG._parede(w0)
            vaos = [{"a": float(LG._g(o, "offset_m")), "l": float(LG._g(o, "width_m", "largura_m")), "peitoril": float(LG._g(o, "sill_m", "peitoril_m", default=0.0)),
                     "alt": float(LG._g(o, "height_m", "altura_m"))} for o in (LG._g(w0, "openings", "vaos", default=[]) or [])]
            ux, uy = (w["x2"] - w["x1"]) / w["L"], (w["y2"] - w["y1"]) / w["L"]
            nx, ny, t, zb = -uy, ux, w["t"] * 1000, z0 + w["z"] * 1000
            liquido = w["L"] * w["h"] - sum(v["l"] * v["alt"] for v in vaos)
            info = (f"{_n(w['L'] * 1000)} × {_n(w['h'] * 1000)} × {_n(t)} mm", f"{_n(liquido, 2)} m² líquidos · {len(vaos)} vão(s) cortado(s)")
            for a, b, la, lb in _retangulos(w["L"], w["h"], vaos):
                o = [(w["x1"] + ux * a) * 1000 - nx * t / 2, (w["y1"] + uy * a) * 1000 - ny * t / 2, zb + b * 1000]
                m["solidos"].append(M.caixa("paredes", COR["paredes"], o, [ux * la * 1000, uy * la * 1000, 0], [nx * t, ny * t, 0], [0, 0, lb * 1000],
                                            f"{p['nome']} · parede {w['id']}", info))
            m["alcados"].append({"titulo": f"{p['nome']} · {w['id']} · {_n(w['L'] * 1000)} × {_n(w['h'] * 1000)} mm · {_n(t)} mm", "L": w["L"] * 1000, "H": w["h"] * 1000,
                                 "rects": [{"x": a * 1000, "y": b * 1000, "w": la * 1000, "h": lb * 1000, "cor": COR["paredes"], "rotulo": ""}
                                           for a, b, la, lb in _retangulos(w["L"], w["h"], vaos)],
                                 "vaos": [{"x": v["a"] * 1000, "y": v["peitoril"] * 1000, "w": v["l"] * 1000, "h": v["alt"] * 1000} for v in vaos]})
            m["lista_corte"].append({"grupo": f"Paredes {_n(t)} mm", "peca": f"{p['nome']} · {w['id']}", "comprimento": round(w["L"] * 1000), "largura": round(w["h"] * 1000),
                                     "espessura": round(t), "n": 1})
            vol, area, n_pecas, topo = vol + liquido * w["t"], area + liquido, n_pecas + 1, max(topo, zb + w["h"] * 1000)
        for f in p.get("faixas") or []:
            x0, y0, x1, y1 = (float(v) * 1000 for v in LG._g(f, "ret", "ret_m"))
            t = float(f.get("espessura_mm") or 0) or 160.0
            camada = "cobertura" if f.get("tipo") == "cobertura" else "lajes"
            m["solidos"].append(M.caixa(camada, COR[camada], [x0, y0, topo], [x1 - x0, 0, 0], [0, y1 - y0, 0], [0, 0, t], f"{p['nome']} · {f.get('tipo', 'laje')} {f['id']}",
                                        (f"{_n(max(x1 - x0, y1 - y0))} × {_n(min(x1 - x0, y1 - y0))} × {_n(t)} mm",), 0.92))
            m["lista_corte"].append({"grupo": f"{'Cobertura' if camada == 'cobertura' else 'Lajes'} {_n(t)} mm", "peca": f"{p['nome']} · {f['id']}",
                                     "comprimento": round(max(x1 - x0, y1 - y0)), "largura": round(min(x1 - x0, y1 - y0)), "espessura": round(t), "n": 1})
            a2 = (x1 - x0) * (y1 - y0) / 1e6
            vol, area, n_pecas = vol + a2 * t / 1000, area + a2, n_pecas + 1
    for g in lig["ligadores"]:                                   # cada ligador no seu sítio, ao pé da parede
        hd = g["tipo"] == "holddown"
        s, h = (60, 340) if hd else (90, 90)
        z = cota[g["piso"]] + g["z"] * 1000
        fix = " · ".join(f"{v} × {LG.PRODUTOS[k][0].lower()}" for k, v in g["fixacoes"].items())
        m["solidos"].append(M.caixa("ligadores", COR[g["tipo"]], [g["x"] * 1000 - s / 2, g["y"] * 1000 - s / 2, z], [s, 0, 0], [0, s, 0], [0, 0, h],
                                    f"{g['id']} · {LG.PRODUTOS[g['tipo']][0]}", (f"{g['piso']} · parede {g['parede']}", fix)))
    for k, t in lig["totais"].items():
        m["quantidades"].append(M.linha("Ligações", t["nome"], t["quantidade"], t["unidade"], "contado ligador a ligador e junta a junta"))
    for j in lig["juntas"]:
        m["quantidades"].append(M.linha("Juntas", f"{j['id']} · {j['tipo']} ({' / '.join(j['entre'])})", j["comprimento_m"], "m", f"{j['parafusos']} parafusos · {_n(j['fita_m'], 2)} m de fita"))
    m["quantidades"].insert(0, M.linha("CLT", "Painéis (líquido, vãos descontados)", vol, "m³", f"{_n(area, 2)} m² · {int(n_pecas)} peças"))
    for g in (corte or {}).get("grupos") or []:
        for b in g["layout"]:
            W, H = b["comprimento_usado_m"] * 1000, b["largura_m"] * 1000
            m["planos_corte"].append({"titulo": f"CLT {_n(g['espessura_mm'])} mm · {g['camadas']} camadas · painel {b['painel']} de {g['paineis']}", "W": W, "H": H,
                                      "pecas": [{"x": q["x_m"] * 1000, "y": q["y_m"] * 1000, "w": q["comprimento_m"] * 1000, "h": q["largura_m"] * 1000, "rotulo": q["id"]}
                                                for q in b["pecas"]], "aproveitamento": b["aproveitamento_percent"]})
    par = lig["totais"]
    m["kpi"] = [f"{int(n_pecas)} peças", f"{_n(lig['parafusos_total'])} parafusos", f"{_n(vol, 2)} m³ de CLT"]
    m["estudo"] = [["CLT líquido", f"{_n(vol, 2)} m³"], ["Área de painéis", f"{_n(area, 1)} m²"], ["Peças", _n(n_pecas)],
                   ["Cantoneiras", _n(par.get("cantoneira", {}).get("quantidade", 0))], ["Ancoragens de tração", _n(par.get("holddown", {}).get("quantidade", 0))],
                   ["Parafusos", _n(lig["parafusos_total"])], ["Fita de estanquidade", f"{_n(par.get('fita', {}).get('quantidade', 0), 1)} m"]]
    if corte:
        m["estudo"] += [["Painéis de prensa", _n(corte["total"]["paineis"])], ["Desperdício de corte", f"{_n(corte['total']['desperdicio_percent'], 1)} %"]]
    m["avisos"] = list(lig["avisos"]) + [f"Hipótese · {k} = {v['valor']}: {v['fonte']}" for k, v in lig["parametros"].items() if "hipótese" in v["fonte"]]
    m["projeto"] = projeto or {}
    return m


def faixas_da_laje(nome: str, poligono, largura_max_m: float, tipo: str = "laje", espessura_mm: float = 160.0):
    """Faixas de uma laje retangular, não mais largas do que a prensa, ao longo do lado maior. Um contorno que não é
    um retângulo alinhado fica numa só faixa (o retângulo envolvente) e devolve um aviso: as juntas ficam por contar."""
    xs, ys = [p[0] for p in poligono], [p[1] for p in poligono]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    area = abs(sum(poligono[i][0] * poligono[(i + 1) % len(poligono)][1] - poligono[(i + 1) % len(poligono)][0] * poligono[i][1] for i in range(len(poligono)))) / 2
    if abs(area - (x1 - x0) * (y1 - y0)) > 1e-3 * max(area, 1e-9):
        return [{"id": nome, "tipo": tipo, "ret": (x0, y0, x1, y1), "espessura_mm": espessura_mm}], f"{nome}: contorno não retangular; desenhada pelo retângulo envolvente, juntas entre faixas por contar."
    ao_longo_x = (x1 - x0) >= (y1 - y0)
    lado = (y1 - y0) if ao_longo_x else (x1 - x0)
    n = max(1, math.ceil(lado / largura_max_m - 1e-9))
    out = []
    for i in range(n):
        a, b = lado * i / n, lado * (i + 1) / n
        out.append({"id": f"{nome}.{i + 1}" if n > 1 else nome, "tipo": tipo, "espessura_mm": espessura_mm,
                    "ret": (x0, y0 + a, x1, y0 + b) if ao_longo_x else (x0 + a, y0, x0 + b, y1)})
    return out, None


def empilhar(pisos: list[dict]) -> list[dict]:
    """Cota de cada piso quando não vem medida: o piso seguinte começa no topo das paredes do anterior mais a espessura
    da laje que lhes assenta em cima. Os pisos que já trazem cota_m ficam como estão."""
    out, z = [], 0.0
    for p in pisos:
        q = dict(p)
        if q.get("cota_m") is None:
            q["cota_m"] = round(z, 4)
        alt = max((float(LG._g(w, "height_m", "altura_m")) + float(LG._g(w, "base_z_m", default=0.0)) for w in q.get("paredes") or []), default=0.0)
        laje = max((float(f.get("espessura_mm") or 0) for f in q.get("faixas") or [] if f.get("tipo") != "cobertura"), default=0.0) / 1000
        z = float(q["cota_m"]) + alt + laje
        out.append(q)
    return out
