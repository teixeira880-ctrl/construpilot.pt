"""Backfill: define lang='pt' em todos os utilizadores que não têm o campo definido.

Sem `lang`, o motor de emails caía para o default (agora 'pt', antes 'fr') → todos
os emails transacionais saíam em francês. Este script normaliza o Mongo.

Execução:
    python -m scripts.backfill_user_lang_pt
"""
import asyncio
import os


async def main():
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

    # 1) Utilizadores sem `lang`
    n_missing = await db.users.count_documents({"lang": {"$exists": False}})
    res1 = await db.users.update_many(
        {"lang": {"$exists": False}},
        {"$set": {"lang": "pt"}},
    )
    # 2) Utilizadores com `lang` a null / string vazia
    res2 = await db.users.update_many(
        {"$or": [{"lang": None}, {"lang": ""}]},
        {"$set": {"lang": "pt"}},
    )

    total_users = await db.users.count_documents({})
    by_lang = {}
    async for u in db.users.find({}, {"lang": 1}):
        by_lang[u.get("lang") or "<none>"] = by_lang.get(u.get("lang") or "<none>", 0) + 1

    print(f"[backfill_user_lang_pt] DB={os.environ.get('DB_NAME') or 'construpilot'}")
    print(f"  users total          : {total_users}")
    print(f"  missing lang before  : {n_missing}")
    print(f"  updated (missing)    : {res1.modified_count}")
    print(f"  updated (null/empty) : {res2.modified_count}")
    print(f"  distribution         : {by_lang}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
