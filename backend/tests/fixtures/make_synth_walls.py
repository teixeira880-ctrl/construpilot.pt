"""Plan synthétique 1/50 : murs à deux faces + chaînes nu/nu, axes, épaisseurs, totaux, sections « 50x30 »."""
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

PPM = 1000 / 50 * 72 / 25.4  # points par mètre à 1/50
OX, OY = 120, 120            # origine (coin bas-gauche du bâtiment) en points

# rangée horizontale : 0.20 | 4.00 | 0.20 | 3.60 | 0.20 | 3.60 | 0.20  = 12.00
XS = [0.0, 0.20, 4.20, 4.40, 8.00, 8.20, 11.80, 12.00]
# colonne verticale : 0.20 | 3.00 | 0.20 | 4.40 | 0.20 = 8.00
YS = [0.0, 0.20, 3.20, 3.40, 7.80, 8.00]


def P(xm, ym):
    return OX + xm * PPM, OY + ym * PPM


def wall_v(c, x1, x2, y1, y2):
    for x in (x1, x2):
        c.line(*P(x, y1), *P(x, y2))


def wall_h(c, y1, y2, x1, x2):
    for y in (y1, y2):
        c.line(*P(x1, y), *P(x2, y))


def cote_h(c, xa, xb, y, text=None):
    (x1, yy), (x2, _) = P(xa, y), P(xb, y)
    c.line(x1, yy, x2, yy)
    c.line(x1, yy - 5, x1, yy + 5)
    c.line(x2, yy - 5, x2, yy + 5)
    c.setFont("Helvetica", 7)
    c.drawCentredString((x1 + x2) / 2, yy + 3, text or f"{xb - xa:.2f}")


def cote_v(c, ya, yb, x, text=None):
    (xx, y1), (_, y2) = P(x, ya), P(x, yb)
    c.line(xx, y1, xx, y2)
    c.line(xx - 5, y1, xx + 5, y1)
    c.line(xx - 5, y2, xx + 5, y2)
    c.saveState()
    c.translate(xx - 3, (y1 + y2) / 2)
    c.rotate(90)
    c.setFont("Helvetica", 7)
    c.drawCentredString(0, 0, text or f"{yb - ya:.2f}")
    c.restoreState()


def build(path: str) -> None:
    c = canvas.Canvas(path, pagesize=landscape(A3))
    c.setLineWidth(0.6)
    # murs verticaux (faces à XS[2k], XS[2k+1])
    for k in range(4):
        wall_v(c, XS[2 * k], XS[2 * k + 1], 0.0, 8.0)
    # murs horizontaux
    for k in range(3):
        wall_h(c, YS[2 * k], YS[2 * k + 1], 0.0, 12.0)
    c.setLineWidth(0.3)
    # chaîne nu/nu haute
    for a, b in zip(XS, XS[1:]):
        cote_h(c, a, b, 8.6)
    cote_h(c, 0.0, 12.0, 9.2)  # total extérieur
    cote_h(c, 0.10, 4.30, 9.8)  # axe → axe (mur ext. gauche → refend 1) = 4.20
    # chaîne verticale gauche
    for a, b in zip(YS, YS[1:]):
        cote_v(c, a, b, -0.6)
    cote_v(c, 0.0, 8.0, -1.2)
    # sections (ne sont pas des cotes)
    c.setFont("Helvetica", 6)
    c.drawString(*P(2.0, 3.28), "50x30")
    c.drawString(*P(6.0, 7.88), "60x30")
    c.setFont("Helvetica", 9)
    c.drawString(60, 60, "Echelle 1/50 — plan synthétique murs")
    c.save()


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else "synth_walls_1_50.pdf")
