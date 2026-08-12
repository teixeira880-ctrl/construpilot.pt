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

