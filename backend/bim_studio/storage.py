"""Armazenamento privado dos ficheiros BIM.

Reutiliza o Object Storage já usado pela plataforma (``engines.object_storage``),
mas sempre sob o prefixo ``pt/bim/<tenant>/<modelo>/v<n>/`` — nenhum caminho
partilhado com outros módulos nem com a França. Os ficheiros nunca são públicos:
só são servidos pela API depois de verificada a organização do utilizador
(ou por URL assinado de curta duração).
"""
from __future__ import annotations

import asyncio
import os
import re

from bim_studio import config

_SAFE = re.compile(r"^[A-Za-z0-9_\-./]+$")


def key_for(tenant_id: str, model_id: str, version: int, name: str) -> str:
    path = f"{config.STORAGE_PREFIX}/{tenant_id}/{model_id}/v{int(version)}/{name}"
    if not _SAFE.match(path) or ".." in path:
        raise ValueError("caminho de armazenamento inválido")
    return path


def _local_path(key: str) -> str:
    root = os.path.realpath(config.LOCAL_STORAGE_DIR)
    p = os.path.realpath(os.path.join(root, key))
    if not p.startswith(root + os.sep):
        raise ValueError("caminho fora do armazenamento")
    return p


def _put_sync(key: str, data: bytes, content_type: str) -> None:
    if config.STORAGE_BACKEND == "local":
        p = _local_path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)
        return
    from engines.object_storage import put_object
    put_object(key, data, content_type)


def _get_sync(key: str) -> bytes:
    if config.STORAGE_BACKEND == "local":
        with open(_local_path(key), "rb") as fh:
            return fh.read()
    from engines.object_storage import get_object
    data, _ = get_object(key)
    return data


async def put(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    await asyncio.to_thread(_put_sync, key, data, content_type)


async def get(key: str) -> bytes:
    return await asyncio.to_thread(_get_sync, key)
