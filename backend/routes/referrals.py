"""Referral Program — Iter 34
Generate short referral codes per user, track signups referred by them, and
credit +30 Pro-days per successful referral (up to 12 months).

Data model additions on `users`:
  - referral_code: str (auto-generated on first GET /api/referrals/me)
  - referred_by: str (referral_code of the referrer, set at register time)
  - referral_bonus_days: int (accumulated free Pro days from referrals, cap 360)

New endpoints:
  - GET  /api/referrals/me           → user's code, share URL, stats
  - GET  /api/referrals/lookup/{code} → public referral code validation (used by /register)

The auth register handler is extended to accept an optional `referred_by_code`.
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/referrals", tags=["referrals"])

BASE_URL = "https://construpilot.fr"
BONUS_DAYS_PER_REFERRAL = 30
MAX_BONUS_DAYS = 360  # 12 months cap


def _generate_code(name: str = "") -> str:
    """8-char shareable code : mixes user initials + entropy to be non-guessable
    but memorable enough. Example : `MARC-9F3K`."""
    prefix = "".join(c for c in (name or "").upper() if c.isalpha())[:4] or "USER"
    return f"{prefix}-{secrets.token_hex(2).upper()}"


async def _get_or_create_code(user: dict) -> str:
    """Return the user's referral_code, creating one lazily if absent."""
    if user.get("referral_code"):
        return user["referral_code"]
    # Attempt up to 5 times for uniqueness (collision odds negligible)
    for _ in range(5):
        code = _generate_code(user.get("name", ""))
        existing = await db.users.find_one({"referral_code": code}, {"_id": 1})
        if not existing:
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"referral_code": code}},
            )
            return code
    # Fallback : add extra entropy
    code = f"REF-{secrets.token_hex(3).upper()}"
    await db.users.update_one(
        {"user_id": user["user_id"]}, {"$set": {"referral_code": code}}
    )
    return code


class ReferralMe(BaseModel):
    code: str
    share_url: str
    total_referrals: int
    bonus_days_earned: int
    bonus_days_cap: int
    recent_referrals: list[dict]


@router.get("/me", response_model=ReferralMe)
async def referrals_me(user=Depends(current_user)):
    """Return the current user's referral code, share URL and stats."""
    code = await _get_or_create_code(user)
    referred_users = await db.users.find(
        {"referred_by": code},
        {"_id": 0, "name": 1, "email": 1, "created_at": 1},
    ).sort("created_at", -1).limit(50).to_list(length=50)

    # Mask email — GDPR-safe display : first char + domain
    def _mask(e: str) -> str:
        if not e or "@" not in e:
            return e
        local, dom = e.split("@", 1)
        return f"{local[0]}***@{dom}"

    recent = [{
        "name": u.get("name", ""),
        "email_masked": _mask(u.get("email", "")),
        "joined_at": u.get("created_at"),
    } for u in referred_users]

    total = len(referred_users)
    fresh_user = await db.users.find_one(
        {"user_id": user["user_id"]}, {"_id": 0, "referral_bonus_days": 1}
    ) or {}
    bonus = fresh_user.get("referral_bonus_days", 0)

    return ReferralMe(
        code=code,
        share_url=f"{BASE_URL}/?ref={code}",
        total_referrals=total,
        bonus_days_earned=bonus,
        bonus_days_cap=MAX_BONUS_DAYS,
        recent_referrals=recent,
    )


@router.get("/lookup/{code}")
async def referrals_lookup(code: str) -> dict:
    """Public endpoint used by the /register frontend to validate a referral
    code shown in the URL query string. Returns the referrer's first name
    (for the "Invité par Marc" welcome message) or 404 if the code is bogus."""
    code = code.upper().strip()
    if not code or len(code) > 32:
        raise HTTPException(400, "Code invalide")
    referrer = await db.users.find_one(
        {"referral_code": code},
        {"_id": 0, "user_id": 1, "name": 1},
    )
    if not referrer:
        raise HTTPException(404, "Code de parrainage inconnu")
    return {
        "code": code,
        "referrer_name": (referrer.get("name") or "").split()[0] or "un ami",
    }


async def credit_referrer(referred_by_code: Optional[str]) -> None:
    """Called from /api/auth/register after a new user is created.

    Credits +BONUS_DAYS_PER_REFERRAL to the referrer, capped at MAX_BONUS_DAYS.
    Silent no-op if the code is empty or unknown.
    """
    if not referred_by_code:
        return
    code = referred_by_code.upper().strip()
    referrer = await db.users.find_one(
        {"referral_code": code},
        {"_id": 0, "user_id": 1, "referral_bonus_days": 1},
    )
    if not referrer:
        return
    current = referrer.get("referral_bonus_days", 0)
    new_total = min(MAX_BONUS_DAYS, current + BONUS_DAYS_PER_REFERRAL)
    await db.users.update_one(
        {"user_id": referrer["user_id"]},
        {"$set": {"referral_bonus_days": new_total}},
    )
