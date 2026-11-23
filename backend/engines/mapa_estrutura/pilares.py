"""QUADRO DE PILARES (tabela gráfica do projeto de estrutura) → betão, cofragem e aço de cada pilar, troço a troço.

Leitura (coordenadas da folha como se vê, depois da rotação) :
- colunas = grupos de pilares do cabeçalho («P3=P6=P19=P20=P21 P22=P23=P24» → 8 pilares iguais) ;
- linhas = troços entre as cotas escritas à direita (116,12 / 113,43 / …) ; o último troço vai até à fundação
  (cota superior das sapatas lida na planta de fundação) ;
- em cada célula : secção (cota horizontal = largura, cota vertical = altura, acima dos estribos), «Arm. Long.: 4Ø16+6Ø12»,
  estribos desenhados «1Ø6(1,38)» / «2Ø6(0,34)» (n.º de ramos e comprimento de cada um) e a tabela Intervalo / Núm. / Separação
  (número de estribos do troço = soma da coluna Núm.) ; células sem «Arm.» = pilar inexistente nesse troço.
- emendas : «80Ø do varão, para o comprimento de sobreposição» (lido nas notas) em cada troço que continua para cima ;
  amarração na fundação : «50Ø do varão, para o comprimento de amarração»."""
from __future__ import annotations

import re

from .fundacoes import KG_M, _f

LONG = re.compile(r"(\d+)Ø(\d+)")
EST = re.compile(r"^(\d+)Ø(\d+)\((\d+[.,]\d+)\)$")


def ler(doc, base_fundacao: float | None = None) -> dict:
    import pymupdf
    for ip, p in enumerate(doc):
        if "QUADRO DE PILARES" not in " ".join(p.get_text().split()):
            continue
        Mx = p.rotation_matrix
        W = []
        for w in p.get_text("words"):
            r = pymupdf.Rect(w[:4]) * Mx
            W.append((r.x0, r.y0, r.x1, r.y1, w[4]))
        txt = " ".join(p.get_text().split())
        m = re.search(r"(\d+)Ø do varão, para o comprimento de sobreposi", txt)
        sob = int(m.group(1)) if m else None
        m = re.search(r"(\d+)Ø do varão, para o comprimento de amarra", txt)
        amar = int(m.group(1)) if m else None
        hdr = sorted([w for w in W if re.fullmatch(r"P[A-Z]?\d+(=P[A-Z]?\d+)*", w[4])], key=lambda w: w[1])
        if not hdr:
            continue
        ytop = min(w[1] for w in hdr)
        hdr = [w for w in hdr if w[1] < ytop + 20]
        cols = {}
        for w in hdr:                                       # cabeçalho em duas linhas («P3=…» / «P22=…») : mesma coluna
            cx = round((w[0] + w[2]) / 2 / 40)
            cols.setdefault(cx, []).append(w)
        colunas = []
        for ws in cols.values():
            nomes = [n for w in ws for n in w[4].split("=")]
            x0 = min(w[0] for w in ws)
            x1 = max(w[2] for w in ws)
            colunas.append({"nomes": nomes, "cx": (x0 + x1) / 2})
        colunas.sort(key=lambda c: c["cx"])
        for i, c in enumerate(colunas):
            c["x0"] = (colunas[i - 1]["cx"] + c["cx"]) / 2 if i else c["cx"] - 80
            c["x1"] = (c["cx"] + colunas[i + 1]["cx"]) / 2 if i + 1 < len(colunas) else c["cx"] + 80
        xmax = max(c["x1"] for c in colunas)
        niveis = sorted([(w[1], _f(w[4])) for w in W if re.fullmatch(r"1?\d\d,\d\d", w[4]) and xmax - 10 < w[0] < xmax + 200], key=lambda t: t[0])
        if len(niveis) < 2:
            continue
        linhas = []
        for (ya, ca), (yb, cb) in zip(niveis, niveis[1:]):
            linhas.append({"y0": ya, "y1": yb, "topo": ca, "base": cb})
        if base_fundacao:                                    # último troço : da cota mais baixa até à fundação
            yb = niveis[-1][0]
            altura_px = (niveis[-1][0] - niveis[-2][0]) * 1.2
            linhas.append({"y0": yb, "y1": yb + altura_px, "topo": niveis[-1][1], "base": base_fundacao, "fundacao": True})
        pilares = []
        for c in colunas:
            for L in linhas:
                cel = [w for w in W if c["x0"] <= (w[0] + w[2]) / 2 < c["x1"] and L["y0"] + 8 < (w[1] + w[3]) / 2 <= L["y1"] + 8]
                if not any(w[4] == "Arm." for w in cel):
                    continue
                cel.sort(key=lambda w: (round(w[1] / 4), w[0]))
                t = " ".join(w[4] for w in cel)
                ml = re.search(r"Long\.:\s*([\dØ+]+)", t)
                if not ml:
                    continue
                longit = [(int(a), int(b)) for a, b in LONG.findall(ml.group(1))]
                est = [(int(m.group(1)), int(m.group(2)), _f(m.group(3))) for w in cel for m in [EST.match(w[4])] if m]
                y_est = min((w[1] for w in cel if EST.match(w[4])), default=1e9)
                dims = [w for w in cel if re.fullmatch(r"0,\d\d|1,\d\d", w[4]) and w[1] < y_est]
                hz = sorted([w for w in dims if (w[2] - w[0]) >= (w[3] - w[1])], key=lambda w: w[1])
                vt = sorted([w for w in dims if (w[2] - w[0]) < (w[3] - w[1])], key=lambda w: w[1])
                if not hz or not vt:
                    continue
                b, h = _f(hz[0][4]), _f(vt[0][4])
                ys_tab = [w for w in cel if w[1] > y_est]
                nums = []                                     # coluna «Núm.» : inteiros na posição x do título «Núm.»
                tit = [w for w in cel if w[4] == "Núm."]
                if tit:
                    xn = (tit[0][0] + tit[0][2]) / 2
                    nums = [int(w[4]) for w in ys_tab if re.fullmatch(r"\d{1,2}", w[4]) and abs((w[0] + w[2]) / 2 - xn) < 12]
                pilares.append({"nomes": c["nomes"], "n": len(c["nomes"]), "b": b, "h": h, "topo": L["topo"], "base": L["base"],
                                "H": round(L["topo"] - L["base"], 3), "long": longit, "estribos": est, "n_estribos": sum(nums),
                                "fundacao": bool(L.get("fundacao"))})
        if pilares:
            return {"pagina": ip, "pilares": pilares, "sobreposicao": sob, "amarracao": amar}
    return {}


def linhas_mapa(q: dict, origem: str = "") -> list:
    if not q:
        return []
    out = []
    org = f"quadro de pilares, folha {q['pagina'] + 1}" + (f" de {origem}" if origem else "")
    sob, amar = q.get("sobreposicao"), q.get("amarracao")
    for p in q["pilares"]:
        nomes = "=".join(p["nomes"])
        piso = f"Pilares {p['base']:.2f} → {p['topo']:.2f}".replace(".", ",")
        n, b, h, H = p["n"], p["b"], p["h"], p["H"]
        out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Pilar {b:.2f} × {h:.2f} — betão", descricao=f"{n} × {b:.2f} × {h:.2f} × {H:.2f} ; {org}",
                        qtd=n * b * h * H, un="m³", refs=nomes))
        out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Pilar {b:.2f} × {h:.2f} — cofragem", descricao=f"{n} × 2 × ({b:.2f} + {h:.2f}) × {H:.2f}",
                        qtd=n * 2 * (b + h) * H, un="m²", refs=nomes))
        for nb, d in p["long"]:
            extra, nota = 0.0, ""
            if p["fundacao"] and amar:
                extra += amar * d / 1000
                nota += f" + amarração {amar}Ø"
            if sob and p["topo"] < max(x["topo"] for x in q["pilares"] if x["nomes"] == p["nomes"]):
                extra += sob * d / 1000
                nota += f" + emenda {sob}Ø"
            comp = H + extra
            out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Pilar — aço longitudinal {nb}Ø{d}",
                            descricao=f"{n} × {nb} × ({H:.2f}{nota} = {comp:.2f} m) × {KG_M.get(d, 0):.3f} kg/m",
                            qtd=n * nb * comp * KG_M.get(d, 0), un="kg", refs=nomes))
        if p["estribos"] and p["n_estribos"]:
            por_est = sum(r * c for r, d, c in p["estribos"])
            d = p["estribos"][0][1]
            out.append(dict(capitulo="Estrutura", piso=piso, designacao=f"Pilar — estribos Ø{d} ({' + '.join(f'{r}Ø{dd}({c:.2f})' for r, dd, c in p['estribos'])})",
                            descricao=f"{n} × {p['n_estribos']} estribos × {por_est:.2f} m × {KG_M.get(d, 0):.3f} kg/m",
                            qtd=n * p["n_estribos"] * por_est * KG_M.get(d, 0), un="kg", refs=nomes))
    return out
