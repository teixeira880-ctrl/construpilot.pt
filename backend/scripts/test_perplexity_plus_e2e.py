"""E2E Perplexity Plus — chama os 4 endpoints com queries reais."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API = os.environ.get("REACT_APP_BACKEND_URL") or "https://construpilot-recon.preview.emergentagent.com"
EMAIL = "info@construpilot.pt"
PASSWORD = "uFuBb6Q5h1QUxCmc"


async def main():
    results = {"endpoints": {}}
    async with httpx.AsyncClient(timeout=120.0) as client:
        print("[STEP] Login…")
        r = await client.post(f"{API}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            print("[FAIL] login", r.status_code)
            return 1
        token = r.json()["token"]
        H = {"Authorization": f"Bearer {token}"}
        print(f"[OK] token acquired")

        # 1. Presets
        r = await client.get(f"{API}/api/perplexity-plus/presets", headers=H)
        presets_ok = r.status_code == 200 and len(r.json()["presets"]) == 5
        results["endpoints"]["presets"] = {"status": r.status_code, "ok": presets_ok}
        print(f"[{'OK' if presets_ok else 'FAIL'}] /presets → 5 presets" if presets_ok else f"[FAIL] /presets {r.status_code}")

        # 2. Norms (preset LNEC)
        print("\n[STEP] /norms LNEC — espessura isolamento parede exterior…")
        t0 = time.time()
        r = await client.post(
            f"{API}/api/perplexity-plus/norms",
            headers={**H, "Content-Type": "application/json"},
            json={"query": "espessura mínima de isolamento térmico em parede exterior zona climática I2", "preset": "LNEC"},
        )
        dt = time.time() - t0
        ok = r.status_code == 200
        if ok:
            d = r.json()
            parsed = d.get("parsed") or {}
            cache = d.get("cache")
            cites = len(d.get("citations") or [])
            normas = len(parsed.get("normas") or [])
            resposta_len = len(parsed.get("resposta_textual") or "")
            print(f"[OK] /norms {dt:.1f}s cache={cache} normas={normas} citations={cites} resposta_len={resposta_len}")
            results["endpoints"]["norms"] = {"ok": True, "cache": cache, "normas": normas, "citations": cites, "duration_s": round(dt, 1)}
        else:
            print(f"[FAIL] /norms {r.status_code} {r.text[:200]}")
            results["endpoints"]["norms"] = {"ok": False}

        # 3. Compare
        print("\n[STEP] /compare betão vs ETICS vs tijolo-face…")
        t0 = time.time()
        r = await client.post(
            f"{API}/api/perplexity-plus/compare",
            headers={**H, "Content-Type": "application/json"},
            json={
                "items": ["ETICS com EPS", "Fachada ventilada com rockwool", "Alvenaria dupla com caixa-de-ar"],
                "criteria": ["desempenho térmico", "custo", "durabilidade"],
                "context": "Moradia T3 em Lisboa, orçamento médio",
            },
        )
        dt = time.time() - t0
        ok = r.status_code == 200
        if ok:
            d = r.json()
            parsed = d.get("parsed") or {}
            cache = d.get("cache")
            scores = parsed.get("scores") or []
            rec = (parsed.get("recomendado") or {}).get("item")
            print(f"[OK] /compare {dt:.1f}s cache={cache} scores_rows={len(scores)} recomendado='{rec}'")
            results["endpoints"]["compare"] = {"ok": True, "cache": cache, "recomendado": rec, "duration_s": round(dt, 1)}
        else:
            print(f"[FAIL] /compare {r.status_code} {r.text[:200]}")
            results["endpoints"]["compare"] = {"ok": False}

        # 4. Materials Watch
        print("\n[STEP] /materials-watch betão + aço + cimento (Lisboa)…")
        t0 = time.time()
        r = await client.post(
            f"{API}/api/perplexity-plus/materials-watch",
            headers={**H, "Content-Type": "application/json"},
            json={
                "materials": ["Betão C25/30", "Aço A500 NR", "Cimento Portland CEM II"],
                "region": "Lisboa",
            },
        )
        dt = time.time() - t0
        ok = r.status_code == 200
        if ok:
            d = r.json()
            parsed = d.get("parsed") or {}
            cache = d.get("cache")
            mats = parsed.get("materiais") or []
            print(f"[OK] /materials-watch {dt:.1f}s cache={cache} materiais={len(mats)}")
            for m in mats[:3]:
                print(f"     - {m.get('nome')}: {m.get('preco_estimado_eur')} €/{m.get('unidade')} ({m.get('tendencia')})")
            results["endpoints"]["materials-watch"] = {"ok": True, "cache": cache, "materiais": len(mats), "duration_s": round(dt, 1)}
        else:
            print(f"[FAIL] /materials-watch {r.status_code} {r.text[:200]}")
            results["endpoints"]["materials-watch"] = {"ok": False}

        # 5. Cache HIT test — repetir query 2 do norms
        print("\n[STEP] /norms (repetido) — testar cache HIT…")
        t0 = time.time()
        r = await client.post(
            f"{API}/api/perplexity-plus/norms",
            headers={**H, "Content-Type": "application/json"},
            json={"query": "espessura mínima de isolamento térmico em parede exterior zona climática I2", "preset": "LNEC"},
        )
        dt = time.time() - t0
        if r.status_code == 200:
            d = r.json()
            cache = d.get("cache")
            print(f"[{'OK' if cache == 'HIT' else 'WARN'}] cache={cache} em {dt:.2f}s (esperado HIT < 1s)")
            results["cache_test"] = {"second_call_cache": cache, "duration_s": round(dt, 2)}
        else:
            results["cache_test"] = {"failed": r.status_code}

        # 6. Chat SSE (quick check)
        print("\n[STEP] /chat SSE — pergunta rápida…")
        t0 = time.time()
        chunks = []
        citations = []
        async with client.stream(
            "POST", f"{API}/api/perplexity-plus/chat",
            headers={**H, "Content-Type": "application/json"},
            json={"message": "Em uma frase: o que é o RGEU?", "preset": "DRE"},
        ) as r:
            if r.status_code != 200:
                print(f"[FAIL] /chat {r.status_code}")
                results["endpoints"]["chat"] = {"ok": False}
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        d = json.loads(payload)
                    except Exception:
                        continue
                    if d.get("delta"):
                        chunks.append(d["delta"])
                    if d.get("citations"):
                        citations = d["citations"]
                dt = time.time() - t0
                text = "".join(chunks)
                print(f"[OK] /chat {dt:.1f}s chunks={len(chunks)} text_len={len(text)} citations={len(citations)}")
                print(f"     excerto: {text[:150]}…")
                results["endpoints"]["chat"] = {
                    "ok": True, "chunks": len(chunks), "text_len": len(text),
                    "citations": len(citations), "duration_s": round(dt, 1),
                }

        # 7. Cache stats final
        r = await client.get(f"{API}/api/perplexity-plus/cache-stats", headers=H)
        if r.status_code == 200:
            print(f"\n[INFO] Cache final: {r.json()}")
            results["cache_stats_final"] = r.json()

    print("\n[SUMMARY]")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)
