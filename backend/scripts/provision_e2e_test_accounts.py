"""Provisionamento idempotente de contas de teste E2E (particular, pro, pro_business).

Executar com o venv do backend:
    /root/.venv/bin/python /app/backend/scripts/provision_e2e_test_accounts.py

Lê MONGO_URL e DB_NAME do /app/backend/.env (mesma config que o backend em produção).
Idempotente: se a conta já existir, só actualiza plano/validade/email_verified sem reiniciar
palavras-passe nem apagar dados.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Importar bcrypt a partir do venv do backend
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bcrypt  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# SEC-Z-002: password lida do env, sem fallback hardcoded.
# Em dev/CI, exportar: E2E_TEST_PASSWORD=TesteE2E!2026
TEST_PASSWORD = os.environ.get("E2E_TEST_PASSWORD", "")
VALID_DAYS = 2

if not TEST_PASSWORD:
    print("Erro: E2E_TEST_PASSWORD não definida no ambiente. Abortar.", file=sys.stderr)
    sys.exit(1)

ACCOUNTS = [
    {
        "email": "teste.particular+e2e@construpilot.pt",
        "name": "Teste Particular E2E",
        "account_type": "particular",
        "plan_id": None,
        "grant_entitlement": False,
    },
    {
        "email": "teste.pro+e2e@construpilot.pt",
        "name": "Teste Pro E2E",
        "company_name": "Teste Pro E2E",
        "account_type": "pro",
        "plan_id": "pro_monthly",
        "grant_entitlement": True,
    },
    {
        "email": "teste.business+e2e@construpilot.pt",
        "name": "Teste Business E2E",
        "company_name": "Teste Business E2E",
        "account_type": "pro_business",
        "plan_id": "pro_business_monthly",
        "grant_entitlement": True,
    },
]


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def new_user_id() -> str:
    return f"user_{uuid.uuid4().hex[:12]}"


async def _upsert_user(db, acc: dict, now_iso: str) -> tuple[dict, bool]:
    """Devolve (user_doc, created_bool). Se existir, só actualiza campos seguros."""
    email = acc["email"].lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        updates = {
            "account_type": acc["account_type"],
            "email_verified": True,
            "must_change_password": False,
            "active": True,
        }
        # Repor palavra-passe para o valor conhecido do teste (idempotente para E2E)
        updates["password_hash"] = hash_password(TEST_PASSWORD)
        if acc.get("company_name"):
            updates["company_name"] = acc["company_name"]
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
        user.update(updates)
        return user, False

    doc = {
        "user_id": new_user_id(),
        "email": email,
        "name": acc["name"],
        "role": "user",
        "account_type": acc["account_type"],
        "company_name": acc.get("company_name"),
        "country": "PT",
        "language": "pt",
        "password_hash": hash_password(TEST_PASSWORD),
        "auth_provider": "password",
        "picture": None,
        "must_change_password": False,
        "email_verified": True,
        "two_fa_enabled": False,
        "provisioned_by_admin": True,
        "active": True,
        "created_at": now_iso,
    }
    if acc.get("plan_id"):
        doc["plan"] = "premium"
    await db.users.insert_one(dict(doc))
    return doc, True


async def _grant_entitlement(db, user: dict, acc: dict, now_iso: str) -> str:
    ent_id = f"e2e_grant_{user['user_id']}"
    expires_at = (datetime.fromisoformat(now_iso) + timedelta(days=VALID_DAYS)).isoformat()
    doc = {
        "entitlement_id": ent_id,
        "user_id": user["user_id"],
        "plan_id": acc["plan_id"],
        "status": "active",
        "source": "e2e_test",
        "granted_at": now_iso,
        "expires_at": expires_at,
    }
    await db.entitlements.update_one(
        {"entitlement_id": ent_id}, {"$set": doc}, upsert=True
    )
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"active_plan_id": acc["plan_id"], "active_audience": "pro"}},
    )
    return expires_at


async def main() -> None:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    now_iso = datetime.now(timezone.utc).isoformat()

    print(f"[provision_e2e] BD destino: {DB_NAME} @ {MONGO_URL.split('@')[-1]}")
    created, updated, granted = 0, 0, 0

    for acc in ACCOUNTS:
        user, was_created = await _upsert_user(db, acc, now_iso)
        if was_created:
            created += 1
            print(f"  [+] CRIADA   {acc['email']}  (user_id={user['user_id']})")
        else:
            updated += 1
            print(f"  [=] ACTUALIZADA  {acc['email']}  (user_id={user['user_id']})")

        if acc.get("grant_entitlement"):
            exp = await _grant_entitlement(db, user, acc, now_iso)
            granted += 1
            print(f"      entitlement {acc['plan_id']} activo até {exp}")

    print(
        f"[provision_e2e] Resumo: criadas={created}  actualizadas={updated}  "
        f"entitlements={granted}  total={len(ACCOUNTS)}"
    )
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
