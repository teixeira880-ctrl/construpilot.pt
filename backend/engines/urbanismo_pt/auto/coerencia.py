"""Guarda de coerência entre motores — «uma só verdade, verificada duas vezes».

1. O processo é a única fonte de verdade: todos os motores (quadro de áreas, verificação PDM/RJUE, plantas, desenhos, 3D,
   memória descritiva, estimativa, ficha estatística) leem os mesmos números. A impressão digital (`assinatura`) muda se
   qualquer dado de base mudar — um documento gerado com outra assinatura fica marcado como desatualizado.
2. Cada número final é recalculado por um caminho INDEPENDENTE (geometria exata com shapely, a partir dos polígonos e das
   plantas) e comparado com o que os motores produziram. Qualquer diferença acima da tolerância bloqueia o «pronto».
3. Texto gerado: todos os números citados têm de existir nos dados do processo; um número que não exista é sinalizado
   (nunca há cálculos inventados num documento).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from engines.urbanismo_pt import volumes as V

TOL_AREA = 0.005     # 0,5 %
TOL_ABS = 0.02       # 2 cm / 0,02 m²


def assinatura(processo: Dict[str, Any]) -> str:
    base = {k: processo.get(k) for k in ("tipo_obra", "volume", "pdm", "enquadramento")}
    base["area_terreno_m2"] = (processo.get("terreno") or {}).get("area_terreno_m2")
    auto = processo.get("auto") or {}
    base["poligono_m"] = (auto.get("terreno") or {}).get("poligono_m")
    base["plantas"] = [[(c["tipo"], c["x0"], c["y0"], c["x1"], c["y1"]) for c in p["compartimentos"]]
                       for p in (auto.get("plantas") or {}).get("pisos", [])]
    txt = json.dumps(base, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(txt.encode()).hexdigest()[:16]


def _igual(a: Optional[float], b: Optional[float], rel: float = TOL_AREA, ab: float = TOL_ABS) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(ab, rel * max(abs(a), abs(b)))


def verificar(processo: Dict[str, Any], verif: Dict[str, Any]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def chk(codigo, descricao, esperado, obtido, ok, critico=True, nota=""):
        checks.append({"codigo": codigo, "descricao": descricao, "esperado": esperado, "obtido": obtido, "ok": bool(ok),
                       "critico": critico, "nota": nota})

    vol = processo.get("volume") or {}
    q = (verif or {}).get("quadro") or {}
    auto = processo.get("auto") or {}
    ter = auto.get("terreno") or {}
    polys = V.building_polygons(vol)
    main = [Polygon(p["pts"]) for p in polys if not p["annexe"]]
    anexos = [Polygon(p["pts"]) for p in polys if p["annexe"]]
    tudo = unary_union(main + anexos)

    # 1. área de implantação (geometria independente)
    ai = round(tudo.area, 2)
    chk("AREA_IMPLANTACAO", "Área de implantação = união exata dos volumes", ai, q.get("area_implantacao_m2"),
        _igual(ai, q.get("area_implantacao_m2")))
    # 2. área de construção: pelas PLANTAS (soma dos compartimentos por piso) + anexos
    plantas = (auto.get("plantas") or {}).get("pisos") or []
    if plantas:
        soma_pisos = sum(sum((c["x1"] - c["x0"]) * (c["y1"] - c["y0"]) for c in p["compartimentos"]) for p in plantas)
        ac = round(soma_pisos + sum(a.area for a in anexos), 2)
        chk("AREA_CONSTRUCAO", "Área de construção = soma das plantas dos pisos + anexos", ac, q.get("area_construcao_m2"),
            _igual(ac, q.get("area_construcao_m2")))
        # 3. as plantas cobrem exatamente a implantação, sem sobreposições
        area_main = unary_union(main).area
        for p in plantas:
            rects = [box(c["x0"], c["y0"], c["x1"], c["y1"]) for c in p["compartimentos"]]
            soma = sum(r.area for r in rects)
            uni = unary_union(rects).area
            chk(f"PLANTA_{p['piso']}_COBERTURA", f"Planta do {p['nome'].lower()} cobre a implantação sem sobreposições",
                round(area_main, 2), round(uni, 2), _igual(area_main, uni) and _igual(soma, uni))
        # 4. mínimos de compartimentos (RGEU)
        nao = [f"{c['nome']} ({p['nome']})" for p in plantas for c in p["compartimentos"] if not c.get("conforme", True)]
        chk("RGEU_COMPARTIMENTOS", "Compartimentos com área e largura mínimas", "todos conformes",
            "todos conformes" if not nao else ", ".join(nao), not nao)
    # 5. índices recalculados
    at = (processo.get("terreno") or {}).get("area_terreno_m2") or q.get("area_terreno_m2")
    if at:
        io = round(ai / at * 100, 2)
        chk("INDICE_OCUPACAO", "Índice de ocupação = implantação / terreno", io, q.get("indice_ocupacao_pct"),
            _igual(io, q.get("indice_ocupacao_pct"), ab=0.02))
        if q.get("area_construcao_m2") is not None:
            iu = round(q["area_construcao_m2"] / at, 3)
            chk("INDICE_UTILIZACAO", "Índice de utilização = construção / terreno", iu, q.get("indice_utilizacao"),
                _igual(iu, q.get("indice_utilizacao"), ab=0.002))
    # 6. dentro do terreno e afastamentos reais ao polígono do prédio
    if ter.get("poligono_m"):
        parcel = Polygon(ter["poligono_m"])
        chk("DENTRO_TERRENO", "Todos os volumes dentro do terreno", "sim", "sim" if parcel.buffer(1e-6).contains(tudo) else "não",
            parcel.buffer(1e-6).contains(tudo))
        alv = (auto.get("alvos") or {}).get("valores") or {}
        if alv:
            minx, miny, maxx, maxy = parcel.bounds
            casa = unary_union(main)
            # lateral: o menor entre a distância às extremas laterais e a distância a qualquer limite (conservador)
            d_lat = min(casa.bounds[0] - minx, maxx - casa.bounds[2], parcel.exterior.distance(casa))
            d_fr = casa.bounds[1] - miny
            d_tz = maxy - casa.bounds[3]
            for cod, lbl, val, lim in (("AF_FRONTAL", "Afastamento frontal", d_fr, alv.get("afastamento_frontal_min_m")),
                                       ("AF_LATERAL", "Afastamento lateral (mínimo)", d_lat, alv.get("afastamento_lateral_min_m")),
                                       ("AF_TARDOZ", "Afastamento de tardoz", d_tz, alv.get("afastamento_tardoz_min_m"))):
                chk(cod, f"{lbl} ≥ alvo", f"≥ {lim:g} m", round(val, 2), val >= (lim or 0) - 0.01)
    # 7. alturas (RGEU)
    hh = V.heights(vol)
    chk("ALTURA_FACHADA", "Altura da fachada = pisos × piso a piso", round(hh["levels"] * hh["storey_h_m"], 2), q.get("altura_fachada_m"),
        _igual(hh["levels"] * hh["storey_h_m"], q.get("altura_fachada_m")))
    chk("RGEU_PISO_A_PISO", "Piso a piso ≥ 2,70 m (RGEU art.º 65.º)", "≥ 2,70 m", hh["storey_h_m"], hh["storey_h_m"] >= 2.70)
    pe = hh["storey_h_m"] - float(vol.get("espessura_laje_m") or 0.3)
    chk("RGEU_PE_DIREITO", "Pé-direito livre ≥ 2,40 m (RGEU art.º 65.º)", "≥ 2,40 m", round(pe, 2), pe >= 2.40 - 1e-6)
    # 8. o procedimento RJUE usa as mesmas áreas do quadro
    resp = ((verif or {}).get("rjue") or {}).get("respostas") or {}
    if "area_construcao_total_m2" in resp and q.get("area_construcao_m2") is not None:
        chk("RJUE_MESMAS_AREAS", "Diagnóstico RJUE calculado com as áreas do quadro", q["area_construcao_m2"],
            resp.get("area_construcao_total_m2"), _igual(q["area_construcao_m2"], resp.get("area_construcao_total_m2")))
    # 9. assinatura do processo
    chk("ASSINATURA", "Documentos gerados com a versão atual dos dados", auto.get("assinatura"), assinatura(processo),
        auto.get("assinatura") in (None, assinatura(processo)), critico=False)

    criticos = [c for c in checks if c["critico"]]
    ok = all(c["ok"] for c in criticos)
    return {"ok": ok, "aprovados": sum(1 for c in checks if c["ok"]), "total": len(checks),
            "taxa": round(sum(1 for c in checks if c["ok"]) / max(1, len(checks)) * 100, 1),
            "falhas": [c for c in checks if not c["ok"]], "checks": checks}


# ------------------------------------------------------------------ números em textos gerados
_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:[ .]\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)\s*(m²|m2|m³|m|%|€|metros|lugares|pisos)")


def _to_float(s: str) -> Optional[float]:
    t = s.replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def numeros_permitidos(*fontes: Any) -> List[float]:
    vals: List[float] = []

    def walk(o):
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            vals.append(float(o))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
    for f in fontes:
        walk(f)
    return vals


def numeros_sem_fonte(texto: str, permitidos: Iterable[float]) -> List[str]:
    perm = list(permitidos)
    fora = []
    for m in _NUM.finditer(texto or ""):
        x = _to_float(m.group(1))
        if x is None or x in (0.0, 1.0, 2.0):
            continue
        nd = len(re.split(r"[.,]", m.group(1))[1]) if re.search(r"[.,]\d+$", m.group(1)) else 0
        if not any(abs(x - p) <= max(0.011, 0.006 * abs(p)) or abs(round(p, nd) - x) < 1e-9 for p in perm):
            fora.append(m.group(0))   # um arredondamento correto de um valor com fonte é aceite (ex.: 5,54 → «5,5»)
    return fora
