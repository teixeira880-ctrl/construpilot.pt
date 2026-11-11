"""Acabamento premium dos PDF de estudo (capa, marca da empresa em todas as páginas, marca d'água, carimbo nos planos).

Recebe o PDF já calculado (nota rendu + planos GO) e devolve um PDF de apresentação:
  • capa A4 com o logótipo da empresa e o do ConstruPilot, título, local, 4 indicadores-chave, miniatura do plano e índice;
  • em cada página da nota: logótipo da empresa no cabeçalho e logótipo em marca d'água (opacidade baixa);
  • em cada plano: logótipo da empresa no cartucho;
  • metadados (título, autor, assunto) e marcadores de navegação.
Sem dependências novas (pymupdf). As fontes DejaVu do repositório garantem o cirílico.
"""
from __future__ import annotations

import os

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "company_logos")
MARCAS = {
    "clt-rezult": {"nome": "CLT Rezult", "logo": "clt-rezult.png", "cor": (0.886, 0.078, 0.067), "site": "clt-rezult.com",
                   "linha": "Cross Laminated Timber · Ukraine"},
}
ESCURO, CINZA, VERDE = (0.10, 0.11, 0.12), (0.42, 0.43, 0.45), (0.09, 0.29, 0.22)


def _fontes():
    from .gros_oeuvre import _fontes as f
    return f()


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def marca(slug: str | None, nome=None, cor=None, logo_png: bytes | None = None) -> dict | None:
    if not slug and not logo_png:
        return None
    b = dict(MARCAS.get(slug or "", {"nome": nome or slug or "", "cor": VERDE, "site": "", "linha": ""}))
    if nome:
        b["nome"] = nome
    if cor:
        b["cor"] = _hex(cor) if isinstance(cor, str) else cor
    if logo_png:
        b["logo_bytes"] = logo_png
    elif b.get("logo") and os.path.exists(os.path.join(ASSETS, b["logo"])):
        b["logo_bytes"] = open(os.path.join(ASSETS, b["logo"]), "rb").read()
    return b


def _logo_rect(pix_w, pix_h, x, y, w_max, h_max, alinhar="esq"):
    k = min(w_max / pix_w, h_max / pix_h)
    w, h = pix_w * k, pix_h * k
    if alinhar == "dir":
        x = x - w
    return (x, y, x + w, y + h)


def embelezar(pdf: bytes, capa: dict, empresa: dict | None = None, n_nota: int | None = None, tr=None) -> bytes:
    """capa = {titulo, subtitulo, local, data, kpis:[(rotulo, valor, unidade)], indice:[(titulo, pagina)], miniatura_pagina:int|None}.
    n_nota = número de páginas da nota (as seguintes são planos)."""
    import pymupdf
    tr = tr or (lambda x: x)
    fr, fb = _fontes()
    src = pymupdf.open(stream=pdf, filetype="pdf")
    cor = (empresa or {}).get("cor", VERDE)
    logo = None
    if empresa and empresa.get("logo_bytes"):
        logo = empresa["logo_bytes"]
        lp = pymupdf.Pixmap(logo)
        lw, lh = lp.width, lp.height
    # ---------------------------------------------------------------- capa
    out = pymupdf.open()
    W, H = 595.28, 841.89
    pg = out.new_page(width=W, height=H)
    pg.insert_font(fontname="cr", fontfile=fr)
    pg.insert_font(fontname="cb", fontfile=fb)

    def t(x, y, s, size, c=ESCURO, bold=False, page=pg):
        page.insert_text((x, y), s, fontname="cb" if bold else "cr", fontsize=size, color=c)

    pg.draw_rect(pymupdf.Rect(0, 0, W, H), color=None, fill=(0.985, 0.98, 0.972))
    pg.draw_rect(pymupdf.Rect(0, 0, W, 300), color=None, fill=ESCURO)
    pg.draw_rect(pymupdf.Rect(0, 296, W, 304), color=None, fill=cor)
    if capa.get("capa_imagem"):
        # imagem de capa (render 3D) em fundo, com véu escuro à esquerda para o título
        pg.insert_image(pymupdf.Rect(0, 0, W, 296), stream=capa["capa_imagem"], keep_proportion=False)
        pg.draw_rect(pymupdf.Rect(0, 0, W * 0.62, 296), color=None, fill=ESCURO, fill_opacity=0.72)
    elif capa.get("miniatura_pagina") is not None and capa["miniatura_pagina"] < len(src):
        sp = src[capa["miniatura_pagina"]]
        clip = sp.rect
        mini = sp.get_pixmap(dpi=60, clip=clip)
        r = pymupdf.Rect(W * 0.40, 30, W - 30, 280)
        pg.draw_rect(r, color=None, fill=(1, 1, 1), fill_opacity=0.96)
        pg.insert_image(r + (6, 6, -6, -6), pixmap=mini, keep_proportion=True)
    if logo:
        pg.draw_rect(pymupdf.Rect(30, 34, 210, 100), color=None, fill=(1, 1, 1))
        pg.insert_image(pymupdf.Rect(*_logo_rect(lw, lh, 40, 42, 160, 50)), stream=logo)
    t(30, 140, "ConstruPilot", 11, (0.85, 0.85, 0.85), True)
    t(30, 156, "× " + (empresa or {}).get("nome", ""), 11, cor, True) if empresa else None
    tit = capa.get("titulo") or "Estudo"
    y = 205
    for linha in _quebra(tit, 20):
        t(30, y, linha, 17, (1, 1, 1), True)
        y += 21
    larg_txt = W * 0.36 if (capa.get("miniatura_pagina") is not None and not capa.get("capa_imagem")) else W * 0.56
    for linha in _quebra(capa.get("subtitulo", ""), int(larg_txt / 4.6)):
        t(30, y + 6, linha, 9, (0.80, 0.80, 0.80))
        y += 12
    t(30, 340, capa.get("local", ""), 12, ESCURO, True)
    t(30, 358, capa.get("data", ""), 9, CINZA)
    # KPIs
    kp = capa.get("kpis") or []
    cw = (W - 60 - 3 * 10) / 4
    for i, (rot, val, un) in enumerate(kp[:8]):
        cx = 30 + (i % 4) * (cw + 10)
        cy = 385 + (i // 4) * 92
        pg.draw_rect(pymupdf.Rect(cx, cy, cx + cw, cy + 80), color=(0.88, 0.88, 0.88), fill=(1, 1, 1), width=0.6)
        pg.draw_rect(pymupdf.Rect(cx, cy, cx + 4, cy + 80), color=None, fill=cor)
        t(cx + 12, cy + 18, str(rot)[:26], 7, CINZA)
        sv = str(val)[:16]
        t(cx + 12, cy + 48, sv, 17 if len(sv) <= 8 else 13, ESCURO, True)
        t(cx + 12, cy + 66, str(un)[:28], 7, CINZA)
    # índice
    iy = 385 + 92 * ((len(kp[:8]) + 3) // 4) + 18
    t(30, iy, tr("Зміст / Contents"), 11, ESCURO, True)
    iy += 18
    ind = (capa.get("indice") or [])[:28]
    passo = min(14.0, (H - 60 - iy) / max(1, len(ind)))
    fs = min(8.5, passo - 1.6)
    for tt, pnum in ind:
        t(42, iy, str(tt)[:80], fs, ESCURO)
        t(W - 50, iy, str(pnum), fs, CINZA, True)
        pg.draw_line((42 + min(len(str(tt)) * fs * 0.52, 380), iy - 2), (W - 58, iy - 2), color=(0.82, 0.82, 0.82), width=0.4, dashes="[1 2] 0")
        iy += passo
    pg.draw_rect(pymupdf.Rect(0, H - 48, W, H), color=None, fill=ESCURO)
    t(30, H - 22, "ConstruPilot · construpilot.pt" + (f"   |   {empresa['nome']} · {empresa.get('site', '')}" if empresa else ""), 8, (0.9, 0.9, 0.9))
    t(30, H - 10, tr("Попередній розрахунок детермінованими модулями — підлягає перевірці відповідальним інженером. / Preliminary design — to be checked by "
      "the responsible engineer."), 5.6, (0.65, 0.65, 0.65))
    # ---------------------------------------------------------------- páginas
    out.insert_pdf(src)
    nn = n_nota if n_nota is not None else len(src)
    for i in range(1, len(out)):
        p = out[i]
        r = p.rect
        nota = (i - 1) < nn
        if logo:
            if nota:
                # under the footer text (baseline 8.5 mm), above the coloured band: never over the text
                p.insert_image(pymupdf.Rect(*_logo_rect(lw, lh, r.width / 2 - 12 * 2.835, r.height - 7.2 * 2.835, 24 * 2.835, 5.4 * 2.835)), stream=logo)
                wm = pymupdf.Rect(r.width * 0.18, r.height * 0.40, r.width * 0.82, r.height * 0.40 + (r.width * 0.64) * lh / lw)
                p.insert_image(wm, stream=_opaco(logo, 0.06), overlay=False)
            else:
                # carimbo da empresa por cima do cartucho ConstruPilot (canto inferior direito)
                bw = 200
                bx, by = r.width - 30 - bw, r.height - 25 - 175 - 46
                p.draw_rect(pymupdf.Rect(bx, by, bx + bw, by + 40), color=cor, fill=(1, 1, 1), width=0.8)
                p.insert_image(pymupdf.Rect(*_logo_rect(lw, lh, bx + 8, by + 5, bw - 16, 30)), stream=logo)
        p.draw_rect(pymupdf.Rect(0, r.height - 3, r.width, r.height), color=None, fill=cor)
    out.set_metadata({"title": capa.get("titulo", ""), "author": "ConstruPilot" + (f" × {empresa['nome']}" if empresa else ""),
                      "subject": capa.get("subtitulo", ""), "creator": "ConstruPilot calc_lots"})
    toc = [[1, tr("Обкладинка / Cover"), 1]] + [[1, str(tt), int(pn)] for tt, pn in (capa.get("indice") or []) if str(pn).isdigit()]
    try:
        out.set_toc(toc)
    except Exception:  # noqa: BLE001
        pass
    return out.tobytes(garbage=3, deflate=True)


def _opaco(png: bytes, alpha: float) -> bytes:
    import pymupdf
    pix = pymupdf.Pixmap(png)
    if not pix.alpha:
        pix = pymupdf.Pixmap(pix, 1)
    n = pix.n
    s = bytearray(pix.samples)
    for i in range(n - 1, len(s), n):
        s[i] = int(s[i] * alpha)
    p2 = pymupdf.Pixmap(pix.colorspace, pix.width, pix.height, bytes(s), True)
    return p2.tobytes("png")


def _quebra(s, n):
    out, linha = [], ""
    for w in str(s).split():
        if len(linha) + len(w) + 1 > n and linha:
            out.append(linha)
            linha = w
        else:
            linha = (linha + " " + w).strip()
    if linha:
        out.append(linha)
    return out[:4]
