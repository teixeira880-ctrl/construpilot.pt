"""Verificação de geometria das imagens fotorrealistas: a foto gerada por IA só é aceite se respeitar a geometria
calculada (mesmas arestas de paredes, cobertura e vãos, mesma câmara).

  pad(base)               → referência no formato do motor (OpenAI 3:2) sem deformar; crop() desfaz no resultado;
  check(out, base, mask)  → alinha a foto à vista calculada (ECC afim, correções pequenas) e mede o contraste da foto exatamente
                            nas arestas previstas (vãos e volume, o pior dos dois, 0..1). Devolve (foto alinhada, pontuação).
O limiar é GEOMETRY_MIN (0.62 por defeito). Abaixo dele a foto é recusada e tenta-se o motor seguinte.
"""
from __future__ import annotations

import io
import logging
import os

log = logging.getLogger(__name__)


def threshold() -> float:
    try:
        return float(os.environ.get("GEOMETRY_MIN") or 0.62)
    except ValueError:
        return 0.62


def _rgb(b: bytes):
    import cv2
    import numpy as np
    return cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)


def _enc(im, fmt: str = ".png") -> bytes:
    import cv2
    ok, buf = cv2.imencode(fmt, im)
    return buf.tobytes()


def pad(base: bytes, ratio: float = 1.5) -> tuple[bytes, tuple[int, int, int, int]]:
    """Alarga a vista (bordos repetidos) até à proporção do motor; devolve a imagem e a caixa (x, y, w, h) original."""
    import cv2
    im = _rgb(base)
    h, w = im.shape[:2]
    if abs(w / h - ratio) < 0.01:
        return base, (0, 0, w, h)
    if w / h > ratio:
        H = round(w / ratio)
        t = (H - h) // 2
        out = cv2.copyMakeBorder(im, t, H - h - t, 0, 0, cv2.BORDER_REPLICATE)
        return _enc(out), (0, t, w, h)
    W = round(h * ratio)
    l_ = (W - w) // 2
    out = cv2.copyMakeBorder(im, 0, 0, l_, W - w - l_, cv2.BORDER_REPLICATE)
    return _enc(out), (l_, 0, w, h)


def crop(out: bytes, padded_size: tuple[int, int], box: tuple[int, int, int, int]) -> bytes:
    import cv2
    im = cv2.resize(_rgb(out), padded_size, interpolation=cv2.INTER_LANCZOS4)
    x, y, w, h = box
    return _enc(im[y:y + h, x:x + w])


def _edges_gray(im):
    import cv2
    import numpy as np
    g = cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    v = float(np.median(g))
    return cv2.Canny(g, int(max(0, 0.5 * v)), int(min(255, 1.2 * v + 30)))


def _align(out, base):
    """Pequena correção afim (enquadramento do motor ligeiramente diferente). Nunca deforma muito."""
    import cv2
    import numpy as np
    h, w = base.shape[:2]
    s = 480 / w
    a = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(base, None, fx=s, fy=s), cv2.COLOR_BGR2GRAY), (0, 0), 3).astype(np.float32)
    b = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(out, (a.shape[1], a.shape[0])), cv2.COLOR_BGR2GRAY), (0, 0), 3).astype(np.float32)
    M = np.eye(2, 3, dtype=np.float32)
    try:
        cv2.findTransformECC(a, b, M, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 120, 1e-5), None, 5)
    except cv2.error:
        return out
    sx, sy = np.hypot(M[0, 0], M[1, 0]), np.hypot(M[0, 1], M[1, 1])
    shear = abs(M[0, 0] * M[0, 1] + M[1, 0] * M[1, 1]) / (sx * sy)
    if not (0.9 < sx < 1.1 and abs(sx - sy) < 0.025 and shear < 0.03 and abs(M[0, 2]) < 0.08 * a.shape[1]
            and abs(M[1, 2]) < 0.08 * a.shape[0]):     # só semelhança (escala uniforme), nunca deformar a casa
        return out
    M[:, 2] /= s
    return cv2.warpAffine(cv2.resize(out, (w, h)), M, (w, h), flags=cv2.INTER_LANCZOS4 + cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


def _ratio(gmax, edges, band) -> float:
    """Cobertura: fração das arestas previstas onde a foto tem uma aresta nítida (≥ 2,2 × o fundo à volta)."""
    import numpy as np
    on, off = gmax[edges > 0], gmax[band > 0]
    if on.size < 40 or off.size < 40:
        return 0.0
    t = 2.2 * float(np.median(off)) + 1.0
    return float((on > t).mean())


def scores(out_im, mask_im) -> dict:
    """Contraste nas arestas previstas vs. à volta delas, separado para os vãos e para o volume (paredes, cobertura,
    silhueta). 0 = nenhuma aresta no sítio certo; ~0,7+ = arestas nítidas exatamente onde a geometria as prevê."""
    import cv2
    import numpy as np
    h, w = mask_im.shape[:2]
    g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(out_im, (w, h)), cv2.COLOR_BGR2GRAY), (0, 0), 1.2).astype(np.float32)
    mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    tol = max(3, int(0.006 * w)) | 1
    gmax = cv2.dilate(mag, np.ones((tol, tol), np.uint8))
    op = (mask_im == 40).astype(np.uint8)
    e_all = cv2.Canny(mask_im, 5, 10)
    e_op = cv2.Canny(op * 255, 50, 100)
    e_str = cv2.subtract(e_all, cv2.dilate(e_op, np.ones((3, 3), np.uint8)))
    far = cv2.distanceTransform((e_all == 0).astype(np.uint8), cv2.DIST_L2, 3)
    band = ((far > 0.02 * w) & (far < 0.05 * w)).astype(np.uint8)
    inside = cv2.dilate((mask_im > 0).astype(np.uint8), np.ones((tol * 3, tol * 3), np.uint8))
    out = {"structure": _ratio(gmax, e_str, band)}
    if e_op.any():
        wall_band = (band & inside & (op == 0)).astype(np.uint8)
        out["openings"] = _ratio(gmax, e_op, wall_band if wall_band.sum() > 200 else band)
    return out


def score(out_im, mask_im) -> float:
    s = scores(out_im, mask_im)
    return min(s.values()) if s else 0.0


def check(out: bytes, base: bytes, mask: bytes) -> tuple[bytes, float]:
    import cv2
    try:
        b = _rgb(base)
        o = cv2.resize(_rgb(out), (b.shape[1], b.shape[0]), interpolation=cv2.INTER_LANCZOS4)
        m = cv2.imdecode(__import__("numpy").frombuffer(mask, "uint8"), cv2.IMREAD_GRAYSCALE)
        m = cv2.resize(m, (b.shape[1], b.shape[0]), interpolation=cv2.INTER_NEAREST)
        s0 = score(o, m)
        a = _align(o, b)
        s1 = score(a, m)
        best, sc = (a, s1) if s1 >= s0 else (o, s0)
        return _enc(best, ".jpg"), round(sc, 3)
    except Exception:  # noqa: BLE001
        log.warning("geometry check failed", exc_info=True)
        return out, 0.0


def mask_from_render(base: bytes) -> bytes:
    """Máscara aproximada a partir da própria vista calculada (cortes 3D): zonas de tom → arestas a respeitar."""
    import cv2
    g = cv2.cvtColor(_rgb(base), cv2.COLOR_BGR2GRAY)
    lab = ((g // 24) * 16 + 50).astype("uint8")                  # nunca 40 (reservado aos vãos)
    return _enc(cv2.medianBlur(lab, 5))
