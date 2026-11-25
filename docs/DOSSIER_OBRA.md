# Dossier de Obra — ConstruPilot PT

Centro de trabalho por obra: áreas → especialidades → fase → local, assistente contextual, dependências e compilação do documento final.
Assenta no processo de obra existente (`/chantiers`): plantas, orçamentos, fotografias e autos são ligados **por referência**, nunca copiados.

## Rotas

| Ecrã | URL |
|---|---|
| Visão geral («Por onde quer começar?») | `/chantiers/:id/dossier` |
| Gestão das especialidades (ativar, ocultar, personalizar) | `/chantiers/:id/dossier?vista=especialidades` |
| Especialidade | `/chantiers/:id/dossier/especialidade/:chave?fase=…&local=…` |
| Compilar / emissões | `/chantiers/:id/dossier/compilar` |

Entrada: botão **Dossier de obra** no processo de obra. Fora de produção, a lista de obras mostra **Exemplo demonstrativo** (cria a «Moradia em L»; o servidor recusa em produção).

API: `/api/dossier-obra/*` (`backend/routes/dossier_obra.py`). Coleções novas: `dossier_obra_configs`, `dossier_obra_items`,
`dossier_obra_specialties`, `dossier_obra_dependencies`, `dossier_obra_emissions` (índices em `server.py`, incluídas na purga de conta).
Nenhuma migração destrutiva: obras antigas abrem sem configuração; os registos já ligados à obra aparecem em «Por organizar».

## Desenho (ecrãs de referência)

- Cabeçalho e menu lateral verde-escuro para toda a plataforma (`styles/workspace-green.css`); com um dossier aberto, o menu mostra «ESPECIALIDADES» e «Documento final».
- Especialidade com medições/materiais → resumo (etapas, próximo passo, pendências, ligações, informação, «Da especialidade ao dossier completo»).
- `?secao=plantas|medicoes|orcamento|materiais|registos` → detalhe (separadores, esquema da medição, camadas, trama, «Antes de começar»).
- Especialidade de verificação → sequência («Preparar…», «Este trabalho liga-se a…», «Documentos e registos»).
- Compilação → conteúdo / pré-visualização / assistente, formatos, orçamento completo e emissões.

## Orçamento por módulo

Cada especialidade tem o separador «Orçamento»: quantidades a partir das medições, preços da biblioteca ou introduzidos (sem preço → «a definir»).
«Orçamentar só esta especialidade» cria um orçamento novo em rascunho; na compilação, «Criar orçamento completo» junta as especialidades escolhidas.
API: `GET /dossier-obra/{id}/orcamento?especialidades=…`, `POST /dossier-obra/{id}/orcamento/rascunho`.
Ações para ligar a Aurora/assistente por prompt: `GET /dossier-obra/acoes`.

## Regras implementadas

- Isolamento: mesma regra do processo de obra (só o dono) + permissão `chantier`; informação financeira só com permissão `devis`/`factures`.
- Modo Guiado/Técnico: preferência do utilizador (`users.dossier_mode`); só muda a apresentação.
- Informação inferida nunca nasce validada; camadas confirmar / corrigir / rejeitar com histórico.
- Alterações com impacto ou em registos aprovados/ligados a compromissos → 409 com o impacto; só com confirmação; os relacionados ficam «a rever».
- Orçamentos aceites, encomendas enviadas e autos aprovados nunca são alterados por este módulo.
- Emissões: retrato congelado (sha256), versão incremental, anteriores preservadas; PDF, DOCX, XLSX e ZIP gerados a partir do mesmo modelo.
- Assistente: reutiliza o Assistente BTP (`routes/assistant.py`); uma conversa por especialidade com `dossier_context`; regras: factos / cálculos / hipóteses / sugestões, sem inventar, pedir validação.

## Testes

```
cd backend && pytest tests/test_dossier_obra.py -n 0          # requer mongomock-motor
cd frontend && yarn build && PYTHON=…/venv/bin/python CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome node scripts/test-dossier-obra.cjs
```
O teste de navegador usa as rotas reais com Mongo em memória e um assistente **simulado** (sem IA).

## Limitações

- As ferramentas existentes (plantas, compras, planeamento, fotografias) recebem `?chantier=&especialidade=&fase=&local=`; hoje só usam `chantier`.
- A pré-visualização de planta mostra a origem da medição (documento, revisão, página, escala, método); não desenha a planta nem lê layers DWG.
- O assistente não foi testado com o modelo de IA real neste ambiente.
- O índice do PDF lista capítulos sem números de página.
