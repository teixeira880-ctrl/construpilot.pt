# Prompt à coller dans Emergent

Copie-colle le bloc ci-dessous dans Emergent, puis attache le zip `construpilot-sprint0-bundle.zip`.

---

## Contexte

Tu travailles sur **ConstruPilot** (SaaS BTP FR — FastAPI + MongoDB + React CRA).
Je viens de faire auditer le code par un audit externe (voir `AUDIT.md` dans le zip). L'audit a remonté **4 problèmes critiques de sécurité** et propose une extension de l'intégration Perplexity existante.

Le zip joint contient **28 fichiers déjà patchés** (créés ou modifiés) qui appliquent l'intégralité du Sprint 0 sécurité + un nouveau module `perplexity_plus`. Aucun autre fichier de mon code ne doit être touché.

## Ce que tu dois faire

### Étape 1 — Extraction
Décompresse le zip **à la racine du dépôt** en écrasant les fichiers existants (28 fichiers). Vérifie ensuite qu'il n'y a **plus aucun** de ces fichiers à la racine du dépôt :
- `.token.txt`
- `.adm_token.txt`
- `.pro_token.txt`

S'il en reste un, supprime-le.

### Étape 2 — Dépendance backend
Dans `backend/requirements.txt` la ligne `slowapi==0.1.9` a été ajoutée. Exécute :
```bash
cd backend && pip install -r requirements.txt
```

### Étape 3 — Variables d'environnement
Un fichier `backend/.env.example` a été livré. Compare-le avec mon `backend/.env` actuel : **ajoute** toute variable manquante et **régénère `JWT_SECRET`** (fuite = rotation obligatoire) :
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Vérifie que `PERPLEXITY_API_KEY` est bien défini (obligatoire pour les nouveaux endpoints).

### Étape 4 — Révocation des tokens fuités
Exécute le script fourni :
```bash
cd backend && python -m scripts.revoke_leaked_tokens
```
Il incrémente `token_version` sur 3 comptes et purge leurs sessions. Résultat attendu : les 3 JWT fuités ne fonctionnent plus.

### Étape 5 — Git : purge de l'historique
Si le dépôt a déjà été poussé sur GitHub/GitLab, purge l'historique des tokens :
```bash
pip install git-filter-repo
git filter-repo --path .token.txt --path .adm_token.txt --path .pro_token.txt --invert-paths
git push --force-with-lease --all
```
Puis effectue un commit propre :
```bash
git add -A
git commit -m "security(sprint0): rate limiting, JWT en cookie only, extension Perplexity+"
git push
```

### Étape 6 — Vérifications automatiques
Lance mon serveur et fais tourner ces smoke tests. Rapporte le résultat de **chacun** :

**A. Backend démarre sans erreur**
```bash
cd backend && uvicorn server:app --reload --port 8000
```
Attendu : aucune exception au startup, log `perplexity_plus index skipped` **absent** (l'index cache doit se créer).

**B. Rate limit auth actif**
```bash
for i in {1..11}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@test.fr","password":"x"}'
done
```
Attendu : dix `400` ou `401`, puis un `429` au 11e appel.

**C. Endpoint Perplexity status**
```bash
curl -s http://localhost:8000/api/pplx/status -b "session_token=<TON_COOKIE>"
```
Attendu : `{"configured": true, "endpoints": [...]}`.

**D. Chat Perplexity streamé**
```bash
curl -N -s http://localhost:8000/api/pplx/chat \
  -b "session_token=<TON_COOKIE>" \
  -H "Content-Type: application/json" \
  -d '{"message":"quel DTU pour un mur en parpaings"}'
```
Attendu : des lignes `data: {"type":"delta","text":"..."}` en flux, puis `data: {"type":"citations","citations":[...]}`, puis `data: {"type":"done",...}`.

**E. Front : cookie only**
1. Lance `cd frontend && npm start`
2. Connecte-toi via l'UI
3. Ouvre la console navigateur → `localStorage.getItem("construpilot_token")` → **doit renvoyer `null`**
4. Recharge la page → l'utilisateur reste connecté (via le cookie `session_token`)

**F. Vérification exhaustive : aucun `construpilot_token` dans le front**
```bash
grep -rn 'construpilot_token' frontend/src/
```
Attendu : **une seule occurrence** dans `context/AuthContext.jsx` (le `localStorage.removeItem` de cleanup legacy).

### Étape 7 — Tests existants
Fais tourner ma suite de tests backend :
```bash
cd backend && python -m pytest tests/ -x -q
```
Rapporte-moi les tests qui échouent (s'il y en a) — normalement rien ne devrait casser puisque le cookie httpOnly était déjà en place, seul l'usage du token localStorage change côté front.

Si un test d'auth échoue parce qu'il lisait `data.token` dans la réponse, adapte-le pour utiliser le cookie renvoyé à la place.

### Étape 8 — Frontend : rebuild
```bash
cd frontend && npm run build
```
Attendu : build réussi, aucun warning bloquant.

---

## Livrable attendu de ta part

Un message qui contient, dans l'ordre :

1. La liste des 28 fichiers touchés (confirmation qu'ils sont bien en place).
2. Le résultat de chacun des 6 tests A → F (avec les logs / codes HTTP réels).
3. Le résultat de `pytest tests/` (nombre de tests passés / échoués + le nom des échecs éventuels).
4. Une capture ou le contenu de mon nouveau `.env` (redacted) pour confirmer que `JWT_SECRET` a bien été régénéré.
5. La confirmation que le git push force-with-lease s'est bien passé (ou l'explication si le repo n'est pas sur Git).

Si l'un des tests échoue, **n'essaie pas de tout réécrire** : arrête-toi, dis-moi précisément ce qui a échoué, et propose UNE correction ciblée. On avance étape par étape.

---

## Notes importantes

- **Ne touche à AUCUN autre fichier** que ceux du bundle. Le zip a été calibré pour ne rien casser.
- Si tu penses qu'un correctif supplémentaire est nécessaire (ex : tests à adapter), demande avant de modifier.
- Les 4 nouveaux endpoints `/api/pplx/*` ne remplacent pas mes routes `/api/btp-ai/*` existantes — ils viennent **en plus**. Aucun code existant n'est cassé.
- Le module `perplexity_plus` n'a pas de dépendance nouvelle : il utilise le SDK `perplexityai==0.43.5` déjà dans `requirements.txt`.
- Le cache Perplexity est en Mongo (collection `perplexity_cache`, TTL 24 h auto).

Vas-y.
