"""Intégration Apify (scraping on-demand depuis l'admin ConstruPilot).

Le token APIFY_API_TOKEN reste exclusivement côté backend.
Modèle asynchrone : on démarre l'Actor, on stocke un job, puis le frontend
interroge l'état (évite de tenir une requête ouverte > 100 s derrière le proxy).
"""
import os
import logging

import httpx

logger = logging.getLogger(__name__)

API = "https://api.apify.com/v2"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def token() -> str:
    t = os.environ.get("APIFY_API_TOKEN")
    if not t:
        raise RuntimeError("APIFY_API_TOKEN manquant : ajoutez-le dans backend/.env")
    return t


def _headers() -> dict:
    return {"Authorization": f"Bearer {token()}"}


async def start_run(actor_id: str, run_input: dict) -> dict:
    """Démarre un run d'Actor. Retourne {id, status, defaultDatasetId}."""
    url = f"{API}/acts/{actor_id.replace('/', '~')}/runs"
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as c:
        r = await c.post(url, headers=_headers(), json=run_input)
    _raise_for(r, actor_id)
    data = r.json().get("data", r.json())
    return {"id": data["id"], "status": data.get("status"),
            "datasetId": data.get("defaultDatasetId")}


async def get_run(run_id: str) -> dict:
    url = f"{API}/actor-runs/{run_id}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(70.0, connect=10.0)) as c:
        r = await c.get(url, headers=_headers(), params={"waitForFinish": 30})
    _raise_for(r)
    data = r.json().get("data", r.json())
    return {"id": data["id"], "status": data.get("status"),
            "datasetId": data.get("defaultDatasetId")}


async def get_dataset_items(dataset_id: str, limit: int = 100) -> list[dict]:
    url = f"{API}/datasets/{dataset_id}/items"
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as c:
        r = await c.get(url, headers=_headers(),
                        params={"format": "json", "clean": "true", "limit": limit})
    _raise_for(r)
    return r.json()


def _raise_for(r: httpx.Response, actor_id: str = "") -> None:
    if r.status_code in (401, 403):
        raise ValueError("Token Apify invalide ou permissions insuffisantes")
    if r.status_code == 404:
        raise ValueError(f"Actor introuvable ou inaccessible{f' : {actor_id}' if actor_id else ''}")
    if r.status_code == 429:
        raise ValueError("Limite de débit Apify atteinte — réessayez plus tard")
    if r.is_error:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:300])
        except Exception:  # noqa: BLE001
            msg = r.text[:300]
        raise ValueError(f"Apify : {msg}")


import json as _json
import re as _re

_EMAIL_RE = _re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def extract_emails(items: list[dict]) -> list[dict]:
    """Ne garde QUE les e-mails : scanne chaque item, déduplique. Rien d'autre.

    Retourne une liste de lignes {email} uniques, triées.
    """
    found: set[str] = set()
    for it in items or []:
        blob = _json.dumps(it, ensure_ascii=False, default=str)
        for e in _EMAIL_RE.findall(blob):
            found.add(e.lower())
    return [{"email": e} for e in sorted(found)]


# Cas d'usage ConstruPilot → Actor + gabarit d'input (points de départ, éditables).
PRESETS = {
    "leads": {
        "label": "Captation de leads / prospects",
        "actor_id": "compass/crawler-google-places",
        "description": "Entreprises BTP, artisans ou prospects via Google Maps (Nice & alentours).",
        "input": {
            "searchStringsArray": [
                "rénovation", "rénovation générale", "maçon", "maçonnerie générale",
                "entreprise générale", "entreprise BTP",
                "entreprise construction de maisons individuelles",
                "peintre", "plaquiste", "électricien",
            ],
            "locationQuery": "Nice, France",
            "maxCrawledPlacesPerSearch": 25,
            "language": "fr",
            "scrapeContacts": True,
        },
    },
    "editais": {
        "label": "Appels d'offres (BOAMP · dép. 06)",
        "actor_id": "apify/website-content-crawler",
        "description": "Avis de marchés publics BOAMP : rénovation / travaux bâtiment, Alpes-Maritimes (06).",
        "input": {
            "startUrls": [{"url": "https://www.boamp.fr/pages/recherche/?q=r%C3%A9novation%20travaux%20b%C3%A2timent%2006"}],
            "maxCrawlPages": 10,
            "crawlerType": "playwright:firefox",
        },
    },
    "social": {
        "label": "Veille réseaux sociaux (TikTok)",
        "actor_id": "clockworks/free-tiktok-scraper",
        "description": "Veille TikTok fiable : hashtags métiers (#rénovation, #maçonnerie…) ou profils concurrents (ajoutez \"profiles\": [\"pseudo\"]). NB : Instagram et Facebook bloquent le scraping public via Apify ; TikTok fonctionne.",
        "input": {
            "hashtags": ["rénovation", "maçonnerie", "plaquiste", "chantier"],
            "resultsPerPage": 20,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
            "shouldDownloadSlideshowImages": False,
        },
    },
}
