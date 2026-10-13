"""Iter153 operator run: exactly one real Autodesk conversion using approved public fixture."""
import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import ezdxf
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from core.db import client, db
from engines.autodesk_client import AutodeskError
from engines.autodesk_dwg import convert

FIXTURE = Path("/app/integration/revision3/fixtures/public-line-2013.dwg")
REFERENCE = Path("/app/integration/revision3/fixtures/public-line-reference.dxf")
ARTIFACT = Path("/app/test_reports/artifacts/iter153_autodesk_output.dxf")
EXPECTED_SHA256 = "3815af3bfe9a0d45c1ce764a37871104eff791dd95cd095b338cc24863baa66f"
EXPECTED_SIZE = 16331
TOL = 1e-8


def assert_geometry(dxf_bytes: bytes):
    tmp = Path("/tmp/iter153_output_check.dxf")
    tmp.write_bytes(dxf_bytes)
    doc = ezdxf.readfile(tmp)
    audit = doc.audit()
    if audit.has_errors:
        raise RuntimeError("DXF audit failed")

    model = list(doc.modelspace())
    lines = [e for e in model if e.dxftype() == "LINE"]
    if len(lines) != 1:
        raise RuntimeError(f"Expected exactly 1 LINE, got {len(lines)}")

    line = lines[0]
    p1 = (float(line.dxf.start.x), float(line.dxf.start.y), float(line.dxf.start.z))
    p2 = (float(line.dxf.end.x), float(line.dxf.end.y), float(line.dxf.end.z))
    expected_a = (50.0, 50.0, 0.0)
    expected_b = (100.0, 100.0, 0.0)

    def close(a, b):
        return all(abs(x - y) <= TOL for x, y in zip(a, b))

    if not ((close(p1, expected_a) and close(p2, expected_b)) or (close(p1, expected_b) and close(p2, expected_a))):
        raise RuntimeError(f"Unexpected line geometry: {p1} -> {p2}")
    if line.dxf.layer != "0":
        raise RuntimeError(f"Expected layer 0, got {line.dxf.layer}")

    layers = {layer.dxf.name for layer in doc.layers}
    if not {"0", "Defpoints"}.issubset(layers):
        raise RuntimeError("Required layers 0/Defpoints missing")

    units = int(doc.header.get("$INSUNITS", 0))
    if units != 4:
        raise RuntimeError(f"Expected INSUNITS=4, got {units}")

    return {"dxfversion": doc.dxfversion, "units": units, "layers": sorted(layers)}


async def main():
    parser = argparse.ArgumentParser(description="Verify the already-authorized AutoCAD task; never submit another one.")
    parser.add_argument("--verify-existing", action="store_true", required=True)
    parser.parse_args()
    fixture = FIXTURE.read_bytes()
    digest = hashlib.sha256(fixture).hexdigest()
    if digest != EXPECTED_SHA256 or len(fixture) != EXPECTED_SIZE:
        raise SystemExit("Fixture integrity mismatch; aborting real run")

    admin = await db.users.find_one({"email": "admin@construpilot.fr"}, {"_id": 0, "user_id": 1})
    if not admin or not admin.get("user_id"):
        raise SystemExit("Admin user_id not found")
    user_id = admin["user_id"]

    job_key = hashlib.sha256(f"{user_id}:dwg-to-dxf:{digest}".encode()).hexdigest()
    existing = await db.cad_conversion_jobs.find_one({"_id": job_key}, {"_id": 0, "status": 1, "workitem_id": 1, "job_id": 1, "cache_expires_at": 1})
    if not existing or not existing.get("workitem_id") or existing.get("status") in {"failed_before_submit", "rejected"}:
        raise SystemExit("No resumable authorized task; refusing a new billable submission")
    if existing.get("status") == "success" and (not existing.get("cache_expires_at") or existing["cache_expires_at"].replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)):
        raise SystemExit("Authorized task cache expired; refusing a new billable submission")

    try:
        output, provenance = await convert(fixture, user_id=user_id)
    except AutodeskError as exc:
        payload = {
            "ok": False,
            "code": exc.code,
            "fallback_safe": exc.fallback_safe,
            "status": exc.status,
            "existing_status": existing.get("status"),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_bytes(output)

    reference_sha = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    output_sha = hashlib.sha256(output).hexdigest()
    geometry = assert_geometry(output)

    job = await db.cad_conversion_jobs.find_one({"_id": job_key}, {"_id": 0})
    if not job:
        raise RuntimeError("Job metadata missing after conversion")

    leaked = []
    job_dump = json.dumps(job, default=str)
    for marker in ("Bearer ", "https://", "uploadKey", "APS_CLIENT_SECRET", "APS_CLIENT_ID"):
        if marker in job_dump:
            leaked.append(marker)

    result = {
        "ok": True,
        "admin_user_id": user_id,
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "provider_status": job.get("provider_status"),
        "workitem_id_present": bool(job.get("workitem_id")),
        "cache_id": job.get("cache_id"),
        "cache_expires_at": str(job.get("cache_expires_at")),
        "cleanup_pending": bool(job.get("cleanup_pending")),
        "output_sha256": output_sha,
        "reference_sha256": reference_sha,
        "output_size": len(output),
        "provenance_provider": provenance.get("provider"),
        "provenance_cached": provenance.get("cached", False),
        "provenance_format_version": provenance.get("format_version"),
        "geometry": geometry,
        "artifact": str(ARTIFACT),
        "metadata_leak_markers": leaked,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        client.close()