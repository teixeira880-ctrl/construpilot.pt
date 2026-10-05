"""Desenhos SVG inline (planta + elevação) — sem matplotlib para payload leve."""
from __future__ import annotations


def plan_view_svg(num_degraus: int, g_cm: float, largura_m: float) -> str:
    """Vista em planta: retângulos sequenciais representando cada cobertor."""
    width_px = 400
    height_px = int(largura_m * 100) + 40
    scale = (width_px - 40) / (num_degraus * g_cm)
    rect_h = min(height_px - 40, 60)

    rects = []
    for i in range(num_degraus):
        x = 20 + i * g_cm * scale
        w = g_cm * scale - 1
        rects.append(
            f'<rect x="{x:.1f}" y="20" width="{w:.1f}" height="{rect_h}" '
            f'fill="#e2e8f0" stroke="#0f766e" stroke-width="1" />'
            f'<text x="{x + w/2:.1f}" y="{20 + rect_h/2 + 4}" '
            f'text-anchor="middle" font-size="10" font-family="monospace" fill="#334155">{i+1}</text>'
        )
    # Cota de largura
    cota_y = 20 + rect_h + 15
    rects.append(
        f'<line x1="20" y1="{cota_y}" x2="{20 + num_degraus * g_cm * scale:.1f}" y2="{cota_y}" '
        f'stroke="#64748b" stroke-width="1" stroke-dasharray="3,2" />'
    )
    rects.append(
        f'<text x="{(20 + num_degraus * g_cm * scale/2):.1f}" y="{cota_y + 14}" '
        f'text-anchor="middle" font-size="11" fill="#64748b">'
        f'{num_degraus} × {g_cm:.1f} cm = {num_degraus * g_cm:.0f} cm</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} {cota_y + 25}" '
        f'width="100%" style="max-width:{width_px}px">'
        f'<text x="10" y="14" font-size="11" font-weight="bold" fill="#0f766e">Vista em planta</text>'
        f'{"".join(rects)}'
        f'</svg>'
    )


def elevation_svg(num_degraus: int, h_cm: float, g_cm: float) -> str:
    """Vista de elevação: perfil em escada."""
    width_px = 480
    scale_x = min(2.0, (width_px - 60) / max(num_degraus * g_cm, 1))
    scale_y = min(scale_x, 160 / max(num_degraus * h_cm, 1))
    scale = min(scale_x, scale_y) if scale_y > 0 else scale_x
    stair_w = num_degraus * g_cm * scale
    stair_h = num_degraus * h_cm * scale

    # Caminho em escada (do canto superior direito até ao inferior esquerdo)
    pts = [(30, 180)]
    for i in range(num_degraus):
        x = 30 + i * g_cm * scale
        y = 180 - i * h_cm * scale
        pts.append((x, y))
        pts.append((x + g_cm * scale, y))
    pts.append((30 + stair_w, 180))
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    # Linha inclinada "tangente" (visualiza o ângulo)
    tangent = (
        f'<line x1="30" y1="180" x2="{30 + stair_w:.1f}" y2="{180 - stair_h:.1f}" '
        f'stroke="#f59e0b" stroke-width="1" stroke-dasharray="3,3" />'
    )
    # Cotas
    cota_v = (
        f'<line x1="{30 + stair_w + 5:.1f}" y1="180" x2="{30 + stair_w + 5:.1f}" '
        f'y2="{180 - stair_h:.1f}" stroke="#64748b" stroke-dasharray="2,2" />'
        f'<text x="{30 + stair_w + 10:.1f}" y="{180 - stair_h/2:.1f}" font-size="11" fill="#64748b">'
        f'{num_degraus * h_cm:.0f} cm</text>'
    )
    cota_h = (
        f'<line x1="30" y1="195" x2="{30 + stair_w:.1f}" y2="195" '
        f'stroke="#64748b" stroke-dasharray="2,2" />'
        f'<text x="{30 + stair_w/2:.1f}" y="208" text-anchor="middle" font-size="11" fill="#64748b">'
        f'{num_degraus * g_cm:.0f} cm · {num_degraus * h_cm / (num_degraus * g_cm) * 100 / 1.74:.0f}°</text>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} 230" '
        f'width="100%" style="max-width:{width_px}px">'
        f'<text x="10" y="14" font-size="11" font-weight="bold" fill="#0f766e">Vista em elevação</text>'
        f'<polyline points="{path}" fill="#e6f7f3" stroke="#0f766e" stroke-width="1.5" />'
        f'{tangent}{cota_v}{cota_h}'
        f'</svg>'
    )


def build_svgs(num_degraus: int, h_cm: float, g_cm: float, largura_m: float) -> dict:
    return {
        "plan_svg": plan_view_svg(num_degraus, g_cm, largura_m),
        "elevation_svg": elevation_svg(num_degraus, h_cm, g_cm),
    }
