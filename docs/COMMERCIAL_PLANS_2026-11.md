# Offre commerciale B2B 2026-11 — Solo · Professional · Business · Enterprise

Branche : `feat/commercial-plans-2026-11` (dépôts `construpilot.fr_1` et `construpilot.pt`, code identique,
seule différence : `DEFAULT_MARKET` dans `backend/engines/commercial_plans.py` et les textes de pages existantes).

## Ce qui change

| Domaine | Fichiers | Effet |
|---|---|---|
| Catalogue unique | `backend/engines/commercial_plans.py` | Prix, limites, fonctions, statut (disponible/bêta/bientôt). Enterprise sans aucun montant. Annuel = 12 × mensuel × 0,85. |
| Mesure & limites | `backend/engines/usage_meter.py` | Pages techniques/mois (idempotent par import), projets actifs, utilisateurs, stockage, appels IA par compte. Compte = propriétaire de l'organisation. |
| API | `backend/routes/commercial.py` | `GET /api/commercial/plans`, `GET /api/commercial/usage`, `POST /api/commercial/checkout`, `POST /api/commercial/portal`, `POST /api/commercial/enterprise-lead`. |
| Stripe | `backend/engines/monetization.py` | Prix HT (`tax_behavior=exclusive`), TVA auto + n° TVA client au checkout B2B, déduplication des webhooks, upgrade/downgrade via portail, `invoice.paid`, refus du webhook sans secret (FR), tiers centralisés (fin des tests de préfixe). |
| Accès | `backend/engines/access.py` (FR) | Niveau Pro/Business calculé via `tier_for_plan_id`. |
| Points d'application | `routes/projects.py`, `routes/company.py`, `routes/phase7.py`, `routes/plans_crud.py`, `engines/ai.py` | Vérification avant création de projet / membre / invitation / import ; décompte des pages ; compteur IA. |
| Démarrage | `backend/server.py` | Insertion (jamais d'écrasement) des 6 plans `cp_*` + index. |
| Front | `frontend/src/components/pricing/*`, `lib/commercialCopy.js`, `lib/market.js`, `pages/Pricing.jsx`, `pages/Enterprise.jsx`, `lib/api.js` | Nouvelle page tarifs (onglet Professionnels par défaut, Particuliers conservé), comparatif, FAQ, formulaire Enterprise, message unique sur HTTP 402. |
| Textes publics | `LandingPro`, `LandingMetre`, `Help`, `ProOffer`, `Landing`, `landingI18n` | Anciens prix 149/249 remplacés ; JSON-LD sans Enterprise. |
| Démo hors ligne (PT) | `frontend/src/lib/demoInterceptor.js`, `fixtures/demo/commercial_plans.json` | La page `/planos` et le formulaire fonctionnent sans internet. |

Les plans historiques (`free`, `project_pass`, `premium_*`, `pro_*`, `pro_business_*`, options) ne sont pas modifiés :
les abonnés existants gardent leurs conditions et ne reçoivent **aucune** nouvelle limite.

## Interrupteurs (tous fermés par défaut)

| Variable | Défaut | Rôle |
|---|---|---|
| `COMMERCIAL_CHECKOUT_ENABLED` | `false` | Ouvre la souscription en ligne Solo/Professional/Business. Fermé → bouton « Créer mon compte ». |
| `STRIPE_LIVE_ALLOWED` | `false` | Avec une clé `sk_live_…`, le checkout B2B est refusé tant que ce n'est pas `true`. |
| `COMMERCIAL_STRIPE_SYNC` | `false` | Autorise `ensure_stripe_catalog` à créer les Products/Prices `cp_*` au démarrage. Sans lui, le Price est créé seulement au premier checkout autorisé. |
| `PLAN_LIMITS_MODE` | `observe` | `off` / `observe` (mesure + journal `usage_events`, jamais de blocage) / `enforce` (HTTP 402). |
| `CP_MARKET` | `fr` (dépôt FR) / `pt` (dépôt PT) | Préfixe des lookup_keys Stripe, e-mail commercial, URL de retour. |
| `COMMERCIAL_SALES_EMAIL` | `info@construpilot.fr` / `info@construpilot.pt` | Destinataire des demandes Enterprise. |
| `COMMERCIAL_ALLOWED_ORIGINS` | domaine du marché | Liste blanche des URL de retour Stripe. |

## Ordre d'activation recommandé

1. Déployer (tout fermé). Vérifier `/tarifs` et `/planos`, le formulaire Enterprise, `GET /api/commercial/plans`.
2. Stripe **mode test** : activer Stripe Tax (inscription TVA FR / PT), `COMMERCIAL_CHECKOUT_ENABLED=true`, faire un checkout Solo mensuel et Business annuel avec la carte 4242…, puis un upgrade via le portail, un échec de paiement (carte 4000 0000 0000 0341) et un rattrapage.
3. Laisser `PLAN_LIMITS_MODE=observe` 2 à 4 semaines ; lire `usage_events` (`limit_would_block`) et `usage_monthly` (pages, appels IA) pour calibrer.
4. Sur autorisation explicite : clé live + `STRIPE_LIVE_ALLOWED=true`, puis `PLAN_LIMITS_MODE=enforce`.

## Tests

`cd backend && python -m pytest tests/test_commercial_offer.py -n 0` → 23 tests (catalogue, Enterprise sans prix,
limites, idempotence, comptes d'organisation, checkout sandbox simulé, formulaire, anti-spam, débit, webhooks).
Non-régression : les suites existantes touchant facturation/accès/projets/plans donnent le même ensemble d'échecs avant
et après (échecs préexistants : tests nécessitant un serveur et une base en direct).

## Retour arrière

* Immédiat, sans redéploiement : `PLAN_LIMITS_MODE=off`, `COMMERCIAL_CHECKOUT_ENABLED=false`.
* Code : revenir au commit précédent de `main`. Les données ajoutées (`plans` `cp_*`, `usage_monthly`, `usage_events`,
  `commercial_leads`, `billing_audit`, `stripe_events`) sont additives ; les supprimer est facultatif.
* Aucun abonnement existant n'est modifié par cette branche.

## Points restant à valider (non faits volontairement)

* Paiement réel, prix Stripe live, Stripe Tax (inscriptions TVA) — autorisation requise.
* Extras (utilisateur 19 €, 500 pages 49 €, onboarding 299 €) : **non publiés** — voir le rapport stratégique.
* Plusieurs fonctions Enterprise sont marquées « Bientôt » (multi-entités, API entreprise, ERP).
* Facturation électronique au Portugal : le module actuel est Factur-X (norme française) ; au Portugal, un logiciel de facturation doit être certifié par l'AT.
