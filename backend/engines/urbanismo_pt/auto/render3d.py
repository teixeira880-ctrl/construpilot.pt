"""Vistas 3D EXATAS do processo, geradas no servidor (sem navegador, sem GPU).

Rasterizador em numpy com z-buffer: terreno, volumes da casa e da garagem (o contorno real, incluindo o L),
cobertura (plana com platibanda ou duas águas), vãos com as posições e dimensões do processo, piscina.
Estas imagens são a REFERÊNCIA geométrica das imagens fotorrealistas: o modelo de imagem só pode trocar
cores planas por materiais, luz e envolvente — a geometria vem daqui (uma só verdade).
Devolve também a máscara da construção, usada para verificar se a imagem final respeitou a geometria.
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from engines.urbanismo_pt import volumes as V

# Cores-base (0..1) — servem só de referência; a imagem final aplica os materiais reais.
COR = {
    "reboco_branco": (0.93, 0.92, 0.89), "granito": (0.60, 0.59, 0.57), "madeira": (0.62, 0.42, 0.26),
    "xisto": (0.33, 0.31, 0.29), "tijolo": (0.66, 0.34, 0.24), "betao": (0.70, 0.70, 0.68),
    "telha_ceramica": (0.66, 0.30, 0.20), "telha_preta": (0.22, 0.22, 0.24), "zinco": (0.52, 0.55, 0.58),
    "plana_seixo": (0.62, 0.60, 0.56), "vidro": (0.13, 0.18, 0.23), "porta": (0.30, 0.22, 0.16),
    "relva": (0.36, 0.55, 0.28), "terra": (0.62, 0.58, 0.48), "agua": (0.20, 0.55, 0.75), "lajeado": (0.78, 0.76, 0.72),
    "garagem": (0.80, 0.79, 0.76),
}


def _mats_parede(fachada: str) -> Tuple[str, str]:
    """(material principal, material secundário) para fachadas mistas."""
    return {"misto_granito_reboco": ("reboco_branco", "granito"), "misto_madeira_reboco": ("reboco_branco", "madeira"),
            "misto_granito_madeira": ("granito", "madeira")}.get(fachada, (fachada if fachada in COR else "reboco_branco",) * 2)


# ------------------------------------------------------------------ geometria
class Cena:
    def __init__(self):
        self.tris: List[np.ndarray] = []
        self.cores: List[Tuple[float, float, float]] = []
        self.ids: List[int] = []      # 0 = envolvente, 1 = construção (para a máscara)

    def tri(self, a, b, c, cor, obj=1):
        self.tris.append(np.array([a, b, c], dtype=np.float64))
        self.cores.append(cor)
        self.ids.append(obj)

    def quad(self, a, b, c, d, cor, obj=1):
        self.tri(a, b, c, cor, obj)
        self.tri(a, c, d, cor, obj)

    def poligono(self, pts, z, cor, obj=1):
        """Polígono simples (pode ser côncavo, p. ex. L) triangulado por orelhas."""
        P = [tuple(p) for p in pts]
        if len(P) > 3 and P[0] == P[-1]:
            P = P[:-1]
        area = sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))
        if area < 0:
            P = P[::-1]
        idx = list(range(len(P)))
        guard = 0
        while len(idx) > 3 and guard < 500:
            guard += 1
            for k in range(len(idx)):
                i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
                a, b, c = P[i0], P[i1], P[i2]
                if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-12:
                    continue
                if any(_dentro(P[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                    continue
                self.tri((*a, z), (*b, z), (*c, z), cor, obj)
                idx.pop(k)
                break
            else:
                break
        if len(idx) == 3:
            a, b, c = (P[i] for i in idx)
            self.tri((*a, z), (*b, z), (*c, z), cor, obj)


def _dentro(p, a, b, c) -> bool:
    def s(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def construir_cena(m: Dict[str, Any], fachada_sol: str = "frente") -> Tuple[Cena, Dict[str, Any]]:
    """`m` = modelo 3D do processo (rotas urbanismo_auto.modelo3d) — as mesmas medidas das peças desenhadas."""
    cena = Cena()
    mats = m.get("materiais") or {}
    p1, p2 = _mats_parede(mats.get("fachada") or "reboco_branco")
    cob = mats.get("cobertura") or "telha_ceramica"
    ter = m.get("terreno") or []
    xs, ys = [p[0] for p in ter] or [0, 30], [p[1] for p in ter] or [0, 30]
    # envolvente: chão largo + terreno (relva)
    pad = 60.0
    cena.quad((min(xs) - pad, min(ys) - pad, -0.03), (max(xs) + pad, min(ys) - pad, -0.03),
              (max(xs) + pad, max(ys) + pad, -0.03), (min(xs) - pad, max(ys) + pad, -0.03), COR["terra"], 0)
    if len(ter) >= 3:
        cena.poligono(ter, -0.01, COR["relva"], 0)
    # via pública (frente)
    cena.quad((min(xs) - pad, min(ys) - 9, -0.02), (max(xs) + pad, min(ys) - 9, -0.02),
              (max(xs) + pad, min(ys) - 1, -0.02), (min(xs) - pad, min(ys) - 1, -0.02), (0.35, 0.35, 0.37), 0)
    casa_bbox = None
    for vol in m.get("volumes") or []:
        pts = [tuple(p) for p in vol["pts"]]
        h = float(vol.get("altura_m") or 3.0)
        anexo = bool(vol.get("anexo"))
        bx = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        if not anexo:
            casa_bbox = bx if casa_bbox is None else (min(casa_bbox[0], bx[0]), min(casa_bbox[1], bx[1]),
                                                      max(casa_bbox[2], bx[2]), max(casa_bbox[3], bx[3]))
        n = len(pts)
        # composição granito + madeira (desenho de arquiteto): corpo social e garagem em granito; ala dos quartos e
        # panos virados ao pátio do L em ripado de madeira
        comp_gm = mats.get("fachada") == "misto_granito_madeira"
        yc = _rects(pts)[0][3] if (comp_gm and n == 6 and not anexo) else None
        arestas = []
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            # parede contínua que atravessa corpo e ala: divide-se na junção para cada parte ter o seu material
            if yc is not None and abs(a[0] - b[0]) < 1e-6 and min(a[1], b[1]) < yc - 1e-6 < yc + 1e-6 < max(a[1], b[1]):
                arestas += [(a, (a[0], yc)), ((a[0], yc), b)]
            else:
                arestas.append((a, b))
        for a, b in arestas:
            comp = math.hypot(b[0] - a[0], b[1] - a[1])
            if comp < 1e-6:
                continue
            # normal exterior (polígono em sentido anti-horário → exterior à direita)
            nx, ny = (b[1] - a[1]) / comp, -(b[0] - a[0]) / comp
            if anexo:
                mat = "garagem" if p1 in ("reboco_branco", "betao") else p1
            elif yc is not None:
                ym = (a[1] + b[1]) / 2
                ala = ym > yc + 1e-6
                patio = abs(a[1] - yc) < 1e-6 and abs(b[1] - yc) < 1e-6
                mat = "madeira" if (ala or patio) else "granito"
            elif p1 != p2:   # fachada mista: material secundário na fachada do sol e nos panos interiores do L
                lado_sol = (ny < -0.7 and fachada_sol == "frente") or (ny > 0.7 and fachada_sol == "tardoz")
                mat = p2 if lado_sol or (abs(nx) > 0.7 and comp < 10) else p1
            else:
                mat = p1
            cena.quad((*a, 0), (*b, 0), (*b, h), (*a, h), COR[mat])
        # cobertura
        if anexo or vol.get("cobertura") == "plana":
            cena.poligono(pts, h + (0.0 if anexo else 0.45), COR["plana_seixo"])
            if not anexo:   # platibanda
                for i in range(n):
                    a, b = pts[i], pts[(i + 1) % n]
                    cena.quad((*a, h), (*b, h), (*b, h + 0.45), (*a, h + 0.45), COR[p1 if p1 != "madeira" else "betao"])
        else:
            rh = float(vol.get("altura_cobertura_m") or 2.0)
            vrect = {"shape": "l" if len(pts) == 6 else "rectangle"}
            rects = _rects(pts)
            for (x0, y0, x1, y1) in rects:
                _telhado(cena, x0, y0, x1, y1, h, rh, COR[cob], COR[p1])
            del vrect
    # vãos
    bb = casa_bbox or (0, 0, 10, 10)
    for o in m.get("vaos") or []:
        z0, z1 = float(o["z0"]), float(o["z1"])
        cor = COR["porta"] if o.get("tipo") == "porta" else COR["vidro"]
        f = o["fachada"]
        if f in ("frente", "tardoz"):
            yp = o.get("plano_m")
            yp = float(yp) if yp is not None else (bb[1] if f == "frente" else bb[3])
            off = -0.03 if f == "frente" else 0.03
            cena.quad((o["x0"], yp + off, z0), (o["x1"], yp + off, z0), (o["x1"], yp + off, z1), (o["x0"], yp + off, z1), cor)
        else:
            xp = float(o.get("plano_m") if o.get("plano_m") is not None else (bb[0] if f == "esquerda" else bb[2]))
            off = -0.03 if f == "esquerda" else 0.03
            cena.quad((xp + off, o["x0"], z0), (xp + off, o["x1"], z0), (xp + off, o["x1"], z1), (xp + off, o["x0"], z1), cor)
    # piscina + lajeado
    pi = m.get("piscina")
    if pi:
        x, y, l, w = (float(pi[k]) for k in ("x_m", "y_m", "l_m", "w_m"))
        cena.quad((x - 1.2, y - 1.2, 0.0), (x + l + 1.2, y - 1.2, 0.0), (x + l + 1.2, y + w + 1.2, 0.0), (x - 1.2, y + w + 1.2, 0.0),
                  COR["lajeado"], 0)
        cena.quad((x, y, 0.01), (x + l, y, 0.01), (x + l, y + w, 0.01), (x, y + w, 0.01), COR["agua"], 0)
    info = {"casa_bbox": bb, "terreno_bbox": (min(xs), min(ys), max(xs), max(ys)), "piscina": pi}
    return cena, info


def _rects(pts) -> List[Tuple[float, float, float, float]]:
    if len(pts) == 4:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return [(min(xs), min(ys), max(xs), max(ys))]
    (xa, ya), (xb, _), (_, yc), (xd, _), _, (_, yf) = pts[:6]
    return [(xa, ya, xb, yc), (xa, yc, xd, yf)]


def _telhado(cena: Cena, x0, y0, x1, y1, h, rh, cor, cor_parede):
    """Duas águas com cumeeira ao longo do lado maior, beirado de 0,4 m."""
    e = 0.4
    if (x1 - x0) >= (y1 - y0):
        ym = (y0 + y1) / 2
        cena.quad((x0 - e, y0 - e, h - 0.15), (x1 + e, y0 - e, h - 0.15), (x1 + e, ym, h + rh), (x0 - e, ym, h + rh), cor)
        cena.quad((x1 + e, y1 + e, h - 0.15), (x0 - e, y1 + e, h - 0.15), (x0 - e, ym, h + rh), (x1 + e, ym, h + rh), cor)
        cena.tri((x0, y0, h), (x0, y1, h), (x0, ym, h + rh), cor_parede)
        cena.tri((x1, y1, h), (x1, y0, h), (x1, ym, h + rh), cor_parede)
    else:
        xm = (x0 + x1) / 2
        cena.quad((x0 - e, y1 + e, h - 0.15), (x0 - e, y0 - e, h - 0.15), (xm, y0 - e, h + rh), (xm, y1 + e, h + rh), cor)
        cena.quad((x1 + e, y0 - e, h - 0.15), (x1 + e, y1 + e, h - 0.15), (xm, y1 + e, h + rh), (xm, y0 - e, h + rh), cor)
        cena.tri((x0, y0, h), (x1, y0, h), (xm, y0, h + rh), cor_parede)
        cena.tri((x1, y1, h), (x0, y1, h), (xm, y1, h + rh), cor_parede)


# ------------------------------------------------------------------ câmara e rasterização
VISTAS = ("perspetiva", "frente", "tardoz", "aerea", "piscina")


def camara(info: Dict[str, Any], vista: str) -> Tuple[np.ndarray, np.ndarray, float]:
    """Câmaras à altura dos olhos (1,7 m) dentro do terreno, a uma distância que enquadra a casa (~60 % da largura)."""
    x0, y0, x1, y1 = info["casa_bbox"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    fov = 55.0
    larg = max(x1 - x0, y1 - y0, 8.0)
    dist = (larg * 0.62) / math.tan(math.radians(fov) / 2) * 1.05
    alvo = np.array([cx, cy, 2.2])

    def de(az_deg, d, z):
        a = math.radians(az_deg)
        return np.array([cx + d * math.sin(a), cy - d * math.cos(a), z])
    if vista == "frente":
        olho = de(0, dist, 1.7)
    elif vista == "tardoz":   # do jardim de tardoz, a olhar para o pátio/ala
        olho = de(150, dist, 1.7)
    elif vista == "piscina" and info.get("piscina"):   # do lado de lá da piscina, a olhar para a casa (foto de revista)
        pi = info["piscina"]
        px, py = float(pi["x_m"]) + float(pi["l_m"]) / 2, float(pi["y_m"]) + float(pi["w_m"]) / 2
        vx, vy = px - cx, py - cy
        n = math.hypot(vx, vy) or 1.0
        d2 = max(n + float(pi["w_m"]) / 2 + 5.0, dist * 0.9)
        olho = np.array([cx + vx / n * d2 + vy / n * 2.5, cy + vy / n * d2 - vx / n * 2.5, 1.6])
        alvo = np.array([cx, cy, 2.0])
    elif vista == "aerea":
        olho = de(-35, dist * 1.15, dist * 0.75)
        alvo = np.array([cx, cy, 0.5])
    else:   # perspetiva 3/4 a partir do canto da frente
        olho = de(-38, dist, 1.7)
    return olho, alvo, fov


def rasterizar(cena: Cena, olho: np.ndarray, alvo: np.ndarray, fov_deg: float = 50.0, W: int = 1536, H: int = 1024,
               sol: Tuple[float, float, float] = (0.45, -0.55, 0.70), ambiente: float = 0.55) -> Tuple[Image.Image, np.ndarray]:
    fwd = alvo - olho
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0.0, 0.0, 1.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    f = 0.5 * H / math.tan(math.radians(fov_deg) / 2)
    # céu em gradiente
    t = np.linspace(0, 1, H)[:, None]
    ceu = (np.array([0.62, 0.77, 0.92]) * (1 - t) + np.array([0.90, 0.93, 0.96]) * t)
    img = np.broadcast_to(ceu[:, None, :], (H, W, 3)).copy()
    zbuf = np.full((H, W), np.inf)
    mask = np.zeros((H, W), dtype=np.uint8)
    L = np.array(sol, dtype=np.float64)
    L /= np.linalg.norm(L)
    near = 0.1
    tarefas = []
    for tri, cor, obj in zip(cena.tris, cena.cores, cena.ids):
        cz = (tri - olho) @ fwd
        if np.all(cz < near):
            continue
        if np.any(cz < near):   # recorte pelo plano próximo (Sutherland–Hodgman) → leque de triângulos
            poly = []
            for i in range(3):
                a, b = tri[i], tri[(i + 1) % 3]
                za, zb = cz[i], cz[(i + 1) % 3]
                if za >= near:
                    poly.append(a)
                if (za >= near) != (zb >= near):
                    poly.append(a + (b - a) * ((near - za) / (zb - za)))
            for k in range(1, len(poly) - 1):
                tarefas.append((np.array([poly[0], poly[k], poly[k + 1]]), cor, obj))
        else:
            tarefas.append((tri, cor, obj))
    for tri, cor, obj in tarefas:
        rel = tri - olho
        cz = np.maximum(rel @ fwd, near * 0.999)
        cx = rel @ right
        cy = rel @ up
        sx = W / 2 + f * cx / cz
        sy = H / 2 - f * cy / cz
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        nn = np.linalg.norm(n)
        if nn < 1e-12:
            continue
        n /= nn
        if n @ (olho - tri[0]) < 0:
            n = -n
        luz = ambiente + (1 - ambiente) * max(0.0, float(n @ L))
        rgb = np.clip(np.array(cor) * luz, 0, 1)
        xmin, xmax = int(max(0, math.floor(sx.min()))), int(min(W - 1, math.ceil(sx.max())))
        ymin, ymax = int(max(0, math.floor(sy.min()))), int(min(H - 1, math.ceil(sy.max())))
        if xmin > xmax or ymin > ymax:
            continue
        px, py = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
        x0, y0, x1, y1, x2, y2 = sx[0], sy[0], sx[1], sy[1], sx[2], sy[2]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / den
        w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / den
        w2 = 1 - w0 - w1
        dentro = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not dentro.any():
            continue
        invz = w0 / cz[0] + w1 / cz[1] + w2 / cz[2]
        z = 1.0 / np.maximum(invz, 1e-9)
        sub = zbuf[ymin:ymax + 1, xmin:xmax + 1]
        ok = dentro & (z < sub - 1e-4)
        if not ok.any():
            continue
        sub[ok] = z[ok]
        img[ymin:ymax + 1, xmin:xmax + 1][ok] = rgb
        mask[ymin:ymax + 1, xmin:xmax + 1][ok] = 255 if obj == 1 else 0
    # bruma ligeira de profundidade
    prof = np.where(np.isfinite(zbuf), zbuf, 0)
    neb = np.clip((prof - 40) / 160, 0, 0.35)[..., None]
    img = img * (1 - neb) + np.array([0.86, 0.90, 0.94]) * neb
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)), mask


def vista(m: Dict[str, Any], nome: str = "perspetiva", fachada_sol: str = "frente", W: int = 1536, H: int = 1024) -> Dict[str, Any]:
    """PNG exato de uma vista + máscara da construção (PNG de 1 canal)."""
    cena, info = construir_cena(m, fachada_sol)
    olho, alvo, fov = camara(info, nome)
    im, mask = rasterizar(cena, olho, alvo, fov, W, H)
    b1, b2 = io.BytesIO(), io.BytesIO()
    im.save(b1, "PNG")
    Image.fromarray(mask).save(b2, "PNG")
    return {"vista": nome, "png": b1.getvalue(), "mascara_png": b2.getvalue(), "triangulos": len(cena.tris),
            "cobertura_mascara": float((mask > 0).mean())}
