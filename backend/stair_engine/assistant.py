"""Assistant IA STAIRPILOT — Claude Sonnet 4.5 via emergentintegrations.

Le LLM NE calcule JAMAIS lui-même : il déclenche des tool calls vers le moteur
déterministe (`compute_optimize`, `compute_straight`, `compute_concrete_analysis`)
et rédige une réponse courte en français à partir des résultats.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

from .concrete import ConcreteAnalysisInput, compute_concrete_analysis
from .forced_solver import ForceSolutionInput, compute_forced_solution
from .models import StairInput, StairResult
from .optimizer import OptimizeInput, compute_optimize
from .straight import compute_straight


MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = (
    "És o assistente STAIRPILOT, especialista em cálculo de escadas de betão (Portugal: RGEU, DL 163/2006 para acessibilidades, EN 1992 / Eurocódigo 2 com Anexo Nacional português). NUNCA calculas uma escada por ti próprio. Chamas as funções do motor fornecidas via tool-use para obter qualquer cota (altura do degrau (espelho), cobertor, inclinação, Blondel, desenvolvimento, altura livre, armaduras, betão). Se faltarem parâmetros essenciais (altura entre pisos, desenvolvimento disponível, abertura na laje), pede-os com precisão antes de qualquer chamada de ferramenta. Respostas curtas e profissionais em português europeu, sem nunca inventar cotas. Após uma chamada de ferramenta, resume os resultados em 3-6 linhas no máximo, destaca a solução recomendada e assinala os alertas vermelhos/laranja. Não inventes códigos de alerta: retoma apenas os fornecidos pela ferramenta.\n\nREGRA IMPORTANTE — PROPOR SEMPRE UMA SOLUÇÃO:\n1. Se `optimize_stair` NÃO devolver NENHUMA solução com `is_buildable=true`,    DEVES chamar imediatamente `force_stair_solution` com as mesmas restrições.\n2. Se o utilizador pedir EXPLICITAMENTE um tipo preciso (reta, em L / um quarto de volta, em U / meia volta, helicoidal)    e esse tipo não aparecer nas `solutions` de `optimize_stair` (está em `excluded` ou ausente),    chama também `force_stair_solution` para não frustrar o utilizador com um tipo imposto que não quer.\n3. Quando utilizas `force_stair_solution`, explica claramente:    (a) que a solução é construível mas FORA DAS REGRAS DE BOA PRÁTICA / RGEU,    (b) que compromissos foram aceites (inclinação, cobertor, altura livre exatos em mm/°),    (c) o uso aceitável (acesso técnico, cave, escada de sótão — nunca habitação principal),    (d) 1 ou 2 alternativas conformes possíveis (aumentar o desenvolvimento, acrescentar um patamar, mudar de tipo)."
)


# ---------------------------------------------------------------------------
# Outils exposés au LLM (schéma OpenAI function-calling, portable via LiteLLM)
# ---------------------------------------------------------------------------
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "optimize_stair",
            "description": (
                "Propõe as melhores configurações de escada de betão (reta, um quarto de volta, meia volta, helicoidal) a partir das restrições do espaço. Devolve até 5 soluções ordenadas por pontuação global."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "floor_height_mm": {"type": "number", "description": "Altura de pavimento acabado a pavimento acabado em mm"},
                    "available_length_mm": {"type": "number", "description": "Desenvolvimento disponível em mm"},
                    "available_width_mm": {"type": "number", "description": "Largura disponível em mm"},
                    "stair_width_mm": {"type": "number", "description": "Largura pretendida do lanço em mm", "default": 900},
                    "stairwell_length_mm": {"type": "number", "description": "Comprimento da abertura na laje em mm (opcional)"},
                    "stairwell_width_mm": {"type": "number", "description": "Largura da abertura na laje em mm (opcional)"},
                    "ceiling_height_mm": {"type": "number", "description": "Pé-direito (para altura livre)"},
                    "slab_thickness_mm": {"type": "number", "description": "Espessura da laje superior em mm", "default": 200},
                    "max_solutions": {"type": "integer", "description": "N.º máx. de soluções", "default": 3},
                },
                "required": ["floor_height_mm", "available_length_mm", "available_width_mm"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_straight",
            "description": "Calcula uma escada reta de betão precisa (números exatos, alertas regulamentares).",
            "parameters": {
                "type": "object",
                "properties": {
                    "floor_height_mm": {"type": "number"},
                    "available_length_mm": {"type": "number"},
                    "available_width_mm": {"type": "number"},
                    "stair_width_mm": {"type": "number", "default": 900},
                    "stairwell_length_mm": {"type": "number"},
                    "stairwell_width_mm": {"type": "number"},
                    "ceiling_height_mm": {"type": "number"},
                    "slab_thickness_mm": {"type": "number", "default": 200},
                },
                "required": ["floor_height_mm", "available_length_mm", "available_width_mm"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_concrete",
            "description": (
                "Pré-dimensionamento de betão armado (laje da escada, armaduras indicativas, medição) a partir de um resultado de escada já calculado. Utiliza apenas se o utilizador pedir explicitamente o betão armado, a medição ou as armaduras."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stair_result": {"type": "object", "description": "Resultado StairResult devolvido por uma ferramenta anterior"},
                    "stair_type": {"type": "string", "enum": ["straight", "quarter_turn_bottom", "quarter_turn_top", "half_turn", "helicoidal"], "default": "straight"},
                    "concrete_class": {"type": "string", "enum": ["C20/25", "C25/30", "C30/37"], "default": "C25/30"},
                    "steel_grade": {"type": "string", "enum": ["B500A", "B500B"], "default": "B500B"},
                    "exposure_class": {"type": "string", "enum": ["XC1", "XC2", "XC3", "XC4"], "default": "XC1"},
                    "live_load_kN_m2": {"type": "number", "default": 2.5},
                },
                "required": ["stair_result"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "force_stair_solution",
            "description": (
                "SOLVER FORÇADO — devolve SEMPRE uma solução geométrica construível, ainda que sacrifique as regras de boa prática (inclinação até 55°, cobertor até 180 mm, altura do degrau até 220 mm, altura livre até 1700 mm). A utilizar APENAS depois de `optimize_stair` não ter encontrado uma solução `is_buildable=true` (todas as soluções excluídas por impossibilidade geométrica). A solução devolvida inclui um alerta NON_CONFORMING_FORCED_SOLUTION que lista os limites regulamentares infringidos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "floor_height_mm": {"type": "number"},
                    "available_length_mm": {"type": "number"},
                    "available_width_mm": {"type": "number"},
                    "stair_width_mm": {"type": "number", "default": 900},
                    "stairwell_length_mm": {"type": "number"},
                    "stairwell_width_mm": {"type": "number"},
                    "ceiling_height_mm": {"type": "number"},
                    "slab_thickness_mm": {"type": "number", "default": 200},
                },
                "required": ["floor_height_mm", "available_length_mm", "available_width_mm"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch tool call → moteur déterministe
# ---------------------------------------------------------------------------
def _dispatch_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Exécute un appel outil et retourne un dict JSON-sérialisable (compact)."""
    try:
        if name == "optimize_stair":
            payload = OptimizeInput(**{k: v for k, v in args.items() if v is not None})
            res = compute_optimize(payload)
            solutions_summary = [
                {
                    "rank": s.rank,
                    "type": s.type,
                    "variant": s.variant,
                    "score_global": s.score_global,
                    "num_steps": s.result.num_steps,
                    "riser_height_mm": s.result.riser_height_mm,
                    "tread_depth_mm": s.result.tread_depth_mm,
                    "blondel_value_mm": s.result.blondel_value_mm,
                    "slope_deg": s.result.slope_deg,
                    "stair_run_mm": s.result.stair_run_mm,
                    "headroom_mm": s.result.headroom_mm,
                    "is_buildable": s.result.is_buildable,
                    "alerts_top": [
                        {"level": a.level, "code": a.code, "message": a.message_fr}
                        for a in s.result.alerts[:3]
                    ],
                }
                for s in res.solutions[: (args.get("max_solutions") or 3)]
            ]
            any_buildable = len(solutions_summary) > 0
            return {
                "ok": True,
                "any_buildable_solution": any_buildable,
                "must_use_force_solver": not any_buildable,
                "solutions": solutions_summary,
                "excluded": [
                    {"type": e.type, "variant": e.variant, "reason": e.reason}
                    for e in res.excluded[:5]
                ],
            }
        if name == "force_stair_solution":
            payload = ForceSolutionInput(**{k: v for k, v in args.items() if v is not None})
            forced = compute_forced_solution(payload)
            sr = forced["stair_result"]
            return {
                "ok": True,
                "type": "straight_forced",
                "num_steps": sr["num_steps"],
                "riser_height_mm": sr["riser_height_mm"],
                "tread_depth_mm": sr["tread_depth_mm"],
                "blondel_value_mm": sr["blondel_value_mm"],
                "slope_deg": sr["slope_deg"],
                "stair_run_mm": sr["stair_run_mm"],
                "headroom_mm": sr["headroom_mm"],
                "is_buildable": True,
                "infractions_dtu": forced["infractions_dtu"],
                "alerts": [
                    {"level": a["level"], "code": a["code"], "message": a.get("message_fr") or a.get("message")}
                    for a in sr.get("alerts", [])
                ],
            }
        if name == "calculate_straight":
            payload = StairInput(**{k: v for k, v in args.items() if v is not None})
            r = compute_straight(payload)
            return {
                "ok": True,
                "num_steps": r.num_steps,
                "num_treads": r.num_treads,
                "riser_height_mm": r.riser_height_mm,
                "tread_depth_mm": r.tread_depth_mm,
                "blondel_value_mm": r.blondel_value_mm,
                "slope_deg": r.slope_deg,
                "stair_run_mm": r.stair_run_mm,
                "stair_length_mm": r.stair_length_mm,
                "headroom_mm": r.headroom_mm,
                "is_buildable": r.is_buildable,
                "alerts": [
                    {"level": a.level, "code": a.code, "message": a.message_fr}
                    for a in r.alerts
                ],
            }
        if name == "analyze_concrete":
            stair_result_dict = args.get("stair_result", {})
            # Le résultat vient d'un appel outil précédent : reconstruire un StairResult
            sr = StairResult(**stair_result_dict) if not isinstance(stair_result_dict, StairResult) else stair_result_dict
            ci = ConcreteAnalysisInput(
                stair_result=sr,
                stair_type=args.get("stair_type", "straight"),
                concrete_class=args.get("concrete_class", "C25/30"),
                steel_grade=args.get("steel_grade", "B500B"),
                exposure_class=args.get("exposure_class", "XC1"),
                live_load_kN_m2=args.get("live_load_kN_m2", 2.5),
            )
            res = compute_concrete_analysis(ci)
            return {
                "ok": True,
                "concrete_volume_m3": res.quantities.concrete_volume_m3,
                "formwork_area_m2": res.quantities.formwork_area_m2,
                "paillasse_thickness_mm": res.paillasse.thickness_recommended_mm,
                "total_steel_kg": res.reinforcement.total_steel_kg,
                "load_ELU_kN_m2": res.load_breakdown_kN_m2.total_ELU,
            }
        return {"ok": False, "error": f'Ferramenta desconhecida: {name}'}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


# ---------------------------------------------------------------------------
# API principale
# ---------------------------------------------------------------------------
@dataclass
class AssistantReply:
    conversation_id: str
    reply_text: str
    referenced_engine_calls: List[Dict[str, Any]] = field(default_factory=list)
    computed_solutions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


async def chat_with_assistant(
    conversation_id: str,
    message: str,
    history: List[Dict[str, str]],
) -> AssistantReply:
    """Envoie un message à l'assistant et retourne la réponse (non-streaming).

    Args:
        conversation_id : id unique de la conversation (utilisé comme session_id).
        message : nouveau message utilisateur (français).
        history : messages précédents [{role: 'user'|'assistant', content: str}, ...]
                  utilisés pour re-hydrater le contexte du chat.
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY em falta em backend/.env")

    t0 = time.perf_counter()

    # Reconstitue l'historique : system + tours précédents
    initial_messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        initial_messages.append({"role": role, "content": content})

    chat = (
        LlmChat(
            api_key=api_key,
            session_id=conversation_id,
            system_message=SYSTEM_PROMPT,
            initial_messages=initial_messages,
        )
        .with_model(MODEL_PROVIDER, MODEL_NAME)
        .with_tools(TOOLS, tool_choice="auto")
        .with_params(max_tokens=1024)
    )

    referenced: List[Dict[str, Any]] = []
    solutions_captured: List[Dict[str, Any]] = []

    response = await chat.send_message_with_tools(UserMessage(text=message))
    safety_max_loops = 4
    while getattr(response, "tool_calls", None) and safety_max_loops > 0:
        safety_max_loops -= 1
        for tc in response.tool_calls:
            args = tc.arguments if isinstance(tc.arguments, dict) else {}
            result = _dispatch_tool(tc.name, args)
            referenced.append({"tool": tc.name, "arguments": args, "ok": result.get("ok", True)})
            if tc.name == "optimize_stair" and result.get("ok"):
                solutions_captured.extend(result.get("solutions", []))
            chat.add_tool_result(tc.id, json.dumps(result))
        response = await chat.send_message_with_tools()

    reply_text = (getattr(response, "content", None) or "").strip()
    if not reply_text:
        reply_text = "Não consegui gerar uma resposta. Pode reformular o pedido?"

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return AssistantReply(
        conversation_id=conversation_id,
        reply_text=reply_text,
        referenced_engine_calls=referenced,
        computed_solutions=solutions_captured,
        metadata={"model": f"{MODEL_PROVIDER}/{MODEL_NAME}", "timing_ms": elapsed_ms},
    )
