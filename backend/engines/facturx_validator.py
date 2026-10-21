"""Validation / certification d'un fichier Factur-X via l'API facturxapi.com.

Envoie le PDF Factur-X à POST /api/v1/validate (XSD + Schematron EN16931)
et renvoie un rapport simplifié. La clé API est lue dans FACTURX_API_KEY.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("facturx_validator")

BASE_URL = "https://api.facturxapi.com/api/v1"


class FacturxValidationError(Exception):
    pass


def _summarize(data: dict) -> dict:
    summary = data.get("summary") or {}
    issues = data.get("issues") or []
    # Fallback legacy: errors/warnings plates
    if not issues:
        for e in data.get("errors") or []:
            issues.append({"severity": "error", "message": e if isinstance(e, str) else str(e)})
        for w in data.get("warnings") or []:
            issues.append({"severity": "warning", "message": w if isinstance(w, str) else str(w)})
    trimmed = [
        {
            "code": i.get("code") or i.get("ruleId") or "",
            "severity": i.get("severity") or "error",
            "stage": i.get("stage") or "",
            "message": i.get("message") or "",
        }
        for i in issues[:50]
    ]
    return {
        "valid": bool(data.get("valid")),
        "profile": data.get("profile"),
        "error_count": summary.get("errorCount", sum(1 for i in trimmed if i["severity"] == "error")),
        "warning_count": summary.get("warningCount", sum(1 for i in trimmed if i["severity"] == "warning")),
        "issues": trimmed,
        "validated_at": data.get("validatedAt"),
    }


async def validate_facturx(pdf_bytes: bytes, filename: str = "facture.pdf") -> dict:
    api_key = os.environ.get("FACTURX_API_KEY")
    if not api_key:
        raise FacturxValidationError("Chave FACTURX_API_KEY ausente")
    url = f"{BASE_URL}/validate?validation_target=en16931&lang=fr"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, pdf_bytes, "application/pdf")},
            )
    except httpx.HTTPError as exc:
        logger.warning("facturxapi network error: %s", exc)
        raise FacturxValidationError("Serviço de validação de faturação eletrónica inacessível") from exc

    if resp.status_code == 401:
        raise FacturxValidationError("Chave API de faturação eletrónica inválida")
    if resp.status_code == 429:
        raise FacturxValidationError("Quota de validação de faturação eletrónica ultrapassada")
    if resp.status_code >= 400:
        logger.warning("facturxapi %s: %s", resp.status_code, resp.text[:300])
        raise FacturxValidationError(f'Validação recusada (HTTP {resp.status_code})')

    return _summarize(resp.json())
