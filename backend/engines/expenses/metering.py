"""Thin pass-through LLM observer. No prompts, images, outputs or credentials are logged."""
import os
from uuid import uuid4

from emergentintegrations.llm.chat import LlmChat, StreamDone

from engines.expenses.store import observe


def usage_units(usage):
    units = {"calls": 1}
    if usage is None:
        return units
    for target, names in {"input_tokens": ("input_tokens", "prompt_tokens"), "output_tokens": ("output_tokens", "completion_tokens")}.items():
        for name in names:
            value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                units[target] = value
                break
    return units


class MeteredChat:
    def __init__(self, *args, expense_feature="ai", **kwargs):
        key = kwargs.get("api_key")
        self._billing = "openai_direct" if key and key == os.environ.get("OPENAI_API_KEY") else "emergent" if key and key == os.environ.get("EMERGENT_LLM_KEY") else "other"
        self._inner = LlmChat(*args, **kwargs)
        self._model = ""
        self._feature = expense_feature

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def with_model(self, provider, model):
        self._inner = self._inner.with_model(provider, model)
        self._model = model
        return self

    async def stream_message(self, *args, **kwargs):
        ref, usage, state = uuid4().hex, None, "interrupted"
        try:
            async for event in self._inner.stream_message(*args, **kwargs):
                if isinstance(event, StreamDone):
                    usage = getattr(event, "usage", None)
                yield event
            state = "completed"
        finally:
            await observe(source_id=ref, provider=self._billing, feature=self._feature, model=self._model,
                          units=usage_units(usage), state=state)

    async def send_message(self, *args, **kwargs):
        return await self._send("send_message", *args, **kwargs)

    async def send_message_multimodal_response(self, *args, **kwargs):
        return await self._send("send_message_multimodal_response", *args, **kwargs)

    async def _send(self, method, *args, **kwargs):
        ref, usage, state = uuid4().hex, None, "failed"
        images = None
        try:
            result = await getattr(self._inner, method)(*args, **kwargs)
            usage, state = getattr(result, "usage", None), "completed"
            if method == "send_message_multimodal_response" and isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], list):
                images = len(result[1])
            return result
        finally:
            units = usage_units(usage)
            if images is not None:
                units["images"] = images
            await observe(source_id=ref, provider=self._billing, feature=self._feature, model=self._model,
                          units=units, state=state)