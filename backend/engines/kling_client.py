"""Cliente Kling AI (imagem) — fotorrealismo a partir da vista calculada da geometria real.

Autenticação (Kling AI Open Platform, região internacional):
  * KLING_API_KEY                       → "Authorization: Bearer <API Key>" (novo padrão, todos os modelos)
  * KLING_ACCESS_KEY + KLING_SECRET_KEY → JWT HS256 (iss=AK, exp=+30 min, nbf=−5 s), padrão antigo
Base: KLING_API_BASE (default https://api-singapore.klingai.com).

Modelo: KLING_IMAGE_MODEL
  * "kling-v3-omni" (default) ou "kling-image-o1" → POST /v1/images/omni-image   (image_list + <<<image_1>>>)
  * "kling-4.0"                                   → POST /image-generation/kling-4.0 (contents refer_image + @id)
  * "kling-v3" / "kling-v2-1"                     → POST /v1/images/generations  (image + image_fidelity)

A Kling NÃO tem parâmetro de controlo de estrutura: a geometria é garantida fora daqui — a imagem só é
usada se engines.geometry_lock confirmar que as arestas (volume, cobertura, vãos) estão no mesmo sítio.
As chaves vivem só nos Secrets do Emergent; nunca em código, logs ou mensagens de erro.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import time
import uuid

log = logging.getLogger(__name__)
DEFAULT_BASE = "https://api-singapore.klingai.com"
_TRANSPORT = None                     # testes: httpx.MockTransport


def configured() -> bool:
    return bool((os.environ.get("KLING_API_KEY") or "").strip() or
                ((os.environ.get("KLING_ACCESS_KEY") or "").strip() and (os.environ.get("KLING_SECRET_KEY") or "").strip()))


def _auth() -> str:
    key = (os.environ.get("KLING_API_KEY") or "").strip()
    if key:
        return f"Bearer {key}"
    import jwt
    ak, sk = os.environ["KLING_ACCESS_KEY"].strip(), os.environ["KLING_SECRET_KEY"].strip()
    now = int(time.time())
    tok = jwt.encode({"iss": ak, "exp": now + 1800, "nbf": now - 5}, sk, algorithm="HS256",
                     headers={"alg": "HS256", "typ": "JWT"})
    return f"Bearer {tok}"


def _b64_jpeg(img: bytes, max_side: int = 2048) -> str:
    """Base64 SEM prefixo data: (exigência da Kling), JPEG < 9,5 MB, lado ≥ 300 px."""
    from PIL import Image
    im = Image.open(io.BytesIO(img)).convert("RGB")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    q = 92
    while True:
        b = io.BytesIO()
        im.save(b, "JPEG", quality=q)
        if b.tell() < 9_500_000 or q <= 60:
            return base64.b64encode(b.getvalue()).decode()
        q -= 8


def _aspect(img: bytes) -> str:
    from PIL import Image
    w, h = Image.open(io.BytesIO(img)).size
    r = w / max(h, 1)
    opts = {"16:9": 16 / 9, "4:3": 4 / 3, "3:2": 1.5, "1:1": 1.0, "21:9": 21 / 9, "3:4": 0.75, "2:3": 2 / 3, "9:16": 9 / 16}
    return min(opts, key=lambda k: abs(opts[k] - r))


def _request(model: str, prompt: str, base: bytes, style: bytes | None) -> tuple[str, dict, str]:
    """(caminho de criação, corpo, caminho de consulta com {id})."""
    imgs = [base] + ([style] if style else [])
    res = os.environ.get("KLING_RESOLUTION") or "2k"
    if model in ("kling-4.0", "kling-image-4.0", "4.0"):
        contents = [{"type": "refer_image", "url": _b64_jpeg(b), "id": f"img{i + 1}"} for i, b in enumerate(imgs)]
        head = "@img1 is the exact geometry of the building. " + ("@img2 is the approved style. " if style else "")
        contents.insert(0, {"type": "prompt", "text": head + prompt})
        body = {"contents": contents, "settings": {"result_type": "single", "n": 1, "resolution": res,
                                                    "aspect_ratio": _aspect(base)},
                "options": {"external_task_id": f"cp-{uuid.uuid4().hex[:20]}"}}
        return "/image-generation/kling-4.0", body, "/tasks?task_ids={id}"
    if model in ("kling-v3", "kling-v2-1"):
        body = {"model_name": model, "prompt": prompt[:2500], "image": _b64_jpeg(base), "n": 1,
                "aspect_ratio": _aspect(base), "resolution": "2k" if res in ("2k", "4k") else "1k"}
        if model == "kling-v2-1":
            body["image_fidelity"] = 1.0
        return "/v1/images/generations", body, "/v1/images/generations/{id}"
    head = ("<<<image_1>>> is the exact geometry of the building: keep it pixel-aligned. "
            + ("Match materials, colours, garden and light of <<<image_2>>>. " if style else ""))
    body = {"model_name": model or "kling-v3-omni", "prompt": (head + prompt)[:2500],
            "image_list": [{"image": _b64_jpeg(b)} for b in imgs], "n": 1, "aspect_ratio": _aspect(base),
            "resolution": res if res in ("1k", "2k", "4k") else "2k"}
    return "/v1/images/omni-image", body, "/v1/images/omni-image/{id}"


def _urls(payload: dict) -> tuple[str | None, list[str]]:
    """(estado normalizado, URLs das imagens) — formatos antigo (task_result) e novo (outputs)."""
    data = payload.get("data")
    if isinstance(data, list):
        data = data[0] if data else {}
    data = data or {}
    st = str(data.get("task_status") or data.get("status") or "").lower()
    st = {"succeed": "succeeded", "success": "succeeded"}.get(st, st)
    urls = [i.get("url") for i in ((data.get("task_result") or {}).get("images") or []) if i.get("url")]
    urls += [o.get("url") for o in (data.get("outputs") or []) if o.get("type", "image") == "image" and o.get("url")]
    return st, urls


async def render(prompt: str, base: bytes, style: bytes | None = None, *, timeout: float = 240.0,
                 model: str | None = None) -> bytes | None:
    """Imagem fotorrealista (bytes) ou None. Nunca levanta exceção para o chamador com segredos no texto."""
    if not configured():
        return None
    import httpx

    model = (model or os.environ.get("KLING_IMAGE_MODEL") or "kling-v3-omni").strip()
    api = (os.environ.get("KLING_API_BASE") or DEFAULT_BASE).rstrip("/")
    path, body, query = _request(model, prompt, base, style)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        async with httpx.AsyncClient(timeout=60, transport=_TRANSPORT) as hc:
            r = await hc.post(api + path, json=body, headers={"Authorization": _auth(), "Content-Type": "application/json"})
            js = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code >= 400 or (js.get("code") not in (0, None)):
                log.warning("kling create %s: HTTP %s code=%s msg=%s", model, r.status_code, js.get("code"),
                            str(js.get("message"))[:160])
                return None
            d = js.get("data") or {}
            tid = d.get("task_id") or d.get("id")
            if not tid:
                return None
            delay = 3.0
            while loop.time() < deadline:
                await asyncio.sleep(delay)
                delay = min(delay * 1.3, 10.0)
                q = await hc.get(api + query.format(id=tid), headers={"Authorization": _auth()})
                st, urls = _urls(q.json() if q.status_code < 500 else {})
                if st == "succeeded" and urls:
                    img = await hc.get(urls[0], follow_redirects=True, timeout=120)
                    img.raise_for_status()
                    return img.content
                if st == "failed":
                    log.warning("kling %s task failed", model)
                    return None
            log.warning("kling %s: timeout", model)
    except Exception as exc:  # noqa: BLE001
        log.warning("kling %s: %s", model, type(exc).__name__)
    return None
