"""Extractor PT-PT para LEITURA DE PLANTAS (StructuroHouse / Structuro)."""
from __future__ import annotations
from .base import register


class PlantasExtractor:
    app_key = "plantas"
    schema = {
        "type": "object",
        "properties": {
            "tipo_edificio": {"type": "string", "enum": ["moradia", "apartamento", "edificio", "anexo"]},
            "tipologia": {"type": "string"},
            "pisos": {"type": "integer", "minimum": 1, "maximum": 10},
            "pe_direito_m": {"type": "number", "minimum": 2.0, "maximum": 6.0},
            "uso": {"type": "string", "enum": ["habitacao", "servicos", "comercio", "misto"]},
        },
        "required": ["tipo_edificio", "pisos"],
    }
    defaults = {"pe_direito_m": 2.60, "uso": "habitacao"}
    prompt_system = (
        "És um extrator PT-PT para LEITURA DE PLANTAS. Lê a descrição e devolve o schema. "
        "Vocabulário: «moradia unifamiliar»=moradia, «apartamento», «edifício» (multifamiliar), "
        "«anexo», «T1/T2/T3», «dois pisos»=2, «R/C + 1º andar»=2, «pé-direito 2,60». "
        "Se faltar o tipo de edifício ou o nº de pisos, devolve clarification_question. "
        "Se faltar o pé-direito, usa 2,60 m. Uso por defeito: habitação."
    )

    def required_fields(self):
        return list(self.schema["required"])

    def post_process(self, data):
        if "pisos" in data and data["pisos"] is not None:
            data["pisos"] = int(data["pisos"])
            if not (1 <= data["pisos"] <= 10):
                raise ValueError(f"pisos fora do intervalo: {data['pisos']}")
        if "pe_direito_m" in data and data["pe_direito_m"] is not None:
            data["pe_direito_m"] = float(data["pe_direito_m"])
        return data


register(PlantasExtractor())
