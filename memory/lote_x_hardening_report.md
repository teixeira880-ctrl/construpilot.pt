# Lote X — Hardening (admin secundário + seed demo gated + uploads validados)

- Preview: `https://construpilot-recon.preview.emergentagent.com`
- Data: 2026-10-15
- Scope: 3 fixes do briefing X.1, X.2, X.3.
- Regras: nenhum GitHub, nenhum push, nenhum deploy, nenhuma edição `.env`.

---

## Resumo PASS/FAIL

| Fix | Estado | Testes | Resultado |
|---|---|---|---|
| **X.1** admin secundário fail-closed | ✅ Done | 2 pytest | 2/2 PASS |
| **X.2** seed demo gated por `SEED_DEMO_DATA` | ✅ Done | 2 pytest | 2/2 PASS |
| **X.3** uploads: whitelist + max_size + sanitização | ✅ Done + aplicado em 1 endpoint referência | 6 pytest | 6/6 PASS |

**Total: 10/10 PASS** (via `pytest tests/test_lote_x_hardening.py -v`).

---

## Tabela de mudanças ficheiro × linhas

| Ficheiro | Linhas afectadas | Mudança |
|---|---|---|
| `/app/backend/server.py` | **387-396** (+10/-5) | X.2: `provision_accounts` gated por `SEED_DEMO_DATA`, com log PT-PT |
| `/app/backend/server.py` | **464-493** (+30/-27) | X.1: admin secundário fail-closed — remove fallback `CP-Admin-2026!`, early-return com log PT-PT se env vazia, comentário SEC-X-001 |
| `/app/backend/core/uploads.py` | **1-92** (**criado**) | X.3: módulo central com `ALLOWED_IMAGE/DOCUMENT/CAD/IMPORT/AUDIO`, `sanitize_filename`, `validate_upload`, `MAX_UPLOAD_MB` configurável |
| `/app/backend/routes/admin_learning.py` | **4-10** (+3/-0) | X.3: import `validate_upload` + whitelists |
| `/app/backend/routes/admin_learning.py` | **73-78** (+4/-3) | X.3: aplica `validate_upload` ao endpoint `/import-file`; remove verificação manual de tamanho |
| `/app/backend/.env.example` | **8-21** (+12/-0) | X.1/X.2/X.3: documenta `SEED_DEMO_DATA`, `SECOND_ADMIN_PASSWORD`, `MAX_UPLOAD_MB` |
| `/app/backend/tests/test_lote_x_hardening.py` | **1-121** (**criado**) | 10 pytests cobrindo os 3 fixes |

Nenhuma edição em `.env` real. GitHub não tocado.

---

## X.1 — Admin secundário fail-closed

**Comportamento antes**: `second_admin_pwd = os.environ.get("SECOND_ADMIN_PASSWORD") or "CP-Admin-2026!"` → se `.env` sem a var, criava a conta com password hardcoded.

**Comportamento depois** (`server.py:464-493`):
```python
second_admin_pwd = (os.environ.get("SECOND_ADMIN_PASSWORD") or "").strip()
if not second_admin_pwd:
    logger.info("Admin secundário não provisionado: SECOND_ADMIN_PASSWORD não definida")
else:
    # ... fluxo normal de criação ...
```

**Verificação live pós-restart**:
```
POST /api/auth/login {email: info@construpilot.pt, password: CP-Admin-2026!}
→ {"detail":"Email ou palavra-passe incorretos"}  ✅ (conta não recriada neste boot)
```

**Testes passados**:
- `test_x1_second_admin_no_hardcoded_fallback` — `"CP-Admin-2026!"` não existe no código.
- `test_x1_second_admin_fail_closed_log_present` — log PT-PT presente.

**Nota importante**: a conta `info@construpilot.pt` pode já existir na BD de execuções anteriores com o hash do password antigo. **A desactivação só se concretiza completamente após eliminação manual pelo Martinho** (ver FOLLOW-UP #1).

---

## X.2 — Seed demo gated por `SEED_DEMO_DATA`

**Investigação prévia** (grep solicitado no briefing):
```
backend/core/provisioned_accounts.py:14  → 3 contas E2E com password `TesteE2E!2026` em claro
backend/server.py:394                     → `if os.environ.get("SEED_DEMO_DATA")=="true"` já existia
                                             mas apenas protegia os 5 ADMIN/DEMO/CLIENT/PRO/COLLEGUE,
                                             NÃO protegia `provision_accounts`.
```

**Mudança** (`server.py:387-396`):
```python
_seed_demo = os.environ.get("SEED_DEMO_DATA", "false").lower() == "true"
logger.info("Seed de contas de demonstração %s", "LIGADO" if _seed_demo else "DESLIGADO")
if _seed_demo:
    try:
        from core.provisioned_accounts import provision_accounts
        await provision_accounts(db, hash_password, new_user_id)
    except Exception as e:
        logger.warning(f"provisioned accounts skipped: {e}")
```

**Verificação live pós-restart**:
```
backend.err.log: "Seed de contas de demonstração DESLIGADO"  ✅
```

A conta `teste.pro+e2e@construpilot.pt` ainda faz login (`200`) porque **já existia na BD** de boots anteriores. O gate só impede nova criação — não apaga contas existentes (nunca apagamos contas, por regra).

**Testes passados**:
- `test_x2_provision_accounts_gated_by_seed_demo_data` — verifica ordem textual: `SEED_DEMO_DATA` definido antes de `await provision_accounts(`.
- `test_x2_seed_log_portuguese` — log PT-PT presente.

**Decisão documentada**: mantive o bloco antigo (linha 394-429) que condiciona os 5 ADMIN/DEMO/CLIENT/PRO/COLLEGUE — já estava correctamente gated. Só adicionei o novo guard para `provision_accounts`.

---

## X.3 — Uploads: whitelist + max_size + sanitização

**Módulo centralizado criado**: `/app/backend/core/uploads.py` (92 linhas).

### Whitelist de content_types

| Constante | Tipos aceites | Uso típico |
|---|---|---|
| `ALLOWED_IMAGE` | `image/png`, `image/jpeg`, `image/webp`, `image/gif` | Avatares, fotos de obras |
| `ALLOWED_DOCUMENT` | `application/pdf` | Orçamentos, dossiers |
| `ALLOWED_CAD` | `application/dxf`, `image/vnd.dxf`, `application/acad`, `application/x-autocad`, `application/octet-stream` | Plantas DWG/DXF |
| `ALLOWED_IMPORT` | `text/csv`, `application/vnd.ms-excel`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Importação dados |
| `ALLOWED_AUDIO` | `audio/mpeg`, `audio/wav`, `audio/webm`, `audio/ogg`, `audio/mp4` | Dictados voz |

**Decisão sobre CAD**: incluí `application/octet-stream` apesar de ser genérico — muitos browsers enviam DWG/DXF assim. Alternativa estrita seria rejeitar `octet-stream` mas quebraria o fluxo real. **FOLLOW-UP**: avaliar magic-bytes para substituir o content-type genérico.

### API

```python
await validate_upload(file, ALLOWED_IMAGE)          # content_type + size + filename
await validate_upload(file, ALLOWED_DOCUMENT, max_mb=15)  # override tamanho
sanitize_filename("../../etc/passwd")  → "passwd"
sanitize_filename("file with !@# chars.pdf")  → "file_with____chars.pdf"
```

- **400** se content_type fora da whitelist.
- **413** se > `max_mb*1024*1024` (default 20MB via `MAX_UPLOAD_MB` env).
- `file.filename = sanitize_filename(...)` — mutação defensiva.

### Aplicação (reference impl)

| Endpoint | Ficheiro:linha | Status | Limite aplicado |
|---|---|---|---|
| `POST /admin/learning/import-file` | `admin_learning.py:73-78` | ✅ Aplicado | `max_mb=15` (preservação de contrato) |

**Padrão de migração para os 8+ endpoints restantes**:
- Endpoints com limite explícito prévio (como este, 15 MB) → **preservar o limite** para não quebrar contratos existentes.
- Endpoints sem limite explícito → aplicar o default global de **20 MB** via `core/uploads.py` (`MAX_UPLOAD_MB`).
- Justificação adicional neste caso: o motor `engines.learning.extract_file_text` extrai texto de exemplos few-shot; ficheiros >15 MB tipicamente são CAD/vídeo não úteis para aprendizagem, logo o limite inferior é funcional (não apenas defensivo).

### Endpoints não migrados neste commit (FOLLOW-UP técnico)

Identificados no relatório W mas não migrados por **limite de contexto/risco**:

| Endpoint | Ficheiro:linha | Razão para adiar |
|---|---|---|
| `POST /assistant/upload-doc` | `assistant.py:649` | Fluxo complexo com múltiplos kinds; precisa de regressão dedicada |
| `POST /assistant/transcribe` | `assistant.py:1040` | Audio pipeline — precisa whitelist AUDIO + testes |
| `POST /assistant/pdf-pages` | `assistant.py:1582` | PDF-only, directo mas regressão necessária |
| `POST /auth/kyc/*` | `auth.py:478, 496-497` | KYC (kbis+decennale) — crítico, testes legais |
| `POST /btp/*` | `btp_router.py:23` | Lista variável de uploads |
| `POST /company-library/upload` | `company_library.py:69` | Idem |
| `POST /company-page/*` | `company_page.py:*` | Multiple handlers |

**Decisão**: cada endpoint restante leva ~2-5 linhas de alteração + regressão dedicada. Deixo como FOLLOW-UP para iteração dedicada (não arrisco quebrar o KYC agora).

### Testes passados (6/6)

```
test_sanitize_filename_removes_path_traversal           PASSED
test_validate_upload_accepts_png                        PASSED
test_validate_upload_rejects_exe                        PASSED  (application/x-msdownload → 400)
test_validate_upload_rejects_oversized                  PASSED  (25MB vs max_mb=20 → 413)
test_validate_upload_sanitizes_path_traversal_filename  PASSED  ("../../etc/passwd" → "passwd")
test_validate_upload_respects_max_mb_env                PASSED  (MAX_UPLOAD_MB=1 → 2MB rejeitado)
```

---

## Resultados numéricos globais

```
pytest tests/test_lote_x_hardening.py -v
→ 10 passed, 2 warnings in 0.62s

Backend reinicia:                              ✅
Login válido (JWT) continua funcional:         ✅ (teste.pro+e2e → 200)
Admin secundário com password antiga falha:    ✅ (info@construpilot.pt + CP-Admin-2026! → 401 `Email ou palavra-passe incorretos`)
Log "Seed de contas DESLIGADO" presente:       ✅
```

---

## FOLLOW-UPs para o Martinho

1. **ALTA** — eliminar manualmente da BD de produção a conta `info@construpilot.pt` **se ela foi criada em boot anterior com password `CP-Admin-2026!`**. O fail-closed só impede novas criações; não apaga a conta pré-existente. Alternativa: definir `SECOND_ADMIN_PASSWORD` em `.env` prod e forçar `must_change_password: True` manualmente.
2. **MÉDIA** — migrar os 8+ endpoints `UploadFile` restantes para `validate_upload` (lista acima). Cada um precisa de regressão dedicada. Em particular o fluxo KYC (`auth.py:478`) é sensível legalmente.
3. **MÉDIA** — avaliar substituir `application/octet-stream` por detecção magic-bytes para uploads CAD (actualmente aceite por compatibilidade com browsers que não detectam DWG/DXF).
4. **BAIXA** — adicionar `SEED_DEMO_DATA=true` ao `.env` de dev se o Martinho quiser contas E2E reprovisionadas em cada boot (actualmente **DESLIGADO** por defeito, mas as contas persistem na BD).

---

## Regras cumpridas

- GitHub BLOQUEADO: ✅ zero chamadas, zero clones, zero push
- Nenhum deploy: ✅
- `.env` intacto: ✅ (apenas `.env.example` tocado)
- `/app/mobile` intacto: ✅
- supervisor conf intacto: ✅
- PT-PT nos logs novos: ✅ (`"Seed de contas de demonstração %s"`, `"Admin secundário não provisionado: SECOND_ADMIN_PASSWORD não definida"`)
- Commit único temático: ✅ (próximo passo)
