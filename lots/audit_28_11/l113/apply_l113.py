"""Lot 113 (FR + PT) — audit de nuit du 28/11/2026, suite 4.

 1. Plans d'exécution Élec & Plomberie : les « pièces » parasites déjà enregistrées (vide entre deux traits de
    mur, lettres des textes — cf. lot 109) recevaient chacune des prises, points lumineux et circuits, d'où un
    plan illisible et un quantitatif faux. Le moteur ignore désormais les contours de moins de 0,5 m² ou de
    largeur moyenne < 30 cm (aucune vraie pièce n'est concernée).
 2. Rénovation énergétique : statut affiché en clair (« collecte » → « Collecte des données »…).

Usage : python3 lots/l113/apply_l113.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-5)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2] if len(sys.argv) > 2 else "fr"
assert site in ("fr", "pt")
MARK = "CP-AUDIT-NUIT-5"
report = []


def replace(name, rel, old, new):
    p = root / rel
    if not p.exists():
        return report.append(f"ABSENT    {name}")
    txt = p.read_text(encoding="utf-8")
    if MARK in txt and new in txt:
        return report.append(f"DÉJÀ      {name}")
    if txt.count(old) != 1:
        return report.append(("IGNORÉ    " if old not in txt else "AMBIGU    ") + name)
    p.write_text(txt.replace(old, new), encoding="utf-8")
    report.append(f"OK        {name}")


replace("1 MEP : contours parasites ignorés", "backend/engines/mep/adapter.py",
        """            rooms.append({"id": r.get("room_id") or f"p{page}-r{len(rooms) + 1}", "name": r.get("name") or "Pièce",
                          "polygon": [[float(x) / ppm, float(y) / ppm] for x, y in r["points"]]})""",
        f"""            poly = [[float(x) / ppm, float(y) / ppm] for x, y in r["points"]]
            # {MARK} : un contour de moins de 0,5 m² ou de largeur moyenne < 30 cm n'est pas une pièce
            area = abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                           for i in range(len(poly)))) / 2
            perim = sum(((poly[i][0] - poly[(i + 1) % len(poly)][0]) ** 2 + (poly[i][1] - poly[(i + 1) % len(poly)][1]) ** 2) ** 0.5
                        for i in range(len(poly)))
            if area < 0.5 or (perim and 2 * area / perim < 0.3):
                continue
            rooms.append({{"id": r.get("room_id") or f"p{{page}}-r{{len(rooms) + 1}}", "name": r.get("name") or "Pièce",
                          "polygon": poly}})""")

if site == "fr":
    replace("2 Rénovation : statut en clair", "frontend/src/pages/Renovation.jsx",
            "Statut : {p.status} · maj",
            "Statut : {({ collecte: \"Collecte des données\", analyse: \"Analyse\", scenarios: \"Scénarios prêts\", "
            "non_calcule: \"Non calculé\", moteur_non_configure: \"Moteur 3CL non connecté\" })[p.status] || p.status} · maj")
else:
    report.append("N/A       2 Rénovation (site .pt)")

print(f"Lot 113 ({site}) — {MARK}")
print("\n".join(report))
sys.exit(1 if any(r.startswith("AMBIGU") for r in report) else 0)
