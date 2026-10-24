"""Identidade visual portuguesa dos documentos ConstruPilot.pt (PDF reportlab).

Paleta ConstruPilot (verde floresta e cobre sobre cal), a mesma do site — azulejo desenhado nas cores da marca.
`faixa_azulejo(cv, x, y, w, h)` desenha uma faixa de azulejos de padrão em vetorial (sem imagem), para cabeçalhos e
rodapés; `canto_azulejo` desenha um painel de azulejos esbatido num canto da página. Sem dependências além do reportlab.
"""
from __future__ import annotations

from reportlab.lib import colors

COBALTO = colors.HexColor("#285541")
COBALTO_ESCURO = colors.HexColor("#203b2d")
COBALTO_NOITE = colors.HexColor("#173c32")
CAL = colors.HexColor("#f8f6f0")
TELHA = colors.HexColor("#a8462a")
OCRE = colors.HexColor("#875133")
GRANITO = colors.HexColor("#1f2933")
COBALTO_CLARO = colors.HexColor("#e7efea")   # fundo de cabeçalhos de quadro claros
COBALTO_LINHA = colors.HexColor("#f4f8f7")   # linhas alternadas dos quadros


def _azulejo(cv, x: float, y: float, s: float, cor=COBALTO, fundo=CAL, ocre=OCRE) -> None:
    """Um azulejo de lado s com canto inferior esquerdo em (x, y): rosáceas de canto + flor central de 4 pétalas."""
    cv.saveState()
    p = cv.beginPath(); p.rect(x, y, s, s); cv.clipPath(p, stroke=0, fill=0)
    cv.setFillColor(fundo); cv.rect(x, y, s, s, stroke=0, fill=1)
    k = s / 60.0
    for cx, cy in ((x, y), (x + s, y), (x, y + s), (x + s, y + s)):
        cv.setFillColor(cor); cv.circle(cx, cy, 13 * k, stroke=0, fill=1)
        cv.setFillColor(fundo); cv.circle(cx, cy, 8 * k, stroke=0, fill=1)
        cv.setFillColor(cor); cv.circle(cx, cy, 4 * k, stroke=0, fill=1)
    cv.setStrokeColor(cor); cv.setLineWidth(max(0.35, 1.8 * k))
    for (x0, y0, xc, yc, x1, y1) in ((13, 0, 30, 17, 47, 0), (13, 60, 30, 43, 47, 60), (0, 13, 17, 30, 0, 47), (60, 13, 43, 30, 60, 47)):
        q = cv.beginPath(); q.moveTo(x + x0 * k, y + y0 * k)
        q.curveTo(x + (x0 + 2 * (xc - x0) / 3) * k, y + (y0 + 2 * (yc - y0) / 3) * k,
                  x + (x1 + 2 * (xc - x1) / 3) * k, y + (y1 + 2 * (yc - y1) / 3) * k, x + x1 * k, y + y1 * k)
        cv.drawPath(q, stroke=1, fill=0)
    cx, cy = x + 30 * k, y + 30 * k
    cv.setFillColor(cor)
    for ang in (0, 90, 180, 270):
        cv.saveState(); cv.translate(cx, cy); cv.rotate(ang)
        cv.ellipse(-5.0 * k, 2.6 * k, 5.0 * k, 21.4 * k, stroke=0, fill=1)
        cv.restoreState()
    cv.setFillColor(fundo); cv.circle(cx, cy, 5 * k, stroke=0, fill=1)
    cv.setFillColor(ocre); cv.circle(cx, cy, 2.6 * k, stroke=0, fill=1)
    cv.restoreState()


def faixa_azulejo(cv, x: float, y: float, w: float, h: float, cor=COBALTO) -> None:
    """Faixa horizontal de azulejos quadrados de lado h, de x a x+w (o último azulejo é cortado)."""
    cv.saveState()
    p = cv.beginPath(); p.rect(x, y, w, h); cv.clipPath(p, stroke=0, fill=0)
    n = int(w // h) + 1
    for i in range(n):
        _azulejo(cv, x + i * h, y, h, cor)
    cv.setStrokeColor(cor); cv.setLineWidth(0.3)
    cv.line(x, y, x + w, y); cv.line(x, y + h, x + w, y + h)
    cv.restoreState()


def _claro(c, k: float):
    """Mistura a cor c com branco (k = 0 → c, 1 → branco)."""
    return colors.Color(c.red + (1 - c.red) * k, c.green + (1 - c.green) * k, c.blue + (1 - c.blue) * k)


def canto_azulejo(cv, x: float, y: float, w: float, h: float, s: float = 18, intensidade: float = 0.12) -> None:
    """Painel de azulejos esbatido (cores misturadas com branco, sem transparência) — marca d'água discreta."""
    k = 1 - intensidade
    cor, ocre = _claro(COBALTO, k), _claro(OCRE, k)
    cv.saveState()
    p = cv.beginPath(); p.rect(x, y, w, h); cv.clipPath(p, stroke=0, fill=0)
    for i in range(int(w // s) + 1):
        for j in range(int(h // s) + 1):
            _azulejo(cv, x + i * s, y + j * s, s, cor, colors.white, ocre)
    cv.restoreState()


__all__ = ["COBALTO", "COBALTO_ESCURO", "COBALTO_NOITE", "CAL", "TELHA", "OCRE", "GRANITO", "COBALTO_CLARO", "COBALTO_LINHA",
           "faixa_azulejo", "canto_azulejo"]
