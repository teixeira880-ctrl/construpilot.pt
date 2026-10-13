"""Explicit operator setup. Creates only the named Activity/alias/transient bucket.
No WorkItem is ever submitted. Run once before enabling APS_DWG_ENABLED.
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.db import client, db
from engines.autodesk_activity import provision
from engines.autodesk_client import AutodeskError


async def main():
    try:
        result = await provision()
        set_key(str(ROOT / ".env"), "APS_ACTIVITY_QUALIFIED", result["qualified_activity"])
        await db.plan_cad_sources.create_index("expires_at", expireAfterSeconds=0, name="cad_cache_expiry")
        # Metadata excludes namespace/client ID and all credential material.
        print(json.dumps({"configured": True, "engine": result["engine"], "version": result["version"],
            "activity_created": result["created"], "specification_sha256": result["specification_sha256"], "workitems_submitted": 0}))
    except AutodeskError as exc:
        print(json.dumps({"configured": False, "error_code": exc.code, "http_status": exc.status, "workitems_submitted": 0}))
        raise SystemExit(1) from None
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())