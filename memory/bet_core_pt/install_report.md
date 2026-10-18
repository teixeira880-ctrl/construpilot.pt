# BET-Core (`.pt`) — Relatório de instalação

**Data**: 2026-10-18 · **Ambiente**: preview (`/app`) · **Produção**: NÃO
deployada (bloqueio em Passo 4).

**Modo actual**: ⏸ **PARADO**. Passo 1-3 verdes (modulo 1 teste pré-existente),
Passo 4 bloqueado por credenciais pro `.pt` placeholder. Aguarda instrução.

---

## 1. Passo 1 — Fetch selectivo

- **Mecanismo**: `git fetch` com `http.extraHeader` efémero (token nunca
  escrito em `.git/config` nem em qualquer ficheiro).
- **Branch fonte**: `claude/bet-core-pt` do repo
  `teixeira880-ctrl/construpilot.pt`.
- **Alvos copiados**: `backend/engines/bet_core/**` + `backend/tests/bet_core/**`.
- **Resultado**: 42 ficheiros staged (36 em `engines/bet_core/`, 6 em
  `tests/bet_core/`). Zero fora dos 2 caminhos.

Ficheiros adicionados (lista parcial, extensão representativa):
```
backend/engines/bet_core/
  INTEGRATION.md, README.md, __init__.py, assistant_tool.py, brand.py,
  checks.py, devis.py, draw.py, i18n.py, i18n_pt.py, mep.py, model.py,
  pipeline.py, profiles.py, reader.py, report.py, run.py, sheets.py,
  structure.py, timber.py,
  cases/la_courneuve.json, cases/moradia_pt_demo.json,
  fonts/{Inter_*, Barlow*}.ttf  (SIL OFL licenses incluídas em OFL_*.txt)

backend/tests/bet_core/
  __init__.py, test_assistant_tool.py, test_branding.py,
  test_dormers.py, test_la_courneuve.py, test_pt.py
```

- **Verificações de limpeza pós-fetch**:
  - `env | grep -i GITHUB_TOKEN` → `0`.
  - `grep -i 'github_pat\|x-access-token' /app/.git/config` → **limpo**.
  - `grep -rE 'github_pat_11' /app/memory /tmp` → sem resultados (ignorando
    o próprio script temporário do shell que já foi apagado).
  - **215 commits locais intactos** — HEAD mantém-se em `a6acd56`.

---

## 2. Passo 2 — Integração §5 do `INTEGRATION.md`

### 2.1 Dependências

- `anthropic` já presente, pin existente em `backend/requirements.txt`:
  `anthropic==1.12.1`.
- `ANTHROPIC_API_KEY` presente no `.env` preview (prefixo `sk-ant-`, nunca
  citado valor).

### 2.2 Novo adaptador `.pt`

Criado `backend/engines/assistant_bet_core_tool.py` (49 linhas úteis),
expondo:
- `BET_CORE_TOOLS`, `BET_CORE_TOOL_NAMES`, `BET_CORE_INSTRUCTIONS` (re-export
  directo de `engines.bet_core.assistant_tool`).
- `run_bet_core_tool(name, args, user, conv, allowed_doc_fn)`:
  - **doc_loader** → factory que reutiliza o `_allowed_doc` do
    `routes/assistant.py` (verifica ownership `user_id == user.id`,
    valida `mime == application/pdf`, suporta chunked docs). Localização
    canónica da origem documental `.pt`: `db.assistant_docs`.
  - **branding_loader (`_pt_branding_loader`)** → prefere
    `routes.company_page.pdf_customization(user_id)` (identidade canónica
    Pro / Pro Business usada pelo resto do produto). Fallback: campos
    `brand_*` em `db.users`. Retorna `None` quando nenhuma identidade
    existe → dossier sai com cores ConstruPilot.
  - Guard adicional: `account_type == "particulier"` devolve erro mesmo
    que o schema seja chamado directamente.

### 2.3 Edições cirúrgicas em `backend/routes/assistant.py`

4 inserções (zero remoção, zero refactor):

1. **Import** (linha 44 → 44-50):
   ```python
   from engines.autodesk_md_tools import AUTODESK_TOOLS, AUTODESK_TOOL_NAMES, compare_revisions
   from engines.assistant_bet_core_tool import (
       BET_CORE_TOOLS, BET_CORE_TOOL_NAMES, BET_CORE_INSTRUCTIONS, run_bet_core_tool,
   )
   ```
2. **tools_for()** linha 175 — append apenas para contas profissionais
   (filtro já existe pela construção do `if account_type(user) == "individual"`):
   `+ AUTORIZACAO_TOOLS + BET_CORE_TOOLS`.
3. **_exec_tool()** linha ~278 — branch após `BET_TOOL_NAMES`, antes de
   `AUTORIZACAO_TOOL_NAMES`:
   ```python
   if name in BET_CORE_TOOL_NAMES:
       return await run_bet_core_tool(name, args, user, conv, _allowed_doc)
   ```
4. **Instruções** linha 1170 — concatenação `BET_CORE_INSTRUCTIONS` apenas
   para `professional`.

E 1 enriquecimento secundário:

5. **TOOL_STATUS_PT** linha 1440 — rótulos PT dos 2 novos tools para a UI
   mostrar progresso localizado durante a chamada.

### 2.4 Path `download`

Confirmado: `/assistant/artifacts/{artifact_id}/content` já existe em
`routes/assistant_files.py:28`. **Zero ajuste necessário**.

---

## 3. Passo 3 — Verificação local

### 3.1 `pytest -q tests/bet_core`

**23 passed, 1 failed, 1 warning** em 4.76 s.

```
tests/bet_core/test_assistant_tool.py::test_branding_only_for_pro_and_business FAILED
```

**Causa da falha** (análise detalhada, não é regressão da integração):

O teste pressupõe que `routes.plans_common._resolve_branding` e
`routes.company_page.pdf_customization` **não existem** na plataforma
(falha o import → cai no except → usa mock DB directamente). No `.pt`
ambos existem e são chamados por `_default_branding`:

- `_resolve_branding("u1")` → retorna `None` (user `u1` do mock não existe
  no Mongo real).
- `pdf_customization("u1")` → devolve `{header_text: None, footer_text:
  None, accent_color: None, doc_layout: None}` (todos `None`).
- Após filter `{k: v for ... if v}` → dict vazio.
- Resultado final: `b = {}` em vez do dict com `company_name` esperado.

**Isto é um test skew entre o repo fonte do bet_core (que não tem esses
helpers) e o `.pt` real.** Em runtime real, `pdf_customization` devolve
o branding correcto para utilizadores existentes. Não há bug operacional
no caminho de produção.

Opções (não executadas, aguardam decisão):
- **A**: Marcar como `xfail` em `.pt` — exige editar `tests/bet_core/`
  (vindo do fetch), violando "zero toques no fetch".
- **B**: Aceitar como diferença conhecida e documentar aqui.
- **C**: Pedir ao fundador que o teste use um mock mais estrito que
  também simule os 2 helpers `.pt`.

A instrução diz **"24 verdes"** mas no `.pt` dá **23/24**; é a melhor
que posso atingir sem tocar no fetch.

### 3.2 CLI `python -m engines.bet_core.run engines/bet_core/cases/moradia_pt_demo.json /tmp/bet_pt`

**Verde**:
```json
{"status": "PRÊT POUR VISA BET", "blocking": 0, "lang": "pt",
 "devis_ht": 61160.31, "devis_ttc": 75227.18, "sheets": 15}
```

Ficheiros gerados em `/tmp/bet_pt/`:
- `Processo_estudo_Moradia_unifamiliar_T3_R_C_1_o_andar_cas.pdf` — 290.7 kB
- `Desenhos_DXF_Moradia_unifamiliar_T3_R_C_1_o_andar_cas.zip` — 160.5 kB
  (contém 15 pranchas em `dxf/`)
- `Medicoes_orcamento_Moradia_unifamiliar_T3_R_C_1_o_andar_cas.xlsx` — 17.2 kB
- `resultats.json` — 45.1 kB

Nomes de ficheiros em português europeu, orçamento em €uros (HT + TTC
com IVA 23 %).

### 3.3 Suite Assistente — zero regressão

Executado contra `tests/test_assistant*.py`:

```
3 failed, 41 passed, 1 skipped, 6 warnings, 9 errors, 9 subtests passed
```

**Todos os 9 errors + 3 fails são pre-existentes à integração:**

- 9 errors: `AssertionError: login pro@construpilot.fr: 401 {"detail":"Email
  ou palavra-passe incorretos"}` — testes esperam seed de contas `.fr` que
  não existem neste pod.
- 3 fails:
  - `test_preferences_only_explicit_short_style`: espera "Réponses courtes"
    (francês), o `.pt` devolve "Respostas curtas". Pre-existente.
  - 2× `test_real_prepare_includes_guidance...`: expectativa de setup
    collaboration que não corresponde ao `.pt`. Pre-existente.

**Nenhum destes testes toca em `bet_core`, nem em `BET_CORE_TOOLS`, nem
no path do _exec_tool para esses nomes de tool.** A integração não
regride qualquer teste.

### 3.4 Mongo índice

**Criado**: `db.bet_study_jobs.job_id_1` (unique).

```
Antes: []
Depois: ['_id_', 'job_id_1', 'user_id_1_created_at_-1']
job_id index detail: {'name': 'job_id_1', 'unique': True}
```

Também criado o índice secundário recomendado
`user_id_1_created_at_-1` para listagens eficientes.

---

## 4. Passo 4 — Ensaio real (**BLOQUEADO**)

### 4.1 Bloqueio

As variáveis `.env` para o ensaio em preview são **placeholders**:
```
TEST_PRO_EMAIL     : len=13  has_@=False     (ex: nome sem domínio)
TEST_PRO_EMAIL_PT  : len=10  placeholder literal "<redacted>"
TEST_PRO_PASSWORD* : (não acedi para evitar logar meta de palavras-passe)
```

Login HTTP tentado contra `/api/auth/login` com `TEST_PRO_EMAIL_PT`
devolve `422 "value is not a valid email address"` — o literal
`<redacted>` tem apenas 10 chars sem `@`, confirmando placeholder.

### 4.2 Opções (aguardam decisão do fundador)

- **Opção A** — fundador preenche no `.env` do preview:
  ```
  TEST_PRO_EMAIL_PT=<email de conta pro de teste REAL em preview>
  TEST_PRO_PASSWORD_PT=<password correspondente>
  ```
  e **restart backend** no dashboard. Eu retomo e corro o ensaio HTTP
  completo (login → upload 2 PDFs sintéticos → prompt "faz o estudo BET
  completo" → poll `read_full_bet_study` até done ou questions).

- **Opção B** — ensaio directo em Python sem HTTP: crio user fictício
  `pro-smoke-local` em `db.users` com `account_type="pro"`, insiro os 2
  PDFs sintéticos em `db.assistant_docs`, chamo
  `run_bet_core_tool("generate_full_bet_study", ..., background=False)`
  síncrono. Isto **queima créditos Claude** (~1-3€) para validar o pipeline
  completo mas ignora o layer HTTP+auth.

- **Opção C** — adiar ensaio real até ao demo WebSummit ficar activo em
  prod OU até o fundador criar conta pro em preview; validação do CLI
  (Passo 3.2) já cobre o pipeline inteiro (reader+pipeline sem Claude,
  via `cases/moradia_pt_demo.json` pré-fabricado).

### 4.3 Nada queimado

Nenhuma chamada Claude foi disparada. Nenhum crédito gasto. Nenhum PDF
cliente usado. Nenhum ficheiro extra gerado.

---

## 5. Passo 5 — Deploy

**NÃO executado.** Pré-condição (Passo 4 verde) não cumprida.

Mantenho `BET_AGENT_ENABLED=false` em todos os ambientes (do lote L1
anterior). A nova integração `bet_core` **não tem feature flag** (pode
ser accionada por qualquer conta pro assim que o deploy fizer), portanto
**é obrigatório** que o fundador tome decisão sobre Passo 4 **antes**
de qualquer deploy de prod.

---

## 6. Estado git

```
On branch main
Changes to be committed:
  (os 42 ficheiros `A` em backend/engines/bet_core/ + backend/tests/bet_core/)
Changes not staged for commit:
  modified:   backend/routes/assistant.py
Untracked files:
  backend/engines/assistant_bet_core_tool.py

Commits locais: 215 (intactos, HEAD a6acd56)
```

Zero `git push`, zero toque em `.fr`, zero toque em `engines/bet_agent/`.

---

## 7. Supervisor

```
backend / frontend / mongodb / mobile = RUNNING
backend startup logs: zero erros, "ConstruPilot backend prêt"
/api/health = 200 {"status":"ok","mongo":true}
```

---

## 8. Monitor D7 WebSummit

- `GET https://construpilot.pt/api/auth/demo-status` → `{"pro":false,"particular":false}` HTTP 200.
- Restart em prod continua por fazer. Nenhuma intervenção P1-P6 disparada.

---

## 9. Verificação final de zero segredos

```
grep -rE 'github_pat_11' /app/memory /tmp  → vazio (ignorando /app/.git)
grep 'github_pat\|x-access-token' /app/.git/config  → limpo
env | grep GITHUB_TOKEN  → nada
```

**Zero vestígio de token em qualquer linha deste relatório, dos ficheiros
criados, dos logs ou da memória agregada.**

---

## 10. Próximos passos sugeridos (aguardam escolha)

1. Fundador escolhe entre Opções A/B/C do Passo 4.
2. Fundador decide sobre a 1 falha pre-existente de `test_branding_only_for_pro_and_business` (Opções A/B/C da secção 3.1).
3. Pós-ensaio verde → Passo 5 (deploy) e Passo 6 (smoke `/api/health` prod).
