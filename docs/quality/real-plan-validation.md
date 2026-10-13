# Ensaios com plantas reais — ConstruPilot

O objetivo é medir a leitura das plantas, a cobertura dos elementos e os erros de cálculo separadamente. Nenhum teste sintético demonstra 98% de precisão em obras reais.

## Preparar a amostra

- Conservar os ficheiros originais e respetivos hashes: PDF vetorial, PDF digitalizado, DXF e ficheiros convertidos de DWG identificados separadamente.
- Incluir obras pequenas e grandes, vários pisos e escalas, revisões, aberturas, áreas, volumes, fundações, paredes, pilares, vigas e armaduras. Separar FR/PT quando as convenções ou regras aplicadas diferirem.
- Uma pessoa competente mede a referência independentemente dos resultados do motor. Registar a folha, elemento, unidade, convenções de dedução e se a quantidade é líquida ou inclui perdas.
- Reservar parte das plantas para validação final, sem a usar no ajuste dos motores. Não misturar os resultados de treino e validação.

## Executar e comparar

1. Importar e processar a planta no ambiente de testes com os motores reais da plataforma. Guardar a versão do código, configurações, hipóteses, escalas e resposta completa de `/api/btp-ai/plans/{plan_id}/analysis`.
2. Copiar `real-plan-truth.template.json`, preencher valores independentes, associar cada elemento a `quantity_id` e `page_index` (base 0), e só depois marcar `verified: true`. Um elemento esperado que o motor não detetou deve continuar na referência, com um identificador reservado.
3. Exportar a resposta do motor para `results.json`. O avaliador aceita a propriedade `quantities` e compara `quantity_net`, não as quantidades com perdas. Para outro motor, normalizar explicitamente o resultado para `{quantity_id, page_index, unit, value}` mantendo a ligação ao documento original.
4. Executar, sem chamadas de rede nem escrita na plataforma:

```bash
python backend/scripts/evaluate_plan_quantities.py --results results.json --truth truth.json --output report.json
```

O relatório contém hashes dos dois JSON, cobertura, proporção das quantidades dentro da tolerância, precisão quando a referência é exaustiva, linhas em falta, duplicadas, unidades incompatíveis e erros por elemento. Resultados adicionais reduzem a precisão quando `exhaustive: true`. Valores ausentes ou inválidos nunca são convertidos em zero.

**Erro máximo de 2% por quantidade não significa 98% de precisão global.** As contagens exigem igualdade por defeito; outras tolerâncias têm de ser definidas antes da avaliação. Não se somam m², m³, unidades e kg numa média de erro sem significado. A amostra verificada é o único âmbito dos resultados apresentados.

## Depois de cada correção

Repetir a planta que revelou o problema e a amostra de regressão pertinente. Registar o erro antes/depois e eventuais regressões. Uma alteração de escala, hipótese de altura ou preço exige nova verificação dos resultados dependentes; não valida automaticamente a realidade física nem o dimensionamento estrutural.

Neste momento, o novo avaliador foi testado com dados sintéticos. As plantas reais e os métrés de referência a enviar pelo utilizador ainda não foram avaliados.
