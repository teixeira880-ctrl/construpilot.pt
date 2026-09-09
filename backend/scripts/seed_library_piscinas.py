"""Insere (com upsert) os 27 items da categoria «Piscinas» nas bibliotecas
de todos os utilizadores existentes cujo starter catalogue já foi semeado.

- Idempotente: usa `(user_id, designation, category)` como chave; se já existir,
  atualiza `unit_price_ht`, `unit`, `vat_rate` e `updated_at`. Não duplica.
- Reutiliza a lista canónica declarada em `routes.library.STARTER_CATALOGUE`
  (secção «Piscinas»), para manter uma única fonte de verdade.

Execução:
    cd /app/backend && python -m scripts.seed_library_piscinas
"""
from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone

from core.db import db
from routes.library import STARTER_CATALOGUE

PISCINA_ITEMS = [it for it in STARTER_CATALOGUE if it.get("category") == "Piscinas"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _upsert_for_user(user_id: str) -> tuple[int, int]:
    """Retorna (inseridos, atualizados)."""
    inserted = updated = 0
    for item in PISCINA_ITEMS:
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


async def main() -> None:
    if not PISCINA_ITEMS:
        print("[seed_library_piscinas] nenhum item de piscina em STARTER_CATALOGUE — abortar")
        return
    users = await db.users.find({"library_seeded": True}, {"user_id": 1}).to_list(2000)
    print(f"[seed_library_piscinas] items canónicos={len(PISCINA_ITEMS)} · users semeados={len(users)}")

    total_ins = total_upd = 0
    for u in users:
        ins, upd = await _upsert_for_user(u["user_id"])
        total_ins += ins
        total_upd += upd
        print(f"  · {u['user_id']}: inseridos={ins} atualizados={upd}")

    grand_total = await db.library_items.count_documents({"category": "Piscinas"})
    print(f"[seed_library_piscinas] concluído — inseridos={total_ins} atualizados={total_upd} · "
          f"total em library_items (Piscinas)={grand_total}")


if __name__ == "__main__":
    asyncio.run(main())
