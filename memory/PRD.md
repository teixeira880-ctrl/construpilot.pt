# CMRENOV Travaux AI — PRD

## 1. Problème & vision
Application web (et mobile-ready) qui aide particuliers et pros du bâtiment à :
- Décrire un projet en langage naturel et obtenir immédiatement une **estimation structurée** (lots, matériaux, main d'œuvre, coût total).
- Utiliser des **calculateurs matériaux** professionnels (peinture, carrelage, placo, béton, isolation).
- **Comparer les prix** des matériaux en temps réel (aujourd'hui mocké, prêt pour Tavily).
- Obtenir des **guides DIY** et un **coach IA** pour les auto-constructeurs.
- Générer des **PDF de devis** et des **leads qualifiés** pour CMRENOV.

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

## 4. État actuel (12/02/2026)
### ✅ Implémenté & testé (Backend 24/24 pytest, tous flows frontend critiques OK)
- Landing, formulaire Smart Project, catalogue travaux.
- Auth email (register/login/logout/me) + Google Emergent.
- Seed idempotent au démarrage : `admin@cmrenov.fr` / `Cmrenov2026!` et `demo@cmrenov.fr` / `Demo2026!`.
- Smart Project IA (GPT via Emergent Universal LLM Key) → analyse projet en lots/matériaux/estimation.
- Estimateur (wizard 3 étapes) + calcul montant global.
- 5 calculateurs matériaux (peinture, carrelage, placo, béton, isolation).
- Recherche prix mockée (demo connector, 10 fournisseurs, cartes prix, badge « Données de démonstration »).
- Dashboard projets utilisateur.
- Coach IA (streaming SSE).
- Back-office admin (users, projets, leads, stats).
- Génération PDF de devis (ReportLab).
- Thème clair/sombre.

### 🟡 Points d'attention identifiés par le testing agent
- **(mineur)** Warning React `setState during render` — non bloquant, à investiguer.
- **(mineur — corrigé)** 401 bruyants côté console sur pages publiques : `AuthContext` ne pingue plus `/auth/me` sans token ni cookie.
- **(mineur)** Cookie `session_token` prime sur `Authorization: Bearer` dans `optional_user` — non bloquant en usage réel.
- **Ambiguïté nommage routes** : brief mentionnait `/api/estimation/calculate` et `/api/tools/calculator/*` ; implémentation utilise `/api/estimation/compute` et `/api/calculators/*`. À aligner si client externe l'exige.

## 5. Backlog priorisé
### P1 — Fiabilité & complétude
- Vérifier le flux **PDF devis** de bout en bout (bouton front → génération → téléchargement).
- Vérifier le **CMRENOV lead generation** (LeadDialog → `/api/leads` → admin).
- Corriger le warning React `setState during render` (probablement dans un composant page).

### P2 — Intégrations & data réelles
- **Tavily** : remplacer le mock `engines/price_search.py` par la vraie API (attente clé utilisateur). Mock déjà au format cible.
- Refactor mineur : uniformiser le format de retour prix pour bascule zéro-diff sur Tavily.
- Enrichir le catalogue matériaux et coefficients régionaux via back-office.

### P3 — Enhancements
- Export estimation → email + PDF signé.
- Historique versions d'un projet.
- Analyse photo / scan de devis (pages présentes, à connecter à un modèle vision).
- Onboarding et tour produit.

## 6. Intégrations 3rd-party
- **Emergent Universal LLM Key** — GPT (Smart Project + Coach).
- **Emergent-managed Google OAuth** — via `auth.emergentagent.com` + callback `/auth/google/session`.
- **Tavily** — **MOCKÉ** (à activer dès réception de la clé).

## 7. Credentials de test
Voir `/app/memory/test_credentials.md`.
