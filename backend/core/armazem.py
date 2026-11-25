"""Armazenamento de objetos (Tigris / S3) para os ficheiros pesados : anexos dos clientes (assistant_docs) e ficheiros gerados
(assistant_artifacts). O disco do servidor e a base de dados deixam de encher com PDF, DWG, DWFX, Excel e imagens.

Funcionamento, sem mudar nenhum leitor :
  • a escrita continua igual (os ficheiros entram na base como hoje) ;
  • um trabalho em segundo plano (armazem_offload) envia para o Tigris os ficheiros com mais de 24 h, verifica o tamanho no
    Tigris e só então retira os bytes da base (campo tigris_key) ;
  • a leitura é transparente : db.assistant_docs / db.assistant_artifacts estão embrulhados (core.db) e, quando um registo
    tem tigris_key e o pedido inclui data_b64, os bytes vêm do Tigris (cache em memória limitada).
Sem credenciais TIGRIS_* nada muda : nenhum envio, nenhuma leitura remota.
Os valores das chaves nunca são escritos em registos nem devolvidos."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import threading
from collections import OrderedDict

log = logging.getLogger("armazem")

CAMPOS = ("tigris_key", "tigris_size", "tigris_sha256")
_cliente = None
_lock = threading.Lock()
_CACHE: "OrderedDict[str, bytes]" = OrderedDict()
_CACHE_MAX = int(os.environ.get("ARMAZEM_CACHE_MB", "64")) * 1024 * 1024
_cache_bytes = 0


def _env(k: str) -> str:
    return (os.environ.get(k) or "").strip()


def bucket() -> str:
    return _env("TIGRIS_BUCKET")


def configurado() -> bool:
    return bool(bucket() and (_env("TIGRIS_ACCESS_KEY_ID") or _env("AWS_ACCESS_KEY_ID"))
                and (_env("TIGRIS_SECRET_ACCESS_KEY") or _env("AWS_SECRET_ACCESS_KEY")))


def cliente():
    global _cliente
    with _lock:
        if _cliente is None:
            import boto3
            from botocore.config import Config
            _cliente = boto3.client(
                "s3", endpoint_url=_env("TIGRIS_ENDPOINT") or _env("AWS_ENDPOINT_URL_S3") or "https://fly.storage.tigris.dev",
                aws_access_key_id=_env("TIGRIS_ACCESS_KEY_ID") or _env("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=_env("TIGRIS_SECRET_ACCESS_KEY") or _env("AWS_SECRET_ACCESS_KEY"),
                region_name=_env("TIGRIS_REGION") or "auto",
                config=Config(retries={"max_attempts": 4, "mode": "standard"}, connect_timeout=10, read_timeout=60))
        return _cliente


def chave(colecao: str, user_id: str | None, ident: str) -> str:
    prefixo = _env("ARMAZEM_PREFIXO") or "construpilot"
    return f"{prefixo}/{colecao}/{user_id or '_'}/{ident}"


def prefixo_utilizador(user_id: str) -> list[str]:
    prefixo = _env("ARMAZEM_PREFIXO") or "construpilot"
    return [f"{prefixo}/{c}/{user_id}/" for c in ("assistant_docs", "assistant_artifacts")]


# ---------------------------------------------------------------- operações (síncronas ; usar via asyncio.to_thread)
def enviar(k: str, data: bytes, sha: str) -> int:
    """Envia e devolve o tamanho confirmado pelo Tigris (head_object)."""
    c = cliente()
    c.put_object(Bucket=bucket(), Key=k, Body=data, Metadata={"sha256": sha})
    return int(c.head_object(Bucket=bucket(), Key=k)["ContentLength"])


def ler(k: str) -> bytes:
    global _cache_bytes
    with _lock:
        if k in _CACHE:
            _CACHE.move_to_end(k)
            return _CACHE[k]
    data = cliente().get_object(Bucket=bucket(), Key=k)["Body"].read()
    if len(data) <= _CACHE_MAX // 4:
        with _lock:
            _CACHE[k] = data
            _cache_bytes += len(data)
            while _cache_bytes > _CACHE_MAX and _CACHE:
                _, v = _CACHE.popitem(last=False)
                _cache_bytes -= len(v)
    return data


def apagar_prefixo(prefixo: str) -> int:
    c, n = cliente(), 0
    for pag in c.get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=prefixo):
        objs = [{"Key": o["Key"]} for o in pag.get("Contents", [])]
        for i in range(0, len(objs), 1000):
            c.delete_objects(Bucket=bucket(), Delete={"Objects": objs[i:i + 1000], "Quiet": True})
            n += len(objs[i:i + 1000])
    return n


def apagar(k: str) -> None:
    cliente().delete_object(Bucket=bucket(), Key=k)


# ---------------------------------------------------------------- leitura transparente
def quer_dados(projection) -> bool:
    """O pedido à base inclui data_b64 ?"""
    if projection is None:
        return True
    if isinstance(projection, (list, tuple)):
        return "data_b64" in projection
    if isinstance(projection, dict):
        incl = [k for k, v in projection.items() if k != "_id" and v]
        if incl:
            return bool(projection.get("data_b64"))
        return projection.get("data_b64", 1) != 0
    return True


def projecao_com_chave(projection):
    """Projeção de inclusão com data_b64 : pede também tigris_key (retirado depois se não foi pedido)."""
    if isinstance(projection, dict) and projection.get("data_b64") and "tigris_key" not in projection:
        return {**projection, "tigris_key": 1}, True
    if isinstance(projection, (list, tuple)) and "data_b64" in projection and "tigris_key" not in projection:
        return list(projection) + ["tigris_key"], True
    return projection, False


async def hidratar(doc: dict | None, retirar_chave: bool = False) -> dict | None:
    if not doc or not doc.get("tigris_key") or doc.get("data_b64"):
        if doc is not None and retirar_chave:
            doc.pop("tigris_key", None)
        return doc
    k = doc["tigris_key"]
    try:
        data = await asyncio.to_thread(ler, k)
        doc["data_b64"] = base64.b64encode(data).decode()
        doc["chunk_count"] = 0
    except Exception as exc:  # noqa: BLE001 — o leitor trata a ausência de bytes como hoje (documento incompleto)
        log.warning("armazem: leitura falhou (%s) para %s", type(exc).__name__, k)
    if retirar_chave:
        doc.pop("tigris_key", None)
    return doc


class Cursor:
    """Cursor Motor com hidratação ; sort/limit/skip/… continuam encadeáveis."""

    def __init__(self, cur, dados: bool, retirar: bool):
        self._cur, self._dados, self._retirar = cur, dados, retirar

    def __getattr__(self, nome):
        attr = getattr(self._cur, nome)
        if nome in ("sort", "limit", "skip", "batch_size", "hint", "max_time_ms", "collation", "allow_disk_use", "where"):
            def encadear(*a, **k):
                self._cur = attr(*a, **k)
                return self
            return encadear
        return attr

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        async for d in self._cur:
            yield (await hidratar(d, self._retirar)) if self._dados else d

    async def to_list(self, length=None):
        out = await self._cur.to_list(length)
        if self._dados:
            out = [await hidratar(d, self._retirar) for d in out]
        return out


class Colecao:
    """Coleção Motor com leitura transparente dos bytes guardados no Tigris."""

    def __init__(self, col):
        self._col = col

    def __getattr__(self, nome):
        return getattr(self._col, nome)

    @staticmethod
    def _proj(args, kwargs):
        if "projection" in kwargs:
            return kwargs["projection"], "kw"
        if len(args) >= 2:
            return args[1], "pos"
        return None, None

    def _ajustar(self, args, kwargs):
        proj, onde = self._proj(args, kwargs)
        dados = quer_dados(proj)
        nova, retirar = projecao_com_chave(proj) if dados else (proj, False)
        if onde == "kw":
            kwargs = {**kwargs, "projection": nova}
        elif onde == "pos":
            args = (args[0], nova) + tuple(args[2:])
        return args, kwargs, dados, retirar

    async def find_one(self, *args, **kwargs):
        args, kwargs, dados, retirar = self._ajustar(args, kwargs)
        d = await self._col.find_one(*args, **kwargs)
        return (await hidratar(d, retirar)) if dados else d

    def find(self, *args, **kwargs):
        args, kwargs, dados, retirar = self._ajustar(args, kwargs)
        return Cursor(self._col.find(*args, **kwargs), dados, retirar)


class BaseDados:
    """Base Motor em que assistant_docs e assistant_artifacts leem os bytes do Tigris quando lá estão."""

    EMBRULHADAS = ("assistant_docs", "assistant_artifacts")

    def __init__(self, db):
        self._db = db
        self._cols = {n: Colecao(db[n]) for n in self.EMBRULHADAS}

    def __getattr__(self, nome):
        if nome in BaseDados.EMBRULHADAS:
            return self._cols[nome]
        return getattr(self._db, nome)

    def __getitem__(self, nome):
        if nome in BaseDados.EMBRULHADAS:
            return self._cols[nome]
        return self._db[nome]

    @property
    def bruta(self):
        return self._db


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
