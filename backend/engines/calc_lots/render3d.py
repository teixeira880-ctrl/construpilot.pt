"""Render 3D fotorrealista gerado a partir do modelo dos planos (gros_oeuvre) — Mitsuba 3 (path tracing, sol + céu físicos).

Geometria = a mesma dos planos de execução: paredes por piso (com a espessura da fachada), lajes e coberturas (com isolamento),
platibandas, terraço, terreno. As fachadas (vãos, revestimentos) são INDICATIVAS quando o modelo não traz `aberturas`:
janelas distribuídas pelas paredes exteriores e envidraçado contínuo na fachada do terraço. Saída: PNG (bytes) por vista.
Dependência: `mitsuba` (pip). Sem Mitsuba → ImportError tratado pelo chamador (o dossier sai sem render).
"""
from __future__ import annotations

import io
import math

import numpy as np

_MI = None


def _mi():
    global _MI
    if _MI is None:
        import mitsuba as mi
        for v in ("llvm_ad_rgb", "scalar_rgb"):
            try:
                mi.set_variant(v)
                break
            except Exception:  # noqa: BLE001
                continue
        _MI = mi
    return _MI


# ------------------------------------------------------------------------------------------------ texturas procedimentais
def _png(arr):
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(np.clip(arr * 255, 0, 255).astype(np.uint8)).save(b, "PNG")
    return b.getvalue()


def _tex_madeira(seed=1):
    """Revestimento vertical de madeira (larício): tábuas de 0,14 m com veio e variação de tom. 512 px = 1,12 m (8 tábuas)."""
    rng = np.random.default_rng(seed)
    H, W = 512, 512
    img = np.zeros((H, W, 3))
    base = np.array([0.55, 0.37, 0.22])
    bw = W // 8
    y = np.arange(H)[:, None]
    for i in range(8):
        tom = base * rng.uniform(0.82, 1.12) + rng.normal(0, 0.015, 3)
        x = np.arange(bw)[None, :]
        veio = 0.06 * np.sin((y / H) * rng.uniform(18, 40) + np.sin(x / 7.0 + rng.uniform(0, 6)) * 1.6)
        ruido = rng.normal(0, 0.025, (H, bw))
        tab = tom[None, None, :] * (1 + veio + ruido)[..., None]
        tab[:, :2] *= 0.45                                   # junta entre tábuas
        img[:, i * bw:(i + 1) * bw] = tab
    return _png(img)


def _tex_relva(seed=2):
    """Relva: manchas grandes (zonas mais secas/mais verdes) + grão fino; mosaico de ~25 m."""
    rng = np.random.default_rng(seed)
    n = 1024
    f = _ruido(n, ((4, 0.5), (16, 0.3), (64, 0.12), (256, 0.08)), seed)
    seco = _ruido(n, ((3, 0.6), (12, 0.4)), seed + 7)
    grao = _ruido(n, ((n, 1.0),), seed + 3)
    c1, c2 = np.array([0.11, 0.20, 0.06]), np.array([0.26, 0.36, 0.11])
    img = c1 + (c2 - c1) * f[..., None]
    sec = np.clip((seco - 0.62) * 3, 0, 1)[..., None] * 0.55
    img = img * (1 - sec) + np.array([0.30, 0.29, 0.14]) * sec
    img = img * (0.82 + 0.36 * grao[..., None])
    return _png(img)


def _ruido(n, oitavas, seed):
    from PIL import Image
    rng = np.random.default_rng(seed)
    f = np.zeros((n, n), np.float32)
    for k, a in oitavas:
        g = rng.normal(0, 1, (k, k)).astype(np.float32)
        f += a * np.asarray(Image.fromarray(g).resize((n, n), Image.BICUBIC))
    return (f - f.min()) / (f.max() - f.min() + 1e-9)


def _tex_altura(seed, oitavas):
    h = _ruido(512, oitavas, seed)
    return _png(np.repeat(h[..., None], 3, axis=2))


def _tex_lajeado(seed=3):
    """Pavimento exterior em lajetas 0,60 × 0,60 m (512 px = 2,4 m)."""
    rng = np.random.default_rng(seed)
    n = 512
    img = np.ones((n, n, 3)) * np.array([0.66, 0.64, 0.60])
    s = n // 4
    for i in range(4):
        for j in range(4):
            img[i * s:(i + 1) * s, j * s:(j + 1) * s] *= rng.uniform(0.92, 1.06)
    img[::s, :] *= 0.55
    img[:, ::s] *= 0.55
    img += rng.normal(0, 0.012, img.shape)
    return _png(img)


# ------------------------------------------------------------------------------------------------ geometria
class _Cena:
    def __init__(self):
        self.objs = {}
        self.n = 0
        self.malhas = []

    def caixa(self, x0, y0, z0, x1, y1, z1, mat, uv=None):
        mi = _mi()
        if x1 - x0 <= 1e-4 or y1 - y0 <= 1e-4 or z1 - z0 <= 1e-4:
            return
        c = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]
        s = [(x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2]
        o = {"type": "cube", "to_world": mi.ScalarTransform4f().translate(c).scale(s), "bsdf": {"type": "ref", "id": mat}}
        self.n += 1
        self.objs[f"o{self.n}"] = o

    def malha(self, nome, v, f, mat):
        """Malha triangular (numpy) → PLY binário temporário."""
        self.malhas.append((nome, np.asarray(v, np.float32), np.asarray(f, np.int32), mat))

    def esfera(self, c, r, mat):
        self.n += 1
        self.objs[f"o{self.n}"] = {"type": "sphere", "center": list(c), "radius": r, "bsdf": {"type": "ref", "id": mat}}

    def cilindro(self, p0, p1, r, mat):
        self.n += 1
        self.objs[f"o{self.n}"] = {"type": "cylinder", "p0": list(p0), "p1": list(p1), "radius": r, "bsdf": {"type": "ref", "id": mat}}


def _materiais(tmp):
    import os
    mi = _mi()
    fm, fr, fl = os.path.join(tmp, "madeira.png"), os.path.join(tmp, "relva.png"), os.path.join(tmp, "lajeado.png")
    fb, fg = os.path.join(tmp, "reboco_h.png"), os.path.join(tmp, "relva_h.png")
    open(fm, "wb").write(_tex_madeira())
    open(fr, "wb").write(_tex_relva())
    open(fl, "wb").write(_tex_lajeado())
    open(fb, "wb").write(_tex_altura(11, ((64, 0.3), (256, 0.4), (512, 0.3))))
    open(fg, "wb").write(_tex_altura(12, ((128, 0.3), (512, 0.7))))

    def bump(fn, esc, k, bsdf):
        return {"type": "bumpmap", "arbitrary": {"type": "bitmap", "raw": True, "filename": fn,
                                                 "to_uv": mi.ScalarTransform4f().scale([esc, esc, 1])}, "scale": k, "bsdf": bsdf}

    def princ(rgb, rough, spec=0.5, metal=0.0):
        return {"type": "principled", "base_color": {"type": "rgb", "value": list(rgb)}, "roughness": rough, "specular": spec, "metallic": metal}

    def tex(fn, rough, esc, spec=0.3, rot=0):
        return {"type": "principled", "base_color": {"type": "bitmap", "filename": fn,
                                                     "to_uv": mi.ScalarTransform4f().rotate([0, 0, 1], rot).scale([esc, esc, 1])},
                "roughness": rough, "specular": spec}
    return {
        "reboco": bump(fb, 6.0, 0.07, princ((0.80, 0.79, 0.76), 0.9, 0.3)),
        "madeira": bump(fb, 4.0, 0.25, tex(fm, 0.7, 4.0)),
        "madeira_r": bump(fb, 4.0, 0.25, tex(fm, 0.7, 4.0, rot=90)),
        "madeira_deck": tex(fm, 0.8, 6.0),
        "vidro": princ((0.010, 0.013, 0.016), 0.0, 1.0),
        "caixilho": princ((0.09, 0.09, 0.10), 0.35, 0.6, 0.7),
        "remate": princ((0.12, 0.12, 0.13), 0.4, 0.5, 0.6),
        "seixo": princ((0.40, 0.39, 0.37), 0.95, 0.2),
        "betao": princ((0.62, 0.61, 0.58), 0.85, 0.3),
        "relva": bump(fg, 1500.0, 1.2, tex(fr, 1.0, 60.0, 0.05)),
        "lajeado": tex(fl, 0.8, 8.0, 0.2),
        "folhagem": {"type": "twosided", "bsdf": princ((0.06, 0.13, 0.035), 0.75, 0.35)},
        "folhagem2": {"type": "twosided", "bsdf": princ((0.11, 0.18, 0.045), 0.75, 0.35)},
        "folhagem3": {"type": "twosided", "bsdf": princ((0.16, 0.20, 0.06), 0.8, 0.3)},
        "tronco": princ((0.25, 0.18, 0.12), 0.9, 0.2),
        "clt": tex(fm, 0.7, 3.0),
    }


def _segs(mu):
    return list(zip(mu["pontos"][:-1], mu["pontos"][1:]))


def _fechado(mu):
    return len(mu["pontos"]) > 3 and abs(mu["pontos"][0][0] - mu["pontos"][-1][0]) < 1e-6 and abs(mu["pontos"][0][1] - mu["pontos"][-1][1]) < 1e-6


def _area_sinal(pts):
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts[:-1], pts[1:]))


def construir(m: dict, opcoes: dict | None = None):
    """→ (_Cena, bbox (x0, x1, y0, y1, z0, z1))."""
    op = opcoes or {}
    cena = _Cena()
    cp = float(m.get("cota_pavimento_m") or 0.0)
    terreno = cp - float(op.get("altura_soco_m", 0.15))
    fach = float(op.get("espessura_fachada_m", 0.18))          # isolamento + revestimento por fora da parede
    xs = [p[0] for mu in m.get("muros") or [] for p in mu["pontos"]] + [g["pos_m"] for g in m["grelhas_x"]]
    ys = [p[1] for mu in m.get("muros") or [] for p in mu["pontos"]] + [g["pos_m"] for g in m["grelhas_y"]]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    zt = max([mu["cota_topo_m"] for mu in m.get("muros") or []] + [lj.get("cota_topo_m") or 0 for lj in m.get("lajes") or []] + [3.0])
    # terreno, soco
    D = 1500
    cena.caixa(bx0 - D, by0 - D, terreno - 0.5, bx1 + D, by1 + D, terreno, "relva")
    niv_ext = sorted({round(mu["cota_base_m"], 3) for mu in m.get("muros") or [] if _fechado(mu) and mu["cota_topo_m"] > cp + 0.5})
    primeiro = niv_ext[0] if niv_ext else cp
    # paredes exteriores por nível (polígonos fechados) com fachada e vãos
    vaos = []
    for mu in m.get("muros") or []:
        if mu["cota_topo_m"] <= cp + 0.5:
            continue
        e = float(mu.get("espessura_m") or 0.2)
        ext = _fechado(mu)
        sg = 1 if _area_sinal(mu["pontos"]) > 0 else -1
        z0, z1 = max(mu["cota_base_m"], terreno), mu["cota_topo_m"]
        superior = mu["cota_base_m"] > primeiro + 0.5
        mat = op.get("material_superior", "madeira") if superior else op.get("material_inferior", "reboco")
        if not ext:
            continue
        for (xa, ya), (xb, yb) in _segs(mu):
            L = math.hypot(xb - xa, yb - ya)
            if L < 1e-3:
                continue
            ux, uy = (xb - xa) / L, (yb - ya) / L
            nx, ny = (uy * sg, -ux * sg)                          # normal exterior
            t_in, t_out = e / 2, e / 2 + fach
            # caixa alinhada aos eixos (as paredes do modelo são ortogonais)
            if abs(ux) > 0.5:
                xa_, xb_ = min(xa, xb) - t_out, max(xa, xb) + t_out
                y0 = ya + ny * t_out if ny < 0 else ya - t_in
                y1 = ya + ny * t_out if ny > 0 else ya + t_in
                cena.caixa(xa_, min(y0, y1), z0, xb_, max(y0, y1), z1, mat + "_r" if mat == "madeira" else mat)
            else:
                ya_, yb_ = min(ya, yb) - t_out, max(ya, yb) + t_out
                x0 = xa + nx * t_out if nx < 0 else xa - t_in
                x1 = xa + nx * t_out if nx > 0 else xa + t_in
                cena.caixa(min(x0, x1), ya_, z0, max(x0, x1), yb_, z1, mat)
            vaos.append(((xa, ya), (xb, yb), (nx, ny), z0, z1, t_out, superior, L))
    # vãos (indicativos ou do modelo)
    lado_terraco = op.get("fachada_envidracada")              # "y+" | "y-" | "x+" | "x-"
    for (a, b, (nx, ny), z0, z1, t_out, sup, L) in vaos:
        if L < 2.0:
            continue
        lado = ("y+" if ny > 0.5 else "y-" if ny < -0.5 else "x+" if nx > 0.5 else "x-")
        grande = (lado == lado_terraco and not sup)
        if grande:
            larg, alt, peit, passo = L * 0.72, min(2.5, z1 - z0 - 0.35), 0.0, None
            cents = [0.5]
        else:
            larg, alt, peit = (1.4, 1.5, 0.9) if not sup else (1.2, 1.6, 0.8)
            n = max(1, int((L - 1.2) // 3.6))
            cents = [(k + 0.5) / n for k in range(n)]
        for c in cents:
            px, py = a[0] + (b[0] - a[0]) * c, a[1] + (b[1] - a[1]) * c
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            off = t_out + 0.012
            zA, zB = z0 + peit + (0.0 if grande else 0.0), z0 + peit + alt
            fr = 0.06
            if not grande:                                          # peitoril metálico
                if abs(ux) > 0.5:
                    yv0 = py + ny * (t_out - 0.02)
                    cena.caixa(px - larg / 2 - 0.08, min(yv0, yv0 + ny * 0.10), zA - fr - 0.04, px + larg / 2 + 0.08, max(yv0, yv0 + ny * 0.10), zA - fr,
                               "caixilho")
                else:
                    xv0 = px + nx * (t_out - 0.02)
                    cena.caixa(min(xv0, xv0 + nx * 0.10), py - larg / 2 - 0.08, zA - fr - 0.04, max(xv0, xv0 + nx * 0.10), py + larg / 2 + 0.08, zA - fr,
                               "caixilho")
            if abs(ux) > 0.5:
                yv = py + ny * off
                cena.caixa(px - larg / 2 - fr, min(yv, yv + ny * 0.03), zA - fr, px + larg / 2 + fr, max(yv, yv + ny * 0.03), zB + fr, "caixilho")
                cena.caixa(px - larg / 2, min(yv, yv + ny * 0.05), zA, px + larg / 2, max(yv, yv + ny * 0.05), zB, "vidro")
                if grande:
                    for k in range(1, 4):
                        xm = px - larg / 2 + larg * k / 4
                        cena.caixa(xm - 0.03, min(yv, yv + ny * 0.07), zA, xm + 0.03, max(yv, yv + ny * 0.07), zB, "caixilho")
            else:
                xv = px + nx * off
                cena.caixa(min(xv, xv + nx * 0.03), py - larg / 2 - fr, zA - fr, max(xv, xv + nx * 0.03), py + larg / 2 + fr, zB + fr, "caixilho")
                cena.caixa(min(xv, xv + nx * 0.05), py - larg / 2, zA, max(xv, xv + nx * 0.05), py + larg / 2, zB, "vidro")
    # lajes / coberturas (com isolamento e remate) + platibandas nas coberturas
    for lj in m.get("lajes") or []:
        if lj.get("piso") == "fundacao" or lj.get("cota_topo_m") is None:
            continue
        x0, x1 = sorted((lj["x0_m"], lj["x1_m"]))
        y0, y1 = sorted((lj["y0_m"], lj["y1_m"]))
        ex = 0.06 + fach
        x0e, x1e = x0 - (ex if abs(x0 - bx0) < 0.3 else 0), x1 + (ex if abs(x1 - bx1) < 0.3 else 0)
        y0e, y1e = y0 - (ex if abs(y0 - by0) < 0.3 else 0), y1 + (ex if abs(y1 - by1) < 0.3 else 0)
        e = float(lj.get("espessura_m") or 0.2)
        topo = lj["cota_topo_m"]
        cobertura = lj.get("piso") == "cobertura" or lj.get("cobertura_terraco")
        cena.caixa(x0e, y0e, topo - e, x1e, y1e, topo, "remate")
        if cobertura:
            iso = float(lj.get("isolamento_m") or 0.2) + 0.12
            cena.caixa(x0e, y0e, topo, x1e, y1e, topo + iso, "remate")
            cena.caixa(x0e + 0.06, y0e + 0.06, topo + iso, x1e - 0.06, y1e - 0.06, topo + iso + 0.02, "seixo")
            h = 0.35
            viz = [l2 for l2 in m.get("lajes") or [] if l2 is not lj and l2.get("cota_topo_m") is not None
                   and abs(l2["cota_topo_m"] - topo) < 0.05 and (l2.get("piso") == "cobertura" or l2.get("cobertura_terraco"))]

            def partilhada(lado):
                for l2 in viz:
                    a0_, a1_ = sorted((l2["x0_m"], l2["x1_m"]))
                    b0_, b1_ = sorted((l2["y0_m"], l2["y1_m"]))
                    if lado == "y0" and abs(b1_ - y0) < 0.05 and a0_ < x1 - 0.1 and a1_ > x0 + 0.1:
                        return True
                    if lado == "y1" and abs(b0_ - y1) < 0.05 and a0_ < x1 - 0.1 and a1_ > x0 + 0.1:
                        return True
                    if lado == "x0" and abs(a1_ - x0) < 0.05 and b0_ < y1 - 0.1 and b1_ > y0 + 0.1:
                        return True
                    if lado == "x1" and abs(a0_ - x1) < 0.05 and b0_ < y1 - 0.1 and b1_ > y0 + 0.1:
                        return True
                return False
            for lado, (a0, b0, a1, b1) in (("y0", (x0e, y0e, x1e, y0e + 0.08)), ("y1", (x0e, y1e - 0.08, x1e, y1e)),
                                           ("x0", (x0e, y0e, x0e + 0.08, y1e)), ("x1", (x1e - 0.08, y0e, x1e, y1e))):
                if not partilhada(lado):
                    cena.caixa(a0, b0, topo + iso, a1, b1, topo + iso + h, "remate")
    # terraço (do modelo ou opção): deck + pala sobre pilares
    for t in op.get("terracos") or []:
        cena.caixa(t["x0"], t["y0"], terreno, t["x1"], t["y1"], t.get("cota", cp) + 0.0, "madeira_deck" if t.get("deck", True) else "lajeado")
        if t.get("coberto"):
            zc = t.get("cota_cobertura", 3.0)
            cena.caixa(t["x0"] - 0.1, t["y0"], zc, t["x1"] + 0.1, t["y1"] + 0.15, zc + 0.30, "remate")
            for xx in (t["x0"] + 0.15, t["x1"] - 0.15):
                cena.caixa(xx - 0.09, t["y1"] - 0.25, t.get("cota", cp), xx + 0.09, t["y1"] - 0.07, zc, "clt")
    # caminho de acesso e vegetação
    cena.caixa(bx0 + (bx1 - bx0) * 0.55, by0 - 9, terreno, bx0 + (bx1 - bx0) * 0.55 + 1.4, by0 - fach - 0.2, terreno + 0.03, "lajeado")
    rng = np.random.default_rng(7)
    cxm, cym = (bx0 + bx1) / 2, (by0 + by1) / 2
    W_, D_ = bx1 - bx0, by1 - by0
    arv = op.get("arvores") or [(bx0 - 14, by1 - 2, 3.0), (bx1 + 10, by1 + 5, 3.4), (bx0 - 11, cym, 2.8), (cxm - W_ * 1.1, by0 - 14, 3.2),
                                (bx1 + 16, cym - 2, 3.0), (bx0 - 18, by1 + 12, 3.3)]
    folhas = {"folhagem": ([], []), "folhagem2": ([], []), "folhagem3": ([], [])}

    def tufo(c, r, mat):
        """Tufo de folhagem: 14 folhas (quadriláteros) orientadas ao acaso dentro de uma esfera de raio r."""
        V, F = folhas[mat]
        npt = 45
        P = np.array(c) + rng.normal(0, r * 0.42, (npt, 3))
        N = rng.normal(0, 1, (npt, 3))
        N /= np.linalg.norm(N, axis=1, keepdims=True)
        A = np.cross(N, np.array([0, 0, 1.0]))
        A[np.linalg.norm(A, axis=1) < 1e-3] = [1.0, 0, 0]
        A /= np.linalg.norm(A, axis=1, keepdims=True)
        B = np.cross(N, A)
        L = rng.uniform(0.05, 0.09, (npt, 1))                    # folha ≈ 10-18 cm, losango alongado
        Wd = L * 0.45
        k = len(V)
        for i in range(npt):
            V += [P[i] - A[i] * L[i], P[i] - B[i] * Wd[i], P[i] + A[i] * L[i], P[i] + B[i] * Wd[i]]
            F += [[k, k + 1, k + 2], [k, k + 2, k + 3]]
            k += 4

    for (tx, ty, r) in arv:                                        # árvore: tronco, 3 pernadas e ~140 tufos de folhas na copa
        h = r * 1.35
        cena.cilindro((tx, ty, terreno), (tx, ty, terreno + h + r * 0.5), 0.10 + r * 0.035, "tronco")
        for k in range(3):
            u = k * 2.1 + rng.uniform(0, 0.6)
            cena.cilindro((tx, ty, terreno + h * 0.8), (tx + math.cos(u) * r * 0.55, ty + math.sin(u) * r * 0.55, terreno + h + r * 0.8), 0.06 + r * 0.01,
                          "tronco")
        for k in range(170):
            v = rng.normal(0, 1, 3)
            v /= np.linalg.norm(v)
            rad = r * (rng.uniform(0.45, 1.0) ** 0.5)
            c = (tx + v[0] * rad * 0.95, ty + v[1] * rad * 0.95, terreno + h + r * 0.85 + v[2] * rad * 0.8)
            tufo(c, r * 0.16, ("folhagem", "folhagem2", "folhagem3")[k % 3])
    for k in range(16):                                            # sebe baixa ao longo da fachada principal
        xx = bx0 + 0.4 + (W_ - 0.8) * (k + 0.5) / 16
        if abs(xx - (bx0 + W_ * 0.55 + 0.7)) < 1.3:
            continue
        for j in range(5):
            tufo((xx + rng.uniform(-0.3, 0.3), by0 - fach - 0.75 + rng.uniform(-0.2, 0.2), terreno + 0.30 + rng.uniform(-0.1, 0.15)), 0.18,
                 ("folhagem", "folhagem2", "folhagem3")[j % 3])
    for mat, (V, F) in folhas.items():
        if V:
            cena.malha(mat, V, F, mat)
    return cena, (bx0, bx1, by0, by1, terreno, zt + 0.6)


def _ply(fn, V, F):
    with open(fn, "wb") as f:
        f.write(f"ply\nformat binary_little_endian 1.0\nelement vertex {len(V)}\nproperty float x\nproperty float y\nproperty float z\n"
                f"element face {len(F)}\nproperty list uchar int vertex_indices\nend_header\n".encode())
        f.write(V.astype("<f4").tobytes())
        fa = np.empty(len(F), dtype=[("n", "u1"), ("i", "<i4", 3)])
        fa["n"] = 3
        fa["i"] = F
        f.write(fa.tobytes())


def _vizinhos(a):
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
    h, w = a.shape[:2]
    return np.stack([p[i:i + h, j:j + w] for i in range(3) for j in range(3) if (i, j) != (1, 1)], 0)


def _despeckle(a):
    """Remove pontos pretos (amostras NaN do bump, espalhadas pelo filtro de reconstrução) e 'fireflies':
    preenche os NaN de fora para dentro (iterativo) e substitui pixels aberrantes pela mediana 3×3."""
    import warnings
    a = np.where(np.isfinite(a), a, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for _ in range(12):
            nan = np.isnan(a).any(axis=2)
            if not nan.any():
                break
            med = np.nanmedian(_vizinhos(a), axis=0)
            a = np.where(nan[..., None] & np.isfinite(med), med, a)
        a = np.nan_to_num(a, nan=0.0)
        med = np.median(_vizinhos(a), axis=0)
    lum = lambda x: 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]
    la, lm = lum(a), lum(med)
    mau = (la < 0.2 * lm) | (la > 4.0 * lm + 0.05)
    return np.where(mau[..., None], med, a)


def _tonemap(img):
    a = np.array(img)[..., :3].astype(np.float64)
    a = _despeckle(a)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    key = math.exp(float(np.mean(np.log(lum + 1e-4))))
    x = a * (0.15 / key)
    x = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)          # ACES (Narkowicz)
    x = np.clip(x, 0, 1)
    x = np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)
    h, w = x.shape[:2]                                                   # vinheta suave + ligeiro calor (gradação fotográfica)
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
    x = x * (1 - 0.18 * np.clip(r2, 0, 1.5) ** 1.5)[..., None]
    x = x * np.array([1.02, 1.0, 0.97])
    return np.clip(x, 0, 1)


def render(m: dict, opcoes: dict | None = None, largura=1600, altura=900, spp=96, orcamento_s: float | None = None) -> list[tuple[str, bytes]]:
    """→ [(nome da vista, PNG)] — vista principal, vista do terraço, vista aérea."""
    import os
    import tempfile
    mi = _mi()
    op = opcoes or {}
    with tempfile.TemporaryDirectory() as tmp:
        mats = _materiais(tmp)
        cena, (x0, x1, y0, y1, z0, z1) = construir(m, op)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        diag = math.hypot(x1 - x0, y1 - y0)
        alvo_z = z0 + (z1 - z0) * 0.42
        fov = 38
        dist = (diag * 0.62) / math.tan(math.radians(fov / 2))
        sol = op.get("sol", [-0.45, -0.75, 0.55])
        vistas = op.get("vistas") or [
            ("principal", (0.55, -0.84), 1.55, 1.05),
            ("terraco", (-0.62, 0.78), 1.55, 1.05),
            ("aerea", (0.70, -0.70), None, 1.25),
        ]
        out = []
        import time
        t0 = time.time()
        for nome, (dx, dy), h, k in vistas:
            if out and orcamento_s and (time.time() - t0) * (len(out) + 1) / len(out) > orcamento_s:
                break                                          # orçamento de tempo: a vista seguinte não caberia
            n = math.hypot(dx, dy)
            dx, dy = dx / n, dy / n
            d = dist * k
            if h is None:
                org = [cx + dx * d * 0.78, cy + dy * d * 0.78, z0 + d * 0.62]
                tgt = [cx, cy, z0 + 1.2]
            else:
                org = [cx + dx * d, cy + dy * d, z0 + h]
                tgt = [cx, cy, alvo_z]
            sc = {"type": "scene", "integrator": {"type": "path", "max_depth": 7},
                  "sensor": {"type": "perspective", "fov": fov, "to_world": mi.ScalarTransform4f().look_at(origin=org, target=tgt, up=[0, 0, 1]),
                             "film": {"type": "hdrfilm", "width": largura, "height": altura, "rfilter": {"type": "gaussian"}},
                             "sampler": {"type": "independent", "sample_count": spp}},
                  "ceu": {"type": "sunsky", "sun_direction": sol, "turbidity": 3.0, "albedo": 0.2}}
            sc.update({k2: v for k2, v in mats.items()})
            sc.update(cena.objs)
            for (nm, V, F, mat) in cena.malhas:
                fn = os.path.join(tmp, f"{nm}.ply")
                if not os.path.exists(fn):
                    _ply(fn, V, F)
                sc["m_" + nm] = {"type": "ply", "filename": fn, "bsdf": {"type": "ref", "id": mat}, "face_normals": True}
            scene = mi.load_dict(sc)
            img = mi.render(scene, spp=spp)
            out.append((nome, _png(_tonemap(img))))
        return out
