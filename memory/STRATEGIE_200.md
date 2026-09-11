# ConstruPilot — Stratégie « 200 % » : devenir la référence européenne (puis mondiale) de l'intelligence de plans BTP

Objectif : ConstruPilot raisonne comme un ingénieur/métreur senior et calcule comme une machine. Zéro faux positif toléré
(abstention > erreur), explicabilité totale, FR + PT natifs, mêmes standards sur construpilot.fr, construpilot.pt et les apps dédiées.

## 0. Décisions structurantes (déjà appliquées le 11/09/2026)
- Modèle IA plans : **GPT-5.5** (vision + raisonnement) via `PLAN_AI_MODEL` (fallback Gemini 3 Flash). Coût accepté par le fondateur.
- Principes ConstruPilot (`engines/plan_principles.py`) injectés dans toutes les lectures de plans (estimation, cotes, géométrie).
- Abstention automatique quand la mesure à l'échelle n'est pas fiable (statut « nd »), traitements longs en tâche de fond (jobs).
- Résultat Houilles : cartouche exact, fermetures avec épaisseurs réelles (0,13 / 0,24 / 0,30), façades 14,96/15,00 et 13,27/13,30 → même diagnostic que le rapport humain, en 4 min.

## 1. Architecture multi-agents (T1 — 4 à 6 semaines)
`engines/agents/` — orchestrateur + agents spécialisés, chacun avec entrée/sortie JSON typées (pydantic) et **preuve de classification** :
1. **Agent Lecture graphique** : vectoriel PDF (pdfplumber/pymupdf : traits, épaisseurs, styles, textes positionnés) + vision. Sortie : couches sémantiques 01-20, segments {id, x1,y1,x2,y2, épaisseur, style, texte proche, confiance}.
2. **Agent Cotations** : association cote ↔ objet, axe/face/hors-tout, unités, chaînes, hiérarchie N1-N5.
3. **Agent Architecture** : murs (2 parallèles), ouvertures (portes/fenêtres/trémies), pièces, surfaces, escaliers.
4. **Agent Structure/Fondations** : poteaux, poutres, semelles, longrines, radier, appuis, excentricités, sections.
5. **Agent Toiture/Étanchéité/Charpente** : pentes, EP, graphe hydraulique, pannes/chevrons.
6. **Agent Métrés** : quantités uniquement après validation géométrique (règle des 2 sources), liaison bibliothèque de prix FR/PT.
7. **Agent Contrôle final (adversarial)** : tente de contredire chaque anomalie et chaque quantité ; ne valide que ce qui résiste.
Chaque agent : GPT-5.5 (raisonnement) + outils déterministes Python (géométrie exacte, sommes, angles, diagonales). Trace complète stockée (`plan_analyses.trace`).

## 2. Moteur géométrique déterministe (T1)
- Extraction vectorielle native des PDF (plus de pixels quand le PDF est vectoriel) : coordonnées exactes, épaisseurs de trait, textes avec position → cotes associées aux traits d'attache par géométrie, pas par IA.
- Graphe du bâtiment (nœuds/arêtes) ; murs = paires de parallèles ; fermeture des chaînes calculée en Python, l'IA n'intervient que pour l'interprétation.
- Diagonales, angles réels, alignements (droite moyenne + distances perpendiculaires, seuils 0-5/5-20/>20 mm).
- Calibration robuste : échelle déclarée × vérification par cotes ; abstention si dispersion > 8 %.

## 3. Fiabilité & anti-hallucination (T1-T2)
- Double lecture systématique (déjà) → **triple** sur ROUGE (troisième passe avec modèle différent : Gemini 3.1 Pro).
- Relecture zone par zone (crop haute résolution) avant toute anomalie ; consensus multi-hypothèses ; scores geometry/text/semantic/global par objet.
- Jeu de tests de référence : 30 plans réels annotés à la main (FR + PT), score de précision/rappel publié dans l'admin ; aucun déploiement si régression.

## 4. Expérience « summum » (T2)
- Rapport CP-xx court/long (fait) + **rapport narratif Houilles-style** généré par GPT-5.5 à partir des données validées (sections numérotées par grande cote).
- Canvas interactif : cotes cliquables (fait), déplacement des extrémités, calques on/off, comparaison de révisions (superposition A/B).
- Multi-plans : architecture vs structure vs fondations vs coupes (superposition virtuelle, écarts mur/poteau/fondation).
- Streaming des raisonnements (SSE) : l'utilisateur voit l'IA « penser » en direct.

## 5. Portugal & international (T2)
- construpilot.pt : mêmes fonctions, prompts PT natifs (pas de traduction à la volée pour l'IA), IVA 6/13/23 %, normes PT (RGEU, Eurocódigos), libellés PDF 100 % PT (mentions légales, condições de pagamento).
- Bibliothèques de prix PT (CYPE Gerador de Preços) + FR (Batiprix-like) ; devises/langues additionnelles (ES, EN) via `pdf_i18n` déjà prêt (fr/en/es/pt/it/de/ar).

## 6. Apps dédiées (T3)
- « Analyser cotes des plans » (fait), « Estimation », « Métré », « Appro », « Rentabilité » : chacune exposée en API publique (`/api/public/v1`, clés API) + widgets embarquables ; PWA mobile chantier (photos, dictée, hors-ligne).
- Marketplace : partage de bibliothèques de prix entre entreprises, notation.

## 7. Qualité logicielle
- Tests backend pytest par agent (fixtures = plans de référence), tests E2E Playwright par app, revue de code + audit sécurité trimestriels, observabilité (durée/coût par analyse, taux d'abstention, taux de confirmation passage 2).

## Priorités immédiates (prochaines sessions)
1. Extraction vectorielle PDF + association cote↔trait déterministe (supprime les « nd » sur PDF vectoriels comme Houilles).
2. Agent Contrôle final adversarial + triple lecture sur ROUGE.
3. Rapport narratif Houilles-style + rapport global multi-pages.
4. PT natif complet (prompts + PDF + IVA).
