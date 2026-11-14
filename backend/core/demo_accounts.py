"""Contas de demonstração e de testes no construpilot.pt — 14/11 (Martinho).

1) Empresa fictícia «Teste Websummit» (dona teste.websummit@construpilot.pt, ~50 trolhas @tws.construpilot.pt, diretores,
   arquiteta, clientes @clientes.tws.construpilot.pt): MANTÉM-SE, mas não pode constar como contas oficiais →
   marcada is_demo=True e excluída da lista de utilizadores do admin, das contagens, das exportações e dos e-mails.
2) Contas criadas por testes automáticos (domínios reservados de teste) e as 2 contas do stand Web Summit: APAGADAS uma
   única vez (marcador em db.maintenance_runs), com todos os dados (core.account_purge). As contas admin nunca são apagadas.
"""
import hashlib
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger("demo_accounts")

NOT_DEMO = {"is_demo": {"$ne": True}}

DEMO_OWNER_EMAIL = "teste.websummit@construpilot.pt"
DEMO_EMAIL_RX = r"@(clientes\.)?tws\.construpilot\.pt$"
TEST_EMAIL_RX = r"@(test\.fr|example\.(com|org|net)|test\.local|tests?\.construpilot\.(pt|fr))$"
PURGE_RUN_ID = "purge_test_and_stand_accounts_2026_11_14"


def stand_emails() -> list[str]:
    return sorted({(os.environ.get("WEBSUMMIT_DEMO_EMAIL_PT") or "demo.websummit@construpilot.pt").strip().lower(),
                   (os.environ.get("WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT") or "demo.websummit.particular@construpilot.pt").strip().lower()}
                  - {"", "<redacted>"})


def is_demo_email(email: str | None) -> bool:
    e = str(email or "").strip().lower()
    return e == DEMO_OWNER_EMAIL or bool(re.search(DEMO_EMAIL_RX, e))


async def mark_demo(db) -> int:
    """Marca a empresa fictícia (dona + membros da organização/empregador + e-mails do domínio fictício)."""
    owner = await db.users.find_one({"email": DEMO_OWNER_EMAIL}, {"_id": 0, "user_id": 1, "organization_id": 1})
    ors = [{"email": DEMO_OWNER_EMAIL}, {"email": {"$regex": DEMO_EMAIL_RX, "$options": "i"}}]
    if owner:
        ors.append({"employer_id": owner["user_id"]})
        if owner.get("organization_id"):
            ors.append({"organization_id": owner["organization_id"]})
    r = await db.users.update_many({"$or": ors, "role": {"$ne": "admin"}, "is_demo": {"$ne": True}},
                                   {"$set": {"is_demo": True, "demo_company": "Teste Websummit"}})
    return r.modified_count


def _purge_filter() -> dict:
    return {"role": {"$ne": "admin"},
            "$or": [{"email": {"$regex": TEST_EMAIL_RX, "$options": "i"}}, {"email": {"$in": stand_emails()}}]}


async def purge_test_and_stand(db, dry_run: bool = False) -> dict:
    """Apaga (uma vez) as contas de testes automáticos e as do stand Web Summit, com todos os seus dados."""
    if not dry_run and await db.maintenance_runs.find_one({"_id": PURGE_RUN_ID}):
        return {"status": "already_done"}
    users = await db.users.find(_purge_filter(), {"_id": 0, "user_id": 1, "email": 1}).to_list(5000)
    if dry_run:
        return {"status": "dry_run", "accounts": [u["email"] for u in users]}
    from core.account_purge import purge_user_data
    total = 0
    for u in users:
        try:
            purged = await purge_user_data(u["user_id"])
            await db.users.delete_one({"user_id": u["user_id"]})
            await db.user_sessions.delete_many({"user_id": u["user_id"]})
            await db.deleted_accounts.insert_one({"email_hash": hashlib.sha256(u["email"].encode()).hexdigest(),
                                                  "deleted_at": datetime.now(timezone.utc).isoformat(),
                                                  "purged_total": sum(purged.values()), "reason": PURGE_RUN_ID})
            total += 1
        except Exception:  # noqa: BLE001 — uma conta falhada não impede as outras
            logger.exception("purge %s failed", u.get("email"))
    await db.maintenance_runs.update_one({"_id": PURGE_RUN_ID},
                                         {"$set": {"done_at": datetime.now(timezone.utc).isoformat(), "deleted_accounts": total}},
                                         upsert=True)
    return {"status": "done", "deleted_accounts": total}


async def run_on_startup(db) -> dict:
    out = {}
    try:
        out["purge"] = await purge_test_and_stand(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("purge skipped: %s", exc)
    try:
        out["demo_marked"] = await mark_demo(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mark_demo skipped: %s", exc)
    return out
