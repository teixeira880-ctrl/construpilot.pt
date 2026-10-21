"""Content pipeline: brief → draft (GPT-5.4 via the universal key) → fact checks → publication on the ConstruPilot blog (FR direct, PT via token inbox)."""
import json
import logging
import os
import re
from difflib import SequenceMatcher

import httpx
import markdown as md

from core.db import db
from growth.common import env, new_id, now_iso, record_cost

logger = logging.getLogger(__name__)
CONTENT_MODEL = ("openai", "gpt-5.4")
SUPERLATIVES = ["le meilleur", "n°1", "numéro 1", "leader", "révolutionnaire", "o mais completo", "o melhor", "líder", "revolucionário", "o mais completo", "100 %", "garanti"]
STATES = ["idea", "brief", "draft", "review", "approved", "scheduled", "published", "failed", "archived"]


async def _llm(system: str, prompt: str, project_id: str, feature: str) -> str:
    from emergentintegrations.llm.chat import UserMessage

    from engines.expenses.metering import MeteredChat
    chat = MeteredChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"growth-{feature}-{new_id('s')}", expense_feature="growth", system_message=system).with_model(*CONTENT_MODEL)
    out = await chat.send_message(UserMessage(text=prompt))
    text = out if isinstance(out, str) else str(out)
    await record_cost(project_id, "openai", feature, (len(prompt) / 4 * 1.25 + len(text) / 4 * 10) / 1_000_000, estimated=True)
    return text


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(m.group(0) if m else text)
    except Exception:
        return {"error": "resposta não analisável", "raw": text[:2000]}


def _sources_block(content: dict) -> str:
    src = ((content.get("research") or {}).get("sources")) or []
    return "\n".join(f"- {s.get('title')} — {s.get('publisher')} ({s.get('date') or 'data não detetada'}) : {s.get('url')}" for s in src) or "- (nenhuma fonte verificada: NÃO acrescentes nenhuma ligação externa)"


async def _brand_context(project_id: str) -> str:
    facts = await db.growth_brand_facts.find({"project_id": project_id, "status": "confirmed"}, {"_id": 0}).to_list(200)
    return "\n".join(f"- [{f['category']}] {f['statement']}" for f in facts) or "- (nenhum facto confirmado)"


async def generate_brief(project: dict, content: dict) -> dict:
    lang = "francês de França" if project["key"] == "fr" else "português de Portugal (vocabulário e realidades locais de Portugal)"
    pages = await db.growth_pages.find({"project_id": project["project_id"], "status_code": 200}, {"_id": 0, "url": 1, "title": 1}).sort("fetched_at", -1).to_list(60)
    seen, internal = set(), []
    for p in pages:
        if p["url"] not in seen:
            seen.add(p["url"]); internal.append(f"{p['url']} — {p.get('title') or ''}")
    system = "És um estratega de conteúdos B2B para um software de construção. Escreves em JSON estrito, sem markdown à volta."
    prompt = f"""Prepara um BRIEFING editorial em {lang}.\nSujet : {content.get('topic')}. Intention : {content.get('intent')}. Public : {content.get('audience') or 'profissionais da construção'}. Format : {content.get('format') or 'guide pratique'}.\nFactos CONFIRMADOS sobre o ConstruPilot (únicos factos utilizáveis para qualquer afirmação comercial):\n{await _brand_context(project['project_id'])}\nPáginas internas existentes (escolhe 2 a 4 ligações pertinentes, não inventes nenhum URL):\n{chr(10).join(internal[:40]) or '(nenhuma página auditada)'}\nFontes externas VERIFICADAS (acessíveis, testadas) — únicas fontes externas autorizadas, apoia o plano nelas:\n{_sources_block(content)}\nRegras: nenhum testemunho, cliente, número, certificação ou preço inventado; nenhum superlativo não demonstrado; nenhuma classificação que coloque o ConstruPilot em primeiro; resposta útil com exemplos concretos.\nResponde em JSON: {{"title": str, "slug": str (kebab-case ascii), "description": str (140-160 car.), "audience": str, "outline": [str], "internal_links": [str], "sources_to_check": [str], "cta": str, "search_intent_note": str}}"""
    data = _json(await _llm(system, prompt, project["project_id"], "content_brief"))
    if "error" in data:
        raise ValueError(data["error"])
    data["internal_links"] = [u for u in data.get("internal_links") or [] if u in seen]
    return data


async def generate_draft(project: dict, content: dict) -> dict:
    lang = "francês de França" if project["key"] == "fr" else "português de Portugal (usa o vocabulário de Portugal: orçamento, obra, empreiteiro, IVA, AT; nunca brasileiro)"
    system = "És um redator técnico de construção rigoroso. Escreves em JSON estrito, sem markdown à volta do JSON."
    prompt = f"""Redige o artigo completo em {lang} a partir deste briefing: {json.dumps({k: content.get(k) for k in ('title', 'description', 'outline', 'audience', 'intent', 'internal_links', 'cta', 'topic')}, ensure_ascii=False)}\nFactos CONFIRMADOS sobre o ConstruPilot (não afirmes mais nada sobre o produto):\n{await _brand_context(project['project_id'])}\nFontes externas VERIFICADAS (as únicas que podes citar ou ligar; cita-as no texto na forma [título](url) e repete-as em "sources"):\n{_sources_block(content)}\nRequisitos: 900 a 1400 palavras, Markdown (## e ###), exemplos numéricos genéricos apresentados como ilustrativos, informações regulamentares/fiscais datadas e assinaladas «a verificar» se incertas, ligações internas apenas entre as do briefing, nenhuma ligação externa fora das fontes verificadas, tom factual, sem superlativos, uma FAQ de 3 perguntas no fim do artigo, uma secção «Fontes» final que liste as fontes utilizadas com a respetiva data. Escreve em português europeu.\nResponde em JSON: {{"title": str, "body_markdown": str, "claims_about_construpilot": [str], "sources": [{{"label": str, "url": str|null, "date": str|null}}], "faq": [{{"q": str, "a": str}}]}}"""
    data = _json(await _llm(system, prompt, project["project_id"], "content_draft"))
    if "error" in data:
        raise ValueError(data["error"])
    return data


async def quality_checks(project: dict, content: dict) -> dict:
    """Blocking: unverified product claims, duplicate slug/title, invalid internal links. Warnings: superlatives, missing sources, dated info."""
    body = content.get("body_markdown") or ""
    blocking, warnings = [], []
    facts = [f["statement"].lower() for f in await db.growth_brand_facts.find({"project_id": project["project_id"], "status": "confirmed"}, {"_id": 0}).to_list(200)]
    for claim in content.get("claims_about_construpilot") or []:
        if not any(SequenceMatcher(None, claim.lower(), f).ratio() > 0.45 or any(w in f for w in claim.lower().split()[:4] if len(w) > 5) for f in facts):
            blocking.append({"kind": "claim_unverified", "text": claim, "fix": "Confirmar este facto na ficha da marca ou retirar a afirmação"})
    others = await db.growth_contents.find({"project_id": project["project_id"], "content_id": {"$ne": content["content_id"]}, "status": {"$nin": ["archived", "failed"]}}, {"_id": 0, "slug": 1, "title": 1, "topic": 1}).to_list(500)
    for o in others:
        if o.get("slug") and o["slug"] == content.get("slug"):
            blocking.append({"kind": "duplicate_slug", "text": o["slug"], "fix": "Escolher um slug único"})
        elif o.get("title") and content.get("title") and SequenceMatcher(None, o["title"].lower(), content["title"].lower()).ratio() > 0.8:
            warnings.append({"kind": "cannibalization", "text": f"Título próximo de «{o['title']} »", "fix": "Atualizar a página existente em vez de criar uma nova"})
    if await db.autoseo_articles.find_one({"slug": content.get("slug")}):
        blocking.append({"kind": "slug_exists_on_blog", "text": content.get("slug"), "fix": "Já existe um artigo publicado com este slug"})
    for s in SUPERLATIVES:
        if s in body.lower():
            warnings.append({"kind": "superlative", "text": s, "fix": "Reformular de forma demonstrável"})
    links = re.findall(r"\]\((https?://[^)\s]+)\)", body)
    verified = {s.get("url") for s in ((content.get("research") or {}).get("sources")) or []}
    site = (project.get("site_url") or "").rstrip("/")
    for u in set(links):
        if not u.startswith(site) and "construpilot" not in u and u.rstrip("/") not in {v.rstrip("/") for v in verified if v}:
            blocking.append({"kind": "source_unverified", "text": u, "fix": "Ligação externa ausente das fontes verificadas: relançar a pesquisa ou retirar a ligação"})
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for u in set(links):
            try:
                r = await client.head(u, headers={"User-Agent": "ConstruPilotGrowthBot/1.0"})
                if r.status_code >= 400:
                    blocking.append({"kind": "broken_link", "text": f"{u} → HTTP {r.status_code}", "fix": "Corrigir ou retirar a ligação"})
            except Exception as e:
                warnings.append({"kind": "link_unverified", "text": f"{u} ({type(e).__name__})", "fix": "Verificar manualmente"})
    if not content.get("sources"):
        warnings.append({"kind": "no_sources", "text": "Nenhuma fonte listada", "fix": "Acrescentar fontes datadas"})
    if not verified:
        warnings.append({"kind": "no_research", "text": "Nenhuma pesquisa de fontes verificadas", "fix": "Lançar «Pesquisar as fontes» antes da redação"})
    if re.search(r"\b(2023|2024)\b", body):
        warnings.append({"kind": "possibly_outdated", "text": "Anos 2023/2024 mencionados", "fix": "Verificar se a informação ainda está atualizada"})
    words = len(body.split())
    if words < 600:
        warnings.append({"kind": "short", "text": f"{words} mots", "fix": "Desenvolver a resposta"})
    return {"blocking": blocking, "warnings": warnings, "passed": not blocking, "checked_at": now_iso(), "word_count": words}


def to_html(body_markdown: str) -> str:
    return md.markdown(body_markdown or "", extensions=["tables", "fenced_code"])


def article_payload(project: dict, content: dict) -> dict:
    site = project["site_url"].rstrip("/")
    return {"autoseo_id": f"growth_{content['content_id']}", "title": content["title"], "slug": content["slug"], "published_url": f"{site}/blog/{content['slug']}",
            "meta_description": content.get("description"), "content_html": to_html(content.get("body_markdown")), "content_markdown": content.get("body_markdown"),
            "keywords": content.get("keywords") or [], "language_code": project["key"], "status": "published", "published_at": now_iso(), "updated_at": now_iso(),
            "faq_schema": {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Pergunta", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in content.get("faq") or []]} if content.get("faq") else None,
            "source": "construpilot_growth", "growth_content_id": content["content_id"], "growth_version": content.get("version", 1)}


async def publish(project: dict, content: dict, actor: str) -> dict:
    """Idempotent: the blog entry is upserted on autoseo_id, so a retry never creates a second article."""
    payload = article_payload(project, content)
    if project["key"] == "fr" or env("GROWTH_PT_SITE_URL") is None:
        target = "blog local"
        await db.autoseo_articles.update_one({"autoseo_id": payload["autoseo_id"]}, {"$set": payload, "$setOnInsert": {"first_received_at": now_iso()}}, upsert=True)
        if project["key"] != "fr":
            target = "blog local (GROWTH_PT_SITE_URL não configurado: o artigo é publicado nesta implementação, filtrado pela língua pt)"
    else:
        target = env("GROWTH_PT_SITE_URL").rstrip("/")
        token = env("GROWTH_PUBLISH_TOKEN")
        if not token:
            raise ValueError("GROWTH_PUBLISH_TOKEN em falta para publicar em construpilot.pt")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{target}/api/growth/publish-inbox", json=payload, headers={"Authorization": f"Bearer {token}"})
            if r.status_code >= 300:
                raise ValueError(f'Publicação PT recusada: HTTP {r.status_code}')
    verification = await verify_published(payload["published_url"], content["title"], project)
    return {"published_url": payload["published_url"], "target": target, "verification": verification, "published_at": payload["published_at"], "published_by": actor}


async def verify_published(url: str, title: str, project: dict) -> dict:
    out = {"url": url, "checked_at": now_iso()}
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "ConstruPilotGrowthBot/1.0"})
            out["http_status"] = r.status_code
            out["title_tag_present"] = title.lower()[:30] in r.text.lower()
            sm = await client.get(f"{project['site_url'].rstrip('/')}/api/blog/sitemap.xml")
            out["in_blog_sitemap"] = sm.status_code == 200 and url.split("/blog/")[-1] in sm.text
    except Exception as e:
        out["error"] = type(e).__name__
    out["indexation"] = "desconhecida (Search Console não ligada)"
    out["note"] = "Numa aplicação renderizada no cliente, a etiqueta <title> pode só aparecer após a execução do JavaScript."
    return out
