# Tests des neuf PDF réels — 10 octobre 2026

## Résultat et périmètre

Les neuf PDF ont été ouverts, rendus et inspectés visuellement, puis traités par le vrai `engines.plan_processor.process_pdf` localement. Aucun appel IA, aucune base ni production. Ce lot valide des corrections de lecture, pas la précision globale des métrés ou des devis. **Le seuil de 98 % n’est pas établi.**

## Défauts reproduits et corrections

- Le moteur de cotes ne recevait pas l’échelle écrite : huit feuilles ne produisaient aucune cote native malgré leurs textes/vectoriels. Import et réextraction utilisent maintenant une fonction commune et l’échelle de chaque page.
- La feuille 08.4 associe 1:50 et 1:200. Une calibration globale est refusée ; chaque vue doit être isolée. La calibration textuelle IA respecte cette réserve. Dans un PDF de plusieurs pages, l’échelle de la première ne se propage plus aux suivantes.
- Le cartouche 07.10 indique R+1, mais un titre intérieur indique « PLAN DE RDC ». La feuille 07.9 contient également sous-sol et RDC. Les mentions sont conservées et signalées, sans affectation automatique à un seul niveau.
- La nomenclature était interprétée comme 51 murs et 39 mesures intérieures. Les coupes, façades et nomenclatures ne passent plus dans la détection de pièces en plan.
- Plusieurs dessins sont légèrement tournés (notamment des textes à environ 1,02°). Les cotes sont désormais recherchées dans le repère de leur texte ; les coordonnées sont ensuite rétablies dans la page. Les traits de même encre colorée servent à distinguer la cotation du mobilier et des hachures, et les attaches restent comparées à tous les traits du dessin.
- Les rattachements incertains sont indiqués « non déterminés » dans le contrôle, exclus des chaînes vérifiées et des cotes de référence pour les murs/travées. Un compteur de candidats ne peut plus annoncer des cotes effectivement extraites lorsque la liste est vide.
- Les réserves sont visibles dans l’éditeur de plan. La version de réextraction passe à 3, sans écraser un niveau affecté manuellement.

## Mesures diagnostiques du passage final

Les candidats ci-dessous ne sont **ni un nombre de quantités finales ni une précision**. La dernière colonne compte seulement ceux qui passent les contrôles géométriques internes actuels ; cela ne constitue pas une validation indépendante.

| Feuille | Type détecté | Échelles | Cotes candidates | Passent les contrôles internes |
|---|---|---|---:|---:|
| 07.10 | floor_plan | 1:50 | 194 | 44 |
| 07.9 | floor_plan | 1:50 | 279 | 82 |
| 08.1 | section | 1:50 | 48 | 35 |
| 08.2 | section | 1:50 | 27 | 13 |
| 08.3 | section | 1:50 | 42 | 25 |
| 08.4 | mixed | 1:50, 1:200 | 0 | 0 |
| 09.2 | elevation | 1:50 | 4 | 0 |
| 09.4 | elevation | 1:50 | 1 | 0 |
| 10 | opening_schedule | non déclarée | 0 | 0 |

Aucune des neuf feuilles ne reçoit une validation complète du métré intérieur. Les candidats douteux restent à reprendre. Les zéros sur la feuille multi-échelle et la nomenclature correspondent à une abstention volontaire de ce moteur, pas à une quantité nulle sur le chantier.

## Reproduction et références

```bash
PYTHONPATH=backend python backend/scripts/audit_pdf_sheets.py \
  --input-dir /chemin/vers/les-pdf \
  --output /chemin/vers/audit.json
```

Le script conserve les SHA-256 des sources et du code, les cotes et diagnostics, sans réseau. Les PDF privés ne sont pas ajoutés au dépôt.

| Source | SHA-256 |
|---|---|
| 07.10 PLAN R+1 BAT B_C_D.pdf | `5bfd9a1730760899298bd545fb2a5d7f3b929997a2caf0078d38284c9ce8d909` |
| 07.9 PLAN R-1 ET RDC BAT B_C_D.pdf | `b3eb8bea4dcb062513f790e0692ef18378784fa7e82c4ae7e2a1c14b81128247` |
| 08.1 COUPES AA_ ET BB_ SUR BÂTIMENT A.pdf | `d6c6f9d9cb437e8f6d9e5aeb8b25100bc6996fa6d64727c9808d4634a74b6c33` |
| 08.2 COUPES DD_ SUR BÂTIMENT A.pdf | `22a6564edcffedf5dbafec50a846358f710c9c7110ab4a532339158c183da01e` |
| 08.3 COUPES EE__FF__GG_ SUR BÂTIMENTS B ET C - COUPES HH__II_ SUR BÂTIMENT D.pdf | `8610fac335499b98d36028ee547dc74d475692208c9b3e240b4c2bbd61c3da4e` |
| 08.4 COUPE CHEMINEMENT PIETON EXTERIEUR _ RAMPE PARKING.pdf | `a6fd0a472ca3b2f63ff54e46037d0bc43295dd0c709030269b1a74c160d8254c` |
| 09.2 FAÇADES BAT A - SUD OUEST_SUD EST.pdf | `4876fc15ef070760f05ca0d4383ef86da021eaaba669da4a2a4b4bbca65731f6` |
| 09.4 FAÇADES BAT D.pdf | `baf82e73e15ea85b5a2bcbe50bb12e45c5db8b22a1a0eb79c00871586fd45ef5` |
| 10 NOMENCLATURE DES BAIES.pdf | `8cf86cf78674b6a412e892ae6454316f533e6d8c0955b8f6f4582e16f0997878` |

## Vérifications et limites

Suite de régression finale : **255 tests Python et 19 sous-tests réussis**. Les 24 nouveaux cas ciblent les défauts de ces feuilles et leurs variantes synthétiques.

- Tests synthétiques de petites cotes, rotations, encres, échelles mixtes, pages de différentes échelles, niveaux ambigus, import/réextraction et conservation des réserves. Cas privés reproduits par des figures synthétiques, sans intégrer les plans au dépôt.
- Contrôle syntaxique/no-undef des 412 fichiers JavaScript/JSX : aucune erreur. Le build complet de production et les services réels ne sont pas validés dans cet environnement.
- Pour les imports existants, ne pas considérer une ancienne calibration automatique comme recertifiée par ce correctif. Réimporter les originaux après intégration, puis confirmer les vues et calibrations avant de réutiliser les anciens métrés.
- Il reste à segmenter les vues de façon fiable, reconnaître et dédupliquer les ouvrages, rapprocher plans/coupes/nomenclature, puis comparer les m², m³ et unités à un métré indépendant validé. Les plans de coffrage/ferraillage, les épaisseurs et les règles de déduction sont nécessaires pour vérifier l’ensemble du gros œuvre.
- Une tolérance de 2 % ou un indice interne de confiance ne démontre pas 98 % de précision. Les essais de quantités utiliseront `evaluate_plan_quantities.py` avec un référentiel confirmé.
