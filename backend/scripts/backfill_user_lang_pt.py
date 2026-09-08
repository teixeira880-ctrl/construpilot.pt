"""Backfill: define lang='pt' em todos os utilizadores que não têm o campo definido.

Sem `lang`, o motor de emails caía para o default (antes 'fr') → todos os emails
transacionais saíam em francês. Este módulo expõe `run(db=None)` reutilizável
(script CLI + endpoint HTTP admin).

Execução CLI:
    python -m scripts.backfill_user_lang_pt

Execução HTTP:
    POST /api/admin/migrations/run  (Bearer admin)
"""
import asyncio
import os


async def run(db=None) -> dict:
    """Executa o backfill. Se `db` é passado (uso HTTP), reutiliza a conexão do backend;
    senão abre uma conexão nova (uso CLI)."""
    client = None
    if db is None:
        try:
            from pathlib import Path
            from dotenv import load_dotenv
            env_path = Path(__file__).resolve().parents[1] / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except Exception:
            pass
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ.get("DB_NAME") or "construpilot"]

    total_users_before = await db.users.count_documents({})
    n_missing = await db.users.count_documents({"lang": {"$exists": False}})
    res1 = await db.users.update_many(
        {"lang": {"$exists": False}},
        {"$set": {"lang": "pt"}},
    )
    res2 = await db.users.update_many(
        {"$or": [{"lang": None}, {"lang": ""}]},
        {"$set": {"lang": "pt"}},
    )
    by_lang: dict[str, int] = {}
    async for u in db.users.find({}, {"lang": 1}):
        k = u.get("lang") or "<none>"
        by_lang[k] = by_lang.get(k, 0) + 1

    if client is not None:
        client.close()

    return {
        "users_total": total_users_before,
        "missing_lang_before": n_missing,
        "updated_missing": res1.modified_count,
        "updated_null_or_empty": res2.modified_count,
        "distribution_after": by_lang,
    }


async def _main_cli() -> None:
    r = await run()
    print(f"[backfill_user_lang_pt] DB={os.environ.get('DB_NAME') or 'construpilot'}")
    for k, v in r.items():
        print(f"  {k:22s}: {v}")


if __name__ == "__main__":
    asyncio.run(_main_cli())
