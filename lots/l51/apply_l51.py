"""Lot 51 — corrections trouvées aux tests réels en production (03/11).

1. Analyse IA d'un plan (« Analyser ») : l'appel était synchrone ; sur un vrai plan il dépasse
   100 s et la passerelle renvoie 524 → « Analyse IA impossible ». Désormais : tâche de fond
   (?background=1) + suivi par /takeoffs/cotes-jobs/{id}, comme les études de cotes.
2. Estimation : surface négative, nulle ou absurde acceptée (total négatif), type de projet ou
   finition inconnus remplacés en silence → refus clair (422).
3. Calculateurs : longueur / largeur / hauteur à 0 acceptées (surfaces fausses) → refus clair.

Usage : python3 lots/l51/apply_l51.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
B = root / "backend"
F = root / "frontend" / "src"

M = {
 "fr": {"surface": "Surface invalide : indiquez une surface supérieure à 0 et au plus 100 000 m².",
        "type": "Type de projet inconnu", "finish": "Niveau de finition inconnu",
        "ceiling": "Hauteur sous plafond invalide (entre 1,80 m et 15 m)"},
 "pt": {"surface": "Área inválida: indique uma área superior a 0 e no máximo 100 000 m².",
        "type": "Tipo de projeto desconhecido", "finish": "Nível de acabamento desconhecido",
        "ceiling": "Pé-direito inválido (entre 1,80 m e 15 m)"},
}[site]

EDITS = {
 B / "routes" / "plans_analysis.py": [
  ('@router.post("/{plan_id}/analyze")\nasync def analyze_plan(plan_id: str, page_index: int = 0, user=Depends(current_user)):\n',
   '@router.post("/{plan_id}/analyze")\n'
   'async def analyze_plan(plan_id: str, page_index: int = 0, background: bool = Query(False), user=Depends(current_user)):\n'
   '    """Lot 51 : ?background=1 → tâche de fond suivie sur /takeoffs/cotes-jobs/{job_id} (évite le 524 > 100 s)."""\n'
   '    if background:\n'
   '        import inspect\n'
   '        from routes.plans_cotes import _start_job\n'
   '        exists = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "plan_id": 1})\n'
   '        if not exists:\n'
   '            raise HTTPException(404, "Plan introuvable")\n'
   '        job = _start_job(lambda: _analyze_plan_now(plan_id, page_index, user), user["user_id"])\n'
   '        return (await job) if inspect.isawaitable(job) else job\n'
   '    return await _analyze_plan_now(plan_id, page_index, user)\n'
   '\n\n'
   'async def _analyze_plan_now(plan_id: str, page_index: int, user):\n', 1),
 ],
 B / "routes" / "estimation_routes.py": [
  ('@router.post("/compute")\n',
   'def _validate_estimate_in(body):\n'
   '    """Lot 51 : refuse les entrées absurdes au lieu de calculer un total faux."""\n'
   '    import math\n'
   '    from engines.catalog import FINISH_BY_KEY, PROJECT_TYPES_BY_KEY\n'
   '    s = body.surface\n'
   '    if s is None or not math.isfinite(s) or s <= 0 or s > 100000:\n'
   f'        raise HTTPException(422, {M["surface"]!r})\n'
   '    if body.project_type not in PROJECT_TYPES_BY_KEY:\n'
   f'        raise HTTPException(422, {M["type"]!r})\n'
   '    if body.finish_level not in FINISH_BY_KEY:\n'
   f'        raise HTTPException(422, {M["finish"]!r})\n'
   '    h = body.ceiling_height_m\n'
   '    if h is not None and (not math.isfinite(h) or h < 1.8 or h > 15):\n'
   f'        raise HTTPException(422, {M["ceiling"]!r})\n'
   '\n\n'
   '@router.post("/compute")\n', 1),
  ('async def compute(body: EstimateIn, user=Depends(optional_user)):\n',
   'async def compute(body: EstimateIn, user=Depends(optional_user)):\n    _validate_estimate_in(body)\n', 1),
 ],
 B / "engines" / "calculator_validation.py": [
  ('positive = {"tile_length", "tile_width", "tiles_per_box", "plate_length", "plate_width", "coats"}',
   'positive = {"tile_length", "tile_width", "tiles_per_box", "plate_length", "plate_width", "coats",\n'
   '                "length", "width", "height"}  # Lot 51 : une dimension nulle fausse le calcul', 1),
 ],
 F / "lib" / "cotesJobs.js": [
  ('export async function pollCotesJob(',
   '// Lot 51 : analyse IA d\'une page de plan en tâche de fond (plus de 524 sur les gros plans).\n'
   'export async function runPlanAnalysis(planId, pageIndex) {\n'
   '  const { data } = await api.post(`/takeoffs/${planId}/analyze?page_index=${pageIndex}&background=1`);\n'
   '  if (!data || !data.job_id) return { data };\n'
   '  return { data: await pollCotesJob(data.job_id, { timeoutMs: 330000 }) };\n'
   '}\n\n'
   'export async function pollCotesJob(', 1),
 ],
 F / "pages" / "PlanTakeoff.jsx": [
  ('await api.post(`/takeoffs/${plan.plan_id}/analyze?page_index=${pageIndex}`)',
   'await runPlanAnalysis(plan.plan_id, pageIndex)', 2),
  ('import { api, ', 'import { runPlanAnalysis } from "@/lib/cotesJobs";\nimport { api, ', 1),
 ],
}

MARKS = {B / "routes" / "plans_analysis.py": "_analyze_plan_now", B / "routes" / "estimation_routes.py": "_validate_estimate_in",
         B / "engines" / "calculator_validation.py": "Lot 51", F / "lib" / "cotesJobs.js": "runPlanAnalysis",
         F / "pages" / "PlanTakeoff.jsx": "runPlanAnalysis"}

out = {}
for f, edits in EDITS.items():
    if not f.exists():
        print(f"FICHIER ABSENT : {f} — ARRÊT, rien écrit")
        sys.exit(1)
    s = f.read_text(encoding="utf-8")
    if MARKS[f] in s:
        print(f"déjà appliqué : {f.relative_to(root)}")
        continue
    for old, new, n in edits:
        c = s.count(old)
        if c != n:
            print(f"ANCRE introuvable ({c}/{n}) dans {f.relative_to(root)} : {old[:70]!r} — ARRÊT, rien écrit")
            sys.exit(1)
        s = s.replace(old, new)
    out[f] = s
for f, s in out.items():
    f.write_text(s, encoding="utf-8")
    print(f"ok {f.relative_to(root)}")
t = pathlib.Path(__file__).resolve().parent / "tests" / "test_l51.py"
(B / "tests" / "test_l51.py").write_bytes(t.read_bytes())
print("ok backend/tests/test_l51.py")
print(f"L51 {site.upper()} OK")
