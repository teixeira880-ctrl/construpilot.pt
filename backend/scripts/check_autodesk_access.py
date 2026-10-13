"""Read-only Autodesk APS connectivity check.

Rules enforced:
- 1 token request max (client_credentials, HTTP Basic)
- 1 engines request max (only if token succeeds)
- no token/client secret value exposure in output
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv


def _load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    load_dotenv(root.parent / "frontend" / ".env")


def _safe_error_code(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except Exception:
        return None
    if isinstance(data, dict):
        for key in ("errorCode", "error", "code"):
            value = data.get(key)
            if isinstance(value, str) and value.strip() in {
                "invalid_client", "invalid_grant", "invalid_request", "invalid_scope",
                "unauthorized_client", "unsupported_grant_type", "AUTH-001", "AUTH-010",
            }:
                return value.strip()
    if response.is_error:
        return "upstream_error"
    return None


def _extract_scopes(payload: Dict[str, Any]) -> List[str]:
    scope = payload.get("scope") or payload.get("scopes")
    if isinstance(scope, str):
        return [s for s in scope.split() if s == "code:all"]
    if isinstance(scope, list):
        return [s for s in scope if s == "code:all"]
    return []


def _engine_items(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "items", "engines"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _extract_engine_id(item: Any) -> str | None:
    if isinstance(item, str) and item.strip():
        return item.strip()
    if isinstance(item, dict):
        for key in ("id", "engine", "engineId", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_engine_ids(payload: Any) -> List[str]:
    ids: List[str] = []
    for item in _engine_items(payload):
        engine_id = _extract_engine_id(item)
        if engine_id and re.fullmatch(r"Autodesk\.AutoCAD\+[A-Za-z0-9_.-]{1,40}", engine_id):
            ids.append(engine_id)
    return ids


def run_check() -> Dict[str, Any]:
    _load_env()

    required = [
        "APS_CLIENT_ID",
        "APS_CLIENT_SECRET",
        "APS_TOKEN_URL",
        "APS_AUTOMATION_BASE_URL",
        "APS_AUTOMATION_REGION",
        "REACT_APP_BACKEND_URL",
    ]
    missing = [key for key in required if not os.environ.get(key)]

    result: Dict[str, Any] = {
        "configured": len(missing) == 0,
        "configured_keys": [k for k in required if os.environ.get(k)],
        "missing_keys": missing,
        "requests_made": {"token": 0, "engines": 0},
        "health": {"status": None},
        "token": {"status": None, "granted_scopes": [], "ttl": None, "error_code": None},
        "engines": {
            "status": None,
            "count": 0,
            "total_count": 0,
            "autocad_engine_ids": [],
            "error_code": None,
        },
    }

    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    if backend_url:
        try:
            with httpx.Client(timeout=15.0, follow_redirects=False) as client:
                health = client.get(f"{backend_url}/api/")
            result["health"]["status"] = health.status_code
        except Exception:
            result["health"]["status"] = "request_error"

    if missing:
        return result

    token_url = os.environ["APS_TOKEN_URL"]
    base_url = os.environ["APS_AUTOMATION_BASE_URL"].rstrip("/")
    region = os.environ["APS_AUTOMATION_REGION"].strip()

    try:
        with httpx.Client(timeout=15.0, follow_redirects=False) as client:
            result["requests_made"]["token"] = 1
            token_resp = client.post(
                token_url,
                auth=(os.environ["APS_CLIENT_ID"], os.environ["APS_CLIENT_SECRET"]),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials", "scope": "code:all"},
            )
            result["token"]["status"] = token_resp.status_code
            result["token"]["error_code"] = _safe_error_code(token_resp)

            token_payload: Dict[str, Any] = {}
            try:
                parsed = token_resp.json()
                if isinstance(parsed, dict):
                    token_payload = parsed
            except Exception:
                token_payload = {}

            result["token"]["granted_scopes"] = _extract_scopes(token_payload)
            expires_in = token_payload.get("expires_in")
            if isinstance(expires_in, int):
                result["token"]["ttl"] = expires_in
            elif isinstance(expires_in, str) and expires_in.isdigit():
                result["token"]["ttl"] = int(expires_in)

            access_token = token_payload.get("access_token") if token_resp.is_success else None
            if not isinstance(access_token, str) or not access_token.strip():
                return result

            result["requests_made"]["engines"] = 1
            engines_resp = client.get(
                f"{base_url}/{region}/v3/engines",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            result["engines"]["status"] = engines_resp.status_code
            result["engines"]["error_code"] = _safe_error_code(engines_resp)

            try:
                engines_payload = engines_resp.json()
            except Exception:
                engines_payload = {}

            all_items = _engine_items(engines_payload)
            engine_ids = _extract_engine_ids(engines_payload)
            result["engines"]["autocad_engine_ids"] = engine_ids
            result["engines"]["count"] = len(engine_ids)
            result["engines"]["total_count"] = len(all_items)
    except Exception:
        if result["token"]["status"] is None:
            result["token"]["status"] = "request_error"
        elif result["requests_made"]["engines"] and result["engines"]["status"] is None:
            result["engines"]["status"] = "request_error"

    return result


if __name__ == "__main__":
    print(json.dumps(run_check(), ensure_ascii=False))
