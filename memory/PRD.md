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

### ✅ Implémenté & testé (Backend 168/168 pytest · Frontend 100%)
- Fondations MVP complètes.
- **PHASE 1** — Stripe subscriptions + 10 plans + trial 7j + paywall.
- **PHASE 2** — Savings Engine + Codes promo admin.
- **PHASE 3** — Referral 5€/5€ + Marketplace + Lead Scoring.
- **PHASE 4** — API commerciale + KYC pros + Portail Pro + Affiliation.
- **PHASE 5** — White Label + Portail Fournisseurs + Enterprise + /docs.
- **PHASE 6** — Onboarding Tour + PWA + Sponsored Products + Historique Prix.
- **PHASE 7** ✅ (iter11) : Push Notifications VAPID + Retention Weekly Digest + Referral Landing riche + fix warning React.
- **PRICING PRO — 12/02/2026** : Pro 49→99€/mois (990€/an), Pro Business 99→199€/mois (1990€/an) — migration DB idempotente.
- **WHATSAPP SHARE — 13/02/2026** ✅ : dialog + lien public /e/:token + message éditable Markdown WA.
- **ITER 12 — 13/02/2026** ✅ 4 features additionnelles :
  - **Revenue Cockpit admin** (`/api/admin/revenue/{kpis,timeseries}`) : MRR/ARR/ARPU/LTV/CAC/LTV·CAC/Trials/Revenu mois + MRR par plan + funnel 30j (signups→trials→paid + leads) + graph recharts quotidien 30/90/180/365j.
  - **Share Analytics** : compteur `share_opens` + `share_last_open_at` + `share_events` (rolling 100 avec UA/IP) sur chaque `GET /public/estimation/{token}`. Endpoint dédié `GET /api/projects/{id}/share/stats`.
  - **Sharing Expiry** : POST `/api/projects/{id}/share` accepte `{expires_in_days: 1|7|30|null}` ; réponse `410 Gone` sur token expiré ; UI select "Sans expiration / 24h / 7j / 30j".
  - **SMS Sharing** : bouton natif `sms:` (mobile) + endpoint `POST /api/projects/{id}/share/sms` Twilio (503 propre si non configuré). `GET /api/share/sms/config` expose l'état sans révéler les clés.
- ENV Twilio prêts (`TWILIO_ACCOUNT_SID` renseigné, TOKEN + FROM à compléter).

### 🟡 Points d'attention (non bloquants)
- Tavily ~25% fallback demo.
- Webhook Stripe non testable en preview.
- Push non testable en Playwright headless (permissions bloquées).
- Twilio SMS : SID configuré, `TWILIO_AUTH_TOKEN` + `TWILIO_FROM_NUMBER` à ajouter dans `.env` pour activer l'envoi serveur (fallback natif `sms:` opérationnel).

## 5. Backlog priorisé

### P0 — Compléter Twilio
- Ajouter `TWILIO_AUTH_TOKEN` + `TWILIO_FROM_NUMBER` dans `.env` puis vérifier `POST /api/projects/{id}/share/sms`.

### P1 — Fiabilité
- Vérification email/téléphone (+5pts lead scoring chacun).
- Domaine Resend vérifié (au-delà de la sandbox).
- Remplacer `window.confirm()` par shadcn AlertDialog dans ApiKeys.jsx.
- Historique de churn réel (au lieu de 5%/mois hardcodé) pour la LTV.
- CAC via input admin manuel ou via CampaignSpend collection.

### P2 — Enrichissements
- Emails de notification quand un lien de partage est ouvert (opt-in).
- Analytics : ouvertures /e/:token par jour dans un mini-chart sur ProjectDetail.
- Expiration granulaire (heures/date custom via calendar picker).
- A/B testing sur les prix (99€ vs 79€).

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
