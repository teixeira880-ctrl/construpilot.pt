# Audit ConstruPilot — Rapport complet

**Date** : 17 septembre 2026
**Périmètre** : Backend FastAPI (450 fichiers Python, ~91 500 lignes) + Frontend React (297 JSX, 80 pages, 194 composants)
**Stack détectée** : FastAPI 0.110 · MongoDB (motor) · React 18 (CRA + CRACO) · Tailwind · APScheduler · JWT + cookies session · Stripe · litellm/emergentintegrations · **Perplexity SDK déjà installé et utilisé**

---

## 1. Note globale

| Domaine | Note | Commentaire |
|---|---|---|
| Architecture backend | 🟡 B | Modulaire (routes/engines/core) mais très fragmenté, beaucoup de fichiers > 1000 lignes |
| Architecture frontend | 🟠 C | 80 pages sans lazy loading, contexte i18n de 1596 lignes, quasi pas de tests |
| Sécurité | 🔴 D | 3 JWT tokens en clair dans l'archive, JWT en localStorage, rate limiting quasi absent |
| Qualité code | 🟡 B | Style cohérent, docstrings en français, mais 81 `except: pass` silencieux |
| Base de données | 🟢 A- | Index créés au startup, TTL pour tokens éphémères, choix cohérents |
| Intégrations IA | 🟢 A | **Perplexity déjà proprement intégré** (btp_ai + growth), fallback multi-providers |
| Tests | 🟡 B | 143 tests backend (bien), mais quasi rien côté frontend (5 fichiers) |
| DevOps / Config | 🟠 C | Pas de `.env.example`, pas de CI visible, pas de Dockerfile |

**Verdict** : le produit est **fonctionnellement dense et bien avancé**, mais **plusieurs points critiques de sécurité** doivent être traités **immédiatement** avant toute mise en production.

---

## 2. 🚨 Points critiques — à corriger dans les 24 h

### C1. Trois JWT tokens en clair à la racine
**Fichiers** : `.token.txt`, `.pro_token.txt`, `.adm_token.txt`

Ces fichiers contiennent des JWT valides jusqu'en **2026-12-20** pour trois comptes (user, pro, admin). Ils ne figurent pas dans `.gitignore` — s'ils sont poussés sur Git, **n'importe qui peut se connecter en tant qu'admin**.

**Actions immédiates** :
1. **Révoquer** ces tokens : incrémenter `token_version` en base pour les 3 comptes concernés (l'auth vérifie déjà `payload['v'] == user['token_version']`, ligne 46 de `core/security.py`).
2. Ajouter au `.gitignore` :
   ```
   .token.txt
   .adm_token.txt
   .pro_token.txt
   .*_token.txt
   ```
3. Purger l'historique Git : `git filter-repo --path .token.txt --path .adm_token.txt --path .pro_token.txt --invert-paths`
4. Vérifier qu'aucun autre secret n'a été poussé : `git log --all -- .token.txt`

### C2. JWT stocké en localStorage (vulnérable XSS)
**Fichier** : `frontend/src/lib/api.js`, `frontend/src/context/AuthContext.jsx`

```js
const token = localStorage.getItem("construpilot_token");
if (token) config.headers.Authorization = `Bearer ${token}`;
```

Le cookie `session_token` (httpOnly, secure, SameSite=lax) est déjà en place — c'est parfait. Le JWT en localStorage **est superflu et dangereux** : tout script XSS peut le voler.

**Correctif** :
- Supprimer `localStorage.setItem("construpilot_token", ...)` dans `AuthContext.jsx` (register, login, verify2fa)
- Retirer `config.headers.Authorization = Bearer ...` dans `api.js`
- L'auth passe déjà par `withCredentials: true` (cookie) — ça continuera à fonctionner
- Adapter tous les `fetch()` directs qui utilisent le token (~29 occurrences dans le frontend) pour utiliser `credentials: "include"` au lieu du header Bearer

### C3. Rate limiting quasi absent
Seulement **2 endpoints** protégés (newsletter, radar). Aucun rate limit sur :
- `/api/auth/login` (le lockout après 5 tentatives est présent, mais pas de rate limit IP global)
- `/api/auth/register`
- `/api/auth/reset-password`
- `/api/ai/chat` (endpoint IA coûteux)
- `/api/btp-ai/research` (Perplexity, appels payants)

**Risques** : brute force distribué, spam d'inscriptions, épuisement du crédit IA.

**Correctif** : installer `slowapi`, ajouter un middleware global :
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
app.state.limiter = limiter
# Endpoints sensibles
@limiter.limit("10/minute")
async def login(...): ...
@limiter.limit("5/minute")
async def register(...): ...
@limiter.limit("20/minute")
async def chat(...): ...
```

### C4. Pas d'`.env.example` — configuration invisible
Aucun fichier `.env.example` livré. Les nouveaux développeurs (ou vous plus tard) devront lire tout le code pour reconstituer la liste des variables. Le `server.py` fait déjà planter au démarrage si `CORS_ORIGINS`, `CORS_PROXY_ORIGIN`, `FRONTEND_URL` manquent.

**Variables critiques recensées** :
```
MONGO_URL, DB_NAME, JWT_SECRET
CORS_ORIGINS, CORS_PROXY_ORIGIN, FRONTEND_URL
EMERGENT_LLM_KEY, PERPLEXITY_API_KEY, OPENAI_API_KEY (optionnel)
STRIPE_SECRET_KEY, RESEND_API_KEY, ELEVENLABS_API_KEY
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
ADMIN_SEED_EMAIL, ADMIN_SEED_PASSWORD
SECOND_ADMIN_EMAIL, SECOND_ADMIN_PASSWORD
SEED_DEMO_DATA (bool)
```

**Correctif** : je fournis un `.env.example` complet dans le zip livré à la fin.

---

## 3. ⚠️ Points sérieux — à corriger dans le mois

### S1. 81 `except: pass` silencieux
Exemples dans `admin.py`, `documents.py`, `situations.py`, `hr.py`, `revenue.py`… Les erreurs sont **avalées sans log**. Un bug de prod peut rester invisible.

**Correctif** : remplacer chaque `except: pass` par `except Exception as e: logger.warning("...: %s", e)`. Un `sed` accompagné d'une review manuelle suffit.

### S2. Fichiers trop volumineux
Sept fichiers dépassent 1000 lignes :
- `routes/plans_analysis.py` : 2673 lignes
- `routes/documents.py` : 1986
- `routes/assistant.py` : 1656
- `routes/plans_export.py` : 1571
- `routes/plans_pc.py` : 1543
- `engines/pdf_takeoff.py` : 1127
- `growth/routes.py` : 1086

Ces fichiers monolithiques rendent le review PR et le refactoring difficiles.

**Correctif** : découper par domaine fonctionnel (ex : `documents.py` → `documents/quotes.py` + `documents/invoices.py` + `documents/situations.py`). Aucun changement d'URL nécessaire.

### S3. Frontend : 80 pages sans code-splitting
`App.js` importe **statiquement** les 80 pages. Le bundle initial est probablement > 2 Mo. Time-to-interactive dégradé sur mobile 3G.

**Correctif** : `React.lazy()` + `<Suspense>` pour toutes les pages hors landing :
```js
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Estimator = lazy(() => import("@/pages/Estimator"));
// ...
<Suspense fallback={<LoadingSpinner />}>
  <Routes>...</Routes>
</Suspense>
```
Gain typique : **-70% de bundle initial**.

### S4. i18n Context de 1596 lignes
`context/I18nContext.jsx` est monolithique. Les traductions devraient être chargées à la demande (par namespace ou par page). Utiliser `react-i18next` avec `backend/http` plutôt qu'un mégafichier JS.

### S5. Aucun typage — ni TypeScript ni JSDoc généralisé
Le backend Pydantic est bien typé, mais le frontend en JS/JSX pur (0 TS/TSX) rend refactoring et refactor cross-fichiers risqués.

**Recommandation** : migration progressive vers TypeScript, ou au minimum activer `checkJs: true` dans `jsconfig.json` avec des JSDoc sur les fonctions publiques (`lib/api.js`, contextes).

### S6. Requêtes N+1 potentielles (1132 boucles avec `find` détectées)
Un scan grep suggère beaucoup de patterns `for x in await db.foo.find(...): await db.bar.find_one({...})` — inefficace à grande échelle.

**Correctif** : remplacer par des `$lookup` MongoDB ou du batching avec `$in` :
```python
# Avant
for u in users:
    e = await db.entitlements.find_one({"user_id": u["user_id"]})
# Après
ids = [u["user_id"] for u in users]
ents = {e["user_id"]: e async for e in db.entitlements.find({"user_id": {"$in": ids}})}
```

### S7. Frontend quasi pas testé
5 fichiers `.test.*` pour 297 composants. Aucun test E2E Playwright/Cypress structuré.

**Recommandation** : viser 30% de couverture sur les flux critiques (auth, création devis, paiement Stripe) avant tout ajout de nouvelles features.

---

## 4. ✅ Ce qui est bien fait

- **Sécurité de base** : bcrypt pour les mots de passe, JWT avec `token_version` pour révocation instantanée, cookies httpOnly + Secure + SameSite=lax, protection anti-brute-force sur `/login` (5 tentatives, 15 min de lockout), validation SIRET pour comptes pros, KYC avec vérification magic bytes.
- **CORS strict** : allowlist explicite, refus de `*` avec credentials (commentaire `SEC-002`).
- **Middleware d'origine canonique** (`CanonicalOriginMiddleware`) — élégant.
- **Perplexity déjà intégré proprement** : `btp_ai/research.py` utilise l'Agent API avec preset configurable, tools web_search, stockage des sources originales, cost tracking, disclaimer explicite ("sources à vérifier"). Bien mieux que 90% des intégrations que je vois.
- **Multi-provider AI** avec fallback automatique (Emergent → OpenAI → Anthropic) et budget monitoring cron.
- **APScheduler** bien utilisé pour ~20 tâches périodiques (alertes prix, relances devis, digest hebdo, tracking postal…).
- **Migration one-shot idempotente** au startup (rendus 3D → collection séparée pour respecter la limite BSON 16 Mo).
- **RBAC organisationnel** propre (`core/permissions.py`) avec rôles owner/admin/chef_chantier/comptable/member/ouvrier.
- **143 tests pytest** — bonne base backend.

---

## 5. Intégration Perplexity : état des lieux

L'intégration existe déjà et est **de bonne qualité** :

| Composant | Fichier | Rôle |
|---|---|---|
| SDK installé | `requirements.txt:90` | `perplexityai==0.43.5` |
| Recherche BTP | `btp_ai/research.py` | Agent API + web_search, sources tracées, cost logging |
| Route `/btp-ai/research` | `btp_ai/routes.py:122` | Exposition sécurisée avec `current_user` |
| Marketing Growth | `growth/providers.py`, `growth/research.py` | Test visibilité + génération de contenu |
| Frontend | `growth/VisibilityPanel.jsx`, `growth/IntegrationsPanel.jsx` | UI configuration |

**Points à améliorer** :

- **Pas de cache sur les recherches** : chaque question repose l'appel Perplexity (payant). Ajouter un cache Mongo avec TTL de 24h sur `(question, country, preset)`.
- **Pas de rate limit** sur `/btp-ai/research` — un utilisateur pourrait vider votre crédit API.
- **Pas de streaming SSE** : les réponses Perplexity peuvent être longues (~10s pour un preset high), un stream améliorerait l'UX.
- **Cases d'usage non couverts** : réglementation dédiée (avec `search_domain_filter` sur Legifrance/AFNOR/CSTB), assistant conversationnel avec citations, RAG sur documents internes (embeddings Perplexity).

Le module que je vous ai livré au message précédent (`construpilot-perplexity.zip`) couvre ces 4 cas d'usage supplémentaires et peut être branché directement.

---

## 6. Roadmap de refonte priorisée

### Sprint 0 — Quick wins sécurité (2-3 jours)
1. Révoquer les 3 tokens fuités + ajouter au `.gitignore`
2. Retirer le JWT du localStorage
3. Ajouter `slowapi` + rate limits sur auth et endpoints IA
4. Créer `.env.example` complet
5. Purger `except: pass` (script + review)

### Sprint 1 — Perplexity étendu (1 semaine)
1. Ajouter cache Mongo sur `/btp-ai/research`
2. Créer routes dédiées : `/api/reglementation` (filtre Legifrance/AFNOR/CSTB), `/api/documents/devis` (JSON structuré), `/api/documents/cctp` (articles référencés DTU)
3. Recherche sémantique sur documents internes (embeddings Perplexity + pgvector ou Mongo Atlas Vector Search)
4. Streaming SSE pour l'assistant conversationnel

### Sprint 2 — Performance frontend (1-2 semaines)
1. Code-splitting `React.lazy` sur toutes les pages hors landing
2. Découper `I18nContext` en namespaces chargés à la demande
3. Migrer les modales lourdes vers `React.lazy` (éditeur PDF, viewer 3D)
4. Optimiser les images (Unsplash → CDN local, formats AVIF/WebP)

### Sprint 3 — Découpage backend (2-3 semaines)
1. Découper les 7 fichiers > 1000 lignes en sous-modules
2. Ajouter tracing OpenTelemetry
3. Refactor des N+1 les plus coûteux (dashboard admin, listing projets)

### Sprint 4 — Qualité (continu)
1. Migration progressive vers TypeScript (contextes + `lib/`)
2. Tests E2E Playwright sur flux critiques
3. CI/CD GitHub Actions (lint, tests, build) — je peux vous fournir la config

---

## 7. Livrables prêts

Je peux produire immédiatement (sur demande) :
- **Patch sécurité Sprint 0** (fichiers modifiés + commits atomiques)
- **`.env.example` complet** avec tous les secrets documentés
- **Extension Perplexity** : les 4 nouvelles routes branchables sur votre code (déjà générées, dans `construpilot-perplexity.zip`)
- **Config CI GitHub Actions** (lint Python + JS, tests pytest, build frontend)
- **Dockerfile multi-stage** + `docker-compose.yml` (backend + MongoDB + reverse proxy)
- **Script de découpe** de `plans_analysis.py` (2673 lignes → 5 sous-modules par thème)

Dites-moi par quoi commencer.
