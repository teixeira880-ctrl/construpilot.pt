"""Escala dos desenhos (23/11/2026): cortes/alçados desenhados RELATIVOS ao pavimento.
Com cotas NGF absolutas (dossier de Amarante, ~304 m) a altura do quadro era 300+ m → escala 1:1000,
desenho de 2 cm numa folha A3. Tudo-ou-nada; âncoras verbatim; idempotente."""
import sys

P = "backend/engines/bet_geo/drawings.py"
s = open(P, encoding="utf-8").read()
if "desenhar relativo ao pavimento" in s:
    print("já aplicado", P); sys.exit(0)
REPS = [
 [
  "    H = b.roof_level + 1.5\n    wa, wb = x1 - x0, y1 - y0",
  "    H = (b.roof_level - b.floor_level) + 1.5      # altura RELATIVA: as cotas do projeto podem ser NGF absolutas\n    wa, wb = x1 - x0, y1 - y0"
 ],
 [
  "    fl, top = b.floor_level, b.roof_level\n    par = 0.5",
  "    fl, top = b.floor_level, b.roof_level\n    zref = fl                                   # desenhar relativo ao pavimento (cotas NGF absolutas → folha à escala)\n    par = 0.5"
 ],
 [
  "    def P(s, z):\n        return (ox + s - s_min, oz + z)",
  "    def P(s, z):\n        return (ox + s - s_min, oz + z - zref)"
 ],
 [
  "        f.line([(xl - 0.6, oz + z), (P(s_max + 0.6, 0)[0], oz + z)], GREY, 0.2, dash=[1, 2])\n        f.text(xl - 0.7, oz + z + 0.06, lab.replace(\".\", \",\"), 5.4, INK, align=\"r\")",
  "        f.line([(xl - 0.6, oz + z - zref), (P(s_max + 0.6, 0)[0], oz + z - zref)], GREY, 0.2, dash=[1, 2])\n        f.text(xl - 0.7, oz + z - zref + 0.06, lab.replace(\".\", \",\"), 5.4, INK, align=\"r\")"
 ],
 [
  "    f.dim((P(s_max, 0)[0] + 1.0, oz + fl), (P(s_max, 0)[0] + 1.0, oz + top), 0.0, _n(top - fl))\n    f.text(ox + (s_max - s_min) / 2, oz + top + par + 0.8, title, 8.5, INK, True)",
  "    f.dim((P(s_max, 0)[0] + 1.0, oz + fl - zref), (P(s_max, 0)[0] + 1.0, oz + top - zref), 0.0, _n(top - fl))\n    f.text(ox + (s_max - s_min) / 2, oz + top - zref + par + 0.8, title, 8.5, INK, True)"
 ],
 [
  "    w = max(x1 - x0, y1 - y0)\n    H = b.roof_level + 1.2",
  "    w = max(x1 - x0, y1 - y0)\n    zref = b.floor_level                         # desenhar relativo ao pavimento (cotas NGF absolutas → folha à escala)\n    H = (b.roof_level - b.floor_level) + 1.2"
 ],
 [
  "                g = Polygon([(p[0] - mnx, p[1] + oz) for p in pr])",
  "                g = Polygon([(p[0] - mnx, p[1] - zref + oz) for p in pr])"
 ],
 [
  "            f.line([(-0.8, oz + b.floor_level - 0.2), (mxx + 0.8, oz + b.floor_level - 0.2)], BROWN, 0.8)",
  "            f.line([(-0.8, oz - 0.2), (mxx + 0.8, oz - 0.2)], BROWN, 0.8)"
 ],
 [
  "                f.text(mxx + 1.0, oz + z, lab, 5.6, INK, align=\"l\")\n                f.line([(mxx + 0.2, oz + z), (mxx + 0.9, oz + z)], INK, 0.3)",
  "                f.text(mxx + 1.0, oz + z - zref, lab, 5.6, INK, align=\"l\")\n                f.line([(mxx + 0.2, oz + z - zref), (mxx + 0.9, oz + z - zref)], INK, 0.3)"
 ],
 [
  "                f.dim((g0 - 0.1, z0 + oz - b.floor_level * 0), (g0 - 0.1, z1 + oz), 0.4, _n(z1 - z0), size=5.0, color=BLUE)",
  "                f.dim((g0 - 0.1, z0 - zref + oz), (g0 - 0.1, z1 - zref + oz), 0.4, _n(z1 - z0), size=5.0, color=BLUE)"
 ]
]
for a, b in REPS:
    n = s.count(a)
    if n != 1:
        print(f"ERRO {P}: âncora encontrada {n}× (esperado 1):")
        print("   " + a.splitlines()[0][:120])
        sys.exit(1)
for a, b in REPS:
    s = s.replace(a, b, 1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P, "— 10 substituições")
