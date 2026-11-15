"""Riscos naturais do terreno: incêndio rural, cheias e inundações, erosão hídrica e movimentos de vertente.

Duas fontes, sempre identificadas em cada resultado:
1. cartografia oficial publicada (SRUP da DGT: REN — zonas ameaçadas pelas cheias, áreas de elevado risco de erosão,
   áreas de instabilidade de vertentes; perigosidade de incêndio rural e áreas ardidas quando o município as publica);
2. suscetibilidade calculada sobre o MDT (declive, forma do relevo, acumulação de escoamento, fator LS) — indicativa.

Regra: a cartografia oficial prevalece; o cálculo do MDT só pode AGRAVAR o nível, nunca dar «sem risco» quando a
cartografia não respondeu (fica «por confirmar»).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import ndimage

NIVEIS = ["baixo", "moderado", "elevado", "muito_elevado"]
ROTULO = {"baixo": "Baixo", "moderado": "Moderado", "elevado": "Elevado", "muito_elevado": "Muito elevado",
          "por_confirmar": "Por confirmar"}

_INC = re.compile(r"(inc[eê]ndio|perigosidade|ardid|apps|fogo|florest)", re.I)
_INC_ALTA = re.compile(r"(muito.?alta|\balta\b|classe.?(iv|v)\b)", re.I)
_ARDIDA = re.compile(r"ardid", re.I)
_CHEIA = re.compile(r"(cheia|inunda|ameaçad|ameacad|leito|margem|dom[ií]nio h[ií]dric|curso.{0,4}d.{0,3}[aá]gua|"
                    r"linha.{0,4}d.{0,3}[aá]gua|albufeir|lagoa)", re.I)
_EROSAO = re.compile(r"eros", re.I)
_VERTENTE = re.compile(r"(instabilidade|vertente|desliza|movimento.{0,6}massa|arriba)", re.I)

FONTES_LEGAIS = {
    "SGIFR": {"diploma": "Decreto-Lei n.º 82/2021, de 13 de outubro (Sistema de Gestão Integrada de Fogos Rurais)",
              "artigo": "condicionamento da edificação em áreas de perigosidade de incêndio rural elevada/muito elevada "
                        "fora dos aglomerados e faixas de gestão de combustível à volta dos edifícios",
              "status": "a_confirmar"},
    "LEI_54_2005": {"diploma": "Lei n.º 54/2005, de 15 de novembro (titularidade dos recursos hídricos)",
                    "artigo": "art.º 11.º: margem de 10 m nas águas não navegáveis nem flutuáveis (30 m nas navegáveis)",
                    "status": "confirmado"},
    "REN": {"diploma": "Decreto-Lei n.º 166/2008, de 22 de agosto (Regime Jurídico da REN), na redação em vigor",
            "artigo": "art.º 20.º: interdição de edificação nas áreas da REN, salvo usos compatíveis do anexo II",
            "status": "confirmado"},
}


def _max(a: str, b: str) -> str:
    if a == "por_confirmar":
        return b if b != "baixo" else a
    if b == "por_confirmar":
        return a
    return a if NIVEIS.index(a) >= NIVEIS.index(b) else b


def _temas(srup: Optional[Dict[str, Any]], pat: re.Pattern) -> Dict[str, List[Dict[str, Any]]]:
    d = (srup or {}).get("data") or {}
    def f(lst):
        return [e for e in lst or [] if pat.search((e.get("titulo") or "") + " " + (e.get("id") or ""))]
    return {"afeta": f(d.get("afeta")), "proximas": f(d.get("proximas_60m")), "por_confirmar": f(d.get("por_confirmar"))}


def _srup_ok(srup) -> bool:
    return bool(srup and srup.get("ok"))


def _distancia_linhas(acc: np.ndarray, mascara: np.ndarray, cel: float, px: float, limiar_m2: float) -> Optional[float]:
    rio = acc * cel >= limiar_m2
    if not rio.any():
        return None
    if (rio & mascara).any():
        return 0.0
    d = ndimage.distance_transform_edt(~rio) * px
    return float(d[mascara].min())


def _resultado(nome, nivel, oficial, calculado, recomendacoes, fontes) -> Dict[str, Any]:
    return {"risco": nome, "nivel": nivel, "rotulo": ROTULO[nivel], "cartografia_oficial": oficial,
            "suscetibilidade_mdt": calculado, "recomendacoes": recomendacoes, "fontes": fontes}


# ------------------------------------------------------------------ incêndio rural
def incendio(relevo: Dict[str, Any], mascara: np.ndarray, srup, solo: Optional[str]) -> Dict[str, Any]:
    t = _temas(srup, _INC)
    decl = np.nan_to_num(relevo["_decl"])[mascara]
    expo = np.nan_to_num(relevo["_expo"])[mascara]
    quente = ((expo >= 135) & (expo <= 270))                     # vertentes SE–O: mais secas e expostas
    ingreme = decl >= 25
    frac = float((ingreme & quente).mean()) if decl.size else 0.0
    calc = "elevado" if frac >= 0.4 else "moderado" if (frac >= 0.15 or float(ingreme.mean()) >= 0.3) else "baixo"
    if relevo.get("forma_dominante") in ("cumeada", "encosta_alta") and calc == "baixo":
        calc = "moderado"                                         # o fogo sobe as encostas
    oficial = None
    if t["afeta"]:
        alta = any(_INC_ALTA.search(e["titulo"] or "") for e in t["afeta"])
        oficial = {"nivel": "muito_elevado" if alta else "elevado", "temas": [e["titulo"] for e in t["afeta"]]}
    elif _srup_ok(srup) and not t["por_confirmar"]:
        oficial = {"nivel": "baixo", "temas": [], "nota": "nenhuma carta de incêndio publicada que afete o terreno"}
    nivel = _max(oficial["nivel"] if oficial else "por_confirmar", calc)
    if solo == "rustico":
        nivel = _max(nivel, "moderado")
    rec = []
    if any(_ARDIDA.search(e["titulo"] or "") for e in t["afeta"]):
        rec.append("Área ardida publicada: confirmar na câmara as restrições temporárias à edificação.")
    if nivel in ("elevado", "muito_elevado"):
        rec.append("Confirmar a classe de perigosidade de incêndio rural na carta do município (ICNF) e se a construção "
                   "é admitida fora de aglomerado; prever faixa de gestão de combustível à volta do edifício.")
    if solo == "rustico" or nivel != "baixo":
        rec += ["Materiais de fachada e cobertura incombustíveis; caixilharia e vãos protegidos de projeções.",
                "Afastar o edifício da vegetação contínua e das linhas de cumeada; acesso de viaturas de socorro."]
    return _resultado("incendio_rural", nivel, oficial, {"nivel": calc, "fracao_vertente_quente_ingreme": round(frac, 3)},
                      rec, ["SGIFR"])


# ------------------------------------------------------------------ cheias e inundações
def cheias(relevo: Dict[str, Any], mascara: np.ndarray, srup, cel: float, px: float) -> Dict[str, Any]:
    t = _temas(srup, _CHEIA)
    acc = relevo["_acc"]
    dl = _distancia_linhas(acc, mascara, cel, px, relevo.get("limiar_linha_agua_m2") or 1500)
    vale = float(relevo.get("fracao_vale") or 0)
    bacia = float(relevo.get("bacia_max_no_terreno_m2") or 0)
    calc = "baixo"
    if dl is not None and dl <= 10:
        calc = "elevado" if bacia >= 20000 else "moderado"
    elif (dl is not None and dl <= 30) or vale >= 0.2:
        calc = "moderado"
    oficial = None
    dist_hidro = None
    if t["afeta"]:
        zonas = [e for e in t["afeta"] if re.search(r"(cheia|inunda|ameaç|ameac)", e["titulo"] or "", re.I)]
        oficial = {"nivel": "muito_elevado" if zonas else "elevado", "temas": [e["titulo"] for e in t["afeta"]]}
        dist_hidro = 0.0
    elif t["proximas"]:
        dist_hidro = min(e["distancia_m"] for e in t["proximas"])
        oficial = {"nivel": "elevado" if dist_hidro <= 10 else "moderado", "temas": [e["titulo"] for e in t["proximas"]],
                   "distancia_m": dist_hidro}
    elif _srup_ok(srup) and not t["por_confirmar"]:
        oficial = {"nivel": "baixo", "temas": []}
    nivel = _max(oficial["nivel"] if oficial else "por_confirmar", calc)
    rec = []
    if dist_hidro is not None and dist_hidro <= 10:
        rec.append("Linha de água cartografada junto ou dentro do terreno: a margem (10 m, ou 30 m se navegável) é domínio "
                   "hídrico — pedir à APA a delimitação e o título de utilização antes de implantar.")
    elif dl is not None and dl <= 10:
        rec.append("O MDT mostra um talvegue (linha de água potencial) junto ou dentro do terreno: confirmar no local e na "
                   "carta militar / APA se é curso de água — se for, a margem de 10 m é domínio hídrico.")
    if nivel in ("moderado", "elevado", "muito_elevado"):
        rec += ["Implantar fora do talvegue e acima da cota de cheia; cota de soleira sobrelevada face ao terreno.",
                "Drenagem periférica e encaminhamento das águas pluviais; evitar caves."]
    return _resultado("cheias_inundacoes", nivel, oficial,
                      {"nivel": calc, "distancia_linha_agua_mdt_m": None if dl is None else round(dl, 1),
                       "fracao_vale": round(vale, 3), "bacia_max_m2": round(bacia, 0)},
                      rec, ["LEI_54_2005", "REN"])


# ------------------------------------------------------------------ erosão hídrica
def erosao(relevo: Dict[str, Any], mascara: np.ndarray, srup) -> Dict[str, Any]:
    t = _temas(srup, _EROSAO)
    ls = relevo["_ls"][mascara]
    p90 = float(np.percentile(ls, 90)) if ls.size else 0.0
    med = float(ls.mean()) if ls.size else 0.0
    calc = "muito_elevado" if med >= 7 else "elevado" if (med >= 3 or p90 >= 8) else "moderado" if (med >= 1 or p90 >= 3) else "baixo"
    oficial = None
    if t["afeta"]:
        oficial = {"nivel": "elevado", "temas": [e["titulo"] for e in t["afeta"]]}
    elif _srup_ok(srup) and not t["por_confirmar"]:
        oficial = {"nivel": "baixo", "temas": []}
    nivel = _max(oficial["nivel"] if oficial else "por_confirmar", calc)
    rec = []
    if nivel != "baixo":
        rec += ["Limitar a área de solo exposto durante a obra; revestimento vegetal dos taludes logo após a terraplenagem.",
                "Valas de drenagem a meia encosta e dissipadores à saída das águas pluviais."]
    if t["afeta"]:
        rec.insert(0, "Área de elevado risco de erosão hídrica (REN): a edificação depende da compatibilidade com a REN.")
    return _resultado("erosao_hidrica", nivel, oficial, {"nivel": calc, "ls_medio": round(med, 2), "ls_p90": round(p90, 2)},
                      rec, ["REN"])


# ------------------------------------------------------------------ movimentos de vertente
def vertentes(relevo: Dict[str, Any], mascara: np.ndarray, srup) -> Dict[str, Any]:
    t = _temas(srup, _VERTENTE)
    decl = np.nan_to_num(relevo["_decl"])[mascara]
    f45 = float((decl >= 45).mean()) if decl.size else 0.0        # ≈ 24°
    f25 = float((decl >= 25).mean()) if decl.size else 0.0
    calc = "elevado" if f45 >= 0.25 else "moderado" if (f45 >= 0.05 or f25 >= 0.4) else "baixo"
    if f45 >= 0.25 and (relevo.get("rugosidade_m") or 0) > 1.0:
        calc = "muito_elevado"
    oficial = None
    if t["afeta"]:
        oficial = {"nivel": "muito_elevado", "temas": [e["titulo"] for e in t["afeta"]]}
    elif _srup_ok(srup) and not t["por_confirmar"]:
        oficial = {"nivel": "baixo", "temas": []}
    nivel = _max(oficial["nivel"] if oficial else "por_confirmar", calc)
    rec = []
    if nivel in ("moderado", "elevado", "muito_elevado"):
        rec += ["Estudo geológico-geotécnico (sondagens) antes do projeto de fundações e contenções.",
                "Evitar aterros sobre a encosta; muros de suporte dimensionados e drenados."]
    if t["afeta"]:
        rec.insert(0, "Área de instabilidade de vertentes (REN): a edificação é, em regra, interdita.")
    return _resultado("movimentos_vertente", nivel, oficial,
                      {"nivel": calc, "fracao_declive_25pct": round(f25, 3), "fracao_declive_45pct": round(f45, 3)},
                      rec, ["REN"])


def avaliar(relevo: Dict[str, Any], mascara: np.ndarray, srup, solo: Optional[str], cel: float, px: float) -> Dict[str, Any]:
    lst = [incendio(relevo, mascara, srup, solo), cheias(relevo, mascara, srup, cel, px),
           erosao(relevo, mascara, srup), vertentes(relevo, mascara, srup)]
    conhecidos = [e["nivel"] for e in lst if e["nivel"] != "por_confirmar"]
    pior = max(conhecidos, key=NIVEIS.index) if conhecidos else "por_confirmar"
    if pior == "baixo" and len(conhecidos) < len(lst):
        pior = "por_confirmar"
    return {"riscos": lst, "nivel_global": pior, "rotulo_global": ROTULO[pior],
            "cartografia_consultada": _srup_ok(srup),
            "fontes_legais": {k: FONTES_LEGAIS[k] for k in FONTES_LEGAIS},
            "nota": "A suscetibilidade calculada sobre o MDT é indicativa; a cartografia de risco do PDM / PMDFCI e da "
                    "REN publicada em Diário da República prevalece."}


def mascaras_exclusao(relevo: Dict[str, Any], cel: float, px: float) -> np.ndarray:
    """Células a evitar na implantação: talvegue (+ 5 m) e declive ≥ 45 %."""
    acc = relevo["_acc"]
    rio = acc * cel >= (relevo.get("limiar_linha_agua_m2") or 1500)
    if rio.any():
        rio = ndimage.distance_transform_edt(~rio) * px <= 5.0
    return rio | (np.nan_to_num(relevo["_decl"]) >= 45)
