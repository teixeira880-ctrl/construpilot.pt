"""Recherche « sources d'abord » : Perplexity (recherche web) propose des sources, chaque URL est ensuite testée (HTTP 200,
titre, date, domaine officiel) — seules les sources vérifiées alimentent le brief et la rédaction."""
import asyncio
import json
import logging
import os
import re
import time
from urllib.parse import urlparse

import httpx

from growth.common import record_cost, now_iso

logger = logging.getLogger(__name__)

TRUSTED = {
    "fr": ["legifrance.gouv.fr", "service-public.fr", "ademe.fr", "ffbatiment.fr", "capeb.fr", "insee.fr", "economie.gouv.fr", "anah.gouv.fr", "anah.fr",
           "qualibat.com", "urssaf.fr", "impots.gouv.fr", "ecologie.gouv.fr", "anil.org", "cstb.fr", "entreprendre.gouv.fr", "france-renov.gouv.fr", "batiactu.com",
           "lemoniteur.fr", "afnor.org", "inrs.fr", "opqibi.com", "fntp.fr"],
    "pt": ["portaldasfinancas.gov.pt", "dre.pt", "diariodarepublica.pt", "impic.pt", "ine.pt", "portaldahabitacao.pt", "iapmei.pt", "gov.pt", "seg-social.pt",
           "dgeg.gov.pt", "adene.pt", "ordemengenheiros.pt", "oasrs.org", "aiccopn.pt", "lnec.pt", "act.gov.pt"],
}
UA = "Mozilla/5.0 (compatible; ConstruPilotGrowthBot/1.0; +https://construpilot.fr) verification de sources"
DATE_RX = re.compile(r"(20[12]\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")


def _domain(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def is_trusted(url: str, lang: str) -> bool:
    d = _domain(url)
    return any(d == t or d.endswith("." + t) for t in TRUSTED.get(lang, []) + TRUSTED["fr"])


async def verify_url(client: httpx.AsyncClient, url: str) -> dict:
    """Test réel : statut HTTP, type de contenu, titre et date détectés. Ne suit que des URL http(s)."""
    out = {"url": url, "ok": False, "status": None, "title": None, "date": None, "content_type": None}
    if not url.startswith(("http://", "https://")):
        out["error"] = "URL non http"; return out
    try:
        r = await client.get(url, headers={"User-Agent": UA, "Accept": "text/html,application/pdf,*/*;q=0.8"}, follow_redirects=True)
        out["status"] = r.status_code
        out["final_url"] = str(r.url)
        ct = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        out["content_type"] = ct
        if r.status_code != 200:
            out["error"] = f"HTTP {r.status_code}"; return out
        if ct.startswith("text/html"):
            html = r.text[:400_000]
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            out["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:200] if m else None
            for pat in (r'property="article:published_time"\s+content="([^"]+)"', r'name="date"\s+content="([^"]+)"', r'"datePublished"\s*:\s*"([^"]+)"', r'property="article:modified_time"\s+content="([^"]+)"'):
                dm = re.search(pat, html, re.I)
                if dm:
                    out["date"] = dm.group(1)[:10]; break
            if not out["date"]:
                dm = DATE_RX.search(html)
                out["date"] = dm.group(0) if dm else None
            text = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I))
            if len(text.split()) < 60:
                out["error"] = "page quasi vide (rendu JS ?)"; return out
        elif ct != "application/pdf":
            out["error"] = f"type {ct or 'inconnu'}"; return out
        out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = type(e).__name__
    return out


async def _perplexity_sources(topic: str, lang: str, n: int = 8) -> tuple[list[dict], float, str | None]:
    from perplexity import AsyncPerplexity
    client = AsyncPerplexity(api_key=os.environ["PERPLEXITY_API_KEY"], max_retries=1, timeout=120.0)
    trusted = ", ".join(TRUSTED[lang][:12])
    instructions = ("Tu es documentaliste pour un média professionnel du bâtiment. Tu réponds UNIQUEMENT en JSON strict : "
                    '{"sources":[{"url":str,"title":str,"publisher":str,"date":str|null,"why":str}]}. '
                    f"Priorité absolue aux sources officielles ou institutionnelles ({trusted}), puis fédérations professionnelles, puis presse spécialisée. "
                    "Exclure blogs commerciaux, forums, pages génériques. Chaque URL doit être une page précise (pas une page d'accueil). Sources récentes (moins de 24 mois) sauf textes réglementaires de référence.")
    q = (f"Trouve {n} sources fiables et précises pour rédiger un article {'en français (France)' if lang == 'fr' else 'em português (Portugal)'} sur : « {topic} ». "
         "Donne l'URL exacte de chaque page.")
    r = await client.responses.create(input=q, instructions=instructions, tools=[{"type": "web_search", "search_context_size": "medium", "max_results": 15}],
                                      store=False, max_output_tokens=1500, preset="fast")
    d = r.model_dump()
    cost = float(((d.get("usage") or {}).get("cost") or {}).get("total_cost") or 0.0)
    text = r.output_text or ""
    m = re.search(r"\{.*\}", text, re.S)
    found = []
    try:
        found = (json.loads(m.group(0)) if m else {}).get("sources") or []
    except Exception:
        pass
    for item in d.get("output") or []:
        if item.get("type") == "search_results":
            found.extend({"url": x.get("url"), "title": x.get("title"), "publisher": _domain(x.get("url") or ""), "date": x.get("date"), "why": "résultat de recherche", "from_search": True}
                         for x in item.get("results") or [])
    return found, cost, d.get("model")


async def find_sources(project: dict, content: dict) -> dict:
    lang = project["key"]
    topic = content.get("title") or content.get("topic") or ""
    t0 = time.monotonic()
    found, cost, model = await _perplexity_sources(topic, lang)
    await record_cost(project["project_id"], "perplexity", "content_research", cost, ref=content["content_id"])
    seen, candidates = set(), []
    for s in found:
        u = (s.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u); candidates.append({**s, "url": u})
    async with httpx.AsyncClient(timeout=15) as client:
        checks = await asyncio.gather(*[verify_url(client, c["url"]) for c in candidates[:20]])
    verified, rejected = [], []
    for c, v in zip(candidates, checks):
        row = {"url": v.get("final_url") or c["url"], "title": v.get("title") or c.get("title") or c["url"], "publisher": c.get("publisher") or _domain(c["url"]),
               "date": v.get("date") or c.get("date"), "why": c.get("why") or "", "trusted": is_trusted(c["url"], lang), "http_status": v.get("status"), "content_type": v.get("content_type"), "checked_at": now_iso()}
        (verified if v["ok"] else rejected).append(row if v["ok"] else {**row, "error": v.get("error")})
    verified.sort(key=lambda s: (not s["trusted"], not bool(s.get("date")), s["url"]))
    return {"sources": verified[:10], "rejected": rejected, "model": model, "cost_usd": cost, "latency_ms": int((time.monotonic() - t0) * 1000), "searched_at": now_iso(),
            "trusted_count": sum(1 for s in verified[:10] if s["trusted"])}
