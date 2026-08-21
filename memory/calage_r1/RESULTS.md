# Calage IA PDF — vérité terrain DWG (fichier R+1 coffrage)

Fichier de référence : `AES_EXE_BET_TZ_R+1_COF_0100 - Plan coffrage PH R+1` (couple DWG + PDF).

## Vérité DWG (extraite via CloudConvert → DXF → dxf_takeoff.extract_structural_metre)
- unité : 1 unité = 1 m
- voiles/murs : ~2960,8 ml · emprise 106,2 m²
- poutres : 694,2 ml · emprise 85,34 m²
- **poteaux : 26** · emprise 0,751 m²
- dalle (hachure) : non détectée sur ce calque

## Comparaison IA PDF (detect_structure_tiled) — avant / après calage
| Élément        | Vérité DWG | IA avant | IA après |
|----------------|-----------:|---------:|---------:|
| Poteaux        | 26         | 66       | **37**   |
| Ouvertures     | ~0         | 39       | **0**    |
| Réservations   | nombreuses | 0        | **64**   |
| Type de plan   | coffrage   | instable | coffrage |

## Correctifs appliqués (engines/plan_structure.py)
1. PROMPT : définition stricte du poteau (élément plein sur trame, repère Px/coté) vs
   réservation (Ø/dim/repère fluide). Consigne « 15–35 poteaux typiques, ne pas gonfler ».
2. PROMPT : sur un plan de coffrage, `openings` DOIT être vide ; trémies → `reservations`.
3. Merge tuilé : ajout de `reservations` (auparavant ignoré → perdu) + `reservation_count`.
4. `_reclassify_coffrage()` : post-traitement déterministe — sur un coffrage, reverse les
   `openings` détectées vers `reservations` et vide `openings` (évite les faux linteaux au métré).
5. Détection robuste du type : `plan_kind = "coffrage"` dès que ≥10 poteaux détectés
   (le vote par tuile est instable sur les plans denses).

## Reste à affiner (itérations futures, si besoin)
- Poteaux : encore ~+42 % vs DWG (37 vs 26) — l'IA capte quelques nœuds de trame/croisements
  de poutres. Nécessiterait un filtrage géométrique (poteaux alignés sur trame) ou plus d'itérations.
