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


# ---------------------------------------------------------------- planta de fundação (geometria)
COTA_TXT = re.compile(r"COTA DO TOSCO\s+(\d+[.,]\d+)", re.I)


def _rects_preenchidos(page, k):
    """Polígonos cheios a cinzento claro (0,80–0,98) da planta : [(cor, x0, y0, x1, y1)] em metros (eixos da folha)."""
    out = []
    for g in page.get_drawings():
        f = g.get("fill")
        if not f or len(f) < 3 or not all(0.80 <= c <= 0.985 for c in f[:3]) or max(f[:3]) - min(f[:3]) > 0.02:
            continue
        r = g["rect"]
        if r.width * k < 0.08 and r.height * k < 0.08:
            continue
        out.append((round(f[0], 2), r.x0 * k, r.y0 * k, r.x1 * k, r.y1 * k))
    return out


def ler_planta(pdf: bytes) -> dict:
    """Planta de fundação : sapatas isoladas, sapatas lineares, vigas de equilíbrio (VEQ) e muros / paredes medidos na geometria
    (retângulos cheios), alturas pelos rótulos («Sapata linear de M4 1,0 x 0,4», «VEQ (0,30 x 0,50)», «MURO M4 (0,25)»),
    cotas («COTA DO TOSCO», «Cota sup. / Cota inf.», «COTA GERAL DE ESCAVAÇÃO») e o tosco do piso de cima (folha seguinte)."""
    import pymupdf
    from shapely.geometry import box
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    toscos = []
    for p in doc:
        for m in COTA_TXT.finditer(" ".join(p.get_text().split())):
            toscos.append(_f(m.group(1)))
    toscos = sorted(set(toscos))
    for ip, page in enumerate(doc):
        txt = " ".join(page.get_text().split())
        if not re.search(r"Planta de Funda[çc][ãa]o", txt, re.I):
            continue
        esc = re.search(r"PLANTA\s+Escala\s+1\s*[:/]\s*(\d+)", txt, re.I) or re.search(r"Escala\s+1\s*[:/]\s*(\d+)", txt, re.I)
        if not esc:
            continue
        k = 0.0254 / 72 * int(esc.group(1))
        rects = _rects_preenchidos(page, k)
        if len(rects) < 2:
            continue
        cores = sorted({c for c, *_ in rects})
        if len(cores) < 2:
            continue
        cf, cm = max(cores), min(cores)                     # mais clara = fundações ; mais escura = muros / paredes
        blocos = [(" ".join(b[4].split()), ((b[0] + b[2]) / 2 * k, (b[1] + b[3]) / 2 * k)) for b in page.get_text("blocks")]
        words = page.get_text("words")
        lin, csup = [], []
        for w in words:                                        # rótulos «Sapata linear de M4 / 1,0 x 0,4 / Cota sup. 100,90» em palavras soltas
            if w[4].lower() != "linear":
                continue
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            horiz = (w[2] - w[0]) >= (w[3] - w[1])          # texto direito ou rodado (folhas A0 a 90°/270°)
            viz = sorted((x for x in words if abs((x[0] + x[2]) / 2 - cx) < 60 and abs((x[1] + x[3]) / 2 - cy) < 60),
                         key=(lambda x: (round((x[1] + x[3]) / 2 / 6), x[0])) if horiz else
                             (lambda x: (round((x[0] + x[2]) / 2 / 6), (x[1] + x[3]) / 2)))
            t = " ".join(x[4] for x in viz)
            m = re.search(r"(\d+[.,]?\d*)\s*x\s*(\d+[.,]\d+)", t)
            if m:
                lin.append((_f(m.group(1)), _f(m.group(2))))
            cotas = [_f(x) for x in re.findall(r"\b(\d{2,3}[.,]\d{2})\b", t)]
            if len(cotas) >= 2:
                csup.append(max(cotas))                        # «Cota sup.» e «Cota inf.» : a de cima é a superior
        veq = [(_f(m.group(1)), _f(m.group(2))) for t, _ in blocos for m in re.finditer(r"VEQ\s*\(?\s*(\d+[.,]\d+)\s*x\s*(\d+[.,]\d+)", t)]
        m_esc = re.search(r"COTA GERAL DE ESCAVA[ÇC][ÃA]O\s+(\d+[.,]\d+)", txt, re.I)
        m_tos = COTA_TXT.search(txt)
        muros_lbl = [(m.group(1), _f(m.group(2)), p) for t, p in blocos for m in re.finditer(r"MURO\s+(M\d+)\s*\((\d+[.,]\d+)\)", t)]
        par_lbl = [p for t, p in blocos if re.fullmatch(r"PAR\s*\d+", t)]
        found = {"isoladas": [], "lineares": [], "veq": [], "muros": [], "paredes": [], "outros": []}
        for c, x0, y0, x1, y1 in rects:
            w, h = x1 - x0, y1 - y0
            a, b = min(w, h), max(w, h)
            g = box(x0, y0, x1, y1)
            if c == cf:
                if a >= 0.9 and b / a < 1.8:
                    found["isoladas"].append(g)
                elif 0.25 <= a <= 0.35 and b >= 0.8:
                    found["veq"].append(g)
                elif 0.55 <= a <= 1.6 and b / a >= 1.8:
                    found["lineares"].append(g)
                else:
                    found["outros"].append(g)
            elif c == cm and 0.15 <= a <= 0.4 and b >= 0.8:
                cx, cy = g.centroid.x, g.centroid.y
                d_par = min((((cx - p[0]) ** 2 + (cy - p[1]) ** 2) ** 0.5 for p in par_lbl), default=1e9)
                d_mur = min((((cx - p[0]) ** 2 + (cy - p[1]) ** 2) ** 0.5 for _, _, p in muros_lbl), default=1e9)
                (found["paredes"] if d_par < d_mur and d_par < 4.0 else found["muros"]).append((g, a))
        lt = re.search(r"((?:\S+\s+){0,40})LAJE T[ÉE]RREA", txt)
        esp = [_f(x) for x in re.findall(r"\b(0[.,]\d{2})\b", lt.group(1))] if lt else []
        malha = re.search(r"Malhasol\s*\(?\s*(A[QR]\s*\d+)", txt, re.I)
        return {"pagina": ip, "escala": int(esc.group(1)), "laje_terrea": esp[:2] if len(esp) >= 2 else None,
                "malha": malha.group(1).replace(" ", "") if malha else None, "isoladas": found["isoladas"], "lineares": found["lineares"],
                "veq": found["veq"], "muros": found["muros"], "paredes": found["paredes"], "outros": found["outros"],
                "h_linear": sorted({h for _, h in lin}), "lin_lbl": lin, "veq_sec": veq[0] if veq else None,
                "cota_sup_linear": max(csup) if csup else None, "cota_escavacao": _f(m_esc.group(1)) if m_esc else None,
                "tosco_fundacao": _f(m_tos.group(1)) if m_tos else None, "toscos": toscos,
                "muros_lbl": [(n, e) for n, e, _ in muros_lbl]}
    return {}


def linhas_planta(pl: dict, quadro: dict | None = None, origem: str = "", area_laje_terrea: float | None = None) -> list:
    """Linhas do mapa a partir da planta de fundação : sapatas lineares, VEQ, muros, paredes do núcleo, laje térrea."""
    from shapely.ops import unary_union
    if not pl:
        return []
    out = []
    pag = f"planta de fundação, folha {pl['pagina'] + 1}" + (f" de {origem}" if origem else "")
    iso = unary_union(pl["isoladas"]) if pl["isoladas"] else None
    lin = unary_union(pl["lineares"]) if pl["lineares"] else None
    # sapatas lineares (H = altura do rótulo com a mesma largura)
    if lin is not None and pl["h_linear"]:
        por_h = defaultdict(float)
        for g in pl["lineares"]:
            a = min(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1])
            hh = min(pl["lin_lbl"], key=lambda t: abs(t[0] - a))[1] if pl["lin_lbl"] else pl["h_linear"][0]
            por_h[hh] += g.area
        dup = sum(g.area for g in pl["lineares"]) - lin.area             # cruzamentos contados uma vez
        for hh, ar in por_h.items():
            ar_liq = ar - dup * ar / max(sum(por_h.values()), 1e-9)
            out.append(dict(capitulo="Fundações", piso="Fundação", designacao=f"Sapatas lineares dos muros h = {hh:.2f} m — betão",
                            descricao=f"área em planta {ar_liq:.2f} m² (cruzamentos uma vez) × {hh:.2f} ; {pag}", qtd=ar_liq * hh, un="m³", refs=""))
            out.append(dict(capitulo="Fundações", piso="Fundação", designacao=f"Sapatas lineares h = {hh:.2f} m — betão de limpeza 0,10 m",
                            descricao=f"{ar_liq:.2f} m² × 0,10", qtd=ar_liq * 0.10, un="m³", refs=""))
        per = lin.length
        hmed = max(pl["h_linear"])
        out.append(dict(capitulo="Fundações", piso="Fundação", designacao="Sapatas lineares — cofragem lateral",
                        descricao=f"perímetro {per:.2f} m × {hmed:.2f}", qtd=per * hmed, un="m²", refs=""))
    # vigas de equilíbrio
    if pl["veq"]:
        sec = pl["veq_sec"]
        V = unary_union(pl["veq"])
        if iso is not None:
            V = V.difference(iso)
        if lin is not None:
            V = V.difference(lin)
        hh = sec[1] if sec else None
        L = V.area / (sec[0] if sec else 0.30)
        if hh:
            out.append(dict(capitulo="Fundações", piso="Fundação", designacao=f"Vigas de equilíbrio VEQ {sec[0]:.2f} × {hh:.2f} — betão",
                            descricao=f"{len(pl['veq'])} troços, {L:.2f} m entre sapatas × {sec[0]:.2f} × {hh:.2f} ; {pag}", qtd=V.area * hh, un="m³", refs="VEQ"))
            out.append(dict(capitulo="Fundações", piso="Fundação", designacao="Vigas de equilíbrio — cofragem lateral",
                            descricao=f"2 × {L:.2f} m × {hh:.2f}", qtd=2 * L * hh, un="m²", refs="VEQ"))
            out.append(dict(capitulo="Fundações", piso="Fundação", designacao="Vigas de equilíbrio — betão de limpeza 0,10 m",
                            descricao=f"{V.area:.2f} m² × 0,10", qtd=V.area * 0.10, un="m³", refs="VEQ"))
    # muros de suporte da cave : do topo da sapata linear ao tosco do piso de cima
    topo = next((t for t in pl["toscos"] if pl.get("tosco_fundacao") and t > pl["tosco_fundacao"] + 1.5), None)
    base = pl.get("cota_sup_linear")
    if pl["muros"]:
        tudo = unary_union([g for g, _ in pl["muros"]] + pl["lineares"] + pl["isoladas"]).buffer(1.5).buffer(-1.5)
        contorno = tudo.exterior if tudo.geom_type == "Polygon" else max(tudo.geoms, key=lambda g: g.area).exterior
        L_ext = sum(g.area / e for g, e in pl["muros"] if contorno.distance(g.centroid) < 1.2)   # muros do contorno (enterrados)
        por_e = defaultdict(list)
        for g, e in pl["muros"]:
            por_e[round(e, 2)].append(g)
        for e, gs in sorted(por_e.items()):
            U = unary_union(gs)
            L = U.area / e
            nomes = ", ".join(n for n, ee in pl["muros_lbl"] if abs(ee - e) < 0.01)
            if topo and base:
                hm = topo - base
                out.append(dict(capitulo="Fundações", piso="Cave", designacao=f"Muros de suporte e = {e:.2f} m — betão",
                                descricao=f"{L:.2f} m × {hm:.2f} m (cota sup. da sapata {base:.2f} → tosco do R/C {topo:.2f}) × {e:.2f}",
                                qtd=L * hm * e, un="m³", refs=nomes))
                out.append(dict(capitulo="Fundações", piso="Cave", designacao=f"Muros de suporte e = {e:.2f} m — cofragem (2 faces)",
                                descricao=f"2 × {L:.2f} × {hm:.2f}", qtd=2 * L * hm, un="m²", refs=nomes))

            else:
                out.append(dict(capitulo="Fundações", piso="Cave", designacao=f"Muros de suporte e = {e:.2f} m — comprimento",
                                descricao="altura por ler (cotas)", qtd=L, un="m", refs=nomes, estado="altura a confirmar"))
    if pl["muros"] and topo and base:
        out.append(dict(capitulo="Fundações", piso="Cave", designacao="Muros do contorno — impermeabilização e drenagem da face enterrada",
                        descricao=f"{L_ext:.2f} m de muro no contorno exterior × {topo - base:.2f} m", qtd=L_ext * (topo - base), un="m²",
                        refs="muros do contorno"))
    if pl["paredes"] and topo and base:
        U = unary_union([g for g, _ in pl["paredes"]])
        out.append(dict(capitulo="Estrutura", piso="Cave", designacao="Paredes do núcleo (PAR) — betão",
                        descricao=f"área em planta {U.area:.2f} m² × {topo - base:.2f} m", qtd=U.area * (topo - base), un="m³", refs="PAR 1, PAR 2"))
    # laje térrea da cave : área do piso enterrado medida na planta de arquitetura (compartimentos, à face interior das paredes)
    A = area_laje_terrea or 0.0
    lt = pl.get("laje_terrea")
    if A > 5 and lt:
        e_l, e_tv = lt[0], lt[1]
        if True:
            out += [dict(capitulo="Fundações", piso="Cave", designacao=f"Laje térrea e = {e_l:.2f} m — betão",
                         descricao=f"{A:.2f} m² (compartimentos da cave, planta de arquitetura) × {e_l:.2f} (pormenor «LAJE TÉRREA»)",
                         qtd=A * e_l, un="m³", refs="laje térrea"),
                    dict(capitulo="Fundações", piso="Cave", designacao=f"Laje térrea — malha eletrossoldada {pl.get('malha') or ''} (pormenor)".replace("  ", " "), descricao=f"{A:.2f} m²",
                         qtd=A, un="m²", refs="laje térrea"),
                    dict(capitulo="Fundações", piso="Cave", designacao="Laje térrea — tela de polietileno 0,2 mm", descricao=f"{A:.2f} m²", qtd=A, un="m²", refs="laje térrea"),
                    dict(capitulo="Movimento de terras", piso="Cave", designacao=f"Tout-venant compactado {e_tv:.2f} m sob a laje térrea", descricao=f"{A:.2f} m² × {e_tv:.2f}",
                         qtd=A * e_tv, un="m³", refs="laje térrea")]
            if pl.get("cota_escavacao") and pl.get("tosco_fundacao"):
                out.append(dict(capitulo="Movimento de terras", piso="Cave", designacao=f"Escavação geral até à cota {pl['cota_escavacao']:.2f}",
                                descricao="área da implantação × (cota do terreno natural − cota de escavação) : cota do terreno no levantamento topográfico",
                                qtd=None, un="m³", refs="", estado="a medir"))
    return out
