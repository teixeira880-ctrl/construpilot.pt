"""Libellés PDF documents pro (devis / facture / avoir) — 7 langues. Fallback FR."""

SUPPORTED = ["fr", "en", "es", "pt", "it", "de", "ar"]

PDF_LABELS = {
    "fr": {
        "doc_quote": "DEVIS", "doc_invoice": "FACTURE", "doc_credit": "AVOIR", "doc_generic": "DOCUMENT",
        "addressed_to": "Adressé à", "client": "Client",
        "lines_title": "Détail des prestations",
        "c_designation": "Désignation", "c_qty": "Qté", "c_unit": "Unité",
        "c_pu_ht": "PU HT", "c_vat": "TVA", "c_total_ht": "Total HT", "no_line": "Aucune ligne",
        "recap": "Récapitulatif", "total_ht": "Total HT", "vat": "TVA {rate} %", "total_ttc": "TOTAL TTC",
        "deposit_asked": "Acompte demandé ({pct} %)", "remaining": "Reste à régler",
        "num": "N°", "date": "Date", "due": "Échéance", "notes": "Notes",
        "agreement": "Bon pour accord (date + signature) :",
        "footer": "Document émis via ConstruPilot. TVA applicable selon la nature des travaux (10 % rénovation logement +2 ans, 20 % neuf, 5,5 % rénovation énergétique). Conditions de règlement selon mentions ci-dessus.",
    },
    "en": {
        "doc_quote": "QUOTE", "doc_invoice": "INVOICE", "doc_credit": "CREDIT NOTE", "doc_generic": "DOCUMENT",
        "addressed_to": "Billed to", "client": "Client",
        "lines_title": "Line items",
        "c_designation": "Description", "c_qty": "Qty", "c_unit": "Unit",
        "c_pu_ht": "Unit price", "c_vat": "VAT", "c_total_ht": "Total excl.", "no_line": "No line",
        "recap": "Summary", "total_ht": "Total excl. VAT", "vat": "VAT {rate}%", "total_ttc": "TOTAL INCL. VAT",
        "deposit_asked": "Deposit requested ({pct}%)", "remaining": "Balance due",
        "num": "No.", "date": "Date", "due": "Due date", "notes": "Notes",
        "agreement": "Approved (date + signature):",
        "footer": "Document issued via ConstruPilot. VAT applicable depending on the nature of the works. Payment terms as stated above.",
    },
    "es": {
        "doc_quote": "PRESUPUESTO", "doc_invoice": "FACTURA", "doc_credit": "ABONO", "doc_generic": "DOCUMENTO",
        "addressed_to": "Facturar a", "client": "Cliente",
        "lines_title": "Detalle de las prestaciones",
        "c_designation": "Descripción", "c_qty": "Cant.", "c_unit": "Ud.",
        "c_pu_ht": "PU sin IVA", "c_vat": "IVA", "c_total_ht": "Total sin IVA", "no_line": "Sin líneas",
        "recap": "Resumen", "total_ht": "Total sin IVA", "vat": "IVA {rate} %", "total_ttc": "TOTAL CON IVA",
        "deposit_asked": "Anticipo solicitado ({pct} %)", "remaining": "Pendiente de pago",
        "num": "N.º", "date": "Fecha", "due": "Vencimiento", "notes": "Notas",
        "agreement": "Conforme (fecha + firma):",
        "footer": "Documento emitido con ConstruPilot. IVA aplicable según la naturaleza de las obras. Condiciones de pago según lo indicado arriba.",
    },
    "pt": {
        "doc_quote": "ORÇAMENTO", "doc_invoice": "FATURA", "doc_credit": "NOTA DE CRÉDITO", "doc_generic": "DOCUMENTO",
        "addressed_to": "Faturar a", "client": "Cliente",
        "lines_title": "Detalhe dos serviços",
        "c_designation": "Designação", "c_qty": "Qtd.", "c_unit": "Un.",
        "c_pu_ht": "PU s/ IVA", "c_vat": "IVA", "c_total_ht": "Total s/ IVA", "no_line": "Sem linhas",
        "recap": "Resumo", "total_ht": "Total s/ IVA", "vat": "IVA {rate} %", "total_ttc": "TOTAL C/ IVA",
        "deposit_asked": "Sinal solicitado ({pct} %)", "remaining": "Por pagar",
        "num": "N.º", "date": "Data", "due": "Vencimento", "notes": "Notas",
        "agreement": "De acordo (data + assinatura):",
        "footer": "Documento emitido via ConstruPilot. IVA aplicável consoante a natureza das obras. Condições de pagamento conforme indicado acima.",
    },
    "it": {
        "doc_quote": "PREVENTIVO", "doc_invoice": "FATTURA", "doc_credit": "NOTA DI CREDITO", "doc_generic": "DOCUMENTO",
        "addressed_to": "Intestato a", "client": "Cliente",
        "lines_title": "Dettaglio delle prestazioni",
        "c_designation": "Descrizione", "c_qty": "Q.tà", "c_unit": "Unità",
        "c_pu_ht": "PU netto", "c_vat": "IVA", "c_total_ht": "Totale netto", "no_line": "Nessuna riga",
        "recap": "Riepilogo", "total_ht": "Totale netto", "vat": "IVA {rate} %", "total_ttc": "TOTALE IVA INCL.",
        "deposit_asked": "Acconto richiesto ({pct} %)", "remaining": "Saldo dovuto",
        "num": "N.", "date": "Data", "due": "Scadenza", "notes": "Note",
        "agreement": "Per accettazione (data + firma):",
        "footer": "Documento emesso tramite ConstruPilot. IVA applicabile secondo la natura dei lavori. Condizioni di pagamento come sopra indicato.",
    },
    "de": {
        "doc_quote": "ANGEBOT", "doc_invoice": "RECHNUNG", "doc_credit": "GUTSCHRIFT", "doc_generic": "DOKUMENT",
        "addressed_to": "Rechnung an", "client": "Kunde",
        "lines_title": "Leistungsübersicht",
        "c_designation": "Bezeichnung", "c_qty": "Menge", "c_unit": "Einheit",
        "c_pu_ht": "EP netto", "c_vat": "MwSt.", "c_total_ht": "Gesamt netto", "no_line": "Keine Position",
        "recap": "Zusammenfassung", "total_ht": "Gesamt netto", "vat": "MwSt. {rate} %", "total_ttc": "GESAMT BRUTTO",
        "deposit_asked": "Angeforderte Anzahlung ({pct} %)", "remaining": "Restbetrag",
        "num": "Nr.", "date": "Datum", "due": "Fällig am", "notes": "Notizen",
        "agreement": "Einverstanden (Datum + Unterschrift):",
        "footer": "Dokument erstellt über ConstruPilot. MwSt. je nach Art der Arbeiten anwendbar. Zahlungsbedingungen wie oben angegeben.",
    },
    "ar": {
        "doc_quote": "عرض سعر", "doc_invoice": "فاتورة", "doc_credit": "إشعار دائن", "doc_generic": "مستند",
        "addressed_to": "موجّهة إلى", "client": "العميل",
        "lines_title": "تفاصيل الخدمات",
        "c_designation": "البيان", "c_qty": "الكمية", "c_unit": "الوحدة",
        "c_pu_ht": "سعر الوحدة", "c_vat": "ض.ق.م", "c_total_ht": "الإجمالي بدون ضريبة", "no_line": "لا بنود",
        "recap": "ملخص", "total_ht": "الإجمالي بدون ضريبة", "vat": "ض.ق.م {rate} %", "total_ttc": "الإجمالي شامل الضريبة",
        "deposit_asked": "الدفعة المقدمة المطلوبة ({pct} %)", "remaining": "المتبقي للدفع",
        "num": "رقم", "date": "التاريخ", "due": "تاريخ الاستحقاق", "notes": "ملاحظات",
        "agreement": "موافق عليه (التاريخ + التوقيع):",
        "footer": "مستند صادر عبر ConstruPilot. تُطبَّق ضريبة القيمة المضافة حسب طبيعة الأعمال. شروط الدفع كما هو مبيّن أعلاه.",
    },
}


def pdf_labels(lang: str | None) -> dict:
    lg = (lang or "fr").lower()[:2]
    if lg not in SUPPORTED:
        lg = "fr"
    base = dict(PDF_LABELS["fr"])
    base.update(PDF_LABELS.get(lg, {}))
    return base
