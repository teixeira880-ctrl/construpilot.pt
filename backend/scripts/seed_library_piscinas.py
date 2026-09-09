"""Insere (com upsert) os 27 items da categoria «Piscinas» nas bibliotecas
de todos os utilizadores existentes cujo starter catalogue já foi semeado.

- Idempotente: usa `(user_id, designation, category)` como chave; se já existir,
  atualiza `unit_price_ht`, `unit`, `vat_rate` e `updated_at`. Não duplica.
- Reutiliza a lista canónica declarada em `routes.library.STARTER_CATALOGUE`
  (secção «Piscinas»), para manter uma única fonte de verdade.

Execução CLI:
    python -m scripts.seed_library_piscinas

Execução HTTP:
    POST /api/admin/migrations/run  (Bearer admin)
"""
from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _piscina_items() -> list[dict]:
    from routes.library import STARTER_CATALOGUE
    return [it for it in STARTER_CATALOGUE if it.get("category") == "Piscinas"]


async def _upsert_for_user(db, user_id: str, items: list[dict]) -> tuple[int, int]:
    """Retorna (inseridos, atualizados)."""
    inserted = updated = 0
    for item in items:
        existing = await db.library_items.find_one({
            "user_id": user_id,
            "designation": item["designation"],
            "category": "Piscinas",
        })
        if existing:
            await db.library_items.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "type": item["type"],
                    "unit": item["unit"],
                    "unit_price_ht": round(float(item["unit_price_ht"]), 2),
                    "vat_rate": float(item["vat_rate"]),
                    "updated_at": _now(),
                }},
            )
            updated += 1
        else:
            now = _now()
            await db.library_items.insert_one({
                "item_id": "lib_" + secrets.token_hex(6),
                "user_id": user_id,
                "type": item["type"],
                "category": "Piscinas",
                "designation": item["designation"],
                "unit": item["unit"],
                "unit_price_ht": round(float(item["unit_price_ht"]), 2),
                "vat_rate": float(item["vat_rate"]),
                "notes": "",
                "source": "piscinas_seed",
                "created_at": now,
                "updated_at": now,
            })
            inserted += 1
    return inserted, updated


async def run(db=None) -> dict:
    """Executa o seed. Se `db` é passado (uso HTTP), reutiliza a conexão do backend;
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

    items = _piscina_items()
    users = await db.users.find({"library_seeded": True}, {"user_id": 1}).to_list(5000)

    total_ins = total_upd = 0
    for u in users:
        ins, upd = await _upsert_for_user(db, u["user_id"], items)
        total_ins += ins
        total_upd += upd

    total_in_db = await db.library_items.count_documents({"category": "Piscinas"})

    if client is not None:
        client.close()

    return {
        "canonical_items": len(items),
        "users_processed": len(users),
        "inserted": total_ins,
        "updated": total_upd,
        "total_in_db": total_in_db,
    }


async def _main_cli() -> None:
    result = await run()
    print(f"[seed_library_piscinas] {result}")


if __name__ == "__main__":
    asyncio.run(_main_cli())
