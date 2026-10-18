# bet_core — moteur BET hybride ConstruPilot (structure, charpente, élec, plomberie, devis)

Écrit pour remplacer la chaîne `structuro_maison*` qui a produit le dossier faux de La Courneuve
(18/10/2026). Principe : **l'IA lit, le code calcule, un vérificateur contrôle**.

```
PC + G2 (PDF) ──► [1. lecture Claude vision] ──► BuildingModel JSON (cases/*.json)
                                                    │
                                     [2. checks.py]  contrôles bloquants (baie en double,
                                                    │ trumeau ≤ 0, niveau inventé, mur dans
                                                    │ la trémie, escalier impossible, comble…)
                                                    ▼
 [3. structure.py] charges → planchers poutrelles-hourdis → descente de charges →
     maçonnerie Porotherme (EN 1996, Φ) → linteaux/poteaux/chaînages → voiles enterrés
     (K0 + mitoyens) → fondations selon la G2 → dallage, escalier → métré
 [4. timber.py]    charpente à pannes sur pignons (EN 1995) — jamais de fermettes W en comble habité
 [5. mep.py]       électricité NF C 15-100 + plomberie DTU 60.11 sur la même géométrie
 [6. sheets.py + draw.py] 22 planches A3 cotées → PDF à l'échelle exacte + DXF (mêmes primitives)
 [7. devis.py]     devis chiffré Excel à formules (PU modifiables)
 [8. report.py]    note de calcul A4 + revue « vérificateur » (statut PRÊT / NON PRÊT)
```

Aucun chiffre structurel n'est produit par un LLM. L'étape 1 (lecture) est la seule confiée à
Claude : elle doit produire le JSON au format de `cases/la_courneuve.json`, avec la source de
chaque élément. Si `checks.run_all()` renvoie une anomalie `bloquant`, le pipeline s'arrête et
l'Assistant doit relire la zone ou poser une question précise à l'utilisateur.

## Lancer

```bash
cd backend
python -m engines.bet_core.run engines/bet_core/cases/la_courneuve.json /tmp/out
pytest -q tests/bet_core
```

Sorties : `Dossier_etude_La_Courneuve.pdf` (note + planches), `Plans_DXF_La_Courneuve.zip`,
`Devis_metre_La_Courneuve.xlsx`, `resultats.json`.

## Intégration Assistant (à faire)

1. Outil `read_building_model` : Claude vision (Opus) lit les pages plans/coupes/façades et
   remplit le JSON ; schéma = `cases/la_courneuve.json`.
2. Outil `run_bet_core` : appelle `run.main()` et renvoie le statut + les fichiers.
3. Les hypothèses du client (`user_hypotheses`) sont extraites de la demande AVANT le calcul.

## Limites (pré-dimensionnement)

- À viser et signer par un ingénieur structure ; notes fabricants (poutrelles, escalier) et
  G2 PRO obligatoires.
- Valeurs indicatives à confirmer : f_k brique (DoP), M_rd des poutrelles (Avis Technique),
  surcharge des fondations voisines (G2 PRO), prix unitaires (bibliothèque entreprise).
- Contreventement au vent de la charpente : par le charpentier.
