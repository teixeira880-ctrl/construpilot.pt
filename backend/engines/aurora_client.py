"""Aurora Company API V1 — cliente backend-only com AS1 HMAC signing.

Regras de segurança (não negociáveis):
  · Nunca expor `AURORA_COMPANY_SIGNING_SECRET` em headers, body, respostas HTTP,
    logs ou exceções.
  · Nunca fazer log da `AURORA_COMPANY_API_KEY` (mesmo mascarada).
  · Config carregada exclusivamente de env vars — nenhum default hardcoded.

AS1 canonical string (linhas separadas por \\n):
  AS1
  <key_id>
  <timestamp Unix segundos>
  <request_id UUID>
  <METHOD uppercase>
  <pathname>
  <query ordenada por chave, url-encoded, vazia se não existir>
  <sha256 hex dos bytes exatos do body>

Signature = HMAC-SHA256(signing_secret, canonical).hexdigest()
Headers:
  Authorization: Bearer <api_key>
  Content-Type: application/json (nos POSTs com body)
  X-Aurora-Request-Id: <uuid>
  X-Aurora-Signature: AS1 key_id=<key_id> ts=<ts> sig=<sig>

Janela de timestamp: ±300s. Não existe X-Aurora-Timestamp separado.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx


class AuroraNotConfigured(RuntimeError):
    """Levantada quando as env vars AURORA_* estão em falta ou vazias."""


class AuroraKeyIdInvalid(RuntimeError):
    """A API key não segue o formato ak_[test|live]_<key_id>_<random>."""


class AuroraConfig:
    """Config carregada de env vars. Nenhum valor default nem hardcoded."""

    def __init__(self) -> None:
        base = (os.environ.get("AURORA_BASE_URL") or "").strip()
        key = (os.environ.get("AURORA_COMPANY_API_KEY") or "").strip()
        secret = (os.environ.get("AURORA_COMPANY_SIGNING_SECRET") or "").strip()
        self.base_url: str = base
        self._api_key: str = key
        self._signing_secret: str = secret
        self.configured: bool = bool(base and key and secret)

        # key_id = ak_[test|live]_<key_id>_<random>
        self.key_id: str | None = None
        if key.startswith(("ak_test_", "ak_live_")):
            parts = key.split("_", 3)  # ["ak", "test|live", "<key_id>", "<random>"]
            if len(parts) >= 3 and parts[2]:
                self.key_id = parts[2]

    @property
    def endpoint_base(self) -> str:
        if not self.base_url:
            raise AuroraNotConfigured("AURORA_BASE_URL não definido.")
        return f"{self.base_url.rstrip('/')}/api/gateway/v1/aurora-core/company"

    def _bearer(self) -> str:
        return f"Bearer {self._api_key}"

    def _secret_bytes(self) -> bytes:
        return self._signing_secret.encode("utf-8")


class AuroraCompanyClient:
    """Cliente HTTP para Aurora Company API V1 (AS1 HMAC signing).

    Instanciar via `get_aurora_client()` para reutilizar o singleton lazy.
    Cada método POST assina o body com AS1 (key_id extraído da API key).
    """

    def __init__(self, config: AuroraConfig | None = None) -> None:
        self.config = config or AuroraConfig()
        if not self.config.configured:
            raise AuroraNotConfigured(
                "Aurora não configurado. Definir AURORA_BASE_URL, "
                "AURORA_COMPANY_API_KEY e AURORA_COMPANY_SIGNING_SECRET no .env."
            )
        if not self.config.key_id:
            raise AuroraKeyIdInvalid(
                "AURORA_COMPANY_API_KEY não segue o formato ak_[test|live]_<key_id>_<random>."
            )
        self._timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
        # Buffer do último canonical string calculado — útil para debug (nunca em logs).
        self._last_canonical: str = ""
        self._last_request_id: str = ""

    # ---------- utilitários ---------------------------------------------
    @staticmethod
    def _new_request_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _sorted_query(params: dict[str, Any] | None) -> str:
        if not params:
            return ""
        # Ordem alfabética por chave, url-encoded, sem espaços.
        items = sorted((k, v) for k, v in params.items() if v is not None)
        return urlencode(items, doseq=True)

    def _canonical_string(
        self,
        *,
        method: str,
        pathname: str,
        query_ordered: str,
        body_bytes: bytes,
        ts: int,
        request_id: str,
    ) -> str:
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        return "\n".join([
            "AS1",
            self.config.key_id or "",
            str(ts),
            request_id,
            method.upper(),
            pathname,
            query_ordered,
            body_hash,
        ])

    def _sign(self, canonical: str) -> str:
        return hmac.new(
            self.config._secret_bytes(),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _signed_headers(
        self,
        *,
        method: str,
        pathname: str,
        query_ordered: str,
        body_bytes: bytes,
        content_type: str = "application/json",
    ) -> tuple[dict[str, str], str]:
        ts = int(time.time())
        req_id = self._new_request_id()
        canonical = self._canonical_string(
            method=method, pathname=pathname, query_ordered=query_ordered,
            body_bytes=body_bytes, ts=ts, request_id=req_id,
        )
        sig = self._sign(canonical)
        # Guardar para debug (nunca serializado em respostas por defeito).
        self._last_canonical = canonical
        self._last_request_id = req_id
        headers: dict[str, str] = {
            "Authorization": self.config._bearer(),
            "Accept": "application/json",
            "User-Agent": "ConstruPilot/1.0 (aurora-company-client)",
            "X-Aurora-Request-Id": req_id,
            "X-Aurora-Signature": f"AS1 key_id={self.config.key_id} ts={ts} sig={sig}",
        }
        if body_bytes:
            headers["Content-Type"] = content_type
        return headers, req_id

    # ---------- Fase 1 · GET sem signing --------------------------------
    async def get_capabilities(self) -> httpx.Response:
        pathname = "/api/gateway/v1/aurora-core/company/capabilities"
        url = f"{self.config.base_url.rstrip('/')}{pathname}"
        headers = {
            "Authorization": self.config._bearer(),
            "Accept": "application/json",
            "User-Agent": "ConstruPilot/1.0 (aurora-company-client)",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            return await c.get(url, headers=headers)

    async def get_project(self, project_id: str) -> httpx.Response:
        if not project_id:
            raise ValueError("project_id vazio.")
        pathname = "/api/gateway/v1/aurora-core/company/projects/get"
        url = f"{self.config.base_url.rstrip('/')}{pathname}"
        headers = {
            "Authorization": self.config._bearer(),
            "Accept": "application/json",
            "User-Agent": "ConstruPilot/1.0 (aurora-company-client)",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            return await c.get(url, params={"project_id": project_id}, headers=headers)

    # ---------- Fase 2 · POST assinado (writes) -------------------------
    async def upsert_project(self, project: dict[str, Any]) -> httpx.Response:
        pathname = "/api/gateway/v1/aurora-core/company/projects/upsert"
        url = f"{self.config.base_url.rstrip('/')}{pathname}"
        body_bytes = json.dumps(project, separators=(",", ":"),
                                ensure_ascii=False).encode("utf-8")
        headers, _ = self._signed_headers(
            method="POST", pathname=pathname, query_ordered="", body_bytes=body_bytes,
        )
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            return await c.post(url, content=body_bytes, headers=headers)

    # ---------- Fase 3 · POST assinado (leitura conversacional) ---------
    async def ask(
        self,
        *,
        question: str,
        project_id: str,
        resources: list[str] | None = None,
    ) -> httpx.Response:
        pathname = "/api/gateway/v1/aurora-core/company/ask"
        url = f"{self.config.base_url.rstrip('/')}{pathname}"
        body = {
            "question": question,
            "project_id": project_id,
            "resources": resources or [],
        }
        body_bytes = json.dumps(body, separators=(",", ":"),
                                ensure_ascii=False).encode("utf-8")
        headers, _ = self._signed_headers(
            method="POST", pathname=pathname, query_ordered="", body_bytes=body_bytes,
        )
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            return await c.post(url, content=body_bytes, headers=headers)


# ------------------ Singleton lazy ---------------------------------------
_client_singleton: AuroraCompanyClient | None = None


def get_aurora_client() -> AuroraCompanyClient:
    """Devolve o singleton do cliente Aurora. Lança `AuroraNotConfigured` se faltar env."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = AuroraCompanyClient()
    return _client_singleton


def reset_aurora_client() -> None:
    """Força reinstanciação (útil após atualização de .env)."""
    global _client_singleton
    _client_singleton = None


def is_aurora_configured() -> bool:
    """Verificação leve, sem instanciar o cliente HTTP."""
    return AuroraConfig().configured
