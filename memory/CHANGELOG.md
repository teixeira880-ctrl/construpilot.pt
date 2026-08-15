# ConstruPilot — CHANGELOG

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
