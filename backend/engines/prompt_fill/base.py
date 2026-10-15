"""Base reutilizável para extração estruturada de parâmetros a partir de
prompts em português europeu (PT-PT). Preserva o funcionamento manual das
calculadoras — a IA é EXTRA, nunca substituto. Falha-se silenciosamente para
o utilizador poder sempre voltar a preencher à mão.

Convenções:
- Cada app regista um extractor via `register()`.
- O LLM responde SEMPRE num envelope JSON. Se faltar algo essencial, devolve
  `clarification_question` em PT-PT (uma pergunta curta).
- A chamada LLM está isolada em `_ask_text`, reutilizando o padrão Emergent
  (claude-sonnet via chave universal), igual ao `structuro_ai.py`.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Protocol

log = logging.getLogger("prompt_fill")

_MODEL = ("anthropic", "claude-sonnet-4-6")


class Extractor(Protocol):
    app_key: str
    schema: dict
    defaults: dict
    prompt_system: str

    def post_process(self, data: dict) -> dict: ...

    def required_fields(self) -> list[str]: ...


def _strip_fences(txt: str) -> str:
    t = (txt or "").strip()
    if t.startswith("```"):
        # remove abertura ```json ou ```
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    if not t.lstrip().startswith("{"):
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            t = m.group(0)
    return t.strip()


async def _ask_text(prompt: str) -> str:
    """Chama o LLM Claude via Emergent (chave universal). Compatível com o
    padrão já usado no projeto (`structuro_ai.extract_facts`)."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY ausente")
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

    chat = LlmChat(
        api_key=key,
        session_id="prompt-fill",
        system_message="Responde em JSON válido, em português europeu, sem texto fora do JSON.",
    ).with_model(*_MODEL)
    resp = await chat.send_message(UserMessage(text=prompt))
    return resp if isinstance(resp, str) else str(resp)


async def run_extractor(
    extractor: Extractor, prompt: str, context: dict | None = None
) -> dict:
    """Devolve envelope JSON (dict), nunca lança:

    - {"ok": true, "params": {...}, "ai_filled": [...], "defaults_used": [...], "notes": [...]}
    - {"ok": false, "clarification_question": "pergunta PT-PT curta"}
    - {"ok": false, "error": "..."}
    """
    system = extractor.prompt_system
    user_payload = {
        "prompt": prompt,
        "contexto_atual": context or {},
        "schema": extractor.schema,
        "valores_por_defeito_normativos": extractor.defaults,
    }
    full_prompt = (
        f"{system}\n\n"
        "Devolve APENAS um JSON válido com o seguinte formato:\n"
        '{"ok": true, "params": {<chaves do schema>}, '
        '"ai_filled": [<chaves cujo valor VEIO do prompt do utilizador>], '
        '"defaults_used": [<chaves cujo valor VEIO dos valores por defeito normativos>], '
        '"notes": [<avisos curtos PT-PT>]}\n'
        "OU, se algo essencial estiver AMBÍGUO ou em FALTA e não houver valor por defeito seguro:\n"
        '{"ok": false, "params": {<chaves do schema JÁ EXTRAÍDAS, mesmo que incompletas>}, '
        '"ai_filled": [<chaves parciais extraídas>], '
        '"missing_fields": [<chaves que ainda faltam>], '
        '"clarification_question": "<pergunta curta PT-PT, uma só>"}\n\n'
        "REGRA IMPORTANTE: mesmo quando devolveres clarification_question, inclui SEMPRE em "
        "`params` todas as chaves que já conseguiste inferir do prompt do utilizador. "
        "Nunca omitas o preenchimento parcial — o formulário aplica-o imediatamente.\n\n"
        f"DADOS: {json.dumps(user_payload, ensure_ascii=False)}"
    )
    try:
        raw = await _ask_text(full_prompt)
    except Exception as exc:  # noqa: BLE001
        log.exception("LLM falhou em run_extractor")
        return {"ok": False, "error": f"Serviço de IA indisponível: {str(exc)[:120]}"}
    try:
        data = json.loads(_strip_fences(raw))
    except Exception:  # noqa: BLE001
        log.warning("JSON inválido do LLM: %r", (raw or "")[:200])
        return {
            "ok": False,
            "error": "Resposta da IA ilegível. Tente reformular o pedido.",
        }
    if not isinstance(data, dict) or "ok" not in data:
        return {"ok": False, "error": "Resposta da IA mal formatada."}
    # Pós-processar `params` SEMPRE que vierem, mesmo com ok=false (preenchimento parcial)
    if isinstance(data.get("params"), dict) and data["params"]:
        try:
            data["params"] = extractor.post_process(data["params"])
        except Exception as exc:  # noqa: BLE001
            # Se o pós-processamento falhar com partial, não deitamos a resposta fora:
            # devolvemos o envelope com clarification mas sem params inválidos.
            if data.get("ok"):
                return {
                    "ok": False,
                    "error": f"Parâmetros inválidos: {str(exc)[:160]}",
                }
            log.warning("post_process falhou em partial: %s", exc)
            data.pop("params", None)
    return data


REGISTRY: dict[str, Extractor] = {}


def register(ext: Extractor) -> Extractor:
    REGISTRY[ext.app_key] = ext
    return ext
