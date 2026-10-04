"""E2E rápido do /api/btp-solver/* (chama LLM real · ~ 30-40 s)."""
import json
import os
import time

import requests

BASE = os.environ.get("BASE_URL", "https://construpilot-recon.preview.emergentagent.com")
EMAIL = os.environ.get("TEST_EMAIL", "info@construpilot.pt")
PASSWORD = os.environ.get("TEST_PASSWORD", "uFuBb6Q5h1QUxCmc")


def _login():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def main():
    token = _login()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("[1] POST /api/btp-solver/solve …")
    t0 = time.time()
    r = requests.post(
        f"{BASE}/api/btp-solver/solve",
        headers=headers,
        json={
            "description": "Fissura diagonal numa parede exterior de alvenaria dupla de uma moradia construída em 1985 na zona do Porto. Fissura visível há 2 meses, acentua-se após chuva prolongada.",
            "tipo_edificio": "moradia unifamiliar",
            "region": "Porto",
            "idade_anos": 40,
        },
        timeout=120,
    )
    dur = time.time() - t0
    r.raise_for_status()
    d = r.json()
    assert d["problem_id"].startswith("bps_"), f"problem_id inválido: {d.get('problem_id')}"
    assert d["model_used"], "model_used ausente"
    print(f"    ✓ problem_id={d['problem_id']} model={d['model_used']} dur={dur:.1f}s")
    print(f"    domain={d['domain']} · urgency={d['urgency']} · web_enriched={d.get('web_enriched')}")
    print(f"    causes={len(d.get('causes',[]))} · solutions={len(d.get('solutions',[]))} · charts={len(d.get('charts',[]))}")
    assert d["summary"], "summary vazio"
    assert d["disclaimer"].startswith("Diagnóstico provisório"), f"disclaimer errado: {d['disclaimer'][:60]}"
    # Verificar que soluções têm estrutura mínima
    for s in d.get("solutions", []):
        assert s["id"], "solução sem id"
        assert s["label"], "solução sem label"
        assert s["risk"] in ("low", "medium", "high", "critical")

    print("[2] GET /api/btp-solver/history …")
    r2 = requests.get(f"{BASE}/api/btp-solver/history?limit=5", headers=headers, timeout=15)
    r2.raise_for_status()
    items = r2.json().get("items") or []
    ids = [it.get("problem_id") for it in items]
    print(f"    ✓ history_count={len(items)} · contains_new={d['problem_id'] in ids}")
    assert d["problem_id"] in ids, "a nova análise não aparece no histórico"

    print("[3] GET /api/btp-solver/{id} …")
    r3 = requests.get(f"{BASE}/api/btp-solver/{d['problem_id']}", headers=headers, timeout=15)
    r3.raise_for_status()
    detail = r3.json()
    assert detail["problem_id"] == d["problem_id"]
    print(f"    ✓ detalhe retornado com {len(detail.get('charts',[]))} charts e {len(detail.get('action_plan',[]))} passos")

    print("\n✅ E2E btp-solver OK")


if __name__ == "__main__":
    main()
