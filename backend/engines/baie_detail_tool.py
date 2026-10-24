"""Ferramenta do Assistente (.pt) « pormenor de montagem de caixilharia » (motor baie_detail, sem IA): corte vertical + corte
horizontal em PNG e PDF guardados como artefactos da conversa (db.assistant_artifacts).

Integração em routes/assistant.py (3 inserções):
    from engines.baie_detail_tool import WINDOW_TOOLS, WINDOW_TOOL_NAMES, WINDOW_INSTRUCTIONS, WINDOW_STATUS, execute_window_tool
    TOOLS = [..., *WINDOW_TOOLS] ; if name in WINDOW_TOOL_NAMES: return await execute_window_tool(name, args, user, conv, db)
    instructions += WINDOW_INSTRUCTIONS ; TOOL_STATUS.update(WINDOW_STATUS)
"""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from . import baie_detail

_T = copy.deepcopy(baie_detail.WINDOW_TOOL)
_T["description"] = (
    "Desenha o PORMENOR DE MONTAGEM de uma caixilharia (janela, porta-janela, porta de correr), com ou sem estore: corte vertical "
    "(peitoril / soleira + topo com padieira e caixa de estore) e corte horizontal (ombreira em planta), à escala, com tramas, legenda "
    "numerada e cotas de reserva calculadas. Usa-a para qualquer pedido de esquema de montagem / assentamento de janela, porta-janela, "
    "estore, caixa de estore ou monobloco. Montagem: applique_int (pelo interior) | tunnel (no vão) | feuillure (em batente) | renovation "
    "(sobre aro existente) | applique_ext (com ETICS); caixa: aucun | monobloc (caixa integrada) | tunnel | interieur | exterieur. "
    "null para uma cota desconhecida (valor corrente assinalado como hipótese). Se a combinação for incompatível, a ferramenta devolve um "
    "erro a reformular como pergunta ao utilizador. lang = \"pt\".")
WINDOW_TOOLS = [_T]
WINDOW_TOOL_NAMES = {_T["name"]}
WINDOW_STATUS = {_T["name"]: "A desenhar o pormenor de montagem da caixilharia…"}
WINDOW_INSTRUCTIONS = ("\n\nPORMENOR DE CAIXILHARIA: para um esquema de montagem de janela, porta-janela, porta de correr, estore ou caixa de "
                       "estore usa draw_window_detail (desenho técnico real, lang \"pt\"). Os 2 cortes e o PDF aparecem automaticamente por "
                       "baixo da resposta: não escrevas ligações. Dá as cotas-chave e as hipóteses a validar.")


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:60] or "pormenor"


async def execute_window_tool(name: str, args: dict, user: dict, conv: dict, db) -> dict:
    uid, cid = user["user_id"], conv["conversation_id"]
    rid = conv.get("_quote_request_id") or cid
    params = {k: v for k, v in (args or {}).items() if v is not None}
    params["lang"] = "pt"
    digest = hashlib.sha256((rid + str(conv.get("_file_call_id", "")) + repr(sorted(params.items()))).encode()).hexdigest()[:27]
    try:
        out = await asyncio.to_thread(baie_detail.render, params)
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": f"{exc}"[:400]}
    now, day = datetime.now(timezone.utc).isoformat(), datetime.now().strftime("%Y-%m-%d")
    body = "\n".join([out["subtitle"]] + [f"{k}: {v}" for k, v in out["key_values"]] + [f"Hipótese / a validar: {n}" for n in out["notes"]])
    docs = []
    for suffix, lab, fmt, mime, data in (("v", "Corte-vertical", "png", "image/png", out["png_vertical"]),
                                         ("h", "Corte-horizontal", "png", "image/png", out["png_horizontal"]),
                                         ("p", "Pormenor-caixilharia", "pdf", "application/pdf", out["pdf"])):
        aid = "file_" + digest + suffix
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": rid, "title": out["title"], "body": body,
               "filename": f"ConstruPilot_{lab}_{_slug(out['title'])}_{day}.{fmt}", "format": fmt, "mime": mime, "size": len(data),
               "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": now, "illustrative": True,
               "vector_schema": True, "schema_args": out["params"], "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        docs.append({k: doc[k] for k in ("artifact_id", "title", "filename", "format", "mime", "size", "download")})
    return {"ok": True, "artifact": docs[0], "horizontal_artifact": docs[1], "pdf_artifact": docs[2], "key_values": out["key_values"],
            "notes": out["notes"], "note": "Pormenor desenhado pelo motor (sem IA): corte vertical + corte horizontal + PDF. Não descrevas o "
                                          "desenho em pormenor; dá as cotas-chave e as hipóteses a validar."}
