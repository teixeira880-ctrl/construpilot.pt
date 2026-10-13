"""Niveau d'accès unique ConstruPilot (séparation stricte des fonctions par offre).

Hiérarchie : particulier_gratuit < particulier_payant < pro < business.
Dérivé de `account_type` (base) + tier d'abonnement (monetization.user_tier).
Source de vérité partagée par le backend (gardes de routes) et le frontend (menu).
"""
from fastapi import Depends, HTTPException

from core.security import current_user

LEVELS = ["particulier_gratuit", "particulier_payant", "pro", "business"]
RANK = {lvl: i for i, lvl in enumerate(LEVELS)}

_TIER_TO_LEVEL = {
    "pro_business": "business",
    "pro": "pro",
    "premium": "particulier_payant",
    "project_pass": "particulier_payant",
    "free": None,  # ne modifie pas la base
}


async def compute_level(user: dict) -> str:
    if not user:
        return "particulier_gratuit"
    if user.get("role") == "admin":
        return "business"
    at = user.get("account_type")
    base = "business" if at == "pro_business" else "pro" if at == "pro" else "particulier_gratuit"
    from engines import monetization
    tier = await monetization.user_tier(user.get("user_id"))
    from_tier = _TIER_TO_LEVEL.get(tier)
    candidates = [base] + ([from_tier] if from_tier else [])
    level = max(candidates, key=lambda lv: RANK[lv])
    # Séparation stricte : un compte PARTICULIER ne peut JAMAIS dépasser
    # « particulier_payant », même si le mode promo gratuit (user_tier) renvoie
    # un tier pro/business. Seuls les comptes 'pro'/'pro_business' (ou admin)
    # accèdent aux fonctions Pro/Business.
    if user.get("account_type") not in ("pro", "pro_business"):
        if RANK[level] > RANK["particulier_payant"]:
            level = "particulier_payant"
    return level


def meets(level: str, minimum: str) -> bool:
    return RANK.get(level, 0) >= RANK.get(minimum, 0)


def require_level(minimum: str):
    async def _dep(user=Depends(current_user)) -> dict:
        level = await compute_level(user)
        if not meets(level, minimum):
            raise HTTPException(
                status_code=403,
                detail=f'Função reservada à oferta «{minimum}». Atualize a sua subscrição.')
        return user
    return _dep
