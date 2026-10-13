"""Contas de clientes criadas a pedido do administrador (idempotente, executado no arranque)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("provisioned_accounts")

ACCOUNTS = [
    {"email": "construtoradavi15@gmail.com", "name": "Construtora Davi", "company_name": "Construtora Davi",
     "temp_password": "Davi1234", "account_type": "pro_business", "plan_id": "pro_business_yearly",
     "valid_days": 90},  # 3 meses a contar da criação do acesso
    # Contas E2E (teste automatizado em produção, validade 2 dias)
    {"email": "teste.particular+e2e@construpilot.pt", "name": "Teste Particular E2E",
     "temp_password": "TesteE2E!2026", "account_type": "particulier", "plan_id": None,
     "valid_days": 2, "e2e": True},
    {"email": "teste.pro+e2e@construpilot.pt", "name": "Teste Pro E2E", "company_name": "Teste Pro E2E",
     "temp_password": "TesteE2E!2026", "account_type": "pro", "plan_id": "pro_monthly",
     "valid_days": 2, "e2e": True},
    {"email": "teste.business+e2e@construpilot.pt", "name": "Teste Business E2E", "company_name": "Teste Business E2E",
     "temp_password": "TesteE2E!2026", "account_type": "pro_business", "plan_id": "pro_business_monthly",
     "valid_days": 2, "e2e": True},
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
                        "user_id": new_user_id(),
                        "must_change_password": not acc.get("e2e", False),
                        "email_verified": True, "two_fa_enabled": False,
                        "provisioned_by_admin": True, "created_at": now}
                await db.users.insert_one(dict(user))
                logger.info("Conta cliente criada pelo administrador: %s", email)
            elif acc.get("e2e"):
                # Contas E2E: repor sempre palavra-passe, account_type e email_verified (idempotente)
                await db.users.update_one(
                    {"user_id": user["user_id"]},
                    {"$set": {"account_type": acc["account_type"],
                              "email_verified": True,
                              "must_change_password": False,
                              "active": True,
                              "password_hash": hash_password(acc["temp_password"])}},
                )
                logger.info("Conta E2E reposta: %s", email)
            # Particular E2E: sem entitlement
            if not acc.get("plan_id"):
                continue
            ent_prefix = "e2e_grant" if acc.get("e2e") else "admin_grant"
            ent_id = f"{ent_prefix}_{user['user_id']}"
            ent = await db.entitlements.find_one({"entitlement_id": ent_id}, {"_id": 0})
            if ent and not acc.get("e2e"):
                exp = _expiry(ent.get("granted_at") or now, acc.get("valid_days"))
                if exp and not ent.get("expires_at"):
                    await db.entitlements.update_one({"entitlement_id": ent_id}, {"$set": {"expires_at": exp}})
                    logger.info("Validade de %s definida até %s", email, exp)
                continue
            doc = {"entitlement_id": ent_id, "user_id": user["user_id"], "plan_id": acc["plan_id"],
                   "status": "active",
                   "source": "e2e_test" if acc.get("e2e") else "admin_grant",
                   "granted_at": now}
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
