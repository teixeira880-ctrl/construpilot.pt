"""Read-only, admin-only caller diagnostics. Never guesses/changes allowed IPs."""
import asyncio
import ipaddress
import os
from datetime import datetime, timezone

from pydantic import BaseModel

from engines import mercifacteur as mf


class PostalDiagnostics(BaseModel):
    configured: bool
    checked_at: str
    configured_ips: list[str]
    observed_ip: str | None = None
    ip_matches_configuration: bool | None = None
    probe_error: str | None = None
    provider_ok: bool = False
    provider_error_code: str | None = None
    price_total_ttc: float | None = None


async def diagnose() -> PostalDiagnostics:
    allowed = []
    for value in os.environ.get("MERCIFACTEUR_AUTHORIZED_IP", "").split(";"):
        try:
            allowed.append(str(ipaddress.ip_address(value.strip())))
        except ValueError:
            continue
    result = PostalDiagnostics(configured=mf.configured(), checked_at=datetime.now(timezone.utc).isoformat(), configured_ips=allowed)
    probe_url = os.environ.get("POSTAL_EGRESS_CHECK_URL")
    if probe_url:
        try:
            async with mf.make_client() as client:
                response = await asyncio.wait_for(client.get(probe_url), timeout=12)
            response.raise_for_status()
            result.observed_ip = str(ipaddress.ip_address(response.json()["ip"]))
            result.ip_matches_configuration = result.observed_ip in allowed
        except Exception:
            result.probe_error = "egress_check_unavailable"
    else:
        result.probe_error = "egress_check_not_configured"
    if result.configured:
        try:
            price = await mf.postage_price()
            result.provider_ok = True
            result.price_total_ttc = price["total_ttc"]
        except mf.PostalProviderError as exc:
            result.provider_error_code = exc.code
    else:
        result.provider_error_code = "not_configured"
    return result