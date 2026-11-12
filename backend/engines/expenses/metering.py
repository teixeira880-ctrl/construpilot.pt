"""Thin pass-through LLM observer. No prompts, images, outputs or credentials are logged."""
import os
from uuid import uuid4

from emergentintegrations.llm.chat import LlmChat, StreamDone

from engines.expenses.store import observe
from engines.expenses.context import actor


async def _guard():
    """Garde-fou de coût : refuse l'appel si le budget IA mensuel du compte est consommé."""
    from engines import usage_meter
    await usage_meter.check_ai_budget(actor().get("user_id"))


async def _account_cost(model, units):
    try:
        from engines import usage_meter
        await usage_meter.note_ai_cost(actor().get("user_id"), model, units)
    except Exception:  # noqa: BLE001 — la mesure ne casse jamais un appel
        pass


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
    # Valeurs par défaut au niveau de la classe : sûres même si l'instance est créée sans __init__.
    _failover = False
    _system = ""
    _provider = ""

    def __init__(self, *args, expense_feature="ai", failover=False, **kwargs):
        # failover=True : si le fournisseur choisi tombe (ou répond vide), send_message bascule
        # automatiquement sur les autres IA (OpenAI / Gemini / Claude) avant d'abandonner.
        self._failover = bool(failover)
        self._system = kwargs.get("system_message") or ""
        self._provider = ""
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
        self._provider = provider
        return self

    async def stream_message(self, *args, **kwargs):
        ref, usage, state = uuid4().hex, None, "interrupted"
        await _guard()
        try:
            async for event in self._inner.stream_message(*args, **kwargs):
                if isinstance(event, StreamDone):
                    usage = getattr(event, "usage", None)
                yield event
            state = "completed"
        finally:
            await observe(source_id=ref, provider=self._billing, feature=self._feature, model=self._model,
                          units=usage_units(usage), state=state)
            await _account_cost(self._model, usage_units(usage))

    async def send_message(self, *args, **kwargs):
        if not self._failover:
            return await self._send("send_message", *args, **kwargs)
        from fastapi import HTTPException
        first_error = None
        try:
            out = await self._send("send_message", *args, **kwargs)
            if isinstance(out, str) and out.strip():
                return out
            first_error = "resposta vazia"
        except HTTPException:
            raise  # budget / droits : jamais contourné par une autre IA
        except Exception as exc:  # noqa: BLE001
            first_error = f"{type(exc).__name__}: {str(exc)[:120]}"
        msg = args[0] if args else kwargs.get("user_message") or kwargs.get("message")
        return await _failover_text(self._system, msg, self._provider, self._model, self._feature, first_error)

    async def send_message_multimodal_response(self, *args, **kwargs):
        return await self._send("send_message_multimodal_response", *args, **kwargs)

    async def _send(self, method, *args, **kwargs):
        ref, usage, state = uuid4().hex, None, "failed"
        images = None
        await _guard()
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
            await _account_cost(self._model, units)


async def _failover_text(system, user_message, provider, model, feature, first_error):
    """Rejoue la même demande (texte + images) sur les autres fournisseurs de la chaîne IA."""
    import asyncio
    import logging
    from engines import ai
    log = logging.getLogger(__name__)
    text = getattr(user_message, "text", None) or (user_message if isinstance(user_message, str) else "") or ""
    images = [getattr(c, "image_base64", None) for c in (getattr(user_message, "file_contents", None) or [])]
    images = [i for i in images if i]
    errors = [f"{provider}/{model}: {first_error}"]
    for prov, mdl in await ai._chain(bool(images)):
        if prov == "perplexity" or (prov, mdl) == (provider, model):
            continue
        try:
            out = await asyncio.wait_for(ai._complete_vision_single(system, text, images, prov, mdl, feature),
                                         ai.PER_PROVIDER_TIMEOUT)
            if len((out or "").strip()) >= ai.MIN_ANSWER_CHARS:
                log.warning("ai failover %s → %s/%s ok après : %s", feature, prov, mdl, " | ".join(errors))
                return out
            errors.append(f"{prov}/{mdl}: resposta vazia")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{prov}/{mdl}: {type(exc).__name__}: {str(exc)[:120]}")
    log.error("ai failover %s : tous les fournisseurs ont échoué : %s", feature, " | ".join(errors))
    raise ConnectionError("LLM indisponível: " + " | ".join(errors)[:300])
