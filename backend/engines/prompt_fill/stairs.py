"""Extractor PT-PT para a app de ESCADAS.

Mapeia o prompt livre do utilizador para o schema da calculadora
`routes/stairs.py` + `engines/stair_engine/calculator.py`.

Normas referenciadas:
- RGEU (DL 38 382/51 e revisões): largura mínima em habitação ≈ 0,80 m
  (usamos 0,90 m por segurança quando o utilizador omite).
- Blondel: 2h + g ≈ 600–660 mm; espelho h ∈ [150, 180] mm; cobertor g ≈ 280 mm.
- DL 163/2006 (acessibilidade) só aplicável a utilização pública.

A IA pode preencher o que o utilizador DISSE e pode usar valores por defeito
normativos. Nunca inventa altura a vencer ou tipo.
"""
from __future__ import annotations

from .base import register


class StairsExtractor:
    app_key = "escadas"

    schema = {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "enum": [
                    "reta",
                    "em_L",
                    "em_U",
                    "com_patamar",
                    "balanceada",
                    "helicoidal",
                ],
            },
            "numero_lancos": {"type": "integer", "minimum": 1, "maximum": 4},
            "sentido_rotacao": {
                "type": "string",
                "enum": ["dextrogiro", "levogiro", "nao_aplicavel"],
            },
            "altura_a_vencer_mm": {
                "type": "number",
                "minimum": 1000,
                "maximum": 6000,
            },
            "largura_mm": {"type": "number", "minimum": 600, "maximum": 2000},
            "abertura_laje_comprimento_mm": {"type": "number"},
            "abertura_laje_largura_mm": {"type": "number"},
            "espelho_alvo_mm": {"type": "number"},
            "cobertor_alvo_mm": {"type": "number"},
            "balanceamento": {"type": "boolean"},
            "material": {
                "type": "string",
                "enum": ["betao_armado", "metalica", "madeira", "mista"],
            },
        },
        "required": ["tipo", "altura_a_vencer_mm", "largura_mm"],
    }

    defaults = {
        "largura_mm": 900,
        "espelho_alvo_mm": 175,
        "cobertor_alvo_mm": 280,
        "material": "betao_armado",
        "sentido_rotacao": "nao_aplicavel",
        "balanceamento": False,
        "numero_lancos": 1,
    }

    prompt_system = (
        "És um extrator técnico de parâmetros de ESCADAS em edifícios de habitação em Portugal, "
        "estrito e sem invenção. A tua única tarefa é ler o pedido em português europeu e devolver "
        "os parâmetros no schema fornecido. "
        "Vocabulário PT: «degraus»/«degrau», «espelho» (altura do degrau), «cobertor»/«pisada» "
        "(profundidade), «patamar», «vão da escada», «lanço». "
        "«Meio quarto» ou «meia volta» = 180° = em_U. «Quarto de volta» = 90° = em_L. "
        "«Dois lanços em meio quarto» = em_U com patamar intermédio. «Caracol» = helicoidal. "
        "Unidades: aceita m, cm, mm; converte sempre para mm. 2,70 m = 2700 mm. 90 cm = 900 mm. "
        "Se o utilizador NÃO disser o espelho/cobertor, usa os VALORES POR DEFEITO normativos "
        "(RGEU/Blondel) — eles vêm no payload. "
        "Se o utilizador NÃO disser a largura, usa 900 mm (RGEU, por segurança). "
        "Se faltar a ALTURA A VENCER ou o TIPO e não houver pistas suficientes, devolve "
        "clarification_question com UMA pergunta curta. Nunca inventes alturas ou tipos. "
        "Se o prompt começar por «mais», «menos», «aumenta», «diminui», «inverte», aplica-o aos "
        "valores presentes em contexto_atual, mantendo os restantes. "
        "Em notas, menciona a norma usada e marca os valores por defeito como «por defeito "
        "(RGEU/Blondel)»."
    )

    def required_fields(self) -> list[str]:
        return list(self.schema["required"])

    def post_process(self, data: dict) -> dict:
        # tipagem numérica
        for k in (
            "altura_a_vencer_mm",
            "largura_mm",
            "espelho_alvo_mm",
            "cobertor_alvo_mm",
            "abertura_laje_comprimento_mm",
            "abertura_laje_largura_mm",
        ):
            if k in data and data[k] is not None:
                data[k] = float(data[k])

        # validações de intervalo (defensivas: a IA pode escorregar)
        altura = data.get("altura_a_vencer_mm")
        if altura is not None and (altura < 1000 or altura > 6000):
            raise ValueError(
                f"Altura a vencer fora do intervalo (1000–6000 mm): {altura:.0f} mm."
            )
        largura = data.get("largura_mm")
        if largura is not None and (largura < 600 or largura > 2000):
            raise ValueError(
                f"Largura fora do intervalo (600–2000 mm): {largura:.0f} mm."
            )
        tipo = data.get("tipo")
        if tipo is not None and tipo not in self.schema["properties"]["tipo"]["enum"]:
            raise ValueError(f"Tipo de escada desconhecido: {tipo!r}.")
        return data


register(StairsExtractor())
