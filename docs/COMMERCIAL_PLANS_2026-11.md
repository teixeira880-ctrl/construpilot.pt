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
| `PLAN_LIMITS_MODE` | `enforce` | `off` / `observe` (mesure + journal `usage_events`, jamais de blocage) / `enforce` (HTTP 402). Décision du 09/11 : `enforce` par défaut. |
| `AI_BUDGET_RATIO_COMMERCIAL` | `0.70` | Part du revenu net (après ~3 % Stripe) qu'un compte Solo/Professional/Business peut consommer en IA. |
| `AI_BUDGET_RATIO_LEGACY` | `1.0` | Idem pour Pro / Pro Business / Premium / Project Pass existants (équilibre : jamais de perte). |
| `FREE_AI_BUDGET_EUR` | `3` | Budget IA mensuel des comptes sans abonnement (gratuit, promo, bêta). Administrateurs exemptés. |
| `AI_PRICE_TABLE` | prix publics | JSON `{"sonnet":[3,15]}` (USD / million de tokens entrée, sortie) pour recaler l'estimation. |
| `CP_MARKET` | `fr` (dépôt FR) / `pt` (dépôt PT) | Préfixe des lookup_keys Stripe, e-mail commercial, URL de retour. |
| `COMMERCIAL_SALES_EMAIL` | `info@construpilot.fr` / `info@construpilot.pt` | Destinataire des demandes Enterprise. |
| `COMMERCIAL_ALLOWED_ORIGINS` | domaine du marché | Liste blanche des URL de retour Stripe. |

## Règle « ne jamais perdre d'argent » (décision du 09/11/2026)

* **Garde-fou de coût IA** (`usage_meter.check_ai_budget`, appelé par `MeteredChat` avant chaque appel et par
  `openai_studies`) : le coût IA estimé d'un compte sur le mois ne dépasse jamais son budget
  (revenu net × ratio, + crédits de packs). Au-delà : 402 `ai_budget`, e-mail d'alerte une fois par mois,
  données et fonctions sans IA intactes. Modèle inconnu = compté au prix maximal ; appel sans compteur = 0,02 €.
* **Options décidées** : utilisateur supplémentaire 39 € HT/mois (Professional et Business uniquement),
  pack 500 pages 79 € HT (crédite aussi 90 % de son prix net en budget IA), prise en main dès 299 € HT,
  intégrations sur devis. Crédit uniquement par un admin avec référence d'accord client
  (`POST /api/commercial/admin/addons/credit`) : rien n'est facturé automatiquement.
* **Limites des nouvelles offres** appliquées dès le premier jour (aucun client existant concerné).

## Ordre d'activation recommandé

1. Déployer (tout fermé). Vérifier `/tarifs` et `/planos`, le formulaire Enterprise, `GET /api/commercial/plans`.
2. Stripe **mode test** : activer Stripe Tax (inscription TVA FR / PT), `COMMERCIAL_CHECKOUT_ENABLED=true`, faire un checkout Solo mensuel et Business annuel avec la carte 4242…, puis un upgrade via le portail, un échec de paiement (carte 4000 0000 0000 0341) et un rattrapage.
3. Suivre `usage_monthly.ai_cost_micros` et `usage_events` (`ai_budget_reached`) pour recaler `AI_PRICE_TABLE`.
4. Sur autorisation explicite : clé live + `STRIPE_LIVE_ALLOWED=true`.

## Tests

`cd backend && python -m pytest tests/test_commercial_offer.py -n 0` → 30 tests (catalogue, Enterprise sans prix,
limites, idempotence, comptes d'organisation, checkout sandbox simulé, formulaire, anti-spam, débit, webhooks).
Non-régression : les suites existantes touchant facturation/accès/projets/plans donnent le même ensemble d'échecs avant
et après (échecs préexistants : tests nécessitant un serveur et une base en direct).

## Retour arrière

* Immédiat, sans redéploiement : `PLAN_LIMITS_MODE=observe` (mesure sans blocage) ou `off`, `COMMERCIAL_CHECKOUT_ENABLED=false`.
* Code : revenir au commit précédent de `main`. Les données ajoutées (`plans` `cp_*`, `usage_monthly`, `usage_events`,
  `commercial_leads`, `billing_audit`, `stripe_events`) sont additives ; les supprimer est facultatif.
* Aucun abonnement existant n'est modifié par cette branche.

## Points restant à valider (non faits volontairement)

* Paiement réel, prix Stripe live, Stripe Tax (inscriptions TVA) — autorisation requise.
* Plusieurs fonctions Enterprise sont marquées « Bientôt » (multi-entités, API entreprise, ERP).
* Facturation électronique au Portugal : le module actuel est Factur-X (norme française) ; au Portugal, un logiciel de facturation doit être certifié par l'AT.
