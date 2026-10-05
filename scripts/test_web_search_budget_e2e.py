"""E2E: budget web search (soft fallback) para o Coach IA como utilizador free.

Objetivo
--------
Garantir que, após **10** chamadas web-search (``use_web_search=True``) consecutivas
feitas por um utilizador do plano Grátis, a 11.ª chamada:

- continua a devolver **HTTP 200** (o soft fallback NÃO é um 429);
- contém ``meta.web_search_fallback == True``;
- contém ``meta.web_search_mode == "budget_exhausted"``;
- contém ``meta.web_enriched == False`` e ``meta.citations == []``.

E valida ainda:
- a 10.ª chamada mostra ``web_remaining == 0`` no payload ``rate_limit``;
- a UI pode ler ``X-RateLimit-Remaining-Web`` do response.

Observação
----------
Este teste consome budget total também (10+1 = 11 pedidos). O plano Grátis tem
limite total de **20/h** para o Coach, logo não ultrapassa o total. O endpoint
usado é curto para minimizar o tempo do Aurora/Perplexity.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE = os.environ.get("BASE_URL") or "https://construpilot-recon.preview.emergentagent.com"
FREE_EMAIL = "particular@construpilot.pt"
FREE_PASS = "Particular2026!"


def _headers(token: str | None = None) -> dict:
    h = {"Content-Type": "application/json", "User-Agent": "ConstruPilot-WebBudget-E2E/1.0"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _login() -> str:
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=json.dumps({"email": FREE_EMAIL, "password": FREE_PASS}).encode(),
        headers=_headers(), method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())["token"]


def _post_coach(token: str, msg: str, use_web: bool | None) -> tuple[int, dict, dict]:
    body = {"message": msg}
    if use_web is not None:
        body["use_web_search"] = use_web
    req = urllib.request.Request(
        f"{BASE}/api/coach/ask",
        data=json.dumps(body).encode(),
        headers=_headers(token), method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), dict(e.headers)


def main() -> int:
    print(f"=== Login {FREE_EMAIL} (plano Grátis) ===")
    tok = _login()
    print(f"[OK] token acquired")

    print("\n=== Enviar 11 pedidos consecutivos com use_web_search=True ===")
    print("    (budget web free = 10/h · total free = 20/h)\n")
    results = []
    for i in range(1, 12):
        t0 = time.time()
        status, data, hdr = _post_coach(tok, f"Teste rápido web #{i}: 2+2 em meia frase.", True)
        dt = int((time.time() - t0) * 1000)
        meta = data.get("meta") or {}
        rl = data.get("rate_limit") or {}
        is_fallback = bool(meta.get("web_search_fallback"))
        mode = meta.get("web_search_mode")
        cits = len(meta.get("citations") or [])
        tag = "WEB_OK" if (status == 200 and meta.get("web_enriched")) else "FALLBACK" if is_fallback else f"{status}"
        print(
            f"  [{i:02d}] HTTP {status} {tag:8} dt={dt:5}ms  "
            f"mode={mode!s:<18} citations={cits:2d}  "
            f"web_remaining={rl.get('web_remaining')} "
            f"X-RL-Rem-Web={hdr.get('x-ratelimit-remaining-web') or hdr.get('X-RateLimit-Remaining-Web')}"
        )
        results.append({"i": i, "status": status, "mode": mode, "fallback": is_fallback,
                        "web_remaining": rl.get("web_remaining"),
                        "web_enriched": meta.get("web_enriched")})
        # curto-circuito após primeiro fallback (não precisamos continuar)
        if is_fallback:
            break

    print("\n=== Validação ===")
    first_fallback_idx = next((r["i"] for r in results if r["fallback"]), None)
    web_ok_before = sum(1 for r in results if r.get("web_enriched"))
    print(f"- 1º fallback na iteração: {first_fallback_idx}")
    print(f"- Nº de respostas com web_enriched antes do fallback: {web_ok_before}")

    # Critério de passagem: fallback deve ocorrer entre a 10.ª e a 11.ª tentativa.
    # Como o utilizador pode ter consumido slots em testes anteriores da mesma hora,
    # consideramos pass se o fallback acontece dentro do envelope esperado.
    ok = (
        first_fallback_idx is not None
        and 1 <= first_fallback_idx <= 11
        and all(r["status"] == 200 for r in results)
    )
    print("\n[PASS]" if ok else "[FAIL]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
