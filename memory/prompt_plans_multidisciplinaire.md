# Prompt système ConstruPilot — moteur d'analyse technique multidisciplinaire de plans BTP (fourni par l'utilisateur, 11/09/2026)
Version condensée injectée dans toutes les lectures IA : backend/engines/plan_principles.py (CORE_PRINCIPLES).
Prompt géométrique (§1-17) : engines/plan_geometry_prompt.py · Rapport PDF (§18-37) : engines/plan_report_pdf.py.
Règle n°1 : les faux positifs sont plus dangereux que les données non déterminées → abstention (statut « nd », plan_cotes.check_dimensions).
Règle n°2 : une ligne n'est jamais automatiquement un mur ; preuve de classification par objet (type, confiance, indices, contradictions, décision).
61 sections : type de document, cartouche, type de fichier, couches sémantiques, analyse des lignes, cotations, graphe géométrique, murs, poteaux, poutres,
semelles, longrines, fondations, dalles, ouvertures, linteaux, escaliers, toiture, étanchéité, isolation, charpente, façades, coupes, niveaux, contrôle des cotes,
contrôle inversé, alignements (0-5/5-20/>20 mm), angles, diagonales, métrés (après validation géométrique), multi-plans, traits parasites, OCR+vision+géométrie,
confiance (geometry/text/semantic/global), 9 passes, relecture avant anomalie, consensus multi-hypothèses, ne jamais halluciner (NON INDIQUÉ/ILLISIBLE/DÉDUIT/CALCULÉ/HYPOTHÈSE),
explication de chaque anomalie, portes/fenêtres, superpositions, hachures, réseaux, réservations, joints, objets non constructifs, classes INFO/À VÉRIFIER/INCOHÉRENCE/MAJEURE,
sécurité géométrique (2 sources), types de trait, appuis, toiture+étanchéité, portes, fenêtres, façades/ouvertures, plan/coupe, versioning, score final, seuil d'abstention, pipeline, principe fondamental.
Vision cible : agents spécialisés (lecture graphique, architecture, structure/fondations, toiture/étanchéité, métrés, contrôle final contradictoire).
