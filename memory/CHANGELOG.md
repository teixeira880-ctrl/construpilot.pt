# ConstruPilot — CHANGELOG

## Itération 119 — 18/06/2026 (Détail chiffrage devis + Vitrine page d'accueil)
- **Détail chiffrage devis (depuis plan)** : `structure_to_quote` accepte `beton_price_m3`, `labor_price_m3`, `margin_pct`. La ligne « Béton coulé » reçoit le prix €/m³, « Aciers HA » le prix €/kg, une ligne « Main d'œuvre béton » (m³) est ajoutée, puis la **marge** est appliquée à ces lignes → prix de vente reporté dans le devis. Frontend `sendToQuote` transmet ces params. Vérifié curl (Béton 138 €, Aciers 2,07 €, MO 103,5 € avec marge 15 %).
- **Vitrine page d'accueil (publicité, option animée)** : nouveau composant `FeatureShowcase.jsx` inséré dans `Landing.jsx` après le bento — 4 blocs alternés animés au scroll (framer-motion `useInView`) : Analyse IA plans/métré béton, Devis express (plan/vidéo), Maquette 3D, Assistant IA & Entreprise. Images réelles, badges statistiques flottants, badge vidéo, puces, CTA. Respecte la charte existante (orange/sombre, police display). Page unique Pro+Particuliers conservée. Vérifié capture d'écran (4 rows, 4 CTA).


## Itération 118 — 18/06/2026 (Marge & main d'œuvre + Comparaison tous presets + Coûts dans PDF)
- **Marge & coût main d'œuvre** : champs « Main d'œuvre €/m³ » (`labor-price-m3`) et « Marge % » (`margin-pct`), stockés dans défauts/presets (`labor_price_m3`, `margin_pct`). Affichage `descriptif-prix-vente` = (coût matière + béton_total×MO) × (1 + marge/100). Vérifié (63 531 €).
- **Comparer tous les presets** : `runCompare` compare désormais TOUS les presets (intégrés + perso), avec lignes « Coût matière » et « Prix de vente estimé » par colonne. Vérifié (Maison 63 531 € vs Immeuble 65 770 €).
- **Coûts dans le PDF béton** : `beton-pdf` accepte `beton_price_m3`, `acier_price_kg`, `labor_price_m3`, `margin_pct` → ajoute un tableau « Chiffrage estimé » (béton, aciers, coût matière, main d'œuvre, prix de vente). Vérifié curl (PDF plus volumineux avec coûts).


## Itération 117 — 18/06/2026 (Coût matière + Comparaison presets + Suppression preset + Dernier preset auto)
- **Coût matière (béton + aciers)** : champ « Prix béton €/m³ » (`beton-price-m3`, stocké dans défauts/presets). Affichage `descriptif-cout-matiere` = béton_total×prix_m³ + acier_total×prix_kg, directement dans le descriptif.
- **Comparer 2 presets** : bouton « Comparer » (`beton-preset-compare`) → dialog `beton-compare-dialog` qui appelle l'analyse du plan courant avec les réglages « Maison » et « Immeuble » et affiche un tableau côte à côte (béton total, aciers, poteaux/poutres/dalles/voiles, coût matière). Vérifié (31 568 € vs 32 681 €).
- **Suppression preset** : bouton corbeille (`beton-preset-delete`) visible quand un preset personnalisé est sélectionné → `DELETE /api/takeoffs/settings/beton-presets/{name}`.
- **Dernier preset auto** : `PUT /api/takeoffs/settings/beton-last-preset` mémorise le preset choisi ; au chargement d'un plan, défauts+presets chargés puis dernier preset ré-appliqué automatiquement. `beton_price_m3` + `last_preset` ajoutés aux modèles/défauts. Vérifié curl + capture d'écran.


## Itération 116 — 18/06/2026 (PDF béton brandé + Prix acier auto + Presets par chantier)
- **PDF béton signé** : `beton-pdf` intègre désormais le logo/en-tête entreprise (`_story_header_branding` + `_resolve_branding`) et un pied de page (`pdf_labels().footer`). Vérifié curl (200).
- **Prix aciers auto** : nouveau champ `acier_price_kg` (dans les défauts + presets + query param de `structure_to_quote`). À la génération du devis, la ligne « Aciers HA » non chiffrée reçoit ce prix au kg → chiffrage instantané. Input « Prix acier €/kg » (`acier-price-kg`) dans l'UI. Vérifié curl (PU=1,8 appliqué).
- **Réglages par chantier (presets)** : `GET /api/takeoffs/settings/beton-presets` (2 intégrés « Maison » / « Immeuble » + personnalisés), `PUT` (upsert nommé, noms réservés bloqués), `DELETE /{name}`. Frontend : `<select>` `beton-preset-select` (applique tous les réglages) + bouton « Enregistrer sous… » (`beton-preset-save`, prompt nom). Vérifié curl (builtins + save/list/delete) + capture d'écran.


## Itération 115 — 18/06/2026 (PNG 3D dans devis + Réglages béton par défaut + Métré PDF)
- **Capture 3D jointe au devis** : `Interactive3D` expose `onAttach` + bouton « Joindre au devis » (`cam-attach-btn`) → PlanTakeoff stocke `plan3dSnapshot` → `sendToQuote` l'envoie en body (`snapshot_png`) à `structure_to_quote` (nouveau modèle `QuoteFromStructureIn`) → stocké dans `doc.attachment_image_b64` → `build_document_pdf` (pdf_docs.py) intègre l'image (reportlab `Image`). Vérifié curl (PDF devis 8,6 Ko avec image).
- **Réglages béton par défaut (entreprise)** : `GET/PUT /api/takeoffs/settings/beton-defaults` (collection `beton_defaults` par user_id) — hauteur murs, ép. dalle/voile, section poutre, ratios aciers. Chemin à 2 segments (`/settings/beton-defaults`) pour éviter le conflit avec `/{plan_id}`. Frontend : chargement au montage + bouton « Enregistrer comme réglages par défaut » (`save-beton-defaults`). Vérifié curl (GET/PUT/persistance).
- **Métré béton PDF** : `GET /api/takeoffs/{plan_id}/structure/{page}/beton-pdf` (reportlab) — synthèse volumes + aciers + tableaux poteaux/poutres, mêmes query params que l'Excel. Bouton « Métré PDF » (`structure-export-beton-pdf`) à côté de « Métré Excel ». Vérifié curl (200, application/pdf).


## Itération 114 — 18/06/2026 (Aciers dans devis + Export 3D PNG + Poutres b×h + Devis vidéo enrichi)
- **Aciers HA dans le devis** : `_descriptif_line_items` renomme la ligne acier en « Aciers HA (fer à béton armé — env. N kg/m³) » (N = moyenne des ratios) ; incluse et chiffrée via bibliothèque dans le devis généré depuis le plan (`structure_to_quote` qui accepte désormais dalle_ep/voile_ep/poutre_l/poutre_h + ratios aciers). Vérifié curl (qty = poids total kg).
- **Export 3D PNG** : `Interactive3D` — `WebGLRenderer({ preserveDrawingBuffer:true })` + bouton « PNG » (`cam-snapshot-btn`) qui télécharge `renderer.domElement.toDataURL()` (maquette-3d-beton.png).
- **Sections poutres réglables (b×h)** : états `poutreL`/`poutreH` + inputs `structure-poutre-l`/`structure-poutre-h` dans `PlanTakeoff.jsx`, transmis à analysis / beton-xlsx / quote. La 3D utilise `poutreLM`/`poutreHM` pour la section des poutres. Vérifié curl (0,20×0,40→0,30×0,80 : béton poutres 2,14→6,43 m³).
- **Devis vidéo enrichi (photos)** : `quote_lines_from_text(text, images)` + `_complete(images=…)` (vision OpenAI) ; `from-text` accepte `images` (data URLs, prefix strippé, max 6). Dialog de relecture (`QuoteEditor.jsx`) : upload photos `capture=environment` (`video-transcript-add-photo`), miniatures + suppression, envoyées à l'IA. Vérifié curl (lignes détaillées à partir d'une photo).


## Itération 113 — 18/08/2026 (Ratios aciers ajustables + Relecture vidéo + Maquette 3D béton)
- **Aciers ajustables** : 5 ratios de ferraillage (kg/m³) éditables dans l'UI (`acier-ratios` / inputs `acier-ratio-{semelles|poteaux|poutres|dalles|voiles}` dans `PlanTakeoff.jsx`). Transmis en query params à `GET .../analysis/{page}` et `GET .../beton-xlsx` (`acier_semelles`, `acier_poteaux`, …). `_compute_descriptif` accepte `acier_ratios` (override de `ACIER_RATIOS`). Vérifié curl : poteaux 130→200 change `acier_total` (21369→23484 kg).
- **Relecture transcription vidéo** : parcours en 2 temps. `POST /api/documents/video-transcribe` (vidéo → transcript) puis dialog éditable (`video-transcript-dialog`/`video-transcript-text`) et `POST /api/documents/from-text` ({text, client_id}) qui génère le devis. Refactor : helpers `_transcribe_video_bytes` et `_quote_doc_from_text` dans `documents.py` (l'ancien `/from-video` les réutilise). Vérifié e2e curl.
- **Maquette 3D des volumes détectés** : `Interactive3D.jsx` étendu — nouveau prop `structure` : rend voiles/murs (rouge, ép. `voileEp`), planchers (dalle verte extrudée, ép. `dalleEp`), poteaux (violet, sol→plafond), poutres (gris foncé, en tête de mur), semelles (jaune, au sol). Bounding box calculée depuis rooms + structure. `Render3dDialog.jsx` passe `structure/dalleEp/voileEp/wallHeight` ; `PlanTakeoff.jsx` les fournit. Vérifié capture d'écran (mode « Maquette interactive »).


## Itération 112 — 18/08/2026 (Métré béton avancé + aciers + Assistant IA + Vidéo→devis + i18n)
- **Tableau Poutres** (B1→Bn : portée + volume béton m³) affiché dans le descriptif `/plan`, calqué sur le Tableau Poteaux (`beams_table` déjà calculé côté backend, exposé/rendu).
- **Semelles éditables** sur le canvas (`PlanCanvas.jsx`) : sélection + déplacement des coins + ajout (bouton « Semelle ») + suppression, comme poteaux/ouvertures. Handlers dans `PlanTakeoff.jsx` (`addStructFooting`, maps drag/delete).
- **Export Métré béton (Excel)** : nouvel endpoint `GET /api/takeoffs/{plan_id}/structure/{page_index}/beton-xlsx` (openpyxl, 3 feuilles : Métré béton / Poteaux / Poutres). Bouton « Métré béton (Excel) » séparé.
- **Aciers (ferraillage)** : ratios moyens kg/m³ par élément (semelles 40, poteaux 130, poutres 140, dalles 85, voiles 60) via `ACIER_RATIOS` dans `_compute_descriptif`. Total aciers affiché dans le descriptif + colonnes dédiées dans l'Excel.
- **Assistant IA** (dialog sur `/plan`) : l'utilisateur guide/corrige la détection en langage naturel → `POST /api/takeoffs/{plan_id}/structure/{page_index}/ai-refine` (Gemini, `refine_structure` dans `plan_structure.py`) renvoie la structure mise à jour + une phrase de réponse ; ne écrase pas en cas d'échec IA.
- **Fonction A — « Ajouter un plan »** depuis l'éditeur de devis (`QuoteEditor.jsx`) : upload → `/takeoffs/upload` → navigation `/plan?open=<id>&auto=1` → analyse Gemini automatique (effet `pendingAuto` dans `PlanTakeoff.jsx`).
- **Fonction B — « Vidéo → devis »** : `POST /api/documents/from-video` (upload vidéo → ffmpeg extrait l'audio mp3 mono 16k → **OpenAI Whisper** transcrit en FR → `quote_lines_from_text` génère les lignes → `_apply_library_prices` chiffre depuis la bibliothèque → crée un devis). Capture mobile via `<input capture="environment">`. Validé e2e (transcription exacte, lignes chiffrées).
- **Bug traduction (devis PDF en portugais)** : `GET /api/documents/{doc_id}/pdf?lang=<fr|..>` — le PDF suit désormais la **langue active de l'interface** (param `lang`) au lieu de `user.lang` figé en base. `QuoteEditor.downloadPdf` passe `lang`.
- **Bug traduction sous-menus** : ajout des clés manquantes (`nav.pro_space`, `nav.discover`, `nav.company`, `nav.invoices`, `nav.situations`, `nav.site`, `nav.catalog`, `nav.compare`) dans `NAV_TRANSLATIONS` (7 langues) — les items des menus « Espace Pro » / « Découvrir » se traduisent correctement.
- Tests : iteration_93 (batch béton/aciers/IA/PDF lang) 100% ; iteration_94 (Fonctions A & D) 100% ; Fonction B validée e2e via curl.


## Itération 111 — 17/08/2026 (Module Suivi de chantier — pack Business)
- Nouveau module **Suivi de chantier** (`/suivi-chantier`, `SiteTracking.jsx`, lien menu « Suivi de chantier ») réservé au **pack Business** (feature `site_tracking` = `PRO_BUSINESS_ONLY` ; free/premium/pro voient un écran « Passer au pack Business » ; admin bypass).
- 3 onglets par chantier (sélecteur nom de chantier) :
  - **Comptes-rendus de visite** (titre + notes + date).
  - **Réserves** (lot, description, entreprise ; bascule En cours ↔ Levée ; suppression).
  - **Checklist d'avancement** (points par lot, cochables, barre de % globale).
- Backend `routes/site.py` (prefix `/site`, registré dans server.py) : CRUD `reports`, `reserves` (PATCH toggle), `checklist` (PATCH toggle) + `/site/projects`. Scopé user_id. Vérifié via curl (create/toggle/list) + capture d'écran (compte Business).
- Fichiers : `backend/routes/site.py`, `backend/server.py`, `frontend/src/pages/SiteTracking.jsx`, `frontend/src/App.js`, `frontend/src/components/Nav.jsx`, `frontend/src/context/BillingContext.jsx`.


## Itération 110 — 17/08/2026 (Fiche PDF publique + QR + Modèle Excel + Coefficient régional)
- **Fiche partagée PDF** : bouton « Télécharger en PDF » sur la page publique `/fiche/:id` (réutilise `POST /calculators-pdf` avec les données partagées, prix inclus). Vérifié + capture.
- **QR code de partage** : nouvel endpoint `GET /qr?data=` (lib `qrcode`, PNG). Affiché dans le dialogue de partage des calculateurs (« Scannez pour ouvrir sur le chantier »). Vérifié (PNG 200) + capture.
- **Modèle Excel** : `GET /prices/catalog/template` génère un .xlsx pré-formaté (en-têtes + exemples). Bouton « Modèle Excel » dans Mon catalogue. Vérifié (xlsx 200).
- **Coefficient départemental** : `GET /prices/departments` (10 zones, ex. IDF ×1.15, DOM ×1.25) ; sélecteur région dans Mon catalogue (persisté localStorage) ; `optimize_cart(..., coefficient)` applique le coef aux prix estimés (démo), pas au catalogue réel. Vérifié (ciment 7,37 → 8,48 € à ×1.15).
- Dépendance ajoutée : `qrcode[pil]` (requirements.txt). Fichiers : `tools.py`, `prices.py`, `price_search.py`, `SharedCalc.jsx`, `Calculators.jsx`, `PriceCatalog.jsx`.


## Itération 109 — 17/08/2026 (Catalogue Prix Admin + Import Tarifs Excel/CSV)
- **Catalogue de prix perso** : page `/mon-catalogue` (`PriceCatalog.jsx`) + lien menu « Catalogue prix » — saisie/édition/suppression de prix réels (nom, prix, unité, fournisseur, catégorie), recherche. Backend `GET/POST/DELETE /prices/catalog` (scopé user_id, upsert par nom).
- **Intégration comparateur** : `/prices/optimize` récupère le catalogue de l'utilisateur (optional_user) ; `optimize_cart(items, catalog)` remplace le prix démo par le prix réel quand le nom correspond (`source="catalog"`, fournisseur = négoce saisi, pas de frais de port). Vérifié : « Plaque BA13 » → Point P 6,50 € (source catalog).
- **Import Tarifs** : `POST /prices/catalog/import` accepte CSV (délimiteurs `;`/`,`/tab, décimales virgule, en-têtes FR : nom/prix/unité/fournisseur/catégorie) ET Excel `.xlsx` (openpyxl). Upsert par nom. Vérifié : CSV 3 lignes + XLSX 2 lignes importées.
- Fichiers : `backend/routes/prices.py`, `backend/engines/price_search.py`, `frontend/src/pages/PriceCatalog.jsx`, `frontend/src/App.js`, `frontend/src/components/Nav.jsx`.


## Itération 108 — 17/08/2026 (Paywall fonctions premium calculateurs)
- **Verrouillage freemium** des fonctions premium des calculateurs (Export PDF, Ajouter au devis, Comparer les formats, Devis groupé, Partager la fiche) via `useBilling().has("calculator_pro_tools")` — nouvelle clé ajoutée à `FEATURE_TIER` (BillingContext) mappée sur `PREMIUM_TIERS = {project_pass, premium, pro, pro_business}`.
- Comportement : le calcul de base reste **gratuit** (acquisition particuliers) ; les fonctions premium affichent une **bannière « Passer Premium »** + verrou. Clic en gratuit → redirection `/tarifs` (connecté) ou `/login` (déconnecté). Payant pour particuliers (Premium + Project pass), inclus Pro/Business, bypass admin.
- Vérifié : utilisateur gratuit → bannière + redirection ; capture d'écran.
- Fichiers : `frontend/src/pages/Calculators.jsx`, `frontend/src/context/BillingContext.jsx`.
- **Accès au code** : orienté vers « Save to GitHub » + ajout du collaborateur hichamon306@gmail.com sur le dépôt GitHub (via support).


## Itération 107 — 17/08/2026 (Persistance panier + Fiche partageable)
- **Persistance sélection** : le panier « Ma sélection » est sauvegardé en localStorage (`construpilot_calc_cart`) et rechargé au retour sur la page.
- **Fiche partageable** : bouton « Partager la fiche » → `POST /calculators-share` crée une fiche publique (token) ; page publique `/fiche/:shareId` (`SharedCalc.jsx`) affiche paramètres, résultats, matériaux/prix, budget + « Préparé par [entreprise] » + CTA. Dialogue de partage avec copie de lien, SMS et e-mail. Endpoints `POST /calculators-share` + `GET /calculators-shared/{id}` (404 si absent). Vérifié curl + capture.
- Fichiers : `backend/routes/tools.py`, `frontend/src/pages/Calculators.jsx`, `frontend/src/pages/SharedCalc.jsx`, `frontend/src/App.js`.
- **Prix réels fournisseurs (tâche 2)** : EN ATTENTE — Point P / Leroy Merlin n'exposent pas d'API prix publique ; clarification demandée à l'utilisateur (catalogue prix admin vs scraper vs API partenaire).


## Itération 106 — 17/08/2026 (Calculateurs : compare Carrelage + Devis multi-calculs + PDF prix)
- **Comparaison Carrelage** : comparaison multi-formats généralisée (config `COMPARE_CONFIG`) — formats 30/45/60/60×120/90, pertes de pose incluses, budget + format le moins cher surligné. Fonctionne aussi pour Placo.
- **Devis multi-calculs** : panier « Ma sélection » (bouton « Ajouter à la sélection ») accumule plusieurs calculs (placo + peinture + béton…) puis « Créer le devis groupé » génère un devis unique avec chaque calcul en catégorie. Vérifié UI (2 calculs).
- **PDF avec prix fournisseurs** : quand les meilleurs prix ont été trouvés, le PDF inclut un tableau « Devis matériaux — prix fournisseurs » (produit/qté/fournisseur/PU/total) + total réel. Endpoint `CalcPdfIn` étendu (`priced_lines`, `priced_total`). Vérifié curl (HTTP 200).
- Fichiers : `backend/routes/tools.py`, `frontend/src/pages/Calculators.jsx`.


## Itération 105 — 17/08/2026 (Calculateurs : multi-formats + PDF + Ajouter au devis)
- **Comparaison multi-formats (Placo)** : bouton « Comparer les formats » → tableau plaques + budget pour 200/250/260/300×120, meilleur prix surligné (frontend, appels parallèles au calc).
- **Export PDF** : endpoint `POST /calculators-pdf` (reportlab/platypus) → fiche de calcul brandée (paramètres, résultats, liste de courses, budget, disclaimer). Bouton « Exporter en PDF ». Vérifié : HTTP 200, application/pdf, 2,3 Ko.
- **Ajouter au devis** : bouton crée un devis (`POST /documents`, doc_type quote) pré-rempli avec les matériaux (prix à compléter) puis ouvre l'éditeur. Gate auth (redirige vers /login si non connecté). Vérifié via curl.
- Fichiers : `backend/routes/tools.py`, `frontend/src/pages/Calculators.jsx`.


## Itération 104 — 16/08/2026 (TVA ajustable + Filtre période pub + Attribution UTM)
- **TVA ajustable** : la conversion devis→facture ouvre un dialogue de choix du taux (5,5 % / 10 % / 20 %). Backend `POST /quotes/sends/{log_id}/to-invoice` accepte `vat_rate`. Vérifié : TTC 12000 @ 20 % → HT 10000 / TVA 2000.
- **Filtre période publicité** : sélecteurs Plateforme + Mois sur le dashboard pub. Backend `/ads/campaigns` & `/ads/summary` acceptent `platform` & `month` ; nouvel endpoint `/ads/filters` (plateformes + mois dispo). Vérifié filtrage (google → 1 campagne).
- **Attribution UTM** : la landing capture `utm_source/medium/campaign` (sessionStorage) et les envoie au lead ; `source` du lead prend l'utm_source pour matcher le tag campagne. Backend `LeadIn` étendu. Vérifié : lead source=adwords-brand.
- Testé : curl (tous flux + seed nettoyé), captures écran (dialogue TVA 3 taux, barre de filtres pub).


## Itération 103 — 16/08/2026 (Facturation depuis devis + Attribution leads + Raccourcis dashboard)
- **Convertir en facture** : bouton sur chaque devis suivi (`/devis`) → `POST /quotes/sends/{log_id}/to-invoice` crée une facture (HT dérivé du TTC à 10 %, snapshot client), idempotent (badge « Voir la facture »). Vérifié curl : FAC-2026-0001, TTC 11000 / HT 10000, 2e appel → already:true.
- **Attribution auto des leads** : champ `lead_source` sur les campagnes pub relie au champ `source` des leads CRM. Nouveaux endpoints `/ads/lead-sources` (distinct) ; `list/summary` renvoient `real_leads` + `real_cpl`. KPIs enrichis (Leads réels, CPL réel). Vérifié : 3 leads source=test → real_cpl 200€.
- **Raccourcis Dashboard** : cartes « Nouveau devis » (/devis-editeur), « Nouvelle facture » (/devis-editeur?type=invoice), « Suivi facturation » (/factures) en haut du tableau de bord.
- Testé : curl (tous flux backend + seed données), captures écran (cartes dashboard, dialogue campagne avec source CRM, KPIs 6 colonnes).


## Itération 102 — 16/08/2026 (Visibilité Devis/Factures)
- Déplacé **« Suivi devis » (/devis)** et **« Factures » (/factures)** du menu déroulant « Plus » vers les liens principaux de la barre de navigation (visibles pour tout utilisateur connecté).
- Retiré ces 2 entrées de `USER_LINKS` et supprimé le bouton fantôme « Suivi devis » redondant (min-[1700px]).
- Vérifié : les liens s'affichent en barre principale et la page /factures se charge correctement.


## Itération 101 — 16/08/2026 (Publicité v2 + Landing 100% multilingue)
- **Graphique Publicité** : ajout d'un BarChart recharts bi-axes (Dépense € à gauche, Leads à droite) par plateforme dans `AdsPanel.jsx` (data-testid `ads-chart`).
- **Édition de campagne** : bouton crayon sur chaque ligne (`ads-edit-<id>`) ouvre le dialogue pré-rempli ; `save()` gère POST (création) et PUT (édition). Vérifié via curl (PUT persiste name/platform/spend/leads).
- **Landing 100% multilingue** : toutes les sections (fonctionnalités, catalogue, comparaison DIY/pro, audiences, FAQ, hero 3D) branchées sur `t()`. ~55 nouvelles clés × 7 langues (fr/en/es/pt/it/de/ar) dans `landingI18n.js`.
- Correctif : renommé le paramètre `t` de `types.map` en `pt` pour éviter le shadowing de la fonction i18n `t`.
- Testé : curl (CRUD + PUT), captures écran (chart, dialogue édition, FAQ/features EN).


## Itération 100 — 16/08/2026 (Module Publicité / Marketing v1)
- Câblé `AdsPanel` dans `/admin` (nouvel onglet « Publicité », entre AI et Requests).
- KPIs : Dépense totale, Budget, Leads, Coût/lead (CPL), ROAS + agrégat par plateforme.
- CRUD campagnes via `/api/ads/campaigns` (GET/POST/PUT/DELETE) + `/api/ads/summary` (routes/ads.py déjà registré dans server.py).
- Corrigé un bug de syntaxe JSX du bouton « Enregistrer » dans `AdsPanel.jsx`.
- Remplacé `window.confirm` par un `AlertDialog` shadcn pour la suppression (cohérence UI).
- Testé : testing_agent iteration_86 (backend 100 %, frontend 100 %) + captures d'écran. CPL/ROAS vérifiés.


## Itération 99 — 16/06/2026 (Option Facturation payante pour les pros)
- Modèle : **Pro Business = Facturation incluse (gratuit)** ; **autres pros = option 5 €/mois**.
- Nouveau plan `invoicing_addon_monthly` (5 €/mois, audience "addon", quota `{addon:"invoicing"}`)
  dans `engines/monetization_catalog.py` (auto-seedé au démarrage via server.py).
- `engines/monetization.py` (fulfillment) : branche add-on → set `user.invoicing_addon=True`
  (ne remplace pas le plan principal).
- `routes/auth.py` `_public` expose `invoicing_addon`.
- `pages/Invoices.jsx` : gate = admin OU tier pro_business OU `user.invoicing_addon` ; écran
  verrouillé avec CTA **« Activer l'option Facturation — 5 €/mois »** → `POST /billing/checkout`
  (plan `invoicing_addon_monthly`) → Stripe.
- Testé (preview) : checkout addon → HTTP 200 + URL Stripe valide ; `invoicing_addon` remonte dans
  `/auth/me` ; compilation OK. Nécessite Deploy (le seed du plan se fait au démarrage).


## Itération 98 — 16/06/2026 (Facturation électronique — Factur-X, Phase 2)
- Plateforme agréée retenue : **SuperPDP** (0,0025 €/facture, API) — raccordement en attente de la
  clé API (compte à créer par l'utilisateur sur superpdp.tech).
- **Génération Factur-X** (format légal FR) codée : `engines/facturx_gen.py` (XML CII profil MINIMUM
  + embarquage via lib `factur-x` → PDF/A-3). Endpoint `GET /documents/{id}/factur-x` (factures only).
- Frontend `pages/Invoices.jsx` : bouton **Factur-X** par facture (téléchargement du PDF électronique).
- Deps : `factur-x==6.7`, `python-stdnum==2.2` (ajoutés à requirements.txt).
- Testé (preview) : facture créée → `/factur-x` HTTP 200, XML `factur-x.xml` embarqué et extrait OK.
  Nécessite un Deploy pour la prod. **Reste : raccordement API SuperPDP (clé API utilisateur).**


## Itération 97 — 16/06/2026 (Écosystème Factures Pro Business — Phase 1)
- Nouvelle page **`/factures`** (`pages/Invoices.jsx`) : liste des factures (`GET /documents?doc_type=invoice`),
  stats (nb, payées, reste à encaisser), **Nouvelle facture** (→ `/devis-editeur?type=invoice`),
  **Facturer un devis** (dialog listant les devis → `POST /documents/{id}/to-invoice` mode total →
  ouvre l'éditeur), PDF (blob), badge statut, **accès direct fiche client** depuis chaque facture.
- Gate **Pro Business** (`tier === "pro_business"` OU `role === "admin"` — cohérent avec le bypass
  admin backend `require_pro_business`) ; sinon écran d'upsell vers `/tarifs`.
- Nav : lien **Factures** ajouté (USER_LINKS, icône FileText). Route protégée dans App.js.
- Le backend existait déjà (documents devis/facture/avoir, numérotation DEV/FAC/AV, conversion,
  paiements, PDF). L'éditeur `QuoteEditor` gère `?type=invoice` et `?plan=` (devis provisoire depuis
  analyse de plan/PC via PlanTakeoff — client/prix/ouvrages modifiables).
- Testé (preview, compte admin) : page rend, dialog conversion, éditeur facture (client/lignes/totaux),
  API to-invoice OK. Nécessite un Deploy pour la prod. **Phase 2 (Factur-X / e-invoicing) en attente.**


## Itération 96 — 16/06/2026 (Suivi des leads pub + relance auto)
- **Suivi leads par source** : `GET /admin/leads/stats` (total, landing, particulier, pro, nouveau,
  gagné) + tableau de bord dans Admin → CRM/Devis (cartes de stats + badge source par lead).
  `pages/Admin.jsx` : state `leadStats`, fetch dans load(), cartes + badge `l.source`.
- **Relance auto** : `routes/leads.py` envoie un e-mail de bienvenue (Resend, template HTML brandé)
  dès qu'un lead est créé avec `source` commençant par "landing" (fire-and-forget). Champ `name`
  optionnel géré.
- Testé (preview) : POST /leads pro+particulier → stats correctes ; `_send_welcome` + send_email
  renvoient Resend `ok:true` ; UI Admin affiche stats + badges. Nécessite un Deploy pour la prod.


## Itération 95 — 16/06/2026 (Page d'accueil orientée conversion pub)
- Refonte du hero de `pages/Landing.jsx` (charte respectée : moss green / slate, Outfit/Manrope) :
  - **Sélecteur d'audience** particulier (défaut) / pro → change dynamiquement H1, sous-titre, CTA
    et destination (particulier → /smart-project ; pro → /estimation).
  - **Capture de lead** : champ e-mail ajouté au formulaire hero → `POST /leads`
    `{email, description, source: "landing-hero-<audience>"}` (non bloquant, navigue quand même).
  - Micro-copie de réassurance + trust badge.
  - **CTA collant mobile** « Estimer mon projet » (apparaît au scroll > 620px, `lg:hidden`).
- Backend `routes/leads.py` : `LeadIn.name`/`phone` rendus optionnels + champ `source` (compatible
  ascendant) pour permettre la capture rapide au hero.
- Testé (preview) : toggle audience OK, H1/CTA swap OK, POST /leads minimal 200 (source taguée),
  CTA mobile visible au scroll, navigation particulier→/smart-project & pro→/estimation OK.
  Nécessite un Deploy pour la prod.


## Itération 94 — 16/06/2026 (Admin : définir l'e-mail 2FA d'un utilisateur)
- `routes/admin.py` `UserIn.two_fa_email` (+ normalisation) → un admin peut définir/effacer l'e-mail
  de réception des codes 2FA de n'importe quel utilisateur via `PUT /admin/users/{id}`.
- `pages/Admin.jsx` (onglet Utilisateurs, colonne 2FA) : bouton ✉️ (icône lucide Mail) ouvrant un
  prompt pour saisir l'e-mail 2FA. Utile car un admin avec 2FA activée + boîte inaccessible ne peut
  pas le régler lui-même (self-service bloqué).
- Testé (preview) : set `mteixeira@live.fr` + reset OK. Nécessite un Deploy pour la prod.


## Itération 93 — 16/06/2026 (2FA : e-mail de réception configurable)

### 🔐 E-mail de réception des codes 2FA (Option B)
- Nouveau champ user `two_fa_email` (optionnel). Si renseigné, les codes 2FA sont envoyés à cette
  adresse ; sinon fallback sur l'e-mail du compte.
- Backend `routes/auth.py` : `ProfileIn.two_fa_email` (+ validation), `_public` expose `two_fa_email`,
  `_send_2fa_email` utilise `two_fa_email or email`, `_start_2fa` renvoie le destinataire masqué
  (`_mask_email`) dans le message de connexion.
- Frontend `components/account/TwoFaCard.jsx` : champ « E-mail de réception des codes 2FA » + bouton
  Enregistrer (visible pour les admins), PUT `/auth/profile`.
- Testé (preview) : enregistrement, rejet e-mail invalide (400), login 2FA → « Code envoyé à
  mo*****@gmail.com ». Nécessite un **Deploy** pour la prod.



## Itération 92 — 16/06/2026 (Prod : SEO, cache & connexion sur domaine perso)

### 🐛 P0 — Connexion impossible en production (www vs non-www / CORS) — RÉSOLU
- **Cause racine** : les navigateurs mobiles **masquent le `www.`**. L'utilisateur était sur
  `www.construpilot.fr` alors que le build appelle l'API en dur sur `https://construpilot.fr`
  (non-www) → requêtes **cross-origin bloquées en CORS** (OPTIONS 400 "Disallowed CORS origin")
  → TOUTES les actions échouaient (login, mot de passe oublié) avec message générique.
- **Fix** : `frontend/src/index.js` — redirection automatique `www.*` → non-www (aligne avec le
  canonical/sitemap et garantit des appels API same-origin, donc plus de CORS).
- Vérifié : `www.construpilot.fr/api/login` = 200 (same-origin). Nouveau build `main.2552263e.js`
  déployé, utilisateur confirme "tout fonctionne".

### 🔄 P0 — "La dernière version ne s'affiche pas" — RÉSOLU
- `frontend/public/sw.js` réécrit : HTML/navigation en **network-first** (au lieu de cache-first),
  cache versionné `construpilot-v3`, assets hashés en cache-first, API network-first.
- `frontend/src/index.js` : `reg.update()` + reload sur `controllerchange` → les appareils
  bloqués se mettent à jour automatiquement.

### 🔍 SEO / Google — RÉSOLU
- Erreur Search Console "le sitemap est un fichier HTML" = l'URL soumise était la racine
  `construpilot.fr/` au lieu de `construpilot.fr/sitemap.xml`. Corrigé côté GSC → 30 pages, statut
  "Opération effectuée". Site indexé sur Bing. Google : indexation en cours (délai normal).
- `frontend/public/sitemap.xml` nettoyé : retrait des pages protégées `/plan` et `/parrainage`.

### ⚠️ Restant / connu
- **Google Login sur domaine perso** : l'OAuth Emergent échoue sur `construpilot.fr`
  ("Session Google invalide"). Contournement : e-mail/mot de passe. Nécessite le support Emergent.
- **CORS backend** : la prod bloque encore le www en CORS (OPTIONS 400), mais sans impact grâce à
  la redirection non-www. `CORS_ORIGINS` (.env) contient déjà www + non-www.
- **Page Admin** : l'utilisateur avait signalé un souci non précisé — jamais détaillé (à revoir).



## Itération 91 — 15/06/2026 (Claude Sonnet 4.6 étendu à tout le texte)

### 🤖 Claude Sonnet 4.6 partout (texte)
- `engines/ai.py` : `PROVIDER/MODEL = anthropic/claude-sonnet-4-6` → toutes les fonctions
  **texte** passent sur Claude (Coach chat, `analyse_description`, `compare_quotes`,
  `project_advice`).
- Ajout `VISION_PROVIDER/VISION_MODEL = openai/gpt-5.5` : `_complete()` bascule
  automatiquement sur le modèle vision quand des **images** sont fournies (`analyse_photo`,
  `analyse_quote` avec image) — car Claude via clé Emergent = texte uniquement.
- Testé : `/api/chat` (SSE Claude) et `/api/estimation/analyse` (peinture 30 m²) OK. ruff clean.

### ⚠️ Production
- Nécessite un **redéploiement** (Deploy) pour www.construpilot.fr.

---

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

## Iter 83 (16/06/2026) — Sélecteur de Modèle IA (Admin)
- **Backend** (`engines/ai.py`) : catalogue `AI_TEXT_MODELS` (3 paliers) + cache mémoire `_TEXT_TIER` chargé depuis `db.app_settings` (`_id:"ai"`, champ `text_tier`). Helpers `get_text_tier()` / `set_text_tier()` / `_text_provider_model()`.
  - opus → `claude-opus-4-8` (qualité max) · sonnet → `claude-sonnet-4-6` (défaut, équilibré) · haiku → `claude-haiku-4-5-20251001` (rapide/éco).
  - `_complete()` (non-vision) et `stream_chat()` (coach) utilisent désormais le modèle dynamique. La vision reste sur `gpt-5.5`.
- **Endpoints Admin** (`routes/admin.py`) : `GET /api/admin/ai-model` (current + options) · `PUT /api/admin/ai-model` `{tier}` (persist + maj cache). Modèle Claude via clé LLM Emergent (playbook integration_expert, source verified).
- **Frontend** : nouvel onglet Admin « IA » (`admin-tab-ai`) + composant `AiModelTab.jsx` (3 cartes cliquables `admin-ai-option-{tier}`, palier actif surligné, maj immédiate via toast).
- **Tests** : backend curl GET/PUT (persistance haiku→sonnet OK) · frontend screenshot (onglet + 3 options + « Actif » sur Sonnet).
- Note : facturation électronique (SuperPDP/Factur-X) mise en pause à la demande de l'utilisateur.

## Iter 84 (16/06/2026) — Emails multilingues + Suivi coûts IA + CRM multilingue (7 langues)
Langues supportées : fr, en, es, pt, it, de, ar (fallback FR).

### 1. Emails multilingues
- Nouveau champ `user.lang` : rempli au register (`RegisterIn.lang`), modifiable via `PUT /api/auth/language` (sync auto depuis l'UI dans `I18nContext.setLang`) et via le profil. `_public` renvoie `lang`. `norm_lang()` normalise (fallback fr).
- Module `engines/email_i18n.py` : table `EMAILS[lang][key]` + helper `T(lang,key,**kw)`. Traduit : reset mot de passe, code 2FA, relances facture J+7/J+15.
- Câblé dans `routes/auth.py` (forgot_password, _send_2fa_email) et `routes/documents.py` (relances facture → langue du pro émetteur).

### 2. Suivi des coûts IA (compteur d'appels, sans €)
- `engines/ai.py` : `_log_usage(feature, provider, model)` incrémente `db.ai_usage` ($inc calls) à chaque appel `_complete`/`stream_chat`. Fonctionnalités taguées : smart_project, photo_analyse, quote_scan, quote_compare, project_advice, coach.
- `AI_TEXT_MODELS` enrichi avec `quality/speed/cost` (1-3) pour le comparateur.
- Endpoint `GET /api/admin/ai-usage` (total + by_feature + by_model + detail). `GET /api/admin/ai-model` renvoie désormais quality/speed/cost.
- Frontend `AiModelTab.jsx` : barres vitesse/coût/qualité par palier + tableau de consommation (par fonctionnalité / par modèle).

### 3. CRM multilingue
- `frontend/src/lib/crmI18n.js` : `CRM_TRANSLATIONS` (7 langues, ~90 clés `crm.*`) fusionné dans `I18nContext`.
- Pages câblées avec `t()` : `Clients.jsx`, `ClientDetail.jsx`, `Invoices.jsx`, `QuoteEditor.jsx`.
- Libellés PDF : `engines/pdf_i18n.py` (`pdf_labels(lang)`), `build_document_pdf(doc, lang=...)` localise devis/facture/avoir ; `documents.py` passe `user.lang`.

### Tests — iteration_83.json : backend 100% (9/9), frontend 100%. Aucun bug critique.
Points optionnels non traités : warning hydration devtools sur un <select> QuoteEditor (non bloquant) ; chrome Admin reste en FR (hors scope).

## Iter 85 (16/06/2026) — Admin multilingue + Alerte budget IA + Relance J+2 + Graphique conso IA
### 1. Admin multilingue (7 langues)
- `frontend/src/lib/adminI18n.js` (`ADMIN_TRANSLATIONS`, ~42 clés `admin.*`) fusionné dans I18nContext.
- `Admin.jsx` : titre + 16 onglets + 5 KPIs principaux traduits ; sous-panneaux (Plans/Revenu, Demandes, Erreurs, Affiliation) → KPIs traduits via `useI18n`. (Le contenu détaillé de certains panneaux reste FR — hors périmètre.)

### 2. Alerte budget IA
- `engines/ai.py check_ai_budget()` : somme mensuelle des appels (via `ai_usage_daily`), email d'alerte si seuil dépassé (1×/mois, verrou `budget_alert_month`).
- Endpoints `GET/PUT /api/admin/ai-budget` (seuil + email d'alerte ; PUT réarme le verrou).
- Job planifié `ai_budget_check` (interval 1h) dans server.py.
- UI : formulaire seuil + email dans l'onglet IA (`AiModelTab.jsx`).

### 3. Relance J+2 prospects
- `routes/leads.py run_prospect_reminders()` : leads landing statut 'nouveau', créés il y a 2-4 j, sans estimation terminée → email de relance (`_j2_reminder_html`), flag `j2_reminded` (1×).
- Job planifié `prospect_j2_reminders` (interval 6h).

### 4. Graphique consommation IA (30 j)
- `engines/ai.py _log_usage()` incrémente aussi `db.ai_usage_daily {_id:YYYY-MM-DD}`.
- Endpoint `GET /api/admin/ai-usage-daily?days=30` (gap-fill 0, clamp 1..90).
- UI : BarChart recharts dans l'onglet IA.

### Tests — iteration_84.json : backend 100% (9/9 pytest), frontend 100%. Aucun bug critique.
Fichier test : /app/backend/tests/test_iter84_ai_budget_daily_j2.py

## Iter 86 (16/06/2026) — Module RH : Pointage & présence chantier (Pro Business)
Réservé au plan Pro Business (admin autorisé). Ouvriers = comptes dédiés (role='worker', employer_id).

### Backend
- `routes/hr.py` (préfixe /api/hr) : gestion ouvriers (CRUD + reset mdp + désactivation), pointage entrée/sortie (selfie base64 + GPS + horodatage, calcul auto des heures), liste + validation des pointages, tableau de bord (heures par ouvrier/chantier + à valider), commentaires/doutes de chantier (ouvrier signale, employeur répond), endpoint selfie protégé (ACL employeur/ouvrier).
- Auth : réutilise `core/security.py` (hash_password/make_jwt/current_user) — pas de nouveau système ; l'ouvrier se connecte via /auth/login. `_public` renvoie role.
- Stockage selfies : `engines/storage.py` (Emergent object storage) via `asyncio.to_thread`. Refs dans `db.hr_files`.
- Collections : users(role=worker), hr_timesheets, hr_notes, hr_files.
- Gating : `engines.monetization.require_pro_business` (402 si non éligible ; le front gate localement via tier).

### Frontend
- `pages/HR.jsx` (employeur, route /rh) : onglets Ouvriers / Pointages / Chantier (doutes) / Tableau de bord + paywall Pro Business. Composant Selfie (blob authentifié).
- `pages/WorkerApp.jsx` (ouvrier, route /pointage, mobile) : choix chantier, selfie (input capture), GPS (geolocation), clock-in/out, doutes, mes heures. Login ouvrier → redirection /pointage.
- `lib/hrI18n.js` (7 langues) fusionné dans I18nContext ; lien nav "RH — Chantier".

### Tests — iteration_85.json : backend 100% (22/22 pytest), frontend 100%. Aucun bug critique.
Fichier test : /app/backend/tests/test_iter85_hr_module.py
Credentials : ouvrier@construpilot.fr / Ouvrier2026! (worker, employeur=admin).
Non bloquant : warning hydration <span> dans <option> (artefact instrumentation) ; a11y DialogDescription corrigé.

## Iter 87 (16/06/2026) — Mode démo paiement + 4 extensions RH
### Mode démo (paiement)
- Stripe déjà en mode TEST (sk_test_) → carte 4242 4242 4242 4242 fonctionne dans le checkout (déblocage au retour via sync_status, sans dépendre du webhook).
- Nouveau : `POST /api/admin/demo-unlock` (+ /demo-lock) octroie une entitlement Pro Business (10 ans) + invoicing_addon → TOUTES les options débloquées instantanément. Bouton "🎬 Mode démo" dans l'Admin.

### Extensions RH
- **Photos de chantier** : POST/GET /api/hr/site-photos (ouvrier upload base64 + légende → object storage). Galerie côté patron (onglet Chantier), upload côté ouvrier (input capture=environment).
- **Export paie** : GET /api/hr/export/csv (UTF-8 BOM, ; sep) + /export/pdf (reportlab, agrégé par ouvrier, heures validées × taux = montant). Boutons dans le dashboard RH.
- **Alerte pointage oublié** : job `run_forgotten_clockouts` (cron 20:00) → email patron si pointage 'open' > 12h (flag alerted_forgotten).
- **Géo-clôture** : PUT /api/hr/projects/{id}/geofence (lat/lng/radius). clock-in/out calculent la distance (haversine) et flag `out_of_zone`. Badge "Hors zone" dans les pointages + gestionnaire géofence ("Use my location") dans le dashboard.
- Nouvelles clés i18n HR (HR_EXTRA, 7 langues).

### Tests : backend validé par curl (géofence hors-zone détecté à 440km, photos, CSV/PDF générés, job sans crash, demo-unlock→tier pro_business). Frontend smoke screenshot OK.
### EN ATTENTE (non fait ce tour) : page d'accueil multilingue (contenu codé en dur FR) + dashboard leads Admin — à traiter au prochain tour.

## 2026-08-16 — Module Publicité / Marketing (v1)
- Câblé le panneau `AdsPanel` dans /admin (nouvel onglet « Publicité »).
- KPIs: Dépense totale, Budget, Leads, Coût/lead (CPL), ROAS + agrégat par plateforme.
- CRUD campagnes via `/api/ads/campaigns` (+ `/api/ads/summary`). Corrigé bug JSX du bouton Enregistrer.
- Remplacé window.confirm par AlertDialog shadcn pour la suppression.
- Testé: testing_agent iteration_86 (backend 100
## 2026-08-17 — Comparatif concurrents + Validation Factur-X (facturxapi.com)
- **Test Suivi de chantier** : e2e testing_agent iteration_87 → backend 12/12, frontend 11/11 flows. Module validé pour prod (route /suivi-chantier, gating admin OR pro_business).
- **Page /comparatif** (publique, SEO) : `frontend/src/pages/Comparatif.jsx` — tableau comparatif ConstruPilot vs Costructor/Obat/Tolteck/Graneet/Batigest/OptimBTP/ProGBat (15 lignes), 4 raisons différenciantes, note de transparence, CTA. JSON-LD FAQPage. Route ajoutée dans App.js + lien "Comparatif" dans Nav (MORE_LINKS).
- **Validation Factur-X** : intégration facturxapi.com (POST https://api.facturxapi.com/api/v1/validate, Bearer + multipart).
  - Clé stockée dans backend/.env → `FACTURX_API_KEY` (jamais en dur).
  - Engine `backend/engines/facturx_validator.py` (httpx async, validation_target=en16931, lang=fr, rapport simplifié valid/profile/error_count/issues).
  - Endpoint `POST /api/documents/{doc_id}/factur-x/validate` : régénère le Factur-X et le soumet au validateur, stocke `facturx_validation` sur le doc.
  - UI Invoices.jsx : bouton "Valider" (pastille verte/rouge) + dialog "Non-conformités détectées" listant code/sévérité/stage/message.
  - Testé e2e (admin) : rapport réel renvoyé — 2 erreurs détectées sur facture non-brandée (PDFA_NOT_COMPLIANT + BR-CO-26 SIRET/TVA vendeur manquant). Le validateur remonte donc bien les vraies non-conformités.
- ⚠️ À NOTER : les factures actuellement générées ne passent pas encore la validation (PDF/A-3 non conforme + il faut renseigner SIRET/TVA dans le branding). La brique de VALIDATION fonctionne ; l'amélioration de la GÉNÉRATION Factur-X (PDF/A-3 strict + champs vendeur) reste à faire si conformité totale souhaitée.

## 2026-08-17 (2) — Factur-X 100% conforme + Badge auto + Facturation à l'avancement (situations)

### 1. Factur-X PDF/A-3 conforme (via facturxapi.com /convert)
- Engine `backend/engines/facturx_converter.py` : `build_invoice_data()` (EN16931) + `convert_facturx()` (POST /api/v1/convert, output=facturx_pdfa3, validation_target=en16931). Renvoie un vrai PDF/A-3 conforme + validation.
- `documents.py` : `_ensure_facturx()` avec CACHE (`facturx_pdf_b64` + `facturx_validation` + `facturx_hash` sur le doc ; invalidé à chaque PUT). Repli local `to_facturx` si API indispo/quota.
- `/documents/{id}/factur-x` (download) et `/factur-x/validate` (rapport détaillé) utilisent le cache → quota minimal.
- Branding étendu : adresse structurée vendeur (`brand_address/city/postal/country`) dans BrandingIn, get/update_branding, `_resolve_branding` (user + org). BrandingDialog.jsx : champs Adresse/CP/Ville/Pays.
- ✅ Testé (curl, admin + SIRET test 10000000900017 / TVA FR88100000009) : émission → `{"valid":true,"profile":"EN16931","error_count":0}`.

### 2. Badge conformité auto
- `/documents/{id}/issue` déclenche `_ensure_facturx(force=True)` (best-effort, non bloquant) → peuple `facturx_validation`.
- Invoices.jsx : badge vert "Conforme EN16931" / rouge "Non conforme" dans la liste (depuis inv.facturx_validation). ✅ vérifié en capture.
- ⚠️ QUOTA : chaque émission consomme 1 crédit facturxapi (sandbox limité). Repli silencieux si 429/erreur.

### 3. Facturation à l'avancement — Situations de travaux
- `backend/routes/situations.py` (router `/situations`) : GET /marches, GET ?marche_id, POST (calcule delta d'avancement par ligne depuis la situation précédente, génère une facture de situation), DELETE.
- Retenue de garantie OPTIONNELLE (0-10%, bouton "5% standard") : montant plein facturé, `net_due` = TTC - retenue (note sur la facture). Collection `situations`.
- Frontend `pages/Situations.jsx` (route `/situations`, gate pro_business/admin) : sélecteur marché, tableau % précédent/cumulé/montant, création, historique. Lien dans Nav (menu Plus) + bouton sur /factures.
- ✅ Testé (curl) : Situation 1 (GO 30%+Plomb 50%) = 25000€ HT / 29000€ TTC / retenue 1250€ / net 27750€ ; Situation 2 delta correct (GO 30%=15000€, Plomb 0€). Page vérifiée en capture.

NOTE : branding de test posé sur admin@construpilot.fr (SIRET/TVA/adresse fictifs) pour prouver la conformité verte. Le vrai user (teixeira) doit renseigner ses SIRET/TVA/adresse réels dans /compte.

## 2026-08-17 (3) — Espace Entreprise (hub + rôles/permissions + gestion des employés)

### Backend
- `routes/company.py` (prefix `/company`) : rôles owner/admin/chef_chantier/comptable/member/ouvrier avec mapping de permissions (features: dashboard, devis, factures, situations, chantier, rh, catalogue, entreprise, pointage).
  - `GET /company/me` → rôle + permissions (gating frontend ; admin plateforme & solo = accès complet).
  - `GET /company/dashboard` → KPIs org-wide (CA TTC, encours, factures conformes, devis, situations, chantiers, réserves, membres/ouvriers) + liste membres + rôles assignables.
  - `POST /company/employees` → le patron crée un compte employé (hash_password, rôle, mdp provisoire, must_change_password). Ouvrier → role=worker + employer_id.
  - `PUT /company/members/{id}` → change rôle et/ou active (désactivation d'accès). `DELETE` → retire de l'org.
- `billing.py` `/billing/me` : les membres d'une org **héritent du tier du propriétaire** (max tier) → les employés accèdent aux modules Business. ✅ testé : collègue hérite `pro_business`.

### Frontend
- `context/PermissionContext.jsx` : `can(feature)` (solo/owner/admin = tout ; rôles limités restreignent). Provider ajouté dans App.js.
- `pages/Entreprise.jsx` (route `/entreprise`, gate pro_business) : hub central — KPIs, 6 cartes modules (gated par can()), gestion équipe (créer employé, changer rôle, désactiver/réactiver, retirer), branding, abonnement.
- Nav : lien "Entreprise" + **gating par permissions** (PRIMARY/MORE/USER/mobile filtrés par `perm`).
- Gating au niveau page (défense en profondeur) : Invoices/Situations/SiteTracking → `NoAccess` si `in_org && !can(feature)`.
- ✅ Testé (curl + captures) : owner = perms complètes + KPIs ; chef_chantier = Factures/Entreprise masqués en nav + `/factures` → NoAccess + `/suivi-chantier` OK ; tier pro_business hérité.

RESTE À FAIRE (demandé par l'utilisateur, non fait ce tour) : Retenue libérée (levée 1 an), Situations cumulées (dashboard marché), Émission groupée, Compte prorata.

## 2026-08-17 (4) — Refonte barre de navigation (fix débordement + design moderne/relief)
- `components/Nav.jsx` restructurée : liens réorganisés en NAV_MAIN (inline : Dashboard, Estimateur, Calculateurs, Prix), 2 menus déroulants NAV_PRO ("Espace Pro", auth + perm) et NAV_DISCOVER ("Découvrir"), + Tarifs inline. ACCOUNT_LINKS via avatar→/compte. Mobile = ALL_LINKS filtrés (auth+perm), breakpoint lg.
- Design relief/3D : header glass + shadow, pill active `bg-primary` + shadow, hover lift (-translate-y-0.5), badges d'icônes arrondis dans les menus, logo en badge arrondi animé.
- Corrige le chevauchement du cluster droit (thème/langue/notifs/user) causé par trop de liens inline.
- Gating par permissions conservé dans tous les menus (desktop + mobile).
- ✅ Vérifié en capture : nav propre sans débordement, menu Espace Pro déroule 11 modules avec icônes.

## 2026-08-17 (5) — Journal d'activité par entreprise (audit léger)
- `engines/activity.py` : `log(user, action, entity, label, meta)` best-effort (résout org via organization_id ou employer_id → journal partagé entreprise ; sinon solo:{uid}). `recent(org_id)`.
- Instrumentation : documents (quote/invoice.create, invoice.issue, document.delete), situations (situation.create, retention.release), company (employee.create, member.update), hr (clock.in / clock.out).
- `GET /company/activity` (owner/admin) → 150 derniers événements de l'org.
- Frontend : section "Activité récente" dans `pages/Entreprise.jsx` (timeline avatar + action + libellé + date FR).
- ✅ Testé (curl + capture) : création devis, ajout employé, suppression doc bien journalisés et affichés.

## 2026-08-17 (5b) — Endpoints backend Situations avancées (UI non encore branchée)
- `routes/situations.py` ajouts (backend OK, testés partiellement) :
  - GET `/situations/summary?marche_id=` → avancement cumulé (par lot : contrat/cumul%/facturé/restant + globaux, retenue détenue).
  - Retenue de garantie : POST `/{marche_id}/reception` (date réception → échéance +1 an), GET `/retentions`, POST `/retentions/{id}/release`, POST `/retentions/{id}/remind` (email Resend).
  - Compte prorata : GET/PUT `/{marche_id}/prorata` (taux % + dépenses → répartition auto par lot).
- ⚠️ RESTE À FAIRE : brancher le FRONTEND (onglets Avancement / Retenue / Prorata dans Situations.jsx) + fonctionnalité "Émission groupée" (POST /documents/issue-batch + UI cases à cocher sur /factures). Non commencés.

## 2026-08-17 (6) — Les 4 fonctionnalités Situations/Facturation branchées (UI) + Émission groupée
- **Situations.jsx** refait en onglets : Nouvelle situation | Avancement | Compte prorata | Retenue de garantie (sélecteur de marché partagé).
- **Avancement (cumulé)** : KPIs (marché/facturé/restant/retenue) + barre d'avancement global + tableau par lot (facturé vs restant). GET /situations/summary. ✅ vérifié capture (57,1%).
- **Compte prorata** : taux % + dépenses communes éditables → cagnotte répartie auto par lot (quote-part). GET/PUT /situations/{id}/prorata. ✅ vérifié capture (2% + 600€ → 2000€, 71,43/28,57%).
- **Retenue de garantie** : liste globale des retenues détenues, saisie date de réception (→ échéance +1 an), bouton Libérer + Relancer (email). GET /situations/retentions, POST reception/release/remind. ✅ backend testé (release_due 2027-06-01).
- **Émission groupée** : `POST /documents/issue-batch` (émet N docs + contrôle conformité Factur-X en lot). UI /factures : cases à cocher sur les brouillons + barre "Émettre la sélection". ✅ testé (2 émises, 2 conformes EN16931).
- Tous les endpoints backend testés via curl ; onglets Avancement + Prorata vérifiés en capture.

## 2026-08-17 (7) — Décompte de situation PDF (format maîtrise d'œuvre)
- `engines/situation_pdf.py` : build_situation_pdf(sit, branding, client) → PDF reportlab (en-tête entreprise SIRET/TVA, titre "DÉCOMPTE DE SITUATION N°x", tableau par lot [Marché HT / % préc. / % cumulé / Cumul HT / Situation HT], totaux HT/TVA/TTC + retenue + NET À PAYER en vert, mention légale libération 1 an).
- Endpoint `GET /situations/{situation_id}/pdf`. Frontend : bouton "Décompte PDF" sur chaque situation de l'historique (Situations.jsx).
- ✅ Testé : PDF valide 2,7 Ko, contenu vérifié (figures cohérentes, TVA multi-taux 20%/10% = 4000€, net 27 750€).

## 2026-08-17 (8) — Mode 100% gratuit (lancement) + relance auto retenue + logo + certificat + export journal
- **Mode gratuit lancement** : `FREE_PROMO_MODE=true` (backend/.env). `monetization.user_tier()` renvoie `pro_business` pour tout utilisateur connecté → toutes les fonctions débloquées. ✅ testé (client free → pro_business). Pour DÉSACTIVER après la phase promo : FREE_PROMO_MODE=false + redéployer.
- **Relance auto retenue** : `situations.run_retention_reminders()` (retenues échéance ≤30j, non libérées, 1 relance/mois max) + job scheduler quotidien 08:30 UTC (server.py). Bouton manuel "Relancer" déjà présent.
- **Nouveau logo** : icône générée → /public/construpilot-icon.png. Intégré dans Nav (badge), favicon (index.html), page Login. Logos aussi dans /public/construpilot-logo.png.
- **Certificat de paiement** : `situation_pdf.build_payment_certificate()` + GET `/situations/{id}/certificate` (montant certifié "Bon à payer" + bloc visa maître d'œuvre). Bouton "Certificat" dans Situations.jsx. ✅ testé (PDF 2,3 Ko).
- **Journal exportable** : GET `/company/activity/export?actor_id=` (CSV BOM ; ; filtrable employé) + `recent(actor_id)`. UI Entreprise.jsx : filtre par employé + bouton "Export CSV". ✅ testé.

## 2026-08-17 (9) — Auto-bibliothèque + bandeau gratuit + journal PDF (UTM & onboarding déjà présents)
- **Auto-enregistrement bibliothèque** : `library.auto_save_from_lines()` appelé à la création ET modification de document (documents.py). Chaque poste (désignation, unité, prix, TVA, catégorie, DESCRIPTION) est upserté dans library_items (dédup par désignation, insensible à la casse). Lignes de situation ignorées. Champ `description` ajouté au modèle DocLine. ✅ testé.
- **Bandeau "100% gratuit"** : bannière verte en haut de Landing.jsx avec CTA /inscription. ✅ vérifié capture.
- **Journal PDF** : GET `/company/activity/pdf?actor_id=` (reportlab) + bouton "PDF" dans Entreprise.jsx (à côté de CSV). ✅ testé (2,1 Ko).
- **UTM (déjà présent)** : Landing.jsx capture utm_source/medium/campaign → leads.py + AdsPanel. Liens pub à utiliser : `https://construpilot.fr/?utm_source=linkedin&utm_medium=social&utm_campaign=lancement`.
- **Onboarding (déjà présent)** : OnboardingTour.jsx (tour de bienvenue affiché 1×/user).

## 2026-08-17 (10) — Compteur inscrits + onboarding ciblé + description éditeur + dashboard canal
- **Compteur inscrits (preuve sociale)** : GET public `/leads/public-count` (users hors worker + base 1240). Composant `components/SignupCounter.jsx` (refresh 15s, pastille pulsante) sous le bandeau de la landing. ✅ vérifié (1 384).
- **Onboarding ciblé** : OnboardingTour.jsx lit sessionStorage `construpilot_utm_source` → bannière dédiée "Bienvenue depuis LinkedIn/Instagram/Facebook + accès 100% gratuit" à l'étape 1.
- **Description éditeur** : champ `description` par ligne dans QuoteEditor.jsx (textarea sous chaque ligne), ajouté au modèle DocLine (backend), envoyé au save et archivé automatiquement dans la bibliothèque (notes).
- **Dashboard canal** : GET `/ads/channels` (agrégation leads par utm_source) + carte "Leads par canal d'acquisition" dans AdsPanel.jsx (pastilles LinkedIn/Instagram/Facebook). ✅ endpoint testé.

## 2026-08-17 (11) — Pub Instagram + e-mail bienvenue + description multi-ligne + générateur UTM
- **Pub Instagram particuliers** : 2 visuels générés (carré + story) — homeowners, offre gratuite, logo/branding.
- **E-mail de bienvenue** : envoyé à l'inscription (auth.register, best-effort emailer, mentionne l'offre 100% gratuite).
- **Description multi-ligne** : QuoteEditor.jsx → textarea (rows=2) par ligne (persisté + archivé en bibliothèque). NB: suggestions IA d'ouvrages NON incluses (multi-ligne seulement).
- **Générateur de lien UTM** : carte dans AdsPanel (réseau + campagne → lien construpilot.fr prêt à copier) + carte "Leads par canal".
- ✅ register testé (token OK), bundle compile (login OK).

## 2026-08-17 (12) — Pack visuels Instagram + relance J+3
- Pack de 5 visuels Instagram générés (avant/après, témoignage, prix, 3D, 100% gratuit).
- Relance J+3 : leads.run_signup_followups() + job scheduler quotidien 09:00 UTC (inscrits ~3j sans devis → e-mail, flag welcome_followup). ✅ backend sain.
- NON FAITS (budget) : Suggestions IA d'ouvrages (nécessite intégration LLM), Landing dédiée particuliers (nouvelle page).
