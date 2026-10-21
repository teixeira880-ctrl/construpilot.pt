# ConstruPilot — dossier integrado e preparação dos ensaios reais

Continuação da PR #2, sobre o main `2e3b2fcbaaaa8ed5e18f3f0eb9f940873f420865`. Os módulos existentes foram ligados entre si, evitando aplicações duplicadas.

## Alterações

- Dossier organizado em cinco áreas: visão geral, planos/documentos, orçamento/compras, comunicação e receção. O Pilote aparece na visão geral e acompanha tarefas persistentes do dossier.
- Lançamento do supervisor com `chantier_id` validado pelo servidor. A pesquisa/controlo do assistente também usa o dossier da conversa. Os relatórios guardam uma impressão das fontes; alterações posteriores aparecem como « modifié depuis le contrôle », em vez de continuarem assinaladas como verificadas.
- Margens calculadas com descontos; secções excluídas dos montantes. Versões e variantes de devis deixam de ser somadas sem escolha explícita. Devis recusados, cancelados e apagados ficam excluídos.
- Pointages limitados ao empregador autenticado. Ligações explícitas a outros dossiers não são substituídas por coincidências de nome. Projetos RH/terreno podem ser associados ao dossier através de « Rattacher ».
- Compras usam totais de linha e quantidades faturáveis, distinguem preço zero de preço ausente e excluem comandos ao brouillon dos compromissos. Uma encomenda comum a vários dossiers exige afetação explícita, para evitar dupla contagem.
- Previsão de custo final/margem baseada em custos registados e resto a comprometer declarado. Taxa horária, seleção de devis e montante restante persistem com controlo de versão. Dados inválidos, preços desconhecidos ou pointages pendentes bloqueiam a previsão completa. A previsão não atesta que todas as despesas foram registadas.
- Seguimento de entregas: data prevista, receção parcial/completa, incidente e notas. Escritas verificam proprietário, dossier, estado da encomenda e versão. Não enviam encomendas ou emails.
- O fluxo existente « sources & révisions » fica acessível a partir de cada planta. Avenants consideram descontos e quantidades a encomendar, incluindo reduções. Preços ambíguos, unidades incompatíveis ou quantidades de devis alteradas ficam sem valorização automática. Criação de novo brouillon, sem alterar o devis original, ligado ao mesmo dossier.
- Portal do cliente em bege quente/cobre, navegação legível em mobile e seleção de página limitada às permissões. Mantém o tom de marca da empresa quando configurado.
- Avaliador de quantidades com referências independentes: cobertura, erros, unidades, duplicados e precisão em referências exaustivas. Corrigida a média do avaliador anterior, que contabilizava referências vazias no denominador.

## Verificações e âmbito

Resultado final: **231 testes Python e 19 subtestes passaram**. Os dois testes de navegador passaram sem erros JavaScript ou overflow nas quatro larguras indicadas. Análise sintática e de nomes indefinidos: **412 ficheiros JS/JSX**, sem erros; ficheiros Python alterados sem erros sintáticos ou avisos Pyflakes.

Os testes de backend usam as funções reais com dados isolados; os testes de navegador usam os componentes reais alterados com respostas de API simuladas. Cobrem contas diferentes, dossiers diferentes, descontos, versões concorrentes, alterações após controlo, quantidades negativas de avenants, dados em falta e zero explícito, critérios de avaliação e navegação em 320/390/768/1440 px.

Comandos de interface (dependências de desenvolvimento instaladas):

```bash
cd frontend
yarn test:pilot
yarn test:workspace
```

O novo teste de interface substitui os componentes não alterados de receção, comunicação e partilha por fixtures. Não certifica esses fluxos externos. O modo offline de projetos e fotografias já existente foi conservado; não foi estendido a toda a plataforma. O portal de participantes e a conta particular geral mantêm percursos distintos.

Não foram implementados novos regimes fiscais, faturação eletrónica por país ou certificação estrutural. A expansão além dos fluxos FR/PT existentes exige especificação e validação próprias.

## Antes de produção

A compilação frontend completa e o arranque com MongoDB/fornecedores reais continuam por validar num ambiente de pré-produção. A instalação completa das dependências tinha ficado bloqueada na resolução Yarn na fase anterior; nesta fase foram compilados e exercitados os componentes alterados com esbuild/Chromium. Não houve fusão no main nem publicação em produção.

As plantas reais ainda não foram enviadas. Ver `docs/quality/real-plan-validation.md` para o protocolo; não se afirma que o motor atingiu 98%.
