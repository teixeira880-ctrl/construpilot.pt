"""Phase C — documented technical research (Perplexity Agent API, web-grounded) with original sources kept. No site data is sent beyond the question itself."""
import os
import time
from datetime import datetime, timezone

from core.db import db

COUNTRY_HINT = {"FR": "França (documentos em francês, regulamentação e normas francesas)", "PT": "Portugal (documentos em português de Portugal, regulamentação portuguesa)"}
SYSTEM = ("És um documentalista técnico da construção. Responde na língua da pergunta. Estrutura: 1) objetivo e condicionantes reformulados, 2) informações em falta que mudariam a solução, 3) soluções documentadas comparadas (condições de utilização, execução, limites), 4) validações necessárias (projetista / fabricante), 5) fontes: cita apenas documentos realmente encontrados (fabricante, organismo técnico como o LNEC, texto oficial do Diário da República), com data se conhecida. Não inventes nenhum número de norma ou de cláusula. Se uma informação não pôde ser verificada, di-lo explicitamente.")


def configured() -> dict:
    return {"perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")), "label": "Perplexity Agent API (pesquisa web, fontes originais)"}


async def search_technical_docs(question: str, country: str, user_id: str, project_id: str | None = None, preset: str = "medium") -> dict:
    if not configured()["perplexity"]:
        return {"ok": False, "error": "PERPLEXITY_API_KEY em falta: pesquisa documental indisponível (ligação em falta)"}
    from perplexity import AsyncPerplexity
    client = AsyncPerplexity(api_key=os.environ["PERPLEXITY_API_KEY"], max_retries=1, timeout=120.0)
    t0 = time.monotonic()
    r = await client.responses.create(input=question, instructions=f'{SYSTEM}\nPaís da obra: {COUNTRY_HINT.get(country, country)}.', preset=preset,
                                      tools=[{"type": "web_search", "search_context_size": "medium", "max_results": 12}], store=False, max_output_tokens=1800)
    d = r.model_dump()
    sources = []
    for item in d.get("output") or []:
        if item.get("type") == "search_results":
            sources.extend({"url": x.get("url"), "title": x.get("title"), "snippet": x.get("snippet"), "date": x.get("date") or x.get("last_updated")} for x in item.get("results") or [])
    usage = d.get("usage") or {}
    rec = {"research_id": f"res_{int(time.time() * 1000)}", "user_id": user_id, "project_id": project_id, "country": country, "question": question, "answer": r.output_text or "",
           "sources": sources, "provider": "perplexity", "model": d.get("model"), "preset": preset, "cost_usd": float(((usage.get("cost") or {}).get("total_cost")) or 0), "latency_ms": int((time.monotonic() - t0) * 1000),
           "status": d.get("status"), "at": datetime.now(timezone.utc).isoformat(), "verified_note": "Fontes fornecidas pela pesquisa web; a sua aplicabilidade à obra (suporte, produto, versão) continua por verificar."}
    await db.btp_research.insert_one(dict(rec))
    rec.pop("_id", None)
    return {"ok": True, **rec}
