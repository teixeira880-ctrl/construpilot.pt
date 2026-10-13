"""Phase C — documented technical research (Perplexity Agent API, web-grounded) with original sources kept. No site data is sent beyond the question itself."""
import os
import time
from datetime import datetime, timezone

from core.db import db

COUNTRY_HINT = {"FR": "France (documents en français, réglementation et DTU/normes françaises)", "PT": "Portugal (documentos em português de Portugal, regulamentação portuguesa)"}
SYSTEM = ("Tu es un documentaliste technique du bâtiment. Réponds dans la langue de la question. Structure : 1) objectif et contraintes reformulés, 2) informations manquantes qui changeraient la solution, "
          "3) solutions documentées comparées (conditions d'emploi, mise en œuvre, limites), 4) validations requises (BET / fabricant), 5) sources : cite uniquement des documents réellement trouvés "
          "(fabricant, organisme technique, texte officiel), avec date si connue. N'invente aucun numéro de norme ou de clause. Si une information n'a pas pu être vérifiée, dis-le explicitement.")


def configured() -> dict:
    return {"perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")), "label": "Perplexity Agent API (recherche web, sources originales)"}


async def search_technical_docs(question: str, country: str, user_id: str, project_id: str | None = None, preset: str = "medium") -> dict:
    if not configured()["perplexity"]:
        return {"ok": False, "error": "PERPLEXITY_API_KEY manquante : recherche documentaire indisponible (connexion manquante)"}
    from perplexity import AsyncPerplexity
    client = AsyncPerplexity(api_key=os.environ["PERPLEXITY_API_KEY"], max_retries=1, timeout=120.0)
    t0 = time.monotonic()
    r = await client.responses.create(input=question, instructions=f"{SYSTEM}\nPays du chantier : {COUNTRY_HINT.get(country, country)}.", preset=preset,
                                      tools=[{"type": "web_search", "search_context_size": "medium", "max_results": 12}], store=False, max_output_tokens=1800)
    d = r.model_dump()
    sources = []
    for item in d.get("output") or []:
        if item.get("type") == "search_results":
            sources.extend({"url": x.get("url"), "title": x.get("title"), "snippet": x.get("snippet"), "date": x.get("date") or x.get("last_updated")} for x in item.get("results") or [])
    usage = d.get("usage") or {}
    rec = {"research_id": f"res_{int(time.time() * 1000)}", "user_id": user_id, "project_id": project_id, "country": country, "question": question, "answer": r.output_text or "",
           "sources": sources, "provider": "perplexity", "model": d.get("model"), "preset": preset, "cost_usd": float(((usage.get("cost") or {}).get("total_cost")) or 0), "latency_ms": int((time.monotonic() - t0) * 1000),
           "status": d.get("status"), "at": datetime.now(timezone.utc).isoformat(), "verified_note": "Sources fournies par la recherche web ; leur applicabilité au chantier (support, produit, version) reste à vérifier."}
    await db.btp_research.insert_one(dict(rec))
    rec.pop("_id", None)
    return {"ok": True, **rec}
