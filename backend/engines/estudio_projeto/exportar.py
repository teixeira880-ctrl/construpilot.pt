"""Exportações de desenho do Estúdio: pranchas PDF vetoriais à escala e DXF em metros, por camadas.

Ambas escrevem as mesmas primitivas que o ecrã mostra (`desenhos.py`), calculadas do modelo único — o que se mede no
PDF à escala ou no DXF é o que o modelo tem.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

ESCALAS = (50, 100, 200, 500, 1000)
CAMADAS = {"PAREDES": 7, "VAOS": 5, "TEXTO_VAOS": 8, "PAVIMENTOS": 9, "MOBILIARIO": 8, "ESCADAS": 6, "TEXTO": 7, "COTAS": 1, "DESENHO": 7}


def _limites(itens: List[dict]) -> Tuple[float, float, float, float]:
    xs, ys = [], []
    for it in itens:
        if it["t"] in ("poly", "line"):
            xs += [p[0] for p in it["pts"]]
            ys += [p[1] for p in it["pts"]]
        elif it["t"] == "text":
            xs.append(it["x"])
            ys.append(it["y"])
        elif it["t"] == "tick":
            xs.append(it["p"][0])
            ys.append(it["p"][1])
    if not xs:
        return 0.0, 0.0, 1.0, 1.0
    return min(xs), min(ys), max(xs), max(ys)


def escala_que_cabe(itens: List[dict], larg_mm: float, alt_mm: float, folga_mm: float = 34.0) -> int:
    x0, y0, x1, y1 = _limites(itens)
    for e in ESCALAS:
        if (x1 - x0) * 1000 / e + folga_mm <= larg_mm and (y1 - y0) * 1000 / e + folga_mm * 0.6 <= alt_mm:
            return e
    return ESCALAS[-1]


def pranchas_pdf(processo: Dict[str, Any], desenhos: List[Dict[str, Any]]) -> bytes:
    """Uma folha A3 horizontal por desenho, vetorial e à escala (a maior de 1:50, 1:100, 1:200… que cabe na folha)."""
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from engines.urbanismo_pt import pdf as UP
    f = UP._fonts()
    d = processo or {}
    ter, req = d.get("terreno") or {}, d.get("requerente") or {}
    buf = io.BytesIO()
    pw, ph = landscape(A3)
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    c.setTitle("Pranchas do Estúdio de Projeto — ConstruPilot")
    mg, cw, chh = 12 * mm, 120 * mm, 46 * mm
    util_w, util_h = (pw - 2 * mg) / mm, (ph - 2 * mg - chh - 6 * mm) / mm
    cor = lambda t: tuple(v / 255 for v in t)  # noqa: E731
    for i, des in enumerate(desenhos, 1):
        itens = des["itens"]
        esc = escala_que_cabe(itens, util_w, util_h)
        x0, y0, x1, y1 = _limites(itens)
        k = 1000.0 / esc * mm                                    # pontos por metro
        ox = mg + ((pw - 2 * mg) - (x1 - x0) * k) / 2 - x0 * k
        oy = mg + chh + 6 * mm + (util_h * mm - (y1 - y0) * k) / 2 - y0 * k
        P = lambda p: (ox + p[0] * k, oy + p[1] * k)  # noqa: E731
        c.setStrokeColorRGB(0.12, 0.16, 0.2)
        c.setLineWidth(1.2)
        c.rect(mg, mg, pw - 2 * mg, ph - 2 * mg)
        for it in itens:
            if it["t"] == "poly":
                pth = c.beginPath()
                for anel in [it["pts"]] + list(it["furos"]):
                    pts = [P(p) for p in anel]
                    pth.moveTo(*pts[0])
                    for q in pts[1:]:
                        pth.lineTo(*q)
                    pth.close()
                if it["fill"] is not None:
                    c.setFillColorRGB(*cor(it["fill"]))
                if it["stroke"] is not None:
                    c.setStrokeColorRGB(*cor(it["stroke"]))
                    c.setLineWidth(max(0.2, it["lw"] * 0.4))
                c.drawPath(pth, fill=1 if it["fill"] is not None else 0, stroke=1 if it["stroke"] is not None and it["lw"] > 0 else 0, fillMode=0)
            elif it["t"] == "line":
                c.setStrokeColorRGB(*cor(it["stroke"]))
                c.setLineWidth(max(0.2, it["lw"] * 0.4))
                c.setDash([4, 3] if it["dash"] else [])
                pts = [P(p) for p in it["pts"]]
                pth = c.beginPath()
                pth.moveTo(*pts[0])
                for q in pts[1:]:
                    pth.lineTo(*q)
                c.drawPath(pth, fill=0, stroke=1)
                c.setDash([])
            elif it["t"] == "tick":
                x, y = P(it["p"])
                c.setStrokeColorRGB(*cor(it["stroke"]))
                c.setLineWidth(0.5)
                c.line(x, y - 3, x, y + 3) if it["horizontal"] else c.line(x - 3, y, x + 3, y)
            elif it["t"] == "text":
                x, y = P((it["x"], it["y"]))
                tam = max(4.5, it["sz"] * 0.5)
                c.setFont(f["regular"], tam)
                c.setFillColorRGB(*cor(it["cor"]))
                x, y = x + it["dx"] * 0.5, y - it["dy"] * 0.5 - tam * 0.32
                {"m": c.drawCentredString, "l": c.drawString, "r": c.drawRightString}[it["anchor"][0]](x, y, it["txt"])
        # escala gráfica
        passo = {50: 1, 100: 1, 200: 2, 500: 5, 1000: 10}[esc]
        bx, by = mg + 8 * mm, mg + chh + 2 * mm
        c.setStrokeColorRGB(0.12, 0.16, 0.2)
        c.setFillColorRGB(0.12, 0.16, 0.2)
        c.setLineWidth(0.6)
        for n in range(5):
            c.rect(bx + n * passo * k, by, passo * k, 1.6 * mm, fill=1 if n % 2 == 0 else 0)
        c.setFont(f["regular"], 6.5)
        c.drawString(bx, by + 2.6 * mm, "0")
        c.drawRightString(bx + 5 * passo * k, by + 2.6 * mm, f"{5 * passo} m")
        # legenda (carimbo), igual à das peças desenhadas do processo
        cx, cy = pw - mg - cw, mg
        c.setFillColorRGB(1, 1, 1)
        c.setStrokeColorRGB(0.12, 0.16, 0.2)
        c.setLineWidth(1.0)
        c.rect(cx, cy, cw, chh, fill=1)
        c.setFillColorRGB(0.12, 0.16, 0.2)
        linhas = [("Processo", d.get("title") or "—"), ("Requerente", req.get("nome") or "—"),
                  ("Local", ", ".join(x for x in (ter.get("morada"), ter.get("concelho")) if x) or "—"),
                  ("Peça", des["titulo"]), ("Escala", f"1:{esc}  (folha A3)"), ("Data / folha", f"{UP._hoje()} · {i}/{len(desenhos)}"),
                  ("Técnico autor", "______________________  (n.º de inscrição na Ordem)")]
        yy = cy + chh - 6 * mm
        for rot, val in linhas:
            c.setFont(f["bold"], 7.5)
            c.drawString(cx + 3 * mm, yy, rot)
            c.setFont(f["regular"], 7.5)
            c.drawString(cx + 28 * mm, yy, str(val)[:70])
            yy -= 5.6 * mm
        if des.get("rodape"):
            c.setFont(f["regular"], 6.5)
            c.setFillGray(0.35)
            c.drawString(mg + 3 * mm, mg + 2.5 * mm, des["rodape"][:150])
        c.showPage()
    c.save()
    return buf.getvalue()


def dxf(desenhos: List[Dict[str, Any]], titulo: Optional[str] = None) -> bytes:
    """DXF (R2010) em METROS com todas as peças lado a lado no espaço do modelo, por camadas. As plantas ficam nas
    coordenadas do modelo (a primeira sem deslocamento): medir no CAD dá as medidas reais."""
    import ezdxf
    from ezdxf import units
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.M
    doc.header["$MEASUREMENT"] = 1
    for nome, cor in CAMADAS.items():
        if nome not in doc.layers:
            doc.layers.add(nome, color=cor)
    msp = doc.modelspace()
    cursor_x, linha_y, alt_linha = 0.0, 0.0, 0.0
    codigo_ant = None
    for des in desenhos:
        itens = des["itens"]
        x0, y0, x1, y1 = _limites(itens)
        if codigo_ant is not None and des.get("code") != codigo_ant:      # nova fila: plantas, depois alçados, depois cortes
            cursor_x, linha_y, alt_linha = 0.0, linha_y - alt_linha - 8.0, 0.0
        primeiro = codigo_ant is None
        dx = 0.0 if primeiro else cursor_x - x0
        dy = 0.0 if primeiro else linha_y - y1
        T = lambda p: (p[0] + dx, p[1] + dy)  # noqa: E731
        for it in itens:
            cam = it.get("cam", "DESENHO")
            if it["t"] == "poly":
                pl = msp.add_lwpolyline([T(p) for p in it["pts"]], close=True, dxfattribs={"layer": cam})
                furos = [msp.add_lwpolyline([T(p) for p in fr], close=True, dxfattribs={"layer": cam}) for fr in it["furos"]]
                if cam == "PAREDES" and it["fill"] is not None:           # paredes cortadas: trama sólida
                    h = msp.add_hatch(color=8, dxfattribs={"layer": cam})
                    h.paths.add_polyline_path([T(p) for p in it["pts"]], is_closed=True, flags=1)
                    for fr in it["furos"]:
                        h.paths.add_polyline_path([T(p) for p in fr], is_closed=True, flags=16)
                _ = (pl, furos)
            elif it["t"] == "line":
                msp.add_lwpolyline([T(p) for p in it["pts"]], dxfattribs={"layer": cam, "linetype": "DASHED" if it["dash"] else "BYLAYER"})
            elif it["t"] == "tick":
                x, y = T(it["p"])
                msp.add_line((x, y - 0.08), (x, y + 0.08), dxfattribs={"layer": cam}) if it["horizontal"] else \
                    msp.add_line((x - 0.08, y), (x + 0.08, y), dxfattribs={"layer": cam})
            elif it["t"] == "text":
                alt = max(0.08, it["sz"] * 0.012)
                x, y = T((it["x"], it["y"]))
                from ezdxf.enums import TextEntityAlignment as A
                al = {"m": A.MIDDLE_CENTER, "l": A.MIDDLE_LEFT, "r": A.MIDDLE_RIGHT}[it["anchor"][0]]
                msp.add_text(it["txt"], height=alt, dxfattribs={"layer": cam if cam != "DESENHO" else "TEXTO"}).set_placement(
                    (x + it["dx"] * 0.012, y - it["dy"] * 0.012), align=al)
        from ezdxf.enums import TextEntityAlignment as A
        msp.add_text(des["titulo"], height=0.25, dxfattribs={"layer": "TEXTO"}).set_placement((x0 + dx, y1 + dy + 0.8), align=A.LEFT)
        cursor_x = (x1 + dx) + 6.0
        alt_linha = max(alt_linha, y1 - y0 + 2.0)
        if primeiro:
            linha_y = y1
        codigo_ant = des.get("code")
    if titulo:
        doc.header["$PROJECTNAME"] = str(titulo)[:120]
    out = io.StringIO()
    doc.write(out)
    return out.getvalue().encode("utf-8")
