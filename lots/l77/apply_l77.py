"""Lot 77 — type de vue « plan de niveau » : « PLAN DE R+1 », « PLAN DU 1er ETAGE », « PLAN DU REZ-DE-CHAUSSÉE ».

Constat (dossier PC réel « PLAN 20260314 plans PC v3 », 25 pages) : les plans d'étage titrés « PLAN DU 1er ETAGE »
/ « PLAN DE R+1 » étaient classés « inconnu » alors que « PLAN DE RDC » était reconnu. Correctif
(engines/plan_page_context.py, FR + PT) : titres PLAN DE/DU + R±n, REZ-DE-CHAUSSÉE, (1er) ÉTAGE, SOUS-SOL,
COMBLES, NIVEAU n. PLAN DE MASSE / SITUATION / TOITURE restent hors plans de niveau.
Usage : python3 lots/l77/apply_l77.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "plan_page_context.py"
s = f.read_text(encoding="utf-8")
if "Lot 77" in s:
    print("déjà appliqué"); print("L77 OK"); sys.exit(0)
A = 'PLAN\\s+(?:R[+\\-\\d ]|RDC|DE\\s+RDC|DU\\s+(?:RDC|SOUS-SOL))|PLANTA'
if s.count(A) != 1:
    print("ANCRE floor introuvable dans plan_page_context.py — ARRÊT, rien écrit"); sys.exit(1)
B = ('PLAN\\s+(?:R[+\\-\\d ]|RDC|DE\\s+(?:RDC|R\\s*[+\\-]\\s*\\d|REZ|L[\'’]?\\s*[EÉ]TAGE|SOUS-SOL|COMBLES?)'
     '|DU\\s+(?:RDC|SOUS-SOL|REZ|\\d+\\s*(?:ER|E|EME|ÈME)?\\s*[EÉ]TAGE|[EÉ]TAGE|NIVEAU|COMBLES?)'
     '|DES\\s+COMBLES|[EÉ]TAGE|NIVEAU\\s+[-+]?\\d|SOUS-SOL|REZ)|PLANTA')
s = s.replace(A, B)
s = s.replace("  # Lot 56 : PT\n", "  # Lot 56 : PT ; Lot 77 : PLAN DE R+1 / DU 1er ETAGE\n", 1)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l77.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l77.py").read_bytes())
print("ok backend/engines/plan_page_context.py + backend/tests/test_l77.py")
print("L77 OK")
