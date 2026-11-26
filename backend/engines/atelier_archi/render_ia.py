"""Render fotorrealista do Estúdio 3D (Ateliê) — a vista 3D capturada é a fotografia de partida.

Motores, pela ordem (o primeiro que responde ganha; a ordem pode ser mudada com ATELIER_RENDER_MOTORES):
  1. "openai"   → OpenAI GPT Image em direto (OPENAI_API_KEY da empresa): images.edit sobre a vista 3D,
                  fidelidade de entrada alta, por isso a geometria (paredes, vãos, cobertura, enquadramento) mantém-se.
                  Modelo OPENAI_IMAGE_MODEL, senão gpt-image-2 → gpt-image-1.5 → gpt-image-1.
  2. "emergent" → Nano Banana (Gemini) pela chave universal Emergent (engines.image_studio), com a vista como referência.
  3. "gpt_image_2", "gemini_image3_pro", "gen4_image" → via Runway (RUNWAYML_API_SECRET), se existir.
Nenhuma exceção sobe: devolve None se todos falharem.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os

log = logging.getLogger(__name__)

ORDEM = "openai,emergent,gpt_image_2,gemini_image3_pro,gen4_image"
CABECA = ("The image is a 3D view of an architectural project. Keep the exact geometry: same building outline, storeys, roof, "
          "every window and door at the same position and size, same camera and framing. Only change materials, light, "
          "vegetation and surroundings so that it looks like a real professional architectural photograph. "
          "No text, no labels, no watermark. ")


def motores() -> list[str]:
    return [m.strip() for m in (os.environ.get("ATELIER_RENDER_MOTORES") or ORDEM).split(",") if m.strip()]


def _pad(img: bytes, ratio: float = 1.5) -> tuple[bytes, tuple[int, int], tuple[int, int, int, int]]:
    """Alarga a vista até 3:2 (formato do GPT Image) com margens da cor do bordo; devolve imagem, tamanho e caixa original."""
    from PIL import Image, ImageOps
    im = Image.open(io.BytesIO(img)).convert("RGB")
    w, h = im.size
    if abs(w / h - ratio) < 0.01:
        box = (0, 0, w, h)
        out = im
    elif w / h > ratio:
        H = round(w / ratio)
        t = (H - h) // 2
        out = ImageOps.expand(im, border=(0, t, 0, H - h - t), fill=im.getpixel((w // 2, 0)))
        box = (0, t, w, h)
    else:
        W = round(h * ratio)
        l_ = (W - w) // 2
        out = ImageOps.expand(im, border=(l_, 0, W - w - l_, 0), fill=im.getpixel((0, h // 2)))
        box = (l_, 0, w, h)
    b = io.BytesIO()
    out.save(b, "PNG")
    return b.getvalue(), out.size, box


def _recortar(img: bytes, tamanho: tuple[int, int], box: tuple[int, int, int, int]) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(img)).convert("RGB").resize(tamanho, Image.LANCZOS)
    x, y, w, h = box
    b = io.BytesIO()
    im.crop((x, y, x + w, y + h)).save(b, "PNG")
    return b.getvalue()


async def _openai(prompt: str, base: bytes, timeout: float) -> tuple[bytes, str] | None:
    try:
        from engines import llm_keys
        if not llm_keys.openai_direct_active():
            return None
    except Exception:  # noqa: BLE001
        if not os.environ.get("OPENAI_API_KEY"):
            return None
        llm_keys = None
    from openai import AsyncOpenAI
    padded, tamanho, box = await asyncio.to_thread(_pad, base)
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=timeout)
    modelos: list[str] = []
    for m in [os.environ.get("OPENAI_IMAGE_MODEL"), "gpt-image-2", "gpt-image-1.5", "gpt-image-1"]:
        if m and m not in modelos:
            modelos.append(m)
    for m in modelos:
        for fidelidade in (True, False):     # gpt-image-2 recusa input_fidelity → tenta sem
            kw = {"input_fidelity": "high"} if fidelidade else {}
            try:
                r = await client.images.edit(model=m, image=("vista-3d.png", padded, "image/png"),
                                             prompt=(CABECA + prompt)[:30000], size="1536x1024",
                                             quality="high", output_format="png", **kw)
                data = base64.b64decode(r.data[0].b64_json)
                return await asyncio.to_thread(_recortar, data, tamanho, box), m
            except Exception as exc:  # noqa: BLE001
                if llm_keys is not None:
                    try:
                        if await llm_keys.note_openai_error(exc):
                            return None      # chave sem crédito / inválida → passa ao motor seguinte
                    except Exception:  # noqa: BLE001
                        pass
                log.warning("render_ia openai %s%s: %s", m, "" if fidelidade else " (sem input_fidelity)", str(exc)[:200])
                if not (fidelidade and "input_fidelity" in str(exc)):
                    break
    return None


async def _contar(motor: str, sessao: str) -> None:
    try:
        from engines.expenses.store import observe
        await observe(source="atelier_render", source_id=sessao, provider="openai" if motor.startswith("gpt-image") else "photoreal",
                      feature="atelier_render", model=motor, units={"images": 1}, state="completed")
    except Exception:  # noqa: BLE001
        pass


async def render(base: bytes, prompt: str, *, sessao: str = "atelier_render", timeout: float = 100.0) -> tuple[bytes, str] | None:
    """(imagem PNG/JPEG, nome do motor) ou None."""
    ordem = motores()
    if "openai" in ordem:
        try:
            res = await asyncio.wait_for(_openai(prompt, base, timeout), timeout + 20)
            if res:
                await _contar(res[1], sessao)
                return res
        except Exception as exc:  # noqa: BLE001
            log.warning("render_ia openai falhou: %s", str(exc)[:200])
    resto = [m for m in ordem if m != "openai"]
    if not resto:
        return None
    try:
        from engines import photoreal as PR
        return await PR.render(base, CABECA + prompt, feature="atelier_render", session_id=sessao, timeout=timeout, engines=resto)
    except Exception as exc:  # noqa: BLE001
        log.warning("render_ia photoreal falhou: %s", str(exc)[:200])
        return None
