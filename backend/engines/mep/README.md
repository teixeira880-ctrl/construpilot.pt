# Moteur MEP — Plans d'exécution Électricité & Plomberie

Moteur **déterministe** (aucun appel LLM) qui transforme la géométrie d'un plan de maison
(pièces, ouvertures, appareils repérés) en pré-étude d'exécution :

| Livrable | Contenu |
|---|---|
| Plan électricité (par niveau) | prises, plan de travail, sorties spécialisées, points lumineux, commandes (simple / va-et-vient), RJ45, tableau GTL, DAAF, LES, n° de circuit |
| Schéma unifilaire | AGCP, DDR 30 mA (type, calibre), disjoncteurs, sections ; conducteurs aux couleurs normalisées |
| Plan plomberie (par niveau) | nourrices EF/ECS, pieuvre PER, colonne montante, chutes, collecteur, sortie vers regard, Ø et pentes |
| Quantitatif | nomenclature électricité + plomberie ; prix **uniquement** depuis la bibliothèque de l'entreprise |
| Contrôles | conformité recalculée sur l'implantation finale (proposée ou modifiée par le pro) |

Référentiels : **FR** NF C 15-100 (7-771, 7-701) + NF DTU 60.11 ; **PT** RTIEBT + DR 23/95.
Les tables sont dans `rules.py` (une valeur = une source). Les valeurs PT marquées « prática corrente »
ne sont pas des minima normatifs et sont signalées comme telles.

Couleurs : phase marron, neutre bleu clair, PE vert/jaune ; eau froide bleue, eau chaude rouge,
eaux usées grises, eaux vannes marron ; symboles électriques en noir (NF EN 60617).

## Utilisation

```python
from engines.mep import generate, recompute
from engines.mep.adapter import from_takeoff      # plan déjà lu dans ConstruPilot (plans_takeoff)
from engines.mep.pdf import build_pdf

study = generate(from_takeoff(plan_doc, country="fr"))
study = recompute(study, {"points": points_modifies})   # après édition par le professionnel
pdf = build_pdf(study)
```

API (offres Pro / Pro Business) : `routes/mep.py` → `/api/mep/studies…` (création depuis un plan,
édition de l'implantation, SVG par calque, PDF, chiffrage bibliothèque).

## Fichiers

- `model.py` normalisation de l'entrée, rattachement des ouvertures aux pièces
- `rules.py` tables FR / PT, simultanéité, choix des tubes
- `equipment.py` appareils (repris du plan ou implantés automatiquement, `source="auto"`)
- `placement.py` placement le long des parois (portes, angles, réservations)
- `electrical.py` implantation + circuits + DDR + tableau + longueurs
- `plumbing.py` nourrices, pieuvre, colonnes, chutes, collecteur, sortie
- `checks.py` contrôles, `quantities.py` nomenclature / prix, `render.py` SVG + PDF, `pdf.py` dossier A3
- `adapter.py` conversion depuis `plans_takeoff`

Tests : `python tests/test_mep_engine.py` (cas d'exemple anonymisé, RDC + R+1).

> Pré-étude générée automatiquement, à vérifier et valider par un professionnel qualifié avant exécution.
