# Studio de projet (Estúdio de Projeto) — modèle unique du bâtiment

Parité avec construpilot.pt (branche `claude/estudio-modelo-unico`, commit `f54f69f`). Un seul modèle (niveaux, murs
multicouches, baies liées aux murs, escaliers, toiture, mobilier, cotes, notes) sert à tout ce qui se voit et se mesure :
plan 2D, 3D, façades, coupes, surfaces, métré géométrique, planches PDF à l'échelle, DXF, IFC. Aucune IA, rien d'estimé par
ratios : ce qui ne peut pas être calculé exactement sort en avertissement.

## Ce qui est identique au .pt (moteur copié tel quel)

`derivar.py`, `cobertura.py`, `escadas.py`, `materiais.py`, `objetos.py`, `operacoes.py`, `__init__.py` : aucune ligne modifiée.
Écarts volontaires, à conserver quand on reprend un correctif du .pt :

| Fichier | Écart |
|---|---|
| `modelo.py` | 4 lignes : `TIPOS_PT = TIPOS_BASE` puis `TIPOS_BASE = sitio.tipos_base(TIPOS_PT)` (murs de départ du pays) |
| `desenhos.py` | 2 lignes : polices et en-tête des PNG pris dans `sitio.volumes()` au lieu de `urbanismo_pt.volumes` |
| `exportar.py` | cartouche fourni par `sitio.carimbo()` / `sitio.autor()`, polices `sitio.fontes_pdf()`, libellés passés par `tr`, calques DXF par `camada_dxf` |
| `ifc.py` | noms des entités, des matériaux et des jeux `CP_…` passés par `tr` / `parte` / `tr_chave` (les clés de recherche restent internes) |

En portugais (`usar_lingua("pt")`, murs `TIPOS_PT`), le moteur donne exactement les mêmes nombres et les mêmes textes que sur
le .pt : c'est ce que vérifie `tests/test_estudio_projeto.py` (tests du .pt repris sans changement de valeurs).

## Ce qui dépend du pays

- `sitio.py` — seul point de couplage au pays (`core/market.py`) : murs de départ français (mêmes épaisseurs que les pièces PC :
  30 cm et 10 cm), murs-types et matériaux ajoutés à la bibliothèque (parpaing + ITI 13+120, brique + ITI, monomur, ITE,
  béton banché, carreaux de plâtre…), polices, cartouche.
- `adapter_fr.py` — modèle initial depuis le **dossier d'urbanisme** (`routes/urbanism.py`), équivalent de `modelo.de_processo` :
  il part de `engines/urbanism/pc_plans.House`, donc des mêmes mesures que le carnet PC (emprise, niveaux, pièces, portes,
  fenêtres, escalier, toiture). Volume en L / T : contour réel, distribution à dessiner. Ce que le modèle ne représente pas
  (soubassement, arase, acrotère) est dit en avertissement.
- `i18n.py` + `i18n_fr*.py` — langue de sortie. Les textes internes restent en portugais (clés stables) ; à la sortie (API, SVG,
  PDF, DXF, CSV, IFC, Assistant) ils sont traduits par le catalogue (≈ 860 textes exacts, ≈ 100 modèles). Le modèle fait
  l'aller-retour : `modelo_saida` (interne → français, pour l'éditeur) et `modelo_entrada` (français → interne, avant
  `normalizar`) ; les opérations de l'Assistant acceptent les noms français (`operacoes_entrada`).
- `routes/estudio_projeto.py` — mêmes routes que le .pt (`/api/estudio-projeto/processos/{id}` où `id` = dossier d'urbanisme),
  collection `urbanism_studios`. « sincronizar-materiais » écrit `materiaux` / `materiaux_studio` dans le dossier : les légendes
  des pièces PC (`pc_plans.materials`) les reprennent. L'export ZIP du dossier reçoit le dossier « Studio-de-projet ».
- `engines/assistant_estudio_tool.py` — outils `estudio_ver` / `estudio_editar` de l'Assistant (particuliers et professionnels).

`tests/test_studio_projet_fr.py` vérifie tout cela, avec un contrôle « aucun mot portugais » sur chaque livrable français.

## Frontend

`frontend/src/components/licenciamento/` (`EstudioProjeto.jsx`, `Estudio3D.jsx`, `estudioGeo.js`) : mêmes fichiers que le .pt,
textes en français. Monté dans la page du dossier (`pages/UrbanismeDossier.jsx`, carte « Studio de projet »), ouvert en plein
écran. Étude d'ensoleillement : le dossier français ne connaît pas l'orientation de la façade sur rue, elle se choisit dans la
vue 3D (sud par défaut).

## À faire dans les lots suivants

- Lots 2 / 3 (BIM, BIM Studio) : partager l'export IFC du Studio (`ifc.py`) — règle « une seule app par fonction ».
- Lot 10 (permis automatique) : orientation réelle de la parcelle et contour du terrain dans les axes du modèle (`contexto`).
