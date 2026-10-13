# Ensaio de documentos de estrutura — Maison Houilles

## Resultado

Foram recebidos e processados localmente 20 PDF, num total de 42 páginas. Não houve erros de importação. Isto não demonstra um métré completo nem precisão de 98%.

A conferência dos cartuchos identificou dois conjuntos com identidades diferentes: dez documentos associados ao dossier STRUCTURO/Houilles (incluindo uma especificação sem identificação completa) e dez documentos cujo conjunto remete para outro projeto. As quantidades do segundo conjunto não foram somadas às de Houilles; a sua correspondência precisa de confirmação. Não foi aplicado ao novo projeto qualquer orçamento de referência da análise anterior.

## Regressão reproduzida e corrigida

Antes desta alteração, sete folhas de estrutura produziam em conjunto 389 candidatos no detetor genérico de paredes. Incluíam desenhos de fundações, detalhes de armaduras, pilares, escadas e lajes. Estes candidatos não constituíam 389 paredes validadas.

- Os títulos de cofragem, armaduras, quadros de linteis e notas de cálculo passam a identificar o contexto técnico.
- Estes documentos deixam de alimentar automaticamente o detetor de paredes/peças. O levantamento de estrutura continua a exigir correspondência por elemento, vista e nível.
- A extração de cotas de desenhos estruturais com escala única é conservada; os avisos de rattachamento incerto continuam ativos.
- Páginas sem texto extraível mostram uma lacuna de leitura e exigem leitura visual/OCR e calibração controlada. Importar uma imagem não equivale a extrair as quantidades.
- Geometria versão 5: a reextração usa a mesma classificação do import; o tratamento das correções manuais mantém-se.

Depois da alteração, os 20 PDF continuam a ser importados sem falhas e as sete folhas deixam de produzir candidatos no detetor genérico. A descrição de uma nota de cálculo de pilares de 14 páginas permanece `unknown`, sem cotas nem paredes produzidas; não é classificada nem valorizada à força. A vista 3D e cinco folhas sem camada de texto útil conservam a necessidade de leitura visual.

## Validação

- 132 testes Python e 8 subtestes passaram na seleção `test_real_sheet_regressions.py`, `test_plan_quote_scope.py`, `test_platform_supervisor.py` e `test_audit_regressions.py`.
- Casos de regressão com PDF sintéticos: cofragem de fundações, cofragem multi-vista, armaduras, pilares, detalhes de laje, quadro de linteis, nota de cálculo e imagem sem texto.
- Verificação da conservação das cotas e da calibração de desenhos estruturais com escala única.
- Uma simples referência ao plano de cofragem numa nota de planta arquitetónica não bloqueia a planta.
- `git diff --check` limpo. Nenhum PDF privado adicionado ao repositório.

O teste usa o motor nativo local do código da PR. Não é uma execução na plataforma em produção nem uma validação dos serviços IA externos. Não houve fusão no main nem deployment.

## Chiffrage

O perímetro pedido é exclusivamente gros œuvre da Maison Houilles. As quantidades do outro conjunto ficam fora desse total até esclarecimento. CCTP, plantas de arquitetura e limites de prestação ainda não foram recebidos nesta etapa; não se apresenta um total global nem preços unitários supostamente confirmados.

As secções indicadas no plano de fundações de Houilles permitem controlos de consumo geométrico por metro linear (50×30, 60×30 e 65×30 cm). Estes controlos unitários não substituem os comprimentos, as deduções de interseções e o métré completo da fundação.

## Continuação após receção dos CCTP 00 a 03

O cliente excluiu explicitamente o conjunto JAOUHAR/Courbevoie. O CCTP de março de 2026 identifica o lote 01 como gros œuvre, incluindo enduits de façade, impermeabilização dos soubassements, redes EU/EV sob o edifício e colocação dos coffres fornecidos pela menuiserie. A preparação geral do fundo de forma e a drenagem periférica são atribuídas ao VRD. Plantas/cortes de arquitetura, estudo de solo e DPGF continuam por receber.

### Escala impressa incompatível com a geometria

A folha `STRUCTURO-Coffrage-fondations.pdf` (SHA-256 `1f052982baf14cbd1ae49b2237b1e30b77bd148c736ba7d20cde20935d5b3909`) declara 1/25, mas duas distâncias perpendiculares de 5,20 m medem 412,74 pontos PDF: 79,373 pontos/m. A aplicação direta do cartucho faria essas distâncias medir cerca de 3,64 m. O motor marcava cotas como incertas, mas ainda permitia uma calibração automática pelo cartucho.

- Geometria versão 6: se pelo menos três grandes cotas formam o consenso já utilizado pelo extrator e contradizem a escala declarada em mais de 5%, a calibração automática e a inferência de geometria ficam bloqueadas.
- O motor conserva as cotas como não verificadas, mostra a necessidade de calibração conferida e não substitui automaticamente a escala impressa por uma estimativa.
- A proteção é partilhada pelo import e pela reextração. As calibrações antigas guardadas não são migradas nem recertificadas por esta alteração.

Validação desta continuação: **38 testes da suite `test_real_sheet_regressions.py` passaram**, incluindo três novos casos (PDF reduzido, ampliado e escala coerente). O plano real devolveu `auto_calibration_blocked=true`, `observed_to_declared_ratio=0.699969`, 51 cotas preservadas para revisão e nenhuma calibração inicial. A tentativa de repetir três suites adicionais ficou bloqueada na recolha por ausência de `httpx`/`fastapi` neste ambiente; os resultados dessas suites da etapa anterior não são apresentados como uma nova execução.

### Pré-métré assistido

A seleção visual dos contornos das sapatas, calibrados com as duas cotas, e a união geométrica sem sobreposições dão 59,0337 m². As funções nativas de área e de volume do ConstruPilot dão **17,710 m³** para 30 cm de espessura. É uma quantidade preliminar das sapatas desenhadas, sem betão de limpeza, aprofundamentos, perdas, aço, infraestrutura ou apoios de terraço não localizados. Não se afirma extração autónoma completa nem 98% de precisão.

O lote 03 lista 12 janelas (33,043 m² nominais) e 16 estores; não somar ambos como vãos independentes. O levantamento assinala a divergência entre lajes 16+4 e compressão mínima de 5 cm, entre brique e parpaing, e a necessidade de reconciliar os níveis e repères. Não foi emitido preço global, feita fusão no main ou realizado deployment. Os PDF privados e os levantamentos específicos permanecem fora do repositório.
