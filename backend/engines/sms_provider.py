"""SMS provider dispatcher (Twilio default, SMS.to opt-in).

Uso:
    from engines.sms_provider import get_sms_client
    client = get_sms_client()
    if client:
        resp = client.send(to="+3519xxx", message="Olá!")
        # resp: {"ok": bool, "id"?: str, "provider": "twilio"|"smsto", ...}

Selecção via env `SMS_PROVIDER` (`twilio` | `smsto`). Default: `twilio`.
Escolhido em tempo de chamada (não em import) para respeitar hot-reload de .env.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SmsToClient:
    """Cliente SMS.to (REST v1)."""

    API_URL = "https://api.sms.to/sms/send"

    def __init__(self, api_key: str, sender_id: str = "ConstruPilot") -> None:
        self.api_key = (api_key or "").strip()
        self.sender_id = (sender_id or "ConstruPilot").strip() or "ConstruPilot"

    def send(self, to: str, message: str) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "reason": "SMS_TO_API_KEY missing", "provider": "smsto"}
        if not to or not message:
            return {"ok": False, "reason": "missing to/message", "provider": "smsto"}
        try:
            r = httpx.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "to": to,
                    "message": message,
                    "sender_id": self.sender_id,
                },
                timeout=10.0,
            )
        except httpx.HTTPError as e:
            logger.error(f"SMS.to network error: {e}")
            return {"ok": False, "reason": f"network: {e}", "provider": "smsto"}
        if 200 <= r.status_code < 300:
            try:
                data = r.json()
            except Exception:
                data = {}
            return {
                "ok": True,
                "id": data.get("message_id") or data.get("id") or data.get("data", {}).get("message_id"),
                "raw": data,
                "provider": "smsto",
            }
        return {
            "ok": False,
            "status": r.status_code,
            "body": r.text[:500],
            "provider": "smsto",
        }


class TwilioClientWrapper:
    """Wrapper para o cliente Twilio existente em engines/alerting."""

    def __init__(self, client: Any, from_number: str) -> None:
        self.client = client
        self.from_number = from_number

    def send(self, to: str, message: str) -> dict[str, Any]:
        if not self.client:
            return {"ok": False, "reason": "twilio client unavailable", "provider": "twilio"}
        if not self.from_number:
            return {"ok": False, "reason": "TWILIO_FROM_NUMBER missing", "provider": "twilio"}
        try:
            msg = self.client.messages.create(
                to=to, from_=self.from_number, body=message)
            return {"ok": True, "id": getattr(msg, "sid", None), "provider": "twilio"}
        except Exception as e:
            logger.error(f"Twilio send error: {e}")
            return {"ok": False, "reason": str(e)[:300], "provider": "twilio"}


def get_sms_client() -> Any:
    """Devolve um cliente SMS conforme SMS_PROVIDER (default: twilio).

    Retorna None se o provider não puder ser inicializado (mantém compat).
    """
    provider = (os.getenv("SMS_PROVIDER") or "twilio").strip().lower()
    if provider == "smsto":
        api_key = os.getenv("SMS_TO_API_KEY", "")
        sender = os.getenv("SMS_TO_SENDER_ID", "ConstruPilot")
        if not api_key:
            logger.warning("SMS_PROVIDER=smsto mas SMS_TO_API_KEY vazia — client no-op")
        return SmsToClient(api_key=api_key, sender_id=sender)
    # Default: twilio
    try:
        from engines.alerting import _twilio_client
        client = _twilio_client()
    except Exception as e:
        logger.error(f"Twilio init falhou: {e}")
        return None
    from_number = os.getenv("TWILIO_FROM_NUMBER") or os.getenv("TWILIO_FROM") or ""
    return TwilioClientWrapper(client=client, from_number=from_number)
