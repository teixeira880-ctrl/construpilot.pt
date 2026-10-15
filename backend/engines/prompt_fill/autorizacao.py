"""Extractor PT-PT para AUTORIZAÇÃO DE OBRAS (RJUE)."""
from __future__ import annotations
from .base import register


class AutorizacaoExtractor:
    app_key = "autorizacao"
    schema = {
        "type": "object",
        "properties": {
            "tipo_obra": {
                "type": "string",
                "enum": ["anexo", "muro", "interiores", "piscina", "ampliacao", "moradia_nova"],
            },
            "area_implantacao_m2": {"type": "number", "minimum": 0, "maximum": 5000},
            "area_construcao_total_m2": {"type": "number", "minimum": 0, "maximum": 10000},
            "altura_m": {"type": "number", "minimum": 0, "maximum": 50},
            "confina_via_publica": {"type": "boolean"},
            "zona_protegida": {"type": "boolean"},
            "concelho": {"type": "string"},
        },
        "required": ["tipo_obra"],
    }
    defaults = {"confina_via_publica": False, "zona_protegida": False}
    prompt_system = (
        "És um extrator PT-PT para AUTORIZAÇÃO DE OBRAS (DL 555/99 — RJUE). "
        "Lê a descrição e devolve o schema. Vocabulário: «anexo/arrumos/telheiro»=anexo, "
        "«muro/vedação»=muro, «só interiores»=interiores, «piscina», "
        "«ampliação»=ampliacao, «moradia nova/construção nova»=moradia_nova. "
        "Converte m, cm→m, m²→m². «8 m²» → area_implantacao_m2=8. "
        "Se o tipo de obra estiver ausente, devolve clarification_question. "
        "Confina com via pública e zona protegida: por defeito False se não mencionado."
    )

    def required_fields(self):
        return list(self.schema["required"])

    def post_process(self, data):
        for k in ("area_implantacao_m2", "area_construcao_total_m2", "altura_m"):
            if k in data and data[k] is not None:
                data[k] = float(data[k])
        return data


register(AutorizacaoExtractor())
