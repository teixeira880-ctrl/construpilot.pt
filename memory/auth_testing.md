# Auth Testing Playbook (Emergent Google OAuth)

> **Contrato de credenciais (actualizado 2026-10-17)**: todas as credenciais de contas reais vivem apenas em `/app/backend/.env`. O documento `/app/memory/test_credentials.md` lista os emails + **nomes de variáveis**, nunca valores. Em qualquer teste (Python/Node/curl), ler via `os.environ.get(...)` / `process.env.*` e abortar com código 2 se a variável estiver vazia ou com placeholder `<redacted>`. Zero fallback hardcoded.

> Para fluxos OAuth Google (mock de sessão), este documento mantém o template Mongo abaixo — os `session_token` gerados aqui são **sintéticos** (via `Date.now()`), não são credenciais reais.

NOTE - Do not be satisfied until you've tested the app completely especially the auth gated pages

## Step 1: Create Test User & Session
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
(Note ConstruPilot : la base est celle de MONGO_URL/DB_NAME du backend/.env — utiliser use('<DB_NAME>')).

## Step 2: Test Backend API
curl -X GET "https://your-app.com/api/auth/me" -H "Authorization: Bearer YOUR_SESSION_TOKEN"
curl -X GET "https://your-app.com/api/pc/dashboard" -H "Authorization: Bearer YOUR_SESSION_TOKEN"

## Step 3: Browser Testing
await page.context.add_cookies([{
    "name": "session_token",
    "value": "YOUR_SESSION_TOKEN",
    "domain": "your-app.com",
    "path": "/",
    "httpOnly": true,
    "secure": true,
    "sameSite": "None"
}]);
await page.goto("https://your-app.com/dashboard");
Note ConstruPilot : le front vérifie localStorage('construpilot_token') OU le hash — pour le test cookie-only,
ajouter aussi localStorage.setItem('construpilot_token', SESSION_TOKEN) via add_init_script,
car le cookie httpOnly n'est pas lisible par JS et l'AuthProvider saute le /auth/me sans indice de connexion.

## Quick Debug
mongosh --eval "use('<DB_NAME>'); db.users.find().limit(2).pretty(); db.user_sessions.find().limit(2).pretty();"
mongosh --eval "use('<DB_NAME>'); db.users.deleteMany({email: /test\\.user\\./}); db.user_sessions.deleteMany({session_token: /test_session/});"

## Checklist
- User document has user_id field (custom UUID)
- Session user_id matches user's user_id exactly
- All queries use {"_id": 0} projection
- API returns user data with user_id field (not 401/404)
- Browser loads dashboard (not login page)
- Callback detection uses useLocation().hash

## Success Indicators
- /api/auth/me returns user data
- Dashboard loads without redirect
- CRUD operations work

## Failure Indicators
- "User not found" errors
- 401 Unauthorized responses
- Redirect to login page

## ConstruPilot specifics
- Bouton Google : data-testid="google-login-btn" sur /login (redirige vers https://auth.emergentagent.com/?redirect={origin}/dashboard)
- Échange session : POST /api/auth/session (header X-Session-ID ou body {session_id}) → cookie httpOnly session_token + user fusionné par email (auth_provider: google)
- current_user : cookie session_token d'abord, puis Bearer (session OU JWT legacy)
- Logout : POST /api/auth/logout supprime la session DB + le cookie

---

## Web Summit demo (`.pt` only) — como testar sem credenciais reais

Adicionado 2026-10-17. Fluxo público para visitantes do stand entrarem com 1 clique.

### Verificação da configuração (sem credenciais)

```bash
curl https://construpilot.pt/api/auth/demo-status
# → {"pro": true, "particular": true}  se segredos configurados
# → {"pro": false, "particular": false} se segredos em falta (fail-closed)
```

### Login demo (sem credenciais no cliente)

```bash
# Pro
curl -X POST https://construpilot.pt/api/auth/demo-login \
  -H "Content-Type: application/json" \
  -d '{"kind":"pro"}' \
  -c /tmp/cookies.txt
# Particular
curl -X POST https://construpilot.pt/api/auth/demo-login \
  -H "Content-Type: application/json" \
  -d '{"kind":"particular"}' \
  -c /tmp/cookies.txt
```

Response body nunca contém password nem `password_hash`. Validação:

```bash
curl -s -X POST https://construpilot.pt/api/auth/demo-login \
  -H "Content-Type: application/json" -d '{"kind":"pro"}' | \
  grep -ciE "password_hash|password\":"
# → 0
```

### Validar bloqueios de modo demo

Após login demo (cookie em `/tmp/cookies.txt`), tentar envio:

```bash
# Envio de documento → esperado 403
curl -b /tmp/cookies.txt -X POST \
  https://construpilot.pt/api/documents/fakeid/send \
  -H "Content-Type: application/json" -d '{}'
# → 403 {"error":"demo_blocked","action":"send_document"}

# Change password → esperado 403
curl -b /tmp/cookies.txt -X POST \
  https://construpilot.pt/api/auth/change-password \
  -H "Content-Type: application/json" \
  -d '{"current_password":"x","new_password":"y"}'
# → 403 {"error":"demo_blocked","action":"change_password"}
```

### Rate limit (10 pedidos/minuto/IP)

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    https://construpilot.pt/api/auth/demo-login \
    -H "Content-Type: application/json" -d '{"kind":"pro"}'
done
# → últimos pedidos devolvem 429
```

### Checklist completa para testing agent

1. `GET /api/auth/demo-status` → ambos `true` em prod.
2. `POST /api/auth/demo-login {kind:"pro"}` → 200, cookie HttpOnly, body sem password.
3. `POST /api/documents/x/send` com cookie demo → 403 `demo_blocked`.
4. `POST /api/auth/change-password` com cookie demo → 403 `demo_blocked`.
5. `POST /api/auth/demo-login` 12 vezes seguidas → últimos retornam 429.
6. `GET /api/auth/me` com cookie demo → 200, `user.is_demo: true`.
7. UI `/demo/entrar` carrega e mostra 2 CTAs (Pro + Particular).
8. UI `/login` mostra bloco `demo-login-block` com 2 botões.

**Nunca** usar valores em claro de passwords demo em comandos ou logs do testing agent. Cookie e response são suficientes para validar o fluxo end-to-end.
