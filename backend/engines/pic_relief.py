"""Relevo, modelo do edifício por pisos, alturas reais das gruas e corte vertical do estaleiro.

- Terreno: interpolado (inverso do quadrado da distância) a partir de pontos cotados — lidos na
  planta, introduzidos pelo utilizador ou pedidos a um modelo digital de terreno oficial.
  Sem pontos cotados, o terreno é plano e isso é dito.
- Edifício: pisos acima e abaixo da soleira, altura piso a piso, cota de soleira.
- Grua: a altura sob o gancho necessária é calculada a partir da cota da base da grua (no
  terreno) até ao ponto mais alto a sobrevoar, mais a folga e a altura da carga: um desnível
  entre a base da grua e o edifício entra diretamente no cálculo.
- Corte vertical A–A′: alturas e distâncias à mesma escala, desenhado em SVG vetorial (o mesmo
  desenho serve o ecrã, o PDF e a folha técnica).
O código é igual nas versões PT e FR; só LANG muda.
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

LANG = "pt"

_T = {
    "pt": {
        "hyp_floor": "Altura piso a piso de {h} m: valor de trabalho, a confirmar com os cortes do projeto.",
        "hyp_levels": "Número de pisos acima da soleira deduzido da altura do edifício: {n}.",
        "hyp_height": "Altura do edifício deduzida dos pisos: {n} × {h} m = {t} m.",
        "hyp_soleira": "Cota de soleira não indicada: adotada a cota média do terreno sob o edifício ({z} m).",
        "hyp_terrain": "Relevo interpolado a partir de {n} pontos cotados ({src}): aproximado entre pontos, "
                       "não substitui o levantamento topográfico.",
        "hyp_flat": "Sem pontos cotados: terreno considerado plano no corte e na vista 3D.",
        "hyp_slope": "Zonas de estaleiro com mais de {p} % de inclinação assinaladas (valor de trabalho).",
        "crane_base": "Grua {i}: base à cota {zb} m e soleira do edifício à cota {z0} m (desnível de {dz} m) — "
                      "incluído na altura sob o gancho ({h} m).",
        "obst_unknown": "Grua {i}: «{label}» está sob a lança e a sua altura não foi indicada — não foi "
                        "verificada no corte.",
        "slope": "«{label}» fica num terreno com cerca de {p} % de inclinação ({dz} m de desnível): preveja "
                 "plataforma ou regularização.",
        "relief": "Desnível no estaleiro: {d} m (cotas {a} a {b} m).",
        "title": "Corte vertical A–A′",
        "subtitle": "Alturas e distâncias à mesma escala · torre e contra-lança esquemáticas",
        "terrain": "Terreno", "terrain_flat": "Terreno (plano — sem pontos cotados)",
        "building": "Edifício", "crane": "Grua", "jib": "lança", "reach": "alcance",
        "hook": "altura sob o gancho necessária", "clear": "folga", "load": "carga",
        "limit": "limite", "unknown_h": "altura não indicada", "z": "cota",
        "levels_up": lambda n: "R/C" if n <= 1 else f"R/C+{n - 1}",
        "levels_down": lambda n: f"{n} cave" if n == 1 else f"{n} caves",
        "base": "base", "top": "topo", "soleira": "soleira", "dz": "desnível base da grua / soleira",
        "rel": "cotas relativas à soleira (±0,00)", "abs": "cotas altimétricas (m)",
        "line": "Linha elétrica", "scale": "escala gráfica",
        "g_building": "Edifício", "q_height": "Altura do edifício (m) — vazio = pisos × altura piso a piso",
        "q_up": "Pisos acima do solo (incluindo o R/C)", "q_down": "Pisos enterrados (caves)",
        "q_fh": "Altura piso a piso (m)", "q_z0": "Cota de soleira (m) — vazio = cota do terreno",
        "q_oh": "Altura dos edifícios vizinhos / árvores sob a lança (m)",
        "src_plan": "lidos na planta", "src_user": "introduzidos pelo utilizador",
        "pdf_aerial": "Vista aérea do estaleiro",
        "pdf_aerial_note": "Vista de cima da maqueta 3D, à escala da planta; alturas das instalações indicativas.",
        "sheet_p2": "PLANO DE ESTALEIRO — CORTE E VISTAS", "sheet_axis": "A–A′: corte vertical (folha 2)",
        "v3d": "Vista 3D", "vaer": "Vista aérea", "alt_note": "Altitudes: {src} (grelha 7 × 7).",
        "obst": {"arbre": "Árvore", "batiment_existant": "Edifício existente", "voisin": "Construção vizinha",
                 "autre": "Obstáculo", "ligne_electrique": "Linha elétrica"},
    },
    "fr": {
        "hyp_floor": "Hauteur d'étage de {h} m : valeur de travail, à confirmer avec les coupes du projet.",
        "hyp_levels": "Nombre de niveaux au-dessus du rez-de-chaussée déduit de la hauteur du bâtiment : {n}.",
        "hyp_height": "Hauteur du bâtiment déduite des niveaux : {n} × {h} m = {t} m.",
        "hyp_soleira": "Cote du rez-de-chaussée non indiquée : cote moyenne du terrain sous le bâtiment "
                       "retenue ({z} m).",
        "hyp_terrain": "Relief interpolé à partir de {n} points cotés ({src}) : approché entre les points, "
                       "ne remplace pas le levé topographique.",
        "hyp_flat": "Aucun point coté : terrain considéré plat dans la coupe et la vue 3D.",
        "hyp_slope": "Zones de chantier de plus de {p} % de pente signalées (valeur de travail).",
        "crane_base": "Grue {i} : pied à la cote {zb} m et rez-de-chaussée du bâtiment à la cote {z0} m "
                      "(dénivelé de {dz} m) — inclus dans la hauteur sous crochet ({h} m).",
        "obst_unknown": "Grue {i} : « {label} » est sous la flèche et sa hauteur n'a pas été indiquée — non "
                        "vérifié dans la coupe.",
        "slope": "« {label} » est sur un terrain d'environ {p} % de pente ({dz} m de dénivelé) : prévoir "
                 "une plateforme ou un nivellement.",
        "relief": "Dénivelé sur l'emprise : {d} m (cotes {a} à {b} m).",
        "title": "Coupe verticale A–A′",
        "subtitle": "Hauteurs et distances à la même échelle · mât et contre-flèche schématiques",
        "terrain": "Terrain", "terrain_flat": "Terrain (plat — aucun point coté)",
        "building": "Bâtiment", "crane": "Grue", "jib": "flèche", "reach": "portée",
        "hook": "hauteur sous crochet nécessaire", "clear": "garde", "load": "charge",
        "limit": "limite", "unknown_h": "hauteur non indiquée", "z": "cote",
        "levels_up": lambda n: "RDC" if n <= 1 else f"R+{n - 1}",
        "levels_down": lambda n: f"{n} sous-sol" if n == 1 else f"{n} sous-sols",
        "base": "pied", "top": "sommet", "soleira": "RDC", "dz": "dénivelé pied de grue / RDC",
        "rel": "cotes relatives au RDC (±0,00)", "abs": "cotes altimétriques (m)",
        "line": "Ligne électrique", "scale": "échelle graphique",
        "g_building": "Bâtiment", "q_height": "Hauteur du bâtiment (m) — vide = niveaux × hauteur d'étage",
        "q_up": "Niveaux hors sol (RDC compris)", "q_down": "Niveaux enterrés (sous-sols)",
        "q_fh": "Hauteur d'étage (m)", "q_z0": "Cote du rez-de-chaussée (m) — vide = cote du terrain",
        "q_oh": "Hauteur des bâtiments voisins / arbres sous la flèche (m)",
        "src_plan": "lus sur le plan", "src_user": "saisis par l'utilisateur",
        "pdf_aerial": "Vue aérienne du chantier",
        "pdf_aerial_note": "Vue de dessus de la maquette 3D, à l'échelle du plan ; hauteurs des installations indicatives.",
        "sheet_p2": "PLAN D'INSTALLATION DE CHANTIER — COUPE ET VUES", "sheet_axis": "A–A′ : coupe verticale (folio 2)",
        "v3d": "Vue 3D", "vaer": "Vue aérienne", "alt_note": "Altitudes : {src} (grille 7 × 7).",
        "obst": {"arbre": "Arbre", "batiment_existant": "Bâtiment existant", "voisin": "Construction voisine",
                 "autre": "Obstacle", "ligne_electrique": "Ligne électrique"},
    },
}
T = _T[LANG]

SLOPE_MAX_PCT = 5.0      # inclinação acima da qual uma zona de estaleiro é assinalada (valor de trabalho)
COUNTER_RATIO = 0.26     # contra-lança esquemática (só para desenho)


def _fr(v, nd=2) -> str:
    if v is None:
        return "—"
    s = f"{float(v):.{nd}f}".rstrip("0").rstrip(".") if nd else f"{float(v):.0f}"
    return s.replace(".", ",")


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Terreno
# ---------------------------------------------------------------------------
class Terrain:
    """Superfície do terreno por inverso do quadrado da distância (8 pontos mais próximos)."""

    def __init__(self, pts_m: list[tuple[float, float, float]], source: str = ""):
        self.pts = [(float(x), float(y), float(z)) for x, y, z in pts_m]
        self.source = source

    def z(self, x: float, y: float) -> float:
        near = sorted(((x - px) ** 2 + (y - py) ** 2, pz) for px, py, pz in self.pts)[:8]
        if near[0][0] < 1e-6:
            return near[0][1]
        w = [1.0 / d for d, _ in near]
        return sum(wi * z for wi, (_, z) in zip(w, near)) / sum(w)

    def zmin(self) -> float:
        return min(p[2] for p in self.pts)

    def zmax(self) -> float:
        return max(p[2] for p in self.pts)


def terrain_from_site(site: dict) -> Terrain | None:
    """`site["spot_heights"]` = [[x, y, z], …] com x, y normalizados 0–1 (como o resto do site)."""
    k = _num(site.get("m_per_px"))
    if not k:
        return None
    W, H = float(site["img_w"]) * k, float(site["img_h"]) * k
    pts = []
    for p in site.get("spot_heights") or []:
        try:
            x, y, z = float(p[0]), float(p[1]), float(p[2])
        except (TypeError, ValueError, IndexError):
            continue
        if 0 <= x <= 1 and 0 <= y <= 1 and -500 < z < 9000:
            pts.append((x * W, y * H, z))
    if len(pts) < 3:
        return None
    return Terrain(pts, str(site.get("spot_source") or ""))


def norm_spots(lst) -> list[list[float]]:
    out = []
    for p in lst or []:
        try:
            x, y, z = float(p[0]), float(p[1]), float(p[2])
        except (TypeError, ValueError, IndexError):
            continue
        if all(math.isfinite(v) for v in (x, y, z)) and -500 < z < 9000:
            out.append([round(min(max(x, 0.0), 1.0), 5), round(min(max(y, 0.0), 1.0), 5), round(z, 2)])
    return out[:400]


def spots_from_analysis(d: dict) -> list[list[float]]:
    """Pontos cotados lidos pela IA: [{"point": [x, y], "z": 181.13}, …]."""
    raw = []
    for s in d.get("spot_heights") or []:
        if isinstance(s, dict) and isinstance(s.get("point"), (list, tuple)) and len(s["point"]) == 2:
            raw.append([s["point"][0], s["point"][1], s.get("z")])
    return norm_spots(raw)


def grid_points(frame: dict, n: int = 7) -> list[tuple[float, float]]:
    """Grelha n × n de (lat, lon) sobre o enquadramento de uma vista aérea."""
    out = []
    for j in range(n):
        lat = frame["maxlat"] - (frame["maxlat"] - frame["minlat"]) * (j + 0.5) / n
        for i in range(n):
            lon = frame["minlon"] + (frame["maxlon"] - frame["minlon"]) * (i + 0.5) / n
            out.append((lat, lon))
    return out


def grid_spots(zs: list, n: int = 7) -> list[list[float]]:
    """Pontos cotados normalizados correspondentes a `grid_points`."""
    out = []
    for k, z in enumerate(zs or []):
        if z is None:
            continue
        j, i = divmod(k, n)
        out.append([(i + 0.5) / n, (j + 0.5) / n, z])
    return norm_spots(out)


def slope_pct(terrain: Terrain | None, poly) -> tuple[float, float]:
    """(inclinação % , desnível m) de uma zona retangular."""
    if terrain is None:
        return 0.0, 0.0
    cs = list(poly.exterior.coords)[:-1]
    zs = [terrain.z(x, y) for x, y in cs]
    span = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in cs for b in cs) or 1.0
    dz = max(zs) - min(zs)
    return 100.0 * dz / span, dz


# ---------------------------------------------------------------------------
# Edifício por pisos
# ---------------------------------------------------------------------------
def building_model(a: dict, buildings: list, terrain: Terrain | None) -> dict:
    notes = []
    fh = _num(a.get("floor_h_m"))
    if not fh or fh <= 0:
        fh = 3.0
    if not _num(a.get("floor_h_m")) or abs(fh - 3.0) < 1e-9:
        notes.append(T["hyp_floor"].format(h=_fr(fh)))
    up = _num(a.get("levels_above"))
    down = max(int(_num(a.get("levels_below")) or 0), 0)
    hb = _num(a.get("hauteur_batiment_m"))
    if hb is None and up:
        hb = round(up * fh, 2)
        notes.append(T["hyp_height"].format(n=int(up), h=_fr(fh), t=_fr(hb)))
    if up is None and hb:
        up = max(1, round(hb / fh))
        notes.append(T["hyp_levels"].format(n=int(up)))
    z0 = _num(a.get("ground_floor_z"))
    if z0 is None:
        if terrain is not None and buildings:
            u = unary_union(buildings)
            pts = [(x, y) for x, y in u.exterior.coords] if u.geom_type == "Polygon" else \
                [(x, y) for g in u.geoms for x, y in g.exterior.coords]
            c = u.centroid
            pts.append((c.x, c.y))
            z0 = round(sum(terrain.z(x, y) for x, y in pts) / len(pts), 2)
            notes.append(T["hyp_soleira"].format(z=_fr(z0)))
        else:
            z0 = 0.0
    return {"height": hb, "floor_h": fh, "levels_above": int(up) if up else None, "levels_below": down,
            "z_soleira": z0, "z_top": (z0 + hb) if hb is not None else None, "z_bottom": z0 - down * fh,
            "absolute": terrain is not None or _num(a.get("ground_floor_z")) is not None, "notes": notes}


def top_to_clear(center, radius: float, bm: dict, buildings: list, obstacles: list, a: dict,
                 terrain: Terrain | None) -> tuple[float | None, list[str]]:
    """Cota mais alta a sobrevoar dentro do disco da lança, e os obstáculos de altura desconhecida."""
    disc = Point(center).buffer(max(radius, 0.1), 64)
    tops, unknown = [], []
    if bm["z_top"] is not None and any(b.intersects(disc) for b in buildings):
        tops.append(bm["z_top"])
    oh = _num(a.get("obstacle_h_m"))
    for o in obstacles:
        if o["type"] == "ligne_electrique" or not o["poly"].intersects(disc):
            continue
        base = terrain.z(o["x"], o["y"]) if terrain else bm["z_soleira"]
        if oh is not None:
            tops.append(base + oh)
        else:
            unknown.append(o["label"])
    return (max(tops) if tops else None), unknown


# ---------------------------------------------------------------------------
# Corte vertical
# ---------------------------------------------------------------------------
def _clip(o, u, W, H) -> tuple[float, float]:
    lo, hi = -1e9, 1e9
    for p, d, m in ((o[0], u[0], W), (o[1], u[1], H)):
        if abs(d) < 1e-12:
            if not 0 <= p <= m:
                return 0.0, 0.0
            continue
        a, b = (0 - p) / d, (m - p) / d
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
    return lo, hi


def section(site: dict, parcel, buildings: list, bm: dict, terrain: Terrain | None, cranes: list,
            obstacles: list, a: dict) -> dict | None:
    k = _num(site.get("m_per_px"))
    if not k or not buildings:
        return None
    W, H = float(site["img_w"]) * k, float(site["img_h"]) * k
    b_union = unary_union(buildings)
    live = [c for c in cranes if c.get("jib_m")]
    if len(live) >= 2:
        o = (live[0]["x"], live[0]["y"])
        d = math.hypot(live[1]["x"] - o[0], live[1]["y"] - o[1]) or 1.0
        u = ((live[1]["x"] - o[0]) / d, (live[1]["y"] - o[1]) / d)
        need = (min(-live[0]["jib_m"] * COUNTER_RATIO - 6, d - live[1]["jib_m"] - 4),
                max(live[0]["jib_m"] + 4, d + live[1]["jib_m"] * COUNTER_RATIO + 6))
    elif live:
        o = (live[0]["x"], live[0]["y"])
        pts = [p for g in ([b_union] if b_union.geom_type == "Polygon" else list(b_union.geoms))
               for p in g.exterior.coords]
        far = max(pts, key=lambda p: math.hypot(p[0] - o[0], p[1] - o[1]))
        d = math.hypot(far[0] - o[0], far[1] - o[1]) or 1.0
        u = ((far[0] - o[0]) / d, (far[1] - o[1]) / d)
        need = (-live[0]["jib_m"] * COUNTER_RATIO - 8, max(live[0]["jib_m"], d) + 6)
    else:
        rect = b_union.minimum_rotated_rectangle
        cs = list(rect.exterior.coords)
        e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        e = e1 if math.hypot(*e1) >= math.hypot(*e2) else e2
        n = math.hypot(*e) or 1.0
        u = (e[0] / n, e[1] / n)
        c = b_union.centroid
        o = (c.x, c.y)
        half = math.hypot(*e) / 2
        need = (-half - 12, half + 12)
    lo, hi = _clip(o, u, W, H)
    s0, s1 = max(lo, need[0]), min(hi, need[1])
    if s1 - s0 < 5:
        return None
    P = lambda s: (o[0] + s * u[0], o[1] + s * u[1])  # noqa: E731
    line = LineString([P(s0), P(s1)])
    proj = lambda x, y: (x - o[0]) * u[0] + (y - o[1]) * u[1]  # noqa: E731
    flat = bm["z_soleira"]
    zf = (lambda x, y: terrain.z(x, y)) if terrain else (lambda x, y: flat)
    n = 240
    prof = []
    for i in range(n + 1):
        s = s0 + (s1 - s0) * i / n
        x, y = P(s)
        prof.append([round(s, 2), round(zf(x, y), 3)])

    def cuts(poly):
        inter = poly.intersection(line)
        segs = [inter] if inter.geom_type == "LineString" else list(getattr(inter, "geoms", []))
        out = []
        for g in segs:
            if g.geom_type != "LineString" or g.length < 0.05:
                continue
            ss = sorted(proj(*p) for p in g.coords)
            out.append((round(ss[0], 2), round(ss[-1], 2)))
        return out

    bcut = [{"s0": a_, "s1": b_} for b in buildings for a_, b_ in cuts(b)]
    ocut = []
    oh = _num(a.get("obstacle_h_m"))
    for ob in obstacles:
        for a_, b_ in cuts(ob["poly"]):
            mx, my = P((a_ + b_) / 2)
            base = zf(mx, my)
            h = None if ob["type"] == "ligne_electrique" else oh
            ocut.append({"s0": a_, "s1": b_, "type": ob["type"], "label": ob["label"], "z_base": round(base, 2),
                         "h": h})
    limits = []
    inter = parcel.exterior.intersection(line)
    for g in ([inter] if inter.geom_type == "Point" else list(getattr(inter, "geoms", []))):
        if g.geom_type == "Point":
            limits.append(round(proj(g.x, g.y), 2))
    cr_out = []
    for idx, c in enumerate(live):
        s = proj(c["x"], c["y"])
        side = -1 if (len(live) >= 2 and idx == 1) else 1
        cr_out.append({"num": c["num"], "label": c["label"], "s": round(s, 2), "off": round(abs(
            (c["x"] - o[0]) * u[1] - (c["y"] - o[1]) * u[0]), 2), "side": side,
            "z_base": c.get("z_base"), "hook_z": c.get("hook_z"), "hsc": c.get("hsc_required_m"),
            "jib": c["jib_m"], "reach": c.get("reach_required_m"), "ok": c.get("ok"),
            "hc": _num(a.get("hauteur_charge_m")), "garde": _num(a.get("garde_m"))})
    pts_m = [P(s0), P(s1)]
    return {"axis": [[round(x, 2), round(y, 2)] for x, y in pts_m],
            "axis_n": [[round(x / W, 5), round(y / H, 5)] for x, y in pts_m],
            "s0": round(s0, 2), "s1": round(s1, 2), "profile": prof, "buildings": bcut, "obstacles": ocut,
            "limits": limits, "cranes": cr_out, "bm": {k_: bm[k_] for k_ in
                                                      ("height", "floor_h", "levels_above", "levels_below",
                                                       "z_soleira", "z_top", "z_bottom", "absolute")},
            "flat": terrain is None}


def terrain_grid(site: dict, terrain: Terrain | None, z_ref: float, n: int = 48) -> dict | None:
    """Grelha de alturas relativas (z − z_ref) para a vista 3D: n × n nós, da esquerda para a direita
    e de cima (y = 0) para baixo."""
    if terrain is None:
        return None
    k = float(site["m_per_px"])
    W, H = float(site["img_w"]) * k, float(site["img_h"]) * k
    z = []
    for j in range(n):
        for i in range(n):
            z.append(round(terrain.z(W * i / (n - 1), H * j / (n - 1)) - z_ref, 3))
    return {"n": n, "z": z, "z_ref": z_ref}


# ---------------------------------------------------------------------------
# Desenho do corte (SVG)
# ---------------------------------------------------------------------------
def section_svg(sec: dict, width: int = 1600) -> str:
    bm = sec["bm"]
    ab = bm["absolute"]
    zref = 0.0 if ab else bm["z_soleira"]

    def zl(z):          # rótulo de cota
        if z is None:
            return "—"
        v = z - zref
        return ("+" if v > 0.004 and not ab else "") + ("±0,00" if abs(v) < 0.005 and not ab else _fr(v, 2))

    prof = sec["profile"]
    zs = [p[1] for p in prof]
    top = [bm["z_top"] or bm["z_soleira"]] + [c["hook_z"] or 0 for c in sec["cranes"] if c["hook_z"]]
    apex = [(c["hook_z"] or (bm["z_top"] or bm["z_soleira"]) + 6) + 1.4 + max(c["jib"] * 0.11, 5)
            for c in sec["cranes"]]
    zmin = min(zs + [bm["z_bottom"]]) - 2.5
    zmax = max(zs + top + apex + [o["z_base"] + (o["h"] or 0) for o in sec["obstacles"]]) + 3
    ml, mr, mt, mb = 96, 40, 92, 70
    ext = [sec["s0"], sec["s1"]]
    for c in sec["cranes"]:
        ext += [c["s"] + c["side"] * c["jib"], c["s"] - c["side"] * (c["jib"] * COUNTER_RATIO + 2)]
    sa, sb = min(ext) - 2, max(ext) + 2
    span = sb - sa
    kx = (width - ml - mr) / span
    ky_max = 1150 - mt - mb
    k = min(kx, ky_max / (zmax - zmin))
    plot_w = span * k
    hgt = int((zmax - zmin) * k + mt + mb)
    X = lambda s: ml + (s - sa) * k  # noqa: E731
    Y = lambda z: mt + (zmax - z) * k  # noqa: E731
    F = "font-family=\"Helvetica, Arial, sans-serif\""
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{hgt}" viewBox="0 0 {width} {hgt}">',
         f'<rect x="0" y="0" width="{width}" height="{hgt}" fill="#ffffff"/>',
         f'<rect x="{ml}" y="{mt}" width="{plot_w:.1f}" height="{(zmax - zmin) * k:.1f}" fill="#EAF6FF"/>']
    xs0, xs1 = ml + (sec["s0"] - sa) * k, ml + (sec["s1"] - sa) * k

    def txt(x, y, s, size=14, color="#0A0D14", anchor="start", weight="normal"):
        o.append(f'<text x="{x:.1f}" y="{y:.1f}" {F} font-size="{size}" fill="{color}" text-anchor="{anchor}" '
                 f'font-weight="{weight}">{escape(str(s))}</text>')

    def line(x1, y1, x2, y2, color="#0A0D14", w=1.5, dash=None):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
                 f'stroke-width="{w}"{da}/>')

    def rect(x, y, w, h, fill, stroke="none", sw=1, op=1.0, dash=None):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0.5):.1f}" height="{max(h, 0.5):.1f}" fill="{fill}" '
                 f'fill-opacity="{op}" stroke="{stroke}" stroke-width="{sw}"{da}/>')

    def mark(x, z, label, color="#0A0D14", right=True):
        y = Y(z)
        o.append(f'<path d="M {x - 7:.1f} {y - 12:.1f} L {x + 7:.1f} {y - 12:.1f} L {x:.1f} {y:.1f} Z" '
                 f'fill="{color}"/>')
        txt(x + (10 if right else -10), y - 3, label, 13, color, "start" if right else "end", "bold")

    def vdim(x, z1, z2, label, color):
        line(x, Y(z1), x, Y(z2), color, 1.6)
        for z in (z1, z2):
            line(x - 7, Y(z), x + 7, Y(z), color, 1.6)
        ym = (Y(z1) + Y(z2)) / 2
        o.append(f'<text x="{x - 8:.1f}" y="{ym:.1f}" {F} font-size="13" fill="{color}" text-anchor="middle" '
                 f'font-weight="bold" transform="rotate(-90 {x - 8:.1f} {ym:.1f})">{escape(label)}</text>')

    # grelha de cotas
    step = 2 if zmax - zmin <= 30 else 5 if zmax - zmin <= 80 else 10
    zt = math.ceil(zmin / step) * step
    while zt <= zmax:
        line(ml, Y(zt), ml + plot_w, Y(zt), "#C9DDEB", 0.8)
        txt(ml - 8, Y(zt) + 5, zl(zt), 12, "#475569", "end")
        zt += step
    # terreno
    pts = " ".join(f"{X(s):.1f},{Y(z):.1f}" for s, z in prof)
    o.append(f'<polygon points="{X(prof[0][0]):.1f},{Y(zmin):.1f} {pts} {X(prof[-1][0]):.1f},{Y(zmin):.1f}" '
             f'fill="#D9C7A4" stroke="none"/>')
    o.append(f'<polyline points="{pts}" fill="none" stroke="#6D4C41" stroke-width="3"/>')
    # limites do estaleiro
    for s in sec["limits"]:
        line(X(s), mt + 22, X(s), Y(min(zs)) + 6, "#FF1744", 2.2, "10 6")
        txt(X(s) + 5, mt + 18, T["limit"], 12, "#FF1744", "start", "bold")
    # obstáculos
    for ob in sec["obstacles"]:
        x0, x1 = X(ob["s0"]), X(ob["s1"])
        if ob["type"] == "ligne_electrique":
            txt((x0 + x1) / 2, Y(ob["z_base"]) - 8, f'{T["line"]} — {T["unknown_h"]}', 12, "#B45309", "middle", "bold")
            line((x0 + x1) / 2, Y(ob["z_base"]), (x0 + x1) / 2, Y(ob["z_base"]) - 6, "#B45309", 2)
            continue
        if ob["h"]:
            color = "#2E7D32" if ob["type"] == "arbre" else "#78909C"
            rect(x0, Y(ob["z_base"] + ob["h"]), x1 - x0, ob["h"] * k, color, "#37474F", 1, 0.55)
            txt((x0 + x1) / 2, Y(ob["z_base"] + ob["h"]) - 6, ob["label"], 12, "#37474F", "middle")
        else:
            rect(x0, Y(ob["z_base"]) - 4, x1 - x0, 4, "#78909C", op=0.8)
            txt((x0 + x1) / 2, Y(ob["z_base"]) - 10, f'{ob["label"]} — {T["unknown_h"]}', 12, "#37474F", "middle")
    # edifício
    for b in sec["buildings"]:
        x0, x1 = X(b["s0"]), X(b["s1"])
        if bm["height"] is not None:
            rect(x0, Y(bm["z_top"]), x1 - x0, (bm["z_top"] - bm["z_soleira"]) * k, "#FFC400", "#7A5A00", 2, 0.92)
        if bm["levels_below"]:
            rect(x0, Y(bm["z_soleira"]), x1 - x0, (bm["z_soleira"] - bm["z_bottom"]) * k, "#B0A79A", "#4E463C", 2, 0.95)
        fh = bm["floor_h"]
        for i in range(1, (bm["levels_above"] or 0)):
            z = bm["z_soleira"] + i * fh
            if bm["z_top"] is None or z < bm["z_top"] - 0.1:
                line(x0, Y(z), x1, Y(z), "#7A5A00", 1.2)
        for i in range(1, bm["levels_below"]):
            line(x0, Y(bm["z_soleira"] - i * fh), x1, Y(bm["z_soleira"] - i * fh), "#4E463C", 1.2)
        line(x0, Y(bm["z_soleira"]), x1, Y(bm["z_soleira"]), "#0A0D14", 2.4)
    if sec["buildings"] and not sec["flat"]:      # terreno natural por cima (escavação visível)
        o.append(f'<polyline points="{pts}" fill="none" stroke="#6D4C41" stroke-width="1.6" stroke-dasharray="7 5"/>')
    if sec["buildings"]:
        bx0 = X(min(b["s0"] for b in sec["buildings"]))
        bx1 = X(max(b["s1"] for b in sec["buildings"]))
        name = T["building"]
        if bm["levels_above"]:
            name += f' {T["levels_up"](bm["levels_above"])}'
        if bm["levels_below"]:
            name += f' + {T["levels_down"](bm["levels_below"])}'
        if bm["height"] is None:
            name += f' — {T["unknown_h"]}'
        ztop = bm["z_top"] if bm["z_top"] is not None else bm["z_soleira"]
        txt((bx0 + bx1) / 2, Y(ztop) - 24, name, 15, "#5C4300", "middle", "bold")
        mark(bx1 + 4, bm["z_soleira"], f'{T["soleira"]} {zl(bm["z_soleira"])}')
        if bm["z_top"] is not None:
            mark(bx1 + 4, bm["z_top"], f'{T["top"]} {zl(bm["z_top"])}')
    # gruas
    for c in sec["cranes"]:
        xc = X(c["s"])
        zb = c["z_base"] if c["z_base"] is not None else bm["z_soleira"]
        hook = c["hook_z"] if c["hook_z"] is not None else (bm["z_top"] or bm["z_soleira"]) + 6
        jz = hook + 1.4
        red = "#FF1744" if c["ok"] else "#B91C1C"
        mw = 1.7 * k
        # base / fundação
        rect(xc - 2.4 * k, Y(zb), 4.8 * k, 1.2 * k, "#9E9E9E", "#424242", 1)
        # torre em treliça
        rect(xc - mw / 2, Y(jz), mw, (jz - zb) * k, "none", red, 2)
        zz, flip = zb, 1
        while zz + 1.7 < jz:
            line(xc - mw / 2 * flip, Y(zz), xc + mw / 2 * flip, Y(zz + 1.7), red, 1)
            zz += 1.7
            flip = -flip
        # lança e contra-lança
        jx = xc + c["side"] * c["jib"] * k
        cx = xc - c["side"] * c["jib"] * COUNTER_RATIO * k
        line(min(xc, jx), Y(jz), max(xc, jx), Y(jz), red, 3.2)
        line(min(xc, jx), Y(jz + 1.2), max(xc, jx), Y(jz + 1.2), red, 1.4)
        line(min(xc, cx), Y(jz + 0.6), max(xc, cx), Y(jz + 0.6), red, 3)
        rect(cx - 1.5 * k * (1 if c["side"] > 0 else 0), Y(jz + 0.3), 1.5 * k, 2.2 * k, "#455A64")
        ah = max(c["jib"] * 0.11, 5)
        line(xc, Y(jz), xc, Y(jz + ah), red, 2.4)
        line(xc, Y(jz + ah), jx - c["side"] * c["jib"] * 0.28 * k, Y(jz + 1.2), "#263238", 1.1)
        line(xc, Y(jz + ah), cx, Y(jz + 0.6), "#263238", 1.1)
        txt(xc, Y(jz + ah) - 10, f'{T["crane"]} {c["num"]} — {c["label"]}', 15, red, "middle", "bold")
        txt((xc + jx) / 2, Y(jz + 1.2) - 8, f'{T["jib"]} {_fr(c["jib"])} m', 13, red, "middle", "bold")
        # carga pendurada no ponto mais afastado a servir
        if c["reach"]:
            xr = xc + c["side"] * min(c["reach"], c["jib"]) * k
            hc = c["hc"] or 0.0
            line(xr, Y(jz), xr, Y(hook - max(hc - 1.2, 0)), "#1B1B1B", 1.4)
            rect(xr - 0.9 * k, Y(hook - max(hc - 1.2, 0)), 1.8 * k, 1.2 * k, "#E53935", "#7F0000", 1)
            if bm["z_top"] is not None and hc:
                low = hook - hc
                if low > bm["z_top"] + 0.05:
                    vdim(xr + c["side"] * 14, bm["z_top"], low, f'{T["clear"]} {_fr(low - bm["z_top"])} m',
                         "#00A843")
            line(xc, Y(zb) + 20, xr, Y(zb) + 20, "#2979FF", 1.4)
            txt((xc + xr) / 2, Y(zb) + 36, f'{T["reach"]} {_fr(c["reach"], 1)} m', 13, "#2979FF", "middle", "bold")
        # altura sob o gancho
        if c["hsc"] is not None:
            vdim(xc - c["side"] * (mw / 2 + 20), zb, hook, f'{_fr(c["hsc"])} m — {T["hook"]}', "#2979FF")
        mark(xc + c["side"] * (mw / 2 + 4), zb, f'{T["base"]} {zl(zb)}', "#0A0D14", c["side"] > 0)
        dz = zb - bm["z_soleira"]
        if abs(dz) >= 0.5 and not sec["flat"]:
            txt(xc, Y(zb) + 56, f'{T["dz"]}: {_fr(dz)} m', 13, "#B45309", "middle", "bold")
    # títulos, legenda, escala gráfica
    txt(ml, 34, T["title"], 24, "#0F5257", "start", "bold")
    txt(ml, 58, T["subtitle"] + " · " + (T["abs"] if ab else T["rel"]), 13, "#475569")
    if sec["flat"]:
        txt(ml + plot_w, 34, T["terrain_flat"], 13, "#6D4C41", "end", "bold")
    bar = next((b for b in (50, 20, 10, 5, 2) if b * k <= plot_w / 4), 2)
    yb = hgt - 26
    line(ml, yb, ml + bar * k, yb, "#0A0D14", 4)
    line(ml, yb - 6, ml, yb + 6, "#0A0D14", 2)
    line(ml + bar * k, yb - 6, ml + bar * k, yb + 6, "#0A0D14", 2)
    txt(ml + bar * k + 10, yb + 5, f'{bar} m — {T["scale"]}', 13)
    txt(xs0 + 4, Y(prof[0][1]) - 10, "A", 22, "#0F5257", "start", "bold")
    txt(xs1 - 4, Y(prof[-1][1]) - 10, "A′", 22, "#0F5257", "end", "bold")
    o.append("</svg>")
    return "".join(o)
