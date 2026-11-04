"""Lot 73 — type de vue : « ÉLÉVATION NORD/SUD… » et « FAÇADE PRINCIPALE/ARRIÈRE… » reconnues comme façades.

Constat (dossier de permis réel Gourlay, pages 8-9) : les élévations titrées « ELEVATION NORD »,
« ELEVATION OUEST » étaient classées « inconnu » → l'analyse intérieure (pièces/murs) restait active sur une
façade. Correctif (engines/plan_page_context.py, FR + PT) : titres ÉLÉVATION + orientation, FAÇADE +
PRINCIPALE/ARRIÈRE/LATÉRALE/AVANT/SUR RUE/SUR JARDIN, et PT ALÇADO FRONTAL/TARDOZ.
Usage : python3 lots/l73/apply_l73.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "plan_page_context.py"
s = f.read_text(encoding="utf-8")
if "Lot 73" in s:
    print("déjà appliqué"); print("L73 OK"); sys.exit(0)
A = ('    elevation = bool(re.search(r"^\\s*(?:FA[ÇC]ADES?\\s+(?:BAT|NORD|SUD|EST|OUEST)|AL[ÇC]ADOS?\\s+(?:NORTE|SUL|NASCENTE|POENTE|ESTE|OESTE|PRINCIPAL|POSTERIOR|LATERAL))", text, re.I | re.M))\n')
if s.count(A) != 1:
    print("ANCRE elevation introuvable dans plan_page_context.py — ARRÊT, rien écrit"); sys.exit(1)
B = ('    # Lot 73 : « ÉLÉVATION NORD », « FAÇADE PRINCIPALE », « ALÇADO FRONTAL » sont des façades\n'
     '    elevation = bool(re.search(r"^\\s*(?:FA[ÇC]ADES?\\s+(?:BAT|NORD|SUD|EST|OUEST|PRINCIPALE|ARRI[ÈE]RE|LAT[ÉE]RALE|AVANT|SUR\\s+(?:RUE|JARDIN|COUR))'
     '|[ÉE]L[ÉE]VATIONS?\\s+(?:NORD|SUD|EST|OUEST|PRINCIPALE|ARRI[ÈE]RE|LAT[ÉE]RALE|AVANT|[A-Z][\'’]?\\s*$)'
     '|AL[ÇC]ADOS?\\s+(?:NORTE|SUL|NASCENTE|POENTE|ESTE|OESTE|PRINCIPAL|POSTERIOR|LATERAL|FRONTAL|TARDOZ))", text, re.I | re.M))\n')
f.write_text(s.replace(A, B), encoding="utf-8")
(root / "backend" / "tests" / "test_l73.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l73.py").read_bytes())
print("ok backend/engines/plan_page_context.py + backend/tests/test_l73.py")
print("L73 OK")
