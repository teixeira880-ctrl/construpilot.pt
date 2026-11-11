# ConstruPilot Experience (`/experiencia`)

Página pública com três partes: filme 3D das funcionalidades, diagnóstico por profissão e estimativa de ganho.
No fim, o visitante pode pedir o relatório ou uma demonstração; só nesse momento é criado um registo.

## Ficheiros

| Ficheiro | Função |
|---|---|
| `frontend/public/cp-experience/index.html` | A página (autónoma, sem bundle). Textos PT/FR/EN, perguntas, matriz e cálculos estão no próprio ficheiro. |
| `frontend/public/cp-experience/vendor/` | three.js r128 e pós-processamento (licença MIT incluída). Sem CDN. |
| `frontend/src/pages/Experience.jsx` | Rota `/experiencia` (e `/experience`), mostra a página em ecrã inteiro. |
| `backend/routes/experience.py` | `POST /api/experience/lead` e `GET /api/experience/leads` (admin). |
| `backend/tests/test_experience_lead.py` | Testes do endpoint. |

## Pedido final

- Guardado em `commercial_leads` com `source: "experience"` e estado `demo_requested` ou `discovery_completed`.
- Notificação interna por e-mail para `info@construpilot.pt` e `info@construpilot.fr`.
  Para mudar: variável `EXPERIENCE_LEAD_EMAILS` (endereços separados por vírgula). Precisa de `RESEND_API_KEY`.
- Nenhum e-mail é enviado ao visitante. Não há agenda: a equipa propõe horários reais por resposta ao e-mail.
- Exige consentimento; regista data e texto do consentimento; conservação de 3 anos (`retain_until`).
- Anti-spam: campo armadilha, tempo mínimo de 2,5 s, 5 pedidos por hora por IP, deduplicação de 24 h.
- A pontuação (0–18) é calculada no servidor. Resume as respostas; não é uma probabilidade de compra.

## Estimativa de ganho

- Cenários de redução de tempo: 40 %, 60 % (inicial) e 70 %. As fontes estão na própria página
  ("De onde vêm estes cenários"). São referências do setor, não medições da ConstruPilot.
- Camada da equipa: 7,4 h por pessoa e por semana (FMI/PlanGrid 2018) × ponto médio da dimensão da equipa.
- Preços dos planos: os de `engines/commercial_plans.py` (Solo 99 €, Professional 249 €, Business 599 €).
  Se o catálogo mudar, atualizar `PLAN` na página.

## Limitações conhecidas

- As funcionalidades aparecem como "a confirmar na demonstração" (`st: 'UNVERIFIED'` em `MATRIX`).
  Mudar para `VERIFIED` só depois de validadas.
- O filme é conceptual: geometria fixa e valores de exemplo.
- Sem dashboard comercial próprio: os registos leem-se em `GET /api/experience/leads` ou no e-mail.
- A página não usa cookies nem analytics; as respostas não ficam guardadas no browser.

## Antes de publicar

1. `cd backend && pytest tests/test_experience_lead.py`
2. Percorrer `/experiencia` até ao pedido e confirmar o registo e os dois e-mails.
3. Subir a versão de `CACHE` em `frontend/public/sw.js`.
