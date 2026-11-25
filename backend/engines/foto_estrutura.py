"""Render fotorrealista de uma estrutura calculada (CLT, LSF, construção tradicional) — para TODAS as contas.

Parte SEMPRE do render calculado (Mitsuba, geometria exata do motor) e pede aos motores de imagem em cascata
(engines.photoreal: GPT Image 2 / Nano Banana Pro / Runway / Nano Banana 3.1) a mesma cena em fotografia, com a geometria
bloqueada no prompt. Se nenhum motor responder, devolve None e o estudo fica com o render calculado (nunca bloqueia).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PROMPTS = {
    "clt": ("Photorealistic construction-site photograph of this exact cross-laminated timber (CLT) building shell, just assembled: "
            "exposed spruce CLT panels with visible lamella texture and panel joints, window and door cut-outs left open, timber roof panels, "
            "on a concrete slab, gravel site, natural daylight, 35 mm lens. Keep the EXACT geometry, proportions, openings, roof shape and camera "
            "of the reference image — do not add or remove any wall, opening or storey. No people, no text, no watermark."),
    "lsf": ("Photorealistic construction-site photograph of this exact light-steel-frame (LSF) structure, just assembled: galvanised cold-formed "
            "steel studs, tracks, headers and roof trusses with their real spacing, on a concrete slab, gravel site, natural daylight, 35 mm lens. "
            "Keep the EXACT geometry, member layout, openings, roof shape and camera of the reference image — do not add or remove members. "
            "No people, no text, no watermark."),
    "tradicional": ("Photorealistic construction-site photograph of this exact reinforced-concrete and masonry building shell: concrete frame, "
                    "brick / block walls, openings left open, natural daylight, 35 mm lens. Keep the EXACT geometry, openings, storeys and camera "
                    "of the reference image. No people, no text, no watermark."),
}


async def fotorrealista(base_png: bytes, sistema: str = "clt", timeout: float = 240.0) -> tuple[bytes, str] | None:
    try:
        from engines import photoreal
        return await photoreal.render(base_png, PROMPTS.get(sistema, PROMPTS["clt"]), timeout=timeout,
                                      feature=f"foto_{sistema}", session_id=f"foto_{sistema}")
    except Exception as exc:  # noqa: BLE001 — a foto embeleza, nunca bloqueia
        log.warning("foto estrutura %s indisponível: %s", sistema, str(exc)[:200])
        return None


def _render_base(sistema: str, args: dict) -> list:
    """Render calculado (Mitsuba) da estrutura, com a mesma entrada que a ferramenta do Assistente."""
    if sistema == "clt":
        from engines.clt import note as N
        from engines.clt.engine import calcular
        from engines.clt.render import render
        return render(calcular(N.projeto(args)), largura=1600, altura=900, spp=64, vistas=[("estrutura", (-0.62, -0.78), 0.55)], orcamento_s=180)
    from engines.lsf import note as N
    from engines.lsf.engine import calcular
    from engines.lsf.render import render
    return render(calcular(N.projeto(args)), largura=1600, altura=900, spp=64, vistas=[("estrutura", (-0.62, -0.78), 0.55)], orcamento_s=180)


async def renders_assistente(sistema: str, args: dict) -> list:
    """[(nome, PNG/JPEG)] para o dossier do Assistente: foto fotorrealista (se algum motor responder) + render calculado.
    Lista vazia se o servidor não tiver Mitsuba (o dossier sai então com a vista do próprio motor)."""
    import asyncio
    try:
        base = await asyncio.to_thread(_render_base, sistema, args)
    except Exception as exc:  # noqa: BLE001
        log.warning("render %s indisponível: %s", sistema, str(exc)[:200])
        return []
    if not base:
        return []
    foto = await fotorrealista(base[0][1], sistema)
    return ([("fotorrealista", foto[0])] if foto else []) + base
