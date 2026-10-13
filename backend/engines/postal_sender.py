"""Require a real, complete sender before preparing a postal quote or shipment."""
from fastapi import HTTPException


def require_sender_branding(branding: dict | None, *, organization: bool = False) -> dict:
    branding = dict(branding or {})
    required = ("address", "postal_code", "city")
    missing = [field for field in required if not str(branding.get(field) or "").strip()]
    if missing:
        raise HTTPException(400, {
            "code": "sender_address_required",
            "message": "Complétez l’adresse d’expédition de votre entreprise dans Identité pro : adresse, code postal et ville.",
            "fields": missing,
            "source": "organization" if organization else "user",
            "action_url": "/entreprise",
        })
    return branding