# ConstruPilot BIM Studio — Relatório técnico (construpilot.pt)

Data: 7 de novembro de 2026 · Branch: `feature/pt-bim-studio` · Repositório: `teixeira880-ctrl/construpilot.pt`
Estado: **código e testes concluídos; não publicado** (deploy reservado à Emergent, após aprovação).

---

## 0. Auditoria inicial (arquitetura encontrada)

| Tema | O que existe |
|---|---|
| Repositórios | PT = `construpilot.pt` (branch `Construpilot`); FR = `construpilot.fr_1` — **repositórios separados, sem código partilhado por git** |
| Backend | FastAPI 0.110 (`backend/server.py`, 128 routers), MongoDB via Motor, APScheduler, workers assíncronos próprios (assistente, agentes, estudos) |
| Frontend | React 19 + CRA/craco, Tailwind + shadcn/ui, `three` 0.170 já instalado, rotas em `src/App.js`, menu em `components/workspace/navigation.js` |
| Autenticação | Cookie httpOnly + JWT (`core/security.py`); `pro_required` (níveis de assinatura); organizações com papéis (`core/permissions.py`: owner/admin/chef_chantier/comptable/member/ouvrier) |
| Isolamento de dados existente | Documentos e biblioteca filtrados por `user_id` |
| Armazenamento | Emergent Object Storage (`engines/object_storage.py`, app `construpilot`) — sem API de eliminação |
| Uploads | `core/uploads.py` (whitelist + magic bytes; IFC/STEP já reconhecido) |
| CAD/plantas | DXF (`ezdxf`), DWG/RVT/IFC via Autodesk APS na nuvem (`plans_pro`), leitura de plantas por visão IA |
| Orçamentação | `routes/documents.py` → coleção `pro_documents` (linhas, IVA PT, totais `_compute_totals`), editor `/devis-editeur/:id` |
| Biblioteca de preços | `routes/library.py` → `library_items` (catálogo inicial PT + artigos da empresa) |
| IA | Claude/Gemini/OpenAI via `engines/ai_providers` |
| Ambiente | `core/environment.py` fail-closed (produção por defeito); mercado PT em `core/market.py` |

**Riscos de partilha com a França identificados:**
1. O Object Storage usa o mesmo nome de aplicação e a mesma chave Emergent que podem ser comuns aos dois sites → o BIM usa **sempre** o prefixo próprio `pt/bim/<empresa>/…`.
2. Módulos de growth/demo do PT referem domínios FR (código pré-existente) → **não tocados**.
3. Separar só por domínio não chega → o módulo **só liga** se `core.market.SITE_COUNTRY == "PT"`, e o script `check_isolation.py` bloqueia qualquer alteração fora do âmbito.
4. Nenhum ficheiro, variável, base de dados ou deploy francês foi lido para escrita ou alterado.

Não existia motor IFC local nem visualizador BIM: o Plans Pro envia IFC à Autodesk e só devolve contagens agregadas. O BIM Studio **complementa** (não substitui) essa funcionalidade.

---

## A. Arquitetura

```
Navegador (/bim-studio)
  BimStudio.jsx ─ perfis (arquiteto/engenheiro/empresa/simples)
  BimViewer.jsx ─ three.js, carregamento progressivo de blocos de geometria
        │  cookie de sessão (API privada)            │ URL assinado temporário (só download do IFC)
        ▼                                            ▼
FastAPI  /api/bim/*  (routes/bim_studio.py) ── pro_required + permissão "devis" + tenant
  │  upload → validação → Object Storage (pt/bim/…) → bim_versions(status=queued)
  │
  ├─ Fila (bim_studio/jobs.py): reserva atómica no Mongo, N workers por processo,
  │     recuperação de órfãos, cancelamento, tempo limite, métricas de duração
  │        └─ subprocesso `python -I worker_main.py` (limites RAM/CPU/ficheiros)
  │              └─ engine.py (IfcOpenShell 0.9): classificação, Psets, materiais, pisos,
  │                 Qto declaradas → geometria → estimativas; malhas por elemento
  │
  ├─ bim_elements (por versão) + bim_overrides (correções/validações humanas)
  ├─ budget.py: grupos → sugestões explicáveis → associações confirmadas → orçamento
  └─ pro_documents (orçamento editável existente) + bim_quote_traces (rastreabilidade)
```

**Visualizador — avaliação de That Open (`engine_components`)**: licença MIT, compatível. Não foi adotado nesta fase porque (1) exige servir o IFC original e o WASM `web-ifc` ao navegador, contrariando o requisito de não expor ficheiros privados; (2) obriga a alinhar versões de `three` com a já usada noutros ecrãs; (3) duplicaria a interpretação do IFC no cliente, com risco de as quantidades vistas e as orçamentadas divergirem. Optou-se por geometria gerada **no servidor** pelo mesmo IfcOpenShell que mede, servida em blocos privados e desenhada com o `three` existente. A migração para That Open continua possível mais tarde.

Licenças: IfcOpenShell (LGPL-3.0, usado como biblioteca não modificada), `three` (MIT, já existente).

## B. Alterações

Ficheiros **novos**:
- `backend/bim_studio/` — `__init__.py`, `config.py`, `constants.py`, `engine.py`, `worker_main.py`, `jobs.py`, `store.py`, `storage.py`, `budget.py`, `sample_models.py`
- `backend/routes/bim_studio.py`
- `backend/tests/test_bim/test_bim_studio.py`
- `frontend/src/pages/BimStudio.jsx`
- `frontend/src/components/bim/` — `BimViewer.jsx`, `BimPanels.jsx`, `bimGeometry.js`, `__tests__/…`
- `frontend/jest.bim.config.cjs`
- `scripts/bim_studio/check_isolation.py`
- `docs/bim_studio/EMERGENT_DEPLOY.md`, `docs/bim_studio/RELATORIO_TECNICO.md`

Ficheiros **existentes** (só linhas acrescentadas, nenhuma removida):
- `backend/server.py` (+5: routers e arranque/paragem do BIM)
- `backend/requirements.txt` (+3: `ifcopenshell==0.8.5`, `isodate==0.7.2`, `lark==1.3.1`)
- `frontend/src/App.js` (+2: rota `/bim-studio`)
- `frontend/src/components/workspace/navigation.js` (+2: entrada no menu e descrição)

## C. Funcionalidades implementadas

- Upload IFC (IFC2X3, IFC4, IFC4X1–X3) com validação de extensão, cabeçalho ISO-10303-21, esquema, fim de ficheiro e tamanho (200 MB por defeito); ifcXML/ifcZIP recusados com mensagem clara.
- Processamento assíncrono isolado, progresso, cancelamento, nova tentativa, tempo limite, recuperação após reinício, duração registada.
- Histórico de versões por modelo, associação opcional a um projeto da empresa, comparação entre versões por GlobalId (adicionados/removidos/alterados).
- Classificação: paredes, portas, janelas, lajes, pilares, vigas, coberturas (incl. lajes de cobertura e agregados IfcRoof), escadas, pavimentos, revestimentos, espaços, estrutura, fachadas, guardas, instalações, mobiliário, outros.
- Extração: GlobalId, classe IFC, tipo pré-definido, nome, descrição, tipo, materiais, espessura de camadas, piso, Psets (até 30×60 propriedades), Qto.
- Motor de medições: declarada (Qto, Net > Gross) → calculada (malha fechada: volume, face superior, face lateral dominante, altura) → estimada (caixa envolvente, área÷altura, paredes não retilíneas). Origem e fonte exata por quantidade, alternativas guardadas, valor original e unidade original preservados, conversão para SI (mm/cm/m/pés via IfcConversionBasedUnit).
- Agregadores não contados (sem dupla contagem); elementos excluíveis; dados em falta assinalados (medição principal, espessura, material).
- Correção e validação humanas com auditoria (quem, quando, valor anterior). **Só a validação humana marca uma medição como "verificada".**
- Visualizador 3D: órbita/zoom/deslocação, seleção por clique, propriedades, ocultar/isolar, filtros por piso e categoria, medição visual de distância (marcada como não verificada), destaque e isolamento dos elementos de um artigo do orçamento, recurso sem WebGL.
- Orçamento: grupos de elementos → sugestões explicáveis da biblioteca da empresa → confirmação → linhas com quantidade, preço da biblioteca, subtotais por categoria e por piso, avisos (artigo sem preço, elementos sem medição), artigos fora do orçamento, orçamento **editável** criado no editor existente (`pro_documents`), rastreabilidade linha → associação → elementos.
- Exportação do mapa de quantidades em Excel (com subtotais) e CSV.
- **Revestimentos por face** (como num software de arquitetura): paredes com lado A/B identificado como interior/exterior (Pset IsExternal + orientação em relação ao centro do edifício, com botão para trocar), lajes com pavimento/teto; pilha de até 8 camadas por face (de dentro para fora) com cor, textura procedimental no 3D (liso, reboco, azulejo, madeira, pedra, tijolo), módulo, zona em altura (ex.: azulejo 0–1,20 m + pintura por cima), espessura e artigo da biblioteca; 15 revestimentos predefinidos (pintura, reboco, estuque, azulejo, azulejo português, capoto/ETICS, granito, xisto, madeira, tijolo face à vista, pladur, microcimento, papel de parede, cerâmico, flutuante); aplicação em massa às faces visíveis (por piso/categoria/isolamento) em modo substituir, acrescentar ou remover; cópia entre versões pelo GlobalId; seleção do lado clicando na face no 3D. As áreas de cada camada entram no orçamento (camada em toda a altura = calculada pela geometria; zona parcial = estimada); escolher um artigo numa camada confirma a associação.
- Perfis: arquiteto, engenheiro (propriedades técnicas abertas), empresa (abre no orçamento, versões), modo simples (passos guiados, sem terminologia IFC, legenda de cores).
- Segurança: tenant por organização, 404 para recursos de outras empresas, permissão "devis" para alterar, URLs assinados (HMAC, 10 min) para descarregar o IFC, ficheiros nunca públicos, nada executado a partir dos ficheiros, limpeza dos ficheiros temporários, interruptor geral.

## D. Testes (executados)

```bash
# Backend — ambiente local com mongomock e armazenamento local
cd backend && python -m pytest tests/test_bim -q            # → 36 passed (configuração do repo: -n 2 --dist loadscope)
# Backend — com TODAS as dependências do requirements.txt instaladas (exceto o pacote privado
# emergentintegrations, substituído por um stub apenas para importação) + testes existentes bet_core
python -m pytest tests/bet_core tests/test_bim -q -n 0       # → 136 passed, 4 skipped
pip check                                                    # → No broken requirements found
# Importação completa de server.py → 1 420 rotas, 24 rotas BIM, 0 conflitos (rota, método)
# Frontend
yarn jest --config jest.bim.config.cjs                       # → 5 passed (executado localmente com Jest 29)
esbuild de src/App.js completo                               # → compila sem erros
# Navegador real (Chrome headless + WebGL SwiftShader): upload → processamento → 3D →
# seleção → medições → sugestões → confirmação → total → destaque no 3D: sem erros de consola
```

Cobertura dos 16 testes pedidos: 1 upload válido ✔ · 2 rejeições (pdf, ifczip, vazio, cabeçalho, esquema, truncado, tamanho) ✔ · 3 extração/contagens ✔ · 4 propriedades ✔ · 5 áreas/volumes exatos ✔ · 6 mm = m e valor original ✔ · 7 dados em falta ✔ · 8 associação ✔ · 9 orçamento (total = Σ qtd × preço, documento criado, rastreio) ✔ · 10 isolamento entre empresas (8 rotas de leitura, eliminação, nova versão + URL assinado adulterado/expirado/forjado) ✔ · 11 permissões (ouvrier) ✔ · 12 modelo grande (1 500 paredes, ≈3 s) ✔ · 13 falhas (IFC corrompido, memória, tempo limite, cancelamento) ✔ · 14 visualização (contrato da geometria + página + navegador real) ✔ · 15 regressão (bet_core + importação total do servidor) ✔ · 16 França inalterada (`check_isolation.py`) ✔.

Modelos de teste: gerados por `bim_studio/sample_models.py` (origem própria, sem licenças de terceiros), com valores esperados conhecidos.

**Não testado aqui**: arranque real do servidor com MongoDB (não disponível neste ambiente), o pacote privado `emergentintegrations`, IFC reais exportados de Revit/ArchiCAD, e o Jest 27 do react-scripts (corrido com Jest 29).

## E. Segurança

| Risco | Mitigação |
|---|---|
| Acesso entre empresas | Todas as consultas filtradas por tenant (organização ou utilizador); 404 sem revelar existência; testado |
| Ficheiros privados expostos | Object Storage privado; geometria só via API autenticada; IFC só via URL assinado HMAC de 10 min ligado a empresa+modelo+versão |
| Ficheiro malicioso / bomba de recursos | Validação de cabeçalho e esquema; tamanho máximo; parser STEP (sem execução); subprocesso `-I` com RLIMIT_AS/CPU/FSIZE, tempo total e limite de elementos/triângulos; ambiente de variáveis mínimo |
| Bloqueio do servidor | Processamento fora do processo web; arranque do módulo em segundo plano |
| Preços/quantidades inventados | Preços só da biblioteca; sugestões não entram no orçamento sem confirmação; quantidades com origem; estimadas assinaladas no orçamento |
| Erros a revelar detalhes internos | Mensagens controladas ao utilizador; detalhe só nos logs |
| Ativação acidental em produção ou em França | Desligado em produção até `BIM_STUDIO_ENABLED=1`; desligado se mercado ≠ PT ou sem IfcOpenShell |
| Rastreabilidade | `bim_audit` (upload, edições, associações, exportações, orçamento) |

Risco residual: o processamento corre no mesmo contentor (isolamento por processo e limites do kernel, não por contentor/seccomp dedicado).

## F. Isolamento — evidências de que a ConstruPilot França não foi modificada

- Todo o trabalho foi feito no clone de `construpilot.pt`; o repositório `construpilot.fr_1` não foi clonado nem escrito.
- `pushed_at` de `construpilot.fr_1` antes e depois do trabalho: **2026-11-07T14:09:01Z** (inalterado); `construpilot.fr`: 2026-10-04 (inalterado).
- `scripts/bim_studio/check_isolation.py` → "OK": só ficheiros autorizados, ficheiros partilhados com linhas apenas acrescentadas e relativas ao BIM, nenhum `.env`/`.emergent` tocado, nenhuma referência FR no código novo.
- Nenhum deploy, DNS, SSL ou variável foi alterado; nenhum job Emergent foi criado ou contactado.

## G. Emergent

Procedimento completo em `docs/bim_studio/EMERGENT_DEPLOY.md` (pré-verificação, merge, dependências, variáveis PT, testes, ambiente de teste, produção após aprovação, checklist, rollback).

## H. Pendências, limitações e riscos

1. **Validar com IFC reais** dos vossos projetos (Revit, ArchiCAD, Allplan) antes de produção — os testes usam modelos sintéticos.
2. Áreas geométricas de formas complexas (paredes curvas/em L, coberturas inclinadas) são marcadas como estimadas; recomenda-se exportar o IFC com Qto (Base Quantities) ativadas.
3. Revestimentos: a área de uma zona parcial (ex.: azulejo até 1,20 m) supõe aberturas distribuídas uniformemente e por isso é marcada como estimada; as texturas 3D são procedimentais (aproximação visual, não imagens de catálogo) e podem mostrar efeito moiré à distância.
4. Sugestões de artigos são heurísticas (sem IA nesta versão); uma camada IA verificável pode ser acrescentada depois.
4. Visualizador próprio (three.js): sem planos de corte nem medição de áreas no 3D.
5. ifcXML/ifcZIP não suportados.
6. Não existia sistema de perfis profissionais → criada preferência própria do BIM Studio (`bim_prefs`).
7. Object Storage sem eliminação → eliminação de modelos é lógica (dados ficam no armazenamento).
8. A pasta `.emergent/emergent.yml` do repositório indica o job `ddad451d-…`; o job de publicação do construpilot.pt referido anteriormente é `b7f56e69-…`. **Confirmar qual job a Emergent deve usar antes do deploy.**
9. Python de produção: rodas IfcOpenShell existem para ARM64/x86-64 e Python 3.11–3.13; confirmar a versão no contentor Emergent.
