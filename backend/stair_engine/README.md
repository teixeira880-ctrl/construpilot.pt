# STAIRPILOT — Moteur de calcul déterministe (Phase 0)

Module de calcul 100% déterministe. Aucune IA n'intervient dans les cotes.
Toutes les cotes en **millimètres** en interne. Angles de pente en **degrés** dans la sortie.

## Modules

| Fichier | Rôle |
|---|---|
| `models.py` | Modèles Pydantic input / output (`StairInput`, `QuarterTurnBottomInput`, `StairResult`, `Alert`, `TreadDetail`) |
| `norms_fr.py` | Seuils DTU 36.3 (structure `StairNorms` configurable — préparé multi-pays) |
| `blondel.py` | Formule de Blondel, calcul giron optimal, recherche du nombre de marches |
| `alerts.py` | Fonctions de check (`check_blondel`, `check_riser`, `check_tread`, `check_slope`, `check_headroom`, ...) |
| `straight.py` | Moteur escalier droit |
| `quarter_turn.py` | Moteur quart tournant bas (modes `straight` = palier / `balanced` = marches balancées) |

## Formules

### Blondel
`2h + g` (en mm). Plages configurables via `norms_fr.py` :
- Optimal : 600–640 mm
- Acceptable : 580–660 mm

### Giron optimal
`g_optimal = 630 - 2h` (target Blondel = 630), clampé à [220, 320] mm.

### Recherche du nombre de marches
Recherche `n` minimisant `|h - 170|` avec `h = floor_height / n` :
1. Strict : `h ∈ [160, 180]`
2. Élargi : `h ∈ [155, 195]` → alerte `RISER_HEIGHT_NON_OPTIMAL` (orange)
3. Fallback : meilleure approximation possible + alertes rouges éventuelles

### Pente
`slope_deg = atan(H / run)` où `run` est le reculement réel (num_treads × giron pour un droit).

### Échappée (rigoureuse, formule Phase 0)
Pour un escalier droit avec trémie de longueur `stairwell_length_mm` :
- Si `stairwell_offset_mm` fourni : bord bas de trémie à `x_start = g + offset` (depuis le pied).
- Sinon (défaut) : trémie collée en haut de l'escalier (`x_end = num_treads * g`).
- Pour chaque marche `i` (nez de marche à `x_i = i*g`, hauteur `y_i = i*h`) :
  - Si `x_i < x_start` : marche sous la dalle → **échappée = ceiling_height − y_i**
  - Si `x_start ≤ x_i ≤ x_end` : marche dans l'ouverture → pas de contrainte
  - Si `x_i > x_end` : marche émerge au-delà de la trémie → alerte `STAIRWELL_TOO_SMALL` (rouge)
- Échappée minimale = min sur toutes les marches sous la dalle.
- Seuil DTU : **1900 mm minimum**, optimal 2100 mm.

### Quart tournant bas — mode "straight" (palier bas rectangulaire)
- `steps_before_landing` marches droites avant palier (défaut 0 : palier au sol).
- Palier de dimensions `landing_length_mm × landing_width_mm` (défaut : `stair_width × stair_width`).
- Volée droite au-dessus avec les risers restants.
- Encombrement total = `landing_length + (num_upper - 1) × g` en longueur.

### Quart tournant bas — mode "balanced" (marches balancées)
- Le quart tournant est réparti sur `num_winders` marches (défaut 3).
- Angle par marche = 90° / num_winders (uniforme).
- Ligne de foulée à `walkline_offset_mm` du limon intérieur (défaut 500 mm — norme française).
- Giron ligne de foulée = `walkline_offset × angle_rad` (arc de cercle).
- Giron intérieur = `inner_radius × angle_rad` (0 si `inner_radius_mm = 0`).
- Giron extérieur = `stair_width × angle_rad`.
- Contraintes DTU :
  - Giron ligne de foulée **>= 240 mm** (sinon `BALANCING_WALKLINE_TOO_SMALL` rouge).
  - Giron intérieur **>= 100 mm** si `inner_radius > 0` (sinon `BALANCING_INNER_TOO_SMALL` orange).
- Emprise du quart tournant : carré de `stair_width × stair_width`.
- Volée droite au-dessus avec `n_steps - num_winders` risers.

## Hypothèses & simplifications Phase 0

1. **Convention marches / girons** : `num_treads = num_steps - 1`. Le dernier "riser" débouche sur le plancher haut (il n'a pas de tread physique).
2. **Trémie** : positionnée alignée avec la volée, collée en haut si offset absent. Pas de gestion latérale complexe.
3. **Slab thickness** : pris en compte pour information mais n'entre pas dans la formule d'échappée simplifiée (l'échappée est mesurée depuis la sous-face de la dalle, qui est déjà représentée par `ceiling_height_mm`).
4. **Nez de marche (débord)** : négligé (tread_thickness renseigné mais pas utilisé pour l'échappée en Phase 0).
5. **QT balancé** : angles uniformes entre winders (méthode simple). La méthode des développées (Perrault) n'est pas implémentée.
6. **QT échappée** : calculée uniquement sur la volée droite au-dessus (les winders sont supposés dans un dégagement libre de plafond).
7. **is_buildable** : passe à `False` dès qu'une alerte rouge est présente.

## Codes d'alertes

| Code | Niveaux | Signification |
|---|---|---|
| `HEADROOM_INSUFFICIENT` | rouge | Échappée < 1900 mm |
| `STAIRWELL_TOO_SMALL` | rouge | Trémie trop courte ou trop étroite |
| `BLONDEL_OUT_OF_RANGE` | rouge / orange | 2h+g hors plage |
| `RISER_TOO_HIGH` | rouge (>200) / orange (>180) | Hauteur de marche excessive |
| `RISER_TOO_LOW` | orange | Hauteur < 150 mm |
| `TREAD_TOO_SMALL` | rouge (<220) / orange (<250) | Giron insuffisant |
| `SLOPE_TOO_STEEP` | rouge (>40°) / orange (>35°) | Pente excessive |
| `STAIR_RUN_TOO_LONG` | rouge | Reculement nécessaire > disponible |
| `STAIR_WIDTH_TOO_SMALL` | orange | Largeur < 700 mm |
| `STAIR_WIDTH_INSUFFICIENT` | rouge | QT ne rentre pas en largeur |
| `RISER_HEIGHT_NON_OPTIMAL` | orange | h en dehors de [160, 180] mais dans [155, 195] |
| `BALANCING_WALKLINE_TOO_SMALL` | rouge | Giron ligne de foulée < 240 |
| `BALANCING_INNER_TOO_SMALL` | orange | Giron intérieur < 100 |
| `BALANCING_IMPOSSIBLE` | rouge | Nombre de winders incohérent |
| `GEOMETRY_OK` | vert | Aucune alerte rouge/orange |
| `OPTIMAL_CONFIG` | vert | Blondel 620-640 + pente 28-33° |
| `GEOMETRY_INVALID` | rouge | Entrée dégénérée (hauteur nulle...) |

## Routes API exposées

- `POST /api/calculate/straight`  → `StairResult`
- `POST /api/calculate/quarter-turn-bottom`  → `StairResult`
- `GET  /api/norms/fr`  → `StairNorms.as_dict()`
- `GET  /api/openapi.json`  → schéma OpenAPI complet
