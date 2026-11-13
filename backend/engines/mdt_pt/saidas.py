"""Saídas do MDT: camadas PNG para o mapa (reprojetadas para lat/lon), DXF (PT-TM06), GeoJSON e a carta em PDF
(hipsometria + curvas de nível, declives, recursos hídricos/escorrência)."""
from __future__ import annotations

import io
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import pttm06 as TM
from .analise import CLASSES_DECLIVE, centros
from .geotiff import Raster

VERDE, COBRE, CREME, TINTA = "#1F4D3A", "#B8733A", "#F6F1E7", "#1B1F1D"


# ------------------------------------------------------------------ cores
def _hex(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def rgba_hipsometria(z: np.ndarray, hs: np.ndarray) -> np.ndarray:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import colormaps, colors
    lo, hi = np.nanpercentile(z, 1), np.nanpercentile(z, 99)
    if hi - lo < 0.5:
        hi = lo + 0.5
    rgb = colormaps["gist_earth"](colors.Normalize(lo - (hi - lo) * 0.15, hi + (hi - lo) * 0.1)(np.nan_to_num(z, nan=lo)))[..., :3]
    sh = 0.45 + 0.55 * hs[..., None]
    out = np.concatenate([np.clip(rgb * sh, 0, 1), np.ones(z.shape + (1,))], axis=-1)
    out[np.isnan(z), 3] = 0
    return (out * 255).astype(np.uint8)


def rgba_declives(decl: np.ndarray, hs: Optional[np.ndarray] = None) -> np.ndarray:
    out = np.zeros(decl.shape + (4,), dtype=np.float64)
    for lo, hi, _, cor in CLASSES_DECLIVE:
        m = (decl >= lo) & (decl < hi)
        out[m, :3] = np.array(_hex(cor)) / 255.0
        out[m, 3] = 1
    if hs is not None:
        out[..., :3] *= (0.7 + 0.3 * hs[..., None])
    out[np.isnan(decl), 3] = 0
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def png(rgba: np.ndarray) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(b, "PNG", optimize=True)
    return b.getvalue()


def para_latlon(r: Raster, rgba: np.ndarray, max_px: int = 1024) -> Tuple[np.ndarray, List[List[float]]]:
    """Reprojeta uma imagem da grelha TM para uma grelha lat/lon regular (L.imageOverlay). Devolve (rgba, [[s,o],[n,e]])."""
    ny, nx = rgba.shape[:2]
    xs = np.array([r.x0, r.x1, r.x0, r.x1])
    ys = np.array([r.y0, r.y0, r.y1, r.y1])
    la, lo = TM.para_ll(xs, ys)
    s, n, o, e = la.min(), la.max(), lo.min(), lo.max()
    escala = max(nx, ny) / max_px if max(nx, ny) > max_px else 1.0
    W = max(int(nx / escala), 2)
    H = max(int(round(W * (n - s) / (e - o) / math.cos(math.radians((n + s) / 2)))), 2)
    lat = n - (np.arange(H) + 0.5) / H * (n - s)
    lon = o + (np.arange(W) + 0.5) / W * (e - o)
    LO, LA = np.meshgrid(lon, lat)
    X, Y = TM.para_tm(LA, LO)
    ci = np.floor((X - r.x0) / r.px).astype(int)
    ri = np.floor((r.y0 - Y) / r.py).astype(int)
    ok = (ci >= 0) & (ci < nx) & (ri >= 0) & (ri < ny)
    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[ok] = rgba[ri[ok], ci[ok]]
    return out, [[round(float(s), 7), round(float(o), 7)], [round(float(n), 7), round(float(e), 7)]]


# ------------------------------------------------------------------ DXF / GeoJSON
def dxf(curvas: List[Dict[str, Any]], linhas_agua: List[Dict[str, Any]], poligono_ll: Optional[Sequence], r: Raster,
        pontos_cotados: int = 12) -> bytes:
    import ezdxf
    doc = ezdxf.new("R2013", setup=True)
    doc.header["$INSUNITS"] = 6
    for nome, cor in (("CURVAS_MESTRAS", 30), ("CURVAS_SECUNDARIAS", 8), ("LINHAS_AGUA_POTENCIAIS", 5),
                      ("LIMITE_TERRENO", 1), ("PONTOS_COTADOS", 7), ("TEXTO_COTAS", 7)):
        doc.layers.add(nome, color=cor)
    msp = doc.modelspace()
    for c in curvas:
        pts = [(x, y, c["cota"]) for x, y in c["xy"]]
        msp.add_polyline3d(pts, dxfattribs={"layer": "CURVAS_MESTRAS" if c["mestra"] else "CURVAS_SECUNDARIAS"})
        if c["mestra"] and len(pts) > 4:
            x, y, z = pts[len(pts) // 2]
            msp.add_text(f"{z:.2f}".rstrip("0").rstrip("."), height=max(r.px * 1.5, 0.8),
                         dxfattribs={"layer": "TEXTO_COTAS"}).set_placement((x, y))
    for l in linhas_agua:
        msp.add_lwpolyline([tuple(p) for p in l["xy"]], dxfattribs={"layer": "LINHAS_AGUA_POTENCIAIS"})
    if poligono_ll:
        x, y = TM.para_tm(np.array([p[0] for p in poligono_ll]), np.array([p[1] for p in poligono_ll]))
        msp.add_lwpolyline(list(zip(x.tolist(), y.tolist())), close=True, dxfattribs={"layer": "LIMITE_TERRENO"})
    ny, nx = r.z.shape
    xc, yc = centros(r)
    for i in np.linspace(0, ny - 1, pontos_cotados).astype(int):
        for j in np.linspace(0, nx - 1, pontos_cotados).astype(int):
            z = r.z[i, j]
            if np.isnan(z):
                continue
            msp.add_point((float(xc[j]), float(yc[i]), float(z)), dxfattribs={"layer": "PONTOS_COTADOS"})
            msp.add_text(f"{z:.2f}", height=max(r.px * 1.2, 0.6),
                         dxfattribs={"layer": "TEXTO_COTAS"}).set_placement((float(xc[j]) + r.px, float(yc[i])))
    s = io.StringIO()
    doc.write(s)
    return s.getvalue().encode("utf-8")


def geojson(curvas_ll: List[Dict[str, Any]], linhas_ll: List[Dict[str, Any]], poligono_ll: Optional[Sequence],
            meta: Dict[str, Any]) -> Dict[str, Any]:
    feats = []
    for c in curvas_ll:
        feats.append({"type": "Feature", "properties": {"tipo": "curva_nivel", "cota": c["cota"], "mestra": c["mestra"]},
                      "geometry": {"type": "LineString", "coordinates": [[b, a] for a, b in c["ll"]]}})
    for l in linhas_ll:
        feats.append({"type": "Feature", "properties": {"tipo": "linha_agua_potencial", "bacia_m2": l["bacia_m2"]},
                      "geometry": {"type": "LineString", "coordinates": [[b, a] for a, b in l["ll"]]}})
    if poligono_ll:
        ring = [[b, a] for a, b in poligono_ll]
        feats.append({"type": "Feature", "properties": {"tipo": "terreno"},
                      "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}})
    return {"type": "FeatureCollection", "name": "ConstruPilot MDT", "fonte": meta.get("fonte"), "features": feats}


# ------------------------------------------------------------------ PDF (cartas)
def _mapa(ax, r: Raster, img: np.ndarray, poligono_tm, titulo: str, curvas=None, linhas=None):
    ax.imshow(img, extent=(r.x0, r.x1, r.y1, r.y0), interpolation="bilinear")
    if curvas:
        for c in curvas:
            a = np.asarray(c["xy"])
            ax.plot(a[:, 0], a[:, 1], color="#3b2f22" if c["mestra"] else "#6b5a45",
                    lw=0.9 if c["mestra"] else 0.35, alpha=0.9)
            if c["mestra"] and len(a) > 8:
                k = len(a) // 2
                ax.text(a[k, 0], a[k, 1], f"{c['cota']:g}", fontsize=5.5, color="#2b2118", ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.1", fc=(1, 1, 1, 0.65), ec="none"))
    if linhas:
        bmax = max([l["bacia_m2"] for l in linhas] + [1])
        for l in linhas:
            a = np.asarray(l["xy"])
            ax.plot(a[:, 0], a[:, 1], color="#1565c0", lw=0.8 + 2.4 * math.sqrt(l["bacia_m2"] / bmax))
    if poligono_tm is not None:
        p = np.vstack([poligono_tm, poligono_tm[:1]])
        ax.plot(p[:, 0], p[:, 1], color="#c62828", lw=1.6)
    ax.set_xlim(r.x0, r.x1)
    ax.set_ylim(r.y1, r.y0)
    ax.set_aspect("equal")
    ax.set_title(titulo, fontsize=11, color=VERDE, loc="left", fontweight="bold")
    ax.tick_params(labelsize=6)
    ax.ticklabel_format(useOffset=False, style="plain")
    # escala e norte
    L = r.x1 - r.x0
    barra = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000][min(range(10), key=lambda i: abs([1, 2, 5, 10, 20, 50, 100, 200, 500, 1000][i] - L / 5))]
    x0, y0 = r.x0 + L * 0.05, r.y1 + (r.y0 - r.y1) * 0.05
    ax.plot([x0, x0 + barra], [y0, y0], color="k", lw=3, solid_capstyle="butt")
    ax.text(x0 + barra / 2, y0 + (r.y0 - r.y1) * 0.02, f"{barra} m", fontsize=7, ha="center")
    xn, yn = r.x1 - L * 0.06, r.y0 - (r.y0 - r.y1) * 0.14
    ax.annotate("N", xy=(xn, yn + (r.y0 - r.y1) * 0.08), xytext=(xn, yn), ha="center", fontsize=9, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="k", lw=1.5))


def pdf_carta(r: Raster, meta: Dict[str, Any], est: Dict[str, Any], classes: List[Dict[str, Any]],
              hs: np.ndarray, decl: np.ndarray, curvas: List[Dict[str, Any]], esc: Dict[str, Any],
              poligono_ll: Optional[Sequence], local: str = "", terras: Optional[Dict[str, Any]] = None,
              cor_empresa: Optional[str] = None, nome_empresa: str = "ConstruPilot",
              logo_b64: Optional[str] = None) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Patch

    cor = cor_empresa if (cor_empresa or "").startswith("#") and len(cor_empresa) == 7 else VERDE
    logo = None
    if logo_b64:
        try:
            import base64 as _b64
            from PIL import Image
            raw = logo_b64.split(",", 1)[-1]
            logo = np.asarray(Image.open(io.BytesIO(_b64.b64decode(raw))).convert("RGBA"))
        except Exception:  # noqa: BLE001
            logo = None
    pol_tm = None
    if poligono_ll:
        x, y = TM.para_tm(np.array([p[0] for p in poligono_ll]), np.array([p[1] for p in poligono_ll]))
        pol_tm = np.c_[x, y]
    data = datetime.now().strftime("%d/%m/%Y")
    buf = io.BytesIO()
    A4 = (11.69, 8.27)

    def cabecalho(fig, titulo, n):
        fig.patch.set_facecolor("white")
        fig.add_artist(plt.Rectangle((0, 0.93), 1, 0.07, transform=fig.transFigure, color=cor))
        x_t = 0.03
        if logo is not None:
            axl = fig.add_axes([0.012, 0.936, 0.06, 0.058])
            axl.add_patch(plt.Rectangle((0, 0), 1, 1, transform=axl.transAxes, color="white"))
            hh, ww = logo.shape[:2]
            k = 0.44 * min(hh, ww) / max(hh, ww)
            ext = (0.06, 0.94, 0.5 - k, 0.5 + k) if ww >= hh else (0.5 - k, 0.5 + k, 0.06, 0.94)
            axl.imshow(logo, extent=ext, aspect="auto")
            axl.set_xlim(0, 1)
            axl.set_ylim(0, 1)
            axl.axis("off")
            x_t = 0.085
        fig.text(x_t, 0.955, f"{nome_empresa} · Modelo Digital do Terreno", color="white", fontsize=13, fontweight="bold", va="center")
        fig.text(0.97, 0.955, f"{titulo}  ·  folha {n}/4", color="white", fontsize=10, ha="right", va="center")
        fig.text(0.03, 0.02, f"Fonte: {meta.get('fonte')} · resolução {meta.get('resolucao_m')} m · ETRS89/PT-TM06 (EPSG:3763) · {data}",
                 fontsize=6.5, color="#555")
        fig.text(0.97, 0.02, "Documento indicativo: não substitui o levantamento topográfico do projeto.", fontsize=6.5,
                 color="#555", ha="right")

    hip = rgba_hipsometria(r.z, hs)
    with PdfPages(buf) as pdf:
        # 1 — resumo
        fig = plt.figure(figsize=A4)
        cabecalho(fig, "Resumo", 1)
        fig.text(0.05, 0.85, "Caracterização altimétrica do terreno", fontsize=18, color=cor, fontweight="bold")
        if local:
            fig.text(0.05, 0.81, local, fontsize=10, color="#333")
        linhas = [
            ("Área analisada", f"{est.get('area_m2', 0):,.0f} m²".replace(",", " ")),
            ("Cota mínima / máxima", f"{est['cota_min']:.2f} m  /  {est['cota_max']:.2f} m"),
            ("Cota média", f"{est['cota_media']:.2f} m"),
            ("Desnível", f"{est['desnivel']:.2f} m"),
            ("Declive médio / máximo (p99)", f"{est['declive_medio_pct']} %  /  {est['declive_max_pct']} %"),
            ("Exposição dominante", est.get("exposicao") or "—"),
            ("Linhas de água potenciais", f"{len(esc.get('linhas', []))} troço(s) (bacia ≥ {esc.get('limiar_m2', 0):,.0f} m²)".replace(",", " ")),
            ("Modelo", "MDT: superfície do terreno, sem vegetação nem construções"),
        ]
        if terras and terras.get("ok"):
            linhas.append(("Plataforma à cota de equilíbrio", f"{terras['cota_equilibrio']:.2f} m"))
            linhas.append(("Escavação / aterro (no terreno)", f"{terras['escavacao_m3']:,.0f} m³  /  {terras['aterro_m3']:,.0f} m³".replace(",", " ")))
        for k, (a, b) in enumerate(linhas):
            yy = 0.72 - k * 0.055
            fig.text(0.05, yy, a, fontsize=10, color="#444")
            fig.text(0.30, yy, b, fontsize=10, color=TINTA, fontweight="bold")
        ax = fig.add_axes([0.70, 0.12, 0.27, 0.62])
        ax.imshow(hip, extent=(r.x0, r.x1, r.y1, r.y0))
        if pol_tm is not None:
            p = np.vstack([pol_tm, pol_tm[:1]])
            ax.plot(p[:, 0], p[:, 1], color="#c62828", lw=1.4)
        ax.axis("off")
        aviso = "; ".join(meta.get("avisos") or [])
        if aviso:
            fig.text(0.06, 0.1, aviso[:220], fontsize=8, color=COBRE, wrap=True)
        pdf.savefig(fig)
        plt.close(fig)

        # 2 — hipsometria + curvas
        fig = plt.figure(figsize=A4)
        cabecalho(fig, "Hipsometria e curvas de nível", 2)
        ax = fig.add_axes([0.06, 0.08, 0.62, 0.82])
        eq = meta.get("equidistancia")
        _mapa(ax, r, hip, pol_tm, f"Hipsometria com curvas de nível (equidistância {eq} m)", curvas=curvas)
        fig.text(0.72, 0.8, "Leitura", fontsize=12, color=cor, fontweight="bold")
        fig.text(0.72, 0.76, f"Curvas mestras a cada {eq * 5:g} m (traço grosso).\nCotas em metros.", fontsize=9, va="top")
        pdf.savefig(fig)
        plt.close(fig)

        # 3 — declives
        fig = plt.figure(figsize=A4)
        cabecalho(fig, "Carta de declives", 3)
        ax = fig.add_axes([0.06, 0.08, 0.62, 0.82])
        _mapa(ax, r, rgba_declives(decl, hs), pol_tm, "Carta de declives (%)")
        ax.legend(handles=[Patch(color=c["cor"], label=c["classe"]) for c in classes], loc="lower right", fontsize=7, framealpha=0.85)
        fig.text(0.72, 0.8, "Distribuição no terreno", fontsize=12, color=cor, fontweight="bold")
        ax2 = fig.add_axes([0.72, 0.42, 0.25, 0.33])
        ax2.barh([c["classe"].split(" · ")[0] for c in classes], [c["pct"] for c in classes], color=[c["cor"] for c in classes])
        ax2.invert_yaxis()
        ax2.tick_params(labelsize=7)
        ax2.set_xlabel("% da área", fontsize=7)
        for k, c in enumerate(classes):
            ax2.text(c["pct"] + 0.5, k, f"{c['pct']:.0f} %", va="center", fontsize=7)
        fig.text(0.72, 0.36, "Declives > 25 % exigem, em regra, muros de suporte,\nestudo geotécnico e atenção à REN "
                 "(áreas de\nelevado risco de erosão hídrica do solo).", fontsize=8, va="top")
        pdf.savefig(fig)
        plt.close(fig)

        # 4 — recursos hídricos / escorrência
        fig = plt.figure(figsize=A4)
        cabecalho(fig, "Recursos hídricos — escorrência", 4)
        ax = fig.add_axes([0.06, 0.08, 0.62, 0.82])
        cinza = np.dstack([hs * 255] * 3 + [np.where(np.isnan(r.z), 0, 255)]).astype(np.uint8)
        rr = esc.get("raster") or r
        _mapa(ax, r, cinza, pol_tm, "Linhas de água potenciais derivadas do MDT", curvas=[c for c in curvas if c["mestra"]],
              linhas=esc.get("linhas"))
        fig.text(0.72, 0.8, "Método", fontsize=12, color=cor, fontweight="bold")
        fig.text(0.72, 0.76, f"Direções de escoamento D8 sobre o MDT\n(depressões preenchidas), grelha de {rr.px:g} m.\n"
                 f"Traça-se uma linha onde a bacia drenada\nultrapassa {esc.get('limiar_m2', 0):,.0f} m²; a espessura cresce\ncom a bacia.".replace(",", " "),
                 fontsize=8.5, va="top")
        fig.text(0.72, 0.5, "Importante", fontsize=12, color=COBRE, fontweight="bold")
        fig.text(0.72, 0.46, "São talvegues potenciais, não a rede\nhidrográfica oficial. Confirmar linhas de água\n"
                 "e respetivas margens (domínio hídrico, Lei\n54/2005) na APA e na carta da REN do PDM.", fontsize=8.5, va="top")
        pdf.savefig(fig)
        plt.close(fig)
    return buf.getvalue()
