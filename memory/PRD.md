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

## 4. État actuel (12/02/2026 — itération 7-8)
### ✅ Implémenté & testé (Backend 119/119 pytest cumulés, tous flows frontend 100%)
- Landing, Smart Project, catalogue travaux, auth email + Google, seed idempotent.
- Smart Project IA, Estimateur wizard, 5 calculateurs matériaux.
- Recherche prix Tavily temps réel (fallback demo intelligent) — **enrichie affiliate** (badge "Lien partenaire" pour Leroy Merlin/ManoMano, tracking Awin/CJ, transparence).
- Dashboard, Coach IA SSE, Back-office admin.
- PDF de devis (téléchargement + envoi email Resend).
- Photos avant/après avec compression client + Object Storage + slider comparateur.
- Chantier Timeline (frise chronologique).
- Alertes Prix (APScheduler cron 08:00 UTC + emails Resend).
- Rebranding ConstruPilot.
- QuoteScanner accepte PDF (pypdf) + images.
- **PHASE 1** : 8 plans core + Stripe checkout + entitlements + trial 7j + soft paywall + upgrade CTA.
- **PHASE 2** : Savings Engine (4 postes calculés) + Codes promo Stripe Coupons/PromotionCodes admin.
- **PHASE 3** : Referral 5€/5€ + Marketplace + Lead Scoring 0-100.
- **PHASE 4** ✅
  - **API Commerciale** : 3 plans (Starter 99€, Business 299€, Scale 999€), clés `ckp_live_XXX`, rate limiting mensuel, endpoints /api/v1/public/{estimation,prices,calculators}. Page `/developpeurs` (renommée depuis `/api` pour éviter collision ingress k8s).
  - **KYC Pros** : SIREN + RC Pro + décennale + admin review + badge "ConstruPilot Verified".
  - **Portail Pro** : dashboard `/pro` avec crédits, leads dispo (filtered), leads achetés, recharge Stripe avec bonus (+5% à 250€, +10% à 500€).
  - **Affiliation Fournisseurs** : configs par supplier (Awin/CJ), enrichissement `/api/prices/search`, tracking clic + redirect `/api/r/aff/{sup}`, admin dashboard clics/redirections/conversions/revenue.

### 🟡 Points d'attention (non bloquants)
- Warning React setState during render dans Login/AuthContext.
- Tavily ~25% fallback demo.
- Webhook Stripe non testable en preview (mais wire vérifié).
- Consider: shadcn AlertDialog remplaçant window.confirm() dans ApiKeys.jsx.
### ✅ Implémenté & testé (Backend 87/87 pytest cumulés, tous flows frontend OK)
- Landing, Smart Project, catalogue travaux, auth email + Google, seed idempotent.
- Smart Project IA, Estimateur wizard, 5 calculateurs matériaux.
- Recherche prix Tavily temps réel (fallback demo intelligent).
- Dashboard, Coach IA SSE, Back-office admin.
- PDF de devis (téléchargement + envoi email Resend).
- Photos avant/après avec compression client + Object Storage + slider comparateur.
- Chantier Timeline (frise chronologique multi-sources).
- Alertes Prix (APScheduler cron 08:00 UTC + emails Resend).
- Rebranding ConstruPilot.
- QuoteScanner accepte PDF (extraction pypdf) + images.
- **CONSTRUPILOT REVENUE ENGINE — PHASE 1 ✅** : 8 plans configurables, Stripe sandbox, checkout, webhook, entitlements, page /tarifs, /paiement/succes+annule, BillingContext, SoftPaywall, trial 7 jours, admin plans + revenu.
- **CONSTRUPILOT REVENUE ENGINE — PHASES 2 & 3 ✅**
  - **Savings Engine** — 4 postes calculés (matériaux 8%, alternatives std→eco, DIY main d'œuvre, fournisseurs 6%) + ROI Project Pass. Component `SavingsCard` sur Estimator + ProjectDetail. FREE : 1er poste ouvert, autres floutés + CTA upgrade.
  - **Codes Promo Admin** — CRUD complet, création Stripe Coupons + PromotionCodes (nested `promotion={type,coupon}`), toggle actif, panel dédié `/admin` tab "Codes promo". `allow_promotion_codes=true` dans checkout Stripe (les codes sont utilisables directement à la caisse).
  - **Referral (parrainage 5€/5€)** — code unique CP-XXXXXX par user, page `/parrainage` (copier lien + code + stats), input "Code parrainage" sur inscription (auto-apply si `?ref=`), génération automatique d'un promotion_code Stripe pour le filleul, crédit +5€ au parrain via webhook `_mark_paid`.
  - **Marketplace Pros + Lead Scoring** — score 0-100 (11 facteurs) + tier (petit/standard/premium/grand) + prix cents. Page `/marketplace` publique (feature-flag `marketplace_enabled` avec bandeau bêta). Endpoints /marketplace/leads (soumission), /marketplace/pros (annuaire vérifiés), /marketplace/register (candidature pro), /marketplace/leads/buy (achat par pros vérifiés avec crédits).

### 🟡 Points d'attention (non bloquants)
- Warning React `setState during render` dans Login/AuthContext.
- Webhook Stripe non testable en preview (mais wire vérifié : `_mark_paid` déclenche entitlement + referral credit).
- Tavily : ~25% requêtes populaires en fallback demo.

## 5. Backlog priorisé
### PHASE 4 — B2B / API / White Label / Affiliation avancée
- Affiliation fournisseurs (tracking clics/conversions/GMV/commissions)
- Badges "Sponsorisé" et "Lien partenaire" (transparence)
- Enrichir marketplace : vérification KYC pros (SIREN/RC/décennale), badges, avis, portail pro complet
- Crédits pros ConstruPilot (rechargement Stripe pour acheter les leads)
- API commerciale (clés, rate limits, usage tracking, billing)
- White Label (logo/couleurs partenaire, sous-domaines)
- Enterprise + SSO
- Revenue Dashboard admin avancé (MRR/ARR/ARPU/LTV/CAC/funnel/A/B)

### P1 — Fiabilité
- Corriger warning React `setState during render`.
- Domaine Resend vérifié (au-delà de la sandbox).
- Vérification par email/téléphone (phone_verified/email_verified pour lead scoring +5pts chacun).

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
