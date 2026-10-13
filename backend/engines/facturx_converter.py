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
    def __init__(self, message: str, issues: list | None = None, hint: str | None = None):
        super().__init__(message)
        self.issues = issues or []
        self.hint = hint


def _digits(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _f(v) -> str:
    try:
        return f"{float(v or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def build_invoice_data(doc: dict, branding: dict | None) -> dict:
    """Construit l'invoice_data EN16931 attendu par facturxapi /convert."""
    from engines.facturx_gen import _real_lines, _unit_code
    branding = branding or {}
    totals = doc.get("totals") or {}
    paid = float(doc.get("paid") or 0)
    dtype = "381" if doc.get("doc_type") == "credit_note" else "380"

    client = doc.get("client") or {}
    buyer_name = (client.get("company")
                  or " ".join(filter(None, [client.get("first_name"), client.get("last_name")]))
                  or "Client")

    # Lignes réelles uniquement (on ignore sections/sous-sections/texte/saut de page)
    # avec remise appliquée, pour une base de TVA cohérente avec le PDF visuel.
    real = _real_lines(doc)
    base_by_rate: dict[float, float] = {}
    line_items = []
    net_total = 0.0
    for i, ln in enumerate(real, 1):
        qty = float(ln.get("qty") or 0)
        disc = float(ln.get("discount_pct") or 0)
        net_price = round(float(ln.get("unit_price_ht") or 0) * (1 - disc / 100), 2)
        line_ht = round(qty * net_price, 2)
        rate = float(ln.get("vat_rate") or 0)
        base_by_rate[rate] = round(base_by_rate.get(rate, 0) + line_ht, 2)
        net_total = round(net_total + line_ht, 2)
        line_items.append({
            "number": str(i),
            "description": (ln.get("designation") or ln.get("title") or "Prestation")[:200] or "Prestation",
            "quantity": f"{qty:.4f}",
            "unit": _unit_code(ln.get("unit")),
            "unit_price": f"{net_price:.2f}",
            "net_amount": f"{line_ht:.2f}",
            "vat_rate": f"{rate:.2f}",
            "vat_category": "S" if rate > 0 else "Z",
        })

    tax_breakdown = []
    tax_total = 0.0
    for rate, base in sorted(base_by_rate.items()):
        amount = round(base * rate / 100, 2)
        tax_total = round(tax_total + amount, 2)
        tax_breakdown.append({
            "rate": f"{rate:.2f}",
            "category": "S" if rate > 0 else "Z",
            "base": f"{base:.2f}",
            "amount": f"{amount:.2f}",
        })
    if not tax_breakdown:
        tax_breakdown.append({"rate": "0.00", "category": "Z", "base": f"{net_total:.2f}", "amount": "0.00"})

    # Totaux dérivés des lignes (cohérence BR-CO EN16931) ; on retombe sur doc.totals si besoin.
    net = net_total or float(totals.get("ht") or 0)
    tva = tax_total or float(totals.get("tva") or 0)
    gross = round(net + tva, 2)
    due = round(gross - paid, 2)

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
        "totals": {"net": _f(net), "tax": _f(tva), "gross": _f(gross), "due": _f(due)},
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
    validation = result.get("validation") or {}
    if not pdf_b64:
        # Conversion 200 mais refusée (ex. validation EN16931 échouée) → on remonte les motifs.
        raw_issues = validation.get("issues") or []
        issues = [{"rule": i.get("ruleId"), "bt": i.get("btCode"), "severity": i.get("severity"),
                   "message": (i.get("message") or "")[:300]}
                  for i in raw_issues if i.get("severity") == "error"][:12]
        hint = None
        rules = {i.get("rule") for i in issues}
        if {"BR-CO-26", "BR-S-02", "BR-S-08"} & rules:
            hint = ("Complétez le SIRET et/ou le numéro de TVA de votre entreprise "
                    "(Profil → Entreprise) : la norme EN 16931 les exige pour certifier la facture.")
        raise FacturxConvertError(
            f"Facture non conforme EN 16931 ({validation.get('summary', {}).get('errorCount', '?')} erreur(s))",
            issues=issues, hint=hint)
    report = {
        "valid": bool(validation.get("valid", data.get("success"))),
        "profile": validation.get("profile") or result.get("targetProfile"),
        "error_count": (validation.get("summary") or {}).get("errorCount", 0),
        "warning_count": (validation.get("summary") or {}).get("warningCount", 0),
        "issues": [],
        "source": "convert",
    }
    return base64.b64decode(pdf_b64), report
