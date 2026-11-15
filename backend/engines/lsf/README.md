# Motor LSF — Estrutura em aço leve (Light Steel Framing)

Motor **determinístico** (nenhum valor produzido por IA) que transforma a geometria de uma planta lida no ConstruPilot
— ou um projeto LSF em JSON — no estudo completo de uma estrutura em aço leve:

| Livrável | Conteúdo |
|---|---|
| Estrutura | cada perfil com a **secção real** (C/U com espessura, cantos vivos) e a sua posição 3D: montantes à modulação, montantes de extremo, de canto e de ligação, vãos com montante rei + montante de apoio em caixão (ou ombreira partilhada / montante de extremo), vergas em caixão com guias, peitoris, montantes curtos, bloqueadores (meia altura e juntas de OSB), fitas de contraventamento, guias de bordadura e vigas de piso com travamentos, asnas Fink com diagonais dorso‑com‑dorso de comprimento máximo dentro dos banzos |
| Placas | OSB / gesso cartonado / ETICS por face e por camada, juntas **sempre sobre um montante**, recortes dos vãos, faixa do piso revestida; **plano de corte MaxRects** com espessura de corte e reaproveitamento das sobras |
| Parafusos | contados **um a um**: por ligação aço/aço (regras com origem) e, nas placas, linha a linha de estrutura sob cada placa (passo de bordo / interior) |
| Ancoragens | buchas por troço de guia inferior (extremos + passo máximo), hold-downs, fixação de paredes sobre piso |
| Quantidades | perfis (kg, m, barras comerciais FFD), placas, parafusos, isolamento, ETICS (placas, rede, cantoneiras, perfil de arranque, reforços), membranas, cobertura, juntas de gesso, remates de vãos |
| Preços | 1) biblioteca da empresa, 2) preços do projeto, 3) mercado online **real** (assinalado « a analisar »; o modo de demonstração nunca é usado), senão « a orçamentar » — nenhum preço inventado |
| Dossier PDF | capa com a marca da empresa e render, síntese, hipóteses, pontos a verificar, mapa de quantidades, lista de corte, regras de fixação, **planta das paredes por piso**, **alçado de fabrico de cada parede com todas as peças numeradas** (mesmos IDs que o Excel e o 3D), asna tipo |
| Excel | mapa com totais por fórmula, lista de corte peça a peça, parafusos por origem, planos de corte, hipóteses |
| 3D | visualizador HTML autónomo (three.js empacotado, funciona sem internet) e render fotorrealista Mitsuba (sol + céu físicos) da estrutura montada |

Línguas: PT, FR, EN, UK. Unidades internas: mm.

## Utilização

```python
from engines.lsf import estudo
from engines.lsf.adapter import from_takeoff, from_mep_input
from engines.lsf.pdf import dossier
from engines.lsf.xlsx import xlsx
from engines.lsf.viewer import html_viewer
from engines.lsf.render import render          # Mitsuba (opcional)

projeto = from_takeoff(plan_doc)               # planta já lida (plans_takeoff) — ou defaults.exemplo()
st = estudo(projeto, biblioteca_da_empresa)
pdf = dossier(st["resultado"], st["linhas"], st["totais"], "pt", branding, render(st["resultado"]))
```

API (ofertas Pro / Pro Business): `routes/lsf.py` → `/api/lsf/studies…` (criação a partir de planta ou de dados, edição do
projeto com recálculo, preços, PDF, Excel, visualizador 3D, render). Assistente BTP: ferramenta `calcul_lsf`
(`engines/calc_lots/outils.py`), com a planta, a marca e a biblioteca de preços injetadas pela ponte. Frontend:
`/estrutura-lsf`, dentro da app « Estudos de Engenharia ».

## Leitura da planta (`adapter.py`)

- implantação de cada piso = união das divisões com os vazios ≤ 60 cm fechados (paredes) → face interior das paredes
  exteriores; a estrutura (gesso + perfis) é posta para fora, o ETICS por fora da estrutura — áreas úteis preservadas;
- espaços sem divisão desenhada (escada, átrio) → divisão virtual (paredes à volta com 10 cm nominais), assinalada;
- degraus de fachada < 25 cm alinhados pelo exterior (imprecisão de desenho), assinalados;
- paredes interiores = eixos entre arestas paralelas de divisões vizinhas, fundidos e prolongados até à parede de apoio;
- vãos associados ao lado do perímetro / à parede interior mais próxima; alturas não cotadas = hipóteses nomeadas;
- pisos em zonas retangulares, vão das vigas na menor dimensão, partido sobre paredes interiores do piso de baixo;
- cobertura de duas águas (asnas) se o último piso for retangular, senão plana.

## Verificação estrutural (`verificacao.py`)

Indicativa, determinística, **reaproveita os motores existentes**: combinações `structuro_eurocode` (EN 1990), ações PT
`bet_clt.norms` (sobrecargas NP EN 1991-1-1, neve Z1–Z3, vento A/B), encurvadura e flexão composta `structuro_ec3.verify_column`
(§6.3.3 método 2) e `structuro_check.util_status`. Acrescenta o próprio do aço enformado a frio (NP EN 1993-1-3 / 1-5):

- secção efetiva dos perfis C: larguras efetivas, lábio (kσ 5.13), encurvadura distorcional do reforço (mola K 5.10b, χd 5.12)
  → Aeff, Weff,y; esforço transverso com encurvadura da alma (Quadro 6.1);
- asnas Fink resolvidas como treliça (método dos deslocamentos) + flexão local dos banzos; vigas de piso (M, V, flechas
  L/250 e L/300, frequência); montantes N+M com vento (zona A); vergas em caixão; montantes de apoio e rei; ancoragens ao
  levantamento (1,0·G + 1,5·W); contraventamento (esforço por metro de parede OSB);
- descida de cargas geométrica: asnas → paredes de apoio → pisos → paredes inferiores; paredes interiores portantes assinaladas.

Parâmetros (zonas, cargas permanentes, cpe/cpi, limites de flecha, γM, resistências do fabricante) em `projeto["verificacao"]`,
com a origem de cada um; API `GET/PUT /api/lsf/studies/{id}/verificacao`; capítulo no dossier PDF, folha no Excel, resumo na
ferramenta `calcul_lsf`. Não verifica: sismo (NP EN 1998-1), ligações aparafusadas, esmagamento da alma, fogo.

## Âmbito

Pré-dimensionamento e quantidades: perfis, espaçamentos, ancoragens e regras de fixação são **parâmetros** do projeto
(com a sua origem). A verificação acima é indicativa; a verificação sísmica, as ligações e a assinatura cabem ao projeto de estabilidade.

## Testes

`pytest tests/test_lsf_engine.py tests/test_lsf_routes_pt.py tests/test_lsf_verificacao.py` — contagens verificadas à mão (comprimentos, parafusos,
ancoragens, parafusos de placa linha a linha), planta real (fixture MEP), plano de corte sem sobreposições, determinismo,
preços (nada inventado), dossier PT/FR/EN/UK, Excel, visualizador, ferramenta do Assistente, fluxo completo da API.

Visualizador: código-fonte em `assets/viewer_src/` (reconstruir com `build_viewer.mjs`).
