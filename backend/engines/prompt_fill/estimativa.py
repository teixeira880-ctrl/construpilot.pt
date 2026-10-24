"""Extractor PT-PT para a ESTIMATIVA DE OBRAS (página /estimation — catálogo engines.catalog; só para contas autenticadas).

Porta da app «devis» de engines/ai_fill.py do .fr: tipo de projeto, área, gama, tipo de edifício, estado, região, cidade e ano.
Os cálculos continuam deterministas no motor de estimativa; aqui só se preenche o formulário.
"""
from __future__ import annotations
from .base import register

PROJECT_TYPES = [
    "construction_maison_neuve", "construction_maison_hors_eau_hors_air", "construction_maison_gros_oeuvre",
    "construction_maison_second_oeuvre", "construction_maison_main_oeuvre", "renovation_complete", "renovation_appartement",
    "salle_de_bain", "cuisine", "peinture", "placo", "isolation", "electricite", "plomberie", "chauffage", "climatisation",
    "carrelage", "parquet", "toiture", "facade", "terrasse", "maconnerie", "fondations", "fenetres", "portes", "extension",
    "renovation_energetique", "piscine_beton", "piscine_coque", "piscine_renovation",
]
REGIONS_PT = ["Lisboa", "Porto", "Algarve (Faro)", "Setúbal", "Braga", "Aveiro", "Coimbra", "Leiria", "Santarém", "Viseu",
              "Évora / Alentejo", "Viana do Castelo", "Vila Real / Bragança", "Castelo Branco / Guarda", "Madeira", "Açores"]


class EstimativaExtractor:
    app_key = "estimativa"
    schema = {
        "type": "object",
        "properties": {
            "project_type": {"type": "string", "enum": PROJECT_TYPES},
            "surface": {"type": "number", "minimum": 1, "maximum": 20000},
            "finish_level": {"type": "string", "enum": ["eco", "standard", "premium", "luxe"]},
            "building_type": {"type": "string", "enum": ["maison", "appartement", "commerce"]},
            "condition": {"type": "string", "enum": ["neuf", "bon", "moyen", "vetuste", "a_renover_totalement"]},
            "region": {"type": "string", "enum": REGIONS_PT},
            "city": {"type": "string"},
            "construction_year": {"type": "integer", "minimum": 1500, "maximum": 2100},
        },
        "required": ["project_type", "surface"],
    }
    defaults = {"finish_level": "standard", "building_type": "maison", "condition": "bon"}
    prompt_system = (
        "És um extrator PT-PT para a ESTIMATIVA DE OBRAS em Portugal. Identifica o TIPO de obra e a área em m². "
        "Mapeamento para project_type: remodelação/renovação completa de moradia=renovation_complete, remodelação de "
        "apartamento=renovation_appartement, casa de banho/WC=salle_de_bain, cozinha=cuisine, pintura=peinture, "
        "pladur/tabiques=placo, isolamento/capoto/ETICS=isolation, eletricidade=electricite, canalização=plomberie, "
        "aquecimento=chauffage, ar condicionado=climatisation, revestimento cerâmico/azulejo/mosaico=carrelage, "
        "soalho/flutuante/pavimento de madeira=parquet, cobertura/telhado=toiture, fachada=facade, terraço=terrasse, "
        "alvenaria=maconnerie, fundações=fondations, janelas/caixilharia=fenetres, portas=portes, ampliação/extensão=extension, "
        "renovação energética=renovation_energetique, piscina em betão=piscine_beton, piscina de poliéster=piscine_coque, "
        "renovação de piscina=piscine_renovation, moradia nova chave na mão=construction_maison_neuve, "
        "só estrutura/tosco=construction_maison_gros_oeuvre, só acabamentos=construction_maison_second_oeuvre. "
        "Gama: económica=eco, média/standard=standard, alta/qualidade=premium, luxo=luxe. Tipo de edifício: moradia/vivenda=maison, "
        "apartamento/T0-T5=appartement, loja/escritório=commerce. Estado: novo=neuf, bom estado=bon, estado médio=moyen, "
        "degradado=vetuste, a renovar totalmente/devoluto=a_renover_totalement. Região: escolhe na lista do schema a partir da "
        "cidade/concelho citado (Matosinhos→Porto, Cascais→Lisboa, Faro/Lagos→Algarve (Faro), Funchal→Madeira). "
        "Nunca inventes a área: se faltar, devolve clarification_question."
    )

    def required_fields(self):
        return list(self.schema["required"])

    def post_process(self, data):
        if data.get("surface") is not None:
            data["surface"] = float(data["surface"])
            if not 1 <= data["surface"] <= 20000:
                raise ValueError(f"área fora do intervalo: {data['surface']}")
        if data.get("project_type") is not None and data["project_type"] not in PROJECT_TYPES:
            raise ValueError(f"tipo de obra desconhecido: {data['project_type']}")
        if data.get("region") is not None and data["region"] not in REGIONS_PT:
            data.pop("region")                       # região fora da lista: a do formulário mantém-se
        if data.get("construction_year") is not None:
            data["construction_year"] = int(data["construction_year"])
        return data


register(EstimativaExtractor())
