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
MIME = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}


def _slug(s: str) -> str:
    from .lingua_ucrania import translit                      # cirílico → latim (nome do ficheiro ucraniano legível)
    s = unicodedata.normalize("NFKD", translit(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:60] or "nota"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _clt_context(args: dict, user: dict) -> dict:
    """Estudo CLT: parâmetros e biblioteca da conta e os pisos revistos (última estimativa da página CLT, ou pisos_json)."""
    import json
    from bim_studio.clt_access import allowed, is_pilot
    from bim_studio.clt_economics import library_merged, merged
    from bim_studio.clt_market import country_of
    from bim_studio.store import get_db, tenant_of
    if not allowed(user):
        raise ValueError("O estudo CLT só está disponível nas contas da app PT.")
    if args.get("empresa") == "clt-rezult" and not is_pilot(user):
        args = {**args, "empresa": None}  # the CLT Rezult branding is dedicated to the pilot account
    db, tenant = get_db(), tenant_of(user)
    params = await db.clt_parameters.find_one({"_id": tenant}) or {}
    library = await db.clt_library.find_one({"_id": tenant}) or {}
    if args.get("pisos_json"):
        try:
            entrada = json.loads(args["pisos_json"])
        except json.JSONDecodeError as exc:
            raise ValueError(f"pisos_json inválido: {exc}") from None
    else:
        last = await db.clt_estimate_inputs.find_one({"_id": tenant}) or {}
        entrada = last.get("body")
    return {**args, "_entrada": entrada, "_parametros": merged(params.get("values")), "_biblioteca": library_merged(library.get("items", {}), country_of(user))}


async def _plan_pdf(doc_id: str, user: dict, db) -> bytes:
    """Bytes of a PDF attached to the Assistant by this user."""
    d = await db.assistant_docs.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not d:
        raise ValueError("Documento não encontrado nesta conta: indica o document_id do PDF dos planos anexado nesta conversa.")
    if d.get("chunk_count"):
        chunks = [c async for c in db.assistant_doc_chunks.find({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0}).sort("index", 1)]
        raw = b"".join(base64.b64decode(c["data_b64"]) for c in chunks)
    else:
        raw = base64.b64decode(d.get("data_b64") or "")
    if raw[:4] != b"%PDF":
        raise ValueError("O documento indicado não é um PDF: os motores CLT leem o PDF vetorial dos planos.")
    return raw


async def _clt_only_context(args: dict, user: dict, conv: dict, db) -> dict:
    """Só CLT: PDF dos planos (se indicado), pisos do estudo CLT desta conversa ou da página CLT, parâmetros e biblioteca da conta."""
    from bim_studio.clt_access import is_pilot
    ctx = await _clt_context({k: v for k, v in args.items() if k != "document_id"}, user)
    if is_pilot(user) and not ctx.get("empresa"):
        ctx["empresa"] = "clt-rezult"
    if is_pilot(user) and not ctx.get("lingua"):
        ctx["lingua"] = "en"                                  # the CLT Rezult account receives its documents in English
    if args.get("document_id"):
        ctx["_pdf"] = await _plan_pdf(args["document_id"], user, db)
    if not args.get("pisos_json"):
        from engines import assistant_clt_agent as agent
        study = await db[agent.COLLECTION].find_one(agent._key(user, conv))
        if study and study.get("pisos"):
            try:
                body, _origins, _hyp = agent.build_input(study, ctx["_parametros"])
                ctx["_entrada"], ctx["_origem"] = body, "paredes lidas no PDF vetorial e pisos definidos no estudo CLT desta conversa"
            except (ValueError, KeyError):
                pass                                          # estudo incompleto: fica a última estimativa da página CLT
    return ctx


async def execute_calc_tool(name: str, args: dict, user: dict, conv: dict, db) -> dict:
    uid, cid = user["user_id"], conv["conversation_id"]
    if name == "clt_so_quantidades":
        try:
            args = await _clt_only_context(args or {}, user, conv, db)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)[:400]}
    if name == "estudo_clt_completo":                          # o resultado depende dos preços atuais: entram no digest
        try:
            doc_id = (args or {}).get("document_id")
            args = await _clt_context({k: v for k, v in (args or {}).items() if k != "document_id"}, user)
            if doc_id:
                args["_pdf"] = await _plan_pdf(doc_id, user, db)
            from bim_studio.clt_access import is_pilot
            if is_pilot(user) and not args.get("lingua"):
                args["lingua"] = "en"                         # the CLT Rezult account receives its documents in English
        except ValueError as exc:
            return {"ok": False, "error": str(exc)[:400]}
    rid = conv.get("_quote_request_id") or cid
    digest = hashlib.sha256((rid + str(conv.get("_file_call_id", "")) + name + repr(sorted((args or {}).items(), key=lambda x: x[0]))).encode()).hexdigest()[:27]
    from engines import calc_live
    # conta seguida ao vivo (CLT Rezult): recalcula sempre, para a página de acompanhamento mostrar o cálculo real
    old = None if calc_live.ativo() else await db.assistant_artifacts.find_one({"artifact_id": "file_" + digest + "n", "user_id": uid}, {"_id": 0, "data_b64": 0})
    if old:
        return {"ok": True, "artifact": {k: old.get(k) for k in ("artifact_id", "title", "filename", "format", "mime", "size", "download")},
                "resume": old.get("body", "")}
    try:
        from . import ucrania as _ua
        _ua.LOOP = asyncio.get_running_loop()               # renders realistas: as chamadas IA correm no loop do servidor
        out = await asyncio.to_thread(run, name, args)
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}
    now, day = _now(), datetime.now().strftime("%Y-%m-%d")
    docs = []
    labs = ("Dossier-UK", "Dossier-UK-preview") if name == "calcul_ucrania" else ("Nota-de-calculo", "Nota-de-calculo-preview")
    for suffix, fmt, data, lab in (("n", "pdf", out["pdf"], labs[0]), ("v", "png", out["png"], labs[1])):
        aid = "file_" + digest + suffix
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": rid, "title": out["titre"], "body": out["resume"],
               "filename": f"ConstruPilot_{lab}_{_slug(out['titre'])}_{day}.{fmt}", "format": fmt, "kind": "calc_note" if fmt == "pdf" else "calc_preview",
               "mime": MIME[fmt], "size": len(data), "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": now,
               "illustrative": False, "calc_note": name, "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        docs.append({k: doc[k] for k in ("artifact_id", "title", "filename", "format", "kind", "mime", "size", "download")})
    extra = []
    for j, (lab, titre_x, data) in enumerate(out.get("pdf_extra") or []):          # dossiers adicionais (p.ex. versão inglesa)
        aid = "file_" + digest + f"e{j + 1}"
        fx = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ("jpg" if data[:3] == b"\xff\xd8\xff" else "pdf")   # fotos 3D: imagens
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": rid, "title": titre_x, "body": out["resume"],
               "filename": f"ConstruPilot_{lab}_{_slug(titre_x)}_{day}.{fx}", "format": fx, "kind": "calc_note" if fx == "pdf" else "calc_preview",
               "mime": MIME.get(fx) or "image/jpeg",
               "size": len(data), "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": now,
               "illustrative": False, "calc_note": name, "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        extra.append({k: doc[k] for k in ("artifact_id", "title", "filename", "format", "kind", "mime", "size", "download")})
    # "artifacts": o cartão de ação do frontend mostra r.artifact + r.artifacts → o dossier inglês aparece por baixo do ucraniano
    return {"ok": True, "artifact": docs[0], "preview_artifact": docs[1], "extra_artifacts": extra, "artifacts": extra, "resume": out["resume"], "data": out["data"],
            "note": "Nota de cálculo produzida pelos motores determinísticos. Restitui os resultados-chave, as não conformidades e as hipóteses "
                    "a validar; não recalcules."}


__all__ = ["CALC_TOOLS", "CALC_TOOL_NAMES", "CALC_INSTRUCTIONS", "CALC_STATUS", "execute_calc_tool"]
