"""Publicação orgânica nas redes sociais: Página Facebook, Instagram (conta profissional ligada à
página) e Página de empresa LinkedIn.

Variáveis de ambiente (produção):
- META_PAGE_ID, META_PAGE_ACCESS_TOKEN (token de página / utilizador do sistema com
  pages_manage_posts, pages_read_engagement, instagram_basic, instagram_content_publish)
- META_IG_USER_ID (opcional: ID da conta Instagram Business ligada à página)
- LINKEDIN_ORG_ID, LINKEDIN_ACCESS_TOKEN (scope w_organization_social; expira ~60 dias)
- META_API_VERSION (por defeito v25.0), LINKEDIN_VERSION (YYYYMM, por defeito 3 meses atrás)

Auto-partilha: os artigos publicados no blogue (Agente CEO, BabyLoveGrowth, AutoSEO) em PT
são partilhados uma vez em cada rede ligada, com um texto curto gerado pela IA.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from core.db import db
from engines.ai import _complete, _json

log = logging.getLogger("social")
SITE_URL = "https://construpilot.pt"
SETTINGS_KEY = "social_settings"
DEFAULTS = {"auto_share": False, "networks": ["facebook", "instagram", "linkedin"], "max_per_day": 6}


class SocialError(Exception):
    pass


def _env(k: str) -> str | None:
    v = os.environ.get(k)
    return v.strip() if v and v.strip() else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def meta_version() -> str:
    return _env("META_API_VERSION") or "v25.0"


def linkedin_version() -> str:
    if _env("LINKEDIN_VERSION"):
        return _env("LINKEDIN_VERSION")
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month - 3
    if m <= 0:
        y, m = y - 1, m + 12
    return f"{y}{m:02d}"


def status() -> dict:
    fb = bool(_env("META_PAGE_ID") and _env("META_PAGE_ACCESS_TOKEN"))
    return {
        "facebook": {"configured": fb, "missing": [k for k in ("META_PAGE_ID", "META_PAGE_ACCESS_TOKEN") if not _env(k)]},
        "instagram": {"configured": fb and bool(_env("META_IG_USER_ID")),
                      "missing": [k for k in ("META_PAGE_ID", "META_PAGE_ACCESS_TOKEN", "META_IG_USER_ID") if not _env(k)]},
        "linkedin": {"configured": bool(_env("LINKEDIN_ORG_ID") and _env("LINKEDIN_ACCESS_TOKEN")),
                     "missing": [k for k in ("LINKEDIN_ORG_ID", "LINKEDIN_ACCESS_TOKEN") if not _env(k)]},
    }


async def get_settings() -> dict:
    doc = await db.app_settings.find_one({"key": SETTINGS_KEY}, {"_id": 0}) or {}
    return {**DEFAULTS, **{k: v for k, v in doc.items() if k in DEFAULTS}}


async def save_settings(patch: dict) -> dict:
    cur = await get_settings()
    if "auto_share" in patch:
        if bool(patch["auto_share"]) and not cur["auto_share"]:
            # Ao ligar: os artigos já publicados NÃO são despejados nas redes (só os novos).
            await db.autoseo_articles.update_many(
                {"status": "published", "social_shared_at": {"$exists": False}},
                {"$set": {"social_shared_at": "backlog"}})
        cur["auto_share"] = bool(patch["auto_share"])
    if "networks" in patch:
        cur["networks"] = [n for n in patch["networks"] if n in ("facebook", "instagram", "linkedin")]
    if "max_per_day" in patch:
        cur["max_per_day"] = max(0, min(20, int(patch["max_per_day"])))
    await db.app_settings.update_one({"key": SETTINGS_KEY}, {"$set": {"key": SETTINGS_KEY, **cur}}, upsert=True)
    return cur


# ------------------------------------------------------------------ texto
async def compose(article: dict) -> dict:
    """Gera textos curtos PT-PT por rede a partir do artigo."""
    aud = "profissionais da construção" if article.get("audience") == "pros" else "particulares que vão fazer obras"
    raw = await _complete(
        "És o gestor de redes sociais do ConstruPilot (construção, Portugal). Escreves em português europeu, "
        "tom próximo e profissional, sem exageros, sem inventar números nem promessas. Nada de normas francesas.",
        f"Artigo: {article.get('title')}\nResumo: {article.get('meta_description') or article.get('excerpt') or ''}\n"
        f"Público: {aud}\n\nEscreve:\n- facebook: 2-3 frases + pergunta ao público (máx. 400 caracteres), sem link no texto;\n"
        "- instagram: 3-5 frases curtas + 'Link na bio' + 5-8 hashtags PT relevantes (máx. 900 caracteres);\n"
        "- linkedin: 3-4 frases profissionais com um insight prático + 3 hashtags (máx. 700 caracteres).\n"
        'Responde APENAS em JSON: {"facebook": "...", "instagram": "...", "linkedin": "..."}',
        feature="ceo_social")
    data = _json(raw, {}) or {}
    base = article.get("meta_description") or article.get("title") or ""
    return {k: (data.get(k) or base)[:2000] for k in ("facebook", "instagram", "linkedin")}


def article_url(article: dict) -> str:
    return article.get("published_url") or f"{SITE_URL}/blog/{article['slug']}"


def image_url(article: dict) -> str | None:
    img = article.get("hero_image_url")
    if not img:
        return None
    return SITE_URL + img if img.startswith("/") else img


# ------------------------------------------------------------------ Meta
async def _meta(client: httpx.AsyncClient, path: str, data: dict) -> dict:
    r = await client.post(f"https://graph.facebook.com/{meta_version()}/{path}",
                          data={**data, "access_token": _env("META_PAGE_ACCESS_TOKEN")})
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:300]}
    if r.status_code >= 400 or "error" in body:
        e = body.get("error") or {}
        raise SocialError(f"Meta {path}: {e.get('message') or body} (code {e.get('code', r.status_code)})")
    return body


async def post_facebook(text: str, link: str) -> dict:
    if not status()["facebook"]["configured"]:
        raise SocialError("Facebook não configurado")
    async with httpx.AsyncClient(timeout=40) as c:
        res = await _meta(c, f"{_env('META_PAGE_ID')}/feed", {"message": text, "link": link})
    return {"id": res.get("id"), "url": f"https://www.facebook.com/{res.get('id')}" if res.get("id") else None}


async def post_instagram(caption: str, image: str) -> dict:
    if not status()["instagram"]["configured"]:
        raise SocialError("Instagram não configurado")
    ig = _env("META_IG_USER_ID")
    async with httpx.AsyncClient(timeout=90) as c:
        container = await _meta(c, f"{ig}/media", {"image_url": image, "caption": caption})
        res = await _meta(c, f"{ig}/media_publish", {"creation_id": container["id"]})
    return {"id": res.get("id")}


# ------------------------------------------------------------------ LinkedIn
async def post_linkedin(text: str, link: str, title: str, description: str) -> dict:
    if not status()["linkedin"]["configured"]:
        raise SocialError("LinkedIn não configurado")
    body = {
        "author": f"urn:li:organization:{_env('LINKEDIN_ORG_ID')}",
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "content": {"article": {"source": link, "title": title[:200], "description": (description or "")[:250]}},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    headers = {"Authorization": f"Bearer {_env('LINKEDIN_ACCESS_TOKEN')}", "LinkedIn-Version": linkedin_version(),
               "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post("https://api.linkedin.com/rest/posts", json=body, headers=headers)
    if r.status_code >= 400:
        raise SocialError(f"LinkedIn HTTP {r.status_code}: {r.text[:300]}")
    return {"id": r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id")}


# ------------------------------------------------------------------ partilha de um artigo
async def share_article(article: dict, networks: list[str] | None = None) -> dict:
    networks = networks or (await get_settings())["networks"]
    st = status()
    texts = await compose(article)
    link, img = article_url(article), image_url(article)
    done = dict(article.get("social") or {})
    results = {}
    for net in networks:
        if done.get(net, {}).get("id"):
            results[net] = {"skipped": "já partilhado"}
            continue
        if not st.get(net, {}).get("configured"):
            results[net] = {"skipped": "não configurado"}
            continue
        try:
            if net == "facebook":
                res = await post_facebook(texts["facebook"], link)
            elif net == "instagram":
                if not img:
                    results[net] = {"skipped": "artigo sem imagem"}
                    continue
                res = await post_instagram(texts["instagram"], img)
            else:
                res = await post_linkedin(texts["linkedin"], link, article.get("title") or "",
                                          article.get("meta_description") or "")
            done[net] = {**res, "at": _now(), "text": texts[net]}
            results[net] = {"ok": True, **res}
        except Exception as e:  # noqa: BLE001
            log.error("Social %s failed for %s: %s", net, article.get("slug"), e)
            results[net] = {"error": str(e)[:300]}
            done[net] = {"error": str(e)[:300], "at": _now()}
    await db.autoseo_articles.update_one({"autoseo_id": article["autoseo_id"]},
                                         {"$set": {"social": done, "social_shared_at": _now()}})
    await db.social_posts.insert_one({"autoseo_id": article["autoseo_id"], "slug": article.get("slug"),
                                      "results": results, "created_at": _now()})
    return results


async def run_auto_share() -> dict:
    """Job (30 em 30 min): partilha artigos PT publicados ainda não partilhados."""
    settings = await get_settings()
    if not settings["auto_share"]:
        return {"skipped": "auto_share desligado"}
    if not any(v["configured"] for v in status().values()):
        return {"skipped": "nenhuma rede configurada"}
    today = datetime.now(timezone.utc).date().isoformat()
    shared_today = await db.social_posts.count_documents({"created_at": {"$gte": today}})
    room = settings["max_per_day"] - shared_today
    if room <= 0:
        return {"skipped": "limite diário"}
    docs = await db.autoseo_articles.find(
        {"status": "published", "language_code": {"$regex": "^pt"}, "social_shared_at": {"$exists": False}},
        {"_id": 0, "content_html": 0, "content_markdown": 0}).sort("published_at", 1).to_list(min(room, 2))
    out = []
    for a in docs:
        out.append({"slug": a.get("slug"), "results": await share_article(a, settings["networks"])})
    return {"shared": len(out), "details": out}
