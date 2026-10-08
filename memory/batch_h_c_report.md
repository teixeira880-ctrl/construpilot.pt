# Batch H + C — Relatório final

Data: 2026-02 · Scope limitado.

---

## H — Tradução Docs.jsx + Payment.jsx (FR residual → PT-PT)

### Ficheiros alterados
- `/app/frontend/src/pages/Docs.jsx` (reescrito)
- `/app/frontend/src/pages/Payment.jsx` (reescrito)

### Principais traduções
| FR | PT-PT |
|---|---|
| Souscrivez au plan | Subscreva o plano |
| Voir les tarifs API | Ver os planos de API |
| Retour aux tarifs | Voltar aos planos |
| Revoir les formules | Rever os planos |
| Votre abonnement / achat est confirmé | A sua subscrição / compra está confirmada |
| Confirmation du paiement… | A confirmar o pagamento… |
| Ne fermez pas cette fenêtre | Não feche esta janela |
| Paiement en cours de traitement | Pagamento em processamento |
| Session introuvable | Sessão não encontrada |
| Paiement annulé | Pagamento cancelado |
| Aller au tableau de bord | Ir para o painel de controlo |
| Créer un projet | Criar um projecto |
| Démarrer / Prêt à intégrer ? | Começar / Pronto para integrar? |
| Parler à un expert | Falar com um especialista |
| Prix matériaux / Calculateurs | Preços de materiais / Calculadoras |
| Chiffrez / Convertissez / Estimez (use-cases) | Orce / Converta / Estime |

### Ajustes de rotas (`/tarifs` → `/planos`)
Todos os links user-facing em Docs/Payment foram actualizados para `/planos` (rota canónica PT-PT) após tradução.

### Grep final
```
grep -nE "\b(souscrivez|voir les|retour aux|revoir les|formules|abonnement|facturation|échéance|renouveler|résilier)\b" Docs.jsx Payment.jsx
→ 0 ocorrências ✓
```

---

## C — Partilha WhatsApp no fluxo portal cliente

### Ficheiros alterados / criados
- **Criado**: `/app/frontend/src/components/btp/BotaoWhatsApp.jsx`
- **Alterado**: `/app/frontend/src/pages/OrcamentoPublico.jsx` (import + botão na secção de acções)
- **Alterado**: `/app/frontend/src/components/btp/AcaoConfirmacao.jsx` (novo estado pós-criação com link gerado + Copiar + WhatsApp)
- **Alterado**: `/app/frontend/src/components/btp/AssistenteBTPChat.jsx` (passa `linkPublico` ao modal após `confirmTool` devolver `public_link_url`)

### 1. `BotaoWhatsApp.jsx` (reutilizável, zero deps)
- SVG WhatsApp inline (ícone oficial)
- `wa.me/?text=` universal (user escolhe contacto)
- Props: `url`, `mensagem`, `variant` (`primary`/`outline`), `className`, `testid`
- Cor oficial `#25D366`
- `data-testid="btn-whatsapp-share"` por omissão (sobrescritível)

### 2. Integração portal público (`/orcamento-publico/:token`)
Secção de acções passa a ter **3 botões lado-a-lado**:
```
[Copiar ligação] [Enviar por WhatsApp] [Descarregar PDF]
```
`data-testid` novos:
- `orc-publico-acoes` (wrapper)
- `orc-publico-whatsapp`

Mensagem WhatsApp: `Orçamento ${numero} — ConstruPilot: <url>`.

### 3. Integração modal `AcaoConfirmacao.jsx`
Novo fluxo em 2 estados:

**Estado A — Pré-confirmação (como antes)**
Mantém texto PT-PT ("Confirmar acção"), checkbox email cliente,
agora com nota: *"Após a criação, poderá também partilhar por
WhatsApp ou copiar a ligação."*

**Estado B — Pós-criação (quando backend devolve `public_link_url`)**
Título verde "Link do cliente gerado" com:
- Link exibido em mono (`data-testid="acao-link-gerado-url"`)
- Botão **Copiar link** (`data-testid="acao-link-copiar"`) → `navigator.clipboard` + `toast.success("Link copiado")`
- Botão **Enviar por WhatsApp** (`data-testid="acao-link-whatsapp"`)
- Botão **Fechar** (`data-testid="acao-link-fechar"`)

Fluxo activado por `linkPublico={url, titulo}` injectado por `AssistenteBTPChat` após `confirmTool` com `payload.public_link_url`.

### 4. Alterações em `AssistenteBTPChat.jsx`
- Novo state `linkPublicoGerado` ({ url, titulo })
- Em `executarConfirmacao`: se `r.payload.public_link_url`, mantém modal aberto e setta `linkPublicoGerado` em vez de fechar
- Novo handler `fecharModalConfirmacao` para limpar ambos os states
- `<AcaoConfirmacao>` recebe novos props `linkPublico` + `onFechar`

### 5. Métrica canal (deferido P2)
Endpoint `/api/public/orcamentos/{token}/track-share` não foi implementado nesta iteração (user indicou que podia ficar P2). Documentado para iteração futura.

### Grep de validação C
```
grep -n "BotaoWhatsApp" OrcamentoPublico.jsx AcaoConfirmacao.jsx BotaoWhatsApp.jsx
→ OrcamentoPublico.jsx:21 (import), :210 (uso)
→ AcaoConfirmacao.jsx:11 (import), :125 (uso)
→ BotaoWhatsApp.jsx:15 (named export), :55 (default export)
```

---

## Métricas globais

| Métrica | Resultado |
|---|---|
| `pytest tests/` | **296 passed, 1 skipped, 13 warnings** ✓ |
| `yarn build` | **Done in 23.37s** ✓ |
| FR residual Docs+Payment | **0 ocorrências** ✓ |
| Regressões | **0** ✓ |
| Dependências novas | **0** ✓ |

---

## Scope cumprido
- [x] H — Docs.jsx + Payment.jsx 100% PT-PT, `/tarifs` → `/planos`
- [x] C — `BotaoWhatsApp.jsx` criado, zero deps
- [x] C — Visível em `/orcamento-publico/:token`
- [x] C — Visível no modal pós-criação (estado "Link gerado")
- [x] C — Botão "Copiar link" presente no modal
- [x] yarn build OK, zero regressões pytest
- [ ] P2 deferido — endpoint `/track-share` para métricas por canal

## Próximas acções recomendadas
1. **P2 — Métrica de canal**: endpoint `POST /api/public/orcamentos/{token}/track-share` com body `{channel: "whatsapp"|"copy"|"email"}` e coleção `orcamento_public_links_shares` para medir viralidade por canal.
2. Considerar `rel="noreferrer"` + fallback para share nativo (`navigator.share`) em mobile para melhor UX nativa iOS/Android.
