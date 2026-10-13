"""APS transport: server-only credentials, finite requests, no automatic retries."""
import asyncio
import hashlib
import os
import time
from urllib.parse import urlsplit

import httpx

SCOPES = "code:all bucket:create bucket:read data:create data:read data:write"
MAX_BYTES = 50 * 1024 * 1024
_token = {}
_lock = asyncio.Lock()


class AutodeskError(RuntimeError):
    def __init__(self, code, message, *, fallback_safe=False, status=None):
        super().__init__(message)
        self.code, self.fallback_safe, self.status = code, fallback_safe, status


def config(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise AutodeskError("not_configured", "Conversão Autodesk não configurada.", fallback_safe=True)
    return value


def api_base():
    return f"{config('APS_AUTOMATION_BASE_URL').rstrip('/')}/{config('APS_AUTOMATION_REGION')}/v3"


def client():
    return httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=False)


async def token():
    fingerprint = hashlib.sha256("|".join(config(k) for k in ("APS_CLIENT_ID", "APS_CLIENT_SECRET", "APS_TOKEN_URL")).encode()).hexdigest()
    async with _lock:
        if _token.get("config") == fingerprint and _token.get("expires", 0) > time.monotonic() + 60:
            return _token["value"]
        try:
            async with client() as http:
                response = await http.post(config("APS_TOKEN_URL"), auth=(config("APS_CLIENT_ID"), config("APS_CLIENT_SECRET")),
                    data={"grant_type": "client_credentials", "scope": SCOPES})
            data = response.json() if response.is_success else {}
            if not isinstance(data.get("access_token"), str):
                raise AutodeskError("authentication_failed", "A Autodesk não autoriza a ligação de conversão.", fallback_safe=True, status=response.status_code)
            _token.update(value=data["access_token"], expires=time.monotonic() + int(data["expires_in"]), config=fingerprint)
            return _token["value"]
        except (httpx.HTTPError, ValueError, KeyError):
            raise AutodeskError("authentication_unavailable", "Autenticação Autodesk temporariamente indisponível.", fallback_safe=True) from None


async def request(method, url, *, accepted=(), **kwargs):
    access = await token()
    try:
        async with client() as http:
            response = await http.request(method, url, headers={"Authorization": f"Bearer {access}"}, **kwargs)
    except httpx.HTTPError:
        raise AutodeskError("transport_error", "Resposta Autodesk indisponível. A tarefa não é relançada automaticamente.") from None
    if response.is_success or response.status_code in accepted:
        return response
    raise AutodeskError("provider_http_error", "A Autodesk recusou a operação de conversão.",
                        fallback_safe=400 <= response.status_code < 500 and response.status_code != 408,
                        status=response.status_code)


def check_signed_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or not any(host.endswith("." + domain) or host == domain for domain in ("amazonaws.com", "autodesk.com", "cloudfront.net")):
        raise AutodeskError("unsafe_storage_url", "Endereço de armazenamento Autodesk recusado.")


async def signed_put(url, data):
    check_signed_url(url)
    try:
        async with client() as http:
            response = await http.put(url, content=data, timeout=120)
        if not response.is_success:
            raise AutodeskError("upload_failed", "Envio do DWG para a Autodesk impossível.", fallback_safe=True)
    except httpx.HTTPError:
        raise AutodeskError("upload_unavailable", "Armazenamento Autodesk indisponível.", fallback_safe=True) from None


async def signed_download(url):
    check_signed_url(url)
    chunks, size = [], 0
    try:
        async with client() as http, http.stream("GET", url, timeout=120) as response:
            if not response.is_success:
                raise AutodeskError("download_failed", "O resultado Autodesk ainda não está disponível.")
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise AutodeskError("output_too_large", "DXF Autodesk demasiado volumoso (>50 MB).")
                chunks.append(chunk)
    except httpx.HTTPError:
        raise AutodeskError("download_unavailable", "Transferência Autodesk interrompida, sem nova conversão.") from None
    return b"".join(chunks)