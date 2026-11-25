"""Mapa de quantidades LSF — linhas codificadas a partir do resultado do motor (nada estimado por rácios).

Preços, por esta ordem:
  1. biblioteca de preços da empresa (`engines.price_library.match_price`) — origem « biblioteca »;
  2. preços fornecidos no projeto (`projeto["precos"]`, por código ou designação) — origem « projeto »;
  3. preço de mercado encontrado online (`market`, só resultados reais, nunca demonstração) — origem « mercado — a analisar »;
  4. sem preço → « a orçamentar » (a linha fica no mapa, sem valor).
"""
from __future__ import annotations

import math
import re
import unicodedata

from .i18n import t


def _slug(s: str) -> str:
    s = s.replace("×", "X").replace(",", ".")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9.]+", "-", s).strip("-").upper()[:48]


def linhas(res: dict, lang: str = "pt") -> list[dict]:
    """→ [{code, cat, designacao, un, qtd, detalhe, refs}] — o mapa de quantidades completo."""
    out = []

    def add(cat, code, des, un, qtd, detalhe="", refs=None, compra=None):
        if not qtd:
            return
        out.append({"code": code, "cat": cat, "designacao": des, "un": un, "qtd": round(qtd, 3 if un in ("m", "m²", "m³", "kg") else 0),
                    "detalhe": detalhe, "refs": refs or [], "compra": compra})

    for p in res["perfis"]:
        tipos = sorted({c["tipoPeca"] for c in p["cortes"]})
        des = f"Perfil LSF {p['perfil']} — aço S350GD+Z275 enformado a frio"
        add("1 Estrutura em aço leve", "LSF-" + _slug(p["perfil"]), des, "kg", p["kg"],
            f"{p['pecas']} peças · {p['metros']:.1f} m · {p['kgm']:.3f} kg/m · " + ", ".join(t(x, lang) for x in tipos[:6]),
            compra={"metros": round(p["metros"], 2), "barras": p["barras"], "barra_mm": res.get("barraComercial", 6000),
                    "maiores_que_barra": p["pecasMaioresQueBarra"]})
    for p in res["placasResumo"]:
        add("2 Placas", "PL-" + _slug(p["placa"]), p["nome"], "un", p["un"],
            f"{p['area']:.1f} m² líquidos · plano de corte com reaproveitamento ({p['unSemSobras']} sem reaproveitar) · desperdício {p['desperdicio'] * 100:.1f} %")
    for p in res["parafusos"]:
        add("3 Parafusos e fixações", "PAR-" + _slug(p["nome"]), p["nome"], "un", p["qtd"],
            " · ".join(f"{k}: {v}" for k, v in p["origens"].items()))
    for a in res["ancoragens"]:
        add("4 Ancoragens e conectores", "ANC-" + _slug(a["nome"]), a["nome"], "un", a["qtd"], " · ".join(a["origens"].keys()))
    ordem = {"Isolamento": "5", "ETICS": "6", "Membranas": "7", "Cobertura": "8", "Acabamento gesso": "9", "Vãos": "10"}
    for e in res["extras"]:
        det = []
        if e.get("rolos"):
            det.append(f"{e['rolos']} rolos")
        if e.get("embalagens"):
            det.append(f"{e['embalagens']} embalagens")
        if e.get("m3"):
            det.append(f"{e['m3']:.2f} m³")
        add(f"{ordem.get(e['cat'], '11')} {e['cat']}", "X-" + _slug(e["cat"] + " " + e["item"]), e["item"], e["un"], e["qtd"], " · ".join(det),
            e.get("refs"))
    out.sort(key=lambda r: (int(r["cat"].split()[0]), r["code"]))
    return out


# artigos vendidos à unidade, para os quais um preço de mercado online por unidade é comparável
MERCADO_UNIDADE = ("PL-", "ANC-")


def consulta_mercado(l: dict) -> str | None:
    """Texto de pesquisa de preço de mercado para uma linha (None = não comparável à unidade)."""
    if not l["code"].startswith(MERCADO_UNIDADE):
        return None
    return l["designacao"]


def precificar(lin: list[dict], biblioteca: list[dict] | None = None, precos: dict | None = None, mercado: dict | None = None) -> dict:
    """Atribui preços às linhas (in-place) e devolve os totais."""
    from engines.price_library import match_price
    precos = precos or {}
    mercado = mercado or {}
    tot = {"biblioteca": 0.0, "projeto": 0.0, "mercado": 0.0}
    sem = 0
    for l in lin:
        l.pop("preco", None)
        m = match_price(l["designacao"], l["un"], biblioteca or []) if biblioteca else None
        if m:
            l["preco"] = {"unit": float(m[0]), "origem": "biblioteca", "ref": m[1], "score": m[2]}
        elif l["code"] in precos or l["designacao"] in precos:
            l["preco"] = {"unit": float(precos.get(l["code"], precos.get(l["designacao"]))), "origem": "projeto"}
        elif l["code"] in mercado:
            mk = mercado[l["code"]]
            l["preco"] = {"unit": float(mk["price"]), "origem": "mercado", "fonte": mk.get("supplier"), "url": mk.get("url"),
                          "data": mk.get("checked_at"), "produto": mk.get("product")}
        if l.get("preco"):
            l["total"] = round(l["preco"]["unit"] * l["qtd"], 2)
            tot[l["preco"]["origem"]] += l["total"]
        else:
            l["total"] = None
            sem += 1
    total = sum(tot.values())
    return {"total": round(total, 2), "por_origem": {k: round(v, 2) for k, v in tot.items()}, "linhas_sem_preco": sem,
            "linhas": len(lin), "completo": sem == 0}


async def precos_mercado(lin: list[dict], limite: int = 12) -> dict:
    """Preços de mercado online (Portugal) para as linhas sem preço comparáveis à unidade. Só resultados reais (mode == web):
    o modo de demonstração do serviço de preços nunca é usado num orçamento."""
    from engines import price_search
    out = {}
    n = 0
    for l in lin:
        if l.get("preco") or n >= limite:
            continue
        q = consulta_mercado(l)
        if not q:
            continue
        n += 1
        try:
            r = await price_search.search(q, 6)
        except Exception:  # noqa: BLE001
            continue
        if r.get("mode") != "web":
            continue
        vals = sorted((x for x in r.get("results") or [] if x.get("price")), key=lambda x: x["price"])
        if not vals:
            continue
        med = vals[len(vals) // 2]
        out[l["code"]] = {**med, "n": len(vals), "checked_at": r.get("checked_at")}
    return out


def resumo_texto(res: dict, tot: dict | None = None) -> str:
    e = res["estudo"]
    s = (f"{e['nMembros']} perfis ({e['kgAco']:.0f} kg de aço, {e['kgPorM2']:.1f} kg/m²)" if e.get("kgPorM2") else f"{e['nMembros']} perfis ({e['kgAco']:.0f} kg)")
    s += f", {e['nParafusos']} parafusos"
    if tot:
        s += f"; total com preço {tot['total']:.2f} € ({tot['linhas_sem_preco']} linha(s) a orçamentar)"
    return s
