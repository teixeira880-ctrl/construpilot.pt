# Études et devis traçables — reprise du 11 octobre 2026

## Besoin et résultat

Le dernier travail partagé demandait de reproduire dans ConstruPilot les études, calculs et présentation des deux devis approuvés, puis de préparer le déploiement Emergent. Les modifications interrompues ont été récupérées et finalisées sur la proposition GitHub existante.

L'ancien parcours PC ne lisait qu'une partie des pages et appliquait des dimensions constructives fixes. Le nouveau parcours `construction-dossier-1` traite les pages sélectionnées, conserve les lectures page par page et calcule les lignes avec un langage arithmétique limité et des unités vérifiées. Les quantités manquantes, contradictions et doublons ne sont pas convertis en zéro. Les prix de catalogue restent des prix budgétaires ; les paramètres des exemples ne deviennent pas des valeurs par défaut des nouveaux projets.

## Changements

- File MongoDB persistante, progression, annulation, notification, contrôle des droits et protection des modifications concurrentes. La navigation ne supprime pas le travail en cours ; une interruption serveur est signalée et nécessite une relance explicite.
- Mesures et prix modifiables ; état de contrôle des mesures, historique des révisions, pays et TVA conservés.
- PDF beige/cuivre : budget par lot, postes détaillés, métrés/formules, sources, hypothèses, provisions, exclusions et origine des prix. Polices embarquées avec leur licence.
- Word et Excel utilisent le même résultat de calcul. Les textes sources ne deviennent pas des formules actives dans le classeur.
- Création idempotente d'un devis commercial modifiable. Son PDF annexe l'étude tant que ses lignes/remises concordent ; une modification écarte l'annexe devenue incohérente et affiche une explication.
- Arrondi monétaire décimal et calcul de TVA sur la base cumulée de chaque taux. Contrôle de l'unité des prix du compte, en plus du barème par défaut.
- Outils assistant pour lancer et consulter cette étude, sans reconstituer des montants parallèles.
- Reprise des pages de présentation Pro/Particuliers déjà préparées dans le travail précédent ; restauration du composant d'aperçu qui manquait dans la copie locale. Voir le rapport de présentation du 10 octobre.

## Validation effectuée

**154 tests Python passent** dans huit suites : `test_plan_studies_regressions`, `test_plan_routes_regressions`, `test_plan_quote_scope`, `test_platform_supervisor`, `test_plan_sources_regressions`, `test_plan_geometry_regressions`, `test_study_dossier`, `test_study_dossier_routes`. Les services externes et la base sont simulés. Deux avertissements de dépréciation du parseur multipart restent sans échec.

Les deux suites du module représentent **47 tests**, compris dans ce total. Elles contrôlent notamment les dimensions, expressions invalides, valeurs absentes/non finies, doublons, provenance, prix, TVA, révisions concurrentes, devis idempotent, annexe PDF, sélection des pages, page 11, annulation et écritures périmées.

| Référence anonymisée | Total HT | Objet de la vérification |
| --- | ---: | --- |
| Maison avec sous-sol | 280 619,68 € | Recalcul des quantités et prix du devis approuvé Saint-Denis |
| Maison avec vide sanitaire | 244 182,39 € | Recalcul des quantités et prix du devis approuvé Houilles |

Un ancien test attendait encore des murs sur le PDF structure redimensionné à 70 %. Il a été actualisé pour vérifier le comportement déjà introduit dans la version précédente : conservation des 63 quadrilatères bruts, détection de l'échelle contradictoire et absence de murs mesurés automatiquement. Le moteur de géométrie n'a pas été modifié par cette actualisation du test.

Les composants réels du dialogue et de l'indicateur d'étude ont passé le scénario Chromium à 1440, 390 et 320 px, avec API simulée : absence de débordement, modification/dévalidation d'une mesure, sauvegarde, TVA préservée, export, navigation pendant traitement, notification et ouverture du devis. Le scénario des pages de présentation passe également à 320/390/768/1440 px. Contrôle statique de **416 fichiers JS/JSX** sans erreur de syntaxe ni nom indéfini ; fichiers Python analysés sans erreur de syntaxe.

Les deux PDF de référence ont été régénérés, contrôlés visuellement sur toutes leurs pages et vérifiés pour les limites de page. Le titre de colonne « Statut » a été élargi. Aucun plan privé supplémentaire n'est ajouté au dépôt ; les nouvelles fixtures ne contiennent que les spécifications anonymisées nécessaires aux calculs.

## Limites et déploiement

Cette validation porte sur les relevés de référence déjà saisis, les calculs et les parcours avec services simulés. Elle ne prouve pas que l'IA extrait seule l'intégralité de nouveaux plans, ni une précision de 98 %. La présentation est un gabarit réutilisable reprenant le style approuvé ; la pagination varie selon les pièces, intitulés et réserves du chantier.

Le build de production complet, MongoDB réel, le worker hébergé et le fournisseur vision restent à valider dans Emergent. Les deux dossiers doivent y être essayés de bout en bout et comparés aux relevés approuvés. Aucun déploiement ni fusion dans `main` n'est effectué par cette reprise.

Voir [le guide et le texte à copier dans Emergent](../deployment-emergent.md).
