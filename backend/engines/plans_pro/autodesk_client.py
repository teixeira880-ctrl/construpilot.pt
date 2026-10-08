"""Cliente Autodesk APS: OAuth v2 + OSS + Model Derivative.

Design:
  - Token cacheado em memória (3599s TTL) — renova automaticamente.
  - Bucket por aplicação (nome derivado do client_id para unicidade global).
  - Upload direto S3 (signed URL), evitando passar pelo gateway Autodesk.
  - Zero credentials nos logs.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("plans_pro.autodesk")

AUTH_BASE = "https://developer.api.autodesk.com/authentication/v2"
OSS_BASE = "https://developer.api.autodesk.com/oss/v2"
MD_BASE = "https://developer.api.autodesk.com/modelderivative/v2"

DEFAULT_SCOPES = "data:read data:write data:create bucket:read bucket:create viewables:read"
VIEWER_SCOPES = "viewables:read data:read"


class AutodeskError(RuntimeError):
    def __init__(self, msg: str, *, status: int | None = None, retriable: bool = False):
        super().__init__(msg)
        self.status = status
        self.retriable = retriable


class AutodeskClient:
    """Cliente HTTP persistente para Autodesk APS."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires: float = 0.0
        self._viewer_token: str | None = None
        self._viewer_expires: float = 0.0
        self._bucket_ready = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    @property
    def client_id(self) -> str:
        return (os.environ.get("AUTODESK_CLIENT_ID") or "").strip()

    @property
    def client_secret(self) -> str:
        return (os.environ.get("AUTODESK_CLIENT_SECRET") or "").strip()

    @property
    def bucket_key(self) -> str:
        """Bucket name global unique derivado do client_id (lowercase, alphanum)."""
        custom = (os.environ.get("AUTODESK_BUCKET_KEY") or "").strip()
        if custom:
            return custom
        if not self.client_id:
            return "construpilot-plans"
        # bucket name: 3..128 chars, lowercase alphanumeric or hyphen
        h = hashlib.sha1(self.client_id.encode()).hexdigest()[:12]
        return f"construpilot-plans-{h}"

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    async def _fetch_token(self, scopes: str) -> tuple[str, int]:
        if not self.is_configured():
            raise AutodeskError("Autodesk APS não configurado (AUTODESK_CLIENT_ID/SECRET em falta).")
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{AUTH_BASE}/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"grant_type": "client_credentials", "scope": scopes},
            )
        if r.status_code != 200:
            # Nunca imprimir credentials; só devolve mensagem genérica + status
            try:
                err = r.json()
                code = err.get("error") or "unknown"
            except Exception:
                code = "parse_error"
            raise AutodeskError(f"OAuth token falhou ({r.status_code}/{code})", status=r.status_code)
        payload = r.json()
        return payload["access_token"], int(payload.get("expires_in", 3599))

    async def access_token(self) -> str:
        """Token internal (full scopes) — cached."""
        async with self._lock:
            now = time.time()
            if self._token and self._token_expires - now > 60:
                return self._token
            token, expires_in = await self._fetch_token(DEFAULT_SCOPES)
            self._token = token
            self._token_expires = now + expires_in
            logger.info("autodesk: new internal token (expires in %ds)", expires_in)
            return token

    async def viewer_token(self) -> dict[str, Any]:
        """Token restrito para o Viewer SDK (frontend). Expira em ~1h."""
        now = time.time()
        if self._viewer_token and self._viewer_expires - now > 60:
            return {
                "access_token": self._viewer_token,
                "expires_in": int(self._viewer_expires - now),
                "token_type": "Bearer",
            }
        token, expires_in = await self._fetch_token(VIEWER_SCOPES)
        self._viewer_token = token
        self._viewer_expires = now + expires_in
        return {"access_token": token, "expires_in": expires_in, "token_type": "Bearer"}

    # ------------------------------------------------------------------
    # OSS
    # ------------------------------------------------------------------
    async def ensure_bucket(self) -> str:
        """Garante que o bucket existe (idempotente)."""
        if self._bucket_ready:
            return self.bucket_key
        token = await self.access_token()
        bucket = self.bucket_key
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Tenta criar; se já existe (409), ok
            r = await client.post(
                f"{OSS_BASE}/buckets",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"bucketKey": bucket, "policyKey": "persistent"},
            )
            if r.status_code in (200, 409):
                self._bucket_ready = True
                return bucket
            raise AutodeskError(f"Falha ao criar bucket ({r.status_code})", status=r.status_code)

    async def upload_object(self, filename: str, data: bytes) -> dict[str, Any]:
        """Upload direto para OSS via signed S3 (small files < 100MB).

        Devolve dict com `objectKey`, `objectId`, `urn` (base64 do objectId).
        """
        bucket = await self.ensure_bucket()
        token = await self.access_token()
        safe_name = filename.replace(" ", "_")
        object_key = f"{int(time.time())}_{safe_name}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            # 1. Pedir URL S3 assinada (single part, simples)
            r = await client.get(
                f"{OSS_BASE}/buckets/{bucket}/objects/{object_key}/signeds3upload",
                headers={"Authorization": f"Bearer {token}"},
                params={"parts": 1, "minutesExpiration": 10},
            )
            if r.status_code != 200:
                raise AutodeskError(f"signeds3upload falhou ({r.status_code})", status=r.status_code)
            s3_data = r.json()
            upload_key = s3_data["uploadKey"]
            urls = s3_data["urls"]
            if not urls:
                raise AutodeskError("signeds3upload sem URLs")

            # 2. PUT direto no S3
            r2 = await client.put(urls[0], content=data, headers={"Content-Type": "application/octet-stream"})
            if r2.status_code not in (200, 201):
                raise AutodeskError(f"S3 PUT falhou ({r2.status_code})", status=r2.status_code)

            # 3. Finalizar upload
            r3 = await client.post(
                f"{OSS_BASE}/buckets/{bucket}/objects/{object_key}/signeds3upload",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"uploadKey": upload_key},
            )
            if r3.status_code not in (200, 201):
                raise AutodeskError(f"Finalização S3 falhou ({r3.status_code})", status=r3.status_code)
            obj = r3.json()
            object_id = obj.get("objectId") or f"urn:adsk.objects:os.object:{bucket}/{object_key}"
            urn = base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")
            logger.info("autodesk: upload OK (bucket=%s, size=%d)", bucket, len(data))
            return {
                "bucket": bucket,
                "object_key": object_key,
                "object_id": object_id,
                "urn": urn,
            }

    # ------------------------------------------------------------------
    # Model Derivative
    # ------------------------------------------------------------------
    async def translate(self, urn: str, *, output_type: str = "svf2") -> dict[str, Any]:
        """Lança job de translation (SVF2 por default)."""
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{MD_BASE}/designdata/job",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "x-ads-force": "true",
                },
                json={
                    "input": {"urn": urn},
                    "output": {
                        "formats": [{"type": output_type, "views": ["2d", "3d"]}],
                    },
                },
            )
        if r.status_code not in (200, 201):
            raise AutodeskError(f"translate falhou ({r.status_code})", status=r.status_code)
        return r.json()

    async def manifest(self, urn: str) -> dict[str, Any]:
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{MD_BASE}/designdata/{urn}/manifest",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code == 404:
            return {"status": "pending", "progress": "0%"}
        if r.status_code != 200:
            raise AutodeskError(f"manifest falhou ({r.status_code})", status=r.status_code)
        return r.json()

    async def thumbnail(self, urn: str, *, width: int = 1600, height: int = 1600) -> bytes | None:
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{MD_BASE}/designdata/{urn}/thumbnail",
                headers={"Authorization": f"Bearer {token}"},
                params={"width": width, "height": height},
            )
        if r.status_code != 200:
            return None
        return r.content

    async def metadata(self, urn: str) -> dict[str, Any]:
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{MD_BASE}/designdata/{urn}/metadata",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code != 200:
            raise AutodeskError(f"metadata falhou ({r.status_code})", status=r.status_code)
        return r.json()

    async def properties(self, urn: str, guid: str) -> dict[str, Any]:
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{MD_BASE}/designdata/{urn}/metadata/{guid}/properties",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code != 200:
            raise AutodeskError(f"properties falhou ({r.status_code})", status=r.status_code)
        return r.json()


# Singleton
autodesk_client = AutodeskClient()
