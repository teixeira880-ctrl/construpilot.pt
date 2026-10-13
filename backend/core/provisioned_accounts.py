"""Contas de clientes criadas a pedido do administrador (idempotente, executado no arranque)."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
logger = logging.getLogger("provisioned_accounts")
ACCOUNTS = [
    {"email": "construtoradavi15@gmail.com", "name": "Construtora Davi", "company_name": "Construtora Davi",
     "temp_password": "Davi1234", "account_type": "pro_business", "plan_id": "pro_business_yearly"},
]
async def provision_accounts(db, hash_password, new_user_id) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for acc in ACCOUNTS:
        email = acc["email"].lower().strip()
        try:
            user = await db.users.find_one({"email": email}, {"_id": 0})
            if not user:
                user = {"email": email, "name": acc["name"], "role": "user", "plan": "premium",
                        "account_type": acc["account_type"], "company_name": acc.get("company_name"),
                        "country": "PT", "language": "pt",
                        "password_hash": hash_password(acc["temp_password"]),
                        "auth_provider": "password", "picture": None,
                        "user_id": new_user_id(), "must_change_password": True,
                        "email_verified": True, "two_fa_enabled": False,
                        "provisioned_by_admin": True, "created_at": now}
                await db.users.insert_one(dict(user))
                logger.info("Conta cliente criada pelo administrador: %s", email)
            ent_id = f"admin_grant_{user['user_id']}"
            if not await db.entitlements.find_one({"entitlement_id": ent_id}):
                await db.entitlements.update_one({"entitlement_id": ent_id},
                    {"$set": {"entitlement_id": ent_id, "user_id": user["user_id"], "plan_id": acc["plan_id"],
                              "status": "active", "source": "admin_grant", "granted_at": now}}, upsert=True)
                await db.users.update_one({"user_id": user["user_id"]},
                    {"$set": {"account_type": acc["account_type"], "active_plan_id": acc["plan_id"], "active_audience": "pro"}})
                logger.info("Acesso %s concedido a %s", acc["plan_id"], email)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Provisionamento de %s falhou: %s", email, exc)
