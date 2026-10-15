"""Extractor PT-PT para MEDIÇÕES (áreas, perímetros, volumes de uma divisão)."""
from __future__ import annotations
from .base import register


class MedicoesExtractor:
    app_key = "medicoes"
    schema = {
        "type": "object",
        "properties": {
            "divisao": {"type": "string"},
            "comprimento_m": {"type": "number", "minimum": 0.1, "maximum": 100},
            "largura_m": {"type": "number", "minimum": 0.1, "maximum": 100},
            "pe_direito_m": {"type": "number", "minimum": 1.5, "maximum": 10},
            "material_pavimento": {"type": "string"},
            "material_paredes": {"type": "string"},
        },
        "required": ["comprimento_m", "largura_m"],
    }
    defaults = {"pe_direito_m": 2.60}
    prompt_system = (
        "És um extrator de parâmetros de MEDIÇÕES em obras de habitação em Portugal. "
        "Lê o pedido em português europeu (PT-PT) e devolve o schema. "
        "Unidades: aceita m, cm; converte para metros. 5,20 m = 5.20. "
        "Vocabulário PT: «sala», «quarto», «cozinha», «casa de banho», «cave», «sótão», "
        "«pavimento», «paredes», «teto», «pé-direito», «divisão». "
        "Se faltar comprimento ou largura, devolve clarification_question. "
        "Se faltar o pé-direito, usa o valor por defeito (2,60 m)."
    )

    def required_fields(self):
        return list(self.schema["required"])

    def post_process(self, data):
        for k in ("comprimento_m", "largura_m", "pe_direito_m"):
            if k in data and data[k] is not None:
                data[k] = float(data[k])
                if data[k] <= 0:
                    raise ValueError(f"{k} inválido: {data[k]}")
        return data


register(MedicoesExtractor())
