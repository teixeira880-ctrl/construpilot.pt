"""Desenho de controlo (PDF) : uma página por planta (compartimentos coloridos com nome e área, portas) e por alçado (vãos
medidos a vermelho), por cima das linhas do próprio DWFX — para conferir de relance o que foi medido."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

INT, EXT, VAO = (205, 230, 215, 150), (190, 215, 250, 150), (255, 60, 60, 70)


def _fonte(tam):
    for f in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def _pagina(linhas, titulo, desenhar, bbox, px=2400):
    x0, y0, x1, y1 = bbox
    S = min(px / max(x1 - x0, 1e-6), 1600 / max(y1 - y0, 1e-6))
    W, H = int((x1 - x0) * S) + 80, int((y1 - y0) * S) + 110
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im, "RGBA")
    T = lambda p: ((p[0] - x0) * S + 40, (p[1] - y0) * S + 80)
    for pl in linhas:
        dr.line([T(p) for p in pl], fill=(120, 120, 120), width=1)
    desenhar(dr, T, S, _fonte(max(11, int(S * 0.22))))
    dr.text((40, 14), titulo, fill=(0, 0, 0), font=_fonte(26))
    dr.text((40, 48), "Controlo da medição ConstruPilot — o que foi medido, pintado sobre as linhas do próprio desenho", fill=(90, 90, 90), font=_fonte(16))
    return im


def _bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def paginas(modelo: dict, titulo: str = "") -> list:
    """[(título, imagem PIL)] — usadas no PDF de controlo e copiadas para a folha «Controlo» do Excel."""
    pags = []
    for p in modelo["pisos"]:
        pts = [q for pl in p.get("_linhas", []) for q in pl] or [q for c in p["compartimentos"] for q in c["_poly"][0]]
        if not pts:
            continue

        def plan(dr, T, S, fn, p=p):
            for c in p["compartimentos"]:
                pol = c["_poly"][0]
                dr.polygon([T(q) for q in pol], fill=EXT if c["exterior"] else INT, outline=(30, 110, 70))
                cx = sum(q[0] for q in pol) / len(pol); cy = sum(q[1] for q in pol) / len(pol)
                dr.text(T((cx - 1.0, cy - 0.2)), f"{c['nome'][:22]}\n{c['area']:.2f} m²", fill=(0, 0, 0), font=fn)
            for d in p["portas"]:
                r = d["L"] * S / 2
                x, y = T((d["x"], d["y"]))
                dr.ellipse([x - r, y - r, x + r, y + r], outline=(200, 0, 160) if d["tipo"] == "interior" else (0, 90, 220), width=2)
        t = f"{titulo} — Planta : {p['piso']}"
        pags.append((t, _pagina(p.get("_linhas", []), t, plan, _bbox(pts))))
    for v in modelo["alcados"]:
        z = v["zona"]

        def alc(dr, T, S, fn, v=v):
            for b in v.get("_caixas", []):
                dr.rectangle([T(b[:2]), T(b[2:])], fill=VAO, outline=(220, 0, 0), width=2)
                dr.text(T((b[0] + 0.05, b[1] + 0.05)), f"{b[2] - b[0]:.2f}×{b[3] - b[1]:.2f}", fill=(150, 0, 0), font=fn)
        t = f"{titulo} — {v['vista']} : {len(v['vaos'])} vãos"
        pags.append((t, _pagina(v.get("_linhas", []), t, alc, (z[0] - 1, z[1] - 1, z[2] + 1, z[3] + 1))))
    return pags


def gerar_pdf(modelo: dict, caminho: str, titulo: str = "", pags=None) -> str:
    ims = [im for _, im in (pags if pags is not None else paginas(modelo, titulo))] or [Image.new("RGB", (800, 200), "white")]
    ims[0].save(caminho, "PDF", resolution=110, save_all=True, append_images=ims[1:])
    return caminho
