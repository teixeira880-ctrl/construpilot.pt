"""Merci Facteur API v1.2 — envoi postal de courriers PDF (token HMAC + sendCourrier)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import httpx

_token: dict = {}

MODES = ("normal", "suivi", "lrar")


def configured() -> bool:
    return bool(os.environ.get("MERCIFACTEUR_PUBLIC_KEY") and os.environ.get("MERCIFACTEUR_SECRET_KEY")
                and os.environ.get("MERCIFACTEUR_USER_ID"))


def _env(k: str) -> str:
    v = os.environ.get(k)
    if not v:
        raise RuntimeError(f"Merci Facteur non configuré ({k})")
    return v


async def get_token(force: bool = False) -> str:
    now = int(time.time())
    if not force and _token.get("value") and now < _token.get("expire", 0) - 60:
        return _token["value"]
    sid, sk = _env("MERCIFACTEUR_PUBLIC_KEY"), _env("MERCIFACTEUR_SECRET_KEY")
    sig = hmac.new(sk.encode(), f"{sid}{now}".encode(), hashlib.sha256).hexdigest()
    headers = {"ww-service-id": sid, "ww-timestamp": str(now), "ww-service-signature": sig,
               "ww-authorized-ip": os.environ.get("MERCIFACTEUR_AUTHORIZED_IP", "111.111.111.111")}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{_env('MERCIFACTEUR_BASE_URL').rstrip('/')}/getToken", headers=headers)
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"Merci Facteur token: {body.get('error')}")
    _token.update(value=body["token"], expire=int(body["expire"]))
    return body["token"]


async def request(method: str, op: str, **kw) -> dict:
    base = _env("MERCIFACTEUR_BASE_URL").rstrip("/")
    headers = {"ww-service-id": _env("MERCIFACTEUR_PUBLIC_KEY"), "ww-access-token": await get_token()}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.request(method, f"{base}/{op}", headers=headers, **kw)
        if r.status_code == 401:
            headers["ww-access-token"] = await get_token(force=True)
            r = await c.request(method, f"{base}/{op}", headers=headers, **kw)
    if r.status_code >= 400:
        try:
            err = r.json().get("error")
        except Exception:  # noqa: BLE001
            err = r.text[:200]
        raise RuntimeError(f"{op}: {err or r.status_code}")
    return r.json()


_ADDR_KEYS = ("civilite", "nom", "prenom", "societe", "adresse1", "adresse2", "adresse3",
              "cp", "ville", "pays", "phone", "email")


def _addr(a: dict) -> dict:
    out = {k: str(a.get(k) or "") for k in _ADDR_KEYS}
    out["pays"] = out["pays"] or "France"
    return out


async def postage_price(mode: str = "normal", pages: int = 1, pays: str = "france") -> dict:
    params = [("modeEnvoi", mode), ("paysDestinataire[]", pays),
              ("letterPageNumber", str(pages)), ("letterPrintSides", "recto")]
    return await request("GET", "getPostagePrice", params=params)


async def send_letter(pdf: bytes, *, sender: dict, recipient: dict, mode: str = "normal",
                      filename: str = "courrier") -> dict:
    content = {"letter": {"base64files": [base64.b64encode(pdf).decode()],
                          "final_filename": filename[:50], "print_sides": "recto"},
               "photo": "", "card": ""}
    form = {"idUser": _env("MERCIFACTEUR_USER_ID"), "modeEnvoi": mode,
            "adress": json.dumps({"exp": _addr(sender), "dest": [{**_addr(recipient), "consent": 0}]},
                                 ensure_ascii=False),
            "content": json.dumps(content, ensure_ascii=False)}
    res = await request("POST", "sendCourrier", data=form)
    if not res.get("success"):
        raise RuntimeError(str(res.get("error") or res)[:300])
    return res


async def tracking(envoi_id: int) -> dict:
    return await request("GET", "getSuiviEnvoi", params={"idEnvoi": envoi_id})
