"""Per-turn trace of what was really sent to the model (structure and sizes only — never document text, images or keys)."""
from datetime import datetime, timezone


def summarize_inputs(inputs: list) -> dict:
    roles, images, text_chars, tool_outputs, tool_calls = {}, 0, 0, 0, 0
    for item in inputs:
        t = item.get("type") or item.get("role") or "?"
        roles[t] = roles.get(t, 0) + 1
        if t == "function_call_output":
            tool_outputs += 1
        if t == "function_call":
            tool_calls += 1
        content = item.get("content")
        if isinstance(content, str):
            text_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "input_image":
                    images += 1
                elif part.get("type") == "input_text":
                    text_chars += len(part.get("text") or "")
    return {"items": len(inputs), "by_type": roles, "images": images, "text_chars": text_chars, "tool_outputs": tool_outputs}


def instruction_blocks(instructions: str) -> list[dict]:
    blocks, start = [], 0
    for marker in ("Acompanhas a resolução", "Fotografias de obra:", "Método para um problema de obra", "Ferramentas determinísticas", "Fontes"):
        i = instructions.find(marker, start)
        if i > 0:
            blocks.append({"until": marker[:40], "chars": i - start})
            start = i
    blocks.append({"until": "end", "chars": len(instructions) - start})
    return blocks


async def save_trace(db, *, user_id: str, conversation_id: str, request_id: str, model: str, effort: str, max_output_tokens: int, instructions: str,
                     tools: list, first_inputs: dict, steps: list[dict], reply_chars: int) -> None:
    await db.assistant_traces.insert_one({
        "user_id": user_id, "conversation_id": conversation_id, "request_id": request_id, "model": model, "reasoning_effort": effort,
        "max_output_tokens": max_output_tokens, "instructions_chars": len(instructions), "instruction_blocks": instruction_blocks(instructions),
        "tools_offered": sorted(t.get("name") or (t.get("function") or {}).get("name") or t.get("type") for t in tools), "first_call_inputs": first_inputs, "steps": steps,
        "steps_count": len(steps), "reply_chars": reply_chars, "created_at": datetime.now(timezone.utc).isoformat()})


def usage_dict(usage) -> dict:
    if not usage:
        return {}
    return {"input_tokens": getattr(usage, "input_tokens", None), "output_tokens": getattr(usage, "output_tokens", None),
            "reasoning_tokens": getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", None)}
