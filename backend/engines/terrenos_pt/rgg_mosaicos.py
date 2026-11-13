"""RGG do BUPi em mosaicos de 2 km guardados no armazenamento de objetos (Tigris/S3) — sem ocupar disco no servidor.

O GeoPackage nacional da eBUPi (~650 MB comprimido, vários GB aberto) não cabe com folga no servidor e não sobrevive
aos deploys. Por isso é cortado uma vez em mosaicos de 2 × 2 km (scripts/bupi_rgg_mosaicos.py), cada um com os
polígonos que lhe tocam, comprimidos, e enviados para o bucket. O backend só descarrega o mosaico onde o utilizador
clica (alguns KB) e guarda os últimos em memória.

Formato de cada mosaico (gzip): b"RGG1" + n (uint32) + n × [fid (int64), área (float32), len (uint32), WKB].
Chave: bupi/rgg/<versao>/<ix>_<iy>.bin.gz, com ix = floor(M / 2000), iy = floor(P / 2000) em PT-TM06.
Manifesto: bupi/rgg/atual.json → {"versao", "data", "tamanho_m", "mosaicos", "poligonos", "fonte"}.
"""
from __future__ import annotations

import gzip
import io
import json
import math
import os
import struct
import time
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

TAMANHO = 2000.0
PREFIXO = "bupi/rgg"
_RAM: "OrderedDict[str, List[Tuple[int, float, bytes]]]" = OrderedDict()
_MANIFESTO: Dict[str, Any] = {"t": 0.0, "m": None}
_CLIENTE: Dict[str, Any] = {"c": None}


def chave_mosaico(x: float, y: float, tamanho: float = TAMANHO) -> Tuple[int, int]:
    return int(math.floor(x / tamanho)), int(math.floor(y / tamanho))


def codificar(itens: Iterable[Tuple[int, float, bytes]]) -> bytes:
    itens = list(itens)
    b = io.BytesIO()
    b.write(b"RGG1" + struct.pack("<I", len(itens)))
    for fid, area, wkb in itens:
        b.write(struct.pack("<qfI", int(fid), float(area), len(wkb)))
        b.write(wkb)
    return gzip.compress(b.getvalue(), compresslevel=6)


def descodificar(dados: bytes) -> List[Tuple[int, float, bytes]]:
    raw = gzip.decompress(dados)
    if raw[:4] != b"RGG1":
        raise ValueError("mosaico RGG inválido")
    (n,) = struct.unpack_from("<I", raw, 4)
    off, out = 8, []
    for _ in range(n):
        fid, area, ln = struct.unpack_from("<qfI", raw, off)
        off += 16
        out.append((fid, area, raw[off:off + ln]))
        off += ln
    return out


# ------------------------------------------------------------------ armazenamento (Tigris / S3)
def configurado() -> bool:
    return bool(os.environ.get("TIGRIS_BUCKET") or os.environ.get("BUPI_RGG_BUCKET"))


def _bucket() -> str:
    return os.environ.get("BUPI_RGG_BUCKET") or os.environ.get("TIGRIS_BUCKET") or ""


def cliente():
    """Cliente S3 do Tigris (credenciais padrão AWS_* do ambiente; endpoint do Tigris por omissão)."""
    if _CLIENTE["c"] is None:
        import boto3
        from botocore.config import Config
        ep = (os.environ.get("AWS_ENDPOINT_URL_S3") or os.environ.get("TIGRIS_ENDPOINT")
              or "https://fly.storage.tigris.dev")
        _CLIENTE["c"] = boto3.client("s3", endpoint_url=ep, region_name=os.environ.get("AWS_REGION") or "auto",
                                     config=Config(retries={"max_attempts": 3}, connect_timeout=10, read_timeout=30))
    return _CLIENTE["c"]


def _ler(chave: str) -> Optional[bytes]:
    try:
        r = cliente().get_object(Bucket=_bucket(), Key=chave)
        return r["Body"].read()
    except Exception as e:  # noqa: BLE001 — NoSuchKey = mosaico vazio
        if "NoSuchKey" in type(e).__name__ or "NoSuchKey" in str(e) or "404" in str(e):
            return b""
        raise


def manifesto() -> Optional[Dict[str, Any]]:
    if _MANIFESTO["m"] is not None and time.time() - _MANIFESTO["t"] < 3600:
        return _MANIFESTO["m"]
    b = _ler(f"{PREFIXO}/atual.json")
    m = json.loads(b) if b else None
    _MANIFESTO.update(t=time.time(), m=m)
    return m


def poligonos_no_mosaico(x: float, y: float) -> Optional[List[Tuple[int, float, bytes]]]:
    """Polígonos (fid, área, WKB) do mosaico que contém (x, y) em PT-TM06. None se os mosaicos não estiverem publicados."""
    m = manifesto()
    if not m:
        return None
    ix, iy = chave_mosaico(x, y, float(m.get("tamanho_m") or TAMANHO))
    chave = f"{PREFIXO}/{m['versao']}/{ix}_{iy}.bin.gz"
    if chave in _RAM:
        _RAM.move_to_end(chave)
        return _RAM[chave]
    b = _ler(chave)
    itens = descodificar(b) if b else []
    _RAM[chave] = itens
    while len(_RAM) > 64:
        _RAM.popitem(last=False)
    return itens
