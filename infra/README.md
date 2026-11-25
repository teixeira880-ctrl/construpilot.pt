# ConstruPilot — infraestrutura independente da Emergent

Objetivo: correr construpilot.pt e construpilot.fr num único servidor próprio (Oracle Always Free ou
Hetzner ARM), com o mesmo código, a mesma base MongoDB e os mesmos ficheiros, sem depender da Emergent.

**Regras:** a Emergent continua em produção até à validação completa. Nada de DNS, produção ou serviços
pagos sem autorização. Segredos só na VM (`infra/.env`, `infra/env/*.env`, permissões 600), nunca no GitHub.

## O que está neste diretório

| Ficheiro | Função |
| --- | --- |
| `docker-compose.yml` | MongoDB 8 (sem porta exposta), backend .pt, backend .fr (perfil `fr`), Caddy (HTTPS) |
| `backend.Dockerfile` | Imagem do backend, ARM64 e x86_64, Python 3.11, um processo uvicorn |
| `backend-entrypoint.sh` | Arranque do uvicorn (1 worker; filas e agendador no mesmo processo) |
| `Caddyfile` | HTTPS automático; site e `/api` no mesmo domínio (cookies e CORS iguais aos da Emergent) |
| `build_frontend.sh` | Build do frontend num contentor Node, publicado em `www/<site>` |
| `backup_mongo.sh` | Backup diário comprimido + cópia para R2 (rclone), retenção 14 dias local |
| `restore_test.sh` | Teste mensal de recuperação: restaura o último backup à parte e compara contagens |
| `.env.example`, `env/*.env.example` | Modelos das variáveis (sem valores) |
| `../scripts/infra/migrate_files.py` | Cópia Emergent Object Storage → R2, retomável, verificada por SHA-256 |

## Variáveis novas (código)

| Variável | Defeito | Efeito |
| --- | --- | --- |
| `STORAGE_BACKEND` | `emergent` | `s3` = R2/S3; `s3+emergent` = escreve no S3 e lê na Emergent o que ainda não foi copiado |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION` | — | Ligação ao R2/S3 |
| `SCHEDULER_ENABLED` | `true` | `false` desliga todas as tarefas automáticas (obrigatório no staging) |
| `HEAVY_RENDER_CONCURRENCY` | `1` | Renders 3D em simultâneo |
| `RENDER_THREADS` / `BLENDER_THREADS` | metade dos núcleos | Núcleos por render |
| `WORKER_IDLE_MAX_S` | `10` | Intervalo máximo entre consultas das filas sem trabalho |

Sem nenhuma destas variáveis, o comportamento na Emergent é o de hoje (armazenamento Emergent, agendador ligado).

## Passo a passo do staging

1. **VM**: Ubuntu 24.04 ARM64, 2 OCPU / 12 GB (Oracle, sem ultrapassar o limite gratuito) ou CAX21.
   Abrir só as portas 22, 80 e 443. Instalar Docker: `curl -fsSL https://get.docker.com | sh`.
2. **Código**: clonar `construpilot.pt` e `construpilot.fr_1` lado a lado em `/opt/construpilot/`.
3. **Variáveis**: `cp infra/.env.example infra/.env`, `cp infra/env/pt.env.example infra/env/pt.env` (idem fr),
   preencher com os valores do painel da Emergent; `chmod 600 infra/.env infra/env/*.env`.
   No staging: `SCHEDULER_ENABLED=false`, chaves Stripe de teste, Resend/Twilio desligados.
4. **Base de dados**: `mongodump` da base da Emergent (precisa do `MONGO_URL` de produção) →
   `docker compose exec -T mongo mongorestore --archive --gzip ... < dump.archive.gz`.
   Comparar o número de documentos por coleção dos dois lados.
5. **Ficheiros**: bucket R2 `construpilot-pt` (idem fr), `STORAGE_BACKEND=s3+emergent`, depois
   `docker compose exec backend_pt python /app/scripts_infra/migrate_files.py --report /app/data/files.json`.
   Relançar até o relatório não ter erros; depois `STORAGE_BACKEND=s3`.
6. **Frontend**: `./build_frontend.sh pt` (e `fr`).
7. **Arranque**: `docker compose up -d --build` (com `.fr`: `docker compose --profile fr up -d --build`).
8. **Backups**: `rclone config` (remote `r2`), `BACKUP_BUCKET` em `infra/.env`, cron do `backup_mongo.sh`;
   correr `restore_test.sh` uma vez antes da mudança.
9. **Testes**: pytest, E2E Playwright contra o staging, percurso de cada motor, carga (k6), segurança.
10. **Mudança** (só com autorização): janela anunciada, dump e ficheiros finais, DNS com TTL baixo,
    `SCHEDULER_ENABLED=true`, webhooks (Stripe, Resend…) para o novo endereço.
    A Emergent fica publicada mais 14 dias para voltar atrás só pelo DNS.

## Limitações conhecidas

- **Blender (`bpy`) não existe para Linux ARM64.** Os renders Blender do urbanismo devolvem a mensagem
  “O Blender não está instalado neste servidor”, como deve acontecer hoje na imagem ARM da Emergent.
  O Mitsuba (renders dos dossiers) funciona em ARM64.
- **`emergentintegrations`** (camada de IA) é instalado a partir do índice da Emergent e é importado no
  arranque. A substituição pelos SDK oficiais (anthropic, openai, google-genai, já instalados) será feita e
  testada no staging com chaves reais dos fornecedores.
