# ConstruPilot : moteur structure depuis un PC

Version livrée le 11 octobre 2026 : `gravity-0.1.0`.

Le code étend le projet ConstruPilot existant. Il ajoute un parcours à
`/structuro/calcul`, dans l'espace StructuroPilot, et utilise les plans déjà
importés, l'authentification, les droits Pro, MongoDB et le fournisseur IA existants.
Il n'est pas déployé automatiquement en production.

## Ce qui fonctionne dans cette version

| Fonction | Fonctionnement réel |
| --- | --- |
| PC | Sélection d'un dossier déjà importé dans `/plan`. Lecture explicite de chaque page par l'IA existante ; progression et reprise des pages manquantes. |
| Repérage | Candidats murs, planchers, poutres, poteaux et semelles visibles. Source document/page/cote conservée. L'IA ne complète pas une section absente. |
| Modèle | Ajout sélectif des candidats, contrôle des doublons entre vues, édition des dimensions, implantations, matériaux, charges et appuis. |
| Descente de charges | Graphe orienté de transferts gravitaires, fractions tributaires explicites, rejet des cycles et appuis inconnus, contrôle des charges externes et réactions au sol. |
| Poutres | Deux appuis simples, poids propre, charge uniforme, charges ponctuelles et réactions transmises. Moments extrêmes, réactions et effort tranchant. |
| Flèches | Superposition élastique avec EI constant fourni, maximum échantillonné sur 401 positions. Ni fissuration, ni fluage, ni limite réglementaire vérifiés. |
| Murs/poteaux | Effort normal et contrainte moyenne en compression centrée. Aucune résistance ou stabilité vérifiée. |
| Semelles | Pression moyenne N/A, poids de la semelle inclus. Géométrie saisie ; portance du sol non déterminée. |
| Cas et combinaisons | Cas G/Q séparés et combinaisons dont chaque facteur est saisi et justifié. Aucune combinaison Eurocode automatique. |
| Plans | Visualisation par niveau, PDF et DXF vectoriel en mètres, repères et dimensions du modèle. Implantation inconnue = élément non dessiné et signalé. |
| Traçabilité | Version du moteur, empreinte du modèle, révision, sources, hypothèses, calculs et domaine de validité. |
| Accès | Compte Pro et propriétaire de l'étude/source ; pas d'accès aux dossiers d'un autre compte. |
| Modifications | Recalcul complet après sauvegarde. Contrôle de concurrence par révision. Édition locale = résultats masqués et exports désactivés jusqu'à sauvegarde. PC modifié = résultats périmés et exports bloqués. |

## Ce que cette version ne doit pas être présentée comme faisant

Ce n'est pas un BET autonome opérationnel ni un moteur de dimensionnement complet.
Un résultat mécanique calculé n'est pas une vérification de résistance. Les sections
sont saisies ou lues, jamais optimisées ni certifiées. Tous les exports portent
« PLAN DE PRINCIPE - NON EXÉCUTOIRE ». `execution_ready` reste toujours `false`.

Le PC ne définit généralement pas la portance du sol, les armatures, les rigidités,
la stabilité de la structure et toutes les charges. Les données absentes restent
inconnues. Les candidats IA doivent être vérifiés, notamment les murs porteurs,
les niveaux, les doublons entre vues et les dimensions intérieures/extérieures.
Les surfaces irrégulières, baies, trémies et jonctions doivent être modélisées
explicitement ; les volumes exposés par le moteur sont bruts et ne sont pas des
quantités de commande. Les coordonnées x/y ne sont pas déduites de pixels non
calibrés. Le graphe des appuis doit être contrôlé par l'utilisateur : il n'existe
pas encore de validation géométrique automatique entre niveaux.

La lecture multi-page est reprise page par page. Fermer l'écran interrompt la
boucle cliente après la requête en cours ; les pages enregistrées sont conservées.
Ce n'est pas un nouveau worker persistant. Un appel IA en échec ne devient jamais
une page réussie. Deux onglets concurrents peuvent appeler le fournisseur pour la
même page ; le contrôle de révision empêche d'écraser une autre modification,
mais il n'est pas un verrou de facturation des appels IA.

## Intégration et déploiement dans Emergent

Branche locale : `codex/structure-pc-20261011`.
**Publication GitHub en attente d'autorisation explicite.** La vérification
automatique a refusé l'envoi externe du code. Cette branche n'est donc pas encore
disponible sur GitHub ; utiliser le correctif fourni pour une intégration locale,
ou autoriser sa publication avant de demander sa récupération dans Emergent.
Base : `codex/pilote-plateforme-main-20261010`, au commit
`b05f5522b646a9ac958d979e80519450a8a0b187` (travail précédent, PR 2).
La nouvelle proposition dépend donc du travail précédent. Ne pas remplacer le
projet Emergent, sa base de données, ses clés ni les autres modules.

1. Après publication autorisée, récupérer la branche dans **le projet Emergent existant** et contrôler la
   différence de code. Si la PR 2 n'est pas intégrée à `main`, conserver cette
   dépendance : intégrer d'abord la PR 2, puis cette proposition, ou tester la
   branche complète dans l'environnement de prévisualisation.
2. Installer les dépendances déclarées du projet. Cette extension réutilise
   FastAPI, Pydantic 2, PyMuPDF, ReportLab et ezdxf déjà déclarés ; aucune nouvelle
   clé de calcul externe ni nouveau service de base de données n'est requis.
3. Lancer uniquement les tests locaux indiqués ci-dessous. Les anciens fichiers
   `test_structuro.py` et `test_iter232_structuro_plan_reader.py` contactent un
   ancien serveur externe ; ne pas les lancer comme une suite locale.
4. Compiler le frontend complet avec la commande du projet et démarrer le backend.
5. Dans un compte Pro de test, ouvrir `/structuro/calcul`, essayer l'exemple fictif,
   modifier une dimension et vérifier la péremption des résultats et des exports.
6. Importer un PC dans `/plan`, le sélectionner, lire toutes les pages, vérifier
   la couverture et retenir les candidats pertinents. Confirmer les cotes sur les
   documents et compléter les hypothèses avec un ingénieur. Tester une panne IA,
   une donnée absente, un second compte et deux onglets concurrents.
7. Faire valider indépendamment les hypothèses, les résultats et les exports
   avant d'activer ce parcours pour les utilisateurs. La mise en ligne du code
   ne transforme pas cette version en étude d'exécution.

Commandes de tests ciblés, à la racine du dépôt :

```bash
PYTHONPATH=backend python -m pytest -q -o addopts='' \
  backend/tests/test_structuro_calc.py \
  backend/tests/test_structuro_calc_routes.py \
  backend/tests/test_study_dossier.py
```

À copier dans Emergent :

```text
Continue le projet ConstruPilot existant, dépôt teixeira880-ctrl/construpilot.fr_1.
Si la branche n'est pas encore publiée, appliquer le correctif fourni après
git apply --check, ou attendre sa publication autorisée. Ne pas recréer le projet.
Intègre la branche codex/structure-pc-20261011 en préservant son travail parent
codex/pilote-plateforme-main-20261010. Lis docs/structure-pc-emergent.md.
Vérifie les conflits, exécute les tests locaux ciblés, compile le frontend complet
et teste /structuro/calcul avec un compte Pro de prévisualisation.
Valide la lecture de toutes les pages d'un PC réel avec les clés IA du projet,
la persistance MongoDB, l'isolation des comptes et les exports PDF/DXF.
Conserve la distinction entre calcul mécanique et dimensionnement Eurocodes.
Ne change pas execution_ready=false et ne produis pas de bon pour exécution.
Présente les résultats des vérifications et l'aperçu avant mise en production.
```

## Qualification nécessaire pour atteindre le niveau d'un logiciel de BET

| Lot à développer | Conditions de réception |
| --- | --- |
| Modèle structurel global | Consolidation multi-vues/niveaux, géométrie cotée, baies/trémies, plans de toiture, portées, appuis, excentricités et continuité vérifiés. Tolérances explicites et contrôle du chemin de charges. |
| Actions et combinaisons | Charges par usage, permanentes, climatiques, accidentelles et phases de chantier ; cas dominants/accompagnants, coefficients favorables/défavorables et enveloppes. Pays, édition et annexe nationale explicitement sélectionnés. |
| Solveur | Portiques/poutres continues, plaques, diaphragmes, stabilité et second ordre selon domaine retenu. Tests analytiques et comparaison avec un solveur indépendant ; aucun report implicite du modèle isostatique à un autre domaine. |
| Béton armé | Flexion simple/composée, cisaillement, poinçonnement, fissuration, déformation différée, ancrage, recouvrement, enrobage et dispositions constructives. Note par vérification avec clause, hypothèses et unités. |
| Acier/bois/maçonnerie | Résistance, stabilité, assemblages, appuis, écrasement local, élancement, flambement/déversement, entailles, humidité/durée de charge selon matériau. |
| Fondations | Rapport géotechnique adapté au projet, stratigraphie/eau, capacité portante et tassements, assise, effets de voisinage, excentricité, glissement/soulèvement, rigidité et calcul structurel de semelles/longrines/radier. Ne pas comparer une charge ELU à une pression ELS. |
| Stabilité et séisme | Contreventement, diaphragmes, dispositions sismiques, irrégularités, torsion et interaction sol-structure selon cas. |
| Existant et travaux provisoires | Reconnaissance des matériaux/appuis/fondations, état réel et phasage. Étaiement et ouvertures dans l'existant nécessitent une étude spécifique. |
| Plans d'exécution | Plans de coffrage, coupes/détails, nomenclature et façonnage des aciers calculés, implantation, tolérances, indices, réservations et cohérence note/plan. Aucun ratio kg/m³ en remplacement d'un ferraillage. |
| Validation et diffusion | Corpus de cas de référence revus par ingénieur, revue indépendante, qualification de chaque module et limites, contrôle des révisions et signature/visa liés à l'empreinte exacte du dossier. |

Pour viser ce niveau, la lecture IA aide à construire et expliquer le modèle ;
les calculs et vérifications doivent être déterministes, qualifiés et audités.
Les paramètres normatifs doivent être versionnés et choisis pour le pays et le
projet. Un simple changement de drapeau `CALC_ENGINE_AVAILABLE` serait incorrect.

## Architecture des ajouts

* `backend/engines/structuro_calc.py` : schéma, contrôles, graphe et mécanique.
* `backend/engines/structuro_pc.py` : lecture IA à la page, sorties non approuvées.
* `backend/engines/structuro_calc_exports.py` : PDF/DXF du modèle enregistré.
* `backend/routes/structuro_calc.py` : routes authentifiées, propriété et révisions.
* `frontend/src/pages/StructureCalc.jsx` : parcours utilisateur et édition.
* `backend/tests/test_structuro_calc*.py` : cas indépendants et protections.

Le moteur utilise m, kN, kN/m, kN/m², kN.m et kN.m² pour EI. Les charges positives
agissent vers le bas. Une poutre a exactement deux appuis ordonnés gauche/droite.
Une liaison précise comment la réaction arrive à l'élément récepteur : force
axiale centrée, charge uniforme ou force ponctuelle positionnée sur une poutre.
Une semelle termine le chemin au sol. Les valeurs non finies, négatives hors
domaine, unités implicites non converties et champs inconnus ne sont pas acceptés.
L'API expose le schéma JSON à `/api/structuro/calc/schema` (accès Pro).

## Vérifications réalisées

64 tests locaux réussis : 34 nouveaux tests de mécanique/export/routes et
30 tests existants du dossier de métré. Cas indépendants : charge uniforme,
charge ponctuelle dissymétrique, charge à l'appui, symétrie, superposition,
positions, transfert de charges, équilibre global, entrées invalides, propriété,
concurrence, source modifiée, panne IA et rejet d'approbations issues de l'IA.

Le composant React a été compilé isolément avec ses composants réels. Un parcours
navigateur local avec API simulée a vérifié l'ouverture de l'exemple, l'édition,
la suppression des résultats périmés, la désactivation des exports, la sauvegarde,
la remise à zéro des confirmations et l'absence de débordement horizontal à 390 px.
Les PDF de démonstration et le DXF ont été générés et contrôlés.

Non vérifiés ici : build complet de toute l'application, IA sur un PC réel,
stockage MongoDB réel, dimensionnement normatif et déploiement Emergent.
L'auto-review a rejeté l'exécution des anciens tests d'intégration visant un
serveur externe avec identifiants et mutations ; ils n'ont pas été validés.

## Sources techniques consultées

* Commission européenne, JRC : [famille des Eurocodes](https://eurocodes.jrc.ec.europa.eu/en-eurocodes/eurocodes-family).
* JRC : [normes nationales](https://eurocodes.jrc.ec.europa.eu/en-eurocodes-implementation/national-standards) et [paramètres nationaux](https://eurocodes.jrc.ec.europa.eu/en-eurocodes-implementation/nationally-determined-parameters).
* Géorisques : [sols argileux et études géotechniques](https://www.georisques.gouv.fr/consulter-les-dossiers-thematiques/retrait-gonflement-des-argiles).
* David Roylance, MIT, *Mechanics of Materials*, [Beam Displacements, diffusion LibreTexts](https://eng.libretexts.org/Bookshelves/Mechanical_Engineering/Mechanics_of_Materials_(Roylance)/04%3A_Bending/4.03%3A_Beam_Displacements).

Ces sources documentent le domaine et les principes ; elles ne constituent pas
une qualification Eurocodes du code livré ni une validation de chantier.
