"""Envio para o Tigris dos ficheiros pesados com mais de 24 h (anexos e ficheiros gerados). Cada envio é verificado
(tamanho confirmado pelo Tigris) antes de retirar os bytes da base ; em caso de dúvida, o ficheiro fica onde está."""
from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone

from core import armazem as A

log = logging.getLogger("armazem")


async def _bytes_doc(db, d: dict) -> bytes | None:
    if d.get("data_b64"):
        return base64.b64decode(d["data_b64"])
    if d.get("chunk_count"):
        ch = [c async for c in db.assistant_doc_chunks.find({"doc_id": d["doc_id"], "user_id": d.get("user_id")}, {"_id": 0}).sort("index", 1)]
        if [c.get("index") for c in ch] == list(range(d["chunk_count"])):
            return b"".join(base64.b64decode(c["data_b64"]) for c in ch)
    return None


async def descarregar(db=None, max_itens: int = 200, idade_h: float = 24, min_bytes: int = 100_000) -> dict:
    """db = a base bruta (Motor). Devolve {"enviados": n, "bytes": b, "falhas": f, "ignorados": i}."""
    if not A.configurado():
        return {"enviados": 0, "motivo": "Tigris não configurado"}
    if db is None:
        from core.db import db as _db
        db = getattr(_db, "bruta", _db)
    limite = (datetime.now(timezone.utc) - timedelta(hours=idade_h)).isoformat()
    res = {"enviados": 0, "bytes": 0, "falhas": 0, "ignorados": 0}
    for colecao, ident in (("assistant_docs", "doc_id"), ("assistant_artifacts", "artifact_id")):
        q = {"tigris_key": {"$exists": False}, "created_at": {"$lt": limite},
             "$or": [{"data_b64": {"$exists": True, "$ne": ""}}, {"chunk_count": {"$gt": 0}}]}
        async for d in db[colecao].find(q, {"_id": 0, ident: 1, "user_id": 1, "data_b64": 1, "chunk_count": 1, "doc_id": 1}).limit(max_itens):
            try:
                data = await _bytes_doc(db, d) if colecao == "assistant_docs" else (base64.b64decode(d["data_b64"]) if d.get("data_b64") else None)
                if not data or len(data) < min_bytes:
                    res["ignorados"] += 1
                    continue
                k, sha = A.chave(colecao, d.get("user_id"), d[ident]), A.sha256(data)
                n = await asyncio.to_thread(A.enviar, k, data, sha)
                if n != len(data):
                    raise IOError(f"tamanho no Tigris {n} ≠ {len(data)}")
                r = await db[colecao].update_one({ident: d[ident], "user_id": d.get("user_id"), "tigris_key": {"$exists": False}},
                                                 {"$set": {"tigris_key": k, "tigris_size": n, "tigris_sha256": sha, "chunk_count": 0},
                                                  "$unset": {"data_b64": ""}})
                if r.modified_count and colecao == "assistant_docs" and d.get("chunk_count"):
                    await db.assistant_doc_chunks.delete_many({"doc_id": d[ident], "user_id": d.get("user_id")})
                res["enviados"] += 1
                res["bytes"] += n
            except Exception as exc:  # noqa: BLE001 — fica na base ; nova tentativa no ciclo seguinte
                res["falhas"] += 1
                log.warning("armazem: envio falhou (%s) para %s/%s", type(exc).__name__, colecao, d.get(ident))
    return res


async def ciclo(intervalo_s: int = 3600) -> None:
    """Trabalho em segundo plano : de hora a hora, enquanto o Tigris estiver configurado."""
    await asyncio.sleep(120)
    while True:
        try:
            if A.configurado():
                r = await descarregar()
                if r.get("enviados") or r.get("falhas"):
                    log.info("armazem: %s", r)
        except Exception:  # noqa: BLE001
            log.warning("armazem: ciclo falhou", exc_info=True)
        await asyncio.sleep(intervalo_s)


async def apagar_utilizador(user_id: str) -> int:
    """Purga de conta : apaga também os ficheiros do utilizador no Tigris."""
    if not A.configurado():
        return 0
    n = 0
    for p in A.prefixo_utilizador(user_id):
        n += await asyncio.to_thread(A.apagar_prefixo, p)
    return n
