"""SSRF-safe site audit: sitemap + BFS crawl of public pages, on-page checks, evidence-based issues."""
import asyncio
import ipaddress
import json
import logging
import re
import socket
import time
import urllib.robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from core.db import db
from growth.common import new_id, now_iso

logger = logging.getLogger(__name__)
UA = "ConstruPilotGrowthBot/1.0 (+https://construpilot.pt) audit interne"
# Le HTML analysé est celui servi aux robots d'indexation (pré-rendu Cloudflare) : même vue que Google.
FETCH_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html) ConstruPilotGrowthBot/1.0"
MAX_BYTES = 2_000_000
PRIVATE_PREFIXES = ("/login", "/admin", "/dashboard", "/project/", "/plan", "/signature/", "/suivi-devis", "/billing", "/api/", "/assistant", "/devis", "/factures", "/clients", "/corbeille")


def _safe_host(host: str) -> bool:
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
        return True
    except Exception:
        return False


def _same_site(url: str, domain: str) -> bool:
    h = (urlparse(url).hostname or "").lower()
    return h == domain or h == f"www.{domain}"


def _norm(url: str) -> str:
    url, _ = urldefrag(url)
    p = urlparse(url)
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return f"{p.scheme}://{p.netloc}{path}" + (f"?{p.query}" if p.query else "")


async def _fetch(client: httpx.AsyncClient, url: str) -> dict:
    """Manual redirect following so every hop is validated against private networks."""
    hops, cur = [], url
    t0 = time.monotonic()
    for _ in range(6):
        p = urlparse(cur)
        if p.scheme not in ("http", "https") or not p.hostname or not _safe_host(p.hostname):
            return {"url": url, "final_url": cur, "status_code": None, "error": "anfitrião não autorizado (endereço privado ou esquema inválido)", "hops": hops}
        try:
            r = await client.get(cur, headers={"User-Agent": FETCH_UA, "Accept": "text/html,*/*;q=0.8"}, follow_redirects=False)
        except Exception as e:
            return {"url": url, "final_url": cur, "status_code": None, "error": f"{type(e).__name__}", "hops": hops}
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            hops.append({"from": cur, "to": urljoin(cur, r.headers["location"]), "status": r.status_code})
            cur = urljoin(cur, r.headers["location"])
            continue
        body = r.content[:MAX_BYTES]
        return {"url": url, "final_url": cur, "status_code": r.status_code, "hops": hops, "load_ms": int((time.monotonic() - t0) * 1000),
                "content_type": r.headers.get("content-type", ""), "html": body.decode(r.encoding or "utf-8", errors="replace") if "html" in r.headers.get("content-type", "") else "",
                "size": len(body), "x_robots": r.headers.get("x-robots-tag")}
    return {"url": url, "final_url": cur, "status_code": None, "error": "demasiados redirecionamentos", "hops": hops}


def _analyze(html: str, url: str, domain: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    md = soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)})
    robots = soup.find("meta", attrs={"name": re.compile("^robots$", re.IGNORECASE)})
    canonical = soup.find("link", rel=lambda v: v and "canonical" in v)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    hreflang = [{"lang": l.get("hreflang"), "href": l.get("href")} for l in soup.find_all("link", rel=lambda v: v and "alternate" in v) if l.get("hreflang")]
    jsonld = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
            for d in (data if isinstance(data, list) else [data]):
                if isinstance(d, dict):
                    jsonld.append(d.get("@type") if isinstance(d.get("@type"), str) else ",".join(d.get("@type") or []) or "?")
        except Exception:
            jsonld.append("invalide")
    links_int, links_ext = set(), set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        full = _norm(urljoin(url, href))
        (links_int if _same_site(full, domain) else links_ext).add(full)
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    imgs = soup.find_all("img")
    return {"title": title, "meta_description": (md.get("content") or "").strip() if md else "", "h1": [h.get_text(" ", strip=True) for h in soup.find_all("h1")],
            "h2": [h.get_text(" ", strip=True) for h in soup.find_all("h2")][:20], "canonical": canonical.get("href") if canonical else None,
            "robots_meta": (robots.get("content") or "") if robots else "", "viewport": bool(viewport), "hreflang": hreflang, "jsonld_types": jsonld,
            "lang_attr": (soup.html.get("lang") if soup.html else None), "internal_links": sorted(links_int)[:300], "external_links_count": len(links_ext),
            "word_count": len(text.split()), "images_without_alt": sum(1 for i in imgs if not (i.get("alt") or "").strip()), "images": len(imgs)}


def _issues(page: dict, project: dict, audit_id: str) -> list[dict]:
    out = []
    url = page["url"]

    def add(kind, severity, evidence, consequence, fix, effort="faible", fact=True):
        out.append({"issue_id": new_id("iss"), "audit_id": audit_id, "project_id": project["project_id"], "url": url, "kind": kind, "severity": severity,
                    "evidence": evidence, "observed_at": page["fetched_at"], "consequence": consequence, "fix": fix, "effort": effort, "is_fact": fact, "status": "open"})
    sc = page.get("status_code")
    if sc is None:
        add("inaccessible", "haute", f"Erro de obtenção: {page.get('error')}", "Página não explorável pelos motores", "Verificar o alojamento / o redirecionamento", "moyen"); return out
    if sc >= 400:
        add("http_error", "haute", f"HTTP {sc}", "Página fora do índice, ligações recebidas desperdiçadas", "Corrigir ou redirecionar (301) para a página equivalente", "faible"); return out
    if len(page.get("hops") or []) > 1:
        add("redirect_chain", "moyenne", f"{len(page['hops'])} redirections : " + " → ".join(h["to"] for h in page["hops"]), "Perda de tempo de carregamento e de sinal", "Redirecionar diretamente para o URL final")
    if not page.get("has_html"):
        add("no_html", "moyenne", f"Content-Type {page.get('content_type')}", "Conteúdo não legível como HTML", "Servir HTML aos motores", "moyen"); return out
    if page.get("word_count", 0) < 80:
        add("thin_html", "haute", f"{page['word_count']} palavras no HTML inicial", "Aplicação renderizada no cliente: os motores e as IA podem ver uma página quase vazia", "Pré-renderização / SSR ou HTML estático para as páginas públicas", "élevé", fact=True)
    if not page["title"]:
        add("missing_title", "haute", "Etiqueta <title> vazia ou ausente", "Título genérico nos resultados", "Acrescentar um título único de 50–60 caracteres")
    elif len(page["title"]) > 65:
        add("long_title", "basse", f"Título de {len(page['title'])} caracteres: «{page['title'][:80]} »", "Título truncado nos resultados", "Encurtar para menos de 60 caracteres")
    if not page["meta_description"]:
        add("missing_description", "moyenne", "Meta description ausente", "Excerto escolhido automaticamente pelo motor", "Acrescentar uma descrição de 140–160 caracteres")
    elif len(page["meta_description"]) > 170:
        add("long_description", "basse", f"Descrição de {len(page['meta_description'])} caractères", "Descrição truncada", "Encurtar para menos de 160 caracteres")
    if not page["h1"]:
        add("missing_h1", "moyenne", "Nenhum <h1>", "Tema principal não explícito", "Acrescentar um H1 único")
    elif len(page["h1"]) > 1:
        add("multiple_h1", "basse", f"{len(page['h1'])} balises H1 : {page['h1'][:3]}", "Hierarquia ambígua", "Manter apenas um H1")
    if not page["canonical"]:
        add("missing_canonical", "moyenne", "Nenhuma etiqueta canonical", "Risco de duplicados entre variantes de URL", "Acrescentar <link rel=canonical>")
    elif _norm(urljoin(url, page["canonical"])) != _norm(page.get("final_url") or url):
        add("canonical_mismatch", "moyenne", f"canonical = {page['canonical']} ≠ URL finale {page.get('final_url')}", "A página indica outro URL como versão principal", "Verificar se a canonical é intencional", fact=True)
    if "noindex" in (page["robots_meta"] or "").lower() or "noindex" in (page.get("x_robots") or "").lower():
        add("noindex", "haute", f"robots = {page['robots_meta'] or page.get('x_robots')}", "Página explicitamente excluída do índice", "Retirar noindex se a página tiver de ser visível", fact=True)
    if not page["viewport"]:
        add("no_viewport", "moyenne", "Meta viewport ausente", "Legibilidade móvel degradada", "Acrescentar <meta name=viewport>")
    if not page.get("lang_attr"):
        add("missing_lang", "basse", "Atributo lang ausente em <html>", "Língua não declarada", f'''Acrescentar lang="{project['language'][:2]}"''')
    elif not page["lang_attr"].lower().startswith(project["language"][:2]):
        add("lang_mismatch", "moyenne", f'''lang="{page['lang_attr']}" para um site {project['language']}''', "Língua declarada incoerente", "Corrigir o atributo lang", fact=True)
    if not page["hreflang"]:
        add("missing_hreflang", "basse", "Nenhum hreflang", "Correspondência FR/PT não declarada (hipótese: página equivalente existente)", "Acrescentar hreflang fr-FR / pt-PT se existir uma página equivalente", fact=False)
    else:
        langs = {h["lang"].lower() for h in page["hreflang"] if h.get("lang")}
        if not any(l.startswith("x-default") for l in langs):
            add("hreflang_no_default", "basse", f'hreflang presentes: {sorted(langs)}', "Sem versão predefinida", "Acrescentar x-default")
    if "invalide" in page["jsonld_types"]:
        add("jsonld_invalid", "moyenne", "Bloco JSON-LD não analisável", "Dados estruturados ignorados", "Corrigir a sintaxe JSON-LD", fact=True)
    if page.get("images_without_alt"):
        add("img_alt", "basse", f"{page['images_without_alt']}/{page['images']} imagens sem alt", "Acessibilidade e compreensão dos elementos visuais reduzidas", "Acrescentar textos alternativos")
    if (page.get("load_ms") or 0) > 3000:
        add("slow_response", "basse", f"Resposta HTML em {page['load_ms']} ms (HTML pré-renderizado servido aos robôs; o tempo real do utilizador não é medido aqui)",
            "Tempo de resposta elevado para os robôs (hipótese: latência da pré-renderização, não Core Web Vitals)", "Verificar a pré-renderização / cache no alojamento", "moyen", fact=False)
    if page.get("size", 0) > 1_000_000:
        add("heavy_html", "basse", f"HTML de {page['size']//1024} ko", "Page lourde", "Reduzir o HTML inicial")
    return out


async def run_audit(audit_id: str):
    audit = await db.growth_audits.find_one({"audit_id": audit_id}, {"_id": 0})
    project = await db.growth_projects.find_one({"project_id": audit["project_id"]}, {"_id": 0})
    domain, base = project["domain"], project["site_url"].rstrip("/")
    max_pages = int(audit.get("max_pages") or 50)
    await db.growth_audits.update_one({"audit_id": audit_id}, {"$set": {"status": "running", "started_at": now_iso(), "progress": 0}})
    rp = urllib.robotparser.RobotFileParser()
    facts = {"robots_txt": None, "sitemap_urls": 0, "sitemaps": []}
    queue, seen, pages, issues = [], set(), [], []
    try:
        async with httpx.AsyncClient(timeout=20, verify=True) as client:
            r = await _fetch(client, f"{base}/robots.txt")
            if r.get("status_code") == 200 and r.get("html") is not None:
                txt = r.get("html") or ""
                try:
                    raw = await client.get(f"{base}/robots.txt", headers={"User-Agent": UA})
                    txt = raw.text
                except Exception:
                    pass
                rp.parse(txt.splitlines()); facts["robots_txt"] = "présent"
                facts["sitemaps"] = [l.split(":", 1)[1].strip() for l in txt.splitlines() if l.lower().startswith("sitemap:")]
            else:
                facts["robots_txt"] = f"absent (HTTP {r.get('status_code')})"
                rp.parse([])
            sitemaps = facts["sitemaps"] or [f"{base}/sitemap.xml"]
            si = 0
            while si < len(sitemaps) and si < 10:
                sm = sitemaps[si]; si += 1
                if not _same_site(sm, domain):
                    continue
                try:
                    raw = await client.get(sm, headers={"User-Agent": UA})
                    if raw.status_code == 200:
                        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", raw.text)
                        for loc in locs:
                            if loc.endswith(".xml") and _same_site(loc, domain) and loc not in sitemaps and len(sitemaps) < 10:
                                sitemaps.append(loc)
                            elif _same_site(loc, domain):
                                facts["sitemap_urls"] += 1
                                if _norm(loc) not in seen:
                                    seen.add(_norm(loc)); queue.append(_norm(loc))
                    else:
                        issues.append({"issue_id": new_id("iss"), "audit_id": audit_id, "project_id": project["project_id"], "url": sm, "kind": "sitemap_missing", "severity": "moyenne",
                                       "evidence": f"HTTP {raw.status_code}", "observed_at": now_iso(), "consequence": "Descoberta das páginas mais lenta", "fix": "Publicar um sitemap XML válido", "effort": "faible", "is_fact": True, "status": "open"})
                except Exception as e:
                    logger.info("sitemap %s: %s", sm, e)
            if _norm(base + "/") not in seen:
                seen.add(_norm(base + "/")); queue.insert(0, _norm(base + "/"))
            sem = asyncio.Semaphore(4)

            async def work(u):
                async with sem:
                    res = await _fetch(client, u)
                    page = {**res, "audit_id": audit_id, "project_id": project["project_id"], "fetched_at": now_iso()}
                    page["has_html"] = bool(page.get("html"))
                    if page.get("html"):
                        page.update(_analyze(page["html"], u, domain))
                    page.pop("html", None)
                    return page
            while queue and len(pages) < max_pages:
                a = await db.growth_audits.find_one({"audit_id": audit_id}, {"_id": 0, "stop_requested": 1})
                if a and a.get("stop_requested"):
                    break
                batch = []
                while queue and len(batch) < 4 and len(pages) + len(batch) < max_pages:
                    u = queue.pop(0)
                    path = urlparse(u).path
                    if path.startswith(PRIVATE_PREFIXES) or not rp.can_fetch(UA, u):
                        continue
                    batch.append(u)
                results = await asyncio.gather(*[work(u) for u in batch])
                for page in results:
                    pages.append(page)
                    issues.extend(_issues(page, project, audit_id))
                    for link in page.get("internal_links") or []:
                        if link not in seen and len(seen) < max_pages * 4:
                            seen.add(link); queue.append(link)
                await db.growth_audits.update_one({"audit_id": audit_id}, {"$set": {"progress": min(99, int(len(pages) * 100 / max_pages)), "pages_crawled": len(pages)}})
            # broken internal links (only among crawled targets)
            status_by_url = {p["url"]: p.get("status_code") for p in pages}
            for p in pages:
                broken = [l for l in (p.get("internal_links") or []) if status_by_url.get(l) is not None and status_by_url[l] >= 400]
                if broken:
                    issues.append({"issue_id": new_id("iss"), "audit_id": audit_id, "project_id": project["project_id"], "url": p["url"], "kind": "broken_links", "severity": "moyenne",
                                   "evidence": f'{len(broken)} ligação(ões) interna(s) para páginas com erro: {broken[:3]}', "observed_at": now_iso(), "consequence": "Percurso interrompido, orçamento de rastreio perdido",
                                   "fix": "Corrigir ou retirar estas ligações", "effort": "faible", "is_fact": True, "status": "open"})
            titles = {}
            for p in pages:
                if p.get("title"):
                    titles.setdefault(p["title"], []).append(p["url"])
            for t, urls in titles.items():
                if len(urls) > 1:
                    issues.append({"issue_id": new_id("iss"), "audit_id": audit_id, "project_id": project["project_id"], "url": urls[0], "kind": "duplicate_title", "severity": "moyenne",
                                   "evidence": f'Título «{t[:70]}» partilhado por {len(urls)} pages : {urls[:3]}', "observed_at": now_iso(), "consequence": "Páginas em concorrência pelo mesmo título",
                                   "fix": "Diferenciar os títulos", "effort": "faible", "is_fact": True, "status": "open"})
            for p in pages:
                for h in p.get("hreflang") or []:
                    if h.get("href") and _norm(h["href"]) != _norm(p.get("final_url") or p["url"]) and not (h.get("lang") or "").startswith("x-default"):
                        try:
                            chk = await _fetch(client, h["href"])
                            if (chk.get("status_code") or 0) >= 400 or chk.get("status_code") is None:
                                issues.append({"issue_id": new_id("iss"), "audit_id": audit_id, "project_id": project["project_id"], "url": p["url"], "kind": "hreflang_target_error", "severity": "moyenne",
                                               "evidence": f"hreflang {h['lang']} → {h['href']} responde HTTP {chk.get('status_code')}", "observed_at": now_iso(), "consequence": "Correspondência de língua inutilizável",
                                               "fix": "Corrigir o destino hreflang", "effort": "faible", "is_fact": True, "status": "open"})
                        except Exception:
                            pass
        if pages:
            await db.growth_pages.insert_many([dict(p) for p in pages])
        if issues:
            await db.growth_issues.insert_many([dict(i) for i in issues])
        stopped = bool((await db.growth_audits.find_one({"audit_id": audit_id}, {"stop_requested": 1}) or {}).get("stop_requested"))
        summary = {"by_severity": {s: sum(1 for i in issues if i["severity"] == s) for s in ("haute", "moyenne", "basse")}, "by_kind": {}}
        for i in issues:
            summary["by_kind"][i["kind"]] = summary["by_kind"].get(i["kind"], 0) + 1
        await db.growth_audits.update_one({"audit_id": audit_id}, {"$set": {"status": "stopped" if stopped else "completed", "finished_at": now_iso(), "progress": 100, "pages_crawled": len(pages),
                                                                             "issues_count": len(issues), "facts": facts, "summary": summary, "note": "Indexação Google: desconhecida (Search Console não ligada) — um URL acessível não está necessariamente indexado."}})
        if (project.get("settings") or {}).get("autopilot_enabled", True):
            from growth.autopilot import after_audit
            try:
                res = await after_audit(project["project_id"], audit_id)
                await db.growth_audits.update_one({"audit_id": audit_id}, {"$set": {"autopilot": res}})
            except Exception as e:  # noqa: BLE001
                logger.warning("autopilot after audit failed: %s", e)
    except Exception as e:
        logger.exception("audit failed")
        await db.growth_audits.update_one({"audit_id": audit_id}, {"$set": {"status": "failed", "error": f"{type(e).__name__}: {e}"[:300], "finished_at": now_iso()}})
