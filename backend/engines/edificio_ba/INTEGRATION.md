# Integração de `edificio_ba` no Assistente (construpilot.pt e construpilot.fr)

Estudo completo de um **edifício multifamiliar em betão armado** (cave opcional + pisos, núcleos de escada/elevador) :
estrutura (vigas e painéis gerados, sismo com proposta de paredes, modelo 3D OpenSees opcional, muros, fundações), 6 desenhos A3,
memória de cálculo, medições, orçamento, quadro de quantidades, Excel com fórmulas e — em Portugal — térmica REH, pichelaria e
eletricidade. Leitura IA das plantas reaproveitando `engines/bet_core/reader.py` ; tudo o resto é determinístico.

## 1. Ficheiros a copiar tal como estão

```
backend/engines/edificio_ba/**      (incluindo casos/exemplo_pt.json)
backend/tests/edificio_ba/**
```
Dependências : numpy, matplotlib, reportlab, openpyxl, PyMuPDF (já presentes). **Opcional** : `openseespy==3.8.0.0` (modelo 3D) ;
sem ele o estudo usa o método das forças laterais e indica-o.

## 2. Patch de `backend/routes/assistant.py` (4 inserções, nada é apagado)

1. Depois do import de `engines.bet_core.assistant_tool` :
```python
from engines.edificio_ba.assistant_tool import (TOOLS as EDIF_TOOLS, TOOL_NAMES as EDIF_TOOL_NAMES,  # edifício multifamiliar
                                               TOOL_STATUS as EDIF_STATUS, INSTRUCTIONS as EDIF_INSTRUCTIONS, execute as execute_edif_tool)
```
2. Na lista das ferramentas profissionais, a seguir a `*BET_TOOLS,` : `*EDIF_TOOLS,`
3. Em `_exec_tool`, logo a seguir ao bloco `if name in BET_TOOL_NAMES:` :
```python
    if name in EDIF_TOOL_NAMES:
        return await execute_edif_tool(name, args, user, conv, db)
```
4. Instruções : a seguir a `instructions += BET_INSTRUCTIONS` : `instructions += EDIF_INSTRUCTIONS` ; e `TOOL_STATUS.update(EDIF_STATUS)`.

Coleção MongoDB criada automaticamente : `edificio_jobs` (índices aconselhados `{job_id: 1}` único, `{user_id: 1, created_at: -1}`).
Livrables em `assistant_artifacts` (mesmo formato do bet_core), descarregados por `/assistant/artifacts/{artifact_id}/content`.

## 3. Verificação

```bash
cd backend && python -m pytest -q tests/edificio_ba          # 16 testes, ≈ 45 s (o teste 3D é ignorado sem OpenSeesPy)
python -c "from engines.edificio_ba import assistant_tool as A; print(A.run_demo('/tmp/edif')['status'])"   # PRONTO, sem internet
```
