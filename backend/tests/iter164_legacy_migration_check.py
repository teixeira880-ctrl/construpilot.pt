"""Iter 164 — legacy allowance migration validated against real DB with fake org key."""
import asyncio
import os
import sys

sys.path.append("/app/backend")

from core.db import db  # noqa
from engines import postal_offer as po  # noqa

FAKE_KEY = "org:test_qa_iter164"
FAKE_USER = {"user_id": "u_qa", "role": "user", "account_type": "pro",
             "active": True, "company_active": True,
             "organization_id": "test_qa_iter164", "org_role": "owner"}


async def main():
    # cleanup any prior
    await db.postal_demo_allowances.delete_one({"_id": FAKE_KEY})

    # Insert legacy shape doc
    await db.postal_demo_allowances.insert_one({
        "_id": FAKE_KEY, "postal_id": "post_old_qa", "user_id": "u_qa",
        "opp_id": "opp_qa", "status": "used"
    })

    offer = await po.offer_for(FAKE_USER)
    print("MIGRATED OFFER:", offer.model_dump())
    assert offer.demo_limit == 20
    assert offer.used == 1
    assert offer.remaining == 19
    assert offer.eligible is True

    # Verify doc migrated
    doc = await db.postal_demo_allowances.find_one({"_id": FAKE_KEY})
    print("DOC AFTER MIGRATE:", {k: doc.get(k) for k in ("_id", "count", "sends", "migrated_at")})
    assert doc.get("count") == 1
    assert isinstance(doc.get("sends"), list) and len(doc["sends"]) == 1
    assert "postal_id" not in doc  # old fields unset

    # cleanup
    await db.postal_demo_allowances.delete_one({"_id": FAKE_KEY})
    print("OK: legacy migration validated, doc cleaned up")


asyncio.run(main())
