"""Lot 85 (FR + PT) — une importation de plan interrompue restait « en cours » pour toujours.

Constat (production .pt, 04/11) : après la chute du serveur sur un plan A0 (corrigée par le Lot 84), la tâche
pjob_… est restée « processing » sans fin, et une 2e importation (Gourlay, A4 11 p., 5 s en local) est elle aussi
restée bloquée. Le traitement tourne dans le processus web : si celui-ci redémarre, personne ne clôt la tâche.
Correctif : GET /takeoffs/upload-jobs/{id} clôt en « error » (message clair, 503) une tâche « processing » sans
nouvelle depuis 10 min ; l'écran d'import affiche alors l'erreur au lieu de tourner indéfiniment.
Usage : python3 lots/l85/apply_l85.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
lang = (sys.argv[2] if len(sys.argv) > 2 else "fr").lower()
msg = ("Importação interrompida no servidor — volte a enviar o ficheiro." if lang == "pt"
       else "Import interrompu côté serveur — renvoyez le fichier.")
f = root / "backend" / "routes" / "plans_crud.py"
s = f.read_text(encoding="utf-8")
if "Lot 85" in s:
    print("déjà appliqué"); print(f"L85 {lang.upper()} OK"); sys.exit(0)
A = '    if j["status"] == "done" and j.get("kind") is None:\n'
if s.count(A) != 1:
    print("ANCRE upload_job introuvable — ARRÊT, rien écrit"); sys.exit(1)
B = ('    # Lot 85 : tâche orpheline (processus redémarré pendant le traitement) → close en erreur après 10 min sans nouvelle\n'
     '    if j.get("status") == "processing" and _stale85(j):\n'
     f'        j.update({{"status": "error", "status_code": 503, "detail": {msg!r}}})\n'
     '        await db.plan_upload_jobs.update_one({"job_id": job_id, "status": "processing"},\n'
     '                                             {"$set": {"status": "error", "status_code": 503, "detail": j["detail"], "updated_at": _now()}})\n'
     + A)
s = s.replace(A, B)
H = '@router.get("/upload-jobs/{job_id}")\n'
if s.count(H) != 1:
    print("ANCRE route upload-jobs introuvable — ARRÊT, rien écrit"); sys.exit(1)
s = s.replace(H, ('def _stale85(j: dict, minutes: int = 10) -> bool:\n'
                  '    """Lot 85 : vrai si la tâche n\'a pas bougé depuis `minutes` (dernier updated_at, sinon created_at)."""\n'
                  '    from datetime import datetime, timezone\n'
                  '    ts = j.get("updated_at") or j.get("created_at")\n'
                  '    try:\n'
                  '        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))\n'
                  '    except (TypeError, ValueError):\n'
                  '        return False\n'
                  '    if t.tzinfo is None:\n'
                  '        t = t.replace(tzinfo=timezone.utc)\n'
                  '    return (datetime.now(timezone.utc) - t).total_seconds() > minutes * 60\n\n\n' + H))
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l85.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l85.py").read_bytes())
print("ok backend/routes/plans_crud.py + backend/tests/test_l85.py")
print(f"L85 {lang.upper()} OK")
