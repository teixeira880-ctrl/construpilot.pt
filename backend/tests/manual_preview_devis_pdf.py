import sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from engines.pdf_docs import build_document_pdf

branding = {
    "company_name": "CM RENOV",
    "contact_line": "61 AVENUE BRETEUIL 75007 PARIS",
    "siret": "93816804400015",
    "vat": "FR62938168044",
    "accent_color": "#1d4ed8",
    "header_text": "CMRENOV\n61 avenue Breteuil\n75007\nPARIS\nFrance\nTVA N° FR62938168044\nTél : +33 (0) 6 23 76 28 47\nEmail : contact@cmrenov.com",
    "footer_text": "CM RENOV - SASU au capital de 5 000 € - RCS Paris 938 168 044 - Assurance décennale AXA n° 1234567 - Pénalités de retard : 3 x taux légal - Médiateur de la consommation : CM2C",
    "logo_b64": open("/tmp/logo_test.b64").read().strip(),
}
doc = {
    "doc_type": "quote",
    "title": "Entretien toiture et rénovation bardages",
    "number": "DEV-2026-202600093",
    "issue_date": "2026-09-22",
    "client": {"company": "SASU Russo", "first_name": "Georges", "last_name": "Russo",
               "address": "8 Avenue Beausite", "postal_code": "78700",
               "city": "Conflans-Sainte-Honorine", "email": "russo-georges@orange.fr",
               "siret": "85332233700017"},
    "lines": [
        {"category": "Toiture", "designation": "Nettoyage de toiture et remplacement de tuiles cassés",
         "description": "Lavage et nettoyage de la couverture existante.\nÉlimination des salissures superficielles, sans intervention sur l'étanchéité.\nIntervention avec moyens d'accès et protections adaptés.",
         "qty": 160, "unit": "m²", "unit_price_ht": 35, "vat_rate": 10},
        {"category": "Bardage", "designation": "Rénovation de bardage bois",
         "description": "Dépose de l'ancien bardage, traitement et pose d'un bardage neuf.",
         "qty": 45, "unit": "m²", "unit_price_ht": 120, "vat_rate": 10},
    ],
    "totals": {"ht": 11000.0, "tva_breakdown": {"10": 1100.0}, "ttc": 12100.0,
               "deposit_pct": 30, "deposit_amount": 3630.0, "remaining": 8470.0},
    "notes": "Devis valable 30 jours. Échafaudage inclus.",
}
pdf = build_document_pdf(doc, branding, lang="fr",
    sign_url="https://pilot-build-demo.preview.emergentagent.com/sign/DEMO-TOKEN-1234567890")
open("/tmp/devis_vert.pdf", "wb").write(pdf)
print("PDF généré :", len(pdf), "octets")
