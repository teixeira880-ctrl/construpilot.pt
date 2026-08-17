"""Génération d'un Factur-X PDF/A-3 conforme via facturxapi.com /convert.

On envoie le PDF visuel (porteur) + les données structurées (invoice_data) ;
le moteur renvoie un vrai Factur-X PDF/A-3 (EN16931) validé. Clé : FACTURX_API_KEY.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("facturx_converter")

BASE_URL = "https://api.facturxapi.com/api/v1"


class FacturxConvertError(Exception):
    pass


def _digits(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _f(v) -> str:
    try:
        return f"{float(v or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def build_invoice_data(doc: dict, branding: dict | None) -> dict:
    """Construit l'invoice_data EN16931 attendu par facturxapi /convert."""
    branding = branding or {}
    totals = doc.get("totals") or {}
    ht = float(totals.get("ht") or 0)
    tva = float(totals.get("tva") or 0)
    ttc = float(totals.get("ttc") or 0)
    paid = float(doc.get("paid") or 0)
    due = round(ttc - paid, 2)
    dtype = "381" if doc.get("doc_type") == "credit_note" else "380"

    client = doc.get("client") or {}
    buyer_name = (client.get("company")
                  or " ".join(filter(None, [client.get("first_name"), client.get("last_name")]))
                  or "Client")

    # Bases HT par taux (somme des lignes arrondies) pour la ventilation TVA.
    base_by_rate: dict[float, float] = {}
    for ln in doc.get("lines") or []:
        rate = float(ln.get("vat_rate") or 0)
        line_ht = round((ln.get("qty") or 0) * (ln.get("unit_price_ht") or 0), 2)
        base_by_rate[rate] = round(base_by_rate.get(rate, 0) + line_ht, 2)

    tax_breakdown = []
    for rate, base in sorted(base_by_rate.items()):
        amount = round(base * rate / 100, 2)
        tax_breakdown.append({
            "rate": f"{rate:.2f}",
            "category": "S" if rate > 0 else "Z",
            "base": f"{base:.2f}",
            "amount": f"{amount:.2f}",
        })
    if not tax_breakdown:
        tax_breakdown.append({"rate": "0.00", "category": "Z", "base": _f(ht), "amount": "0.00"})

    line_items = []
    for i, ln in enumerate(doc.get("lines") or [], 1):
        qty = float(ln.get("qty") or 0)
        pu = float(ln.get("unit_price_ht") or 0)
        rate = float(ln.get("vat_rate") or 0)
        line_items.append({
            "number": str(i),
            "description": (ln.get("designation") or "Article")[:200],
            "quantity": f"{qty}",
            "unit": "C62",
            "unit_price": f"{pu:.2f}",
            "net_amount": f"{round(qty * pu, 2):.2f}",
            "vat_rate": f"{rate:.2f}",
            "vat_category": "S" if rate > 0 else "Z",
        })

    seller = {
        "name": branding.get("company_name") or "ConstruPilot",
        "address": {
            "street": branding.get("address") or "1 rue de la Construction",
            "city": branding.get("city") or "Paris",
            "postal_code": branding.get("postal_code") or "75001",
            "country": (branding.get("country") or "FR")[:2].upper(),
        },
    }
    if _digits(branding.get("siret")):
        seller["siret"] = _digits(branding.get("siret"))
    if branding.get("vat"):
        seller["vat_id"] = str(branding.get("vat")).upper().replace(" ", "")

    buyer = {
        "name": buyer_name,
        "address": {
            "street": client.get("address") or "-",
            "city": client.get("city") or "-",
            "postal_code": client.get("postal_code") or "-",
            "country": "FR",
        },
    }

    issue_date = str(doc.get("issue_date") or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "invoice_number": str(doc.get("number") or doc.get("doc_id") or "FACTURE"),
        "issue_date": issue_date,
        "invoice_type": dtype,
        "currency": "EUR",
        "seller": seller,
        "buyer": buyer,
        "totals": {"net": _f(ht), "tax": _f(tva), "gross": _f(ttc), "due": _f(due)},
        "tax_breakdown": tax_breakdown,
        "line_items": line_items,
    }


async def convert_facturx(pdf_bytes: bytes, invoice_data: dict) -> tuple[bytes, dict]:
    """Renvoie (pdf_facturx_pdfa3_bytes, rapport_validation). Lève FacturxConvertError."""
    api_key = os.environ.get("FACTURX_API_KEY")
    if not api_key:
        raise FacturxConvertError("Clé FACTURX_API_KEY absente")
    url = f"{BASE_URL}/convert?lang=fr"
    form = {
        "validation_target": "en16931",
        "output": "facturx_pdfa3",
        "invoice_data": json.dumps(invoice_data),
    }
    files = {"file": ("facture.pdf", pdf_bytes, "application/pdf")}
    try:
        async with httpx.AsyncClient(timeout=150.0) as client:
            resp = await client.post(url, headers={"Authorization": f"Bearer {api_key}"},
                                     data=form, files=files)
    except httpx.HTTPError as exc:
        raise FacturxConvertError("Service Factur-X injoignable") from exc

    if resp.status_code == 401:
        raise FacturxConvertError("Clé API Factur-X invalide")
    if resp.status_code == 429:
        raise FacturxConvertError("Quota Factur-X dépassé")
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = (resp.json() or {}).get("error") or resp.text[:200]
        except Exception:
            detail = resp.text[:200]
        logger.warning("facturxapi /convert %s: %s", resp.status_code, detail)
        raise FacturxConvertError(f"Conversion refusée (HTTP {resp.status_code})")

    data = resp.json()
    result = data.get("result") or {}
    pdf_b64 = result.get("pdf")
    if not pdf_b64:
        raise FacturxConvertError("Aucun PDF Factur-X renvoyé")
    validation = result.get("validation") or {}
    report = {
        "valid": bool(validation.get("valid", data.get("success"))),
        "profile": validation.get("profile") or result.get("targetProfile"),
        "error_count": 0 if validation.get("valid") else 0,
        "warning_count": 0,
        "issues": [],
        "source": "convert",
    }
    return base64.b64decode(pdf_b64), report
