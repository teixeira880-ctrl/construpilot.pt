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
SUPERLATIVES = ["le meilleur", "n°1", "numéro 1", "leader", "révolutionnaire", "le plus complet", "o melhor", "líder", "revolucionário", "o mais completo", "100 %", "garanti"]
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
        return {"error": "réponse non analysable", "raw": text[:2000]}


def _sources_block(content: dict) -> str:
    src = ((content.get("research") or {}).get("sources")) or []
    return "\n".join(f"- {s.get('title')} — {s.get('publisher')} ({s.get('date') or 'date non détectée'}) : {s.get('url')}" for s in src) or "- (aucune source vérifiée : n'ajoute AUCUN lien externe)"


async def _brand_context(project_id: str) -> str:
    facts = await db.growth_brand_facts.find({"project_id": project_id, "status": "confirmed"}, {"_id": 0}).to_list(200)
    return "\n".join(f"- [{f['category']}] {f['statement']}" for f in facts) or "- (aucun fait confirmé)"


async def generate_brief(project: dict, content: dict) -> dict:
    lang = "français de France" if project["key"] == "fr" else "portugais du Portugal (vocabulaire et réalités locales du Portugal)"
    pages = await db.growth_pages.find({"project_id": project["project_id"], "status_code": 200}, {"_id": 0, "url": 1, "title": 1}).sort("fetched_at", -1).to_list(60)
    seen, internal = set(), []
    for p in pages:
        if p["url"] not in seen:
            seen.add(p["url"]); internal.append(f"{p['url']} — {p.get('title') or ''}")
    system = "Tu es un stratège de contenu B2B pour un logiciel BTP. Tu écris en JSON strict, sans markdown autour."
    prompt = f"""Prépare un BRIEF éditorial en {lang}.
Sujet : {content.get('topic')}. Intention : {content.get('intent')}. Public : {content.get('audience') or 'professionnels du bâtiment'}. Format : {content.get('format') or 'guide pratique'}.
Faits CONFIRMÉS sur ConstruPilot (seuls faits utilisables pour toute affirmation commerciale) :
{await _brand_context(project['project_id'])}
Pages internes existantes (choisis 2 à 4 liens pertinents, n'invente aucune URL) :
{chr(10).join(internal[:40]) or '(aucune page auditée)'}
Sources externes VÉRIFIÉES (accessibles, testées) — seules sources externes autorisées, appuie le plan dessus :
{_sources_block(content)}
Règles : aucun témoignage, client, chiffre, certification ou tarif inventé ; pas de superlatif non démontré ; pas de classement plaçant ConstruPilot premier ; réponse utile avec exemples concrets.
Réponds en JSON : {{"title": str, "slug": str (kebab-case ascii), "description": str (140-160 car.), "audience": str, "outline": [str], "internal_links": [str], "sources_to_check": [str], "cta": str, "search_intent_note": str}}"""
    data = _json(await _llm(system, prompt, project["project_id"], "content_brief"))
    if "error" in data:
        raise ValueError(data["error"])
    data["internal_links"] = [u for u in data.get("internal_links") or [] if u in seen]
    return data


async def generate_draft(project: dict, content: dict) -> dict:
    lang = "français de France" if project["key"] == "fr" else "portugais du Portugal (utilise le vocabulaire du Portugal : orçamento, obra, empreiteiro, IVA, AT ; jamais de brésilien)"
    system = "Tu es un rédacteur technique BTP rigoureux. Tu écris en JSON strict, sans markdown autour du JSON."
    prompt = f"""Rédige l'article complet en {lang} à partir de ce brief : {json.dumps({k: content.get(k) for k in ('title', 'description', 'outline', 'audience', 'intent', 'internal_links', 'cta', 'topic')}, ensure_ascii=False)}
Faits CONFIRMÉS sur ConstruPilot (ne rien affirmer d'autre sur le produit) :
{await _brand_context(project['project_id'])}
Sources externes VÉRIFIÉES (les seules que tu peux citer ou lier ; cite-les dans le texte sous la forme [titre](url) et reprends-les dans "sources") :
{_sources_block(content)}
Exigences : 900 à 1400 mots, Markdown (## et ###), exemples chiffrés génériques présentés comme illustratifs, informations réglementaires/fiscales datées et signalées « à vérifier » si incertaines, liens internes uniquement parmi ceux du brief, aucun lien externe hors sources vérifiées, ton factuel, pas de superlatif, une FAQ de 3 questions en fin d'article, une section « Sources » finale listant les sources utilisées avec leur date.
Réponds en JSON : {{"title": str, "body_markdown": str, "claims_about_construpilot": [str], "sources": [{{"label": str, "url": str|null, "date": str|null}}], "faq": [{{"q": str, "a": str}}]}}"""
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
            blocking.append({"kind": "claim_unverified", "text": claim, "fix": "Confirmer ce fait dans la fiche de marque ou retirer l'affirmation"})
    others = await db.growth_contents.find({"project_id": project["project_id"], "content_id": {"$ne": content["content_id"]}, "status": {"$nin": ["archived", "failed"]}}, {"_id": 0, "slug": 1, "title": 1, "topic": 1}).to_list(500)
    for o in others:
        if o.get("slug") and o["slug"] == content.get("slug"):
            blocking.append({"kind": "duplicate_slug", "text": o["slug"], "fix": "Choisir un slug unique"})
        elif o.get("title") and content.get("title") and SequenceMatcher(None, o["title"].lower(), content["title"].lower()).ratio() > 0.8:
            warnings.append({"kind": "cannibalization", "text": f"Titre proche de « {o['title']} »", "fix": "Mettre à jour la page existante plutôt que d'en créer une nouvelle"})
    if await db.autoseo_articles.find_one({"slug": content.get("slug")}):
        blocking.append({"kind": "slug_exists_on_blog", "text": content.get("slug"), "fix": "Un article publié porte déjà ce slug"})
    for s in SUPERLATIVES:
        if s in body.lower():
            warnings.append({"kind": "superlative", "text": s, "fix": "Reformuler de façon démontrable"})
    links = re.findall(r"\]\((https?://[^)\s]+)\)", body)
    verified = {s.get("url") for s in ((content.get("research") or {}).get("sources")) or []}
    site = (project.get("site_url") or "").rstrip("/")
    for u in set(links):
        if not u.startswith(site) and "construpilot" not in u and u.rstrip("/") not in {v.rstrip("/") for v in verified if v}:
            blocking.append({"kind": "source_unverified", "text": u, "fix": "Lien externe absent des sources vérifiées : relancer la recherche ou retirer le lien"})
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for u in set(links):
            try:
                r = await client.head(u, headers={"User-Agent": "ConstruPilotGrowthBot/1.0"})
                if r.status_code >= 400:
                    blocking.append({"kind": "broken_link", "text": f"{u} → HTTP {r.status_code}", "fix": "Corriger ou retirer le lien"})
            except Exception as e:
                warnings.append({"kind": "link_unverified", "text": f"{u} ({type(e).__name__})", "fix": "Vérifier manuellement"})
    if not content.get("sources"):
        warnings.append({"kind": "no_sources", "text": "Aucune source listée", "fix": "Ajouter des sources datées"})
    if not verified:
        warnings.append({"kind": "no_research", "text": "Aucune recherche de sources vérifiées", "fix": "Lancer « Rechercher les sources » avant la rédaction"})
    if re.search(r"\b(2023|2024)\b", body):
        warnings.append({"kind": "possibly_outdated", "text": "Années 2023/2024 mentionnées", "fix": "Vérifier que l'information est encore à jour"})
    words = len(body.split())
    if words < 600:
        warnings.append({"kind": "short", "text": f"{words} mots", "fix": "Développer la réponse"})
    return {"blocking": blocking, "warnings": warnings, "passed": not blocking, "checked_at": now_iso(), "word_count": words}


def to_html(body_markdown: str) -> str:
    return md.markdown(body_markdown or "", extensions=["tables", "fenced_code"])


def article_payload(project: dict, content: dict) -> dict:
    site = project["site_url"].rstrip("/")
    return {"autoseo_id": f"growth_{content['content_id']}", "title": content["title"], "slug": content["slug"], "published_url": f"{site}/blog/{content['slug']}",
            "meta_description": content.get("description"), "content_html": to_html(content.get("body_markdown")), "content_markdown": content.get("body_markdown"),
            "keywords": content.get("keywords") or [], "language_code": project["key"], "status": "published", "published_at": now_iso(), "updated_at": now_iso(),
            "faq_schema": {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in content.get("faq") or []]} if content.get("faq") else None,
            "source": "construpilot_growth", "growth_content_id": content["content_id"], "growth_version": content.get("version", 1)}


async def publish(project: dict, content: dict, actor: str) -> dict:
    """Idempotent: the blog entry is upserted on autoseo_id, so a retry never creates a second article."""
    payload = article_payload(project, content)
    if project["key"] == "fr" or env("GROWTH_PT_SITE_URL") is None:
        target = "blog local"
        await db.autoseo_articles.update_one({"autoseo_id": payload["autoseo_id"]}, {"$set": payload, "$setOnInsert": {"first_received_at": now_iso()}}, upsert=True)
        if project["key"] != "fr":
            target = "blog local (GROWTH_PT_SITE_URL non configuré : l'article est publié sur ce déploiement, filtré par langue pt)"
    else:
        target = env("GROWTH_PT_SITE_URL").rstrip("/")
        token = env("GROWTH_PUBLISH_TOKEN")
        if not token:
            raise ValueError("GROWTH_PUBLISH_TOKEN manquant pour publier sur construpilot.pt")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{target}/api/growth/publish-inbox", json=payload, headers={"Authorization": f"Bearer {token}"})
            if r.status_code >= 300:
                raise ValueError(f"Publication PT refusée : HTTP {r.status_code}")
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
    out["indexation"] = "inconnue (Search Console non connectée)"
    out["note"] = "Sur une application rendue côté client, la balise <title> peut n'apparaître qu'après exécution du JavaScript."
    return out
