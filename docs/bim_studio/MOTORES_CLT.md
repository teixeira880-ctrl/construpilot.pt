# Motores CLT: geometria, corte, 3D e desenhos de fabrico

Este documento descreve os motores acrescentados ao piloto CLT em 2026-11-11, as
bibliotecas open-source em que assentam e os testes feitos com os desenhos reais.

## Princípio

Cada quantidade é calculada por pelo menos dois caminhos independentes e o
resultado só fica "medido" quando os caminhos concordam dentro de 2 %. O que é
lido automaticamente fica "detetado, por confirmar"; o que vem de uma imagem é
sempre "estimativa de imagem".

## Motores

| Módulo | Faz | Verificação cruzada |
|---|---|---|
| `bim_studio/clt_walls.py` | Rede de paredes por eixos: juntas L/T/X/colineares, peças de produção (a parede mais longa passa, a outra encosta), divisão acima de 18 m, vãos por peça, comprimento de juntas verticais | Volume das peças vs união das plantas (Shapely/GEOS) menos sobreposições |
| `bim_studio/clt_nesting.py` | Plano de corte das peças nos painéis de prensa, por espessura e número de camadas; comprimento e largura à medida opcionais; corte de serra | Heurística de prateleiras vs OR-Tools CP-SAT (fica o melhor) e mínimo teórico por área |
| `bim_studio/clt_ifc.py` | Modelo IFC4: IfcWall por peça, IfcOpeningElement por vão, conjunto de camadas CLT, Qto_WallBaseQuantities e Pset ConstruPilot_CLT com a origem | Volume de cada sólido recalculado por OpenCascade vs volume analítico, peça a peça |
| `bim_studio/clt_drawings.py` | DXF em mm (planta dos eixos, alçado de fabrico por peça com vãos e cotas, plano de corte) e PDF A3 com uma folha por grupo | DXF relido pelo ezdxf nos testes |
| `bim_studio/clt_pdf_walls.py` | Leitor genérico de PDF vetorial: escala "1:N" lida na folha, contornos pela cor da legenda, larguras nominais ±3 mm, paredes só tracejadas | Comparado com o take-off revisto do Home A |
| `bim_studio/clt_raster_walls.py` | Leitor de plantas em imagem (JPG/PNG): banda de cinzento das paredes, separação horizontal/vertical, incerteza de 1 píxel | Só estimativa; nunca passa a "medido" |

Formato de prensa por omissão: Rezult, comprimento ≤ 18,00 m, largura ≤ 3,50 m,
espessura 60 a 360 mm (clt-rezult.com/en/technical-characteristics, lido em
2026-11-11). Corte de serra de 10 mm: hipótese editável.

## API (`/api/clt-industrial/motores`)

- `POST /analise`: pisos com paredes por eixo → juntas, peças, plano de corte, verificação 3D e totais.
- `POST /ifc`: o mesmo corpo → ficheiro IFC (recusa com 422 se a verificação 3D falhar).
- `POST /desenhos?formato=pdf|dxf`: desenhos de fabrico.
- `POST /pdf-paredes` (multipart): PDF, página, altura estrutural, escala opcional, cor opcional → paredes detetadas e análise.

Na página `/clt-industrial`, separador "Juntas, corte, 3D e fabrico".

## Testes com os desenhos reais

`python -m scripts.clt_engines_report --pdf "Home A.en.pdf" --image "RDC=terreo.jpg" --out pasta`
gera o relatório PDF, o IFC e os desenhos de fabrico. Resultados de 2026-11-11 (Home A, SHA-256 0320687a…):

- Leitor genérico, sem números de traçado revistos: RDC 23/23 paredes, erro de comprimento 0,05 %; +1 17/17 paredes (incluindo a parede só tracejada de 2,499 m), erro 0,00 %.
- Volume das peças vs união das plantas: RDC 18,540 vs 18,539 m³; +1 12,602 vs 12,602 m³.
- IFC: 40 peças, 31,141 m³, erro máximo OpenCascade 0,01 %.
- Plano de corte: 100 mm, 6 painéis (mínimo teórico 5); 160 mm, 1 painel.
- Imagens da segunda casa: leitura feita, mas só estimativa (±50 mm por medida a 20,2 px/m).

## Bibliotecas e licenças

| Biblioteca | Licença | Uso |
|---|---|---|
| Shapely / GEOS | BSD-3 / LGPL-2.1 | geometria 2D |
| OR-Tools (CP-SAT) | Apache-2.0 | plano de corte |
| IfcOpenShell + OpenCascade | LGPL-3.0 / LGPL-2.1 | IFC e sólidos 3D |
| ezdxf | MIT | DXF |
| Matplotlib | PSF/BSD | PDF dos desenhos |
| OpenCV | Apache-2.0 | imagens |
| PyMuPDF | AGPL-3.0 ou comercial | leitura de PDF (já existia) |

Todas já estavam no `requirements.txt`; não há dependências novas. As
bibliotecas LGPL são usadas como dependências, sem copiar código.

Avaliados e não integrados: FreeCAD (LGPL, pesado para servidor), Bonsai/BlenderBIM,
LibreCAD, QCAD e LibreDWG (GPL: não podem entrar no produto); o DWG continua via
Autodesk APS.

Atenção: o PyMuPDF é AGPL-3.0. Num serviço web, a AGPL obriga a publicar o código
do produto ou a comprar a licença comercial à Artifex. Alternativas permissivas
para a leitura vetorial: pdfplumber/pdfminer.six (MIT) e pypdfium2 (Apache-2.0/BSD).

## Limites

- Paredes acima de 3,50 m de altura (painel vertical) são recusadas e têm de ser divididas.
- Um vão sobre uma junta de painel é recusado.
- Paredes curvas não são lidas; diagonais são lidas no PDF vetorial mas não nas imagens.
- Os desenhos são de conferência de fabrico, não substituem o projeto de execução.
