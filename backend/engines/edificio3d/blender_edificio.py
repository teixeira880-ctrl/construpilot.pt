"""
ConstruPilot — Motor Blender «Edifício 3D georreferenciado».

Gera, com a Blender Python API (bpy), um edifício contemporâneo com GEOMETRIA 3D REAL
(paredes com espessura e vãos, caixilharia, vidro, portas, ripado de madeira, lajes,
telhado de duas águas com beirais, rufos e cumeeira), exporta-o em GLB e produz renders
Cycles das fachadas, vista aérea e antes/depois.

Execução (qualquer das duas):
    blender -b -P blender_edificio.py -- parametros.json pasta_saida
    python  blender_edificio.py parametros.json pasta_saida        (com o módulo pip «bpy»)

Sistema local (metros): origem = centro da implantação ao nível do terreno,
+X = Este, +Y = Norte, +Z = altitude. O GLB é exportado já rodado para o azimute real
da fachada principal, pronto para ser colocado no ponto de implantação (ArcGIS Pro / web).
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import bpy
import numpy as np

# ---------------------------------------------------------------------------
# Parâmetros
# ---------------------------------------------------------------------------
DEFAULTS = {
    "largura_m": 12.0,          # frente
    "profundidade_m": 9.0,
    "pisos": 2,
    "pe_direito_m": 3.0,        # altura por piso
    "espessura_parede_m": 0.30,
    "inclinacao_telhado_graus": 30.0,
    "beiral_m": 0.60,
    "azimute_fachada_graus": 180.0,   # direção para onde olha a fachada principal (0=N, 90=E, 180=S)
    "latitude": None, "longitude": None, "altitude_m": None,
    "cor_fachada": [0.93, 0.92, 0.89],
    "cor_telha": [0.36, 0.36, 0.355],
    "ortofoto_path": None,      # imagem do terreno (antes) para envolvente real
    "ortofoto_lado_m": 120.0,   # lado (m) coberto pela ortofoto, centrada na implantação
    "render": {"largura_px": 1600, "altura_px": 1067, "amostras": 64, "vistas": None},
}


def _args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    if len(argv) < 2:
        raise SystemExit("uso: blender -b -P blender_edificio.py -- parametros.json pasta_saida")
    with open(argv[0], encoding="utf-8") as f:
        p = json.load(f)
    out = {**DEFAULTS, **p}
    out["render"] = {**DEFAULTS["render"], **(p.get("render") or {})}
    return out, argv[1]


# ---------------------------------------------------------------------------
# Texturas procedimentais em imagem (exportáveis em GLB)
# ---------------------------------------------------------------------------
RNG = np.random.default_rng(7)


def _noise(n, scale):
    """Ruído suave por interpolação de grelha (sem dependências)."""
    g = RNG.random((scale + 1, scale + 1))
    x = np.linspace(0, scale, n, endpoint=False)
    i = x.astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    a = g[i][:, i] * (1 - f)[None, :] + g[i][:, i + 1] * f[None, :]
    b = g[i + 1][:, i] * (1 - f)[None, :] + g[i + 1][:, i + 1] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def _img(name, rgb):
    h, w, _ = rgb.shape
    im = bpy.data.images.new(name, w, h, alpha=False)
    px = np.ones((h, w, 4), dtype=np.float32)
    px[..., :3] = np.clip(rgb, 0, 1)
    im.pixels.foreach_set(px.ravel())
    im.pack()
    return im


def tex_reboco(cor):
    n = 512
    v = 0.035 * (_noise(n, 24) - 0.5) + 0.02 * (RNG.random((n, n)) - 0.5)
    return _img("reboco", np.dstack([np.full((n, n), c) + v for c in cor]))


def tex_madeira():
    """Ripado vertical: ripas de 0,10 m com junta escura — imagem = 1 m × 1 m."""
    n = 512
    u = np.arange(n) / n
    ripa = (u * 10) % 1.0
    junta = (ripa > 0.90).astype(float)
    idx = (u * 10).astype(int)
    tom = 0.85 + 0.25 * RNG.random(11)[idx]
    veio = 0.5 + 0.5 * np.sin(np.linspace(0, 60, n)[:, None] + 9 * _noise(n, 6) + idx[None, :] * 1.7)
    base = np.array([0.50, 0.31, 0.16])
    rgb = base[None, None, :] * (tom[None, :, None] * (0.88 + 0.12 * veio[..., None]))
    rgb = rgb * (1 - 0.75 * junta[None, :, None])
    return _img("madeira_ripado", rgb)


def tex_telha(cor):
    """Telha cinzenta: fiadas de 0,33 m com sombra e juntas desencontradas — 1 m × 1 m."""
    n = 512
    v = np.arange(n) / n
    u = np.arange(n) / n
    fiada = (v * 3) % 1.0
    row = (v * 3).astype(int)
    sombra = 0.70 + 0.30 * fiada            # mais claro no topo de cada fiada
    off = (row % 2) * 0.125
    junta_v = ((u[None, :] + off[:, None]) * 4) % 1.0 < 0.02
    junta_h = fiada < 0.03
    tom = 0.9 + 0.2 * RNG.random((3, 4))[row % 3][:, ((u * 4).astype(int)) % 4]
    k = sombra[:, None] * tom * (1 - 0.6 * (junta_v | junta_h[:, None]))
    k = k + 0.03 * (_noise(n, 32) - 0.5)
    return _img("telha", np.dstack([c * k for c in cor]))


def tex_relva():
    n = 512
    k = 0.80 + 0.25 * _noise(n, 8) + 0.12 * _noise(n, 64) + 0.06 * (RNG.random((n, n)) - 0.5)
    return _img("relva", np.dstack([0.24 * k, 0.32 * k, 0.15 * k]))


def tex_lajeado():
    n = 512
    u = np.arange(n) / n
    j = ((u * 2) % 1.0 < 0.015)
    k = 0.62 + 0.06 * _noise(n, 20)
    k = k * (1 - 0.45 * (j[None, :] | j[:, None]))
    return _img("lajeado", np.dstack([k, k * 0.98, k * 0.95]))


# ---------------------------------------------------------------------------
# Materiais
# ---------------------------------------------------------------------------
def material(nome, cor=(0.8, 0.8, 0.8), rough=0.6, metal=0.0, imagem=None, vidro=False, emissao=None):
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*cor, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if imagem is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = imagem
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if vidro:
        bsdf.inputs["Transmission Weight"].default_value = 1.0
        bsdf.inputs["IOR"].default_value = 1.45
        bsdf.inputs["Roughness"].default_value = 0.02
        bsdf.inputs["Base Color"].default_value = (0.82, 0.88, 0.90, 1.0)
    if emissao:
        bsdf.inputs["Emission Color"].default_value = (*emissao[0], 1.0)
        bsdf.inputs["Emission Strength"].default_value = emissao[1]
    return m


# ---------------------------------------------------------------------------
# Construtor de malhas por material (uma malha por material → GLB leve)
# ---------------------------------------------------------------------------
class Malha:
    def __init__(self, tex_m=1.0):
        self.v, self.f, self.uv = [], [], []
        self.tex_m = tex_m      # metros cobertos por uma repetição da textura

    def _uvs(self, pts):
        a, b, c = (np.array(pts[i]) for i in range(3))
        nrm = np.cross(b - a, c - a)
        ax = int(np.argmax(np.abs(nrm)))
        s = 1.0 / self.tex_m
        if ax == 2:
            return [(p[0] * s, p[1] * s) for p in pts]
        if ax == 0:
            return [(p[1] * s, p[2] * s) for p in pts]
        return [(p[0] * s, p[2] * s) for p in pts]

    def poly(self, pts):
        base = len(self.v)
        self.v.extend(pts)
        self.f.append(tuple(range(base, base + len(pts))))
        self.uv.append(self._uvs(pts))

    def hexa(self, P):
        """8 vértices: 0-3 base, 4-7 topo (mesma ordem)."""
        for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (3, 0, 4, 7), (1, 2, 6, 5)):
            self.poly([P[i] for i in q])

    def caixa(self, x0, y0, z0, x1, y1, z1):
        x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
        if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
            return
        self.hexa([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                   (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])

    def objeto(self, nome, mat, colecao):
        if not self.f:
            return None
        me = bpy.data.meshes.new(nome)
        me.from_pydata(self.v, [], self.f)
        uvl = me.uv_layers.new(name="UVMap")
        k = 0
        for poly, uvs in zip(me.polygons, self.uv):
            for li, uv in zip(poly.loop_indices, uvs):
                uvl.data[li].uv = uv
            k += 1
        me.validate()
        me.materials.append(mat)
        ob = bpy.data.objects.new(nome, me)
        colecao.objects.link(ob)
        return ob


# ---------------------------------------------------------------------------
# Edifício
# ---------------------------------------------------------------------------
class Edificio:
    def __init__(self, p):
        self.p = p
        self.W = float(p["largura_m"]); self.D = float(p["profundidade_m"])
        self.N = int(p["pisos"]); self.h = float(p["pe_direito_m"])
        self.t = float(p["espessura_parede_m"])
        self.H = self.N * self.h
        self.th = math.radians(float(p["inclinacao_telhado_graus"]))
        self.o = float(p["beiral_m"])
        self.OX, self.OY = -self.W / 2, -self.D / 2
        self.m = {k: Malha(tm) for k, tm in (
            ("reboco", 2.0), ("madeira", 1.0), ("caixilho", 1.0), ("vidro", 1.0), ("telha", 1.0),
            ("zinco", 1.0), ("pedra", 1.0), ("interior", 2.0), ("soalho", 1.0), ("porta", 1.0))}

    # --- referencial de cada fachada: (u ao longo, v altura, w profundidade para dentro)
    def P(self, fach, u, v, w):
        OX, OY, W, D = self.OX, self.OY, self.W, self.D
        if fach == "frente":
            return (OX + u, OY + w, v)
        if fach == "tardoz":
            return (OX + u, OY + D - w, v)
        if fach == "esquerda":
            return (OX + w, OY + u, v)
        return (OX + W - w, OY + u, v)            # direita

    def bloco(self, mat, fach, u0, u1, v0, v1, w0, w1):
        a = self.P(fach, u0, v0, w0); b = self.P(fach, u1, v1, w1)
        self.m[mat].caixa(a[0], a[1], a[2], b[0], b[1], b[2])

    def painel(self, mat, fach, u0, u1, v0, v1, w0, w1, vaos):
        """Painel retangular com aberturas, decomposto em grelha (vãos com ombreiras reais)."""
        us = sorted({u0, u1, *[x for o in vaos for x in (o[0], o[1]) if u0 < x < u1]})
        vs = sorted({v0, v1, *[x for o in vaos for x in (o[2], o[3]) if v0 < x < v1]})
        for j in range(len(vs) - 1):
            run = None
            for i in range(len(us) - 1):
                cu, cv = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
                livre = any(o[0] < cu < o[1] and o[2] < cv < o[3] for o in vaos)
                if not livre:
                    run = (run[0], us[i + 1]) if run else (us[i], us[i + 1])
                elif run:
                    self.bloco(mat, fach, run[0], run[1], vs[j], vs[j + 1], w0, w1); run = None
            if run:
                self.bloco(mat, fach, run[0], run[1], vs[j], vs[j + 1], w0, w1)

    def janela(self, fach, u0, u1, v0, v1, porta=False):
        f, w0, w1 = 0.06, 0.10, 0.18
        c = "caixilho"
        self.bloco(c, fach, u0, u0 + f, v0, v1, w0, w1)
        self.bloco(c, fach, u1 - f, u1, v0, v1, w0, w1)
        self.bloco(c, fach, u0 + f, u1 - f, v1 - f, v1, w0, w1)
        if not porta:
            self.bloco(c, fach, u0 + f, u1 - f, v0, v0 + f, w0, w1)
            n = max(1, math.ceil((u1 - u0) / 1.6))
            for k in range(1, n):
                uc = u0 + (u1 - u0) * k / n
                self.bloco(c, fach, uc - f / 2, uc + f / 2, v0 + f, v1 - f, w0, w1)
            self.bloco("vidro", fach, u0 + f, u1 - f, v0 + f, v1 - f, 0.135, 0.145)
            if v0 > 0.3:   # peitoril em pedra
                self.bloco("pedra", fach, u0 - 0.05, u1 + 0.05, v0 - 0.05, v0, -0.05, 0.12)
        else:
            self.bloco("porta", fach, u0 + f, u1 - f, 0.0, v1 - f, 0.12, 0.17)
            uh = u1 - f - 0.12
            self.bloco(c, fach, uh - 0.03, uh, 0.7, 1.6, 0.06, 0.12)       # puxador vertical

    def construir(self):
        W, D, H, h, t = self.W, self.D, self.H, self.h, self.t
        sup = (H - 0.6)  # topo de vãos do último piso

        # Vãos por fachada (u0, u1, v0, v1) — gerados para qualquer largura/profundidade
        def fila(L, n, larg, v0, v1, margem=1.2):
            if n <= 0:
                return []
            passo = (L - 2 * margem) / n
            return [(margem + passo * (i + 0.5) - larg / 2, margem + passo * (i + 0.5) + larg / 2, v0, v1) for i in range(n)]

        porta_u = (W / 2 - 0.55, W / 2 + 0.55)
        vaos = {"frente": [], "tardoz": [], "esquerda": [], "direita": []}
        # frente — piso 0: envidraçado amplo à esquerda, porta ao centro, janela à direita
        vaos["frente"] += [(1.1, W / 2 - 1.6, 0.15, 2.65), (porta_u[0], porta_u[1], 0.0, 2.35),
                           (W / 2 + 1.5, W - 1.2, 0.9, 2.45)]
        # tardoz — piso 0: janela de correr ampla + janela
        vaos["tardoz"] += [(W / 2 - 2.2, W / 2 + 2.2, 0.0, 2.55), (W - 3.4, W - 1.3, 0.9, 2.4)]
        # laterais — piso 0
        for s in ("esquerda", "direita"):
            vaos[s] += [(D / 2 - 1.5, D / 2 + 1.5, 0.9, 2.4)]
        # pisos superiores
        for k in range(1, self.N):
            z = k * h
            vaos["frente"] += fila(W, 3, 2.0 if W >= 10 else 1.4, z + 0.8, z + 2.4)
            vaos["tardoz"] += fila(W, 3, 1.8 if W >= 10 else 1.2, z + 0.9, z + 2.3)
            for s in ("esquerda", "direita"):
                vaos[s] += [(D / 2 - 1.0, D / 2 + 1.0, z + 0.9, z + 2.3)]

        # Paredes exteriores (reboco branco) com vãos reais
        self.painel("reboco", "frente", 0, W, 0, H, 0, t, vaos["frente"])
        self.painel("reboco", "tardoz", 0, W, 0, H, 0, t, vaos["tardoz"])
        self.painel("reboco", "esquerda", t, D - t, 0, H, 0, t, vaos["esquerda"])
        self.painel("reboco", "direita", t, D - t, 0, H, 0, t, vaos["direita"])

        # Caixilharia preta, vidro, porta
        for fach, lst in vaos.items():
            for (u0, u1, v0, v1) in lst:
                self.janela(fach, u0, u1, v0, v1, porta=(fach == "frente" and v0 == 0.0 and (u0, u1) == porta_u))
                if fach == "tardoz" and v0 == 0.0:   # correr: perfil inferior
                    self.bloco("caixilho", fach, u0, u1, 0.0, 0.06, 0.10, 0.18)

        # Apontamentos em madeira: coluna da entrada (toda a altura) + base do tardoz
        zona = (W / 2 - 1.25, W / 2 + 1.25)
        self.painel("madeira", "frente", zona[0], zona[1], 0, H, -0.04, 0.0,
                    [o for o in vaos["frente"] if o[0] >= zona[0] - 1e-6 and o[1] <= zona[1] + 1e-6]
                    + [(max(o[0], zona[0]), min(o[1], zona[1]), o[2], o[3]) for o in vaos["frente"]
                       if o[1] > zona[0] and o[0] < zona[1]])
        self.painel("madeira", "tardoz", W / 2 - 2.6, W / 2 + 2.6, 0, h - 0.05, -0.04, 0.0, vaos["tardoz"])
        # Pala da entrada (aço escuro)
        self.bloco("zinco", "frente", zona[0] - 0.2, zona[1] + 0.2, 2.55, 2.70, -1.3, 0.0)

        # Lajes e interior
        x0, x1, y0, y1 = self.OX + t, self.OX + W - t, self.OY + t, self.OY + D - t
        self.m["soalho"].caixa(x0, y0, 0.0, x1, y1, 0.03)
        for k in range(1, self.N):
            self.m["interior"].caixa(x0, y0, k * h - 0.22, x1, y1, k * h)
            self.m["soalho"].caixa(x0, y0, k * h, x1, y1, k * h + 0.03)
        self.m["interior"].caixa(x0, y0, H - 0.2, x1, y1, H)
        # parede interior divisória (dá profundidade através do vidro)
        self.m["interior"].caixa(self.OX + W * 0.62, y0, 0.03, self.OX + W * 0.62 + 0.12, y1 - 2.5, H - 0.2)

        # Empenas (triângulos das fachadas laterais, sob o telhado)
        rise = (D / 2) * math.tan(self.th)
        for xa, xb in ((self.OX, self.OX + t), (self.OX + W - t, self.OX + W)):
            a = (self.OY, H); b = (self.OY + D, H); c = (self.OY + D / 2, H + rise)
            m = self.m["reboco"]
            m.poly([(xa, a[0], a[1]), (xa, c[0], c[1]), (xa, b[0], b[1])])
            m.poly([(xb, a[0], a[1]), (xb, b[0], b[1]), (xb, c[0], c[1])])
            m.poly([(xa, a[0], a[1]), (xa, b[0], b[1]), (xb, b[0], b[1]), (xb, a[0], a[1])])
            m.poly([(xa, a[0], a[1]), (xb, a[0], a[1]), (xb, c[0], c[1]), (xa, c[0], c[1])])
            m.poly([(xa, b[0], b[1]), (xa, c[0], c[1]), (xb, c[0], c[1]), (xb, b[0], b[1])])

        self._telhado(rise)

    def _vertente(self, mat, xa, xb, ya, yb, dz0, dz1):
        """Laje inclinada entre ya (beirado) e yb (cumeeira); dz0/dz1 deslocam base/topo."""
        H, OY, tg = self.H, self.OY, math.tan(self.th)
        def z(y):
            d = (y - OY) if y <= OY + self.D / 2 else (OY + self.D - y)
            return H + d * tg
        lo, hi = sorted((ya, yb))
        P = [(xa, lo, z(lo) + dz0), (xb, lo, z(lo) + dz0), (xb, hi, z(hi) + dz0), (xa, hi, z(hi) + dz0),
             (xa, lo, z(lo) + dz1), (xb, lo, z(lo) + dz1), (xb, hi, z(hi) + dz1), (xa, hi, z(hi) + dz1)]
        self.m[mat].hexa(P)

    def _telhado(self, rise):
        W, D, OX, OY, o = self.W, self.D, self.OX, self.OY, self.o
        og = 0.45                                # beiral nas empenas
        dv = 0.22 / math.cos(self.th)            # espessura vertical da cobertura
        xa, xb = OX - og, OX + W + og
        yr = OY + D / 2
        # duas águas em telha cinzenta
        self._vertente("telha", xa, xb, OY - o, yr, 0.0, dv)
        self._vertente("telha", xa, xb, yr, OY + D + o, 0.0, dv)
        # forro dos beirais em madeira (inclinado, sob a laje)
        self._vertente("madeira", xa, xb, OY - o, OY, -0.025, 0.0)
        self._vertente("madeira", xa, xb, OY + D, OY + D + o, -0.025, 0.0)
        for x0, x1 in ((xa, OX), (OX + W, xb)):
            self._vertente("madeira", x0, x1, OY, yr, -0.025, 0.0)
            self._vertente("madeira", x0, x1, yr, OY + D, -0.025, 0.0)
        # guarda-fogos / testeiras nas empenas e tubo de queda de águas
        for x0, x1 in ((xa - 0.04, xa), (xb, xb + 0.04)):
            self._vertente("zinco", x0, x1, OY - o, yr, -0.10, dv + 0.03)
            self._vertente("zinco", x0, x1, yr, OY + D + o, -0.10, dv + 0.03)
        tg = math.tan(self.th)
        ze = self.H - o * tg
        for ye, s in ((OY - o, -1), (OY + D + o, 1)):
            self.m["zinco"].caixa(xa - 0.04, ye, ze - 0.10, xb + 0.04, ye + s * 0.05, ze + dv + 0.02)   # rufo/testeira
            self.m["zinco"].caixa(xa, ye + s * 0.05, ze - 0.12, xb, ye + s * 0.17, ze)                 # caleira
            yw = (OY - 0.06) if s < 0 else (OY + D + 0.06)                                              # junto à parede
            for xd in (OX + 0.25, OX + W - 0.25):                                                       # tubos de queda
                self.m["zinco"].caixa(xd - 0.05, yw - 0.05, 0.0, xd + 0.05, yw + 0.05, ze - 0.25)
                self.m["zinco"].caixa(xd - 0.05, min(yw, ye + s * 0.11), ze - 0.30, xd + 0.05, max(yw, ye + s * 0.11), ze - 0.20)
        # cumeeira
        self.m["zinco"].caixa(xa, yr - 0.16, self.H + rise + dv - 0.05, xb, yr + 0.16, self.H + rise + dv + 0.10)


# ---------------------------------------------------------------------------
# Cena, câmaras e renders
# ---------------------------------------------------------------------------
def limpar():
    for c in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images,
              bpy.data.cameras, bpy.data.lights, bpy.data.collections):
        for x in list(c):
            c.remove(x)


def ceu(scene, azim_sol, elev_sol):
    w = bpy.data.worlds.get("Mundo") or bpy.data.worlds.new("Mundo")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    ok = False
    for tipo in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        try:
            sky.sky_type = tipo
            ok = True
            break
        except Exception:
            continue
    try:
        sky.sun_elevation = math.radians(elev_sol)
        sky.sun_rotation = math.radians(azim_sol)
        sky.sun_disc = False
    except Exception:
        pass
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.35 if ok else 1.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    # Sol físico
    ld = bpy.data.lights.new("Sol", "SUN")
    ld.energy = 3.2
    ld.angle = math.radians(1.5)
    ld.color = (1.0, 0.96, 0.90)
    sol = bpy.data.objects.new("Sol", ld)
    scene.collection.objects.link(sol)
    sol.rotation_euler = (math.radians(90 - elev_sol), 0, math.radians(azim_sol))


def camara(scene, nome, loc, alvo_xy, lente=35.0, orto=None, cota_alvo=None):
    cd = bpy.data.cameras.new(nome)
    cam = bpy.data.objects.new(nome, cd)
    scene.collection.objects.link(cam)
    cam.location = loc
    if orto:
        cd.type = "ORTHO"
        cd.ortho_scale = orto
        cam.rotation_euler = (0, 0, 0)
        return cam
    cd.lens = lente
    cd.sensor_width = 36
    dx, dy = alvo_xy[0] - loc[0], alvo_xy[1] - loc[1]
    dist = math.hypot(dx, dy)
    # câmara horizontal + descentramento: verticais direitas (fotografia de arquitetura)
    cam.rotation_euler = (math.radians(90), 0, math.atan2(dy, dx) - math.pi / 2)
    largura_vista = dist * 36 / lente
    cd.shift_y = ((cota_alvo or loc[2]) - loc[2]) / largura_vista
    return cam


def render(scene, cam, caminho, rp):
    scene.camera = cam
    scene.render.filepath = caminho
    bpy.ops.render.render(write_still=True)


def main():
    p, out_dir = _args()
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    limpar()
    scene = bpy.context.scene
    col_ed = bpy.data.collections.new("Edificio"); scene.collection.children.link(col_ed)
    col_tr = bpy.data.collections.new("Terreno"); scene.collection.children.link(col_tr)

    # Materiais
    M = {
        "reboco": material("Reboco branco", rough=0.85, imagem=tex_reboco(p["cor_fachada"])),
        "madeira": material("Madeira ripado", rough=0.55, imagem=tex_madeira()),
        "caixilho": material("Caixilharia preta", cor=(0.02, 0.02, 0.022), rough=0.35, metal=0.6),
        "vidro": material("Vidro", vidro=True),
        "telha": material("Telha cinzenta", rough=0.85, imagem=tex_telha(p["cor_telha"])),
        "zinco": material("Zinco / aço escuro", cor=(0.12, 0.12, 0.13), rough=0.45, metal=0.7),
        "pedra": material("Pedra clara", cor=(0.78, 0.76, 0.72), rough=0.6),
        "interior": material("Interior", cor=(0.85, 0.84, 0.80), rough=0.9),
        "soalho": material("Soalho", rough=0.5, imagem=bpy.data.images.get("madeira_ripado")),
        "porta": material("Porta madeira", rough=0.45, imagem=bpy.data.images.get("madeira_ripado")),
    }

    ed = Edificio(p)
    ed.construir()
    objs_ed = [o for k, mal in ed.m.items() if (o := mal.objeto(f"ed_{k}", M[k], col_ed))]

    # Terreno: ortofoto real (se fornecida) ou relva + pavimentos
    lado = float(p.get("ortofoto_lado_m") or 120.0)
    orto = p.get("ortofoto_path")
    chao = Malha(tex_m=lado if orto else 4.0)
    chao.poly([(-lado / 2, -lado / 2, 0), (lado / 2, -lado / 2, 0), (lado / 2, lado / 2, 0), (-lado / 2, lado / 2, 0)])
    if orto and os.path.exists(orto):
        img = bpy.data.images.load(orto); img.pack()
        # UV 0..1 sobre o quadrado (Malha usa x/lado → desloca meio)
        chao.uv = [[((x + lado / 2) / lado, (y + lado / 2) / lado) for (x, y, _z) in chao.v]]
        mt_chao = material("Ortofoto", rough=0.95, imagem=img)
    else:
        mt_chao = material("Relva", rough=0.95, imagem=tex_relva())
    chao.objeto("terreno", mt_chao, col_tr)
    pav = Malha(tex_m=1.0)
    W, D = ed.W, ed.D
    pav.caixa(-0.8, -D / 2 - 7.0, 0.0, 0.8, -D / 2 - 1.3, 0.025)                  # caminho de entrada
    pav.caixa(-W / 2 + 0.8, D / 2, 0.0, W / 2 - 0.8, D / 2 + 3.5, 0.025)          # terraço no tardoz
    pav.caixa(-0.8, -D / 2 - 1.3, 0.0, 0.8, -D / 2, 0.08)                          # soleira/patamar
    pav.objeto("pavimentos", material("Lajeado", rough=0.8, imagem=tex_lajeado()), col_tr)

    # Iluminação: sol a ~35° vindo da frente-esquerda (no referencial não rodado)
    ceu(scene, azim_sol=-35.0, elev_sol=34.0)

    # Interior quente (dá vida ao vidro)
    for k in range(ed.N):
        ld = bpy.data.lights.new(f"luz_int_{k}", "AREA"); ld.energy = 140; ld.size = 3.0; ld.color = (1, 0.82, 0.6)
        lo = bpy.data.objects.new(ld.name, ld); scene.collection.objects.link(lo)
        lo.location = (0, 0, k * ed.h + ed.h - 0.4)

    # Render
    rp = p["render"]
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(rp["amostras"])
    try:
        scene.cycles.use_denoising = True
    except Exception:
        pass
    scene.render.resolution_x = int(rp["largura_px"]); scene.render.resolution_y = int(rp["altura_px"])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 90
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

    alt_total = ed.H + (ed.D / 2) * math.tan(ed.th)
    zc = alt_total / 2 + 0.3
    dist = max(ed.W, ed.D) * 1.75 + 2
    cams = {
        "fachada_frente":   camara(scene, "c_frente", (0, -D / 2 - dist, 1.6), (0, 0), cota_alvo=zc),
        "fachada_tardoz":   camara(scene, "c_tardoz", (0, D / 2 + dist, 1.6), (0, 0), cota_alvo=zc),
        "fachada_esquerda": camara(scene, "c_esq", (-W / 2 - dist, 0, 1.6), (0, 0), cota_alvo=zc),
        "fachada_direita":  camara(scene, "c_dir", (W / 2 + dist, 0, 1.6), (0, 0), cota_alvo=zc),
        "perspetiva":       camara(scene, "c_persp", (-dist * 0.85, -D / 2 - dist * 0.95, 1.7), (0, 0), cota_alvo=zc),
        "aerea_telhado":    camara(scene, "c_aerea", (0, 0, 60), (0, 0), orto=max(W, D) * 1.6),
        "aerea_envolvente": camara(scene, "c_aerea2", (0, 0, 80), (0, 0), orto=min(lado, max(W, D) * 4)),
    }
    vistas = rp.get("vistas") or list(cams) + ["antes_perspetiva", "antes_aerea"]
    imagens = {}
    for nome in vistas:
        antes = nome.startswith("antes_")
        base = {"antes_perspetiva": "perspetiva", "antes_aerea": "aerea_envolvente"}.get(nome, nome)
        if base not in cams:
            continue
        for o in objs_ed:
            o.hide_render = antes
        f = os.path.join(out_dir, f"{nome}.jpg")
        render(scene, cams[base], f, rp)
        imagens[nome] = os.path.basename(f)
    for o in objs_ed:
        o.hide_render = False

    # Exportar GLB georreferenciável: rodado para o azimute real, origem = centro no terreno
    az = float(p["azimute_fachada_graus"])
    rot = math.radians(180.0 - az)        # a frente modelada olha para -Y (Sul)
    from mathutils import Matrix
    Rz = Matrix.Rotation(rot, 4, "Z")
    for o in objs_ed:
        o.data.transform(Rz)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs_ed:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs_ed[0]
    glb = os.path.join(out_dir, "edificio.glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True)
    blend = os.path.join(out_dir, "edificio.blend")
    try:
        bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    except Exception:
        blend = None

    # Métricas geométricas reais (verificação)
    nv = sum(len(o.data.vertices) for o in objs_ed)
    nf = sum(len(o.data.polygons) for o in objs_ed)
    manifesto = {
        "motor": f"Blender {bpy.app.version_string}",
        "glb": "edificio.glb",
        "blend": os.path.basename(blend) if blend else None,
        "imagens": imagens,
        "geometria": {"vertices": nv, "faces": nf, "objetos": len(objs_ed),
                      "materiais": [o.active_material.name for o in objs_ed]},
        "dimensoes": {"largura_m": ed.W, "profundidade_m": ed.D, "pisos": ed.N, "pe_direito_m": ed.h,
                      "altura_cumeeira_m": round(alt_total, 2), "beiral_m": ed.o,
                      "inclinacao_graus": float(p["inclinacao_telhado_graus"])},
        "georreferenciacao": {
            "latitude": p.get("latitude"), "longitude": p.get("longitude"), "altitude_m": p.get("altitude_m"),
            "azimute_fachada_graus": az, "origem": "centro da implantação ao nível do terreno",
            "eixos_glb": "glTF Y-up; +X Este, -Z Norte (após conversão Y-up)", "unidades": "metros",
        },
        "duracao_s": round(time.time() - t0, 1),
    }
    with open(os.path.join(out_dir, "manifesto.json"), "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)
    print("CONSTRUPILOT_OK", json.dumps(manifesto, ensure_ascii=False))


if __name__ == "__main__":
    main()
