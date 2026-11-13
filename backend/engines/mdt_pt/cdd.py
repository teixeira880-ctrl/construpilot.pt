"""Cliente do Centro de Dados da DGT (CDD) — cobertura LiDAR de Portugal continental (MDT 50 cm e 2 m).

Fonte oficial: Direção-Geral do Território, levantamento LiDAR 2023-2024 (10 pts/m², exatidão altimétrica < 10 cm),
dados abertos CC-BY-4.0, ficheiros GeoTIFF de 1 km × 1 km em ETRS89/PT-TM06 (EPSG:3763).

Fluxo (o mesmo do portal https://cdd.dgterritorio.gov.pt):
  1. autenticação Keycloak (conta gratuita do CDD) — DGT_CDD_USER / DGT_CDD_PASSWORD no ambiente do backend;
  2. pesquisa STAC  POST /dgt-be/v1/search  {bbox, collections:[MDT-2m|MDT-50cm]};
  3. descarga  GET  /dgt-be/v1/download/…  → 302 para URL pré-assinado (armazenamento S3) → GeoTIFF.
Cada folha descarregada fica numa cache em disco (MDT_CACHE_DIR, limite MDT_CACHE_MAX_GB), por isso o mesmo terreno
nunca é descarregado duas vezes. Portugal inteiro (≈ 2,3 TB MDT+MDS) não é copiado: as folhas são obtidas a pedido.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx

log = logging.getLogger(__name__)

SITE = "https://cdd.dgterritorio.gov.pt"
STAC_SEARCH = f"{SITE}/dgt-be/v1/search"
AUTH = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect"
CLIENT_ID = "aai-oidc-dgt"
REDIRECT = f"{SITE}/auth/callback"
COLECOES = ("MDT-50cm", "MDT-2m")
FONTE = "DGT — Levantamento LiDAR de Portugal continental (CDD), CC-BY-4.0"
UA = {"User-Agent": "ConstruPilot-MDT/1.0 (+https://construpilot.pt)",
      "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"}

_DIR = os.environ.get("MDT_CACHE_DIR") or os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "mdt_cache"))
_MAX_BYTES = float(os.environ.get("MDT_CACHE_MAX_GB") or 4) * 1e9
SESSAO_S = 25 * 60


class CddErro(RuntimeError):
    pass


def credenciais() -> Tuple[str, str]:
    return ((os.environ.get("DGT_CDD_USER") or "").strip(), (os.environ.get("DGT_CDD_PASSWORD") or "").strip())


def configurado() -> bool:
    u, p = credenciais()
    return bool(u and p)


class _Sessao:
    def __init__(self):
        self.cliente: Optional[httpx.AsyncClient] = None
        self.desde = 0.0
        self.lock = asyncio.Lock()
        self.falhou_ate = 0.0        # após falha de autenticação, não insistir durante 10 min

    async def cliente_ok(self) -> httpx.AsyncClient:
        async with self.lock:
            if self.cliente is not None and time.time() - self.desde < SESSAO_S:
                return self.cliente
            if time.time() < self.falhou_ate:
                raise CddErro("autenticação no CDD da DGT falhou há pouco; nova tentativa dentro de minutos")
            if self.cliente is not None:
                await self.cliente.aclose()
                self.cliente = None
            try:
                self.cliente = await _autenticar()
            except Exception:
                self.falhou_ate = time.time() + 600
                raise
            self.desde = time.time()
            return self.cliente


_S = _Sessao()


async def _autenticar() -> httpx.AsyncClient:
    user, pwd = credenciais()
    if not (user and pwd):
        raise CddErro("credenciais do CDD da DGT não configuradas (DGT_CDD_USER / DGT_CDD_PASSWORD)")
    c = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0), headers=UA, follow_redirects=True)
    try:
        await c.get(SITE)
        r = await c.get(f"{AUTH}/auth", params={"client_id": CLIENT_ID, "response_type": "code",
                                                  "redirect_uri": REDIRECT, "scope": "openid profile email"})
        html = r.text
        m = re.search(r"<form[^>]*id=['\"]kc-form-login['\"][^>]*action=['\"]([^'\"]+)['\"]", html)
        if m:
            acao = m.group(1).replace("&amp;", "&")
            if acao.startswith("/"):
                acao = "https://auth.cdd.dgterritorio.gov.pt" + acao
            dados = dict(re.findall(r"<input[^>]*type=['\"]hidden['\"][^>]*name=['\"]([^'\"]+)['\"][^>]*value=['\"]([^'\"]*)['\"]", html))
            dados.update({"username": user, "password": pwd})
            await c.post(acao, data=dados, headers={"Origin": "https://auth.cdd.dgterritorio.gov.pt"})
        t = await c.post(STAC_SEARCH, json={"bbox": [-9.0, 38.0, -8.0, 39.0], "limit": 1})
        if t.status_code != 200:
            raise CddErro(f"autenticação no CDD da DGT recusada (HTTP {t.status_code}) — verificar a conta")
        return c
    except Exception:
        await c.aclose()
        raise


def _tipo_ext(tipo: str) -> str:
    base = (tipo or "").split(";")[0].strip().lower()
    return ".tiff" if base in ("image/tiff", "image/geotiff") else ""


async def pesquisar(bbox_ll: Tuple[float, float, float, float], colecao: str) -> List[Dict[str, str]]:
    """Folhas (id, url) da coleção que intersectam bbox (lon_min, lat_min, lon_max, lat_max). Só a versão mais recente."""
    if colecao not in COLECOES:
        raise ValueError(colecao)
    c = await _S.cliente_ok()
    r = await c.post(STAC_SEARCH, json={"bbox": list(bbox_ll), "collections": [colecao], "limit": 1000})
    if r.status_code != 200:
        raise CddErro(f"pesquisa STAC do CDD falhou (HTTP {r.status_code})")
    melhores: Dict[str, Tuple[int, str, str]] = {}
    for it in (r.json() or {}).get("features", []):
        iid = str(it.get("id") or "")
        for ln in it.get("links", []):
            if ln.get("rel") == "self" and ln.get("href"):
                iid = str(ln["href"]).rstrip("/").split("/")[-1]
                break
        url = ""
        for a in (it.get("assets") or {}).values():
            if _tipo_ext(str(a.get("type", ""))) and a.get("href"):
                url = str(a["href"])
                break
        if not (iid and url):
            continue
        m = re.search(r"_v(\d+)$", iid, re.I)
        base, ver = (iid[: m.start()], int(m.group(1))) if m else (iid, 0)
        if base not in melhores or ver > melhores[base][0]:
            melhores[base] = (ver, iid, url)
    return [{"id": v[1], "url": v[2]} for v in melhores.values()]


def _caminho(colecao: str, iid: str) -> str:
    seguro = re.sub(r"[^A-Za-z0-9._-]", "_", iid)
    return os.path.join(_DIR, colecao, seguro + ".tiff")


def _limpar_cache() -> None:
    try:
        fich = []
        for raiz, _, nomes in os.walk(_DIR):
            for n in nomes:
                p = os.path.join(raiz, n)
                st = os.stat(p)
                fich.append((st.st_atime, st.st_size, p))
        total = sum(f[1] for f in fich)
        for _, tam, p in sorted(fich):
            if total <= _MAX_BYTES:
                break
            os.remove(p)
            total -= tam
    except OSError:
        pass


async def folha(colecao: str, iid: str, url: str) -> bytes:
    """Bytes do GeoTIFF de uma folha (cache em disco primeiro)."""
    p = _caminho(colecao, iid)
    if os.path.exists(p) and os.path.getsize(p) > 1024:
        os.utime(p)
        with open(p, "rb") as fh:
            return fh.read()
    c = await _S.cliente_ok()
    dados = b""
    for tent in range(3):
        try:
            r = await c.get(url, follow_redirects=False)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0), headers=UA) as s3:
                    r = await s3.get(r.headers["location"])
            if r.status_code == 200 and r.content[:2] in (b"II", b"MM") and len(r.content) > 1024:
                dados = r.content
                break
            log.warning("CDD folha %s: HTTP %s", iid, r.status_code)
        except httpx.HTTPError as e:
            log.warning("CDD folha %s: %s", iid, e)
        await asyncio.sleep(1.5 * (tent + 1))
    if not dados:
        raise CddErro(f"descarga da folha {iid} falhou")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".part"
    with open(tmp, "wb") as fh:
        fh.write(dados)
    os.replace(tmp, p)
    _limpar_cache()
    return dados
