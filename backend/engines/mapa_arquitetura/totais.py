"""Quadro de QUANTIDADES TOTAIS do mapa (regra do Martinho, 25/11) : vem em primeiro lugar no mapa (PDF e Excel) e antes de
qualquer orçamento — betão m³ (total e por elemento), aço kg, cofragem m², alvenarias m², pavimentos m², vãos… Soma exata das
linhas medidas do mapa ; as linhas «a medir» não entram (ficam listadas no mapa)."""
from __future__ import annotations

import re
import unicodedata

UN = {"m²": "m2", "m³": "m3", "m": "ml", "un": "u", "ud": "u"}
UN_TXT = {"m2": "m²", "m3": "m³", "ml": "m", "u": "un", "kg": "kg"}
ESTRUTURA = ("Movimento de terras", "Fundações", "Estrutura")
ORDEM = ["Escavação", "Aterro / tout-venant", "Betão de limpeza", "Betão", "Aço", "Cofragem", "Malha eletrossoldada",
         "Vigotas pré-esforçadas", "Laje de vigotas (abobadilhas)", "Blocos de aligeiramento", "Impermeabilização de muros",
         "Tela de polietileno"]


def _n(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


def _elemento(d: str) -> str:
    if "vigas / reforcos" in d or "armaduras desenhadas" in d:
        return "vigas e reforços desenhados"
    if re.search(r"sapata|fundac|vigas de equilibrio|veq\b|lintel", d):
        return "fundações"
    if re.search(r"laje terrea|massame|pavimento terreo", d):
        return "laje térrea"
    if re.search(r"\bmuro|nucleo|parede", d):
        return "muros e paredes"
    if re.search(r"\bpilar", d):
        return "pilares"
    if re.search(r"\bviga", d):
        return "vigas"
    if re.search(r"\blaje|lva|lfa|\blm\b|nervura", d):
        return "lajes"
    return "outros"


def _el(dz: str, d: str, cap: str = "") -> str:
    if cap.startswith("Arranjos exteriores"):
        return "arranjos exteriores"
    e = _elemento(dz)                     # a designação manda ; a descrição só quando a designação não diz o elemento
    return e if e != "outros" else _elemento(d)


def familia(l: dict) -> tuple[str, str | None]:
    """(quantidade total, elemento) de uma linha do mapa."""
    d = _n(l.get("designacao")) + " " + _n(l.get("descricao"))[:60]
    dz = _n(l.get("designacao"))
    u = UN.get(str(l.get("un") or ""), str(l.get("un") or ""))
    cap = str(l.get("capitulo") or "Geral")
    if cap in ESTRUTURA or re.search(r"betao|aco\b|cofragem", dz):
        if u == "m3" and re.search(r"escavac", dz):
            return "Escavação", None
        if u == "m3" and re.search(r"tout-venant|aterro", dz):
            return "Aterro / tout-venant", None
        if u == "m3" and "betao de limpeza" in dz:
            return "Betão de limpeza", None
        if u == "kg" and re.search(r"\baco\b|estribo|armadura|emenda|varao|ø", dz + " " + str(l.get("designacao") or "").lower()):
            return "Aço", _el(dz, d, cap)
        if u == "m2" and "cofragem" in dz:
            return "Cofragem", _el(dz, d, cap)
        if u == "m3" and "betao" in dz:
            return "Betão", _el(dz, d, cap)
        if u == "m2" and re.search(r"malha|malhasol|\bcq\d|\baq\d", dz):
            return "Malha eletrossoldada", None
        if u == "ml" and "vigota" in dz:
            return "Vigotas pré-esforçadas", None
        if u == "m2" and "laje de vigotas" in dz:
            return "Laje de vigotas (abobadilhas)", None
        if u == "u" and "bloco" in dz:
            return "Blocos de aligeiramento", None
        if u == "m2" and "impermeabiliza" in dz:
            return "Impermeabilização de muros", None
        if u == "m2" and "tela" in dz:
            return "Tela de polietileno", None
    base = re.split(r"\s+[—(]|\s+e\s*=|\s+\d", str(l.get("designacao") or ""), maxsplit=1)[0].strip(" /—")
    return f"{cap} — {base}", None


def totais(linhas: list) -> list:
    """[{"quantidade", "unidade" (m², m³, m, kg, un), "total", "por_elemento" {…} ou None, "linhas"}] pela ordem da obra."""
    acc: dict = {}
    for l in linhas or []:
        if not l.get("qtd"):
            continue
        u = UN.get(str(l.get("un") or ""), str(l.get("un") or ""))
        fam, el = familia(l)
        t = acc.setdefault((fam, u), {"total": 0.0, "por": {}, "n": 0})
        t["total"] += float(l["qtd"])
        t["n"] += 1
        if el:
            t["por"][el] = t["por"].get(el, 0.0) + float(l["qtd"])

    def chave(kv):
        f = kv[0][0]
        return (ORDEM.index(f) if f in ORDEM else len(ORDEM), f)
    return [{"quantidade": f, "unidade": UN_TXT.get(u, u), "total": round(v["total"], 2),
             "por_elemento": {k: round(x, 2) for k, x in sorted(v["por"].items(), key=lambda kv: -kv[1])} if len(v["por"]) > 1 else None,
             "linhas": v["n"]}
            for (f, u), v in sorted(acc.items(), key=chave)]
