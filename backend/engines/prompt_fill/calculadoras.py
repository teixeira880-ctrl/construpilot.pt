"""Extractor PT-PT genérico para CALCULADORAS (betão, tinta, azulejos, pladur…)."""
from __future__ import annotations
from .base import register


class CalculadorasExtractor:
    app_key = "calculadoras"
    schema = {
        "type": "object",
        "properties": {
            "calc_type": {
                "type": "string",
                "enum": ["betao", "armadura", "tinta", "azulejo", "pladur", "isolamento", "carga_laje"],
            },
            "area_m2": {"type": "number", "minimum": 0.1, "maximum": 10000},
            "comprimento_m": {"type": "number", "minimum": 0.1, "maximum": 1000},
            "largura_m": {"type": "number", "minimum": 0.1, "maximum": 1000},
            "espessura_cm": {"type": "number", "minimum": 0.1, "maximum": 100},
            "demaos": {"type": "integer", "minimum": 1, "maximum": 5},
            "classe_betao": {"type": "string"},
        },
        "required": ["calc_type"],
    }
    defaults = {"demaos": 2, "classe_betao": "C25/30"}
    prompt_system = (
        "És um extrator PT-PT para CALCULADORAS rápidas de obras. "
        "Identifica o tipo de cálculo e extrai parâmetros. Mapeamento: "
        "«betão»→betao, «armaduras/aço»→armadura, «tinta/pintura»→tinta, "
        "«azulejo/mosaico»→azulejo, «pladur/gesso cartonado»→pladur, "
        "«isolamento térmico/XPS/EPS/lã mineral»→isolamento, «carga da laje»→carga_laje. "
        "Unidades: m², cm (espessura), demãos (default 2), classe betão (default C25/30). "
        "Se o tipo não for identificável, devolve clarification_question."
    )

    def required_fields(self):
        return list(self.schema["required"])

    def post_process(self, data):
        for k in ("area_m2", "comprimento_m", "largura_m", "espessura_cm"):
            if k in data and data[k] is not None:
                data[k] = float(data[k])
        if "demaos" in data and data["demaos"] is not None:
            data["demaos"] = int(data["demaos"])
        return data


register(CalculadorasExtractor())
