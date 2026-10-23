"""Ponte Assistente (.pt) ↔ motores de cálculo calc_lots: executa a ferramenta, guarda a nota PDF e a pré-visualização PNG como
artefactos da conversa (db.assistant_artifacts, mesmo formato que os outros ficheiros do Assistente) e devolve o resumo ao modelo.

Integração em routes/assistant.py (4 inserções, nada é apagado):
    from engines.calc_lots.assistant_bridge import CALC_TOOLS, CALC_TOOL_NAMES, CALC_INSTRUCTIONS, CALC_STATUS, execute_calc_tool
    TOOLS = [..., *CALC_TOOLS]                                   # a seguir às ferramentas BET
    if name in CALC_TOOL_NAMES: return await execute_calc_tool(name, args, user, conv, db)     # no início de _exec_tool
    instructions += CALC_INSTRUCTIONS ; TOOL_STATUS.update(CALC_STATUS)
Sem IA: os números vêm dos motores determinísticos; ValueError → {"ok": False, "error"} (o modelo pede o dado em falta).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from .outils import CALC_TOOL_NAMES, CALC_TOOLS, PROGRESS_LABELS, PROTOCOL_PT, run

CALC_STATUS = dict(PROGRESS_LABELS)
CALC_INSTRUCTIONS = ("\n\nMOTORES DE CÁLCULO (notas PDF determinísticas): " + PROTOCOL_PT +
                     " A nota PDF e a pré-visualização aparecem AUTOMATICAMENTE como ficheiros descarregáveis por baixo da tua resposta: não "
                     "escrevas ligações nem caminhos. Restitui os resultados-chave, as não conformidades e as hipóteses a validar; não recalcules.")
MIME = {"pdf": "application/pdf", "png": "image/png"}


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:60] or "nota"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def execute_calc_tool(name: str, args: dict, user: dict, conv: dict, db) -> dict:
    uid, cid = user["user_id"], conv["conversation_id"]
    rid = conv.get("_quote_request_id") or cid
    digest = hashlib.sha256((rid + str(conv.get("_file_call_id", "")) + name + repr(sorted((args or {}).items(), key=lambda x: x[0]))).encode()).hexdigest()[:27]
    old = await db.assistant_artifacts.find_one({"artifact_id": "file_" + digest + "n", "user_id": uid}, {"_id": 0, "data_b64": 0})
    if old:
        return {"ok": True, "artifact": {k: old.get(k) for k in ("artifact_id", "title", "filename", "format", "mime", "size", "download")},
                "resume": old.get("body", "")}
    try:
        out = await asyncio.to_thread(run, name, args)
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}
    now, day = _now(), datetime.now().strftime("%Y-%m-%d")
    docs = []
    for suffix, fmt, data, lab in (("n", "pdf", out["pdf"], "Nota-de-calculo"), ("v", "png", out["png"], "Nota-de-calculo-preview")):
        aid = "file_" + digest + suffix
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": rid, "title": out["titre"], "body": out["resume"],
               "filename": f"ConstruPilot_{lab}_{_slug(out['titre'])}_{day}.{fmt}", "format": fmt, "kind": "calc_note" if fmt == "pdf" else "calc_preview",
               "mime": MIME[fmt], "size": len(data), "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": now,
               "illustrative": False, "calc_note": name, "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        docs.append({k: doc[k] for k in ("artifact_id", "title", "filename", "format", "kind", "mime", "size", "download")})
    return {"ok": True, "artifact": docs[0], "preview_artifact": docs[1], "resume": out["resume"], "data": out["data"],
            "note": "Nota de cálculo produzida pelos motores determinísticos. Restitui os resultados-chave, as não conformidades e as hipóteses "
                    "a validar; não recalcules."}


__all__ = ["CALC_TOOLS", "CALC_TOOL_NAMES", "CALC_INSTRUCTIONS", "CALC_STATUS", "execute_calc_tool"]
