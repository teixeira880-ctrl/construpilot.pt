import pytest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from check_autodesk_access import run_check


class TestIter152AutodeskApsReadonly:
    """Read-only APS auth + engines listing + external app health."""

    def test_aps_token_and_engines_readonly(self):
        data = run_check()

        if not data.get("configured"):
            pytest.fail(f"APS env not fully configured: missing={data.get('missing_keys')}")

        assert data["health"]["status"] == 200, "External /api/ health endpoint should return 200"
        assert data["requests_made"]["token"] == 1, "Exactly one token request required"

        token_status = data["token"]["status"]
        assert isinstance(token_status, int), f"Token request failed at transport stage: {token_status}"
        assert token_status == 200, (
            "APS token stage failed "
            f"status={token_status} code={data['token'].get('error_code')}"
        )

        ttl = data["token"].get("ttl")
        assert isinstance(ttl, int), "Token TTL must be an integer when token succeeds"

        assert data["requests_made"]["engines"] == 1, "Exactly one engines request required after token success"
        engines_status = data["engines"]["status"]
        assert isinstance(engines_status, int), f"Engines request failed at transport stage: {engines_status}"
        assert engines_status == 200, (
            "APS engines stage failed "
            f"status={engines_status} code={data['engines'].get('error_code')}"
        )

        assert isinstance(data["engines"]["count"], int)
        assert data["engines"]["count"] > 0, "At least one AutoCAD engine must be listed"
        assert isinstance(data["engines"]["autocad_engine_ids"], list)
