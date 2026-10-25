"""FrameModel : bâtiment à ossature BA sur trame (immeuble collectif, bureaux, commerce, parking, ERP).

Repère : x le long de la grande dimension (trame `grid.x`), y le long de la petite (`grid.y`), origine au coin
bas-gauche de l'emprise (nu extérieur des poteaux de rive). Cotes en mètres, niveaux = dessus de dalle brute.

Champs (voir cases/immeuble_demo_pt.json) :
  kind = "frame", building_type, project{name,address,country,client,architect,pc_ref,g2_ref}
  grid{x[],y[],x_labels[],y_labels[]}
  levels[{id,name,floor_top,height,use,on_grade?}]        du plus bas au plus haut ; height = hauteur d'étage
  roof{use}                                               dalle haute du dernier niveau (toiture)
  structure{column[b,h], beam[b,h], slab, concrete, steel, columns_omit[[xlab,ylab]], column_sections{"B3":[b,h]},
            void_cells[[xlab,ylab]]}                      cases de trame SANS plancher (emprise en L, U, cour…) : case
                                                          comprise entre la file xlab et la suivante, ylab et la suivante
  cores[{id,label,x0,y0,x1,y1,wall}]                      cages d'escalier / ascenseur (voiles BA)
  balconies[{side:N|S|E|W, depth, a0, a1, levels[]}]       balcons en console (a = abscisse le long de la façade)
  units[{id,name,typology,levels[],x0,y0,x1,y1,fixtures{}}] fractions / logements / lots (répétés sur `levels`)
  risers[{id,kind:AF|ECS|EU|EP|VENT|ELEC|GAZ,x,y,label?}]  colonnes montantes / chutes / gaines
  geotech{sigma_adm_mpa, depth, source}, facade{weight}, loads{partitions, finishes}, mep{hot_water}
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .lang import _

BLOCK, WARN = "bloquant", "avertissement"

# usage → (q FR, q PT, ψ2, libellé FR, libellé PT) — EN 1991-1-1 tableaux 6.1/6.2 + annexes nationales
USES = {
    "habitation":        (1.5, 2.0, 0.3, "Habitation (cat. A)", "Habitação (cat. A)"),
    "bureaux":           (2.5, 3.0, 0.3, "Bureaux (cat. B)", "Escritórios (cat. B)"),
    "commerce":          (5.0, 4.0, 0.6, "Commerce (cat. D1)", "Comércio (cat. D1)"),
    "scolaire":          (2.5, 3.0, 0.6, "Enseignement (cat. C1)", "Escolar (cat. C1)"),
    "public":            (4.0, 4.0, 0.6, "Lieu public (cat. C3)", "Espaço público (cat. C3)"),
    "stationnement":     (2.5, 2.5, 0.6, "Parking véhicules légers (cat. F)", "Estacionamento ligeiros (cat. F)"),
    "technique":         (5.0, 5.0, 0.8, "Locaux techniques (cat. E)", "Áreas técnicas (cat. E)"),
    "toiture":           (1.0, 0.4, 0.0, "Toiture-terrasse inaccessible (cat. H)", "Cobertura não acessível (cat. H)"),
    "terrasse":          (1.5, 2.0, 0.3, "Toiture-terrasse accessible", "Cobertura acessível"),
}
USE_ALIASES = {"habitação": "habitation", "habitacao": "habitation", "logement": "habitation", "residential": "habitation",
               "escritorios": "bureaux", "escritórios": "bureaux", "comércio": "commerce", "comercio": "commerce",
               "garagem": "stationnement", "estacionamento": "stationnement", "parking": "stationnement",
               "cobertura": "toiture", "terraço": "terrasse", "terraco": "terrasse", "escola": "scolaire",
               "equipement": "public", "erp": "public"}
BALCONY_Q = 3.5           # kN/m² balcons (EN 1991-1-1 tab. 6.2, valeur prudente)
CONCRETE = {"C20/25": 20, "C25/30": 25, "C30/37": 30, "C35/45": 35, "C40/50": 40}


def use_key(u: str | None) -> str:
    u = (u or "habitation").strip().lower()
    u = USE_ALIASES.get(u, u)
    return u if u in USES else "habitation"


@dataclass
class Level:
    id: str
    name: str
    z: float              # dessus de dalle (m)
    height: float         # hauteur d'étage (m)
    use: str
    on_grade: bool = False


@dataclass
class Slab:
    """Dalle portée : dalle du plancher d'un niveau (ou toiture). `carries` = niveau dont elle reçoit l'usage."""
    id: str
    name: str
    z: float
    use: str
    h: float
    level_below: str | None   # niveau dont les poteaux portent cette dalle


@dataclass
class Unit:
    id: str
    name: str
    typology: str
    level: str
    x0: float
    y0: float
    x1: float
    y1: float
    fixtures: dict

    @property
    def area(self) -> float:
        return round((self.x1 - self.x0) * (self.y1 - self.y0), 1)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclass
class Frame:
    raw: dict
    levels: list[Level] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)

    # ---------------- généralités
    @property
    def country(self) -> str:
        return (self.raw.get("project") or {}).get("country", "FR")

    @property
    def project(self) -> dict:
        return self.raw["project"]

    @property
    def gx(self) -> list[float]:
        return [float(v) for v in self.raw["grid"]["x"]]

    @property
    def gy(self) -> list[float]:
        return [float(v) for v in self.raw["grid"]["y"]]

    @property
    def xl(self) -> list[str]:
        lab = self.raw["grid"].get("x_labels") or []
        return [str(v) for v in lab] if len(lab) == len(self.gx) else [str(i + 1) for i in range(len(self.gx))]

    @property
    def yl(self) -> list[str]:
        lab = self.raw["grid"].get("y_labels") or []
        return [str(v) for v in lab] if len(lab) == len(self.gy) else [chr(65 + j) for j in range(len(self.gy))]

    @property
    def L(self) -> float:
        return self.gx[-1] - self.gx[0]

    @property
    def W(self) -> float:
        return self.gy[-1] - self.gy[0]

    @property
    def st(self) -> dict:
        return self.raw["structure"]

    @property
    def fck(self) -> float:
        return float(CONCRETE.get(str(self.st.get("concrete", "C25/30")).upper().replace(" ", ""), 25))

    @property
    def steel(self) -> str:
        return self.st.get("steel") or ("A500 NR" if self.country == "PT" else "B500B")

    # ---------------- poteaux
    def node_name(self, i: int, j: int) -> str:
        return f"{self.yl[j]}{self.xl[i]}"

    @property
    def voids(self) -> set[tuple[int, int]]:
        """Cases (i, j) sans plancher : i = file x à gauche, j = file y en dessous."""
        out = set()
        xi = {lab: k for k, lab in enumerate(self.xl)}
        yj = {lab: k for k, lab in enumerate(self.yl)}
        for v in self.st.get("void_cells") or []:
            try:
                a, b = str(v[0]), str(v[1])
            except (TypeError, IndexError):
                continue
            i, j = (xi.get(a), yj.get(b)) if a in xi else (xi.get(b), yj.get(a))
            if i is not None and j is not None and i < len(self.gx) - 1 and j < len(self.gy) - 1:
                out.add((i, j))
        return out

    def cell_in(self, i: int, j: int) -> bool:
        """La case (i, j) porte un plancher (dans la trame et pas évidée)."""
        return 0 <= i < len(self.gx) - 1 and 0 <= j < len(self.gy) - 1 and (i, j) not in self.voids

    def point_in(self, x: float, y: float) -> bool:
        """Point dans l'emprise réelle (cases pleines)."""
        gx, gy = self.gx, self.gy
        if not (gx[0] - 1e-6 <= x <= gx[-1] + 1e-6 and gy[0] - 1e-6 <= y <= gy[-1] + 1e-6):
            return False
        i = max(0, min(len(gx) - 2, next((k for k in range(len(gx) - 1) if x <= gx[k + 1] + 1e-9), len(gx) - 2)))
        j = max(0, min(len(gy) - 2, next((k for k in range(len(gy) - 1) if y <= gy[k + 1] + 1e-9), len(gy) - 2)))
        return self.cell_in(i, j)

    def boundary_edges(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Arêtes du contour réel (côtés de cases pleines bordant le vide ou l'extérieur)."""
        gx, gy = self.gx, self.gy
        out = []
        for j in range(len(gy) - 1):
            for i in range(len(gx) - 1):
                if not self.cell_in(i, j):
                    continue
                if not self.cell_in(i, j - 1):
                    out.append(((gx[i], gy[j]), (gx[i + 1], gy[j])))
                if not self.cell_in(i, j + 1):
                    out.append(((gx[i], gy[j + 1]), (gx[i + 1], gy[j + 1])))
                if not self.cell_in(i - 1, j):
                    out.append(((gx[i], gy[j]), (gx[i], gy[j + 1])))
                if not self.cell_in(i + 1, j):
                    out.append(((gx[i + 1], gy[j]), (gx[i + 1], gy[j + 1])))
        return out

    @property
    def footprint(self) -> float:
        gx, gy = self.gx, self.gy
        return sum((gx[i + 1] - gx[i]) * (gy[j + 1] - gy[j]) for j in range(len(gy) - 1) for i in range(len(gx) - 1) if self.cell_in(i, j))

    @property
    def columns(self) -> list[tuple[int, int]]:
        omit = {(str(a), str(b)) for a, b in (self.st.get("columns_omit") or [])}
        out = []
        voids = self.voids
        for j in range(len(self.gy)):
            for i in range(len(self.gx)):
                if (self.xl[i], self.yl[j]) in omit or (self.yl[j], self.xl[i]) in omit:
                    continue
                if voids and not any(self.cell_in(i + di, j + dj) for di in (-1, 0) for dj in (-1, 0)):
                    continue
                if self.in_core(self.gx[i], self.gy[j], strict=True):
                    continue
                out.append((i, j))
        return out

    def col_section(self, i: int, j: int) -> tuple[float, float]:
        sec = (self.st.get("column_sections") or {}).get(self.node_name(i, j)) or self.st.get("column") or [0.30, 0.30]
        return float(sec[0]), float(sec[1])

    @property
    def beam_section(self) -> tuple[float, float]:
        b = self.st.get("beam") or [0.30, 0.50]
        return float(b[0]), float(b[1])

    # ---------------- noyaux
    @property
    def cores(self) -> list[dict]:
        return [dict(c, wall=float(c.get("wall", 0.20))) for c in self.raw.get("cores") or []]

    def in_core(self, x: float, y: float, strict: bool = False) -> bool:
        e = 0.01 if strict else -0.01
        return any(c["x0"] + e < x < c["x1"] - e and c["y0"] + e < y < c["y1"] - e for c in self.cores)

    # ---------------- dalles portées
    def slab_h(self, lid: str | None = None) -> float:
        per = (self.st.get("slab_levels") or {})
        return float(per.get(lid, self.st.get("slab", 0.20)))

    @property
    def slabs(self) -> list[Slab]:
        out = []
        for k, lv in enumerate(self.levels):
            if lv.on_grade:
                continue
            below = self.levels[k - 1].id if k > 0 else None
            out.append(Slab(lv.id, lv.name, lv.z, lv.use, self.slab_h(lv.id), below))
        top = self.levels[-1]
        roof = self.raw.get("roof") or {}
        out.append(Slab("COB", _("Toiture", "Cobertura"), round(top.z + top.height, 3), use_key(roof.get("use", "toiture")),
                        self.slab_h("COB"), top.id))
        return out

    @property
    def base_level(self) -> Level:
        return self.levels[0]

    @property
    def height_total(self) -> float:
        return round(self.slabs[-1].z - self.levels[0].z, 2)

    # ---------------- balcons
    @property
    def balconies(self) -> list[dict]:
        return list(self.raw.get("balconies") or [])

    # ---------------- colonnes montantes
    @property
    def risers(self) -> list[dict]:
        return list(self.raw.get("risers") or [])

    def units_on(self, lid: str) -> list[Unit]:
        return [u for u in self.units if u.level == lid]

    def level(self, lid: str) -> Level:
        return next(l for l in self.levels if l.id == lid)

    @property
    def geo(self) -> dict:
        return self.raw.get("geotech") or {}


def load(path: str | Path) -> Frame:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def strip_none(v):
    """Champs « null » de la lecture IA → absents (les valeurs par défaut du moteur s'appliquent)."""
    if isinstance(v, dict):
        for k in [k for k, x in v.items() if x is None]:
            del v[k]
        for x in v.values():
            strip_none(x)
    elif isinstance(v, list):
        for x in v:
            strip_none(x)
    return v


def from_dict(raw: dict) -> Frame:
    strip_none(raw)
    for k in ("project", "structure", "grid", "roof", "geotech", "facade", "loads", "mep", "seismic"):
        if not isinstance(raw.get(k, {}), dict):
            raw.pop(k, None)
    raw.setdefault("project", {})
    for k, v in (("name", "Projet"), ("address", ""), ("country", "FR"), ("pc_ref", "—"), ("g2_ref", "—")):
        raw["project"].setdefault(k, v)
    raw.setdefault("structure", {})
    m = Frame(raw=raw)
    lv = sorted(raw["levels"], key=lambda d: float(d["floor_top"]))
    for k, d in enumerate(lv):
        m.levels.append(Level(str(d["id"]), str(d.get("name") or d["id"]), float(d["floor_top"]), float(d["height"]),
                              use_key(d.get("use")), bool(d.get("on_grade", k == 0))))
    ids = [l.id for l in m.levels]
    for u in raw.get("units") or []:
        for lid in (u.get("levels") or [u.get("level")]):
            if lid not in ids:
                continue
            m.units.append(Unit(f"{u['id']}" if len(u.get("levels") or [1]) == 1 else f"{lid}-{u['id']}",
                                str(u.get("name") or u["id"]), str(u.get("typology") or ""), lid,
                                float(u["x0"]), float(u["y0"]), float(u["x1"]), float(u["y1"]), dict(u.get("fixtures") or {})))
    return m


# ================================================================ contrôles avant calcul
def check(m: Frame) -> list[dict]:
    out = []

    def a(code, level, fr, pt, fix_fr="", fix_pt=""):
        out.append({"code": code, "level": level, "message": _(fr, pt), "fix": _(fix_fr, fix_pt)})

    for name, g in (("x", m.gx), ("y", m.gy)):
        if len(g) < 2:
            a("GRID-01", BLOCK, f"Trame {name} : au moins 2 files de poteaux sont nécessaires.",
              f"Trama {name}: são necessários pelo menos 2 alinhamentos de pilares.",
              "Relire le plan de coffrage / les plans de niveaux.", "Reler a planta de estrutura / plantas dos pisos.")
            continue
        spans = [b - a_ for a_, b in zip(g, g[1:])]
        if any(s <= 0 for s in spans):
            a("GRID-02", BLOCK, f"Trame {name} non croissante : {g}", f"Trama {name} não crescente: {g}",
              "Les abscisses des files doivent être croissantes.", "As coordenadas dos alinhamentos devem ser crescentes.")
        elif max(spans) > 12.0 or min(spans) < 1.5:
            a("GRID-03", BLOCK, f"Portées de trame {name} hors domaine (1,5 à 12 m) : {[round(s, 2) for s in spans]}",
              f"Vãos da trama {name} fora do domínio (1,5 a 12 m): {[round(s, 2) for s in spans]}",
              "Vérifier la trame (une file oubliée ?).", "Verificar a trama (falta um alinhamento?).")
        elif max(spans) > 8.5:
            a("GRID-04", WARN, f"Portée de {max(spans):.2f} m en trame {name} : dalle et poutres épaisses, une précontrainte peut être plus économique.",
              f"Vão de {max(spans):.2f} m na trama {name}: lajes e vigas espessas, o pré-esforço pode ser mais económico.")
    if not m.levels:
        a("LEV-01", BLOCK, "Aucun niveau.", "Nenhum piso.", "Relever les niveaux (coupes).", "Indicar os pisos (cortes).")
    for lv in m.levels:
        if not 2.2 <= lv.height <= 9.0:
            a("LEV-02", BLOCK, f"Hauteur d'étage {lv.name} = {lv.height} m hors domaine (2,20 à 9,00 m).",
              f"Altura do piso {lv.name} = {lv.height} m fora do domínio (2,20 a 9,00 m).", "Relire les coupes.", "Reler os cortes.")
    for k in range(1, len(m.levels)):
        d = round(m.levels[k].z - m.levels[k - 1].z, 3)
        if abs(d - m.levels[k - 1].height) > 0.05:
            a("LEV-03", BLOCK, f"Niveaux incohérents : {m.levels[k - 1].name} à {m.levels[k - 1].z} m + {m.levels[k - 1].height} m ≠ {m.levels[k].name} à {m.levels[k].z} m.",
              f"Cotas incoerentes: {m.levels[k - 1].name} a {m.levels[k - 1].z} m + {m.levels[k - 1].height} m ≠ {m.levels[k].name} a {m.levels[k].z} m.",
              "Corriger floor_top ou height.", "Corrigir floor_top ou height.")
    if len(m.columns) < 4:
        a("COL-01", BLOCK, "Moins de 4 poteaux sur la trame.", "Menos de 4 pilares na trama.")
    b, h = m.beam_section
    if not (0.15 <= b <= 0.80 and 0.25 <= h <= 1.50):
        a("BEAM-01", BLOCK, f"Section de poutre {b}×{h} hors domaine.", f"Secção de viga {b}×{h} fora do domínio.")
    if not 0.12 <= m.slab_h() <= 0.40:
        a("SLAB-01", BLOCK, f"Épaisseur de dalle {m.slab_h()} m hors domaine (0,12 à 0,40).", f"Espessura de laje {m.slab_h()} m fora do domínio (0,12 a 0,40).")
    x0, x1, y0, y1 = m.gx[0], m.gx[-1], m.gy[0], m.gy[-1]
    for u in m.units:
        if u.x0 < x0 - 0.5 or u.x1 > x1 + 0.5 or u.y0 < y0 - 0.5 or u.y1 > y1 + 0.5 or u.x1 <= u.x0 or u.y1 <= u.y0:
            a("UNIT-01", BLOCK, f"Fraction {u.name} ({u.level}) hors emprise ou rectangle invalide.",
              f"Fração {u.name} ({u.level}) fora da implantação ou retângulo inválido.", "Relire les plans de niveaux.", "Reler as plantas.")
    for c in m.cores:
        if not (x0 - 0.01 <= c["x0"] < c["x1"] <= x1 + 0.01 and y0 - 0.01 <= c["y0"] < c["y1"] <= y1 + 0.01):
            a("CORE-01", BLOCK, f"Noyau {c.get('id')} hors emprise.", f"Núcleo {c.get('id')} fora da implantação.")
    for r in m.risers:
        if not (x0 - 0.6 <= float(r["x"]) <= x1 + 0.6 and y0 - 0.6 <= float(r["y"]) <= y1 + 0.6):
            a("RIS-01", BLOCK, f"Colonne {r.get('id')} hors emprise.", f"Coluna {r.get('id')} fora da implantação.")
    if m.voids:
        for u in m.units:
            cx, cy = u.center
            if not m.point_in(cx, cy):
                a("UNIT-02", BLOCK, f"Fraction {u.name} ({u.level}) dans une case de trame déclarée vide (void_cells).",
                  f"Fração {u.name} ({u.level}) numa célula da trama declarada vazia (void_cells).",
                  "Corriger void_cells ou le rectangle de la fraction.", "Corrigir void_cells ou o retângulo da fração.")
        if m.footprint < 0.3 * m.L * m.W:
            a("VOID-01", BLOCK, "Cases vides > 70 % de la trame : emprise incohérente.", "Células vazias > 70 % da trama: implantação incoerente.")
    if not m.units:
        a("UNIT-00", WARN, "Aucune fraction / aucun lot relevé : réseaux et plans de niveaux limités aux colonnes.",
          "Nenhuma fração relevada: redes e plantas limitadas às colunas.")
    if m.country not in ("FR", "PT"):
        a("CTRY", BLOCK, "Pays non pris en charge (FR ou PT).", "País não suportado (FR ou PT).")
    return out


def has_block(anomalies: list[dict]) -> bool:
    return any(x.get("level") == BLOCK for x in anomalies)


def span_list(g: list[float]) -> list[float]:
    return [round(b - a, 3) for a, b in zip(g, g[1:])]


def ceil_to(v: float, step: float) -> float:
    return round(math.ceil(v / step - 1e-9) * step, 3)
