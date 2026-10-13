"""Client Emergent Object Storage (stockage persistant de fichiers).

Les fichiers (plans, documents BET) sont stockés ici, JAMAIS en base64 dans Mongo.
Mongo ne conserve que la référence (storage_path). Pas d'API de suppression → soft-delete en base.
"""
from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = _BASE.rstrip("/") + "/objstore/api/v1/storage"
_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "construpilot"

_storage_key: str | None = None

MIME = {
    "pdf": "application/pdf", "dxf": "image/vnd.dxf", "dwg": "application/acad",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
    "ifc": "application/octet-stream",
}


def mime_for(filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    return MIME.get(ext, "application/octet-stream")


def init_storage() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": _KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type},
                        data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple[bytes, str]:
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
