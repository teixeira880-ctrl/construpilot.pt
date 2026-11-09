"""Especialidades de uma habitação a partir das DIVISÕES lidas na planta: eletricidade, canalização / drenagem e aquecimento (piso radiante
+ bomba de calor) — cálculo pelos motores existentes (instalacoes, aquecimento, piso_radiante) e cálculo de quantidades para o orçamento.

Entrada (no modelo estrutural m):
  m["divisoes"] = [{id, nome_en, nome_uk, tipo, cota, x0, y0, x1, y1, pe_direito, aquecida, janelas_m2, aparelhos[{tipo, x, y}], porta (x, y),
                    revestimento}]
  m["mep"] = {cidade_ua | concelho, U{parede, cobertura, pavimento_enu, janela}, niveis[{cota, en, uk, contorno, laje_cota}], cobertura_sobre,
              quadro{cota, x, y}, central{cota, x, y}, unidade_exterior{x, y}, coluna_agua{x, y}, entrada_agua{cota, x, y},
              coletores[{cota, x, y}], prumadas[{id, x, y}], saida_esgoto{x, y}}
Os planos (planos_especialidades.py) desenham estes resultados; o orçamento (devis_ua.py) usa calcular()["quantidades"].
Pré-dimensionamento: valores a validar pelos projetistas das especialidades (eletricidade, águas e esgotos, AVAC).
"""
from __future__ import annotations

import math

from . import aquecimento, instalacoes, piso_radiante

# tipo de divisão → (instalacoes, aquecimento/piso_radiante)
_TIPOS = {"sala": ("sala", "sala"), "quarto": ("quarto", "quarto"), "cozinha": ("cozinha", "cozinha"), "casa_de_banho": ("casa_de_banho", "casa_de_banho"),
          "corredor": ("corredor", "corredor"), "lavandaria": ("lavandaria", "lavandaria"), "arrumos": ("arrumos", "arrumos"),
          "escritorio": ("escritorio", "escritorio")}
AQUECIDA_MIN_T = 18
ALTURA_EQUIP = {"lavatorio": 0.55, "autoclismo": 0.20, "chuveiro": 1.10, "banheira": 0.70, "lava_loica": 0.55, "maquina_lavar_loica": 0.45,
                "maquina_lavar_roupa": 0.45, "maquina_secar": 0.0, "tanque": 0.55}


# ---------------------------------------------------------------- geometria
def area(d):
    return (d["x1"] - d["x0"]) * (d["y1"] - d["y0"])


def centro(d):
    return ((d["x0"] + d["x1"]) / 2, (d["y0"] + d["y1"]) / 2)


def _segs(poly):
    return list(zip(poly[:-1], poly[1:]))


def _sobrepoe(a0, a1, b0, b1):
    return max(0.0, min(max(a0, a1), max(b0, b1)) - max(min(a0, a1), min(b0, b1)))


def parede_exterior(d, contorno, tol=0.35):
    """Comprimento das arestas do retângulo da divisão que coincidem com o contorno exterior do piso."""
    tot = 0.0
    arestas = [((d["x0"], d["y0"]), (d["x1"], d["y0"])), ((d["x1"], d["y0"]), (d["x1"], d["y1"])),
               ((d["x0"], d["y1"]), (d["x1"], d["y1"])), ((d["x0"], d["y0"]), (d["x0"], d["y1"]))]
    for (ax, ay), (bx, by) in arestas:
        for (cx, cy), (ex, ey) in _segs(contorno):
            if abs(ay - by) < 1e-6 and abs(cy - ey) < 1e-6 and abs(ay - cy) <= tol:
                tot += _sobrepoe(ax, bx, cx, ex)
            elif abs(ax - bx) < 1e-6 and abs(cx - ex) < 1e-6 and abs(ax - cx) <= tol:
                tot += _sobrepoe(ay, by, cy, ey)
    return tot


def _dentro(px, py, poly):
    ins = False
    for (x1, y1), (x2, y2) in _segs(poly):
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            ins = not ins
    return ins


def area_sob(d, poly, n=24):
    """Área da divisão por baixo do polígono poly (amostragem em grelha n × n)."""
    if not poly:
        return 0.0
    dx, dy = (d["x1"] - d["x0"]) / n, (d["y1"] - d["y0"]) / n
    k = sum(1 for i in range(n) for j in range(n) if _dentro(d["x0"] + (i + 0.5) * dx, d["y0"] + (j + 0.5) * dy, poly))
    return area(d) * k / (n * n)


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ---------------------------------------------------------------- cálculo
def calcular(m: dict) -> dict:
    mep = m.get("mep") or {}
    divs = m.get("divisoes") or []
    if not divs:
        raise ValueError("indicar as divisões (m['divisoes']) lidas na planta")
    niveis = sorted(mep.get("niveis") or [], key=lambda n: n["cota"])
    nivel = {round(n["cota"], 2): n for n in niveis}
    U = {"parede": 0.30, "cobertura": 0.25, "pavimento_enu": 0.35, "janela": 1.3}
    U.update(mep.get("U") or {})
    clima = {"cidade_ua": mep["cidade_ua"]} if mep.get("cidade_ua") else {"concelho": mep.get("concelho") or "Lisboa"}
    hyp: list[str] = []
    cotas = sorted({round(d["cota"], 2) for d in divs})
    top = max(cotas)
    # --- 1. perdas de calor divisão a divisão (EN 12831 simplificada)
    aq = [d for d in divs if d.get("aquecida", True)]
    linhas_aq = []
    for d in aq:
        nv = nivel.get(round(d["cota"], 2)) or {}
        A = area(d)
        L_ext = parede_exterior(d, nv.get("contorno") or [])
        par = []
        jan = float(d.get("janelas_m2") or 0)
        bruto = L_ext * float(d["pe_direito"])
        if bruto > 0:
            par.append({"area_m2": round(max(0.0, bruto - jan), 2), "U": U["parede"], "lado": "exterior", "designacao": "parede"})
        if jan:
            par.append({"area_m2": jan, "U": U["janela"], "lado": "exterior", "designacao": "janela"})
        # teto: cobertura se não houver piso aquecido por cima
        acima = [c for c in cotas if c > round(d["cota"], 2)]
        if not acima:
            par.append({"area_m2": round(A, 2), "U": U["cobertura"], "lado": "exterior", "designacao": "cobertura"})
        else:
            sob = area_sob(d, mep.get("cobertura_sobre")) if round(d["cota"], 2) < top else A
            if A - sob > 0.2:
                par.append({"area_m2": round(A - sob, 2), "U": U["cobertura"], "lado": "exterior", "designacao": "cobertura (terraço)"})
        abaixo = [c for c in cotas if c < round(d["cota"], 2)]
        if abaixo and not any(x.get("aquecida", True) and round(x["cota"], 2) == max(abaixo) for x in divs):
            par.append({"area_m2": round(A, 2), "U": U["pavimento_enu"], "lado": "enu", "designacao": "pavimento sobre cave"})
        linhas_aq.append({"nome": d["id"], "tipo": _TIPOS[d["tipo"]][1], "area_m2": round(A, 2), "pe_direito_m": d["pe_direito"], "paredes": par})
    per = aquecimento.perdas(dict(clima, divisoes=linhas_aq, pisos=len([c for c in cotas if any(x.get("aquecida", True) for x in divs if round(x["cota"], 2) == c)])))
    phi = {r["nome"]: r["phi"] for r in per["divisoes"]}
    # --- 2. piso radiante por coletor (um coletor por piso aquecido)
    ufh = {}
    for col in mep.get("coletores") or []:
        ds = [d for d in aq if abs(d["cota"] - col["cota"]) < 0.05]
        if not ds:
            continue
        r = piso_radiante.calcular({"divisoes": [{"nome": d["id"], "tipo": _TIPOS[d["tipo"]][1], "area_m2": area(d), "phi_w": phi[d["id"]],
                                                  "revestimento": d.get("revestimento"), "comprimento_m": d["x1"] - d["x0"], "largura_m": d["y1"] - d["y0"],
                                                  "local_inferior": "nao_aquecido" if col["cota"] <= min(c["cota"] for c in mep["coletores"]) else "aquecido",
                                                  "distancia_coletor_m": round(_dist(centro(d), (col["x"], col["y"])) * 0.8 + 1.0, 1)} for d in ds]})
        ufh[round(col["cota"], 2)] = dict(r, coletor=col)
    # --- 3. bomba de calor (perdas totais) — dimensionamento pelo motor aquecimento
    phi_tot = sum(phi.values())
    tv = max([u["theta_ida"] for u in ufh.values()] or [35.0])
    bc = aquecimento.bomba_calor(phi_tot, per["theta_e"], {"emissores": "piso_radiante", "temperatura_ida": round(tv, 1),
                                                          "volume_instalacao_l": sum(u["volume_agua_l"] for u in ufh.values()) + 40,
                                                          "pisos": len(ufh), "alimentacao": "tri"})
    # --- 4. eletricidade (RTIEBT / HD 60364) — distâncias reais ao quadro
    q = mep.get("quadro") or {"cota": 0.0, "x": 0.0, "y": 0.0}
    el_div = []
    for d in divs:
        c = centro(d)
        L = _dist(c, (q["x"], q["y"])) + abs(d["cota"] - q["cota"]) + 1.5
        el_div.append({"nome": d["id"], "tipo": _TIPOS[d["tipo"]][0], "area_m2": round(area(d), 2), "perimetro_m": round(2 * (d["x1"] - d["x0"] + d["y1"] - d["y0"]), 1),
                       "comprimento_m": max(d["x1"] - d["x0"], d["y1"] - d["y0"]) if d["tipo"] == "corredor" else None,
                       "distancia_quadro_m": round(L, 1)})
    cz = next((d for d in divs if d["tipo"] == "cozinha"), None)
    lav = next((d for d in divs if d["tipo"] == "lavandaria"), None)
    cen = mep.get("central") or q
    L_c = lambda p: round(_dist((p["x"], p["y"]), (q["x"], q["y"])) + abs(p.get("cota", q["cota"]) - q["cota"]) + 2.0, 1)   # noqa: E731
    p_bc = round(bc["p_nominal_kw"] / max(bc.get("cop") or 2.5, 2.5) * 1.15, 1)          # potência elétrica máx. do compressor (indicativa)
    el = instalacoes.eletricidade({"divisoes": el_div, "alimentacao": "trifasica",
                                   "equipamentos": {"placa": "tri", "forno": True, "maquina_lavar_roupa": bool(lav), "maquina_lavar_loica": bool(cz),
                                                    "maquina_secar": bool(lav), "termoacumulador": False, "bomba_calor_kw": p_bc,
                                                    "apoio_bomba_calor_kw": bc.get("apoio_kw") or 0},
                                   "comprimentos_m": {"bomba_calor": L_c(cen) + 6, "apoio_bomba_calor": L_c(cen)},
                                   "comprimento_entrada_m": 12})
    # --- 5. canalização: abastecimento troço a troço (AF e AQ) + drenagem
    col_a = mep.get("coluna_agua") or {"x": q["x"], "y": q["y"]}
    ent = mep.get("entrada_agua") or {"cota": min(cotas), "x": col_a["x"], "y": col_a["y"]}
    z0 = min(cotas)
    rede, rede_q, drenagem, fixos = [], [], [], []
    rede.append({"nome": "E", "montante": None, "comprimento_m": round(_dist((ent["x"], ent["y"]), (col_a["x"], col_a["y"])) + 10, 1), "desnivel_m": 0, "agua": "fria"})
    rede_q.append({"nome": "AQS", "montante": None, "comprimento_m": round(_dist((cen["x"], cen["y"]), (col_a["x"], col_a["y"])) + 2, 1), "desnivel_m": 0, "agua": "quente"})
    prev, prev_q = "E", "AQS"
    for c in cotas:
        nm, nq = f"C{c:+.2f}", f"Q{c:+.2f}"
        dz = 0.0 if c == z0 else c - prev_z
        rede.append({"nome": nm, "montante": prev, "comprimento_m": round(max(dz, 0.5), 2), "desnivel_m": round(dz, 2), "agua": "fria"})
        rede_q.append({"nome": nq, "montante": prev_q, "comprimento_m": round(max(dz, 0.5), 2), "desnivel_m": round(dz, 2), "agua": "quente"})
        prev, prev_q, prev_z = nm, nq, c
        for d in [x for x in divs if round(x["cota"], 2) == c and x.get("aparelhos")]:
            for i, a in enumerate(d["aparelhos"]):
                if a["tipo"] not in instalacoes.DISPOSITIVOS:          # p. ex. secador de condensação: só eletricidade
                    continue
                Lr = round(_dist((a["x"], a["y"]), (col_a["x"], col_a["y"])) + 1.0, 1)
                quente = instalacoes.DISPOSITIVOS[a["tipo"]][1]
                tag = f"{d['id']}/{i + 1}"
                rede.append({"nome": tag, "montante": nm, "comprimento_m": Lr, "desnivel_m": ALTURA_EQUIP.get(a["tipo"], 0.5), "agua": "fria",
                             "dispositivos": [{"tipo": a["tipo"], "quantidade": 1}]})
                if quente:
                    rede_q.append({"nome": "q" + tag, "montante": nq, "comprimento_m": Lr, "desnivel_m": ALTURA_EQUIP.get(a["tipo"], 0.5), "agua": "quente",
                                   "dispositivos": [{"tipo": a["tipo"], "quantidade": 1}]})
                # drenagem: aparelho → tubo de queda mais próximo
                pr = min(mep.get("prumadas") or [{"id": "TQ", "x": col_a["x"], "y": col_a["y"]}], key=lambda t: _dist((t["x"], t["y"]), (a["x"], a["y"])))
                fixos.append({"div": d, "a": a, "prumada": pr["id"], "tag": tag, "L_ramal": round(_dist((a["x"], a["y"]), (pr["x"], pr["y"])), 2)})
    # drenagem: ramais → tubo de queda → coletor enterrado → saída
    por_tq = {}
    for f in fixos:
        por_tq.setdefault(f["prumada"], []).append(f)
    said = mep.get("saida_esgoto") or {"x": 0, "y": 0}
    for tq, fs in por_tq.items():
        pr = next(t for t in mep["prumadas"] if t["id"] == tq)
        z_top = max(f["div"]["cota"] for f in fs)
        drenagem.append({"nome": tq, "jusante": "COL", "tipo": "tubo_queda", "comprimento_m": round(z_top - z0 + 0.5, 2), "dispositivos": []})
        for f in fs:
            drenagem.append({"nome": "r" + f["tag"], "jusante": tq, "tipo": "ramal", "comprimento_m": max(0.5, f["L_ramal"]), "inclinacao_pct": 2,
                             "dispositivos": [{"tipo": f["a"]["tipo"], "quantidade": 1}]})
    L_col = max(_dist((t["x"], t["y"]), (said["x"], said["y"])) for t in mep["prumadas"] if t["id"] in por_tq) + 2
    drenagem.append({"nome": "COL", "jusante": None, "tipo": "coletor", "comprimento_m": round(L_col, 1), "inclinacao_pct": 1.5, "dispositivos": []})
    can = instalacoes.canalizacao({"rede": rede + rede_q, "rede_drenagem": drenagem, "pressao_rede_kpa": 300, "ventilacao_secundaria": False})
    if any(round(f["div"]["cota"], 2) == z0 and z0 < -1.0 for f in fixos):
        hyp.append("aparelhos da cave abaixo da cota provável do coletor público: estação elevatória de águas residuais (bomba trituradora / poço) — a confirmar "
                   "com a cota da rede pública")
    hyp.append("cave não aquecida (conforme o estudo térmico): sem piso radiante na cave; prever aquecimento local se o ginásio for utilizado")
    # --- 6. quantidades (orçamento)
    Q = quantidades(m, divs, el, can, ufh, bc, fixos, rede, rede_q, drenagem)
    return {"divisoes": divs, "perdas": per, "phi": phi, "phi_total_w": phi_tot, "piso_radiante": ufh, "bomba_calor": bc, "eletricidade": el,
            "canalizacao": can, "rede_af": rede, "rede_aq": rede_q, "drenagem": drenagem, "aparelhos": fixos, "quantidades": Q, "hipoteses": hyp,
            "mep": mep, "niveis": niveis}


def quantidades(m, divs, el, can, ufh, bc, fixos, rede, rede_q, dren) -> dict:
    """Quantidades para o orçamento (unidades: m, un, m²)."""
    q: dict = {}
    # eletricidade
    q["tomadas"] = sum(p["tomadas"] for p in el["pontos"])
    q["pontos_luz"] = sum(p["pontos_luz"] for p in el["pontos"])
    q["interruptores"] = sum(max(1, p["pontos_luz"]) for p in el["pontos"])
    cabo = {}
    for c in el["circuitos"]:
        k = c["seccao"]
        n = max(1, int(c.get("pontos") or 1))
        L = c["comprimento_m"] * (1.0 + 0.25 * (n - 1) if c["familia"] in ("iluminacao", "tomadas") else 1.0) * 1.1
        cabo[k] = cabo.get(k, 0.0) + L * (5 if c.get("b") == 3 else 3) / 3       # m de cabo equivalente 3 condutores (5 c. trifásico)
    q["cabo_m"] = {f"{k:g}": round(v, 0) for k, v in sorted(cabo.items())}
    q["circuitos"] = len(el["circuitos"])
    q["diferenciais"] = el["diferenciais"]
    q["quadro_modulos"] = len(el["circuitos"]) + 2 * el["diferenciais"] + 8
    q["tubo_corrugado_m"] = round(sum(cabo.values()) * 0.9, 0)
    q["caixas"] = q["tomadas"] + q["pontos_luz"] + q["interruptores"] + len(divs)
    q["ponto_dedicado"] = sum(1 for c in el["circuitos"] if c["familia"] not in ("iluminacao", "tomadas"))
    # canalização
    tub = {}
    for r in (can.get("rede") or {}).get("trocos", []):
        k = (r.get("agua") or "fria", r.get("dn") or 20)
        tub[k] = tub.get(k, 0.0) + float(r.get("comprimento_m") or 0)
    q["tubo_agua_m"] = {f"{'AF' if a == 'fria' else 'AQ'} Ø{d}": round(v * 1.1, 1) for (a, d), v in sorted(tub.items())}
    if not tub:
        q["tubo_agua_m"] = {"AF Ø20": round(sum(t["comprimento_m"] for t in rede) * 1.1, 1), "AQ Ø20": round(sum(t["comprimento_m"] for t in rede_q) * 1.1, 1)}
    pvc = {}
    for r in (can.get("rede_drenagem") or {}).get("trocos", []):
        pvc[r.get("dn") or 50] = pvc.get(r.get("dn") or 50, 0.0) + float(r.get("comprimento_m") or 0)
    q["tubo_pvc_m"] = {f"Ø{k}": round(v * 1.1, 1) for k, v in sorted(pvc.items())}
    ap = {}
    for f in fixos:
        ap[f["a"]["tipo"]] = ap.get(f["a"]["tipo"], 0) + 1
    q["aparelhos"] = ap
    q["pontos_agua"] = sum(1 for _ in fixos) + sum(1 for f in fixos if instalacoes.DISPOSITIVOS[f["a"]["tipo"]][1])
    q["pontos_esgoto"] = sum(1 for f in fixos if instalacoes.DISPOSITIVOS[f["a"]["tipo"]][2] > 0)
    q["tubos_queda"] = len({f["prumada"] for f in fixos})
    q["estacao_elevatoria"] = 1 if any(f["div"]["cota"] < -1.0 for f in fixos) else 0
    # aquecimento
    q["piso_radiante_m2"] = round(sum(r["A_em"] for u in ufh.values() for r in u["divisoes"]), 1)
    q["tubo_pex_m"] = round(sum(u["tubo_total_m"] for u in ufh.values()), 0)
    q["circuitos_pr"] = sum(u["circuitos"] for u in ufh.values())
    q["coletores"] = [{"cota": c, "saidas": u["circuitos"]} for c, u in ufh.items()]
    q["bc_kw"] = bc["p_nominal_kw"]
    q["apoio_kw"] = bc.get("apoio_kw") or 0
    q["vaso_l"] = (bc.get("vaso") or {}).get("vaso_l") or 0
    q["deposito_inercia_l"] = bc.get("deposito_inercia_l") or 0
    n_oc = max(2, sum(1 for d in divs if d["tipo"] == "quarto") + 1)
    q["aqs_l"] = 300 if n_oc >= 4 else 200
    q["termostatos"] = sum(len(u["divisoes"]) for u in ufh.values())
    return q
