# ConstruPilot — PRD

> **Rebranding 12/02/2026** : l'app était initialement nommée « CMRENOV Travaux AI ». Elle a été renommée **ConstruPilot** — tagline : *Estimez. Comparez. Construisez.*

## 1. Problème & vision
Application web (et mobile-ready) qui aide particuliers et pros du bâtiment à :
- Décrire un projet en langage naturel et obtenir immédiatement une **estimation structurée** (lots, matériaux, main d'œuvre, coût total).
- Utiliser des **calculateurs matériaux** professionnels (peinture, carrelage, placo, béton, isolation).
- **Comparer les prix** des matériaux en temps réel via Tavily.
- Obtenir des **guides DIY** et un **coach IA** pour les auto-constructeurs.
- Générer des **PDF de devis** (téléchargement + envoi email Resend) et des **leads qualifiés** ConstruPilot Pro.
- **Documenter son chantier** : photos avant/après (Object Storage), timeline chronologique, alertes prix quotidiennes.

Langue produit : **Français**.

## 2. Personas
- **Particulier** — décrit un projet, obtient une estimation, télécharge un PDF, contacte CMRENOV.
- **DIY / auto-constructeur** — utilise Coach IA, calculateurs et guides « Je le fais moi-même ».
- **Pro CMRENOV** (admin) — back-office : prix référence, coefficients régionaux, fournisseurs, utilisateurs, projets, leads, stats.

## 3. Architecture
- **Backend** : FastAPI (Motor async) — routes préfixées `/api`.
- **DB** : MongoDB (choix confirmé par l'utilisateur, en remplacement du PostgreSQL initial).
- **Frontend** : React + Tailwind + shadcn/ui — routes SPA via React Router.
- **IA** : GPT via Emergent Universal LLM Key (via `emergentintegrations`).
- **Auth** : JWT + cookie (email/password) et Google via Emergent-managed OAuth.
- **PDF** : ReportLab côté backend.
- **Prix** : `engines/price_search.py` — **MOCKÉ** (demo connector) — prêt à basculer sur Tavily quand la clé sera fournie.

### Arborescence clé
```
/app/backend/
  server.py, core/{db.py,security.py}
  engines/{ai.py, estimation.py, calculators.py, diy.py, price_search.py (MOCK), pdf.py, catalog.py}
  routes/{auth.py, ai_routes.py, estimation_routes.py, projects.py, prices.py, tools.py, leads.py, admin.py}
  tests/backend_test.py — 24/24 ✅
/app/frontend/src/
  App.js, context/AuthContext.jsx, lib/api.js
  pages/{Landing, Login, SmartProject, Estimator, Dashboard, ProjectDetail, Calculators, PriceSearch, Diy, Coach, PhotoAnalyse, QuoteScanner, Admin}.jsx
  components/{Nav.jsx, Bits.jsx, LeadDialog.jsx, EstimationView.jsx, AuthCallback.jsx}
```

### Endpoints backend (implémentés & testés)
- **Auth** : `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, Google Emergent flow.
- **IA** : `POST /api/estimation/analyse` (Smart Project), `POST /api/chat` (Coach — SSE streaming).
- **Estimation** : `POST /api/estimation/compute`.
- **Calculateurs** : `POST /api/calculators/{paint|tile|drywall|concrete|insulation}`.
- **Prix** (mocké) : `POST /api/prices/search`.
- **Projects** : CRUD `/api/projects`.
- **Leads** : `POST /api/leads`, admin `GET /api/admin/leads`, `GET /api/admin/stats`.
- **Admin** : RBAC via `Depends(admin_user)` — user reçoit 403.

## 4. État actuel (12/02/2026 — itération 4)
### ✅ Implémenté & testé (Backend 49/49 pytest cumulés, tous flows frontend OK)
- Landing, formulaire Smart Project, catalogue travaux.
- Auth email (register/login/logout/me) + Google Emergent.
- Seed idempotent au démarrage : `admin@construpilot.fr` / `Construpilot2026!` et `demo@construpilot.fr` / `Demo2026!`. Suppression automatique des anciens comptes `@cmrenov.fr`.
- Smart Project IA (GPT via Emergent Universal LLM Key) → analyse projet en lots/matériaux/estimation.
- Estimateur (wizard 3 étapes) + calcul montant global.
- 5 calculateurs matériaux (peinture, carrelage, placo, béton, isolation).
- **Recherche prix Tavily temps réel** (mode `web`) avec fallback intelligent (2 appels + demo).
- Dashboard projets utilisateur, Coach IA (streaming SSE), Back-office admin.
- **PDF de devis** — bouton "Télécharger" ET "Envoyer par email" (via Resend) sur Estimator + ProjectDetail.
- **Photos avant/après** — compression client Canvas (~150 Ko cible), galerie multi-photos, slider comparateur horizontal, Emergent Object Storage.
- **Chantier Timeline** — frise chronologique mélangeant photos + dépenses + progression + leads, avec filtres.
- **Alertes Prix** — création alertes, vérification quotidienne (APScheduler cron 08:00 UTC) + bouton "Vérifier maintenant" + notifications email Resend.
- Thème clair/sombre.
- **Rebranding ConstruPilot** — tagline "Estimez. Comparez. Construisez.", logo Constru+**Pilot**, PDF/emails/UI cohérents.

### 🟡 Points d'attention (non bloquants)
- Warning React `setState during render` dans Login/AuthContext (identifié par testing agent iter 4).
- Tavily : ~25% des requêtes populaires (ex: "peinture") en fallback demo.
- Cookie `session_token` prime sur `Authorization: Bearer` dans `optional_user`.

## 5. Backlog priorisé
### P1 — Fiabilité
- Corriger warning React `setState during render` dans Login/AuthContext.
- Domaine Resend vérifié (au lieu de `onboarding@resend.dev` en sandbox) pour envoyer vers n'importe quel destinataire.

### P2 — Enhancements produit
- Onboarding / tour produit interactif.
- Historique versions d'un projet.
- Analyse photo / scan de devis (pages présentes, à connecter à un modèle vision).
- Whitelist Tavily élargie + parseur prix plus robuste.
- App mobile PWA (installer + offline).

## 6. Intégrations 3rd-party
- **Emergent Universal LLM Key** — GPT (Smart Project + Coach) + Object Storage.
- **Emergent-managed Google OAuth**.
- **Tavily** — mode web opérationnel avec fallback demo.
- **Resend** — envoi PDF + alertes prix (sandbox `onboarding@resend.dev`).
- **Emergent Object Storage** — bucket `construpilot/projects/{project_id}/photos/*`.
- **APScheduler** — cron quotidien 08:00 UTC pour les alertes prix.

## 7. Credentials de test
Voir `/app/memory/test_credentials.md`.
