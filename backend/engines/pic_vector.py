"""Leitura vetorial de uma folha de projeto (PDF) para o plano de estaleiro.

Numa planta de arquitetura em PDF vetorial, o limite do prédio vem normalmente desenhado a
vermelho (traço grosso interrompido). Este módulo lê esse traçado diretamente dos vetores —
é exato, ao contrário de uma leitura por IA — e devolve também o formato real da folha, que
com a escala escrita (1:100…) dá a escala exata da imagem.
Tudo é devolvido em coordenadas normalizadas 0–1 da página tal como é vista (x → direita,
y → baixo), as mesmas do resto do módulo.
"""
from __future__ import annotations

import math
import re

PT_MM = 25.4 / 72.0


def _open(pdf_bytes: bytes, page_index: int = 0):
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if not 0 <= page_index < len(doc):
        raise ValueError("Página inexistente")
    page = doc[page_index]
    if page.rotation:
        page.remove_rotation()          # coordenadas = página tal como é vista
    return doc, page


def sheet_info(pdf_bytes: bytes, page_index: int = 0) -> dict:
    """Formato real da folha (mm)."""
    doc, page = _open(pdf_bytes, page_index)
    try:
        return {"w_mm": round(page.rect.width * PT_MM, 1), "h_mm": round(page.rect.height * PT_MM, 1)}
    finally:
        doc.close()


def parse_scale(text) -> int | None:
    """«1/100», «1:100», «1-100», «Escala: 1-100» → 100. None se não for uma escala."""
    m = re.search(r"\b1\s*[/:\-]\s*(\d{2,5})\b", str(text or ""))
    if not m:
        return None
    n = int(m.group(1))
    return n if 10 <= n <= 20000 else None


def m_per_px(scale_n: int, sheet_w_mm: float, img_w_px: int) -> float:
    """Metros reais por píxel de uma imagem que mostra a folha inteira."""
    return (sheet_w_mm / 1000.0) * scale_n / float(img_w_px)


def _is_red(c) -> bool:
    return bool(c) and len(c) >= 3 and c[0] > 0.75 and c[1] < 0.3 and c[2] < 0.3


def _simplify(pts: list, tol: float, lo: int = 0, hi: int | None = None) -> list[int]:
    """Douglas-Peucker: índices dos pontos mantidos."""
    hi = len(pts) - 1 if hi is None else hi
    if hi - lo < 2:
        return [lo, hi] if hi > lo else [lo]
    (x1, y1), (x2, y2) = pts[lo], pts[hi]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    best, idx = 0.0, lo
    for i in range(lo + 1, hi):
        d = abs(dy * (pts[i][0] - x1) - dx * (pts[i][1] - y1)) / norm
        if d > best:
            best, idx = d, i
    if best <= tol:
        return [lo, hi]
    return _simplify(pts, tol, lo, idx)[:-1] + _simplify(pts, tol, idx, hi)


def _fit_line(pts: list) -> tuple[float, float, float, float] | None:
    """Reta de mínimos quadrados totais: (ponto x, ponto y, direção x, direção y)."""
    n = len(pts)
    if n < 2:
        return None
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    return mx, my, math.cos(ang), math.sin(ang)


def _corners(path: list, idx: list[int], closed: bool) -> list:
    """Vértices exatos: interseção das retas ajustadas aos traços de cada lado (os centros dos
    traços nunca caem em cima do vértice, por isso os cantos são reconstruídos)."""
    segs = list(zip(idx, idx[1:]))
    lines = []
    for a, b in segs:
        inner = path[a + 1:b] if b - a > 2 else path[a:b + 1]
        lines.append(_fit_line(inner))

    def cross(l1, l2, fallback):
        if not l1 or not l2:
            return fallback
        x1, y1, dx1, dy1 = l1
        x2, y2, dx2, dy2 = l2
        den = dx1 * dy2 - dy1 * dx2
        if abs(den) < 0.05:              # lados quase paralelos: fica o traço do canto
            return fallback
        t = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / den
        p = (x1 + t * dx1, y1 + t * dy1)
        # um canto reconstruído nunca fica longe do traço de canto
        return p if math.hypot(p[0] - fallback[0], p[1] - fallback[1]) < 0.2 * max(
            1.0, math.hypot(path[idx[0]][0] - path[idx[-1]][0], path[idx[0]][1] - path[idx[-1]][1]),
            max(math.hypot(path[a][0] - path[b][0], path[a][1] - path[b][1]) for a, b in segs)) else fallback

    out = []
    if closed:
        # o encadeamento fecha entre a última e a primeira marca: lado suplementar
        last = _fit_line([path[idx[-1]], path[idx[0]]]) if math.hypot(
            path[idx[-1]][0] - path[idx[0]][0], path[idx[-1]][1] - path[idx[0]][1]) > 1e-6 else None
        ring = lines + ([last] if last else [])
        pts_idx = idx if last else idx[:-1]
        for i, k in enumerate(pts_idx):
            out.append(cross(ring[i - 1], ring[i % len(ring)], path[k]))
        return out
    out.append(path[idx[0]])
    for i in range(1, len(idx) - 1):
        out.append(cross(lines[i - 1], lines[i], path[idx[i]]))
    out.append(path[idx[-1]])
    return out


def red_boundary(pdf_bytes: bytes, page_index: int = 0) -> dict | None:
    """Limite do prédio desenhado a vermelho. Devolve {"points": [[x,y]…] (0–1), "closed": bool,
    "marks": n, "length_mm": comprimento do traçado na folha} ou None se não houver traçado claro.
    `closed` é False quando o traçado sai da folha: o polígono é então fechado em linha reta
    entre as duas pontas e isso tem de ser confirmado pelo utilizador."""
    doc, page = _open(pdf_bytes, page_index)
    try:
        w, h = page.rect.width, page.rect.height
        marks = []
        for g in page.get_drawings():
            if not (_is_red(g.get("color")) or _is_red(g.get("fill"))):
                continue
            r = g["rect"]
            if max(r.width, r.height) <= 0.05 * max(w, h):
                marks.append(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))      # um traço = um caminho
                continue
            # caminho grande: vários traços no mesmo caminho, ou uma linha contínua / tracejada
            sub: list = []               # sub-caminho de linhas em curso (traço desenhado lado a lado)
            for it in g["items"]:
                if it[0] == "l" and g.get("fill") is not None:
                    p1, p2 = it[1], it[2]
                    if not sub or abs(sub[-1][0] - p1.x) + abs(sub[-1][1] - p1.y) > 0.01:
                        sub = [(p1.x, p1.y)]
                    sub.append((p2.x, p2.y))
                    if len(sub) >= 3 and abs(sub[0][0] - p2.x) + abs(sub[0][1] - p2.y) <= 0.01:
                        xs, ys = [q[0] for q in sub], [q[1] for q in sub]
                        if max(max(xs) - min(xs), max(ys) - min(ys)) <= 0.05 * max(w, h):
                            marks.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
                        sub = []
                    continue
                if it[0] == "re":
                    q = it[1]
                    if max(q.width, q.height) <= 0.05 * max(w, h):
                        marks.append(((q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2))
                elif it[0] == "qu":
                    q = it[1].rect
                    if max(q.width, q.height) <= 0.05 * max(w, h):
                        marks.append(((q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2))
                elif it[0] == "l" and g.get("fill") is None:
                    p1, p2 = it[1], it[2]
                    n = max(1, int(math.hypot(p2.x - p1.x, p2.y - p1.y) // 10))
                    marks += [(p1.x + (p2.x - p1.x) * i / n, p1.y + (p2.y - p1.y) * i / n) for i in range(n + 1)]
    finally:
        doc.close()
    if len(marks) < 12:
        return None

    # encadear os traços pelo vizinho mais próximo, a partir de uma ponta
    def chain(start: int) -> tuple[list, float]:
        left = marks[:]
        cur = left.pop(start)
        path, gaps = [cur], []
        while left:
            j = min(range(len(left)), key=lambda k: (left[k][0] - cur[0]) ** 2 + (left[k][1] - cur[1]) ** 2)
            gaps.append(math.hypot(left[j][0] - cur[0], left[j][1] - cur[1]))
            cur = left.pop(j)
            path.append(cur)
        return path, max(gaps)

    # ponta = traço cujo vizinho mais próximo «do outro lado» está mais longe; testa-se as
    # melhores candidatas e fica o encadeamento com o menor salto máximo
    def spread(i):
        d = sorted(math.hypot(marks[i][0] - q[0], marks[i][1] - q[1]) for k, q in enumerate(marks) if k != i)
        return d[1] if len(d) > 1 else 0.0

    ends = sorted(range(len(marks)), key=spread, reverse=True)[:6]
    path, jump = min((chain(i) for i in ends), key=lambda t: t[1])
    step = sorted(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(path, path[1:]))[len(path) // 2]
    if jump > 12 * max(step, 1e-6):
        return None                      # vários traçados vermelhos soltos: leitura não fiável
    length = sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(path, path[1:]))
    closed = math.hypot(path[0][0] - path[-1][0], path[0][1] - path[-1][1]) <= 4 * step
    idx = _simplify(path, 0.6 * step)       # ≈ 3 mm na folha: as pequenas inflexões do limite ficam
    if len(idx) < 3:
        return None
    pts = _corners(path, idx, closed)
    return {"points": [[round(min(max(x / w, 0.0), 1.0), 5), round(min(max(y / h, 0.0), 1.0), 5)] for x, y in pts],
            "closed": closed, "marks": len(marks), "length_mm": round(length * PT_MM, 1)}


def apply_to_site(site: dict, pdf_bytes: bytes, scale_text=None, page_index: int = 0) -> list[str]:
    """Completa o `site` lido pela IA com o que o PDF vetorial dá de forma exata: escala
    (escala escrita × formato real da folha) e limite do prédio (traçado a vermelho).
    Devolve as notas a mostrar ao utilizador. Não altera nada se a imagem não for a folha inteira."""
    notes: list[str] = []
    info = sheet_info(pdf_bytes, page_index)
    try:
        ratio_img = float(site["img_w"]) / float(site["img_h"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return notes
    if abs(ratio_img - info["w_mm"] / info["h_mm"]) > 0.01 * ratio_img:
        return notes
    site["sheet"] = dict(info)
    n = parse_scale(scale_text)
    if n:
        exact = m_per_px(n, info["w_mm"], int(site["img_w"]))
        read = site.get("m_per_px")
        if read and abs(read - exact) > 0.05 * exact:
            notes.append(f"A cota lida na planta dá uma escala diferente da escala escrita (1:{n}): foi usada a "
                         "escala escrita com o formato real da folha — confirme com uma cota conhecida.")
        site["m_per_px"] = exact
        site["sheet"]["scale_n"] = n
        notes.append(f"Escala exata: 1:{n} numa folha de {info['w_mm']:.0f} × {info['h_mm']:.0f} mm.")
    b = red_boundary(pdf_bytes, page_index)
    if b:
        site["parcel"] = b["points"]
        site["sheet"]["boundary"] = "vetor"
        notes.append("Limite do prédio lido diretamente do traçado a vermelho do PDF."
                     + ("" if b["closed"] else " O traçado sai da folha: foi fechado em linha reta — confirme."))
    return notes
