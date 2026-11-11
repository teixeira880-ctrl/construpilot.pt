"""Complete CLT study for the Assistant: quantities, prices, plan and profitability in one PDF note.

The numbers come only from clt_economics.estimate with the account's own parameters and library, and from the
floors the company reviewed on the CLT page (the last estimate it ran there) or passed explicitly. Nothing is
recomputed here: the note lays the estimate out and lists every value still marked as a hypothesis.
"""
from __future__ import annotations

from bim_studio.clt_economics import CATEGORIES, STAGE_ORDER, EstimateInput, estimate

STAGE_NAMES = {"compra": "Compra de matéria-prima", "fabrico": "Fabrico", "producao": "Produção (energia e mão de obra)", "transporte": "Transporte", "montagem": "Montagem",
               "revestimentos": "Revestimentos e isolamentos", "acabamentos": "Instalações e acabamentos",
               "entrega": "Entrega", "indiretos": "Custos indiretos", "venda": "Venda"}
ORIGINS = {"empresa": "empresa", "mercado": "mercado", "hipotese": "HIPÓTESE", "norma": "norma"}


def _n(value, digits=2):
    if value is None:
        return "—"
    text = f"{float(value):,.{digits}f}"
    return text.replace(",", " ").replace(".", ",")


def note(entrada: dict, parametros: dict, biblioteca: dict, titulo: str | None = None) -> dict:
    """entrada: EstimateInput as JSON; parametros / biblioteca: the account's merged parameters and library."""
    from engines.calc_lots import notes
    from reportlab.lib.units import mm

    body = EstimateInput.model_validate(entrada)
    r = estimate(body, parametros, biblioteca)
    t, plan = r["total"], r["plano"]
    titre = titulo or "Estudo CLT completo"
    kp = [{"label": "Custo total", "value": _n(t["custo_total_eur"], 0), "unit": "€"},
          {"label": "Venda sem IVA", "value": _n(t["receita_eur"], 0), "unit": "€"},
          {"label": f"Venda com IVA {_n(t['iva_percent'], 0)} %", "value": _n(t["receita_com_iva_eur"], 0), "unit": "€"},
          {"label": "Margem", "value": _n(t["margem_percent"], 1), "unit": "%", "ok": (t["margem_percent"] or 0) > 0},
          {"label": "CLT fabricado", "value": _n(t["fabrico_m3"]), "unit": "m³"},
          {"label": "Prazo", "value": str(plan["dias"]), "unit": "dias"}]
    estado = ("Todos os valores vêm da empresa ou do mercado." if r["status"] == "valores_da_empresa" else
              f"ESTIMATIVA: {len(r['hipoteses_por_confirmar'])} valores ainda são hipóteses (lista no fim). "
              "A empresa confirma-os em Parâmetros e Biblioteca na página CLT.")
    blocs = [("kpis", kp),
             ("p", "Quantidades medidas nos planos revistos na página CLT e preços da biblioteca da empresa. Betão e lajes de betão "
                   "fora do âmbito. Não inclui cálculo estrutural, projetos de especialidade nem planos de execução. " + estado)]

    W = mm
    blocs.append(("h2", "1. Quantidades por piso"))
    rows = []
    for p in r["pisos"]:
        pm = p["paineis_m2"]
        rows.append([p["piso"], _n(p["parede_m2"]), _n(pm.get("laje")), _n(pm.get("cobertura")), _n(pm.get("lintel")),
                     _n(p["fabrico_m3"]), _n(p["madeira_comprada_m3"]), _n(p["adesivo_kg"], 0), _n(p["viga_aco_m"])])
    blocs.append(("table", ["Piso", "Paredes m²", "Laje m²", "Cobertura m²", "Lintéis m²", "CLT m³", "Madeira m³", "Cola kg", "Aço m"],
                  rows, [18 * W, 22 * W, 18 * W, 22 * W, 20 * W, 18 * W, 22 * W, 20 * W, 20 * W]))
    rows = [[p["piso"], _n(p["placa_m2"]), _n(p["teto_m2"]), _n(p["fachada_m2"]), _n(p["laje_betao_m2"]), _n(p["cobertura_m2"]),
             _n(p["horas_fabrico"], 1), _n(p["horas_montagem"], 1)] for p in r["pisos"]]
    blocs.append(("table", ["Piso", "Placa m²", "Teto m²", "Fachada m²", "Isol. laje m²", "Isol. cob. m²", "h fabrico", "h montagem"],
                  rows, [18 * W, 22 * W, 22 * W, 24 * W, 24 * W, 24 * W, 22 * W, 24 * W]))
    for text in r["notas_quantidades"]:
        blocs.append(("p", text))

    blocs.append(("h2", "2. Orçamento detalhado (quantidade × preço unitário)"))
    for cat in CATEGORIES:
        lines = [l for l in r["linhas"] if l["categoria"] == cat and l["quantidade"]]
        if not lines:
            continue
        blocs.append(("p", CATEGORIES[cat][0]))
        rows = [[l["codigo"], l["designacao"], _n(l["quantidade"]), l["unidade"], _n(l["custo_unitario_eur"]),
                 _n(l["custo_eur"]) if l["fase"] != "venda" else "—", _n(l["venda_eur"]) if l["venda_eur"] is not None else "—",
                 ORIGINS.get(l["origem"], l["origem"])] for l in lines]
        blocs.append(("table", ["Código", "Designação", "Qtd.", "Un.", "€/un.", "Custo €", "Venda €", "Origem"],
                      rows, [28 * W, 50 * W, 17 * W, 10 * W, 15 * W, 20 * W, 20 * W, 20 * W]))

    blocs.append(("h2", "3. Custos por fase e rentabilidade"))
    rows = [[STAGE_NAMES.get(s, s), _n(t["custos_eur"].get(s, 0))] for s in STAGE_ORDER if t["custos_eur"].get(s)]
    rows += [["Custo total", _n(t["custo_total_eur"])], ["Venda sem IVA", _n(t["receita_eur"])],
             [f"IVA {_n(t['iva_percent'], 0)} %", _n(t["iva_eur"])], ["Venda com IVA (cliente final)", _n(t["receita_com_iva_eur"])],
             ["Margem €", _n(t["margem_eur"])], ["Margem % da venda", _n(t["margem_percent"], 1)]]
    blocs.append(("table", ["Fase", "€"], rows, [120 * W, 60 * W]))
    rows = [[p["piso"], _n(p["custo_total_eur"]), _n(p["receita_eur"]), _n(p["margem_eur"]), _n(p["margem_percent"], 1)] for p in r["pisos"]]
    blocs.append(("table", ["Piso", "Custo €", "Venda €", "Margem €", "Margem %"], rows, [36 * W, 36 * W, 36 * W, 36 * W, 36 * W]))

    blocs.append(("h2", "4. Plano de seguimento, da fabricação à montagem"))
    rows = [[STAGE_NAMES.get(f["fase"], f["fase"]), f["descricao"], str(f["dias"]), f["inicio"], f["fim"]] for f in plan["fases"]]
    blocs.append(("table", ["Fase", "Descrição", "Dias", "Início", "Fim"], rows, [36 * W, 78 * W, 14 * W, 26 * W, 26 * W]))
    blocs.append(("p", f"{t['viagens']} viagens de painéis para a obra e {t['viagens_materia_prima']} de matéria-prima. "
                       "Ao criar o lote de custos a partir desta estimativa, a página CLT segue o real contra este orçamento."))

    hyp = r["hipoteses_por_confirmar"]
    pdf, png = notes.pdf(titre, "Quantidades, preços, plano e rentabilidade · motor ConstruPilot CLT", blocs, hyp)
    resumo = [f"{titre}: custo {_n(t['custo_total_eur'], 0)} €, venda {_n(t['receita_eur'], 0)} € sem IVA "
              f"({_n(t['receita_com_iva_eur'], 0)} € com IVA {_n(t['iva_percent'], 0)} %), margem {_n(t['margem_percent'], 1)} %.",
              f"CLT {_n(t['fabrico_m3'])} m³, montagem {_n(t['montagem_m2'])} m², prazo {plan['dias']} dias "
              f"({plan['inicio']} → {plan['fim']}).",
              "Custos por fase: " + "; ".join(f"{STAGE_NAMES.get(s, s)} {_n(v, 0)} €" for s, v in t["custos_eur"].items() if v),
              estado]
    if hyp:
        resumo.append("Hipóteses por confirmar: " + "; ".join(hyp[:25]) + (" …" if len(hyp) > 25 else ""))
    data = {"custo_total_eur": t["custo_total_eur"], "receita_eur": t["receita_eur"], "receita_com_iva_eur": t["receita_com_iva_eur"],
            "margem_percent": t["margem_percent"], "fabrico_m3": t["fabrico_m3"], "dias": plan["dias"], "estado": r["status"],
            "hipoteses": len(hyp)}
    return {"titre": titre, "pdf": pdf, "png": png, "resumo": resumo, "data": data}
