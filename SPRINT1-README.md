# ConstruPilot — Sprint 1 : Solveur BTP + Analyse de plan Pro

Deux nouveaux modules backend + deux pages React.

## Nouveaux modules backend

### `backend/btp_solver/` — Résolution de problèmes BTP

Cascade IA : **Perplexity Sonar** (recherche + citations Légifrance / CSTB / AFNOR) → **Claude Sonnet 4.6** (structuration JSON) → **GPT‑5.6 Terra** (fallback).

Réponse JSON complète avec :
- diagnostic + causes probables (confiance)
- solutions chiffrées (coût min/max, durée, risque, garantie, étapes)
- références normatives (DTU, NF, code de la construction)
- 4 graphiques provisionnels (comparatif coût, comparatif durée, radar risque/complexité, camembert causes)
- niveau d'urgence auto‑détecté

**Endpoints**
| Méthode | Chemin | Description | Rate limit |
|---|---|---|---|
| POST | `/api/btp-solver/solve` | Résout un problème | 10/heure |
| GET  | `/api/btp-solver/history?limit=20` | Historique du user | — |
| GET  | `/api/btp-solver/{problem_id}` | Récupère un problème | — |

Stockage : `db.btp_problems` (index user_id+generated_at_iso, problem_id unique).

### `backend/plans_pro/` — Analyse de plan Pro

Réutilise `engines.autodesk_md.extract()` (déjà en prod : upload OSS + traduction MD + extraction properties avec cache par hash). Ajoute :
- **Agrégation quantités par catégorie** (murs, dalles, portes, fenêtres, poteaux, poutres…) — surface m², volume m³, longueur m, count.
- **Cascade Vision IA parallèle** : Claude Sonnet 4.6 Vision + GPT‑4o + Gemini 2.0 Flash → fusion par vote (kind, count, confidence).
- **Vérification normes Perplexity** (domaines Légifrance/CSTB/AFNOR) sur les pathologies détectées.
- **Job asynchrone** avec polling (progress 10 → 60 → 80 → 100 %).

**Endpoints**
| Méthode | Chemin | Description | Rate limit |
|---|---|---|---|
| POST | `/api/plans-pro/upload` | Upload DWG/RVT/IFC/PDF/PNG → `job_id` | 20/heure |
| GET  | `/api/plans-pro/job/{job_id}` | Statut + progression | — |
| GET  | `/api/plans-pro/job/{job_id}/result` | Résultat complet | — |
| POST | `/api/plans-pro/analyze-image` | Analyse image seule (base64) | 30/heure |
| GET  | `/api/plans-pro/history?limit=20` | Historique | — |

Stockage : `db.plans_pro_jobs` (index user_id+created_at, job_id unique, TTL 30 j).

## Frontend

- `frontend/src/pages/BtpSolver.jsx` — formulaire + résultat + graphiques
- `frontend/src/components/btpSolver/SolverCharts.jsx` — charts SVG (bar / radar / pie), zéro dépendance externe
- `frontend/src/pages/PlansPro.jsx` — upload + polling + tableau quantités + éléments vision

**À faire à l'installation** :
Ajoutez les routes React dans votre routeur (React Router) :
```jsx
import BtpSolver from "@/pages/BtpSolver";
import PlansPro from "@/pages/PlansPro";
// ...
<Route path="/btp-solver" element={<BtpSolver />} />
<Route path="/plans-pro"  element={<PlansPro />} />
```
Et un lien dans votre menu principal.

## Variables d'environnement (déjà présentes dans .env.example Sprint 0)

```
EMERGENT_LLM_KEY=              # requis (Claude/GPT/Gemini via emergentintegrations)
PERPLEXITY_API_KEY=            # requis pour btp_solver + norm check plans_pro

# Autodesk (obligatoire pour DWG/RVT/IFC/PDF)
APS_CLIENT_ID=
APS_CLIENT_SECRET=
APS_BUCKET_KEY=construpilot-plans
APS_OSS_BASE_URL=https://developer.api.autodesk.com
```

## server.py

Deux inclusions de routers ajoutées après `perplexity_plus` :
```python
from btp_solver.routes import router as btp_solver_router
api_router.include_router(btp_solver_router)
from plans_pro.routes import router as plans_pro_router
api_router.include_router(plans_pro_router)
```
Et 5 index Mongo créés au startup.
