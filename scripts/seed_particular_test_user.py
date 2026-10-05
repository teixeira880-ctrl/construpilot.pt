"""Seed/upsert do utilizador particular de teste.

Email:    particular@construpilot.pt
Password: Particular2026!
Account:  particulier
Plano:    Grátis
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from core.db import db  # noqa: E402
from core.security import hash_password, new_user_id  # noqa: E402


EMAIL = "particular@construpilot.pt"
PASSWORD = "Particular2026!"
NAME = "Particular Teste"


async def main():
    existing = await db.users.find_one({"email": EMAIL})
    hashed = hash_password(PASSWORD)
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.users.update_one(
            {"email": EMAIL},
            {"$set": {
                "password_hash": hashed,
                "account_type": "particulier",
                "role": "user",
                "name": NAME,
                "email_verified": True,
                "updated_at": now,
            }},
        )
        print(f"[OK] Updated existing user {EMAIL} (user_id={existing.get('user_id')})")
    else:
        uid = new_user_id()
        await db.users.insert_one({
            "user_id": uid,
            "email": EMAIL,
            "name": NAME,
            "password_hash": hashed,
            "account_type": "particulier",
            "role": "user",
            "email_verified": True,
            "created_at": now,
            "updated_at": now,
            "token_version": 0,
            "lang": "pt",
            "country": "PT",
        })
        print(f"[OK] Created user {EMAIL} (user_id={uid})")
    print(f"    Email:    {EMAIL}")
    print(f"    Password: {PASSWORD}")
    print(f"    Plano:    particulier (free)")


if __name__ == "__main__":
    asyncio.run(main())
