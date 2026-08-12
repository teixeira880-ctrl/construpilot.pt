# ConstruPilot — PRD

> **Rebranding 12/02/2026** : l'app était initialement nommée « CMRENOV Travaux AI ». Elle est renommée **ConstruPilot** — tagline : *Estimez. Comparez. Construisez.*

## 1. Problème & vision
Application web (et mobile-ready) qui aide particuliers et pros du bâtiment à :
- Décrire un projet en langage naturel et obtenir une **estimation structurée** (lots, matériaux, main d'œuvre, coût total).
- Utiliser des **calculateurs matériaux** professionnels (peinture, carrelage, placo, béton, isolation).
- **Comparer les prix** des matériaux en temps réel (Tavily).
- Obtenir des **guides DIY** et un **coach IA** pour les auto-constructeurs.
- Générer des **PDF de devis** (téléchargement + envoi email Resend) et des **leads qualifiés** ConstruPilot Pro.
- **Documenter son chantier** : photos avant/après (Object Storage), timeline chronologique, alertes prix quotidiennes.
- **Partager les estimations** aux clients via WhatsApp (lien public lecture seule).

Langue produit : **Français**.

## 2. Personas
- **Particulier** — décrit un projet, obtient une estimation, télécharge un PDF, contacte CMRENOV.
- **DIY / auto-constructeur** — utilise Coach IA, calculateurs et guides « Je le fais moi-même ».
- **Pro** (artisan, entreprise) — envoie l'estimation à ses clients (WhatsApp/email/PDF), gère plusieurs projets, marge, CRM.
- **Admin** — back-office : plans, promo codes, sponsorships, KYC, revenue, leads, stats.

## 3. Architecture
- Backend : FastAPI (Motor async) — routes préfixées `/api`.
- DB : MongoDB.
- Frontend : React + Tailwind + shadcn/ui.
- IA : GPT via Emergent Universal LLM Key + `emergentintegrations`.
- Auth : JWT + Google via Emergent-managed OAuth.
- PDF : ReportLab / pypdf.
- Prix : Tavily réel + fallback demo.

## 4. État actuel (13/02/2026 — itération 12)

### ✅ Implémenté & testé (Backend 155+/155+ pytest · Frontend 100%)
- Fondations MVP complètes.
- **PHASE 1** — Stripe subscriptions + 10 plans + trial 7j + paywall.
- **PHASE 2** — Savings Engine + Codes promo admin.
- **PHASE 3** — Referral 5€/5€ + Marketplace + Lead Scoring.
- **PHASE 4** — API commerciale + KYC pros + Portail Pro + Affiliation.
- **PHASE 5** — White Label + Portail Fournisseurs + Enterprise + /docs.
- **PHASE 6** — Onboarding Tour + PWA + Sponsored Products + Historique Prix.
- **PHASE 7** ✅ (iter11) :
  - Push Notifications VAPID : hook `usePushNotifications`, composant `PushToggle` sur Dashboard, endpoints `/api/push/{public-key,subscribe,unsubscribe,test}`.
  - Retention Weekly Digest : `engines/retention.py` + APScheduler CronTrigger lundi 09:00 UTC + admin trigger manuel `/api/admin/retention/send-digests`.
  - Referral Landing riche : nouvelle page `/inviter` (Invite.jsx) avec 5 canaux de partage (WhatsApp/Facebook/X/Email/Copier).
  - Warning React setState-during-render corrigé (Login `useEffect` around navigate).
  - Nav "Parrainer" pointe désormais sur `/inviter`.
- **PRICING PRO — 12/02/2026** :
  - Pro : 49€ → **99€/mois** · 490€/an → **990€/an**
  - Pro Business : 99€ → **199€/mois** · 990€/an → **1990€/an**
  - Migration DB au startup (`server.py` — PRICE_MIGRATION dict).
- **WHATSAPP SHARE — 13/02/2026** ✅ :
  - Backend `routes/share.py` : `POST /api/projects/{id}/share` (auth) génère un token URL-safe + persiste `share_token`. `DELETE` révoque. `GET /api/public/estimation/{token}` renvoie une vue lecture seule.
  - Frontend `components/WhatsAppShare.jsx` : dialog avec téléphone optionnel, message éditable pré-rempli en Markdown WhatsApp (`*gras*`, `_italique_`) + lien public.
  - Page publique `PublicEstimation.jsx` route `/e/:token` : header sobre ConstruPilot, 3 KPIs (min/avg/max), détail par lot, CTA d'acquisition.
  - Intégration boutons vert émeraude : Estimator (texte simple sans lien) + ProjectDetail (avec génération de lien public).

### 🟡 Points d'attention (non bloquants)
- Tavily ~25% fallback demo.
- Webhook Stripe non testable en preview.
- Push non testable en Playwright headless (permissions bloquées).

## 5. Backlog priorisé

### P0 — Revenue avancé
- Revenue Dashboard admin (MRR/ARR/ARPU/LTV/CAC/funnel/A/B testing).

### P1 — Fiabilité
- Vérification email/téléphone (+5pts lead scoring chacun).
- Domaine Resend vérifié (au-delà de la sandbox).
- Remplacer `window.confirm()` par shadcn AlertDialog dans ApiKeys.jsx.
- Modèle `PushUnsubIn` dédié (endpoint seul) au lieu de réutiliser `PushSubIn`.

### P2 — Enrichissements sharing
- Sharing via SMS natif (Twilio) — pour compléter WhatsApp.
- Expiration configurable du token de partage (par défaut : perpétuel).
- Analytics du sharing : nb d'ouvertures du lien public par projet.

## 6. Intégrations 3rd-party
- **Emergent Universal LLM Key** — GPT (Smart Project + Coach) + Object Storage + Nano Banana.
- **Emergent-managed Google OAuth**.
- **Tavily** — mode web opérationnel.
- **Resend** — envoi PDF + alertes prix + retention digest (sandbox).
- **Emergent Object Storage** — photos chantier.
- **APScheduler** — 3 crons (alertes prix 08:00, snapshot prix 03:00, digest hebdo lundi 09:00 UTC).
- **Stripe (sandbox Emergent)** — Subscriptions + Project Pass + Portal + Webhook.
- **pywebpush** — Push Notifications VAPID.
- **pypdf** — extraction texte devis PDF.

## 7. Credentials de test
Voir `/app/memory/test_credentials.md`.
