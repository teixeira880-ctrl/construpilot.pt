"""Ferramentas Anthropic tool-use do Reader BET-PT.

Define:
    - `READER_TOOLS` — list[dict] com `name`, `description`, `input_schema`
      no formato do SDK Anthropic.
    - `handle_tool_use(name, input_json, building, pending_questions)` →
      dispatcher Python para cada tool_use emitido pelo modelo.

Regra dura: todas as tools são **report-only**. O modelo não calcula nada;
só reporta o que viu. Dimensões ambíguas devem usar `request_zoom_crop` para
pedir re-leitura em zoom ou `ask_user` para pergunta on-the-fly.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from engines.bet_agent.models.building import (
    BuildingModel,
    ElementSource,
    Floor,
    Opening,
    Roof,
    Room,
    SlabOpening,
    Stair,
    StructuralElement,
    Wall,
)


# ---------------------------------------------------------------------------
# Schema helper
# ---------------------------------------------------------------------------

_SOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "page": {"type": "integer", "minimum": 1,
                 "description": "Nº de página 1-indexed."},
        "bbox": {
            "type": "object",
            "properties": {
                "x1": {"type": "number"},
                "y1": {"type": "number"},
                "x2": {"type": "number"},
                "y2": {"type": "number"},
            },
            "required": ["x1", "y1", "x2", "y2"],
        },
        "extraction_method": {
            "type": "string",
            "enum": ["vision", "vector_text", "user"],
        },
    },
    "required": ["page", "bbox", "extraction_method"],
}

_CONFIDENCE_SCHEMA: dict[str, Any] = {
    "type": "number",
    "minimum": 0.0,
    "maximum": 1.0,
    "description": "Confiança 0..1 na leitura (<0.5 → bloqueante).",
}


def _elem_schema(extra: dict[str, Any]) -> dict[str, Any]:
    """Monta input_schema com os campos obrigatórios partilhados."""
    props: dict[str, Any] = {
        "id": {"type": "string", "description": "ID estável do elemento (ex: 'P-R1-01')."},
        "source": _SOURCE_SCHEMA,
        "confidence": _CONFIDENCE_SCHEMA,
        "user_imposed": {"type": "boolean", "default": False},
    }
    required: list[str] = ["id", "source", "confidence"]
    props.update(extra["properties"])
    required.extend(extra.get("required", []))
    return {"type": "object", "properties": props, "required": required}


READER_TOOLS: list[dict[str, Any]] = [
    {
        "name": "report_floor",
        "description": "Reporta um piso lido na planta (cave/rc/piso/sotao/cobertura).",
        "input_schema": _elem_schema({
            "properties": {
                "kind": {"type": "string", "enum": ["cave", "rc", "piso", "sotao", "cobertura"]},
                "level_m": {"type": "number"},
                "height_clear_m": {"type": "number"},
                "habitable": {"type": "boolean"},
            },
            "required": ["kind", "level_m"],
        }),
    },
    {
        "name": "report_wall",
        "description": "Reporta uma parede lida (comprimento + espessura + tipo).",
        "input_schema": _elem_schema({
            "properties": {
                "floor_id": {"type": "string"},
                "kind": {"type": "string", "enum": ["exterior", "interior", "contencao", "empena"]},
                "length_m": {"type": "number", "minimum": 0.01},
                "thickness_m": {"type": "number", "minimum": 0.01},
                "material_hint": {"type": "string"},
            },
            "required": ["floor_id", "kind", "length_m", "thickness_m"],
        }),
    },
    {
        "name": "report_structural_element",
        "description": "Reporta pilar / viga / laje / sapata / viga_fundacao / parede_cave.",
        "input_schema": _elem_schema({
            "properties": {
                "floor_id": {"type": "string"},
                "kind": {"type": "string",
                         "enum": ["pilar", "viga", "laje", "sapata", "viga_fundacao", "parede_cave"]},
                "width_mm": {"type": "integer"},
                "height_mm": {"type": "integer"},
                "length_m": {"type": "number"},
                "thickness_mm": {"type": "integer"},
                "span_m": {"type": "number"},
            },
            "required": ["floor_id", "kind"],
        }),
    },
    {
        "name": "report_opening",
        "description": "Reporta porta / janela / portão de garagem / varanda numa parede.",
        "input_schema": _elem_schema({
            "properties": {
                "wall_id": {"type": "string"},
                "kind": {"type": "string",
                         "enum": ["porta", "janela", "portao_garagem", "varanda"]},
                "width_m": {"type": "number", "minimum": 0.01},
                "height_m": {"type": "number", "minimum": 0.01},
                "sill_height_m": {"type": "number"},
            },
            "required": ["wall_id", "kind", "width_m", "height_m"],
        }),
    },
    {
        "name": "report_stair",
        "description": "Reporta uma escada (de piso A para piso B) com a abertura disponível.",
        "input_schema": _elem_schema({
            "properties": {
                "floor_from_id": {"type": "string"},
                "floor_to_id": {"type": "string"},
                "opening_length_m": {"type": "number", "minimum": 0.01},
                "opening_width_m": {"type": "number", "minimum": 0.01},
                "riser_count": {"type": "integer"},
                "riser_height_m": {"type": "number"},
                "tread_depth_m": {"type": "number"},
            },
            "required": ["floor_from_id", "floor_to_id", "opening_length_m", "opening_width_m"],
        }),
    },
    {
        "name": "report_roof",
        "description": "Reporta a cobertura (inclinada telha / inclinada chapa / plana).",
        "input_schema": _elem_schema({
            "properties": {
                "kind": {"type": "string",
                         "enum": ["inclinada_telha_ceramica", "inclinada_chapa",
                                  "plana_acessivel", "plana_nao_acessivel"]},
                "slope_pct": {"type": "number"},
                "area_m2": {"type": "number"},
                "overhang_m": {"type": "number"},
            },
            "required": ["kind"],
        }),
    },
    {
        "name": "report_room",
        "description": "Reporta um compartimento (nome, área, altura, janelas).",
        "input_schema": _elem_schema({
            "properties": {
                "floor_id": {"type": "string"},
                "name": {"type": "string"},
                "use_hint": {"type": "string"},
                "area_m2": {"type": "number", "minimum": 0.01},
                "min_clear_height_m": {"type": "number"},
                "has_window": {"type": "boolean"},
            },
            "required": ["floor_id", "name", "area_m2"],
        }),
    },
    {
        "name": "report_slab_opening",
        "description": "Reporta uma abertura na laje (caixa escadas, elevador, patim).",
        "input_schema": _elem_schema({
            "properties": {
                "floor_id": {"type": "string"},
                "length_m": {"type": "number", "minimum": 0.01},
                "width_m": {"type": "number", "minimum": 0.01},
                "purpose": {"type": "string"},
            },
            "required": ["floor_id", "length_m", "width_m", "purpose"],
        }),
    },
    {
        "name": "request_zoom_crop",
        "description": (
            "Pede um crop ampliado de uma zona ambígua para re-leitura. "
            "Usar quando confiança <0.7 e re-leitura total do PNG não resolveu."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1},
                "bbox": {
                    "type": "object",
                    "properties": {
                        "x1": {"type": "number"},
                        "y1": {"type": "number"},
                        "x2": {"type": "number"},
                        "y2": {"type": "number"},
                    },
                    "required": ["x1", "y1", "x2", "y2"],
                },
                "reason": {"type": "string"},
            },
            "required": ["page", "bbox", "reason"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Pergunta bloqueante ao utilizador quando leitura em zoom não resolveu após 3 tentativas "
            "OU detectou contradição com hipótese fixada OU elemento com confiança <0.5. "
            "Fornece sempre uma vinheta/crop (bbox) para o utilizador localizar a dúvida na planta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question_pt": {"type": "string", "description": "Pergunta em PT-PT."},
                "page": {"type": "integer", "minimum": 1},
                "bbox": {
                    "type": "object",
                    "properties": {
                        "x1": {"type": "number"},
                        "y1": {"type": "number"},
                        "x2": {"type": "number"},
                        "y2": {"type": "number"},
                    },
                    "required": ["x1", "y1", "x2", "y2"],
                },
                "severity": {"type": "string", "enum": ["bloqueante", "leve"],
                             "default": "bloqueante"},
            },
            "required": ["question_pt", "page", "bbox"],
        },
    },
    {
        "name": "finish",
        "description": (
            "Chamar quando toda a estrutura foi reportada e não há dúvidas "
            "bloqueantes abertas. Fecha o ciclo do reader."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Nota final curta em PT."},
            },
            "required": ["summary"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatcher Python
# ---------------------------------------------------------------------------

class ToolDispatchResult:
    """Resultado da dispatch de um tool_use. `tool_result_payload` é o texto
    JSON a devolver ao modelo no próximo turno (como `tool_result` block)."""

    __slots__ = ("ok", "tool_result_payload", "zoom_request", "user_question", "finish_signal")

    def __init__(
        self,
        ok: bool,
        tool_result_payload: str,
        zoom_request: dict[str, Any] | None = None,
        user_question: dict[str, Any] | None = None,
        finish_signal: bool = False,
    ) -> None:
        self.ok = ok
        self.tool_result_payload = tool_result_payload
        self.zoom_request = zoom_request
        self.user_question = user_question
        self.finish_signal = finish_signal


def _append_or_err(
    building: BuildingModel,
    list_name: str,
    model_cls,
    raw: dict[str, Any],
) -> ToolDispatchResult:
    try:
        instance = model_cls.model_validate(raw)
    except ValidationError as exc:
        return ToolDispatchResult(
            ok=False,
            tool_result_payload=f'{{"error": "validation_failed", "detail": {exc.json()}}}',
        )
    getattr(building, list_name).append(instance)
    return ToolDispatchResult(ok=True, tool_result_payload='{"status":"ok"}')


_HANDLERS: dict[str, tuple[type, str | None]] = {
    "report_floor": (Floor, "floors"),
    "report_wall": (Wall, "walls"),
    "report_structural_element": (StructuralElement, "structural_elements"),
    "report_opening": (Opening, "openings"),
    "report_stair": (Stair, "stairs"),
    "report_room": (Room, "rooms"),
    "report_slab_opening": (SlabOpening, "slab_openings"),
}


def handle_tool_use(
    name: str,
    raw_input: dict[str, Any],
    building: BuildingModel,
    pending_questions: list[dict[str, Any]],
) -> ToolDispatchResult:
    """Dispatcher central. Devolve `ToolDispatchResult` com o payload a devolver
    ao modelo como `tool_result` content block.
    """
    if name == "report_roof":
        try:
            building.roof = Roof.model_validate(raw_input)
        except ValidationError as exc:
            return ToolDispatchResult(ok=False,
                                      tool_result_payload=f'{{"error":"validation_failed","detail":{exc.json()}}}')
        return ToolDispatchResult(ok=True, tool_result_payload='{"status":"ok"}')

    if name in _HANDLERS:
        cls, attr = _HANDLERS[name]
        return _append_or_err(building, attr, cls, raw_input)

    if name == "request_zoom_crop":
        return ToolDispatchResult(
            ok=True,
            tool_result_payload=(
                '{"status":"zoom_queued",'
                '"note":"crop sera enviado no proximo turno"}'
            ),
            zoom_request=raw_input,
        )

    if name == "ask_user":
        pending_questions.append(raw_input)
        return ToolDispatchResult(
            ok=True,
            tool_result_payload=(
                '{"status":"question_recorded",'
                '"note":"aguarda resposta do utilizador"}'
            ),
            user_question=raw_input,
        )

    if name == "finish":
        return ToolDispatchResult(
            ok=True,
            tool_result_payload='{"status":"finished"}',
            finish_signal=True,
        )

    return ToolDispatchResult(
        ok=False,
        tool_result_payload=f'{{"error":"unknown_tool","name":"{name}"}}',
    )
