"""Acessos oferecidos a clientes reais (criados a pedido do fundador).

Corre SEMPRE no arranque (como o seed do Web Summit), ao contrário de
`provisioned_accounts.py`, que só corre com SEED_DEMO_DATA=true porque contém
contas de teste.

Regras:
  - Zero password em claro no código: a palavra-passe provisória é lida de uma
    variável de ambiente por conta. Sem variável → conta saltada (fail-closed).
  - Conta nova: criada com `must_change_password=True` (a app obriga a mudar a
    palavra-passe na primeira ligação) e um entitlement com `expires_at`.
  - Conta existente: a palavra-passe NUNCA é reescrita. Só é garantido o
    entitlement (uma vez; a validade conta a partir da primeira concessão).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("client_grants")

GRANTS = [
    {"email": "ruifilipemaga@gmail.com", "name": "Rui Filipe",
     "temp_password_env": "GRANT_RUI_PASSWORD",
     "account_type": "pro_business", "plan_id": "pro_business_yearly",
     "valid_days": 90},  # Pro Business gratuito durante 3 meses
]


def _env(key: str) -> str | None:
    v = (os.environ.get(key) or "").strip()
    return v or None


async def apply_client_grants(db, hash_password, new_user_id, now: datetime | None = None) -> dict:
    now_dt = now or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    summary: dict[str, str] = {}
    for g in GRANTS:
        email = g["email"].lower().strip()
        try:
            user = await db.users.find_one({"email": email}, {"_id": 0})
            if not user:
                pw = _env(g["temp_password_env"])
                if not pw:
                    logger.warning("Acesso de %s saltado: variável %s ausente", email, g["temp_password_env"])
                    summary[email] = "skipped_no_password"
                    continue
                user = {"email": email, "name": g["name"], "role": "user", "plan": "premium",
                        "account_type": g["account_type"], "company_name": g.get("company_name"),
                        "country": "PT", "language": "pt",
                        "password_hash": hash_password(pw), "auth_provider": "password",
                        "picture": None, "user_id": new_user_id(),
                        "must_change_password": True, "email_verified": True,
                        "two_fa_enabled": False, "provisioned_by_admin": True,
                        "created_at": now_iso}
                await db.users.insert_one(dict(user))
                summary[email] = "created"
            else:
                summary[email] = "exists"
            ent_id = f"admin_grant_{user['user_id']}"
            if await db.entitlements.find_one({"entitlement_id": ent_id}, {"_id": 0}):
                continue
            exp = (now_dt + timedelta(days=g["valid_days"])).isoformat()
            await db.entitlements.update_one(
                {"entitlement_id": ent_id},
                {"$set": {"entitlement_id": ent_id, "user_id": user["user_id"],
                          "plan_id": g["plan_id"], "status": "active",
                          "source": "admin_grant", "granted_at": now_iso, "expires_at": exp}},
                upsert=True)
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"account_type": g["account_type"], "plan": "premium",
                          "active_plan_id": g["plan_id"], "active_audience": "pro"}})
            summary[email] += "+granted"
            logger.info("Acesso %s concedido a %s até %s", g["plan_id"], email, exp)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Acesso de %s falhou: %s", email, exc)
            summary[email] = "error"
    return summary
