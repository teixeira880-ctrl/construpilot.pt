# Métodos comuns de medição, cálculo e apresentação

Os métodos desenvolvidos para o motor CLT passam a ser os mesmos para todas as empresas e para a construção
tradicional. Código: `backend/engines/takeoff_core` (sem dependências novas; o mesmo pacote existe no repositório FR).

## Passos (iguais para todos)

1. **Alturas**: as do projeto (corte); sem alturas na planta, RDC 3,00 m e outros pisos 2,50 m, marcadas «standard».
2. **Rede de paredes** (`rede.py`, vindo de `bim_studio/clt_walls.py`): extremos ligados ao eixo da parede vizinha,
   troços alinhados sob um lintel passam a uma peça com o vão recortado. Na construção tradicional, um intervalo de
   0,60 a 3,00 m entre dois troços da mesma parede, sem outra parede a atravessá-lo, é lido como vão (altura standard
   2,10 m) e fica «estimativa» até ser confirmado.
3. **Peças**: juntas L/T/X sem contagem dupla; divisão ao formato de produção só nos sistemas pré-fabricados (CLT,
   ossaturas).
4. **Quantidades** (`sistemas.py`): CLT, alvenaria de tijolo, alvenaria de bloco, betão armado, ossatura de madeira,
   ossatura metálica leve e divisória de gesso cartonado, sistema por projeto ou parede a parede. Pavimento, teto e
   rodapé a partir das divisões desenhadas; vãos (caixilharia) contados nas peças.
5. **Origem de cada número**: medido · regra (valor publicado ou da empresa) · estimativa (hipótese, altura standard,
   vão inferido) · estimativa de imagem.
6. **Verificações cruzadas**: volume das peças vs união exata das plantas (GEOS); área bruta − vãos vs área líquida;
   eixos desenhados vs peças (informativo: mostra a contagem dupla evitada). Tolerância 2 % (editável).
7. **Preços**: biblioteca da empresa, cada preço com fonte; quantidades sem preço listadas. IVA: PT 23 % (CIVA art. 18.º),
   FR 20 % (CGI art. 278), UA 20 % (ПКУ ст. 193.1), editável no projeto.
8. **Dossier premium** (`dossier.py`, ReportLab + pypdf, sem AGPL) em PT/EN/UK/FR com o **Anexo A de desenhos cotados**
   (`desenhos.py`: planta cotada e alçados por peça em A3, escala normalizada; DXF em mm pelo ezdxf).

Marca: conta piloto → CLT Rezult; todas as outras contas → ConstruPilot. Parâmetros e biblioteca guardados por empresa
(`takeoff_parameters`, `takeoff_library`).

## Onde

- Página `/metodos-medicao` («Medições e dossier (CLT e tradicional)»): planta já lida em «Plantas e medições» ou
  projeto JSON → cálculo → dossier PDF, desenhos PDF e DXF; parâmetros e biblioteca da empresa.
- API `/api/metodos`: `GET sistemas`, `PUT parametros`, `PUT biblioteca`, `GET plantas`, `POST plantas/{id}/projeto`,
  `POST estudo`, `POST desenhos?formato=pdf|dxf&lang=`, `POST dossier?lang=`.

## Prova de equivalência com o motor CLT

`tests/test_takeoff_core.py` usa as 40 paredes reais do Home A (eixos do desenho de fabrico, 23 no RDC e 17 no +1):
o núcleo comum dá exatamente as mesmas peças, comprimentos, volumes e juntas que `clt_walls`. A mesma geometria
medida como alvenaria dá as mesmas áreas e volumes de parede; só mudam as regras do sistema.

## Fora do âmbito

Cálculo de cargas, fundações, armaduras e projeto de execução. A taxa de aço do betão armado é uma hipótese de
orçamento, não um dimensionamento.
