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
