"""Contas de clientes criadas a pedido do administrador (idempotente, executado no arranque).

- a conta só é criada se o e-mail ainda não existir (nunca reescreve uma palavra-passe);
- palavra-passe provisória, mudança obrigatória na primeira ligação (must_change_password);
- acesso concedido por entitlement « admin_grant » (sem Stripe), com validade opcional.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("provisioned_accounts")

ACCOUNTS = [
    {"email": "construtoradavi15@gmail.com", "name": "Construtora Davi", "company_name": "Construtora Davi",
     "temp_password": "Davi1234", "account_type": "pro_business", "plan_id": "pro_business_yearly",
     "valid_days": 90},  # 3 meses a contar da criação do acesso
]


def _expiry(start_iso: str, days: int | None) -> str | None:
    if not days:
        return None
    return (datetime.fromisoformat(start_iso) + timedelta(days=days)).isoformat()


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
            ent = await db.entitlements.find_one({"entitlement_id": ent_id}, {"_id": 0})
            if ent:
                exp = _expiry(ent.get("granted_at") or now, acc.get("valid_days"))
                if exp and not ent.get("expires_at"):
                    await db.entitlements.update_one({"entitlement_id": ent_id}, {"$set": {"expires_at": exp}})
                    logger.info("Validade de %s definida até %s", email, exp)
                continue
            doc = {"entitlement_id": ent_id, "user_id": user["user_id"], "plan_id": acc["plan_id"],
                   "status": "active", "source": "admin_grant", "granted_at": now}
            exp = _expiry(now, acc.get("valid_days"))
            if exp:
                doc["expires_at"] = exp
            await db.entitlements.update_one({"entitlement_id": ent_id}, {"$set": doc}, upsert=True)
            await db.users.update_one({"user_id": user["user_id"]},
                                      {"$set": {"account_type": acc["account_type"],
                                                "active_plan_id": acc["plan_id"], "active_audience": "pro"}})
            logger.info("Acesso %s concedido a %s (até %s)", acc["plan_id"], email, exp or "sem fim")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Provisionamento de %s falhou: %s", email, exc)
