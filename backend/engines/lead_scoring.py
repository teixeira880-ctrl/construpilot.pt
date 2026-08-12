"""Lead scoring 0-100 pour le Marketplace ConstruPilot.

Facteurs mesurables :
- budget (10 pts si renseigné, +5 si >5k, +5 si >20k)
- adresse (10 pts si code postal ou ville)
- description (10 pts si >100 chars, 5 si >30)
- surface (10 pts si connue)
- délai (10 pts si <90j, 5 si <180j)
- téléphone (10 pts si présent, +5 si vérifié)
- email (10 pts si présent, +5 si vérifié)
- photos (5 pts par photo jusqu'à 15)
- type travaux détaillé (10 pts si lot précis dans description)
- intention (bonus 5 si "urgent" / "cette année")
"""
import re

BUDGET_TIERS = [
    (0, 5000, "petit"),
    (5000, 20000, "standard"),
    (20000, 50000, "premium"),
    (50000, 10**9, "grand"),
]

LOT_KEYWORDS = ("électricité", "plomberie", "peinture", "carrelage", "cuisine",
                "salle de bain", "chauffage", "isolation", "toiture", "menuiserie",
                "placo", "sol", "parquet", "façade", "extension", "combles")


def budget_tier(budget: float | None) -> str:
    if not budget:
        return "petit"
    for lo, hi, name in BUDGET_TIERS:
        if lo <= budget < hi:
            return name
    return "grand"


def score(lead: dict) -> dict:
    detail: list[dict] = []
    pts = 0

    def add(label: str, value: int, reason: str = ""):
        nonlocal pts
        pts += value
        detail.append({"label": label, "points": value, "reason": reason})

    budget = lead.get("budget") or 0
    if budget > 0:
        add("Budget renseigné", 10, f"{budget} €")
        if budget >= 5000:
            add("Budget significatif", 5, ">= 5 000 €")
        if budget >= 20000:
            add("Budget premium", 5, ">= 20 000 €")

    address = (lead.get("address") or "").strip()
    if address:
        if re.search(r"\b\d{5}\b", address):
            add("Adresse complète", 10, "code postal détecté")
        else:
            add("Adresse partielle", 5, "sans code postal")

    desc = (lead.get("description") or "").strip()
    if len(desc) >= 100:
        add("Description détaillée", 10, f"{len(desc)} caractères")
    elif len(desc) >= 30:
        add("Description sommaire", 5, f"{len(desc)} caractères")

    if lead.get("surface"):
        add("Surface indiquée", 10, f"{lead['surface']} m²")

    delay_days = lead.get("delay_days")
    if delay_days is not None:
        if delay_days <= 90:
            add("Démarrage rapide", 10, "≤ 3 mois")
        elif delay_days <= 180:
            add("Démarrage court terme", 5, "≤ 6 mois")

    phone = (lead.get("phone") or "").strip()
    if phone and len(re.sub(r"\D", "", phone)) >= 9:
        add("Téléphone présent", 10, phone)
        if lead.get("phone_verified"):
            add("Téléphone vérifié", 5)

    email = (lead.get("email") or "").strip()
    if "@" in email:
        add("Email présent", 10)
        if lead.get("email_verified"):
            add("Email vérifié", 5)

    photos = lead.get("photos_count", 0) or 0
    if photos:
        pt = min(15, photos * 5)
        add("Photos jointes", pt, f"{photos} photo(s)")

    low = desc.lower()
    matched = [kw for kw in LOT_KEYWORDS if kw in low]
    if matched:
        pt = min(10, len(matched) * 3)
        add("Type de travaux détaillé", pt, ", ".join(matched[:4]))

    if any(kw in low for kw in ("urgent", "cette année", "asap", "au plus vite")):
        add("Intention forte", 5, "mots-clés d'urgence")

    total = min(100, pts)
    if total >= 75:
        rating = "excellent"
    elif total >= 55:
        rating = "bon"
    elif total >= 35:
        rating = "moyen"
    else:
        rating = "faible"
    return {"score": total, "rating": rating, "tier": budget_tier(budget),
            "detail": detail}


LEAD_PRICE_CENTS_BY_TIER = {"petit": 2000, "standard": 4500,
                            "premium": 8000, "grand": 12000}


def lead_price_cents(tier: str) -> int:
    return LEAD_PRICE_CENTS_BY_TIER.get(tier, 3000)
