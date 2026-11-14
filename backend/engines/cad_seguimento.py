"""Folha de seguimento das quantidades medidas num DWG/DXF (construção tradicional e arranjos exteriores).

Mesmo método do dossier CLT: tudo o que é calculado aparece DESENHADO e NUMERADO sobre a planta, com uma tabela que usa
os mesmos números, para a empresa poder controlar cada quantidade.

1. Cada artigo da medição (uma camada do desenho) recebe um número e uma cor; os seus elementos (tramas, polilinhas,
   linhas, blocos) são redesenhados a partir da geometria do próprio ficheiro, nunca de um modelo aproximado.
2. Prova «desenhado = medido»: a área (ou o número de blocos) do que está desenhado é comparada com a quantidade da
   medição; uma diferença acima de 2 % fica escrita como ERRO.
3. Cruzamento com o que está ESCRITO no desenho: cada área escrita («1481,55 m²») é comparada com o elemento medido que
   contém esse texto. O que não tem texto para conferir fica dito, não fica assumido.
4. A estrutura calculada (malha de betão) é desenhada sobre o contorno medido, com os eixos numerados.

Nada é inventado: sem geometria não há desenho, e isso fica escrito na tabela.
"""
from __future__ import annotations

import io
import math

from engines.cad_geometry import walk_entities
from engines.cad_quantidades_camadas import _AREA_ESCRITA, _pts

TOLERANCIA_PCT = 2.0
CORES = [(0.84, 0.15, 0.16), (0.12, 0.47, 0.71), (0.17, 0.63, 0.17), (1.0, 0.5, 0.05), (0.58, 0.4, 0.74), (0.55, 0.34, 0.29),
         (0.89, 0.47, 0.76), (0.09, 0.75, 0.81), (0.74, 0.74, 0.13), (0.2, 0.2, 0.6), (0.6, 0.2, 0.2), (0.1, 0.5, 0.4)]
_FUNDO_MAX = 25000

_TXT = {
    "titulo": ("Seguimento das quantidades medidas", "Suivi des quantités mesurées"),
    "sub": ("Cada número da planta corresponde a uma linha da tabela. Geometria redesenhada a partir do próprio desenho CAD.",
            "Chaque numéro du plan correspond à une ligne du tableau. Géométrie redessinée à partir du plan CAO lui-même."),
    "tab": ("Artigos medidos", "Articles mesurés"),
    "n": ("N.º", "N°"), "art": ("Artigo", "Article"), "cam": ("Camada", "Calque"), "qtd": ("Medição", "Métré"),
    "des": ("Desenhado", "Dessiné"), "res": ("Controlo", "Contrôle"), "ori": ("Origem", "Origine"),
    "ok": ("confere", "conforme"), "erro": ("ERRO: não confere", "ERREUR : non conforme"),
    "semgeo": ("sem geometria para desenhar", "pas de géométrie à dessiner"),
    "compr": ("comprimento ao eixo (pares de linhas paralelas contam uma vez)", "longueur à l'axe (paires de lignes parallèles comptées une fois)"),
    "escrito": ("Cruzamento com o que está escrito no desenho", "Recoupement avec ce qui est écrit sur le plan"),
    "e_txt": ("Texto no desenho", "Texte sur le plan"), "e_esc": ("Escrito", "Écrit"), "e_med": ("Medido", "Mesuré"),
    "e_dif": ("Diferença", "Écart"), "e_onde": ("Elemento", "Élément"),
    "e_fora": ("texto fora de qualquer elemento medido: não conferido", "texte hors de tout élément mesuré : non recoupé"),
    "e_nada": ("O desenho não tem áreas escritas: não há texto para conferir as medições. As quantidades vêm só da geometria.",
               "Le plan ne comporte pas de surfaces écrites : aucun texte pour recouper les métrés. Les quantités viennent de la seule géométrie."),
    "excl": ("Camadas não orçamentadas (a tracejado cinzento quando estão junto da obra medida)", "Calques non chiffrés (en tirets gris lorsqu'ils jouxtent les ouvrages mesurés)"),
    "estr": ("Estrutura calculada sobre o contorno medido", "Structure calculée sur le contour mesuré"),
    "estr_txt": ("Contorno do edifício medido no desenho (camada «{c}», {a} m²). Malha de pilares calculada: {nx} eixos × {ny} eixos, "
                 "{p} pilares. Pré-dimensionamento a validar pelo projetista.",
                 "Contour du bâtiment mesuré sur le plan (calque « {c} », {a} m²). Trame de poteaux calculée : {nx} axes × {ny} axes, "
                 "{p} poteaux. Prédimensionnement à valider par le bureau d'études."),
    "estr_metal": ("Estrutura metálica: {p} pórticos afastados {s} m, {v} vão(s) de {vao} m, sobre o retângulo {c} × {l} m do contorno medido. "
                   "Os pórticos não são desenhados: a orientação fica a validar pelo projetista.",
                   "Charpente métallique : {p} portiques espacés de {s} m, {v} travée(s) de {vao} m, sur le rectangle {c} × {l} m du contour mesuré. "
                   "Les portiques ne sont pas dessinés : l'orientation reste à valider par le bureau d'études."),
    "nota": ("Áreas: tramas (HATCH) da camada, ilhas descontadas; sem tramas, polilinhas fechadas. Tolerância do controlo: 2 %.",
             "Surfaces : hachures (HATCH) du calque, îlots déduits ; sans hachures, polylignes fermées. Tolérance du contrôle : 2 %."),
}


def _t(k: str, lang: str) -> str:
    return _TXT[k][1 if lang == "fr" else 0]


def _poligono_trama(e):
    """Polígono da trama com as ilhas retiradas (regra par-ímpar), em unidades do desenho."""
    from ezdxf.path import from_hatch
    from shapely.geometry import Polygon
    geo = None
    for path in from_hatch(e):
        pts = [(float(v.x), float(v.y)) for v in path.flattening(distance=0.001, segments=16)]
        if len(pts) < 3:
            continue
        p = Polygon(pts).buffer(0)
        if p.is_empty:
            continue
        geo = p if geo is None else geo.symmetric_difference(p)
    return geo


def formas(doc, medicao: dict, entidades=None) -> dict:
    """Geometria (em metros) de cada artigo da medição, mais o fundo e os textos de área.

    → {"artigos": [{n, camada, designacao, unit, qty, medida, poligonos, linhas, pontos, desenhado, confere}],
       "fundo": [[(x, y), …]], "excluidas": [[(x, y), …]], "textos": [{texto, valor, x, y}]}"""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    u = float(medicao.get("fator_m") or 1.0)
    linhas = [l for l in medicao.get("linhas") or [] if l.get("camada")]
    por = {l["camada"]: {"n": i + 1, "camada": l["camada"], "designacao": l.get("designation") or "", "unit": l.get("unit"),
                         "qty": float(l.get("qty") or 0), "tramas": [], "fechadas": [], "linhas": [], "pontos": []}
           for i, l in enumerate(linhas)}
    excl = {x["camada"] for x in medicao.get("excluidas") or [] if x.get("camada")}
    fundo, excluidas = [], []
    fonte = entidades if entidades is not None else walk_entities(doc, explode_dimensions=False, diagnostics=[])
    m = lambda pts: [(x * u, y * u) for x, y in pts]  # noqa: E731
    for e in fonte:
        if getattr(e, "_cp_role", None) == "dimension":
            continue
        layer, t = e.dxf.get("layer", "0"), e.dxftype()
        a = por.get(layer)
        if a is None:
            if t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC"):
                pts = _pts(e)
                if len(pts) >= 2:
                    if t in ("LWPOLYLINE", "POLYLINE") and getattr(e, "closed", False):
                        pts = pts + pts[:1]
                    if layer in excl:
                        excluidas.append(m(pts))
                    elif len(fundo) < _FUNDO_MAX:
                        fundo.append(m(pts))
            continue
        try:
            if t == "HATCH":
                g = _poligono_trama(e)
                if g is not None and not g.is_empty:
                    a["tramas"].append(g)
            elif t in ("LWPOLYLINE", "POLYLINE", "LINE", "ARC"):
                pts = _pts(e)
                if len(pts) < 2:
                    continue
                if t in ("LWPOLYLINE", "POLYLINE") and getattr(e, "closed", False) and len(pts) >= 3:
                    p = Polygon(pts).buffer(0)
                    if not p.is_empty:
                        a["fechadas"].append(p)
                    pts = pts + pts[:1]
                a["linhas"].append(m(pts))
        except Exception:  # noqa: BLE001, uma entidade ilegível não impede o seguimento das outras
            continue
    for e in doc.modelspace().query("INSERT"):
        a = por.get(e.dxf.get("layer", "0"))
        if a is not None:
            a["pontos"].append((float(e.dxf.insert.x) * u, float(e.dxf.insert.y) * u))
    from shapely.affinity import scale as _scale
    artigos = []
    for a in por.values():
        medida = {"m2": "area", "m": "comprimento"}.get(a["unit"], "contagem")
        pols = []
        if medida == "area":
            # a medição soma as tramas (ou, sem tramas, as polilinhas fechadas): desenha-se exatamente o mesmo conjunto
            for g in a["tramas"] or a["fechadas"]:
                g = _scale(g, xfact=u, yfact=u, origin=(0, 0))
                pols += list(g.geoms) if hasattr(g, "geoms") else [g]
            desenhado = sum(p.area for p in pols)
        elif medida == "contagem":
            desenhado = float(len(a["pontos"]))
        else:
            desenhado = None
        confere = None if desenhado is None else (abs(desenhado - a["qty"]) <= max(TOLERANCIA_PCT / 100 * a["qty"], 0.011))
        artigos.append({"n": a["n"], "camada": a["camada"], "designacao": a["designacao"], "unit": a["unit"], "qty": a["qty"],
                        "medida": medida, "poligonos": pols, "linhas": a["linhas"] if medida != "contagem" else [],
                        "pontos": a["pontos"] if medida == "contagem" else [],
                        "desenhado": None if desenhado is None else round(desenhado, 2), "confere": confere,
                        "uniao": unary_union(pols) if pols else None})
    textos = []
    for e in doc.modelspace().query("TEXT MTEXT"):
        try:
            s = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
            ins = e.dxf.insert
        except Exception:  # noqa: BLE001
            continue
        for mt in _AREA_ESCRITA.finditer(s or ""):
            textos.append({"texto": " ".join((s or "").split())[:80], "valor": float(mt.group(1).replace(",", ".")),
                           "x": float(ins.x) * u, "y": float(ins.y) * u})
    return {"artigos": artigos, "fundo": fundo, "excluidas": excluidas, "textos": textos}


def cruzar_escrito(f: dict) -> list[dict]:
    """Cada área escrita no desenho contra o polígono medido que contém o texto (o mais pequeno, se houver vários)."""
    from shapely.geometry import Point
    rows = []
    for tx in f["textos"]:
        pt, melhor = Point(tx["x"], tx["y"]), None
        for a in f["artigos"]:
            for p in a["poligonos"]:
                if p.contains(pt) and (melhor is None or p.area < melhor[1].area):
                    melhor = (a, p)
        if melhor is None:
            # o texto pode estar ao lado: aceita-se só uma área medida única que coincide a 2 %
            iguais = [(a, p) for a in f["artigos"] for p in a["poligonos"] if abs(p.area - tx["valor"]) <= TOLERANCIA_PCT / 100 * tx["valor"]]
            total = [a for a in f["artigos"] if a["medida"] == "area" and abs(a["qty"] - tx["valor"]) <= TOLERANCIA_PCT / 100 * tx["valor"]]
            if len(iguais) == 1:
                melhor = iguais[0]
            elif len(total) == 1:
                a = total[0]
                rows.append({"texto": tx["texto"], "escrito": tx["valor"], "medido": a["qty"], "n": a["n"], "camada": a["camada"],
                             "erro_pct": round(abs(a["qty"] - tx["valor"]) / tx["valor"] * 100, 2) if tx["valor"] else None, "ok": True})
                continue
        if melhor is None:
            rows.append({"texto": tx["texto"], "escrito": tx["valor"], "medido": None, "n": None, "camada": None, "erro_pct": None, "ok": None})
            continue
        a, p = melhor
        err = abs(p.area - tx["valor"]) / tx["valor"] * 100 if tx["valor"] else None
        rows.append({"texto": tx["texto"], "escrito": tx["valor"], "medido": round(p.area, 2), "n": a["n"], "camada": a["camada"],
                     "erro_pct": None if err is None else round(err, 2), "ok": err is not None and err <= TOLERANCIA_PCT})
    return rows


def _num(x, lang, d=2):
    s = f"{x:,.{d}f}".replace(",", " ")
    return s.replace(".", ",")


def _ponto_etiqueta(a):
    if a["poligonos"]:
        p = max(a["poligonos"], key=lambda g: g.area).representative_point()
        return p.x, p.y
    if a["linhas"]:
        from shapely.geometry import LineString
        ln = max((LineString(l) for l in a["linhas"] if len(l) >= 2), key=lambda g: g.length, default=None)
        if ln is not None:
            p = ln.interpolate(0.5, normalized=True)
            return p.x, p.y
    if a["pontos"]:
        return a["pontos"][0]
    return None


def _malha(estrutura: dict | None):
    g = (estrutura or {}).get("geometria") or (estrutura or {}).get("malha") or {}
    if isinstance(g, dict) and isinstance(g.get("x"), list) and isinstance(g.get("y"), list):
        return g["x"], g["y"]
    return None


def pdf(doc, medicao: dict, *, titulo: str = "", lang: str = "pt", estrutura: dict | None = None, brand: dict | None = None,
        entidades=None) -> dict:
    """→ {"pdf": bytes, "artigos": [...], "escrito": [...], "erros": n, "avisos": [...]} (sem as geometrias)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from engines.takeoff_core import desenhos
    fr, fb = desenhos.register_fonts()
    f = formas(doc, medicao, entidades)
    escrito = cruzar_escrito(f)
    ed = medicao.get("edificio") or {}
    contorno = [tuple(p) for p in ed.get("pontos") or []]
    malha = _malha(estrutura)
    cor = colors.Color(*((brand or {}).get("cor") or (0.06, 0.25, 0.45)))

    xs, ys = [], []
    for a in f["artigos"]:
        for p in a["poligonos"]:
            x0, y0, x1, y1 = p.bounds
            xs += [x0, x1]
            ys += [y0, y1]
        for l in a["linhas"]:
            xs += [q[0] for q in l]
            ys += [q[1] for q in l]
        for q in a["pontos"]:
            xs.append(q[0])
            ys.append(q[1])
    for q in contorno:
        xs.append(q[0])
        ys.append(q[1])
    tem_geo = bool(xs)
    if tem_geo:
        bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
        mx, my = max((bx1 - bx0) * 0.10, 1.0), max((by1 - by0) * 0.10, 1.0)
        bx0, bx1, by0, by1 = bx0 - mx, bx1 + mx, by0 - my, by1 + my

    class Planta(Flowable):
        def __init__(self, w, h):
            super().__init__()
            self.width, self.height = w, h

        def draw(self):
            c = self.canv
            s = min(self.width / (bx1 - bx0), self.height / (by1 - by0))
            ox = (self.width - (bx1 - bx0) * s) / 2
            oy = (self.height - (by1 - by0) * s) / 2
            X = lambda x: ox + (x - bx0) * s  # noqa: E731
            Y = lambda y: oy + (y - by0) * s  # noqa: E731

            def dentro(l):
                return any(bx0 <= x <= bx1 and by0 <= y <= by1 for x, y in l)

            def traco(l):
                p = c.beginPath()
                p.moveTo(X(l[0][0]), Y(l[0][1]))
                for x, y in l[1:]:
                    p.lineTo(X(x), Y(y))
                c.drawPath(p, stroke=1, fill=0)

            c.setLineWidth(0.25)
            c.setStrokeColor(colors.Color(.82, .82, .82))
            for l in f["fundo"]:
                if dentro(l):
                    traco(l)
            c.setStrokeColor(colors.Color(.55, .55, .55))
            c.setDash(2, 2)
            for l in f["excluidas"]:
                if dentro(l):
                    traco(l)
            c.setDash()
            for a in f["artigos"]:
                r, g, b = CORES[(a["n"] - 1) % len(CORES)]
                c.setStrokeColor(colors.Color(r, g, b))
                c.setFillColor(colors.Color(r, g, b, alpha=0.28))
                c.setLineWidth(0.7)
                for pol in a["poligonos"]:
                    p = c.beginPath()
                    for ring in [pol.exterior, *pol.interiors]:
                        co = list(ring.coords)
                        p.moveTo(X(co[0][0]), Y(co[0][1]))
                        for x, y in co[1:]:
                            p.lineTo(X(x), Y(y))
                        p.close()
                    c.drawPath(p, stroke=1, fill=1, fillMode=0)        # par-ímpar: as ilhas ficam vazias
                if not a["poligonos"]:
                    c.setLineWidth(1.4)
                    for l in a["linhas"]:
                        traco(l)
                c.setFillColor(colors.Color(r, g, b))
                for x, y in a["pontos"]:
                    c.circle(X(x), Y(y), 2.2, stroke=0, fill=1)
            if contorno:
                c.setStrokeColor(colors.black)
                c.setLineWidth(1.1)
                traco(contorno + contorno[:1])
            if malha and contorno:
                gx, gy = malha
                x0 = min(q[0] for q in contorno)
                y0 = min(q[1] for q in contorno)
                x1 = max(q[0] for q in contorno)
                y1 = max(q[1] for q in contorno)
                c.setStrokeColor(colors.Color(.1, .1, .5))
                c.setLineWidth(0.4)
                c.setDash(6, 2, 1, 2)
                c.setFont(fb, 6.5)
                c.setFillColor(colors.Color(.1, .1, .5))
                # a malha é devolvida em coordenadas locais do contorno (origem no canto inferior esquerdo) ou absolutas
                dx = x0 if max(gx, default=0) <= (x1 - x0) + 1e-6 and min(gx, default=0) >= -1e-6 and x0 > max(gx, default=0) else 0.0
                dy = y0 if max(gy, default=0) <= (y1 - y0) + 1e-6 and min(gy, default=0) >= -1e-6 and y0 > max(gy, default=0) else 0.0
                for i, x in enumerate(gx):
                    c.line(X(x + dx), Y(y0) - 8, X(x + dx), Y(y1) + 8)
                    c.drawCentredString(X(x + dx), Y(y1) + 10, str(i + 1))
                for j, y in enumerate(gy):
                    c.line(X(x0) - 8, Y(y + dy), X(x1) + 8, Y(y + dy))
                    c.drawRightString(X(x0) - 10, Y(y + dy) - 2, chr(65 + j % 26))
                c.setDash()
            for a in f["artigos"]:
                pt = _ponto_etiqueta(a)
                if pt is None:
                    continue
                r, g, b = CORES[(a["n"] - 1) % len(CORES)]
                c.setFillColor(colors.white)
                c.setStrokeColor(colors.Color(r, g, b))
                c.setLineWidth(1.0)
                c.circle(X(pt[0]), Y(pt[1]), 6.2, stroke=1, fill=1)
                c.setFillColor(colors.black)
                c.setFont(fb, 7)
                c.drawCentredString(X(pt[0]), Y(pt[1]) - 2.4, str(a["n"]))
            # escala gráfica
            passo = 10 ** math.floor(math.log10(max((bx1 - bx0) / 5, 0.1)))
            c.setStrokeColor(colors.black)
            c.setLineWidth(1)
            c.line(4, 4, 4 + passo * s, 4)
            c.setFont(fr, 6.5)
            c.setFillColor(colors.black)
            c.drawString(4, 8, f"{passo:g} m")

    S = {"h1": ParagraphStyle("h1", fontName=fb, fontSize=14, leading=18, textColor=cor, spaceAfter=3),
         "h2": ParagraphStyle("h2", fontName=fb, fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3),
         "p": ParagraphStyle("p", fontName=fr, fontSize=8.5, leading=11),
         "c": ParagraphStyle("c", fontName=fr, fontSize=7.6, leading=9.4),
         "cb": ParagraphStyle("cb", fontName=fb, fontSize=7.6, leading=9.4, textColor=colors.white)}
    P = lambda s, st="c": Paragraph(str(s), S[st])  # noqa: E731
    page = landscape(A3)
    W, H = page[0] - 24 * mm, page[1] - 24 * mm
    story = [P(f"{_t('titulo', lang)}{' · ' + titulo if titulo else ''}", "h1"), P(_t("sub", lang), "p"), Spacer(1, 2 * mm)]
    if tem_geo:
        story += [Planta(W, H - 22 * mm), PageBreak()]
    story.append(P(_t("tab", lang), "h2"))
    rows = [[P(_t(k, lang), "cb") for k in ("n", "art", "cam", "qtd", "des", "res")]]
    estilos = [("BACKGROUND", (0, 0), (-1, 0), cor), ("GRID", (0, 0), (-1, -1), 0.3, colors.Color(.7, .7, .7)),
               ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    erros = 0
    for i, a in enumerate(f["artigos"], start=1):
        if a["medida"] == "comprimento":
            des, res = (f"{len(a['linhas'])} " + ("lignes" if lang == "fr" else "linhas")) if a["linhas"] else _t("semgeo", lang), _t("compr", lang)
        elif a["desenhado"] is None or (not a["poligonos"] and not a["pontos"]):
            des, res = _t("semgeo", lang), "—"
        else:
            des = f"{_num(a['desenhado'], lang, 0 if a['unit'] == 'un' else 2)} {a['unit']}"
            res = _t("ok", lang) if a["confere"] else _t("erro", lang)
            if not a["confere"]:
                erros += 1
                estilos.append(("BACKGROUND", (5, i), (5, i), colors.Color(.99, .85, .83)))
        r, g, b = CORES[(a["n"] - 1) % len(CORES)]
        estilos.append(("BACKGROUND", (0, i), (0, i), colors.Color(r, g, b, alpha=0.35)))
        rows.append([P(f"<b>{a['n']}</b>"), P(a["designacao"]), P(a["camada"]),
                     P(f"{_num(a['qty'], lang, 0 if a['unit'] == 'un' else 2)} {a['unit']}"), P(des), P(res)])
    story.append(Table(rows, colWidths=[14 * mm, 150 * mm, 70 * mm, 40 * mm, 45 * mm, 70 * mm], style=TableStyle(estilos), repeatRows=1))
    story += [Spacer(1, 2 * mm), P(_t("nota", lang), "p")]

    story.append(P(_t("escrito", lang), "h2"))
    if escrito:
        rows = [[P(_t(k, lang), "cb") for k in ("e_txt", "e_esc", "e_med", "e_dif", "e_onde", "res")]]
        est2 = [("BACKGROUND", (0, 0), (-1, 0), cor), ("GRID", (0, 0), (-1, -1), 0.3, colors.Color(.7, .7, .7))]
        for i, r_ in enumerate(escrito, start=1):
            if r_["ok"] is None:
                rows.append([P(r_["texto"]), P(f"{_num(r_['escrito'], lang)} m²"), P("—"), P("—"), P("—"), P(_t("e_fora", lang))])
                continue
            if not r_["ok"]:
                erros += 1
                est2.append(("BACKGROUND", (5, i), (5, i), colors.Color(.99, .85, .83)))
            rows.append([P(r_["texto"]), P(f"{_num(r_['escrito'], lang)} m²"), P(f"{_num(r_['medido'], lang)} m²"),
                         P("—" if r_["erro_pct"] is None else f"{_num(r_['erro_pct'], lang)} %"), P(f"<b>{r_['n']}</b> · {r_['camada']}"),
                         P(_t("ok", lang) if r_["ok"] else _t("erro", lang))])
        story.append(Table(rows, colWidths=[120 * mm, 40 * mm, 40 * mm, 30 * mm, 90 * mm, 69 * mm], style=TableStyle(est2), repeatRows=1))
    else:
        story.append(P(_t("e_nada", lang), "p"))

    avisos = []
    if estrutura:
        story.append(P(_t("estr", lang), "h2"))
        g = estrutura.get("geometria") or {}
        if malha:
            story.append(P(_t("estr_txt", lang).format(c=ed.get("camada", ""), a=_num(float(ed.get("area_m2") or 0), lang), nx=len(malha[0]),
                                                      ny=len(malha[1]), p=estrutura.get("pilares", "—")), "p"))
        elif g.get("porticos"):
            story.append(P(_t("estr_metal", lang).format(p=g.get("porticos"), s=g.get("afastamento"), v=g.get("vaos"), vao=g.get("vao"),
                                                        c=g.get("comprimento"), l=g.get("largura")), "p"))
            avisos.append("pórticos metálicos não desenhados (orientação a validar)")
    excl = medicao.get("excluidas") or []
    if excl:
        story.append(P(_t("excl", lang), "h2"))
        story.append(P("<br/>".join(f"{x.get('camada')}: {x.get('motivo')}" for x in excl[:40]), "p"))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                      title=f"{_t('titulo', lang)} {titulo}".strip()).build(story)
    if not escrito:
        avisos.append("o desenho não tem áreas escritas para conferir as medições")
    artigos = [{k: a[k] for k in ("n", "camada", "designacao", "unit", "qty", "medida", "desenhado", "confere")} for a in f["artigos"]]
    return {"pdf": buf.getvalue(), "artigos": artigos, "escrito": escrito, "erros": erros, "avisos": avisos, "desenhado": tem_geo}


def pdf_bytes(dxf: bytes, medicao: dict, **kw) -> dict:
    """DXF em bytes → folha de seguimento (mesma leitura tolerante do motor de medição)."""
    import os
    import tempfile

    import ezdxf
    from ezdxf.recover import readfile as recover_readfile
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as fh:
        fh.write(dxf)
        path = fh.name
    try:
        try:
            doc = ezdxf.readfile(path)
        except (ezdxf.DXFError, UnicodeError):
            doc, _ = recover_readfile(path)
    finally:
        os.unlink(path)
    return pdf(doc, medicao, **kw)


