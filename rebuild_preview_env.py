#!/usr/bin/env python3
"""Reconstrói /app/backend/.env da PRÉ-VISUALIZAÇÃO a partir de BACKEND_ENV_FULL (uma só linha, pares separados por espaços).
Separa pelos NOMES conhecidos das 116 chaves (na ordem do ficheiro), por isso espaços ou '=' dentro dos valores não estragam nada.
Nunca imprime valores. MONGO_URL / DB_NAME / CORS_ORIGINS forçados para a pré-visualização (Mongo local)."""
import os, re, sys
NAMES = ['ANTHROPIC_API_KEY', 'ELEVENLABS_API_KEY', 'EMERGENT_LLM_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY', 'RESEND_API_KEY', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'ADMIN_E2E_EMAIL', 'ADMIN_E2E_PASSWORD', 'ADMIN_SEED_EMAIL', 'ADMIN_SEED_PASSWORD', 'APP_COUNTRY', 'APP_ORIGIN', 'APS_AUTOMATION_BASE_URL', 'APS_AUTOMATION_REGION', 'APS_TOKEN_URL', 'ASSISTANT_CLAUDE_MODEL_FAST', 'ASSISTANT_CLAUDE_MODEL_THOROUGH', 'ASSISTANT_GEMINI_MODEL_FAST', 'ASSISTANT_GEMINI_MODEL_THOROUGH', 'ASSISTANT_IMAGE_MODEL', 'ASSISTANT_MODEL_FAST', 'ASSISTANT_MODEL_THOROUGH', 'AURORA_BASE_URL', 'AURORA_COMPANY_API_KEY', 'AURORA_COMPANY_SIGNING_SECRET', 'AUTODESK_CALLBACK_URL', 'AUTODESK_CLIENT_ID', 'AUTODESK_CLIENT_SECRET', 'AUTOSEO_WEBHOOK_TOKEN', 'AVATAR_AGENT_KEY', 'CLAUDE_MODEL', 'CLOUDCONVERT_API_BASE', 'CLOUDCONVERT_API_KEY', 'CLOUDCONVERT_SYNC_BASE', 'CLT_PILOT_TENANT_ID', 'CLT_PILOT_USER_ID', 'CLT_REZULT_TEMP_PASSWORD', 'DGT_CDD_PASSWORD', 'DGT_CDD_USER', 'DISABLE_ESLINT_PLUGIN', 'ENTERPRISE_ALERT_EMAIL', 'ENV', 'EUR_USD_RATE', 'EXPO_PACKAGER_PROXY_URL', 'EXPO_PUBLIC_PLACEHOLDER', 'FREE_PROMO_MODE', 'FRONTEND_URL', 'GEMINI_MODEL', 'GEMINI_PROJECT_ID', 'GENERATE_SOURCEMAP', 'GRANT_CSORES_UFP_PASSWORD', 'GRANT_MCPHERSN_PASSWORD', 'GRANT_NEC_ESTG_IPLEIRIA_PASSWORD', 'GRANT_RUI_PASSWORD', 'GRANT_RUI_RUBEN_ULO_PASSWORD', 'GRANT_UBI_PASSWORD', 'HEYCATCH_API_KEY', 'INTEGRATION_PROXY_URL', 'JWT_SECRET', 'LEVELDESIRE_TEMP_PASSWORD', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'LIVEKIT_URL', 'NODE_OPTIONS', 'ODA_FILE_CONVERTER', 'PERPLEXITY_API_KEY', 'POSTAL_ENABLED', 'PRESENTATION_WORK_DIR', 'PROVISION_DAVI_PASSWORD', 'PUBLIC_APP_URL', 'PUBLIC_BACKEND_URL', 'PUBLIC_LINK_TTL_DAYS', 'RADAR_ENABLED', 'RADAR_SOURCES', 'RECEIPT_EMAIL_ENABLED', 'RUNWAYML_API_SECRET', 'RUNWAY_MONTHLY_QUOTA', 'SECOND_ADMIN_EMAIL', 'SECOND_ADMIN_PASSWORD', 'SEED_ADMIN_DEMO_PASSWORD', 'SEED_CLIENT_DEMO_PASSWORD', 'SEED_COLLEGUE_DEMO_PASSWORD', 'SEED_DEMO_DATA', 'SEED_DEMO_PASSWORD', 'SEED_PRO_DEMO_PASSWORD', 'SENDER_EMAIL', 'SENDER_PT_FROM', 'SENDER_PT_NAME', 'SENDER_PT_REPLY', 'SMS_PROVIDER', 'SMS_TO_SENDER_ID', 'STUDIES_MODEL_ANALYSIS', 'STUDIES_MODEL_LIGHT', 'TAVILY_API_KEY', 'TEST_ADMIN_EMAIL', 'TEST_ADMIN_PASSWORD', 'TEST_E2E_BUSINESS_PASSWORD', 'TEST_E2E_PARTICULAR_PASSWORD', 'TEST_E2E_PRO_PASSWORD', 'TEST_PRO_EMAIL', 'TEST_PRO_EMAIL_FR', 'TEST_PRO_PASSWORD_FR', 'TEST_PRO_PASSWORD_PT', 'TIGRIS_ACCESS_KEY_ID', 'TIGRIS_BUCKET', 'TIGRIS_ENDPOINT', 'TIGRIS_SECRET_ACCESS_KEY', 'TOK', 'TWILIO_FROM_NUMBER', 'VAPID_CLAIM_EMAIL', 'VAPID_PRIVATE_KEY', 'VAPID_PUBLIC_KEY', 'WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT', 'WEBSUMMIT_DEMO_PASSWORD_PT']
raw = os.environ.get("BACKEND_ENV_FULL") or (open(sys.argv[1]).read() if len(sys.argv) > 1 else "")
if not raw: sys.exit("ERRO: BACKEND_ENV_FULL vazio")
raw = raw.replace("\r", " ").replace("\n", " ").strip()
pos = []
for k in NAMES:
    m = re.search(r"(?:^|\s)" + re.escape(k) + "=", raw)
    if not m: sys.exit("ERRO: chave em falta no texto colado: " + k)
    pos.append((m.end(), m.start(), k))
pos.sort()
if [p[2] for p in pos] != NAMES: print("AVISO: ordem diferente da esperada (tratado)")
vals = {}
for i, (vstart, _, k) in enumerate(pos):
    vend = pos[i + 1][1] if i + 1 < len(pos) else len(raw)
    v = raw[vstart:vend].strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].replace('\\"', '"')
    vals[k] = v
vals.update({"MONGO_URL": "mongodb://localhost:27017", "DB_NAME": "test_database", "CORS_ORIGINS": ""})
def q(v): return '"' + v.replace('"', '\\"') + '"' if re.search(r'[\s#"\'$]', v) or v == "" else v
out = "/app/backend/.env" if len(sys.argv) < 3 else sys.argv[2]
if os.path.exists(out) and "--force" not in sys.argv: sys.exit("ERRO: " + out + " já existe (usar --force)")
with open(out, "w") as f:
    for k, v in vals.items(): f.write(k + "=" + q(v) + "\n")
os.chmod(out, 0o600)
print("OK:", len(vals), "variáveis escritas em", out)
print("vazias:", [k for k, v in vals.items() if v == "" and k != "CORS_ORIGINS"])
