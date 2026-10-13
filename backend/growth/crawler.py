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
            return {"url": url, "final_url": cur, "status_code": None, "error": "hôte non autorisé (adresse privée ou schéma invalide)", "hops": hops}
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
    return {"url": url, "final_url": cur, "status_code": None, "error": "trop de redirections", "hops": hops}


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
        add("inaccessible", "haute", f"Erreur de récupération : {page.get('error')}", "Page non explorable par les moteurs", "Vérifier l'hébergement / la redirection", "moyen"); return out
    if sc >= 400:
        add("http_error", "haute", f"HTTP {sc}", "Page hors index, liens entrants gaspillés", "Corriger ou rediriger (301) vers la page équivalente", "faible"); return out
    if len(page.get("hops") or []) > 1:
        add("redirect_chain", "moyenne", f"{len(page['hops'])} redirections : " + " → ".join(h["to"] for h in page["hops"]), "Perte de temps de chargement et de signal", "Rediriger directement vers l'URL finale")
    if not page.get("has_html"):
        add("no_html", "moyenne", f"Content-Type {page.get('content_type')}", "Contenu non lisible comme HTML", "Servir du HTML aux moteurs", "moyen"); return out
    if page.get("word_count", 0) < 80:
        add("thin_html", "haute", f"{page['word_count']} mots dans le HTML initial", "Application rendue côté client : les moteurs et les IA peuvent voir une page presque vide", "Pré-rendu / SSR ou HTML statique pour les pages publiques", "élevé", fact=True)
    if not page["title"]:
        add("missing_title", "haute", "Balise <title> vide ou absente", "Titre générique dans les résultats", "Ajouter un titre unique de 50–60 caractères")
    elif len(page["title"]) > 65:
        add("long_title", "basse", f"Titre de {len(page['title'])} caractères : « {page['title'][:80]} »", "Titre tronqué dans les résultats", "Raccourcir sous 60 caractères")
    if not page["meta_description"]:
        add("missing_description", "moyenne", "Meta description absente", "Extrait choisi automatiquement par le moteur", "Ajouter une description de 140–160 caractères")
    elif len(page["meta_description"]) > 170:
        add("long_description", "basse", f"Description de {len(page['meta_description'])} caractères", "Description tronquée", "Raccourcir sous 160 caractères")
    if not page["h1"]:
        add("missing_h1", "moyenne", "Aucun <h1>", "Sujet principal non explicite", "Ajouter un H1 unique")
    elif len(page["h1"]) > 1:
        add("multiple_h1", "basse", f"{len(page['h1'])} balises H1 : {page['h1'][:3]}", "Hiérarchie ambiguë", "Conserver un seul H1")
    if not page["canonical"]:
        add("missing_canonical", "moyenne", "Aucune balise canonical", "Risque de doublons entre variantes d'URL", "Ajouter <link rel=canonical>")
    elif _norm(urljoin(url, page["canonical"])) != _norm(page.get("final_url") or url):
        add("canonical_mismatch", "moyenne", f"canonical = {page['canonical']} ≠ URL finale {page.get('final_url')}", "La page indique une autre URL comme version principale", "Vérifier que la canonical est volontaire", fact=True)
    if "noindex" in (page["robots_meta"] or "").lower() or "noindex" in (page.get("x_robots") or "").lower():
        add("noindex", "haute", f"robots = {page['robots_meta'] or page.get('x_robots')}", "Page explicitement exclue de l'index", "Retirer noindex si la page doit être visible", fact=True)
    if not page["viewport"]:
        add("no_viewport", "moyenne", "Meta viewport absente", "Lisibilité mobile dégradée", "Ajouter <meta name=viewport>")
    if not page.get("lang_attr"):
        add("missing_lang", "basse", "Attribut lang absent sur <html>", "Langue non déclarée", f"Ajouter lang=\"{project['language'][:2]}\"")
    elif not page["lang_attr"].lower().startswith(project["language"][:2]):
        add("lang_mismatch", "moyenne", f"lang=\"{page['lang_attr']}\" pour un site {project['language']}", "Langue déclarée incohérente", "Corriger l'attribut lang", fact=True)
    if not page["hreflang"]:
        add("missing_hreflang", "basse", "Aucun hreflang", "Correspondance FR/PT non déclarée (hypothèse : page équivalente existante)", "Ajouter hreflang fr-FR / pt-PT si une page équivalente existe", fact=False)
    else:
        langs = {h["lang"].lower() for h in page["hreflang"] if h.get("lang")}
        if not any(l.startswith("x-default") for l in langs):
            add("hreflang_no_default", "basse", f"hreflang présents : {sorted(langs)}", "Pas de version par défaut", "Ajouter x-default")
    if "invalide" in page["jsonld_types"]:
        add("jsonld_invalid", "moyenne", "Bloc JSON-LD non analysable", "Données structurées ignorées", "Corriger la syntaxe JSON-LD", fact=True)
    if page.get("images_without_alt"):
        add("img_alt", "basse", f"{page['images_without_alt']}/{page['images']} images sans alt", "Accessibilité et compréhension des visuels réduites", "Ajouter des textes alternatifs")
    if (page.get("load_ms") or 0) > 3000:
        add("slow_response", "basse", f"Réponse HTML en {page['load_ms']} ms (HTML pré-rendu servi aux robots ; le temps utilisateur réel n'est pas mesuré ici)",
            "Temps de réponse élevé pour les robots (hypothèse : latence du pré-rendu, pas Core Web Vitals)", "Vérifier le pré-rendu / cache côté hébergeur", "moyen", fact=False)
    if page.get("size", 0) > 1_000_000:
        add("heavy_html", "basse", f"HTML de {page['size']//1024} ko", "Page lourde", "Réduire le HTML initial")
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
                                       "evidence": f"HTTP {raw.status_code}", "observed_at": now_iso(), "consequence": "Découverte des pages ralentie", "fix": "Publier un sitemap XML valide", "effort": "faible", "is_fact": True, "status": "open"})
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
                                   "evidence": f"{len(broken)} lien(s) interne(s) vers des pages en erreur : {broken[:3]}", "observed_at": now_iso(), "consequence": "Parcours interrompu, budget de crawl perdu",
                                   "fix": "Corriger ou retirer ces liens", "effort": "faible", "is_fact": True, "status": "open"})
            titles = {}
            for p in pages:
                if p.get("title"):
                    titles.setdefault(p["title"], []).append(p["url"])
            for t, urls in titles.items():
                if len(urls) > 1:
                    issues.append({"issue_id": new_id("iss"), "audit_id": audit_id, "project_id": project["project_id"], "url": urls[0], "kind": "duplicate_title", "severity": "moyenne",
                                   "evidence": f"Titre « {t[:70]} » partagé par {len(urls)} pages : {urls[:3]}", "observed_at": now_iso(), "consequence": "Pages en concurrence sur le même titre",
                                   "fix": "Différencier les titres", "effort": "faible", "is_fact": True, "status": "open"})
            for p in pages:
                for h in p.get("hreflang") or []:
                    if h.get("href") and _norm(h["href"]) != _norm(p.get("final_url") or p["url"]) and not (h.get("lang") or "").startswith("x-default"):
                        try:
                            chk = await _fetch(client, h["href"])
                            if (chk.get("status_code") or 0) >= 400 or chk.get("status_code") is None:
                                issues.append({"issue_id": new_id("iss"), "audit_id": audit_id, "project_id": project["project_id"], "url": p["url"], "kind": "hreflang_target_error", "severity": "moyenne",
                                               "evidence": f"hreflang {h['lang']} → {h['href']} répond HTTP {chk.get('status_code')}", "observed_at": now_iso(), "consequence": "Correspondance de langue non exploitable",
                                               "fix": "Corriger la cible hreflang", "effort": "faible", "is_fact": True, "status": "open"})
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
                                                                             "issues_count": len(issues), "facts": facts, "summary": summary, "note": "Indexation Google : inconnue (Search Console non connectée) — une URL accessible n'est pas nécessairement indexée."}})
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
