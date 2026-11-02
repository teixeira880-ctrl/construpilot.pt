"""Planta de arquiteto fictícia « Moradia Ferreira » (piso térreo, 1/50, A3) — versão .pt.

Mesma geometria que o plano demo do .fr; só o título e a morada mudam (Cascais, fictícia).

Géométrie en mètres, origine = angle intérieur sud-ouest. Sorties : PDF vectoriel + PNG
(pour le takeoff) + rooms.json (polygones en pixels du PNG, métré exact).
"""
import json, math, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Arc, Polygon, FancyArrow

EXT = 0.30          # mur extérieur
H = 2.50            # hauteur sous plafond
SCALE = 50          # 1/50
PAGE_W, PAGE_H = 420.0, 297.0   # A3 paysage (mm)
OX, OY = 45.0, 50.0             # origine intérieure sur la page (mm)
DPI = 120

def mm(x, y):  # mètres -> mm page
    return OX + x * 1000 / SCALE, OY + y * 1000 / SCALE

ROOMS = [  # id, x0, y0, x1, y1
    ("sejour",   0.0, 0.0, 7.4, 4.8),
    ("ch1",      7.5, 0.0, 12.0, 4.8),
    ("entree",   0.0, 4.9, 3.9, 7.4),
    ("wc",       0.0, 7.5, 1.4, 10.0),
    ("cellier",  1.5, 7.5, 3.9, 10.0),
    ("degag",    4.0, 4.9, 12.0, 6.0),
    ("ch2",      4.0, 6.1, 7.3, 10.0),
    ("sdb",      7.4, 6.1, 9.6, 10.0),
    ("ch3",      9.7, 6.1, 12.0, 10.0),
]
NAMES = {
 "fr": {"sejour": "Séjour / Cuisine", "ch1": "Chambre 1", "entree": "Entrée", "wc": "WC", "cellier": "Cellier",
        "degag": "Dégagement", "ch2": "Chambre 2", "sdb": "Salle de bain", "ch3": "Chambre 3"},
 "en": {"sejour": "Living / Kitchen", "ch1": "Bedroom 1", "entree": "Entrance", "wc": "WC", "cellier": "Utility room",
        "degag": "Hallway", "ch2": "Bedroom 2", "sdb": "Bathroom", "ch3": "Bedroom 3"},
 "pt": {"sejour": "Sala / Cozinha", "ch1": "Quarto 1", "entree": "Entrada", "wc": "WC", "cellier": "Lavandaria",
        "degag": "Corredor", "ch2": "Quarto 2", "sdb": "Casa de banho", "ch3": "Quarto 3"},
}
# Ouvertures : (pièces concernées, type, largeur, hauteur, mur, position)
#   mur : ("h", y, x_centre) mur horizontal à y ; ("v", x, y_centre) mur vertical à x
OPEN = [
 (["sejour"], "baie", 2.40, 2.15, ("h", 0.0 - EXT / 2, 3.2)),
 (["sejour"], "fenetre", 1.20, 1.25, ("v", 0.0 - EXT / 2, 2.4)),
 (["sejour"], "fenetre", 1.00, 1.05, ("h", 0.0 - EXT / 2, 6.3)),
 (["sejour", "entree"], "porte", 0.90, 2.04, ("h", 4.85, 2.6)),
 (["ch1"], "fenetre", 1.40, 1.35, ("h", 0.0 - EXT / 2, 9.75)),
 (["ch1", "degag"], "porte", 0.83, 2.04, ("h", 4.85, 11.0)),
 (["entree"], "porte_entree", 0.90, 2.15, ("v", 0.0 - EXT / 2, 6.15)),
 (["entree", "degag"], "porte", 0.90, 2.04, ("v", 3.95, 5.45)),
 (["wc", "entree"], "porte", 0.73, 2.04, ("h", 7.45, 0.75)),
 (["wc"], "fenetre", 0.40, 0.60, ("v", 0.0 - EXT / 2, 8.9)),
 (["cellier", "entree"], "porte", 0.83, 2.04, ("h", 7.45, 2.7)),
 (["cellier"], "fenetre", 0.60, 0.75, ("h", 10.0 + EXT / 2, 2.7)),
 (["ch2", "degag"], "porte", 0.83, 2.04, ("h", 6.05, 5.0)),
 (["ch2"], "fenetre", 1.20, 1.35, ("h", 10.0 + EXT / 2, 5.65)),
 (["sdb", "degag"], "porte", 0.73, 2.04, ("h", 6.05, 8.0)),
 (["sdb"], "fenetre", 0.60, 0.75, ("h", 10.0 + EXT / 2, 8.5)),
 (["ch3", "degag"], "porte", 0.83, 2.04, ("h", 6.05, 10.6)),
 (["ch3"], "fenetre", 1.00, 1.25, ("v", 12.0 + EXT / 2, 8.05)),
]
TXT = {
 "fr": {"title": "MAISON DUPONT — PLAN DU REZ-DE-CHAUSSÉE", "scale": "Échelle 1/50 · cotes en mètres · HSP 2,50 m",
        "fict": "Projet fictif de démonstration ConstruPilot — Atelier Lumen Architectes (fictif)",
        "addr": "Lotissement Les Vergers, lot 12 · 78400 Chatou (adresse fictive)", "shab": "Surface des pièces",
        "ind": "Indice A · 02/11/2026", "north": "N"},
 "en": {"title": "DUPONT HOUSE — GROUND FLOOR PLAN", "scale": "Scale 1:50 · dimensions in metres · ceiling 2.50 m",
        "fict": "Fictional ConstruPilot demo project — Atelier Lumen Architects (fictional)",
        "addr": "Les Vergers estate, plot 12 · 78400 Chatou, France (fictional address)", "shab": "Room floor area",
        "ind": "Rev. A · 02/11/2026", "north": "N"},
 "pt": {"title": "MORADIA FERREIRA — PLANTA DO RÉS-DO-CHÃO", "scale": "Escala 1/50 · cotas em metros · pé-direito 2,50 m",
        "fict": "Projeto fictício de demonstração ConstruPilot — Atelier Lumen Arquitetos (fictício)",
        "addr": "Rua das Amendoeiras, 12 · 2750-310 Cascais (morada fictícia)", "shab": "Área dos compartimentos",
        "ind": "Revisão A · 02/11/2026", "north": "N"},
}

def fmt(v, lang):
    s = f"{v:.2f}"
    return s if lang == "en" else s.replace(".", ",")

def room(rid):
    return next(r for r in ROOMS if r[0] == rid)

def draw(lang, out_base):
    fig = plt.figure(figsize=(PAGE_W / 25.4, PAGE_H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, PAGE_W); ax.set_ylim(0, PAGE_H); ax.set_aspect("equal"); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), PAGE_W, PAGE_H, fc="white", ec="none"))
    ax.add_patch(Rectangle((8, 8), PAGE_W - 16, PAGE_H - 16, fc="none", ec="black", lw=0.8))
    wall = "#2b2b2b"
    # Dalle extérieure (murs) = grand rectangle plein, puis on « creuse » les pièces
    x0, y0 = mm(-EXT, -EXT); x1, y1 = mm(12.0 + EXT, 10.0 + EXT)
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=wall, ec=wall, lw=0.6, hatch="////"))
    for rid, a, b, c, d in ROOMS:
        p0, p1 = mm(a, b), mm(c, d)
        ax.add_patch(Rectangle(p0, p1[0] - p0[0], p1[1] - p0[1], fc="white", ec="black", lw=0.5))
    # Ouvertures
    for rooms_, kind, w, h, (ori, pos, c) in OPEN:
        th = EXT if (ori == "v" and pos in (-EXT / 2, 12.0 + EXT / 2)) or (ori == "h" and pos in (-EXT / 2, 10.0 + EXT / 2)) else 0.10
        if ori == "h":
            a, b = mm(c - w / 2, pos - th / 2 - 0.01); cc, dd = mm(c + w / 2, pos + th / 2 + 0.01)
        else:
            a, b = mm(pos - th / 2 - 0.01, c - w / 2); cc, dd = mm(pos + th / 2 + 0.01, c + w / 2)
        ax.add_patch(Rectangle((a, b), cc - a, dd - b, fc="white", ec="none", zorder=3))
        if kind in ("fenetre", "baie"):
            if ori == "h":
                for f in (0.25, 0.5, 0.75):
                    yy = b + (dd - b) * f
                    ax.plot([a, cc], [yy, yy], color="black", lw=0.5, zorder=4)
                ax.plot([a, a], [b, dd], color="black", lw=0.6, zorder=4); ax.plot([cc, cc], [b, dd], color="black", lw=0.6, zorder=4)
            else:
                for f in (0.25, 0.5, 0.75):
                    xx = a + (cc - a) * f
                    ax.plot([xx, xx], [b, dd], color="black", lw=0.5, zorder=4)
                ax.plot([a, cc], [b, b], color="black", lw=0.6, zorder=4); ax.plot([a, cc], [dd, dd], color="black", lw=0.6, zorder=4)
        else:  # porte : battant + arc
            r = w * 1000 / SCALE
            if ori == "h":
                hx, hy = a, (b + dd) / 2
                ax.plot([hx, hx], [hy, hy + r], color="black", lw=0.7, zorder=4)
                ax.add_patch(Arc((hx, hy), 2 * r, 2 * r, theta1=0, theta2=90, lw=0.4, ls="--", zorder=4))
            else:
                hx, hy = (a + cc) / 2, b
                ax.plot([hx, hx + r], [hy, hy], color="black", lw=0.7, zorder=4)
                ax.add_patch(Arc((hx, hy), 2 * r, 2 * r, theta1=0, theta2=90, lw=0.4, ls="--", zorder=4))
    # Étiquettes pièces
    shab = 0.0
    for rid, a, b, c, d in ROOMS:
        s = (c - a) * (d - b); shab += s
        cx, cy = mm((a + c) / 2, (b + d) / 2)
        fs = 7 if (c - a) > 1.8 else 5.5
        ax.text(cx, cy + 2.2, NAMES[lang][rid], ha="center", va="center", fontsize=fs, weight="bold", zorder=5)
        ax.text(cx, cy - 2.2, f"{fmt(s, lang)} m²", ha="center", va="center", fontsize=fs - 0.5, zorder=5)
    # Cotations extérieures
    def dim_h(xa, xb, y, label, off):
        (pa, py), (pb, _) = mm(xa, y), mm(xb, y)
        yy = py + off
        ax.annotate("", xy=(pa, yy), xytext=(pb, yy), arrowprops=dict(arrowstyle="<->", lw=0.4, shrinkA=0, shrinkB=0))
        ax.plot([pa, pa], [py, yy + (1.5 if off > 0 else -1.5)], color="black", lw=0.3)
        ax.plot([pb, pb], [py, yy + (1.5 if off > 0 else -1.5)], color="black", lw=0.3)
        ax.text((pa + pb) / 2, yy + (1.2 if off > 0 else -2.6), label, ha="center", fontsize=5.5)
    def dim_v(ya, yb, x, label, off):
        (px, pa), (_, pb) = mm(x, ya), mm(x, yb)
        xx = px + off
        ax.annotate("", xy=(xx, pa), xytext=(xx, pb), arrowprops=dict(arrowstyle="<->", lw=0.4, shrinkA=0, shrinkB=0))
        ax.plot([px, xx + (1.5 if off > 0 else -1.5)], [pa, pa], color="black", lw=0.3)
        ax.plot([px, xx + (1.5 if off > 0 else -1.5)], [pb, pb], color="black", lw=0.3)
        ax.text(xx + (1.4 if off > 0 else -1.4), (pa + pb) / 2, label, va="center", ha="left" if off > 0 else "right", rotation=90, fontsize=5.5)
    dim_h(-EXT, 12.0 + EXT, -EXT, fmt(12.0 + 2 * EXT, lang), -14)
    dim_h(0.0, 7.4, -EXT, fmt(7.4, lang), -7); dim_h(7.5, 12.0, -EXT, fmt(4.5, lang), -7)
    dim_h(0.0, 1.4, 10.0 + EXT, fmt(1.4, lang), 7); dim_h(1.5, 3.9, 10.0 + EXT, fmt(2.4, lang), 7)
    dim_h(4.0, 7.3, 10.0 + EXT, fmt(3.3, lang), 7); dim_h(7.4, 9.6, 10.0 + EXT, fmt(2.2, lang), 7)
    dim_h(9.7, 12.0, 10.0 + EXT, fmt(2.3, lang), 7)
    dim_v(-EXT, 10.0 + EXT, -EXT, fmt(10.0 + 2 * EXT, lang), -14)
    dim_v(0.0, 4.8, -EXT, fmt(4.8, lang), -7); dim_v(4.9, 7.4, -EXT, fmt(2.5, lang), -7); dim_v(7.5, 10.0, -EXT, fmt(2.5, lang), -7)
    dim_v(0.0, 4.8, 12.0 + EXT, fmt(4.8, lang), 7); dim_v(4.9, 6.0, 12.0 + EXT, fmt(1.1, lang), 7); dim_v(6.1, 10.0, 12.0 + EXT, fmt(3.9, lang), 7)
    # Nord
    nx, ny = 330, 250
    ax.add_patch(Polygon([[nx, ny + 12], [nx - 4, ny], [nx, ny + 3], [nx + 4, ny]], closed=True, fc="black"))
    ax.text(nx, ny + 15, TXT[lang]["north"], ha="center", fontsize=9, weight="bold")
    # Cartouche
    cx0, cy0, cw, ch = 300, 14, 112, 58
    ax.add_patch(Rectangle((cx0, cy0), cw, ch, fc="white", ec="black", lw=0.8))
    for yy in (cy0 + 44, cy0 + 30, cy0 + 18, cy0 + 9):
        ax.plot([cx0, cx0 + cw], [yy, yy], color="black", lw=0.4)
    t = TXT[lang]
    ax.text(cx0 + 3, cy0 + 50, t["title"], fontsize=7, weight="bold", va="center")
    ax.text(cx0 + 3, cy0 + 37, t["scale"], fontsize=6, va="center")
    ax.text(cx0 + 3, cy0 + 24, f"{t['shab']} : {fmt(shab, lang)} m²", fontsize=6, va="center")
    ax.text(cx0 + 3, cy0 + 13.5, t["addr"], fontsize=4.6, va="center")
    ax.text(cx0 + 3, cy0 + 4.5, f"{t['fict']} · {t['ind']}", fontsize=3.9, va="center", style="italic")
    fig.savefig(out_base + ".pdf")
    fig.savefig(out_base + ".png", dpi=DPI)
    plt.close(fig)
    return shab

def takeoff_rooms(lang):
    """Polygones (pixels du PNG) + métré exact, au format plans_takeoff.rooms."""
    pxmm = DPI / 25.4
    hpx = round(PAGE_H * pxmm)
    def px(x, y):
        X, Y = mm(x, y)
        return [round(X * pxmm, 1), round(hpx - Y * pxmm, 1)]
    out = []
    for rid, a, b, c, d in ROOMS:
        w, l = c - a, d - b
        ops = []
        for rooms_, kind, ow, oh, _ in OPEN:
            if rid in rooms_:
                t = "fenetre" if kind in ("fenetre", "baie") else "porte"
                ops.append({"type": t, "width_m": ow, "height_m": oh, "area_m2": round(ow * oh, 2)})
        oarea = round(sum(o["area_m2"] for o in ops), 2)
        per = round(2 * (w + l), 2)
        gross = round(per * H, 2)
        out.append({"room_id": f"room_{rid}", "page_index": 0, "name": NAMES[lang][rid],
                    "points": [px(a, b), px(c, b), px(c, d), px(a, d)], "openings": ops,
                    "surface_m2": round(w * l, 2), "perimeter_m": per, "ceiling_area_m2": round(w * l, 2),
                    "ceiling_height_m": H, "wall_area_gross_m2": gross,
                    "wall_area_net_m2": round(gross - oarea, 2), "openings_area_m2": oarea})
    return out, {"pixels_per_meter": round(pxmm * 1000 / SCALE, 4),
                 "width_px": round(PAGE_W * pxmm), "height_px": hpx}

if __name__ == "__main__":
    out = sys.argv[1]
    shab = draw("pt", f"{out}/plan-moradia-ferreira-pt")
    rooms, meta = takeoff_rooms("pt")
    json.dump({"pt": {"rooms": rooms, "meta": meta, "shab": round(shab, 2)}},
              open(f"{out}/rooms_ferreira_pt.json", "w"), ensure_ascii=False, indent=1)
    print(round(shab, 2), meta)
