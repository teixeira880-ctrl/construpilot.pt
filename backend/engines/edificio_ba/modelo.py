"""Modelo do edifício (JSON → objeto Spec) e controlos de coerência do levantamento.

Referencial local (metros) : X ao longo da fachada de referência « y0 » (fachada principal), Y para o tardoz ; origem no eixo do
pilar de canto da fachada principal. Contorno retangular L × B entre eixos dos pilares de fachada. Sistema estrutural :
lajes maciças de betão armado sobre vigas, pilares, paredes e núcleos de escada/elevador ; cave enterrada opcional.

Formato (chaves em inglês, valores em metros) — ver casos/exemplo_pt.json :
  project   {name, address, municipality, altitude_m, country PT|FR, front_orientation N|NE|E|SE|S|SO|O|NO}
  levels    {basement bool, floors int (pisos de habitação acima da cave), storey_height, ground_floor_level, clear_height}
  footprint {L, B}
  columns   [{id, x, y, b?, h?}]                    pilares da arquitetura (b segundo X, h segundo Y)
  cores     [{id, kind stair|lift, x0, y0, x1, y1, t, door: {side x0|x1|y0|y1, width}}]
  walls     [{id, x0, y0, x1, y1, t, proposed?}]    paredes de betão (alinhadas com X ou Y)
  beams     null (automáticas) | [{id, x0, y0, x1, y1}]
  balconies [{side y0|y1|x0|x1, depth, from, to}]   varandas em consola
  basement  {polygon [[x,y]…], walls [{from i, to j, soil_height, name}], columns [{id, x, y}], parking_spaces}
  soil      {sigma_rd_kpa, sigma_sls_kpa, ground_type A–E, geotech_report bool, description}
  seismic   PT {zone_type1 "1.x", zone_type2 "2.x", q, importance} · FR {zone "1"–"5", q, importance}
  materials {concrete "C30/37"}
  units     [{id, level, typology "T2", rooms [{kind, name, area}], facades [{orientation, length}], common_wall_m,
              openings [{type, facade, count}]}]
  opening_types {V1: {width, height, label}}
  interior_walls_m {partitions, separating, common}   (ml por piso-tipo ; listas por nível aceites)
  network   {water_pressure_kpa, street_level}
  systems   {pv_kwp, heating, dhw}
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import perfis
from .textos import level_name, t

ORIENT = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
_DEG = {o: 45 * i for i, o in enumerate(ORIENT)}
BLOCK, WARN = "bloqueante", "aviso"


def _rot(o: str, deg: int) -> str:
    o = (o or "S").upper().replace("W", "O")
    return ORIENT[int(round(((_DEG.get(o, 180) + deg) % 360) / 45)) % 8]


def polygon_area(P) -> float:
    return abs(sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))) / 2


def point_in_polygon(x, y, P) -> bool:
    inside = False
    n = len(P)
    j = n - 1
    for i in range(n):
        xi, yi = P[i]
        xj, yj = P[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


@dataclass
class Spec:
    raw: dict
    country: str = "PT"
    lang: str = "pt"
    prof: dict = field(default_factory=dict)
    name: str = ""
    address: str = ""
    municipality: str = ""
    altitude: float | None = None
    front: str = "S"
    L: float = 0.0
    B: float = 0.0
    H: float = 3.0
    clear_h: float = 2.70
    n: int = 1
    basement: bool = False
    z0: float = 0.0
    columns: list = field(default_factory=list)
    cores: list = field(default_factory=list)
    walls: list = field(default_factory=list)
    beams_in: list | None = None
    balconies: list = field(default_factory=list)
    bpoly: list = field(default_factory=list)
    bwalls: list = field(default_factory=list)
    bcols: list = field(default_factory=list)
    parking: int = 0
    soil: dict = field(default_factory=dict)
    seismic: dict = field(default_factory=dict)
    fck: float = 30.0
    concrete: str = "C30/37"
    loads: dict = field(default_factory=dict)
    prices: dict = field(default_factory=dict)
    units: list = field(default_factory=list)
    opening_types: dict = field(default_factory=dict)
    interior: dict = field(default_factory=dict)
    network: dict = field(default_factory=dict)
    systems: dict = field(default_factory=dict)
    slab_h: float = 0.22
    slab_hg: float = 0.26
    facade_kn_m: float = 8.0
    parapet_kn_m: float = 1.0
    auto_walls: bool = True
    decisions: list = field(default_factory=list)

    # ---------------------------------------------------------------- níveis
    @property
    def fyk(self) -> float:
        return 500.0

    def levels(self) -> list[tuple[int, str, float]]:
        """[(k, nome, cota)] : −1 cave (se existir), 0 … n−1 pisos, n cobertura."""
        out = []
        if self.basement:
            out.append((-1, level_name(self, -1, self.n, True), round(self.z0 - self.H, 2)))
        for k in range(self.n + 1):
            out.append((k, level_name(self, k, self.n, self.basement), round(self.z0 + k * self.H, 2)))
        return out

    def lname(self, k: int) -> str:
        return level_name(self, k, self.n, self.basement)

    def side_orientation(self, side: str) -> str:
        return {"y0": self.front, "y1": _rot(self.front, 180), "x1": _rot(self.front, -90), "x0": _rot(self.front, 90)}[side]

    def side_of_orientation(self, o: str) -> str | None:
        for s in ("y0", "y1", "x0", "x1"):
            if self.side_orientation(s) == (o or "").upper().replace("W", "O"):
                return s
        return None

    @property
    def area_floor(self) -> float:
        return self.L * self.B

    def balcony_area(self) -> float:
        return sum((b["to"] - b["from"]) * b["depth"] for b in self.balconies)

    def basement_area(self) -> float:
        return polygon_area(self.bpoly) if self.basement and self.bpoly else 0.0

    def t(self, pt, fr):
        return t(self, pt, fr)


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v, default=-9) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _f(d, k, default=None):
    v = (d or {}).get(k)
    return default if v is None else v


def load(raw: dict) -> Spec:
    """Constrói o Spec com valores por defeito explícitos (registados em S.decisions)."""
    raw = raw or {}
    pr = raw.get("project") or {}
    country = (pr.get("country") or "PT").upper()
    prof = perfis.profile(country)
    S = Spec(raw=raw, country=country, lang=prof["lang"], prof=prof)
    S.name = pr.get("name") or "Edifício"
    S.address = pr.get("address") or ""
    S.municipality = pr.get("municipality") or ""
    S.altitude = pr.get("altitude_m")
    S.front = (pr.get("front_orientation") or "S").upper().replace("W", "O")
    lv = raw.get("levels") or {}
    S.basement = bool(lv.get("basement"))
    S.n = int(_f(lv, "floors", 1))
    S.H = float(_f(lv, "storey_height", 3.0))
    S.clear_h = float(_f(lv, "clear_height", round(S.H - 0.30, 2)))
    S.z0 = float(_f(lv, "ground_floor_level", 0.0))
    fp = raw.get("footprint") or {}
    S.L, S.B = float(_f(fp, "L", 0.0)), float(_f(fp, "B", 0.0))
    S.columns = [{"id": str(c.get("id") or f"P{i + 1}"), "x": float(c["x"]), "y": float(c["y"]),
                  "b": float(c["b"]) if c.get("b") else None, "h": float(c["h"]) if c.get("h") else None}
                 for i, c in enumerate(raw.get("columns") or [])]
    S.cores = []
    for i, c in enumerate(raw.get("cores") or []):
        x0, y0, x1, y1 = (float(c[k]) for k in ("x0", "y0", "x1", "y1"))
        door = c.get("door") or {}
        S.cores.append({"id": str(c.get("id") or ("NE" if c.get("kind") == "stair" else "NL") + (str(i + 1) if i else "")),
                        "kind": c.get("kind") or "stair", "box": (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
                        "t": float(_f(c, "t", 0.20)), "door_side": door.get("side"), "door": float(_f(door, "width", 0.0))})
    S.walls = []
    for i, w in enumerate(raw.get("walls") or []):
        x0, y0, x1, y1 = (float(w[k]) for k in ("x0", "y0", "x1", "y1"))
        S.walls.append(_wall(str(w.get("id") or f"W{i + 1}"), x0, y0, x1, y1, float(_f(w, "t", 0.25)), bool(w.get("proposed"))))
    S.beams_in = [{"id": str(b.get("id") or f"V{i + 1}"), "a": (float(b["x0"]), float(b["y0"])), "b": (float(b["x1"]), float(b["y1"]))}
                  for i, b in enumerate(raw.get("beams") or [])] or None
    S.balconies = [{"side": b.get("side") or "?", "depth": _num(b.get("depth")), "from": _num(_f(b, "from", 0.0)),
                    "to": _num(_f(b, "to", S.L if b.get("side") in ("y0", "y1") else S.B))} for b in raw.get("balconies") or []]
    bs = raw.get("basement") or {}
    if S.basement:
        S.bpoly = [(float(p[0]), float(p[1])) for p in bs.get("polygon") or []]
        if not S.bpoly and S.L and S.B:
            S.bpoly = [(0.0, 0.0), (S.L, 0.0), (S.L, S.B), (0.0, S.B)]
            S.decisions.append(t(S, "Contorno da cave não indicado : cave sob a projeção do edifício.",
                                 "Contour du sous-sol non indiqué : sous-sol sous l'emprise du bâtiment."))
        bw = bs.get("walls")
        if not bw:
            bw = [{"from": i, "to": (i + 1) % len(S.bpoly), "soil_height": S.H} for i in range(len(S.bpoly))]
            S.decisions.append(t(S, "Muros de cave em todo o contorno, com terras em toda a altura (por defeito).",
                                 "Voiles enterrés sur tout le contour, terres sur toute la hauteur (par défaut)."))
        S.bwalls = []
        for i, w in enumerate(bw):
            a, b = int(w["from"]), int(w["to"])
            S.bwalls.append({"name": w.get("name") or f"M{i + 1}", "i0": a, "i1": b, "ht": float(_f(w, "soil_height", S.H))})
        S.bcols = [{"id": str(c.get("id") or f"PG{i + 1}"), "x": float(c["x"]), "y": float(c["y"])} for i, c in enumerate(bs.get("columns") or [])]
        S.parking = int(_f(bs, "parking_spaces", 0))
    so = raw.get("soil") or {}
    S.soil = {"sigma_rd": float(_f(so, "sigma_rd_kpa", 300.0)), "sigma_sls": float(_f(so, "sigma_sls_kpa", 200.0)),
              "ground": (so.get("ground_type") or "B").upper(), "report": bool(so.get("geotech_report")), "description": so.get("description") or ""}
    if not so.get("sigma_rd_kpa"):
        S.decisions.append(t(S, "Sem estudo geotécnico : σRd = 300 kPa / σ serviço = 200 kPa admitidos (a confirmar por sondagens).",
                             "Sans étude de sol : σRd = 300 kPa / σ ELS = 200 kPa admis (à confirmer par une G2)."))
    se = raw.get("seismic") or {}
    if country == "FR":
        S.seismic = {"zone": str(_f(se, "zone", "2")), "q": float(_f(se, "q", 2.0)), "importance": se.get("importance") or "II"}
    else:
        S.seismic = {"zone1": str(_f(se, "zone_type1", "1.6")), "zone2": str(_f(se, "zone_type2", "2.5")), "q": float(_f(se, "q", 2.0)),
                     "importance": se.get("importance") or "II"}
    if not se:
        S.decisions.append(t(S, "Zonamento sísmico não indicado : zonas 1.6 / 2.5 admitidas (Grande Porto) — confirmar no Anexo Nacional.",
                             "Zone sismique non indiquée : zone 2 admise — à confirmer (arrêté du 22/10/2010)."))
    ma = raw.get("materials") or {}
    S.concrete = ma.get("concrete") or prof["concrete"]
    S.fck = perfis.fck_of(S.concrete)
    S.loads = {k: dict(v, **((raw.get("loads") or {}).get(k) or {})) for k, v in prof["loads"].items()}
    S.prices = dict(prof["prices"], **(raw.get("prices") or {}))
    S.units = [dict(u, level=_int(u.get("level"), -9)) for u in raw.get("units") or []]
    S.opening_types = raw.get("opening_types") or {}
    S.interior = raw.get("interior_walls_m") or {}
    S.network = raw.get("network") or {}
    S.systems = raw.get("systems") or {}
    sl = raw.get("slab") or {}
    S.slab_h = float(_f(sl, "h", 0.22))
    S.slab_hg = float(_f(sl, "h_basement_roof", 0.26))
    S.facade_kn_m = float(_f(raw, "facade_load_kn_m", 8.0))
    S.auto_walls = bool(_f(raw, "auto_walls", True))
    S.decisions += [str(d) for d in raw.get("_decisions") or []]
    return S


def _wall(wid, x0, y0, x1, y1, t_, proposed=False):
    ax = "Y" if abs(x1 - x0) < abs(y1 - y0) else "X"
    if ax == "Y":
        x = (x0 + x1) / 2
        a, b = sorted((y0, y1))
        return {"id": wid, "axis": "Y", "x0": x, "x1": x, "y0": a, "y1": b, "t": t_, "proposed": proposed, "Lw": round(b - a + t_, 3)}
    y = (y0 + y1) / 2
    a, b = sorted((x0, x1))
    return {"id": wid, "axis": "X", "x0": a, "x1": b, "y0": y, "y1": y, "t": t_, "proposed": proposed, "Lw": round(b - a + t_, 3)}


# ------------------------------------------------------------------ controlos
def validate(S: Spec) -> list[dict]:
    """→ [{level, code, message, fix}] ; um « bloqueante » impede o cálculo."""
    A = []

    def add(lvl, code, pt, fr, fix_pt="", fix_fr=""):
        A.append({"level": lvl, "code": code, "message": S.t(pt, fr), "fix": S.t(fix_pt, fix_fr)})
    if not (3.0 <= S.L <= 80.0 and 3.0 <= S.B <= 60.0):
        add(BLOCK, "FOOTPRINT", f"Contorno L × B = {S.L} × {S.B} m fora do domínio (3–80 m × 3–60 m).",
            f"Emprise L × B = {S.L} × {S.B} m hors domaine (3–80 m × 3–60 m).", "Indicar L e B entre eixos dos pilares de fachada.",
            "Indiquer L et B entre axes des poteaux de façade.")
        return A
    if not 1 <= S.n <= 12:
        add(BLOCK, "FLOORS", f"{S.n} pisos : fora do domínio do método (1 a 12).", f"{S.n} niveaux : hors domaine de la méthode (1 à 12).")
    if not 2.5 <= S.H <= 4.5:
        add(BLOCK, "STOREY", f"Pé-direito estrutural {S.H} m fora de 2,5–4,5 m.", f"Hauteur d'étage {S.H} m hors 2,5–4,5 m.")
    tol = 0.35
    seen = []
    for c in S.columns:
        if not (-tol <= c["x"] <= S.L + tol and -tol <= c["y"] <= S.B + tol):
            add(BLOCK, "COL-OUT", f"Pilar {c['id']} ({c['x']}, {c['y']}) fora do contorno do edifício.",
                f"Poteau {c['id']} ({c['x']}, {c['y']}) hors de l'emprise.", "Corrigir as coordenadas ou declará-lo como pilar da cave.",
                "Corriger les coordonnées ou le déclarer en poteau de sous-sol.")
        for o in seen:
            if math.hypot(o["x"] - c["x"], o["y"] - c["y"]) < 0.15:
                add(BLOCK, "COL-DUP", f"Pilares {o['id']} e {c['id']} sobrepostos.", f"Poteaux {o['id']} et {c['id']} superposés.")
        seen.append(c)
    for c in S.cores:
        x0, y0, x1, y1 = c["box"]
        if x1 - x0 < 1.2 or y1 - y0 < 1.2:
            add(BLOCK, "CORE-SIZE", f"Núcleo {c['id']} demasiado pequeno ({x1 - x0:.2f} × {y1 - y0:.2f} m).",
                f"Noyau {c['id']} trop petit ({x1 - x0:.2f} × {y1 - y0:.2f} m).")
        if x0 < -tol or y0 < -tol or x1 > S.L + tol or y1 > S.B + tol:
            add(BLOCK, "CORE-OUT", f"Núcleo {c['id']} fora do contorno.", f"Noyau {c['id']} hors de l'emprise.")
        for col in S.columns:
            if x0 + 0.05 < col["x"] < x1 - 0.05 and y0 + 0.05 < col["y"] < y1 - 0.05:
                add(BLOCK, "COL-IN-CORE", f"Pilar {col['id']} dentro do núcleo {c['id']}.", f"Poteau {col['id']} dans le noyau {c['id']}.")
        if not 0.15 <= c["t"] <= 0.40:
            add(WARN, "CORE-T", f"Espessura do núcleo {c['id']} = {c['t']} m (corrente 0,20–0,30).",
                f"Épaisseur du noyau {c['id']} = {c['t']} m (courant 0,20–0,30).")
    for w in S.walls:
        if w["Lw"] < 1.0:
            add(BLOCK, "WALL-SHORT", f"Parede {w['id']} com {w['Lw']:.2f} m : usar pilar.", f"Voile {w['id']} de {w['Lw']:.2f} m : prévoir un poteau.")
        if w["x0"] < -tol or w["x1"] > S.L + tol or w["y0"] < -tol or w["y1"] > S.B + tol:
            add(BLOCK, "WALL-OUT", f"Parede {w['id']} fora do contorno.", f"Voile {w['id']} hors de l'emprise.")
    n_vert = len(S.columns) + len(S.cores) + len(S.walls)
    if n_vert < 4:
        add(BLOCK, "FEW-SUPPORTS", "Menos de 4 elementos verticais : levantamento incompleto.", "Moins de 4 éléments porteurs verticaux : relevé incomplet.")
    for b in S.balconies:
        if b["side"] not in ("y0", "y1", "x0", "x1"):
            add(BLOCK, "BALC-SIDE", f"Varanda com fachada « {b['side']} » desconhecida.", f"Balcon sur façade « {b['side']} » inconnue.")
        elif not 0.4 <= b["depth"] <= 3.0:
            add(BLOCK, "BALC-DEPTH", f"Varanda em consola de {b['depth']} m fora de 0,4–3,0 m.", f"Balcon en console de {b['depth']} m hors 0,4–3,0 m.")
        elif b["depth"] > 2.2:
            add(WARN, "BALC-LONG", f"Consola de {b['depth']} m : prever apoio ou viga em consola.", f"Console de {b['depth']} m : prévoir une poutre console.")
    if S.basement:
        P = S.bpoly
        if len(P) < 3 or polygon_area(P) < 10:
            add(BLOCK, "BASEMENT-POLY", "Contorno da cave inválido.", "Contour du sous-sol invalide.")
        for w in S.bwalls:
            if not (0 <= w["i0"] < len(P) and 0 <= w["i1"] < len(P)):
                add(BLOCK, "BASEMENT-WALL", f"Muro {w['name']} refere vértices inexistentes.", f"Voile {w['name']} : sommets inexistants.")
            elif not 0 <= w["ht"] <= 6.0:
                add(BLOCK, "BASEMENT-SOIL", f"Muro {w['name']} : altura de terras {w['ht']} m fora de 0–6 m.",
                    f"Voile {w['name']} : hauteur de terres {w['ht']} m hors 0–6 m.")
        for c in S.bcols:
            if len(P) >= 3 and not point_in_polygon(c["x"], c["y"], P):
                add(BLOCK, "BCOL-OUT", f"Pilar da cave {c['id']} fora do contorno da cave.", f"Poteau de sous-sol {c['id']} hors du contour.")
    if S.fck > 50:
        add(BLOCK, "CONCRETE", f"Betão {S.concrete} : os motores cobrem até C50/60.", f"Béton {S.concrete} : les moteurs couvrent jusqu'à C50/60.",
            "Indicar uma classe ≤ C50/60.", "Indiquer une classe ≤ C50/60.")
    for w in S.raw.get("walls") or []:
        try:
            if abs(float(w["x1"]) - float(w["x0"])) > 0.05 and abs(float(w["y1"]) - float(w["y0"])) > 0.05:
                add(BLOCK, "WALL-DIAG", f"Parede {w.get('id')} oblíqua : só paredes alinhadas com X ou Y são tratadas.",
                    f"Voile {w.get('id')} oblique : seuls les voiles parallèles à X ou Y sont traités.")
        except (KeyError, TypeError, ValueError):
            pass
    lv_ok = set(range(S.n))
    for u in S.units:
        if _int(u.get("level"), -9) not in lv_ok:
            add(BLOCK, "UNIT-LEVEL", f"Fração {u.get('id')} num nível inexistente ({u.get('level')}).", f"Logement {u.get('id')} : niveau inexistant ({u.get('level')}).")
        a = sum(_num(r.get("area")) for r in u.get("rooms") or [])
        if a <= 5:
            add(BLOCK, "UNIT-AREA", f"Fração {u.get('id')} sem divisões com área.", f"Logement {u.get('id')} sans pièces surfacées.")
        for o in u.get("openings") or []:
            if o.get("type") not in S.opening_types:
                add(BLOCK, "OPENING-TYPE", f"Vão do tipo « {o.get('type')} » (fração {u.get('id')}) sem dimensões em opening_types.",
                    f"Baie de type « {o.get('type')} » (logement {u.get('id')}) sans dimensions dans opening_types.")
    for k in range(S.n):
        a = sum(sum(_num(r.get("area")) for r in u.get("rooms") or []) for u in S.units if _int(u.get("level"), -9) == k)
        if a > S.area_floor * 1.02:
            add(BLOCK, "UNIT-SUM", f"Áreas das frações do {S.lname(k)} ({a:.0f} m²) superiores à área do piso ({S.area_floor:.0f} m²).",
                f"Surfaces des logements du {S.lname(k)} ({a:.0f} m²) supérieures à l'emprise ({S.area_floor:.0f} m²).")
    return A
