# ConstruPilot — CHANGELOG

## Itération 90 — 15/06/2026 (Claude Opus 4.8 sur le Coach IA)

### 🤖 Intégration Claude Opus 4.8
- Le **Coach IA (chat travaux)** utilise désormais **Claude Opus 4.8** (`anthropic` /
  `claude-opus-4-8`) via emergentintegrations + `EMERGENT_LLM_KEY` (clé universelle, aucune
  clé à fournir).
- `engines/ai.py` : ajout `CHAT_PROVIDER/CHAT_MODEL` + `_chat()` accepte un override
  provider/model ; `stream_chat()` (Coach) passe sur Claude. Les autres fonctions IA
  (analyse Smart Project, conseils) restent sur gpt-5.5 (inchangées).
- Testé : endpoint `POST /api/chat` renvoie bien un flux SSE Claude en streaming.

### ⚠️ Production
- Nécessite un **redéploiement** (Deploy) pour www.construpilot.fr.

---

## Itération 89 — 15/06/2026 (Revue de code — correctifs sûrs)

### 🧹 Nettoyage lint (code de production)
- Supprimé 2 imports inutilisés `require_pro_business` (`plans_render.py`, `plans_crud.py`,
  suite à l'ouverture de l'accès Plan) et 1 variable inutilisée `existing` (`documents.py`,
  l'appel `_get_owned` reste comme garde d'ownership). **`ruff --select F,E9` = 0 erreur.**

### ℹ️ Points de revue analysés = faux positifs (aucune action)
- « Secrets en dur » : `plans_pc.py:529` = `"pcs_" + secrets.token_hex(8)` (jeton aléatoire) ;
  fichiers de test = jetons de test (fixtures). Pas de vrai secret.
- « 32 variables non définies » : `ruff F821 = 0`.

### ⏭️ Volontairement non fait (risqué / cosmétique)
- Refactors de complexité (`pc_export.py`, `pc_study.py`, `estimation.py`) — sprint dédié.
- `is`→`==` : uniquement dans des fichiers de test.
- Réduction d'imports des routes — refactor architectural.

---

## Itération 88 — 15/06/2026 (Visite guidée d'accueil multilingue)

### 🌍 OnboardingTour traduit (7 langues)
- Nouveau bloc `ONB_TRANSLATIONS` (16 clés `onb.*`) + refactor `OnboardingTour.jsx`
  (STEPS → clés `s1..s4`, rendu via `t()`). Étapes, titres, corps, CTA, « Passer le tour »,
  « Suivant », « Terminer » suivent la langue.
- Vérifié (screenshot) : visite guidée en Allemand.

### ⏳ Reste à faire
- CRM clients + éditeur devis/factures + libellés PDF (7 langues).
- Vue résultats Estimateur (`EstimationView`) + dialogues.
- Emails (reset, relances, 2FA) dans la langue du destinataire.

### ⚠️ Production
- Nécessite un **redéploiement** (Deploy) pour www.construpilot.fr.

---

## Itération 87 — 15/06/2026 (Tableau de bord multilingue)

### 🌍 Dashboard traduit (7 langues)
- Nouveau bloc `DASH_TRANSLATIONS` (fusionné dans `TRANSLATIONS`) : ~32 clés `dash.*`.
- `Dashboard.jsx` câblé : bandeau (Espace client / Bonjour / statut du plan), boutons
  (Passer Premium, Nouvelle estimation), 4 statistiques, 4 onglets (Projets / Devis analysés /
  Alertes prix / Demandes), états vides, cartes projet (Ouvrir, lots terminés), alertes
  (Seuil, Objectif atteint / En surveillance), et toast « Projet supprimé ».
- Vérifié (screenshot) : Dashboard en Allemand (Hallo, Meine Projekte, Neue Schätzung…).

### ⏳ Reste à faire
- Composant `OnboardingTour` (fenêtre d'accueil) encore en français.
- CRM clients, éditeur devis/factures + libellés PDF (7 langues).
- Emails (reset, relances, 2FA) dans la langue du destinataire (stocker `user.lang`).

### ⚠️ Production
- Nécessite un **redéploiement** (Deploy) pour www.construpilot.fr.

---

## Itération 86 — 15/06/2026 (Menu / navigation multilingue complet)

### 🌍 Navigation entièrement traduite (7 langues)
- Nouveau bloc `NAV_TRANSLATIONS` (fusionné dans `TRANSLATIONS`) : `nav.more`, `nav.start`,
  `nav.admin`, `nav.reviews`, `nav.clients`, `nav.library`, `nav.studies`, `nav.account`.
- `Nav.jsx` : « Plus » → `t("nav.more")`, « Commencer » → `t("nav.start")`, « Admin »,
  bouton rapide « Suivi devis », et **USER_LINKS** (Suivi devis, Avis clients, Clients,
  Bibliothèque, Études PC, Équipe, Parrainer, Mon compte) dotés de clés `key` et rendus via
  `t()` (menu déroulant desktop + menu mobile).
- Vérifié (screenshot) : nav en Allemand (« Mehr », « Loslegen », liens traduits).

### ⏳ Reste à faire
- Tableau de bord, CRM clients, Facturation (7 langues).
- Emails (reset, relances, 2FA) dans la langue du destinataire.
- Widget 3D de la page d'accueil (labels « Hauteur murs », « Reset », « Vue dessus »…).

### ⚠️ Production
- Nécessite un **redéploiement** (Deploy) pour www.construpilot.fr.

---

## Itération 85 — 15/06/2026 (Formules multilingues)

### 🌍 Localisation du contenu des formules (backend)
- Nouveau `engines/plan_i18n.py` : overlay `PLAN_I18N[lang][plan_id]` (name, tagline,
  description, badge, features) pour EN/ES/PT/IT/DE/AR (FR = valeurs DB par défaut).
- `GET /api/plans?lang=xx` applique `localize_plan()` sur chaque formule.
- Frontend `Pricing.jsx` passe la langue courante (`useI18n().lang`) et **rafraîchit au
  changement de langue** → cartes de formules entièrement traduites (nom, tagline,
  description, badge, features, boutons).
- Vérifié (screenshot) : Tarifs en Anglais (Free/Project Pass/Premium… + features EN),
  et API en Arabe.

### ⏳ Reste à faire (prochaines passes)
- Vue résultats Estimateur (`EstimationView`) + dialogues (Lead/Email PDF).
- Tableau de bord, CRM clients, Facturation.
- Emails (reset, relances, 2FA) dans la langue du destinataire.

### ⚠️ Production
- Nécessite un **redéploiement** (Deploy) pour www.construpilot.fr.

---

## Itération 84 — 15/06/2026 (i18n : Estimateur + sélecteur Login)

### 🌍 Traduction
- **Estimateur (`Estimator.jsx`) entièrement traduit** dans les 7 langues (FR/EN/ES/PT/IT/DE/AR) :
  titre, sous-titre, étapes (Projet/Bâtiment/Finitions), tous les labels de formulaire,
  placeholders, boutons (Retour/Continuer/Créer/Enregistrer/PDF), états (`est.cond.*`),
  types de bâtiment (`est.bt.*`), et toutes les notifications (calcul, PDF, sauvegarde, import Coach).
  Nouveau bloc `EST_TRANSLATIONS` fusionné dans `TRANSLATIONS`.
- **Sélecteur de langue ajouté sur la page Login** (`LangToggle`), utile pour les visiteurs
  arabophones (la page Login n'a pas la nav globale).
- Vérifié (screenshot) : Estimateur en Allemand.

### ⏳ Reste à faire (prochaines passes)
- **Vue résultats de l'Estimateur** (`EstimationView.jsx`) et dialogues associés
  (LeadDialog, EmailPdfDialog…) : encore en français.
- **Localisation des formules en base de données** (noms/descriptions/features des plans) :
  NON FAIT ce tour-ci — nécessite un mécanisme backend (`/api/plans?lang=`) + traduction du
  contenu des ~8 plans × 7 langues. À planifier.
- Autres pages (Dashboard, CRM, Facturation, Plan 2D/3D…) = phases suivantes.

### ⚠️ Production
- Nécessite un **redéploiement** (Deploy) pour www.construpilot.fr.

---

## Itération 83 — 15/06/2026 (i18n Phase 2 : Arabe/RTL, auto-détection, Login/Compte/Tarifs + brevet)

### 🌍 Traduction Phase 2
- **7ᵉ langue : Arabe (ar)** avec **mise en page RTL** (`document.documentElement.dir=rtl`
  pour `ar`). Sélecteur : FR/EN/ES/PT/IT/DE/AR.
- **Détection auto de la langue** du navigateur au 1ᵉʳ passage (`navigator.languages`),
  mappée sur les langues supportées, sinon FR (`I18nContext.detectLang`).
- **Pages entièrement traduites (7 langues)** : Login, Compte (page + bannière mot de
  passe provisoire), Tarifs (titres, onglets, cartes, boutons, notifications, encarts).
  Nouveau bloc d'augmentation `PAGE_TRANSLATIONS` (clés `login.*`, `account.*`, `pricing.*`)
  fusionné dans `TRANSLATIONS`.
- Testé (screenshots) : Login AR (RTL + textes), Tarifs AR (RTL + textes).
- ⏳ Reste : Estimateur (+ vue résultats `EstimationView`) et autres pages/dialogues =
  phases suivantes. Les **noms/features des formules** proviennent de la DB (contenu backend)
  → localisation backend distincte à prévoir.

### ⚖️ Mentions légales
- Pied de page global (`Nav.jsx Footer`) : **« © {année} ConstruPilot — Tous droits réservés ·
  Brevet n° FR261104 »** (visible sur toutes les pages via Shell).

### 💶 Correctif tarif
- Encart Tarifs : Project Pass « 19,90 € » → **50 €** (aligné sur le nouveau prix).

### ⚠️ Production
- Nécessite un **redéploiement** (Deploy) pour www.construpilot.fr.

---

## Itération 82 — 15/06/2026 (Coach→Estimateur + i18n Phase 1)

### 🔗 Copilot Travaux → Estimateur (avec extraction IA)
- Nouveau bouton **« Chiffrer ce projet dans l'estimateur »** dans le Coach IA
  (`Coach.jsx`), visible dès qu'il y a une demande client.
- Au clic : appel `POST /api/estimation/analyse` (IA `analyse_description`) sur la
  concaténation des messages utilisateur → extraction **type de travaux + surface +
  finition + état + lots + résumé**, stockée en `sessionStorage.estimator_prefill`,
  puis navigation vers `/estimation?from=coach`.
- `Estimator.jsx` lit le pré-remplissage au montage et remplit le formulaire
  (type, surface, bâtiment, finition, état, description) + toast de confirmation.
- Testé e2e (screenshot) : « Rénovation 70 m² Paris » → Estimateur pré-rempli
  (type « Rénovation appartement », surface 70).

### 🌍 Traduction — Phase 1 (i18n)
- **2 nouvelles langues ajoutées : Italien (IT) + Allemand (DE)** → le sélecteur propose
  désormais FR/EN/ES/PT/IT/DE (`I18nContext.jsx` LangToggle).
- Blocs `it` et `de` complets pour toutes les clés déjà existantes
  (nav, common, quote, team, landing).
- **Page Coach IA entièrement traduite** dans les 6 langues (titre, sous-titre,
  message d'accueil, 6 exemples, placeholder, boutons, barre estimateur, toasts,
  erreurs micro) via nouvelles clés `coach.*`.
- Vérifié (screenshot) : bascule DE/IT sur `/coach` (nav + exemples + placeholder traduits).
- ⏳ **Reste à faire (Phases 2+)** : traduction propre des ~38 autres pages, dialogues et
  notifications (Estimateur, Tarifs, Connexion/Compte, Tableau de bord, CRM, Facturation,
  Plan 2D/3D…). Arabe (RTL) possible ultérieurement (nécessite mise en page dédiée).

### ⚠️ Production
- Nécessite un **redéploiement** (bouton Deploy) pour appliquer sur www.construpilot.fr.

---

## Itération 81 — 15/06/2026 (Facturation 3D à l'unité + Project Pass 50 €)

### 💳 Project Pass 50 € + achats 3D à l'unité (option a : Plan ouvert à tous)
- **Project Pass** : 19,90 € → **50 €**, inclut **3 rendus 3D offerts** (quota `free_renders_3d: 3`).
- **Produits à l'unité** (nouveaux plans `one_time`, audience `addon`) : `render_credit_3d` (5 €),
  `video_credit_3d` (10 €), `mockup_credit_3d` (5 €). Synchronisés dans Stripe via
  `ensure_stripe_catalog`.
- **Accès Plan 2D ouvert à tous les connectés** : retrait du gate `require_pro_business` sur
  `plans_crud` (upload/duplicate) + retrait des features `plan_takeoff`/`render_3d` du gating
  Pro Business dans `BillingContext`.
- **Contrôle 3D par action** (`engines/monetization.py`) :
  - `resolve_3d_access(user, kind)` → `unlimited` (admin/pro/pro_business) · `free` (Project Pass,
    render only, 3 offerts) · `credit` · `denied`.
  - `require_3d_access` lève **402** avec detail structuré `{error:'credit_required', kind,
    price_cents, price_eur, credit_plan_id, message}`.
  - `consume_3d` : `$inc render3d_free_used` (offert) ou `$dec credits_3d.<kind>` (crédit).
  - `credits_3d_summary` → endpoint `GET /api/billing/credits-3d`.
  - `_mark_paid` : un paiement d'un produit crédit incrémente `users.credits_3d.<kind>`
    (sans changer le plan actif).
- **Gating endpoints** (`plans_render.py`) : `render-3d` (kind render), `render-video`
  (kind video), nouveau `POST /{plan_id}/interactive-3d` (kind mockup, déblocage par plan,
  ré-ouverture gratuite via `interactive_unlocks`).
- **Frontend** : compteur `credits-3d-counter` (offerts + crédits + tarifs), paywall
  `credit-paywall` (402 → bouton « Acheter (X €) » → checkout Stripe), bouton « Maquette
  interactive » passe par le déblocage backend. `PlanTakeoff` gère le 402 sur render/vidéo/maquette.

### Tests (auto-testés backend)
- `resolve/consume/summary` + `_mark_paid` crédit validés en Python.
- API : `GET /billing/credits-3d` (free=0/pro_business=unlimited), `render-3d` free → **402**
  structuré. Plans DB : Project Pass 5000 (free_renders_3d 3), crédits 500/1000/500.
- UI : dialog 3D + compteur « illimité » (admin) OK (screenshot).
- ⚠️ Le paiement Stripe réel (carte) n'est pas testable automatiquement en preview ; le crédit
  est bien accordé au retour de checkout via `/billing/status` (sync_status → _mark_paid).

---

## Itération 80 — 15/06/2026 (Tarifs + Correctifs Auth + Admin info@)

### 💰 Nouveaux tarifs abonnements
- Premium : 9,99 € → **19 €/mois** · annuel 79 € → **190 €/an** (~17 %).
- Pro : 99 € → **199 €/mois** · annuel 990 € → **2100 €/an** (~12 %).
- Pro Business : 299 € → **350 €/mois** · annuel 2990 € → **3500 €/an** (~17 %).
- Source de vérité : `server.py::seed()` → `PRICE_MIGRATION` (force les montants à chaque
  démarrage, idempotent) + `YEARLY_COPY` (recalcule les % d'économie affichés).
  `monetization_catalog.py` mis à jour pour cohérence (nouveaux montants + taglines).
- Front `/tarifs` lit `amount_cents` via `GET /api/plans` → propagation auto. Fixé le SEO
  obsolète « dès 39 €/mois » → « Premium dès 19 €/mois ».
- ⏳ **EN ATTENTE (non implémenté)** : Project Pass 19,90 € → **50 €** (3 rendus 3D offerts),
  puis achats à l'unité (rendu 3D 5 €, vidéo 3D 10 €, maquette interactive 5 €), illimités
  pour Pro/Pro Business. Mécanique de facturation à l'unité à développer.

### 🔐 Correctifs Authentification (comptes Google)
- **`change-password`** : `current_password` devient optionnel. Un compte Google (sans
  `password_hash`) peut désormais **définir** un mot de passe sans ancien mot de passe.
  Un compte avec mot de passe exige toujours l'ancien. (routes/auth.py)
- **`forgot-password`** : ne bloque plus les comptes Google — le lien de reset est envoyé
  à tout compte existant (permet de définir un mot de passe). Copie email adaptée
  (« définir » vs « réinitialiser »). Anti-énumération conservée.
- **`_public`** expose `has_password` → le front `/compte` (`PasswordForm.jsx`) affiche
  « Définir un mot de passe » (sans champ ancien mot de passe) pour les comptes Google.
- **Root cause « identifiants incorrects »** : compte Google = pas de mot de passe → le
  login email/mot de passe échouait toujours. Résolu en permettant de définir un mot de passe.

### 👤 Admin secondaire info@construpilot.fr
- Seed idempotent dans `server.py::seed()` (hors `SEED_DEMO_DATA`) : crée/​promeut
  `info@construpilot.fr` en `role=admin`. Override via `SECOND_ADMIN_EMAIL` /
  `SECOND_ADMIN_PASSWORD`. Mot de passe provisoire `CP-Admin-2026!` (`must_change_password`).
- Accès complet à `/admin` (Prix, Coeff, Fournisseurs, Utilisateurs, Projets, CRM/Devis,
  Codes promo, KYC, Affiliation, Plans & Revenu, Revenue Cockpit, Demandes, Erreurs client).

### Tests (auto-testés par l'agent principal)
- Login `info@construpilot.fr` → role admin, /admin rendu complet (screenshot).
- Compte Google : set-password sans ancien mot de passe → 200, puis login email OK.
- `forgot-password` compte Google → crée bien un token de reset.
- Prix `/api/plans` conformes (Premium 1900/19000, Pro 19900/210000, ProBusiness 35000/350000).
- ⚠️ Ces changements doivent être **redéployés** pour s'appliquer sur www.construpilot.fr (prod).

---

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

### Étape 3 — Éditeur de devis (livrée le 15/06)
- Backend : modèle **générique** `pro_documents` (doc_type quote|invoice|credit_note) + compteurs
  `doc_counters` (numérotation DEV-2026-0001). `routes/documents.py` : CRUD, `from-plan/{id}`
  (import du métré IA en devis éditable), `/issue`, `/status`, `/pdf`. Totaux serveur : HT,
  TVA **multi-taux** (10/20/5,5 %), TTC, **acompte**. `engines/pdf_docs.py` : PDF devis/facture/avoir.
- Frontend `QuoteEditor.jsx` (`/devis-editeur` + `/devis-editeur/:docId`) :
  - Devis vide, sélection client, titre, statut (brouillon/envoyé/signé/refusé).
  - Lignes éditables (désignation/qté/unité/PU HT/TVA), ajout **depuis la bibliothèque** (picker),
    **auto-enregistrement** des nouvelles lignes libres dans la bibliothèque.
  - Récap live (HT, TVA par taux, TTC, acompte, reste à régler), export PDF.
  - **Modifiable à tout moment** (même après envoi/signature).
- Enchaînements : bouton « Créer un devis » (Suivi devis), « Devis » sur chaque fiche client
  (`?client=`), et **plan → fiche client → devis pré-rempli** (`?plan=&client=`) depuis PlanTakeoff.
- Testé : from-plan (4 lignes, TTC 7807,80 €), CRUD, PDF (DEV-2026-0001, multi-TVA, acompte),
  auto-save biblio, UI (TTC 573 € multi-taux) via curl + screenshot.

### Étape 4 — Factures, avoirs, paiements & page client (livrée le 15/06)
- Backend `routes/documents.py` :
  - `POST /{quote_id}/to-invoice` (mode **total / prorata / acompte / détaillé**). Le mode
    **acompte** reprend le % d'acompte du devis (ex : 30 %) + mention réglementaire.
  - `POST /{invoice_id}/to-credit-note` (avoirs, numérotés AV-2026-xxxx).
  - `POST /{doc_id}/payments` + `DELETE .../payments/{id}` : suivi des règlements
    (statut auto partial/paid, reste dû).
  - `GET /client-summary/{client_id}` : KPIs (CA signé, facturé, encaissé, reste à facturer,
    reste à régler) + devis/factures/avoirs.
- Frontend :
  - Page **`/clients/:clientId`** (`ClientDetail.jsx`) : KPIs, sections Devis signés /
    Factures (avec paiements) / Avoirs / devis refusés, dialogues « Facturer » (acompte 30 %
    pré-rempli) et « Enregistrer un paiement ».
  - Fiche client cliquable → page détaillée. Numérotation FAC-2026-xxxx.
  - `QuoteEditor` généralisé (devis / facture / avoir) : édition possible même après émission.
- Testé (curl) : conversion total/prorata 40 %/acompte 30 % (FAC-2026-0002, 3300 €),
  paiement partiel (statut Partiel), avoir, synthèse client ; UI validée par screenshots.

### Reste à faire (roadmap Suite Pro)
- Étape 5 — Certifications (Qualibat, RGE, QualiPAC, Qualifelec, Qualibois) + branding avancé
  (logos affichés sur devis / factures / avoirs PDF).
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
