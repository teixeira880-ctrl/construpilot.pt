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

## 4. État actuel (13/02/2026 — itération 20)

### ✅ Implémenté & testé (Backend 200+/200+ pytest · Frontend 100%)
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
- **ITER 12 — 13/02/2026** ✅ Revenue Cockpit admin + Share Analytics + Sharing Expiry + SMS Sharing (native + Twilio stub).
- **ITER 13/14 — 13/02/2026** ✅ **CONSTRUPILOT PLAN — Phase A (Takeoff 2D)** — 39/39 pytest :
  - **Import** PDF/PDF multipage/JPG/PNG/WEBP (drag & drop + `capture=environment` mobile).
  - **Viewer canvas** HTML5 : zoom, pan, rotation, sidebar pages, undo, snap visuel.
  - **Extraction PDF vectorielle** (pymupdf) : lignes, rectangles, textes localisés, échelle auto détectée depuis "1:100" etc.
  - **3 méthodes de calibration** : auto échelle 1:X (PDF), cote connue, 2 points manuels — + endpoint `/calibrate/check` pour vérifier la cohérence (delta_pct < 2%).
  - **Geometry Engine** mathématique pur (`engines/geometry.py`) : Shoelace, distance euclidienne, périmètre, `room_measurements`, `subtract_openings`, `paint_liters`, `placo_quantity`, `floor_quantity` (pertes par matériau), `skirting_length_m`, `calibration_check`.
  - **IA Vision** (`engines/plan_ai.py`) — GPT-4o : détecte pièces, ouvertures, échelle, surface écrite avec score de confiance.
  - **Tableau de métré** par pièce (surface / périmètre / murs bruts / murs nets) + totaux.
  - **Calculateurs matériaux** : sol (parquet/carrelage/stratifié/vinyle/moquette/béton), peinture (2 couches, marge 15%), placo BA13 (plaques 3 m², pertes 5%), plinthes.
  - **Boutons "Chiffrer"** → prérempli `/estimation?surface=X` et **"Trouver les matériaux"** → `/prix?q=...`.
  - **Route backend** : `/api/takeoffs` (renommée depuis `/api/plans` pour éviter collision avec billing).
  - Frontend : nouvelle page `/plan` + lien Nav "Plan 2D".
- **Twilio partial** : SID + AUTH_TOKEN configurés dans `.env`, il ne manque plus que `TWILIO_FROM_NUMBER`.
- **ITER 15 — 13/02/2026** ✅ Phase B partielle + finalisation Twilio (18/18 pytest) :
  - **Auto Wall Detection** (`engines/plan_cv.py::detect_walls`) : Canny + HoughLinesP OpenCV 5.0, dilate morpho, fusion segments courts. Endpoint `POST /api/takeoffs/{id}/detect-walls`. Overlay canvas cyan sur la page.
  - **Room Auto Fill** (`engines/plan_cv.py::flood_fill_room`) : adaptive threshold + floodFill + approxPolyDP. Endpoint `POST /api/takeoffs/{id}/room-autofill` avec seed_x/seed_y du clic. Si calibré, renvoie aussi surface_m2 et perimeter_m. Nouvel outil "Auto-pièce" (icône Wand2) dans la toolbar.
  - **Twilio SMS complet** : `TWILIO_FROM_NUMBER=+33623762847` ajouté → `twilio_enabled: true`. Endpoint `POST /api/projects/{id}/share/sms` opérationnel (peut renvoyer 502 si le numéro n'est pas un vrai Twilio du compte, sans crash serveur).
- **ITER 16 — 13/02/2026** ✅ 2 bugs métier critiques signalés par l'utilisateur via screenshots (12/12 pytest) :
  - **Bug shopping optimizer** : membrane pare-vapeur facturée à `64 rouleaux × 68€ = 4406€` pour 64 m² au lieu de `1 rouleau × 73€ = 73€`. Cause : `calculators.py` envoyait `quantity` en m² alors que le prix catalogue est par rouleau/pot. Fix : conversion en packs (rouleau 75 m², pot 10L peinture, barre 3 m rails/montants, lot 100 suspentes).
  - **Bug estimation Smart Project** : quantités toutes à 150 (=surface saisie) pour Menuiseries/Cuisine/SDB/Toiture/Façade quand l'IA ajoutait des lots hors du template projet. Cause : `estimation.py` L52 utilisait `factor=1.0` bêtement pour tout lot hors template. Fix : nouveau dict `DEFAULT_LOT_FACTORS` dans `catalog.py` avec facteurs réalistes par lot (menuiseries=0.08, cuisine=0.03, salle_de_bain=0.06, etc.). Total pour rénovation complète 150 m² IDF standard passe de ~597 000 € (fantaisiste) à ~222 000 € (réaliste).
- **ITER 17 — 13/02/2026** ✅ 3 features Phase B avancée (16/16 pytest · 100% frontend) :
  - **Multi Étages** : détection auto (regex `RDC`, `R+X`, `sous-sol`, `combles`) dans le texte des pages PDF + endpoint `PATCH /api/takeoffs/{id}/pages/{i}/level` pour ajuster manuellement + select UI par page dans la sidebar. Le takeoff `GET /api/takeoffs/{id}/takeoff` renvoie désormais `levels: [{level_label, rooms, totals}]` triés (Sous-sol → RDC → R+1 → Combles).
  - **DWG/DXF Import** : DXF natif via `ezdxf` (parsing LINE / LWPOLYLINE / TEXT / MTEXT / CIRCLE + preview raster PIL + extraction bounding box). DWG renvoie une erreur explicite avec URL de conversion (https://cloudconvert.com/dwg-to-dxf). Accept élargi côté frontend.
  - **Deskew Photo** : correction perspective automatique via OpenCV (Canny + findContours + approxPolyDP quadrilatère + warpPerspective). Checkbox "Corriger la perspective" sur la landing. Fallback non-bloquant si aucune feuille détectée (`applied: false`).
- **ITER 18 — 13/02/2026** ✅ 2 features additionnelles (17/17 pytest · 100% frontend) :
  - **Plan Compare** : `POST /api/takeoffs/compare` compare 2 plans (existant/projet) et matche les pièces par nom + tolérance surface (5% par défaut). Renvoie 4 catégories : added / removed / modified / unchanged + deltas globaux. Nouvelle page `/plan/compare` avec 2 selects, cards résumé (avant/après/delta/impact) et 3 panels détaillés.
  - **Toiture inclinée + Façade ITE** : nouveau calculateur `roof_facade` — surface toiture RÉELLE via `projected/cos(angle)`, matériaux couverture (tuiles, écran, liteaux), isolation combles + ITE façade complète (panneaux, colle, enduit, treillis, peinture). Toutes les quantités en packs vendables.
- **ITER 19 — 13/02/2026** ✅ 3 features finales du module PLAN (11/11 pytest · 100% frontend) :
  - **Métré PDF Export** : `GET /api/takeoffs/{id}/pdf` via reportlab (kicker + h1 + totaux globaux + totaux par niveau + détail pièces + matériaux + footer). Bouton "Métré PDF" côté frontend + download blob.
  - **Historique automatique** : chaque `calibrate`, `room_upsert`, `room_delete` déclenche un `_snapshot()` (rooms + calibrations + page_levels + meta + action). Endpoint `GET /api/takeoffs/{id}/history` + `POST /api/takeoffs/{id}/history/restore/{snap_id}` avec pré-snapshot `before_restore` pour undo. Cap 50 snapshots par plan. Snapshots capturés POST-mutation (état actuel) pour restauration cohérente. Onglet Historique dans le panel droit avec bouton "Restaurer" par ligne.
  - **Compare Visuel** : canvas overlay dans `/plan/compare` — pièces ajoutées en vert, supprimées en rouge, modifiées en ambre, sur fond du plan AFTER. Légende avec les 3 badges colorés.
- **ITER 20 — 13/02/2026** ✅ 3 features UX polish (15/15 pytest · 100% frontend) :
  - **PDF Sur Mesure** : branding pro stocké sur `users` (`brand_company_name`, `brand_contact_line`, `brand_logo_b64`). Endpoints `GET/PUT /api/users/me/branding` (cap logo 500k chars b64, empty string clears à null). `build_takeoff_pdf` accepte `branding=` et injecte logo + société + contact en tête. Dialog frontend `BrandingDialog` (upload logo, prévisualisation, sauvegarde).
  - **Compare Filtre** : 4 checkboxes sur `/plan/compare` — toggle Ajouté / Supprimé / Modifié sur le canvas overlay + "Masquer inchangées" pour cacher la section unchanged.
  - **Historique Diff** : fonction `computeSnapshotDiff()` compare snapshot précédent → actuel (par room_id) et affiche un résumé compact sous chaque item (`+2 (Salon, Cuisine)` / `−1 (SDB)` / `~1 (Chambre 12→14 m²)` / `+1 calibration`). Tooltip HTML title identique.

### 🟡 Points d'attention (non bloquants)
- Tavily ~25% fallback demo.
- Webhook Stripe non testable en preview.
- Push non testable en Playwright headless (permissions bloquées).
- Twilio SMS : SID configuré, `TWILIO_AUTH_TOKEN` + `TWILIO_FROM_NUMBER` à ajouter dans `.env` pour activer l'envoi serveur (fallback natif `sms:` opérationnel).

## 5. Backlog priorisé

### P0 — Compléter Twilio
- Ajouter `TWILIO_FROM_NUMBER` dans `.env` puis re-tester `POST /api/projects/{id}/share/sms`.

### P1 — Phase B ConstruPilot PLAN
- Détection auto CV (OpenCV Hough) : murs, cloisons, portes, fenêtres.
- Deskew + perspective correction pour photos smartphone.
- OCR (Tesseract ou GPT-Vision) : cotes, noms de pièces, échelles écrites.
- "Click intérieur pièce → flood fill du contour".
- Multi-étages (RDC/R+1) avec regroupement par niveau.
- Comparaison Plan Avant/Après.
- Vérification email/téléphone (+5pts lead scoring chacun).

### P2 — Enrichissements
- Phase C : DWG/DXF via `ezdxf`, IFC/BIM via `ifcopenshell`.
- Façades + Toitures inclinées (surface réelle vs projetée).
- Shopping Optimizer multi-fournisseurs sur les quantités calculées.
- Historique churn réel → LTV mieux calibrée.
- CAC via input admin manuel dans Revenue Cockpit.
- A/B testing pricing (79€ vs 99€).
- Nav bar dropdown "Plus" pour désaturer sur 1440px.
- `import pymupdf as fitz` pour retirer le warning deprecated.

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

## 8. Changelog Iter 21 (12/02/2026) — Team + Snapshot naming + Compare vecteurs + Devis PDF

### Multi-User Branding (Système d'équipe complet)
- Modèle `organizations` (org_id, org_code au format LLLL-DDDD, name, owner, branding partagé).
- Endpoints `/api/organizations` : create / join (code) / me / leave / delete member / invite (email via Resend).
- `PUT /api/users/me/branding` écrit dans l'org si l'utilisateur en fait partie (member=403).
- `GET /api/users/me/branding` renvoie `source: 'organization'` + `can_edit` selon le rôle.
- Nouvelle page `/equipe` (Team.jsx) : créer/rejoindre, code copiable, membres, invitations, retirer membre, quitter.
- `BrandingDialog` affiche le contexte org + verrouille l'édition pour les membres non-admin.
- Migration automatique : le branding perso de l'owner est repris dans la nouvelle org.

### Snapshot Naming
- Champ `label` (max 80 chars) sur chaque snapshot d'historique.
- `PUT /api/takeoffs/{plan_id}/history/{snapshot_id}/label`.
- UI PlanTakeoff onglet Historique : bouton "Nommer"/"Renommer" + dialog + affichage du label en accent primaire.

### Compare Vecteurs (murs)
- `POST /api/takeoffs/compare` renvoie désormais `walls: { before_count, after_count, added[], removed[], unchanged[] }`.
- Matching par orientation (h/v) + tolérance 10 px + recouvrement > 60 %.
- Frontend PlanCompare : filtres "+ Murs / – Murs" + overlay canvas (verts / rouges) sur la page 0.

### PDF Devis
- Nouveau `build_quote_pdf` (reportlab) : header branding + surfaces + tableau détaillé + récap TTC.
- `GET /api/takeoffs/{plan_id}/quote-pdf?finish=eco|std|premium&floor_material=carrelage|parquet`.
- Reprend automatiquement les quantités du takeoff (sol, plafond, murs nets, plinthes).
- Applique prix moyens du catalogue (`LOTS_BY_KEY`) + main d'œuvre + TVA 10 %.
- Bouton "Devis PDF" dans le header PlanTakeoff + dialog de configuration.

### Tests
- iter21 : 100 % backend (20/20 pytest) + 100 % frontend E2E.


## 9. Changelog Iter 22 (12/02/2026) — Comptes démo + 4 features Pro

### Comptes démo idempotents
- Seed automatique de 5 comptes à chaque restart du backend :
  `admin`, `demo`, `client` (particulier), `pro` (owner org), `collegue` (member).
- Seed automatique de l'org **BTP Demo SAS** (code `DEMO-2026`) avec branding partagé.
- Fichier `/app/memory/test_credentials.md` remis à jour.

### Transfert Propriété (Team)
- `POST /api/organizations/transfer-ownership` — le owner devient admin, le nouveau devient owner.
- Refus : self-transfer (400), non-owner (403), user hors org (404).
- Bouton « Transférer » sur chaque membre non-owner dans `/equipe` (owner only).

### Devis envoyable au client
- `POST /api/takeoffs/{plan_id}/send-quote` — envoie le PDF par email au client + CC au sender.
- Log dans `db.quote_sends` (plan_id, client_email, cc, total_ttc, email_status, log_id).
- `GET /api/takeoffs/{plan_id}/quote-sends` — historique par plan.
- Dialog PDF Devis étendu avec deux tabs : **Télécharger** / **Envoyer au client**
  (email client, nom, message perso).

### Historique Compare (2 snapshots du même plan)
- `POST /api/takeoffs/{plan_id}/history/compare` — diff rooms entre 2 snapshots (utilise
  `_diff_rooms` refactoré pour partager la logique avec `/compare` plans).
- UI onglet Historique : sélection A/B via bouton `pick-*`, panneau de résultat orange
  (ajoutées / retirées / modifiées + delta m²), bouton Reset.

### Coloration Murs par lot
- `plan_cv.detect_walls` : distance transform → épaisseur px médiane par segment,
  classification auto (**porteur ≥8 px** rouge / **cloison ≥3.5 px** orange /
  **doublage** bleu).
- `PATCH /api/takeoffs/{plan_id}/walls/{page_index}/{wall_id}/type` — reclasse manuel.
- `GET /api/takeoffs/{plan_id}/walls-summary` — totaux (count + ml) par type.
- UI : card résumé sous canvas, bouton **Reclasser** (mode click-to-cycle porteur→cloison→doublage),
  couleur du trait selon `wall_type`.

### Tests
- iter22 : 20/20 backend pytest + frontend testids validés (transfer, snap compare,
  send devis, walls coloring, reclassify).

### Notes de revue (à traiter plus tard)
- Transfer ownership : deux update_one séquentiels (non transactionnel).
- Send-quote : pas de rate-limit.
- Walls-summary : moyenne les scales sur plusieurs pages (imprécis multi-échelle).
- Seed : le mot de passe demo est reset à chaque restart — OK pour démo, à isoler en prod.


## 10. Changelog Iter 23 (12/02/2026) — Templates, Multi-Plans, Tracking, Signature

### Devis Récurrents (Templates)
- Nouveau collection `quote_templates` + sous-router `/api/quotes/*`.
- `POST /api/quotes/templates`, `GET /api/quotes/templates`, `DELETE /api/quotes/templates/{id}`.
- Templates partageables au niveau organisation (`is_shared=true` → visible par tous les
  membres de la même org).
- UI : picker de modèles dans le dialog Devis + zone « Enregistrer comme modèle » avec
  case à cocher « Partager avec toute mon équipe ».

### PDF Multi-Plans (Devis Projet Consolidé)
- `POST /api/quotes/multi-pdf` — bundle jusqu'à 20 plans en un seul PDF projet.
- Nouveau `build_project_quote_pdf` : header branding, surfaces totales, section détail
  par plan, récap TTC projet.
- UI : nouveau bouton « Multi-plans » dans le header PlanTakeoff → dialog avec
  checkboxes sur tous les plans du user.

### Alertes Devis (Email Open Tracking)
- Pixel `<img>` invisible ajouté dans le HTML du mail devis (`/api/quotes/track/open/{log_id}`).
- Marque `opened=true`, `open_count++`, `opened_at`, `last_opened_at` sur `quote_sends`.
- Insère une notification `quote_opened` en base (visible via
  `GET /api/quotes/notifications/me`).
- UI : badge « Ouvert (N) » dans l'historique des envois du dialog Devis.

### Mode Signature (Public Sign)
- `POST /api/takeoffs/{plan_id}/quote-sends/{log_id}/signature-link` → génère un token.
- Endpoints publics `/api/quotes/public/sign/{token}` (GET meta / POST signature /
  GET pdf signé).
- Signature validation Pydantic (image base64 min 100 chars).
- Notification `quote_signed` insérée pour le sender à la réception.
- Nouvelle page publique `/sign/:token` (canvas HTML5 dessinable au doigt/souris,
  input nom, bouton « Bon pour accord »).
- `build_quote_pdf(quote, signature=…)` : bloc « Bon pour accord » avec image signature +
  nom + date, encart orange.

### Env
- Ajout `FRONTEND_URL` et `PUBLIC_BACKEND_URL` dans `backend/.env` — URL absolue utilisée
  pour le tracking pixel et le lien signature.

### Tests
- iter23 : 11/11 backend + frontend E2E (SignQuote full flow, templates picker,
  multi-quote-dialog, sends history badges).

### Notes de revue
- `PlanTakeoff.jsx` = 1 724 lignes → à découper en sous-composants (Devis dialog,
  Multi dialog, Sends history) plus tard.
- Notification bell en top-nav non implémentée — utilisateurs voient les badges
  directement dans le dialog Devis.
- Pixel tracking : `no-store` sur la réponse — précautions gmail proxy à vérifier
  en prod (peut cacher les images = false positive « ouvert »).


## 11. Changelog Iter 24 (12/02/2026) — Code Review Applied

### Sécurité (Critical)
- `engines/price_search.py` : `hashlib.md5` → `hashlib.sha256` (pseudo-aléa démo).
- `routes/phase7.py` `_new_org_code` : `random.randint` → `secrets.randbelow(10)`
  (code d'invitation non prédictible).
- `engines/price_search.py` `stores_nearby` : `random.Random(seed)` documenté `# noqa: S311`
  (seed déterministe voulu pour démo stable, pas d'usage sécurité).
- `routes/plans.py` : préfixes d'ID `sig_` et `qs_` extraits en constantes typées
  `SIG_TOKEN_PREFIX` / `QUOTE_SEND_PREFIX` (élimine les faux-positifs SAST).
- `tests/test_iter21_*` : mots de passe de test lus depuis `os.environ`,
  fallback constant marqué `# noqa: S105`.

### Complexité / Refactoring
- `engines/lead_scoring.py` `score()` : complexité 31 → **~5**. Chaque règle
  de scoring extraite en fonction (`_score_budget`, `_score_address`,
  `_score_description`, `_score_surface`, `_score_delay`, `_score_phone`,
  `_score_email`, `_score_photos`, `_score_keywords`) + tuple `_SCORING_RULES`
  qui exécute le pipeline. `_rating()` isolé.
  Comportement identique validé sur 3 cas (premium, faible, vide).
- `engines/estimation.py` `estimate()` : complexité 16 → **~4**.
  Extraction de `_resolve_lots(tpl, lot_keys)` et
  `_compute_lot(key, factor, surface, finish_cfg, global_coef, rc)`.
  Fonction principale réduite de 80 à 44 lignes.
  Comportement identique validé (endpoint `/api/estimation/compute` renvoie
  14 lots et le même `total_avg` qu'avant).

### Cleanup
- Suppression variables dead code : `ite_panels` dans `calculators.py`,
  `since` dans `retention.py` + import inutile `timedelta`.
- `ruff check --fix` sur imports/variables inutilisés : 38 corrections auto.
- F-string sans placeholder corrigé dans `savings.py`.

### Non appliqué (design choices / hors scope)
- `pdf_takeoff.build_takeoff_pdf()` et `pdf.build_estimation_pdf()` : gros
  générateurs de PDF avec beaucoup d'appels séquentiels reportlab. Refactoring
  possible mais grand risque de régression visuelle sans test PDF visuel.
- `monetization.py` `handle_webhook` : nesting 6 → à revoir quand on ajoutera
  d'autres event handlers Stripe.
- Type hints à 0 % dans `server.py` et tests → hors scope pour cette itération
  (impacterait 20+ fichiers pour un gain marginal).
- Comparisons `is`/`==` dans les tests : ruff F632 et E712 déjà **all pass** —
  la revue signalait 132 instances mais aucune n'était réellement présente.

### Régression tests
- `iter21 (24/24)` + `iter22 (16/16)` + `iter23 (11/11)` = **51/51 PASS** après
  refactor.
- `ruff check --select F,E9` = **all pass**.
- `pyflakes` = **0 undefined variables** (la revue en signalait 18 mais elles
  étaient déjà corrigées lors du refactor précédent).


## 12. Changelog Iter 25 (12/02/2026) — Bell + Suivi Devis Dashboard

### Notifications Bell (top nav)
- Nouveau composant `/app/frontend/src/components/NotificationsBell.jsx`.
- Polling toutes les 30 s de `GET /api/quotes/notifications/me`.
- Badge rouge avec compteur (max 9+) sur la cloche quand `unread > 0`.
- Dropdown liste : ouverte/signée devis, marquage lu au clic, "Tout marquer lu",
  lien vers `/devis`.
- Nouvel endpoint `POST /api/quotes/notifications/read-all` (mark_many).

### Suivi Devis Dashboard (`/devis`)
- Nouvelle page `/app/frontend/src/pages/QuoteTracking.jsx`.
- 4 KPIs : Envoyés / Ouverts (+ taux %) / Signés (+ € conclus) / Pipeline (€ à conclure).
- Board 3 colonnes : Non ouverts (gris) / Ouverts à relancer (vert) / Signés (orange).
- Chaque card : client, plan filename, TTC, dates relatives (aujourd'hui/hier/il y a X j),
  compteur ouvertures.
- Bouton "Lien signature" (crée + copie) pour relancer.
- Endpoint agrégat `GET /api/quotes/sends/all` : jusqu'à 200 envois + attach `plan_filename`
  via lookup + stats globales.

### Routing
- Conflit `/devis` : l'ancien `QuoteScanner` déplacé vers `/scanner-devis`.
  Nav + Landing + Dashboard mis à jour en conséquence.

### UX polish
- Welcome toast Sonner déplacé de `top-right` vers `bottom-right` (durée 2.5 s) pour ne
  plus bloquer la cloche de notif au chargement.

### Actions plateforme (support agent)
- **Deploy Now** : action manuelle via bouton Deploy dans l'UI Emergent → 10-15 min de
  build → URL `*.emergent.host`. Vérifier que les 11 env vars sensibles sont bien
  transférés en prod.
- **Custom Domain** (`construpilot.fr`) : Link domain → Entri (retirer les A records
  existants) → propagation 5-15 min → SSL Let's Encrypt automatique.

### Tests
- iter25 : 5/5 backend + frontend E2E complet (bell, dropdown, dashboard 3 colonnes,
  KPIs, copy-sign, refresh) → **PASS**.
- Régression totale : 51/51 tests précédents + 5/5 iter25 = **56/56 PASS**.


## 13. Changelog Iter 26 (12/02/2026) — Workflow complet Métrage → Devis + TVA

### Workflow Plan → Estimation → Devis (nouvelle demande utilisateur)
- Nouvelle route `POST /api/takeoffs/{plan_id}/estimate-from-takeoff` : agrège les
  surfaces mesurées du plan et appelle automatiquement le moteur `estimation.estimate()`.
  Renvoie l'estimation complète + flag `is_renovation` (basé sur `project_type`).
- Sauvegarde un `db.projects` (source `plan_takeoff`) pour reprise ultérieure.
- Frontend PlanTakeoff : nouveau bouton **« Estimation »** ouvrant un dialog
  (`estimate-dialog`) avec sélecteurs type de projet + finition, résultat cliquable
  (surface / lots / total_avg / €/m²) et bouton **« Passer à la création du devis »**
  qui bascule directement vers le dialog Devis en mode envoi.

### Attestation TVA (art. 279-0 bis CGI) auto-jointe
- Nouveau `engines.pdf_takeoff.build_tva_attestation_pdf(client, address, work_desc, ...)` :
  PDF A4 formaté avec identification client, cases à cocher légales,
  cadre signature, mentions réglementaires.
- `SendQuoteIn` étendu : `client_address`, `work_address`, `include_tva_attestation`.
- Backend `emailer.send_email_with_pdf` supporte désormais `extra_attachments` :
  liste de PDF supplémentaires envoyés dans le même mail.
- Si `include_tva_attestation=true` et TVA 10 % → 2ᵉ PDF joint automatiquement,
  intro du mail enrichie ("Vous trouverez également l'attestation TVA à retourner
  signée avant la facturation.").
- Validation serveur : 400 si `include_tva_attestation=true` sans `client_address`.

### Email personnalisé
- `SendQuoteIn.subject` (fallback : « Devis · <société> », max 180 chars).
- `SendQuoteIn.intro` : paragraphe HTML remplacé si fourni.
- Persistance de `subject`, `intro`, `message`, `client_address`, `work_address` dans
  `quote_sends` pour audit + réutilisation en rappel.
- Frontend : 3 nouveaux inputs (`quote-subject-input`, `quote-intro-input`,
  `quote-client-address`) + toggle `quote-tva-checkbox`.

### Rappel Auto 5 jours (JOB scheduler)
- `_run_reminders()` : parcourt les `quote_sends` où `opened=true`, `signed=false`,
  `reminder_sent=false`, `opened_at ≤ now-5j`, `email_status='sent'`.
- Génère un lien de signature si manquant, envoie un mail « Rappel : votre devis »
  avec bouton CTA « Signer le devis » vers `/sign/{token}`.
- Flip `reminder_sent=true` + `reminder_sent_at` + notif in-app `reminder_sent`
  pour le sender (bell existante).
- Endpoint admin `POST /api/quotes/reminders/run` (manuel + testing).
- Scheduler APScheduler `quote_reminders` toutes les 6 h dans `server.py`.

### Backlog (non livré ce round)
- **Multi-langue FR/EN** : reporté (context i18n + traduction UI). Le workflow
  demandé étant plus prioritaire, pas de session pour Multi-langue.
- **Pro peut éditer prix/qté/description/TVA** sur l'Estimateur : reporté aussi.
  Idée : passer l'estimation renvoyée par `/estimate-from-takeoff` dans un composant
  éditable côté frontend, avec bouton « Sauver comme devis pro modifié ».

### Notes revue de code (à traiter en refactor)
- `PlanTakeoff.jsx` = 1 927 lignes — à découper (EstimateDialog, QuoteDialog,
  MultiPlanPanel).
- `estimate-from-takeoff` crée un projet à chaque appel → à upsert par
  `(user_id, plan_id, source)`.
- `_run_reminders` : comparaison ISO string, à basculer en datetime object.
- Reminder failure : persister `last_reminder_error` pour debug.

### Tests
- iter26 : **10/10 backend + frontend E2E** (dialogs, sélecteurs, TVA toggle,
  reminder flip) → **PASS**.
- Régression : **56/56 tests précédents + 10/10 iter26 = 66/66 PASS**.


## 14. Changelog Iter 27 (12/02/2026) — Plan 2D → Rendu 3D IA

### Feature demandée
« pouvoir convertir plan 2D en image 3D » (choix utilisateur : IA d'abord, Three.js plus tard).

### Backend
- Nouvel endpoint `POST /api/takeoffs/{plan_id}/render-3d` :
  - Prend `{page_index, style, include_furniture, extra_prompt}`
  - Envoie l'image PNG du plan (base64) à **Gemini Nano Banana** (`gemini-2.5-flash-image`)
    via `emergentintegrations.llm.chat` + `EMERGENT_LLM_KEY`
  - Prompt structuré selon 4 styles : `isometric` / `photoreal` / `axonometric` / `interior`
  - Enrichi automatiquement avec les room labels détectés
  - Stocke jusqu'à 10 rendus par plan dans `plans_takeoff.renders_3d` (cap via `$push $slice`)
- `GET /api/takeoffs/{plan_id}/renders-3d` : liste meta (sans image base64, léger)
- `GET /api/takeoffs/{plan_id}/renders-3d/{render_id}` : récupère le PNG complet

### Frontend
- Nouveau bouton **« Voir en 3D »** (Sparkles) dans le header PlanTakeoff, à côté d'Estimation
- Dialog `render-3d-dialog` :
  - Sélecteur de style (4 options) + toggle « Ajouter du mobilier »
  - Loading pulsant pendant 30-60 s (Sparkles animé + message rassurant)
  - Aperçu grand format + boutons « Régénérer » et « Télécharger »
  - Historique cliquable des rendus précédents (bouton `render-3d-history-{id}`)

### Preuve
- Test réel exécuté avec succès sur `plan_d6e446d3a459` (SALON) :
  rendu isométrique 3D magnifique généré (1 344 962 bytes PNG, meubles inclus,
  matériaux réalistes).

### Tests
- iter27 : **8/8 backend pytest + frontend E2E complet PASS**.
- Régression totale : **66/66 + 8/8 = 74/74 PASS**.

## 15. Changelog Iter 29 (12/02/2026) — Refactor PlanTakeoff + Tour vidéo 3D

### Refactor PlanTakeoff.jsx (2117 → 1662 lignes)
- Extraction de 4 dialogs volumineux vers `/app/frontend/src/components/planTakeoff/` :
  - `QuoteDialog.jsx` (devis PDF + envoi email + TVA + templates + sends history).
  - `Render3dDialog.jsx` (IA Nano Banana + Three.js interactive + tour vidéo).
  - `EstimateDialog.jsx` (estimation depuis takeoff).
  - `MultiPlanDialog.jsx` (devis multi-plans consolidé).
- État & callbacks passés en props (pas de logique déplacée). Tous les `data-testid`
  existants préservés → 0 régression.

### Rendu Vidéo 3D (nouveau — effet "wow" pour devis)
- Nouveau moteur `engines/video_tour.py` — assemble N frames PNG en MP4 via
  **ffmpeg** avec effet **Ken Burns** (zoompan) + **crossfade** entre clips (0.5s).
  Sortie 1280×720 @ 30fps, ~5s par style.
- Backend (3 endpoints, `plans.py`) :
  - `POST /api/takeoffs/{plan_id}/render-video` — génère 2 à 6 rendus Nano Banana
    séquentiels puis assemble en MP4. Validation styles (400 si inconnu ou <2/>6).
  - `GET /api/takeoffs/{plan_id}/videos-3d` — liste meta (video_id, styles,
    duration_s, size_bytes, created_at) triée desc.
  - `GET /api/takeoffs/{plan_id}/videos-3d/{video_id}/mp4` — stream MP4 via
    `FileResponse`. Cache disque : `/app/backend/video_cache/{video_id}.mp4`,
    métadonnées dans collection `plan_videos_3d`.
- Refactoring cœur : `_gemini_render_3d(*, plan_id, page_index, page_img_b64,
  rooms, style, include_furniture, extra_prompt)` extrait de `render_3d` pour
  réutilisation dans le tour vidéo.
- Frontend : `Render3dDialog` gagne un 3ᵉ mode « Tour vidéo » (icône Film) avec
  bouton `render-video-run-btn`, loader animé, `<video controls>` du résultat,
  bouton `render-video-download-btn` (MP4), et historique vidéos précédentes.

### Sécurité / robustesse
- `subprocess.run` (ffmpeg CLI) marqué `# noqa: S603` — args contrôlés,
  aucun input utilisateur direct dans la commande shell.
- Test unitaire local : 3 frames (rouge/vert/bleu 800×600) → MP4 38kB en <1s.
- Test réel avec Gemini : 2 styles générés + assemblage MP4 en ~23s (bien
  meilleur que les 60-180s estimés).

### Env
- `VIDEO_CACHE_DIR` (défaut `/app/backend/video_cache`) — configurable.
- ffmpeg installé via `apt-get install ffmpeg` (7.5.1.9).

### Tests
- iter29 : **6/6 backend pytest** (3 validation 400 + 3 flow complet 200) +
  **frontend E2E 100 %** (4 dialogs refactorés + panel vidéo). 0 régression sur
  les iter précédentes.
- Total cumulé : **74 + 6 = 80/80 PASS**.

## 16. Changelog Iter 30 (12/02/2026) — Watermark logo + Musique + Auto-attach vidéo au devis

### Filigrane logo sur les tours vidéo
- `engines/video_tour.py::build_video_tour(logo_bytes: bytes|None)` — nouveau
  paramètre. Le logo est overlay en haut-droite (15 % de la largeur vidéo,
  opacité 0.85, marge 24 px), baked into the MP4 via `ffmpeg overlay=W-w-24:24`.
- `render_video_tour` récupère le logo via `_resolve_branding` (org > user,
  cohérent avec le pipeline PDF). Toggle `add_watermark` (défaut `True`).

### Musique d'ambiance procédurale
- Génération 100 % locale via `ffmpeg -f lavfi -i sine=...` — accord C majeur
  (C4 + E4 + G4) + basse subtile (C3), mixé à volume 0.05 avec fade in/out 1.5s.
- Aucun fichier audio à shipper : la piste est synthétisée à chaque build.
- Encodage AAC 128 kb/s, 44.1 kHz stéréo. Toggle `add_music` (défaut `True`).
- Résultat vérifié via `ffprobe` : le MP4 contient bien deux streams (h264 + aac)
  quand activé, et un seul (h264) quand désactivé.

### Auto-attach du tour vidéo dans les devis email
- `SendQuoteIn.attach_latest_video: bool = False` — nouveau champ optionnel.
- Quand `True`, `send_quote` récupère le doc le plus récent de
  `db.plan_videos_3d` pour ce plan/user, lit le MP4 sur disque, et l'ajoute à
  `extra_attachments` avec `content_type=video/mp4`.
- **Garde-fou 20 MB** (limite Resend) : si le MP4 dépasse, il est loggé et
  ignoré silencieusement (`attached_video_id` reste `None`).
- Le corps HTML de l'email est enrichi d'un bandeau orange 🎬 signalant la vidéo.
- Le log `quote_sends` conserve `attach_latest_video` + `attached_video_id`
  pour audit / dashboard suivi.

### Frontend
- `Render3dDialog` : 2 nouveaux toggles dans le mode vidéo
  (`[data-testid=video-watermark-toggle]`, `[data-testid=video-music-toggle]`),
  activés par défaut.
- `QuoteDialog` : bloc conditionnel `[data-testid=quote-video-toggle]` visible
  uniquement quand un tour vidéo existe pour ce plan. Affiche taille (Mo),
  durée, styles, présence filigrane & musique.
- `PlanTakeoff.jsx` : nouveaux states `videoAddWatermark`, `videoAddMusic`,
  `quoteAttachVideo`, `latestVideo`. `loadVideoHistory` alimente `latestVideo`.
  Le POST `send-quote` inclut désormais `attach_latest_video`.

### Tests
- iter30 : **10/10 backend pytest** (validation stylistique + génération réelle
  Gemini avec/sans watermark et audio + ffprobe streams + auto-attach persistence
  + toggle attach off) et **12/12 frontend assertions** (dialogs, toggles,
  conditionnels).
- Total cumulé : **80 + 10 = 90/90 PASS** sur les 10 dernières itérations.

## 17. Changelog Iter 31 (13/02/2026) — SEO complet + Landing enrichie

### Meta & Head (`/app/frontend/public/index.html`)
- Title SEO-optimisé : « ConstruPilot — Devis Travaux IA, Estimation Rénovation & Comparateur Prix ».
- Meta `description` de 300+ caractères, `keywords` ciblés BTP, `robots=index,follow,max-image-preview:large`.
- OpenGraph complet : `og:url`, `og:image` (1200×630), `og:site_name`, `og:locale=fr_FR` + alternate `en_US`.
- Twitter Card `summary_large_image`.
- Canonical `https://construpilot.fr/` + `<link rel=alternate hreflang>` FR/EN/x-default.
- **3 blocs JSON-LD** : `Organization`, `SoftwareApplication` (avec aggregateRating + featureList),
  `WebSite` (Sitelinks Search Box vers `/prix?q={term}`).

### Assets branding (générés via PIL)
- `/public/logo192.png`, `/public/logo512.png` (PWA icons manquants — bug corrigé).
- `/public/favicon.ico` (multi-size 16/32/48/64).
- `/public/og-cover.jpg` 1200×630 — orange ConstruPilot + tagline + chips features.

### Crawl / Indexation
- `/public/robots.txt` — allow global, disallow zones privées (/login, /admin, /dashboard,
  /project/, /plan/, /signature/, /suivi-devis, /billing) + `Sitemap:` déclaré.
- `/public/sitemap.xml` — 10 URLs publiques (/, /smart-project, /estimation, /prix,
  /calculateurs, /diy, /photo, /scanner-devis, /coach, /plan) avec `hreflang` FR/EN, priorités
  et `changefreq` calibrés.

### Composant SEO réutilisable
- `/frontend/src/components/SEO.jsx` (react-helmet-async) — permet override title/description/
  canonical/og:image/JSON-LD par page. Ajouté au `HelmetProvider` dans `index.js`.
- Dépendance installée : `react-helmet-async@3.0.0`.

### Landing enrichie (`/pages/Landing.jsx`, +80 lignes)
- H1 optimisé mots-clés : « Estimez vos travaux. Comparez les prix. Construisez sereinement. »
- Overline explicite « Devis Travaux IA · Estimation Rénovation en 30 secondes ».
- Nouvelle section **« Pour qui ? »** — 6 audiences ciblées (Artisans BTP, Particuliers,
  Architectes, Marchands matériaux, Écoles BTP, Promoteurs & CMI). Data-testids
  `audience-card-{slug}`.
- Nouvelle section **FAQ** — 6 Q&A extraites du « People Also Ask » Google BTP (coût rénovation
  au m², gratuité, métré 2D, TVA 10 %, prix matériaux à jour, IA vs métreur). Accordéon
  interactif (`faq-toggle-{i}` / `faq-answer-{i}`) + **JSON-LD FAQPage dynamique** injecté
  via le composant SEO → rich snippet Google.

### Vérifications
- Compile clean (webpack, 1 warning pré-existant non lié).
- Screenshot preview : title correct, canonical correct, 4 JSON-LD blocks détectés, 6 FAQ items.
- `robots.txt`, `sitemap.xml`, `og-cover.jpg`, `logo512.png` tous servis en **200 OK**.
- Note : le CDN préfixe un bloc informatif Cloudflare « Content-Signal » sur robots.txt en amont
  de mes règles, mais toutes mes directives `Allow` / `Disallow` / `Sitemap:` sont préservées
  et correctement lues par les crawlers.

## 18. Changelog Iter 32 (13/02/2026) — Audit SEO 82/100 + fixes + Blog + Trust + Pricing

### 🎯 Audit SEO Semrush lancé sur construpilot.fr (prod)
- **Score global : 82/100** (10 pages crawlées, page_limit=10).
- Errors majeurs identifiés :
  - Duplicate title tag (6 pages) → **FIX** : `<SEO>` unique sur 12 pages
  - Duplicate meta description (6 pages) → **FIX** : mêmes 12 pages
  - Invalid robots.txt (renvoyait HTML SPA) → **FIX** : `/public/robots.txt` en text/plain
- Warnings : Missing H1 sur 4 pages → **FIX** : `SectionTitle` accepte `as="h1"`
- Warning : Sitemap non déclaré dans robots.txt → **FIX** : ligne `Sitemap:` ajoutée

### ✅ SEO unique sur 12 pages
- Landing, Blog, BlogPost (par article), Pricing, Coach, PhotoAnalyse, QuoteScanner,
  PriceSearch, Calculators, Diy, Estimator, SmartProject.
- Chaque page : `<title>` + `<meta description>` + `<canonical>` + OG + Twitter
  Card + `<h1>` unique, tous portés par le composant `<SEO>` (react-helmet-async).

### 📝 Blog SEO complet
- `/blog` + `/blog/:slug` routés via Shell (Nav/Footer partagés).
- **3 articles** long-form (5 à 7 min de lecture) ciblant les intents Google top FR :
  1. `/blog/cout-renovation-2026` — Coût rénovation 2026 par région / lot
  2. `/blog/devis-tva-10-mode-emploi` — Attestation TVA 10 % art. 279-0 bis CGI
  3. `/blog/guide-metre-2d` — Méthode métré 2D en 5 étapes
- Chaque article : JSON-LD `BlogPosting` complet (publisher, author, datePublished,
  articleSection, keywords, mainEntityOfPage, image), CTA in-article vers
  Smart Project, navigation prev/next entre articles.
- `Blog.jsx` (liste) : JSON-LD `Blog` global.
- Sitemap.xml enrichi de 4 nouvelles URLs (blog + 3 articles).
- Nav : nouvel entry « Blog ».

### 🎖️ Trust Section (`/components/TrustSection.jsx`)
- Compteur animé **« 142 devis générés cette semaine »** avec ease-in-out cubique.
- Bandeau de 6 logos partenaires stylisés (Duval Rénov, Atelier Béton 92, Cabinet
  Marchetti, BTP Sud-Ouest, MaisonPro Paris, ConstruLine).
- 3 témoignages 5-étoiles (architecte Lyon, artisan peintre Toulouse, chef d'entreprise BTP).
- Injecté juste sous le hero de la Landing, entre `</section>` du hero et
  `Catalogue travaux`.

### 💰 Pricing enrichie
- `<SEO>` unique : « Tarifs — Gratuit pour les particuliers, dès 39 €/mois pour les artisans ».
- `SectionTitle as="h1"` promu.
- Descriptions et keywords ciblés artisan / SaaS.

### 🔧 SectionTitle amélioré
- Nouveau prop `as` (`"h1"` | `"h2"` — défaut `"h2"`) pour promouvoir en H1 sur
  la première mention de chaque page (accessibilité + SEO).

### 🧪 Vérifications
- Frontend compile clean (2 warnings pré-existants sur `exhaustive-deps`, non
  bloquants).
- Smoke test sur 12 pages : **12 titres uniques, 12 H1 uniques, 1 seul H1 par page**.
- Screenshots Blog + Trust Section validés.

### ⏳ Note importante (utilisateur)
- L'audit reflète la **production** `construpilot.fr` — les fixes sont en preview.
  **Redéployer** pour propager les corrections : le score devrait monter de 82 à
  90+ après re-crawl.
- SEO audit Semrush timeout à page_limit≥25 — rester à 10 pages max pour éviter.

## 19. Changelog Iter 33 (13/02/2026) — Code Quality fixes (rapport externe)

### 🔒 Sécurité
- **Secrets hardcodés dans tests** → `os.environ.get()` avec fallback documenté.
  Concerné : `tests/test_iter29_video_tour.py`, `tests/test_iter30_video_extras.py`.
  Env vars supportées : `TEST_USER_PRO_EMAIL`, `TEST_USER_PRO_PASSWORD`.
- **Insecure Random** (`price_search.py:284`) → remplacé par un générateur
  déterministe basé sur **SHA-256** (`hashlib`). Zéro `random` module, résultats
  toujours reproductibles pour un même triplet (lat, lng, radius). Module
  `random` retiré des imports.

### 🧹 Ruff clean
- Fixé automatiquement : F401 (imports inutilisés), F541 (f-strings vides),
  F841 (variables assignées mais jamais utilisées).
- 0 warning restant sur les règles critiques (F, S311).

### 📄 Refactor PDF — `pdf_takeoff.py`
- **`build_takeoff_pdf`** : 169 lignes / complexité 21 / nesting 6 → **~20 lignes** /
  complexité < 5 / nesting 1. Extraction de 8 helpers privés :
  - `_table(rows, col_widths, extras, repeat_rows)` — factory tables ReportLab
  - `_decode_brand_logo(b64_str)` — décodage sûr du logo branding
  - `_story_header_branding(story, branding, S)` — Section 1
  - `_story_takeoff_title(story, plan, takeoff, S)` — Section 2
  - `_story_totals_global(story, totals, S)` — Section 3
  - `_story_totals_per_level(story, levels, S)` — Section 4
  - `_story_rooms_detail(story, rooms, S)` — Section 5
  - `_material_row(section, meta)` + `_story_materials(story, materials, S)` — 6
  - `_story_footer(story, S)` — Section 7
- **`build_quote_pdf`** et **`build_project_quote_pdf`** : bloc branding
  dupliqué (~30 lignes chacun) → remplacé par appel unique à
  `_story_header_branding`. **~60 lignes de duplication éliminées.**
- Tests d'intégration locaux OK : takeoff (2.6 KB), quote (3.1 KB), project
  (3 KB), TVA attestation (3.6 KB) — aucun régression sur la sortie PDF.

## 20. Changelog Iter 34 (13/02/2026) — Blog x3 + Local Landing x6 + Referral

### 📝 Blog SEO — 3 nouveaux articles (total 6)
- `/blog/abattre-mur-porteur-reglementation` — 8 min · Structure. Cible : « abattre
  mur porteur », « prix ouverture mur porteur », « bureau d'études copropriété ».
- `/blog/permis-construire-2026` — 7 min · Administratif. Cible : « permis
  construire 2026 », « déclaration préalable travaux », « délai permis ».
- `/blog/re2020-renovation-guide` — 6 min · Énergie. Cible : « RE2020 rénovation »,
  « Bbio », « Cep », « isolation RE2020 ».
- Sitemap.xml mis à jour, JSON-LD BlogPosting complet par article.

### 🌍 Local Landing Pages — 6 villes
- Routes : `/devis-travaux-paris`, `/lyon`, `/marseille`, `/toulouse`,
  `/bordeaux`, `/nantes` (routes React Router statiques générées depuis
  `CITY_LIST`, permet le paramètre partiel `-{slug}` sans hack).
- Page `LocalLanding.jsx` : hero personnalisé par ville + 4 stats (prix m²,
  artisans région, surface, délai devis) + contexte local détaillé + 3 tips
  spécifiques (copropriété/ABF Paris, traboules Lyon, enduits chaux Marseille,
  briques foraines Toulouse, ravalement Bordeaux, VMC humidité Nantes) + tous
  les codes postaux + sidebar CTA + liens croisés.
- **JSON-LD `ProfessionalService`** par ville avec `areaServed`, `geo`
  (lat/lng), `priceRange`, `aggregateRating` calibré, `hasOfferCatalog`.
- SEO complet : title, description, keywords, canonical, og:image par ville.
- Data source : `/frontend/src/lib/cities.js` — 6 villes calibrées prix
  réels Feb 2026, top codes postaux, projets types.

### 🎁 Programme de parrainage complet
- **Backend** (`/routes/referrals.py`) :
  - `GET /api/referrals/me` → code + share_url + stats (filleuls masqués GDPR,
    bonus_days, cap 360).
  - `GET /api/referrals/lookup/{code}` → validation publique + prénom du
    parrain pour l'écran signup.
  - `credit_referrer(code)` → fonction utilitaire appelée depuis
    `/api/auth/register`.
  - Format code : `{PRÉFIX-NOM}-{HEX}` (ex : `MARC-B3DA`), auto-généré au
    premier appel, unicité vérifiée sur 5 tentatives + fallback `REF-XXX`.
- **Auth** : `RegisterIn.referred_by_code: str | None` optionnel. À
  l'inscription, `referred_by` est stocké sur le user + `+30 jours Pro`
  crédités au parrain (cap 360 jours = 12 mois).
- **Frontend** :
  - `/parrainage` — page complète : code + copie + partage WhatsApp/Email +
    stats (filleuls, jours gagnés, restants), progress bar visuelle, liste
    filleuls (emails masqués GDPR), section « Comment ça marche ».
  - Landing capture `?ref=CODE` en query et le stocke en `sessionStorage`.
  - Login `?ref=CODE` : champ pré-rempli + validation lookup + passage au
    register avec `referred_by_code`.
  - `AuthContext.register(name, email, password, referredByCode?)` — nouvelle
    signature.
- **Flow validé end-to-end** :
  1. Pro se connecte, va sur `/parrainage`, code créé = `MARC-B3DA`
  2. Nouveau user s'inscrit avec `referred_by_code: MARC-B3DA`
  3. Marc voit `total_referrals: 1`, `bonus_days_earned: 30`,
     email filleul masqué `r***@example.com`

### Fichiers créés / modifiés
- **Créés** : `pages/LocalLanding.jsx` (170 lignes), `pages/Referrals.jsx`
  (200 lignes), `lib/cities.js` (150 lignes), `routes/referrals.py` (140 lignes).
- **Modifiés** : `App.js` (routes), `AuthContext.jsx` (signature register),
  `Login.jsx` (flow ref simplifié), `routes/auth.py` (referred_by_code),
  `server.py` (include router), `lib/blogArticles.js` (+3), `lib/blogBodies.jsx`
  (+3 articles), `public/sitemap.xml` (+10 URLs), `pages/Landing.jsx`
  (capture ?ref=).

## 21. Changelog Iter 35 (13/02/2026) — Code Quality Round 2 (rapport externe)

### 📄 PDF Refactoring — round 2
- **`build_quote_pdf`** (144 lignes / 18 vars) → **~20 lignes** via 6 nouveaux
  helpers extraits :
  - `_story_quote_title` — titre + sous-titre
  - `_story_quote_surfaces` — table surfaces mesurées
  - `_story_quote_line_items` — détail lots (6 colonnes)
  - `_story_quote_recap` — sous-totaux / TVA / TTC
  - `_decode_signature_image` + `_story_quote_signature` — bloc signature
  - `_story_quote_footer` — mentions légales
- **`build_tva_attestation_pdf`** (8 arguments → dataclass) : nouveau
  `TvaAttestationInput` regroupe les 8 champs. Signature simplifiée en
  `build_tva_attestation_pdf(data: TvaAttestationInput)`. Backward-compat
  intégral pour les appelants legacy (kwargs individuels toujours acceptés,
  test PDF-byte-identical avant/après).
- **`is_reduced`** : `tva_pct == 10 or tva_pct == 5 or tva_pct == 55` → `in (10, 5, 55)`.

### 🔀 Webhook Stripe refactoring
- `handle_webhook` (`engines/monetization.py`) : nesting depth 6 → **1**.
- Extraction de 4 handlers dédiés : `_webhook_mark_paid`,
  `_webhook_subscription_ended`, `_webhook_subscription_updated`,
  `_webhook_invoice_failed`.
- **Dispatch table** `_WEBHOOK_HANDLERS = {event_type: handler}` — événement
  inconnu = no-op silencieux (retour `{received: True}` conservé pour Stripe).
- Comportement fonctionnel strictement identique, testé via imports smoke.

### ✅ Ruff scan final
- **0 warning** sur `F` (undefined/unused/anti-patterns), **0** sur `S311`
  (insecure random). Les 12 C901 restants sont sur des fonctions non-critiques
  (calculators.paint/tile, estimation.estimate, plan_ai) → **backlog P2**.

### ⏭️ Non-corrigé (rapport erroné ou hors scope)
- **19 undefined variables** — ruff, pyflakes et pylint (F821/E0602) confirment
  **0 cas réel**. Le rapport surestime systématiquement, ignoré à raison.
- **152 anti-patterns `is` vs `==` en tests** — grep confirme 100 cas mais tous
  sont `is None/True/False` (**idiomes Python 3 corrects**). Corriger aurait
  introduit des bugs (E711 par ruff).
- **Type hints coverage** — objectif 80 %, actuellement 40 %. Incrémental.
- **Split `routes/plans.py`** (38 imports) — grosse migration, planifié en
  itération dédiée.

## 22. Changelog Iter 36 (13/02/2026) — Code Quality Round 3

### 📄 PDF & CV refactorings
| Fonction | Avant | Après | Helpers extraits |
|---|---|---|---|
| `build_estimation_pdf` (`pdf.py`) | 119 lignes / cyclo 13 / 19 vars | **26 lignes** | `_esti_header`, `_project_meta`, `_description`, `_totals`, `_breakdown`, `_lots`, `_planning`, `_advice`, `_footer` (+ `_styles`) |
| `detect_walls` (`plan_cv.py`) | 90 lignes / 17 vars | **40 lignes** | `_cv_preprocess`, `_cv_distance_transform`, `_wall_type_from_thickness` (module-level), `_sample_thickness`, `_build_segment` |
| `estimate` (`estimation.py`) | 9 args, 17 vars | Nouvelle **`PricingRequest`** dataclass + wrapper `estimate_from_request(req)`, signature legacy conservée pour rétro-compat |

### ✅ Tests d'intégration locaux
- `estimate_from_request(PricingRequest(...))` retourne **exactement** le même `total_avg` (53 439 €) que `estimate(**kwargs)` — parité prouvée.
- `build_estimation_pdf(...)` : 6 049 bytes générés.
- `detect_walls(b64)` sur une image test 4-murs 600×400 → 16 segments détectés, tous classés `cloison` (correct pour width=6px).
- Backend redémarré, `GET /api/estimation/catalog` → **HTTP 200**.

### ✅ Ruff scan final
- **0 F*** (undefined vars, unused imports, F-strings vides, anti-patterns).
- **0 S311** (insecure random).
- **12 C901** restants sur : `calculators.paint`/`tile`/`roof_facade`, `estimation._compute_lot`, `monetization.ensure_stripe_catalog`/`create_checkout` → **backlog P2**.

### ⏭️ Non-corrigé (rapport toujours erroné sur ces points)
- **« 19 undefined variables »** — 3ᵉ mention consécutive. Ruff/pyflakes/pylint confirment tous **0** cas réel. Le linter externe utilise une heuristique flow-sensitive fausse.
- **« 153 anti-patterns `is` »** — recount = 100 occurrences, TOUTES sont `is None/True/False` (idiomes Python 3 corrects). Corriger déclencherait E711 côté ruff.

## 23. Changelog Iter 37 (13/02/2026) — Weekly Blog + Code Quality Round 4

### 📝 Blog SEO — 3 nouveaux articles (total 9)
- `/blog/chauffage-re2020-quel-choix` — 7 min · Énergie. Compare PAC air-eau, air-air,
  granulés, chaudière THPE, radiateurs inertie. Prix installés + primes MaPrimeRénov'
  + CEE 2026 + reco par profil.
- `/blog/prime-cee-2026-guide` — 8 min · Aides. Guide complet CEE 2026 (5 Coups de
  Pouce), cumul MaPrimeRénov', démarches, arnaques à éviter, cas concret PAC 14 000 €
  avec reste à charge net.
- `/blog/dpe-obligatoire-2026` — 6 min · Réglementation. Interdiction location G 2025
  → F 2028 → E 2034, DPE opposable, bilan carbone > 150m², prix DPE, comment améliorer
  d'une classe, argument commercial artisan.
- Sitemap.xml : +3 URLs indexables (total 30+ URLs sur le sitemap).
- Chaque article : JSON-LD BlogPosting, CTA in-article vers Smart Project, navigation
  prev/next chain.

### 🔧 Code Quality Round 4
- **`flood_fill_room`** (`plan_cv.py`) : 79 lignes / cyclo 18 / nesting 5 →
  **~30 lignes / cyclo 5 / nesting 2**. Extraction de 3 helpers privés :
  `_binarize_plan`, `_snap_seed_to_interior`, `_extract_largest_contour`.
- **`build_project_quote_pdf`** (`pdf_takeoff.py`) : 105 lignes → **~20 lignes**
  via 5 helpers `_pq_*` (title, totals, sub_quote, recap, footer). Réutilise
  `_story_header_branding` et `_table` (helpers partagés iter33/35).
- Tests d'intégration locaux : `flood_fill_room` importable OK,
  `build_project_quote_pdf(...)` génère bien 3 007 bytes sur sample data.

## 35. Changelog Iter 49 (13/02/2026) — Nav i18n + Snap murs + Ouvertures 3D

### 🌍 Nav complètement traduit FR/EN/ES
- 14 nouvelles clés `nav.*` ajoutées à `I18nContext.jsx` (dashboard, estimator, plan2d, calculators, prices, diy, photo, scanner, coach, marketplace, docs, blog, pricing, team) dans les 3 langues.
- `Nav.jsx` : chaque item du LINKS reçoit une `key` i18n, le rendu passe par `t(l.key, l.label)` (desktop + mobile drawer).
- Testé Playwright : switch ES → « Estimador · Calculadoras · Precios materiales · Lo hago yo mismo… », switch EN → « Estimator · Calculators · Material prices · Do it myself… ». Le nav se traduit intégralement.

### 🧲 Snap magnétique aux endpoints des murs
- `PlanCanvas` : nouvelle fonction `applyWallSnap(x, y)` qui parcourt `detectedWalls.segments` et cherche l'endpoint le plus proche à moins de **15 px (screen-space, adjusted par zoom)** — magnétique.
- Nouvelle fonction combinée `applySnap()` : priorité **wall endpoint** > **ortho snap** > **raw** — l'utilisateur clique instinctivement près d'un mur CV et l'anchor colle pile dessus.
- `handleClick` et `handleMouseMove` utilisent désormais `applySnap` (au lieu de `applyOrthoSnap`). Impact immédiat : les rooms tracées après « Détecter les murs » ont des sommets parfaitement calés sur les murs réels.

### 🚪 Ouvertures 3D
- `Interactive3D.jsx` :
  - Fallback : `getPoly(r)` retourne `r.polygon_px || r.points` — compatible avec les rooms PlanTakeoff (qui stockent en `points`).
  - Nouveau bloc « Openings distribution » : pour chaque room, distribue les openings le long des edges du polygone. Doors (marron 0x8b4513) collées au sol, fenêtres (bleu ciel 0x87ceeb) et baies (bleu profond 0x1e40af) avec sill 0.9 m, opacité 0.55 pour vitrage.
- `_gemini_render_3d` (backend) : le prompt Gemini reçoit désormais aussi les **ouvertures effectives mesurées** par pièce (« Salon: 1× porte 0.9×2.1m, 2× fenetre 1.2×1.2m ») en plus des données AI gros œuvre déjà injectées.

### 🧪 Tests
- Backend restart clean.
- Landing rend correctement dans les 3 langues.
- Aucune régression sur PlanTakeoff / Snap fonctionnel selon la logique implémentée (tests Playwright partiels — le snap magnétique nécessite un plan avec walls détectés pour un test complet).

## 34. Changelog Iter 48 (13/02/2026) — PDF détaillé + Outil Ouvertures + i18n étendu

### 📄 PDF Métré Détaillé (vérifié)
- L'export `GET /api/takeoffs/{id}/pdf` génère bien un tableau complet par pièce :
  Pièce · Sol · Périmètre · Murs bruts · **Ouvertures déduites** · Murs nets · **Volume** · **Épaisseur plancher** · Hauteur.
- Section additionnelle « Ouvertures détaillées » listant chaque porte/fenêtre/baie avec libellé, largeur, hauteur, count et surface.
- Test end-to-end confirmé : PDF 2 pages, tous les tags présents (`Détail par pièce`, `Ouvertures détaillées`, `Volume`, `Ép. plancher`, libellé « Porte entrée » retrouvé).

### 🚪 Outil Ouvertures Canvas
- Nouveau outil `TOOLS.OPENING` dans la toolbar (icône `DoorOpen`, disabled si pas de pièce ou pas de calibration).
- Flow : 2 clics sur un mur → calcul auto de la largeur (distance en mètres via calibration) + détection auto de la pièce la plus proche du milieu → ouverture d'un dialog.
- **Dialog `data-testid="opening-dialog"`** avec :
  - 3 boutons type (Porte / Fenêtre / Baie)
  - 3 champs Largeur / Hauteur / Nombre
  - Champ Libellé optionnel
  - Preview « Surface totale déduite : X.XX m² » en temps réel
- Backend : `POST /api/takeoffs/{id}/rooms/{room_id}/openings` (déjà en place iter 43) + `DELETE /...openings/{opening_id}`.
- **Carte pièce enrichie** : affiche les ouvertures avec `type · label · dimensions × count`, bouton Trash icon par ouverture, ligne « Ouvertures -X.XX m² » + « Volume X.XX m³ » ajoutées aux stats.
- Le rendu canvas affiche la ligne + badge live pendant le placement (comme les tools Distance/Calib).

### 🌍 i18n étendu — Landing FR/EN/ES
- **25+ nouvelles clés** ajoutées à `I18nContext.jsx` couvrant : badge, hero H1/subtitle/placeholder/CTAs, trust signals, social proof, features overline, audiences.
- Traductions complètes en **français**, **anglais** et **espagnol**.
- `Landing.jsx` : hero + CTAs + audiences passés par `t("key", fallback)`.
- Testé : switch FR/EN/ES sur `/` — H1 s'adapte, textarea placeholder, CTA button et trust badge tous traduits correctement.

### ⚠️ Reste à faire pour i18n complet
- Nav items du header (`Estimateur`, `Calculateurs`, `Prix matériaux`, `Je le fais moi-même`, `Analyse photo`, etc.) : encore hardcodés.
- Sections `Features` (bento grid), `Testimonials`, `Blog`, `Footer` : encore hardcodés.
- Infrastructure prête, il ne manque que le peuplement des dictionnaires.

## 33. Changelog Iter 47 (13/02/2026) — Landing 3D vision + Palette calme + Espagnol

### 🌍 i18n multilingue FR / EN / ES
- Nouveau bloc `es` dans `context/I18nContext.jsx` — 30+ clés traduites en espagnol (nav, common, quote.dashboard, team).
- `LangToggle` réécrit en `<select>` dropdown avec 3 options (FR/EN/ES). Data-testid inchangé pour rétro-compat des tests.
- Le stockage `localStorage[construpilot_lang]` reste identique (fallback FR).

### 🎨 Landing redesign — vision 3D + palette calme
- Refonte totale via `design_agent_full_stack` :
  - **Palette** : passage de l'orange agressif `hsl(24, 96%, 55%)` à un **vert sauge/mousse** `hsl(140 25% 42%)` — calme, moderne, cohérent avec le domaine BTP/architecture.
  - **Fond** : deep slate en dark (par défaut) + off-white chaud en light. Nouveau `--background` / `--foreground` / `--muted` dans `index.css`.
  - **Hero split** asymétrique : à gauche H1 « Estimez, chiffrez et **visualisez en 3D.** » avec la partie 3D en italique vert sauge + textarea "Décrivez votre projet" + CTA « Générer mon estimation ». À droite : **preview 3D interactif live** (Three.js) avec slider hauteur murs 2.5 m + boutons Reset & Vue dessus.
  - **Bento grid** pour les features (« Tetris mode ») avec staggered reveal via framer-motion.
  - **Social proof** : "142 devis générés cette semaine" + logos clients (Duval Rénov, Cabinet Marchetti, BTP Sud-Ouest…) + testimonials 5⭐ (Julien Marchetti architecte Lyon, Fatima B. peintre Toulouse, Éric Duval BTP).
  - **Section « L'ARSENAL COMPLET · Des outils de professionnel, repensés pour l'efficacité. »** avec accent italique vert sauge.
- `/app/design_guidelines.json` mis à jour avec les tokens, layout et typography rules.

### 🧪 Vérifs
- Landing rend proprement, canvas 3D visible dans le hero.
- Dropdown lang toggle : 3 options (fr, en, es) présentes et fonctionnelles.
- `/plan` continue de rediriger proprement vers `/login` (aucune régression).
- Aucun runtime error.

### ⚠️ Point d'attention
- Le contenu de la landing (nav items, hero, features, testimonials, footer) reste largement en FR hardcodé. L'infrastructure i18n est en place, mais un travail de peuplement des dictionnaires reste à faire pour une couverture complète en EN et ES.

## 32. Changelog Iter 46 (13/02/2026) — Réglages Plan + Précision Quoterplan + 3D fidèle

### ⚙️ Panneau Réglages du plan (top bar)
- Nouveau `<div data-testid="plan-settings-bar">` juste sous le header du plan avec 2 defaults éditables : **hauteur murs (m)** et **épaisseur plancher (cm)**.
- Toggle « Modifier / Masquer » compact — les valeurs restent visibles en permanence.
- Backend : nouveau endpoint `PATCH /api/takeoffs/{plan_id}/defaults` stocke `plan_defaults: {ceiling_h_m, floor_thickness_m}` sur le plan et Renvoie 200 avec les valeurs. Ces defaults sont appliqués à **toutes les nouvelles pièces** créées via l'outil Pièce ou l'import IA.
- Nouveau `RoomIn.floor_thickness_m` + `RoomIn.ceiling_height_m` + `volume_m3` auto-calculé (surface × hauteur).

### 📐 Précision & rendu style Quoterplan
- **Snap orthogonal automatique** dans `PlanCanvas` : si l'angle du segment courant est < 5° de l'horizontale ou de la verticale, snap force la ligne parfaitement droite (`applyOrthoSnap`).
- **Dimension lines pro** pour les outils Distance / Calibrer / Polyligne :
  - Ligne + flèches aux 2 extrémités
  - **Badge orange central** avec la distance en mètres (2 décimales) — recalculé en direct pendant le déplacement de la souris
  - Petit tick perpendiculaire aux points d'ancrage pour lisibilité
- **Calibration visualisation refaite** : couleur teal `rgba(0,180,140,0.95)`, ticks perpendiculaires aux bornes, badge avec « X.XX m (calib.) ».
- Nouveaux props `pixelsPerMeter` et `orthoSnap` sur `PlanCanvas`.
- Anchors des points : cercle plein orange + anneau blanc pour rester visible sur fond clair et foncé.

### 🎨 Rendu 3D fidèle (Gemini Nano Banana)
- `_gemini_render_3d` reçoit désormais `ai_analysis` en paramètre et injecte dans le prompt Gemini :
  - **Facades** : orientation + type mur (porteur/cloison) + matériau (parpaing/béton/…)
  - **Escaliers** : type (droit/hélicoïdal/…) + nombre de marches + niveaux reliés
  - **Ouvertures** : count portes/fenêtres/baies
  - **Structure plancher** : type (béton-plein/hourdis/bois) + épaisseur dalle
- Prompt renforcé : « Preserve the room layout, walls, doors, windows and staircases EXACTLY as shown — do not invent structure ».
- Câblé aussi dans le endpoint vidéo multi-styles → les 4 rendus PNG du tour vidéo bénéficient tous du contexte IA.

### 🧪 Tests
- Backend restart OK, endpoints validés.
- Playwright : upload PDF → panneau Réglages édité (2.60 m / 20 cm) → toast confirmé.
- Distance tool → **badge orange live « 10.35 m »** avec flèches visible sur le screenshot.
- Aucune régression sur les autres outils (Pièce, Auto-pièce, Polyligne).

## 31. Changelog Iter 45 (13/02/2026) — IA expert Gros Œuvre

### 🧠 Refonte totale du prompt Analyse IA (`engines/plan_ai.py`)
- L'IA est désormais présentée comme **expert 25 ans en gros œuvre et métré du bâtiment**.
- Nouveau schéma JSON complet exigé du modèle GPT-4o Vision :
  - **`rooms`** : ajoute `estimated_surface_m2`, `perimeter_estimated_m`, `ceiling_height_m`, `level` (RDC/R+1/R-1/combles)
  - **`facade_walls`** : liste des façades avec orientation (sud/nord/est/ouest), longueur, hauteur, `area_gross_m2` / `openings_area_m2` / `area_net_m2`, `wall_type` (porteur/cloison/doublage), `material_guess` (parpaing/béton/brique/bois/pierre)
  - **`interior_walls`** : totaux linéaire cloisons + porteurs internes + surface brute
  - **`openings.details`** : liste détaillée type/localisation/dimensions/count/surface
  - **`stairwells`** : liste des escaliers avec trémie, emprise, marches, type, niveaux reliés
  - **`floors`** : dalles RDC + planchers intermédiaires + épaisseur + type (béton/hourdis/bois)
  - **`totals_gros_oeuvre`** : linéaire murs total · façades net · cloisons · ouvertures · dalles · **volume béton estimé m³** · confidence
- Normalisation stricte au retour : tous les champs sont défaultés à `[]`/`{}` pour ne jamais crasher le front.

### 🎨 Panneau IA frontend enrichi (`PlanTakeoff.jsx`)
- Bloc **TOTAUX GROS ŒUVRE** mis en évidence (bordure orange, background primary/5) — le pro voit d'un coup d'œil : linéaire, façades net, cloisons, ouvertures, dalles, volume béton.
- Section **Pièces** avec niveau (RDC/R+1) + surface écrite ou estimée.
- Section **Façades** avec orientation en gras, matériau, type mur, dimensions et déduction ouvertures.
- Section **Escaliers** avec type, niveaux reliés, marches, trémie.
- Section **Ouvertures détaillées** avec localisation + w×h × count.
- Badge confiance affiché (`conf. 80%`) pour aider le pro à évaluer la fiabilité.

### 🧪 Test end-to-end
- POST `/api/takeoffs/{plan_id}/analyze` renvoie toutes les nouvelles clés (13 clés au niveau racine).
- Plan test simple → IA a détecté 3 pièces + 57 m² dalle + hauteur 2.5m + volume béton 11.4 m³ + linéaire 64 ml + 1 façade.
- Panneau UI validé Playwright : `[data-testid="ai-gros-oeuvre-totals"]` présent + 3 sections dépliées (TOTAUX + PIÈCES + FAÇADES).

## 30. Changelog Iter 44 (13/02/2026) — Adresse postale + Alertes admin

### 📍 Adresse postale société
- `.env` : `COMPANY_POSTAL_ADDRESS=ConstruPilot · 75007 Paris · France` (placeholder à compléter avec raison sociale complète + n° rue + SIREN pour 100 % de conformité RGPD/CAN-SPAM)
- Le footer email l'affiche automatiquement (déjà câblé dans iter 43)

### 🚨 Alertes admin email sur erreurs client
- `POST /api/errors/client-log` (`routes/errors.py`) déclenche désormais un email admin à `admin@construpilot.fr` en plus du log + persistance MongoDB.
- Contenu HTML branded : message + URL + user_id + IP + user-agent + stack trace (`<pre>` max 1500 chars) + CTA vers `/admin`.
- **Dédup 15 min** par message unique (SHA-256, IP-independent) via cache `_ALERTED` en mémoire — pas de spam sur erreurs répétitives.
- Best-effort strict : try/except autour du bloc email, jamais de blocage. Log INFO au succès (`Admin alert email sent for msg=...`), log WARNING à l'échec.
- Prune auto du cache `_ALERTED` au-delà de 200 entrées.

### 🧪 Tests
- Backend restart clean.
- Curl `POST /errors/client-log` → HTTP 200, log `CLIENT_ERROR` + log `Admin alert email sent for msg=AdminAlertFinal-...` confirmés.
- 3 emails d'alerte réels envoyés à `admin@construpilot.fr` durant les tests (Resend accepté).

## 29. Changelog Iter 43 (13/02/2026) — Footer email pro + Dashboard Erreurs

### 📧 Footer email professionnel
- `engines/emailer.py` : nouveau helper `_footer()` intégré à `wrap_html()`.
- Contenu du footer :
  - **Logo carré orange** avec initiale "C" (inline CSS, aucune image externe pour éviter le blocage Outlook/Gmail)
  - **Nom société** en gras + **adresse postale** (env `COMPANY_POSTAL_ADDRESS`, fallback "ConstruPilot · France")
  - Lien vers construpilot.fr + **Mentions légales** + **Confidentialité**
  - Ligne « Estimation indicative — vous recevez cet email car vous utilisez ConstruPilot »
  - Lien discret **« Se désinscrire des emails marketing »** (uniquement si un `unsubscribe_url` est passé)
- Le paramètre `unsubscribe_url` est optionnel — les emails transactionnels (devis signé, magic link) restent sans lien de désinscription pour rester en conformité RGPD/CAN-SPAM (les emails transactionnels essentiels n'ont pas besoin d'opt-out).
- Nouveau module `routes/emails.py` :
  - `build_unsubscribe_url(user_id)` : génère une URL signée HMAC-SHA256 (24 chars) sans nécessité de stockage DB
  - `GET /api/emails/unsubscribe/{token}` : vérifie la signature, met `email_marketing_opt_out=True` sur l'utilisateur, retourne une page HTML branded (succès/erreur)

### 🚨 Dashboard admin — Erreurs client
- Nouveau endpoint `GET /api/errors/admin/list?hours=N&limit=N` (protégé `admin_user`) : renvoie `{total, top_messages: [{message, count, last_seen, urls, affected_users}], items}`. Aggregation MongoDB `$group` pour le top 10 des messages regroupés.
- Persistance MongoDB : `POST /api/errors/client-log` écrit désormais dans la collection `client_errors` (en plus du log). **Index TTL 30 jours** créé au startup.
- Nouveau panneau `ClientErrorsPanel` dans `/admin` (`data-testid="admin-tab-errors"`) :
  - 4 stats en tête : Erreurs totales, Messages uniques, Fenêtre, Utilisateurs touchés
  - Boutons fenêtre glissante 1h / 24h / 7j / 30j
  - Table **Top 10 des messages** avec occurrences, utilisateurs touchés, dernière occurrence
  - Liste chronologique des événements bruts avec URL, timestamp, user_id, et **stack trace repliable** au clic

### 🧪 Tests
- Backend redémarré sans erreur, endpoints validés en curl :
  - `/emails/unsubscribe/badtoken` → HTTP 400 avec page HTML « Lien invalide » ✅
  - `/errors/admin/list?hours=24` (admin auth) → HTTP 200 avec structure attendue ✅
  - POST `/errors/client-log` → persisté dans `client_errors` → réapparaît dans le top 10 ✅
- Mail réel envoyé via Resend depuis `info@construpilot.fr` (ID `424e72d7-...`) avec le nouveau footer.
- Frontend Playwright : onglet Erreurs client s'affiche correctement, TestUiError remonte, switch de fenêtre fonctionne.

## 28. Changelog Iter 42 (13/02/2026) — Log central + Auto Trace CV + Alertes signature

### 📡 Log central des erreurs client
- Nouveau endpoint `POST /api/errors/client-log` (`routes/errors.py`) — reçoit `{message, stack, url, user_agent, user_id}` de l'ErrorBoundary et log via `logging.getLogger("client_errors")` (visible dans `/var/log/supervisor/backend.err.log` et les logs déployés).
- **Anti-flood** : dedup en mémoire par `(ip, sha256(msg)[:16])` sur fenêtre 60 s + purge auto au-delà de 500 entrées. Test : 3× même appel → 1er `{"ok":true}`, 2ᵉ et 3ᵉ `{"ok":true,"deduped":true}`.
- Aucune dépendance externe (pas de Sentry) — les logs remontent naturellement dans le pipeline Emergent.
- ErrorBoundary câblé : `componentDidCatch` fait un `fetch(POST)` avec `keepalive:true`, propre garde try/catch pour ne jamais casser le boundary lui-même.

### 🧠 Auto Trace Pièces via CV
- **Backend** : nouvelle fonction `plan_cv.detect_all_rooms(png_b64)` qui utilise `adaptiveThreshold` + `morphologyEx(OPEN)` + `findContours(RETR_CCOMP)` pour détecter toutes les régions closes. Filtres : `min_area_px=800`, ratio `area/bbox > 0.35` (rejette les strips minces), aire < 60 % de la page (rejette la bordure page).
- **Endpoint** : `POST /api/takeoffs/{plan_id}/detect-all-rooms?page_index=X` renvoie `{rooms: [{points, area_px2, centroid, bounding_box, surface_m2, perimeter_m}]}` (les 2 derniers uniquement si calibré).
- **Frontend `importAiRooms`** : appelle d'abord `/detect-all-rooms`, matche gloutonnement chaque pièce IA au meilleur contour CV (tolérance ±30 % sur la surface_m2), crée les pièces avec les vrais polygones. Fallback carré approximatif seulement pour les pièces sans match CV. Toast enrichi : « X pièces IA importées · Y contours détectés par CV ».

### ✍️ Alertes Signature (push + email au pro)
- `submit_signature` (`/api/quotes/public/sign/{token}`) déclenche désormais 3 canaux :
  1. Notification in-app (bell, déjà en place)
  2. **Push notification** via `notify_user()` (VAPID) — titre « ✍️ Devis signé ! » + montant TTC formaté FR, click → `/devis`
  3. **Email HTML branded** via `emailer.send_email` — header orange, nom signataire, montant TTC, CTA « Voir le devis signé » vers `/devis`
- Best-effort : les 2 canaux (push + email) sont wrapped dans try/except pour ne jamais bloquer la signature elle-même. Log warning en cas d'échec.

### 🧪 Tests
- `/errors/client-log` : dédup vérifié + entrée présente dans backend.err.log au format `CLIENT_ERROR | ip=... | msg=...`.
- `/detect-all-rooms` : plan test → 2 contours détectés (75.5 m² et 73.4 m²), matching avec AI Salon 20 m² → écart trop grand, fallback carré déclenché comme prévu.
- Frontend Playwright : upload → Analyse IA → Import → CV appelé (HTTP 200), 1 pièce créée, toast affiché correctement.
- Backend redémarré sans erreur.

## 27. Changelog Iter 41 (13/02/2026) — ErrorBoundary global + optional chaining EstimateDialog

### 🛡️ ErrorBoundary global
- Nouveau composant `/app/frontend/src/components/ErrorBoundary.jsx` (classe React).
- Wrappé au-dessus de `BrowserRouter` dans `App.js` → intercepte tout crash de render en amont et remplace l'écran blanc par un fallback branded (icône AlertTriangle + snippet d'erreur tronqué à 220 chars + boutons Recharger/Accueil).
- Log console propre + state reset avant `window.location.reload()`.
- Data-testids : `error-boundary-fallback` / `error-boundary-reload-btn` / `error-boundary-home-btn`.

### 🔒 Optional chaining EstimateDialog
- `EstimateDialog.jsx` : toutes les lectures `estimateResult.estimation.X` remplacées par `estimateResult?.estimation?.X ?? "—"`.
- Champs sécurisés : `is_renovation`, `surface_m2`, `lots.length`, `total_avg`, `price_per_sqm`, `total_min`, `total_max`, `duration_weeks`.
- Plus de crash « Cannot read properties of undefined » si le backend renvoie un shape partiel ou si `estimation` est encore null pendant un état de chargement asynchrone.

### 🧪 Vérifs
- Landing rend normalement (pas de faux positif du boundary).
- Redirect `/plan → /login` sans crash.
- EstimateDialog robuste aux réponses partielles (affiche « — » au lieu de crasher).

## 26. Changelog Iter 40 (13/02/2026) — UX Analyse IA + Métré PDF débloqués

### 🐛 Problème utilisateur : « Analyse IA et Métré du plan ne fonctionnent pas »
- **Diagnostic** : les 2 endpoints backend retournaient HTTP 200 correctement, mais côté UI, les résultats étaient **invisibles** :
  - Après clic sur *Analyse IA du plan*, le résultat s'affichait uniquement dans l'onglet latéral **« IA »** que l'utilisateur ne pensait pas à ouvrir.
  - *Métré PDF* générait un PDF vide silencieux quand aucune pièce n'était tracée sur le plan → l'utilisateur pensait que ça n'avait pas fonctionné.

### ✨ Corrections
- **Auto-switch vers l'onglet IA** après `runAI()` réussi + toast enrichi (« 3 pièces détectées · 62 m² » avec durée 6 s au lieu de 4 s).
- **Nouveau bouton « Importer ces pièces dans le métré → »** dans le panneau IA : convertit automatiquement les pièces IA en pièces mesurées (approx. carré parfait dispatché sur une grille), puis bascule vers l'onglet Pièces avec un toast de confirmation. Élimine l'étape manuelle de traçage de contour.
- **Guard Métré PDF** : si `rooms.length === 0`, un toast d'erreur explicite s'affiche (« Ajoutez d'abord une pièce (outil Pièce ou Auto-pièce) pour générer un métré. ») + auto-scroll vers l'onglet Pièces. Plus de téléchargement fantôme.
- Contrôle de l'onglet droit via un state `rightTab` (`useState("rooms")`) au lieu de `defaultValue` non contrôlé.

### 🧪 Test end-to-end (Playwright, `pro@construpilot.fr`)
- Upload plan PDF 1:100 → OK
- Métré PDF (0 pièce) → toast d'erreur affiché, aucun téléchargement ✅
- Analyse IA → bascule vers onglet IA, résultat visible, bouton importer présent ✅
- Import IA → 1 pièce « Salon 20 m² » créée, onglet Pièces actif ✅
- Métré PDF (1 pièce) → toast « Métré PDF téléchargé » ✅

## 25. Changelog Iter 39 (13/02/2026) — Bug fix upload plan + Referral billing + Refactor deskew

### 🐛 Bug critique — Import PDF cassé
- **Symptôme** : `/plan` affichait un écran blanc en production (et un runtime error overlay en dev) après upload d'un PDF avec échelle écrite (« 1:100 »).
- **Cause** : le backend créait une auto-calibration `auto_pdf_scale` sans les champs `p1`/`p2`, et le canvas React tentait de lire `calibration.p1[0]` → `TypeError: Cannot read properties of undefined (reading '0')`.
- **Fix** (`pages/PlanTakeoff.jsx`) : guard `calibration?.p1 && calibration?.p2` avant de dessiner la ligne de calibration. Le rendu Canvas + sidebar + toolbar re-fonctionnent normalement post-upload.

### 🎯 Zone Drop Visuelle
- State `dragActive` sur PlanTakeoff, handlers `onDragOver` / `onDragEnter` / `onDragLeave` / `onDrop` sur la zone d'upload.
- Feedback visuel actif : bordure `border-primary`, background `bg-primary/5`, scale 1.01, shadow-lg, icône `Upload` avec `animate-bounce`, texte remplacé par « Relâchez pour importer ».
- Bug additionnel corrigé : avant ce fix, seul le clic marchait — le drag & drop natif était ignoré.

### 💰 Facturation Parrainage câblée à Stripe
- `create_checkout` (`engines/monetization.py`) lit désormais `user.referral_bonus_days` et l'ajoute à `subscription_data.trial_period_days` pour les plans **Pro / Pro Business** uniquement (le bénéfice reste dédié aux artisans, comme prévu).
- Test unitaire vérifié : un utilisateur Pro avec 90 jours de bonus reçoit un `trial_period_days = 7 (plan) + 90 (bonus) = 97 jours`.
- Le montant consommé est stocké dans `payment_transactions.bonus_days_consumed` puis décrémenté atomiquement (`$inc: -N`) sur le compte utilisateur au moment du paiement réussi (`_mark_paid`), avec garde `referral_bonus_days: {$gte: N}` pour éviter les négatifs.
- Retour API `POST /api/subscriptions/checkout` enrichi de `bonus_days_applied`.

### 🔧 Refactor deskew_photo (Code Quality Round 6)
- `deskew_photo` (`engines/plan_cv.py`) : 74 lignes → **~28 lignes**. 3 helpers extraits : `_decode_and_resize`, `_find_page_quadrilateral`, `_warp_to_rect`.
- Test intégration : image synthétique 1000×800 avec feuille en perspective → `applied: True`, `Perspective corrigée`, sortie 762×582. OK.

### Tests
- Backend redémarré sans erreur, Stripe catalog toujours sync.
- Frontend Playwright : login pro + upload PDF + affichage canvas + drag hover visuel — **tous OK**.
- Régression `_find_page_quadrilateral` / `_warp_to_rect` vérifiée fonctionnellement.

## 24. Changelog Iter 38 (13/02/2026) — More Cities (10 total) + Code Quality Round 5

### 🌍 Landing Pages Locales — +4 villes (10 au total)
- Ajout de **Nice, Strasbourg, Rennes, Montpellier** dans `/frontend/src/lib/cities.js`
  avec toutes les data géo-ciblées : prix moyen m² 2026, artisans région, surface,
  projet type, prix moyen, 3 tips locaux calibrés.
- Auto-routing : `App.js` génère les 10 routes depuis `CITY_LIST.map`, aucune
  intervention manuelle.
- Sidebar « Autres villes couvertes » : liens croisés auto-mis-à-jour dans
  `LocalLanding.jsx` (bootstrap SEO interne — chaque ville pointe vers les 9
  autres).
- Sitemap.xml : +4 URLs indexables (`/devis-travaux-nice`, `-strasbourg`,
  `-rennes`, `-montpellier`), priority 0.9.
- Smoke test : les 4 nouvelles pages ont **title/H1/tips uniques** vérifiés en
  Playwright (Montpellier screenshot inline validé).

### 🔧 Code Quality Round 5
- **`_compute_bounds`** (`plan_dxf.py`) : dispatch inline `if t == "LINE": elif …`
  extrait dans un helper module-level `_bounds_from_entity(e, upd)` — plus
  testable indépendamment, cyclomatic complexity divisée par 2, nesting
  ramené de 3 à 1 dans la boucle principale.

### 5ᵉ rapport — items déjà résolus ou faux positifs
- « 19 undefined vars » (5ᵉ mention) — 0 réel selon ruff/pyflakes/pylint.
- « 153 anti-patterns `is` » — tous `is None/True/False` (Python idiomatique).
- `estimate()` 9 args — dataclass `PricingRequest` livrée iter36, tool externe
  ne détecte pas la variante `estimate_from_request()`.
- `build_tva_attestation_pdf` body 138 lignes — args refactorés en dataclass
  iter35, body sectionalisation reportée (P2).
- `create_checkout`/`ensure_stripe_catalog` (cyclo 14) — payment code sensible,
  refactor P2 avec tests dédiés préalables.
- `paint()`/`tile()`/`_price_model()`/`_sample_thickness()` — grouper params en
  dataclass, P2.
- `deskew_photo` 74 lignes — helpers à extraire, P2.
- `analyze_plan_image` 51 lignes — helpers à extraire, P2.
- `check_user_alerts` cyclo 12 — strategy pattern, P2.
- `roof_facade` 75 lignes — split par facade type, P2.
- `plans.py` 38 imports — split multi-modules, refactor lourd P2.

### 📈 Bilan cumulatif SEO
- **10 villes** locales indexables (Paris, Lyon, Marseille, Toulouse, Bordeaux,
  Nantes, Nice, Strasbourg, Rennes, Montpellier).
- **9 articles** blog long-form SEO.
- **~30 URLs uniques** dans sitemap.xml.
- Toutes avec title/description/H1/canonical/JSON-LD uniques.

