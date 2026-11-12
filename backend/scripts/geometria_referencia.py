"""Gera as plantas de referência do banco de ensaio de geometria (tests/fixtures/geometria).

Cada planta é descrita por um modelo exato (paredes, aberturas, divisões) e exportada em quatro formas:
DXF (unidades mm, cotas DIMENSION nativas), PDF vetorial à escala declarada, imagem 150 dpi e « digitalização »
(rotação ligeira, ruído, desfoque). O ficheiro `<nome>.geo.json` guarda a verdade calculada a partir do modelo:
áreas das divisões ao nu das paredes, comprimentos de paredes por eixo, contagens de vãos, escala, cotas.

Determinístico (semente fixa) : correr de novo produz os mesmos ficheiros.
Uso : python scripts/geometria_referencia.py [pasta_destino]
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import ezdxf
import fitz
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

MM_PT = 72 / 25.4


@dataclass
class Abertura:
    tipo: str            # porta | janela
    parede: str          # id da parede
    centro: float        # posição ao longo do eixo (m, a partir do início)
    largura: float


@dataclass
class Parede:
    pid: str
    x1: float
    y1: float
    x2: float
    y2: float
    espessura: float
    exterior: bool = False

    @property
    def comprimento(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def corpo(self):
        return LineString([(self.x1, self.y1), (self.x2, self.y2)]).buffer(self.espessura / 2, cap_style=3, join_style=2)

    def ponto(self, s):
        t = s / self.comprimento
        return self.x1 + (self.x2 - self.x1) * t, self.y1 + (self.y2 - self.y1) * t


@dataclass
class Planta:
    nome: str
    descricao: str
    escala: int
    paredes: list[Parede]
    aberturas: list[Abertura]
    divisoes: dict[str, tuple[float, float]]          # nome → ponto interior
    cotas: list[tuple[tuple[float, float], tuple[float, float], float]] = field(default_factory=list)  # p1, p2, deslocamento

    def parede(self, pid):
        return next(p for p in self.paredes if p.pid == pid)

    def corpo_paredes(self):
        return unary_union([p.corpo() for p in self.paredes])

    def divisoes_poligonos(self):
        """Faces interiores delimitadas pelos corpos das paredes (vãos fechados): a verdade das áreas."""
        corpo = self.corpo_paredes()
        env = corpo.envelope.buffer(1)
        livres = env.difference(corpo)
        partes = list(getattr(livres, "geoms", [livres]))
        out = {}
        for nome, pt in self.divisoes.items():
            from shapely.geometry import Point
            face = next(g for g in partes if g.contains(Point(pt)))
            out[nome] = face
        return out

    def verdade(self) -> dict:
        divs = self.divisoes_poligonos()
        corpo = self.corpo_paredes()
        ext = [p for p in self.paredes if p.exterior]
        contorno = Polygon(corpo.exterior.coords) if corpo.geom_type == "Polygon" else Polygon(max(corpo.geoms, key=lambda g: g.area).exterior.coords)
        return {
            "planta": self.nome, "descricao": self.descricao, "verificado": True,
            "fonte": "modelo geométrico exato (scripts/geometria_referencia.py)",
            "escala_declarada": f"1:{self.escala}",
            "area_implantacao_m2": round(contorno.area, 3),
            "area_paredes_m2": round(corpo.area, 3),
            "divisoes": {n: {"area_m2": round(g.area, 3), "perimetro_m": round(g.length, 3)} for n, g in divs.items()},
            "area_util_total_m2": round(sum(g.area for g in divs.values()), 3),
            "paredes": {
                "exteriores_eixo_m": round(sum(p.comprimento for p in ext), 3),
                "interiores_eixo_m": round(sum(p.comprimento for p in self.paredes if not p.exterior), 3),
                "espessuras_m": sorted({p.espessura for p in self.paredes}),
            },
            "contagens": {"porta": sum(a.tipo == "porta" for a in self.aberturas),
                          "janela": sum(a.tipo == "janela" for a in self.aberturas)},
            "cotas_m": sorted(round(math.dist(a, b), 3) for a, b, _ in self.cotas),
        }


# ---------------------------------------------------------------- modelos

def casa_a() -> Planta:
    """Moradia T2 retangular 12,00 × 9,00 m, paredes exteriores 0,30, divisórias 0,10/0,15."""
    e, i = .30, .10
    W, H = 12.0, 9.0
    c = e / 2
    paredes = [
        Parede("E-S", c, c, W - c, c, e, True), Parede("E-E", W - c, c, W - c, H - c, e, True),
        Parede("E-N", W - c, H - c, c, H - c, e, True), Parede("E-O", c, H - c, c, c, e, True),
        Parede("I-V", 7.0, e, 7.0, H - e, .15),
        Parede("I-H1", e, 4.5, 7.0 - .075, 4.5, i),
        Parede("I-H2", 7.0 + .075, 3.0, W - e, 3.0, i),
        Parede("I-H3", 7.0 + .075, 6.0, W - e, 6.0, i),
    ]
    aberturas = [
        Abertura("porta", "E-S", 2.0, .90), Abertura("porta", "I-H1", 3.0, .80), Abertura("porta", "I-V", 1.5, .80),
        Abertura("porta", "I-V", 4.5, .70), Abertura("porta", "I-V", 7.3, .80),
        Abertura("janela", "E-S", 5.0, 1.50), Abertura("janela", "E-S", 9.5, 1.20), Abertura("janela", "E-E", 7.5, 1.20),
        Abertura("janela", "E-N", 3.0, 2.00), Abertura("janela", "E-N", 9.5, 1.20), Abertura("janela", "E-O", 4.0, 1.00),
    ]
    divisoes = {"Sala": (3.5, 6.5), "Cozinha": (3.5, 2.0), "Quarto 1": (9.5, 1.5), "Instalação sanitária": (9.5, 4.5), "Quarto 2": (9.5, 7.5)}
    cotas = [((0, 0), (W, 0), -1.2), ((0, 0), (0, H), -1.2), ((0, 0), (7.0, 0), -.7), ((7.0, 0), (W, 0), -.7),
             ((W, 0), (W, 3.0), 1.0), ((W, 3.0), (W, 6.0), 1.0), ((W, 6.0), (W, H), 1.0)]
    return Planta("casa_a", "Moradia T2 retangular 12×9 m", 50, paredes, aberturas, divisoes, cotas)


def casa_b() -> Planta:
    """Moradia em L (14,00 × 10,00 com recorte 5,00 × 4,00), paredes 0,35 / 0,11 / 0,15, sete divisões."""
    e = .35
    c = e / 2
    nomes = ["E-S", "E-E", "E-RN", "E-RE", "E-N", "E-O"]
    # eixos das paredes exteriores a meio da espessura (contorno exterior: (0,0)-(14,0)-(14,6)-(9,6)-(9,10)-(0,10))
    eixo = [(c, c), (14 - c, c), (14 - c, 6 - c), (9 - c, 6 - c), (9 - c, 10 - c), (c, 10 - c)]
    ext = [Parede(nomes[k], *a, *b, e, True) for k, (a, b) in enumerate(zip(eixo, eixo[1:] + eixo[:1]))]
    i, m = .11, .15
    inter = [
        Parede("I-V1", 5.0, e, 5.0, 10 - e, m),
        Parede("I-V2", 9.0 + .075, e, 9.0 + .075, 6 - e, m),
        Parede("I-H1", e, 5.5, 5.0 - .075, 5.5, i),
        Parede("I-H2", 5.0 + .075, 3.2, 9.0, 3.2, i),
        Parede("I-H3", 5.0 + .075, 6.6, 9 - e, 6.6, i),
        Parede("I-H4", 9.0 + .15, 3.0, 14 - e, 3.0, i),
    ]
    aberturas = [
        Abertura("porta", "E-S", 6.5, .90), Abertura("porta", "I-V1", 2.5, .80), Abertura("porta", "I-V1", 7.5, .80),
        Abertura("porta", "I-H2", 2.0, .80), Abertura("porta", "I-H3", 1.8, .70), Abertura("porta", "I-V2", 1.5, .80),
        Abertura("porta", "I-H4", 2.0, .80),
        Abertura("janela", "E-S", 2.5, 1.60), Abertura("janela", "E-S", 11.5, 1.40), Abertura("janela", "E-E", 4.5, 1.20),
        Abertura("janela", "E-RN", 2.5, 1.20), Abertura("janela", "E-N", 4.0, 2.40), Abertura("janela", "E-O", 2.0, 1.00),
        Abertura("janela", "E-O", 7.5, 1.20), Abertura("janela", "E-RE", 2.0, .60),
    ]
    divisoes = {"Sala comum": (2.5, 7.5), "Cozinha": (2.5, 2.5), "Hall": (7.0, 1.5), "Instalação sanitária": (7.0, 5.0),
                "Suite": (7.0, 8.5), "Quarto 1": (11.5, 1.5), "Quarto 2": (11.5, 4.5)}
    cotas = [((0, 0), (14, 0), -1.4), ((0, 0), (0, 10), -1.4), ((0, 0), (5, 0), -.8), ((5, 0), (9, 0), -.8), ((9, 0), (14, 0), -.8),
             ((14, 0), (14, 3), 1.0), ((14, 3), (14, 6), 1.0), ((0, 10), (9, 10), 1.0)]
    return Planta("casa_b", "Moradia em L 14×10 m, sete divisões", 50, ext + inter, aberturas, divisoes, cotas)


def casa_c() -> Planta:
    """Apartamento T1 compacto 8,40 × 6,20 m, à escala 1:100 (texto e traços pequenos)."""
    e, i = .25, .10
    W, H = 8.4, 6.2
    c = e / 2
    paredes = [
        Parede("E-S", c, c, W - c, c, e, True), Parede("E-E", W - c, c, W - c, H - c, e, True),
        Parede("E-N", W - c, H - c, c, H - c, e, True), Parede("E-O", c, H - c, c, c, e, True),
        Parede("I-V", 5.2, e, 5.2, H - e, i),
        Parede("I-H", 5.2 + .05, 2.4, W - e, 2.4, i),
    ]
    aberturas = [Abertura("porta", "E-O", 1.2, .90), Abertura("porta", "I-V", 1.2, .80), Abertura("porta", "I-H", 1.4, .70),
                 Abertura("janela", "E-S", 2.6, 1.80), Abertura("janela", "E-N", 6.8, 1.20), Abertura("janela", "E-E", 4.3, 1.00)]
    divisoes = {"Sala e cozinha": (2.5, 3.0), "Instalação sanitária": (6.8, 1.2), "Quarto": (6.8, 4.3)}
    cotas = [((0, 0), (W, 0), -1.2), ((0, 0), (0, H), -1.2), ((W, 0), (W, 2.4), .9), ((W, 2.4), (W, H), .9)]
    return Planta("casa_c", "Apartamento T1 8,40×6,20 m à escala 1:100", 100, paredes, aberturas, divisoes, cotas)


# ---------------------------------------------------------------- geometria de desenho

def _corpos_com_vaos(pl: Planta):
    """Corpo das paredes com os vãos recortados (portas: vazio; janelas: vazio, desenhadas à parte)."""
    corpo = pl.corpo_paredes()
    for a in pl.aberturas:
        p = pl.parede(a.parede)
        s0, s1 = a.centro - a.largura / 2, a.centro + a.largura / 2
        x0, y0 = p.ponto(s0)
        x1, y1 = p.ponto(s1)
        corte = LineString([(x0, y0), (x1, y1)]).buffer(p.espessura / 2 + .002, cap_style=2)
        corpo = corpo.difference(corte)
    return corpo


def _linhas_poligono(g):
    for poly in getattr(g, "geoms", [g]):
        for ring in [poly.exterior, *poly.interiors]:
            cs = list(ring.coords)
            for a, b in zip(cs, cs[1:]):
                if math.dist(a, b) > 1e-6:
                    yield a, b


def _simbolos_aberturas(pl: Planta):
    """Linhas finas dos vãos : janelas (3 linhas paralelas) e portas (folha + arco em polilinha)."""
    linhas, arcos = [], []
    for a in pl.aberturas:
        p = pl.parede(a.parede)
        ux, uy = (p.x2 - p.x1) / p.comprimento, (p.y2 - p.y1) / p.comprimento
        nx, ny = -uy, ux
        s0, s1 = a.centro - a.largura / 2, a.centro + a.largura / 2
        x0, y0 = p.ponto(s0)
        x1, y1 = p.ponto(s1)
        h = p.espessura / 2
        if a.tipo == "janela":
            for k in (-h, 0, h):
                linhas.append(((x0 + nx * k, y0 + ny * k), (x1 + nx * k, y1 + ny * k)))
            for xx, yy in ((x0, y0), (x1, y1)):
                linhas.append(((xx - nx * h, yy - ny * h), (xx + nx * h, yy + ny * h)))
        else:
            hx, hy = x0 + nx * h, y0 + ny * h
            linhas.append(((hx, hy), (hx + nx * a.largura, hy + ny * a.largura)))
            pts = [(hx + a.largura * (math.cos(t) * ux + math.sin(t) * nx), hy + a.largura * (math.cos(t) * uy + math.sin(t) * ny))
                   for t in np.linspace(0, math.pi / 2, 13)]
            arcos.append(pts)
    return linhas, arcos


# ---------------------------------------------------------------- exportações

def exportar_dxf(pl: Planta, destino: Path):
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    for nome, cor in (("A-WALL", 7), ("A-DOOR", 3), ("A-GLAZ", 5), ("A-ANNO-DIMS", 1), ("A-ANNO-TEXT", 2)):
        doc.layers.add(nome, color=cor)
    msp = doc.modelspace()
    mm = lambda p: (p[0] * 1000, p[1] * 1000)
    for a, b in _linhas_poligono(_corpos_com_vaos(pl)):
        msp.add_line(mm(a), mm(b), dxfattribs={"layer": "A-WALL"})
    linhas, arcos = _simbolos_aberturas(pl)
    for a, b in linhas:
        msp.add_line(mm(a), mm(b), dxfattribs={"layer": "A-GLAZ"})
    for pts in arcos:
        msp.add_lwpolyline([mm(p) for p in pts], dxfattribs={"layer": "A-DOOR"})
    for (p1, p2, d) in pl.cotas:
        horiz = abs(p2[1] - p1[1]) < 1e-9
        base = (p1[0] * 1000, (p1[1] + d) * 1000) if horiz else ((p1[0] + d) * 1000, p1[1] * 1000)
        dim = msp.add_linear_dim(base=base, p1=mm(p1), p2=mm(p2), angle=0 if horiz else 90,
                                 dimstyle="EZDXF", dxfattribs={"layer": "A-ANNO-DIMS"})
        dim.render()
    for nome, pt in pl.divisoes.items():
        area = pl.divisoes_poligonos()[nome].area
        msp.add_text(nome, height=180, dxfattribs={"layer": "A-ANNO-TEXT", "insert": (pt[0] * 1000 - 600, pt[1] * 1000 + 150)})
        msp.add_text(f"{area:.2f} m²", height=150, dxfattribs={"layer": "A-ANNO-TEXT", "insert": (pt[0] * 1000 - 600, pt[1] * 1000 - 150)})
    doc.saveas(destino)


def exportar_pdf(pl: Planta, destino: Path):
    """PDF vetorial A3 paisagem à escala declarada, com cotas desenhadas (traço, marcas, texto)."""
    doc = fitz.open()
    pg = doc.new_page(width=420 * MM_PT, height=297 * MM_PT)
    k = 1000 / pl.escala * MM_PT          # pt por metro
    ox, oy = 40 * MM_PT, 297 * MM_PT - 45 * MM_PT
    P = lambda p: fitz.Point(ox + p[0] * k, oy - p[1] * k)
    sh = pg.new_shape()
    for a, b in _linhas_poligono(_corpos_com_vaos(pl)):
        sh.draw_line(P(a), P(b))
    sh.finish(color=(0, 0, 0), width=.7)
    linhas, arcos = _simbolos_aberturas(pl)
    for a, b in linhas:
        sh.draw_line(P(a), P(b))
    for pts in arcos:
        sh.draw_polyline([P(p) for p in pts])
    sh.finish(color=(0, 0, 0), width=.18)
    for (p1, p2, d) in pl.cotas:
        horiz = abs(p2[1] - p1[1]) < 1e-9
        q1 = (p1[0], p1[1] + d) if horiz else (p1[0] + d, p1[1])
        q2 = (p2[0], p2[1] + d) if horiz else (p2[0] + d, p2[1])
        sh.draw_line(P(q1), P(q2))
        for a, b in ((p1, q1), (p2, q2)):
            sh.draw_line(P(a), P(b))
        for q in (q1, q2):
            t = .12
            sh.draw_line(P((q[0] - t, q[1] - t)), P((q[0] + t, q[1] + t)))
        val = f"{math.dist(p1, p2):.2f}"
        mid = P(((q1[0] + q2[0]) / 2, (q1[1] + q2[1]) / 2))
        fs = 7 if pl.escala <= 50 else 5
        if horiz:
            pg.insert_text(fitz.Point(mid.x - fs * 1.2, mid.y - 2), val, fontsize=fs)
        else:
            pg.insert_text(fitz.Point(mid.x - 2, mid.y + fs * 1.2), val, fontsize=fs, rotate=90)
    sh.finish(color=(0, 0, 0), width=.12)
    sh.commit()
    divs = pl.divisoes_poligonos()
    fs = 8 if pl.escala <= 50 else 6
    for nome, pt in pl.divisoes.items():
        q = P(pt)
        pg.insert_text(fitz.Point(q.x - 20, q.y - 2), nome, fontsize=fs)
        pg.insert_text(fitz.Point(q.x - 20, q.y + fs + 1), f"{divs[nome].area:.2f} m²", fontsize=fs - 1)
    pg.insert_text(fitz.Point(300 * MM_PT, 280 * MM_PT), f"PLANTA DO PISO 0 — ESCALA 1:{pl.escala}", fontsize=10)
    pg.insert_text(fitz.Point(300 * MM_PT, 287 * MM_PT), f"{pl.descricao}", fontsize=7)
    doc.save(destino, deflate=True)


def exportar_imagens(pdf: Path, destino_png: Path, destino_scan: Path, seed: int, dpi_scan: int = 150):
    """Imagem limpa 150 dpi (PNG) e « digitalização » (JPEG 75 %): rotação 0,6°, desfoque, contraste reduzido, ruído."""
    doc = fitz.open(pdf)
    pix = doc[0].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w).copy()
    cv2.imwrite(str(destino_png), img)
    pix = doc[0].get_pixmap(dpi=dpi_scan, colorspace=fitz.csGRAY)
    base = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w).copy()
    rng = np.random.default_rng(seed)
    h, w = base.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), .6, 1.0)
    scan = cv2.warpAffine(base, M, (w, h), borderValue=255)
    scan = cv2.GaussianBlur(scan, (3, 3), .8)
    ruido = rng.normal(0, 9, scan.shape)
    scan = np.clip(scan.astype(float) * .93 + 10 + ruido, 0, 255).astype(np.uint8)
    cv2.imwrite(str(destino_scan), scan, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return {"dpi": 150, "dpi_scan": dpi_scan, "rotacao_scan_graus": .6}


def gerar(destino: Path):
    destino.mkdir(parents=True, exist_ok=True)
    for velho in destino.glob("*_scan.png"):
        velho.unlink()
    indice = []
    for n, fabrica in enumerate((casa_a, casa_b, casa_c)):
        pl = fabrica()
        v = pl.verdade()
        exportar_dxf(pl, destino / f"{pl.nome}.dxf")
        exportar_pdf(pl, destino / f"{pl.nome}.pdf")
        v["imagem"] = exportar_imagens(destino / f"{pl.nome}.pdf", destino / f"{pl.nome}.png", destino / f"{pl.nome}_scan.jpg", seed=n)
        if pl.escala >= 100:   # a 1:100 uma digitalização a 150 dpi é o caso-limite; a 300 dpi é o caso real
            v["imagem"]["scan_300"] = exportar_imagens(destino / f"{pl.nome}.pdf", destino / "_lixo.png", destino / f"{pl.nome}_scan300.jpg", seed=10 + n, dpi_scan=300)
            (destino / "_lixo.png").unlink()
        v["pdf"] = {"formato": "A3 paisagem", "origem_mm": [40, 45]}
        (destino / f"{pl.nome}.geo.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        indice.append(pl.nome)
    return indice


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "tests/fixtures/geometria"
    print(gerar(out))
