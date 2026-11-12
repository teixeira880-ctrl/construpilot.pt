"""Vistas FOTORREALISTAS da moradia sem IA nem API: renderização física (path tracing, Mitsuba 3) da geometria REAL lida
nas plantas — mesmas fachadas, pisos, cobertura e vãos que engines.house3d, mesma câmara e mesmo enquadramento.

Materiais reais (reboco texturado, telha cerâmica em fiadas, laje de cobertura em gravilha com platibanda, caixilharia
antracite, vidro duplo refletor, soleiras), relvado, passeio em betão, céu físico com sol (Hosek-Wilkie / sunsky),
iluminação global e sombras suaves; tone mapping fílmico + grão fotográfico. ~5–25 s por vista no CPU.
Sem Mitsuba instalado → None (fica a vista calculada de engines.house3d).
"""
from __future__ import annotations

import io
import logging
import math
import threading

import numpy as np

from engines import house3d as H

log = logging.getLogger(__name__)
_LOCK = threading.Lock()
SPP = 128


def available() -> bool:
    try:
        import mitsuba  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _mi():
    import mitsuba as mi
    if mi.variant() is None:
        for v in ("llvm_ad_rgb", "scalar_rgb"):
            try:
                mi.set_variant(v)
                break
            except Exception:  # noqa: BLE001
                continue
    return mi


# ------------------------------------------------------------------ texturas procedimentais (sRGB → bitmap)
def _noise(h, w, scale, seed):
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(5):
        s = max(2, int(scale / (2 ** o)))
        g = rng.random((h // s + 2, w // s + 2))
        from PIL import Image
        g = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), dtype=float) / 255
        acc += amp * g
        tot += amp
        amp *= 0.5
    return acc / tot


def _tex_plaster(seed=1):
    n = _noise(512, 512, 64, seed)
    base = np.array([0.86, 0.84, 0.79])
    img = base[None, None, :] * (0.93 + 0.12 * n[..., None])
    return np.clip(img, 0, 1)


def _tex_tiles(seed=2):
    h, w = 512, 512
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3))
    rows, cols = 16, 12
    for r in range(rows):
        for c in range(cols):
            col = np.array([0.55, 0.24, 0.14]) * (0.82 + 0.3 * rng.random()) + np.array([0.02, 0.01, 0]) * rng.random()
            y0, y1 = r * h // rows, (r + 1) * h // rows
            off = (w // cols // 2) if r % 2 else 0
            x0, x1 = (c * w // cols + off) % w, ((c + 1) * w // cols + off)
            grad = np.linspace(1.0, 0.72, y1 - y0)[:, None, None]
            if x1 <= w:
                img[y0:y1, x0:x1] = col * grad
            else:
                img[y0:y1, x0:w] = col * grad
                img[y0:y1, 0:x1 - w] = col * grad
            img[y1 - 3:y1, :] *= 0.55
    n = _noise(h, w, 32, seed + 5)
    return np.clip(img * (0.9 + 0.2 * n[..., None]), 0, 1)


def _tex_grass(seed=3):
    n1, n2 = _noise(1024, 1024, 128, seed), _noise(1024, 1024, 8, seed + 1)
    g = np.stack([0.20 + 0.08 * n1, 0.26 + 0.09 * n1, 0.14 + 0.05 * n2], -1)          # relva real (verde-oliva, pouco saturada)
    return np.clip(g * (0.8 + 0.4 * n2[..., None]), 0, 1)


def _tex_gravel(seed=4):
    n = _noise(512, 512, 6, seed)
    return np.clip(np.stack([0.42 + 0.25 * n] * 3, -1) * np.array([1.0, 0.98, 0.94]), 0, 1)


def _tex_concrete(seed=5):
    n = _noise(512, 512, 48, seed)
    img = np.stack([0.66 + 0.1 * n] * 3, -1) * np.array([1.0, 0.99, 0.96])
    img[::128, :] *= 0.7
    img[:, ::128] *= 0.7
    return np.clip(img, 0, 1)


def _bitmap(mi, arr):
    lin = np.power(np.clip(arr, 0, 1), 2.2).astype(np.float32)
    return {"type": "bitmap", "bitmap": mi.Bitmap(lin), "raw": True, "filter_type": "bilinear", "wrap_mode": "repeat"}


# ------------------------------------------------------------------ geometria
def _to_mi(p):
    return tuple(float(v) for v in p)          # Z para cima, como engines.calc_lots.render3d


def _obj(path, polys, uv_scale=(1.0, 1.0), uv_axes=None):
    """Escreve os polígonos (coordenadas do modelo) num OBJ com UV em metros / uv_scale."""
    V, T, F = [], [], []
    for poly in polys:
        p = np.array(poly, dtype=float)
        if uv_axes is None:
            e1 = p[1] - p[0]
            e1 = e1 / (np.linalg.norm(e1) or 1)
            nrm = np.cross(p[1] - p[0], p[2] - p[0])
            nrm = nrm / (np.linalg.norm(nrm) or 1)
            e2 = np.cross(nrm, e1)
        else:
            e1, e2 = uv_axes
        base = len(V)
        for q in p:
            V.append(_to_mi(q))
            T.append(((q - p[0]) @ e1 / uv_scale[0], (q - p[0]) @ e2 / uv_scale[1]))
        for k in range(1, len(p) - 1):
            F.append((base + 1, base + k + 1, base + k + 2))
    with open(path, "w") as f:
        f.writelines(f"v {x:.4f} {y:.4f} {z:.4f}\n" for x, y, z in V)
        f.writelines(f"vt {u:.4f} {v:.4f}\n" for u, v in T)
        f.writelines(f"f {a}/{a} {b}/{b} {c}/{c}\n" for a, b, c in F)
    return path


def _box(x0, y0, z0, x1, y1, z1):
    c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return [[c[i] for i in q] for q in f]


def _geometry(raw):
    env = raw.get("envelope") or {}
    L, W = H._num(env.get("length_x"), 10), H._num(env.get("width_y"), 8)
    lvls = H._levels(raw) or [{"id": "RC", "floor_top": 0.0, "ceiling_height": 2.6}]
    roof = raw.get("roof") or {}
    top = lvls[-1]["floor_top"]
    eaves = H._num(roof.get("eaves_level"), top + H._num(lvls[-1].get("ceiling_height"), 2.6) + 0.3)
    ridge = H._num(roof.get("ridge_level"), eaves)
    sides = H._sides(raw, L, W)
    rtype = str(roof.get("type") or "")
    pitched = ridge > eaves + 0.3 and "plat" not in rtype and "terras" not in rtype
    return L, W, lvls, roof, eaves, ridge, sides, pitched


def _parts(raw):
    """→ dict material → lista de polígonos; mesmas regras que house3d (empenas, vãos, cobertura)."""
    L, W, lvls, roof, eaves, ridge, sides, pitched = _geometry(raw)
    P = {"wall": [], "roof": [], "flat": [], "parapet": [], "frame": [], "glass": [], "door": [], "sill": [], "plinth": []}
    zb = 0.0
    P["wall"] += [f for f in _box(0, 0, zb, L, W, eaves)]
    P["plinth"] += _box(-0.03, -0.03, -0.05, L + 0.03, W + 0.03, 0.35)[2:]
    two = pitched and str(roof.get("type") or "deux_pans").startswith("deux")
    ax_r = str(roof.get("ridge_axis") or ("y" if W > L else "x"))
    ov = 0.45
    if pitched:
        if ax_r == "y":
            rx = H._num(roof.get("ridge_x"), L / 2)
            for y in (0.0, W):
                P["wall"].append([(0, y, eaves), (L, y, eaves), (rx, y, ridge)])
            p1 = [(-ov, -ov, eaves - 0.3), (rx, -ov, ridge), (rx, W + ov, ridge), (-ov, W + ov, eaves - 0.3)]
            p2 = [(L + ov, -ov, eaves - 0.3), (L + ov, W + ov, eaves - 0.3), (rx, W + ov, ridge), (rx, -ov, ridge)]
        else:
            ry = H._num(roof.get("ridge_y"), W / 2)
            for x in (0.0, L):
                P["wall"].append([(x, 0, eaves), (x, W, eaves), (x, ry, ridge)])
            p1 = [(-ov, -ov, eaves - 0.3), (L + ov, -ov, eaves - 0.3), (L + ov, ry, ridge), (-ov, ry, ridge)]
            p2 = [(-ov, W + ov, eaves - 0.3), (-ov, ry, ridge), (L + ov, ry, ridge), (L + ov, W + ov, eaves - 0.3)]
        P["roof"] += [p1, p2]
        for poly in (p1, p2):                                        # espessura da cobertura (beirado)
            P["parapet"].append([(x, y, z - 0.12) for x, y, z in poly[::-1]])
        if not two:
            pass
    else:
        P["flat"].append([(0.2, 0.2, eaves + 0.05), (L - 0.2, 0.2, eaves + 0.05), (L - 0.2, W - 0.2, eaves + 0.05), (0.2, W - 0.2, eaves + 0.05)])
        t = 0.2
        for b in (_box(-0.02, -0.02, eaves, L + 0.02, t, eaves + 0.5), _box(-0.02, W - t, eaves, L + 0.02, W + 0.02, eaves + 0.5),
                  _box(-0.02, 0, eaves, t, W, eaves + 0.5), _box(L - t, 0, eaves, L + 0.02, W, eaves + 0.5)):
            P["parapet"] += b
    # vãos: caixilho (antracite) + vidro recuado + soleira
    for o in raw.get("openings") or []:
        if not isinstance(o, dict) or o.get("side") not in sides:
            continue
        ax, pos, length, n, kind, _l = sides[o["side"]]
        lv = next((x for x in lvls if x.get("id") == o.get("level")), None)
        if lv is None:
            continue
        a, b = H._num(o.get("from")), H._num(o.get("to"))
        if b <= a:
            continue
        z0 = max(0.0, lv["floor_top"] + H._num(o.get("sill")))
        z1 = lv["floor_top"] + H._num(o.get("sill")) + H._num(o.get("height"), 1.2)
        if z1 <= 0.05:
            continue
        if z0 >= eaves - 0.1:                                       # acima do beirado: só existe numa empena
            ax_r = str(roof.get("ridge_axis") or ("y" if W > L else "x"))
            gable = pitched and str(roof.get("type") or "deux_pans").startswith("deux") and ((ax_r == "y") == (ax == "y"))
            if not gable:
                continue
        door = H._num(o.get("sill")) < 0.05 and "jan" not in str(o.get("kind") or "").lower()
        s = 1 if (n[0] + n[1]) > 0 else -1

        def quad(off, a_, b_, z0_, z1_):
            if ax == "x":
                return [(pos + s * off, a_, z0_), (pos + s * off, b_, z0_), (pos + s * off, b_, z1_), (pos + s * off, a_, z1_)]
            return [(a_, pos + s * off, z0_), (b_, pos + s * off, z0_), (b_, pos + s * off, z1_), (a_, pos + s * off, z1_)]
        P["frame"].append(quad(0.012, a, b, z0, z1))
        m = 0.06
        if door:
            P["door"].append(quad(0.018, a + m, b - m, z0 + 0.01, z1 - m))
        else:
            mid = (a + b) / 2
            P["glass"].append(quad(0.018, a + m, mid - 0.025, z0 + m, z1 - m))
            P["glass"].append(quad(0.018, mid + 0.025, b - m, z0 + m, z1 - m))
            # soleira (pedra) saliente
            if ax == "x":
                P["sill"] += _box(min(pos, pos + s * 0.06), a - 0.04, z0 - 0.05, max(pos, pos + s * 0.06), b + 0.04, z0)
            else:
                P["sill"] += _box(a - 0.04, min(pos, pos + s * 0.06), z0 - 0.05, b + 0.04, max(pos, pos + s * 0.06), z0)
    return P


def _camera(raw, view, width, height):
    """Mesma projeção ortográfica e mesmo enquadramento que engines.house3d.render_png (as máscaras de geometria coincidem)."""
    L, W, lvls, roof, eaves, ridge, sides, pitched = _geometry(raw)
    names = list(sides)
    main = next((k for k in names if "princ" in k.lower() or "front" in k.lower()), names[0])
    nm = sides[main][3]
    lat = next((k for k in names if abs(sides[k][3][0] * nm[0] + sides[k][3][1] * nm[1]) < 0.1), names[1])
    nl = sides[lat][3]
    vx, vy = -(nm[0] * 0.78 + nl[0] * 0.62), -(nm[1] * 0.78 + nl[1] * 0.62)
    k = math.hypot(vx, vy)
    vx, vy = vx / k, vy / k
    for _ in range({"main": 0, "aerial": 0, "side": 1, "rear": 2, "side_other": 3}.get(view, 0)):
        vx, vy = -vy, vx
    rx, ry = -vy, vx
    el = math.radians(46 if view == "aerial" else 27)
    cx, cy = L / 2, W / 2

    def P(x, y, z):
        u = (x - cx) * rx + (y - cy) * ry
        d = (x - cx) * vx + (y - cy) * vy
        return u, -(z * math.cos(el)) - d * math.sin(el)
    # mesmos pontos de enquadramento que house3d (faces + chão ±2 m)
    pts = [P(x, y, z) for x in (0, L) for y in (0, W) for z in (0, eaves)]
    pts += [P(x, y, z) for x in (-0.45, L + 0.45) for y in (-0.45, W + 0.45) for z in (eaves - 0.3, ridge if pitched else eaves + 0.45)]
    pts += [P(x, y, 0) for x in (-2, L + 2) for y in (-2, W + 2)]
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    sc = min(width * 0.78 / (maxx - minx), height * 0.74 / (maxy - miny))
    ox = width / 2 - sc * (minx + maxx) / 2
    oy = height * 0.53 - sc * (miny + maxy) / 2
    u0, v0 = (width / 2 - ox) / sc, (height / 2 - oy) / sc
    R = np.array([rx, ry, 0.0])
    U = np.array([math.sin(el) * vx, math.sin(el) * vy, math.cos(el)])
    Fw = np.array([math.cos(el) * vx, math.cos(el) * vy, -math.sin(el)])
    c3 = np.array([cx, cy, 0.0]) + u0 * R + (-v0) * U
    return c3, R, U, Fw, width / 2 / sc, height / 2 / sc


def _tonemap(img):
    a = np.asarray(img, dtype=np.float32)[..., :3]
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    key = np.exp(np.mean(np.log(lum + 1e-4)))
    a = a * (0.24 / max(key, 1e-4))
    A, B, C, D, E = 2.51, 0.03, 2.43, 0.59, 0.14                      # ACES fílmico
    a = np.clip((a * (A * a + B)) / (a * (C * a + D) + E), 0, 1)
    return np.power(a, 1 / 2.2)


def _post(rgb):
    from PIL import Image, ImageEnhance, ImageFilter
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    vig = 1 - 0.18 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    rgb = np.clip(rgb * vig[..., None] + np.random.default_rng(0).normal(0, 0.008, rgb.shape), 0, 1)
    im = Image.fromarray((rgb * 255).astype(np.uint8))
    im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    return ImageEnhance.Contrast(im).enhance(1.05)


def render(raw: dict, width: int = 2560, height: int = 1440, view: str = "main", spp: int = SPP) -> bytes | None:
    """PNG fotorrealista (renderização física) ou None se o motor não estiver disponível."""
    if not available():
        return None
    try:
        with _LOCK:
            return _render(raw, width, height, view, spp)
    except Exception:  # noqa: BLE001 — nunca bloqueia o orçamento: fica a vista calculada
        log.warning("pbr render failed", exc_info=True)
        return None


VIEWS_EYE = {"main": ((0.55, -0.84), 1.6, 1.0), "side": ((0.84, 0.55), 1.6, 1.0), "rear": ((-0.55, 0.84), 1.6, 1.0),
             "side_other": ((-0.84, -0.55), 1.6, 1.0), "aerial": ((0.70, -0.70), None, 1.2)}


def _render(raw, width, height, view, spp):
    """Câmara à altura dos olhos (fotografia de arquitetura) ou drone; materiais e tone mapping de engines.calc_lots.render3d."""
    import os
    import tempfile
    mi = _mi()
    from engines.calc_lots import render3d as R3
    L, W, lvls, roof, eaves, ridge, sides, pitched = _geometry(raw)
    parts = _parts(raw)
    # direção da fachada principal (a mesma regra que house3d)
    names = list(sides)
    main = next((k for k in names if "princ" in k.lower() or "front" in k.lower()), names[0])
    nm = sides[main][3]
    lat = next((k for k in names if abs(sides[k][3][0] * nm[0] + sides[k][3][1] * nm[1]) < 0.1), names[1])
    nl = sides[lat][3]
    dx, dy = nm[0] * 0.80 + nl[0] * 0.55, nm[1] * 0.80 + nl[1] * 0.55
    rot = {"main": 0, "side": 1, "rear": 2, "side_other": 3, "aerial": 0}.get(view, 0)
    for _ in range(rot):
        dx, dy = -dy, dx
    n = math.hypot(dx, dy)
    dx, dy = dx / n, dy / n
    top = ridge if pitched else eaves + 0.5
    cx, cy = L / 2, W / 2
    diag = math.hypot(L, W)
    fov = 40
    dist = (max(diag, top * 1.6) * 0.66) / math.tan(math.radians(fov / 2))
    if view == "aerial":
        d = dist * 1.15
        org = [cx + dx * d * 0.78, cy + dy * d * 0.78, d * 0.62]
        tgt = [cx, cy, 1.2]
    else:
        org = [cx + dx * dist, cy + dy * dist, 1.6]
        tgt = [cx, cy, top * 0.42]
    sol = [-dy * 0.6 - dx * 0.35, dx * 0.6 - dy * 0.35, 0.55]               # sol lateral, de fim de tarde
    with tempfile.TemporaryDirectory() as tmp:
        mats = R3._materiais(tmp)
        ft = os.path.join(tmp, "telha.png")
        open(ft, "wb").write(R3._png(_tex_tiles()))
        mats["telha"] = {"type": "principled", "roughness": 0.55, "specular": 0.35,
                         "base_color": {"type": "bitmap", "filename": ft, "to_uv": mi.ScalarTransform4f().scale([1, 1, 1])}}
        mats["soco"] = {"type": "principled", "base_color": {"type": "rgb", "value": [0.30, 0.29, 0.28]}, "roughness": 0.9}
        mats["porta"] = {"type": "principled", "base_color": {"type": "rgb", "value": [0.07, 0.07, 0.075]}, "roughness": 0.4, "metallic": 0.5}
        mats["pedra"] = {"type": "principled", "base_color": {"type": "rgb", "value": [0.74, 0.72, 0.68]}, "roughness": 0.7}
        mat_of = {"wall": "reboco", "plinth": "soco", "roof": "telha", "flat": "seixo", "parapet": "remate", "frame": "caixilho",
                  "glass": "vidro", "door": "porta", "sill": "pedra"}
        uvs = {"wall": (2.0, 2.0), "roof": (3.6, 2.4), "flat": (1.5, 1.5)}
        sc = {"type": "scene", "integrator": {"type": "path", "max_depth": 7},
              "sensor": {"type": "perspective", "fov": fov, "to_world": mi.ScalarTransform4f().look_at(origin=org, target=tgt, up=[0, 0, 1]),
                         "film": {"type": "hdrfilm", "width": width, "height": height, "rfilter": {"type": "gaussian"}},
                         "sampler": {"type": "independent", "sample_count": int(spp)}},
              "ceu": {"type": "sunsky", "sun_direction": sol, "turbidity": 3.0, "albedo": 0.2}}
        sc.update(mats)
        for name, polys in parts.items():
            if polys:
                sc["m_" + name] = {"type": "obj", "filename": _obj(os.path.join(tmp, name + ".obj"), polys, uvs.get(name, (1.0, 1.0))),
                                   "face_normals": True, "bsdf": {"type": "ref", "id": mat_of[name]}}
        XY = (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
        g = 60.0                                                       # relvado (textura de render3d: UV 0..1 → 60 repetições)
        sc["m_relva"] = {"type": "obj", "face_normals": True, "bsdf": {"type": "ref", "id": "relva"},
                         "filename": _obj(os.path.join(tmp, "relva.obj"), [[(-g, -g, -0.02), (g, -g, -0.02), (g, g, -0.02), (-g, g, -0.02)]],
                                          (2 * g, 2 * g), XY)}
        G = 4000.0                                                     # campo até ao horizonte (sem faixa preta)
        sc["m_campo"] = {"type": "obj", "face_normals": True,
                         "bsdf": {"type": "principled", "base_color": {"type": "rgb", "value": [0.11, 0.15, 0.06]}, "roughness": 1.0},
                         "filename": _obj(os.path.join(tmp, "campo.obj"), [[(-G, -G, -0.05), (G, -G, -0.05), (G, G, -0.05), (-G, G, -0.05)]],
                                          (1.0, 1.0), XY)}
        sc["m_passeio"] = {"type": "obj", "face_normals": True, "bsdf": {"type": "ref", "id": "lajeado"},
                           "filename": _obj(os.path.join(tmp, "passeio.obj"),
                                            [[(-1.2, -1.2, 0.0), (L + 1.2, -1.2, 0.0), (L + 1.2, W + 1.2, 0.0), (-1.2, W + 1.2, 0.0)]],
                                            (8.0, 8.0), XY)}
        img = mi.render(mi.load_dict(sc), spp=int(spp))
        rgb = R3._tonemap(img)
    from PIL import Image, ImageFilter
    im = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.UnsharpMask(radius=1.0, percent=50, threshold=2))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


DOSSIER_VIEWS = (("main", "Perspetiva principal", "Perspective principale"), ("side", "Perspetiva lateral", "Perspective latérale"),
                 ("rear", "Perspetiva posterior", "Perspective arrière"), ("aerial", "Vista aérea", "Vue aérienne"))


def dossier_renders(raw: dict, out_dir, width: int = 0, height: int = 0, spp: int = 0) -> list:
    """Pelo menos 3 perspetivas (aqui 4) da moradia para o dossier: render físico; sem Mitsuba, vistas 3D calculadas.
    → [(caminho PNG, legenda PT, legenda FR)]."""
    import os
    from pathlib import Path
    import time
    width = width or int(os.environ.get("DOSSIER_PBR_W") or 1600)
    height = height or int(os.environ.get("DOSSIER_PBR_H") or 900)
    spp = spp or int(os.environ.get("DOSSIER_PBR_SPP") or 24)
    if os.environ.get("PYTEST_CURRENT_TEST"):                      # testes: imagens pequenas e rápidas
        width, height, spp = 320, 180, 4
    # orçamento de tempo (produção = CPU fraco): passado o limite, as vistas restantes são as vistas 3D rápidas — o estudo
    # nunca fica preso nas imagens (12/11: 26 min em produção)
    budget = float(os.environ.get("DOSSIER_RENDER_BUDGET") or 90)
    t0 = time.monotonic()
    out = []
    for view, pt, fr in DOSSIER_VIEWS:
        slow_ok = available() and (time.monotonic() - t0) < budget
        png = render(raw, width, height, view, spp) if slow_ok else None
        if not png:
            try:
                png = H.render_png(raw, width, height, view)
            except Exception:  # noqa: BLE001
                continue
        p = Path(out_dir) / f"perspetiva_{view}.png"
        p.write_bytes(png)
        out.append((p, pt, fr))
    return out


def add_to_dossier(raw: dict, pdf_path, lang: str = "pt", out_dir=None) -> list:
    """Insere no dossier, logo a seguir à capa, uma página por perspetiva (imagem a toda a largura + legenda).
    Devolve as imagens geradas (para também serem entregues como ficheiros)."""
    from pathlib import Path

    import pymupdf
    pdf_path = Path(pdf_path)
    rs = dossier_renders(raw, out_dir or pdf_path.parent)
    if not rs:
        return []
    doc = pymupdf.open(str(pdf_path))
    W, Hh = (doc[0].rect.width, doc[0].rect.height) if len(doc) else (842, 595)
    fr = str(lang or "").lower().startswith("fr")
    title = "Perspectives 3D du projet" if fr else "Perspetivas 3D do projeto"
    note = ("Rendus physiques (soleil, ciel, matériaux) générés depuis la géométrie lue sur les plans — sans IA."
            if fr else "Renders físicos (sol, céu, materiais) gerados a partir da geometria lida nas plantas — sem IA.")
    for i, (p, pt, frl) in enumerate(rs):
        pg = doc.new_page(pno=1 + i, width=W, height=Hh)
        m = 28
        pg.insert_text((m, m + 14), title if i == 0 else (frl if fr else pt), fontsize=14 if i == 0 else 12, fontname="hebo")
        if i == 0:
            pg.insert_text((m, m + 30), note, fontsize=8, fontname="helv", color=(0.35, 0.35, 0.38))
        top = m + 40
        box = pymupdf.Rect(m, top, W - m, Hh - m - 18)
        pg.insert_image(box, filename=str(p), keep_proportion=True)
        pg.insert_text((m, Hh - m - 4), frl if fr else pt, fontsize=9, fontname="helv", color=(0.3, 0.3, 0.32))
    tmp = pdf_path.with_suffix(".tmp.pdf")
    doc.save(str(tmp), garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf_path)
    return rs
