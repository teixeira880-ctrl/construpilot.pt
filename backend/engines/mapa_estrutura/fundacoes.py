"""Fundações a partir do QUADRO DE ELEMENTOS DE FUNDAÇÃO do projeto de estrutura (PDF vetorial) : referências, dimensões,
altura e armaduras inferiores / superiores em X e Y (ex. «10Ø12af.0,15»). Para cada linha do quadro :

- número de sapatas = número de referências listadas («P14, P27 e P28» → 3 ; «PAR 1-PAR 2» → 1, sapata comum) ;
- betão = Lx × Ly × H × n ; cofragem lateral = 2 (Lx + Ly) H × n ; betão de limpeza = Lx × Ly × 0,10 × n (pormenor do projeto) ;
- aço : n varões por direção, comprimento = dimensão − 2 × recobrimento (recobrimento lido nas notas, «recobrimento de 80 mm»),
  massa nominal do varão (EN 10080 : 0,222 / 0,395 / 0,617 / 0,888 / 1,208 / 1,578 / 2,466 kg/m para Ø6…Ø20).

As dobras / amarrações não estão no quadro : o aço é o dos troços retos medidos, e isso fica escrito em cada linha (sem rácio)."""
from __future__ import annotations

import re
from collections import defaultdict

KG_M = {6: 0.222, 8: 0.395, 10: 0.617, 12: 0.888, 16: 1.578, 20: 2.466, 25: 3.853, 32: 6.313}
ARM = re.compile(r"(\d+)\s*Ø\s*(\d+)\s*af\.?\s*(\d+[.,]\d+)", re.I)
DIM = re.compile(r"(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)", re.I)


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def _refs(txt: str) -> list:
    """«P14, P27 e P28» → [P14, P27, P28] ; «PAR 1-PAR 2» → [PAR 1-PAR 2] (uma sapata comum)."""
    partes = [p.strip() for p in re.split(r",|\be\b", txt) if p.strip()]
    return partes or [txt.strip()]


def ler_quadro(pdf: bytes) -> dict:
    """{"linhas": [{refs, n, lx, ly, h, arm: {inf_x, inf_y, sup_x, sup_y}}], "recobrimento": m, "pagina": i} ou {}."""
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    for ip, page in enumerate(doc):
        words = page.get_text("words")
        tit = [w for w in words if w[4].upper() == "FUNDAÇÃO"]
        quadro = [w for w in words if w[4].upper() == "QUADRO"]
        if not tit or not quadro:
            continue
        txt = page.get_text()
        m = re.search(r"recobrimento\s+de\s+(\d+)\s*mm", txt, re.I)
        rec = int(m.group(1)) / 1000 if m else None
        for q in quadro:
            # cabeçalho «Referências … Dimensões … Altura … Armadura» na mesma linha de texto, perto do título
            vert = abs(q[2] - q[0]) < abs(q[3] - q[1])                     # texto rodado (folha a 90°/270°)
            eixo = (lambda w: (w[0] + w[2]) / 2) if vert else (lambda w: (w[1] + w[3]) / 2)
            ao_longo = (lambda w: (w[1] + w[3]) / 2) if vert else (lambda w: (w[0] + w[2]) / 2)
            cab = [w for w in words if w[4] in ("Referências", "Dimensões", "Altura") and abs(eixo(w) - eixo(q)) < 40]
            if len(cab) < 3:
                continue
            c0 = eixo(cab[0])
            col = {w[4]: ao_longo(w) for w in cab}
            arm_cols = sorted(ao_longo(w) for w in words if w[4] == "Armadura" and abs(eixo(w) - c0) < 3)
            sinal = -1 if eixo(q) > c0 else 1                               # as linhas ficam do lado oposto ao título
            linhas = defaultdict(list)
            for w in words:
                d = (eixo(w) - c0) * sinal
                if 3 < d < 400 and min(col.values()) - 80 < ao_longo(w) < (arm_cols[-1] if arm_cols else col["Altura"]) + 120:
                    linhas[round(eixo(w) / 4)].append(w)
            out = []
            for k in sorted(linhas, key=lambda k: abs(k * 4 - c0)):
                ws = sorted(linhas[k], key=ao_longo)
                ref = " ".join(w[4] for w in ws if ao_longo(w) < (col["Dimensões"] + col["Referências"]) / 2 + 10)
                dim = next((DIM.fullmatch(w[4]) for w in ws if DIM.fullmatch(w[4])), None)
                alt = next((w[4] for w in ws if abs(ao_longo(w) - col["Altura"]) < 25 and re.fullmatch(r"\d+[.,]\d+", w[4])), None)
                arms = [(ao_longo(w), ARM.fullmatch(w[4])) for w in ws if ARM.fullmatch(w[4])]
                if not dim or not alt or not ref:
                    if out:
                        break                                               # fim do quadro
                    continue
                pos = {}
                nomes = ["inf_x", "inf_y", "sup_x", "sup_y"]
                for y, a in arms:
                    j = min(range(len(arm_cols)), key=lambda i: abs(arm_cols[i] - y)) if arm_cols else len(pos)
                    if j < 4:
                        pos[nomes[j]] = {"n": int(a.group(1)), "d": int(a.group(2)), "af": _f(a.group(3)), "txt": a.group(0)}
                refs = _refs(ref)
                out.append({"refs": refs, "ref_txt": ref, "n": len(refs), "lx": _f(dim.group(1)), "ly": _f(dim.group(2)), "h": _f(alt), "arm": pos})
            if out:
                return {"linhas": out, "recobrimento": rec, "pagina": ip}
    return {}


def linhas_mapa(quadro: dict, origem: str = "") -> list:
    """Linhas do mapa (capítulo Fundações) para o mapa premium."""
    if not quadro:
        return []
    rec = quadro.get("recobrimento")
    out = []
    pag = f"quadro de elementos de fundação, folha {quadro['pagina'] + 1}" + (f" de {origem}" if origem else "")
    aco = defaultdict(float)
    aco_refs = defaultdict(list)
    for r in quadro["linhas"]:
        lx, ly, h, n = r["lx"], r["ly"], r["h"], r["n"]
        tit = f"Sapata {lx:.2f} × {ly:.2f} × {h:.2f} m".replace(".", ",")
        refs = ", ".join(r["refs"])
        out.append(dict(capitulo="Fundações", piso="Fundação", designacao=f"{tit} — betão", descricao=f"{n} × {lx:.2f} × {ly:.2f} × {h:.2f} ; {pag}",
                        qtd=lx * ly * h * n, un="m³", refs=refs))
        out.append(dict(capitulo="Fundações", piso="Fundação", designacao=f"{tit} — cofragem lateral", descricao=f"{n} × 2 × ({lx:.2f} + {ly:.2f}) × {h:.2f}",
                        qtd=2 * (lx + ly) * h * n, un="m²", refs=refs))
        out.append(dict(capitulo="Fundações", piso="Fundação", designacao=f"{tit} — betão de limpeza 0,10 m", descricao=f"{n} × {lx:.2f} × {ly:.2f} × 0,10 (pormenor «Betão de limpeza 0,10»)",
                        qtd=lx * ly * 0.10 * n, un="m³", refs=refs))
        if rec is None:
            continue
        for k, a in r["arm"].items():
            comp = (lx if k.endswith("x") else ly) - 2 * rec
            kg = a["n"] * comp * KG_M.get(a["d"], 0) * n
            aco[a["d"]] += kg
            aco_refs[a["d"]].append(f"{refs} {k.replace('_', ' ')} {a['txt']}")
            out.append(dict(capitulo="Fundações", piso="Fundação", designacao=f"{tit} — aço {k.replace('_', ' ')} {a['txt']}",
                            descricao=f"{n} sapata(s) × {a['n']} varões × ({(lx if k.endswith('x') else ly):.2f} − 2 × {rec:.3f}) = "
                                      f"{a['n'] * comp * n:.2f} m × {KG_M.get(a['d'], 0):.3f} kg/m ; troços retos (dobras no pormenor)",
                            qtd=kg, un="kg", refs=refs, estado="medido (sem dobras)"))
    return out
