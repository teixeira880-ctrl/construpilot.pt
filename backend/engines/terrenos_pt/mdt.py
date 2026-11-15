"""Modelos digitais de elevação oficiais: DGT LiDAR (MDT 50 cm / 2 m) e Copernicus DEM GLO-30.

Ordem de fiabilidade usada em todo o ConstruPilot (terrenos, licenciamento, topografia):
1. DGT — Modelo Digital do Terreno LiDAR (levantamento 2024-2025, exatidão altimétrica ~10 cm), 50 cm, senão 2 m.
   Dados abertos (CC BY 4.0) no Centro de Dados da DGT; o descarregamento exige uma conta gratuita:
   variáveis de ambiente DGT_CDD_USER e DGT_CDD_PASSWORD. É solo nu (sem edifícios nem árvores).
2. Copernicus DEM GLO-30 (ESA/Airbus, 30 m), COG público. Atenção: é um modelo de SUPERFÍCIE (DSM) — inclui
   edifícios e copas; serve de verificação cruzada e de recurso onde a DGT não responde (ou nos Açores/Madeira).
3. Só depois os recursos antigos (Google Elevation / EU-DEM 25 m), em engines.urbanismo_pt.auto.geo.

Os ficheiros são guardados em disco (cache LRU, MDT_CACHE_DIR, por omissão /tmp/construpilot_mdt) e lidos com o
Pillow (GeoTIFF float32): nenhuma dependência nova.
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import re
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from engines.urbanismo_pt.auto import geo as G

from . import geometria as GM

CDD = "https://cdd.dgterritorio.gov.pt"
CDD_STAC = f"{CDD}/dgt-be/v1/search"
CDD_AUTH = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect/auth"
CDD_CLIENT = "aai-oidc-dgt"
COP_BASE = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"
MAX_FICHEIRO = 250 * 1024 * 1024
FONTE_DGT = "DGT — Modelo Digital do Terreno LiDAR (CC BY 4.0)"
FONTE_COP = "Copernicus DEM GLO-30 (© DLR/Airbus, ESA Copernicus) — modelo de superfície"


def _pasta() -> str:
    p = os.environ.get("MDT_CACHE_DIR") or "/tmp/construpilot_mdt"
    os.makedirs(p, exist_ok=True)
    return p


def _limpar_cache(max_bytes: int = 3 * 1024 ** 3) -> None:
    try:
        fs = [(os.path.getatime(os.path.join(_pasta(), f)), os.path.join(_pasta(), f)) for f in os.listdir(_pasta())]
        tot = sum(os.path.getsize(f) for _, f in fs)
        for _, f in sorted(fs):
            if tot <= max_bytes:
                break
            tot -= os.path.getsize(f)
            os.remove(f)
    except OSError:
        pass


# ------------------------------------------------------------------ leitura de GeoTIFF (Pillow)
class Raster:
    """GeoTIFF de uma banda em memória: transformação afim simples (sem rotação), valor nulo, amostragem bilinear."""

    def __init__(self, dados, x0: float, y0: float, sx: float, sy: float, nodata: Optional[float]):
        self.a, self.x0, self.y0, self.sx, self.sy, self.nodata = dados, x0, y0, sx, sy, nodata
        self.h, self.w = dados.shape

    @classmethod
    def ler(cls, conteudo: bytes) -> "Raster":
        import numpy as np
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = 400_000_000
        im = Image.open(io.BytesIO(conteudo))
        tags = im.tag_v2
        escala = tags.get(33550)
        tie = tags.get(33922)
        if not escala or not tie or len(tie) < 6:
            raise ValueError("GeoTIFF sem georreferenciação")
        nd = tags.get(42113)
        try:
            nodata = float(str(nd).strip().strip("\x00")) if nd is not None else None
        except ValueError:
            nodata = None
        if im.mode not in ("F", "I", "I;16", "I;16S"):
            im = im.convert("F")
        a = np.asarray(im, dtype="float32")
        # PixelIsArea: o ponto de amarração é o canto do píxel (i, j)
        x0 = float(tie[3]) - float(tie[0]) * float(escala[0])
        y0 = float(tie[4]) + float(tie[1]) * float(escala[1])
        return cls(a, x0, y0, float(escala[0]), float(escala[1]), nodata)

    def contem(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x0 + self.w * self.sx and self.y0 - self.h * self.sy <= y <= self.y0

    def valor(self, x: float, y: float) -> Optional[float]:
        c = (x - self.x0) / self.sx - 0.5
        r = (self.y0 - y) / self.sy - 0.5
        if c < -0.5 or r < -0.5 or c > self.w - 0.5 or r > self.h - 0.5:
            return None
        c0, r0 = max(0, min(self.w - 1, int(math.floor(c)))), max(0, min(self.h - 1, int(math.floor(r))))
        c1, r1 = min(self.w - 1, c0 + 1), min(self.h - 1, r0 + 1)
        fc, fr = min(1.0, max(0.0, c - c0)), min(1.0, max(0.0, r - r0))
        vs = [float(self.a[r0, c0]), float(self.a[r0, c1]), float(self.a[r1, c0]), float(self.a[r1, c1])]
        if any(not math.isfinite(v) or (self.nodata is not None and abs(v - self.nodata) < 1e-6) or v < -500 for v in vs):
            ok = [v for v in vs if math.isfinite(v) and v > -500 and (self.nodata is None or abs(v - self.nodata) >= 1e-6)]
            return round(sum(ok) / len(ok), 3) if ok else None
        top = vs[0] * (1 - fc) + vs[1] * fc
        bot = vs[2] * (1 - fc) + vs[3] * fc
        return round(top * (1 - fr) + bot * fr, 3)


_RAM: "OrderedDict[str, Raster]" = OrderedDict()


def _raster_de_ficheiro(caminho: str) -> Raster:
    r = _RAM.get(caminho)
    if r is not None:
        _RAM.move_to_end(caminho)
        return r
    with open(caminho, "rb") as f:
        r = Raster.ler(f.read())
    _RAM[caminho] = r
    while len(_RAM) > 6:
        _RAM.popitem(last=False)
    os.utime(caminho, None)
    return r


# ------------------------------------------------------------------ Copernicus DEM GLO-30
def nome_copernicus(lat: float, lon: float) -> str:
    la, lo = math.floor(lat), math.floor(lon)
    ns = f"{'N' if la >= 0 else 'S'}{abs(la):02d}"
    ew = f"{'E' if lo >= 0 else 'W'}{abs(lo):03d}"
    return f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"


async def _ficheiro_copernicus(lat: float, lon: float) -> Optional[str]:
    nome = nome_copernicus(lat, lon)
    destino = os.path.join(_pasta(), nome + ".tif")
    if os.path.exists(destino):
        return destino
    st, b = await G._get(f"{COP_BASE}/{nome}/{nome}.tif", None, want="bytes", tries=2, conc=2)
    if not b or b[:2] not in (b"II", b"MM") or len(b) > MAX_FICHEIRO:
        return None                      # 404 = mar (sem quadrícula) ou serviço indisponível
    tmp = destino + ".part"
    with open(tmp, "wb") as f:
        f.write(b)
    os.replace(tmp, destino)
    _limpar_cache()
    return destino


async def copernicus(pontos: List[Tuple[float, float]]) -> Dict[str, Any]:
    out: List[Optional[float]] = [None] * len(pontos)
    grupos: Dict[str, List[int]] = {}
    for i, (la, lo) in enumerate(pontos):
        grupos.setdefault(nome_copernicus(la, lo), []).append(i)
    for nome, idx in grupos.items():
        la, lo = pontos[idx[0]]
        cam = await _ficheiro_copernicus(la, lo)
        if not cam:
            continue
        try:
            r = await asyncio.get_running_loop().run_in_executor(None, _raster_de_ficheiro, cam)
        except Exception:  # noqa: BLE001 — ficheiro corrompido: apaga e segue
            try:
                os.remove(cam)
            except OSError:
                pass
            continue
        for i in idx:
            out[i] = r.valor(pontos[i][1], pontos[i][0])
    if all(v is None for v in out):
        return G._res(False, nota="Copernicus DEM indisponível")
    return G._res(True, {"z": out, "resolucao_m": 30, "tipo": "DSM"}, FONTE_COP, COP_BASE,
                  "Modelo de superfície de 30 m (inclui edifícios e vegetação): indicativo.")


# ------------------------------------------------------------------ DGT LiDAR (Centro de Dados)
_SESSAO: Dict[str, Any] = {"cliente": None, "t": 0.0, "falha_ate": 0.0}
_LOCK: Optional[asyncio.Lock] = None


def _credenciais() -> Optional[Tuple[str, str]]:
    u, p = (os.environ.get("DGT_CDD_USER") or "").strip(), os.environ.get("DGT_CDD_PASSWORD") or ""
    return (u, p) if u and p else None


def _form_keycloak(html: str) -> Optional[Tuple[str, Dict[str, str]]]:
    m = re.search(r'<form[^>]*id="kc-form-login"[^>]*>', html, re.I) or re.search(r'<form[^>]*action="[^"]*login-actions[^"]*"[^>]*>', html, re.I)
    if not m:
        return None
    act = re.search(r'action="([^"]+)"', m.group(0))
    if not act:
        return None
    resto = html[m.end():]
    fim = resto.lower().find("</form>")
    corpo = resto[: fim if fim >= 0 else len(resto)]
    campos = {}
    for inp in re.finditer(r"<input[^>]*>", corpo, re.I):
        t = inp.group(0)
        if re.search(r'type="hidden"', t, re.I):
            n = re.search(r'name="([^"]+)"', t)
            v = re.search(r'value="([^"]*)"', t)
            if n:
                campos[n.group(1)] = (v.group(1) if v else "").replace("&amp;", "&")
    return act.group(1).replace("&amp;", "&"), campos


async def _cliente_dgt():
    """Sessão autenticada no Centro de Dados da DGT (cookies), renovada a cada 25 min."""
    import httpx
    global _LOCK
    cred = _credenciais()
    if not cred or time.time() < _SESSAO["falha_ate"]:
        return None
    if _LOCK is None:
        _LOCK = asyncio.Lock()
    async with _LOCK:
        c = _SESSAO["cliente"]
        if c is not None and time.time() - _SESSAO["t"] < 25 * 60:
            return c
        if c is not None:
            await c.aclose()
        c = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=True,
                              headers={**G.UA, "Accept-Language": "pt-PT,pt;q=0.9"})
        try:
            await c.get(CDD)
            r = await c.get(CDD_AUTH, params={"client_id": CDD_CLIENT, "response_type": "code", "scope": "openid profile email",
                                              "redirect_uri": f"{CDD}/auth/callback"})
            f = _form_keycloak(r.text)
            if not f:
                raise RuntimeError("formulário de login da DGT não encontrado")
            acao, campos = f
            if acao.startswith("/"):
                acao = "https://auth.cdd.dgterritorio.gov.pt" + acao
            campos.update(username=cred[0], password=cred[1])
            r = await c.post(acao, data=campos, headers={"Origin": "https://auth.cdd.dgterritorio.gov.pt", "Referer": str(r.url)})
            if not str(r.url).startswith(CDD) or r.status_code >= 400:
                raise RuntimeError("credenciais DGT recusadas")
            t = await c.post(CDD_STAC, json={"bbox": [-9.0, 38.0, -8.0, 39.0], "limit": 1})
            if t.status_code != 200:
                raise RuntimeError("pesquisa STAC da DGT recusada")
        except Exception:  # noqa: BLE001
            await c.aclose()
            _SESSAO.update(cliente=None, falha_ate=time.time() + 600)   # não martelar a DGT durante 10 min
            return None
        _SESSAO.update(cliente=c, t=time.time())
        return c


def _href_tif(item: dict) -> Optional[str]:
    for a in (item.get("assets") or {}).values():
        h = (a or {}).get("href") or ""
        if re.search(r"\.tiff?(\?|$)", h, re.I) or "tiff" in str(a.get("type") or "").lower():
            return h
    return None


async def _tiles_dgt(c, bbox: List[float], colecao: str) -> List[Tuple[str, str]]:
    r = await c.post(CDD_STAC, json={"bbox": bbox, "collections": [colecao], "limit": 50})
    if r.status_code != 200:
        return []
    feats = (r.json() or {}).get("features") or []
    # versão mais recente de cada folha primeiro
    feats.sort(key=lambda f: str((f.get("properties") or {}).get("datetime") or f.get("id")), reverse=True)
    out, vistos = [], set()
    for f in feats:
        h = _href_tif(f)
        fid = str(f.get("id") or h)
        folha = re.sub(r"-\d{2}-\d{4}$", "", fid)
        if h and folha not in vistos:
            vistos.add(folha)
            out.append((fid, h))
    return out


async def _ficheiro_dgt(c, fid: str, href: str) -> Optional[str]:
    seguro = re.sub(r"[^\w.-]+", "_", fid)[:120]
    destino = os.path.join(_pasta(), f"dgt_{seguro}.tif")
    if os.path.exists(destino):
        return destino
    tmp = destino + ".part"
    try:
        async with c.stream("GET", href) as r:
            if r.status_code != 200 or "text/html" in r.headers.get("content-type", ""):
                return None
            n = 0
            with open(tmp, "wb") as f:
                async for bloco in r.aiter_bytes(1 << 16):
                    n += len(bloco)
                    if n > MAX_FICHEIRO:
                        raise ValueError("ficheiro demasiado grande")
                    f.write(bloco)
        os.replace(tmp, destino)
    except Exception:  # noqa: BLE001
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None
    _limpar_cache()
    return destino


async def dgt_lidar(pontos: List[Tuple[float, float]]) -> Dict[str, Any]:
    c = await _cliente_dgt()
    if c is None:
        nota = ("MDT LiDAR da DGT não configurado (DGT_CDD_USER / DGT_CDD_PASSWORD)" if not _credenciais()
                else "Centro de Dados da DGT indisponível")
        return G._res(False, nota=nota)
    if not all(36.8 <= la <= 42.3 and -9.6 <= lo <= -6.0 for la, lo in pontos):
        return G._res(False, nota="MDT LiDAR da DGT só cobre Portugal continental")
    las, los = [p[0] for p in pontos], [p[1] for p in pontos]
    bbox = [min(los) - 1e-4, min(las) - 1e-4, max(los) + 1e-4, max(las) + 1e-4]
    xy = [GM.tm06(la, lo) for la, lo in pontos]
    for colecao, res_m in (("MDT-50cm", 0.5), ("MDT-2m", 2.0)):
        out: List[Optional[float]] = [None] * len(pontos)
        try:
            tiles = await _tiles_dgt(c, bbox, colecao)
        except Exception:  # noqa: BLE001
            tiles = []
        for fid, href in tiles[:6]:
            cam = await _ficheiro_dgt(c, fid, href)
            if not cam:
                continue
            try:
                r = await asyncio.get_running_loop().run_in_executor(None, _raster_de_ficheiro, cam)
            except Exception:  # noqa: BLE001
                continue
            for i, (x, y) in enumerate(xy):
                if out[i] is None and r.contem(x, y):
                    out[i] = r.valor(x, y)
            if all(v is not None for v in out):
                break
        if sum(v is not None for v in out) >= max(1, int(0.8 * len(pontos))):
            return G._res(True, {"z": out, "resolucao_m": res_m, "tipo": "MDT", "colecao": colecao}, f"{FONTE_DGT} {colecao}",
                          f"{CDD}", "Modelo digital do terreno LiDAR (solo nu), exatidão altimétrica ~10 cm.")
    return G._res(False, nota="sem MDT LiDAR da DGT para este local")


# ------------------------------------------------------------------ fachada
async def cotas_oficiais(pontos: List[Tuple[float, float]], verificar: bool = True) -> Optional[Dict[str, Any]]:
    """Cotas pelos modelos oficiais (DGT LiDAR → Copernicus). None se nenhum responder (o chamador usa os recursos antigos).

    Com as duas fontes disponíveis, junta a verificação cruzada: diferença média DGT − Copernicus (o Copernicus é um
    modelo de superfície, por isso diferenças de alguns metros em zonas edificadas ou arborizadas são normais).
    """
    if not pontos:
        return None
    dgt = await dgt_lidar(pontos)
    cop = await copernicus(pontos) if (verificar or not dgt["ok"]) else None
    if dgt["ok"]:
        if cop and cop["ok"]:
            difs = [a - b for a, b in zip(dgt["data"]["z"], cop["data"]["z"]) if a is not None and b is not None]
            if difs:
                dgt["data"]["verificacao"] = {"fonte": cop["fonte"], "pontos": len(difs),
                                              "dif_media_m": round(sum(difs) / len(difs), 2),
                                              "dif_max_abs_m": round(max(abs(d) for d in difs), 2)}
        return dgt
    if cop and cop["ok"]:
        cop["data"]["dgt_nota"] = dgt.get("nota")
        return cop
    return None
