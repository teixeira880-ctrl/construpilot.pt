"""Divisões (nome, tipo, área, posição) e vãos exteriores sobre a geometria REAL.

Duas fontes, confrontadas:
  1. quadro de áreas escrito nas peças desenhadas («3.Sala Comum - 44,80m²», «Quarto 15,00 m²»…) — leitura de texto;
  2. a IA localiza cada divisão sobre o NOSSO desenho do edifício (transformação conhecida → coordenadas exatas em metros).
Uma posição só é aceite dentro da área de construção; as zonas de cada divisão são células de Voronoi recortadas
pelo contorno (zona aproximada, usada só para implantar equipamentos e cotar — nunca para áreas: as áreas são as
declaradas, ou a célula quando nada está escrito, assinalado como hipótese).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field

from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.ops import unary_union, voronoi_diagram

from .model import Building

log = logging.getLogger(__name__)

TYPES = [   # (tipo, palavras) — por ordem: o primeiro que casa ganha
    ("casa_de_banho", ("inst. san", "inst san", "i.s.", "i.s ", "instalacao sanitaria", "instalacoes sanitarias", "wc", "casa de banho",
                       "banho", "sdb", "sde", "salle d'eau", "salle de bain", "toilette")),
    ("cozinha", ("cozinha", "kitchenette", "cuisine", "copa")),
    ("lavandaria", ("lavandaria", "buanderie", "tratamento de roupa")),
    ("garagem", ("garagem", "garage", "parqueamento", "estacionamento")),
    ("tecnico", ("tecnic", "técnic", "caldeira", "local tech", "chaufferie")),
    ("arrumos", ("despensa", "arrumo", "arrecada", "closet", "dressing", "roupeiro", "cellier", "rangement", "vestiar")),
    ("corredor", ("circula", "corredor", "hall", "entrada", "vestibulo", "átrio", "atrio", "degagement", "dégagement", "couloir", "escada")),
    ("escritorio", ("escritorio", "escritório", "bureau", "biblioteca", "office")),
    ("quarto", ("quarto", "suite", "chambre", "dormit")),
    ("sala", ("sala", "estar", "social", "jantar", "living", "sejour", "séjour", "salon", "jogos", "multiusos")),
    ("exterior", ("varanda", "terraco", "terraço", "piscina", "alpendre", "logradouro", "patio", "pátio", "jardim", "terrasse",
                  "balcon", "loggia", "deck")),
]
UNHEATED = {"garagem", "tecnico", "exterior"}
WET = {"casa_de_banho", "cozinha", "lavandaria"}
PRINCIPAL = {"sala", "quarto", "escritorio"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def room_type(name: str, default: str | None = "sala") -> str | None:
    n = " " + _norm(name) + " "
    for t, words in TYPES:
        if any(_norm(w) in n for w in words):
            return t
    return default


@dataclass
class Room:
    name: str
    area: float                       # área útil (m²)
    type: str = "sala"
    x: float | None = None            # posição (m, eixos do Building)
    y: float | None = None
    zone: Polygon | None = None       # zona aproximada (Voronoi ∩ contorno)
    source: str = ""                  # "quadro" | "ia" | "geometria"
    number: str = ""

    @property
    def heated(self) -> bool:
        return self.type not in UNHEATED

    @property
    def placed(self) -> bool:
        return self.x is not None and self.y is not None

    def to_dict(self) -> dict:
        return {"name": self.name, "area": self.area, "type": self.type, "x": self.x, "y": self.y, "source": self.source,
                "number": self.number}


@dataclass
class Opening:
    edge: LineString                  # troço do contorno (m)
    width: float
    orient: str                       # N, NE, E, SE, S, SO, O, NO (normal exterior)
    height: float = 2.20
    sill: float = 0.0
    kind: str = "envidracado"


@dataclass
class Window:
    name: str
    w: float                          # largura (m)
    h: float                          # altura (m)
    qty: int = 1
    room: str = ""
    orient: str = ""

    @property
    def area(self) -> float:
        return round(self.w * self.h * self.qty, 2)


@dataclass
class Layout:
    rooms: list[Room] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)       # mapa de vãos (texto), se existir
    notes: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)

    @property
    def useful_area(self) -> float:
        return round(sum(r.area for r in self.rooms if r.heated), 2)

    def wet(self):
        return [r for r in self.rooms if r.type in WET]


# ----------------------------------------------------------------------------- 1. quadro de áreas (texto)
_AREA_LINE = re.compile(
    r"^\s*(?:(?P<num>\d{1,2}[a-z]?)\s*[.\-)]\s*)?(?P<name>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .'/()º-]{1,48}?)\s*[-–:=]?\s*"
    r"(?:A\s*=\s*)?(?P<area>\d{1,3}(?:[.,]\d{1,2}))\s*m\s*(?:2|²)\s*$", re.I)
_SKIP = ("total", "area de construcao", "area bruta", "implantacao", "lote", "terreno", "impermeabiliz", "cobertura",
         "area util total", "abc", "pv", "m2 ")


def schedule_from_text(texts: list[str]) -> list[Room]:
    """Quadro de áreas escrito numa peça desenhada. Fica o quadro mais completo (uma folha), sem duplicados."""
    best: list[Room] = []
    for txt in texts:
        rows, seen = [], set()
        for raw in (txt or "").splitlines():
            m = _AREA_LINE.match(raw.strip())
            if not m:
                continue
            name = re.sub(r"\s+", " ", m.group("name")).strip(" .-–")
            if len(name) < 2 or any(s in _norm(name) for s in _SKIP) or re.fullmatch(r"[A-Z]{1,3}\d*", name):
                continue
            if not m.group("num") and room_type(name, None) is None:     # «Tinta plástica 36,5 m²» não é uma divisão
                continue
            area = float(m.group("area").replace(",", "."))
            if not 0.8 <= area <= 400:
                continue
            key = (m.group("num") or "", _norm(name), area)
            if key in seen:
                continue
            seen.add(key)
            rows.append(Room(name=name, area=area, type=room_type(name), source="quadro", number=m.group("num") or ""))
        if len(rows) > len(best):
            best = rows
    return best


def doc_texts(docs) -> list[tuple[int, int, str]]:
    """(doc, página, texto) de todas as páginas PDF."""
    import pymupdf
    out = []
    for i, d in enumerate(docs):
        try:
            pdf = pymupdf.open(stream=d[1], filetype="pdf")
        except Exception:  # noqa: BLE001
            continue
        for j, page in enumerate(pdf):
            if j > 60:
                break
            out.append((i, j, page.get_text() or ""))
    return out


# ----------------------------------------------------------------------------- 2. o nosso desenho (para a IA)
def plan_png(b: Building, px: int = 1400) -> tuple[bytes, callable]:
    """PNG do contorno e das paredes lidas + função (u, v ∈ 0..1000) → (x, y) em metros."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x0, y0, x1, y1 = b.footprint.bounds
    pad = 0.06 * max(x1 - x0, y1 - y0)
    X0, Y0, X1, Y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    w_in = 10.0
    h_in = w_in * (Y1 - Y0) / (X1 - X0)
    fig = plt.figure(figsize=(w_in, h_in), dpi=px / w_in)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(X0, X1)
    ax.set_ylim(Y0, Y1)
    ax.axis("off")
    for p in getattr(b.footprint, "geoms", [b.footprint]):
        ax.fill(*p.exterior.xy, color="#f3f4f6", lw=0)
        ax.plot(*p.exterior.xy, color="#111", lw=1.5)
        for h in p.interiors:
            ax.fill(*h.xy, color="white", lw=0)
            ax.plot(*h.xy, color="#111", lw=1.2)
    for w in b.walls:
        ax.add_patch(matplotlib.patches.Polygon(list(w.line.buffer(w.t / 2, cap_style=2).exterior.coords), color="#111"))
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)

    def to_m(u, v):
        return X0 + float(u) / 1000 * (X1 - X0), Y1 - float(v) / 1000 * (Y1 - Y0)
    return buf.getvalue(), to_m


ROOMS_SYSTEM = "És um arquiteto a ler peças desenhadas. Respondes só com JSON válido."
ROOMS_PROMPT = """Primeira imagem: folha original da planta (com os nomes e áreas das divisões, ou números remetendo para um quadro).
Segunda imagem: o MESMO piso redesenhado por nós (contorno e paredes a preto), noutra escala/posição; pode estar rodado ou espelhado
em relação à folha — orienta-te pela forma do contorno e pelos pátios.
{known}
Para cada divisão, devolve o seu centro na SEGUNDA imagem (coordenadas 0–1000, 0,0 = canto superior esquerdo):
{{"rooms": [{{"name": "Sala Comum", "area_m2": 44.8, "x": 512, "y": 300}}, ...]}}
Só divisões que vês nas duas imagens. Não inventes áreas: area_m2 = valor escrito, ou null."""


async def ask_rooms(llm, sheet_png: bytes, b: Building, known: list[Room]) -> list[Room]:
    if llm is None:
        return []
    ours, to_m = plan_png(b)
    k = ("Divisões do quadro de áreas: " + "; ".join(f"{r.number + '. ' if r.number else ''}{r.name} {r.area:.2f} m²" for r in known)
         if known else "Lê também os nomes e as áreas escritas.")
    try:
        txt = await llm(ROOMS_SYSTEM, ROOMS_PROMPT.format(known=k),
                        images=[base64.b64encode(sheet_png).decode(), base64.b64encode(ours).decode()], max_tokens=4000)
        m = re.search(r"\{.*\}", txt or "", re.S)
        data = json.loads(m.group(0)) if m else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("bet_geo rooms AI failed: %s", type(exc).__name__)
        return []
    out = []
    for it in data.get("rooms") or []:
        try:
            x, y = to_m(it["x"], it["y"])
            a = it.get("area_m2")
            out.append(Room(name=str(it.get("name") or "Divisão")[:60], area=float(a) if a else 0.0,
                            type=room_type(str(it.get("name") or "")), x=round(x, 2), y=round(y, 2), source="ia"))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _merge(known: list[Room], placed: list[Room], fp, notes: list[str]) -> list[Room]:
    """Quadro (áreas) + IA (posições). Uma posição fora da área de construção é recusada."""
    inside = fp.buffer(0.3)
    good = [p for p in placed if inside.contains(Point(p.x, p.y))]
    outside = [p for p in placed if not inside.contains(Point(p.x, p.y))]
    if outside:
        notes.append("Fora da área de construção lida (tratadas como espaço exterior, não aquecido): "
                     + ", ".join(p.name for p in outside) + ".")
        for r in known:                                  # 2 fontes: quadro diz divisão, geometria diz exterior → exterior
            if any(_norm(p.name) == _norm(r.name) for p in outside) and not any(_norm(g.name) == _norm(r.name) for g in good):
                r.type = "exterior"
    if not known:
        return [p for p in good if p.area > 0 or True]
    used = set()
    for r in known:
        best, bd = None, 1e9
        for i, p in enumerate(good):
            if i in used:
                continue
            same = _norm(p.name) == _norm(r.name)
            close_area = p.area and abs(p.area - r.area) <= max(0.3, 0.05 * r.area)
            d = (0 if same else 1) + (0 if close_area else 1)
            if d < bd and (same or close_area or _norm(r.name) in _norm(p.name) or _norm(p.name) in _norm(r.name)):
                best, bd = i, d
        if best is not None:
            used.add(best)
            r.x, r.y = good[best].x, good[best].y
            r.source = "quadro+ia"
    return known


def zones(rooms: list[Room], fp) -> None:
    pts = [r for r in rooms if r.placed and r.type != "exterior"]
    if len(pts) < 2:
        for r in pts:
            r.zone = fp
        return
    vd = voronoi_diagram(MultiPoint([(r.x, r.y) for r in pts]), envelope=fp.envelope.buffer(5))
    for r in pts:
        cell = next((c for c in vd.geoms if c.contains(Point(r.x, r.y))), None)
        if cell is not None:
            z = cell.intersection(fp)
            if not z.is_empty:
                r.zone = max(getattr(z, "geoms", [z]), key=lambda g: g.area) if z.geom_type != "Polygon" else z


# ----------------------------------------------------------------------------- 2b. mapa de vãos (texto)
_DIM = re.compile(r"DIMENS[ÃA]O(?:ES)?\s*:?\s*\n?\s*(\d{2,4})\s*[x×]\s*(\d{2,4})\s*(cm|mm)?", re.I)


def windows_from_text(texts: list[str]) -> list[Window]:
    """Fichas do mapa de vãos exteriores («DESIGNAÇÃO Ve 3 … DIMENSÃO 290x184 cm … QUANTIDADES 01 … LOCALIZAÇÃO 3. Sala»).
    A dimensão que se repete em quase todas as fichas (≈ pé-direito) é a altura."""
    rows = []
    for t in texts:
        if not re.search(r"(?i)v[ãa]os?\s+exteriores|mapa\s+de\s+v[ãa]os|caixilharia", t or ""):
            continue
        d = _DIM.search(t)
        if not d:
            continue
        k = 0.001 if (d.group(3) or "").lower() == "mm" else 0.01
        a, b_ = float(d.group(1)) * k, float(d.group(2)) * k
        q = re.search(r"(?i)QUANTIDADES?\s*:?\s*\n?\s*(\d{1,3})", t)
        loc = re.search(r"(?i)LOCALIZA[ÇC][ÃA]O\s*:?\s*\n?\s*(.+)", t)
        des = re.search(r"(?i)DESIGNA[ÇC][ÃA]O\s*:?\s*\n?\s*(.+)", t)
        rows.append([des.group(1).strip()[:20] if des else f"V{len(rows) + 1}", a, b_, int(q.group(1)) if q else 1,
                     loc.group(1).strip()[:60] if loc else ""])
    if not rows:
        return []
    from collections import Counter
    c = Counter(round(v, 2) for r in rows for v in (r[1], r[2]))
    common = c.most_common(1)[0][0]
    out, seen = [], set()
    for name, a, b_, q, loc in rows:
        if name in seen:
            continue
        seen.add(name)
        h, w = (a, b_) if round(a, 2) == common else (b_, a) if round(b_, 2) == common else (min(a, b_), max(a, b_))
        out.append(Window(name=name, w=w, h=h, qty=q, room=loc))
    return out


# ----------------------------------------------------------------------------- 3. vãos exteriores (geometria)
ORIENTS = ["E", "NE", "N", "NO", "O", "SO", "S", "SE"]


def orient_of(edge: LineString, fp, north_deg: float = 90.0) -> str:
    """Orientação da normal exterior de um troço do contorno. north_deg: ângulo do Norte no desenho (90 = para cima)."""
    (x0, y0), (x1, y1) = edge.coords[0], edge.coords[-1]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = (y1 - y0), -(x1 - x0)
    L = math.hypot(nx, ny) or 1
    nx, ny = nx / L, ny / L
    if fp.contains(Point(mx + 0.3 * nx, my + 0.3 * ny)):
        nx, ny = -nx, -ny
    ang = (math.degrees(math.atan2(ny, nx)) - (north_deg - 90.0)) % 360
    return ORIENTS[int(((ang + 22.5) % 360) // 45)]


def openings(b: Building, min_w: float = 0.6, max_w: float = 10.0) -> list[Opening]:
    """Troços da envolvente (contorno exterior e pátios) sem parede lida = vãos (envidraçados / portas)."""
    fp = b.footprint
    ext_walls = unary_union([w.line.buffer(w.t / 2 + 0.25, cap_style=2) for w in b.walls]) if b.walls else Polygon()
    north = float(b.hypotheses.get("north_deg") or 90.0)
    out = []
    for ring in [fp.exterior, *fp.interiors]:
        coords = list(ring.coords)
        for a, c in zip(coords, coords[1:]):
            edge = LineString([a, c])
            if edge.length < min_w:
                continue
            free = edge.difference(ext_walls)
            for g in getattr(free, "geoms", [free]):
                if g.is_empty or g.geom_type != "LineString" or g.length < min_w:
                    continue
                # troço livre longo demais: parede não lida (não um vão) → só até max_w, o resto é fachada cega
                w = min(g.length, max_w)
                out.append(Opening(edge=g, width=round(w, 2), orient=orient_of(g, fp, north)))
    return out


def _room_of(name: str, rooms: list[Room]) -> Room | None:
    m = re.match(r"\s*(\d{1,2})\s*[.\-)]", name or "")
    if m:
        r = next((r for r in rooms if r.number == m.group(1)), None)
        if r:
            return r
    n = _norm(re.sub(r"^\s*\d{1,2}\s*[.\-)]\s*", "", name or ""))
    return next((r for r in rooms if _norm(r.name) == n), None)


def _orient_windows(lay: Layout, b: Building) -> None:
    """Orientação de cada vão: troço livre da fachada mais perto da divisão onde está; sem posição, a orientação
    dominante dos troços livres medidos (assinalado)."""
    if not lay.windows:
        return
    for w in lay.windows:
        r = _room_of(w.room, lay.rooms)
        if r is not None and r.placed and lay.openings:
            p = Point(r.x, r.y)
            near = [o for o in lay.openings if r.zone is not None and o.edge.intersects(r.zone.buffer(0.4))] or lay.openings
            w.orient = max(near, key=lambda o: o.width / (1.0 + o.edge.distance(p))).orient
        else:
            w.orient = ""                                   # sem posição: repartido pelas orientações medidas


def glazing_by_orient(lay: Layout, b: Building, height: float) -> tuple[dict[str, float], str]:
    """Área envidraçada por orientação (só divisões aquecidas). Fonte 1: mapa de vãos; fonte 2: troços livres × altura."""
    geo: dict[str, float] = {}
    for o in lay.openings:
        geo[o.orient] = geo.get(o.orient, 0.0) + o.width * min(height, 2.4)
    if lay.windows:
        out: dict[str, float] = {}
        gt = sum(geo.values()) or 1.0
        for w in lay.windows:
            r = _room_of(w.room, lay.rooms)
            if r is not None and not r.heated:
                continue
            if w.orient:
                out[w.orient] = out.get(w.orient, 0.0) + w.area
            else:
                for k, v in (geo.items() if geo else [("S", gt)]):
                    out[k] = out.get(k, 0.0) + w.area * v / gt
        return {k: round(v, 2) for k, v in out.items()}, "mapa de vãos"
    return {k: round(v, 2) for k, v in geo.items()}, "troços de fachada sem parede × altura (hipótese)"


# ----------------------------------------------------------------------------- orquestração
def page_png(data: bytes, index: int, dpi: int = 110) -> bytes | None:
    import pymupdf
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
        return pdf[index].get_pixmap(dpi=dpi).tobytes("png")
    except Exception:  # noqa: BLE001
        return None


async def read_layout(b: Building, docs, llm=None) -> Layout:
    lay = Layout()
    texts = doc_texts(docs)
    known = schedule_from_text([t for _, _, t in texts])
    if known:
        lay.notes.append(f"Quadro de áreas lido nas peças desenhadas: {len(known)} divisões, "
                         f"{sum(r.area for r in known):.1f} m²".replace(".", ","))
    # folha com mais nomes de divisões → IA
    def score(t):
        return sum(1 for ln in t.splitlines() if room_type(ln) != "sala" or "sala" in _norm(ln))
    cand = sorted(texts, key=lambda it: -score(it[2]))
    sheet = None
    if cand:
        di, pj, _ = cand[0]
        sheet = page_png(docs[di][1], pj)
    placed = []
    if sheet is not None and llm is not None:
        placed = await ask_rooms(llm, sheet, b, known)
    rooms = _merge(known, placed, b.footprint, lay.notes) if (known or placed) else []
    if not rooms:                                         # nada escrito, sem IA: uma zona única (hipótese visível)
        a = round(b.footprint.area * 0.88, 1)
        c = b.footprint.representative_point()
        rooms = [Room(name="Zona habitável (divisões não lidas)", area=a, type="sala", x=c.x, y=c.y, source="geometria")]
        lay.notes.append("Divisões não lidas: área útil = 88 % da área de construção (hipótese) — juntar a planta com o quadro de áreas.")
    rooms = [r for r in rooms if r.area > 0 or r.placed]
    for r in rooms:
        if r.area <= 0:
            r.area = 0.0
    zones(rooms, b.footprint)
    for r in rooms:
        if r.area <= 0 and r.zone is not None:
            r.area = round(r.zone.area * 0.9, 1)
            r.source += "+zona"
    lay.rooms = rooms
    lay.openings = openings(b)
    lay.windows = windows_from_text([t for _, _, t in texts])
    _orient_windows(lay, b)
    # confrontação: área útil (quadro) vs área de construção (geometria)
    ua = sum(r.area for r in rooms if r.type != "exterior")
    if ua > 0:
        ratio = ua / b.footprint.area
        lay.checks.append({"check": "área útil (quadro) / área de construção (geometria)", "value": round(ratio, 3),
                           "ok": 0.70 <= ratio <= 1.02, "sources": ["quadro de áreas", "contorno lido"]})
    n_placed = sum(1 for r in rooms if r.placed)
    if known and n_placed < len(rooms):
        lay.notes.append(f"{len(rooms) - n_placed} divisão(ões) sem posição na planta: equipamentos dessas divisões só no quadro.")
    return lay
