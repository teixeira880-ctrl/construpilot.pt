"""Extractor PT-PT para ORÇAMENTOS de obras."""
from __future__ import annotations
from .base import register


class OrcamentosExtractor:
    app_key = "orcamentos"
    schema = {
        "type": "object",
        "properties": {
            "tipo_obra": {
                "type": "string",
                "enum": ["remodelacao_total", "remodelacao_parcial", "construcao_nova", "ampliacao", "manutencao"],
            },
            "tipologia": {"type": "string"},
            "area_m2": {"type": "number", "minimum": 10, "maximum": 5000},
            "gama_acabamentos": {"type": "string", "enum": ["baixa", "media", "alta", "luxo"]},
            "prazo_meses": {"type": "integer", "minimum": 1, "maximum": 36},
            "regiao": {"type": "string"},
        },
        "required": ["tipo_obra", "area_m2"],
    }
    defaults = {"gama_acabamentos": "media", "regiao": "Lisboa"}
    prompt_system = (
        "És um extrator de parâmetros de ORÇAMENTOS de obras em Portugal (IVA 6% reabilitação / 23% normal). "
        "Lê o pedido em português europeu (PT-PT). Vocabulário: «remodelação», «ampliação», «construção nova», "
        "«acabamentos» (baixa/média/alta/luxo), «T1/T2/T3/T4», «m²», «mês/meses», «região». "
        "Converte área em m². «T3 de 120 metros» → tipologia=T3, area_m2=120. "
        "Se faltar o tipo de obra ou a área, devolve clarification_question. "
        "Se faltar gama de acabamentos, usa «media» por defeito. Região: «Lisboa» por defeito."
    )

    def required_fields(self):
        return list(self.schema["required"])

    def post_process(self, data):
        if "area_m2" in data and data["area_m2"] is not None:
            data["area_m2"] = float(data["area_m2"])
            if not (10 <= data["area_m2"] <= 5000):
                raise ValueError(f"area_m2 fora do intervalo: {data['area_m2']}")
        return data


register(OrcamentosExtractor())
