# Continuação: perímetro do orçamento e unidades do PDF

## Problema corrigido

O orçamento demonstrativo anterior cobria apenas B/C. Não demonstrava o custo do empreendimento completo. Há uma divergência documental por resolver: os dez desenhos disponíveis indicam 29 habitações e um local de atividade; a indicação do utilizador é de aproximadamente 50 habitações. O orçamento de referência indicado pelo utilizador não deve ser convertido automaticamente num resultado calculado.

No produto, a consolidação multi-nível podia apresentar «Total projet» e «devis global» mesmo com planos indisponíveis, sem medidas ou com medidas sem preço. Um plano repetido podia ser somado duas vezes. Valores não finitos não eram excluídos consistentemente.

- A API devolve cobertura explícita: planos ausentes/vazios/repetidos, medidas inválidas e medidas sem posto valorizável.
- Os montantes são identificados como subtotais das medidas registadas. A cobertura completa do empreendimento não é inferida da cobertura dessas medidas.
- A interface, o título/notas do devis e o PDF conservam a indicação de perímetro parcial. Planos não valorizados mostram «Non chiffré»/«N/C», em vez de um preço zero.
- Cada plano repetido é valorizado uma só vez. Quantidades nulas, negativas, ausentes ou não finitas ficam assinaladas e não são valorizadas.

## Leitura de unidades

Nos PDF CAD, «6,1 m» e o expoente «2» podiam estar em spans separados. O leitor tratava o primeiro span como uma distância. O contexto da linha preserva agora a identificação de m²/m³ mesmo com expoente separado; esses spans não entram no leitor de comprimentos. A versão de geometria passa a 4.

Passagem nos desenhos reais: **49 candidatos provenientes de rótulos de área foram excluídos**: 22 na folha 07.10 e 27 na 07.9. Os candidatos passaram de 194 para 172 e de 279 para 252, respetivamente. Isto remove entradas erradas do leitor; não representa 49 erros de métré final corrigidos nem comprova uma percentagem de precisão.

## Fontes e ensaios

Foram processados dez PDF pelo motor nativo local, sem erros de importação. Aos nove documentos do relatório `2026-10-10-plans-reels.md` juntou-se a folha 09.1, fachadas norte do edifício A. Os PDF privados continuam fora do repositório.

- 121 testes Python e 8 subtestes passaram nesta seleção, incluindo casos reais de rotas executados com dependências isoladas e PDF exportado inspecionado por extração de texto.
- Casos novos: orçamento parcial apesar de todas as medidas registadas terem preço; plano ausente; plano vazio; medidas inválidas/sem preço; duplicados; contagem unitária; expoentes separados m²/m³; conservação do perímetro no PDF.
- 412 ficheiros JS/JSX sem erros de sintaxe ou nomes indefinidos.
- A nomenclatura contém 119 vãos nominais: A 87, B 14, C 8 e D 10. A soma aritmética foi cruzada com `geometry.subtract_openings`. Não se confundem vãos com habitações nem se considera a dimensão nominal como dimensão de execução confirmada.

Reprodução:

```bash
PYTHONPATH=backend python backend/scripts/audit_pdf_sheets.py --input-dir /chemin/pdf --output /chemin/import.json
PYTHONPATH=backend python -m pytest -o addopts='' -n 0 -q backend/tests/test_plan_quote_scope.py backend/tests/test_real_sheet_regressions.py backend/tests/test_platform_supervisor.py backend/tests/test_audit_regressions.py
```

Os testes que importam rotas precisam de `MONGO_URL`, `DB_NAME` e `JWT_SECRET` de teste. A base e os serviços externos são simulados; não usar credenciais de produção.

## Limites

Não foi estabelecido um métré completo nem 98% de precisão. Faltam plantas detalhadas dos pisos/subsolo de A, dados estruturais, CCTP/DPGF e especificações/preços de execução para completar o orçamento global. As fachadas e cortes disponíveis não substituem esses elementos. Build de produção, MongoDB, trabalhadores de fundo e fornecedores reais continuam a precisar de validação em pré-produção. Sem fusão no main ou deployment.

Os imports antigos não são certificados por esta alteração. Depois da integração, reextrair e rever as cotes; conservar as correções manuais e os avisos do motor.
