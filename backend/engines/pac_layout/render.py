"""Desenho : planta de implantação por piso desenhada SOBRE a planta do arquiteto + esquema de princípio (PNG)."""
from __future__ import annotations

import io
import math

import numpy as np

HOT, COLD, LOOP, COND, RISER = "#d1495b", "#1f6fb2", "#e07a3f", "#6b6b6b", "#5a2d82"
INK = "#1f2a33"


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _offset(path, d):
    """Polyline décalée de d px (perpendiculairement à chaque segment, approximé pour des tracés orthogonaux)."""
    out = []
    for i, (x, y) in enumerate(path):
        a = path[max(0, i - 1)]
        b = path[min(len(path) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1
        out.append((x - dy / n * d, y + dx / n * d))
    return out


def level_png(bg_png: bytes, lv, res: dict, brand_name: str, accent: str, logo_png: bytes | None, project: str,
              planche: str, dpi_ratio: float) -> bytes:
    """bg_png : planche rendue à RENDER_DPI ; coordonnées de `res` au DPI de travail (dpi_ratio = RENDER_DPI / DPI)."""
    plt = _mpl()
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    from matplotlib.patches import Circle, Rectangle
    import matplotlib.patheffects as pe
    from PIL import Image

    L = res["levels"][lv.name]
    ppm = lv.px_per_m
    with Image.open(io.BytesIO(bg_png)) as im:
        bg = np.asarray(im.convert("RGB"))
    W, H = lv.size
    # cadrage : emprise + équipements + 2 m
    pts = [(e["x"], e["y"]) for e in L["equipment"]]
    if lv.footprint is not None and lv.footprint.any():
        ys, xs = np.nonzero(lv.footprint)
        pts += [(xs.min(), ys.min()), (xs.max(), ys.max())]
    xs_, ys_ = zip(*pts)
    m = 2.2 * ppm
    x0, x1 = max(0, min(xs_) - m), min(W, max(xs_) + m)
    y0, y1 = max(0, min(ys_) - m), min(H, max(ys_) + m)

    fig = plt.figure(figsize=(16.5, 11.0), dpi=200)
    hdr = fig.add_axes([0.0, 0.925, 1.0, 0.075]); hdr.axis("off")
    if logo_png:
        with Image.open(io.BytesIO(logo_png)) as li:
            la = np.asarray(li.convert("RGBA"))
        zoom = 0.62 * 0.075 * 11.0 * 72 / max(1, la.shape[0])
        hdr.add_artist(AnnotationBbox(OffsetImage(la, zoom=zoom), (0.035, 0.5), frameon=False, xycoords="axes fraction"))
    hdr.text(0.07, 0.62, brand_name, fontsize=15, fontweight="bold", color=accent, transform=hdr.transAxes)
    hdr.text(0.5, 0.62, f"{project} — Implantação de bomba de calor ar-água reversível — {lv.name}", ha="center", fontsize=13.5,
             fontweight="bold", transform=hdr.transAxes)
    hdr.text(0.5, 0.22, f"Base : {planche} · Piso radiante (aquecimento e arrefecimento) + ventiloconvectores de teto · "
             "Planta de princípio, sem cotas", ha="center", fontsize=9, color="#555", transform=hdr.transAxes)
    hdr.plot([0.01, 0.99], [0.02, 0.02], color=accent, lw=2, transform=hdr.transAxes)

    ax = fig.add_axes([0.01, 0.02, 0.74, 0.90])
    ax.imshow(bg, extent=(0, W, H, 0))
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal"); ax.axis("off")
    st = [pe.withStroke(linewidth=2.5, foreground="white")]

    # zones de plancher + serpentins
    loop_rooms = {lp["room"]: lp for lp in L["loops"]}
    ov = np.zeros((H, W, 4), np.float32)
    for r in lv.rooms:
        if r.name not in loop_rooms or r.mask is None:
            continue
        ov[r.mask] = (0.878, 0.478, 0.247, 0.13)
        rx0, ry0, rx1, ry1 = r.bbox()
        step = max(9.0, loop_rooms[r.name]["pitch"] * ppm * 1.6)
        horiz = (rx1 - rx0) >= (ry1 - ry0)
        segs = []
        if horiz:
            for y in np.arange(ry0 + 6, ry1 - 3, step):
                row = r.mask[int(y), rx0:rx1 + 1]
                if row.any():
                    idx = np.nonzero(row)[0]
                    segs.append(((rx0 + idx.min() + 5, y), (rx0 + idx.max() - 5, y)))
        else:
            for x in np.arange(rx0 + 6, rx1 - 3, step):
                col = r.mask[ry0:ry1 + 1, int(x)]
                if col.any():
                    idx = np.nonzero(col)[0]
                    segs.append(((x, ry0 + idx.min() + 5), (x, ry0 + idx.max() - 5)))
        for (p, q) in segs:
            ax.plot([p[0], q[0]], [p[1], q[1]], color=LOOP, lw=0.6, alpha=0.55)

    ax.imshow(ov, extent=(0, W, H, 0), interpolation="nearest")
    for nw in L["networks"]:
        path = nw["path"]
        xs, ys = zip(*path)
        k = nw["kind"]
        if k == "amenee":
            ax.plot(xs, ys, color=LOOP, lw=1.3, ls="--")
        elif k == "eau_froide":
            ax.plot(xs, ys, color=COLD, lw=3.6, alpha=0.3)
            ax.plot(xs, ys, color=COLD, lw=1.5)
        elif k == "condensats":
            ax.plot(xs, ys, color=COND, lw=1.0, ls=":", zorder=4)
        else:   # pac, module_collecteur, module_colonne, colonne_collecteur : aller / retour
            for d, c in ((-3, HOT), (3, COLD)):
                o = _offset(path, d)
                ax.plot([p[0] for p in o], [p[1] for p in o], color=c, lw=2.2, zorder=5)

    ann = dict(fontsize=7, color="#222", path_effects=st, zorder=9)
    for e in L["equipment"]:
        x, y = e["x"], e["y"]
        if e["kind"] == "module":
            s = 0.30 * ppm
            ax.add_patch(Rectangle((x - s, y - s), 2 * s, 2 * s, fc="#fdecea", ec=HOT, lw=1.8, zorder=7))
            ax.text(x, y, "MH\n+\nDI", ha="center", va="center", fontsize=6, fontweight="bold", zorder=8)
            ax.annotate(f"Módulo hidráulico + depósito de inércia\n({e['room']})", xy=(x, y), xytext=(x - 3.2 * ppm, y + 4.2 * ppm),
                        arrowprops=dict(arrowstyle="-", color="#444", lw=0.7), **ann)
        elif e["kind"] == "collecteur":
            ax.add_patch(Rectangle((x - 0.12 * ppm, y - 0.32 * ppm), 0.24 * ppm, 0.64 * ppm, fc="#fff1e6", ec=LOOP, lw=1.8, zorder=7))
            ax.text(x + 0.45 * ppm, y + 0.45 * ppm, "SR", fontsize=6, ha="center", va="center", color="#7a5a00", fontweight="bold",
                    zorder=8, bbox=dict(boxstyle="round,pad=0.2", fc="#fff3cd", ec="#b8860b"))
            ax.annotate(f"Coletor {lv.name}\n{L.get('collector_outlets', 0)} saídas ({e['room']})", xy=(x, y),
                        xytext=(x + 2.0 * ppm, y - 3.0 * ppm), arrowprops=dict(arrowstyle="-", color="#444", lw=0.7), **ann)
        elif e["kind"] == "colonne":
            ax.add_patch(Circle((x, y), 0.09 * ppm, fc="white", ec=RISER, lw=1.8, zorder=9))
            ax.add_patch(Circle((x, y), 0.035 * ppm, fc=RISER, ec="none", zorder=10))
        elif e["kind"] == "pac":
            w_, h_ = 0.45 * ppm, 0.22 * ppm
            ax.add_patch(Rectangle((x - w_, y - h_), 2 * w_, 2 * h_, fc="#e8eef5", ec="#333", lw=1.8, zorder=7))
            ax.text(x, y, "BC", ha="center", va="center", fontsize=7, fontweight="bold", zorder=8)
            ax.annotate(f"Unidade exterior BC\n(contra {e['room']}, sobre apoios)", xy=(x, y), xytext=(x + 2.0 * ppm, y + 2.4 * ppm),
                        arrowprops=dict(arrowstyle="-", color="#444", lw=0.7), **ann)
    for v in L["vc"]:
        x, y = v["x"], v["y"]
        ax.add_patch(Rectangle((x - 0.22 * ppm, y - 0.14 * ppm), 0.44 * ppm, 0.28 * ppm, fc="#dceefb", ec=COLD, lw=1.6, zorder=7))
        ax.text(x, y, v["id"], ha="center", va="center", fontsize=6.5, fontweight="bold", color=COLD, zorder=8)
        ax.add_patch(Circle((x + 0.27 * ppm, y + 0.17 * ppm), 0.04 * ppm, fc=COND, ec="none", zorder=8))
    for t in L["thermostats"]:
        ax.text(t["x"], t["y"], "T", fontsize=5.5, ha="center", va="center", color="white", fontweight="bold", zorder=8,
                bbox=dict(boxstyle="circle,pad=0.18", fc="#7a3e00", ec="none"))

    # légende + tableau des boucles
    lg = fig.add_axes([0.765, 0.05, 0.225, 0.86]); lg.axis("off")
    y = 0.97
    lg.text(0, y, "Legenda", fontsize=10, fontweight="bold", transform=lg.transAxes); y -= 0.06
    items = [("line", HOT, "-", 2.4, "Ida água"), ("line", COLD, "-", 2.4, "Retorno água"),
             ("line", COLD, "-", 1.5, "Água fria ventiloconvectores\n(teto falso, isolada anticondensação)"),
             ("line", LOOP, "--", 1.4, "Alimentação dos circuitos de piso"),
             ("patch", LOOP, None, None, "Zona de piso radiante (aquec./arref.)"),
             ("line", COND, ":", 1.2, "Drenagem de condensados (bomba)"),
             ("vc", COLD, None, None, "Ventiloconvector de teto (cassete)"),
             ("t", None, None, None, "Termóstato ambiente calor / frio"),
             ("sr", None, None, None, "Sonda de ponto de orvalho (ida piso)"),
             ("col", None, None, None, "Coluna montante (courete)")]
    for kind, c, ls, lw, label in items:
        if kind == "line":
            lg.plot([0.0, 0.10], [y, y], color=c, ls=ls, lw=lw, transform=lg.transAxes)
        elif kind == "patch":
            lg.add_patch(Rectangle((0.0, y - 0.015), 0.10, 0.03, fc=c, alpha=0.2, transform=lg.transAxes))
        elif kind == "vc":
            lg.add_patch(Rectangle((0.02, y - 0.015), 0.06, 0.03, fc="#dceefb", ec=c, transform=lg.transAxes))
        elif kind == "t":
            lg.text(0.05, y, "T", fontsize=6.5, ha="center", va="center", color="white", fontweight="bold", transform=lg.transAxes,
                    bbox=dict(boxstyle="circle,pad=0.18", fc="#7a3e00", ec="none"))
        elif kind == "sr":
            lg.text(0.05, y, "SR", fontsize=6.5, ha="center", va="center", color="#7a5a00", fontweight="bold", transform=lg.transAxes,
                    bbox=dict(boxstyle="round,pad=0.2", fc="#fff3cd", ec="#b8860b"))
        elif kind == "col":
            lg.add_patch(Circle((0.05, y), 0.016, fc="white", ec=RISER, lw=1.6, transform=lg.transAxes))
        lg.text(0.13, y, label, fontsize=7.5, va="center", transform=lg.transAxes)
        y -= 0.042 if "\n" not in label else 0.058
    y -= 0.03
    lg.text(0, y, f"Circuitos de piso {lv.name} (pré-dim.)", fontsize=9, fontweight="bold", transform=lg.transAxes)
    y -= 0.045
    lg.text(0, y, f"{'Compart.':<14}{'A (m²)':>7}{'passo':>6}{'circ':>5}{'L/circ':>7}", fontsize=7, family="monospace", transform=lg.transAxes)
    for lp in L["loops"]:
        y -= 0.032
        lg.text(0, y, f"{lp['room'][:13]:<14}{lp['area']:>7.2f}{int(lp['pitch'] * 100):>4}cm{lp['loops']:>5}{lp['length']:>6.0f}m",
                fontsize=7, family="monospace", transform=lg.transAxes)
    y -= 0.04
    tot = sum(lp["area"] for lp in L["loops"])
    lg.text(0, y, f"Total : {L.get('collector_outlets', 0)} circuitos · {tot:.2f} m² aquecidos\nCircuito ≤ 120 m, tubo PEX Ø16".replace(".", ","),
            fontsize=7.5, transform=lg.transAxes)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def principle_png(res: dict) -> bytes:
    """Schéma de principe générique : PAC → module → ballon tampon → circuit plancher (collecteurs par niveau) / circuit VC."""
    plt = _mpl()
    from matplotlib.patches import FancyBboxPatch
    fig, ax = plt.subplots(figsize=(12, 9), dpi=170)
    ax.set_xlim(0, 120); ax.set_ylim(0, 90); ax.axis("off")

    def box(x, y, w, h, t, fc="#f4f6f8", ec="#333", fs=8.5, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=ec, lw=1.4))
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal")

    def arrow(x1, y1, x2, y2, c):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=c, lw=2.2, mutation_scale=13))

    ax.text(60, 87, "Esquema de princípio — bomba de calor ar-água reversível", ha="center", fontsize=12, fontweight="bold")
    ax.plot([22, 22], [50, 82], color="#555", lw=1.2, ls="--")
    ax.text(11, 80, "EXTERIOR", ha="center", fontsize=9, color="#555", fontweight="bold")
    ax.text(26, 80, "INTERIOR", ha="left", fontsize=9, color="#555", fontweight="bold")
    box(2, 55, 17, 14, "Bomba de calor\nar-água reversível\n(unidade exterior)", fc="#e8eef5", bold=True)
    box(27, 55, 20, 14, "Módulo hidráulico\n• vaso de expansão\n• válvula de segurança\n• separador de lamas\n  magnético", fc="#fff7e6", fs=8)
    box(54, 52, 13, 20, "Depósito\nde inércia\n50–100 L", fc="#fdecea")
    arrow(19, 64, 27, 64, HOT); arrow(27, 59, 19, 59, COLD); arrow(47, 64, 54, 64, HOT); arrow(54, 59, 47, 59, COLD)
    lvs = res.get("heated_levels") or []
    loops = {n: res["levels"][n].get("collector_outlets", 0) for n in lvs}
    vcs = {n: len(res["levels"][n]["vc"]) for n in lvs}
    ax.text(36, 47.5, "CIRCUITO 1 — Piso radiante (aquecimento / arrefecimento)", ha="center", fontsize=9.5, fontweight="bold", color="#7a3e00")
    ax.text(36, 44.8, "≈ 35 °C no inverno | ≈ 18 °C no verão (nunca abaixo do ponto de orvalho)", ha="center", fontsize=7.5, color="#555")
    ax.plot([57, 57, 41.6], [52, 38.5, 38.5], color=HOT, lw=2.6)
    box(31, 36, 10, 5, "Circulador 1", fc="white", fs=7.5)
    box(26, 27, 20, 6, "Válvula misturadora\n+ sonda de ida", fc="white", fs=7.5)
    ax.plot([36, 36], [36, 33], color=HOT, lw=2.6); ax.plot([36, 36], [27, 24], color=HOT, lw=2.6)
    txt = "\n".join(f"Coletor {n} : {loops[n]} circuitos" for n in lvs) or "Coletor"
    box(20, 12, 32, 12, txt + "\n+ sonda de ponto de orvalho", fc="white", fs=7.5)
    box(2, 26, 15, 7, "Termóstato por\ncompartimento (calor/frio)", fc="white", fs=7)
    ax.text(95, 47.5, "CIRCUITO 2 — Ventiloconvectores de teto", ha="center", fontsize=9.5, fontweight="bold", color="#0b4f7c")
    ax.text(95, 44.8, "Água fria ≈ 7 °C — ar frio insuflado pelo teto", ha="center", fontsize=7.5, color="#555")
    ax.plot([67, 76], [62, 62], color=COLD, lw=2.6)
    box(76, 59, 11, 6, "Circulador 2", fc="white", fs=7.5)
    ax.plot([87, 115, 115], [62, 62, 40], color=COLD, lw=2.6)
    vtxt = "\n".join(f"{n} : {vcs[n]} ventiloconvector(es)" for n in lvs if vcs[n]) or "Ventiloconvectores"
    box(74, 27, 42, 12, vtxt + "\nválvula de 2 vias por unidade", fc="#e3f1fb", ec=COLD, fs=7.5)
    box(80, 12, 30, 9, "Tabuleiro + bomba de condensados\npor unidade → drenagem", fc="white", fs=7.5)
    ax.text(95, 6, "Tubagens de água fria isoladas (anticondensação)", ha="center", fontsize=7.5, color=COLD, style="italic")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
