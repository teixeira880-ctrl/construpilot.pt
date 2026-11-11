"""CLT cost, hours, margin and lead time from measured quantities and company parameters.

Every parameter carries its origin. "empresa" is a value the company entered.
"mercado" is a published average with its source. "hipotese" has no public source
and must be replaced by the company before the result is used to quote.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

Origin = Literal["empresa", "mercado", "hipotese"]
Value = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=6)]
CENT = Decimal("0.01")

SOURCES = {
    "holzkurier_lamelas": "Holzkurier, lamelas da Europa Central, 2.º trimestre 2025: 305–325 €/m³ (timber-online.net)",
    "holzkurier_clt": "Holzkurier, abril 2025: CLT a cerca de 500 €/m³ à porta da fábrica (timber-online.net)",
    "brandt_2019": "Brandt et al. 2019, BioResources 14(4): perda de 15% na madeira, 1,18 m³ de lamela por m³ de CLT",
    "kiilto_pur": "Kiilto Kestopur G 10 (PUR para CLT): 140–200 g/m² por junta colada",
    "sodra_epd": "Södra, EPD CLT 2025: 222 kWh de eletricidade por m³ no fabrico (A3)",
    "erse_2026": "ERSE / Eurostat, 1.º semestre 2026: eletricidade não doméstica em Portugal 0,1398 €/kWh sem IVA",
    "eurostat_2025": "Eurostat, 2025: custo médio da mão de obra em Portugal 19,4 €/h",
    "cnr_2022": "CNR, transporte rodoviário português: 1,13 €/km para um camião de 40 t",
    "gerador_clt": "Gerador de preços CYPE, EMD010 parede CLT: 1,543 h/m² de mão de obra, grua 4,35 €/m², 128,71 €/m² montado",
    "gerador_venda": "Gerador de preços CYPE, EMD010: 128,71 €/m² montado menos 67,02 €/m² de painel = 61,69 €/m² de montagem",
    "zaask_pladur": "Zaask Portugal: placa de gesso 1,90–5,03 €/m² de material, instalação média 25 €/m²",
    "zaask_pintura": "Zaask Portugal: pintura interior, média 7 €/m² de mão de obra",
    "rezult_eta": "Rezult ETA-21/0914: adesivo tipo I EN 15425, lamelas de 20 a 43 mm, dosagem não publicada",
}

# key: (group, label, unit, default, origin, source key or note)
CATALOGUE = {
    "timber_eur_m3": ("compra", "Madeira de lamelas, preço de compra", "€/m³", "315", "mercado", "holzkurier_lamelas"),
    "timber_input_m3_per_m3": ("compra", "Madeira comprada por m³ de CLT (perdas incluídas)", "m³/m³", "1.18", "mercado", "brandt_2019"),
    "adhesive_eur_kg": ("compra", "Adesivo PUR, preço de compra", "€/kg", "5", "hipotese", "Sem preço público. Preencher com a fatura do fornecedor."),
    "adhesive_kg_m2": ("compra", "Adesivo por m² de junta colada", "kg/m²", "0.16", "mercado", "kiilto_pur"),
    "labour_eur_h": ("producao", "Custo médio da hora do operário (fábrica)", "€/h", "19.4", "mercado", "eurostat_2025"),
    "fabrication_h_m3": ("producao", "Tempo de fabrico por m³ de CLT", "h/m³", "2", "hipotese", "Sem dado público. Medir na fábrica: horas totais da linha ÷ m³ produzidos."),
    "electricity_kwh_m3": ("producao", "Eletricidade por m³ de CLT", "kWh/m³", "222", "mercado", "sodra_epd"),
    "electricity_eur_kwh": ("producao", "Preço da eletricidade", "€/kWh", "0.1398", "mercado", "erse_2026"),
    "consumables_eur_m3": ("producao", "Outros consumíveis de fabrico (embalagem, ferramentas, manutenção)", "€/m³", "0", "hipotese", "Preencher com a contabilidade da fábrica."),
    "transport_eur_km": ("transporte", "Custo do camião por km", "€/km", "1.13", "mercado", "cnr_2022"),
    "transport_km": ("transporte", "Distância fábrica–obra (ida e volta)", "km", "300", "hipotese", "Indicar a distância real da obra."),
    "truck_m3": ("transporte", "m³ de CLT por camião", "m³/viagem", "35", "hipotese", "Depende do formato dos painéis e do limite de peso."),
    "assembly_basis": ("montagem", "Base de faturação da montagem subcontratada (1 = m², 0 = m³)", "—", "1", "hipotese", "Escolher como o subempreiteiro fatura."),
    "assembly_eur_m2": ("montagem", "Montagem subcontratada por m² de painel", "€/m²", "42.87", "mercado", "gerador_clt"),
    "assembly_eur_m3": ("montagem", "Montagem subcontratada por m³ de CLT", "€/m³", "0", "hipotese", "Preencher se o subempreiteiro faturar por m³."),
    "assembly_h_m2": ("montagem", "Horas de montagem por m² de painel", "h/m²", "1.543", "mercado", "gerador_clt"),
    "assembly_accessories_eur_m2": ("montagem", "Ligações, banda EPDM e fixações por m²", "€/m²", "11.5", "mercado", "gerador_clt"),
    "purchase_days": ("prazos", "Prazo de compra e receção da madeira", "dias", "21", "hipotese", "Prazo do fornecedor."),
    "factory_m3_day": ("prazos", "Capacidade de fabrico", "m³/dia", "20", "hipotese", "Capacidade real da linha."),
    "transport_days": ("prazos", "Prazo de entrega na obra", "dias", "2", "hipotese", "Planeamento logístico."),
    "assembly_crew": ("prazos", "Operários da equipa de montagem", "pessoas", "4", "hipotese", "Equipa do subempreiteiro."),
    "work_hours_day": ("prazos", "Horas de trabalho por dia", "h/dia", "8", "hipotese", "Horário da obra."),
    "board_eur_m2": ("revestimentos", "Placa de gesso, material", "€/m²", "3.5", "mercado", "zaask_pladur"),
    "board_waste": ("revestimentos", "Placa comprada por m² aplicado (desperdício incluído)", "m²/m²", "1.05", "hipotese", "Medir nas obras anteriores."),
    "board_fix_eur_m2": ("revestimentos", "Fixações, fita e massa por m² de placa", "€/m²", "1.5", "hipotese", "Preencher com a fatura do fornecedor."),
    "board_sub_eur_m2": ("revestimentos", "Aplicação de placa subcontratada por m² de camada", "€/m²", "25", "mercado", "zaask_pladur"),
    "paint_material_eur_m2": ("revestimentos", "Tinta por m² (duas demãos)", "€/m²", "1.5", "hipotese", "Preencher com o preço da tinta e o rendimento."),
    "paint_sub_eur_m2": ("revestimentos", "Pintura subcontratada por m²", "€/m²", "7", "mercado", "zaask_pintura"),
    "sale_clt_eur_m3": ("venda", "Preço de venda do CLT por m³", "€/m³", "500", "mercado", "holzkurier_clt"),
    "sale_assembly_eur_m2": ("venda", "Preço de venda da montagem por m²", "€/m²", "61.69", "mercado", "gerador_venda"),
    "sale_finish_markup": ("venda", "Margem sobre o custo dos revestimentos", "%", "15", "hipotese", "Política comercial da empresa."),
}


class Parameter(BaseModel):
    value: Value
    origin: Origin = "empresa"
    source: str = Field(default="", max_length=300)


def defaults():
    return {key: {"group": g, "label": label, "unit": unit, "value": value, "origin": origin,
                  "source": SOURCES.get(source, source)}
            for key, (g, label, unit, value, origin, source) in CATALOGUE.items()}


def merged(saved):
    """Catalogue defaults overlaid with what the company saved."""
    result = defaults()
    for key, item in (saved or {}).items():
        if key in result:
            result[key].update(value=str(item["value"]), origin=item.get("origin", "empresa"),
                               source=item.get("source") or "Valor da empresa")
    return result


class Wall(BaseModel):
    thickness_mm: Annotated[Decimal, Field(gt=0, le=500)]
    layers: Annotated[int, Field(ge=3, le=9)]
    length_m: Annotated[Decimal, Field(gt=0, le=10_000)]


class FloorInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    height_m: Annotated[Decimal, Field(gt=0, le=20)]
    walls: list[Wall] = Field(min_length=1, max_length=500)
    board_layers_m2: Value = Decimal(0)
    paint_m2: Value = Decimal(0)


class EstimateInput(BaseModel):
    floors: list[FloorInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique(self):
        if len({f.name for f in self.floors}) != len(self.floors):
            raise ValueError("Cada piso deve ter um nome único.")
        return self


def _ceil(numerator, denominator):
    if not denominator:
        return None
    return (Decimal(numerator) / denominator).to_integral_value(rounding=ROUND_CEILING)


def _q(value):
    return float(Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP))


def estimate(body: EstimateInput, parameters):
    p = {key: Decimal(str(item["value"])) for key, item in parameters.items()}
    hypotheses = sorted(item["label"] for item in parameters.values() if item["origin"] == "hipotese")
    floors, totals = [], {}
    for floor in body.floors:
        area = sum((w.length_m * floor.height_m for w in floor.walls), Decimal(0))
        volume = sum((w.length_m * floor.height_m * w.thickness_mm / 1000 for w in floor.walls), Decimal(0))
        glue_area = sum((w.length_m * floor.height_m * (w.layers - 1) for w in floor.walls), Decimal(0))
        glue_kg = glue_area * p["adhesive_kg_m2"]
        timber_m3 = volume * p["timber_input_m3_per_m3"]
        fabrication_h = volume * p["fabrication_h_m3"]
        assembly_h = area * p["assembly_h_m2"]
        assembly = (area * p["assembly_eur_m2"] if p["assembly_basis"] >= 1 else volume * p["assembly_eur_m3"])
        boards = floor.board_layers_m2
        costs = {
            "compra": timber_m3 * p["timber_eur_m3"] + glue_kg * p["adhesive_eur_kg"],
            "producao": fabrication_h * p["labour_eur_h"]
                        + volume * p["electricity_kwh_m3"] * p["electricity_eur_kwh"] + volume * p["consumables_eur_m3"],
            "transporte": Decimal(0),
            "montagem": assembly + area * p["assembly_accessories_eur_m2"],
            "revestimentos": boards * (p["board_waste"] * p["board_eur_m2"] + p["board_fix_eur_m2"] + p["board_sub_eur_m2"])
                             + floor.paint_m2 * (p["paint_material_eur_m2"] + p["paint_sub_eur_m2"]),
        }
        floors.append((floor, area, volume, timber_m3, glue_kg, fabrication_h, assembly_h, boards, costs))
    volume_total = sum((f[2] for f in floors), Decimal(0))
    trips = _ceil(volume_total, p["truck_m3"]) or Decimal(0)
    transport = trips * p["transport_km"] * p["transport_eur_km"]
    rows = []
    for floor, area, volume, timber_m3, glue_kg, fabrication_h, assembly_h, boards, costs in floors:
        costs["transporte"] = transport * volume / volume_total if volume_total else Decimal(0)
        cost = sum(costs.values(), Decimal(0))
        revenue = (volume * p["sale_clt_eur_m3"] + area * p["sale_assembly_eur_m2"]
                   + costs["revestimentos"] * (1 + p["sale_finish_markup"] / 100))
        margin = revenue - cost
        row = {
            "piso": floor.name, "comprimento_m": _q(sum((w.length_m for w in floor.walls), Decimal(0))),
            "altura_m": float(floor.height_m), "montagem_m2": _q(area), "fabrico_m3": _q(volume),
            "madeira_comprada_m3": _q(timber_m3), "adesivo_kg": _q(glue_kg),
            "eletricidade_kwh": _q(volume * p["electricity_kwh_m3"]),
            "horas_fabrico": _q(fabrication_h), "horas_montagem": _q(assembly_h),
            "placa_m2": _q(boards * p["board_waste"]), "pintura_m2": _q(floor.paint_m2),
            "custos_eur": {k: _q(v) for k, v in costs.items()}, "custo_total_eur": _q(cost),
            "receita_eur": _q(revenue), "margem_eur": _q(margin),
            "margem_percent": _q(margin * 100 / revenue) if revenue else None,
        }
        rows.append(row)
        for key, value in (("montagem_m2", area), ("fabrico_m3", volume), ("horas_fabrico", fabrication_h),
                           ("horas_montagem", assembly_h), ("custo_total_eur", cost), ("receita_eur", revenue),
                           ("margem_eur", margin)):
            totals[key] = totals.get(key, Decimal(0)) + value
    crew_day = p["assembly_crew"] * p["work_hours_day"]
    schedule = {
        "compra_dias": float(p["purchase_days"]),
        "fabrico_dias": float(_ceil(volume_total, p["factory_m3_day"])) if p["factory_m3_day"] else None,
        "transporte_dias": float(p["transport_days"]),
        "montagem_dias": float(_ceil(totals["horas_montagem"], crew_day)) if crew_day else None,
    }
    schedule["total_dias"] = sum(v for v in schedule.values() if v is not None)
    percent = _q(totals["margem_eur"] * 100 / totals["receita_eur"]) if totals["receita_eur"] else None
    totals = {k: _q(v) for k, v in totals.items()}
    totals["viagens"] = int(trips)
    totals["margem_percent"] = percent
    return {"pisos": rows, "total": totals, "prazo": schedule, "hipoteses_por_confirmar": hypotheses,
            "status": "estimativa" if hypotheses else "valores_da_empresa"}
