# STAIRPILOT — Product Requirements Document

## Vision produit
Application mobile Expo (React Native) permettant à un bureau d'études béton ou à un maçon (persona France, DTU 36.3) de concevoir et calculer un escalier béton coulé en place — droit, quart tournant, demi-tournant, hélicoïdal — avec vérification de conformité en temps réel.

Le moteur de calcul est **100% déterministe** — aucune IA n'invente de cotes.

## Personas cibles
- **BE béton** (bureau d'études structure) — France, référentiel DTU 36.3.
- **Maçon** confronté à un escalier béton sur chantier.
- Pas d'authentification au MVP. Projets stockés localement sur l'appareil.

## Stack
- **Backend** : FastAPI + MongoDB (`/app/backend`).
- **Frontend** : Expo Router (React Native, SDK 57) — `/app/mobile`.
- **Moteur de calcul** : Python déterministe (`/app/backend/stair_engine/`).
- **Rendu 2D** : `react-native-svg` (composants `StairPlan`, `StairSection`).
- **Stockage local** : `@react-native-async-storage/async-storage`.
- **Base de règles** : seuils DTU 36.3 dans `norms_fr.py`.

## Roadmap phases

### Phase 0 — Moteur de calcul déterministe ✅ TERMINÉ
- Module `stair_engine/` complet (escalier droit + QT bas modes straight/balanced).
- 4 routes API (`/api/calculate/straight`, `/api/calculate/quarter-turn-bottom`, `/api/norms/fr`, `/api/openapi.json`).
- Système d'alertes 17 codes, semantic `is_buildable` distinguant blockers géométriques vs non-conformités DTU.
- 42/42 tests passants.

### Phase 1 — App mobile Expo + rendu 2D coté ✅ TERMINÉ
**Backend étendu :**
- 2 routes ajoutées : `/api/calculate/quarter-turn-top` et `/api/calculate/half-turn`.
- 11 nouveaux tests pytest (test_phase1_stairs.py).
- Total : **54/54 tests backend passants**.

**App mobile Expo :**
- 4 écrans : Home (liste projets), Type-select (4 typologies), Form (saisie steps), Result (chiffres + SVG + alertes).
- Rendu 2D SVG en plan et en coupe pour les 4 types (droit, QT bas, QT haut, demi-tournant).
- Stockage local AsyncStorage clé `stairpilot_projects_v1` avec CRUD complet (list, get, save, delete, duplicate).
- Design BTP : palette blanc / gris anthracite / bleu technique / rouge-orange-vert. Pas d'emojis. Typo mono pour cotes.
- Gestion CORS + timeout + erreurs réseau (message FR clair).

**Choix techniques Phase 1 (validés) :**
- Expo Router (file-based) sur `_layout.tsx` + `index/type-select/form/result.tsx`.
- Pas de state manager (React state + AsyncStorage + navigation params).
- Toutes URL via `process.env.EXPO_PUBLIC_BACKEND_URL`.
- Composants `<View>/<Text>/<TouchableOpacity>` uniquement (pas de HTML).

### Phase 2 — Persistance cloud + hélicoïdal + comparateur (à venir)
- Auth optionnelle (Emergent Google Auth ou JWT custom).
- Sync projets multi-devices via MongoDB.
- Escalier hélicoïdal.
- Comparateur multi-solutions (proposer 3 variantes).

### Phase 3 — Béton armé
- Ferraillage escaliers béton.
- Notes de calcul BAEL / EC2.

### Phase 4 — Export & assistant IA (P1 + P2 ✅ TERMINÉS)
**P1 — Export PDF dossier technique ✅**
- Backend : `stair_engine/pdf_dossier.py` (reportlab) + route `POST /api/dossier/generate`.
- 6 pages A4 : fiche projet, plan, coupe longitudinale, métré béton, ferraillage, annexes.
- Enrichi automatiquement avec l'analyse béton armé (`concrete_analysis` optionnel).
- Frontend : bouton `export-pdf-btn` dans `result.tsx`. Web = blob + `<a download>`. Natif = `expo-file-system` cache + `expo-sharing`.
- Tests : 6/6 pytest (unit + intégration URL publique). Fichier PDF ~7KB minimal, ~22KB avec ferraillage complet.

**P2 — Coupes 2D supplémentaires ✅**
- Nouveaux composants SVG : `StairSectionTransverse.tsx` (coupe transversale à mi-volée : largeur, paillasse, garde-corps, aciers principaux + répartition) et `StairSectionAxial.tsx` (coupe béton armé : paillasse inclinée + attentes + chapeaux + étriers).
- 3 onglets dans `result.tsx` : "Coupe long." / "Coupe trans." / "Coupe axe" (testID `tab-section-long/trans/axial`).

**P3 — Assistant IA Claude Sonnet 4.5 ✅**
- Backend : `stair_engine/assistant.py` (emergentintegrations `LlmChat` + `send_message_with_tools`), route `POST /api/assistant/chat` + `GET /api/assistant/conversations/{id}`.
- Tools exposés (OpenAI schema portable) : `optimize_stair`, `calculate_straight`, `analyze_concrete`. Le LLM ne calcule jamais lui-même, il déclenche les fonctions moteur.
- Prompt système strict FR : refuse d'inventer des cotes, demande clarification si params manquants.
- Historique MongoDB collection `assistant_conversations` (`_id = conversation_id`), re-hydraté via `initial_messages` à chaque tour.
- Tests : 4 pytest slow (utilise la vraie API Anthropic) + 7 pytest publics — 11/11 passants.
- Frontend : écran `/assistant.tsx` (bulles user/assistant, spinner, 3 suggestions, cartes solutions cliquables → `/result`). Persistence AsyncStorage `stairpilot_assistant_conv_v1`. Bouton "Nouveau" en header. Erreur/timeout affichée en bandeau.

**P4 — Vue 3D interactive ✅**
- Écran `/view-3d.tsx` accessible depuis `/result` via bouton `view-3d-btn`.
- Rendu via `@react-three/fiber` (web) et `@react-three/fiber/native` (natif, chargé via `Platform.OS` + `require`). `three@0.186`, `expo-gl@57`.
- Géométrie générée depuis `StairResult` pour les 5 types : droit (Box), quart tournant bas/haut (winders trapézoïdaux approximés), demi-tournant (2 volées + palier), hélicoïdal (secteurs radiaux + fût cylindrique).
- Contrôles : OrbitControls chargé dynamiquement sur web (glisser rotation + molette zoom) avec fallback rotation auto si non dispo.
- Sélecteur matériau béton (brut #7A7A7A / lisse #A8A8A8 / peint #E8E4DC) + bouton "Reset" caméra.
- Éclairage : ambient 0.6 + 2 directional lights + sol receiveShadow.

## Contraintes techniques (transverses)
- Toutes routes préfixées `/api`.
- MongoDB via `MONGO_URL`, `DB_NAME` (non utilisé activement en Phase 1).
- Frontend Expo utilise `EXPO_PACKAGER_PROXY_URL` (non modifiable).
- URL app mobile web preview : `https://escalier-pro.expo.preview.emergentagent.com`
- URL backend public : `https://escalier-pro.preview.emergentagent.com/api/*`
- Toutes cotes en **mm** en interne. Angles en degrés en sortie.

## Décisions clés — Phase 1
1. **Convention marches** : `num_treads = num_steps - 1` (le dernier riser débouche sur le plancher haut).
2. **QT balancé** : angles uniformes entre winders (méthode simple, méthode des développées non implémentée).
3. **Demi-tournant** : split hauteur en 2 volées équilibrées + 4-12 winders au milieu (mode auto par défaut).
4. **Nez de marche (débord)** : `tread_thickness_mm` non utilisé pour l'échappée en Phase 1.
5. **Recherche `n`** : minimise `|h - 170mm|` dans plage optimale [160, 180], fallback [155, 195].
6. **Storage** : AsyncStorage local uniquement. Pas de cloud sync en Phase 1.

## Semantic is_buildable
- **7 BLOCKING_CODES** → `is_buildable=false` : STAIR_RUN_TOO_LONG, STAIR_WIDTH_INSUFFICIENT, STAIRWELL_TOO_SMALL, HEADROOM_INSUFFICIENT, GEOMETRY_INVALID, BALANCING_IMPOSSIBLE, AUTO_WINDERS_NO_SOLUTION.
- **Autres red alerts** = non-conformités DTU, `is_buildable=true` (constructible mais non-conforme).
