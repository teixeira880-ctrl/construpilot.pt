"""CLT price libraries, technical parameters, total cost, margin and planning.

Two kinds of company data:

* Price libraries: one item per price, with a cost and an optional sale price,
  a unit and a calculation basis (per m³ of CLT, per m² of assembly, per hour of
  fabrication, per trip, per project day…). Every quantity of the estimate is
  the basis quantity times the item's consumption per basis.
* Technical parameters: consumptions, times, capacities and distances that turn
  the measured geometry into basis quantities.

Every value carries its origin. "empresa" is a value the company entered.
"mercado" is a published average with its source. "hipotese" has no public source
and must be replaced by the company before the result is used to quote.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from bim_studio import clt_fitout

Origin = Literal["empresa", "mercado", "hipotese"]
Value = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=6)]
CENT = Decimal("0.01")

SOURCES = {
    "press_reference": "Formato de prensa de referência: Rezult, comprimento ≤ 18,00 m e largura ≤ 3,50 m "
                       "(clt-rezult.com/en/technical-characteristics, lido em 2026-11-11). Indique o formato da sua prensa.",
    "holzkurier_lamelas": "Holzkurier, lamelas da Europa Central, 2.º trimestre 2025: 305–325 €/m³ (timber-online.net)",
    "holzkurier_clt": "Holzkurier, abril 2025: CLT a cerca de 500 €/m³ à porta da fábrica (timber-online.net)",
    "brandt_2019": "Brandt et al. 2019, BioResources 14(4): perda de 15% na madeira, 1,18 m³ de lamela por m³ de CLT",
    "kiilto_pur": "Kiilto Kestopur G 10 (PUR para CLT): 140–200 g/m² por junta colada",
    "sodra_epd": "Södra, EPD CLT 2025: 222 kWh de eletricidade por m³ no fabrico (A3)",
    "eurostat_elec": "Eurostat nrg_pc_205, Portugal, não doméstico 500–1999 MWh, sem impostos, 1.º semestre 2026: 0,1086 €/kWh",
    "eurostat_2025": "Eurostat, 2025: custo médio da mão de obra em Portugal 19,4 €/h",
    "cnr_2022": "CNR, transporte rodoviário português: 1,13 €/km para um camião de 40 t",
    "gerador_clt": "Gerador de preços CYPE, EMD010 parede CLT: 1,543 h/m² de mão de obra (38,52 €/m²), grua 0,058 h/m² a 75,04 €/h, 128,71 €/m² montado",
    "gerador_acess": "Gerador de preços CYPE, EMD010: banda EPDM 5,86 + reforço de juntas 2,04 + ligações 2,10 + fixações 1,50 €/m²",
    "gerador_venda": "Gerador de preços CYPE, EMD010: 128,71 €/m² montado menos 67,02 €/m² de painel = 61,69 €/m²",
    "zaask_pladur": "Zaask Portugal: placa de gesso 1,90–5,03 €/m² de material, instalação média 25 €/m²",
    "zaask_pintura": "Zaask Portugal: pintura interior, média 7 €/m² de mão de obra",
    "rezult_eta": "Rezult ETA-21/0914: adesivo tipo I EN 15425, lamelas de 20 a 43 mm, dosagem não publicada",
    "pku_193": ("Código Tributário da Ucrânia (Податковий кодекс України), art. 193.1 a): taxa base de ПДВ 20 %. A primeira venda de "
                "habitação nova é tributada; o art. 197.1.14 isenta só as vendas seguintes."),
    "pku_195": ("Código Tributário da Ucrânia, art. 195.1.1: taxa 0 % na exportação de bens (painéis enviados para fora da Ucrânia); "
                "aplica-se o IVA do país de destino."),
    "civa": "Código do IVA, art. 18.º: taxa normal de 23% no continente. A taxa de 6% só se aplica a obras específicas (verba 2.27 e 2.32 da lista I).",
    "agua": "Tarifa municipal (ERSAR não publica uma média nacional por API). Indicar a tarifa do concelho da fábrica.",
}

CATEGORIES = {
    "materia_prima": ("Matéria-prima", "compra"),
    "energia": ("Energia e água", "producao"),
    "colaboradores": ("Colaboradores", "producao"),
    "transporte": ("Transporte", "transporte"),
    "maquinas": ("Gruas e máquinas", "montagem"),
    "montagem": ("Montagem em obra", "montagem"),
    "revestimentos": ("Revestimentos", "revestimentos"),
    "isolamentos": ("Isolamentos, impermeabilização e betão leve", "revestimentos"),
    "estrutura": ("Estrutura complementar", "compra"),
    "caixilharia": ("Caixilharia e portas", "acabamentos"),
    "eletricidade": ("Eletricidade", "acabamentos"),
    "canalizacao": ("Canalização e louças", "acabamentos"),
    "acabamentos": ("Pavimentos, cerâmica e acabamentos", "acabamentos"),
    "indiretos": ("Engenharia, estaleiro e imprevistos", "indiretos"),
    "venda": ("Venda do CLT", "venda"),
}
BASES = {
    "m3_clt": "m³ de CLT fabricado", "m3_madeira": "m³ de madeira comprada", "kg_cola": "kg de cola",
    "m2_montagem": "m² de painel montado", "h_fabrico": "hora de fabrico", "h_montagem": "hora de montagem",
    "kwh": "kWh consumido", "km_materia_prima": "km de transporte da matéria-prima",
    "km_obra": "km de transporte para a obra", "viagem": "viagem para a obra",
    "dia_fabrico": "dia de fabrico", "dia_montagem": "dia de montagem",
    "m2_placa": "m² de placa aplicada (por camada)", "m2_pintura": "m² pintado", "projeto": "projeto",
    "m2_teto": "m² de teto falso", "m2_laje": "m² de laje CLT com betão leve", "m2_cobertura": "m² de cobertura plana",
    "m2_fachada": "m² de face exterior de parede", "m_viga_aco": "m de viga de aço",
    "pct_custo": "% do custo direto",
    "un_tomada": "tomada", "un_ponto_luz": "ponto de luz", "un_interruptor": "interruptor", "m_cabo": "m de cabo",
    "m_tubo_eletrico": "m de tubo elétrico", "un_circuito": "circuito", "un_quadro": "quadro elétrico", "un_diferencial": "diferencial",
    "un_ponto_agua": "ponto de água", "m_tubo_agua": "m de tubo de água", "un_ponto_esgoto": "ponto de esgoto",
    "m_tubo_esgoto": "m de tubo de esgoto", "un_sanita": "sanita", "un_lavatorio": "lavatório", "un_base_duche": "base de duche",
    "un_banheira": "banheira", "un_lava_loica": "lava-loiça", "un_aqs": "equipamento de águas quentes",
    "m2_caixilharia": "m² de caixilharia exterior", "un_vao_exterior": "vão exterior", "un_porta_interior": "porta interior",
    "un_porta_entrada": "porta de entrada", "m2_pavimento": "m² de pavimento", "m2_pavimento_ceramico": "m² de pavimento cerâmico",
    "m2_ceramica_parede": "m² de cerâmica de parede", "m_rodape": "m de rodapé",
}
PROJECT_BASES = {"km_materia_prima", "km_obra", "viagem", "dia_fabrico", "dia_montagem", "projeto"}

# code: (category, name, unit, cost, sale, basis, consumption per basis, origin, source)
LIBRARY = {
    "MP-LAMELA": ("materia_prima", "Madeira de lamelas C24 seca e aplainada", "m³", "315", None, "m3_madeira", "1", "mercado", "holzkurier_lamelas"),
    "MP-COLA-PUR": ("materia_prima", "Adesivo PUR monocomponente tipo I", "kg", "5", None, "kg_cola", "1", "hipotese", "Sem preço público. Preencher com a fatura do fornecedor."),
    "EN-ELETRICIDADE": ("energia", "Eletricidade da fábrica", "kWh", "0.1086", None, "kwh", "1", "mercado", "eurostat_elec"),
    "EN-AGUA": ("energia", "Água da fábrica", "m³", "2.5", None, "m3_clt", "0.05", "hipotese", "agua"),
    "COL-OPERADOR": ("colaboradores", "Operador de linha CLT", "h", "19.4", None, "h_fabrico", "1", "mercado", "eurostat_2025"),
    "TR-MATERIA-PRIMA": ("transporte", "Transporte da madeira até à fábrica", "km", "1.13", None, "km_materia_prima", "1", "mercado", "cnr_2022"),
    "TR-OBRA": ("transporte", "Transporte dos painéis até à obra", "km", "1.13", None, "km_obra", "1", "mercado", "cnr_2022"),
    "MAQ-GRUA": ("maquinas", "Grua autopropulsada 30 t", "h", "75.04", None, "m2_montagem", "0.058", "mercado", "gerador_clt"),
    "MONT-PAINEL-M2": ("montagem", "Montagem subcontratada de painéis CLT", "m²", "38.52", "61.69", "m2_montagem", "1", "mercado", "gerador_clt"),
    "MONT-ACESSORIOS": ("montagem", "Ligações, banda EPDM e fixações", "m²", "11.5", None, "m2_montagem", "1", "mercado", "gerador_acess"),
    "REV-PLACA-BA13": ("revestimentos", "Placa de gesso BA13 (material)", "m²", "3.5", "4.03", "m2_placa", "1.05", "mercado", "zaask_pladur"),
    "REV-FIXACOES": ("revestimentos", "Fixações, fita e massa", "m²", "1.5", "1.73", "m2_placa", "1", "hipotese", "Preencher com a fatura do fornecedor."),
    "REV-PLACA-SUB": ("revestimentos", "Aplicação de placa subcontratada", "m²", "25", "28.75", "m2_placa", "1", "mercado", "zaask_pladur"),
    "REV-TINTA": ("revestimentos", "Tinta, duas demãos", "m²", "1.5", "1.73", "m2_pintura", "1", "hipotese", "Preencher com o preço da tinta e o rendimento."),
    "REV-PINTURA-SUB": ("revestimentos", "Pintura subcontratada", "m²", "7", "8.05", "m2_pintura", "1", "mercado", "zaask_pintura"),
    "REV-PLACA-BA15": ("revestimentos", "Placa de gesso BA15 do teto (material)", "m²", "4.5", "5.18", "m2_teto", "1.05", "mercado", "zaask_pladur"),
    "REV-TETO-SUB": ("revestimentos", "Teto falso suspenso subcontratado (perfis e aplicação)", "m²", "25", "28.75", "m2_teto", "1", "mercado", "zaask_pladur"),
    "ISO-LAJE": ("isolamentos", "Membrana acústica e betão leve 100 mm sobre a laje", "m²", "28", "32.2", "m2_laje", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "ISO-COBERTURA": ("isolamentos", "Cobertura plana: XPS 100 mm, betão leve, PVC e seixo", "m²", "60", "69", "m2_cobertura", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "ISO-FACHADA": ("isolamentos", "Fachada: lã mineral 100 mm e membrana de vapor (sem acabamento exterior)", "m²", "22", "25.3", "m2_fachada", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "EST-VIGA-ACO": ("estrutura", "Viga de aço (perfil não indicado no desenho), fornecida e montada", "m", "90", "103.5", "m_viga_aco", "1", "hipotese", "O perfil não está no desenho. Preencher após o cálculo estrutural."),
    "CX-CAIXILHARIA": ("caixilharia", "Caixilharia exterior em alumínio com corte térmico e vidro duplo, colocada", "m²", "350", "402.5", "m2_caixilharia", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CX-REMATES": ("caixilharia", "Peitoris, soleiras e remates de vão", "un", "60", "69", "un_vao_exterior", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CX-PORTA-ENTRADA": ("caixilharia", "Porta de entrada de segurança, colocada", "un", "1200", "1380", "un_porta_entrada", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CX-PORTA-INTERIOR": ("caixilharia", "Porta interior lacada com aro e ferragens, colocada", "un", "280", "322", "un_porta_interior", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "EL-TOMADA": ("eletricidade", "Tomada com caixa, aparelhagem e mão de obra", "un", "35", "40.25", "un_tomada", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "EL-PONTO-LUZ": ("eletricidade", "Ponto de luz com caixa e mão de obra", "un", "30", "34.5", "un_ponto_luz", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "EL-INTERRUPTOR": ("eletricidade", "Interruptor com caixa e aparelhagem", "un", "25", "28.75", "un_interruptor", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "EL-CABO": ("eletricidade", "Cabo H07V (equivalente 3 condutores)", "m", "1.2", "1.38", "m_cabo", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "EL-TUBO": ("eletricidade", "Tubo corrugado VD embebido na parede técnica", "m", "0.6", "0.69", "m_tubo_eletrico", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "EL-QUADRO": ("eletricidade", "Quadro elétrico com disjuntores, montado", "un", "450", "517.5", "un_quadro", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "EL-DIFERENCIAL": ("eletricidade", "Interruptor diferencial 30 mA", "un", "60", "69", "un_diferencial", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-PONTO-AGUA": ("canalizacao", "Ponto de água (multicamada, acessórios e mão de obra)", "un", "45", "51.75", "un_ponto_agua", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-TUBO-AGUA": ("canalizacao", "Tubo multicamada isolado", "m", "4", "4.6", "m_tubo_agua", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-PONTO-ESGOTO": ("canalizacao", "Ponto de esgoto em PVC com sifão", "un", "40", "46", "un_ponto_esgoto", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-TUBO-ESGOTO": ("canalizacao", "Tubo PVC de esgoto", "m", "6", "6.9", "m_tubo_esgoto", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-SANITA": ("canalizacao", "Sanita suspensa com autoclismo embutido, colocada", "un", "380", "437", "un_sanita", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-LAVATORIO": ("canalizacao", "Lavatório com misturadora, colocado", "un", "220", "253", "un_lavatorio", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-DUCHE": ("canalizacao", "Base de duche, resguardo e misturadora", "un", "450", "517.5", "un_base_duche", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-BANHEIRA": ("canalizacao", "Banheira com misturadora, colocada", "un", "550", "632.5", "un_banheira", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-LAVA-LOICA": ("canalizacao", "Lava-loiça com misturadora, colocado", "un", "200", "230", "un_lava_loica", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "CN-AQS": ("canalizacao", "Bomba de calor para águas quentes 200 L, instalada", "un", "1800", "2070", "un_aqs", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "AC-PAVIMENTO": ("acabamentos", "Pavimento flutuante com base acústica e rodapé de remate", "m²", "35", "40.25", "m2_pavimento", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "AC-PAV-CERAMICO": ("acabamentos", "Pavimento cerâmico com impermeabilização, colocado", "m²", "45", "51.75", "m2_pavimento_ceramico", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "AC-CERAMICA-PAREDE": ("acabamentos", "Cerâmica de parede 10×10 com impermeabilização, colocada", "m²", "50", "57.5", "m2_ceramica_parede", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "AC-RODAPE": ("acabamentos", "Rodapé de madeira lacado", "m", "8", "9.2", "m_rodape", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "AC-FACHADA": ("acabamentos", "Acabamento exterior da fachada (sistema a definir)", "m²", "45", "51.75", "m2_fachada", "1", "hipotese", "Preencher com o preço do fornecedor ou subempreiteiro."),
    "IND-ENGENHARIA": ("indiretos", "Projeto de estabilidade e desenhos de fabrico", "%", "3", "3", "pct_custo", "1", "hipotese", "Percentagem do custo direto, faturada ao custo. Preencher com o valor da empresa."),
    "IND-ESTALEIRO": ("indiretos", "Estaleiro, seguros e segurança em obra", "%", "3", "3", "pct_custo", "1", "hipotese", "Percentagem do custo direto, faturada ao custo. Preencher com o valor da empresa."),
    "IND-IMPREVISTOS": ("indiretos", "Imprevistos", "%", "5", "5", "pct_custo", "1", "hipotese", "Percentagem do custo direto, faturada ao custo. Preencher com o valor da empresa."),
    "VENDA-CLT": ("venda", "Painel CLT fornecido", "m³", "0", "500", "m3_clt", "1", "mercado", "holzkurier_clt"),
}

# key: (group, label, unit, default, origin, source)
CATALOGUE = {
    "timber_input_m3_per_m3": ("fabrico", "Madeira comprada por m³ de CLT (perdas incluídas)", "m³/m³", "1.18", "mercado", "brandt_2019"),
    "adhesive_kg_m2": ("fabrico", "Cola por m² de junta colada", "kg/m²", "0.16", "mercado", "kiilto_pur"),
    "fabrication_h_m3": ("fabrico", "Tempo de fabrico por m³ de CLT", "h/m³", "2", "hipotese", "Sem dado público. Medir na fábrica: horas totais da linha ÷ m³ produzidos."),
    "press_length_m": ("fabrico", "Comprimento máximo do painel de prensa", "m", "18", "mercado", "press_reference"),
    "press_width_m": ("fabrico", "Largura máxima do painel de prensa", "m", "3.5", "mercado", "press_reference"),
    "electricity_kwh_m3": ("fabrico", "Eletricidade por m³ de CLT", "kWh/m³", "222", "mercado", "sodra_epd"),
    "factory_m3_day": ("fabrico", "Capacidade de fabrico", "m³/dia", "20", "hipotese", "Capacidade real da linha."),
    "materia_prima_km": ("transporte", "Distância serração–fábrica (ida e volta)", "km", "200", "hipotese", "Indicar o fornecedor."),
    "materia_prima_truck_m3": ("transporte", "m³ de madeira por camião", "m³/viagem", "35", "hipotese", "Carga habitual do fornecedor."),
    "obra_km": ("transporte", "Distância fábrica–obra (ida e volta)", "km", "300", "hipotese", "Indicar a distância real da obra."),
    "truck_m3": ("transporte", "m³ de CLT por camião", "m³/viagem", "35", "hipotese", "Depende do formato dos painéis e do limite de peso."),
    "assembly_h_m2": ("montagem", "Horas de montagem por m² de painel", "h/m²", "1.543", "mercado", "gerador_clt"),
    "assembly_crew": ("montagem", "Operários da equipa de montagem", "pessoas", "4", "hipotese", "Equipa do subempreiteiro."),
    "work_hours_day": ("montagem", "Horas de trabalho por dia", "h/dia", "8", "hipotese", "Horário da obra."),
    "purchase_days": ("prazos", "Prazo de compra e receção da madeira", "dias", "21", "hipotese", "Prazo do fornecedor."),
    "transport_days": ("prazos", "Prazo de entrega na obra", "dias", "2", "hipotese", "Planeamento logístico."),
    "fitout_days": ("prazos", "Prazo de instalações e acabamentos até à entrega da chave", "dias", "60", "hipotese", "Planeamento da empresa e dos subempreiteiros."),
    "standard_height_ground_m": ("geometria", "Altura standard do RDC (quando a planta não marca alturas)", "m", "3.00", "empresa",
                                 "Standard da empresa: RDC 3,00 m quando a planta não indica altura."),
    "standard_height_upper_m": ("geometria", "Altura standard dos outros pisos (quando a planta não marca alturas)", "m", "2.50", "empresa",
                                "Standard da empresa: 2,50 m nos pisos acima do RDC quando a planta não indica altura."),
    "iva_percent": ("venda", "IVA sobre a venda", "%", "23", "mercado", "civa"),
    "iva_ua_percent": ("venda", "ПДВ (IVA ucraniano) sobre a venda", "%", "20", "mercado", "pku_193"),
}


def _source(key):
    return SOURCES.get(key, key)


class Parameter(BaseModel):
    value: Value
    origin: Origin = "empresa"
    source: str = Field(default="", max_length=300)


def defaults():
    return {key: {"group": g, "label": label, "unit": unit, "value": value, "origin": origin, "source": _source(source)}
            for key, (g, label, unit, value, origin, source) in CATALOGUE.items()}


def merged(saved):
    """Technical parameters: defaults overlaid with what the company saved."""
    result = defaults()
    for key, item in (saved or {}).items():
        if key in result:
            result[key].update(value=str(item["value"]), origin=item.get("origin", "empresa"),
                               source=item.get("source") or "Valor da empresa")
    return result


class LibraryItem(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    category: Literal[tuple(CATEGORIES)]
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=12)
    cost_eur: Value
    sale_eur: Value | None = None
    basis: Literal[tuple(BASES)]
    per_basis: Value = Decimal(1)
    origin: Origin = "empresa"
    source: str = Field(default="", max_length=300)
    effective_from: date | None = None

    @field_validator("code")
    @classmethod
    def upper(cls, value):
        return value.upper()


def library_defaults():
    items = {}
    for code, (category, name, unit, cost, sale, basis, per_basis, origin, source) in LIBRARY.items():
        note = " · Venda = custo + 15% (hipótese)" if category == "revestimentos" else ""
        items[code] = {"code": code, "category": category, "name": name, "unit": unit, "cost_eur": cost,
                       "sale_eur": sale, "basis": basis, "per_basis": per_basis, "origin": origin,
                       "source": _source(source) + note, "effective_from": None, "standard": True}
    return items


def library_merged(saved):
    """Library defaults overlaid with the company items. A saved item with
    `deleted` removes a standard item from the calculation."""
    result = library_defaults()
    for code, item in (saved or {}).items():
        if item.get("deleted"):
            result.pop(code, None)
            continue
        base = result.get(code, {"standard": False})
        result[code] = {**base, **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in item.items()},
                        "standard": base.get("standard", False)}
    return result


HEADERS = {
    "categoria": "category", "category": "category", "código": "code", "codigo": "code", "code": "code",
    "designação": "name", "designacao": "name", "nome": "name", "name": "name", "unidade": "unit", "unit": "unit",
    "custo": "cost_eur", "custo (€)": "cost_eur", "preço de compra": "cost_eur", "cost": "cost_eur",
    "venda": "sale_eur", "venda (€)": "sale_eur", "preço de venda": "sale_eur", "sale": "sale_eur",
    "base": "basis", "base de cálculo": "basis", "consumo por base": "per_basis", "qtd por base": "per_basis",
    "por base": "per_basis", "fonte": "source", "origem": "source", "em vigor desde": "effective_from",
}
_CATEGORY_NAMES = {**{k: k for k in CATEGORIES}, **{v[0].lower(): k for k, v in CATEGORIES.items()}}
_BASIS_NAMES = {**{k: k for k in BASES}, **{v.lower(): k for k, v in BASES.items()}}


def _number(text):
    text = str(text or "").strip().replace("€", "").replace(" ", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    else:
        text = text.replace(",", ".")
    return Decimal(text)


def rows_to_items(rows):
    """Turn a table (first row = headers) into validated library items and row errors.

    Accepts the headers of the template (Categoria, Código, Designação, Unidade,
    Custo, Venda, Base, Consumo por base, Fonte) in Portuguese or English.
    """
    rows = [[str(c or "").strip() for c in row] for row in rows if any(str(c or "").strip() for c in row)]
    if len(rows) < 2:
        raise ValueError("A tabela precisa de uma linha de cabeçalho e pelo menos um preço.")
    columns = [HEADERS.get(h.lower()) for h in rows[0]]
    if not {"code", "name", "cost_eur"} <= set(columns):
        raise ValueError("Cabeçalhos obrigatórios: Código, Designação e Custo.")
    items, errors = [], []
    for number, row in enumerate(rows[1:], start=2):
        raw = {col: row[i] for i, col in enumerate(columns) if col and i < len(row) and row[i] != ""}
        try:
            raw["category"] = _CATEGORY_NAMES.get(raw.get("category", "materia_prima").lower(), raw.get("category"))
            raw["basis"] = _BASIS_NAMES.get(raw.get("basis", "projeto").lower(), raw.get("basis"))
            for key in ("cost_eur", "sale_eur", "per_basis"):
                if key in raw:
                    raw[key] = _number(raw[key])
            raw.setdefault("unit", "un")
            raw["origin"] = "empresa"
            items.append(LibraryItem.model_validate(raw).model_dump(mode="json"))
        except Exception as exc:  # noqa: BLE001 - reported to the user row by row
            errors.append({"row": number, "error": str(exc).splitlines()[0][:200]})
    return items, errors


def read_table_file(data: bytes, filename: str):
    """Rows from an Excel, CSV or PDF price list."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        from io import BytesIO
        from openpyxl import load_workbook

        sheet = load_workbook(BytesIO(data), read_only=True, data_only=True).worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)][:2000]
    if name.endswith((".csv", ".tsv", ".txt")):
        import csv
        from io import StringIO

        text = data.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=";,\t")
        return list(csv.reader(StringIO(text), dialect))[:2000]
    if name.endswith(".pdf"):
        import fitz

        rows = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in list(doc)[:20]:
                for table in page.find_tables().tables:
                    rows.extend(table.extract())
        return rows[:2000]
    raise ValueError("Formatos aceites: .xlsx, .csv e .pdf com tabela.")


def parse_eurostat(payload):
    """Latest value and period from a Eurostat JSON-stat response with one series."""
    index = payload["dimension"]["time"]["category"]["index"]
    values = payload.get("value", {})
    for period, position in sorted(index.items(), key=lambda kv: kv[1], reverse=True):
        value = values.get(str(position))
        if value is not None:
            return period, Decimal(str(value))
    raise ValueError("O Eurostat não devolveu nenhum valor.")


ELECTRICITY_URL = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_pc_205"
                   "?geo={geo}&nrg_cons={band}&tax=X_TAX&currency=EUR&unit=KWH&lastTimePeriod=4&format=JSON")


class Wall(BaseModel):
    thickness_mm: Annotated[Decimal, Field(gt=0, le=500)]
    layers: Annotated[int, Field(ge=3, le=9)]
    length_m: Annotated[Decimal, Field(gt=0, le=10_000)]


class Panel(BaseModel):
    """CLT element given by its area: slab, roof, lintel or panel over an opening."""
    kind: Literal["laje", "cobertura", "lintel", "parede"]
    label: str = Field(default="", max_length=120)
    thickness_mm: Annotated[Decimal, Field(gt=0, le=500)]
    layers: Annotated[int, Field(ge=3, le=13)]
    area_m2: Annotated[Decimal, Field(gt=0, le=100_000)]


class Room(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    tipo: Literal["sala", "quarto", "cozinha", "casa_de_banho", "lavandaria", "corredor", "escritorio", "arrumos", "exterior"]
    area_m2: Annotated[Decimal, Field(gt=0, le=10_000)]
    perimetro_m: Value = Decimal(0)
    comprimento_m: Value = Decimal(0)
    aparelhos: list[Literal["lavatorio", "bide", "banheira", "chuveiro", "autoclismo", "lava_loica", "maquina_lavar_loica",
                            "maquina_lavar_roupa", "tanque", "torneira_exterior"]] = Field(default_factory=list, max_length=30)
    rect_m: list[float] | None = Field(default=None, min_length=4, max_length=4)


class Window(BaseModel):
    largura_m: Annotated[Decimal, Field(gt=0, le=100)]
    sobre: Literal["lintel", "viga"] | None = None
    tipo: Literal["janela", "vao_envidracado"] = "janela"


class Segment(BaseModel):
    """One measured wall run, kept for traceability (the estimate uses the walls by thickness)."""
    ref: str = Field(min_length=1, max_length=40)
    thickness_mm: Annotated[Decimal, Field(gt=0, le=500)]
    length_m: Annotated[Decimal, Field(gt=0, le=1_000)]
    # Plan rectangle of the run in metres [x0, y0, x1, y1], read on the drawing; it draws the fabrication annex.
    rect_m: list[Annotated[float, Field(ge=-100_000, le=100_000, allow_inf_nan=False)]] | None = Field(
        default=None, min_length=4, max_length=4)


class Lintel(BaseModel):
    """CLT lintel drawn over an opening between two runs (plan rectangle in metres, door head height)."""
    ref: str = Field(min_length=1, max_length=40)
    rect_m: list[Annotated[float, Field(ge=-100_000, le=100_000, allow_inf_nan=False)]] = Field(min_length=4, max_length=4)
    head_m: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)]
    thickness_mm: Annotated[float, Field(gt=0, le=500, allow_inf_nan=False)] | None = None


class FloorInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    # Empty when the plan marks no height: the company standard is used (see standard_heights).
    height_m: Annotated[Decimal, Field(gt=0, le=20)] | None = None
    walls: list[Wall] = Field(default_factory=list, max_length=500)
    panels: list[Panel] = Field(default_factory=list, max_length=500)
    board_layers_m2: Value = Decimal(0)
    paint_m2: Value = Decimal(0)
    ceiling_m2: Value = Decimal(0)
    slab_buildup_m2: Value = Decimal(0)
    roof_buildup_m2: Value = Decimal(0)
    facade_m2: Value = Decimal(0)
    steel_beam_m: Value = Decimal(0)
    rooms: list[Room] = Field(default_factory=list, max_length=200)
    windows: list[Window] = Field(default_factory=list, max_length=200)
    interior_doors: Annotated[int, Field(ge=0, le=500)] = 0
    ceiling_height_m: Value | None = None
    riser_m: list[float] | None = Field(default=None, min_length=2, max_length=2)
    segments: list[Segment] = Field(default_factory=list, max_length=2000)
    lintels: list[Lintel] = Field(default_factory=list, max_length=500)

    @field_validator("height_m", mode="before")
    @classmethod
    def blank_height(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def has_clt(self):
        if not self.walls and not self.panels:
            raise ValueError("Cada piso precisa de paredes ou de painéis CLT.")
        return self


class EstimateInput(BaseModel):
    floors: list[FloorInput] = Field(min_length=1, max_length=20)
    start: date | None = None
    start_mode: Literal["compra", "fabrico"] = "compra"
    # pt: Portuguese VAT (CIVA art. 18); ua: Ukrainian ПДВ (Tax Code art. 193.1); ua_export: export from Ukraine, 0 % (art. 195.1.1)
    vat_regime: Literal["pt", "ua", "ua_export"] = "pt"

    @model_validator(mode="after")
    def unique(self):
        if len({f.name for f in self.floors}) != len(self.floors):
            raise ValueError("Cada piso deve ter um nome único.")
        return self


def _ceil(numerator, denominator):
    if not denominator:
        return Decimal(0)
    return (Decimal(numerator) / denominator).to_integral_value(rounding=ROUND_CEILING)


def _q(value):
    return float(Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP))


STAGE_ORDER = ("compra", "producao", "transporte", "montagem", "revestimentos", "acabamentos", "indiretos")


def standard_heights(body: EstimateInput, parameters):
    """Floors without a height get the company standard: the first floor (RDC) the ground value, the others the upper
    value (parameters standard_height_ground_m / standard_height_upper_m, editable). Returns (body, notes)."""
    if all(fl.height_m is not None for fl in body.floors):
        return body, []
    value = lambda key: Decimal(str(parameters.get(key, {}).get("value", CATALOGUE[key][3])))
    floors, notes = [], []
    for i, fl in enumerate(body.floors):
        if fl.height_m is None:
            h = value("standard_height_ground_m" if i == 0 else "standard_height_upper_m")
            floors.append(fl.model_copy(update={"height_m": h}))
            notes.append(f"{fl.name}: altura não marcada na planta, usada a altura standard de {h} m (editável).")
        else:
            floors.append(fl)
    return body.model_copy(update={"floors": floors}), notes


def fitout_floors(body: EstimateInput):
    """The floors as the fit-out engine reads them (rooms without the exterior ones)."""
    return [{"name": fl.name, "height_m": fl.height_m, "ceiling_height_m": fl.ceiling_height_m, "riser_m": fl.riser_m,
             "interior_doors": fl.interior_doors, "windows": [w.model_dump() for w in fl.windows],
             "rooms": [{**r.model_dump(), "area_m2": float(r.area_m2), "perimetro_m": float(r.perimetro_m),
                        "comprimento_m": float(r.comprimento_m)} for r in fl.rooms if r.tipo != "exterior"]}
            for fl in body.floors]


def estimate(body: EstimateInput, parameters, library):
    p = {key: Decimal(str(item["value"])) for key, item in parameters.items()}
    body, height_notes = standard_heights(body, parameters)
    items = [LibraryItem.model_validate({k: v for k, v in item.items() if k != "standard"}) for item in library.values()]
    floors = []
    for floor in body.floors:
        elements = [(w.length_m * floor.height_m, w.thickness_mm, w.layers) for w in floor.walls]
        elements += [(e.area_m2, e.thickness_mm, e.layers) for e in floor.panels]
        area = sum((a for a, _, _ in elements), Decimal(0))
        volume = sum((a * t / 1000 for a, t, _ in elements), Decimal(0))
        glue_area = sum((a * (n - 1) for a, _, n in elements), Decimal(0))
        floors.append({
            "floor": floor, "m3_clt": volume, "m2_montagem": area, "kg_cola": glue_area * p["adhesive_kg_m2"],
            "m3_madeira": volume * p["timber_input_m3_per_m3"], "h_fabrico": volume * p["fabrication_h_m3"],
            "h_montagem": area * p["assembly_h_m2"], "kwh": volume * p["electricity_kwh_m3"],
            "m2_placa": floor.board_layers_m2, "m2_pintura": floor.paint_m2, "m2_teto": floor.ceiling_m2,
            "m2_laje": floor.slab_buildup_m2, "m2_cobertura": floor.roof_buildup_m2, "m2_fachada": floor.facade_m2,
            "m_viga_aco": floor.steel_beam_m,
            "parede_m2": sum((w.length_m * floor.height_m for w in floor.walls), Decimal(0)),
            "paineis_m2": {kind: sum((e.area_m2 for e in floor.panels if e.kind == kind), Decimal(0))
                           for kind in ("laje", "cobertura", "lintel", "parede")},
        })
    fit, fit_notes = clt_fitout.quantities(fitout_floors(body))
    for f, extra in zip(floors, fit):
        for basis in BASES:
            f.setdefault(basis, extra.get(basis, Decimal(0)))
    volume_total = sum((f["m3_clt"] for f in floors), Decimal(0))
    timber_total = sum((f["m3_madeira"] for f in floors), Decimal(0))
    assembly_hours = sum((f["h_montagem"] for f in floors), Decimal(0))
    trips = _ceil(volume_total, p["truck_m3"])
    timber_trips = _ceil(timber_total, p["materia_prima_truck_m3"])
    crew_day = p["assembly_crew"] * p["work_hours_day"]
    days = {"compra": p["purchase_days"], "fabrico": _ceil(volume_total, p["factory_m3_day"]),
            "transporte": p["transport_days"], "montagem": _ceil(assembly_hours, crew_day),
            "acabamentos": p["fitout_days"] if any(f["floor"].rooms or f["floor"].windows for f in floors) else Decimal(0)}
    project = {"km_materia_prima": timber_trips * p["materia_prima_km"], "km_obra": trips * p["obra_km"],
               "viagem": trips, "dia_fabrico": days["fabrico"], "dia_montagem": days["montagem"], "projeto": Decimal(1)}

    lines, rows = [], []
    for item in sorted(items, key=lambda i: i.basis == "pct_custo"):
        stage = CATEGORIES[item.category][1]
        per_floor = []
        for index, f in enumerate(floors):
            share = f["m3_clt"] / volume_total if volume_total else Decimal(1) / len(floors)
            if item.basis == "pct_custo":
                base = sum((l["per_floor"][index] * l["item"].cost_eur for l in lines
                            if l["stage"] != "venda" and l["item"].basis != "pct_custo"), Decimal(0)) / 100
            elif item.basis in PROJECT_BASES:
                base = project[item.basis] * share
            else:
                base = f[item.basis]
            per_floor.append(base * item.per_basis)
        qty = sum(per_floor, Decimal(0))
        lines.append({"item": item, "stage": stage, "per_floor": per_floor, "qty": qty})
    for index, f in enumerate(floors):
        costs = {stage: Decimal(0) for stage in STAGE_ORDER}
        revenue = Decimal(0)
        for line in lines:
            qty = line["per_floor"][index]
            if line["stage"] != "venda":
                costs[line["stage"]] += qty * line["item"].cost_eur
            if line["item"].sale_eur is not None:
                revenue += qty * line["item"].sale_eur
        cost = sum(costs.values(), Decimal(0))
        margin = revenue - cost
        rows.append({
            "piso": f["floor"].name, "comprimento_m": _q(sum((w.length_m for w in f["floor"].walls), Decimal(0))),
            "altura_m": float(f["floor"].height_m), "montagem_m2": _q(f["m2_montagem"]), "fabrico_m3": _q(f["m3_clt"]),
            "madeira_comprada_m3": _q(f["m3_madeira"]), "adesivo_kg": _q(f["kg_cola"]), "eletricidade_kwh": _q(f["kwh"]),
            "horas_fabrico": _q(f["h_fabrico"]), "horas_montagem": _q(f["h_montagem"]),
            "placa_m2": _q(f["m2_placa"]), "pintura_m2": _q(f["m2_pintura"]), "teto_m2": _q(f["m2_teto"]),
            "parede_m2": _q(f["parede_m2"]), "paineis_m2": {k: _q(v) for k, v in f["paineis_m2"].items()},
            "laje_betao_m2": _q(f["m2_laje"]), "cobertura_m2": _q(f["m2_cobertura"]), "fachada_m2": _q(f["m2_fachada"]),
            "viga_aco_m": _q(f["m_viga_aco"]),
            "custos_eur": {k: _q(v) for k, v in costs.items()}, "custo_total_eur": _q(cost),
            "receita_eur": _q(revenue), "margem_eur": _q(margin),
            "margem_percent": _q(margin * 100 / revenue) if revenue else None,
            "_raw": (cost, revenue, margin, costs),
        })
    vat, vat_source = {"pt": (p["iva_percent"], parameters["iva_percent"]["source"]),
                       "ua": (p.get("iva_ua_percent", Decimal(20)), (parameters.get("iva_ua_percent") or {}).get("source") or _source("pku_193")),
                       "ua_export": (Decimal(0), _source("pku_195"))}[body.vat_regime]
    total_cost = sum((r["_raw"][0] for r in rows), Decimal(0))
    total_revenue = sum((r["_raw"][1] for r in rows), Decimal(0))
    total_margin = total_revenue - total_cost
    stages_total = {s: _q(sum((r["_raw"][3][s] for r in rows), Decimal(0))) for s in STAGE_ORDER}
    for r in rows:
        r.pop("_raw")
    totals = {
        "montagem_m2": _q(sum((f["m2_montagem"] for f in floors), Decimal(0))), "fabrico_m3": _q(volume_total),
        "horas_fabrico": _q(sum((f["h_fabrico"] for f in floors), Decimal(0))), "horas_montagem": _q(assembly_hours),
        "custos_eur": stages_total, "custo_total_eur": _q(total_cost), "receita_eur": _q(total_revenue),
        "margem_eur": _q(total_margin), "margem_percent": _q(total_margin * 100 / total_revenue) if total_revenue else None,
        "viagens": int(trips), "viagens_materia_prima": int(timber_trips),
        "iva_percent": float(vat), "iva_eur": _q(total_revenue * vat / 100),
        "receita_com_iva_eur": _q(total_revenue * (1 + vat / 100)), "iva_regime": body.vat_regime, "iva_fonte": vat_source,
    }
    detail = [{"codigo": l["item"].code, "designacao": l["item"].name, "categoria": l["item"].category, "fase": l["stage"],
               "base": l["item"].basis, "quantidade": _q(l["qty"]), "unidade": l["item"].unit,
               "custo_unitario_eur": float(l["item"].cost_eur),
               "custo_eur": _q(l["qty"] * l["item"].cost_eur) if l["stage"] != "venda" else 0.0,
               "venda_eur": _q(l["qty"] * l["item"].sale_eur) if l["item"].sale_eur is not None else None,
               "origem": l["item"].origin} for l in lines]
    hypotheses = sorted([item["label"] for item in parameters.values() if item["origin"] == "hipotese"]
                        + [f"{i.code} · {i.name}" for i in items if i.origin == "hipotese"])
    return {"pisos": rows, "total": totals, "notas_quantidades": height_notes + fit_notes, "linhas": detail, "plano": planning(days, body.start, body.start_mode),
            "hipoteses_por_confirmar": hypotheses, "status": "estimativa" if hypotheses else "valores_da_empresa"}


def planning(days, start=None, mode="compra"):
    """Sequential plan: purchase, fabrication, delivery, assembly. Calendar days."""
    start = start or date.today()
    stages = [("compra", "Compra e receção da matéria-prima"), ("fabrico", "Fabrico dos painéis"),
              ("transporte", "Transporte e entrega na obra"), ("montagem", "Montagem em obra"),
              ("acabamentos", "Instalações e acabamentos até à entrega da chave")]
    stages = [s for s in stages if s[0] != "acabamentos" or days.get("acabamentos")]
    if mode == "fabrico":
        stages = stages[1:]
    plan, cursor = [], start
    for key, label in stages:
        length = int(days[key])
        end = cursor + timedelta(days=max(length, 1) - 1)
        plan.append({"fase": key, "descricao": label, "dias": length, "inicio": cursor.isoformat(), "fim": end.isoformat()})
        cursor = end + timedelta(days=1)
    return {"inicio": start.isoformat(), "fim": plan[-1]["fim"], "dias": sum(s["dias"] for s in plan), "fases": plan}


LOT_UNITS = {"m³": "m3", "m3": "m3", "m²": "m2", "m2": "m2", "m": "m", "kg": "kg", "h": "h", "un": "un",
             "viagem": "viagem", "lote": "lote", "l": "L", "kwh": "kWh", "km": "km", "dia": "dia"}


def lot_from_estimate(name, result):
    """A cost-tracking lot whose baseline is the estimate, one line per priced item."""
    lines = []
    for line in result["linhas"]:
        if line["fase"] == "venda" or not line["quantidade"] or not line["custo_unitario_eur"]:
            continue
        unit = LOT_UNITS.get(line["unidade"].lower(), "un")
        lines.append({"code": line["codigo"], "stage": {"revestimentos": "montagem", "indiretos": "montagem", "acabamentos": "entrega"}.get(line["fase"], line["fase"]),
                      "name": line["designacao"][:120], "unit": unit, "rate_eur": str(line["custo_unitario_eur"]),
                      "baseline_qty": str(line["quantidade"]), "uncommitted_remaining_eur": str(line["custo_eur"]),
                      "source_reference": f"Cálculo automático ConstruPilot · base {line['base']}"})
    return {"name": name[:120], "revenue_eur": str(result["total"]["receita_eur"]),
            "planned_delivery": result["plano"]["fim"], "lines": lines}


def slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").upper()[:40] or "ITEM"
