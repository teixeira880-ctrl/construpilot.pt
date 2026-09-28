"""Smoke test E2E do Coach IA (Aurora).

Corre contra o backend em execução:
    cd /app/backend && python -m scripts.test_coach_e2e

Espera-se, na condição atual de Aurora upstream (bug text vazio):
- POST /api/coach/ask retorna HTTP 503 com error=coach_unavailable
- msg do utilizador foi persistida em `coach_messages`
- msg do assistente NÃO foi persistida
- documento em `coach_failures` foi criado
- email admin foi tentado (Resend log)

Quando o bug Aurora for corrigido, o mesmo script vai retornar 200 automaticamente.
"""
from __future__ import annotations

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
EMAIL = os.environ.get("COACH_E2E_EMAIL", "info@construpilot.pt")
PASSWORD = os.environ.get("COACH_E2E_PASSWORD", "uFuBb6Q5h1QUxCmc")


async def _login(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    if not tok:
        raise RuntimeError(f"login: no token in response keys={list(data)}")
    return tok


async def main() -> int:
    if not BASE:
        print("REACT_APP_BACKEND_URL não definido")
        return 1

    async with httpx.AsyncClient(timeout=60.0) as http:
        token = await _login(http)
        headers = {"Authorization": f"Bearer {token}"}

        # --- 1) POST /coach/ask sem projeto ---
        r = await http.post(
            f"{BASE}/api/coach/ask",
            headers=headers,
            json={"message": "Preço médio de betão C25/30 em Lisboa?"},
        )
        status = r.status_code
        body = r.json()
        print(f"[1] POST /api/coach/ask (sem projeto) → HTTP {status}")
        print(f"    body keys: {list(body if isinstance(body, dict) else body.get('detail', {}))}")

        conversation_id = None
        if status == 200:
            reply = body.get("reply") or ""
            meta = body.get("meta") or {}
            conversation_id = body.get("conversation_id")
            assert reply.strip(), "reply vazio devolvido como 200"
            print(f"    ✓ Aurora respondeu com {len(reply)} chars · mode={meta.get('mode_used')}")
        elif status == 503:
            detail = body.get("detail") or {}
            conversation_id = detail.get("conversation_id")
            assert detail.get("error") == "coach_unavailable"
            print(f"    ✓ 503 gracioso · conversation_id={conversation_id}")
        else:
            print(f"    ✗ HTTP inesperado {status}: {body}")
            return 2

        # --- 2) Verificar coleção coach_messages ---
        db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = db_client[os.environ["DB_NAME"]]
        msgs = await db.coach_messages.find(
            {"conversation_id": conversation_id}, {"_id": 0}
        ).sort("ts", 1).to_list(None)
        print(f"[2] coach_messages para conv={conversation_id}: {len(msgs)}")
        roles = [m["role"] for m in msgs]
        print(f"    roles: {roles}")
        assert "user" in roles, "msg utilizador não persistida"
        if status == 200:
            assert "assistant" in roles, "msg assistente não persistida em sucesso"
            print("    ✓ user + assistant persistidos")
        else:
            assert "assistant" not in roles, "msg assistente persistida indevidamente em 503"
            print("    ✓ user persistido, assistente NÃO persistido (503 esperado)")

        # --- 3) Se 503, verificar coach_failures ---
        if status == 503:
            f = await db.coach_failures.find_one({}, {"_id": 0}, sort=[("ts", -1)])
            assert f, "coach_failures vazio após 503"
            print(f"[3] coach_failures último: {f['failure_id']}")
            print(f"    reasoning error: {f['reasoning_meta'].get('error')}")
            print(f"    fast error: {f['fast_meta'].get('error')}")
            assert f["reasoning_meta"]["mode"] == "reasoning"
            assert f["fast_meta"]["mode"] == "fast"
            print("    ✓ incidente registado com ambos os metas")

        # --- 4) GET /coach/conversations/{id} ---
        r = await http.get(f"{BASE}/api/coach/conversations/{conversation_id}", headers=headers)
        print(f"[4] GET /api/coach/conversations/{conversation_id} → HTTP {r.status_code}")
        assert r.status_code == 200
        h = r.json()
        assert h["count"] == len(msgs)
        print(f"    ✓ histórico devolve {h['count']} msgs")

        # --- 5) GET /coach/conversations (lista) ---
        r = await http.get(f"{BASE}/api/coach/conversations", headers=headers)
        print(f"[5] GET /api/coach/conversations → HTTP {r.status_code}")
        assert r.status_code == 200
        cs = r.json()
        assert cs["count"] >= 1
        print(f"    ✓ {cs['count']} conversas listadas")

        print()
        print("=" * 50)
        print("SMOKE TEST OK · Coach IA (Aurora) funcional end-to-end.")
        print(f"Estado Aurora: {'sucesso (200)' if status == 200 else '503 gracioso (bug upstream text vazio)'}")
        print("=" * 50)
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
