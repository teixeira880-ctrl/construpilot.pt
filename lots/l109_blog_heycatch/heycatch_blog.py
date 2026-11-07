"""Blog HeyCatch (construpilot.pt) — leitura em direto da API HeyCatch, sem cópia na base de dados.

Guia : https://heycatch.ai/blog-agents.md
  · chave só em parâmetro de query `key` (variável de ambiente HEYCATCH_API_KEY) ;
  · lista paginada por offset (limit 50) até `total` ; artigo único com content_html ;
  · 401/403 → estado vazio ; 404 → 404 ; 429 → espera Retry-After e tenta uma vez ;
  · erros e timeouts nunca derrubam o site ; cache em memória de 120 s (artigos novos sem redeploy).
O HTML é limpo aqui (scripts, styles, iframes, atributos on*, URLs javascript:) antes de chegar ao navegador.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException

log = logging.getLogger("heycatch")
router = APIRouter(prefix="/blog/heycatch", tags=["blog"])
BASE = os.environ.get("HEYCATCH_API_BASE", "https://api.heycatch.ai/v1").rstrip("/")
TTL = 120.0
_cache: dict[str, tuple[float, object]] = {}

ALLOWED = {"h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "th",
           "td", "caption", "a", "blockquote", "strong", "b", "em", "i", "u", "s", "code", "pre", "sup", "sub", "span", "div",
           "section", "aside", "figure", "figcaption", "img", "details", "summary", "dl", "dt", "dd", "mark", "small", "abbr"}
DROP = {"script", "style", "iframe", "object", "embed", "noscript", "template", "form", "input", "button", "link", "meta",
        "svg", "math", "frame", "frameset", "base"}
ATTRS = {"href", "title", "id", "class", "src", "alt", "width", "height", "colspan", "rowspan", "scope", "start", "rel",
         "target", "loading", "open"}
_BAD_URL = re.compile(r"^\s*(javascript|vbscript|data):", re.I)


# Chave publicável do blog (o guia HeyCatch permite-a no código) ; HEYCATCH_API_KEY no ambiente tem prioridade.
_PUBLISHABLE_KEY = "hck_lv_cfcae4f9a95924320149f4e4"


def _key() -> str:
    return (os.environ.get("HEYCATCH_API_KEY") or _PUBLISHABLE_KEY).strip()


def sanitize_html(html: str) -> str:
    """Mantém títulos, parágrafos, listas, tabelas, ligações, citações, ênfases, código e o id dos h2."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(DROP):
        tag.decompose()
    for tag in soup.find_all("h1"):     # o título do artigo (já mostrado) é o único <h1> da página
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED:
            tag.unwrap()
            continue
        for attr in list(tag.attrs):
            val = tag.attrs[attr]
            sval = " ".join(val) if isinstance(val, list) else str(val)
            if attr.lower().startswith("on") or attr not in ATTRS or (attr in ("href", "src") and _BAD_URL.match(sval)):
                del tag.attrs[attr]
        if tag.name == "a" and tag.get("href", "").startswith("http") and "construpilot.pt" not in tag.get("href", ""):
            tag["rel"] = "noopener noreferrer"
            tag["target"] = "_blank"
    return str(soup)


async def _get(path: str, params: dict) -> tuple[int, dict]:
    """GET HeyCatch ; devolve (status, json). Nunca levanta exceção (0 = rede/timeout)."""
    key = _key()
    if not key:
        return 0, {}
    q = {**params, "key": key}
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{BASE}{path}", params=q)
        except Exception as e:  # noqa: BLE001 — rede, DNS, timeout : estado vazio
            log.warning("heycatch %s : %s", path, str(e)[:120])
            return 0, {}
        if r.status_code == 429 and attempt == 1:
            try:
                wait = min(float(r.headers.get("Retry-After", "2")), 10.0)
            except ValueError:
                wait = 2.0
            await asyncio.sleep(max(wait, 0.5))
            continue
        try:
            return r.status_code, (r.json() if r.content else {})
        except ValueError:
            return r.status_code, {}
    return 429, {}


def _cached(k: str):
    hit = _cache.get(k)
    return hit[1] if hit and time.monotonic() - hit[0] < TTL else None


def _card(a: dict) -> dict:
    return {k: a.get(k) for k in ("id", "slug", "title", "meta_description", "published", "updated", "read_time",
                                   "keywords", "featured_image", "hero_image_url", "language", "published_at", "updated_at")}


async def all_articles() -> dict:
    """Todos os artigos (mais recentes primeiro), {articles, total}. Estado vazio em 401/403/erro."""
    hit = _cached("list")
    if hit is not None:
        return hit
    out, offset, total = [], 0, None
    while True:
        st, data = await _get("/articles", {"limit": 50, "offset": offset})
        if st != 200:
            if st in (401, 403):
                log.warning("heycatch : chave recusada (%s) — blog vazio", st)
            break
        items = data.get("articles") or []
        total = int(data.get("total") or 0)
        out += [_card(a) for a in items if a.get("slug")]
        offset += len(items)
        if not items or offset >= total or offset > 5000:
            break
    res = {"articles": out, "total": len(out) if total is None else max(total, len(out)) if out else 0}
    if st == 200 or out:
        _cache["list"] = (time.monotonic(), res)
    return res


@router.get("")
async def list_articles() -> dict:
    """Lista pública (título, datas, tempo de leitura, descrição) — a página /blog pagina com ?page=."""
    return await all_articles()


@router.get("/{slug}")
async def get_article(slug: str) -> dict:
    """Artigo completo com content_html já limpo ; 404 se o slug não existir."""
    ck = f"a:{slug}"
    hit = _cached(ck)
    if hit is not None:
        return hit
    st, data = await _get(f"/articles/{quote(slug, safe='')}", {})
    if st == 404:
        raise HTTPException(404, "Artigo não encontrado")
    a = (data or {}).get("article") or {}
    if st != 200 or not a:
        raise HTTPException(503 if st not in (401, 403) else 404, "Blog indisponível")
    res = {**_card(a), "content_html": sanitize_html(a.get("content_html") or ""), "jsonLd": a.get("jsonLd") or {}}
    _cache[ck] = (time.monotonic(), res)
    return res
