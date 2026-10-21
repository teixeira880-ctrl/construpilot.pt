"""Verified DiDo contract: /rows, pageSize 100, envelope {total,page,data}."""
import asyncio
import os

import httpx


class SitadelSourceError(RuntimeError):
    pass


class SitadelClient:
    def __init__(self):
        self.base = os.environ["SITADEL_API_URL"].rstrip("/")
        self.http = httpx.AsyncClient(timeout=45, headers={"Accept": "application/json"})

    async def close(self):
        await self.http.aclose()

    async def get(self, url, params=None):
        for attempt in range(3):
            try:
                response = await self.http.get(url, params=params)
                if response.status_code in (429, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise SitadelSourceError("A fonte oficial não responde. Tente novamente mais tarde.")
            except (httpx.HTTPStatusError, ValueError) as exc:
                code = getattr(getattr(exc, "response", None), "status_code", "format")
                raise SitadelSourceError(f'Fonte oficial indisponível ou contrato alterado ({code}).') from exc

    async def metadata(self, rid):
        meta = await self.get(f"{self.base}/datafiles/{rid}")
        columns = {c.get("name") for c in meta.get("columns", [])}
        required = {"NUM_DAU", "DEP_CODE", "TYPE_DAU", "ETAT_DAU", "DATE_REELLE_AUTORISATION", "ADR_CODPOST_TER"}
        if not required.issubset(columns) or not meta.get("millesime") or not meta.get("published"):
            raise SitadelSourceError("Esquema da fonte de licenças alterado: sincronização suspensa, nenhum dado inventado.")
        return meta

    async def pages(self, rid, meta, department, start):
        page, received, expected = 1, 0, None
        while True:
            payload = await self.get(f"{self.base}/datafiles/{rid}/rows", {
                "millesime": meta["millesime"], "DEP_CODE": f"eq:{department}",
                "DATE_REELLE_AUTORISATION": f"gte:{start}", "ETAT_DAU": "in:2,5",
                "TYPE_DAU": "eq:PC", "page": page, "pageSize": 100,
            })
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list) or not isinstance(payload.get("total"), int):
                raise SitadelSourceError("Resposta inesperada da fonte de licenças: importação não publicada.")
            if int(payload.get("page", 0)) != page or (expected is not None and expected != payload["total"]):
                raise SitadelSourceError("A paginação da fonte de licenças mudou durante a importação. Tente novamente.")
            expected = payload["total"]
            rows = payload["data"]
            received += len(rows)
            if received > expected or (not rows and received < expected):
                raise SitadelSourceError("Exportação incompleta: dados anteriores conservados.")
            yield rows, page, expected
            if received == expected:
                break
            page += 1
            await asyncio.sleep(0.15)

    async def communes(self, department):
        data = await self.get(os.environ["SITADEL_COMMUNES_URL"], {
            "codeDepartement": department, "fields": "code,nom,centre", "format": "json", "geometry": "centre",
        })
        if not isinstance(data, list):
            raise SitadelSourceError("Referencial de concelhos indisponível.")
        return {str(c["code"]): c for c in data}