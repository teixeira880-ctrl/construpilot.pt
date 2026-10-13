# ConstruPilot — mettre à jour le projet existant sur Emergent

Version préparée le 11 octobre 2026. Le code est dans la [PR 2](https://github.com/teixeira880-ctrl/construpilot.fr_1/pull/2), branche `codex/pilote-plateforme-main-20261010` du dépôt `teixeira880-ctrl/construpilot.fr_1`. La PR reste en brouillon : aucun déploiement n'a été effectué depuis cette reprise.

## 1. Ouvrir le bon projet

Ouvrir le projet ConstruPilot déjà utilisé dans Emergent et lui transmettre le texte ci-dessous. Il s'agit d'une mise à jour de son code existant. La branche et la PR servent à vérifier les changements dans le même dépôt ; elles ne représentent pas un nouveau projet.

L'agent doit comparer puis appliquer les modifications de la PR dans ce même projet, en conservant les changements déjà présents. Faire relever le commit exact intégré. Ne pas créer de nouveau projet, de nouvelle application ou de nouvelle base de données. Si l'interface ne propose pas de synchronisation GitHub dans la session actuelle, faire appliquer les modifications de code par l'agent dans les fichiers du projet actuel ; ne pas contourner cette limite en réimportant le dépôt comme nouveau projet.

## 2. Texte à copier dans Emergent

```text
Mets à jour le code du projet ConstruPilot ACTUEL avec les modifications de la PR :
https://github.com/teixeira880-ctrl/construpilot.fr_1/pull/2
Dépôt : teixeira880-ctrl/construpilot.fr_1
Branche : codex/pilote-plateforme-main-20261010

Le travail est déjà codé. C'est une mise à jour du projet existant : ne crée
aucun nouveau projet, aucune nouvelle application et aucune nouvelle base.
Compare le code actuel avec la PR, puis intègre ses modifications dans les
fichiers de CE projet. Préserve les modifications locales, les fonctions
existantes et la configuration. Relève le SHA exact intégré. N'écrase pas
le projet avec main, qui ne contient pas encore cette proposition.

Lis docs/deployment-emergent.md et docs/audits/2026-10-11-etude-devis.md.
Conserve le moteur construction-dossier-1, les formules et leurs sources,
les hypothèses/provisions visibles, le PDF beige/cuivre et le devis modifiable.
Les montants des deux fixtures sont des références de test : aucune quantité
de Saint-Denis ou Houilles ne doit devenir une valeur par défaut d'un autre projet.

Installe les dépendances des manifestes et réalise le build de production.
Vérifie les variables d'environnement existantes, MongoDB, le modèle vision,
la clé IA et le démarrage du worker pc_study_jobs. Ne montre aucune clé.

Exécute les tests indiqués dans le guide. Puis fais un essai réel sur le PC
complet de Saint-Denis : les 11 pages doivent être comptabilisées, notamment
la page 11. Contrôle les cotes, niveaux, baies, trémies, sous-sol, rampe,
matériaux, forfaits et exclusions contre le dossier approuvé.
Teste aussi Houilles avec son vide sanitaire de 80 cm et ses refends.
Signale les écarts de lecture, de périmètre, de quantité et de prix séparément.
Ne force jamais le résultat IA pour atteindre le montant de référence.

Vérifie qu'on peut quitter la page pendant une étude, retrouver le résultat,
corriger une mesure/un prix, recalculer puis exporter PDF, Word et Excel.
Crée un devis modifiable, contrôle son total et son annexe, puis modifie
une ligne : l'ancienne étude ne doit plus être annexée comme si elle concordait.
Teste l'isolation entre deux comptes et l'annulation/reprise après redémarrage.

Rends la prévisualisation, le SHA, les résultats de tests et les écarts restants.
Prépare ensuite la mise à jour de l'application existante en conservant ses
comptes, documents, fichiers, domaine et données de production.
```

## 3. Configuration à contrôler

Réutiliser la configuration du projet ; ce tableau n'est pas une liste exhaustive des services historiques de ConstruPilot.

| Élément | Contrôle |
| --- | --- |
| `MONGO_URL`, `DB_NAME` | Connexion à la base prévue pour cet environnement ; conserver la base de production lors de la mise à jour. |
| `JWT_SECRET` | Conserver la configuration d'authentification existante. |
| `PLAN_AI_MODEL` | Modèle vision réellement disponible, au format `fournisseur:modèle`. Le code actuel propose `openai:gpt-5.5` si cette variable est absente ; vérifier sa disponibilité dans le compte Emergent. |
| `OPENAI_API_KEY` / `EMERGENT_LLM_KEY` | Clé serveur utilisable par le fournisseur choisi ; aucune clé dans le frontend. |
| `STUDIES_MODEL_ANALYSIS`, `STUDIES_MODEL_LIGHT` | Garder les modèles configurés pour les autres moteurs d'étude. |
| `REACT_APP_BACKEND_URL` | Origine du backend public, sans suffixe `/api` : le frontend l'ajoute. Recompiler après modification. |
| `FRONTEND_URL`, `CORS_ORIGINS`, `CORS_PROXY_ORIGIN` | Origines de l'environnement pour la connexion par cookie. |
| Worker | `backend/server.py` lance `start_study_workers()` au démarrage FastAPI. Vérifier que la file passe de `queued` à `running`, puis `completed`. |
| Collections | `pc_study_jobs` et `pc_study_history` sont utilisées ; les index de la file sont créés au démarrage. Pas de suppression de collections ni de conversion globale des anciennes études. |

Une fermeture de page ne doit pas arrêter une étude. Un arrêt du serveur peut interrompre le traitement : la reprise doit être explicite, sans nouvelle dépense IA lancée silencieusement.

## 4. Commandes de vérification

Depuis la racine du dépôt, après installation des dépendances backend :

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_study_dossier.py backend/tests/test_study_dossier_routes.py -q -o asyncio_mode=auto
```

Résultat attendu pour les deux suites du nouveau module : **47 tests réussis**. Les variables de démarrage backend doivent être chargées ; ces tests simulent la base et les appels IA.

Depuis `frontend`, avec Yarn et les dépendances installées :

```bash
yarn install --frozen-lockfile
yarn playwright install chromium
yarn test:dossier
yarn test:landing
yarn build
```

`CHROMIUM_EXECUTABLE_PATH` permet de sélectionner un Chromium déjà installé. Ne pas remplacer les versions de dépendances au hasard si l'installation échoue : relever la première erreur et la traiter avant de publier.

Les fixtures doivent retrouver **280 619,68 € HT** pour la maison avec sous-sol et **244 182,39 € HT** pour celle avec vide sanitaire. Elles valident le recalcul de relevés déjà établis. La lecture IA réelle peut produire des écarts qui doivent être contrôlés avant utilisation commerciale.

## 5. Publier la version contrôlée

Quand la prévisualisation, le build et l'essai réel sont validés, utiliser **Re-publish** dans le projet actuel pour mettre à jour la même application. Conserver son domaine, sa base, les comptes, documents et fichiers existants. Vérifier que le résumé de l'opération désigne bien l'application ConstruPilot déjà en ligne.

Après publication : ouvrir l'URL publique, se connecter, retrouver un ancien dossier, lancer une nouvelle étude et télécharger son PDF. Contrôler les journaux et le statut des tâches. En cas de régression, revenir à l'image de production précédente ; conserver les documents et les collections ajoutées pendant l'essai.

## Sources Emergent consultées le 11 octobre 2026

- [Espace de travail et limites de l'import GitHub](https://help.emergent.sh/a-tour-of-the-workspace)
- [Publication web](https://help.emergent.sh/deploying-web)
- [Prévisualisation, Re-publish et Replace](https://help.emergent.sh/preview-vs-deployed-separate)
- [Secrets et variables](https://help.emergent.sh/secrets-env-variables)
