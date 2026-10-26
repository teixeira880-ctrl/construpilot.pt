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


def _score_budget(lead: dict, add) -> None:
    b = lead.get("budget") or 0
    if b <= 0:
        return
    add("Orçamento indicado", 10, f"{b} €")
    if b >= 5000:
        add("Budget significatif", 5, ">= 5 000 €")
    if b >= 20000:
        add("Budget premium", 5, ">= 20 000 €")


def _score_address(lead: dict, add) -> None:
    addr = (lead.get("address") or "").strip()
    if not addr:
        return
    if re.search(r"\b\d{5}\b", addr):
        add("Morada completa", 10, "código postal detetado")
    else:
        add("Morada parcial", 5, "sem código postal")


def _score_description(lead: dict, add) -> None:
    desc = (lead.get("description") or "").strip()
    if len(desc) >= 100:
        add("Descrição detalhada", 10, f"{len(desc)} caracteres")
    elif len(desc) >= 30:
        add("Descrição sumária", 5, f"{len(desc)} caracteres")


def _score_surface(lead: dict, add) -> None:
    if lead.get("surface"):
        add("Área indicada", 10, f"{lead['surface']} m²")


def _score_delay(lead: dict, add) -> None:
    d = lead.get("delay_days")
    if d is None:
        return
    if d <= 90:
        add("Arranque rápido", 10, "≤ 3 meses")
    elif d <= 180:
        add("Arranque a curto prazo", 5, "≤ 6 meses")


def _score_phone(lead: dict, add) -> None:
    phone = (lead.get("phone") or "").strip()
    if phone and len(re.sub(r"\D", "", phone)) >= 9:
        add("Telefone presente", 10, phone)
        if lead.get("phone_verified"):
            add("Telefone verificado", 5)


def _score_email(lead: dict, add) -> None:
    email = (lead.get("email") or "").strip()
    if "@" in email:
        add("E-mail presente", 10)
        if lead.get("email_verified"):
            add("E-mail verificado", 5)


def _score_photos(lead: dict, add) -> None:
    photos = lead.get("photos_count", 0) or 0
    if photos:
        add("Fotografias anexadas", min(15, photos * 5), f"{photos} photo(s)")


def _score_keywords(lead: dict, add) -> None:
    low = (lead.get("description") or "").lower()
    matched = [kw for kw in LOT_KEYWORDS if kw in low]
    if matched:
        add("Tipo de obras detalhado", min(10, len(matched) * 3),
            ", ".join(matched[:4]))
    if any(kw in low for kw in ("urgent", "cette année", "asap", "au plus vite")):
        add("Intenção forte", 5, "palavras-chave de urgência")


# Pipeline de règles — ajouter/retirer une règle = 1 ligne
_SCORING_RULES = (
    _score_budget, _score_address, _score_description, _score_surface,
    _score_delay, _score_phone, _score_email, _score_photos, _score_keywords,
)


def _rating(total: int) -> str:
    if total >= 75:
        return "excellent"
    if total >= 55:
        return "bon"
    if total >= 35:
        return "moyen"
    return "faible"


def score(lead: dict) -> dict:
    detail: list[dict] = []
    pts = 0

    def add(label: str, value: int, reason: str = "") -> None:
        nonlocal pts
        pts += value
        detail.append({"label": label, "points": value, "reason": reason})

    for rule in _SCORING_RULES:
        rule(lead, add)

    total = min(100, pts)
    return {"score": total, "rating": _rating(total),
            "tier": budget_tier(lead.get("budget") or 0), "detail": detail}


LEAD_PRICE_CENTS_BY_TIER = {"petit": 2000, "standard": 4500,
                            "premium": 8000, "grand": 12000}


def lead_price_cents(tier: str) -> int:
    return LEAD_PRICE_CENTS_BY_TIER.get(tier, 3000)
