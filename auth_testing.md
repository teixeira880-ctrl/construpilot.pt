# Auth Testing Playbook (Emergent Google OAuth)

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
