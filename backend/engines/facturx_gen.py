"""Génération de factures au format Factur-X (profil BASIC, conforme France / EN 16931).

Produit un PDF/A-3 avec un XML CII (Cross Industry Invoice) embarqué, profil BASIC :
en-tête + parties (vendeur/acheteur avec adresse + SIRET + TVA) + LIGNES de facture
+ ventilation de TVA par taux + totaux. Déterministe : aucun montant n'est recalculé
autrement que par les règles arithmétiques EN 16931 (qté × PU, bases et taxes par taux).

Chaîne de repli zéro-coupure : BASIC (XSD strict) → BASIC (sans XSD) → MINIMUM → PDF nu.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from facturx import generate_from_binary

# Unités françaises → codes UN/ECE Rec. 20 (obligatoires en CII).
_UNIT_CODE = {
    "u": "C62", "unité": "C62", "unite": "C62", "forfait": "C62", "ens": "C62",
    "ensemble": "C62", "pce": "C62", "pièce": "C62", "piece": "C62", "lot": "C62",
    "m²": "MTK", "m2": "MTK", "mp": "MTK",
    "m": "MTR", "ml": "MTR", "mL": "MTR",
    "m³": "MTQ", "m3": "MTQ",
    "kg": "KGM", "t": "TNE",
    "h": "HUR", "heure": "HUR", "j": "DAY", "jour": "DAY",
    "l": "LTR", "litre": "LTR",
}


def _unit_code(unit: str | None) -> str:
    return _UNIT_CODE.get((unit or "").strip().lower(), "C62")


def _d(v) -> str:
    try:
        return f"{float(v or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _q(v) -> str:
    try:
        return f"{float(v or 0):.4f}"
    except (TypeError, ValueError):
        return "0.0000"


def _date102(iso: str | None) -> str:
    if not iso:
        return ""
    return str(iso)[:10].replace("-", "")


def _buyer_name(client: dict) -> str:
    if not client:
        return "Client"
    name = (client.get("name")
            or client.get("company")
            or f"{client.get('first_name', '')} {client.get('last_name', '')}".strip())
    return name or "Client"


def _real_lines(doc: dict) -> list[dict]:
    out = []
    for ln in doc.get("lines") or []:
        if ln.get("kind") in ("section", "subsection", "text", "pagebreak"):
            continue
        out.append(ln)
    return out


def _vat_category(rate: float) -> str:
    # S = taux normal/réduit (>0), Z = taux zéro. (Exonérations fines = profil supérieur.)
    return "S" if rate > 0 else "Z"


def build_facturx_xml(doc: dict, branding: dict | None) -> bytes:
    """Construit le XML CII profil BASIC depuis la facture et le branding société."""
    branding = branding or {}
    totals = doc.get("totals") or {}
    client = doc.get("client") or {}

    number = escape(str(doc.get("number") or doc.get("doc_id") or "FACTURE"))
    type_code = "381" if doc.get("doc_type") == "credit_note" else "380"
    issue = _date102(doc.get("issue_date"))
    due = _date102(doc.get("due_date"))
    currency = escape((branding.get("currency") or "EUR").upper()[:3] or "EUR")

    seller = escape(branding.get("company_name") or "ConstruPilot")
    seller_line = escape(str(branding.get("address") or ""))
    seller_cp = escape(str(branding.get("postal_code") or ""))
    seller_city = escape(str(branding.get("city") or ""))
    seller_country = escape(str(branding.get("country") or "PT").upper()[:2] or "PT")
    seller_vat = escape(str(branding.get("vat") or branding.get("tva_intra") or "").replace(" ", ""))
    seller_siret = escape(str(branding.get("siret") or "").replace(" ", ""))

    buyer = escape(_buyer_name(client))
    buyer_line = escape(str(client.get("address") or ""))
    buyer_cp = escape(str(client.get("postal_code") or ""))
    buyer_city = escape(str(client.get("city") or ""))
    buyer_country = escape(str(client.get("country") or "PT").upper()[:2] or "PT")

    # --- Lignes + bases/taxes par taux (déterministe) ---
    lines = _real_lines(doc)
    line_total = 0.0
    basis_by_rate: dict[float, float] = {}
    tax_by_rate: dict[float, float] = {}
    line_xml_parts: list[str] = []
    for i, ln in enumerate(lines, start=1):
        qty = float(ln.get("qty") or 0)
        disc = float(ln.get("discount_pct") or 0)
        net_price = round(float(ln.get("unit_price_ht") or 0) * (1 - disc / 100), 4)
        line_ht = round(qty * net_price, 2)
        rate = float(ln.get("vat_rate") or 0)
        line_total += line_ht
        basis_by_rate[rate] = round(basis_by_rate.get(rate, 0.0) + line_ht, 2)
        tax_by_rate[rate] = round(tax_by_rate.get(rate, 0.0) + line_ht * rate / 100, 2)
        name = escape((ln.get("designation") or ln.get("title") or "Prestation").strip()[:400]) or "Prestation"
        uc = _unit_code(ln.get("unit"))
        cat = _vat_category(rate)
        line_xml_parts.append(f"""    <ram:IncludedSupplyChainTradeLineItem>
      <ram:AssociatedDocumentLineDocument>
        <ram:LineID>{i}</ram:LineID>
      </ram:AssociatedDocumentLineDocument>
      <ram:SpecifiedTradeProduct>
        <ram:Name>{name}</ram:Name>
      </ram:SpecifiedTradeProduct>
      <ram:SpecifiedLineTradeAgreement>
        <ram:NetPriceProductTradePrice>
          <ram:ChargeAmount>{_d(net_price)}</ram:ChargeAmount>
        </ram:NetPriceProductTradePrice>
      </ram:SpecifiedLineTradeAgreement>
      <ram:SpecifiedLineTradeDelivery>
        <ram:BilledQuantity unitCode="{uc}">{_q(qty)}</ram:BilledQuantity>
      </ram:SpecifiedLineTradeDelivery>
      <ram:SpecifiedLineTradeSettlement>
        <ram:ApplicableTradeTax>
          <ram:TypeCode>VAT</ram:TypeCode>
          <ram:CategoryCode>{cat}</ram:CategoryCode>
          <ram:RateApplicablePercent>{_d(rate)}</ram:RateApplicablePercent>
        </ram:ApplicableTradeTax>
        <ram:SpecifiedTradeSettlementLineMonetarySummation>
          <ram:LineTotalAmount>{_d(line_ht)}</ram:LineTotalAmount>
        </ram:SpecifiedTradeSettlementLineMonetarySummation>
      </ram:SpecifiedLineTradeSettlement>
    </ram:IncludedSupplyChainTradeLineItem>""")

    line_total = round(line_total, 2)
    tax_basis = round(sum(basis_by_rate.values()), 2)
    tax_total = round(sum(tax_by_rate.values()), 2)
    grand = round(tax_basis + tax_total, 2)
    prepaid = round(float(doc.get("paid") or 0), 2)
    due_amount = round(grand - prepaid, 2)

    # --- Ventilation de TVA (une ApplicableTradeTax par taux) ---
    tax_blocks = []
    for rate in sorted(basis_by_rate.keys()):
        cat = _vat_category(rate)
        tax_blocks.append(f"""      <ram:ApplicableTradeTax>
        <ram:CalculatedAmount>{_d(tax_by_rate.get(rate, 0.0))}</ram:CalculatedAmount>
        <ram:TypeCode>VAT</ram:TypeCode>
        <ram:BasisAmount>{_d(basis_by_rate.get(rate, 0.0))}</ram:BasisAmount>
        <ram:CategoryCode>{cat}</ram:CategoryCode>
        <ram:RateApplicablePercent>{_d(rate)}</ram:RateApplicablePercent>
      </ram:ApplicableTradeTax>""")
    tax_xml = "\n".join(tax_blocks)

    legal_block = (f"""        <ram:SpecifiedLegalOrganization>
          <ram:ID schemeID="0002">{seller_siret}</ram:ID>
        </ram:SpecifiedLegalOrganization>""") if seller_siret else ""
    vat_block = (f"""        <ram:SpecifiedTaxRegistration>
          <ram:ID schemeID="VA">{seller_vat}</ram:ID>
        </ram:SpecifiedTaxRegistration>""") if seller_vat else ""

    def _addr(line, cp, city, country):
        parts = ["        <ram:PostalTradeAddress>"]
        if cp:
            parts.append(f"          <ram:PostcodeCode>{cp}</ram:PostcodeCode>")
        if line:
            parts.append(f"          <ram:LineOne>{line}</ram:LineOne>")
        if city:
            parts.append(f"          <ram:CityName>{city}</ram:CityName>")
        parts.append(f"          <ram:CountryID>{country}</ram:CountryID>")
        parts.append("        </ram:PostalTradeAddress>")
        return "\n".join(parts)

    seller_addr = _addr(seller_line, seller_cp, seller_city, seller_country)
    buyer_addr = _addr(buyer_line, buyer_cp, buyer_city, buyer_country)

    payment_terms = (f"""      <ram:SpecifiedTradePaymentTerms>
        <ram:DueDateDateTime>
          <udt:DateTimeString format="102">{due}</udt:DateTimeString>
        </ram:DueDateDateTime>
      </ram:SpecifiedTradePaymentTerms>""") if due else ""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100" xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>{number}</ram:ID>
    <ram:TypeCode>{type_code}</ram:TypeCode>
    <ram:IssueDateTime>
      <udt:DateTimeString format="102">{issue}</udt:DateTimeString>
    </ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
{chr(10).join(line_xml_parts)}
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:Name>{seller}</ram:Name>
{legal_block}
{seller_addr}
{vat_block}
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>{buyer}</ram:Name>
{buyer_addr}
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>{currency}</ram:InvoiceCurrencyCode>
{tax_xml}
{payment_terms}
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>{_d(line_total)}</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>{_d(tax_basis)}</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="{currency}">{_d(tax_total)}</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>{_d(grand)}</ram:GrandTotalAmount>
        <ram:TotalPrepaidAmount>{_d(prepaid)}</ram:TotalPrepaidAmount>
        <ram:DuePayableAmount>{_d(due_amount)}</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""
    # Nettoyage des lignes vides laissées par les blocs optionnels absents.
    xml = "\n".join(l for l in xml.splitlines() if l.strip() != "")
    return xml.encode("utf-8")


def _minimum_xml(doc: dict, branding: dict | None) -> bytes:
    """XML MINIMUM de dernier recours (en-tête + totaux, sans lignes)."""
    branding = branding or {}
    totals = doc.get("totals") or {}
    ht = _d(totals.get("ht"))
    tva = _d(totals.get("tva"))
    ttc = _d(totals.get("ttc"))
    due = _d(float(totals.get("ttc") or 0) - float(doc.get("paid") or 0))
    seller = escape(branding.get("company_name") or "ConstruPilot")
    buyer = escape(_buyer_name(doc.get("client") or {}))
    number = escape(str(doc.get("number") or doc.get("doc_id") or "FACTURE"))
    issue = _date102(doc.get("issue_date"))
    siret = escape(str(branding.get("siret") or "").replace(" ", ""))
    legal = (f'<ram:SpecifiedLegalOrganization><ram:ID schemeID="0002">{siret}'
             f'</ram:ID></ram:SpecifiedLegalOrganization>') if siret else ""
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
        {legal}
        <ram:PostalTradeAddress><ram:CountryID>FR</ram:CountryID></ram:PostalTradeAddress>
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty><ram:Name>{buyer}</ram:Name></ram:BuyerTradeParty>
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
    return xml.encode("utf-8")


def to_facturx(pdf_bytes: bytes, doc: dict, branding: dict | None) -> bytes:
    """Renvoie un PDF Factur-X (PDF/A-3 + XML CII BASIC embarqué).

    Repli progressif : BASIC strict → BASIC sans XSD → MINIMUM → PDF nu."""
    xml_basic = build_facturx_xml(doc, branding)
    for kwargs in ({"level": "basic", "check_xsd": True},
                   {"level": "basic", "check_xsd": False}):
        try:
            return generate_from_binary(pdf_bytes, xml_basic, flavor="factur-x", **kwargs)
        except Exception:
            continue
    # Dernier recours : profil MINIMUM, puis PDF nu.
    try:
        return generate_from_binary(pdf_bytes, _minimum_xml(doc, branding),
                                    flavor="factur-x", level="minimum", check_xsd=False)
    except Exception:
        return pdf_bytes
