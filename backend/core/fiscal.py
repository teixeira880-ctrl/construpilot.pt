"""Politique fiscale versionnée : la langue d'affichage ne décide jamais d'un taux de TVA."""
from typing import Optional

FISCAL_POLICY_VERSION = "2026-09.1"

# Taux proposés dans l'éditeur + taux par défaut d'une ligne dont la TVA n'a pas été choisie.
# Le défaut est toujours le taux normal : un taux réduit doit être confirmé par l'utilisateur.
POLICIES: dict[str, dict] = {
    "FR": {"country": "FR", "currency": "EUR", "rates": [0, 5.5, 10, 20], "default_rate": 20,
           "reduced_hint": "10 % (rénovation de logements > 2 ans, art. 279-0 bis CGI) et 5,5 % (rénovation énergétique) sous conditions : à confirmer avec attestation.",
           "zero_label": "0 % (autoliquidation sous-traitance / exonération)"},
    "PT": {"country": "PT", "currency": "EUR", "rates": [0, 6, 13, 23], "default_rate": 23,
           "reduced_hint": "6 % (Verba 2.27 CIVA — empreitadas de reabilitação de imóveis de habitação) sob condições : a confirmar.",
           "zero_label": "0 % (autoliquidação / isenção)"},
}


def policy_for(country: Optional[str]) -> dict:
    c = (country or "PT").upper().strip()  # construpilot.pt: Portugal por omissão
    if c in POLICIES:
        return {**POLICIES[c], "known": True, "version": FISCAL_POLICY_VERSION}
    return {"country": c or None, "currency": "EUR", "rates": sorted({r for p in POLICIES.values() for r in p["rates"]}),
            "default_rate": None, "reduced_hint": None, "zero_label": "0 %", "known": False, "version": FISCAL_POLICY_VERSION}


def suggest_reduced_rate(country: Optional[str], *text_hints: str) -> Optional[dict]:
    """Suggestion (jamais appliquée automatiquement) d'un taux réduit déduite du texte."""
    c = (country or "").upper()
    blob = " ".join(h for h in text_hints if h).lower()
    if c == "PT":
        reno = any(k in blob for k in ("renov", "reabilit", "remodel", "restaur", "beneficia", "obra"))
        habit = any(k in blob for k in ("casa", "moradia", "apartament", "habita", "quarto", "cozinha", "casa de banho", "wc", "sala", "vivenda", "t1", "t2", "t3"))
        if reno and habit:
            return {"rate": 6.0, "reason": "Contexte de réhabilitation d'un logement détecté dans le texte (Verba 2.27 CIVA) — à confirmer."}
    if c == "FR":
        reno = any(k in blob for k in ("rénov", "renov", "réhabilit", "rehabilit", "remise en état", "existant"))
        habit = any(k in blob for k in ("maison", "appartement", "logement", "habitation", "salle de bain", "cuisine", "chambre"))
        if reno and habit:
            return {"rate": 10.0, "reason": "Contexte de rénovation d'un logement détecté dans le texte (art. 279-0 bis CGI, logement > 2 ans, attestation) — à confirmer."}
    return None
