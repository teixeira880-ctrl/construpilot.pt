# ConstruPilot BIM Studio — Instruções de deploy para a Emergent (só construpilot.pt)

> Claude programou e testou. **A Emergent é a única responsável pelo deploy**, e a produção
> só é ativada após aprovação explícita do Martinho depois de validar o ambiente de teste.
> **Não tocar em nada da ConstruPilot França** (repositório `construpilot.fr_1`, domínios,
> base de dados, variáveis, deploys).

## 0. Âmbito
- Repositório: `teixeira880-ctrl/construpilot.pt`
- Branch a integrar: `feature/pt-bim-studio` (base: `Construpilot`)
- Nada mais a alterar: sem DNS, sem SSL, sem novos serviços externos, sem outras plataformas de alojamento.

## 1. Pré-verificação (obrigatória)
```bash
cd /app
git fetch origin feature/pt-bim-studio
git remote get-url origin        # deve terminar em teixeira880-ctrl/construpilot.pt
python3 scripts/bim_studio/check_isolation.py --base origin/Construpilot   # deve terminar em "OK"
```
Se o script falhar: **parar** e reportar (não fazer deploy).

## 2. Integrar o código
```bash
git checkout Construpilot
git merge --no-ff origin/feature/pt-bim-studio -m "BIM Studio PT"
```

## 3. Dependências (backend)
Acrescentadas ao `backend/requirements.txt` (rodas binárias existem para Linux ARM64 e x86-64, Python 3.11–3.13):
```
ifcopenshell==0.9.0.post1
isodate==0.7.2
lark==1.3.1
```
```bash
cd /app/backend && pip install -r requirements.txt
python -c "import ifcopenshell, ifcopenshell.geom; print(ifcopenshell.version)"   # → 0.9.0.post1
```
Sem novas dependências no frontend (usa o `three` já instalado).

## 4. Variáveis de ambiente — APENAS no ambiente PT
| Variável | Teste (preview) | Produção | Notas |
|---|---|---|---|
| `BIM_STUDIO_ENABLED` | `1` | **não definir** até aprovação; depois `1` | Por defeito: ligado em preview/dev, desligado em produção |
| `BIM_URL_SECRET` | segredo aleatório (≥32 car.) | segredo aleatório **diferente** | Assina os URLs temporários. Sem ele usa `JWT_SECRET` |
| `BIM_MAX_UPLOAD_MB` | `200` | `200` | Tamanho máximo do IFC |
| `BIM_WORKER_MEMORY_MB` | `3072` | ajustar à máquina | Limite de memória do processo de análise |
| `BIM_JOB_TIMEOUT_S` | `900` | `900` | Tempo máximo por modelo |
| `BIM_MAX_CONCURRENT_JOBS` | `1` | `1` | Análises em paralelo por processo backend |

Não é preciso migrar dados: as coleções novas (`bim_models`, `bim_versions`, `bim_elements`,
`bim_overrides`, `bim_mappings`, `bim_audit`, `bim_prefs`, `bim_quote_traces`) e os índices são
criados no arranque. Os ficheiros vão para o Object Storage já usado pela plataforma, sob o prefixo
privado `pt/bim/<empresa>/...`.

## 5. Ambiente de teste primeiro
1. Reiniciar backend e frontend (`supervisorctl restart backend frontend`).
2. Executar os testes automáticos:
```bash
cd /app/backend && pip install mongomock-motor==0.0.36 && python -m pytest tests/test_bim -n 0 -q
cd /app/frontend && yarn jest --config jest.bim.config.cjs
```
3. Validar com a checklist da secção 7 no URL de preview.
4. Enviar o resultado ao Martinho e **esperar a aprovação explícita** antes da produção.

## 6. Produção (só após aprovação)
- Definir `BIM_STUDIO_ENABLED=1` e `BIM_URL_SECRET` no ambiente de produção **PT**.
- Deploy pelo procedimento habitual do job Emergent da construpilot.pt.
- Executar a checklist da secção 7 em https://construpilot.pt.

## 7. Checklist pós-deploy
- [ ] `GET /api/health` responde como antes (funcionalidades existentes intactas).
- [ ] Menu → "BIM Studio (modelos IFC)" abre `/bim-studio` com conta Pro.
- [ ] Conta particular não tem acesso (403/rota Pro).
- [ ] Carregar `moradia_teste.ifc` (gerado com `python -m bim_studio.sample_models moradia_teste.ifc`): estado passa a "concluído" em < 1 min.
- [ ] Modelo 3D visível; clicar numa parede mostra propriedades e medições com origem.
- [ ] Parede Norte = 28 m² (declarada); Divisória interior = 14 m² (calculada).
- [ ] Separador Orçamento: "Sugerir artigos" → confirmar 2 grupos → total coerente → "Gerar orçamento editável" abre o editor de orçamentos.
- [ ] Exportação Excel do mapa de quantidades descarrega.
- [ ] Outra conta Pro (outra empresa) **não** vê o modelo (lista vazia, 404 por URL direto).
- [ ] Ficheiro .pdf renomeado para .ifc é recusado com mensagem clara.
- [ ] Planos Pro, Orçamentos, Biblioteca e Assistente BTP continuam a funcionar.
- [ ] **construpilot.fr não recebeu nenhum deploy nem alteração** (último deploy FR inalterado).

## 8. Rollback
Por ordem de rapidez:
1. **Instantâneo, sem deploy de código**: `BIM_STUDIO_ENABLED=0` + reiniciar backend → todas as rotas `/api/bim/*` respondem 404, a fila não arranca, a página mostra "indisponível". Dados mantidos.
2. **Reverter código**: `git revert -m 1 <commit de merge>` na branch `Construpilot` e redeploy. As alterações a ficheiros existentes são só aditivas (5 linhas em `server.py`, 3 em `requirements.txt`, 2 em `App.js`, 2 em `navigation.js`).
3. Dados: as coleções `bim_*` e o prefixo `pt/bim/` podem ficar (inertes) ou ser removidos manualmente. Os orçamentos já criados a partir do BIM continuam a ser orçamentos normais.

## 9. Pedidos à Emergent
- Não alterar o código (o Claude é o único a programar). Se algo falhar, reportar o erro exato e os logs (`/var/log/supervisor/backend.err.log`, linhas com `bim_studio`).
- Não aplicar nada no projeto/job francês.
