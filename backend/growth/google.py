"""Google Search Console connection (OAuth 2, tokens encrypted at rest) and daily performance sync. GA4 is exposed as « à connecter »."""
import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet

from core.db import db
from growth.common import env, new_id, now_iso

logger = logging.getLogger(__name__)
SCOPES = "https://www.googleapis.com/auth/webmasters.readonly openid email"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256((env("JWT_SECRET") or "growth").encode()).digest()))


def redirect_uri() -> str:
    return f"{(env('FRONTEND_URL') or '').rstrip('/')}/api/growth/integrations/google/callback"


def status() -> dict:
    cid, sec = env("GOOGLE_GROWTH_CLIENT_ID"), env("GOOGLE_GROWTH_CLIENT_SECRET")
    return {"client_configured": bool(cid and sec), "project_id_hint": env("GOOGLE_GROWTH_PROJECT_ID"), "redirect_uri": redirect_uri(),
            "missing": [k for k, v in (("GOOGLE_GROWTH_CLIENT_ID", cid), ("GOOGLE_GROWTH_CLIENT_SECRET", sec)) if not v],
            "how_to": "Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID (Web application); acrescentar o URI de redirecionamento acima; ativar a API «Google Search Console API». Copiar Client ID / Client secret para backend/.env (ou Publish → Secrets) e reiniciar."}


ADS_SCOPES = "https://www.googleapis.com/auth/adwords openid email"


def start_url(project_id: str, user_id: str, provider: str = "google_search_console") -> str:
    state = _fernet().encrypt(json.dumps({"project_id": project_id, "user_id": user_id, "provider": provider, "t": now_iso()}).encode()).decode()
    return AUTH_URL + "?" + urlencode({"client_id": env("GOOGLE_GROWTH_CLIENT_ID"), "redirect_uri": redirect_uri(), "response_type": "code",
                                      "scope": ADS_SCOPES if provider == "google_ads" else SCOPES, "access_type": "offline", "prompt": "consent", "state": state})


async def handle_callback(code: str, state: str) -> dict:
    data = json.loads(_fernet().decrypt(state.encode(), ttl=900))
    provider = data.get("provider") or "google_search_console"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(TOKEN_URL, data={"code": code, "client_id": env("GOOGLE_GROWTH_CLIENT_ID"), "client_secret": env("GOOGLE_GROWTH_CLIENT_SECRET"),
                                               "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
        r.raise_for_status()
        tok = r.json()
        site_list = []
        if provider == "google_search_console":
            sites = await client.get("https://www.googleapis.com/webmasters/v3/sites", headers={"Authorization": f"Bearer {tok['access_token']}"})
            site_list = [s.get("siteUrl") for s in (sites.json().get("siteEntry") or [])] if sites.status_code == 200 else []
    sets = {"project_id": data["project_id"], "provider": provider, "status": "connected", "connected_at": now_iso(), "connected_by": data["user_id"],
            "tokens_enc": _fernet().encrypt(json.dumps(tok).encode()).decode(), "scope": tok.get("scope")}
    if provider == "google_search_console":
        sets.update({"sites": site_list, "site_url": None})
    await db.growth_connections.update_one({"project_id": data["project_id"], "provider": provider}, {"$set": sets}, upsert=True)
    return data


async def _access_token(conn: dict) -> str:
    tok = json.loads(_fernet().decrypt(conn["tokens_enc"].encode()))
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(TOKEN_URL, data={"refresh_token": tok.get("refresh_token"), "client_id": env("GOOGLE_GROWTH_CLIENT_ID"), "client_secret": env("GOOGLE_GROWTH_CLIENT_SECRET"), "grant_type": "refresh_token"})
        r.raise_for_status()
        return r.json()["access_token"]


async def sync(project_id: str) -> dict:
    conn = await db.growth_connections.find_one({"project_id": project_id, "provider": "google_search_console"}, {"_id": 0})
    if not conn or conn.get("status") != "connected":
        return {"ok": False, "reason": "Search Console não ligada"}
    project = await db.growth_projects.find_one({"project_id": project_id}, {"_id": 0})
    site = conn.get("site_url") or next((s for s in conn.get("sites") or [] if project["domain"] in s), None)
    if not site:
        return {"ok": False, "reason": "Nenhuma propriedade Search Console correspondente ao domínio; escolher a propriedade nas integrações", "sites": conn.get("sites")}
    token = await _access_token(conn)
    end = (datetime.now(timezone.utc) - timedelta(days=2)).date()
    start = end - timedelta(days=28)
    rows_all = {}
    async with httpx.AsyncClient(timeout=40) as client:
        for dims in (["date"], ["query"], ["page"], ["country"], ["device"]):
            body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dims, "rowLimit": 250}
            r = await client.post(f"https://www.googleapis.com/webmasters/v3/sites/{quote(site, safe='')}/searchAnalytics/query",
                                  json=body, headers={"Authorization": f"Bearer {token}"})
            if r.status_code != 200:
                return {"ok": False, "reason": f"Search Console HTTP {r.status_code}", "detail": r.text[:200]}
            rows_all[dims[0]] = [{"key": x["keys"][0], "clicks": x.get("clicks", 0), "impressions": x.get("impressions", 0), "ctr": round(x.get("ctr", 0) * 100, 2), "position": round(x.get("position", 0), 1)} for x in r.json().get("rows") or []]
    snap = {"snapshot_id": new_id("gsc"), "project_id": project_id, "site_url": site, "start": start.isoformat(), "end": end.isoformat(), "synced_at": now_iso(), "data": rows_all,
            "totals": {"clicks": sum(x["clicks"] for x in rows_all["date"]), "impressions": sum(x["impressions"] for x in rows_all["date"])},
            "limits": "Dados agregados da Search Console (atraso de ~2 dias). Não discriminam as funcionalidades IA da Google; não os apresentar como tal."}
    await db.growth_gsc_snapshots.insert_one(dict(snap))
    await db.growth_connections.update_one({"project_id": project_id, "provider": "google_search_console"}, {"$set": {"last_sync": now_iso(), "site_url": site}})
    snap.pop("_id", None)
    return {"ok": True, **snap}
