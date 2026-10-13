# Revisão do main e Pilote ConstruPilot — 10 de outubro de 2026

Base: `main`, commit `2e3b2fcbaaaa8ed5e18f3f0eb9f940873f420865`.
Esta proposta parte das alterações recentes do main. Não substitui a proposta anterior de redesign das páginas de apresentação e não representa uma publicação em produção.

## Resultado

Foi acrescentado o **Pilote ConstruPilot**, acessível em `/agents` por contas autenticadas, incluindo particulares. O supervisor controla os plans/métrés guardados e, quando o perfil tem acesso a devis, os devis desse utilizador. As permissões e os limites dos outros agentes profissionais continuam a aplicar-se.

O assistente conversacional recebeu ferramentas para localizar documentos, executar os seis calculadores existentes, lançar o supervisor, consultar o seu estado e pedir a sua paragem. O acesso ao assistente conversacional conserva as condições de subscrição existentes. A disponibilidade do supervisor não concede acesso às funcionalidades profissionais pagas.

Exemplo de pedido: « Vérifie les métrés et les devis de mon dossier, corrige les valeurs recalculables et indique ce qui reste à confirmer. »

O controlo automático é uma tarefa explícita que continua no servidor quando se muda de página; não é uma vigilância permanente de toda a plataforma. Não tem acesso administrativo global, não executa código arbitrário, não altera permissões e não assina, fatura ou envia documentos por iniciativa própria.

## Correções

| Área | Problema corrigido / comportamento novo |
| --- | --- |
| Calculadores | Contrato comum entre API e assistente; rejeição de NaN/Inf, números negativos, divisores nulos, contagens fracionadas, opções e campos desconhecidos. A cadeia `false` já não equivale a verdadeiro. O agente exige os campos efetivos; os exemplos da interface ficam identificados como valores por defeito. |
| Métrés | Recalcula a partir da geometria e da escala da página correta. Deteta escalas ausentes, polígonos inválidos, aberturas ou deduções incoerentes. Alturas desconhecidas não passam a volumes certificados. Preserva geometria, escala e alturas introduzidas. |
| Devis | Recalcula totais dos rascunhos, incluindo descontos, IVA e acompte. Assinala preços/quantidades ausentes e hipóteses. Devis enviados ou assinados não são corrigidos automaticamente. |
| Devis multi-níveis | Conserva a margem no preço de venda e o preço de custo separado; valida a margem; mantém a unidade `u` nas contagens e identifica linhas por chiffrer. |
| Facturas de acompte | A base de cálculo inclui os descontos e exclui linhas de apresentação. Não houve emissão de facturas durante a revisão. |
| Assistente de devis | A adição de linhas protege edições concorrentes, evita duplicar a mesma operação repetida no mesmo pedido e invalida o PDF Factur-X em cache. |
| Bibliotecas de preços | A gravação automática conserva dados na biblioteca do próprio utilizador. Não alimenta o agregado automático entre contas e não transforma preços estimados ou incompletos em referências por repetição. A pesquisa respeita `company_only` e os catálogos partilhados autorizados. Não apaga registos históricos do agregado anterior. |
| Gemini | O fallback deixa de repetir um turno depois de tentar uma ferramenta, incluindo falha após uma eventual gravação e antes do registo da ação. |
| Execução dos agentes | Lançamento e aquisição de tarefas atómicos, autorização revalidada, lease renovável, duração limitada, resultados parciais, cancelamento e proteção contra conclusão por um worker obsoleto. Um erro não produz uma notificação de sucesso. |
| Interface | Modos « contrôler » / « contrôler et corriger », acompanhamento em segundo plano, detalhes paginados, ligação ao plano/devis concreto e possibilidade de desfazer a última correção. |

## Escritas e limites

- Cada consulta/escrita é limitada ao `user_id` autenticado; não se alarga o acesso a documentos de colegas apenas por pertencerem à mesma empresa.
- Antes de gravar, compara geometria/linhas, estado e versão com a leitura inicial. Um conflito é assinalado sem substituir uma edição manual.
- Regista até 20 correções por documento. A restauração só aceita a última correção ainda não anulada e um documento que não tenha sido alterado entretanto.
- A verificação posterior confirma o resultado gravado. A tarefa distingue documentos corrigidos de dados que ainda precisam de validação.
- Seleção explícita: até 50 plans e 50 devis. Controlo geral: até 200 documentos por tipo; acima disso rejeita antes da primeira correção e pede uma seleção menor. Não corta silenciosamente a cobertura.
- Até 2 000 campos corrigidos por documento. Resultados por documento ficam em `agent_checks`, paginados. O resumo transporta apenas os primeiros 40 detalhes.
- Uma tarefa interrompida pode ter correções já aplicadas, conservadas no histórico. Após reinício, uma tarefa com lease expirado fica em erro; não se repete automaticamente uma escrita potencialmente já executada.
- Os calculadores respondem com a proveniência fornecida e distinguem coerência aritmética de verificação das medidas de origem. Não existe nesta alteração um reprocessamento retroativo de todos os cálculos ou estudos IA anteriores.

## Verificação efetuada

Análise sintática de **583 ficheiros Python** e análise sintática/nomes não definidos de **410 ficheiros JS/JSX**: sem erros encontrados nesses controlos. Isto não equivale a revisão funcional exaustiva de cada fluxo do produto.

**201 testes Python distintos e 19 subtestes passaram**, em execução isolada de serviços externos:

- 148 testes existentes: audit, colaboração e persistência do assistente, safeguards de devis, CAD, geometria, rotas, fontes e estudos de plans.
- 53 testes novos: entradas inválidas, escalas por página, aberturas, alturas ausentes, totais/descontos, permissões, isolamento entre contas, conflitos, restauração, lançamentos concorrentes, aquisição de tarefas, revogação de acesso, cancelamento, margem multi-níveis, acompte, idempotência de linhas e não repetição de ferramentas no fallback Gemini.

Chromium sobre os componentes React reais com serviços simulados: modos de controlo/correção, persistência ao navegar, erro sem falso sucesso, detalhes, conflito de restauração, restauração, cancelamento; larguras **320, 390, 768 e 1 440 px**, sem overflow horizontal ou erros JavaScript. As capturas em `docs/previews/pilote-*.jpg` mostram dados simulados e o estado de interrupção utilizado no teste, não dados de produção.

A execução conjunta dos 198 testes inicialmente selecionados passou. Após os últimos controlos de fallback e dados corrompidos, os 53 testes do novo módulo foram reexecutados com sucesso; o total de casos distintos é 201.

Comandos principais, numa instalação de desenvolvimento com as dependências do backend e um ambiente de teste:

```bash
PYTHONPATH=backend python -m pytest -q backend/tests/test_platform_supervisor.py
cd frontend
yarn install
yarn playwright install chromium
yarn test:pilot
```

O teste de interface usa `esbuild` e Playwright declarados como dependências de desenvolvimento. `CHROMIUM_EXECUTABLE_PATH` permite usar um Chromium já instalado. Não chama a API de produção.

## Validações ainda necessárias antes de produção

**A compilação de produção completa não foi validada.** Duas tentativas de instalação Yarn ficaram na resolução de dependências e foram interrompidas. Não foi alterado o conjunto de versões da aplicação para contornar esse problema; foi apenas acrescentada a dependência de desenvolvimento `esbuild` para reproduzir o teste de interface. O main consultado não contém lockfile frontend.

Os testes usam base de dados em memória e respostas de fornecedores simuladas. Falta validar o arranque completo com MongoDB real, o worker no ambiente de alojamento, o build frontend com as dependências reais e os fornecedores IA configurados em pré-produção. Os testes live existentes não foram disparados contra serviços externos, pagamentos, emails ou contas de clientes.

Não há demonstração de **98% de precisão** na interpretação de plans. Isso exige um corpus representativo de plans pequenos e grandes com métrés de referência, separado por tipo de documento e especialidade. O supervisor deteta e corrige inconsistências calculáveis; não certifica o reconhecimento integral do desenho, preços de mercado ou dimensionamento estrutural.

Não foi efetuada fusão no main, migração de dados de clientes nem publicação em produção.
