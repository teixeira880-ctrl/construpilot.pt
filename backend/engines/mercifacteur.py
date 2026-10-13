"""Merci Facteur v1.2. No automatic retry of a billable POST, including HTTP401."""
import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
import math
import os
import time

import httpx

log = logging.getLogger(__name__)
_token = {}
_token_lock = asyncio.Lock()
MODES = ("normal", "suivi", "lrar")
KEYS = ("MERCIFACTEUR_BASE_URL", "MERCIFACTEUR_PUBLIC_KEY", "MERCIFACTEUR_SECRET_KEY",
        "MERCIFACTEUR_USER_ID", "MERCIFACTEUR_AUTHORIZED_IP")


class PostalProviderError(RuntimeError):
    def __init__(self, code, message, uncertain=False):
        self.code, self.uncertain = code, uncertain
        super().__init__(message)


def configured():
    return all(os.environ.get(key) for key in KEYS)


def _env(key):
    if not os.environ.get(key):
        raise PostalProviderError("not_configured", "Serviço postal não configurado. Contacte o administrador.")
    return os.environ[key]


async def _call(method, operation, headers, **kwargs):
    billable = operation == "sendCourrier"
    try:
        async with make_client() as client:
            response = await asyncio.wait_for(client.request(method, f'{_env("MERCIFACTEUR_BASE_URL").rstrip("/")}/{operation}',
                headers={**headers, "Accept": "application/json"}, **kwargs), timeout=25)
    except (httpx.HTTPError, asyncio.TimeoutError):
        raise PostalProviderError("provider_timeout", "O serviço postal não responde no prazo previsto.", uncertain=billable)
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
    except ValueError:
        log.warning("Postal provider non-JSON: operation=%s status=%s", operation, response.status_code)
        raise PostalProviderError("provider_unavailable", "O serviço postal devolve uma resposta inválida. Tente o preço mais tarde.", uncertain=billable)
    error = data.get("error") or {}
    code = str(error.get("code") or "provider_rejected") if isinstance(error, dict) else "provider_rejected"
    if response.status_code >= 500:
        raise PostalProviderError("provider_unavailable", "O serviço postal está temporariamente indisponível.", uncertain=billable)
    if response.status_code >= 400 or data.get("success") is False:
        log.warning("Postal provider rejected operation=%s code=%s status=%s", operation, code, response.status_code)
        if code == "INVALID_TOKEN_FOR_IP":
            _token.clear()
            message = "O endereço IP do servidor não está autorizado pela Merci Facteur. O administrador deve atualizar a configuração postal."
        elif response.status_code in (401, 403):
            _token.clear()
            message = "A Merci Facteur recusa o acesso à conta postal. Verifique as autorizações da conta."
        elif "DOUBL" in code.upper() or "DUPLIC" in code.upper():
            message = "A Merci Facteur assinala um duplicado. Verifique o histórico antes de qualquer novo envio."
            billable = True
        else:
            message = "A Merci Facteur recusou o pedido. Verifique a conta postal e os contactos antes de tentar novamente."
        duplicate = "DOUBL" in code.upper() or "DUPLIC" in code.upper()
        raise PostalProviderError(code, message, uncertain=duplicate)
    if data.get("success") is not True:
        raise PostalProviderError("provider_invalid_response", "O serviço postal não confirmou o pedido.", uncertain=billable)
    return data


def make_client():
    # Identical routing for provider calls and the admin-only egress probe.
    # INTEGRATION_PROXY_URL is an API gateway, NOT an HTTP CONNECT proxy.
    return httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5), follow_redirects=False)


def configuration_fingerprint():
    return hashlib.sha256(json.dumps([os.environ.get(k, "") for k in KEYS]).encode()).hexdigest()


async def get_token(force=False):
    async with _token_lock:
        now = int(time.time())
        fingerprint = configuration_fingerprint()
        if not force and _token.get("config") == fingerprint and _token.get("value") and now < _token.get("expire", 0) - 60:
            return _token["value"]
        sid, sk = _env("MERCIFACTEUR_PUBLIC_KEY"), _env("MERCIFACTEUR_SECRET_KEY")
        signature = hmac.new(sk.encode(), f"{sid}{now}".encode(), hashlib.sha256).hexdigest()
        body = await _call("POST", "getToken", {"ww-service-id": sid, "ww-timestamp": str(now),
            "ww-service-signature": signature, "ww-authorized-ip": _env("MERCIFACTEUR_AUTHORIZED_IP")})
        try:
            token, expires = body["token"], int(body["expire"])
            if not isinstance(token, str) or not token or expires <= now:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise PostalProviderError("invalid_token", "A Merci Facteur devolveu uma autorização inválida.")
        _token.update(value=token, expire=expires, config=fingerprint)
        return token


async def request(method, op, **kw):
    headers = {"ww-service-id": _env("MERCIFACTEUR_PUBLIC_KEY"), "ww-access-token": await get_token()}
    return await _call(method, op, headers, **kw)


def _addr(address):
    keys = ("civilite", "nom", "prenom", "societe", "adresse1", "adresse2", "adresse3", "cp", "ville", "pays", "phone", "email")
    return {key: str(address.get(key) or ("França" if key == "pays" else "")) for key in keys}


async def postage_price(mode="normal", pages=1, pays="france"):
    result = await request("GET", "getPostagePrice", params=[("modeEnvoi", mode), ("paysDestinataire[]", pays),
        ("letterPageNumber", str(pages)), ("letterPrintSides", "recto")])
    try:
        postage = float(result["affranchissement"]["FRANCE"]["amount"])
        content = float(result["content"]["totalContentTtc"])
        if not all(math.isfinite(v) and v >= 0 for v in (postage, content)) or postage + content <= 0:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise PostalProviderError("invalid_price", "O preço postal recebido está incompleto. Nenhum envio é autorizado.")
    return {"mode": mode, "pages": pages, "postage": postage, "content_ttc": content,
            "total_ttc": round(postage + content, 2), "currency": "EUR"}


async def send_letter(pdf, *, sender, recipient, mode="normal", filename="courrier", reference):
    content = {"letter": {"base64files": [base64.b64encode(pdf).decode()], "final_filename": filename[:50],
                          "print_sides": "recto"}, "photo": "", "card": ""}
    form = {"idUser": _env("MERCIFACTEUR_USER_ID"), "modeEnvoi": mode, "antidoublon": reference,
        "adress": json.dumps({"exp": _addr(sender), "dest": [{**_addr(recipient), "consent": 0}]}, ensure_ascii=False),
        "content": json.dumps(content, ensure_ascii=False)}
    return await request("POST", "sendCourrier", data=form)


async def tracking(envoi_id):
    result = await request("GET", "getSuiviEnvoi", params={"idEnvoi": envoi_id})
    for key in ("statutPrintEnvoi", "lastState"):
        if isinstance(result.get(key), str):
            result[key] = html.unescape(result[key])
    return result


async def list_sends():
    return await request("GET", "listEnvois", params={"idUser": _env("MERCIFACTEUR_USER_ID")})