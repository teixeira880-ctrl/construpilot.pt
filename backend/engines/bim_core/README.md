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
