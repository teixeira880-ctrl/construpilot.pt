"""Lot 82 — étude de permis (PC) : la synthèse IA d'un dossier de 11 pages échouait (« Étude non aboutie »).

Constat (production construpilot.fr, 04/11, dossier réel « Dossier_Complet_Permis_Construct_Gourlay », 11 pages) :
les 11 pages sont lues (≈ 4 min) puis l'étape « Consolidation des ouvrages » est coupée par un délai fixe de
180 s → asyncio.TimeoutError → message générique « Étude non aboutie », et tout le travail IA est perdu.
Correctif (engines/study_dossier_ai.py + study_dossier_jobs.py, FR + PT) : délai de synthèse adapté au dossier
(240 s + 20 s par page lue, plafonné à 600 s, toujours sous la surveillance du bail du job) ; en cas de dépassement,
message clair « synthèse trop longue, relancez ou scindez le dossier » au lieu du message générique.
Usage : python3 lots/l82/apply_l82.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
fa = root / "backend" / "engines" / "study_dossier_ai.py"
fj = root / "backend" / "engines" / "study_dossier_jobs.py"
a, j = fa.read_text(encoding="utf-8"), fj.read_text(encoding="utf-8")
if "Lot 82" in a and "Lot 82" in j:
    print("déjà appliqué"); print(f"L82 {site.upper()} OK"); sys.exit(0)
A1 = '"\\nLectures : " + payload), timeout=180)\n'
if a.count(A1) != 1:
    print("ANCRE synthèse timeout=180 introuvable — ARRÊT, rien écrit"); sys.exit(1)
a = a.replace(A1, '"\\nLectures : " + payload), timeout=min(600, 240 + 20 * len(analyses)))  # Lot 82 : délai adapté au dossier\n')
MSG = {"fr": "La synthèse IA du dossier a dépassé le délai ; relancez l’étude ou scindez le dossier par bâtiment / lot. Vos pièces et l’ancienne étude sont conservées.",
       "pt": "A síntese IA do processo excedeu o tempo limite; relance o estudo ou divida o processo por edifício / lote. As suas peças e o estudo anterior são conservados."}[site]
A2 = "                msg = str(exc.detail) if isinstance(exc, HTTPException) else str(exc) if isinstance(exc, StudyError) else "
if j.count(A2) != 1:
    print("ANCRE message d'échec introuvable dans study_dossier_jobs.py — ARRÊT, rien écrit"); sys.exit(1)
j = j.replace(A2, f"                msg = {MSG!r} if isinstance(exc, asyncio.TimeoutError) else str(exc.detail) if isinstance(exc, HTTPException) else str(exc) if isinstance(exc, StudyError) else ", 1)
j = j.replace('                log.warning("PC job failed: %s", type(exc).__name__)\n',
              '                log.warning("PC job failed: %s", type(exc).__name__)  # Lot 82 : TimeoutError → message clair\n', 1)
if "Lot 82" not in j:
    print("ANCRE log PC job failed introuvable — ARRÊT, rien écrit"); sys.exit(1)
if not re.search(r"^import asyncio", j, re.M):
    print("asyncio non importé dans study_dossier_jobs.py — ARRÊT, rien écrit"); sys.exit(1)
fa.write_text(a, encoding="utf-8")
fj.write_text(j, encoding="utf-8")
(root / "backend" / "tests" / "test_l82.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l82.py").read_bytes())
print("ok backend/engines/study_dossier_ai.py + study_dossier_jobs.py + backend/tests/test_l82.py")
print(f"L82 {site.upper()} OK")
