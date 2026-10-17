"""E2E rate-limit test: 21 Coach requests as free user → 20 OK + 1 × 429.

Usage: python scripts/test_particulares_rate_limit.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request


BASE = os.environ.get("BASE_URL") or "https://construpilot-recon.preview.emergentagent.com"
FREE_EMAIL = os.environ.get("TEST_PARTICULAR_EMAIL", "particular@construpilot.pt")
FREE_PASS = (os.environ.get("TEST_PARTICULAR_PASSWORD") or "").strip()
if not FREE_PASS or FREE_PASS == "<redacted>":
    raise SystemExit("TEST_PARTICULAR_PASSWORD ausente/placeholder. Abort.")


def _common_headers():
    return {
        "Content-Type": "application/json",
        "User-Agent": "ConstruPilot-E2E-Test/1.0",
    }


def login(email: str, password: str) -> str:
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers=_common_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return data["token"]


def post_coach(token: str, msg: str) -> tuple[int, dict]:
    body = json.dumps({"message": msg}).encode()
    headers = _common_headers()
    headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE}/api/coach/ask",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    print(f"=== Login free user {FREE_EMAIL} ===")
    token = login(FREE_EMAIL, FREE_PASS)
    print(f"[OK] token acquired ({token[:12]}…)")

    print("\n=== Enviar 21 pedidos consecutivos ao Coach (limite free=20/h) ===")
    results = []
    for i in range(1, 22):
        t0 = time.time()
        status, data = post_coach(token, f"Pergunta curta {i}: 2+2=? Responde só com um número.")
        dt = int((time.time() - t0) * 1000)
        tag = "OK" if status == 200 else "RL" if status == 429 else "ER"
        plan = data.get("current_plan") if status == 429 else None
        results.append((i, status, tag, plan, dt))
        print(f"  [{i:02d}] HTTP {status} {tag} dt={dt}ms{'  plan='+str(plan) if plan else ''}")
        if status == 429:
            print(f"       → message: {data.get('message','')[:140]}")
            print(f"       → upgrade_url: {data.get('upgrade_url')}  current_plan: {data.get('current_plan')}")
            print(f"       → retry_after_seconds: {data.get('retry_after_seconds')}")
            break

    ok = sum(1 for _, s, *_ in results if s == 200)
    rl = sum(1 for _, s, *_ in results if s == 429)
    print(f"\n[SUMMARY] {ok} OK / {rl} rate-limited")
    print("[PASS]" if ok == 20 and rl == 1 and results[-1][3] == "free" else "[FAIL]")
    return 0 if (ok == 20 and rl == 1) else 1


if __name__ == "__main__":
    sys.exit(main())
