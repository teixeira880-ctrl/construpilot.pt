"""Extractor PT-PT para ACRESCENTAR UM ELEMENTO DE FUNDAÇÃO na leitura de planta (página /structuro/lecture-plan — PlanReader).

Porta da app «plan_fondation» de engines/ai_fill.py do .fr. Os tipos seguem os do motor de leitura de plantas.
"""
from __future__ import annotations
from .base import register

TYPES = ["semelle_isolee", "semelle_filante", "longrine", "chainage", "poteau"]


class FundacaoExtractor:
    app_key = "fundacao"
    schema = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": TYPES},
            "repere": {"type": "string"},
            "longueur_m": {"type": "number", "minimum": 0.05, "maximum": 500},
            "largeur_m": {"type": "number", "minimum": 0.05, "maximum": 20},
            "hauteur_m": {"type": "number", "minimum": 0.05, "maximum": 10},
            "nombre": {"type": "integer", "minimum": 1, "maximum": 500},
        },
        "required": ["type"],
    }
    defaults = {"nombre": 1}
    prompt_system = (
        "És um extrator PT-PT para ACRESCENTAR um elemento de fundação lido numa planta. Dimensões em METROS. "
        "Tipo: «sapata isolada»=semelle_isolee, «sapata contínua/corrida»=semelle_filante, «viga de fundação/lintel de "
        "fundação»=longrine, «lintel de travamento/cinta»=chainage, «pilar»=poteau. «80 por 80» ou «80x80 cm» = largeur_m 0.80 e "
        "longueur_m 0.80 (converte cm→m). «altura 40 cm» = hauteur_m 0.40. «3 sapatas» = nombre 3. «referência S1» = repere «S1». "
        "Para uma sapata contínua, «em 12 m» = longueur_m 12. Se o tipo não for identificável, devolve clarification_question. "
        "Nunca inventes dimensões ausentes do pedido."
    )

    def required_fields(self):
        return list(self.schema["required"])

    def post_process(self, data):
        if data.get("type") is not None and data["type"] not in TYPES:
            raise ValueError(f"tipo de elemento desconhecido: {data['type']}")
        for k in ("longueur_m", "largeur_m", "hauteur_m"):
            if data.get(k) is not None:
                data[k] = float(data[k])
                if data[k] <= 0:
                    raise ValueError(f"{k} inválido: {data[k]}")
        if data.get("nombre") is not None:
            data["nombre"] = max(1, int(data["nombre"]))
        return data


register(FundacaoExtractor())
