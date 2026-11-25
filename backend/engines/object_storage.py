"""Stockage persistant de fichiers (plans, documents BET, photos…).

Les fichiers sont stockés ici, JAMAIS en base64 dans Mongo. Mongo ne conserve que la référence (storage_path).
Pas d'API de suppression → soft-delete en base.

Backend choisi par ``STORAGE_BACKEND`` (même API et mêmes chemins dans tous les cas) :
- ``emergent`` (défaut, comportement actuel) : Emergent Object Storage ;
- ``s3`` : tout stockage compatible S3 (Cloudflare R2, Hetzner Object Storage, MinIO…) ;
- ``s3+emergent`` : écriture S3, lecture S3 puis repli sur Emergent si le fichier n'y est pas encore
  (bascule sans interruption pendant la copie des fichiers ; voir scripts/infra/migrate_files.py).
Variables S3 : S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_REGION (défaut « auto »).
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


BACKEND = (os.environ.get("STORAGE_BACKEND") or "emergent").strip().lower()
_s3 = None


def _s3_client():
    global _s3
    if _s3 is None:
        import boto3
        from botocore.config import Config
        _s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("S3_REGION") or "auto",
            config=Config(retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=10, read_timeout=120),
        )
    return _s3


def _bucket() -> str:
    b = (os.environ.get("S3_BUCKET") or "").strip()
    if not b:
        raise RuntimeError("S3_BUCKET em falta")
    return b


def s3_put(path: str, data: bytes, content_type: str) -> dict:
    _s3_client().put_object(Bucket=_bucket(), Key=path, Body=data, ContentType=content_type or "application/octet-stream")
    return {"path": path, "size": len(data), "content_type": content_type}


def s3_get(path: str) -> tuple[bytes, str]:
    obj = _s3_client().get_object(Bucket=_bucket(), Key=path)
    return obj["Body"].read(), obj.get("ContentType") or "application/octet-stream"


def s3_exists(path: str) -> bool:
    try:
        _s3_client().head_object(Bucket=_bucket(), Key=path)
        return True
    except Exception:  # noqa: BLE001
        return False


def init_storage() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": _KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if BACKEND.startswith("s3"):
        return s3_put(path, data, content_type)
    return emergent_put(path, data, content_type)


def get_object(path: str) -> tuple[bytes, str]:
    if BACKEND == "s3":
        return s3_get(path)
    if BACKEND == "s3+emergent":
        try:
            return s3_get(path)
        except Exception:  # noqa: BLE001 — ainda não copiado: lê na Emergent
            return emergent_get(path)
    return emergent_get(path)


def emergent_put(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type},
                        data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def emergent_get(path: str) -> tuple[bytes, str]:
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
