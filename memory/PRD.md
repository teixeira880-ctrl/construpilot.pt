# STAIRPILOT — Product Requirements Document

## Vision produit
Application mobile Expo (React Native) permettant à un bureau d'études béton ou à un maçon (persona France, DTU 36.3) de concevoir et calculer un escalier béton coulé en place — droit, quart tournant, demi-tournant, hélicoïdal — avec vérification de conformité en temps réel.

Le moteur de calcul est **100% déterministe** — aucune IA n'invente de cotes.

## Personas cibles
- **BE béton** (bureau d'études structure) — France, référentiel DTU 36.3.
- **Maçon** confronté à un escalier béton sur chantier.
- Pas d'authentification au MVP. Projets stockés localement sur l'appareil (Phase 2).

## Stack
- **Backend** : FastAPI + MongoDB (`/app/backend`).
- **Frontend** : Expo (React Native) — `/app/mobile`.
- **Moteur de calcul** : Python déterministe (`/app/backend/stair_engine/`).
- **Base de règles** : seuils DTU 36.3 dans `norms_fr.py` (structure préparée multi-pays).

## Roadmap phases

### Phase 0 — Moteur de calcul déterministe (BACKEND UNIQUEMENT) ✅ TERMINÉ
Objectif : prouver que le moteur géométrique est fiable et testable avant d'attaquer l'UI mobile.

**Périmètre livré :**
- Module Python modulaire `/app/backend/stair_engine/` :
  - `models.py` — Pydantic input/output
  - `norms_fr.py` — seuils DTU 36.3 configurables
  - `blondel.py` — formule de Blondel + recherche `n`
  - `alerts.py` — système d'alertes (rouge / orange / vert)
  - `straight.py` — moteur escalier droit
  - `quarter_turn.py` — moteur QT bas (modes `straight` et `balanced`)
  - `README.md` — formules et hypothèses
- Routes FastAPI (préfixe `/api`) :
  - `POST /api/calculate/straight`
  - `POST /api/calculate/quarter-turn-bottom`
  - `GET /api/norms/fr`
  - `GET /api/openapi.json` (alias)
- Tests pytest : **24/24 passants** dans `/app/backend/tests/test_stair_engine.py`
- Échappée : formule **rigoureuse** (position trémie + hauteur cumulée par marche)
- QT bas : mode `balanced` (par défaut) avec 3 marches balancées + volée droite, ligne de foulée 500mm

**Choix techniques Phase 0 (validés utilisateur) :**
1. QT bas — paramètre `balancing: "straight" | "balanced"`, défaut `balanced`.
2. Échappée — formule rigoureuse dès Phase 0 (paramètre optionnel `stairwell_offset_mm`).
3. Seuils DTU — valeurs FR par défaut, structure configurable pour multi-pays.
4. pytest — dans `requirements.txt` unique.
5. Aucune IA/LLM en Phase 0.

**Ce qui NE FAIT PAS partie de Phase 0 :**
- Rendu 2D/3D
- UI Expo
- IA/LLM
- Export PDF
- Escaliers demi-tournant / hélicoïdal
- Béton armé / ferraillage

### Phase 1 — UI Expo & autres types d'escaliers (à venir)
- Écran de saisie mobile-first
- Rendu 2D en coupe + plan
- QT haut, demi-tournant, hélicoïdal
- Stockage local des projets

### Phase 2 — Persistance & partage
- Projets MongoDB (multi-devices)
- Export PDF fiche technique
- Partage projet

### Phase 3 — Béton armé
- Ferraillage escaliers béton
- Notes de calcul BAEL / EC2

## Contraintes techniques (transverses)
- Toutes routes préfixées `/api`.
- MongoDB via variables d'env (`MONGO_URL`, `DB_NAME`) — non utilisé en Phase 0.
- Frontend Expo utilise `EXPO_PACKAGER_PROXY_URL` (non modifiable).
- Toutes cotes en **mm** en interne. Angles en degrés dans la sortie.

## Décisions clés à valider par l'utilisateur (Phase 0)
1. **Convention marches** : `num_treads = num_steps - 1` (le dernier riser débouche sur le plancher haut).
2. **QT balancé** : angles uniformes entre winders (méthode simple), méthode des développées non implémentée en Phase 0.
3. **QT échappée** : calcul rigoureux uniquement sur la volée droite au-dessus du quart tournant (marches balancées supposées dans un dégagement libre).
4. **Nez de marche (débord)** : `tread_thickness_mm` renseigné mais non utilisé pour l'échappée en Phase 0.
5. **Recherche `n`** : minimise `|h - 170mm|` dans plage optimale [160, 180], fallback [155, 195] avec alerte orange.
