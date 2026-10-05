"""
Teste OAuth v2 Autodesk APS — Sprint 3 preflight.
NAO imprime credenciais nem access_token.
Reporta: status, scopes, expires_in, token_type.
"""
import os
import sys
import base64
import httpx
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

CLIENT_ID = os.getenv("AUTODESK_CLIENT_ID")
CLIENT_SECRET = os.getenv("AUTODESK_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("[FAIL] Credenciais Autodesk em falta no .env")
    sys.exit(1)

print(f"[INFO] Client ID presente: {len(CLIENT_ID)} chars")
print(f"[INFO] Client Secret presente: {len(CLIENT_SECRET)} chars")

AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"
SCOPES = "data:read data:write data:create bucket:read bucket:create viewables:read"

credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
basic_auth = base64.b64encode(credentials.encode()).decode()

headers = {
    "Authorization": f"Basic {basic_auth}",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}

data = {
    "grant_type": "client_credentials",
    "scope": SCOPES,
}

try:
    response = httpx.post(AUTH_URL, headers=headers, data=data, timeout=30.0)
    print(f"[INFO] HTTP Status: {response.status_code}")

    if response.status_code == 200:
        payload = response.json()
        print(f"[OK] token_type: {payload.get('token_type')}")
        print(f"[OK] expires_in: {payload.get('expires_in')} segundos")
        if payload.get("access_token"):
            print(f"[OK] access_token recebido (len={len(payload['access_token'])}, nao impresso)")
        print(f"[OK] scopes pedidos: {SCOPES}")
        print("[PASS] OAuth v2 Autodesk APS funcional")
        sys.exit(0)
    else:
        try:
            err = response.json()
            print(f"[FAIL] Erro: {err.get('error')} - {err.get('error_description', 'sem detalhe')}")
        except Exception:
            print(f"[FAIL] Resposta: {response.text[:200]}")
        sys.exit(2)
except httpx.HTTPError as e:
    print(f"[FAIL] HTTP error: {type(e).__name__}: {e}")
    sys.exit(3)
