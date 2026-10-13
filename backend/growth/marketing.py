"""Publicités et e-mails à partir des contenus publiés : textes Google Ads (RSA), Meta/Instagram, LinkedIn — validés en longueur,
exportables CSV ; newsletters FR/PT (digest des articles) envoyées via Resend aux abonnés après approbation."""
import csv
import io
import logging
import os
import re

from core.db import db
from growth import content as ct
from growth.common import new_id, now_iso

logger = logging.getLogger(__name__)

LIMITS = {"google": {"headlines": (15, 30), "descriptions": (4, 90), "keywords": (12, 80)},
          "meta": {"primary_texts": (3, 125), "headlines": (3, 40), "descriptions": (2, 30)},
          "linkedin": {"intros": (2, 150), "headlines": (2, 70)}}


def _fit(items, count: int, max_len: int) -> list[str]:
    out = []
    for it in items or []:
        t = re.sub(r"\s+", " ", str(it or "")).strip().strip('"')
        if t and len(t) <= max_len and t not in out:
            out.append(t)
    return out[:count]


def normalize_ads(data: dict) -> dict:
    out = {}
    for platform, fields in LIMITS.items():
        src = data.get(platform) or {}
        out[platform] = {k: _fit(src.get(k), n, ml) for k, (n, ml) in fields.items()}
        if platform == "meta":
            out[platform]["cta"] = (src.get("cta") or "LEARN_MORE")[:30]
    out["google"]["path1"] = re.sub(r"[^a-z0-9-]", "", (data.get("google") or {}).get("path1", "").lower())[:15]
    out["google"]["path2"] = re.sub(r"[^a-z0-9-]", "", (data.get("google") or {}).get("path2", "").lower())[:15]
    return out


def ads_complete(ads: dict) -> list[str]:
    """RSA Google exige ≥ 3 titres et ≥ 2 descriptions ; Meta ≥ 1 texte et 1 titre."""
    missing = []
    if len(ads["google"]["headlines"]) < 3: missing.append("Google : moins de 3 titres valides")
    if len(ads["google"]["descriptions"]) < 2: missing.append("Google : moins de 2 descriptions valides")
    if not ads["meta"]["primary_texts"] or not ads["meta"]["headlines"]: missing.append("Meta : texte principal ou titre manquant")
    return missing


async def generate_ads(project: dict, content: dict) -> dict:
    lang = "français de France" if project["key"] == "fr" else "portugais du Portugal"
    system = "Tu es un concepteur-rédacteur publicitaire B2B rigoureux (secteur bâtiment). JSON strict uniquement, aucune promesse non démontrable, aucun superlatif, aucun chiffre inventé."
    facts = await ct._brand_context(project["project_id"])
    prompt = f"""Article publié : « {content.get('title')} » — {content.get('description')}
URL : {content.get('published_url')}
Extrait : {(content.get('body_markdown') or '')[:1800]}
Faits CONFIRMÉS sur ConstruPilot (seuls arguments produit autorisés) :
{facts}
Rédige en {lang} des annonces qui envoient vers cet article (angle : réponse utile puis découverte de ConstruPilot).
Contraintes STRICTES de longueur (compte les caractères) :
- google.headlines : 15 titres ≤ 30 caractères, variés (question, bénéfice, chiffre générique, appel à l'action), google.descriptions : 4 descriptions ≤ 90 caractères, google.keywords : 12 mots-clés d'intention (expressions de 2 à 5 mots), google.path1/path2 ≤ 15 caractères ascii.
- meta.primary_texts : 3 textes ≤ 125 caractères, meta.headlines : 3 titres ≤ 40, meta.descriptions : 2 ≤ 30, meta.cta parmi LEARN_MORE, SIGN_UP, DOWNLOAD, GET_QUOTE.
- linkedin.intros : 2 accroches ≤ 150, linkedin.headlines : 2 titres ≤ 70.
Réponds en JSON : {{"google": {{"headlines": [], "descriptions": [], "keywords": [], "path1": "", "path2": ""}}, "meta": {{"primary_texts": [], "headlines": [], "descriptions": [], "cta": ""}}, "linkedin": {{"intros": [], "headlines": []}}}}"""
    data = ct._json(await ct._llm(system, prompt, project["project_id"], "ads_copy"))
    if "error" in data:
        raise ValueError(data["error"])
    ads = normalize_ads(data)
    final_url = f"{content.get('published_url')}?utm_source=ads&utm_medium=cpc&utm_campaign={content.get('slug') or content['content_id']}"
    return {"ad_id": new_id("ad"), "project_id": project["project_id"], "content_id": content["content_id"], "title": content.get("title"), "final_url": final_url,
            "platforms": ads, "missing": ads_complete(ads), "status": "proposed", "created_at": now_iso(), "created_by": "autopilot", "publications": []}


def google_csv(ad: dict, campaign: str) -> str:
    """Format d'import Google Ads Editor (annonce responsive sur le Réseau de Recherche + mots-clés)."""
    g = ad["platforms"]["google"]
    buf = io.StringIO(); w = csv.writer(buf)
    head = ["Campaign", "Ad Group", "Final URL", "Path 1", "Path 2"] + [f"Headline {i}" for i in range(1, 16)] + [f"Description {i}" for i in range(1, 5)]
    w.writerow(head)
    row = [campaign, ad["title"][:60], ad["final_url"], g.get("path1", ""), g.get("path2", "")] + g["headlines"] + [""] * (15 - len(g["headlines"])) + g["descriptions"] + [""] * (4 - len(g["descriptions"]))
    w.writerow(row)
    w.writerow([]); w.writerow(["Campaign", "Ad Group", "Keyword", "Criterion Type"])
    for k in g["keywords"]:
        w.writerow([campaign, ad["title"][:60], k, "Phrase"])
    return buf.getvalue()


def meta_csv(ad: dict, campaign: str) -> str:
    m = ad["platforms"]["meta"]
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Campaign Name", "Ad Set Name", "Ad Name", "Body", "Title", "Link Description", "Call to Action", "Link"])
    i = 0
    for body in m["primary_texts"]:
        for h in m["headlines"]:
            i += 1
            w.writerow([campaign, ad["title"][:60], f"{ad['title'][:40]} #{i}", body, h, (m["descriptions"] or [""])[0], m.get("cta", "LEARN_MORE"), ad["final_url"]])
    return buf.getvalue()


async def generate_newsletter(project: dict, contents: list[dict]) -> dict:
    lang_key = project["key"]
    lang = "français de France" if lang_key == "fr" else "portugais du Portugal"
    facts = await ct._brand_context(project["project_id"])
    items = [{"title": c.get("title"), "description": c.get("description"), "url": c.get("published_url")} for c in contents]
    system = "Tu es responsable éditorial d'une newsletter B2B bâtiment. JSON strict uniquement, ton sobre et utile, aucun superlatif ni promesse non démontrable."
    prompt = f"""Prépare la newsletter en {lang} présentant ces articles : {items}
Faits CONFIRMÉS sur ConstruPilot (seul contenu produit autorisé) : {facts}
Réponds en JSON : {{"subject": str (≤ 60 car., commence par une majuscule, sans emoji ni majuscules criardes), "preheader": str (≤ 90), "intro": str (2 phrases), "items": [{{"url": str, "title": str, "blurb": str (≤ 200 car.)}}], "cta_label": str (≤ 30), "cta_url": str (une page du site {project['site_url']}), "outro": str (1 phrase)}}"""
    data = ct._json(await ct._llm(system, prompt, project["project_id"], "newsletter"))
    if "error" in data:
        raise ValueError(data["error"])
    allowed = {c.get("published_url") for c in contents}
    data["items"] = [i for i in data.get("items") or [] if i.get("url") in allowed] or [{**i, "blurb": i["description"] or ""} for i in items]
    if not str(data.get("cta_url") or "").startswith(project["site_url"]):
        data["cta_url"] = project["site_url"]
    return {"newsletter_id": new_id("nl"), "project_id": project["project_id"], "lang": lang_key, "subject": (data.get("subject") or "ConstruPilot")[:60], "preheader": (data.get("preheader") or "")[:90],
            "intro": data.get("intro") or "", "items": data["items"], "cta_label": (data.get("cta_label") or "Découvrir")[:30], "cta_url": data["cta_url"], "outro": data.get("outro") or "",
            "content_ids": [c["content_id"] for c in contents], "status": "proposed", "created_at": now_iso(), "created_by": "autopilot"}


def newsletter_html(nl: dict, unsubscribe_url: str) -> str:
    from engines.emailer import wrap_html
    utm = f"utm_source=newsletter&utm_medium=email&utm_campaign={nl['newsletter_id']}"
    blocks = "".join(f"<h3 style='margin:18px 0 4px;font-size:16px'><a href='{i['url']}?{utm}' style='color:#1f5136;text-decoration:none'>{i['title']}</a></h3><p style='margin:0;color:#444'>{i.get('blurb') or ''}</p>" for i in nl["items"])
    body = f"<p style='color:#666;font-size:12px'>{nl.get('preheader','')}</p><p>{nl.get('intro','')}</p>{blocks}<p style='margin-top:18px'>{nl.get('outro','')}</p>"
    cta = f"{nl.get('cta_url')}{'&' if '?' in (nl.get('cta_url') or '') else '?'}{utm}"
    return wrap_html(nl["subject"], body, cta_url=cta, cta_label=nl.get("cta_label"), unsubscribe_url=unsubscribe_url)


async def send_newsletter(nl: dict, actor: str, test_to: str | None = None) -> dict:
    from engines.emailer import send_email
    front = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    if test_to:
        await send_email(test_to, f"[TEST] {nl['subject']}", newsletter_html(nl, f"{front}/api/newsletter/unsubscribe?token=test"), from_name="ConstruPilot")
        return {"sent": 1, "failed": 0, "test": True}
    subs = await db.newsletter_subscribers.find({"unsubscribed_at": None, "lang": nl["lang"]}, {"_id": 0, "email": 1, "token": 1}).to_list(20000)
    sent = failed = 0
    for s in subs:
        try:
            await send_email(s["email"], nl["subject"], newsletter_html(nl, f"{front}/api/newsletter/unsubscribe?token={s['token']}"), from_name="ConstruPilot")
            sent += 1
        except Exception as e:  # noqa: BLE001
            failed += 1; logger.warning("newsletter send failed %s: %s", s["email"], e)
    await db.email_campaigns.insert_one({"campaign_id": "camp_" + os.urandom(5).hex(), "subject": nl["subject"], "message": newsletter_html(nl, "#")[:5000], "recipients_count": len(subs),
                                         "recipients_sample": [s["email"] for s in subs[:50]], "sent": sent, "failed": failed, "sent_by": actor, "source": "growth_newsletter", "newsletter_id": nl["newsletter_id"], "created_at": now_iso()})
    return {"sent": sent, "failed": failed, "recipients": len(subs)}


async def on_published(project: dict, content: dict) -> None:
    """Après publication d'un article : une proposition d'annonces (une seule par contenu)."""
    if await db.growth_ads.find_one({"content_id": content["content_id"]}):
        return
    try:
        ad = await generate_ads(project, content)
        await db.growth_ads.insert_one(dict(ad))
    except Exception as e:  # noqa: BLE001
        logger.warning("ads generation failed for %s: %s", content["content_id"], e)


async def weekly_newsletter(project: dict, days: int = 7) -> dict | None:
    """Digest hebdo (proposition) des articles publiés récemment, si aucun digest ne les couvre déjà."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    covered = set()
    async for n in db.growth_newsletters.find({"project_id": project["project_id"], "status": {"$ne": "rejected"}}, {"_id": 0, "content_ids": 1}):
        covered.update(n.get("content_ids") or [])
    recent = [c async for c in db.growth_contents.find({"project_id": project["project_id"], "status": "published", "published_at": {"$gte": since}}, {"_id": 0}) if c["content_id"] not in covered]
    if not recent:
        return None
    nl = await generate_newsletter(project, recent[:5])
    await db.growth_newsletters.insert_one(dict(nl))
    return nl
