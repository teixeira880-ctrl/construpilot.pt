"""Extractor PT-PT para ESTUDO DE MORADIA (dimensionamento preliminar)."""
from __future__ import annotations
from .base import register


class MoradiaExtractor:
    app_key = "moradia"
    schema = {
        "type": "object",
        "properties": {
            "tipologia": {"type": "string"},
            "area_lote_m2": {"type": "number", "minimum": 50, "maximum": 50000},
            "area_bruta_m2": {"type": "number", "minimum": 30, "maximum": 2000},
            "pisos": {"type": "integer", "minimum": 1, "maximum": 5},
            "pe_direito_m": {"type": "number", "minimum": 2.4, "maximum": 4.0},
            "cave": {"type": "boolean"},
        },
        "required": ["tipologia", "area_bruta_m2"],
    }
    defaults = {"pisos": 2, "pe_direito_m": 2.70, "cave": False}
    prompt_system = (
        "És um extrator PT-PT para ESTUDO DE MORADIA (unifamiliar). "
        "Vocabulário: «T1/T2/T3/T4/T5» é a tipologia. «lote de 400 m²» → area_lote_m2=400. "
        "«área bruta 180 m²» ou «área de construção 180 m²» → area_bruta_m2=180. "
        "«dois pisos»=2, «com cave»→cave=true. Pé-direito por defeito: 2,70 m. "
        "Se faltar tipologia ou área bruta, devolve clarification_question."
    )

    def required_fields(self):
        return list(self.schema["required"])

    def post_process(self, data):
        for k in ("area_lote_m2", "area_bruta_m2", "pe_direito_m"):
            if k in data and data[k] is not None:
                data[k] = float(data[k])
        if "pisos" in data and data["pisos"] is not None:
            data["pisos"] = int(data["pisos"])
        return data


register(MoradiaExtractor())
