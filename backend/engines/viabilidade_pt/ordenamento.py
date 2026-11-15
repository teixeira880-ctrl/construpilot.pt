"""Ordenamento do território e edificabilidade: cruza o terreno com o PDM (CRUS), a REN, a RAN, as servidões e
restrições de utilidade pública, e calcula o potencial construtivo com os parâmetros municipais disponíveis.

Princípio herdado de engines.urbanismo_pt.regras: os parâmetros MUNICIPAIS (Iu, Io, cércea, pisos, afastamentos) nunca
são inventados — vêm do utilizador (regulamento do PDM / PP / loteamento). Sem eles, o potencial fica «sem dados» e o
relatório diz exatamente o que falta.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from engines.urbanismo_pt import regras as RG

# Pressupostos de estudo quando o PDM não foi introduzido (claramente marcados como tal)
PRESSUPOSTOS_AFASTAMENTO = {"frontal": 5.0, "lateral": 3.0, "tardoz": 6.0}


def _classes(pdm) -> List[Dict[str, Any]]:
    return ((pdm or {}).get("data") or {}).get("classes") or []


def solo_dominante(pdm) -> Dict[str, Any]:
    cl = _classes(pdm)
    if not cl:
        return {"solo": "desconhecido", "classe": None, "categoria": None, "habitacional": None, "fracao": 0.0,
                "estado": "por_confirmar" if not (pdm or {}).get("ok") else "sem_dados"}
    c = cl[0]
    return {"solo": c["solo"], "classe": c.get("classe"), "categoria": c.get("categoria"), "habitacional": c.get("habitacional"),
            "fracao": c.get("fracao"), "estado": "ok", "outras": cl[1:]}


def _fr(lst) -> float:
    return round(min(1.0, sum(e.get("fracao") or 0 for e in lst or [])), 4)


def condicionantes(srup) -> Dict[str, Any]:
    d = (srup or {}).get("data") or {}
    afeta = d.get("afeta") or []
    ren = [e for e in afeta if e.get("tipo") == "REN"]
    ran = [e for e in afeta if e.get("tipo") == "RAN"]
    hid = d.get("hidricos") or []
    outras = [e for e in afeta if e.get("tipo") == "servidao"]
    return {
        "consultado": bool(srup and srup.get("ok")), "incompleto": bool(d.get("incompleta")),
        "ren": {"fracao": _fr(ren), "temas": [e["titulo"] for e in ren]},
        "ran": {"fracao": _fr(ran), "temas": [e["titulo"] for e in ran]},
        "dominio_hidrico": [{"titulo": e["titulo"], "distancia_m": e.get("distancia_m")} for e in hid],
        "servidoes": [{"titulo": e["titulo"], "fracao": e.get("fracao"), "distancia_m": e.get("distancia_m")} for e in outras],
        "por_confirmar": [e["titulo"] for e in d.get("por_confirmar") or []],
    }


def afastamentos(pdm_params: Dict[str, Any]) -> Dict[str, Any]:
    p = RG.normalizar_pdm(pdm_params)
    out, pres = {}, []
    for lado, key in (("frontal", "afastamento_frontal_min_m"), ("lateral", "afastamento_lateral_min_m"),
                      ("tardoz", "afastamento_tardoz_min_m")):
        v = p.get(key)
        if v is None:
            v = PRESSUPOSTOS_AFASTAMENTO[lado]
            pres.append(lado)
        out[lado] = max(v, RG.CC_1360_MIN_M) if lado != "frontal" else v
    return {"valores_m": out, "pressupostos": pres,
            "nota": ("Afastamentos " + ", ".join(pres) + " são pressupostos de estudo (o PDM não foi introduzido): "
                     "confirmar no regulamento municipal.") if pres else "Afastamentos do regulamento municipal introduzidos.",
            "minimo_nacional": {"valor_m": RG.CC_1360_MIN_M, "fonte": RG.FONTES["CC_1360"]["artigo"]}}


def potencial(area_terreno: float, area_edificavel: float, pdm_params: Dict[str, Any], cond: Dict[str, Any]) -> Dict[str, Any]:
    p = RG.normalizar_pdm(pdm_params)
    # a área da REN/RAN não conta como área disponível para edificar (o índice aplica-se à parcela — confirmar no PDM)
    falta = [c["label"] for c in RG.PDM_CAMPOS if c["key"] in ("iu_max", "io_max_pct", "n_pisos_max", "altura_fachada_max_m")
             and p.get(c["key"]) is None]
    iu, io = p.get("iu_max"), p.get("io_max_pct")
    ac = round(area_terreno * iu, 1) if iu else None
    ai = round(area_terreno * io / 100.0, 1) if io else None
    if ai is not None:
        ai = min(ai, round(area_edificavel, 1))
    pisos = p.get("n_pisos_max")
    if pisos is None and p.get("altura_fachada_max_m"):
        pisos = max(1, int(p["altura_fachada_max_m"] // RG.RGEU_PISO_A_PISO_MIN_M))
    if ac is None and ai is not None and pisos:
        ac = round(ai * pisos, 1)
    if ac is not None and ai is not None and pisos:
        ac = min(ac, round(ai * pisos, 1))
    return {
        "area_terreno_m2": round(area_terreno, 1),
        "area_livre_para_implantacao_m2": round(area_edificavel, 1),
        "area_implantacao_max_m2": ai, "area_construcao_max_m2": ac, "n_pisos_max": pisos,
        "altura_fachada_max_m": p.get("altura_fachada_max_m"),
        "parametros": {k: v for k, v in p.items() if v is not None},
        "em_falta": falta,
        "estado": "calculado" if (ac or ai) else "sem_dados",
        "nota": ("Potencial calculado com os parâmetros municipais introduzidos e limitado pela área livre do terreno "
                 "(afastamentos, REN/RAN, talvegues e declives > 45 % excluídos).") if (ac or ai) else
                ("Sem índices do PDM: introduza Iu, Io, n.º de pisos e cércea do regulamento para obter a área de construção "
                 "máxima. A área livre para implantação já está calculada."),
        "fonte_conceitos": RG.FONTES["DR_5_2019"]["diploma"],
        "ren_ran_fracao": round(cond["ren"]["fracao"] + cond["ran"]["fracao"], 4),
    }


def avaliar(pdm, srup, area_terreno: float, area_edificavel: float, pdm_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    pp = pdm_params or {}
    solo = solo_dominante(pdm)
    cond = condicionantes(srup)
    return {"solo": solo, "condicionantes": cond, "afastamentos": afastamentos(pp),
            "potencial": potencial(area_terreno, area_edificavel, pp, cond),
            "regras_nacionais": [
                {"titulo": "Distância de janelas ao prédio vizinho", **{k: RG.FONTES["CC_1360"][k] for k in ("diploma", "artigo", "status")}},
                {"titulo": "Altura face ao alinhamento fronteiro (45°)", **{k: RG.FONTES["RGEU_59"][k] for k in ("diploma", "artigo", "status")}},
                {"titulo": "Pé-direito mínimo em habitação", **{k: RG.FONTES["RGEU_65_1"][k] for k in ("diploma", "artigo", "status")}},
            ]}
