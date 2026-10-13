"""Publication directe des annonces approuvées : Google Ads (REST, campagne Search + RSA, tout en PAUSED) et
Meta Marketing API (campagne OUTCOME_TRAFFIC + ad set + créa lien + annonce, tout en PAUSED). Activation = geste explicite."""
import hashlib
import hmac
import json
import logging
import re

import httpx

from core.db import db
from growth.common import env, now_iso

logger = logging.getLogger(__name__)
GADS_V = env("GOOGLE_ADS_VERSION") or "v25"
META_V = env("META_API_VERSION") or "v25.0"


class ConnectorError(Exception):
    pass


def _digits(v: str) -> str:
    return re.sub(r"\D", "", v or "")


# ---------- état ----------
async def status(project_id: str) -> dict:
    conn = await db.growth_connections.find_one({"project_id": project_id, "provider": "google_ads", "status": "connected"}, {"_id": 0, "tokens_enc": 0})
    g_missing = [k for k in ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CUSTOMER_ID") if not env(k)]
    if not conn:
        g_missing.append("Autorização Google (botão «Autorizar Google Ads»)")
    m_missing = [k for k in ("META_ADS_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "META_PAGE_ID") if not env(k)]
    return {"google": {"configured": not g_missing, "missing": g_missing, "oauth_connected": bool(conn), "connected_at": (conn or {}).get("connected_at"),
                       "customer_id": env("GOOGLE_ADS_CUSTOMER_ID"), "login_customer_id": env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
                       "how_to": "Developer token: Google Ads → conta de administrador → Ferramentas → Centro de API. Customer ID: no canto superior direito do Google Ads (sem hífenes). Depois «Autorizar Google Ads» (scope adwords)."},
            "meta": {"configured": not m_missing, "missing": m_missing, "ad_account_id": env("META_AD_ACCOUNT_ID"), "page_id": env("META_PAGE_ID"),
                     "how_to": "Meta Business Settings → Utilizadores do sistema → token com ads_management, ads_read, pages_read_engagement; Ad Account ID (act_…) e Page ID."}}


# ---------- Google Ads ----------
async def _google_token(project_id: str) -> str:
    from growth import google as g
    conn = await db.growth_connections.find_one({"project_id": project_id, "provider": "google_ads", "status": "connected"}, {"_id": 0})
    if not conn:
        raise ConnectorError("Google Ads não autorizado: clique em «Autorizar Google Ads»")
    return await g._access_token(conn)


async def _gads_mutate(client: httpx.AsyncClient, token: str, customer_id: str, resource: str, body: dict) -> dict:
    headers = {"Authorization": f"Bearer {token}", "developer-token": env("GOOGLE_ADS_DEVELOPER_TOKEN"), "Content-Type": "application/json"}
    if env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
        headers["login-customer-id"] = _digits(env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"))
    r = await client.post(f"https://googleads.googleapis.com/{GADS_V}/customers/{customer_id}/{resource}:mutate", headers=headers, json=body)
    if r.is_error:
        try:
            detail = r.json()
            msg = (detail.get("error") or {}).get("message") or str(detail)[:300]
        except ValueError:
            msg = r.text[:300]
        raise ConnectorError(f"Google Ads {resource} : HTTP {r.status_code} — {msg}")
    return r.json()


async def publish_google(project: dict, ad: dict, daily_budget_eur: float = 10.0, validate_only: bool = False) -> dict:
    g = ad["platforms"]["google"]
    if len(g["headlines"]) < 3 or len(g["descriptions"]) < 2:
        raise ConnectorError("RSA incompleto: mínimo 3 títulos e 2 descrições")
    token = await _google_token(project["project_id"])
    cid = _digits(env("GOOGLE_ADS_CUSTOMER_ID"))
    name = f"Growth {project['key'].upper()} · {ad['title'][:80]}"
    micros = str(round(daily_budget_eur * 1_000_000))
    out = {"platform": "google", "status": "PAUSED", "customer_id": cid, "created_at": now_iso(), "validate_only": validate_only}
    async with httpx.AsyncClient(timeout=40) as client:
        budget = await _gads_mutate(client, token, cid, "campaignBudgets", {"operations": [{"create": {"name": f"{name} budget", "amountMicros": micros, "deliveryMethod": "STANDARD", "explicitlyShared": False}}], "validateOnly": validate_only})
        if validate_only:
            return {**out, "validated": True}
        out["budget"] = budget["results"][0]["resourceName"]
        camp = await _gads_mutate(client, token, cid, "campaigns", {"operations": [{"create": {
            "name": name, "status": "PAUSED", "advertisingChannelType": "SEARCH", "campaignBudget": out["budget"], "manualCpc": {"enhancedCpcEnabled": False},
            "networkSettings": {"targetGoogleSearch": True, "targetSearchNetwork": True, "targetContentNetwork": False, "targetPartnerSearchNetwork": False}}}]})
        out["campaign"] = camp["results"][0]["resourceName"]
        grp = await _gads_mutate(client, token, cid, "adGroups", {"operations": [{"create": {"name": ad["title"][:100], "campaign": out["campaign"], "status": "PAUSED", "type": "SEARCH_STANDARD", "cpcBidMicros": "1000000"}}]})
        out["ad_group"] = grp["results"][0]["resourceName"]
        if g["keywords"]:
            kw = await _gads_mutate(client, token, cid, "adGroupCriteria", {"operations": [{"create": {"adGroup": out["ad_group"], "status": "ENABLED", "keyword": {"text": k, "matchType": "PHRASE"}}} for k in g["keywords"]], "partialFailure": True})
            out["keywords"] = len(kw.get("results") or [])
        rsa = {"headlines": [{"text": h} for h in g["headlines"]], "descriptions": [{"text": d} for d in g["descriptions"]]}
        if g.get("path1"):
            rsa["path1"] = g["path1"]
        if g.get("path2") and g.get("path1"):
            rsa["path2"] = g["path2"]
        ad_res = await _gads_mutate(client, token, cid, "adGroupAds", {"operations": [{"create": {"adGroup": out["ad_group"], "status": "PAUSED", "ad": {"finalUrls": [ad["final_url"]], "responsiveSearchAd": rsa}}}]})
        out["ad"] = ad_res["results"][0]["resourceName"]
    out["manage_url"] = f"https://ads.google.com/aw/campaigns?ocid={cid}"
    return out


# ---------- Meta ----------
def _meta_auth() -> dict:
    tok = env("META_ADS_ACCESS_TOKEN")
    d = {"access_token": tok}
    if env("META_APP_SECRET"):
        d["appsecret_proof"] = hmac.new(env("META_APP_SECRET").encode(), tok.encode(), hashlib.sha256).hexdigest()
    return d


async def _meta_post(client: httpx.AsyncClient, path: str, data: dict) -> dict:
    form = {k: json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else str(v) for k, v in {**data, **_meta_auth()}.items()}
    r = await client.post(f"https://graph.facebook.com/{META_V}/{path}", data=form)
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:300]}
    if r.status_code >= 400 or "error" in body:
        e = body.get("error") or body
        raise ConnectorError(f"Meta {path} : {e.get('message') if isinstance(e, dict) else e} (code {e.get('code') if isinstance(e, dict) else r.status_code})")
    return body


async def meta_health() -> dict:
    if not env("META_ADS_ACCESS_TOKEN"):
        raise ConnectorError("META_ADS_ACCESS_TOKEN em falta")
    async with httpx.AsyncClient(timeout=20) as client:
        params = {"access_token": env("META_ADS_ACCESS_TOKEN"), "fields": "id,name,currency,account_status"}
        r = await client.get(f"https://graph.facebook.com/{META_V}/act_{_digits(env('META_AD_ACCOUNT_ID'))}", params=params)
        body = r.json()
        if "error" in body:
            raise ConnectorError(f"Meta : {body['error'].get('message')}")
        perms = await client.get(f"https://graph.facebook.com/{META_V}/me/permissions", params={"access_token": env("META_ADS_ACCESS_TOKEN")})
        granted = {p["permission"] for p in (perms.json().get("data") or []) if p.get("status") == "granted"} if perms.status_code == 200 else set()
    return {"account": body, "granted": sorted(granted), "missing_scopes": sorted({"ads_management", "ads_read", "pages_read_engagement"} - granted) if granted else []}


async def publish_meta(project: dict, ad: dict, daily_budget_eur: float = 10.0) -> dict:
    m = ad["platforms"]["meta"]
    if not m["primary_texts"] or not m["headlines"]:
        raise ConnectorError("Criativo Meta incompleto")
    acct = _digits(env("META_AD_ACCOUNT_ID"))
    name = f"Growth {project['key'].upper()} · {ad['title'][:80]}"
    country = "PT" if project["key"] == "pt" else "FR"
    out = {"platform": "meta", "status": "PAUSED", "created_at": now_iso()}
    async with httpx.AsyncClient(timeout=40) as client:
        camp = await _meta_post(client, f"act_{acct}/campaigns", {"name": name, "objective": "OUTCOME_TRAFFIC", "status": "PAUSED", "special_ad_categories": []})
        out["campaign_id"] = camp["id"]
        adset = await _meta_post(client, f"act_{acct}/adsets", {"name": f"{name} — {country}", "campaign_id": camp["id"], "daily_budget": round(daily_budget_eur * 100), "billing_event": "IMPRESSÕES",
                                                                 "optimization_goal": "LINK_CLICKS", "status": "PAUSED", "targeting": {"geo_locations": {"countries": [country]}}})
        out["adset_id"] = adset["id"]
        creative = await _meta_post(client, f"act_{acct}/adcreatives", {"name": f'{name} — criativo', "object_story_spec": {"page_id": env("META_PAGE_ID"), "link_data": {
            "message": m["primary_texts"][0], "link": ad["final_url"], "name": m["headlines"][0], "description": (m["descriptions"] or [""])[0],
            "call_to_action": {"type": m.get("cta") or "LEARN_MORE", "value": {"link": ad["final_url"]}}}}})
        out["creative_id"] = creative["id"]
        adr = await _meta_post(client, f"act_{acct}/ads", {"name": f"{name} — annonce", "adset_id": adset["id"], "creative": {"creative_id": creative["id"]}, "status": "PAUSED"})
        out["ad_id"] = adr["id"]
    out["manage_url"] = f"https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={acct}"
    return out
