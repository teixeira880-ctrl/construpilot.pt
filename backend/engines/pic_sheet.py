"""Folha técnica do plano de estaleiro: o plano é desenhado por cima do PDF original do
projetista, à escala e no formato da folha (A1, A0…), sem rasterizar o desenho de origem.
A legenda é colocada automaticamente na zona mais vazia da folha."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from engines import pic

PT_MM = 25.4 / 72.0
MM = 72.0 / 25.4


def _rgb(hexa: str) -> tuple[float, float, float]:
    h = (hexa or "#334155").lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _txt(s) -> str:
    """Texto compatível com a fonte base do PDF (WinAnsi)."""
    s = str(s).replace("≥", ">=").replace("≤", "<=").replace("−", "-").replace("→", "->")
    return s.encode("cp1252", "replace").decode("cp1252")


def _fr(v, nd=2) -> str:
    if v is None:
        return "—"
    return (f"{float(v):.{nd}f}".rstrip("0").rstrip(".") if nd else f"{float(v):.0f}").replace(".", ",")


def _free_box(page, bw: float, bh: float, avoid: list, margin: float) -> tuple[float, float]:
    """Canto superior esquerdo da zona com menos tinta onde cabe uma caixa bw × bh (pt),
    fora das zonas a evitar (retângulos em pt)."""
    import pymupdf
    z = 0.12
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, alpha=False)
    w, h, data = pix.width, pix.height, pix.samples
    # tabela de somas (tinta = 255 - cinzento)
    integ = [[0] * (w + 1) for _ in range(h + 1)]
    for y in range(h):
        row, acc, base = integ[y + 1], 0, y * w
        prev = integ[y]
        for x in range(w):
            acc += 255 - data[base + x]
            row[x + 1] = prev[x + 1] + acc

    def ink(x0, y0, x1, y1):
        a, b, c, d = int(x0 * z), int(y0 * z), min(int(x1 * z), w), min(int(y1 * z), h)
        return integ[d][c] - integ[b][c] - integ[d][a] + integ[b][a]

    best = None
    step = 8 * MM
    y = margin
    while y + bh <= page.rect.height - margin:
        x = margin
        while x + bw <= page.rect.width - margin:
            hit = sum(max(0.0, min(x + bw, r[2]) - max(x, r[0])) * max(0.0, min(y + bh, r[3]) - max(y, r[1]))
                      for r in avoid)
            score = ink(x, y, x + bw, y + bh) + hit * 50.0
            if best is None or score < best[0]:
                best = (score, x, y)
            x += step
        y += step
    return (best[1], best[2]) if best else (margin, margin)


def _page2(doc, d: dict, snapshot: bytes | None, snapshot_aerial: bytes | None, W: float, H: float,
           company: str) -> None:
    """Folha 2: corte vertical A–A′ (vetorial) e vistas 3D / aérea, no mesmo formato da folha original."""
    import pymupdf
    from engines import pic_relief as relief
    sec = (d.get("result") or {}).get("section")
    if not (sec and sec.get("svg")) and not snapshot and not snapshot_aerial:
        return
    pg = doc.new_page(width=W, height=H)
    m = max(12 * MM, W * 0.02)
    tb = 16 * MM
    sh = pg.new_shape()
    sh.draw_rect(pymupdf.Rect(m, m, W - m, H - m))
    sh.finish(color=(0, 0, 0), width=1.0)
    sh.draw_line((m, H - m - tb), (W - m, H - m - tb))
    sh.finish(color=(0, 0, 0), width=0.6)
    sh.commit()
    pg.insert_text((m + 4 * MM, H - m - tb + 7 * MM), _txt(relief.T["sheet_p2"]), fontname="hebo",
                   fontsize=14, color=(0, 0, 0))
    pg.insert_text((m + 4 * MM, H - m - tb + 12.5 * MM),
                   _txt(f"{company} · {datetime.now(timezone.utc).strftime('%d/%m/%Y')}"),
                   fontname="helv", fontsize=9, color=(0.2, 0.2, 0.2))
    inner = pymupdf.Rect(m + 6 * MM, m + 6 * MM, W - m - 6 * MM, H - m - tb - 6 * MM)
    imgs = [(b, t) for b, t in ((snapshot, relief.T["v3d"]), (snapshot_aerial, relief.T["vaer"])) if b]
    top = inner
    if sec and sec.get("svg"):
        if imgs:
            top = pymupdf.Rect(inner.x0, inner.y0, inner.x1, inner.y0 + inner.height * 0.56)
        src = pymupdf.open("pdf", pymupdf.open(stream=sec["svg"].encode("utf-8"), filetype="svg").convert_to_pdf())
        pg.show_pdf_page(top, src, 0, keep_proportion=True)
        y_img = top.y1 + 6 * MM
    else:
        y_img = inner.y0
    if imgs:
        gap = 8 * MM
        cw = (inner.width - gap * (len(imgs) - 1)) / len(imgs)
        for i, (b, t) in enumerate(imgs):
            x = inner.x0 + i * (cw + gap)
            pg.insert_text((x, y_img + 5 * MM), _txt(t), fontname="hebo", fontsize=12, color=(0.06, 0.32, 0.34))
            r = pymupdf.Rect(x, y_img + 8 * MM, x + cw, inner.y1)
            try:
                pg.insert_image(r, stream=b, keep_proportion=True)
            except Exception:  # noqa: BLE001 — imagem ilegível: a folha sai sem ela
                pass


def build(pdf_bytes: bytes, d: dict, branding: dict | None = None, page_index: int = 0,
          snapshot: bytes | None = None, snapshot_aerial: bytes | None = None) -> bytes:
    import pymupdf
    res, site = d["result"], d["site"]
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    doc = pymupdf.open()
    doc.insert_pdf(src, from_page=page_index, to_page=page_index)
    src.close()
    page = doc[0]
    if page.rotation:
        page.remove_rotation()
    W, H = page.rect.width, page.rect.height
    k = W / res["site"]["width_m"]                     # pt por metro

    def P(x, y):
        return pymupdf.Point(x * k, y * k)

    avoid = []

    def poly(pts, color, fill=None, fill_opacity=0.3, width=0.9, dashes=None, track=True):
        sh = page.new_shape()
        sh.draw_polyline([P(x, y) for x, y in pts] + [P(*pts[0])])
        sh.finish(color=color, fill=fill, fill_opacity=fill_opacity if fill else 1, width=width,
                  dashes=dashes, closePath=True)
        sh.commit()
        if track:
            xs, ys = [p[0] * k for p in pts], [p[1] * k for p in pts]
            avoid.append((min(xs), min(ys), max(xs), max(ys)))

    def tag(x, y, text, color, r=3.2 * MM):
        c = P(x, y)
        sh = page.new_shape()
        sh.draw_circle(c, r)
        sh.finish(color=color, fill=(1, 1, 1), width=1.1)
        sh.commit()
        fs = 9 if len(text) < 2 else 7.5
        tw = pymupdf.get_text_length(text, "hebo", fs)
        page.insert_text((c.x - tw / 2, c.y + fs * 0.35), text, fontname="hebo", fontsize=fs, color=color)

    # zona de construção servida (contorno)
    for b in site.get("buildings") or []:
        poly([pic.to_m(site, p) for p in b], _rgb("#FF8F00"), fill=_rgb("#FFC400"), fill_opacity=0.12,
             width=1.4, dashes="[6 3] 0")
    parcel = [pic.to_m(site, p) for p in site.get("parcel") or []]
    if len(parcel) >= 3:
        xs, ys = [p[0] * k for p in parcel], [p[1] * k for p in parcel]
        avoid.append((min(xs), min(ys), max(xs), max(ys)))

    legend = []
    n = 0
    red, green = _rgb("#FF1744"), _rgb("#00A843")
    for e in res["elements"]:
        col = _rgb(e.get("color"))
        if e["type"] == "acces":
            c = P(e["x"], e["y"])
            sh = page.new_shape()
            s = 4 * MM
            sh.draw_polyline([(c.x, c.y - s), (c.x + s, c.y + s * 0.8), (c.x - s, c.y + s * 0.8), (c.x, c.y - s)])
            sh.finish(color=col, fill=col, fill_opacity=0.9, width=0.8)
            sh.commit()
            page.insert_text((c.x - 2.6, c.y + s * 0.55), "A", fontname="hebo", fontsize=8, color=(1, 1, 1))
            legend.append(("A", e["label"], col))
            continue
        n += 1
        rect = pic._rect(e["x"], e["y"], e["w"], e["h"], e["rot"])
        if e["type"] == "grue" and e.get("jib_m"):
            c = P(e["x"], e["y"])
            sh = page.new_shape()
            sh.draw_circle(c, e["jib_m"] * k)
            sh.finish(color=red, fill=red, fill_opacity=0.035, width=1.6, dashes="[10 5] 0")
            lift = e.get("lift_radius_m")
            if lift and lift < e["jib_m"] - 0.05:
                sh.draw_circle(c, lift * k)
                sh.finish(color=green, width=1.3, dashes="[4 4] 0")
            sh.draw_line(c, (c.x + e["jib_m"] * k, c.y))
            sh.finish(color=red, width=1.0)
            sh.commit()
            page.insert_text((c.x + 6 * MM, c.y - 1.5 * MM), _txt(f"R = {_fr(e['jib_m'])} m"), fontname="hebo",
                             fontsize=9, color=red)
        poly(list(rect.exterior.coords)[:-1], col, fill=col, fill_opacity=0.35, width=1.0)
        tag(e["x"], e["y"], str(n), col)
        dims = f" ({_fr(e['w'])} × {_fr(e['h'])} m)" if e["w"] and e["h"] else ""
        legend.append((str(n), e["label"] + dims, col))

    # ---- traço do corte A–A′ ------------------------------------------------
    sec = res.get("section")
    if sec and sec.get("axis"):
        from engines import pic_relief as relief
        teal = _rgb("#0F5257")
        a, b = (tuple(q) for q in sec["axis"])
        sh = page.new_shape()
        sh.draw_line(P(*a), P(*b))
        sh.finish(color=teal, width=1.6, dashes="[14 4 3 4] 0")
        for q in (a, b):
            sh.draw_circle(P(*q), 2.4 * MM)
            sh.finish(color=teal, fill=teal)
        sh.commit()
        for q, lab in ((a, "A"), (b, "A'")):
            pq = P(*q)
            page.insert_text((pq.x + 3.5 * MM, pq.y - 2 * MM), lab, fontname="hebo", fontsize=14, color=teal)

    # ---- legenda / carimbo do plano de estaleiro --------------------------
    cranes = [c for c in res.get("cranes") or [] if c.get("label")]
    rows = [(num, _txt(label), col) for num, label, col in legend]
    extra = []
    for c in cranes:
        name = f"Grua {c['num']}: " if len(cranes) > 1 else "Grua: "
        extra.append(_txt(f"{name}{c['label']} · lança {_fr(c['jib_m'])} m · alcance necessário "
                          f"{_fr(c['reach_required_m'], 1)} m"))
        extra.append(_txt(f"   carga no raio útil {_fr(c['capacity_at_reach_t'])} t · na ponta da lança "
                          f"{_fr(c['tip_t'])} t · carga a elevar {_fr(c['load']['t'])} t · "
                          f"{'ADEQUADA' if c['ok'] else 'A REVER'}"))
    if cranes:
        extra.append(_txt("Círculo vermelho: zona varrida pela lança. Círculo verde: limite de elevação da carga mais pesada."))
    if res.get("cloture_ml"):
        extra.append(_txt(f"Vedação do estaleiro: {_fr(res['cloture_ml'], 1)} m (limite a vermelho)."))
    sheet = site.get("sheet") or {}
    escala = f"Escala 1:{sheet['scale_n']}" if sheet.get("scale_n") else "Escala da folha original"
    company = (branding or {}).get("company_name") or "ConstruPilot"
    lh, pad = 4.6 * MM, 3 * MM
    bw = 165 * MM
    bh = 2 * pad + 13 * MM + lh * (len(rows) + len(extra) + (1 if res.get('section') else 0)) + 9 * MM
    x0, y0 = _free_box(page, bw, bh, avoid, 22 * MM)
    sh = page.new_shape()
    sh.draw_rect(pymupdf.Rect(x0, y0, x0 + bw, y0 + bh))
    sh.finish(color=(0, 0, 0), fill=(1, 1, 1), width=0.9)
    sh.draw_line((x0, y0 + 13 * MM), (x0 + bw, y0 + 13 * MM))
    sh.finish(color=(0, 0, 0), width=0.5)
    sh.commit()
    page.insert_text((x0 + pad, y0 + 6.5 * MM), "PLANO DE ESTALEIRO", fontname="hebo", fontsize=13, color=(0, 0, 0))
    page.insert_text((x0 + pad, y0 + 11 * MM),
                     _txt(f"{company} · {escala} · {datetime.now(timezone.utc).strftime('%d/%m/%Y')}"),
                     fontname="helv", fontsize=8, color=(0.2, 0.2, 0.2))
    y = y0 + 13 * MM + pad + lh * 0.7
    for num, label, col in rows:
        page.insert_text((x0 + pad, y), num, fontname="hebo", fontsize=8.5, color=col)
        page.insert_text((x0 + pad + 9 * MM, y), label[:110], fontname="helv", fontsize=8, color=(0, 0, 0))
        y += lh
    for line in extra:
        page.insert_text((x0 + pad, y), line[:140], fontname="helv", fontsize=7.6, color=(0.1, 0.1, 0.1))
        y += lh
    page.insert_text((x0 + pad, y0 + bh - pad),
                     _txt("Documento de preparação. Características da grua a confirmar com a ficha técnica da "
                          "empresa de aluguer. Hipóteses e verificações: ver memória."),
                     fontname="heit", fontsize=6.6, color=(0.3, 0.3, 0.3))
    if sec and sec.get("axis"):
        page.insert_text((x0 + pad, y0 + bh - pad - lh * 0.9), _txt(relief.T["sheet_axis"]), fontname="hebo",
                         fontsize=7.6, color=_rgb("#0F5257"))
    _page2(doc, d, snapshot, snapshot_aerial, W, H, company)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out
