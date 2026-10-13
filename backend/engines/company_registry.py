"""Public legal-entity candidates only; never infer a homeowner from a site."""
import os
import re

import httpx
from fastapi import HTTPException


def normalize_company(item):
    seat = item.get("siege") or {}
    legal = str(item.get("nature_juridique") or "")
    if (not legal or legal.startswith("1")
            or (item.get("complements") or {}).get("est_entrepreneur_individuel") is not False
            or item.get("statut_diffusion") != "O" or item.get("etat_administratif") != "A"
            or seat.get("statut_diffusion_etablissement") != "O"
            or seat.get("etat_administratif") != "A" or seat.get("est_siege") is not True):
        return None
    siren = str(item.get("siren") or "")
    name = item.get("nom_raison_sociale") or item.get("nom_complet")
    if not re.fullmatch(r"\d{9}", siren) or not name or not seat.get("adresse"):
        return None
    street = " ".join(str(seat.get(k) or "").strip() for k in
                      ("numero_voie", "indice_repetition", "type_voie", "libelle_voie")).strip()
    street = re.sub(r"\s+", " ", street)
    return {"nom": name, "siren": siren, "siret": seat.get("siret") or "",
            "adresse1": street, "adresse2": seat.get("complement_adresse") or "",
            "cp": seat.get("code_postal") or "", "ville": seat.get("libelle_commune") or "",
            "societe": "", "email": "", "telephone": "",
            "adresse_complete": seat["adresse"],
            "source_url": f'{os.environ["COMPANY_REGISTRY_SOURCE_URL"].rstrip("/")}/{siren}'}


async def search_companies(query):
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(os.environ["COMPANY_REGISTRY_SEARCH_URL"],
                                        params={"q": query, "per_page": 10, "etat_administratif": "A"},
                                        headers={"Accept": "application/json", "User-Agent": "ConstruPilot-Radar/1.0"})
        if response.status_code == 429:
            raise HTTPException(429, "Annuaire temporairement saturé. Réessayez dans quelques instants.")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("Unexpected registry response")
    except httpx.TimeoutException:
        raise HTTPException(504, "L'annuaire ne répond pas dans le délai prévu.")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Annuaire indisponible. Vous pouvez saisir des coordonnées connues manuellement.")
    return [candidate for item in payload["results"] if (candidate := normalize_company(item))]