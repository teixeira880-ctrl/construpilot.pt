import asyncio
import os
import sys
from datetime import datetime, timezone

from core.db import db
from core.security import hash_password, new_user_id

EMAIL = os.environ.get("ADMIN_DEBORA_EMAIL", "deboradsmelo@gmail.com")
# SEC-Z-002: password lida do env, sem fallback hardcoded.
PASSWORD = os.environ.get("ADMIN_DEBORA_PASSWORD", "")
NAME = "Debora Smelo"


async def main():
    if not PASSWORD:
        print("Erro: ADMIN_DEBORA_PASSWORD não definida no ambiente. Abortar.", file=sys.stderr)
        sys.exit(1)
    email = EMAIL.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        upd = {
            "role": "admin",
            "plan": "premium",
            "password_hash": hash_password(PASSWORD),
            "auth_provider": "password",
            "two_fa_enabled": False,
            "two_fa_seed_reset": True,
            "must_change_password": False,
        }
        await db.users.update_one({"email": email}, {"$set": upd})
        print(f"Compte existant promu admin: {email}")
    else:
        await db.users.insert_one({
            "email": email, "name": NAME, "role": "admin",
            "plan": "premium", "password_hash": hash_password(PASSWORD),
            "auth_provider": "password", "picture": None,
            "user_id": new_user_id(), "must_change_password": False,
            "two_fa_enabled": False, "two_fa_seed_reset": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"Nouveau compte admin cree: {email}")

    u = await db.users.find_one({"email": email}, {"_id": 0, "email": 1, "role": 1, "user_id": 1})
    print("Verification:", u)


if __name__ == "__main__":
    asyncio.run(main())
