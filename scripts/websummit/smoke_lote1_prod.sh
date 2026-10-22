#!/usr/bin/env bash
# Smoke LOTE 1 em prod `construpilot.pt` após "deploy on" (clique manual do fundador).
# Chamar quando se detectar deploy; não bloqueia 2b/2c/2d em curso.
# Zero credenciais em claro: lê de env.
set -u

PROD_URL="${PROD_URL:-https://construpilot.pt}"
DEMO_PRO_EMAIL="${WEBSUMMIT_DEMO_EMAIL_PT:-demo.websummit@construpilot.pt}"
DEMO_PRO_PWD="${WEBSUMMIT_DEMO_PASSWORD_PT:-}"
DEMO_PART_EMAIL="${WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT:-demo.websummit.particular@construpilot.pt}"
DEMO_PART_PWD="${WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT:-}"

echo "== Smoke LOTE 1 em prod ($PROD_URL) =="

echo "[1/3] /api/health"
H=$(curl -s -o /dev/null -w "%{http_code}" "$PROD_URL/api/health")
[ "$H" = "200" ] && echo "  OK ($H)" || { echo "  FAIL ($H)"; exit 1; }

_login_and_check () {
  local LABEL="$1"; local EMAIL="$2"; local PWD="$3"
  if [ -z "$PWD" ]; then
    echo "[$LABEL] skipped (password em falta no env)"
    return 0
  fi
  echo "[$LABEL] login + GET Moradia Martins"
  TOKEN=$(curl -s -X POST "$PROD_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PWD\"}" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('token') or d.get('access_token') or '')" 2>/dev/null)
  if [ -z "$TOKEN" ]; then echo "  FAIL (token vazio)"; return 1; fi
  PROJECTS=$(curl -s -H "Authorization: Bearer $TOKEN" "$PROD_URL/api/projects")
  MM_ID=$(echo "$PROJECTS" | python3 -c "import sys,json;ps=json.load(sys.stdin);print(next((p['project_id'] for p in (ps if isinstance(ps,list) else ps.get('projects',[])) if p.get('name')=='Moradia Martins'),''))" 2>/dev/null)
  if [ -z "$MM_ID" ]; then echo "  FAIL (Moradia Martins não encontrada)"; return 1; fi
  P=$(curl -s -H "Authorization: Bearer $TOKEN" "$PROD_URL/api/projects/$MM_ID")
  python3 - <<PY
import sys, json
p = json.loads('''$P''')
est = p.get('estimation') or {}
src = est.get('source','')
total = est.get('total_avg', 0)
n = len(est.get('lots') or [])
assert est, "estimation ausente"
assert src.startswith('engines.estimation.'), f"source errada: {src!r}"
assert total > 0, f"total_avg={total}"
assert n >= 10, f"lots={n}"
print(f"  OK (total €{total:,.2f}, {n} lotes, source={src})")
PY
}

_login_and_check "2/3 demo pro"       "$DEMO_PRO_EMAIL"  "$DEMO_PRO_PWD"  || exit 1
_login_and_check "3/3 demo particular" "$DEMO_PART_EMAIL" "$DEMO_PART_PWD" || exit 1

echo "== Smoke LOTE 1 ✅ =="
