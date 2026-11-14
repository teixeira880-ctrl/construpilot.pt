"""Estrutura de um edifício a partir do CONTORNO medido no DWG de implantação (pré-dimensionamento calculado).

14/11 (Valpaços): «e a estrutura tem que calcular». A implantação dá o contorno exato do edifício (polígono de
1662,25 m² na camada SMC_LIMITE CONSTR P0, igual à área escrita), mas não dá a malha de pilares nem o pé-direito.
Este módulo:
1. lê o contorno (polígono cuja área coincide com a área de implantação escrita, ou o maior da camada de construção);
2. gera uma malha de pilares regular com vão ≤ vão máximo (hipótese declarada), as células fora do contorno ficam
   sem laje (o contorno real é respeitado, não o retângulo envolvente);
3. corre o motor de estruturas bet_frame (EN 1990/1991/1992 — lajes, vigas contínuas, pilares em flexão composta,
   sapatas pelo método das bielas), que dimensiona e devolve as quantidades de betão, aço e cofragem por elemento.

Nada estrutural é escrito à mão: os números vêm do cálculo. As HIPÓTESES (malha, pé-direito, solução em betão armado,
uso, betão/aço, tensão do terreno) vão escritas em cada linha — é um pré-dimensionamento a validar pelo projetista de
estruturas e pelo estudo geotécnico.
"""
from __future__ import annotations

import math
import re

VAO_MAX = 7.5          # m — malha corrente de lajes maciças/vigas em betão armado
PE_DIREITO = 5.0       # m — hipótese para comércio de 1 piso sem corte (a confirmar)

_CAMADA_EDIF = re.compile(r"limite.?constr|implant|edif(icio)?\b|construc|footprint|emprise", re.I)
_AREA_IMPL = re.compile(r"implanta[cç][aã]o:?\s*(\d{2,6}(?:[.,]\d{1,2})?)\s*m", re.I)


def contornos(doc, entidades, fator_m: float = 1.0) -> list[dict]:
    """Polígonos candidatos a contorno de edifício (camadas de construção/implantação), em metros."""
    from ezdxf.path import from_hatch

    from engines.cad_geometry import hatch_area, polyline_length_area
    out = []
    for e in entidades:
        layer = e.dxf.get("layer", "0")
        if not _CAMADA_EDIF.search(layer) or re.search(r"verde|green|esp\b|relva|lote|canal", layer, re.I):
            continue
        t = e.dxftype()
        try:
            if t == "HATCH":
                a = hatch_area(e) * fator_m ** 2
                loops = [[(float(v.x) * fator_m, float(v.y) * fator_m) for v in p.flattening(0.05)] for p in from_hatch(e)]
                loops = [l for l in loops if len(l) >= 3]
                if not loops:
                    continue
                pts = max(loops, key=lambda l: abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(l, l[1:] + l[:1]))))
            elif t == "LWPOLYLINE" and e.closed:
                a = polyline_length_area(e)[1] * fator_m ** 2
                pts = [(float(p[0]) * fator_m, float(p[1]) * fator_m) for p in e.get_points("xy")]
            else:
                continue
        except Exception:  # noqa: BLE001
            continue
        if a >= 30:
            out.append({"camada": layer, "area_m2": round(a, 2), "pontos": pts})
    return out


def area_implantacao_escrita(doc) -> float | None:
    for e in doc.modelspace().query("TEXT MTEXT"):
        try:
            t = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
        except Exception:  # noqa: BLE001
            continue
        m = _AREA_IMPL.search(t or "")
        if m:
            return float(m.group(1).replace(",", "."))
    return None


_COTA_SOLEIRA = re.compile(r"cota\s*(?:de\s*)?soleira:?\s*(\d{1,4}(?:[.,]\d{1,2})?)", re.I)


def cota_soleira(doc) -> float | None:
    """Altitude (m) da cota de soleira escrita no desenho — usada na neve (NP EN 1991-1-3)."""
    for e in doc.modelspace().query("TEXT MTEXT"):
        try:
            t = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
        except Exception:  # noqa: BLE001
            continue
        m = _COTA_SOLEIRA.search(t or "")
        if m:
            v = float(m.group(1).replace(",", "."))
            if 0 <= v <= 2500:
                return v
    return None


def escolher(cands: list[dict], escrita: float | None) -> dict | None:
    if not cands:
        return None
    if escrita:
        ok = [c for c in cands if abs(c["area_m2"] - escrita) <= 0.01 * escrita]
        if ok:
            return {**ok[0], "origem": f"polígono da camada «{ok[0]['camada']}» com {ok[0]['area_m2']} m² = área de implantação escrita ({escrita} m²)"}
    c = max(cands, key=lambda c: c["area_m2"])
    return {**c, "origem": f"maior polígono das camadas de construção («{c['camada']}», {c['area_m2']} m²) — sem área escrita para confirmar"}


def _malha(a0: float, a1: float, vmax: float) -> list[float]:
    n = max(1, math.ceil((a1 - a0) / vmax - 1e-9))
    passo = (a1 - a0) / n
    return [round(i * passo, 3) for i in range(n + 1)]


def modelo_frame(pontos: list[tuple[float, float]], *, nome: str, pisos: int = 1, pe_direito: float = PE_DIREITO,
                 uso: str = "commerce", vao_max: float = VAO_MAX, concreto: str = "C25/30", pais: str = "PT") -> dict:
    """Contorno (m) → modelo bet_frame com a malha e as células fora do contorno sem laje."""
    from shapely.geometry import Point, Polygon
    poly = Polygon(pontos).buffer(0)
    x0, y0, x1, y1 = poly.bounds
    gx, gy = _malha(x0, x1, vao_max), _malha(y0, y1, vao_max)
    xl = [str(i + 1) for i in range(len(gx))]
    yl = [chr(65 + j) if j < 26 else f"A{chr(65 + j - 26)}" for j in range(len(gy))]
    rel = Polygon([(x - x0, y - y0) for x, y in poly.exterior.coords])
    voids = []
    for i in range(len(gx) - 1):
        for j in range(len(gy) - 1):
            cx, cy = (gx[i] + gx[i + 1]) / 2, (gy[j] + gy[j + 1]) / 2
            cel = Polygon([(gx[i], gy[j]), (gx[i + 1], gy[j]), (gx[i + 1], gy[j + 1]), (gx[i], gy[j + 1])])
            if not rel.contains(Point(cx, cy)) and rel.intersection(cel).area < 0.5 * cel.area:
                voids.append([xl[i], yl[j]])
    levels = [{"id": f"P{k}", "name": "R/C" if k == 0 else f"Piso {k}", "floor_top": round(k * pe_direito, 2),
               "height": pe_direito, "use": uso, "on_grade": k == 0} for k in range(pisos)]
    return {"kind": "frame", "schema_version": "frame-1", "building_type": "comercio",
            "project": {"name": nome, "country": pais, "address": "—", "client": "—", "architect": "—",
                        "pc_ref": "Implantação DWG", "g2_ref": "sem estudo geotécnico — hipótese"},
            "geometry": {"overall": {"length": round(gx[-1], 2), "width": round(gy[-1], 2), "facade_to_axis": 0.15,
                                     "source": "contorno medido no DWG de implantação"}},
            "grid": {"x": gx, "y": gy, "x_labels": xl, "y_labels": yl},
            "levels": levels, "roof": {"use": "cobertura"},
            "structure": {"column": [0.40, 0.40], "beam": [0.30, 0.60], "slab": 0.22, "concrete": concreto,
                          "steel": "A500 NR" if pais == "PT" else "B500B", "void_cells": voids},
            "cores": [], "balconies": [], "units": []}


def calcular(pontos, *, nome: str, pisos: int = 1, pe_direito: float = PE_DIREITO, uso: str = "commerce",
             vao_max: float = VAO_MAX, lang: str = "pt") -> dict:
    from engines.bet_frame.lang import use_lang
    with use_lang(lang):
        return _calcular(pontos, nome=nome, pisos=pisos, pe_direito=pe_direito, uso=uso, vao_max=vao_max)


def _calcular(pontos, *, nome, pisos, pe_direito, uso, vao_max) -> dict:
    """Corre o bet_frame e devolve as linhas de medição da estrutura (com hipóteses) + resumo."""
    from engines.bet_frame import calc, devis, model
    raw = modelo_frame(pontos, nome=nome, pisos=pisos, pe_direito=pe_direito, uso=uso, vao_max=vao_max)
    m = model.from_dict(raw)
    bloq = [a for a in model.check(m) if a.get("level") == model.BLOCK]
    if bloq:
        raise ValueError("Modelo estrutural recusado pelo verificador: " + "; ".join(str(a.get("message"))[:160] for a in bloq[:3]))
    r = calc.compute(m)
    e = {"risers": [], "units": []}            # sem redes: só fundações e estrutura
    linhas_bf = devis.build_lines(m, r, e)
    gx, gy = raw["grid"]["x"], raw["grid"]["y"]
    hip = (f"Pré-dimensionamento calculado (EN 1990/1991/1992, motor ConstruPilot) sobre o contorno medido no DWG. HIPÓTESES a "
           f"confirmar: estrutura em betão armado {raw['structure']['concrete']} / {raw['structure']['steel']}, malha de pilares "
           f"{gx[1]-gx[0]:.2f} × {gy[1]-gy[0]:.2f} m (vão máx. {vao_max} m), {pisos} piso(s), pé-direito {pe_direito} m, uso "
           f"comércio (cat. D1), cobertura plana não acessível, fundações diretas em sapatas sem estudo geotécnico. "
           f"A validar pelo projetista de estruturas.")
    linhas = []
    for l in linhas_bf:
        if not str(l.get("lot", "")).startswith(("1.", "2.")) or not l.get("qty"):
            continue                                   # só fundações e estrutura (as redes vêm de outros motores)
        un = {"m³": "m3", "m²": "m2", "u": "un"}.get(l["unit"], l["unit"])
        linhas.append({"kind": "item", "category": "Estrutura — " + str(l["lot"]).split(". ", 1)[-1], "designation": l["des"],
                       "unit": un, "qty": l["qty"], "description": hip, "classe": "estrutura"})
    n_pil = sum(1 for _ in r.get("columns") or [])
    from shapely.geometry import Polygon
    area_real = Polygon(pontos).buffer(0).area
    area_malha = m.footprint
    hip_area = (f" Área coberta pela malha {area_malha:.2f} m² para um contorno real de {area_real:.2f} m² (células parcialmente "
                f"fora do contorno arredondadas à malha).")
    for l in linhas:
        l["description"] += hip_area
    return {"linhas": linhas, "hipoteses": hip + hip_area, "pilares": n_pil, "malha": {"x": gx, "y": gy},
            "celulas_sem_laje": len(raw["structure"]["void_cells"]), "modelo": raw}
