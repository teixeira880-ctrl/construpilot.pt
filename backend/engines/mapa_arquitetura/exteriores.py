"""Arranjos exteriores e espaço público (estrada de acesso, passeios, lancis, muros de vedação) lidos no DWFX.

- Zonas de pavimento = regiões cobertas pela trama de cada camada (Paver, trama do arruamento, calçada…), fechadas pelos próprios
  traços da trama ; a implantação do edifício e as camadas do levantamento topográfico (T0x-…) ficam de fora.
- Camadas de cada pavimento = legenda «Descrição das camadas» da folha (espessuras escritas : «0,06m», «4 cm»…), agrupadas
  por tipo de pavimento pelas palavras da legenda (paver / passeio / areia / base granular → passeio ; betuminos / sub base →
  arruamento). O agrupamento fica escrito em cada linha.
- Lancil = linha de limite do passeio (camada LIMPASSEIO / lancil / guia) ; muros de vedação = pares de linhas da camada MUROS.
Controlo cruzado : a «área cedida para domínio público» escrita na folha é comparada com a área do passeio medida."""
from __future__ import annotations

import math
import re

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from . import dwfx, plantas

FOLHA = re.compile(r"espa[cç]o p[uú]blico|arranjos? exteriores|arruamento|via de acesso", re.I)
TOPO = re.compile(r"^T\d\d-", re.I)
ESP = re.compile(r"(\d+[.,]\d+)\s*m\b|(\d+)\s*cm\b", re.I)


def _esp(t: str):
    m = ESP.search(t)
    if not m:
        return None
    return float(m.group(1).replace(",", ".")) if m.group(1) else int(m.group(2)) / 100


def legenda(folha) -> list:
    """[(n.º, texto, espessura m | None)] da «Descrição das camadas» (linhas «N - …» ; a linha seguinte sem número completa a anterior)."""
    t = sorted([e for e in folha.elementos if e.tipo == "texto"], key=lambda e: (round(e.pos[1], 1), e.pos[0]))
    itens = []
    for e in t:
        m = re.match(r"^(\d{1,2})\s*-\s*(.+)$", e.texto.strip())
        if m:
            itens.append([int(m.group(1)), m.group(2).strip(), e.pos])
        elif itens and re.match(r"^com\s", e.texto.strip(), re.I) and abs(e.pos[1] - itens[-1][2][1]) < 1.5:
            itens[-1][1] += " " + e.texto.strip()
    vistos, out = set(), []
    for n, txt, _ in sorted(itens):
        if n not in vistos:
            vistos.add(n)
            out.append((n, txt, _esp(txt)))
    return out


def _grupo(txt: str) -> str | None:
    t = txt.lower()
    if re.search(r"betumin|sub.?base|asfalt", t):
        return "arruamento"
    if re.search(r"paver|passeio|areia|granular britado|calçada|cubo", t):
        return "passeio"
    return None


def medir(z, lista, papeis_forcados=None) -> dict:
    out = {"zonas": [], "lancil": 0.0, "muros": [], "legenda": [], "folha": None, "area_cedida": None}
    for i, (_, _, nome) in enumerate(lista):
        if not FOLHA.search(nome):
            continue
        f = dwfx.ler(z, i, lista)
        if not f.upm:
            continue
        leg = legenda(f)
        if not leg:
            continue
        txt = " ".join(e.texto for e in f.elementos if e.tipo == "texto")
        m = re.search(r"cedida.{0,80}?(\d+[.,]\d+)\s*m\s*[2²]", txt, re.I | re.S)
        out.update(folha=nome, legenda=leg, area_cedida=float(m.group(1).replace(",", ".")) if m else None)
        # implantação do edifício (não é pavimento)
        bld = [Polygon(pl).buffer(0) for e in f.elementos if e.tipo == "path" and re.search(r"tramarch|implant|constru", e.camada or "", re.I)
               and not TOPO.match(e.camada or "") for pl in e.pls if len(pl) >= 4]
        B = unary_union(bld).buffer(0.2) if bld else None
        por = {}
        for e in f.elementos:
            if e.tipo != "path" or TOPO.match(e.camada or "") or not re.search(r"paver|trama$|pavim|calçad|betumin|asfalt", e.camada or "", re.I):
                continue
            for pl in e.pls:
                for a, b in zip(pl, pl[1:]):
                    if a != b:
                        s = LineString([a, b])
                        if B is None or not B.contains(s):
                            por.setdefault(e.camada, []).append(s)
        # zona da intervenção = à volta das linhas de lancil e dos muros (os pormenores ao lado da planta ficam de fora)
        ref = [LineString(pl) for e in f.elementos if e.tipo == "path" and re.search(r"limpasseio|lancil|^muros?$|limite lote", e.camada or "", re.I)
               and not TOPO.match(e.camada or "") for pl in e.pls if len(pl) > 1]
        Z = unary_union(ref).envelope.buffer(15) if ref else None
        for cam, segs in por.items():
            if Z is not None:
                segs = [s_ for s_ in segs if Z.contains(s_)]
            if len(segs) < 100:                                  # uma trama tem centenas de traços
                continue
            U = unary_union([s.buffer(0.3) for s in segs]).buffer(-0.3)
            zonas = [g for g in getattr(U, "geoms", [U]) if g.area > 5]
            if zonas:
                tipo = "passeio" if re.search(r"paver|calçad", cam, re.I) else "arruamento"
                out["zonas"].append({"camada": cam, "tipo": tipo, "area": round(sum(g.area for g in zonas), 2), "n": len(zonas)})
        out["lancil"] = round(sum(math.dist(a, b) for e in f.elementos if e.tipo == "path" and re.search(r"limpasseio|lancil", e.camada or "", re.I)
                                  and not TOPO.match(e.camada or "") for pl in e.pls for a, b in zip(pl, pl[1:])), 2)
        mu = [(a, b) for e in f.elementos if e.tipo == "path" and re.fullmatch(r"muros?", e.camada or "", re.I) for pl in e.pls
              for a, b in zip(pl, pl[1:]) if math.dist(a, b) > 0.1]
        out["muros"] = [{"t": p["t"], "L": p["L"]} for p in plantas.paredes_duplas(mu, 0.1, 0.45)]
        break
    return out


def linhas_mapa(ex: dict) -> list:
    if not ex or not ex.get("folha"):
        return []
    out = []
    org = f"folha «{ex['folha']}»"
    for zz in ex["zonas"]:
        A = zz["area"]
        nome = "Passeio / estacionamento" if zz["tipo"] == "passeio" else "Arruamento / alargamento da via"
        desc = f"área da trama «{zz['camada']}» ({zz['n']} zona(s)) ; {org}"
        if zz["tipo"] == "passeio" and ex.get("area_cedida"):
            desc += f" ; controlo : área cedida ao domínio público escrita na folha {ex['area_cedida']:.2f} m²"
        out.append(dict(capitulo="Arranjos exteriores e espaço público", piso="Exterior", designacao=f"{nome} — área", descricao=desc,
                        qtd=A, un="m²", refs=zz["camada"]))
        tem_passeio = any(re.search(r"passeio", t, re.I) for _, t, _ in ex["legenda"])
        for n, txt, e in ex["legenda"]:
            g = _grupo(txt)
            if g != zz["tipo"] or e is None:
                continue
            if tem_passeio and re.search(r"estacionamento", txt, re.I):
                continue                                     # estacionamento em paver : zona própria (não separada na trama) — não se soma ao passeio
            out.append(dict(capitulo="Arranjos exteriores e espaço público", piso="Exterior", designacao=f"{nome} — camada {n} : {txt[:70]}",
                            descricao=f"{A:.2f} m² × {e:.2f} m (legenda da folha ; camada atribuída ao {zz['tipo']} pela descrição)",
                            qtd=A * e, un="m³", refs=f"legenda {n}"))
    if ex["lancil"]:
        lan = [(n, t) for n, t, _ in ex["legenda"] if re.search(r"lancil|guia", t, re.I)]
        out.append(dict(capitulo="Arranjos exteriores e espaço público", piso="Exterior",
                        designacao="Lancil pré-fabricado (limite do passeio)" + (f" — legenda {', '.join(str(n) for n, _ in lan)}" if lan else ""),
                        descricao=f"comprimento da linha de limite do passeio ; {org}", qtd=ex["lancil"], un="m", refs="LIMPASSEIO"))
    if ex["muros"]:
        from collections import defaultdict
        por = defaultdict(float)
        for m in ex["muros"]:
            por[round(m["t"] * 20) / 20] += m["L"]
        for t, L in sorted(por.items()):
            out.append(dict(capitulo="Arranjos exteriores e espaço público", piso="Exterior", designacao=f"Muro de vedação e = {t:.2f} m — comprimento",
                            descricao=f"pares de linhas da camada MUROS ; altura no pormenor do muro (a confirmar) ; {org}",
                            qtd=L, un="m", refs="MUROS", estado="medido (altura a confirmar)"))
    return out
