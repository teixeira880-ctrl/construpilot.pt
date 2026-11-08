# Piloto automático v2 (construpilot.pt) — instruções para a Emergent

Claude programou e testou. A Emergent só faz o deploy, depois da aprovação do Martinho. **Nada da ConstruPilot França é tocado.**

## Âmbito
- Repositório `teixeira880-ctrl/construpilot.pt`, branch `feature/pt-piloto-automatico-v2` (base `Construpilot`).
- Sem novas dependências (Python nem JavaScript). Sem migrações (campos novos nos documentos `urbanismo_processos`).

## Variáveis (só PT, todas opcionais)
| Variável | Para quê |
|---|---|
| `EMERGENT_LLM_KEY` | já existe — imagens fotorrealistas (Gemini «Nano Banana») |
| `RUNWAYML_API_SECRET` | já existe se o Runway estiver ativo — recurso se o Gemini falhar |
| `URB_IMG_LIMIAR_GEOMETRIA` | limiar da verificação automática da geometria das imagens (por omissão `0.45`); afinar com imagens reais |

## Deploy de teste
```bash
git fetch origin feature/pt-piloto-automatico-v2 && git checkout Construpilot && git merge --no-ff origin/feature/pt-piloto-automatico-v2
cd backend && python -m pytest tests/test_urbanismo_auto_v2.py tests/test_urbanismo_auto_v2_routes.py tests/test_urbanismo_auto.py tests/test_urbanismo_auto_routes.py tests/test_urbanismo_pt.py -q
supervisorctl restart backend frontend
```

## Checklist no ambiente de teste
- [ ] Em `/licenciamento-automatico`, colar: «casa térrea em L com 200 m2 habitáveis, piscina e garagem exterior, terreno de 1500 m2,
      fachadas em granito e madeira, na Rua …, <freguesia>, <concelho>» → «Fazer tudo automaticamente».
- [ ] As etapas avançam até «Imagens realistas»; abre a página do processo com Coerência N/N.
- [ ] Planta do rés-do-chão em L, piscina e garagem independente na planta de implantação.
- [ ] Galeria «Imagens realistas»: 4 vistas fotorrealistas (Gemini real) com «geometria verificada», antes/depois sobre o ortofotomapa.
      **Confirmar a olho que as fotorrealistas respeitam a forma da casa** — se a verificação marcar muitas como «comparar», ajustar `URB_IMG_LIMIAR_GEOMETRIA`.
- [ ] «Mudar o projeto»: escolher «Alentejano (monte)» → tudo recalculado; imagens marcadas como desatualizadas; «Atualizar imagens».
- [ ] Peças desenhadas (PDF) e ZIP incluem as páginas «Simulação 3D».
- [ ] Assistente: «cria um dossier completo para … (frase acima)» → chama licenciamento_automatico e licenciamento_imagens sozinho.
- [ ] Aurora (avatar): pedir o mesmo; usa `POST /api/urbanismo-auto/dossier-completo` pela ponte (confirmação de escrita em voz).

## Rollback
`git revert -m 1 <merge>` e redeploy. As alterações ao motor existente são compatíveis (83 testes antigos do licenciamento aprovados).

## Atualização — nível de imagens «promotor imobiliário» (referências do cliente)

Conjunto gerado por omissão (POST /imagens sem corpo, `/dossier-completo`, Assistente e Aurora):
perspetiva, piscina, frente, jardim, aérea, perspetiva ao entardecer, interiores (sala, cozinha, suite, I.S. da suite),
planta de implantação humanizada (exata, sem IA), antes/depois DGT e — se o cliente enviar uma foto do terreno —
montagem sobre essa fotografia (só entra no dossier depois de aprovada pelo cliente).

Regras mantidas: geometria sempre da vista exata; fotorrealistas verificadas automaticamente; interiores não verificados
ficam fora do dossier; ampliação registada (`qualidade.ampliada`), nunca apresentada como resolução nativa.

Novas rotas: `POST /api/urbanismo-auto/processos/{pid}/foto-terreno` (multipart `ficheiro`, ≤15 MB, reescrita como JPEG
limpo, armazenamento privado) · `POST /api/urbanismo-auto/processos/{pid}/imagens/{iid}/aprovar` `{aprovada}`.

Variáveis opcionais (sem novo deploy para afinar):
- `URB_IMG_GEMINI_MODEL` — modelo de imagem Gemini (por omissão o do image_studio). Se a chave Emergent der acesso a um
  modelo de imagem superior, indicá-lo aqui — a confirmar no ambiente de teste, não assumido.
- `URB_IMG_CANDIDATOS` (2) — candidatos por vista, escolhido o de melhor geometria/nitidez. Custo ≈ 10 × N + 2 imagens por processo.
- `URB_IMG_LIMIAR_GEOMETRIA` (0.45) · `URB_IMG_LIMIAR_INTERIOR` (0.40) · `URB_IMG_LARGURA_MIN` (1920).

A validar no ambiente de teste com a chave real: qualidade das saídas Gemini face às referências, limiares de geometria
(interiores sobretudo) e tempo total (estimado 2 a 5 min com 3 pedidos em paralelo).

## Atualização — cadeia Runway → OpenAI → Emergent, Claude como juiz, modo leigo

Ordem automática por vista (`URB_IMG_FORNECEDORES`, por omissão `openai,runway,gemini` (o Runway ignorava a maquete: geometria 0,05 no teste real)):
1. Runway gen4_image (`RUNWAYML_API_SECRET`) — referência alargada a 16:9 (sem deformar a casa), prompt ≤ 990 caracteres.
2. OpenAI gpt-image-1 em edição, qualidade alta, `input_fidelity=high` (`OPENAI_API_KEY`; disjuntor de crédito existente).
3. Emergent / Gemini (`EMERGENT_LLM_KEY`) — último recurso, com ronda estrita.
Fornecedor sem chave é saltado. Claude (`ANTHROPIC_API_KEY`, modelo `URB_IMG_JUIZ_MODEL`, por omissão claude-sonnet-5-5)
NÃO gera imagens: julga cada candidato (realismo 0-10 e geometria) e os defeitos que aponta entram nas instruções do
fornecedor seguinte. Aceitação: geometria numérica ≥ limiar E (juiz indisponível OU geometria confirmada e realismo ≥
`URB_IMG_REALISMO_MIN`, por omissão 7). A confirmar no ambiente de teste: que as três chaves existem e que o parâmetro
`input_fidelity` é aceite pela conta OpenAI (se não for, o erro é registado e passa-se ao fornecedor seguinte).

Modo leigo (`URB_MODO_LEIGO=1` por omissão; `modo_leigo:false` no pedido para profissionais): não pergunta o que consegue
decidir — morada aproximada, casa mais pequena se não couber, renovação sem plantas tratada como estudo (registado),
repetição automática quando a DGT/mapas não respondem (`URB_LEIGO_ESPERA_S`, 15 s). Papelada em `a_completar`.
