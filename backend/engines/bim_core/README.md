# bim_core — modelo BIM IFC 4.3 do ConstruPilot

Planta lida no módulo Plantas (estrutura IA corrigida + divisões + calibração) → `BuildingModel` em metros
(`model.py`) → ficheiro IFC 4.3 (`ifc_builder.py`, IfcOpenShell 0.8.5, LGPL-3.0).

- Determinístico: nenhum valor gerado por IA; o que falta vira aviso (`warnings`), não é inventado.
- GlobalId estáveis (uuid5 de plano + página + id de origem): regenerar mantém os mesmos identificadores.
- Unidades SI em metros; Psets normalizados (`Pset_*Common`), quantidades (`Qto_*BaseQuantities`),
  materiais, e `CP_Origem` (id do elemento na planta) em cada elemento.
- Convenções do piso: cota 0 = pavimento; lajes de −e a 0; vigas penduradas no topo; sapatas sob a laje.
- Validação de esquema (`validate`) antes de entregar o ficheiro.

Rotas: `GET /api/bim/takeoffs/{plan_id}/{page}/summary` e `.../ifc` (`routes/bim.py`).
Visualizador: página `/bim` (That Open Engine + web-ifc, `frontend/src/components/bim/bimEngine.js`).

```bash
cd backend && python -m pytest -q tests/test_bim_core.py
```

## Pré-dimensionamento estrutural (`analysis.py`)

Pórtico 3D gerado do modelo (pilares encastrados, vigas ligadas a pilares/vigas/paredes resistentes), cargas
EN 1991-1-1 por faixas de influência, combinações EN 1990 (ELU, ELS quase-permanente), solver **PyNite (MIT)**,
dimensionamento das vigas com `engines.structuro_ec2.design_section` (EN 1992-1-1) e flecha a longo prazo (L/250).
Resultados por GlobalId → cores no visualizador. Só cargas verticais; `execution_ready` sempre False.
Rota: `GET /api/bim/takeoffs/{plan_id}/{page}/analysis`.

## IFC externos (`ifc_reader.py`)

`POST /api/bim/ifc/analysis` recebe um IFC de qualquer programa (Revit, Archicad, Tekla, Allplan…), lê-o em memória
(não é guardado) e devolve o pré-dimensionamento de um piso com os **GlobalId do próprio ficheiro**, para colorir
o modelo no visualizador. No `/bim`, "Abrir IFC" seguido de "Calcular estrutura" usa esta rota; o piso escolhe-se
no painel.

- Geometria lida em coordenadas do mundo (IfcOpenShell), em metros, qualquer que seja a unidade do ficheiro;
  edifícios rodados e georreferenciados são deslocados para perto de (0, 0).
- Paredes, pilares e vigas: retângulo de área mínima em planta; lajes: união das faces projetadas (Shapely).
- Piso *i*: paredes/pilares com o centro entre a cota do piso e a do seguinte; vigas e lajes com o topo à cota do
  piso seguinte (teto). Sem laje no teto, a laje do pavimento é usada como laje tipo (aviso `slab_from_floor`).
- Paredes resistentes: `Pset_WallCommon.LoadBearing`; sem a propriedade, espessura ≥ 15 cm.
- Pilares: o N_Ed dos pilares empilhados dos pisos de cima (± 30 cm em planta) é somado; um pilar sem pilar por
  baixo é assinalado (`column_transfer`).
- Limites: pilares que atravessam vários pisos num só elemento contam só no piso do seu centro; cargas de paredes
  dos pisos de cima sobre vigas não são transmitidas.
