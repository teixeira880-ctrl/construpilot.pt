"""Ligação ao BIM: o terreno como modelo IFC georreferenciado e o modelo IFC do projeto implantado no terreno.

- `ifc_terreno`: IFC 4 (ISO 16739-1:2018) escrito diretamente em STEP, sem dependências — IfcSite com IfcMapConversion
  para PT-TM06 (EPSG:3763, altitudes no datum de Cascais), terreno natural do MDT como IfcGeographicElement
  (TERRAIN, IfcTriangulatedFaceSet), limite do prédio, zona livre para edificar e implantação recomendada (volume),
  com Psets dos resultados da análise. Abre-se em Revit, Archicad, BIMcollab, Solibri ou no visualizador /bim.
- `ler_modelo_ifc`: lê um IFC do utilizador (IfcOpenShell, quando instalado) → pegada, orientação, n.º de pisos e
  altura, para implantar esse edifício no terreno em vez de um retângulo genérico.
- `georreferenciar_ifc`: escreve no IFC do utilizador a IfcMapConversion da implantação escolhida (posição, rotação e
  cota de soleira), para o projeto abrir já no sítio certo em qualquer programa BIM.
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from engines.mdt_pt import analise as AN
from engines.mdt_pt.geotiff import Raster

_NS = uuid.UUID("0e7c4b9a-3f51-4c1e-8d2a-7b6f15c3a9d4")      # espaço de nomes ConstruPilot — viabilidade
_B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
PE_DIREITO_PISO = 3.0


def guid(*partes) -> str:
    """GlobalId IFC (22 carateres) determinístico."""
    n = uuid.uuid5(_NS, ":".join(str(p) for p in partes)).int
    out = []
    for _ in range(22):
        out.append(_B64[n % 64])
        n //= 64
    return "".join(reversed(out))


def _s(txt: Optional[str]) -> str:
    """Cadeia STEP (ISO 10303-21): apóstrofos duplicados, não-ASCII em \\X2\\…\\X0\\."""
    if txt is None:
        return "$"
    out, buf = [], []
    for ch in str(txt):
        if 32 <= ord(ch) < 127:
            if buf:
                out.append("\\X2\\" + "".join(f"{ord(c):04X}" for c in buf) + "\\X0\\")
                buf = []
            out.append("''" if ch == "'" else "\\\\" if ch == "\\" else ch)
        else:
            buf.append(ch)
    if buf:
        out.append("\\X2\\" + "".join(f"{ord(c):04X}" for c in buf) + "\\X0\\")
    return "'" + "".join(out) + "'"


def _f(v: float) -> str:
    t = f"{float(v):.4f}".rstrip("0")
    return t + "0" if t.endswith(".") else t


def _dms(graus: float) -> str:
    s = -1 if graus < 0 else 1
    g = abs(graus)
    d = int(g)
    m = int((g - d) * 60)
    sec = (g - d - m / 60) * 3600
    si = int(sec)
    mi = int(round((sec - si) * 1e6))
    return f"({s * d},{s * m},{s * si},{s * mi})"


class _Step:
    def __init__(self):
        self.linhas: List[str] = []

    def add(self, txt: str) -> str:
        self.linhas.append(txt)
        return f"#{len(self.linhas)}"


def _malha(r: Raster, mascara_zona: np.ndarray, max_lado: int = 140) -> Tuple[np.ndarray, List[Tuple[int, int, int]]]:
    """Vértices (x, y, z TM) e triângulos do MDT dentro da zona (prédio + margem)."""
    passo = max(1, int(math.ceil(max(mascara_zona.shape) / max_lado)))
    z = AN._preencher_nan(r.z.astype(np.float64))
    xc, yc = AN.centros(r)
    I = np.arange(0, z.shape[0], passo)
    J = np.arange(0, z.shape[1], passo)
    sub = mascara_zona[np.ix_(I, J)]
    idx = -np.ones(sub.shape, dtype=np.int64)
    pts = []
    for a, i in enumerate(I):
        for b, j in enumerate(J):
            if sub[a, b]:
                idx[a, b] = len(pts)
                pts.append((xc[j], yc[i], z[i, j]))
    tris = []
    for a in range(len(I) - 1):
        for b in range(len(J) - 1):
            p, q, s_, t = idx[a, b], idx[a, b + 1], idx[a + 1, b], idx[a + 1, b + 1]
            if p >= 0 and q >= 0 and s_ >= 0:
                tris.append((p + 1, s_ + 1, q + 1))
            if q >= 0 and t >= 0 and s_ >= 0:
                tris.append((q + 1, s_ + 1, t + 1))
    return np.asarray(pts, dtype=float), tris


def ifc_terreno(r: Raster, mascara: np.ndarray, anel_tm: Sequence[Sequence[float]], resultado: Dict[str, Any],
                nome: str = "Terreno", implantacao: Optional[Dict[str, Any]] = None,
                zona_livre_tm: Optional[List[List[List[float]]]] = None, margem_m: float = 15.0) -> bytes:
    from scipy import ndimage
    from engines.mdt_pt import pttm06 as TM

    zona = ndimage.binary_dilation(mascara, iterations=max(1, int(margem_m / r.px)))
    pts, tris = _malha(r, zona)
    if len(tris) == 0:
        raise ValueError("terreno demasiado pequeno para gerar a malha IFC")
    anel = np.asarray(anel_tm, dtype=float)
    ox, oy = float(np.round(anel[:, 0].mean(), 0)), float(np.round(anel[:, 1].mean(), 0))
    oz = float(np.floor(np.nanmin(pts[:, 2])))
    la0, lo0 = TM.ponto_ll(ox, oy)
    chave = f"{ox:.0f}:{oy:.0f}"
    W = _Step()
    a = W.add
    org = a(f"IFCORGANIZATION($,{_s('ConstruPilot')},$,$,$)")
    app = a(f"IFCAPPLICATION({org},'1.0',{_s('ConstruPilot — Viabilidade do terreno')},'CP-VIAB')")
    pes = a(f"IFCPERSON($,{_s('ConstruPilot')},$,$,$,$,$,$)")
    po = a(f"IFCPERSONANDORGANIZATION({pes},{org},$)")
    oh = a(f"IFCOWNERHISTORY({po},{app},$,.ADDED.,$,$,$,{int(time.time())})")
    u_l = a("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)")
    u_a = a("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)")
    u_v = a("IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)")
    u_r = a("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")
    units = a(f"IFCUNITASSIGNMENT(({u_l},{u_a},{u_v},{u_r}))")
    o0 = a("IFCCARTESIANPOINT((0.,0.,0.))")
    ax0 = a(f"IFCAXIS2PLACEMENT3D({o0},$,$)")
    norte = a("IFCDIRECTION((0.,1.))")
    ctx = a(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,{ax0},{norte})")
    body = a(f"IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,{ctx},$,.MODEL_VIEW.,$)")
    anot = a(f"IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Annotation','Model',*,*,*,*,{ctx},$,.MODEL_VIEW.,$)")
    proj = a(f"IFCPROJECT('{guid('proj', chave)}',{oh},{_s(nome)},{_s('Estudo de viabilidade do terreno')},$,$,$,({ctx}),{units})")
    crs = a(f"IFCPROJECTEDCRS('EPSG:3763',{_s('ETRS89 / Portugal TM06')},'ETRS89',{_s('Cascais Helmert 1938 (altitudes)')},"
            f"'Transverse Mercator',$,{u_l})")
    a(f"IFCMAPCONVERSION({ctx},{crs},{_f(ox)},{_f(oy)},{_f(oz)},1.,0.,1.)")
    sp = a(f"IFCLOCALPLACEMENT($,{ax0})")
    est = resultado.get("relevo") or {}
    site = a(f"IFCSITE('{guid('site', chave)}',{oh},{_s(nome)},{_s('Prédio analisado')},$,{sp},$,$,.ELEMENT.,"
             f"{_dms(la0)},{_dms(lo0)},{_f(oz)},$,$)")
    a(f"IFCRELAGGREGATES('{guid('agg', chave)}',{oh},$,$,{proj},({site}))")
    contidos = []

    # terreno natural (TIN do MDT)
    loc = pts - np.array([ox, oy, oz])
    plist = a("IFCCARTESIANPOINTLIST3D((" + ",".join(f"({_f(x)},{_f(y)},{_f(z)})" for x, y, z in loc) + "))")
    tfs = a(f"IFCTRIANGULATEDFACESET({plist},$,.F.,(" + ",".join(f"({p},{q},{s})" for p, q, s in tris) + "),$)")
    rep = a(f"IFCSHAPEREPRESENTATION({body},'Body','Tessellation',({tfs}))")
    pds = a(f"IFCPRODUCTDEFINITIONSHAPE($,$,({rep}))")
    tp = a(f"IFCLOCALPLACEMENT({sp},{ax0})")
    terr = a(f"IFCGEOGRAPHICELEMENT('{guid('mdt', chave)}',{oh},{_s('Terreno natural (MDT)')},"
             f"{_s((resultado.get('mdt') or {}).get('fonte') or 'MDT')},$,{tp},{pds},$,.TERRAIN.)")
    contidos.append(terr)

    def polilinha3d(xy_tm, z_fn, nome_el, desc, tag):
        cps = []
        for x, y in list(xy_tm) + [list(xy_tm)[0]]:
            zz = z_fn(x, y)
            cps.append(a(f"IFCCARTESIANPOINT(({_f(x - ox)},{_f(y - oy)},{_f(zz - oz)}))"))
        pl = a("IFCPOLYLINE((" + ",".join(cps) + "))")
        rp = a(f"IFCSHAPEREPRESENTATION({anot},'Annotation','Curve3D',({pl}))")
        pd = a(f"IFCPRODUCTDEFINITIONSHAPE($,$,({rp}))")
        lp = a(f"IFCLOCALPLACEMENT({sp},{ax0})")
        return a(f"IFCANNOTATION('{guid(tag, chave)}',{oh},{_s(nome_el)},{_s(desc)},$,{lp},{pd})")

    zfill = Raster(AN._preencher_nan(r.z.astype(np.float64)).astype(np.float32), r.x0, r.y0, r.px, r.py)

    def zt(x, y):
        return float(AN.amostrar(zfill, np.array([x]), np.array([y]))[0]) + 0.05

    contidos.append(polilinha3d(anel.tolist(), zt, "Limite do prédio", "Estremas do terreno analisado", "limite"))
    for k, anel_z in enumerate(zona_livre_tm or []):
        if len(anel_z) >= 3:
            contidos.append(polilinha3d(anel_z, zt, "Zona livre para edificar", "Após afastamentos e condicionantes", f"livre{k}"))

    bld = None
    if implantacao and implantacao.get("ok"):
        pol = np.asarray(implantacao["poligono_tm"], dtype=float)
        sol = float(implantacao.get("cota_soleira_sugerida") or oz)
        pisos = int(implantacao.get("n_pisos") or 2)
        h = pisos * PE_DIREITO_PISO
        cps = [a(f"IFCCARTESIANPOINT(({_f(x - ox)},{_f(y - oy)}))") for x, y in list(pol) + [pol[0]]]
        pl = a("IFCPOLYLINE((" + ",".join(cps) + "))")
        prof = a(f"IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,{_s('Implantação')},{pl})")
        oz_b = a(f"IFCCARTESIANPOINT((0.,0.,{_f(sol - oz)}))")
        axb = a(f"IFCAXIS2PLACEMENT3D({oz_b},$,$)")
        up = a("IFCDIRECTION((0.,0.,1.))")
        sol_ = a(f"IFCEXTRUDEDAREASOLID({prof},{axb},{up},{_f(h)})")
        rp = a(f"IFCSHAPEREPRESENTATION({body},'Body','SweptSolid',({sol_}))")
        pd = a(f"IFCPRODUCTDEFINITIONSHAPE($,$,({rp}))")
        bp = a(f"IFCLOCALPLACEMENT({sp},{ax0})")
        bld = a(f"IFCBUILDING('{guid('bld', chave)}',{oh},{_s('Edifício proposto')},$,$,{bp},$,$,.ELEMENT.,{_f(sol - oz)},$,$)")
        a(f"IFCRELAGGREGATES('{guid('aggb', chave)}',{oh},$,$,{site},({bld}))")
        vol = a(f"IFCBUILDINGELEMENTPROXY('{guid('vol', chave)}',{oh},{_s('Volume de implantação recomendado')},"
                f"{_s(f'{pisos} piso(s) × {PE_DIREITO_PISO:.1f} m, soleira à cota {sol:.2f} m')},$,{bp},{pd},$,.ELEMENT.)")
        a(f"IFCRELCONTAINEDINSPATIALSTRUCTURE('{guid('contb', chave)}',{oh},$,$,({vol}),{bld})")
    a(f"IFCRELCONTAINEDINSPATIALSTRUCTURE('{guid('conts', chave)}',{oh},$,$,(" + ",".join(contidos) + f"),{site})")

    # Psets com os resultados
    def pset(nome_ps, valores: Dict[str, Any], alvo, tag):
        props = []
        for k, v in valores.items():
            if v is None:
                continue
            if isinstance(v, bool):
                val = f"IFCBOOLEAN(.{'T' if v else 'F'}.)"
            elif isinstance(v, (int, float)):
                val = f"IFCREAL({_f(v)})"
            else:
                val = f"IFCTEXT({_s(str(v)[:250])})"
            props.append(a(f"IFCPROPERTYSINGLEVALUE({_s(k)},$,{val},$)"))
        if not props:
            return
        ps = a(f"IFCPROPERTYSET('{guid('ps', tag, chave)}',{oh},{_s(nome_ps)},$,(" + ",".join(props) + "))")
        a(f"IFCRELDEFINESBYPROPERTIES('{guid('rdp', tag, chave)}',{oh},$,$,({alvo}),{ps})")

    rk = resultado.get("riscos") or {}
    orden = resultado.get("ordenamento") or {}
    pot = orden.get("potencial") or {}
    via = (resultado.get("viabilidade") or {})
    pset("CP_ViabilidadeTerreno", {
        "Classificacao": via.get("classificacao"), "Sintese": via.get("sintese"),
        "AreaTerreno_m2": pot.get("area_terreno_m2"), "AreaLivreImplantacao_m2": pot.get("area_livre_para_implantacao_m2"),
        "AreaConstrucaoMax_m2": pot.get("area_construcao_max_m2"), "SoloPDM": (orden.get("solo") or {}).get("solo"),
        "CategoriaPDM": (orden.get("solo") or {}).get("categoria"),
        "FracaoREN": ((orden.get("condicionantes") or {}).get("ren") or {}).get("fracao"),
        "FracaoRAN": ((orden.get("condicionantes") or {}).get("ran") or {}).get("fracao"),
        "RiscoGlobal": rk.get("rotulo_global"),
    }, site, "viab")
    pset("CP_RelevoTerreno", {
        "CotaMin_m": est.get("cota_min"), "CotaMax_m": est.get("cota_max"), "Desnivel_m": est.get("desnivel"),
        "DecliveMedio_pct": est.get("declive_medio_pct"), "Exposicao": est.get("exposicao"),
        "FormaRelevo": est.get("forma_dominante"), "FonteMDT": (resultado.get("mdt") or {}).get("fonte"),
    }, terr, "relevo")
    for e in rk.get("riscos") or []:
        pset(f"CP_Risco_{e['risco']}", {"Nivel": e["rotulo"], "Recomendacao": "; ".join(e.get("recomendacoes") or [])[:250]},
             site, "r_" + e["risco"])
    cab = ("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [ReferenceView_V1.2]'),'2;1');\n"
           f"FILE_NAME({_s(nome + '.ifc')},'{time.strftime('%Y-%m-%dT%H:%M:%S')}',({_s('ConstruPilot')}),({_s('ConstruPilot')}),"
           f"'ConstruPilot viabilidade','ConstruPilot','');\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n")
    corpo = "\n".join(f"#{i + 1}={l};" for i, l in enumerate(W.linhas))
    return (cab + corpo + "\nENDSEC;\nEND-ISO-10303-21;\n").encode("ascii")


# ------------------------------------------------------------------ IFC do utilizador
def ler_modelo_ifc(dados: bytes) -> Dict[str, Any]:
    """Pegada (retângulo mínimo orientado), n.º de pisos e altura do edifício de um IFC do utilizador."""
    try:
        from engines.bim_core import ifc_reader as R
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"leitor IFC indisponível neste servidor ({type(e).__name__})") from e
    f = R.open_ifc(dados)
    pisos = R.storeys(f)
    sh = R._shapes(f, (*R.WALLS, "IfcColumn", "IfcSlab"))
    if not sh:
        raise ValueError("O IFC não tem paredes, pilares nem lajes com geometria.")
    v = np.concatenate([vv for (_el, vv, _t) in sh.values()])
    try:                                                   # coordenadas do ficheiro → metros (projetos em mm, cm…)
        import ifcopenshell.util.unit as UU
        v = v * float(UU.calculate_unit_scale(f) or 1.0)
    except Exception:  # noqa: BLE001
        pass
    xy = v[:, :2]
    zmin, zmax = float(v[:, 2].min()), float(v[:, 2].max())
    from scipy.spatial import ConvexHull
    hull = xy[ConvexHull(xy).vertices]
    best = None
    for i in range(len(hull)):
        p, q = hull[i], hull[(i + 1) % len(hull)]
        ang = math.atan2(q[1] - p[1], q[0] - p[0])
        c, s = math.cos(-ang), math.sin(-ang)
        rot = hull @ np.array([[c, -s], [s, c]]).T
        w, d = float(np.ptp(rot[:, 0])), float(np.ptp(rot[:, 1]))
        if best is None or w * d < best[0]:
            mx, my = (rot[:, 0].min() + rot[:, 0].max()) / 2, (rot[:, 1].min() + rot[:, 1].max()) / 2
            cc, ss = math.cos(ang), math.sin(ang)
            best = (w * d, w, d, ang, (mx * cc - my * ss, mx * ss + my * cc))
    _, w, d, ang, centro = best
    if d > w:
        w, d, ang = d, w, ang + math.pi / 2
    proj = f.by_type("IfcProject")
    return {"largura_m": round(float(w), 2), "profundidade_m": round(float(d), 2), "area_pegada_m2": round(float(w * d), 1),
            "rotacao_modelo_graus": round(math.degrees(ang) % 180, 1), "n_pisos": max(1, len([p for p in pisos if p["elevation"] >= -0.5])),
            "altura_m": round(zmax - zmin, 2), "cota_base_modelo": round(zmin, 2), "pisos": pisos,
            "centro_local": [round(float(centro[0]), 3), round(float(centro[1]), 3)],
            "projeto": (proj[0].Name if proj else None), "esquema": f.schema}


def georreferenciar_ifc(dados: bytes, implantacao: Dict[str, Any], modelo: Dict[str, Any], r: Optional[Raster] = None) -> bytes:
    """Escreve a IfcMapConversion (EPSG:3763) que coloca o modelo do utilizador na implantação recomendada.
    Com `r` (MDT da análise), acrescenta ao mesmo ficheiro a superfície do terreno natural (IfcGeographicElement
    TERRAIN, nas coordenadas e unidades do projeto) — o relevo aparece à volta do edifício no Revit/Archicad/BlenderBIM."""
    import tempfile
    import os
    from engines.bim_core import ifc_reader as R
    f = R.open_ifc(dados)
    ctxs = [c for c in f.by_type("IfcGeometricRepresentationContext") if not c.is_a("IfcGeometricRepresentationSubContext")]
    if not ctxs:
        raise ValueError("IFC sem contexto geométrico")
    for mc in f.by_type("IfcMapConversion"):
        f.remove(mc)
    unit = next((u for u in f.by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT"), None)
    crs = f.createIfcProjectedCRS("EPSG:3763", "ETRS89 / Portugal TM06", "ETRS89", "Cascais Helmert 1938", None, None, unit)
    cx, cy = implantacao["centro_tm"]
    # rotação: eixo maior do modelo alinhado com a fachada principal recomendada
    az = math.radians(implantacao["azimute_fachada_principal"])
    eixo = math.radians(modelo.get("rotacao_modelo_graus") or 0.0)
    ang = -az - eixo                                       # eixo maior do modelo ao longo da fachada principal
    sol = float(implantacao.get("cota_soleira_sugerida") or 0.0) - float(modelo.get("cota_base_modelo") or 0.0)
    mx, my = modelo.get("centro_local") or (0.0, 0.0)
    ca, sa = math.cos(ang), math.sin(ang)
    e0, n0 = float(cx) - (mx * ca - my * sa), float(cy) - (mx * sa + my * ca)   # origem local → centro da implantação
    # unidades do ficheiro: a pegada (ifcopenshell.geom) vem em metros; a IfcMapConversion aplica-se às coordenadas do
    # ficheiro, por isso a escala tem de ser «metros por unidade» (0,001 num projeto em milímetros)
    try:
        import ifcopenshell.util.unit as UU
        k = float(UU.calculate_unit_scale(f)) or 1.0
    except Exception:  # noqa: BLE001
        k = 1.0
    f.createIfcMapConversion(ctxs[0], crs, e0, n0, sol, ca, sa, k)
    if r is not None:
        try:
            _terreno_no_modelo(f, r, e0, n0, sol, ang, k)
        except Exception as e:  # noqa: BLE001 — o IFC georreferenciado continua válido sem o terreno
            import logging
            logging.getLogger(__name__).info("terreno no IFC do utilizador: %s", e)
    fd, path = tempfile.mkstemp(suffix=".ifc")
    os.close(fd)
    try:
        f.write(path)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(path)


def _terreno_no_modelo(f, r: Raster, e0: float, n0: float, h0: float, ang: float, k: float, max_lado: int = 120) -> None:
    """Superfície do MDT no IFC do utilizador, no referencial local do projeto (inverso da IfcMapConversion)."""
    import ifcopenshell.api
    from engines.mdt_pt.grelha import reamostrar
    from engines.mdt_pt.analise import _preencher_nan, centros
    api = ifcopenshell.api.run
    rr = r
    while max(rr.z.shape) > max_lado:
        rr = reamostrar(rr, rr.px * 2)
    z = _preencher_nan(rr.z.astype(np.float64))
    xc, yc = centros(rr)
    X, Y = np.meshgrid(xc, yc)
    dx, dy = X.ravel() - e0, Y.ravel() - n0
    ca, sa = math.cos(ang), math.sin(ang)
    lx = (dx * ca + dy * sa) / k
    ly = (-dx * sa + dy * ca) / k
    lz = (z.ravel() - h0) / k
    ny, nx = z.shape
    idx = np.arange(ny * nx).reshape(ny, nx)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    T = np.r_[np.c_[a, c, b], np.c_[b, c, d]] + 1
    pts = f.createIfcCartesianPointList3D([(round(float(p), 4), round(float(q), 4), round(float(w), 4)) for p, q, w in zip(lx, ly, lz)])
    fs = f.createIfcTriangulatedFaceSet(Coordinates=pts, Closed=False, CoordIndex=[tuple(int(i) for i in t) for t in T])
    body = next((c for c in f.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body"), None)
    if body is None:
        body = next(c for c in f.by_type("IfcGeometricRepresentationContext") if not c.is_a("IfcGeometricRepresentationSubContext"))
    el = api("root.create_entity", f, ifc_class="IfcGeographicElement", name="Terreno natural (MDT ConstruPilot)")
    try:
        el.PredefinedType = "TERRAIN"
    except Exception:  # noqa: BLE001 — IFC2X3 não tem PredefinedType
        pass
    rep = f.createIfcShapeRepresentation(body, "Body", "Tessellation", [fs])
    api("geometry.assign_representation", f, product=el, representation=rep)
    api("geometry.edit_object_placement", f, product=el, matrix=np.eye(4))
    sites = f.by_type("IfcSite")
    if sites:
        api("spatial.assign_container", f, products=[el], relating_structure=sites[0])
