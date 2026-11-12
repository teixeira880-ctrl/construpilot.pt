"""Constrói a cena no Blender a partir de spec.json (blender3d.especificacao) e faz os renders Cycles + exportações.

Uso: python -m engines.urbanismo_pt.auto.blender_run spec.json pasta_saida
Saída na pasta: <camara>_antes.jpg / <camara>_depois.jpg, modelo.glb, cena.blend, georreferencia.json, manifesto.json.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector

# ------------------------------------------------------------------ materiais (procedimentais, em metros)
CORES = {
    "granito": ((0.40, 0.385, 0.36), (0.29, 0.28, 0.265), (0.55, 0.54, 0.51)),
    "xisto": ((0.30, 0.28, 0.25), (0.20, 0.19, 0.17), (0.42, 0.38, 0.32)),
    "tijolo": ((0.55, 0.24, 0.14), (0.42, 0.17, 0.10), (0.78, 0.74, 0.68)),
    "betao": ((0.58, 0.57, 0.55), (0.48, 0.47, 0.45), (0.62, 0.61, 0.59)),
}
COB = {"telha_ceramica": (0.42, 0.11, 0.05), "telha_preta": (0.07, 0.07, 0.075), "zinco": (0.36, 0.38, 0.40),
       "plana_seixo": (0.55, 0.53, 0.50)}
CAIX = {"aluminio_antracite": (0.035, 0.038, 0.042), "aluminio_branco": (0.85, 0.85, 0.84), "madeira": (0.30, 0.17, 0.08),
        "pvc_branco": (0.88, 0.88, 0.87)}


def _bsdf(m):
    nt = m.node_tree
    return nt, nt.nodes.get("Principled BSDF")


def _novo(nome):
    m = bpy.data.materials.new(nome)
    try:
        m.use_nodes = True
    except Exception:  # noqa: BLE001 — Blender 6 já não tem este atributo
        pass
    return m


def _uv_metros(nt):
    """Coordenadas UV (escritas em metros na malha)."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    return tc.outputs["UV"]


def mat_simples(nome, cor, rough=0.6, metal=0.0, spec=0.5):
    m = _novo(nome)
    _, b = _bsdf(m)
    b.inputs["Base Color"].default_value = (*cor, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def _bump(nt, b, altura_out, forca=0.25, dist=0.02):
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = forca
    bp.inputs["Distance"].default_value = dist
    nt.links.new(altura_out, bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])


def mat_pedra(nome, tipo):
    """Cantaria de granito (ou xisto, tijolo, betão): blocos com junta e grão da pedra."""
    c1, c2, junta = CORES[tipo]
    m = _novo(nome)
    nt, b = _bsdf(m)
    uv = _uv_metros(nt)
    br = nt.nodes.new("ShaderNodeTexBrick")
    dims = {"granito": (0.60, 0.30, 0.012), "xisto": (0.40, 0.12, 0.02), "tijolo": (0.24, 0.07, 0.012), "betao": (1.20, 0.60, 0.004)}[tipo]
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = dims[0]
    br.inputs["Row Height"].default_value = dims[1]
    br.inputs["Mortar Size"].default_value = dims[2]
    br.offset = 0.5
    br.inputs["Color1"].default_value = (*c1, 1)
    br.inputs["Color2"].default_value = (*c2, 1)
    br.inputs["Mortar"].default_value = (*junta, 1)
    nt.links.new(uv, br.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 60.0
    nz.inputs["Detail"].default_value = 8.0
    nt.links.new(uv, nz.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "OVERLAY"
    mix.inputs["Factor"].default_value = 0.45
    nt.links.new(br.outputs["Color"], mix.inputs["A"])
    nt.links.new(nz.outputs["Color"], mix.inputs["B"])
    # grão do granito: pintas escuras (biotite) e claras (feldspato)
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    vo.inputs["Scale"].default_value = 220.0
    nt.links.new(uv, vo.inputs["Vector"])
    rp = nt.nodes.new("ShaderNodeValToRGB")
    rp.color_ramp.elements[0].position = 0.05
    rp.color_ramp.elements[0].color = (0.05, 0.05, 0.05, 1)
    rp.color_ramp.elements[1].position = 0.12
    rp.color_ramp.elements[1].color = (0.5, 0.5, 0.5, 1)
    nt.links.new(vo.outputs["Distance"], rp.inputs["Fac"])
    gr = nt.nodes.new("ShaderNodeMix")
    gr.data_type = "RGBA"
    gr.blend_type = "OVERLAY"
    gr.inputs["Factor"].default_value = 0.6 if tipo == "granito" else 0.15
    nt.links.new(mix.outputs["Result"], gr.inputs["A"])
    nt.links.new(rp.outputs["Color"], gr.inputs["B"])
    nt.links.new(gr.outputs["Result"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.72
    h = nt.nodes.new("ShaderNodeMath")
    h.operation = "ADD"
    nt.links.new(br.outputs["Fac"], h.inputs[0])
    nt.links.new(nz.outputs["Fac"], h.inputs[1])
    _bump(nt, b, h.outputs[0], 0.35, 0.015)
    return m


def mat_madeira(nome):
    """Ripado vertical de madeira (réguas de 12 cm com junta escura)."""
    m = _novo(nome)
    nt, b = _bsdf(m)
    uv = _uv_metros(nt)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv, sep.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")          # troca u ↔ v: réguas verticais
    nt.links.new(sep.outputs["Y"], comb.inputs["X"])
    nt.links.new(sep.outputs["X"], comb.inputs["Y"])
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Brick Width"].default_value = 2.4
    br.inputs["Row Height"].default_value = 0.12
    br.inputs["Mortar Size"].default_value = 0.008
    br.inputs["Color1"].default_value = (0.42, 0.24, 0.12, 1)
    br.inputs["Color2"].default_value = (0.33, 0.18, 0.09, 1)
    br.inputs["Mortar"].default_value = (0.05, 0.03, 0.02, 1)
    nt.links.new(comb.outputs[0], br.inputs["Vector"])
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = "Y"
    wv.inputs["Scale"].default_value = 6.0
    wv.inputs["Distortion"].default_value = 6.0
    wv.inputs["Detail"].default_value = 3.0
    nt.links.new(uv, wv.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.25
    nt.links.new(br.outputs["Color"], mix.inputs["A"])
    nt.links.new(wv.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.55
    _bump(nt, b, br.outputs["Fac"], 0.5, 0.01)
    return m


def mat_reboco(nome):
    m = _novo(nome)
    nt, b = _bsdf(m)
    uv = _uv_metros(nt)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 90.0
    nt.links.new(uv, nz.inputs["Vector"])
    b.inputs["Base Color"].default_value = (0.86, 0.85, 0.82, 1)
    b.inputs["Roughness"].default_value = 0.85
    _bump(nt, b, nz.outputs["Fac"], 0.12, 0.004)
    return m


def mat_telha(nome, cor, plana=False):
    m = _novo(nome)
    nt, b = _bsdf(m)
    uv = _uv_metros(nt)
    if plana:
        nz = nt.nodes.new("ShaderNodeTexVoronoi")
        nz.inputs["Scale"].default_value = 40.0
        nt.links.new(uv, nz.inputs["Vector"])
        b.inputs["Base Color"].default_value = (*cor, 1)
        _bump(nt, b, nz.outputs["Distance"], 0.6, 0.02)
        b.inputs["Roughness"].default_value = 0.9
        return m
    wv = nt.nodes.new("ShaderNodeTexWave")                 # canais da telha (ao longo da pendente) + fiadas
    wv.wave_type = "BANDS"
    wv.bands_direction = "X"
    wv.wave_profile = "SIN"
    wv.inputs["Scale"].default_value = 1.0 / 0.21 / 1.0
    nt.links.new(uv, wv.inputs["Vector"])
    fi = nt.nodes.new("ShaderNodeTexWave")
    fi.wave_type = "BANDS"
    fi.bands_direction = "Y"
    fi.wave_profile = "SAW"
    fi.inputs["Scale"].default_value = 1.0 / 0.40
    nt.links.new(uv, fi.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 3.0
    nt.links.new(uv, nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (cor[0] * 0.75, cor[1] * 0.75, cor[2] * 0.75, 1)
    ramp.color_ramp.elements[1].color = (min(1, cor[0] * 1.2), min(1, cor[1] * 1.2), min(1, cor[2] * 1.2), 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    h = nt.nodes.new("ShaderNodeMath")
    h.operation = "ADD"
    nt.links.new(wv.outputs["Fac"], h.inputs[0])
    nt.links.new(fi.outputs["Fac"], h.inputs[1])
    _bump(nt, b, h.outputs[0], 0.7, 0.03)
    b.inputs["Roughness"].default_value = 0.6
    return m


def mat_vidro(nome):
    m = _novo(nome)
    _, b = _bsdf(m)
    b.inputs["Base Color"].default_value = (0.02, 0.025, 0.03, 1)
    b.inputs["Roughness"].default_value = 0.03
    for k in ("Coat Weight", "Clearcoat"):
        if k in b.inputs:
            b.inputs[k].default_value = 1.0
            break
    for k in ("Specular IOR Level", "Specular"):
        if k in b.inputs:
            b.inputs[k].default_value = 1.0
            break
    return m


def mat_relva(nome):
    m = _novo(nome)
    nt, b = _bsdf(m)
    uv = _uv_metros(nt)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.6
    nz.inputs["Detail"].default_value = 6.0
    nt.links.new(uv, nz.inputs["Vector"])
    fino = nt.nodes.new("ShaderNodeTexNoise")
    fino.inputs["Scale"].default_value = 80.0
    nt.links.new(uv, fino.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.10, 0.20, 0.05, 1)
    ramp.color_ramp.elements[1].color = (0.24, 0.34, 0.10, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.95
    _bump(nt, b, fino.outputs["Fac"], 0.6, 0.02)
    return m


def mat_lajeado(nome):
    """Lajeado de granito (acessos e terraço)."""
    m = _novo(nome)
    nt, b = _bsdf(m)
    uv = _uv_metros(nt)
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Brick Width"].default_value = 0.60
    br.inputs["Row Height"].default_value = 0.40
    br.inputs["Mortar Size"].default_value = 0.008
    br.inputs["Color1"].default_value = (0.62, 0.61, 0.58, 1)
    br.inputs["Color2"].default_value = (0.52, 0.51, 0.49, 1)
    br.inputs["Mortar"].default_value = (0.30, 0.29, 0.28, 1)
    nt.links.new(uv, br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.7
    _bump(nt, b, br.outputs["Fac"], 0.3, 0.01)
    return m


def mat_orto(nome, caminho, dentro_relva=None):
    m = _novo(nome)
    nt, b = _bsdf(m)
    if caminho and os.path.exists(caminho):
        tx = nt.nodes.new("ShaderNodeTexImage")
        tx.image = bpy.data.images.load(caminho)
        tx.interpolation = "Cubic"
        nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
    else:
        b.inputs["Base Color"].default_value = (0.25, 0.27, 0.18, 1)
    b.inputs["Roughness"].default_value = 0.95
    return m


def mat_emissao(nome, cor, forca=4.0):
    m = _novo(nome)
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*cor, 1)
    e.inputs["Strength"].default_value = forca
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


# ------------------------------------------------------------------ malhas
def malha(nome, verts, faces, uvs=None, mats=None, idx=None, colecao=None, suave=False):
    me = bpy.data.meshes.new(nome)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    if uvs is not None:
        lay = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                lay.data[li].uv = uvs[vi] if not callable(uvs) else uvs(poly.index, vi)
    for m in mats or []:
        me.materials.append(m)
    if idx is not None:
        for poly, k in zip(me.polygons, idx):
            poly.material_index = k
    me.update()
    if suave:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(nome, me)
    (colecao or bpy.context.scene.collection).objects.link(ob)
    return ob


class Construtor:
    """Acumula quads com UV em metros e índice de material, e cria um só objeto no fim."""

    def __init__(self):
        self.v, self.f, self.uv, self.mi = [], [], [], []

    def quad(self, pts, uvs, mi):
        k = len(self.v)
        self.v += [tuple(p) for p in pts]
        self.uv += [tuple(u) for u in uvs]
        self.f.append(tuple(range(k, k + len(pts))))
        self.mi.append(mi)

    def caixa(self, x0, y0, z0, x1, y1, z1, mi):
        c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        for a, b, cc, d, uvax in ((0, 1, 5, 4, "x"), (1, 2, 6, 5, "y"), (2, 3, 7, 6, "x"), (3, 0, 4, 7, "y"), (4, 5, 6, 7, "xy"), (3, 2, 1, 0, "xy")):
            pts = [c[a], c[b], c[cc], c[d]]
            if uvax == "x":
                uvs = [(p[0], p[2]) for p in pts]
            elif uvax == "y":
                uvs = [(p[1], p[2]) for p in pts]
            else:
                uvs = [(p[0], p[1]) for p in pts]
            self.quad(pts, uvs, mi)

    def criar(self, nome, mats, colecao, solidify=0.0):
        me = bpy.data.meshes.new(nome)
        me.from_pydata(self.v, [], self.f)
        lay = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                lay.data[li].uv = self.uv[me.loops[li].vertex_index][:2]
        for m in mats:
            me.materials.append(m)
        for poly, k in zip(me.polygons, self.mi):
            poly.material_index = k
        me.validate()
        if solidify:                       # paredes contínuas nos cantos: junta os vértices repetidos antes da espessura
            import bmesh
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.002)
            bm.normal_update()
            bm.to_mesh(me)
            bm.free()
        me.update()
        ob = bpy.data.objects.new(nome, me)
        colecao.objects.link(ob)
        if solidify:
            mod = ob.modifiers.new("espessura", "SOLIDIFY")
            mod.thickness = solidify
            mod.offset = -1
        return ob


def _area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def _lado(nx, ny):
    if abs(ny) >= abs(nx):
        return "frente" if ny < 0 else "tardoz"
    return "esquerda" if nx < 0 else "direita"


# ------------------------------------------------------------------ cena
def construir(spec, pasta):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    col = {n: bpy.data.collections.new(n) for n in ("terreno_antes", "terreno_depois", "projeto", "envolvente", "envolvente_antes", "tecnico")}
    for c in col.values():
        sc.collection.children.link(c)

    M = {
        "granito": mat_pedra("Granito", "granito"), "xisto": mat_pedra("Xisto", "xisto"), "tijolo": mat_pedra("Tijolo", "tijolo"),
        "betao": mat_pedra("Betão", "betao"), "madeira": mat_madeira("Madeira ripada"), "reboco": mat_reboco("Reboco branco"),
        "vidro": mat_vidro("Vidro"), "caixilho": mat_simples("Caixilharia", CAIX.get(spec["caixilharia"], CAIX["aluminio_antracite"]), 0.35, 0.6),
        "porta": mat_madeira("Porta"), "garagem": mat_simples("Portão", (0.06, 0.065, 0.07), 0.4, 0.5),
        "rufo": mat_simples("Capeamento", (0.70, 0.70, 0.68), 0.6), "laje": mat_simples("Laje", (0.80, 0.79, 0.76), 0.7),
        "relva": mat_relva("Relva"), "lajeado": mat_lajeado("Lajeado de granito"),
        "vizinho": mat_simples("Envolvente", (0.78, 0.76, 0.72), 0.85), "vizinho_tel": mat_telha("Envolvente telhado", (0.45, 0.22, 0.13)),
        "limite": mat_emissao("Limite do terreno", (1.0, 0.78, 0.05), 6.0), "tronco": mat_simples("Tronco", (0.18, 0.12, 0.08), 0.9),
        "copa": mat_simples("Copa", (0.10, 0.20, 0.06), 0.8),
        "soco": mat_pedra("Soco de granito", "granito"), "ombreira": mat_pedra("Ombreiras de granito", "betao"),
        "pavimento_int": mat_simples("Pavimento interior", (0.35, 0.28, 0.22), 0.4),
    }
    cobm = spec["cobertura_material"]
    M["telha"] = mat_telha("Cobertura", COB.get(cobm, COB["telha_ceramica"]), plana=(cobm == "plana_seixo"))
    if "faixa_granito_reboco" in json.dumps(spec["paredes"]):
        pass
    ordem = list(M.keys())
    mi = {k: i for i, k in enumerate(ordem)}
    lista = [M[k] for k in ordem]

    # chão (antes: relevo natural; depois: plataforma da casa) com o ortofotomapa oficial
    ch = spec["chao"]
    orto = mat_orto("Ortofotomapa", os.path.join(pasta, "orto.jpg"))
    for estado, k in (("antes", 2), ("depois", 3)):
        verts = [(v[0], v[1], v[k]) for v in ch["verts"]]
        malha(f"Terreno ({estado})", verts, ch["faces"], uvs=ch["uvs"], mats=[orto], colecao=col[f"terreno_{estado}"], suave=True)

    zs = [v[2] for v in ch["verts"]]
    xs = [v[0] for v in ch["verts"]]
    ys = [v[1] for v in ch["verts"]]
    cxm, cym = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    R, r0 = 3000.0, 0.0
    saia = []
    for k in range(64):
        a = 2 * math.pi * k / 64
        saia.append((cxm + R * math.cos(a), cym + R * math.sin(a), min(zs) - 1.5))
    malha("Envolvente distante", saia, [list(range(64))], mats=[mat_simples("Campo", (0.16, 0.19, 0.10), 0.95)], colecao=sc.collection)

    # relva do terreno, lajeados e árvores (só «depois»)
    if spec.get("relva"):
        r = spec["relva"]
        malha("Relva do lote", r["verts"], r["faces"], uvs=[(v[0], v[1]) for v in r["verts"]], mats=[M["relva"]], colecao=col["projeto"])
    for pv in spec.get("pavimentos_malha") or []:
        malha(f"Pavimento {pv['tipo']}", pv["verts"], pv["faces"], uvs=[(v[0], v[1]) for v in pv["verts"]], mats=[M["lajeado"]], colecao=col["projeto"])

    # construção: paredes (material por fachada), coberturas, vãos, portão
    b = Construtor()
    pp = spec["piso_a_piso"]
    for vol in spec["volumes"]:
        pts = vol["pts"]
        if _area(pts) < 0:
            pts = pts[::-1]
        z0, h = vol["z0"], vol["h"]
        for i in range(len(pts)):
            (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % len(pts)]
            L = math.hypot(xb - xa, yb - ya)
            if L < 1e-6:
                continue
            nx, ny = (yb - ya) / L, -(xb - xa) / L
            lado = _lado(nx, ny)
            mat = spec["paredes"]["anexo"] if vol["anexo"] else spec["paredes"]["principal"][lado]
            u0 = xa * abs(ny) + ya * abs(nx)
            faixas = [(0.45, pp, "granito"), (pp, h, "reboco")] if mat == "faixa_granito_reboco" and h > pp else [(0.45, h, mat if mat != "faixa_granito_reboco" else "granito")]
            faixas = [(z0, 0.45, "soco")] + faixas
            for za, zb, mm in faixas:
                b.quad([(xa, ya, za), (xb, yb, za), (xb, yb, zb), (xa, ya, zb)],
                       [(u0, za), (u0 + L, za), (u0 + L, zb), (u0, zb)], mi[mm])
    tel, pl = Construtor(), Construtor()
    for cb in spec["coberturas"]:
        x0, y0, x1, y1 = cb["rect"]
        z, H, e = cb["z"], cb["h"], cb["beiral"]
        parede = spec["paredes"]["principal"]
        if cb["tipo"] == "plana" or H <= 0.05:
            pl.quad([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], mi["telha" if cobm == "plana_seixo" else "laje"])
            t = 0.2
            for (ax, ay, bx, by) in ((x0 - 0.05, y0 - 0.05, x1 + 0.05, y0 + t), (x1 - t, y0 - 0.05, x1 + 0.05, y1 + 0.05),
                                     (x0 - 0.05, y1 - t, x1 + 0.05, y1 + 0.05), (x0 - 0.05, y0 - 0.05, x0 + t, y1 + 0.05)):
                pl.caixa(ax, ay, z, bx, by, z + 0.35, mi["rufo"])
            continue
        if cb["tipo"] == "uma_agua":
            sl = H / (y1 - y0)
            pts = [(x0 - e, y0 - e, z - e * sl), (x1 + e, y0 - e, z - e * sl), (x1 + e, y1 + e, z + H + e * sl), (x0 - e, y1 + e, z + H + e * sl)]
            tel.quad(pts, [(p[0], math.hypot(p[1] - y0, p[2] - z)) for p in pts], mi["telha"])
            for xx, lado in ((x0, "esquerda"), (x1, "direita")):
                tri = [(xx, y0, z), (xx, y1, z), (xx, y1, z + H)]
                b.quad(tri if xx == x1 else tri[::-1], [(p[1], p[2]) for p in (tri if xx == x1 else tri[::-1])], mi[_mp(parede[lado])])
            b.quad([(x0, y1, z), (x1, y1, z), (x1, y1, z + H), (x0, y1, z + H)], [(x0, z), (x1, z), (x1, z + H), (x0, z + H)], mi[_mp(parede["tardoz"])])
            continue
        # duas águas: cumeeira ao longo do lado maior
        ao_x = (x1 - x0) >= (y1 - y0)
        if ao_x:
            ym = (y0 + y1) / 2
            sl = H / (ym - y0)
            ze = z - e * sl
            a1 = [(x0 - e, y0 - e, ze), (x1 + e, y0 - e, ze), (x1 + e, ym, z + H), (x0 - e, ym, z + H)]
            a2 = [(x1 + e, y1 + e, ze), (x0 - e, y1 + e, ze), (x0 - e, ym, z + H), (x1 + e, ym, z + H)]
            for pts in (a1, a2):
                tel.quad(pts, [(p[0], math.hypot(p[1] - ym, p[2] - z - H)) for p in pts], mi["telha"])
            for xx, lado in ((x0, "esquerda"), (x1, "direita")):
                tri = [(xx, y0, z), (xx, y1, z), (xx, ym, z + H)]
                tri = tri if xx == x1 else tri[::-1]
                b.quad(tri, [(p[1], p[2]) for p in tri], mi[_mp(parede[lado])])
        else:
            xm = (x0 + x1) / 2
            sl = H / (xm - x0)
            ze = z - e * sl
            a1 = [(x0 - e, y1 + e, ze), (x0 - e, y0 - e, ze), (xm, y0 - e, z + H), (xm, y1 + e, z + H)]
            a2 = [(x1 + e, y0 - e, ze), (x1 + e, y1 + e, ze), (xm, y1 + e, z + H), (xm, y0 - e, z + H)]
            for pts in (a1, a2):
                tel.quad(pts, [(p[1], math.hypot(p[0] - xm, p[2] - z - H)) for p in pts], mi["telha"])
            for yy, lado in ((y0, "frente"), (y1, "tardoz")):
                tri = [(x0, yy, z), (x1, yy, z), (xm, yy, z + H)]
                tri = tri if yy == y0 else tri[::-1]
                b.quad(tri, [(p[0], p[2]) for p in tri], mi[_mp(parede[lado])])
    # recortes dos vãos (atravessam a parede); as faces do recorte ficam com o material da ombreira
    cut = Construtor()
    for o in spec["vaos"]:
        z0c = max(o["z0"], 0.0) if o["tipo"] != "porta" else 0.0
        cut.caixa(o["x0"], o["y"] - 0.6, z0c, o["x1"], o["y"] + 0.6, o["z1"], mi["ombreira"])
    g = spec.get("garagem")
    if g:
        p = g["porta"]
        cut.caixa(p["x0"], p["y"] - 0.6, 0.0, p["x1"], p["y"] + 0.6, p["z1"], mi["ombreira"])
    casa = b.criar("Moradia (projeto)", lista, col["projeto"], solidify=0.30)
    if cut.v:
        cobj = cut.criar("recortes", lista, sc.collection)
        bo = casa.modifiers.new("vaos", "BOOLEAN")
        bo.operation = "DIFFERENCE"
        bo.object = cobj
        try:
            bo.solver = "EXACT"
            bo.material_mode = "TRANSFER"
        except Exception:  # noqa: BLE001
            pass
        cobj.hide_render = True
        cobj.hide_viewport = True
    if tel.v:
        tel.criar("Cobertura (projeto)", lista, col["projeto"], solidify=0.2)
    if pl.v:
        pl.criar("Coberturas planas (projeto)", lista, col["projeto"])

    # caixilharia recuada 12 cm dentro do vão, vidro, peitoril saliente
    v = Construtor()
    for o in spec["vaos"]:
        s_ = -1.0 if o["lado"] == "frente" else 1.0          # sentido para fora
        y = o["y"]
        x0, x1, z0, z1 = o["x0"], o["x1"], max(o["z0"], 0.0), o["z1"]
        fr = 0.065
        ya, yb = y - s_ * 0.10, y - s_ * 0.17               # caixilho dentro do vão
        yv = y - s_ * 0.135
        if o["tipo"] == "porta":
            v.caixa(x0, min(ya, yb), 0.0, x1, max(ya, yb), z1, mi["porta"])
            v.caixa(x0 - 0.1, min(y, y + s_ * 0.6), -0.2, x1 + 0.1, max(y, y + s_ * 0.6), 0.02, mi["rufo"])   # soleira
            continue
        for (ax, az, bx, bz) in ((x0, z0, x1, z0 + fr), (x0, z1 - fr, x1, z1), (x0, z0, x0 + fr, z1), (x1 - fr, z0, x1, z1)):
            v.caixa(ax, min(ya, yb), az, bx, max(ya, yb), bz, mi["caixilho"])
        n_mont = int((x1 - x0) // 1.4)
        for k in range(1, n_mont + 1):
            xm = x0 + (x1 - x0) * k / (n_mont + 1)
            v.caixa(xm - fr / 2, min(ya, yb), z0, xm + fr / 2, max(ya, yb), z1, mi["caixilho"])
        quad = [(x0, yv, z0), (x1, yv, z0), (x1, yv, z1), (x0, yv, z1)]
        v.quad(quad if s_ > 0 else quad[::-1], [(0, 0), (1, 0), (1, 1), (0, 1)], mi["vidro"])
        if o["z0"] > 0.3:     # peitoril de granito, saliente 5 cm
            v.caixa(x0 - 0.04, min(y - s_ * 0.10, y + s_ * 0.05), z0 - 0.05, x1 + 0.04, max(y - s_ * 0.10, y + s_ * 0.05), z0, mi["rufo"])
    # interior escuro atrás dos vidros (a casa não tem interior modelado)
    for vol in spec["volumes"]:
        xs_ = [q[0] for q in vol["pts"]]
        ys_ = [q[1] for q in vol["pts"]]
        v.caixa(min(xs_) + 0.6, min(ys_) + 0.6, 0.0, max(xs_) - 0.6, max(ys_) - 0.6, 0.02, mi["pavimento_int"])
    if g:
        p = g["porta"]
        v.caixa(p["x0"], p["y"] + 0.12, 0.0, p["x1"], p["y"] + 0.18, p["z1"], mi["garagem"])
    if v.v:
        v.criar("Vãos e caixilharia", lista, col["projeto"])

    # árvores simples (copa irregular), só no «depois»
    for i, t in enumerate(spec.get("arvores") or []):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=t["h"] * 0.45, location=(t["x"], t["y"], t["z"] + t["h"] * 0.22))
        tr = bpy.context.active_object
        tr.data.materials.append(M["tronco"])
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=t["r"], location=(t["x"], t["y"], t["z"] + t["h"] * 0.62))
        cp = bpy.context.active_object
        cp.scale = (1.0, 1.0, 0.85)
        cp.data.materials.append(M["copa"])
        dsp = cp.modifiers.new("irregular", "DISPLACE")
        tex = bpy.data.textures.new(f"copa{i}", "CLOUDS")
        tex.noise_scale = 0.7
        dsp.texture = tex
        dsp.strength = t["r"] * 0.45
        for p in cp.data.polygons:
            p.use_smooth = True
        for ob in (tr, cp):
            for c in ob.users_collection:
                c.objects.unlink(ob)
            col["projeto"].objects.link(ob)

    # envolvente (OpenStreetMap)
    for k, vz in enumerate(spec.get("vizinhos") or []):
        e = Construtor()
        pts = vz["pts"] if _area(vz["pts"]) > 0 else vz["pts"][::-1]
        z0, z1 = vz["z0"], vz["z0"] + 0.5 + vz["h"]
        for i in range(len(pts)):
            (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % len(pts)]
            L = math.hypot(xb - xa, yb - ya)
            e.quad([(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)], [(0, z0), (L, z0), (L, z1), (0, z1)], mi["vizinho"])
        e.quad([(x, y, z1) for x, y in pts], [(x, y) for x, y in pts], mi["vizinho_tel"])
        e.criar(f"Edifício existente {k + 1}", lista, col["envolvente_antes" if vz["no_terreno"] else "envolvente"])

    # limite do terreno (só na planta de topo)
    t = spec["terreno"]
    lim = Construtor()
    for i in range(len(t)):
        (xa, ya, za), (xb, yb, zb) = t[i], t[(i + 1) % len(t)]
        L = math.hypot(xb - xa, yb - ya)
        nx, ny = -(yb - ya) / L * 0.15, (xb - xa) / L * 0.15
        lim.quad([(xa - nx, ya - ny, za + 0.3), (xb - nx, yb - ny, zb + 0.3), (xb + nx, yb + ny, zb + 0.3), (xa + nx, ya + ny, za + 0.3)],
                 [(0, 0), (1, 0), (1, 1), (0, 1)], mi["limite"])
    lim.criar("Limite do terreno", lista, col["tecnico"])
    return col


def _mp(mat):
    return "granito" if mat == "faixa_granito_reboco" else mat


def luz(spec):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Céu")
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:  # noqa: BLE001
        pass
    nt = w.node_tree
    sky = nt.nodes.new("ShaderNodeTexSky")
    tipos = sky.bl_rna.properties["sky_type"].enum_items.keys()
    sky.sky_type = "MULTIPLE_SCATTERING" if "MULTIPLE_SCATTERING" in tipos else ("NISHITA" if "NISHITA" in tipos else tipos[0])
    d = spec["sol"]["dir_local"]
    el = math.radians(spec["sol"]["elevacao"])
    rot = math.atan2(d[0], d[1])
    for k, val in (("sun_elevation", el), ("sun_rotation", rot), ("sun_disc", False), ("altitude", 150.0)):
        try:
            setattr(sky, k, val)
        except Exception:  # noqa: BLE001
            pass
    bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = float(os.environ.get("CP_BLENDER_CEU", 0.22))
    nt.links.new(sky.outputs[0], bg.inputs["Color"])
    out = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    ld = bpy.data.lights.new("Sol", "SUN")
    ld.energy = float(os.environ.get("CP_BLENDER_SOL", 3.6))
    ld.angle = math.radians(0.6)
    ld.color = (1.0, 0.95, 0.88)
    ob = bpy.data.objects.new("Sol", ld)
    sc.collection.objects.link(ob)
    ob.rotation_euler = (-Vector(d)).to_track_quat("-Z", "Y").to_euler()


def camara(c, larg, alt):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new(c["id"])
    ob = bpy.data.objects.new(c["id"], cd)
    sc.collection.objects.link(ob)
    ob.location = c["pos"]
    if c.get("ortografica"):
        cd.type = "ORTHO"
        cd.ortho_scale = c["escala"]
        n = Vector((c["norte"][0], c["norte"][1], 0.0)).normalized()
        ob.rotation_euler = Vector((0, 0, -1)).to_track_quat("-Z", "Y").to_euler()
        ang = math.atan2(-n.x, n.y)
        ob.rotation_euler = (0.0, 0.0, ang)
        cd.clip_end = 1000
    else:
        cd.lens = c.get("lente_mm", 35)
        cd.sensor_width = 36
        ob.rotation_euler = (Vector(c["alvo"]) - Vector(c["pos"])).to_track_quat("-Z", "Y").to_euler()
        cd.clip_end = 2000
    sc.camera = ob
    return ob


def renderizar(spec, pasta):
    t0 = time.time()
    col = construir(spec, pasta)
    luz(spec)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = spec["render"]["amostras"]
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:  # noqa: BLE001
        pass
    sc.cycles.max_bounces = 6
    th = os.environ.get("CP_BLENDER_THREADS")
    if th:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = int(th)
    for vt in ("AgX", "Filmic"):
        try:
            sc.view_settings.view_transform = vt
            break
        except Exception:  # noqa: BLE001
            continue
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:  # noqa: BLE001
        pass
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    larg, alt = spec["render"]["largura"], spec["render"]["altura"]

    def estado(nome):
        depois = nome == "depois"
        col["terreno_antes"].hide_render = depois
        col["terreno_depois"].hide_render = not depois
        col["projeto"].hide_render = not depois
        col["envolvente_antes"].hide_render = depois
        col["tecnico"].hide_render = True
    ficheiros, imagens = [], []
    for c in spec["camaras"]:
        camara(c, larg, alt)
        quad = c.get("ortografica")
        sc.render.resolution_x = alt + alt // 3 if quad else larg
        sc.render.resolution_y = alt + alt // 3 if quad else alt
        for est in (("depois",) if c.get("so_depois") else ("antes", "depois")):
            estado(est)
            if quad:
                col["tecnico"].hide_render = False
            nome = f"{c['id']}_{est}.jpg"
            sc.render.filepath = os.path.join(pasta, nome)
            t1 = time.time()
            bpy.ops.render.render(write_still=True)
            ficheiros.append(nome)
            imagens.append({"ficheiro": nome, "camara": c["id"], "titulo": c["titulo"], "estado": est, "segundos": round(time.time() - t1, 1)})
            print(f"[blender] {nome} {time.time() - t1:.1f} s", flush=True)

    # exportações: modelo do «depois» (glb), cena completa (.blend), georreferência
    estado("depois")
    for c in col.values():
        c.hide_viewport = c.hide_render
    col["tecnico"].hide_viewport = True
    try:
        bpy.ops.export_scene.gltf(filepath=os.path.join(pasta, "modelo.glb"), export_format="GLB", use_visible=True,
                                  export_apply=True, export_cameras=False, export_lights=False)
        ficheiros.append("modelo.glb")
    except Exception as e:  # noqa: BLE001
        print("[blender] glb falhou:", e, flush=True)
    for c in col.values():
        c.hide_viewport = False
    try:
        bpy.ops.file.pack_all()
    except Exception:  # noqa: BLE001
        pass
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(pasta, "cena.blend"), compress=True)
    ficheiros.append("cena.blend")
    geo = {**spec["georef"], "sol": spec["sol"], "camaras": spec["camaras"],
           "nota": "Modelo em metros no referencial local (x ao longo da frente, y para o tardoz, z = 0 na soleira). "
                   "Para colocar em SIG: transladar para origem_pt_tm06 e rodar o eixo y para azimute_eixo_y (graus, a partir do norte)."}
    with open(os.path.join(pasta, "georreferencia.json"), "w") as f:
        json.dump(geo, f, ensure_ascii=False, indent=1)
    ficheiros.append("georreferencia.json")
    man = {"ficheiros": ficheiros, "imagens": imagens, "segundos": round(time.time() - t0, 1),
           "blender": bpy.app.version_string, "motor": "Cycles (CPU, path tracing)", "amostras": spec["render"]["amostras"],
           "resolucao": [larg, alt]}
    with open(os.path.join(pasta, "manifesto.json"), "w") as f:
        json.dump(man, f, ensure_ascii=False)
    return man


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        _spec = json.load(f)
    renderizar(_spec, sys.argv[2])
