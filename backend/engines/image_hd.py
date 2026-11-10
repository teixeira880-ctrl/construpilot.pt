"""Haute définition commune à toutes les images 3D / photoréalistes générées par l'IA (tous comptes, tous modules).

Les modèles d'image renvoient en général ~1 Mpx (≈1024–1408 px de côté). On applique ici, sans appel externe :
  • agrandissement Lanczos jusqu'à `long_side` px (4K par défaut : 3840 px sur le grand côté) ;
  • netteté (unsharp mask à deux rayons : micro-détails + contours) et léger gain de contraste local ;
  • export JPEG 4:4:4 haute qualité (poids raisonnable pour le stockage base64) ou PNG à la demande.
Toute erreur renvoie l'image d'origine : la haute définition embellit, elle ne bloque jamais une génération.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)

HD_LONG_SIDE = 3840
HD_PROMPT = (" Render in maximum resolution and high definition: tack-sharp focus across the whole frame, crisp edges, "
             "fine material textures (wood grain, concrete pores, glass reflections), no blur, no noise, no compression artefacts.")


def hd_prompt(prompt: str) -> str:
    """Ajoute la consigne « haute définition » au prompt (une seule fois)."""
    return prompt if HD_PROMPT.strip()[:30] in prompt else prompt.rstrip() + HD_PROMPT


def sharpen(data: bytes, mime: str = "image/png", *, long_side: int = HD_LONG_SIDE, fmt: str = "jpeg") -> tuple[bytes, str]:
    """Agrandit et affine une image générée. Renvoie (octets, mime)."""
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        im = Image.open(io.BytesIO(data))
        im.load()
        if getattr(im, "is_animated", False):
            return data, mime
        alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if alpha else "RGB")
        w, h = im.size
        k = long_side / max(w, h)
        if k > 1.05:
            im = im.resize((round(w * k), round(h * k)), Image.LANCZOS)
            f = min(k, 4.0)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.2 * f, percent=55, threshold=2))   # contours
        im = im.filter(ImageFilter.UnsharpMask(radius=0.8, percent=90, threshold=1))           # micro-détails
        im = ImageEnhance.Contrast(im).enhance(1.04)
        out = io.BytesIO()
        if fmt == "png" or alpha:
            im.save(out, "PNG", optimize=True)
            return out.getvalue(), "image/png"
        im.save(out, "JPEG", quality=93, subsampling=0, optimize=True, progressive=True)
        return out.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001
        log.warning("image_hd.sharpen failed — original kept", exc_info=True)
        return data, mime


def sharpen_b64(b64: str, mime: str = "image/png", **kw) -> tuple[str, str]:
    import base64
    data, m = sharpen(base64.b64decode(b64), mime, **kw)
    return base64.b64encode(data).decode(), m
