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

## 4. État actuel (12/02/2026 — itération 5)
### ✅ Implémenté & testé (Backend 69/69 pytest cumulés, tous flows frontend OK)
- Landing, formulaire Smart Project, catalogue travaux.
- Auth email (register/login/logout/me) + Google Emergent.
- Seed idempotent : `admin@construpilot.fr` / `Construpilot2026!` et `demo@construpilot.fr` / `Demo2026!`.
- Smart Project IA, Estimateur wizard, 5 calculateurs matériaux.
- **Recherche prix Tavily temps réel** (mode `web` + fallback demo).
- Dashboard, Coach IA (SSE), Back-office admin.
- **PDF de devis** — téléchargement + envoi email via Resend.
- **Photos avant/après** — compression client Canvas + Emergent Object Storage + slider comparateur.
- **Chantier Timeline** — frise chronologique.
- **Alertes Prix** — APScheduler cron 08:00 UTC + notifications Resend.
- **Rebranding ConstruPilot** — tagline "Estimez. Comparez. Construisez."
- **QuoteScanner** — accepte désormais les PDF (extraction pypdf) en plus des images.
- **CONSTRUPILOT REVENUE ENGINE — PHASE 1** ✅
  - 8 plans configurables en DB (Free / Project Pass 19,90€ / Premium 9,99€/mois / Premium 79€/an / Pro 49€/mois / Pro 490€/an / Pro Business 99€/mois / Pro Business 990€/an).
  - Feature flags (`trial_enabled`, `trial_days=7`, `paywall_mode='soft'`, `marketplace/affiliate/api/white_label` désactivés).
  - **Stripe sandbox Emergent** claimable — catalogue Products+Prices synchronisé automatiquement au startup.
  - Endpoints : `/api/plans`, `/api/billing/checkout`, `/api/billing/status/{id}`, `/api/billing/me`, `/api/billing/portal`, `/api/billing/flags`, `/api/stripe/webhook`.
  - Admin : `/api/admin/plans` (CRUD), `/api/admin/feature-flags`, `/api/admin/plans/sync-stripe`, `/api/admin/revenue` (MRR-ready).
  - Frontend : `/tarifs` (page publique avec tabs Particulier/Pro), `/paiement/succes`, `/paiement/annule`, `BillingContext` + `SoftPaywall` (non bloquant).
  - Upgrade CTA "Passer Premium — 7 j offerts" sur Dashboard pour FREE.
  - Trial 7 jours activé sur tous les abonnements.

### 🟡 Points d'attention (non bloquants)
- Warning React `setState during render` dans Login/AuthContext.
- Tavily : ~25% requêtes populaires en fallback demo.
- Webhook Stripe : nécessite un événement Stripe réel pour tester la signature.

## 5. Backlog priorisé
### PHASE 2 — Conversion & Savings (à venir)
- Savings Engine (matériaux + DIY + alternatives + fournisseurs) — calculs réels
- Smart Paywall contextuel avancé (messages selon écran)
- Calculateur ROI sur pricing + résultat d'estimation
- Promo codes (réductions %, fixes, expiration, limite)
- Referral program (parrainage crédits)

### PHASE 3 — Leads Marketplace + Affiliation
- Affiliation fournisseurs (tracking clics/conversions/GMV)
- Lead Marketplace (score qualité 0-100, tarification par tranche, crédits pro)
- Badges "Sponsorisé" et "Lien partenaire"

### PHASE 4 — B2B / API / White Label
- API commerciale (clés, rate limits, usage tracking, billing)
- White Label (logo/couleurs partenaire)
- Enterprise + SSO
- Revenue Dashboard admin complet (MRR/ARR/ARPU/LTV/CAC/funnel)

### P1 — Fiabilité
- Corriger warning React `setState during render`.
- Domaine Resend vérifié (au-delà de la sandbox).

## 6. Intégrations 3rd-party
- **Emergent Universal LLM Key** — GPT (Smart Project + Coach) + Object Storage.
- **Emergent-managed Google OAuth**.
- **Tavily** — mode web opérationnel avec fallback demo.
- **Resend** — envoi PDF + alertes prix (sandbox `onboarding@resend.dev`).
- **Emergent Object Storage** — bucket `construpilot/projects/{project_id}/photos/*`.
- **APScheduler** — cron quotidien 08:00 UTC pour les alertes prix.
- **Stripe (sandbox Emergent)** — Subscriptions + one-time (Project Pass) + Customer Portal + Webhook.
- **pypdf** — extraction texte devis PDF.

## 7. Credentials de test
Voir `/app/memory/test_credentials.md`.
