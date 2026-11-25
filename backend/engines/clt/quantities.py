"""Mapa de quantidades CLT — linhas codificadas a partir do resultado do motor (nada estimado por rácios).

Preços, pela mesma ordem do motor LSF (engines.lsf.quantities.precificar):
  1. biblioteca de preços da empresa; 2. preços do projeto; 3. preço de mercado online real (só artigos à unidade);
  4. sem preço → « a orçamentar ».
"""
from __future__ import annotations

from engines.lsf.quantities import _slug, precificar  # noqa: F401 — mesma lógica de preços

MERCADO_UNIDADE = ("CON-", "ANC-")


def linhas(res: dict, lang: str = "pt") -> list[dict]:
    out = []

    def add(cat, code, des, un, qtd, detalhe="", refs=None, compra=None):
        if not qtd:
            return
        out.append({"code": code, "cat": cat, "designacao": des, "un": un, "qtd": round(qtd, 3 if un in ("m", "m²", "m³", "kg") else 0),
                    "detalhe": detalhe, "refs": refs or [], "compra": compra})

    prod = res.get("produto") or {}
    for r in res["paineisResumo"]:
        cam = "-".join(str(int(c)) for c in r["camadas"])
        des = f"Painel CLT {r['esp']:.0f} mm ({len(r['camadas'])} camadas {cam}) — {prod.get('nome') or 'CLT'} {prod.get('classe') or ''}".strip()
        add("1 Painéis CLT", "CLT-" + _slug(r["painel"]), des, "m³", r["volPrensa"],
            f"{r['n']} painéis · {r['areaLiq']:.1f} m² · líquido {r['volLiq']:.2f} m³ · envolvente {r['volBruto']:.2f} m³ · "
            f"prensa {r['volPrensa']:.2f} m³ ({r['brutos']} brutos) · perda {r['desperdicio'] * 100:.1f} % · {r['kg'] / 1000:.1f} t",
            compra={"m3_liquido": round(r["volLiq"], 3), "m3_envolvente": round(r["volBruto"], 3), "brutos": r["brutos"]})
    cnc = res["estudo"].get("corteCNC")
    if cnc:
        add("2 Fabrico", "FAB-CNC", "Maquinagem CNC — contornos, recortes de vãos e bolsas", "m", cnc,
            f"{res['estudo']['nPaineis']} painéis · {res['estudo']['m2Vaos']:.1f} m² de vãos recortados ({res['estudo']['m3Vaos']:.2f} m³)")
    for e in res["extras"]:
        if e["cat"] in ("Lamelado-colado", "Réguas de junta"):
            cat = "3 Lamelado-colado e réguas"
            add(cat, "GL-" + _slug(e["item"]), e["item"], e["un"], e["qtd"], e.get("detalhe") or ", ".join(e.get("refs") or [])[:120])
    for p in res["parafusos"]:
        add("4 Parafusos e pregos", "PAR-" + _slug(p["nome"]), p["nome"], "un", p["qtd"], " · ".join(f"{k}: {v}" for k, v in p["origens"].items()))
    for c in res["conectores"]:
        add("5 Conectores metálicos", "CON-" + _slug(c["nome"]), c["nome"], "un", c["qtd"], " · ".join(f"{k}: {v}" for k, v in c["origens"].items()))
    for a in res["ancoragens"]:
        add("6 Ancoragens", "ANC-" + _slug(a["nome"]), a["nome"], "un", a["qtd"], " · ".join(a["origens"].keys()))
    for m in res["metros"]:
        add("7 Bandas e fitas", "SEL-" + _slug(m["chave"]), m["nome"], "m", m["m"],
            (f"{m['rolos']} rolos · " if m.get("rolos") else "") + " · ".join(f"{k}: {v:.1f} m" for k, v in m["origens"].items()))
    ordem = {"Membranas": "8", "Isolamento exterior": "9", "Cobertura": "10", "Camadas interiores": "11"}
    for e in res["extras"]:
        if e["cat"] in ("Lamelado-colado", "Réguas de junta"):
            continue
        det = []
        if e.get("rolos"):
            det.append(f"{e['rolos']} rolos")
        if e.get("m3"):
            det.append(f"{e['m3']:.2f} m³")
        add(f"{ordem.get(e['cat'], '12')} {e['cat']}", "X-" + _slug(e["cat"] + " " + e["item"]), e["item"], e["un"], e["qtd"], " · ".join(det),
            e.get("refs"))
    out.sort(key=lambda r: (int(r["cat"].split()[0]), r["code"]))
    return out


def consulta_mercado(l: dict) -> str | None:
    if not l["code"].startswith(MERCADO_UNIDADE):
        return None
    return l["designacao"]


async def precos_mercado(lin: list[dict], limite: int = 12) -> dict:
    """Preços de mercado online para os artigos à unidade sem preço. Só resultados reais (mode == web), nunca demonstração."""
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
    s = f"{e['nPaineis']} painéis CLT, {e['m3Liq']:.2f} m³ líquidos ({e['m3Prensa']:.2f} m³ de prensa, perda {e['desperdicio'] * 100:.1f} %)"
    s += f", {e['nParafusos']} parafusos/pregos, {e['nConectores']} conectores"
    if tot:
        s += f"; total com preço {tot['total']:.2f} € ({tot['linhas_sem_preco']} linha(s) a orçamentar)"
    return s
