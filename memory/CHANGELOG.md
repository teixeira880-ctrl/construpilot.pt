# ConstruPilot — CHANGELOG

## Itération 78 — 15/06/2026 (Suite Pro — Étape 0 + Étape 1)

### Étape 0 — Langue Portugaise 🇵🇹
- `context/I18nContext.jsx` : ajout du bloc `pt` (dictionnaire complet) + `PT` dans le sélecteur de langue.
- La navigation et les zones internationalisées basculent en portugais (Painel, Medir, Preços de materiais…).
- ⚠️ Note : les pages au texte codé en dur (français) ne sont pas encore traduites — traduction profonde page par page = lot ultérieur.

### Étape 1 — CRM Clients + extraction IA
- Backend `routes/clients.py` : CRUD complet des fiches clients (nom, prénom, société, email, tél,
  adresse, CP, ville, SIRET, notes), scoped par `user_id`. Collection Mongo `clients`.
  - `POST /api/clients`, `GET /api/clients?q=`, `GET/PUT/DELETE /api/clients/{id}`.
  - `POST /api/clients/from-plan/{plan_id}` : crée automatiquement une fiche depuis le
    cartouche / permis de construire détecté par l'IA (`ai_analysis.client_info`).
- `engines/plan_ai.py` : nouvelle section `client_info` dans le prompt (maître d'ouvrage,
  adresse projet, tél…) + normalisation.
- Frontend :
  - Page `/clients` (`Clients.jsx`) : recherche, création/édition (dialog), suppression, cartes.
  - Lien nav « Clients » (icône Contact).
  - PlanTakeoff : carte « Client détecté sur le plan » + bouton « Créer la fiche client » (IA).

### Tests
- CRUD Clients validé via curl (create/list/update/search/delete) + UI (création « Jean Martin »).
- `from-plan` renvoie 400 clair si aucune info détectée (pas de 500).
- Portugais validé (nav bascule, sélecteur fr/en/es/pt).

### Étape 2 — Bibliothèque perso (livrée le 15/06)
- Backend `routes/library.py` : collection `library_items` {type ouvrage|materiau, category, designation,
  unit, unit_price_ht, vat_rate, notes}. CRUD + recherche + filtre par type.
- Catalogue de départ (38 ouvrages/matériaux BTP, prix HT modifiables) auto-seedé une seule fois
  par utilisateur (flag `library_seeded`). Endpoint `/library/reset-catalogue`.
- Frontend : page `/bibliotheque` (`Library.jsx`) — table, filtres Tous/Ouvrages/Matériaux,
  recherche, création/édition (dialog : type, catégorie, unité, PU HT, TVA 10/20/5,5 %), suppression.
- Lien nav « Bibliothèque ». Testé (auto-seed 38, CRUD, filtre, recherche via curl + UI).

### Reste à faire (roadmap Suite Pro)
- Étape 3 — Éditeur de devis : devis vide + **import du devis généré par l'IA (plan/PC) en devis modifiable**,
  sélection client, lignes depuis la bibliothèque (auto-save des nouvelles lignes), logo + certifs.
  Inclut l'enchaînement **plan → fiche client → devis pré-rempli à son nom**.
- Étape 4 — Factures (num. FAC-2026-0001, acomptes, TVA multi-taux 10/20/5,5 %).
- Étape 5 — Certifications (Qualibat, RGE, QualiPAC, Qualifelec, Qualibois) + branding avancé.

---

## Itération 77 — 15/06/2026 (lot 6 demandes)

### 1. Compte admin débloqué (2FA OPT-IN)
- `server.py::seed()` : migration one-shot `two_fa_seed_reset` qui repasse `two_fa_enabled=False`
  sur le compte admin (le code email n'était pas délivrable de façon fiable et bloquait la connexion).
- Le login admin renvoie de nouveau `{user, token}` directement. Le 2FA reste réactivable depuis `/compte`.

### 2. Renommages Plan 2D
- Menu / page « Plan 2D » → « **Mesurer** » (Nav.jsx, I18nContext FR/EN/ES, PcDashboard, paywall PlanTakeoff).
- Outil « Polyligne » → « **Périmètre** » (PlanTakeoff toolbar, ObjectPanel).

### 3. Analyse IA du plan + symboles
- `engines/plan_ai.py` : modèle passé à **gemini-3-flash-preview** (via EMERGENT_LLM_KEY).
- Prompt étendu : détection des symboles **électriques** (`electrical`: prises, interrupteurs,
  points lumineux, spots, tableau, RJ45/TV) et **plomberie** (`plumbing`: WC, lavabos, douches,
  baignoires, éviers, chauffe-eau, lave-linge, arrivées/évacuations) + normalisation.
- Frontend : carte `data-testid=ai-symbols` dans l'onglet IA de PlanTakeoff.

### 4. Graphique Chiffre d'Affaires mensuel
- Backend : `GET /api/quotes/revenue/monthly` — agrège le CA des devis **signés** sur 12 mois.
- Frontend : `components/RevenueChart.jsx` (recharts, thème vert olive), affiché sur `/devis` et `/dashboard`.

### 5. Avis Clients
- Backend `routes/reviews.py` :
  - `POST /api/reviews/request/{log_id}` — marque le chantier terminé + envoie une demande d'avis au client.
  - `GET/POST /api/reviews/collect/{token}` — collecte publique (note 1-5 + commentaire).
  - `GET /api/reviews/me`, `PATCH /api/reviews/{review_id}/publish`.
  - Helper `get_reviews_for_user()` → injecté dans le PDF devis (`_story_quote_reviews`).
- Frontend : `/avis/:token` (ReviewCollect.jsx, public), `/mes-avis` (MyReviews.jsx), bouton
  « Chantier terminé » sur les cartes signées de `/devis`, lien nav « Avis clients ».
- Collection Mongo `reviews` {review_id, token, user_id, log_id, client_email, rating, comment, submitted, published}.

### 6. Export PDF Récap comptable
- Backend : `GET /api/quotes/recap-pdf?year=&month=` → `build_accounting_recap_pdf()` (reportlab) :
  tableau des devis du mois + synthèse (CA signé HT/TVA 10%/TTC, pipeline), prêt pour le comptable.
- Frontend : section « Export comptable » sur `/devis` (sélecteur mois/année + bouton PDF, CSV conservé).

### Tests
- `/app/backend/tests/test_iter77_reviews_revenue_recap.py` — 8 passed. Agent de test : 0 bug (backend 100%, frontend 100%).
- Flux avis validé bout-en-bout (request → collect → me → présence dans le PDF devis).
