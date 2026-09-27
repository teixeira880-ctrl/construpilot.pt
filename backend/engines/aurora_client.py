"""Aurora Company API V1 — cliente backend-only.

Regras de segurança (não negociáveis):
  · Nunca expor `AURORA_COMPANY_SIGNING_SECRET` em headers, body, respostas HTTP,
    logs ou exceções.
  · Nunca fazer log da `AURORA_COMPANY_API_KEY` (mesmo mascarada).
  · Config carregada exclusivamente de env vars — nenhum default hardcoded.
  · POSTs (writes) só são executados depois de a especificação AS1 HMAC oficial
    do Aurora ser confirmada pelo utilizador. Até lá, os métodos que fazem POST
    levantam `NotImplementedError`.

Env vars requeridas:
  · AURORA_BASE_URL              — ex.: https://api.aurora.example
  · AURORA_COMPANY_API_KEY       — bearer token da Company API
  · AURORA_COMPANY_SIGNING_SECRET — secret AS1 HMAC (usado internamente, nunca enviado)
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import httpx


class AuroraNotConfigured(RuntimeError):
    """Levantada quando as env vars AURORA_* estão em falta ou vazias."""


class AuroraSpecMissing(NotImplementedError):
    """Levantada em métodos que exigem a especificação AS1 HMAC oficial."""


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

    @property
    def endpoint_base(self) -> str:
        if not self.base_url:
            raise AuroraNotConfigured("AURORA_BASE_URL não definido.")
        return f"{self.base_url.rstrip('/')}/api/gateway/v1/aurora-core/company"

    # Acessos controlados para uso interno do cliente. Não expor publicamente.
    def _bearer(self) -> str:
        return f"Bearer {self._api_key}"

    def _secret_bytes(self) -> bytes:
        return self._signing_secret.encode("utf-8")


class AuroraCompanyClient:
    """Cliente HTTP para Aurora Company API V1. Instanciar via `get_aurora_client()`."""

    def __init__(self, config: AuroraConfig | None = None) -> None:
        self.config = config or AuroraConfig()
        if not self.config.configured:
            raise AuroraNotConfigured(
                "Aurora não configurado. Definir AURORA_BASE_URL, "
                "AURORA_COMPANY_API_KEY e AURORA_COMPANY_SIGNING_SECRET no .env."
            )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0),
            headers={
                "Authorization": self.config._bearer(),
                "Accept": "application/json",
                "User-Agent": "ConstruPilot/1.0 (aurora-company-client)",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # -------- utilitários internos ---------------------------------------
    @staticmethod
    def _new_request_id() -> str:
        """Idempotency key por pedido. Header oficial a confirmar (ver reporte)."""
        return str(uuid.uuid4())

    def _as1_sign(
        self,
        *,
        method: str,
        path: str,
        body_bytes: bytes,
        ts: str,
        request_id: str,
    ) -> str:
        """Assinatura AS1 HMAC.

        PLACEHOLDER — a fórmula canónica exata (ordem de campos, encoding, headers
        assinados, algoritmo, formato do timestamp) depende da spec oficial Aurora.
        Não implementar à cega — abrir issue quando a spec for fornecida.
        """
        raise AuroraSpecMissing(
            "AS1 HMAC signing pendente da spec oficial Aurora. "
            "Métodos que escrevem (POST) estão bloqueados até obtenção da spec."
        )

    # -------- Fase 1 · leituras (sem signing) ----------------------------
    async def get_capabilities(self) -> dict[str, Any]:
        """GET /capabilities — teste de conexão / descoberta de schema."""
        url = f"{self.config.endpoint_base}/capabilities"
        r = await self._client.get(url)
        r.raise_for_status()
        return r.json()

    async def get_project(self, project_id: str) -> dict[str, Any]:
        """GET /projects/get?project_id=…"""
        if not project_id:
            raise ValueError("project_id vazio.")
        url = f"{self.config.endpoint_base}/projects/get"
        r = await self._client.get(url, params={"project_id": project_id})
        r.raise_for_status()
        return r.json()

    # -------- Fase 2 · escritas (bloqueadas até termos spec AS1) ---------
    async def upsert_project(self, project: dict[str, Any]) -> dict[str, Any]:
        raise AuroraSpecMissing(
            "upsert_project requer AS1 HMAC + idempotency header. "
            "Aguardar spec oficial antes de implementar."
        )

    async def ask(
        self,
        *,
        question: str,
        project_id: str,
        resources: list[str] | None = None,
    ) -> dict[str, Any]:
        raise AuroraSpecMissing(
            "ask requer POST assinado com AS1 HMAC. "
            "Aguardar spec oficial antes de implementar."
        )


# ------------------ Singleton lazy (evita instanciar se não configurado) ---
_client_singleton: AuroraCompanyClient | None = None


def get_aurora_client() -> AuroraCompanyClient:
    """Devolve o singleton do cliente Aurora. Lança `AuroraNotConfigured` se faltar env."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = AuroraCompanyClient()
    return _client_singleton


def is_aurora_configured() -> bool:
    """Verificação leve, sem instanciar o cliente HTTP."""
    return AuroraConfig().configured
