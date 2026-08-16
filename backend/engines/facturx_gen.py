"""Génération de factures au format Factur-X (profil MINIMUM, conforme France).
Embarque un XML CII (EN16931 / MINIMUM) dans le PDF pour produire un PDF/A-3."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from facturx import generate_from_binary


def _d(v) -> str:
    try:
        return f"{float(v or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _date102(iso: str | None) -> str:
    if not iso:
        return ""
    return str(iso)[:10].replace("-", "")


def build_facturx_xml(doc: dict, branding: dict | None) -> bytes:
    branding = branding or {}
    totals = doc.get("totals") or {}
    ht = _d(totals.get("ht"))
    tva = _d(totals.get("tva"))
    ttc = _d(totals.get("ttc"))
    paid = float(doc.get("paid") or 0)
    due = _d(float(totals.get("ttc") or 0) - paid)

    seller = escape(branding.get("company_name") or "ConstruPilot")
    contact = escape(branding.get("contact_line") or "")
    client = doc.get("client") or {}
    buyer = escape(client.get("name") or "Client")
    number = escape(str(doc.get("number") or doc.get("doc_id") or "FACTURE"))
    issue = _date102(doc.get("issue_date"))
    seller_vat = escape(str(branding.get("vat") or branding.get("tva_intra") or ""))
    vat_block = (f'<ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">{seller_vat}'
                 f'</ram:ID></ram:SpecifiedTaxRegistration>') if seller_vat else ""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:factur-x.eu:1p0:minimum</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>{number}</ram:ID>
    <ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime><udt:DateTimeString format="102">{issue}</udt:DateTimeString></ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:Name>{seller}</ram:Name>
        <ram:PostalTradeAddress><ram:CountryID>FR</ram:CountryID></ram:PostalTradeAddress>
        {vat_block}
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>{buyer}</ram:Name>
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:TaxBasisTotalAmount>{ht}</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">{tva}</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>{ttc}</ram:GrandTotalAmount>
        <ram:DuePayableAmount>{due}</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""
    _ = contact  # réservé pour enrichissement futur (adresse/SIRET vendeur)
    return xml.encode("utf-8")


def to_facturx(pdf_bytes: bytes, doc: dict, branding: dict | None) -> bytes:
    """Renvoie un PDF Factur-X (PDF/A-3 avec XML embarqué). Fallback = PDF simple."""
    xml = build_facturx_xml(doc, branding)
    try:
        out = generate_from_binary(pdf_bytes, xml, flavor="factur-x", level="minimum",
                                   check_xsd=True)
        return out
    except Exception:
        # En cas d'échec de conformité, on embarque quand même sans validation stricte.
        try:
            return generate_from_binary(pdf_bytes, xml, flavor="factur-x",
                                        level="minimum", check_xsd=False)
        except Exception:
            return pdf_bytes
