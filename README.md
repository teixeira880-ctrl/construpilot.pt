# ConstruPilot — Bundle Sprint 0 + Perplexity+

Ce bundle contient **28 fichiers** (créés ou modifiés) qui appliquent :

1. **Sprint 0 sécurité** — 4 correctifs critiques identifiés dans `AUDIT.md`
2. **Extension Perplexity** — 4 nouvelles routes IA (chat SSE, réglementation, devis, CCTP) avec cache 24 h

Aucun autre fichier de votre code n'est touché. Décompressez le zip **à la racine du dépôt** en écrasant les fichiers existants, puis suivez les 6 étapes ci-dessous.

---

## Étapes d'application

### 1. Extraire à la racine du dépôt
```bash
cd /path/to/construpilot.fr
unzip -o construpilot-sprint0-bundle.zip
```

Vérifiez qu'aucun `.token.txt / .adm_token.txt / .pro_token.txt` ne subsiste :
```bash
ls -la .token.txt .adm_token.txt .pro_token.txt 2>/dev/null || echo "OK : aucun token en clair"
```

Si un fichier subsiste (venu de votre copie locale), supprimez-le : `rm -f .token.txt .adm_token.txt .pro_token.txt`

### 2. Installer la dépendance backend ajoutée
```bash
cd backend
pip install -r requirements.txt   # ajoute slowapi==0.1.9
```

### 3. Créer le `.env` à partir du template
```bash
cp backend/.env.example backend/.env
# Renseigner MONGO_URL, JWT_SECRET, CORS_ORIGINS, PERPLEXITY_API_KEY, etc.
```

**Important** : régénérez `JWT_SECRET` (rotation recommandée après la fuite) :
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Révoquer les tokens fuités
```bash
cd backend
python -m scripts.revoke_leaked_tokens
```

Cela incrémente `token_version` sur les 3 comptes concernés et purge leurs sessions.

### 5. Purger l'historique Git (si le repo a été poussé sur Git)
```bash
pip install git-filter-repo
git filter-repo --path .token.txt --path .adm_token.txt --path .pro_token.txt --invert-paths
git push --force-with-lease --all
```

### 6. Redémarrer et tester
```bash
# Backend
uvicorn server:app --reload --port 8000

# Frontend
cd ../frontend
npm install   # aucune nouvelle dépendance mais reproduit le lock
npm start
```

Vérifiez :
- ✅ Un login puis un rechargement de page : l'utilisateur est toujours connecté (cookie httpOnly)
- ✅ `curl -X POST http://localhost:8000/api/auth/login` répété 11 fois → 429 sur le 11e (rate limit)
- ✅ `GET /api/pplx/status` (avec cookie de session) → `{"configured": true, ...}`
- ✅ `POST /api/pplx/chat` en SSE renvoie des chunks `data: {"type":"delta","text":"..."}`

---

## Fichiers du bundle

### Nouveaux fichiers (7)
| Fichier | Rôle |
|---|---|
| `backend/core/rate_limit.py` | Limiteur global slowapi |
| `backend/perplexity_plus/__init__.py` | Module extension Perplexity |
| `backend/perplexity_plus/client.py` | Client + cache Mongo 24 h + streaming |
| `backend/perplexity_plus/routes.py` | 4 endpoints `/api/pplx/*` |
| `backend/scripts/revoke_leaked_tokens.py` | Script révocation JWT fuités |
| `backend/.env.example` | Template des variables d'environnement |
| `AUDIT.md` | Rapport d'audit complet |

### Fichiers modifiés (21)
- Backend (5) : `server.py`, `routes/auth.py`, `routes/ai_routes.py`, `btp_ai/routes.py`, `requirements.txt`
- Frontend (15) : `lib/api.js` + `context/AuthContext.jsx` + 13 fichiers nettoyés du JWT localStorage
- Racine (1) : `.gitignore` (ajout `*.token.txt`, `*.pem`, `*.key`)

---

## Endpoints Perplexity+ ajoutés

| Endpoint | Description | Rate limit |
|---|---|---|
| `POST /api/pplx/chat` | Assistant BTP conversationnel, streaming SSE, citations | 20/min |
| `POST /api/pplx/reglementation` | Recherche filtrée Legifrance/AFNOR/CSTB/RE2020 | 15/h |
| `POST /api/pplx/documents/devis` | Devis JSON structuré avec prix sourcés | 10/h |
| `POST /api/pplx/documents/cctp` | Article CCTP référencé DTU/NF/EN | 10/h |
| `GET /api/pplx/status` | Health check | — |

Tous exigent une auth (cookie de session), utilisent le SDK `perplexityai` **déjà présent** dans vos requirements, et bénéficient d'un cache Mongo TTL 24 h automatique.

---

## Rollback

En cas de problème, tous les fichiers modifiés sont récupérables via `git`:
```bash
git checkout HEAD~1 -- backend/server.py backend/routes/auth.py backend/routes/ai_routes.py backend/btp_ai/routes.py backend/requirements.txt frontend/src
```

Les fichiers **créés** peuvent être supprimés sans effet de bord :
```bash
rm -rf backend/core/rate_limit.py backend/perplexity_plus backend/scripts/revoke_leaked_tokens.py
```

Et dans `server.py`, retirer les 3 imports `slowapi` + les 3 lignes `app.state.limiter / add_exception_handler / add_middleware` — le tour est joué.
