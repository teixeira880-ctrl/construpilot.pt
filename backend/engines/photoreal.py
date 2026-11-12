"""Rendu photoréaliste « niveau studio » à partir d'une image de référence géométrique (rendu calculé du projet).

Cascade de moteurs (le premier qui répond gagne ; la géométrie de la référence est verrouillée dans chaque prompt) :
  1. GPT Image 2 (OpenAI) via Runway — 2560×1440, qualité « high » (agrandi en 4K par image_hd : plus rapide) ;
  2. Gemini 3 Pro Image (Nano Banana Pro) via Runway — 1344×768 ;
  3. Runway Gen-4 Image — 1920×1080 ;
  4. Nano Banana 3.1 via la clé universelle Emergent (engines.image_studio).
L'ordre se règle par la variable PHOTOREAL_MODELS (ex. "gpt_image_2,gemini_image3_pro,gen4_image,emergent").
Chaque image retenue passe par engines.image_hd (Full HD affiné, PHOTOREAL_LONG). Aucune exception ne remonte : None si tout échoue.

Moteur « openai » : OpenAI GPT Image en direct (clé OPENAI_API_KEY de l'entreprise), images.edit avec input_fidelity=high
— la vue calculée est la photo de départ, donc la géométrie est conservée ; modèle OPENAI_IMAGE_MODEL (gpt-image-1 par défaut).
Avec verify= (engines.geometry_lock), chaque image est alignée sur la vue calculée et refusée si les arêtes de la géométrie
(murs, toiture, baies) ne sont pas exactement au même endroit ; on passe alors au moteur suivant.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os

log = logging.getLogger(__name__)

DEFAULT_ORDER = "emergent,gemini_image3_pro,gpt_image_2,gen4_image"     # Nano Banana 3.1 primeiro (~15 s), GPT Image 2 é lento (~2 min)
RATIO = {"gpt_image_2": "1920:1088", "gemini_image3_pro": "1344:768", "gen4_image": "1920:1080"}  # menores resoluções 16:9 de cada motor
LONG_SIDE = int(os.environ.get("PHOTOREAL_LONG", 1920))      # Full HD : rápido e nítido no PDF
PROMPT_MAX = {"gen4_image": 1000}


def _order() -> list[str]:
    return [m.strip() for m in (os.environ.get("PHOTOREAL_MODELS") or DEFAULT_ORDER).split(",") if m.strip()]


def _data_uri(img: bytes, max_side: int = 2048) -> str:
    """JPEG < 5 Mo (limite Runway) en data URI."""
    from PIL import Image
    im = Image.open(io.BytesIO(img)).convert("RGB")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    q = 92
    while True:
        b = io.BytesIO()
        im.save(b, "JPEG", quality=q)
        if b.tell() < 4_500_000 or q <= 60:
            return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
        q -= 8


async def _runway(model: str, prompt: str, refs: list[tuple[str, bytes]], timeout: float) -> bytes | None:
    secret = os.environ.get("RUNWAYML_API_SECRET")
    if not secret:
        return None
    import httpx
    from runwayml import AsyncRunwayML
    client = AsyncRunwayML(api_key=secret)
    ref_list = [{"uri": _data_uri(b), "tag": tag} for tag, b in refs]
    if model == "gemini_image3_pro":
        for r in ref_list:
            r["subject"] = "object"
    kw = {"model": model, "prompt_text": prompt[:PROMPT_MAX.get(model, 30000)], "ratio": RATIO[model], "reference_images": ref_list}
    if model == "gpt_image_2":
        kw["quality"] = "high"
    task = await client.text_to_image.create(**kw)
    tid = getattr(task, "id", None)
    loop = asyncio.get_running_loop()
    deadline, delay = loop.time() + timeout, 3.0
    while True:
        t = await client.tasks.retrieve(tid)
        st = getattr(t, "status", None)
        if st == "SUCCEEDED":
            break
        if st in ("FAILED", "CANCELLED") or loop.time() >= deadline:
            log.warning("photoreal %s: %s %s", model, st, getattr(t, "failure", ""))
            return None
        await asyncio.sleep(delay)
        delay = min(delay * 1.3, 10)
    url = (getattr(t, "output", None) or [None])[0]
    if not url:
        return None
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as hc:
        r = await hc.get(url)
        r.raise_for_status()
        return r.content


async def _openai(prompt: str, base: bytes, style: bytes | None, timeout: float) -> bytes | None:
    """GPT Image (OpenAI direct) : édition de la vue calculée, fidélité d'entrée haute, 1536×1024 puis recadrage exact."""
    from engines import llm_keys
    if not llm_keys.openai_direct_active():
        return None
    from openai import AsyncOpenAI
    from engines import geometry_lock as G
    padded, box = G.pad(base, 1.5)
    from PIL import Image
    pw, ph = Image.open(io.BytesIO(padded)).size
    imgs = [("geometry.png", padded, "image/png")] + ([("style.jpg", style, "image/jpeg")] if style else [])
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=timeout)
    head = ("The first image is the exact geometry of the building: keep every edge where it is — same outline, storeys, roof, "
            "every window and door at the same position and size, same camera. Only change materials, light and surroundings "
            "to make it a real photograph. ")
    if style:
        head += "The second image is the approved style: match its materials, colours, garden and light. "
    models = [os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-1"]
    if models[0] != "gpt-image-1":
        models.append("gpt-image-1")
    for m in models:
        try:
            r = await client.images.edit(model=m, image=imgs if len(imgs) > 1 else imgs[0], prompt=(head + prompt)[:31000],
                                         size="1536x1024", quality="high", input_fidelity="high", output_format="png")
            data = base64.b64decode(r.data[0].b64_json)
            return G.crop(data, (pw, ph), box)
        except Exception as exc:  # noqa: BLE001
            if await llm_keys.note_openai_error(exc):
                return None
            log.warning("photoreal openai %s: %s", m, str(exc)[:200])
    return None


async def _meter(model: str, feature: str, session_id: str, provider: str = "runway") -> None:
    try:
        from engines.expenses.store import observe
        await observe(source="photoreal", source_id=session_id, provider=provider, feature=feature, model=model,
                      units={"images": 1}, state="completed")
    except Exception:  # noqa: BLE001
        pass


def _tagged(prompt: str, style: bool, head: str | None = None) -> str:
    """Prompt Runway : la référence géométrique s'appelle @model, le style validé @style."""
    head = head or ("Use @model as the exact geometric reference: same building, same massing, storeys, openings and the very same "
            "camera position and framing. ")
    if style:
        head += "Use @style only for materials, colours, landscaping and lighting. "
    return head + prompt


async def render(base: bytes, prompt: str, *, style_ref: bytes | None = None, timeout: float = 240.0,
                 feature: str = "photoreal", session_id: str = "photoreal", head: str | None = None,
                 engines: list[str] | None = None, verify=None) -> tuple[bytes, str] | None:
    """Photo réaliste de la référence `base`. Renvoie (octets, nom du moteur) ou None.
    verify(octets) → (octets alignés, score 0..1) : l'image n'est retenue que si score ≥ geometry_lock.threshold()."""
    from engines import image_hd

    async def accept(img: bytes, name: str):
        if verify is None:
            return img, name
        from engines import geometry_lock as G
        aligned, sc = await asyncio.to_thread(verify, img)
        log.info("photoreal %s geometry score %.2f (min %.2f)", name, sc, G.threshold())
        return (aligned, name) if sc >= G.threshold() else None

    for model in (engines or _order()):
        try:
            if model == "openai":
                data = await asyncio.wait_for(_openai(prompt, base, style_ref, timeout), timeout + 30)
                if data:
                    await _meter("gpt-image", feature, session_id, provider="openai")
                    hd, _ = await asyncio.to_thread(image_hd.sharpen, data, "image/png", long_side=LONG_SIDE)
                    ok = await accept(hd, "openai_gpt_image")
                    if ok:
                        return ok
                continue
            if model == "emergent":
                from engines import image_studio
                out = await asyncio.wait_for(image_studio.generate(
                    prompt=prompt, provider="gemini", reference_images=[base] + ([style_ref] if style_ref else []),
                    feature=feature, session_id=session_id), timeout)
                if out:
                    ok = await accept(out[0][0], "nano_banana_3.1")
                    if ok:
                        return ok
                continue
            if model not in RATIO:
                continue
            refs = [("model", base)] + ([("style", style_ref)] if style_ref else [])
            data = await asyncio.wait_for(_runway(model, _tagged(prompt, bool(style_ref), head), refs, timeout), timeout + 30)
            if data:
                await _meter(model, feature, session_id)
                hd, _ = await asyncio.to_thread(image_hd.sharpen, data, "image/png", long_side=LONG_SIDE)
                ok = await accept(hd, model)
                if ok:
                    return ok
        except Exception as exc:  # noqa: BLE001 — on passe au moteur suivant
            log.warning("photoreal %s failed: %s", model, str(exc)[:200])
    return None
